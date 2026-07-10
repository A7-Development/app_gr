"""Mapper bronze -> silver do estado da NF-e (SERPRO Consulta NF-e).

Le um snapshot de `wh_serpro_raw_nfe` e materializa:

- `wh_nfe_evento`: 1 linha por evento (append; identidade natural
  tenant+chave+tpEvento+nSeqEvento — re-map nao duplica).
- `wh_nfe_situacao`: upsert da linha unica da chave com o estado derivado.

Regra de perda zero (Ricardo 2026-07-10): alem dos escalares promovidos a
coluna, as subarvores `evento`/`retEvento`/`infProt` vao VERBATIM em JSONB.

Classificador de situacao (validado contra payloads reais 2026-07-10):
- protNFe.cStat da consulta e o da AUTORIZACAO — nota cancelada continua
  com cStat=100. O cancelamento e o EVENTO 110111 com retEvento.cStat
  homologado (135 registrado/vinculado, 136 registrado, 155 homologado
  FORA DE PRAZO).
- Eventos chegam DESORDENADOS no array — ordenacao por dh_evento.
- cStat nao mapeado vira situacao="desconhecida" (nunca falha silenciosa).
"""

from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import SourceType
from app.modules.integracoes.adapters.data.serpro.version import ADAPTER_VERSION
from app.warehouse.nfe_estado import NfeEvento, NfeSituacao
from app.warehouse.serpro_raw_nfe import SerproRawNfe

logger = logging.getLogger(__name__)

# tpEvento -> rotulo canonico de manifestacao do destinatario.
MANIFESTACAO_POR_TIPO = {
    210200: "confirmacao",
    210210: "ciencia",
    210220: "desconhecimento",
    210240: "operacao_nao_realizada",
}

TP_EVENTO_CANCELAMENTO = 110111
# retEvento.cStat que homologam o cancelamento. 155 = fora de prazo.
RET_CSTAT_CANCELAMENTO_OK = {135, 136, 155}

# protNFe.cStat -> situacao base (antes de aplicar eventos).
_SITUACAO_POR_PROT_CSTAT = {
    100: "autorizada",
    150: "autorizada_fora_prazo",
    110: "denegada",
    301: "denegada",
    302: "denegada",
    303: "denegada",
    101: "cancelada",
    151: "cancelada",
    155: "cancelada_fora_prazo",
}


# ---- Coercao defensiva (numeros podem vir como int, str ou notacao) -------


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value))
    except (ValueError, TypeError):
        return None


def _as_str(value: Any, max_len: int | None = None) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    return s[:max_len] if max_len else s


def _as_dt(value: Any) -> datetime | None:
    s = _as_str(value)
    if s is None:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        logger.warning("serpro mapper: timestamp fora do ISO: %r", s)
        return None


def _sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, ensure_ascii=False, default=str).encode()
    ).hexdigest()


# ---- Parse dos eventos ------------------------------------------------------


@dataclass(slots=True)
class _EventoParseado:
    tp_evento: int
    n_seq_evento: int
    dh_evento: datetime | None
    values: dict[str, Any]


