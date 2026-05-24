"""Controladoria · Cota Sub · drill PDD (F2 do redesign, 2026-05-23 → fix 2026-05-24).

Decompoe a categoria PDD (Provisao para Devedores Duvidosos) do Balance
hero em:

  1. PDD consolidado D-1 / D0 / Δ  (fonte do balanco — `_sum_pdd`)
  2. PDD granular D-1 / D0          (Σ `wh_estoque_recebivel.valor_pdd`)
     — sinaliza divergencia consolidado vs granular (defasagem QiTech)
  3. Matriz de migracao A/B/C/D/E/F/G/H/WOP ↔ A/B/C/D/E/F/G/H/WOP/NOVO
     — celulas (faixa_d1, faixa_d0) agregando qtd_papeis + sum_delta_pdd
  4. Papeis WOP                     (write-off NOVO no dia — papel virou
                                     WOP em D0 sem aparecer em
                                     `wh_liquidacao_recebivel`)
  5. Top N papeis por |Δ valor_pdd| (excluindo WOP, ja listados acima)

WOP fantasma: faixa_pdd_d0 IS NULL na granular = papel saiu do estoque sem
liquidacao registrada. Caso pedagogico do redesign: R$ 118.045,68 separa a
leitura granular da consolidada QiTech em REALINVEST quando WOP material
acontece sem espelho contabil. Ver memo [[project_cota_sub_redesign]].

Fix 2026-05-24 — dois bugs do bucket "papeis_wop" descobertos via REALINVEST
20/05 ("BLB+FRICOCK virando WOP" eram na verdade liquidacoes normais):

  Bug 1: `_VALID_FAIXAS` esquecia "WOP" — papeis legitimamente em WOP em
         D-1 eram re-rotulados como NOVO, fazendo "WOP→WOP" aparecer como
         "NOVO→WOP" (3 BMP/V-JOY do REALINVEST 20/05).
  Bug 2: Bucket `papeis_wop` nao cruzava com `wh_liquidacao_recebivel` —
         qualquer papel que sumisse do estoque virava "write-off",
         incluindo recompras/liquidacoes normais (4 BLB/FRICOCK do
         REALINVEST 20/05, todos com ganho liquido positivo).

Bucket WOP corrigido = (faixa_d0='WOP') ∧ (faixa_d1!='WOP') ∧
                       (seu_numero ∉ liquidacoes do dia).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import case, func, select
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
from app.warehouse.liquidacao_recebivel import LiquidacaoRecebivel

ZERO = Decimal("0")

# Fix 2026-05-24: "WOP" passa a ser faixa valida. Antes, papeis legitimamente
# em WOP em D-1 eram re-rotulados como "NOVO" pelo `_normalize_faixa_d1` —
# fazendo "WOP→WOP" (papel parado em write-off) aparecer como "NOVO→WOP"
# (papel novo virou write-off no dia), o que e enganoso na matriz e no
# bucket de papeis_wop.
_VALID_FAIXAS = {"A", "B", "C", "D", "E", "F", "G", "H", "WOP"}

# Defaults atualizados 2026-05-24: Ricardo confirmou que o detalhamento
# deve mostrar TODOS os papeis com variacao de PDD (nao apenas top por
# threshold). Caso 13/05 REALINVEST: filtro >= R$ 100 cortava 49 dos 51
# papeis, escondendo R$ 268 de variacao agregada. Threshold = R$ 0,01
# elimina apenas papeis com Δ matematicamente zero (sem variacao real).
# Cap de 1000 papeis e seguranca pra carteira atipica; carteira REALINVEST
# tipica tem < 100 papeis com variacao por dia.
_DEFAULT_TOP_N = 1000
_DEFAULT_THRESHOLD_BRL = Decimal("0.01")


def _normalize_faixa_d1(raw: str | None) -> PddFaixaKey:
    """Faixa em D-1; quando o papel nao existia em D-1 (so apareceu em D0), retorna NOVO."""
    if raw is None:
        return "NOVO"
    return raw if raw in _VALID_FAIXAS else "NOVO"  # type: ignore[return-value]


def _normalize_faixa_d0(raw: str | None, seu_numero: str, liquidados_d0: set[str]) -> PddFaixaKey:
    """Faixa em D0 com distincao entre LIQUIDADO e WOP.

    Quando o papel sumiu entre D-1 e D0:
      - Esta em `wh_liquidacao_recebivel` em D0 -> LIQUIDADO (cobranca normal,
        PDD reverte por inteiro)
      - NAO esta em liquidacao -> WOP (write-off real, PDD vira perda
        definitiva)

    Antes do fix 2026-05-24 ambos caiam em "WOP", o que fazia papeis
    liquidados com PDD em D-1 sumirem invisivelmente do drill: nao entravam
    no top (filtro `faixa_d0 != WOP`) nem no bucket `papeis_wop` (cross-check
    com liquidados exclui).
    """
    if raw is None:
        if seu_numero in liquidados_d0:
            return "LIQUIDADO"
        return "WOP"
    return raw if raw in _VALID_FAIXAS else "WOP"  # type: ignore[return-value]


async def _sum_pdd_granular(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fundo_doc: str,
    data: date,
) -> Decimal:
    """Σ wh_estoque_recebivel.valor_pdd para a data (granular, TOTAL inclui WOP)."""
    stmt = (
        select(func.coalesce(func.sum(EstoqueRecebivel.valor_pdd), ZERO))
        .where(EstoqueRecebivel.tenant_id == tenant_id)
        .where(EstoqueRecebivel.fundo_doc == fundo_doc)
        .where(EstoqueRecebivel.data_referencia == data)
    )
    return Decimal((await db.execute(stmt)).scalar() or 0)


async def _sum_pdd_granular_por_bucket(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fundo_doc: str,
    data: date,
) -> tuple[Decimal, Decimal]:
    """Σ valor_pdd separado em (ex_wop, wop) para a data.

    - ex_wop = faixas A-H (= contribuicao real ao PL Sub Jr)
    - wop    = faixa WOP (= ja fora do PL, informativo)
    """
    stmt = (
        select(
            func.coalesce(
                func.sum(
                    case(
                        (EstoqueRecebivel.faixa_pdd != "WOP", EstoqueRecebivel.valor_pdd),
                        else_=ZERO,
                    )
                ),
                ZERO,
            ).label("ex_wop"),
            func.coalesce(
                func.sum(
                    case(
                        (EstoqueRecebivel.faixa_pdd == "WOP", EstoqueRecebivel.valor_pdd),
                        else_=ZERO,
                    )
                ),
                ZERO,
            ).label("wop"),
        )
        .where(EstoqueRecebivel.tenant_id == tenant_id)
        .where(EstoqueRecebivel.fundo_doc == fundo_doc)
        .where(EstoqueRecebivel.data_referencia == data)
    )
    row = (await db.execute(stmt)).one()
    return Decimal(row.ex_wop or 0), Decimal(row.wop or 0)


async def _liquidados_seu_numero_set(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fundo_doc: str,
    data: date,
) -> set[str]:
    """Set de `seu_numero` dos titulos liquidados em D0.

    Usado pelo bucket `papeis_wop` (`_build_matriz_e_papeis`) para EXCLUIR
    papeis que sumiram do estoque por liquidacao normal (recompra, baixa
    por deposito cedente/sacado, liquidacao normal) — nao sao write-off.

    `seu_numero` e a chave de business preservada entre as duas tabelas
    (a UQ do estoque inclui `numero_documento`; a UQ de liquidacao inclui
    `id_recebivel` que nao existe no estoque, entao `seu_numero` e o ponto
    mais forte de match). Em REALINVEST nao ha duplicacao de `seu_numero`
    no mesmo dia em wh_liquidacao_recebivel.
    """
    stmt = (
        select(LiquidacaoRecebivel.seu_numero)
        .where(LiquidacaoRecebivel.tenant_id == tenant_id)
        .where(LiquidacaoRecebivel.fundo_doc == fundo_doc)
        .where(LiquidacaoRecebivel.data_posicao == data)
    )
    return {row[0] for row in (await db.execute(stmt)).all() if row[0]}


async def _build_matriz_e_papeis(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    fundo_doc: str,
    data_d1: date,
    data_d0: date,
    threshold_brl: Decimal,
    top_n: int,
    liquidados_d0: set[str],
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
        faixa_d0 = _normalize_faixa_d0(
            r.faixa_pdd_d0_raw,
            seu_numero=r.seu_numero or "",
            liquidados_d0=liquidados_d0,
        )
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

        # WOP destacado — write-off NOVO no dia. Fix 2026-05-24:
        # (a) faixa_d0 == "WOP"   — papel em write-off em D0
        # (b) faixa_d1 != "WOP"   — NAO estava em WOP em D-1 (evento do dia,
        #                           nao papel parado em WOP ha dias)
        # (c) PDD relevante       — abs(valor_pdd_d1) > 0 (mantido do antigo)
        # Cross-check com liquidados_d0 agora vive no `_normalize_faixa_d0`:
        # papel liquidado retorna LIQUIDADO (nao WOP), entao automaticamente
        # nao entra aqui.
        if (
            faixa_d0 == "WOP"
            and faixa_d1 != "WOP"
            and abs(papel.valor_pdd_d1) > 0
        ):
            papeis_wop.append(papel)

        # Lista "Papeis com variacao de PDD" (exclui apenas WOP novo, que
        # ja tem destaque proprio acima). Inclui papeis LIQUIDADO no dia
        # com PDD > 0 em D-1 (PDD reversa por cobranca normal).
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

    # Granular — total + separado por bucket (ex-WOP vs WOP).
    pdd_gran_d1 = await _sum_pdd_granular(db, tenant_id=tenant_id, fundo_doc=fundo_doc, data=d1)
    pdd_gran_d0 = await _sum_pdd_granular(db, tenant_id=tenant_id, fundo_doc=fundo_doc, data=data_d0)
    pdd_gran_ex_wop_d1, pdd_gran_wop_d1 = await _sum_pdd_granular_por_bucket(
        db, tenant_id=tenant_id, fundo_doc=fundo_doc, data=d1,
    )
    pdd_gran_ex_wop_d0, pdd_gran_wop_d0 = await _sum_pdd_granular_por_bucket(
        db, tenant_id=tenant_id, fundo_doc=fundo_doc, data=data_d0,
    )

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
            pdd_granular_ex_wop_d1=pdd_gran_ex_wop_d1,
            pdd_granular_ex_wop_d0=pdd_gran_ex_wop_d0,
            pdd_granular_wop_d1=pdd_gran_wop_d1,
            pdd_granular_wop_d0=pdd_gran_wop_d0,
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

    # Fix 2026-05-24: set de liquidados em D0 pra excluir do bucket WOP
    # papeis que sumiram do estoque por liquidacao normal (recompra,
    # baixa por deposito cedente/sacado, liquidacao normal). Caso REALINVEST
    # 20/05: 4 BLB+FRICOCK apareciam como WOP por falta deste cross-check.
    liquidados_d0 = await _liquidados_seu_numero_set(
        db, tenant_id=tenant_id, fundo_doc=fundo_doc, data=data_d0,
    )

    matriz, papeis_wop, top_papeis, total_acima_threshold = await _build_matriz_e_papeis(
        db,
        tenant_id=tenant_id,
        fundo_doc=fundo_doc,
        data_d1=d1,
        data_d0=data_d0,
        threshold_brl=threshold_brl,
        top_n=top_n,
        liquidados_d0=liquidados_d0,
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
        pdd_granular_ex_wop_d1=pdd_gran_ex_wop_d1,
        pdd_granular_ex_wop_d0=pdd_gran_ex_wop_d0,
        pdd_granular_wop_d1=pdd_gran_wop_d1,
        pdd_granular_wop_d0=pdd_gran_wop_d0,
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
