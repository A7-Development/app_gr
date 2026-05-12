"""Spike: balancete patrimonial diário COSIF para Cota Subordinada.

Valida o modelo proposto em
`C:\\Users\\RicardoPimenta\\.claude\\plans\\analise-esse-documento-que-elegant-moth.md`:

  PL Cota Sub = Σ_silver_total − |Cotas Sr emitidas| − |Cotas Mez emitidas|
  ΔPL Cota Sub = ΔΣ_silver − Δ|Sr emitidas| − Δ|Mez emitidas|

Lê os silvers em D-1 e D0, classifica cada linha em cosif via cascata
(override → regra estrutural → pendente), agrega em árvore hierárquica
COSIF e produz 3 CSVs:

  spike_balancete_diario.csv      árvore COSIF com saldos D-1, D0, Δ
  spike_reconciliacao.csv         equação ΔPL Sub = ΔAtivo − ΔPassivo − ΔSr − ΔMez
  spike_cobertura.csv             % rows classificadas por source

Uso (de backend/):
    .venv\\Scripts\\python.exe scripts/spike_cota_sub_cosif.py \\
        --ua "REALINVEST FIDC" --d-1 2026-05-07 --d0 2026-05-08

Sem --out: grava em `scripts/out/`.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID

import app.shared.identity.tenant  # noqa: F401  (registry SQLAlchemy)
from app.core.database import AsyncSessionLocal
from sqlalchemy import text


# ─── CATÁLOGO COSIF (extrato do balancete oficial REALINVEST mar/2026) ──────
# Suficiente para o spike validar o modelo. Migration de Fase 1 fará seed
# completo do PLANO COSIF II.
# Formato: codigo -> (nome, natureza D|C, parent)

COSIF_CATALOG: dict[str, tuple[str, str, str | None]] = {
    # Grupo 1 — Ativo
    "1":                    ("CIRCULANTE E REALIZAVEL A LONGO PRAZO", "D", None),
    "1.1":                  ("DISPONIBILIDADES", "D", "1"),
    "1.1.2":                ("DEPOSITOS BANCARIOS", "D", "1.1"),
    "1.1.2.80":             ("BANCOS PRIVADOS - CONTA DEPOSITOS", "D", "1.1.2"),
    "1.1.2.80.00.001":      ("BANCOS CONTA MOVIMENTO", "D", "1.1.2.80"),
    "1.1.2.80.00.002":      ("BANCO BRADESCO S/A", "D", "1.1.2.80"),
    "1.1.2.80.00.007":      ("SINGULARE CORRETORA - CONCILIACAO", "D", "1.1.2.80"),
    "1.3":                  ("TVM E INSTRUMENTOS FINANC. DERIVATIVOS", "D", "1"),
    "1.3.1":                ("LIVRES", "D", "1.3"),
    "1.3.1.10":             ("TITULOS DE RENDA FIXA", "D", "1.3.1"),
    "1.3.1.10.07":          ("NOTAS DO TESOURO NACIONAL", "D", "1.3.1.10"),
    "1.3.1.10.07.001":      ("NTN - NOTAS DO TESOURO NACIONAL", "D", "1.3.1.10.07"),
    "1.3.1.10.16":          ("NOTAS DO BANCO CENTRAL", "D", "1.3.1.10"),
    "1.3.1.10.16.001":      ("NOTA COMERCIAL", "D", "1.3.1.10.16"),
    "1.3.1.15":             ("COTAS DE FUNDOS DE INVESTIMENTO", "D", "1.3.1"),
    "1.3.1.15.30":          ("COTAS DE FUNDOS MUTUOS DE RENDA FIXA", "D", "1.3.1.15"),
    "1.3.1.15.30.001":      ("COTAS DE FUNDOS DE RENDA FIXA", "D", "1.3.1.15.30"),
    "1.6":                  ("OPERACOES DE CREDITO", "D", "1"),
    "1.6.1":                ("EMPRESTIMOS E TITULOS DESCONTADOS", "D", "1.6"),
    "1.6.1.30":             ("TITULOS DESCONTADOS", "D", "1.6.1"),
    "1.6.1.30.00.001":      ("RECEBIVEIS EM CURSO NORMAL", "D", "1.6.1.30"),
    "1.6.1.30.00.002":      ("RECEBIVEIS VENCIDOS", "D", "1.6.1.30"),
    "1.6.9":                ("PROVISAO PARA OP. DE CREDITO (-)", "C", "1.6"),
    "1.6.9.97.00.001":      ("(-) PDD - PROVISAO PARA DEVEDORES DUVIDOSOS", "C", "1.6.9"),
    "1.8":                  ("OUTROS CREDITOS", "D", "1"),
    "1.8.4":                ("NEGOCIACAO E INTERMEDIACAO DE VALORES", "D", "1.8"),
    "1.8.4.30":             ("DEVEDORES - CONTA LIQUIDACOES PENDENTES", "D", "1.8.4"),
    "1.8.4.30.00.005":      ("AJUSTE DE COMPENSACAO DE COTA", "D", "1.8.4.30"),
    "1.9":                  ("OUTROS VALORES E BENS", "D", "1"),
    "1.9.9":                ("DESPESAS ANTECIPADAS", "D", "1.9"),
    "1.9.9.10.00":          ("DESPESAS ANTECIPADAS", "D", "1.9.9"),
    # Grupo 4 — Passivo
    "4":                    ("CIRCULANTE E EXIGIVEL A LONGO PRAZO", "C", None),
    "4.9":                  ("OUTRAS OBRIGACOES", "C", "4"),
    "4.9.1":                ("COBRANCA E ARRECADACAO DE TRIBUTOS", "C", "4.9"),
    "4.9.1.10":             ("IOF A RECOLHER", "C", "4.9.1"),
    "4.9.1.10.00.001":      ("IOF A RECOLHER", "C", "4.9.1.10"),
    "4.9.9":                ("DIVERSAS", "C", "4.9"),
    "4.9.9.30":             ("PROVISAO PARA PAGAMENTOS A EFETUAR", "C", "4.9.9"),
    "4.9.9.30.50":          ("OUTRAS DESPESAS ADMINISTRATIVAS", "C", "4.9.9.30"),
    "4.9.9.30.50.002":      ("AUDITORIA", "C", "4.9.9.30.50"),
    "4.9.9.30.50.003":      ("CONSULTORIA ESPECIALIZADA", "C", "4.9.9.30.50"),
    "4.9.9.30.50.004":      ("BANCO LIQUIDANTE", "C", "4.9.9.30.50"),
    "4.9.9.30.50.005":      ("SELIC", "C", "4.9.9.30.50"),
    "4.9.9.30.50.008":      ("TAXA DE CUSTODIA", "C", "4.9.9.30.50"),
    "4.9.9.30.50.021":      ("DESPESAS DE COBRANCA", "C", "4.9.9.30.50"),
    "4.9.9.30.90":          ("OUTROS PAGAMENTOS", "C", "4.9.9.30"),
    "4.9.9.30.90.005":      ("CREDITOS A CONCILIAR", "C", "4.9.9.30.90"),
    "4.9.9.83":             ("VALORES A PAGAR A SOC. ADMINISTRADORA", "C", "4.9.9"),
    "4.9.9.83.00":          ("VALORES A PAGAR A SOC. ADMINISTRADORA", "C", "4.9.9.83"),
    "4.9.9.83.00.001":      ("TAXA DE ADMINISTRACAO", "C", "4.9.9.83.00"),
    "4.9.9.83.00.004":      ("TAXA DE GESTAO", "C", "4.9.9.83.00"),
    # Grupo 6 — PL (cotas emitidas)
    "6":                    ("PATRIMONIO LIQUIDO", "C", None),
    "6.1":                  ("PATRIMONIO LIQUIDO", "C", "6"),
    "6.1.1":                ("CAPITAL SOCIAL", "C", "6.1"),
    "6.1.1.70":             ("COTAS DE INVESTIMENTO", "C", "6.1.1"),
    "6.1.1.70.30.001":      ("PESSOAS JURIDICAS - EMISSAO", "C", "6.1.1.70"),
    "6.1.1.70.20.001":      ("PESSOAS FISICAS - EMISSAO", "C", "6.1.1.70"),
    # Grupo 8 — DRE (despesas acumuladas do mes — competência)
    "8":                    ("CONTAS DE RESULTADO DEVEDORAS", "D", None),
    "8.1":                  ("DESPESAS OPERACIONAIS", "D", "8"),
    "8.1.7":                ("DESPESAS ADMINISTRATIVAS", "D", "8.1"),
    "8.1.7.54":             ("DESPESAS DE SERVICOS DO SISTEMA FINANCEIRO", "D", "8.1.7"),
    "8.1.7.54.00.004":      ("TAXA DE CUSTODIA (DRE)", "D", "8.1.7.54"),
    "8.1.7.81":             ("DESPESAS DE TAXA DE ADMINISTRACAO DO FUNDO", "D", "8.1.7"),
    "8.1.7.81.00.001":      ("TAXA DE ADMINISTRACAO (DRE)", "D", "8.1.7.81"),
    "8.1.7.81.00.004":      ("TAXA DE GESTAO (DRE)", "D", "8.1.7.81"),
    # Fallback
    "PENDENTE":             ("(nao classificado)", "?", None),
}


# ─── CLASSIFIER ──────────────────────────────────────────────────────────────
# Cascata: override de tenant (hardcoded por enquanto) → regra estrutural →
# pendente. Cada result carrega cosif + source + rule_id para auditoria.

@dataclass
class ClassifyResult:
    cosif: str
    source: str           # "rule" | "override" | "pendente"
    rule_id: str | None = None
    classe_sr_mez_sub: str | None = None  # senior | mezanino | subordinado | compensacao


# Overrides simulados para REALINVEST (no Fase 1 vêm de tenant_papel_classificacao
# editado pelo admin via /admin/cosif). Hoje hardcoded só para o spike.
REALINVEST_OVERRIDES: dict[tuple[str, str], tuple[str, str | None]] = {
    # (silver_origin, identificador) -> (cosif, classe_sr_mez_sub)
    # Identificador estável do admin (campo "código" do payload).
    ("wh_saldo_conta_corrente", "BRADESCO"): ("1.1.2.80.00.002", None),
    ("wh_saldo_conta_corrente", "SOCOPA"):   ("1.1.2.80.00.007", None),
    ("wh_saldo_conta_corrente", "CONCILIA"): ("4.9.9.30.90.005", None),
    ("wh_posicao_cota_fundo",   "REALIAVE"): ("1.6.1.30.00.001", None),
    ("wh_posicao_cota_fundo",   "REALIVEN"): ("1.6.1.30.00.002", None),
    ("wh_posicao_outros_ativos","PDD"):       ("1.6.9.97.00.001", None),
}


def classify(silver_origin: str, row: dict[str, Any]) -> ClassifyResult:
    """Cascata override → rule → pendente.

    Identificador para override: campo "codigo" do row (estável no admin).
    """
    cod = (row.get("codigo") or "").upper().strip()

    # 1. Override
    override = REALINVEST_OVERRIDES.get((silver_origin, cod))
    if override:
        cosif, classe = override
        return ClassifyResult(cosif, "override", rule_id=None, classe_sr_mez_sub=classe)

    # 2. Regras estruturais por silver_origin
    if silver_origin == "wh_saldo_conta_corrente":
        return ClassifyResult("PENDENTE", "pendente")
    if silver_origin == "wh_saldo_tesouraria":
        return ClassifyResult("1.1.2.80.00.001", "rule", rule_id="tesouraria.bancos_movimento")
    if silver_origin == "wh_posicao_compromissada":
        return ClassifyResult("1.2.1.10.05.001", "rule", rule_id="compromissada.ltn")
    if silver_origin == "wh_posicao_cota_fundo":
        nome = (row.get("ativo_nome") or "").upper()
        if "VENCER" in nome:
            return ClassifyResult("1.6.1.30.00.001", "rule", rule_id="cf.dc_a_vencer")
        if "VENCIDO" in nome:
            return ClassifyResult("1.6.1.30.00.002", "rule", rule_id="cf.dc_vencidos")
        return ClassifyResult("1.3.1.15.30.001", "rule", rule_id="cf.di_rf")
    if silver_origin == "wh_posicao_outros_ativos":
        return ClassifyResult("1.8.4.30.00.005", "rule", rule_id="oa.ajuste_compensacao")
    if silver_origin == "wh_posicao_renda_fixa":
        papel = (row.get("nome_do_papel") or "").upper()
        qtde = Decimal(str(row.get("quantidade") or 0))
        if qtde < 0:
            # Cota emitida pelo fundo — passivo sob otica Cota Sub.
            if papel.startswith("SR"):
                return ClassifyResult("6.1.1.70.30.001", "rule",
                                      rule_id="rf.cota_sr_emitida", classe_sr_mez_sub="senior")
            if papel.startswith("MEZ"):
                return ClassifyResult("6.1.1.70.30.001", "rule",
                                      rule_id="rf.cota_mez_emitida", classe_sr_mez_sub="mezanino")
            if papel.startswith("SUB"):
                return ClassifyResult("6.1.1.70.30.001", "rule",
                                      rule_id="rf.cota_sub_emitida", classe_sr_mez_sub="subordinado")
            return ClassifyResult("PENDENTE", "pendente",
                                  rule_id="rf.cota_emitida_sem_classe")
        # qtde >= 0
        if papel.startswith(("SR", "MEZ", "SUB")):
            # Contrapartida positiva da cota emitida — compensacao (grupos 3/9).
            return ClassifyResult("PENDENTE", "rule",
                                  rule_id="rf.contrapartida_compensacao",
                                  classe_sr_mez_sub="compensacao")
        if "NTN" in papel:
            return ClassifyResult("1.3.1.10.07.001", "rule", rule_id="rf.ntn")
        if "NCPX" in papel or "NOTA" in papel:
            return ClassifyResult("1.3.1.10.16.001", "rule", rule_id="rf.nota_comercial")
        return ClassifyResult("PENDENTE", "pendente")
    if silver_origin == "wh_cpr_movimento":
        hist = (row.get("historico_traduzido") or "").upper()
        desc = (row.get("descricao") or "").upper()
        txt = hist + " " + desc

        # CPR vem em 5 sabores semânticos no payload QiTech. Ordem de teste
        # importa — específico antes de genérico.

        # (1) APORTE — emissão de cotas (PL). Antes de qualquer outra regra.
        if "APORTE" in txt:
            return ClassifyResult("6.1.1.70.30.001", "rule", rule_id="cpr.aporte")

        # (2) LIQUIDADOS — liquidações pendentes (Ativo Outros Créditos).
        if "LIQUIDADOS" in txt:
            return ClassifyResult("1.8.4.30.00.005", "rule", rule_id="cpr.liquidados")

        # (3) DIFERIMENTO / a Diferir — despesa antecipada (Ativo).
        if "DIFERIMENTO" in txt or "DIFERIR" in txt:
            return ClassifyResult("1.9.9.10.00", "rule", rule_id="cpr.diferimento")

        # (4) IOF a Recolher — passivo tributário.
        if "IOF" in txt:
            return ClassifyResult("4.9.1.10.00.001", "rule", rule_id="cpr.iof.recolher")

        # (5) CONCILIAR — passivo conciliação.
        if "CONCILIAR" in txt:
            return ClassifyResult("4.9.9.30.90.005", "rule", rule_id="cpr.creditos_conciliar")

        # (6) APROPRIADA — competência mensal (DRE — grupo 8).
        # Reconhecimento contábil de despesa apropriada no mês corrente.
        if "APROPRIADA" in hist:
            if "CUSTODIA" in hist or "CUSTÓDIA" in hist:
                return ClassifyResult("8.1.7.54.00.004", "rule", rule_id="cpr.dre.custodia")
            if "ADMINISTRACAO" in hist or "ADMINISTRAÇÃO" in hist:
                return ClassifyResult("8.1.7.81.00.001", "rule", rule_id="cpr.dre.adm")
            if "GESTAO" in hist or "GESTÃO" in hist:
                return ClassifyResult("8.1.7.81.00.004", "rule", rule_id="cpr.dre.gestao")
            # Outras "Apropriada" caem em DRE genérico.
            return ClassifyResult("8.1.7", "rule", rule_id="cpr.dre.outras_adm")

        # (7) "Despesa de X com pagamento DD/MM" / "Despesas com X em DD/MM" —
        # provisão a pagar futura (Passivo 4.9.x).
        if "AUDITORIA" in txt:
            return ClassifyResult("4.9.9.30.50.002", "rule", rule_id="cpr.passivo.auditoria")
        if "CUSTODIA" in txt or "CUSTÓDIA" in txt:
            return ClassifyResult("4.9.9.30.50.008", "rule", rule_id="cpr.passivo.custodia")
        if "BANCO LIQUIDANTE" in txt:
            return ClassifyResult("4.9.9.30.50.004", "rule", rule_id="cpr.passivo.banco_liquidante")
        if "SELIC" in txt:
            return ClassifyResult("4.9.9.30.50.005", "rule", rule_id="cpr.passivo.selic")
        if "COBRANCA" in txt or "COBRANÇA" in txt:
            return ClassifyResult("4.9.9.30.50.021", "rule", rule_id="cpr.passivo.cobranca")
        if "CONSULTORIA" in txt:
            return ClassifyResult("4.9.9.30.50.003", "rule", rule_id="cpr.passivo.consultoria")
        if "ADMINISTRACAO" in txt or "ADMINISTRAÇÃO" in txt:
            return ClassifyResult("4.9.9.83.00.001", "rule", rule_id="cpr.passivo.adm")
        if "GESTAO" in txt or "GESTÃO" in txt:
            return ClassifyResult("4.9.9.83.00.004", "rule", rule_id="cpr.passivo.gestao")

        return ClassifyResult("4.9.9.30", "rule", rule_id="cpr.outras_provisoes")
    return ClassifyResult("PENDENTE", "pendente")


# ─── EXTRAÇÃO ────────────────────────────────────────────────────────────────
# Lê todos os silvers para uma data. Retorna lista uniforme de dicts com
# `silver_origin`, `codigo`, `valor`, `extras` para classificar.

@dataclass
class SilverRow:
    silver_origin: str
    codigo: str | None
    nome: str
    valor: Decimal
    raw: dict[str, Any]  # para classify ter acesso aos campos


_QUERIES: dict[str, str] = {
    "wh_saldo_conta_corrente": """
        SELECT codigo, descricao AS nome, valor_total AS valor, codigo AS k
        FROM wh_saldo_conta_corrente
        WHERE unidade_administrativa_id = :ua AND data_posicao = :d
    """,
    "wh_saldo_tesouraria": """
        SELECT NULL AS codigo, descricao AS nome, valor, descricao AS k
        FROM wh_saldo_tesouraria
        WHERE unidade_administrativa_id = :ua AND data_posicao = :d
    """,
    "wh_posicao_compromissada": """
        SELECT codigo, papel AS nome, valor_bruto AS valor, codigo AS k
        FROM wh_posicao_compromissada
        WHERE unidade_administrativa_id = :ua AND data_posicao = :d
    """,
    "wh_posicao_renda_fixa": """
        SELECT codigo, nome_do_papel AS nome, valor_bruto AS valor,
               nome_do_papel, quantidade, indexador, codigo AS k
        FROM wh_posicao_renda_fixa
        WHERE unidade_administrativa_id = :ua AND data_posicao = :d
    """,
    "wh_posicao_cota_fundo": """
        SELECT ativo_codigo AS codigo, ativo_nome AS nome, valor_atual AS valor,
               ativo_nome, ativo_codigo AS k
        FROM wh_posicao_cota_fundo
        WHERE unidade_administrativa_id = :ua AND data_posicao = :d
    """,
    "wh_posicao_outros_ativos": """
        SELECT codigo, descricao AS nome, valor_total AS valor, codigo AS k
        FROM wh_posicao_outros_ativos
        WHERE unidade_administrativa_id = :ua AND data_posicao = :d
    """,
    "wh_cpr_movimento": """
        SELECT NULL AS codigo, COALESCE(historico_traduzido, descricao) AS nome,
               valor, historico_traduzido, descricao,
               COALESCE(historico_traduzido, descricao) AS k
        FROM wh_cpr_movimento
        WHERE unidade_administrativa_id = :ua AND data_posicao = :d
    """,
}


async def fetch_silver(db, ua_id: UUID, d: date) -> list[SilverRow]:
    out: list[SilverRow] = []
    for origin, sql in _QUERIES.items():
        result = await db.execute(text(sql), {"ua": ua_id, "d": d})
        for row in result.mappings().all():
            r = dict(row)
            out.append(SilverRow(
                silver_origin=origin,
                codigo=r.get("codigo"),
                nome=r.get("nome") or "",
                valor=Decimal(str(r.get("valor") or 0)),
                raw=r,
            ))
    return out


# ─── AGREGAÇÃO POR COSIF ─────────────────────────────────────────────────────

def aggregate_by_cosif(rows: list[SilverRow]) -> dict[str, Decimal]:
    """Retorna {cosif_codigo: saldo_total} aplicando classifier."""
    totais: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for r in rows:
        cls = classify(r.silver_origin, r.raw)
        totais[cls.cosif] += r.valor
    return dict(totais)


def propagate_to_parents(saldos_analiticos: dict[str, Decimal]) -> dict[str, Decimal]:
    """Cada analítico contribui para todos os ancestrais via parent_codigo."""
    out: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    for cosif, valor in saldos_analiticos.items():
        cur = cosif
        while cur is not None:
            out[cur] += valor
            info = COSIF_CATALOG.get(cur)
            if info is None:
                break
            cur = info[2]  # parent
    return dict(out)


# ─── COTAS Sr/Mez EMITIDAS (módulo) ──────────────────────────────────────────

def sum_cotas_emitidas(rows: list[SilverRow], classe: str) -> Decimal:
    """Soma |valor_bruto| das cotas emitidas (qtde<0) da classe Sr ou Mez."""
    total = Decimal(0)
    for r in rows:
        if r.silver_origin != "wh_posicao_renda_fixa":
            continue
        cls = classify(r.silver_origin, r.raw)
        if cls.classe_sr_mez_sub == classe:
            total += abs(r.valor)
    return total


# ─── COBERTURA ───────────────────────────────────────────────────────────────

def cobertura(rows: list[SilverRow]) -> tuple[dict[str, int], list[tuple[str, str, Decimal]]]:
    """Histograma por source + top-N pendentes por |valor|."""
    counts: dict[str, int] = defaultdict(int)
    valor_por_source: dict[str, Decimal] = defaultdict(lambda: Decimal(0))
    pendentes: list[tuple[str, str, Decimal]] = []  # (silver, codigo/nome, valor)
    for r in rows:
        cls = classify(r.silver_origin, r.raw)
        counts[cls.source] += 1
        valor_por_source[cls.source] += abs(r.valor)
        if cls.source == "pendente":
            ident = r.codigo or r.nome
            pendentes.append((r.silver_origin, ident, r.valor))
    pendentes.sort(key=lambda x: abs(x[2]), reverse=True)
    return dict(counts), pendentes[:10]


# ─── CSV WRITERS ─────────────────────────────────────────────────────────────

def write_balancete_csv(
    path: Path,
    saldos_d1: dict[str, Decimal],
    saldos_d0: dict[str, Decimal],
) -> None:
    contas = sorted(set(saldos_d1) | set(saldos_d0))
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["cosif", "nivel", "natureza", "nome", "d_minus_1", "d_zero", "delta", "delta_pct"])
        for cosif in contas:
            info = COSIF_CATALOG.get(cosif, ("?", "?", None))
            nome, natureza, _ = info
            nivel = cosif.count(".") + 1 if cosif != "PENDENTE" else 0
            d1 = saldos_d1.get(cosif, Decimal(0))
            d0 = saldos_d0.get(cosif, Decimal(0))
            delta = d0 - d1
            delta_pct = (delta / abs(d1) * 100) if d1 else Decimal(0)
            w.writerow([
                cosif, nivel, natureza, nome,
                f"{d1:.2f}", f"{d0:.2f}", f"{delta:.2f}", f"{delta_pct:.4f}",
            ])


def write_reconciliacao_csv(
    path: Path,
    pl_total_d1: Decimal,
    pl_total_d0: Decimal,
    sr_d1: Decimal,
    sr_d0: Decimal,
    mez_d1: Decimal,
    mez_d0: Decimal,
) -> Decimal:
    pl_sub_d1 = pl_total_d1 - sr_d1 - mez_d1
    pl_sub_d0 = pl_total_d0 - sr_d0 - mez_d0
    delta_pl_total = pl_total_d0 - pl_total_d1
    delta_sr = sr_d0 - sr_d1
    delta_mez = mez_d0 - mez_d1
    delta_pl_sub_calc = delta_pl_total - delta_sr - delta_mez
    delta_pl_sub_real = pl_sub_d0 - pl_sub_d1
    residuo = delta_pl_sub_real - delta_pl_sub_calc
    pct_d1 = (delta_pl_sub_real / abs(pl_sub_d1) * 100) if pl_sub_d1 else Decimal(0)

    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["componente", "d_minus_1", "d_zero", "delta"])
        w.writerow(["PL Total (soma silver)",
                    f"{pl_total_d1:.2f}", f"{pl_total_d0:.2f}", f"{delta_pl_total:.2f}"])
        w.writerow(["(-) Cotas Sr emitidas (modulo)",
                    f"{sr_d1:.2f}", f"{sr_d0:.2f}", f"{delta_sr:.2f}"])
        w.writerow(["(-) Cotas Mez emitidas (modulo)",
                    f"{mez_d1:.2f}", f"{mez_d0:.2f}", f"{delta_mez:.2f}"])
        w.writerow(["= PL Cota Sub",
                    f"{pl_sub_d1:.2f}", f"{pl_sub_d0:.2f}", f"{delta_pl_sub_real:.2f}"])
        w.writerow([])
        w.writerow(["Δ PL Cota Sub (calc = ΔTotal-ΔSr-ΔMez)", "", "", f"{delta_pl_sub_calc:.2f}"])
        w.writerow(["Δ PL Cota Sub (real)",                   "", "", f"{delta_pl_sub_real:.2f}"])
        w.writerow(["Resíduo",                                 "", "", f"{residuo:.2f}"])
        w.writerow(["% sobre PL Sub D-1",                      "", "", f"{pct_d1:.6f}%"])
    return residuo


def write_cobertura_csv(
    path: Path,
    counts_d1: dict[str, int], pendentes_d1,
    counts_d0: dict[str, int], pendentes_d0,
) -> None:
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(["periodo", "source", "rows"])
        for source in ("override", "rule", "pendente"):
            w.writerow(["D-1", source, counts_d1.get(source, 0)])
            w.writerow(["D0", source, counts_d0.get(source, 0)])
        w.writerow([])
        w.writerow(["periodo", "silver_origin", "identificador", "valor"])
        for silv, ident, val in pendentes_d1:
            w.writerow(["D-1", silv, ident, f"{val:.2f}"])
        for silv, ident, val in pendentes_d0:
            w.writerow(["D0", silv, ident, f"{val:.2f}"])


# ─── MAIN ────────────────────────────────────────────────────────────────────

async def _resolve_ua_id(db, nome: str) -> UUID:
    row = await db.execute(
        text("SELECT id FROM cadastros_unidade_administrativa WHERE nome = :n"),
        {"n": nome},
    )
    val = row.scalar_one_or_none()
    if val is None:
        raise SystemExit(f"UA '{nome}' nao encontrada em cadastros_unidade_administrativa")
    return UUID(str(val))


async def main(ua_nome: str, d1: date, d0: date, out_dir: Path) -> int:
    out_dir.mkdir(parents=True, exist_ok=True)
    async with AsyncSessionLocal() as db:
        ua_id = await _resolve_ua_id(db, ua_nome)
        print(f"UA: {ua_nome}  id={ua_id}")
        print(f"D-1: {d1}  D0: {d0}")

        rows_d1 = await fetch_silver(db, ua_id, d1)
        rows_d0 = await fetch_silver(db, ua_id, d0)
        print(f"silver rows D-1: {len(rows_d1)}, D0: {len(rows_d0)}")

        # 1. Agrega por cosif analítico, depois propaga para ancestrais
        analiticos_d1 = aggregate_by_cosif(rows_d1)
        analiticos_d0 = aggregate_by_cosif(rows_d0)
        saldos_d1 = propagate_to_parents(analiticos_d1)
        saldos_d0 = propagate_to_parents(analiticos_d0)

        # 2. PL Total = soma de TUDO no silver (pares de compensação se anulam)
        pl_total_d1 = sum(r.valor for r in rows_d1)
        pl_total_d0 = sum(r.valor for r in rows_d0)

        # 3. Cotas Sr e Mez emitidas (módulo)
        sr_d1 = sum_cotas_emitidas(rows_d1, "senior")
        sr_d0 = sum_cotas_emitidas(rows_d0, "senior")
        mez_d1 = sum_cotas_emitidas(rows_d1, "mezanino")
        mez_d0 = sum_cotas_emitidas(rows_d0, "mezanino")

        # 4. Cobertura
        counts_d1, pendentes_d1 = cobertura(rows_d1)
        counts_d0, pendentes_d0 = cobertura(rows_d0)

        # 5. Escreve CSVs
        bal_path = out_dir / "spike_balancete_diario.csv"
        rec_path = out_dir / "spike_reconciliacao.csv"
        cob_path = out_dir / "spike_cobertura.csv"
        write_balancete_csv(bal_path, saldos_d1, saldos_d0)
        residuo = write_reconciliacao_csv(
            rec_path,
            pl_total_d1, pl_total_d0,
            sr_d1, sr_d0,
            mez_d1, mez_d0,
        )
        write_cobertura_csv(cob_path, counts_d1, pendentes_d1, counts_d0, pendentes_d0)

        # 6. Resumo no terminal
        pl_sub_d1 = pl_total_d1 - sr_d1 - mez_d1
        pl_sub_d0 = pl_total_d0 - sr_d0 - mez_d0
        delta_pl_sub = pl_sub_d0 - pl_sub_d1
        pct = (delta_pl_sub / abs(pl_sub_d1) * 100) if pl_sub_d1 else Decimal(0)
        print()
        print("=" * 70)
        print("RESUMO COTA SUB")
        print("=" * 70)
        print(f"PL Total       D-1: {pl_total_d1:>18,.2f}   D0: {pl_total_d0:>18,.2f}")
        print(f"Cotas Sr (mod) D-1: {sr_d1:>18,.2f}   D0: {sr_d0:>18,.2f}")
        print(f"Cotas Mez(mod) D-1: {mez_d1:>18,.2f}   D0: {mez_d0:>18,.2f}")
        print(f"PL Cota Sub    D-1: {pl_sub_d1:>18,.2f}   D0: {pl_sub_d0:>18,.2f}")
        print(f"Delta PL Cota Sub:  {delta_pl_sub:>18,.2f}   ({pct:.6f}% sobre D-1)")
        print(f"Residuo da equacao: {residuo:>18,.2f}")
        print()
        print("COBERTURA COSIF")
        for k in ("override", "rule", "pendente"):
            print(f"  {k:10s}: D-1={counts_d1.get(k,0):4d}  D0={counts_d0.get(k,0):4d}")
        if pendentes_d0:
            print()
            print("TOP 10 PENDENTES D0 (por |valor|)")
            for silv, ident, val in pendentes_d0:
                print(f"  {silv:30s} {ident or '(sem id)':30s} {val:>15,.2f}")
        print()
        print(f"CSVs escritos em {out_dir}")
        for p in (bal_path, rec_path, cob_path):
            print(f"  {p}")
        return 0


def _parse_date(s: str) -> date:
    y, m, d = s.split("-")
    return date(int(y), int(m), int(d))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ua", default="REALINVEST FIDC", help="Nome da UA")
    ap.add_argument("--d-1", dest="d1", default="2026-05-07", help="Data D-1 (YYYY-MM-DD)")
    ap.add_argument("--d0", default="2026-05-08", help="Data D0 (YYYY-MM-DD)")
    ap.add_argument("--out", default=None, help="Diretorio de saida (default: scripts/out/)")
    args = ap.parse_args()
    out = Path(args.out) if args.out else Path(__file__).parent / "out"
    sys.exit(asyncio.run(main(args.ua, _parse_date(args.d1), _parse_date(args.d0), out)))
