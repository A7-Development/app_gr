"""Decode bronze CNAB -> wh_boleto_evento (timeline silver). Fatia 2 do rebuild.

Le as ocorrencias do bronze (`wh_cnab_raw_ocorrencia`) + o header do arquivo
(`wh_cnab_raw_arquivo.conteudo`, de onde sai a UA), decodifica cada codigo em
evento canonico e faz upsert idempotente em `wh_boleto_evento` (por
`ocorrencia_id` -- 1:1 com o bronze).

Decodifica RETORNO e REMESSA:
  - RETORNO: `decode_ocorrencia` (cod de ocorrencia -> evento confirmado pelo
    banco). Data do evento = data da ocorrencia (payload). origem=retorno.
  - REMESSA: `decode_comando_remessa` (comando -> instrucao que ENVIAMOS;
    01=registro -> EFEITO_ENVIA). Data do evento = data de geracao do arquivo
    (`arquivo.data_ref`, do header) -- a remessa nao tem data por registro.
    origem=remessa. A UA da remessa NAO vem do header (la e o cedente, nao o
    fundo) -- fica None e o fold a resolve pelo titulo (_enriquecer_ua).

Re-rodar e seguro: o upsert atualiza so os campos decodificados (tipo/efeito/
UA/versao); os campos vindos do bronze imutavel ficam. Bumpar `DECODER_VERSION`
e re-rodar reprocessa a timeline inteira sem re-ingerir nada.

UA (retorno): resolvida do nome da empresa no header CNAB (pos 47-76) casado
contra `wh_dim_unidade_administrativa` (token match) -- grava o nome CANONICO
da dim, pra casar com o lado titulo da conciliacao.
"""

from __future__ import annotations

import unicodedata
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.adapters.cobranca.eventos import (
    DECODER_VERSION,
    decode_comando_remessa,
    decode_ocorrencia,
)
from app.modules.integracoes.adapters.cobranca.mappers.boleto import (
    _parse_centavos,
    parse_ddmmaa,
)
from app.warehouse.boleto_evento import (
    ORIGEM_REMESSA,
    ORIGEM_RETORNO,
    BoletoEvento,
)
from app.warehouse.cnab_raw_arquivo import (
    TIPO_ARQUIVO_REMESSA,
    TIPO_ARQUIVO_RETORNO,
    CnabRawArquivo,
)
from app.warehouse.cnab_raw_ocorrencia import CnabRawOcorrencia
from app.warehouse.dim import DimUnidadeAdministrativa

_CHUNK = 1000
_LINE_WIDTH = 400

# Campos atualizados no conflito (decode pode mudar; bronze nao).
_UPDATE_COLS = (
    "ua_id",
    "ua_nome",
    "tipo_evento",
    "efeito_estado",
    "decoded_at",
    "decoded_by_version",
)


def _records(conteudo: str) -> list[str]:
    """Quebra o CNAB em registros (por linha, ou chunk de 400 se sem newline)."""
    if "\n" in conteudo:
        return [r.rstrip("\r\n") for r in conteudo.split("\n")]
    return [conteudo[i : i + _LINE_WIDTH] for i in range(0, len(conteudo), _LINE_WIDTH)]


def _header_empresa(conteudo: str) -> str | None:
    """Nome da empresa no header (registro tipo 0), pos 47-76 (1-based)."""
    for r in _records(conteudo):
        if r[:1] == "0" and len(r) >= 76:
            return r[46:76].strip() or None
    return None


def _norm(s: str) -> str:
    """Uppercase sem acento, espacos colapsados."""
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.upper().split())


def _resolve_ua(
    empresa: str | None, uas: list[tuple[int, str]]
) -> tuple[int | None, str | None]:
    """(ua_id, nome canonico da dim) a partir do nome da empresa do header.

    Casa o primeiro token (>=2 chars) do nome da dim contra o header; em empate,
    vence o token mais longo (mais especifico). Sem match -> (None, None).
    """
    if not empresa:
        return None, None
    h = _norm(empresa)
    melhor: tuple[int, str] | None = None
    melhor_len = 0
    for ua_id, nome in uas:
        tokens = _norm(nome).split()
        token = tokens[0] if tokens else ""
        if len(token) >= 2 and token in h and len(token) > melhor_len:
            melhor = (ua_id, nome)
            melhor_len = len(token)
    if melhor is None:
        return None, None
    return melhor[0], melhor[1]


