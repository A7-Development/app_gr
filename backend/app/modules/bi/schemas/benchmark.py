"""Schemas da L2 Benchmark (CVM FIDC - dados publicos via postgres_fdw).

Fonte: `cvm_remote.*` (foreign tables apontando pra DB `cvm_benchmark` na mesma
instancia Postgres da VM 27). Detalhes em `docs/integracao-cvm-fidc.md`.

L3 tabs: Visao geral | PDD | Evolucao | Fundos

Diferente da L2 Operacoes, o dado e **publico** (sem `tenant_id`). A autorizacao
permanece a mesma (require_module BI.READ) - esconde o modulo pra quem nao tem
licenca/permissao, mas os numeros sao de mercado.
"""

from pydantic import BaseModel

from app.modules.bi.schemas.common import KPI, CategoryValue, Point


class BenchmarkResumo(BaseModel):
    """KPIs agregados do mercado FIDC na competencia selecionada (ou ultima)."""

    competencia: str | None  # 'YYYY-MM' - exibido como chip no header, nao como KPI
    total_fundos: KPI
    pl_total: KPI
    pdd_mediana: KPI
    inadimplencia_mediana: KPI
    cobertura_mediana: KPI


class PDDDistribuicao(BaseModel):
    """L3 PDD - histograma em buckets + top fundos por %PDD."""

    histograma: list[CategoryValue]  # bucket -> quantidade
    top_fundos: list[CategoryValue]  # denominacao -> %PDD


class BenchmarkEvolucao(BaseModel):
    """L3 Evolucao - series temporais agregadas do mercado."""

    pl_mediano: list[Point]  # PL mediano por competencia
    pl_total: list[Point]  # PL total por competencia
    num_fundos: list[Point]  # quantidade de fundos reportando


class FundoRow(BaseModel):
    """Linha da tabela de fundos."""

    cnpj_fundo: str
    denominacao_social: str | None
    classe_anbima: str | None
    situacao: str | None
    patrimonio_liquido: float
    numero_cotistas: int | None
    valor_total_dc: float | None
    percentual_pdd: float | None
    indice_inadimplencia: float | None


class FundosLista(BaseModel):
    """L3 Fundos - lista de fundos na competencia selecionada."""

    competencia: str  # 'YYYY-MM'
    fundos: list[FundoRow]
    total: int  # total de fundos na competencia (pode ser > len(fundos) se paginado)
