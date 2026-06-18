"""Controladoria · Classificador de NATUREZA do evento de liquidacao.

Primitivo PURO (sem DB). Espelha `cpr_natureza.py`. Decide se um evento de
`wh_liquidacao_recebivel` que casa com a queda de saldo de um papel que FICOU
na carteira (liquidacao parcial) e:

  - `cash_settlement` (GIRO): houve entrada de caixa (recompra parcial,
    liquidacao parcial, baixa por deposito). A queda de VP da carteira e
    compensada pela perna de caixa na Tesouraria -> NEUTRO no PL Sub.
  - `credit_loss` (PERDA): NAO houve entrada de caixa — valor foi perdoado
    (ABATIMENTO CONCEDIDO). A queda de VP da carteira NAO tem contrapartida
    de caixa -> bate no PL Sub como perda de credito (value-mover do DC).

REGRA DE OURO: a NATUREZA do `tipo_movimento` decide o balde — nunca o sinal
do `valor_pago` (no abatimento o `valor_pago` carrega o valor ABATIDO, nao
caixa recebido; tratar como giro vazaria a perda pro plug de Disponibilidades).

Por que existe (bug 17/06/2026): 3 abatimentos no cedente TING (DID110568/9/70,
-R$ 14.334 de VP) eram classificados como `liquidacao_parcial` (giro). A perda
sumia do DC e reaparecia disfarcada de "rendimento liquido de caixa" no plug de
Disponibilidades — sem gerar atencao e induzindo a IA a explicar como "desvio de
provisao". Aqui a perda volta pro grupo certo (DC), com o cedente nomeado.

Guard: `tipo_movimento` desconhecido -> `cash_settlement` (preserva o
comportamento anterior; so o que e explicitamente perda muda de balde).
"""

from __future__ import annotations

import unicodedata
from typing import Literal

LiquidacaoNature = Literal["credit_loss", "cash_settlement"]


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn"
    )


def _norm(tipo: str | None) -> str:
    return _strip_accents(tipo or "").upper().strip()


# Palavras-chave de PERDA (sem entrada de caixa). Ordem nao importa — qualquer
# match marca credit_loss. Conservador: so o que e inequivocamente perdao/perda.
# Extensivel quando a QiTech trouxer novos tipos (ex.: "PERDA NEGOCIADA").
_CREDIT_LOSS_KEYWORDS: tuple[str, ...] = (
    "ABATIMENTO",   # ABATIMENTO CONCEDIDO — valor perdoado ao sacado, sem caixa.
)


def classify_liquidacao_nature(tipo_movimento: str | None) -> LiquidacaoNature:
    """Classifica o evento de liquidacao parcial casado: perda vs giro.

    `credit_loss` quando o `tipo_movimento` indica perdao/perda sem caixa
    (abatimento). `cash_settlement` caso contrario (giro carteira->caixa).
    Desconhecido cai em `cash_settlement` (guard que preserva o legado).
    """
    t = _norm(tipo_movimento)
    if not t:
        return "cash_settlement"
    if any(kw in t for kw in _CREDIT_LOSS_KEYWORDS):
        return "credit_loss"
    return "cash_settlement"


def is_credit_loss(tipo_movimento: str | None) -> bool:
    """Conveniencia: o evento e perda de credito (abatimento)?"""
    return classify_liquidacao_nature(tipo_movimento) == "credit_loss"
