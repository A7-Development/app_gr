"""Schemas da L2 Benchmark (CVM FIDC - dados publicos via postgres_fdw).

Fonte: `cvm_remote.*` (foreign tables apontando pra DB `cvm_benchmark` na mesma
instancia Postgres da VM 27). Detalhes em `docs/integracao-cvm-fidc.md`.

L3 tabs: Visao geral | PDD | Evolucao | Fundos

Diferente da L2 Operacoes, o dado e **publico** (sem `tenant_id`). A autorizacao
permanece a mesma (require_module BI.READ) - esconde o modulo pra quem nao tem
licenca/permissao, mas os numeros sao de mercado.
"""

from datetime import date

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


# ---------------------------------------------------------------------------
# Mercado — Top administradoras + distribuicao condominio (Aberto/Fechado)
# ---------------------------------------------------------------------------


class AdminLinha(BaseModel):
    """Linha de ranking de administradora (top N)."""

    cnpj_admin: str | None
    admin: str
    quantidade_fundos: int
    pl_total: float


class BenchmarkAdmins(BaseModel):
    """Top 10 administradoras por quantidade de fundos e por PL sob administracao.

    `competencia` e a ultima do range selecionado — ranking sempre snapshot.
    """

    competencia: str  # 'YYYY-MM'
    top_por_quantidade: list[AdminLinha]
    top_por_pl: list[AdminLinha]
    total_admins: int  # total distinto de administradoras na competencia


class CondomPonto(BaseModel):
    """Ponto mensal da serie Aberto vs Fechado."""

    periodo: date
    aberto_qtd: int
    fechado_qtd: int
    aberto_pct: float  # 0..100, relativo a (aberto+fechado) daquela competencia
    fechado_pct: float


class BenchmarkCondom(BaseModel):
    """Distribuicao Aberto/Fechado — snapshot + serie mensal no range.

    `aberto_qtd`/`fechado_qtd` e `aberto_pct`/`fechado_pct` sao sempre da
    `competencia` (ultima do range). `evolucao` e mensal dentro do range.

    Fundos com `condom` fora de `('ABERTO','FECHADO')` sao ignorados (CVM
    ocasionalmente publica `'NA'` / `'0'` para fundos em liquidacao).
    """

    competencia: str  # 'YYYY-MM' — snapshot
    aberto_qtd: int
    fechado_qtd: int
    aberto_pct: float
    fechado_pct: float
    evolucao: list[CondomPonto]
