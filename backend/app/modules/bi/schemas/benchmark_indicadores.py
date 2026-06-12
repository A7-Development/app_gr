"""Pydantic schemas — BI Benchmark: indicadores de benchmarking (cesta de 17).

Resposta do Comparador (/bi/benchmark/indicadores): ate 3 fundos lado a lado
+ medianas do universo na competencia. Cada indicador vem com o valor e o
`*_rank` (percentil 0-100 no universo; direcao "maior=melhor" e metadado de
front via INDICADOR_DIRECAO do service).
"""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class IndicadoresFundo(BaseModel):
    """Cesta de indicadores de UM fundo numa competencia (+ percentis)."""

    cnpj: str
    denom_social: str | None = None
    condominio: str | None = Field(
        default=None, description="Aberto | Fechado (cadastral, tab_i.condom)."
    )

    pl: float | None = None
    pl_rank: float | None = None
    pl_medio: float | None = None
    subordinacao_pct: float | None = None
    subordinacao_pct_rank: float | None = None
    subordinacao_jr_pct: float | None = None
    subordinacao_jr_pct_rank: float | None = None
    sub_jr_sobre_sub_pct: float | None = None
    sub_jr_sobre_sub_pct_rank: float | None = None
    passivo_ativo_pct: float | None = None
    passivo_ativo_pct_rank: float | None = None
    dc_ativo_pct: float | None = None
    dc_ativo_pct_rank: float | None = None
    alta_liquidez_pl_pct: float | None = None
    alta_liquidez_pl_pct_rank: float | None = None
    prazo_medio_dias: float | None = None
    prazo_medio_dias_rank: float | None = None
    inad_total_pct: float | None = None
    inad_total_pct_rank: float | None = None
    inad_90_pct: float | None = None
    inad_90_pct_rank: float | None = None
    inad_180_pct: float | None = None
    inad_180_pct_rank: float | None = None
    cobertura_pdd_pct: float | None = None
    cobertura_pdd_pct_rank: float | None = None
    pdd_pl_pct: float | None = None
    pdd_pl_pct_rank: float | None = None
    recompra_dc_pct: float | None = None
    recompra_dc_pct_rank: float | None = None
    desagio_recompra: float | None = None
    captacao_liq_pl_pct: float | None = None
    captacao_liq_pl_pct_rank: float | None = None
    giro_pct: float | None = None
    giro_pct_rank: float | None = None
    rentab_sub_pct: float | None = None
    rentab_sub_pct_rank: float | None = None
    atingimento_pp: float | None = None
    atingimento_pp_rank: float | None = None
    scr_dh_pct: float | None = None
    scr_dh_pct_rank: float | None = None
    yield_efetivo_pct: float | None = None
    yield_efetivo_pct_rank: float | None = None
    divida_ativa_pct: float | None = None
    divida_ativa_pct_rank: float | None = None


class ComparadorIndicadoresResponse(BaseModel):
    """Resposta do Comparador: fundos pedidos + mediana do universo."""

    competencia: date
    total_fundos_universo: int = Field(
        description="Fundos com PL>0 no universo da competencia."
    )
    fundos: list[IndicadoresFundo]
    nao_encontrados: list[str] = Field(
        default_factory=list,
        description="CNPJs pedidos sem informe na competencia.",
    )
    mediana: dict[str, float | None] = Field(
        description="Mediana do universo por indicador (mesmas chaves dos campos)."
    )
    direcao: dict[str, bool] = Field(
        description="Por indicador: true = maior e melhor (orienta realce/radar)."
    )


class CompetenciasDisponiveisResponse(BaseModel):
    competencias: list[date]
