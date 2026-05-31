"""Controladoria · Classificador de NATUREZA do CPR (wh_cpr_movimento).

Primitivo PURO (sem DB). Substitui o split-por-sinal (CPR>0=ativo / CPR<0=passivo)
por uma classificacao por NATUREZA, ancorada na descricao nativa do lancamento —
mesmo metodo do RF (nome_do_papel) e do extrato (codigo historico).

Por que: o sinal NAO e fiel ao balanco. O CPR<0 mistura *despesa a pagar*
(taxas, consultoria, auditoria) com *capital de cotista* (Cotas a Resgatar,
Aporte, Resgate) — naturezas de grupos diferentes (Passivo Operacional vs
Patrimonio). O CPR>0 mistura *floating a receber* (ponte de liquidacao), *despesa
diferida* (despesa antecipada, ativo que amortiza -PL) e *ajustes a recuperar*.
Classificar por sinal joga tudo num balde so e o auditor de despesa pegaria a
Cota a Resgatar (-R$3M) como se fosse provisao.

REGRA DE OURO: a NATUREZA decide o grupo e o auditor dono — nunca o sinal.

Guard: lancamento que nao casa nenhuma regra cai em `nao_classificado` e e
SINALIZADO (nunca silenciado num sinal por default). Quando a QiTech traz um
lancamento novo, ele aparece em vez de corromper o residuo (mesmo espirito do
detector de nao-reconhecidos que pegou a VCNC).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

# ── Vocabulario canonico das naturezas ──────────────────────────────────────
Natureza = Literal[
    "floating_a_receber",   # ponte: liquidacao paga, caixa em transito (d+1). Ativo.
    "despesa_diferida",     # despesa antecipada (CVM/Rating/ANBIMA), amortiza -PL. Ativo.
    "valor_a_receber",      # a recuperar: devolucao duplicidade, transf a menor, taxa a receber. Ativo.
    "capital_cotista",      # Cotas a Resgatar / Aporte / Resgate de cotas. Passivo (Patrimonio).
    "imposto_a_recolher",   # IOF / IR a recolher. Passivo (tributos).
    "despesa_a_pagar",      # provisoes de despesa (taxas, consultoria, auditoria...). Passivo.
    "ajuste_estorno",       # estorno / transf saldo residual / transf a maior. Reconciliacao.
    "nao_classificado",     # guard: nao casou nenhuma regra. Sinalizar.
]

# Lado do balanco + grupo de apresentacao + auditor dono, por natureza.
Lado = Literal["ativo", "passivo", "ajuste"]

NATUREZA_INFO: dict[Natureza, tuple[Lado, str, str]] = {
    "floating_a_receber": ("ativo", "Disponibilidades · Valores a Receber", "caixa"),
    "despesa_diferida":   ("ativo", "Despesas Antecipadas",                  "despesa"),
    "valor_a_receber":    ("ativo", "Valores a Receber",                     "a_receber"),
    "capital_cotista":    ("passivo", "Patrimonio · Cotas",                  "cotas"),
    "imposto_a_recolher": ("passivo", "Tributos a Recolher",                 "contas_a_pagar"),
    "despesa_a_pagar":    ("passivo", "Contas a Pagar",                      "contas_a_pagar"),
    "ajuste_estorno":     ("ajuste", "Reconciliacao",                        "reconciliacao"),
    "nao_classificado":   ("ajuste", "Nao Classificado",                     "reconciliacao"),
}

# ── Normalizacao ────────────────────────────────────────────────────────────
# Tira a data do TEXTO (vem errada — usar so colunas de data) + acento + caixa.
_DATE_RE = re.compile(r"\s*\d{1,2}[./]\d{1,2}([./]\d{2,4})?")


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def _norm(descricao: str | None) -> str:
    s = _DATE_RE.sub(" ", descricao or "")
    s = _strip_accents(s).lower()
    return re.sub(r"\s+", " ", s).strip()


# ── Regras, em ORDEM DE PRIORIDADE (especifico antes do generico) ───────────
# Cada regra: (natureza, predicado sobre o texto normalizado `t`).
# A 1a que retorna True ganha. Predicados explicitos pra resolver ambiguidade
# (ex.: "taxa de administracao A RECEBER" e a_receber, nao despesa).
_REGRAS: list[tuple[Natureza, object]] = [
    # 1. Floating — a ponte de liquidacao (o maior item do CPR>0).
    ("floating_a_receber", lambda t: t.startswith("liquid") and "prov" in t),

    # 2. Despesa diferida — despesa antecipada que amortiza.
    ("despesa_diferida", lambda t: "diferimento de despesa" in t or " a diferir" in t),

    # 3. Capital de cotista — obrigacoes/movimento de patrimonio com o cotista.
    #    Vem ANTES de despesa: "Cotas a Resgatar" nao e despesa.
    ("capital_cotista", lambda t: "irrf" not in t and (
        "cotas a resgatar" in t
        or "resgate de cota" in t          # "Resgate de Cotas - PJ"
        or "compensacao de cotas" in t
        or t == "aporte"                    # "Aporte" puro (capital)
        or t.startswith("dev. aporte") or t.startswith("dev aporte")
        or "devolucao de aporte" in t or t == "dev. aporte"
    )),

    # 4. Valor a receber / a recuperar — vem ANTES de despesa pra capturar o
    #    "a receber" que senao cairia em despesa (ex.: Taxa de Adm a Receber).
    ("valor_a_receber", lambda t: (
        " a receber" in t
        or "duplicidade" in t
        or "transferencia a menor" in t
        or "cred juros" in t
        or "resultado de selic" in t
        or "resgate de titulo" in t         # resgate de RF (nao cotista)
        or "irrf sobre resgate" in t        # IRRF retido no resgate: credito (ativo, +)
        or "aquisicao de ativos" in t       # TED p/ comprar ativos: ponte (ativo em transito)
        or "remessa nao carregada" in t     # TED paga, remessa pendente: a recuperar
    )),

    # 5. Imposto a recolher — tributos (CVM e despesa, nao imposto: fica fora).
    ("imposto_a_recolher", lambda t: (
        "iof a recolher" in t or "ir a recolher" in t
    )),

    # 6. Ajuste / estorno — reconciliacao pura (vem antes de despesa pra nao
    #    confundir "transf liqu e baix" com despesa).
    ("ajuste_estorno", lambda t: (
        "estorno" in t
        or "transf liqu e baix" in t
        or "transferencia saldo residual" in t
        or "transferencia a maior" in t
    )),

    # 7. Despesa a pagar — provisoes operacionais (o grosso do CPR<0).
    ("despesa_a_pagar", lambda t: (
        t.startswith("despesa")
        or t.startswith("taxa de") or t.startswith("tx ")
        or "banco liquidante" in t
        or "registradora" in t or "crdc" in t or "certificadora" in t
        or "consultoria" in t or "cobranca" in t or "auditoria" in t
        or "custodia" in t or "gestao" in t or "administracao" in t
        or "anbid" in t or "anbima" in t
        or "fiscalizacao cvm" in t or "fiscalizacao da cvm" in t
        or "distribuicao" in t or "plataforma" in t
        or "selic" in t or "custo" in t or "juros ntn" in t
        or "despesas bancarias" in t or "baixa parcial" in t
    )),
]


def classify_cpr_nature(descricao: str | None) -> Natureza:
    """Classifica um lancamento de wh_cpr_movimento pela NATUREZA.

    Ancorado na descricao normalizada (sem data/acento/caixa). A 1a regra que
    casa ganha (ordem de prioridade resolve ambiguidade). Sem match -> guard
    `nao_classificado` (sinalizar, nunca silenciar).
    """
    t = _norm(descricao)
    if not t:
        return "nao_classificado"
    for natureza, pred in _REGRAS:
        if pred(t):  # type: ignore[operator]
            return natureza
    return "nao_classificado"


def lado_balanco(natureza: Natureza) -> Lado:
    """ativo | passivo | ajuste — pro grupo do balanco."""
    return NATUREZA_INFO[natureza][0]
