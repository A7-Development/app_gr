"""Silver catalog primitives — catálogo do modelo canônico interno.

Fase 3a do refactor de proveniência transversal (2026-05-18). Paralelo a
`endpoint_catalog.py` (fontes externas) e `metric_catalog.py` (consumo).
Resolve "esse silver é populado por quem?" e "alimenta quais métricas?".

## Por que existe

Hoje a relação `endpoint → silver` é declarada via `EndpointSpec.canonical_table`.
A relação `silver → métrica` está implícita nos services. Sem catálogo central
de silvers, não dá pra fazer reverse lookup ("essa tabela alimenta o quê?")
nem expor freshness por silver de forma uniforme.

`SilverSpec` declara cada tabela `wh_*` como objeto de primeira classe:
quais endpoints a alimentam, qual sua chave primária lógica, se é tenant-scoped,
se tem dimensão temporal.

## Convenções

- `table_name`: snake_case prefixado com `wh_` (ex.: `wh_estoque_recebivel`).
  Espelha `__tablename__` do model SQLAlchemy.
- `fed_by_endpoints`: tupla de `EndpointSpec.global_id` (ex.:
  `("qitech.market.fidc_estoque",)`). Quando múltiplos endpoints/admins
  alimentam o mesmo silver, lista todos. Vazia se silver é derivado de outro
  silver (não vindo direto de endpoint externo).
- `primary_key`: tupla de coluna names que formam a chave lógica de upsert
  (não inclui `id` artificial). Usada pra debug e validação.
- `tenant_scoped`: True se a tabela tem `tenant_id`. Quase sempre True.
- `temporal`: True se a tabela tem dimensão de data (`data_referencia`,
  `data_posicao`, etc) que permite filtragem por janela temporal.

## Quem declara?

Para silvers QiTech-alimentados, o catálogo vive em
`app/warehouse/silver_catalog.py`. Quando outros adapters virarem, cada
um pode adicionar entradas (ou criar arquivo paralelo se ficar grande).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SilverSpec:
    """One silver (canonical) table of the warehouse.

    Attributes:
        table_name: nome físico da tabela no Postgres (ex.: "wh_estoque_recebivel").
            Espelha `__tablename__` do model. Prefixado com `wh_` por convenção.
        label: pt-BR human-readable (ex.: "Estoque de recebíveis").
        description: 1-2 frases sobre o que essa tabela representa no domínio.
        fed_by_endpoints: tupla de `EndpointSpec.global_id` que populam essa
            tabela (ex.: `("qitech.market.fidc_estoque",)`). Quando vazia,
            silver é derivado/computado (não vem direto de fonte externa).
        primary_key: tupla das colunas que formam a chave lógica de upsert.
            Não inclui `id` artificial. Usada em validações e debug.
        tenant_scoped: True se a tabela tem `tenant_id`. Quase sempre True
            no GR (multi-tenant absoluto). Tabelas globais (catalogos,
            calendarios) podem ter False.
        temporal: True se a tabela tem dimensão de data que permite filtro
            por janela. Influencia a UI de cobertura/freshness.
        date_column: nome da coluna de data quando `temporal=True`. None
            quando não-temporal.
    """

    table_name: str
    label: str
    description: str
    fed_by_endpoints: tuple[str, ...]
    primary_key: tuple[str, ...]
    tenant_scoped: bool = True
    temporal: bool = True
    date_column: str | None = None

    def __post_init__(self) -> None:
        # table_name: snake_case, prefixo `wh_`
        if not self.table_name.startswith("wh_"):
            raise ValueError(
                f"SilverSpec({self.table_name!r}): table_name must start "
                f"with 'wh_' prefix"
            )
        if not _is_snake_case(self.table_name):
            raise ValueError(
                f"SilverSpec({self.table_name!r}): table_name must be "
                f"snake_case (lowercase + underscore)"
            )
        # fed_by_endpoints: cada item é global_id válido (`<admin>.<name>`)
        for ep_id in self.fed_by_endpoints:
            if not ep_id or "." not in ep_id:
                raise ValueError(
                    f"SilverSpec({self.table_name!r}): fed_by_endpoints "
                    f"must reference global_ids `<admin>.<name>` "
                    f"(got {ep_id!r})"
                )
        # primary_key: pelo menos 1 coluna, cada não-vazia
        if not self.primary_key:
            raise ValueError(
                f"SilverSpec({self.table_name!r}): primary_key cannot be empty"
            )
        for col in self.primary_key:
            if not col or not isinstance(col, str):
                raise ValueError(
                    f"SilverSpec({self.table_name!r}): primary_key items "
                    f"must be non-empty strings (got {col!r})"
                )
        # temporal: implica date_column preenchida
        if self.temporal and not self.date_column:
            raise ValueError(
                f"SilverSpec({self.table_name!r}): temporal=True requires "
                f"date_column to be set"
            )
        if not self.temporal and self.date_column:
            raise ValueError(
                f"SilverSpec({self.table_name!r}): date_column set but "
                f"temporal=False — incoherent"
            )


def _is_snake_case(value: str) -> bool:
    """Valida que value é snake_case (lowercase, dígitos, underscore)."""
    if not value:
        return False
    return all(c.islower() or c.isdigit() or c == "_" for c in value)