async def decode_tenant_eventos(
    db: AsyncSession, *, tenant_id: UUID, banco: str | None = None
) -> dict[str, int]:
    """Decodifica o bronze de retorno + remessa do tenant para `wh_boleto_evento`.

    Returns {arquivos, ocorrencias, eventos, sem_ua}.
    """
    uas = [
        (row.ua_id, row.nome)
        for row in (
            await db.execute(
                select(
                    DimUnidadeAdministrativa.ua_id, DimUnidadeAdministrativa.nome
                ).where(DimUnidadeAdministrativa.tenant_id == tenant_id)
            )
        ).all()
    ]

    arq_stmt = select(CnabRawArquivo).where(
        CnabRawArquivo.tenant_id == tenant_id,
        CnabRawArquivo.tipo_arquivo.in_(
            [TIPO_ARQUIVO_RETORNO, TIPO_ARQUIVO_REMESSA]
        ),
    )
    if banco is not None:
        arq_stmt = arq_stmt.where(CnabRawArquivo.banco == banco)
    arquivos = (await db.execute(arq_stmt)).scalars().all()

    decoded_at = datetime.now(UTC)
    n_arq = n_oc = n_ev = n_sem_ua = 0
    pending: list[dict[str, Any]] = []

    async def _flush() -> None:
        for i in range(0, len(pending), _CHUNK):
            chunk = pending[i : i + _CHUNK]
            stmt = pg_insert(BoletoEvento).values(chunk)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_wh_boleto_evento_ocorrencia",
                set_={c: getattr(stmt.excluded, c) for c in _UPDATE_COLS},
            )
            await db.execute(stmt)
        pending.clear()

    for arq in arquivos:
        n_arq += 1
        is_remessa = arq.tipo_arquivo == TIPO_ARQUIVO_REMESSA
        # Remessa: a UA do header CNAB e o cedente/beneficiario, nao o fundo --
        # nao confiavel. Fica None; o fold a resolve pelo titulo. Retorno: header
        # carrega o nome do fundo -> casa com a dim de UA.
        if is_remessa:
            ua_id, ua_nome = None, None
        else:
            ua_id, ua_nome = _resolve_ua(_header_empresa(arq.conteudo), uas)
            if ua_id is None:
                n_sem_ua += 1
        ocorrencias = (
            await db.execute(
                select(CnabRawOcorrencia).where(
                    CnabRawOcorrencia.arquivo_id == arq.id
                )
            )
        ).scalars().all()
        for o in ocorrencias:
            n_oc += 1
            p = o.payload
            numero = (p.get("numero_documento") or "").strip()
            nosso = (p.get("nosso_numero") or "").strip() or numero
            if not numero and not nosso:
                continue  # sem identidade -> nao entra na timeline
            codigo = (p.get("codigo_ocorrencia") or "").strip()
            if is_remessa:
                # Remessa nao tem data por registro: o evento "instrucao enviada"
                # data da geracao do arquivo (header -> arquivo.data_ref).
                tipo, efeito = decode_comando_remessa(arq.banco, codigo)
                data_ocorrencia = arq.data_ref
                origem = ORIGEM_REMESSA
            else:
                tipo, efeito = decode_ocorrencia(arq.banco, codigo)
                data_ocorrencia = parse_ddmmaa(p.get("data_ocorrencia"))
                origem = ORIGEM_RETORNO
            if data_ocorrencia is None:
                continue  # sem data nao posiciona na timeline (NOT NULL)
            pending.append(
                {
                    "id": uuid4(),
                    "tenant_id": tenant_id,
                    "banco_origem": arq.banco,
                    "ua_id": ua_id,
                    "ua_nome": ua_nome,
                    "nosso_numero": nosso,
                    "numero_documento": numero or nosso,
                    "sacado_documento": (p.get("sacado_documento") or "").strip() or None,
                    "sacado_nome": (p.get("sacado_nome") or "").strip() or None,
                    "codigo_ocorrencia": codigo,
                    "tipo_evento": tipo,
                    "efeito_estado": efeito,
                    "data_ocorrencia": data_ocorrencia,
                    "data_vencimento": parse_ddmmaa(p.get("data_vencimento")),
                    "valor_titulo": _parse_centavos(p.get("valor_titulo")),
                    "valor_pago": _parse_centavos(p.get("valor_pago")),
                    "data_pagamento": parse_ddmmaa(p.get("data_pagamento")),
                    "origem": origem,
                    "arquivo_id": arq.id,
                    "ocorrencia_id": o.id,
                    "decoded_at": decoded_at,
                    "decoded_by_version": DECODER_VERSION,
                }
            )
            n_ev += 1
            if len(pending) >= _CHUNK:
                await _flush()

    await _flush()
    await db.commit()
    return {
        "arquivos": n_arq,
        "ocorrencias": n_oc,
        "eventos": n_ev,
        "sem_ua": n_sem_ua,
    }
