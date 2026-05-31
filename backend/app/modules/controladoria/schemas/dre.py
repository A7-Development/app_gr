"""Pydantic schemas — Controladoria · DRE.

Contrato dos endpoints `/api/v1/controladoria/dre/*`. Espelho do silver
canonico `wh_dre_mensal` (CLAUDE.md §13.2.1: dominio le APENAS de silver).

Estrutura do pivot e hierarquica em 3 niveis:

    grupo (ordem_grupo, grupo_dre)
        subgrupo
            descricao   <- folha (linha individual de wh_dre_mensal)

Cada nivel carrega `valores[]` agregados por competencia + `totais`
agregado no periodo inteiro. Frontend renderiza como tabela hierarquica
expandivel (DataTable + getSubRows).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field

# Valores canonicos da coluna `fonte` em wh_dre_mensal -- espelham
# `_TIPO_TO_FONTE` no ETL Bitfin (etl.py). Usado pra validar o filtro `fonte`
# dos endpoints: valor fora dessa lista vira 422 (em vez de silenciosamente
# retornar zero linhas, como acontecia quando o frontend mandava os nomes de
# tipo_origem -- dre_legacy/pagamento_opcao/comissao_fechamento -- que nunca
# casavam com a coluna silver).
DreFonte = Literal["DRE_OPERACIONAL", "CONTAS_A_PAGAR", "COMISSAO"]


class DreCelula(BaseModel):
    """Valor agregado de uma linha em uma competencia (mes)."""

    competencia: date = Field(description="Primeiro dia do mes (YYYY-MM-01)")
    receita: Decimal
    custo: Decimal
    resultado: Decimal
    quantidade: int


class DreLinhaTotais(BaseModel):
    """Total da linha (grupo / subgrupo / descricao) no periodo inteiro."""

    receita: Decimal
    custo: Decimal
    resultado: Decimal
    quantidade: int


class DreFornecedor(BaseModel):
    """4o (e ultimo) nivel da hierarquia — fornecedor dentro de uma descricao.

    Quando o silver tem rows sem fornecedor identificado (vide
    RECEITA_OPERACIONAL, PDD, COMISSAO_COMERCIAL — todos com
    fornecedor_documento NULL), elas sao agregadas como um fornecedor
    sintetico com `fornecedor=None` + `fornecedor_documento=None`. Frontend
    detecta esse caso e renderiza a descricao como folha (sem expand).
    """

    fornecedor: str | None
    fornecedor_documento: str | None
    valores: list[DreCelula]
    totais: DreLinhaTotais


class DreDescricao(BaseModel):
    """No do pivot — uma descricao dentro de um subgrupo, com fornecedores."""

    descricao: str
    fornecedores: list[DreFornecedor]
    valores: list[DreCelula]
    totais: DreLinhaTotais


class DreSubgrupo(BaseModel):
    """No intermediario — agrupa descricoes.

    `ordem_grupo` mora aqui (nao no grupo macro) porque na classificacao
    e atributo do subgrupo: dentro de um mesmo `grupo_dre` macro
    (ex.: RECEITA_OPERACIONAL) existem varios subgrupos cada um com sua
    propria ordem (1=Operação, 2=Credito Estruturado, 3=Recompra, ...,
    7=Despesa). Frontend ordena subgrupos por `ordem_grupo` asc.
    """

    ordem_grupo: int
    subgrupo: str
    descricoes: list[DreDescricao]
    valores: list[DreCelula] = Field(
        description="Agregado das descricoes por competencia",
    )
    totais: DreLinhaTotais


class DreGrupo(BaseModel):
    """No raiz da hierarquia — um grupo canonico da DRE.

    Ordenacao na resposta: por `min(subgrupos.ordem_grupo)` asc —
    e.g. RECEITA_OPERACIONAL (min=1) vem antes de PROVISAO_PDD (min=6).
    """

    grupo_dre: str
    subgrupos: list[DreSubgrupo]
    valores: list[DreCelula] = Field(
        description="Agregado dos subgrupos por competencia",
    )
    totais: DreLinhaTotais


class DrePivotResponse(BaseModel):
    """Resposta do GET /pivot — DRE hierarquica expandivel."""

    competencias: list[date] = Field(
        description="Lista ordenada de meses do periodo (mesmo se sem dado, "
        "vem com zeros). Frontend usa pra montar header da tabela.",
    )
    grupos: list[DreGrupo]
    valores_total: list[DreCelula] = Field(
        description="Total geral por competencia (soma de todos os grupos)",
    )
    totais: DreLinhaTotais = Field(
        description="Total geral no periodo inteiro",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Receita por NATUREZA (Desagio/Tarifa/Multa/Juros/Ad Valorem/Imposto)
# Estrutura: natureza -> tipo (descricao) x competencia. Receita = SO receita
# (total_apurado); custos descem para outras secoes do DRE.
# ─────────────────────────────────────────────────────────────────────────────


class DreReceitaCelula(BaseModel):
    """Receita de um no em uma competencia (mes)."""

    competencia: date = Field(description="Primeiro dia do mes (YYYY-MM-01)")
    receita: Decimal
    quantidade: int


class DreReceitaTipo(BaseModel):
    """Folha: um tipo (descricao do catalogo) dentro de uma natureza.

    `produtos` = subgrupos Bitfin onde o tipo aparece (ex.: Desagio aparece
    em Operação e Crédito Estruturado) — contexto preservado sem ramificar
    a hierarquia.
    """

    descricao: str
    produtos: list[str]
    valores: list[DreReceitaCelula]
    total: Decimal


class DreReceitaNatureza(BaseModel):
    """No de natureza (Desagio/Tarifa/Multa/Juros/Ad Valorem/Imposto)."""

    natureza: str
    tipos: list[DreReceitaTipo]
    valores: list[DreReceitaCelula]
    total: Decimal


class DreReceitaNaturezaResponse(BaseModel):
    """Resposta do GET /receita-por-natureza."""

    competencias: list[date]
    naturezas: list[DreReceitaNatureza]
    valores_total: list[DreReceitaCelula]
    total: Decimal


class DreFornecedorRow(BaseModel):
    """Uma linha do drill por fornecedor."""

    fornecedor: str | None
    fornecedor_documento: str | None
    receita: Decimal
    custo: Decimal
    resultado: Decimal
    quantidade: int


class DreFornecedoresResponse(BaseModel):
    """Resposta do GET /drill/fornecedores — top fornecedores em um corte."""

    grupo_dre: str
    subgrupo: str | None
    descricao: str | None
    competencia_de: date
    competencia_ate: date
    fornecedores: list[DreFornecedorRow]
    total_fornecedores: int = Field(
        description="Total de fornecedores distintos no corte (antes do limit)",
    )
