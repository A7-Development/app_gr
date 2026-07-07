"""ETL da referencia Bacen: STR -> ref_bacen_instituicao; Informes_Agencias ->
ref_bacen_agencia.

Upsert SEM delete: agencia/instituicao que sai do snapshot do Bacen permanece
na ref (o acervo CNAB historico referencia agencias extintas). Re-rodar e
idempotente; a coluna `posicao`/`fetched_at` marca a ultima vez vista.

Segmento da instituicao: heuristica deterministica sobre o nome extenso do STR
(testada em tests/). Refinamento via BcBase/EntidadesSupervisionadas e
follow-up -- a heuristica cobre o que o classificador de canal precisa
(cooperativo / IP / SCD / banco).
"""

from __future__ import annotations

import logging
import re
import unicodedata
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.adapters.data.bacen.client import (
    fetch_agencias,
    fetch_participantes_str,
)
from app.modules.integracoes.adapters.data.bacen.version import ADAPTER_VERSION
from app.warehouse.ref_bacen import (
    SEGMENTO_BANCO,
    SEGMENTO_BANCO_COOPERATIVO,
    SEGMENTO_COOPERATIVA,
    SEGMENTO_FINANCEIRA,
    SEGMENTO_IP,
    SEGMENTO_OUTROS,
    SEGMENTO_SCD,
    RefBacenAgencia,
    RefBacenInstituicao,
)

logger = logging.getLogger(__name__)

_CHUNK = 1000


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.upper().split())


def inferir_segmento(nome_extenso: str, nome_reduzido: str = "") -> str:
    """Segmento canonico a partir do nome oficial (heuristica deterministica).

    Ordem importa: "BANCO COOPERATIVO SICOOB" contem "BANCO" -- o teste de
    cooperativo vem antes do de banco.
    """
    n = _norm(f"{nome_extenso} {nome_reduzido}")
    if "BANCO COOPERATIVO" in n or "BCO COOPERATIVO" in n:
        return SEGMENTO_BANCO_COOPERATIVO
    if "COOPERATIV" in n:  # cooperativa / cooperativo de credito
        return SEGMENTO_COOPERATIVA
    if "INSTITUICAO DE PAGAMENTO" in n or re.search(r"\bIP\b", n):
        return SEGMENTO_IP
    if "SOCIEDADE DE CREDITO DIRETO" in n or re.search(r"\bSCD\b", n):
        return SEGMENTO_SCD
    if "CREDITO, FINANCIAMENTO" in n or "FINANCEIRA" in n:
        return SEGMENTO_FINANCEIRA
    # "ITAU UNIBANCO S.A." nao contem "BANCO" isolado; "CAIXA ECONOMICA" idem.
    if (
        re.search(r"\bBANCO\b|\bBCO\b", n)
        or "UNIBANCO" in n
        or "CAIXA ECONOMICA" in n
    ):
        return SEGMENTO_BANCO
    return SEGMENTO_OUTROS


def _parse_data_br(v: str | None) -> Any:
    """DD/MM/YYYY -> date (None se vazio/invalido)."""
    from datetime import datetime as dt

    v = (v or "").strip()
    if not v:
        return None
    try:
        return dt.strptime(v, "%d/%m/%Y").date()
    except ValueError:
        return None


def _pad_agencia(v: Any) -> str | None:
    """Codigo de agencia normalizado a 5 digitos zero-padded (formato CNAB)."""
    s = str(v or "").strip()
    if not s or not s.isdigit() or int(s) == 0:
        return None
    return s.zfill(5)


async def sync_instituicoes(db: AsyncSession) -> dict[str, int]:
    """STR -> ref_bacen_instituicao. Returns metricas."""
    rows = await fetch_participantes_str()
    fetched_at = datetime.now(UTC)
    values: list[dict[str, Any]] = []
    vistos: set[str] = set()
    for r in rows:
        codigo = (r.get("Número_Código") or "").strip()
        if not codigo or not codigo.isdigit() or codigo in vistos:
            continue  # sem codigo Compe = inalcancavel via CNAB; dup = 1a vence
        vistos.add(codigo)
        nome_ext = (r.get("Nome_Extenso") or "").strip()
        nome_red = (r.get("Nome_Reduzido") or "").strip()
        values.append(
            {
                "codigo_compe": codigo.zfill(3),
                "ispb": (r.get("ISPB") or "").strip().zfill(8),
                "nome_reduzido": nome_red[:120],
                "nome_extenso": nome_ext[:255] or None,
                "participa_compe": _norm(r.get("Participa_da_Compe") or "") == "SIM",
                "segmento": inferir_segmento(nome_ext, nome_red),
                "segmento_fonte": "heuristica_nome",
                "inicio_operacao": _parse_data_br(r.get("Início_da_Operação")),
                "fetched_at": fetched_at,
                "fetched_by_version": ADAPTER_VERSION,
            }
        )
    for i in range(0, len(values), _CHUNK):
        stmt = pg_insert(RefBacenInstituicao).values(values[i : i + _CHUNK])
        stmt = stmt.on_conflict_do_update(
            index_elements=["codigo_compe"],
            set_={
                c: getattr(stmt.excluded, c)
                for c in (
                    "ispb", "nome_reduzido", "nome_extenso", "participa_compe",
                    "segmento", "segmento_fonte", "inicio_operacao",
                    "fetched_at", "fetched_by_version",
                )
            },
        )
        await db.execute(stmt)
    logger.info("ref_bacen_instituicao: %d upserts", len(values))
    return {"instituicoes": len(values)}


