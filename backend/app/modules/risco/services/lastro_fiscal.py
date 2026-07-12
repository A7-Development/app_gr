"""Ciencia do lastro fiscal (F4) -- ocorrencias SEFAZ em notas da carteira aberta.

OCORRENCIA = evento SEFAZ (`wh_nfe_evento`) cuja nota lastreia TITULO EM
ABERTO (`wh_titulo.situacao=0` via `wh_titulo_fiscal`), ocorrido APOS a
efetivacao da operacao. Grao do feed: evento x nota (titulos agregados).

Read PURO sobre warehouse + decision_log — zero import de `integracoes`
(fronteira decidida 2026-07-11: maquinario la, ciencia aqui).

Catalogo FIS-* (familia fiscal do catalogo de sinais; severidades espelham
o rating de liquidacao):

    FIS-01 critica   nota cancelada (110111, retCStat 135/136)
    FIS-02 critica   cancelada FORA DE PRAZO (retCStat 155)
    FIS-03 critica   sacado: operacao nao realizada (210240)
    FIS-04 critica   sacado: desconhecimento da operacao (210220)
    FIS-05 media     titulo aberto ha >N dias SEM manifestacao (ausencia —
                     vive no resumo, nao no feed de eventos)
    FIS-06 positiva  sacado CONFIRMOU a operacao (210200) — trava
                     cancelamento na SEFAZ
    FIS-07 baixa     carta de correcao (110110) pos-cessao
    FIS-09 info      ciencia da operacao (210210)
    FIS-99 info      demais eventos (CT-e/MDF-e/averbacao/...) — zero
                     ocultacao: fato novo nunca some do feed
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.warehouse.fiscal_nfe import Nfe
from app.warehouse.nfe_estado import NfeEvento, NfeSituacao
from app.warehouse.operacao import Operacao
from app.warehouse.titulo import Titulo
from app.warehouse.titulo_fiscal import WhTituloFiscal

SITUACAO_TITULO_EM_ABERTO = 0
DIAS_SEM_MANIFESTACAO = 7

# tpEvento -> (codigo, severidade). Cancelamento (110111) e resolvido a
# parte porque o codigo depende do retEvento.cStat (135/136 vs 155).
_TP_MANIFESTACAO = {210200, 210210, 210220, 210240}
_CLASSIFICACAO: dict[int, tuple[str, str]] = {
    210240: ("FIS-03", "critica"),
    210220: ("FIS-04", "critica"),
    210200: ("FIS-06", "positiva"),
    110110: ("FIS-07", "baixa"),
    210210: ("FIS-09", "info"),
}

SEVERIDADES = ("critica", "media", "baixa", "positiva", "info")


def classificar_evento(tp_evento: int, ret_c_stat: int | None) -> tuple[str, str]:
    """(codigo FIS-*, severidade) de um evento SEFAZ."""
    if tp_evento == 110111:
        if ret_c_stat == 155:
            return "FIS-02", "critica"
        return "FIS-01", "critica"
    return _CLASSIFICACAO.get(tp_evento, ("FIS-99", "info"))


@dataclass(slots=True)
class Ocorrencia:
    """Uma linha do feed: evento SEFAZ x nota, com titulos abertos agregados."""

    evento_id: UUID
    chave_acesso: str
    codigo: str
    severidade: str
    tp_evento: int
    desc_evento: str | None
    justificativa: str | None
    dh_evento: datetime | None
    autor_documento: str | None
    pos_cessao: bool | None
    # Nota (do XML do cliente, quando ingerida)
    nfe_numero: int | None
    emitente_nome: str | None
    emitente_documento: str | None
    destinatario_nome: str | None
    valor_nota: float | None
    situacao_nota: str | None
    # Titulos EM ABERTO lastreados pela nota
    qtd_titulos_abertos: int
    saldo_devedor_aberto: float
    primeira_efetivacao: datetime | None


def _base_titulos_abertos(tenant_id: UUID) -> sa.Select:
    """(chave, agregados de titulo aberto + efetivacao) por nota da carteira."""
    return (
        sa.select(
            WhTituloFiscal.chave_acesso.label("chave_acesso"),
            sa.func.count(sa.distinct(Titulo.titulo_id)).label("qtd_titulos"),
            sa.func.coalesce(sa.func.sum(Titulo.saldo_devedor), 0).label(
                "saldo_devedor"
            ),
            sa.func.min(Operacao.data_de_efetivacao).label("primeira_efetivacao"),
        )
        .select_from(Titulo)
        .join(
            WhTituloFiscal,
            sa.and_(
                WhTituloFiscal.tenant_id == Titulo.tenant_id,
                WhTituloFiscal.titulo_id == Titulo.titulo_id,
            ),
        )
        .join(
            Operacao,
            sa.and_(
                Operacao.tenant_id == Titulo.tenant_id,
                Operacao.operacao_id == Titulo.operacao_id,
            ),
            isouter=True,
        )
        .where(
            Titulo.tenant_id == tenant_id,
            Titulo.situacao == SITUACAO_TITULO_EM_ABERTO,
        )
        .group_by(WhTituloFiscal.chave_acesso)
    )


async def listar_ocorrencias(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    desde: datetime | None = None,
    severidades: list[str] | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    """Feed de ocorrencias (paginacao REAL — §14.6: total exposto, nada some).

    Ordenado por dh_evento DESC. `severidades` filtra pos-classificacao
    (a classificacao e Python; filtro SQL equivalente por tpEvento).
    """
    abertos = _base_titulos_abertos(tenant_id).subquery()
    stmt = (
        sa.select(
            NfeEvento.id,
            NfeEvento.chave_acesso,
            NfeEvento.tp_evento,
            NfeEvento.ret_c_stat,
            NfeEvento.desc_evento,
            NfeEvento.x_just,
            NfeEvento.x_correcao,
            NfeEvento.dh_evento,
            NfeEvento.autor_cnpj,
            NfeEvento.autor_cpf,
            abertos.c.qtd_titulos,
            abertos.c.saldo_devedor,
            abertos.c.primeira_efetivacao,
            Nfe.numero.label("nfe_numero"),
            Nfe.emitente_nome,
            Nfe.emitente_documento,
            Nfe.destinatario_nome,
            Nfe.valor_total,
            NfeSituacao.situacao.label("situacao_nota"),
        )
        .join(abertos, abertos.c.chave_acesso == NfeEvento.chave_acesso)
        .join(
            Nfe,
            sa.and_(
                Nfe.tenant_id == NfeEvento.tenant_id,
                Nfe.chave_acesso == NfeEvento.chave_acesso,
            ),
            isouter=True,
        )
        .join(
            NfeSituacao,
            sa.and_(
                NfeSituacao.tenant_id == NfeEvento.tenant_id,
                NfeSituacao.chave_acesso == NfeEvento.chave_acesso,
            ),
            isouter=True,
        )
        .where(NfeEvento.tenant_id == tenant_id)
        .order_by(NfeEvento.dh_evento.desc().nulls_last())
    )
    if desde is not None:
        stmt = stmt.where(NfeEvento.dh_evento >= desde)

    rows = (await db.execute(stmt)).all()

    ocorrencias: list[Ocorrencia] = []
    for r in rows:
        codigo, severidade = classificar_evento(r.tp_evento, r.ret_c_stat)
        if severidades and severidade not in severidades:
            continue
        pos_cessao = (
            None
            if r.primeira_efetivacao is None or r.dh_evento is None
            else r.dh_evento > r.primeira_efetivacao
        )
        ocorrencias.append(
            Ocorrencia(
                evento_id=r.id,
                chave_acesso=r.chave_acesso,
                codigo=codigo,
                severidade=severidade,
                tp_evento=r.tp_evento,
                desc_evento=r.desc_evento,
                justificativa=r.x_just or r.x_correcao,
                dh_evento=r.dh_evento,
                autor_documento=r.autor_cnpj or r.autor_cpf,
                pos_cessao=pos_cessao,
                nfe_numero=r.nfe_numero,
                emitente_nome=r.emitente_nome,
                emitente_documento=r.emitente_documento,
                destinatario_nome=r.destinatario_nome,
                valor_nota=float(r.valor_total) if r.valor_total is not None else None,
                situacao_nota=r.situacao_nota,
                qtd_titulos_abertos=int(r.qtd_titulos),
                saldo_devedor_aberto=float(r.saldo_devedor),
                primeira_efetivacao=r.primeira_efetivacao,
            )
        )

    total = len(ocorrencias)
    inicio = (page - 1) * page_size
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "ocorrencias": ocorrencias[inicio : inicio + page_size],
    }


async def resumo(db: AsyncSession, tenant_id: UUID) -> dict[str, Any]:
    """KPIs da carteira: vigiadas, mortas, sem manifestacao, % confirmada."""
    abertos = _base_titulos_abertos(tenant_id).subquery()

    notas_vigiadas = (
        await db.execute(sa.select(sa.func.count()).select_from(abertos))
    ).scalar_one()

    mortas = (
        await db.execute(
            sa.select(
                sa.func.count(),
                sa.func.coalesce(sa.func.sum(abertos.c.saldo_devedor), 0),
            )
            .select_from(abertos)
            .join(
                NfeSituacao,
                sa.and_(
                    NfeSituacao.tenant_id == tenant_id,
                    NfeSituacao.chave_acesso == abertos.c.chave_acesso,
                ),
            )
            .where(NfeSituacao.cancelada.is_(True))
        )
    ).one()

    # Chaves da carteira COM alguma manifestacao do sacado registrada.
    manifestadas = (
        sa.select(NfeEvento.chave_acesso)
        .where(
            NfeEvento.tenant_id == tenant_id,
            NfeEvento.tp_evento.in_(_TP_MANIFESTACAO),
        )
        .distinct()
        .subquery()
    )
    corte = datetime.now(UTC) - timedelta(days=DIAS_SEM_MANIFESTACAO)
    sem_manifestacao = (
        await db.execute(
            sa.select(
                sa.func.count(),
                sa.func.coalesce(sa.func.sum(abertos.c.saldo_devedor), 0),
            )
            .select_from(abertos)
            .where(
                abertos.c.chave_acesso.not_in(sa.select(manifestadas.c.chave_acesso)),
                abertos.c.primeira_efetivacao < corte,
            )
        )
    ).one()

    confirmadas = (
        await db.execute(
            sa.select(sa.func.count(sa.distinct(NfeEvento.chave_acesso)))
            .select_from(NfeEvento)
            .join(abertos, abertos.c.chave_acesso == NfeEvento.chave_acesso)
            .where(
                NfeEvento.tenant_id == tenant_id,
                NfeEvento.tp_evento == 210200,
            )
        )
    ).scalar_one()

    return {
        "notas_vigiadas": int(notas_vigiadas),
        "notas_mortas": int(mortas[0]),
        "notas_mortas_saldo": float(mortas[1]),
        "sem_manifestacao": int(sem_manifestacao[0]),
        "sem_manifestacao_saldo": float(sem_manifestacao[1]),
        "sem_manifestacao_dias": DIAS_SEM_MANIFESTACAO,
        "confirmadas": int(confirmadas),
        "pct_confirmada": (
            round(100.0 * confirmadas / notas_vigiadas, 1) if notas_vigiadas else 0.0
        ),
    }
