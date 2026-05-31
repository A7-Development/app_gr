"""Controladoria · Conferencia de cessao — aquisicao (DC) vs caixa (extrato).

Reconcilia, por dia e por cedente, o que o fundo registrou como AQUISICAO de
recebiveis (Σ valor_compra em wh_aquisicao_recebivel) contra o que de fato
SAIU do caixa pro cedente (debitos em wh_extrato_bancario, contrapartida =
cedente_doc) numa janela [D, D + janela_dias].

Achado empirico (REALINVEST, 2026-05-30): a cessao liquida como TED ao cedente
no valor EXATO da compra, no mesmo dia (codigo bancario 0307). Logo o match
1:1 por cedente eh possivel. O cross-check acende 3 sinais:
  - erro de lancamento (descasa): TED != Σ valor_compra (DC e caixa descasam)
  - furo de sync do extrato (sem_extrato): aquisicao existe, extrato sem debito
  - fluxo extra ao cedente (recompra/coobrigacao): debito > compra (contexto)

Heuristica de disponibilidade do extrato: se NENHUM cedente do dia tem debito
na janela, o extrato provavelmente nao foi sincronizado pro periodo -> marca
o dia inteiro como `extrato_disponivel=False` (todos sem_extrato), em vez de
acusar falsamente cada cedente como descasa. Caso real: 11-22/05/2026 (gap).

Silver-only (§13.2.1): le wh_aquisicao_recebivel + wh_extrato_bancario.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.conferencia_cessao import (
    ConferenciaCessaoCedente,
    ConferenciaCessaoLancamento,
    ConferenciaCessaoResponse,
)
from app.warehouse.aquisicao_recebivel import AquisicaoRecebivel
from app.warehouse.extrato_bancario import ExtratoBancario

ZERO = Decimal("0")

# Tolerancia de match (centavos de arredondamento).
_MATCH_TOL = Decimal("0.01")

# Janela forward default (dias corridos): a cessao costuma liquidar no mesmo
# dia (D) ou no seguinte (D+1). Tunavel.
_JANELA_DIAS_DEFAULT = 1


async def compute_conferencia_cessao(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    janela_dias: int = _JANELA_DIAS_DEFAULT,
) -> ConferenciaCessaoResponse:
    """Confere as aquisicoes do dia contra os debitos de caixa aos cedentes.

    Args:
        tenant_id: escopo multi-tenant.
        ua_id: UUID da UA (FIDC).
        data_d0: dia das aquisicoes a conferir.
        janela_dias: dias corridos apos D vasculhados no extrato (default 1).

    Raises:
        ValueError: quando a UA nao existe.
    """
    ua = (
        await db.execute(
            select(UnidadeAdministrativa)
            .where(UnidadeAdministrativa.tenant_id == tenant_id)
            .where(UnidadeAdministrativa.id == ua_id)
        )
    ).scalar_one_or_none()
    if ua is None:
        raise ValueError(f"Unidade Administrativa {ua_id} nao encontrada")

    fundo_doc = ua.cnpj or ""
    data_fim = data_d0 + timedelta(days=janela_dias)

    # ── Aquisicoes do dia agrupadas por cedente ─────────────────────────────
    aq_stmt = (
        select(
            AquisicaoRecebivel.cedente_doc,
            AquisicaoRecebivel.cedente_nome,
            func.count().label("n"),
            func.coalesce(func.sum(AquisicaoRecebivel.valor_compra), ZERO).label("total"),
        )
        .where(AquisicaoRecebivel.tenant_id == tenant_id)
        .where(AquisicaoRecebivel.data_aquisicao == data_d0)
        .where(
            (AquisicaoRecebivel.unidade_administrativa_id == ua_id)
            | (
                (AquisicaoRecebivel.unidade_administrativa_id.is_(None))
                & (AquisicaoRecebivel.fundo_doc == fundo_doc)
            )
        )
        .group_by(AquisicaoRecebivel.cedente_doc, AquisicaoRecebivel.cedente_nome)
    )
    aq_rows = (await db.execute(aq_stmt)).all()

    # Data do lancamento mais recente do extrato (frescor — informativo).
    ext_max = (
        await db.execute(
            select(func.max(ExtratoBancario.data_lancamento)).where(
                ExtratoBancario.tenant_id == tenant_id
            )
        )
    ).scalar_one_or_none()

    if not aq_rows:
        return ConferenciaCessaoResponse(
            fundo_id=str(ua_id),
            fundo_nome=ua.nome,
            data=data_d0,
            janela_dias=janela_dias,
            extrato_disponivel=ext_max is not None and ext_max >= data_d0,
            extrato_ultimo_lancamento=ext_max,
            total_aquisicoes=ZERO,
            total_debito_caixa=ZERO,
            n_cedentes=0,
            n_casa=0,
            n_descasa=0,
            n_sem_extrato=0,
            cedentes=[],
        )

    cedente_docs = {r.cedente_doc for r in aq_rows}

    # ── Debitos do extrato aos cedentes do dia, na janela [D, D+janela] ──────
    ext_stmt = (
        select(
            ExtratoBancario.contrapartida_doc,
            ExtratoBancario.data_lancamento,
            ExtratoBancario.valor,
        )
        .where(ExtratoBancario.tenant_id == tenant_id)
        .where(ExtratoBancario.tipo == "D")
        .where(ExtratoBancario.contrapartida_doc.in_(cedente_docs))
        .where(ExtratoBancario.data_lancamento >= data_d0)
        .where(ExtratoBancario.data_lancamento <= data_fim)
        .where(
            (ExtratoBancario.unidade_administrativa_id == ua_id)
            | (ExtratoBancario.unidade_administrativa_id.is_(None))
        )
        .order_by(ExtratoBancario.data_lancamento)
    )
    debitos_por_cedente: dict[str, list[tuple[date, Decimal]]] = {}
    for doc, dp, valor in (await db.execute(ext_stmt)).all():
        debitos_por_cedente.setdefault(doc, []).append((dp, Decimal(valor or 0)))

    # Heuristica de disponibilidade: se NENHUM cedente do dia tem debito na
    # janela, o extrato provavelmente nao foi sincronizado pro periodo.
    extrato_disponivel = len(debitos_por_cedente) > 0

    cedentes: list[ConferenciaCessaoCedente] = []
    total_aq = ZERO
    total_deb = ZERO
    n_casa = n_descasa = n_sem_extrato = 0
    for r in aq_rows:
        total_compra = Decimal(r.total)
        total_aq += total_compra
        debitos = debitos_por_cedente.get(r.cedente_doc, [])
        sum_deb = sum((v for _, v in debitos), ZERO)
        total_deb += sum_deb
        match_exato = any(abs(v - total_compra) < _MATCH_TOL for _, v in debitos)

        if not extrato_disponivel:
            status = "sem_extrato"
            n_sem_extrato += 1
        elif match_exato or abs(sum_deb - total_compra) < _MATCH_TOL:
            status = "casa"
            n_casa += 1
        else:
            status = "descasa"
            n_descasa += 1

        cedentes.append(
            ConferenciaCessaoCedente(
                cedente_doc=r.cedente_doc,
                cedente_nome=r.cedente_nome,
                n_titulos=int(r.n or 0),
                valor_aquisicao=total_compra,
                valor_debito_caixa=sum_deb,
                diferenca=total_compra - sum_deb,
                status=status,  # type: ignore[arg-type]
                match_exato=match_exato,
                lancamentos=[
                    ConferenciaCessaoLancamento(data_lancamento=dp, valor=v)
                    for dp, v in debitos
                ],
            )
        )

    # Ordena: descasa primeiro (atencao), depois sem_extrato, depois casa;
    # dentro de cada grupo por valor de aquisicao DESC.
    _rank = {"descasa": 0, "sem_extrato": 1, "casa": 2}
    cedentes.sort(key=lambda c: (_rank[c.status], -c.valor_aquisicao))

    return ConferenciaCessaoResponse(
        fundo_id=str(ua_id),
        fundo_nome=ua.nome,
        data=data_d0,
        janela_dias=janela_dias,
        extrato_disponivel=extrato_disponivel,
        extrato_ultimo_lancamento=ext_max,
        total_aquisicoes=total_aq,
        total_debito_caixa=total_deb,
        n_cedentes=len(cedentes),
        n_casa=n_casa,
        n_descasa=n_descasa,
        n_sem_extrato=n_sem_extrato,
        cedentes=cedentes,
    )
