"""Controladoria · Movimento de Nota Comercial (Op. Estruturadas) — posicao-first.

Abre o ΔSaldo da linha "Op. Estruturadas" do balanco Cota Sub em movimentos por
codigo de NC, lendo a posicao (wh_posicao_renda_fixa, nome_do_papel NCPX/VCNC/
PDDNC). Ver schema pro racional + o desafio do caixa (liquidacao da NC vem como
transferencia interna do fundo, generica a DC+NC -> extrato so como sinal soft).

Silver-only (§13.2.1): wh_posicao_renda_fixa (autoritativo) + wh_extrato_bancario (soft).
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.conferencia_nota_comercial import (
    ConferenciaNotaComercialResponse,
    MovimentoNotaComercial,
    SinalExtratoNC,
)
from app.modules.integracoes.public import dia_util_anterior_qitech
from app.warehouse.extrato_bancario import ExtratoBancario
from app.warehouse.posicao_renda_fixa import PosicaoRendaFixa

ZERO = Decimal("0")
_NOMES_NC = ("NCPX", "VCNC", "PDDNC")
# Abaixo disso, Δ valor_bruto e ruido (nem carrego conta).
_TOL = Decimal("1.0")
# Banda do sinal soft do extrato (amortizacao e LIQUIDA do carrego; o credito
# bruto inclui o carrego do dia -> tolera algumas centenas).
_BANDA_SOFT = Decimal("600.0")
_TOL_AQUISICAO = Decimal("0.01")


def _fmt(v: Decimal) -> str:
    return f"R$ {float(v):,.2f}"


async def compute_conferencia_nota_comercial(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date | None = None,
) -> ConferenciaNotaComercialResponse:
    """Movimento das NCs do dia (aquisicao/amortizacao/quitacao/apropriacao)."""
    ua = (
        await db.execute(
            select(UnidadeAdministrativa)
            .where(UnidadeAdministrativa.tenant_id == tenant_id)
            .where(UnidadeAdministrativa.id == ua_id)
        )
    ).scalar_one_or_none()
    if ua is None:
        raise ValueError(f"Unidade Administrativa {ua_id} nao encontrada")

    d1 = data_d1 or await dia_util_anterior_qitech(
        db, tenant_id=tenant_id, ua_id=ua_id, data_d0=data_d0,
    )

    async def _load(data: date) -> dict[str, dict]:
        stmt = (
            select(
                PosicaoRendaFixa.codigo,
                PosicaoRendaFixa.emitente,
                PosicaoRendaFixa.cnpj_emitente,
                PosicaoRendaFixa.data_vencimento,
                PosicaoRendaFixa.valor_bruto,
                PosicaoRendaFixa.valor_aplicado,
            )
            .where(PosicaoRendaFixa.tenant_id == tenant_id)
            .where(PosicaoRendaFixa.unidade_administrativa_id == ua_id)
            .where(PosicaoRendaFixa.data_posicao == data)
            .where(PosicaoRendaFixa.nome_do_papel.in_(_NOMES_NC))
        )
        out: dict[str, dict] = {}
        for cod, emit, cnpj, venc, bruto, aplic in (await db.execute(stmt)).all():
            out[cod] = {
                "emitente": emit or "",
                "cnpj_emitente": cnpj or "",
                "data_vencimento": venc,
                "valor_bruto": Decimal(bruto or 0),
                "valor_aplicado": Decimal(aplic or 0),
            }
        return out

    pos_d1 = await _load(d1)
    pos_d0 = await _load(data_d0)

    pos_total_d1 = sum((r["valor_bruto"] for r in pos_d1.values()), ZERO)
    pos_total_d0 = sum((r["valor_bruto"] for r in pos_d0.values()), ZERO)

    # ── Classifica cada codigo ──────────────────────────────────────────────
    movimentos: list[MovimentoNotaComercial] = []
    tot_aquis = tot_amort = tot_aprop = ZERO

    for cod in sorted(set(pos_d1) | set(pos_d0)):
        r1 = pos_d1.get(cod)
        r0 = pos_d0.get(cod)
        meta = r0 or r1
        b1 = r1["valor_bruto"] if r1 else ZERO
        b0 = r0["valor_bruto"] if r0 else ZERO
        delta = b0 - b1
        aplicado = (meta or {}).get("valor_aplicado", ZERO)
        emit = (meta or {})["emitente"]

        if r1 is None and b0 > _TOL:  # nova
            tipo, caixa = "aquisicao", -aplicado
            tot_aquis += aplicado
            bullet = f"{cod} {emit}: aquisicao de {_fmt(aplicado)} (caixa saiu)."
        elif b0 <= _TOL < b1:  # zerou/sumiu
            tipo, caixa = "quitacao", b1
            tot_amort += b1
            bullet = f"{cod} {emit}: quitada — posicao caiu de {_fmt(b1)} a zero."
        elif delta < -_TOL:  # amortizacao parcial
            tipo, caixa = "amortizacao", -delta
            tot_amort += -delta
            bullet = (
                f"{cod} {emit}: amortizacao de {_fmt(-delta)} (reducao liquida do "
                f"carrego; bruto recebido ~ {_fmt(-delta)} + carrego do dia)."
            )
        elif delta > _TOL:  # apropriacao (carrego)
            tipo, caixa = "apropriacao", ZERO
            tot_aprop += delta
            bullet = f"{cod} {emit}: carrego de {_fmt(delta)} (juros do dia, sem caixa)."
        else:
            continue  # sem mudanca relevante

        movimentos.append(
            MovimentoNotaComercial(
                codigo=cod,
                emitente=emit,
                cnpj_emitente=(meta or {})["cnpj_emitente"],
                tipo=tipo,  # type: ignore[arg-type]
                data_vencimento=(meta or {}).get("data_vencimento"),
                valor_bruto_d1=b1,
                valor_bruto_d0=b0,
                delta_bruto=delta,
                valor_aplicado=aplicado,
                caixa_evento=caixa,
                bullet=bullet,
            )
        )

    # ── Sinal SOFT do extrato (indicio, nao prova) ──────────────────────────
    await _anexa_sinais_extrato(db, tenant_id, ua_id, data_d0, movimentos)

    # Ordena: caixa primeiro (aquisicao/amort/quit), carrego depois; |valor| desc.
    _rank = {"aquisicao": 0, "quitacao": 1, "amortizacao": 1, "apropriacao": 2}
    movimentos.sort(key=lambda m: (_rank[m.tipo], -abs(m.caixa_evento or m.delta_bruto)))

    return ConferenciaNotaComercialResponse(
        fundo_id=str(ua_id),
        fundo_nome=ua.nome,
        data=data_d0,
        data_anterior=d1,
        posicao_total_d1=pos_total_d1,
        posicao_total_d0=pos_total_d0,
        delta_posicao=pos_total_d0 - pos_total_d1,
        n_notas_d0=len(pos_d0),
        total_aquisicao=tot_aquis,
        total_amortizacao=tot_amort,
        total_apropriacao=tot_aprop,
        movimentos=movimentos,
    )


async def _anexa_sinais_extrato(
    db: AsyncSession,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    movimentos: list[MovimentoNotaComercial],
) -> None:
    """Best-effort SOFT: marca indicio de valor compativel no extrato.

    - aquisicao: debito ao cnpj_emitente ~ valor_aplicado em [D0-5, D0].
    - amort/quit: credito 'TRANSF LIQU E BAIX' ~ caixa_evento em [D0-1, D0+1].
    NUNCA autoritativo (a liquidacao da NC e transferencia interna do fundo).
    """
    eventos = [m for m in movimentos if m.tipo in ("aquisicao", "amortizacao", "quitacao")]
    if not eventos:
        return

    janela_ini = data_d0 - timedelta(days=5)
    janela_fim = data_d0 + timedelta(days=1)
    cnpjs = {m.cnpj_emitente for m in eventos if m.cnpj_emitente}

    conds = [ExtratoBancario.descricao.ilike("%TRANSF%LIQU%BAIX%")]
    if cnpjs:
        conds.append(ExtratoBancario.contrapartida_doc.in_(cnpjs))
    stmt = (
        select(
            ExtratoBancario.data_lancamento,
            ExtratoBancario.tipo,
            ExtratoBancario.valor,
            ExtratoBancario.contrapartida_doc,
            ExtratoBancario.descricao,
        )
        .where(ExtratoBancario.tenant_id == tenant_id)
        .where(ExtratoBancario.data_lancamento >= janela_ini)
        .where(ExtratoBancario.data_lancamento <= janela_fim)
        .where(or_(*conds))
    )
    rows = [
        (dl, tp, Decimal(v or 0), doc, desc)
        for dl, tp, v, doc, desc in (await db.execute(stmt)).all()
    ]
    ext_disp = bool(rows)

    nota_soft = (
        "Liquidacao da NC vem como transferencia interna do fundo (generica a "
        "DC+NC) — confirma valor, nao o pagador."
    )
    for m in eventos:
        achou = None
        if m.tipo == "aquisicao":
            alvo = m.valor_aplicado
            for dl, tp, v, doc, desc in rows:
                if tp == "D" and doc == m.cnpj_emitente and abs(v - alvo) < _TOL_AQUISICAO:
                    achou = (dl, v, desc)
                    break
        else:  # amortizacao / quitacao
            alvo = m.caixa_evento
            for dl, tp, v, _doc, desc in rows:
                if tp == "C" and abs(v - alvo) < _BANDA_SOFT and "LIQU" in (desc or "").upper():
                    achou = (dl, v, desc)
                    break
        if achou:
            dl, v, desc = achou
            m.extrato_sinal = SinalExtratoNC(
                encontrado=True, valor=v,
                data_lancamento=dl.date() if hasattr(dl, "date") else dl,
                descricao=(desc or "")[:60], nota=nota_soft,
            )
        else:
            m.extrato_sinal = SinalExtratoNC(
                encontrado=False, nota=("extrato sem dado no periodo" if not ext_disp else nota_soft),
            )
