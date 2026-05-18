"""Metric catalog primitives — catálogo transversal de métricas/drivers/KPIs.

Fase 3a do refactor de proveniência transversal (2026-05-18). Paralelo a
`endpoint_catalog.py` (fontes externas) e `silver_catalog.py` (modelo
canônico interno). Resolve "como esse número foi calculado?" sem caixa-preta.

## Por que existe

Hoje cada módulo (controladoria, bi, risco) calcula seus KPIs e drivers em
services próprios, sem catálogo central. Quando o usuário pergunta "de onde
veio esse número?", a resposta exige ler N services e inferir o caminho até
o endpoint da administradora.

`MetricSpec` declara cada métrica do sistema como objeto de primeira classe:
qual módulo é dono, qual fórmula aplica, quais silvers e endpoints alimentam,
qual versão da regra. Permite:

1. **UI admin `/admin/proveniencia`** listar todas as métricas com proveniência.
2. **Reverse lookup**: "esse silver alimenta quais métricas?" → grep no catálogo.
3. **Auditoria**: cada `decision_log` referencia `MetricSpec.global_id`.
4. **Specialist Agent** (CLAUDE.md §19): tool determinística pra consultar
   catálogo em vez de inventar nomes.

## Convenções

- `module_code`: snake_case, espelha `Module` enum (`controladoria`, `bi`,
  `risco`, etc).
- `name`: hierárquico `<sub_area>.<categoria>.<atomo>` (ex.:
  `cota_sub.driver.apropriacao_dc`, `bi.vop.acumulado_mes`). Único dentro do
  módulo.
- `global_id`: `{module_code}.{name}` (ex.: `controladoria.cota_sub.driver.pdd`).
  Único no sistema todo.
- `version`: semver compacto ("1.0.0"). Bump quando fórmula muda
  semanticamente. Múltiplas versões coexistem — `decision_log` referencia a
  versão usada.

## Quem declara?

Cada módulo declara suas métricas em `app/modules/<modulo>/metric_catalogs/`
(ou similar). O `app/shared/metric_catalog.py` define apenas o primitivo
+ registry pra agregar.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class MetricCategory(StrEnum):
    """Tipo da métrica — influencia onde aparece na UI e como é interpretada.

    DRIVER: parcela explicativa de uma variação total (ex.: cada um dos 11
        drivers da Cota Sub). Soma de drivers ≈ ΔPL contábil. Aparece no
        AnaliseVariacaoCard.

    KPI: número agregado de alto nível (ex.: VOP do mês, PL do fundo, taxa
        de inadimplência). Aparece em KpiStrip/KpiCard.

    SERIE: série temporal (ex.: cota Sub histórica, rentabilidade 12M).
        Aparece em chart/EChartsCard.

    AGREGADO: agregação dimensional (ex.: PL por classe, VOP por produto).
        Aparece em tabela ou breakdown.

    INDICADOR: índice composto ou metadado calculado (ex.: faixa PDD média,
        DSO da carteira). Aparece em badges/labels.
    """

    DRIVER = "driver"
    KPI = "kpi"
    SERIE = "serie"
    AGREGADO = "agregado"
    INDICADOR = "indicador"


@dataclass(frozen=True)
class MetricSpec:
    """One metric / driver / KPI of the system.

    Attributes:
        module_code: snake_case do módulo dono (`controladoria`, `bi`, etc.).
            Espelha o `Module` enum.
        name: identificador hierárquico único dentro do módulo. Convenção
            `<sub_area>.<categoria>.<atomo>` (ex.: "cota_sub.driver.pdd").
            Validado como sequência de atoms `[a-z][a-z0-9_]*` separados
            por ponto.
        label: pt-BR human-readable, exibido na UI.
        description: 1-2 frases descrevendo o que a métrica significa
            (linguagem de domínio, não técnica).
        category: tipo da métrica — vê `MetricCategory`.
        formula_description: explicação humana da fórmula (ex.: "dEstoque -
            Aquisicoes + Liquidacoes"). Quando o cálculo é não-trivial, é
            esta string que aparece na UI quando o usuário clica "ver como
            foi calculado".
        silver_tables_required: tupla de nomes de silver (ex.:
            `("wh_estoque_recebivel", "wh_aquisicao_recebivel")`). Vazia
            quando a métrica não depende de silver (ex.: constantes).
        endpoints_required: tupla de `EndpointSpec.global_id` (ex.:
            `("qitech.market.fidc_estoque",)`). Quando algum endpoint estiver
            em estado degradado (PARTIAL/NOT_PUBLISHED/FURO_DEFINITIVO) pra
            uma data, a métrica é marcada como `indeterminada_por_dado`.
        version: semver compacto ("1.0.0", "1.1.0", "2.0.0"). Bump quando a
            fórmula muda. Registrado em `decision_log.rule_or_model_version`.
        owner: opcional — quem é responsável pela manutenção/correção (ex.:
            "controladoria-team"). Útil pra triagem.
    """

    module_code: str
    name: str
    label: str
    description: str
    category: MetricCategory
    formula_description: str
    silver_tables_required: tuple[str, ...]
    endpoints_required: tuple[str, ...]
    version: str
    owner: str | None = None

    @property
    def global_id(self) -> str:
        """System-wide unique identifier: `{module_code}.{name}`.

        Example: "controladoria.cota_sub.driver.pdd",
        "bi.vop.acumulado_mes".
        """
        return f"{self.module_code}.{self.name}"

    def __post_init__(self) -> None:
        # module_code: snake_case atom
        if not self.module_code or not _looks_like_snake_atom(self.module_code):
            raise ValueError(
                f"MetricSpec({self.name!r}): module_code must be a non-empty "
                f"snake_case atom without dots, got {self.module_code!r}"
            )
        # name: dotted snake_case (cada atom valida individualmente)
        if not self.name:
            raise ValueError(
                f"MetricSpec({self.name!r}): name cannot be empty"
            )
        atoms = self.name.split(".")
        if len(atoms) < 2:
            raise ValueError(
                f"MetricSpec({self.name!r}): name must have at least 2 atoms "
                f"separated by dot (got {self.name!r})"
            )
        for atom in atoms:
            if not _looks_like_snake_atom(atom):
                raise ValueError(
                    f"MetricSpec({self.name!r}): each atom of name must be "
                    f"snake_case (offending atom: {atom!r})"
                )
        # version: semver compacto
        if not _looks_like_semver(self.version):
            raise ValueError(
                f"MetricSpec({self.name!r}): version must be semver "
                f"`MAJOR.MINOR.PATCH` (got {self.version!r})"
            )
        # silver/endpoints: cada item não-vazio
        for tbl in self.silver_tables_required:
            if not tbl or not isinstance(tbl, str):
                raise ValueError(
                    f"MetricSpec({self.name!r}): silver_tables_required must "
                    f"contain non-empty strings (got {tbl!r})"
                )
        for ep_id in self.endpoints_required:
            if not ep_id or "." not in ep_id:
                raise ValueError(
                    f"MetricSpec({self.name!r}): endpoints_required must "
                    f"reference global_ids in format `<admin>.<name>` "
                    f"(got {ep_id!r})"
                )


def _looks_like_snake_atom(value: str) -> bool:
    """Validate snake_case atom: starts with letter, only lowercase/digit/_.

    Accepted: "qitech", "cota_sub", "v2", "apropriacao_dc".
    Rejected: "" / "QiTech" / "1cota" / "cota-sub" / "cota.sub".
    """
    if not value or not value[0].isalpha():
        return False
    return all(c.islower() or c.isdigit() or c == "_" for c in value)


def _looks_like_semver(value: str) -> bool:
    """Validate semver compacto: `MAJOR.MINOR.PATCH` (3 inteiros não-negativos).

    Aceito: "1.0.0", "0.1.0", "10.20.30".
    Rejeitado: "1.0" / "1.0.0-rc1" / "v1.0.0" / "1.0.0.0".
    """
    parts = value.split(".")
    if len(parts) != 3:
        return False
    return all(p.isdigit() for p in parts)
