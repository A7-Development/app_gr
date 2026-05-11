"""Controladoria · Estoque Carteira — Pydantic schemas do bundle.

Resposta de `GET /relatorios/padronizados/qitech-estoque-carteira/bundle`.
Consumido pela page `/controladoria/relatorios/padronizados/qitech-estoque-carteira`
no slot Z4 do `DashboardBiPadrao` (KpiStrip + grid de charts).

A pagina ainda usa o endpoint generico `GET /relatorios/{slug}` para a tabela
paginada de recebiveis (DataTable). Bundle so cobre os agregados, evitando
calcular KPIs em JS a partir de 500 rows truncadas (que mente quando o fundo
tem >500 titulos).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from app.modules.controladoria.schemas.reports import ProvenanceMetadata


class KpisCarteira(BaseModel):
    """KPIs agregados da carteira numa data de referencia."""

    valor_nominal_total: Decimal
    valor_presente_total: Decimal
    valor_aquisicao_total: Decimal
    valor_pdd_total: Decimal
    qtd_titulos: int
    # Share do valor_nominal cuja situacao_recebivel = 'Vencido' (em pontos %).
    pct_vencido: float
    # valor_pdd_total / valor_nominal_total * 100 (em pontos %).
    pdd_medio_pct: float
    # Concentracao top-N por sacado (share do valor_nominal).
    concentracao_top1_sacados_pct: float
    concentracao_top5_sacados_pct: float
    # Concentracao top-N por cedente.
    concentracao_top1_cedentes_pct: float
    concentracao_top5_cedentes_pct: float


class BreakdownItem(BaseModel):
    """Item generico de breakdown (faixa, sacado, originador, situacao).

    Para top-N + bucket "Outros", o servico ja inclui a row "Outros" agregada
    quando aplicavel — frontend nao precisa truncar.
    """

    chave: str = Field(description="Valor da dimensao agrupada (codigo, doc, etc).")
    label: str = Field(description="Texto display amigavel (nome do sacado, faixa A-H, etc).")
    valor_nominal: Decimal
    # Populado APENAS em `por_faixa_pdd` (decomposicao real do valor_pdd_total
    # por faixa Bacen 2682). Demais breakdowns deixam None — o card que
    # decompoe PDD precisa do valor real de provisao; os outros decompoem
    # valor_nominal e nao tem PDD agregada propria.
    valor_pdd: Decimal | None = None
    qtd_titulos: int
    pct_do_total: float = Field(description="Share desta dimensao sobre valor_nominal_total (em pontos %).")


class CarteiraBundleResponse(BaseModel):
    """Bundle agregado da carteira FIDC.

    `is_empty=true` indica que nao ha row em `wh_estoque_recebivel` para o
    escopo (tenant + fundo + data_referencia). Frontend renderiza EmptyState
    nesses casos em vez de KPIs zerados.

    Quando `data_referencia` requisitado for None e o tenant nao tem nenhuma
    row, `data_referencia` tambem retorna None.
    """

    data_referencia: date | None
    fundo_doc: str | None = Field(description="CNPJ do fundo (digits-only) quando filtrado por UA.")
    fundo_nome: str | None
    kpis: KpisCarteira
    por_faixa_pdd: list[BreakdownItem]
    top_sacados: list[BreakdownItem]
    top_cedentes: list[BreakdownItem]
    por_originador: list[BreakdownItem]
    por_produto: list[BreakdownItem]
    por_situacao: list[BreakdownItem]
    por_coobrigacao: list[BreakdownItem]
    provenance: ProvenanceMetadata
    is_empty: bool
