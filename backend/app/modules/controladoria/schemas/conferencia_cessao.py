"""Pydantic schemas — Controladoria · Conferencia de cessao (aquisicao vs caixa).

Reconcilia, por dia e por cedente, o que o fundo registrou como AQUISICAO de
recebiveis (Σ valor_compra em wh_aquisicao_recebivel) contra o que SAIU do
caixa pro cedente (debitos em wh_extrato_bancario, contrapartida = cedente_doc).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# casa       = debito(s) ao cedente batem a Σ valor_compra do dia
# descasa    = ha extrato no periodo, mas o cedente nao bate (valor diverge ou
#              sem debito) -> candidato a erro de lancamento DC<->caixa
# sem_extrato = o extrato nao foi sincronizado pro periodo (nao da pra conferir)
ConferenciaStatus = Literal["casa", "descasa", "sem_extrato"]


class ConferenciaCessaoLancamento(BaseModel):
    """1 debito do extrato bancario casado (ou candidato) ao cedente."""

    data_lancamento: date
    valor:           Decimal


class ConferenciaCessaoCedente(BaseModel):
    """Conferencia da cessao de UM cedente num dia: aquisicao vs caixa."""

    cedente_doc:        str
    cedente_nome:       str
    n_titulos:          int = Field(description="Qtd de recebiveis adquiridos do cedente no dia")
    valor_aquisicao:    Decimal = Field(description="Σ valor_compra (o que o fundo registrou pagar)")
    valor_debito_caixa: Decimal = Field(description="Σ debitos ao cedente no extrato (janela)")
    diferenca:          Decimal = Field(description="valor_aquisicao - valor_debito_caixa")
    status:             ConferenciaStatus
    match_exato:        bool = Field(
        description="True quando um debito UNICO == valor_aquisicao (TED de cessao limpa)"
    )
    lancamentos:        list[ConferenciaCessaoLancamento] = Field(
        default_factory=list, description="Debitos ao cedente na janela (proveniencia)"
    )


class ConferenciaCessaoResponse(BaseModel):
    """Conferencia de cessao de um dia: aquisicoes (DC) x debitos de caixa.

    Achado empirico (REALINVEST, 2026-05-30): a cessao liquida como TED ao
    cedente no valor EXATO da compra, no mesmo dia (codigo bancario 0307).
    Acende 3 sinais:
      - erro de lancamento (descasa): TED != Σ valor_compra
      - furo de sync do extrato (sem_extrato): aquisicao existe, extrato sem debito
      - fluxo extra ao cedente (recompra/coobrigacao): debito > compra
    """

    fundo_id:                  str
    fundo_nome:                str
    data:                      date
    janela_dias:               int = Field(description="Dias corridos apos D vasculhados no extrato")

    extrato_disponivel:        bool = Field(
        description="False quando NENHUM cedente do dia tem debito no extrato "
                    "(provavel furo de sincronizacao — nao da pra conferir)."
    )
    extrato_ultimo_lancamento: date | None = Field(
        default=None, description="Data do lancamento mais recente do extrato (frescor)"
    )

    total_aquisicoes:          Decimal = Field(description="Σ valor_compra do dia (todos cedentes)")
    total_debito_caixa:        Decimal = Field(description="Σ debitos casados/candidatos no extrato")

    n_cedentes:                int
    n_casa:                    int
    n_descasa:                 int
    n_sem_extrato:             int

    cedentes:                  list[ConferenciaCessaoCedente] = Field(default_factory=list)