def _parse_evento(item: dict[str, Any]) -> _EventoParseado | None:
    """Extrai escalares + subarvores verbatim de um procEventoNFe[i]."""
    evento = item.get("evento") if isinstance(item.get("evento"), dict) else {}
    inf = evento.get("infEvento") if isinstance(evento.get("infEvento"), dict) else {}
    det = inf.get("detEvento") if isinstance(inf.get("detEvento"), dict) else {}
    ret_evento = (
        item.get("retEvento") if isinstance(item.get("retEvento"), dict) else None
    )
    ret = {}
    if ret_evento and isinstance(ret_evento.get("infEvento"), dict):
        ret = ret_evento["infEvento"]

    tp_evento = _as_int(inf.get("tpEvento"))
    if tp_evento is None:
        logger.warning("serpro mapper: evento sem tpEvento — pulado: %s", item)
        return None
    n_seq = _as_int(inf.get("nSeqEvento")) or 1
    dh_evento = _as_dt(inf.get("dhEvento"))

    values: dict[str, Any] = {
        "id_evento": _as_str(inf.get("Id"), 60),
        "c_orgao": _as_str(inf.get("cOrgao"), 2),
        "tp_amb": _as_int(inf.get("tpAmb")),
        "autor_cnpj": _as_str(inf.get("CNPJ"), 14),
        "autor_cpf": _as_str(inf.get("CPF"), 11),
        "dh_evento": dh_evento,
        "tp_evento": tp_evento,
        "n_seq_evento": n_seq,
        "ver_evento": _as_str(inf.get("verEvento"), 10),
        "desc_evento": _as_str(det.get("descEvento"), 120),
        "x_just": _as_str(det.get("xJust")),
        "x_correcao": _as_str(det.get("xCorrecao")),
        "det_n_prot": _as_str(det.get("nProt"), 20),
        "ret_ver_aplic": _as_str(ret.get("verAplic"), 30),
        "ret_c_orgao": _as_str(ret.get("cOrgao"), 2),
        "ret_c_stat": _as_int(ret.get("cStat")),
        "ret_x_motivo": _as_str(ret.get("xMotivo"), 255),
        "ret_x_evento": _as_str(ret.get("xEvento"), 120),
        "ret_cnpj_dest": _as_str(ret.get("CNPJDest"), 14),
        "ret_cpf_dest": _as_str(ret.get("CPFDest"), 11),
        "ret_email_dest": _as_str(ret.get("emailDest"), 120),
        "ret_dh_reg_evento": _as_dt(ret.get("dhRegEvento")),
        "ret_n_prot": _as_str(ret.get("nProt"), 20),
        # Perda zero: subarvores completas, como vieram.
        "evento_json": evento,
        "ret_evento_json": ret_evento,
    }
    return _EventoParseado(
        tp_evento=tp_evento, n_seq_evento=n_seq, dh_evento=dh_evento, values=values
    )


# ---- Classificador de situacao ---------------------------------------------


def classificar_situacao(
    prot_c_stat: int | None, eventos: list[_EventoParseado]
) -> tuple[str, bool, datetime | None]:
    """Deriva (situacao, cancelada, dh_cancelamento) do protocolo + eventos."""
    if prot_c_stat is None:
        situacao = "desconhecida"
    else:
        situacao = _SITUACAO_POR_PROT_CSTAT.get(prot_c_stat, "desconhecida")
        if situacao == "desconhecida":
            logger.warning(
                "serpro mapper: protNFe.cStat=%s sem mapeamento de situacao",
                prot_c_stat,
            )

    cancelada = situacao.startswith("cancelada")
    dh_cancelamento: datetime | None = None

    # Eventos mandam: cancelamento homologado sobrepoe o cStat da autorizacao.
    for ev in eventos:
        if ev.tp_evento != TP_EVENTO_CANCELAMENTO:
            continue
        ret_c_stat = ev.values.get("ret_c_stat")
        if ret_c_stat in RET_CSTAT_CANCELAMENTO_OK:
            cancelada = True
            dh_cancelamento = ev.dh_evento
            situacao = (
                "cancelada_fora_prazo" if ret_c_stat == 155 else "cancelada"
            )
    return situacao, cancelada, dh_cancelamento


def manifestacao_mais_recente(
    eventos: list[_EventoParseado],
) -> tuple[str | None, datetime | None]:
    """Manifestacao do destinatario mais recente por dh_evento.

    Eventos chegam desordenados no array (validado 2026-07-10) — ordena.
    """
    manifestacoes = [
        ev for ev in eventos if ev.tp_evento in MANIFESTACAO_POR_TIPO
    ]
    if not manifestacoes:
        return None, None
    ultimo = max(
        manifestacoes,
        key=lambda ev: (ev.dh_evento is not None, ev.dh_evento, ev.n_seq_evento),
    )
    return MANIFESTACAO_POR_TIPO[ultimo.tp_evento], ultimo.dh_evento


# ---- Entry point ------------------------------------------------------------


@dataclass(slots=True)
class MapResult:
    chave: str
    situacao: str
    eventos_novos: int
    qtd_eventos: int


