"""Controladoria · Cota Sub · drill PDD (F2 do redesign, 2026-05-23).

Decompoe a categoria PDD (Provisao para Devedores Duvidosos) do Balance
hero em:

  1. PDD consolidado D-1 / D0 / Δ  (fonte do balanco — `_sum_pdd`)
  2. PDD granular D-1 / D0          (Σ `wh_estoque_recebivel.valor_pdd`)
     — sinaliza divergencia consolidado vs granular (defasagem QiTech)
  3. Matriz de migracao A/B/C/D/E/F/G/H ↔ WOP/NOVO
     — celulas (faixa_d1, faixa_d0) agregando qtd_papeis + sum_delta_pdd
  4. Papeis WOP                     (write-off — papel sumiu entre D-1 e D0)
  5. Top N papeis por |Δ valor_pdd| (excluindo WOP, ja listados acima)

WOP fantasma: faixa_pdd_d0 IS NULL na granular = papel saiu do estoque sem
liquidacao registrada. Caso pedagogico do redesign: R$ 118.045,68 separa a
leitura granular da consolidada QiTech em REALINVEST quando WOP material
acontece sem espelho contabil. Ver memo [[project_cota_sub_redesign]].
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.cota_sub_drill import (
    DrillPddMigracaoCelula,
    DrillPddPapel,
    DrillPddResponse,
    PddFaixaKey,
)
from app.modules.controladoria.services.cota_sub import _sum_pdd
from app.modules.controladoria.services.cota_sub_explainers import (
    _check_estoque_disponibilidade,
)
from app.modules.integracoes.public import dia_util_anterior_qitech
from app.warehouse.estoque_recebivel import EstoqueRecebivel

ZERO = Decimal("0")

_VALID_FAIXAS = {"A", "B", "C", "D", "E", "F", "G", "H"}

_DEFAULT_TOP_N = 20
_DEFAULT_THRESHOLD_BRL = Decimal("100")


def _normalize_faixa_d1(raw: str | None) -> PddFaixaKey:
    """Faixa em D-1; quando o papel nao existia em D-1 (so apareceu em D0), retorna NOVO."""
    if raw is None:
        return "NOVO"
    return raw if raw in _VALID_FAIXAS else "NOVO"  # type: ignore[return-value]


def _normalize_faixa_d0(raw: str | None) -> PddFaixaKey:
    """Faixa em D0; quando o papel sumiu entre D-1 e D0, retorna WOP."""
    if raw is None:
        return "WOP"
    return raw if raw in _VALID_FAIXAS else "WOP"  # type: ignore[return-value]


async def _sum_pdd_granular(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fundo_doc: str,
    data: date,
) -> Decimal:
    """Σ wh_estoque_recebivel.valor_pdd para a data (granular)."""
    stmt = (
        select(func.coalesce(func.sum(EstoqueRecebivel.valor_pdd), ZERO))
        .where(EstoqueRecebivel.tenant_id == tenant_id)
        .where(EstoqueRecebivel.fundo_doc == fundo_doc)
        .where(EstoqueRecebivel.data_referencia == data)
    )
    return Decimal((await db.execute(stmt)).scalar() or 0)


async def _build_matriz_e_papeis(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fundo_doc: str,
    data_d1: date,
    data_d0: date,
    threshold_brl: Decimal,
    top_n: int,
) -> tuple[list[DrillPddMigracaoCelula], list[DrillPddPapel], list[DrillPddPapel], int]:
    """Constroi matriz + papeis WOP + top N papeis numa unica passada pelo banco.

    Retorna (matriz, papeis_wop, top_papeis, total_acima_threshold).

    Estrategia: 1 query FULL OUTER JOIN puxa todos os papeis de D-1 + D0,
    agregamos em Python (matriz + top N + WOP). Pra REALINVEST (~2800 papeis)
    a queries roda em <500ms e o trabalho em Python e desprezivel.
    """
    d1q = (
        select(EstoqueRecebivel)
        .where(EstoqueRecebivel.tenant_id == tenant_id)
        .where(EstoqueRecebivel.fundo_doc == fundo_doc)
        .where(EstoqueRecebivel.data_referencia == data_d1)
        .subquery()
    )
    d0q = (
        select(EstoqueRecebivel)
        .where(EstoqueRecebivel.tenant_id == tenant_id)
        .where(EstoqueRecebivel.fundo_doc == fundo_doc)
        .where(EstoqueRecebivel.data_referencia == data_d0)
        .subquery()
    )

    stmt = select(
        func.coalesce(d0q.c.seu_numero, d1q.c.seu_numero).label("seu_numero"),
        func.coalesce(d0q.c.numero_documento, d1q.c.numero_documento).label("numero_documento"),
        func.coalesce(d0q.c.cedente_doc, d1q.c.cedente_doc).label("cedente_doc"),
        func.coalesce(d0q.c.cedente_nome, d1q.c.cedente_nome).label("cedente_nome"),
        func.coalesce(d0q.c.sacado_doc, d1q.c.sacado_doc).label("sacado_doc"),
        func.coalesce(d0q.c.sacado_nome, d1q.c.sacado_nome).label("sacado_nome"),
        func.coalesce(d0q.c.tipo_recebivel, d1q.c.tipo_recebivel).label("tipo_recebivel"),
        func.coalesce(d0q.c.data_vencimento_ajustada, d1q.c.data_vencimento_ajustada).label(
            "data_vencimento_ajustada"
        ),
        func.coalesce(d0q.c.valor_nominal, d1q.c.valor_nominal).label("valor_nominal"),
        func.coalesce(d1q.c.valor_presente, ZERO).label("valor_presente_d1"),
        func.coalesce(d0q.c.valor_presente, ZERO).label("valor_presente_d0"),
        func.coalesce(d1q.c.valor_pdd, ZERO).label("valor_pdd_d1"),
        func.coalesce(d0q.c.valor_pdd, ZERO).label("valor_pdd_d0"),
        d1q.c.faixa_pdd.label("faixa_pdd_d1_raw"),
        d0q.c.faixa_pdd.label("faixa_pdd_d0_raw"),
        d0q.c.situacao_recebivel.label("situacao_recebivel_d0"),
    ).select_from(
        d0q.join(
            d1q,
            (d0q.c.seu_numero == d1q.c.seu_numero)
            & (d0q.c.numero_documento == d1q.c.numero_documento),
            full=True,
        )
    )
    rows = (await db.execute(stmt)).all()

    # Matriz: chave = (faixa_d1, faixa_d0) -> acumulador
    matriz_acc: dict[tuple[PddFaixaKey, PddFaixaKey], dict[str, object]] = {}
    papeis_wop: list[DrillPddPapel] = []
    candidatos_top: list[DrillPddPapel] = []
    total_acima_threshold = 0

    for r in rows:
        faixa_d1 = _normalize_faixa_d1(r.faixa_pdd_d1_raw)
        faixa_d0 = _normalize_faixa_d0(r.faixa_pdd_d0_raw)
        delta_pdd = Decimal(r.valor_pdd_d0 or 0) - Decimal(r.valor_pdd_d1 or 0)

        # ---- Agrega na matriz ----
        key = (faixa_d1, faixa_d0)
        if key not in matriz_acc:
            matriz_acc[key] = {
                "qtd_papeis":            0,
                "sum_valor_nominal":     ZERO,
                "sum_valor_presente_d1": ZERO,
                "sum_valor_presente_d0": ZERO,
                "sum_valor_pdd_d1":      ZERO,
                "sum_valor_pdd_d0":      ZERO,
                "sum_delta_pdd":         ZERO,
            }
        acc = matriz_acc[key]
        acc["qtd_papeis"] = int(acc["qtd_papeis"]) + 1  # type: ignore[operator]
        acc["sum_valor_nominal"] = Decimal(acc["sum_valor_nominal"]) + Decimal(r.valor_nominal or 0)  # type: ignore[arg-type]
        acc["sum_valor_presente_d1"] = Decimal(acc["sum_valor_presente_d1"]) + Decimal(r.valor_presente_d1 or 0)  # type: ignore[arg-type]
        acc["sum_valor_presente_d0"] = Decimal(acc["sum_valor_presente_d0"]) + Decimal(r.valor_presente_d0 or 0)  # type: ignore[arg-type]
        acc["sum_valor_pdd_d1"] = Decimal(acc["sum_valor_pdd_d1"]) + Decimal(r.valor_pdd_d1 or 0)  # type: ignore[arg-type]
        acc["sum_valor_pdd_d0"] = Decimal(acc["sum_valor_pdd_d0"]) + Decimal(r.valor_pdd_d0 or 0)  # type: ignore[arg-type]
        acc["sum_delta_pdd"] = Decimal(acc["sum_delta_pdd"]) + delta_pdd  # type: ignore[arg-type]

        # ---- Papel canonico ----
        papel = DrillPddPapel(
            cedente_doc=r.cedente_doc or "",
            cedente_nome=r.cedente_nome or "",
            sacado_doc=r.sacado_doc or "",
            sacado_nome=r.sacado_nome or "",
            seu_numero=r.seu_numero or "",
            numero_documento=r.numero_documento or "",
            tipo_recebivel=r.tipo_recebivel or "",
            valor_nominal=Decimal(r.valor_nominal or 0),
            data_vencimento_ajustada=r.data_vencimento_ajustada,
            faixa_pdd_d1=faixa_d1,
            faixa_pdd_d0=faixa_d0,
            valor_pdd_d1=Decimal(r.valor_pdd_d1 or 0),
            valor_pdd_d0=Decimal(r.valor_pdd_d0 or 0),
            delta_valor_pdd=delta_pdd,
            situacao_recebivel_d0=r.situacao_recebivel_d0,
        )

        # WOP destacado: papel sumiu entre D-1 e D0 (faixa_d0 == "WOP")
        if faixa_d0 == "WOP" and abs(papel.valor_pdd_d1) > 0:
            papeis_wop.append(papel)

        # Candidato a top N (excluindo WOP — ja listado acima)
        if faixa_d0 != "WOP" and abs(delta_pdd) > threshold_brl:
            total_acima_threshold += 1
            candidatos_top.append(papel)

    # ---- Materializa matriz ----
    matriz: list[DrillPddMigracaoCelula] = []
    for (faixa_d1, faixa_d0), acc in matriz_acc.items():
        matriz.append(
            DrillPddMigracaoCelula(
                faixa_de=faixa_d1,
                faixa_para=faixa_d0,
                qtd_papeis=int(acc["qtd_papeis"]),  # type: ignore[arg-type]
                sum_valor_nominal=Decimal(acc["sum_valor_nominal"]),  # type: ignore[arg-type]
                sum_valor_presente_d1=Decimal(acc["sum_valor_presente_d1"]),  # type: ignore[arg-type]
                sum_valor_presente_d0=Decimal(acc["sum_valor_presente_d0"]),  # type: ignore[arg-type]
                sum_valor_pdd_d1=Decimal(acc["sum_valor_pdd_d1"]),  # type: ignore[arg-type]
                sum_valor_pdd_d0=Decimal(acc["sum_valor_pdd_d0"]),  # type: ignore[arg-type]
                sum_delta_pdd=Decimal(acc["sum_delta_pdd"]),  # type: ignore[arg-type]
            )
        )

    # Ordena matriz: WOP primeiro (impacto material), depois por |sum_delta_pdd| DESC.
    matriz.sort(
        key=lambda c: (
            0 if c.faixa_para == "WOP" else 1,
            -abs(c.sum_delta_pdd),
        )
    )

    # WOP por |valor_pdd_d1| DESC (maior risco perdido)
    papeis_wop.sort(key=lambda p: abs(p.valor_pdd_d1), reverse=True)

    # Top N por |delta_valor_pdd| DESC
    candidatos_top.sort(key=lambda p: abs(p.delta_valor_pdd), reverse=True)
    top_papeis = candidatos_top[:top_n]

    return matriz, papeis_wop, top_papeis, total_acima_threshold


async def compute_drill_pdd(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date | None = None,
    threshold_brl: Decimal = _DEFAULT_THRESHOLD_BRL,
    top_n: int = _DEFAULT_TOP_N,
) -> DrillPddResponse:
    """Drill PDD: matriz de migracao + papeis WOP + top papeis por delta."""
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
    d1 = data_d1 or await dia_util_anterior_qitech(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0,
    )

    # PDD consolidado (fonte do balanco — valor negativo na QiTech, mantemos sinal).
    pdd_cons_d1_raw = await _sum_pdd(db, tenant_id, ua_id, d1)
    pdd_cons_d0_raw = await _sum_pdd(db, tenant_id, ua_id, data_d0)
    pdd_cons_d1 = abs(pdd_cons_d1_raw)
    pdd_cons_d0 = abs(pdd_cons_d0_raw)
    pdd_cons_delta = pdd_cons_d0 - pdd_cons_d1

    # Granular — informativo, exibe divergencia vs consolidado.
    pdd_gran_d1 = await _sum_pdd_granular(db, tenant_id=tenant_id, fundo_doc=fundo_doc, data=d1)
    pdd_gran_d0 = await _sum_pdd_granular(db, tenant_id=tenant_id, fundo_doc=fundo_doc, data=data_d0)

    # Guard de disponibilidade do granular nos 2 dias.
    motivo = await _check_estoque_disponibilidade(
        db, tenant_id=tenant_id, fundo_doc=fundo_doc,
        data_d0=data_d0, data_d1=d1,
    )
    estoque_d1_ok = motivo is None or "D-1" not in (motivo or "")
    estoque_d0_ok = motivo is None or "D0" not in (motivo or "")

    if motivo is not None:
        # Granular nao disponivel em uma das datas — devolve consolidado + flags,
        # matriz/wop/top vazios (FULL OUTER JOIN produziria sinais espelhados).
        return DrillPddResponse(
            fundo_id=str(ua_id),
            fundo_nome=ua.nome,
            data=data_d0,
            data_anterior=d1,
            pdd_consolidado_d1=pdd_cons_d1,
            pdd_consolidado_d0=pdd_cons_d0,
            pdd_consolidado_delta=pdd_cons_delta,
            pdd_granular_d1=pdd_gran_d1,
            pdd_granular_d0=pdd_gran_d0,
            estoque_disponivel_d1=estoque_d1_ok,
            estoque_disponivel_d0=estoque_d0_ok,
            motivo_indisponivel=motivo,
            matriz=[],
            papeis_wop=[],
            papeis_wop_total_pdd_d1=ZERO,
            top_papeis=[],
            top_papeis_threshold_brl=threshold_brl,
            top_papeis_n_solicitado=top_n,
            top_papeis_total_acima_threshold=0,
        )

    matriz, papeis_wop, top_papeis, total_acima_threshold = await _build_matriz_e_papeis(
        db,
        tenant_id=tenant_id,
        fundo_doc=fundo_doc,
        data_d1=d1,
        data_d0=data_d0,
        threshold_brl=threshold_brl,
        top_n=top_n,
    )

    papeis_wop_total_pdd = sum((abs(p.valor_pdd_d1) for p in papeis_wop), ZERO)

    return DrillPddResponse(
        fundo_id=str(ua_id),
        fundo_nome=ua.nome,
        data=data_d0,
        data_anterior=d1,
        pdd_consolidado_d1=pdd_cons_d1,
        pdd_consolidado_d0=pdd_cons_d0,
        pdd_consolidado_delta=pdd_cons_delta,
        pdd_granular_d1=pdd_gran_d1,
        pdd_granular_d0=pdd_gran_d0,
        estoque_disponivel_d1=True,
        estoque_disponivel_d0=True,
        motivo_indisponivel=None,
        matriz=matriz,
        papeis_wop=papeis_wop,
        papeis_wop_total_pdd_d1=papeis_wop_total_pdd,
        top_papeis=top_papeis,
        top_papeis_threshold_brl=threshold_brl,
        top_papeis_n_solicitado=top_n,
        top_papeis_total_acima_threshold=total_acima_threshold,
    )
