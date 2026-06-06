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

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.adapters.cobranca.bradesco import (
    estado_from_codigo as bradesco_estado_from_codigo,
)
from app.modules.integracoes.adapters.cobranca.bradesco import (
    parse_retorno as bradesco_parse_retorno,
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
from app.modules.integracoes.adapters.cobranca.version import ADAPTER_VERSION
from app.modules.integracoes.filesource import get_file_source
from app.warehouse.cnab_raw_arquivo import (
    BANCO_DESCONHECIDO,
    TIPO_ARQUIVO_REMESSA,
    TIPO_ARQUIVO_RETORNO,
)

# Layout -> (parser de retorno, decoder de estado). Adicionar banco = +1 aqui
# + o parser do banco + a entrada em detect._POR_CODIGO.
_LAYOUTS = {
    "cnab400_bradesco": {
        "parse_retorno": bradesco_parse_retorno,
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
    raws = await fs.fetch(fs_cfg)

    result = CobrancaSyncResult(arquivos_vistos=len(raws))
    fetched_at = datetime.now(UTC)

    for raw in raws:
        tipo = _classificar_tipo(raw.conteudo)
        # Deteccao header-based vale para remessa E retorno (mesmas posicoes no
        # header CNAB). Remessa segue so-bronze (parse-later), mas ja gravada
        # com o banco correto -- nao mais "desconhecido".
        det = detectar_banco(raw.conteudo)
        banco = det.banco if det else BANCO_DESCONHECIDO
        layout = det.layout if det else "desconhecido"

        # Para retorno reconhecido, ja parseia (precisamos do data_ref do header
        # para gravar no bronze + mapear).
        parsed = None
        data_ref = None
        spec = _LAYOUTS.get(layout) if det else None
        if det is not None and spec is not None:
            parsed = spec["parse_retorno"](raw.conteudo)
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
        if created and data_ref is not None:
            arquivo.data_ref = data_ref

        if not created:
            result.arquivos_duplicados += 1
            continue
        result.arquivos_novos += 1

        if tipo != TIPO_ARQUIVO_RETORNO:
            continue  # remessa: so bronze (parse-later)
        if det is None:
            result.arquivos_sem_banco += 1
            continue  # banco nao reconhecido: so bronze
        if spec is None:
            result.arquivos_sem_parser += 1
            continue  # banco reconhecido, parser ainda nao implementado
        if parsed is None or data_ref is None:
            continue  # retorno sem data de referencia legivel

        result.ocorrencias_gravadas += await persist_ocorrencias(
            db, arquivo=arquivo, ocorrencias=parsed.ocorrencias, fetched_at=fetched_at
        )
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

    if commit:
        await db.commit()
    return result
