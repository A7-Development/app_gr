"""Controladoria · Movimento de Contas a Pagar (CPR<0) — provisao + pagamento.

Decompoe o ΔSaldo da linha Contas a Pagar em apropriacao (accrual de taxa) vs
baixa (pagamento/estorno), e classifica os pagamentos de despesa do caixa pelo
codigo `historico` do extrato. Pagamento sem provisao compativel -> sinalizado.
Ver schema pro racional + dicionario de codigos + armadilha do saldo acumulado.

Silver-only (§13.2.1): wh_cpr_movimento + wh_extrato_bancario.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.cadastros.public import UnidadeAdministrativa
from app.modules.controladoria.schemas.conferencia_contas_a_pagar import (
    ConferenciaContasAPagarResponse,
    MovimentoProvisao,
    PagamentoDespesa,
)
from app.modules.integracoes.public import dia_util_anterior_qitech
from app.warehouse.aquisicao_recebivel import AquisicaoRecebivel
from app.warehouse.cpr_movimento import CprMovimento
from app.warehouse.extrato_bancario import ExtratoBancario
from app.warehouse.posicao_renda_fixa import PosicaoRendaFixa

ZERO = Decimal("0")
_TOL = Decimal("1.0")

# Despesa com codigo proprio (debito direto da administradora/banco).
_DESPESA_CODES: dict[str, str] = {
    "0887": "Custódia (SINGULARE)",
    "0869": "Taxa Adm FIDC (SINGULARE)",
    "0870": "Taxa Adm FIDC NP (SINGULARE)",
    "0941": "Banco Liquidante SELIC",
    "0943": "Reembolso Custo SELIC",
    "0917": "Taxa ANBIMA",
    "0919": "Taxa CVM",
    "0918": "Taxa Distribuição",
    "3053": "Taxa Registradora",
    "3051": "Auditoria de Lastro",
    "3057": "Auditoria de Exercício",
    "3045": "IOF",
    "3043": "IR decêndio",
    "0920": "IR / IOF",
    "0948": "Reembolso Prestador de Fundos",
    "0915": "Reembolso Cartório",
    "0916": "Reembolso Correios",
    "0914": "Reembolso CDT/RTD",
    "0603": "Registro de Cobrança",
}
_TARIFA_CODE = "0770"   # tarifa de TED — sempre NAO provisionada
_TED_CODE = "0307"      # TED generico — despesa so se contraparte for fornecedor

# Token canonico de despesa, pra casar pagamento <-> provisao por tipo.
_TOKENS: list[tuple[str, tuple[str, ...]]] = [
    ("custodia", ("custodia", "custódia")),
    ("gestao", ("gestao", "gestão")),
    ("administracao", ("administracao", "administração", "adm fidc", "taxa adm")),
    ("cvm", ("cvm",)),
    ("anbima", ("anbima",)),
    ("auditoria", ("auditoria", "audifac", "confiance")),
    ("consultoria", ("consultoria",)),
    ("cobranca", ("cobranca", "cobrança")),
    ("banco_liquidante", ("banco liquidante", "liquidante")),
    ("registradora", ("registradora",)),
    ("distribuicao", ("distribuicao", "distribuição")),
    ("rating", ("rating",)),
    ("imposto", ("ir decendio", "ir / iof", "ir-iof", " iof", "imposto")),
    ("selic", ("selic",)),
]


def _token(text: str | None) -> str | None:
    t = (text or "").lower()
    for canon, kws in _TOKENS:
        if any(k in t for k in kws):
            return canon
    return None


_DATE_RE = re.compile(r"\s*\d{1,2}/\d{1,2}/\d{2,4}.*$")
_TAIL_RE = re.compile(
    r"\s*(com\s+pagamento|com\s+vencimento|com\s+venc\.?|a\s+pagar\s+em|"
    r"a\s+diferir.*|com\s+venc|em)\s*$",
    re.IGNORECASE,
)


def _norm_desc(d: str | None) -> str:
    """Remove a data (errada) e o sufixo de pagamento/vencimento da descricao."""
    s = _DATE_RE.sub("", d or "")
    s = _TAIL_RE.sub("", s).strip(" .-")
    return s or (d or "")


async def compute_movimento_contas_a_pagar(
    db: AsyncSession,
    *,
    tenant_id: UUID,
    ua_id: UUID,
    data_d0: date,
    data_d1: date | None = None,
) -> ConferenciaContasAPagarResponse:
    """Movimento de Contas a Pagar do dia: provisoes (CPR<0) + pagamentos."""
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

    # ── Provisoes CPR<0 por descricao normalizada (saldo por tipo) ──────────
    async def _load_cpr(data: date) -> dict[str, Decimal]:
        stmt = (
            select(CprMovimento.descricao, CprMovimento.valor)
            .where(CprMovimento.tenant_id == tenant_id)
            .where(CprMovimento.unidade_administrativa_id == ua_id)
            .where(CprMovimento.data_posicao == data)
            .where(CprMovimento.valor < 0)
        )
        acc: dict[str, Decimal] = {}
        for desc, valor in (await db.execute(stmt)).all():
            key = _norm_desc(desc)
            acc[key] = acc.get(key, ZERO) + Decimal(valor or 0)
        return acc

    cpr1 = await _load_cpr(d1)
    cpr0 = await _load_cpr(data_d0)

    saldo_cpr_d1 = sum(cpr1.values(), ZERO)
    saldo_cpr_d0 = sum(cpr0.values(), ZERO)

    provisoes: list[MovimentoProvisao] = []
    tot_aprop = tot_baixa = ZERO
    tokens_baixados: set[str] = set()
    baixa_valores: list[Decimal] = []  # magnitudes baixadas (pra match por valor)
    for key in sorted(set(cpr1) | set(cpr0)):
        s1 = cpr1.get(key, ZERO)
        s0 = cpr0.get(key, ZERO)
        delta = s0 - s1  # <0 apropriou (mais negativo), >0 baixou
        if abs(delta) < _TOL:
            continue
        if key not in cpr1:
            tipo = "nova_provisao"
        elif key not in cpr0 or abs(s0) < _TOL:
            tipo = "quitada"
        elif delta < 0:
            tipo = "apropriacao"
        else:
            tipo = "baixa"
        if delta < 0:
            tot_aprop += -delta
        else:
            tot_baixa += delta
            baixa_valores.append(delta)
            tk = _token(key)
            if tk:
                tokens_baixados.add(tk)
        provisoes.append(
            MovimentoProvisao(
                descricao=key, saldo_d1=s1, saldo_d0=s0, delta=delta, tipo=tipo,  # type: ignore[arg-type]
            )
        )
    provisoes.sort(key=lambda p: -abs(p.delta))

    # ── Pagamentos de despesa no caixa (D0) ─────────────────────────────────
    cedentes = {
        r[0]
        for r in (
            await db.execute(
                select(AquisicaoRecebivel.cedente_doc.distinct()).where(
                    AquisicaoRecebivel.cedente_doc.isnot(None)
                )
            )
        ).all()
    }
    nc_emit = {
        r[0]
        for r in (
            await db.execute(
                select(PosicaoRendaFixa.cnpj_emitente.distinct())
                .where(PosicaoRendaFixa.nome_do_papel.in_(("NCPX", "VCNC", "PDDNC")))
                .where(PosicaoRendaFixa.cnpj_emitente.isnot(None))
            )
        ).all()
    }

    deb = (
        await db.execute(
            select(
                ExtratoBancario.historico,
                ExtratoBancario.valor,
                ExtratoBancario.contrapartida_nome,
                ExtratoBancario.contrapartida_doc,
            )
            .where(ExtratoBancario.tenant_id == tenant_id)
            .where(ExtratoBancario.unidade_administrativa_id == ua_id)
            .where(ExtratoBancario.data_lancamento == data_d0)
            .where(ExtratoBancario.tipo == "D")
        )
    ).all()

    pagamentos: list[PagamentoDespesa] = []
    tot_pago = tot_nao_prov = ZERO
    for hist, valor, cp_nome, cp_doc in deb:
        v = abs(Decimal(valor or 0))
        h = (hist or "").strip()
        if h in _DESPESA_CODES:
            canal, label, tk = "codigo_proprio", _DESPESA_CODES[h], _token(_DESPESA_CODES[h])
        elif h == _TARIFA_CODE:
            canal, label, tk = "tarifa_ted", "Tarifa de TED", None
        elif h == _TED_CODE:
            doc = (cp_doc or "").strip()
            if doc in cedentes or doc in nc_emit or doc == fundo_doc or not doc:
                continue  # cessao / NC / interno — tem dono
            canal, label, tk = "ted_fornecedor", (cp_nome or "fornecedor").strip(), _token(cp_nome)
        else:
            continue  # codigo interno / nao-despesa

        # Provisionado = casa provisao baixada por TIPO (token) OU por VALOR
        # (ex.: Tercon nao tem 'gestao' no nome, mas paga R$ 6.960,44 = a baixa
        # da Taxa de Gestao). Tarifa de TED nunca passa pelo CPR.
        if canal == "tarifa_ted":
            provisionado = False
        else:
            provisionado = (tk is not None and tk in tokens_baixados) or any(
                abs(v - bv) < _TOL for bv in baixa_valores
            )

        tot_pago += v
        if not provisionado:
            tot_nao_prov += v
        pagamentos.append(
            PagamentoDespesa(
                canal=canal,  # type: ignore[arg-type]
                historico=h, label=label,
                contrapartida=(cp_nome or None) if canal == "ted_fornecedor" else None,
                valor=v, provisionado=provisionado,
            )
        )
    pagamentos.sort(key=lambda p: (-p.valor))

    return ConferenciaContasAPagarResponse(
        fundo_id=str(ua_id),
        fundo_nome=ua.nome,
        data=data_d0,
        data_anterior=d1,
        saldo_cpr_d1=saldo_cpr_d1,
        saldo_cpr_d0=saldo_cpr_d0,
        delta_cpr=saldo_cpr_d0 - saldo_cpr_d1,
        total_apropriacao=tot_aprop,
        total_baixa=tot_baixa,
        provisoes=provisoes,
        pagamentos=pagamentos,
        total_pago=tot_pago,
        total_nao_provisionado=tot_nao_prov,
    )
