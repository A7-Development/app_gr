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

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.integracoes.adapters.data.bacen.client import (
    fetch_agencias,
    fetch_participantes_str,
    fetch_postos,
    fetch_sedes_segmentos,
)
from app.modules.integracoes.adapters.data.bacen.version import ADAPTER_VERSION
from app.shared.audit_log.decision_log import DecisionLog, DecisionType
from app.warehouse.ref_bacen import (
    FONTE_OLINDA,
    SEGMENTO_BANCO,
    SEGMENTO_BANCO_COOPERATIVO,
    SEGMENTO_COOPERATIVA,
    SEGMENTO_FINANCEIRA,
    SEGMENTO_IP,
    SEGMENTO_OUTROS,
    SEGMENTO_SCD,
    RefBacenAgencia,
    RefBacenInstituicao,
    RefBacenPosto,
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


# Prefixo numerico do NomePosto: "6425 - PLATAFORMA EMPRESAS..." -> 06425.
# Alguns postos nao tem codigo no nome (PABs de orgaos publicos); ficam NULL.
_POSTO_CODIGO_RE = re.compile(r"^\s*(\d{1,5})\s*[-–]")  # noqa: RUF001 -- en dash e real no NomePosto


def extrair_posto_codigo(nome_posto: str | None) -> str | None:
    """Codigo do posto (5 digitos zero-padded) extraido do prefixo do NomePosto.

    O CNAB entrega esse codigo no campo de agencia; o resolver casa por
    (banco_compe, posto_codigo). Postos sem prefixo numerico retornam None.
    """
    m = _POSTO_CODIGO_RE.match(nome_posto or "")
    if not m or int(m.group(1)) == 0:
        return None
    return m.group(1).zfill(5)


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
                # Linha vista no snapshot vivo = fonte olinda (promove linha
                # bcb_historico que reapareceu; cadastro mais fresco vence).
                "fonte": FONTE_OLINDA,
                "fetched_at": fetched_at,
                "fetched_by_version": ADAPTER_VERSION,
            }
        )
    for i in range(0, len(values), _CHUNK):
        stmt = pg_insert(RefBacenAgencia).values(values[i : i + _CHUNK])
        # NAO toca endereco/bairro/cep/primeira|ultima_competencia/ativa —
        # colunas da serie historica BCB (estatica), preservadas no upsert.
        stmt = stmt.on_conflict_do_update(
            constraint="uq_ref_bacen_agencia_banco_ag",
            set_={
                c: getattr(stmt.excluded, c)
                for c in (
                    "cnpj_base", "nome_if", "nome_agencia", "municipio",
                    "municipio_ibge", "uf", "data_inicio", "posicao",
                    "fonte", "fetched_at", "fetched_by_version",
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


def _canonico_oficial(segmento_oficial: str) -> str:
    """De-para do rotulo OFICIAL do Bacen -> segmento canonico (6 familias).

    NAO e inferencia: o rotulo ja e a classificacao oficial; isto so agrupa
    os ~30 tipos oficiais nas 6 familias que usamos.
    """
    s = _norm(segmento_oficial)
    if "BANCO" in s and "COOPERATIV" in s:
        return SEGMENTO_BANCO_COOPERATIVO
    if "COOPERATIV" in s:
        return SEGMENTO_COOPERATIVA
    if "INSTITUICAO DE PAGAMENTO" in s:
        return SEGMENTO_IP
    if "CREDITO DIRETO" in s:
        return SEGMENTO_SCD
    if "FINANCIAMENTO E INVESTIMENTO" in s or "MICROEMPREENDEDOR" in s:
        return SEGMENTO_FINANCEIRA
    if s.startswith("BANCO") or "CAIXA ECONOMICA" in s or s == "BNDES":
        return SEGMENTO_BANCO
    return SEGMENTO_OUTROS


async def sync_segmento_oficial(db: AsyncSession) -> dict[str, int]:
    """Relacao de Instituicoes em Funcionamento -> segmento OFICIAL.

    Casa por ISPB (= base do CNPJ, 8 digitos). Substitui a heuristica de nome
    pelo rotulo oficial do Bacen. `is_banco_digital` = banco sem rede fisica
    (<=1 agencia) — a UNICA inferencia (digital nao e categoria regulatoria).
    """
    sedes = await fetch_sedes_segmentos()
    por_cnpj: dict[str, tuple[str, str]] = {}
    for r in sedes:
        cnpj = (r["cnpj"] or "").strip().zfill(8)[-8:]
        if cnpj and r["segmento"]:
            por_cnpj[cnpj] = (_canonico_oficial(r["segmento"]), r["segmento"][:80])

    insts = (await db.execute(select(RefBacenInstituicao))).scalars().all()
    n = 0
    for inst in insts:
        hit = por_cnpj.get((inst.ispb or "").zfill(8)[-8:])
        if hit is not None:
            inst.segmento = hit[0]
            inst.segmento_oficial = hit[1]
            inst.segmento_fonte = "oficial_bacen"
            n += 1
    await db.flush()
    # is_banco_digital: banco (oficial) com <=1 agencia fisica.
    await db.execute(
        text(
            "UPDATE ref_bacen_instituicao i SET is_banco_digital = ("
            "  i.segmento = :banco AND ("
            "    SELECT count(*) FROM ref_bacen_agencia a"
            "    WHERE a.banco_compe = i.codigo_compe) <= 1)"
        ),
        {"banco": SEGMENTO_BANCO},
    )
    logger.info("bacen segmento oficial: %d instituicoes classificadas", n)
    return {"segmento_oficial": n}


async def sync_postos(db: AsyncSession) -> dict[str, int]:
    """Informes_PostosDeAtendimento -> ref_bacen_posto.

    A OUTRA metade da rede fisica (PAB/PAE). O banco_compe e resolvido pelo
    ISPB(=CnpjBase) via STR -- rode `sync_instituicoes` antes. Upsert-sem-delete
    por (cnpj_base, nome_posto): acumula historia via LEAST/GREATEST da posicao
    (posto que sai do snapshot permanece; o acervo CNAB historico o referencia).
    """
    ispb_to_compe = {
        row.ispb: row.codigo_compe
        for row in (
            await db.execute(
                select(RefBacenInstituicao.ispb, RefBacenInstituicao.codigo_compe)
            )
        ).all()
    }
    rows = await fetch_postos()
    fetched_at = datetime.now(UTC)
    values: list[dict[str, Any]] = []
    com_codigo = 0
    vistos: set[tuple[str, str]] = set()
    for r in rows:
        cnpj_base = str(r.get("Cnpj") or "").strip().zfill(8)[-8:]
        nome_posto = str(r.get("NomePosto") or "").strip()
        if not cnpj_base or cnpj_base == "00000000" or not nome_posto:
            continue
        key = (cnpj_base, nome_posto[:255])
        if key in vistos:
            continue  # 1a ocorrencia vence (dups raros no snapshot)
        vistos.add(key)
        codigo = extrair_posto_codigo(nome_posto)
        if codigo:
            com_codigo += 1
        posicao = _parse_data_br(r.get("Posicao"))
        values.append(
            {
                "id": uuid4(),
                "cnpj_base": cnpj_base,
                "banco_compe": ispb_to_compe.get(cnpj_base),
                "nome_if": (str(r.get("NomeIf") or "").strip()[:255] or None),
                "nome_posto": nome_posto[:255],
                "posto_codigo": codigo,
                "tipo_posto": (str(r.get("TipoPosto") or "").strip()[:80] or None),
                "endereco": (str(r.get("Endereco") or "").strip()[:255] or None),
                "bairro": (str(r.get("Bairro") or "").strip()[:255] or None),
                "cep": (str(r.get("Cep") or "").strip()[:9] or None),
                "municipio": (str(r.get("Municipio") or "").strip()[:120] or None),
                "municipio_ibge": int(r["MunicipioIbge"])
                if str(r.get("MunicipioIbge") or "").strip().isdigit()
                else None,
                "uf": (str(r.get("UF") or "").strip()[:2] or None),
                "primeira_posicao": posicao,
                "ultima_posicao": posicao,
                "fetched_at": fetched_at,
                "fetched_by_version": ADAPTER_VERSION,
            }
        )
    for i in range(0, len(values), _CHUNK):
        stmt = pg_insert(RefBacenPosto).values(values[i : i + _CHUNK])
        stmt = stmt.on_conflict_do_update(
            constraint="uq_ref_bacen_posto",
            set_={
                "banco_compe": stmt.excluded.banco_compe,
                "nome_if": stmt.excluded.nome_if,
                "posto_codigo": stmt.excluded.posto_codigo,
                "tipo_posto": stmt.excluded.tipo_posto,
                "endereco": stmt.excluded.endereco,
                "bairro": stmt.excluded.bairro,
                "cep": stmt.excluded.cep,
                "municipio": stmt.excluded.municipio,
                "municipio_ibge": stmt.excluded.municipio_ibge,
                "uf": stmt.excluded.uf,
                # historia acumulada: mantem a 1a posicao, avanca a ultima.
                "primeira_posicao": func.least(
                    RefBacenPosto.primeira_posicao, stmt.excluded.primeira_posicao
                ),
                "ultima_posicao": func.greatest(
                    RefBacenPosto.ultima_posicao, stmt.excluded.ultima_posicao
                ),
                "fetched_at": stmt.excluded.fetched_at,
                "fetched_by_version": stmt.excluded.fetched_by_version,
            },
        )
        await db.execute(stmt)
    logger.info(
        "ref_bacen_posto: %d upserts (com_codigo=%d)", len(values), com_codigo
    )
    return {"postos": len(values), "postos_com_codigo": com_codigo}


async def sync_ref_bacen(db: AsyncSession) -> dict[str, int]:
    """Ciclo completo: instituicoes (STR) + agencias + segmento oficial + postos."""
    m1 = await sync_instituicoes(db)
    m2 = await sync_agencias(db)
    m3 = await sync_segmento_oficial(db)
    m4 = await sync_postos(db)
    metricas = {**m1, **m2, **m3, **m4}
    # Fonte publica global (sem tenant), mas decision_log exige tenant_id:
    # atribui ao mantenedor do sistema (ou 1o tenant) so p/ proveniencia.
    tid = (
        await db.execute(
            text(
                "SELECT id FROM tenants WHERE is_system_maintainer = true LIMIT 1"
            )
        )
    ).scalar_one_or_none() or (
        await db.execute(text("SELECT id FROM tenants LIMIT 1"))
    ).scalar_one()
    # Observabilidade — alimenta o Painel de Saude das Integracoes.
    db.add(
        DecisionLog(
            tenant_id=tid,
            decision_type=DecisionType.SYNC,
            inputs_ref={"fonte": "bacen_publico"},
            rule_or_model="ref_bacen_adapter",
            rule_or_model_version=ADAPTER_VERSION,
            output={"ok": True, "rows": sum(v for v in metricas.values() if isinstance(v, int)), **metricas},
            explanation="sync referencia Bacen: instituicoes + agencias + segmento oficial + postos",
            triggered_by="script:sync_ref_bacen",
        )
    )
    await db.commit()
    return metricas
