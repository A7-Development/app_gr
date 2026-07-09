"""Orquestrador de sync da cobranca (CNAB -> bronze -> wh_boleto).

A pasta de retornos e uma INBOX com arquivos de varios bancos misturados. O
banco se descobre lendo o header de cada arquivo (`detect.detectar_banco`),
nao o nome nem a config. Fluxo por execucao de um `tenant_source_config`
generico de cobranca (source_type COBRANCA):

    FileSource.fetch -> por arquivo: classifica (retorno/remessa) -> detecta
    banco -> land bronze (sha) -> [retorno de banco com parser] parse ->
    persist ocorrencias -> map -> upsert wh_boleto

Tudo pousa no bronze (bronze-now), inclusive remessa e banco nao reconhecido.
So vira wh_boleto o retorno de banco cujo parser ja existe (`_LAYOUTS`).
Adicionar banco = +1 entrada em `detect._POR_CODIGO` + parser + `_LAYOUTS`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.enums import Environment, SourceType
from app.modules.integracoes.adapters.cobranca.bradesco import (
    estado_from_codigo as bradesco_estado_from_codigo,
)
from app.modules.integracoes.adapters.cobranca.bradesco import (
    parse_remessa as bradesco_parse_remessa,
)
from app.modules.integracoes.adapters.cobranca.bradesco import (
    parse_retorno as bradesco_parse_retorno,
)
from app.modules.integracoes.adapters.cobranca.decode_evento import (
    decode_tenant_eventos,
)
from app.modules.integracoes.adapters.cobranca.detect import detectar_banco
from app.modules.integracoes.adapters.cobranca.landing import land_cnab_arquivo
from app.modules.integracoes.adapters.cobranca.mappers.boleto import (
    map_ocorrencias_to_boletos,
    parse_ddmmaa,
)
from app.modules.integracoes.adapters.cobranca.persist import (
    persist_ocorrencias,
    upsert_boletos,
)
from app.modules.integracoes.adapters.cobranca.project_vigente import (
    project_tenant_vigente,
)
from app.modules.integracoes.adapters.cobranca.resolve_titulo import resolve_titulo_ids
from app.modules.integracoes.adapters.cobranca.version import ADAPTER_VERSION
from app.modules.integracoes.filesource import get_file_source
from app.modules.integracoes.models.file_landing import FileLanding
from app.warehouse.cnab_raw_arquivo import (
    BANCO_DESCONHECIDO,
    TIPO_ARQUIVO_REMESSA,
    TIPO_ARQUIVO_RETORNO,
)
from app.warehouse.cobranca_sync_run import (
    SYNC_FASE_COLETA,
    SYNC_FASE_DECODE,
    SYNC_FASE_DONE,
    SYNC_FASE_PROJECT,
    SYNC_STATUS_ERROR,
    SYNC_STATUS_OK,
    CobrancaSyncRun,
)

# Layout -> (parser de retorno, decoder de estado). Adicionar banco = +1 aqui
# + o parser do banco + a entrada em detect._POR_CODIGO.
_LAYOUTS = {
    "cnab400_bradesco": {
        "parse_retorno": bradesco_parse_retorno,
        "parse_remessa": bradesco_parse_remessa,
        "estado_resolver": bradesco_estado_from_codigo,
    },
    # BMP (274) e Vortx (310) usam o MESMO CNAB400-padrao FEBRABAN do Bradesco:
    # posicoes do registro de detalhe identicas (nosso 71-82, ocorrencia 109-110,
    # documento 117-126, venc 147-152, valor 153-165) e mesmos codigos de
    # ocorrencia. Validado 2026-06-06 contra os arquivos reais (100% dos detalhes
    # cruzam wh_titulo pelo documento). Reaproveitam o parser e o decoder.
    "cnab400_bmp": {
        "parse_retorno": bradesco_parse_retorno,
        "parse_remessa": bradesco_parse_remessa,
        "estado_resolver": bradesco_estado_from_codigo,
    },
    "cnab400_vortx": {
        "parse_retorno": bradesco_parse_retorno,
        "parse_remessa": bradesco_parse_remessa,
        "estado_resolver": bradesco_estado_from_codigo,
    },
}


@dataclass
class CobrancaSyncResult:
    arquivos_vistos: int = 0
    arquivos_novos: int = 0
    arquivos_duplicados: int = 0
    arquivos_sem_banco: int = 0  # retorno com banco nao reconhecido
    arquivos_sem_parser: int = 0  # banco reconhecido mas parser nao implementado
    ocorrencias_gravadas: int = 0
    boletos_upsertados: int = 0
    ocorrencias_ignoradas: int = 0
    remessas_processadas: int = 0  # remessas (registro) parseadas -> bronze


def _classificar_tipo(conteudo: str) -> str:
    """Classifica o arquivo como retorno ou remessa pelo header CNAB."""
    head = conteudo[:120].upper()
    if "RETORNO" in head:
        return TIPO_ARQUIVO_RETORNO
    return TIPO_ARQUIVO_REMESSA


async def sync_cobranca(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    config: dict,
    commit: bool = True,
) -> CobrancaSyncResult:
    """Roda um ciclo de sync de cobranca para um tenant_source_config (inbox).

    `config` e o `tenant_source_config.config` (jsonb decifrado) com
    `file_source` (mode/path/glob...). `tenant_id` vem da linha do
    tenant_source_config (explicito -- regra multitenant).
    """
    fs_cfg = config["file_source"]
    fs = get_file_source(fs_cfg["mode"])
    raws = await fs.fetch(fs_cfg, db=db, tenant_id=tenant_id)

    result = CobrancaSyncResult(arquivos_vistos=len(raws))
    fetched_at = datetime.now(UTC)
    # Registros da landing zone a marcar como consumidos ao fim do ciclo.
    # Duplicado tambem consome: o conteudo JA esta no bronze (ex.: ingerido
    # antes pelo mount legado) — pendencia resolvida do mesmo jeito.
    consumed_landing_ids: set[UUID] = set()

    for raw in raws:
        tipo = _classificar_tipo(raw.conteudo)
        # Deteccao header-based vale para remessa E retorno (mesmas posicoes no
        # header CNAB). Remessa segue so-bronze (parse-later), mas ja gravada
        # com o banco correto -- nao mais "desconhecido".
        det = detectar_banco(raw.conteudo)
        banco = det.banco if det else BANCO_DESCONHECIDO
        layout = det.layout if det else "desconhecido"

        # Parseia retorno E remessa de banco reconhecido (precisamos do data_ref
        # do header para gravar no bronze; remessa usa o data_ref como data do
        # evento "instrucao enviada" no decode). Layouts diferentes -> parser por
        # tipo (parse_retorno vs parse_remessa), ambos no mesmo `spec`.
        parsed = None
        data_ref = None
        spec = _LAYOUTS.get(layout) if det else None
        if det is not None and spec is not None:
            parser = (
                spec["parse_retorno"]
                if tipo == TIPO_ARQUIVO_RETORNO
                else spec["parse_remessa"]
            )
            parsed = parser(raw.conteudo)
            data_ref = parse_ddmmaa(parsed.data_ref_raw)

        arquivo, created = await land_cnab_arquivo(
            db,
            tenant_id=tenant_id,
            banco=banco,
            tipo_arquivo=tipo,
            layout=layout,
            raw=raw,
            fetched_at=fetched_at,
        )
        if raw.landing_id is not None:
            consumed_landing_ids.add(raw.landing_id)
        if created and data_ref is not None:
            arquivo.data_ref = data_ref

        if not created:
            result.arquivos_duplicados += 1
            continue
        result.arquivos_novos += 1

        if det is None:
            # Banco nao reconhecido: so bronze (vale p/ remessa e retorno).
            if tipo == TIPO_ARQUIVO_RETORNO:
                result.arquivos_sem_banco += 1
            continue
        if spec is None:
            if tipo == TIPO_ARQUIVO_RETORNO:
                result.arquivos_sem_parser += 1
            continue  # banco reconhecido, parser ainda nao implementado
        if parsed is None or data_ref is None:
            continue  # sem data de referencia legivel no header

        # Ocorrencias -> bronze (vale p/ remessa e retorno; o decode separa por
        # tipo_arquivo e gera a timeline com a origem certa).
        result.ocorrencias_gravadas += await persist_ocorrencias(
            db, arquivo=arquivo, ocorrencias=parsed.ocorrencias, fetched_at=fetched_at
        )

        if tipo == TIPO_ARQUIVO_REMESSA:
            # Remessa NAO popula o wh_boleto by-date (caminho legado). Segue so
            # ate o bronze; vira timeline (evento "enviado") no decode->project.
            result.remessas_processadas += 1
            continue

        values, ignorados = map_ocorrencias_to_boletos(
            [(o.linha_num, o.payload) for o in parsed.ocorrencias],
            tenant_id=tenant_id,
            banco=det.banco,
            data_ref=data_ref,
            source_type=det.source_type,
            estado_resolver=spec["estado_resolver"],
            ingested_by_version=ADAPTER_VERSION,
            arquivo_id=arquivo.id,
        )
        result.ocorrencias_ignoradas += ignorados
        result.boletos_upsertados += await upsert_boletos(db, values)

    if consumed_landing_ids:
        await db.execute(
            update(FileLanding)
            .where(
                FileLanding.tenant_id == tenant_id,
                FileLanding.id.in_(consumed_landing_ids),
                FileLanding.consumed_at.is_(None),
            )
            .values(consumed_at=fetched_at)
        )

    if commit:
        await db.commit()
    return result


async def _run_update(run_id: UUID | None, **fields: Any) -> None:
    """Atualiza a linha de `wh_cobranca_sync_run` numa sessao CURTA (commit
    imediato) -- assim o polling do front enxerga o progresso em tempo real,
    sem esperar a transacao longa do ciclo. `heartbeat_at` sempre atualiza."""
    if run_id is None:
        return
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(CobrancaSyncRun)
            .where(CobrancaSyncRun.id == run_id)
            .values(heartbeat_at=datetime.now(UTC), **fields)
        )
        await db.commit()


async def run_cobranca_manual_sync(
    tenant_id: UUID, run_id: UUID | None = None
) -> dict[str, Any]:
    """Ciclo manual completo de cobranca (botao da pagina banco-cobrador).

    Por TENANT (banco e UA saem dos arquivos/titulos -- nao se define UA):
      1. coleta os arquivos da inbox -> bronze + ocorrencias (`sync_cobranca`);
      2. decodifica o bronze -> timeline (`decode_tenant_eventos`);
      3. projeta a timeline -> estado vigente (`project_tenant_vigente`).

    `run_id`: quando dado, atualiza a fase/heartbeat e o status final em
    `wh_cobranca_sync_run` (observabilidade do botao). Le a config 'cobranca' do
    `tenant_source_config`. Idempotente (dedup por sha; upsert; reprojecao).
    """
    # Import lazy: source_config service nao depende do adapter, mas mantemos
    # localizado para nao alargar o import-time deste modulo.
    from app.modules.integracoes.services.source_config import get_decrypted_config

    try:
        async with AsyncSessionLocal() as db:
            config = await get_decrypted_config(
                db, tenant_id, SourceType.COBRANCA, Environment.PRODUCTION
            )
            if config is None:
                raise ValueError(
                    "Fonte 'cobranca' nao configurada para o tenant "
                    "(rode seed_cobranca_source.py)."
                )
            await _run_update(run_id, fase=SYNC_FASE_COLETA)
            coleta = await sync_cobranca(
                db, tenant_id=tenant_id, config=config, commit=True
            )
            await _run_update(
                run_id,
                fase=SYNC_FASE_DECODE,
                arquivos_vistos=coleta.arquivos_vistos,
                arquivos_novos=coleta.arquivos_novos,
            )
            eventos = await decode_tenant_eventos(db, tenant_id=tenant_id)
            # Resolve a identidade estavel do titulo (nao nosso_numero, que
            # colide entre cedentes) — espinha de identidade (2026-07-09).
            await resolve_titulo_ids(db, tenant_id)
            await _run_update(run_id, fase=SYNC_FASE_PROJECT)
            vigente = await project_tenant_vigente(db, tenant_id=tenant_id)
    except Exception as e:
        await _run_update(
            run_id,
            status=SYNC_STATUS_ERROR,
            fase=None,
            finished_at=datetime.now(UTC),
            erro=str(e)[:2000],
        )
        raise

    await _run_update(
        run_id,
        status=SYNC_STATUS_OK,
        fase=SYNC_FASE_DONE,
        finished_at=datetime.now(UTC),
        boletos_ativos=vigente["ativos"],
    )
    return {"coleta": asdict(coleta), "eventos": eventos, "vigente": vigente}
