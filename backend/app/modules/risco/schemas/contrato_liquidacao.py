"""Pydantic schemas of the liquidation-contract screen (modulo risco)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.risco.models.contrato_liquidacao import (
    ExpectativaBaixaManual,
    ExpectativaBoleto,
    FluxoLiquidacao,
)


class PerfilObservado(BaseModel):
    """Observed liquidation behaviour of one product inside the window.

    Counts are exposed alongside the percentages so the frontend can always
    reconcile on-screen (CLAUDE.md 14.6) — pct fields are derived server-side
    from the same counts.
    """

    janela_dias: int
    qtd_titulos: int
    valor_total: float
    qtd_bancarizados: int
    # Liquidated titles that HAVE a registered boleto but whose current boleto
    # state is not "liquidado" — i.e. liquidated outside the bank rail.
    qtd_baixa_manual_bancarizados: int
    pct_bancarizado: float | None
    pct_baixa_manual_bancarizados: float | None


class ContratoLiquidacaoRow(BaseModel):
    """One product in the listing: declared contract + observed profile."""

    produto_sigla: str
    produto_nome: str
    # None em todos os campos declarados = contrato EM ABERTO (sem versao).
    version: int | None = None
    fluxo_esperado: FluxoLiquidacao | None = None
    boleto: ExpectativaBoleto | None = None
    baixa_manual: ExpectativaBaixaManual | None = None
    justificativa: str | None = None
    atualizado_em: datetime | None = None
    em_aberto: bool
    observado: PerfilObservado
    # Divergence slugs computed server-side (see services.contrato_liquidacao).
    divergencias: list[str] = Field(default_factory=list)


class ContratoLiquidacaoUpdate(BaseModel):
    """Defines (or redefines) the contract — always creates a NEW version."""

    model_config = ConfigDict(extra="forbid")

    fluxo_esperado: FluxoLiquidacao
    boleto: ExpectativaBoleto
    baixa_manual: ExpectativaBaixaManual
    justificativa: str | None = Field(default=None, max_length=512)


class ContratoLiquidacaoVersao(BaseModel):
    """One historical version of a product contract."""

    version: int
    fluxo_esperado: FluxoLiquidacao
    boleto: ExpectativaBoleto
    baixa_manual: ExpectativaBaixaManual
    justificativa: str | None
    created_at: datetime
    created_by: UUID | None