async def mapear_snapshot(db: AsyncSession, raw: SerproRawNfe) -> MapResult:
    """Materializa um snapshot do bronze no silver (idempotente).

    Commit e do caller (compoe com o ETL na mesma transacao).
    """
    payload: dict[str, Any] = raw.payload or {}
    nfe_proc = payload.get("nfeProc") if isinstance(payload.get("nfeProc"), dict) else {}
    prot = nfe_proc.get("protNFe") if isinstance(nfe_proc.get("protNFe"), dict) else {}
    inf_prot = prot.get("infProt") if isinstance(prot.get("infProt"), dict) else {}
    eventos_raw = payload.get("procEventoNFe") or payload.get("procEventosNFe")
    eventos_list = eventos_raw if isinstance(eventos_raw, list) else []

    eventos = [
        parsed
        for item in eventos_list
        if isinstance(item, dict) and (parsed := _parse_evento(item)) is not None
    ]

    # ---- wh_nfe_evento (append, identidade natural) ----
    eventos_novos = 0
    for ev in eventos:
        stmt = (
            pg_insert(NfeEvento)
            .values(
                tenant_id=raw.tenant_id,
                raw_id=raw.id,
                chave_acesso=raw.chave_acesso,
                **ev.values,
                source_type=SourceType.DATA_SERPRO_NFE,
                source_id=(
                    f"{raw.chave_acesso}:{ev.tp_evento}:{ev.n_seq_evento}"
                ),
                source_updated_at=ev.values.get("ret_dh_reg_evento"),
                hash_origem=_sha(ev.values["evento_json"]),
                ingested_by_version=ADAPTER_VERSION,
            )
            .on_conflict_do_nothing(constraint="uq_wh_nfe_evento_identidade")
            .returning(NfeEvento.id)
        )
        if (await db.execute(stmt)).scalar_one_or_none() is not None:
            eventos_novos += 1

    # ---- wh_nfe_situacao (upsert da linha unica) ----
    prot_c_stat = _as_int(inf_prot.get("cStat"))
    situacao, cancelada, dh_cancelamento = classificar_situacao(
        prot_c_stat, eventos
    )
    manifestacao, dh_manifestacao = manifestacao_mais_recente(eventos)
    dh_ultimo_evento = max(
        (ev.dh_evento for ev in eventos if ev.dh_evento is not None),
        default=None,
    )

    values = {
        "tenant_id": raw.tenant_id,
        "last_raw_id": raw.id,
        "chave_acesso": raw.chave_acesso,
        "nfe_proc_versao": _as_str(nfe_proc.get("versao"), 8),
        "prot_tp_amb": _as_int(inf_prot.get("tpAmb")),
        "prot_ver_aplic": _as_str(inf_prot.get("verAplic"), 30),
        "prot_dh_recbto": _as_dt(inf_prot.get("dhRecbto")),
        "prot_n_prot": _as_str(inf_prot.get("nProt"), 20),
        "prot_dig_val": _as_str(inf_prot.get("digVal"), 44),
        "prot_c_stat": prot_c_stat,
        "prot_x_motivo": _as_str(inf_prot.get("xMotivo"), 255),
        "prot_id": _as_str(inf_prot.get("Id"), 60),
        "prot_json": inf_prot or None,
        "situacao": situacao,
        "cancelada": cancelada,
        "dh_cancelamento": dh_cancelamento,
        "manifestacao": manifestacao,
        "dh_manifestacao": dh_manifestacao,
        "qtd_eventos": len(eventos),
        "dh_ultimo_evento": dh_ultimo_evento,
        "consultado_em": raw.fetched_at,
        "source_type": SourceType.DATA_SERPRO_NFE,
        "source_id": raw.chave_acesso,
        "source_updated_at": raw.fetched_at,
        "hash_origem": raw.payload_sha256,
        "ingested_by_version": ADAPTER_VERSION,
    }
    stmt = pg_insert(NfeSituacao).values(**values)
    stmt = stmt.on_conflict_do_update(
        constraint="uq_wh_nfe_situacao_tenant_chave",
        set_={
            k: stmt.excluded[k]
            for k in values
            if k not in ("tenant_id", "chave_acesso")
        }
        | {"ingested_at": sa.func.now()},
    )
    await db.execute(stmt)
    await db.flush()

    logger.info(
        "serpro silver chave=%s situacao=%s eventos=%d (novos=%d)",
        raw.chave_acesso,
        situacao,
        len(eventos),
        eventos_novos,
    )
    return MapResult(
        chave=raw.chave_acesso,
        situacao=situacao,
        eventos_novos=eventos_novos,
        qtd_eventos=len(eventos),
    )


async def remapear_chave(
    db: AsyncSession, *, tenant_id: UUID, chave: str
) -> MapResult | None:
    """Re-mapeia a chave a partir do snapshot MAIS RECENTE do bronze."""
    raw = (
        await db.execute(
            sa.select(SerproRawNfe)
            .where(
                SerproRawNfe.tenant_id == tenant_id,
                SerproRawNfe.chave_acesso == chave,
            )
            .order_by(SerproRawNfe.fetched_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if raw is None:
        return None
    return await mapear_snapshot(db, raw)
