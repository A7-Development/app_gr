"""Response schema do endpoint que invoca o agente de variacao da Cota Sub.

Envelopa o output do agente (AnalysisVariacaoCotaResponse) com metadata
da execucao (from_cache, custo, duracao, modelo) — UI usa pra mostrar
indicadores honestos ("Analise carregada do cache 5min atras, custo R$ 0").
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.agentic.engine.output_schemas import AnalysisVariacaoCotaResponse


class AgenteVariacaoRunMetadata(BaseModel):
    """Metadata da execucao — separado do conteudo da analise."""

    model_config = ConfigDict(extra="forbid")

    analysis_run_id: UUID = Field(
        description="ID da row em agent_analysis_run pra audit/re-fetch.",
    )
    audit_version: str = Field(
        description="Composto agent+persona+expertises+prompt (ex.: "
                    "'controladoria.analista_variacao_cota@v1+...').",
    )
    model_used: str = Field(description="Modelo LLM que rodou (ex.: 'claude-sonnet-4-6').")
    from_cache: bool = Field(
        description="True = resposta veio de execucao previa (custo R$ 0). "
                    "False = LLM foi invocado agora.",
    )
    cache_age_seconds: int = Field(
        description="Idade do cache em segundos quando from_cache=True. 0 quando miss.",
    )
    tokens_input: int
    tokens_output: int
    tokens_cache_read: int
    tokens_cache_creation: int
    cost_brl_estimated: Decimal = Field(
        description="Custo estimado em BRL desta execucao (0 quando from_cache=True).",
    )
    duration_ms: int = Field(
        description="Duracao da invocacao do LLM em ms (0 quando from_cache=True).",
    )


class AgenteVariacaoRunResponse(BaseModel):
    """Response do POST /cota-sub/agente/analista-variacao/run."""

    model_config = ConfigDict(extra="forbid")

    metadata: AgenteVariacaoRunMetadata
    analise: AnalysisVariacaoCotaResponse
