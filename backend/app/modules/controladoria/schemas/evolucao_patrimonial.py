"""Pydantic schemas -- Controladoria · Evolucao Patrimonial.

Serie temporal da evolucao do PL do passivo do FIDC (todas as classes de
cota), espelhando o contrato TypeScript em
`frontend/src/app/(app)/controladoria/evolucao-patrimonial/page.tsx`.

Fonte (silver, CLAUDE.md §13.2.1):
    - wh_mec_evolucao_cotas    -- PL, quantidade, valor da cota, fluxo
                                   (aporte/retirada/entradas/saidas) e
                                   variacoes % por classe num dia.
    - wh_rentabilidade_fundo   -- % do CDI (percentual_bench_mark),
                                   rentabilidade real e o retorno do proprio
                                   CDI (indexador='CDI').

Decisao de tipo: este endpoint alimenta charts/KPIs (display), nao uma
reconciliacao contabil. Usa `float` (precisao de display suficiente,
zero coerce string->number no frontend) ao inves de `Decimal` -- divergindo
conscientemente do cota_sub (que reconcilia residuo exato).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field

# Classe de cota canonica. "sub" = subordinada junior (residual, absorve
# resultado), "mez" = mezanino, "sr" = senior. Classificacao por heuristica
# sobre `carteira_cliente_nome` (mesma convencao do cota_sub).
ClasseCota = Literal["sub", "mez", "sr"]

Granularidade = Literal["diaria", "mensal"]


class SeriePontoClasse(BaseModel):
    """Metricas de uma classe de cota num ponto da serie."""

    classe: ClasseCota
    patrimonio: float = Field(description="PL da classe no ponto (R$)")
    quantidade: float = Field(description="Quantidade de cotas")
    valor_cota: float = Field(description="Valor da cota (R$)")
    variacao_diaria_pct: float = Field(description="Variacao % no dia (MEC)")
    variacao_mensal_pct: float = Field(description="Variacao % no mes (MEC, MTD)")
    # Fluxo de capital da classe. Para os fundos observados (REALINVEST) os
    # campos MEC `aporte`/`retirada` vem sempre zerados e o capital de cotista
    # circula em `entradas`/`saidas` -- usamos estes como captacao bruta.
    entradas: float = Field(description="Aportes/captacao bruta da classe (R$)")
    saidas: float = Field(description="Resgates/saida bruta da classe (R$)")
    captacao_liquida: float = Field(description="entradas - saidas (R$)")
    pct_cdi: float | None = Field(
        default=None,
        description="% do CDI no ponto (rentabilidade_fundo, indexador CDI)",
    )
    rentab_real_cdi_pct: float | None = Field(
        default=None,
        description="Rentabilidade real acima do CDI no ponto (%)",
    )


class SeriePonto(BaseModel):
    """Um ponto da serie temporal (1 dia, ou 1 mes se granularidade=mensal)."""

    data: date
    pl_total: float = Field(
        description="Soma do PL das classes filtradas presentes no ponto (R$)"
    )
    cdi_retorno_pct: float | None = Field(
        default=None,
        description=(
            "Retorno do proprio CDI no intervalo do ponto (%). Diaria: "
            "rentabilidade_diaria do indexador CDI. Mensal: composto dos "
            "retornos diarios do mes."
        ),
    )
    classes: list[SeriePontoClasse]


class ClasseInfo(BaseModel):
    """Classe disponivel para o fundo no periodo (alimenta o multiselect)."""

    classe: ClasseCota
    label: str = Field(description="Rotulo pt-BR (Subordinada/Mezanino/Senior)")
    carteira_cliente_nome: str
    primeiro_dia: date
    ultimo_dia: date


class ResumoClasse(BaseModel):
    """Resumo da classe no periodo filtrado -- alimenta cards/KPIs por classe."""

    classe: ClasseCota
    label: str
    pl_inicio: float
    pl_atual: float
    valor_cota_inicio: float
    valor_cota_atual: float
    rentab_periodo_pct: float | None = Field(
        default=None,
        description="valor_cota_atual / valor_cota_inicio - 1 (em %)",
    )
    captacao_liquida_periodo: float
    pct_cdi_ultimo: float | None = Field(
        default=None, description="Ultimo % do CDI observado no periodo"
    )
    participacao_pct: float | None = Field(
        default=None, description="pl_atual / pl_total_atual (todas as classes)"
    )


class KpiResumo(BaseModel):
    """KPIs do fundo (todas as classes filtradas) no periodo."""

    pl_total_inicio: float
    pl_total_atual: float
    pl_total_delta_pct: float | None = None
    captacao_liquida_periodo: float
    subordinacao_pct: float | None = Field(
        default=None,
        description=(
            "PL Sub / PL total (todas as classes do fundo, independente do "
            "filtro de classe) no ultimo ponto -- metrica estrutural/covenant."
        ),
    )
    rentab_sub_periodo_pct: float | None = Field(
        default=None, description="Rentabilidade da classe Sub no periodo (%)"
    )
    pct_cdi_sub_ultimo: float | None = Field(
        default=None, description="Ultimo % do CDI da classe Sub"
    )


class Proveniencia(BaseModel):
    fonte: str = Field(default="admin:qitech", description="source_type da origem")
    relatorio: str = Field(default="mec + rentabilidade")
    atualizado_em: datetime | None = Field(
        default=None, description="Maior source_updated_at observado na serie"
    )
    gaps_ignorados: int = Field(
        default=0,
        description=(
            "Linhas MEC all-zero (patrimonio=qtd=cota=0) tratadas como buraco "
            "de publicacao QiTech e excluidas da serie. > 0 sinaliza dias com "
            "snapshot incompleto no periodo."
        ),
    )


class EvolucaoPatrimonialResponse(BaseModel):
    """Bundle completo da pagina Evolucao Patrimonial."""

    fundo_id: str
    fundo_nome: str
    periodo_inicio: date
    periodo_fim: date
    granularidade: Granularidade
    classes_disponiveis: list[ClasseInfo]
    serie: list[SeriePonto]
    resumo_por_classe: list[ResumoClasse]
    kpis: KpiResumo
    proveniencia: Proveniencia