async def sync_agencias(db: AsyncSession) -> dict[str, int]:
    """Informes_Agencias -> ref_bacen_agencia.

    O banco_compe da agencia e resolvido pelo ISPB/CnpjBase da instituicao
    (STR) -- rode `sync_instituicoes` antes. Agencia cujo CnpjBase nao casa
    com nenhuma instituicao com codigo Compe e pulada (inalcancavel via CNAB).
    """
    from sqlalchemy import select

    ispb_to_compe = {
        row.ispb: row.codigo_compe
        for row in (
            await db.execute(
                select(RefBacenInstituicao.ispb, RefBacenInstituicao.codigo_compe)
            )
        ).all()
    }
    rows = await fetch_agencias()
    fetched_at = datetime.now(UTC)
    values: list[dict[str, Any]] = []
    sem_banco = sem_codigo = 0
    vistos: set[tuple[str, str]] = set()
    for r in rows:
        cnpj_base = str(r.get("CnpjBase") or "").strip().zfill(8)
        banco = ispb_to_compe.get(cnpj_base)
        if banco is None:
            sem_banco += 1
            continue
        agencia = _pad_agencia(r.get("CodigoCompe"))
        if agencia is None:
            sem_codigo += 1
            continue
        key = (banco, agencia)
        if key in vistos:
            continue  # 1a ocorrencia vence (dups raros no snapshot)
        vistos.add(key)
        values.append(
            {
                "id": uuid4(),
                "banco_compe": banco,
                "cnpj_base": cnpj_base,
                "nome_if": str(r.get("NomeIf") or "")[:255],
                "agencia_codigo": agencia,
                "nome_agencia": (str(r.get("NomeAgencia") or "").strip() or None),
                "municipio": (str(r.get("Municipio") or "").strip() or None),
                "municipio_ibge": int(r["MunicipioIbge"])
                if str(r.get("MunicipioIbge") or "").strip().isdigit()
                else None,
                "uf": (str(r.get("UF") or "").strip()[:2] or None),
                "data_inicio": _parse_data_br(r.get("DataInicio")),
                "posicao": _parse_data_br(r.get("Posicao")),
                "fetched_at": fetched_at,
                "fetched_by_version": ADAPTER_VERSION,
            }
        )
    for i in range(0, len(values), _CHUNK):
        stmt = pg_insert(RefBacenAgencia).values(values[i : i + _CHUNK])
        stmt = stmt.on_conflict_do_update(
            constraint="uq_ref_bacen_agencia_banco_ag",
            set_={
                c: getattr(stmt.excluded, c)
                for c in (
                    "cnpj_base", "nome_if", "nome_agencia", "municipio",
                    "municipio_ibge", "uf", "data_inicio", "posicao",
                    "fetched_at", "fetched_by_version",
                )
            },
        )
        await db.execute(stmt)
    # Pos-passe: instituicao com agencia fisica no Informes_Agencias E banco
    # por definicao -- corrige nomes que a heuristica nao alcanca. So promove
    # a partir de "outros" (cooperativo/ip/scd nunca sao rebaixados).
    from sqlalchemy import update

    bancos_com_agencia = {v["banco_compe"] for v in values}
    if bancos_com_agencia:
        await db.execute(
            update(RefBacenInstituicao)
            .where(
                RefBacenInstituicao.codigo_compe.in_(bancos_com_agencia),
                RefBacenInstituicao.segmento == SEGMENTO_OUTROS,
            )
            .values(segmento=SEGMENTO_BANCO, segmento_fonte="informes_agencias")
        )
    logger.info(
        "ref_bacen_agencia: %d upserts (sem_banco=%d sem_codigo=%d)",
        len(values), sem_banco, sem_codigo,
    )
    return {"agencias": len(values), "sem_banco": sem_banco, "sem_codigo": sem_codigo}


async def sync_ref_bacen(db: AsyncSession) -> dict[str, int]:
    """Ciclo completo: instituicoes (STR) + agencias (Informes_Agencias)."""
    m1 = await sync_instituicoes(db)
    m2 = await sync_agencias(db)
    await db.commit()
    return {**m1, **m2}
