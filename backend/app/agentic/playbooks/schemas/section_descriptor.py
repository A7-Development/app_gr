"""Universal UI contract for the credit dossier esteira (Phase 1 — foundation).

See docs/esteira-credito-interface-camadas.md.

Principle (A1): every node — agent OR NOT — exposes a ``SectionDescriptor``
(a list of blocks). The backend BUILDS the descriptor; the frontend renderer is
"dumb" and never changes when a new flow/node is added. Consistency lives in the
closed block vocabulary (Layer C), not in per-type code.

This module is the Pydantic mirror of ``frontend/src/design-system/types/section.ts``
plus the ui-hint mechanism (A2) that lets an agent's ``output_schema`` declare
which block each field becomes. It is contract-only: nothing is wired into an
endpoint yet (that is Phase 1 / Etapa 2 — the descriptor builder).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ════════════════════════════════════════════════════════════════════════════
# Provenance + citation (mirror of tokens/provenance.ts)
# ════════════════════════════════════════════════════════════════════════════

ProvenanceOrigin = Literal["fonte", "agente", "documento", "analista"]


class DocLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["doc"] = "doc"
    doc_id: str
    page: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    trecho: str | None = None


class SilverLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["silver"] = "silver"
    table: str
    field: str


class AgentStepLocator(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["agent_step"] = "agent_step"
    run_id: str
    step_id: str | None = None


ProvenanceLocator = Annotated[
    DocLocator | SilverLocator | AgentStepLocator,
    Field(discriminator="kind"),
]


class ProvenanceRef(BaseModel):
    """Travels on every block/field/value. Citation = origin + locator."""

    model_config = ConfigDict(extra="forbid")

    origin: ProvenanceOrigin
    locator: ProvenanceLocator | None = None
    # Agent conclusion: dotted -> solid once homologated (signature E3).
    homologado: bool | None = None


# ════════════════════════════════════════════════════════════════════════════
# Layer C — closed block vocabulary (6 display + 2 interactive + 1 recursive)
# ════════════════════════════════════════════════════════════════════════════

BlockType = Literal[
    "ficha",
    "tabela",
    "grafico",
    "conclusao_agente",
    "apontamentos",
    "texto",
    "conferencia",
    "fonte_origem",
    "sub_dossie",
]


class FichaBadge(BaseModel):
    model_config = ConfigDict(extra="forbid")
    texto: str
    tom: Literal["ok", "atencao", "critico", "neutro"]


class FichaCampo(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str
    valor: str
    # Linha secundária (muted) — ex.: a leitura do agente sob um valor.
    nota: str | None = None
    # Marcador curto inline (situação, "leitura fraca", etc.).
    badge: FichaBadge | None = None
    provenance: ProvenanceRef | None = None


class FichaBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["ficha"] = "ficha"
    id: str
    provenance: ProvenanceRef | None = None
    titulo: str | None = None
    campos: list[FichaCampo] = Field(default_factory=list)


class TabelaColuna(BaseModel):
    model_config = ConfigDict(extra="forbid")
    key: str
    label: str
    align: Literal["left", "right", "center"] | None = None
    formato: Literal["texto", "numero", "brl", "pct", "data"] | None = None


class TabelaCelula(BaseModel):
    model_config = ConfigDict(extra="forbid")
    valor: str | float | int | None = None
    provenance: ProvenanceRef | None = None


class TabelaBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["tabela"] = "tabela"
    id: str
    provenance: ProvenanceRef | None = None
    titulo: str | None = None
    colunas: list[TabelaColuna] = Field(default_factory=list)
    linhas: list[dict[str, TabelaCelula]] = Field(default_factory=list)
    # Reconciliation footer (§14.6): visible sum that matches the headline.
    rodape: dict[str, TabelaCelula] | None = None


class GraficoSerie(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nome: str
    pontos: list[dict[str, Any]] = Field(default_factory=list)  # {x: str, y: float}


class GraficoKpi(BaseModel):
    model_config = ConfigDict(extra="forbid")
    eyebrow: str | None = None
    valor: str
    delta: str | None = None
    contexto: str | None = None


class GraficoBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["grafico"] = "grafico"
    id: str
    provenance: ProvenanceRef | None = None
    titulo: str | None = None
    kpi: GraficoKpi | None = None
    series: list[GraficoSerie] = Field(default_factory=list)


class ConclusaoRecomendacao(BaseModel):
    model_config = ConfigDict(extra="forbid")
    veredito: Literal["aprovar", "negar", "condicional"]
    condicoes: list[str] = Field(default_factory=list)


class ConclusaoAgenteBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["conclusao_agente"] = "conclusao_agente"
    id: str
    provenance: ProvenanceRef | None = None
    agente: str
    resumo: str
    recomendacao: ConclusaoRecomendacao | None = None
    homologado: bool = False


class Apontamento(BaseModel):
    model_config = ConfigDict(extra="forbid")
    severidade: Literal["critico", "atencao", "info"]
    titulo: str
    descricao: str | None = None
    evidencia: str | None = None
    provenance: ProvenanceRef | None = None


class ApontamentosBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["apontamentos"] = "apontamentos"
    id: str
    provenance: ProvenanceRef | None = None
    titulo: str | None = None
    itens: list[Apontamento] = Field(default_factory=list)


class TextoBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["texto"] = "texto"
    id: str
    provenance: ProvenanceRef | None = None
    titulo: str | None = None
    markdown: str


class ConferenciaLinha(BaseModel):
    model_config = ConfigDict(extra="forbid")
    campo: str
    valor_ia: str
    valor_dossie: str
    estado: Literal["ok", "ajustado", "pendente"]
    locator: ProvenanceLocator | None = None


class ConferenciaBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["conferencia"] = "conferencia"
    id: str
    provenance: ProvenanceRef | None = None
    titulo: str | None = None
    linhas: list[ConferenciaLinha] = Field(default_factory=list)


class FonteOrigemBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["fonte_origem"] = "fonte_origem"
    id: str
    provenance: ProvenanceRef | None = None
    doc_id: str
    locator: ProvenanceLocator | None = None


class SubDossieBlock(BaseModel):
    """Recursive (Phase 2 — the dream). Declared and idle in Phase 1."""

    model_config = ConfigDict(extra="forbid")
    type: Literal["sub_dossie"] = "sub_dossie"
    id: str
    provenance: ProvenanceRef | None = None
    titulo: str
    descriptor: SectionDescriptor


Block = Annotated[
    FichaBlock
    | TabelaBlock
    | GraficoBlock
    | ConclusaoAgenteBlock
    | ApontamentosBlock
    | TextoBlock
    | ConferenciaBlock
    | FonteOrigemBlock
    | SubDossieBlock,
    Field(discriminator="type"),
]


# ════════════════════════════════════════════════════════════════════════════
# Layer B — SectionDescriptor (what each node exposes)
# ════════════════════════════════════════════════════════════════════════════


class SectionDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    # Station this section belongs to (declared in the graph — Etapa 4).
    station_id: str
    titulo: str
    blocks: list[Block] = Field(default_factory=list)
    provenance: ProvenanceRef | None = None
    # § gera seção: does it enter the compiled dossier projection? False = only
    # workbench / trail, not a section of the final document.
    generates_dossier_section: bool = True


# Station readiness vocabulary (mirror of StationState; bússola model §1.1).
StationState = Literal[
    "fechada",
    "fechada_com_ressalva",
    "sua_vez",
    "homologar",
    "rodando",
    "aguardando_documento",
    "em_espera",
    "bloqueada",
    "falhou",
]

CLOSED_STATION_STATES: frozenset[str] = frozenset(
    {"fechada", "fechada_com_ressalva"}
)


class StationDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    label: str
    sublabel: str | None = None
    state: StationState
    # Readiness BY DEPENDENCY, not sequence (§1.1): ids of stations that must
    # close before this one can open. Empty = no prerequisite.
    depends_on: list[str] = Field(default_factory=list)
    # Set when state="bloqueada": "esperando Cadastral".
    blocked_reason: str | None = None
    # The compass: suggested next station. NOT a lock — every ready station is navigable.
    is_recommended_next: bool = False
    sections: list[SectionDescriptor] = Field(default_factory=list)


class DossierDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Human code (DC-AAAA-NNNN).
    code: str
    stations: list[StationDescriptor] = Field(default_factory=list)


# Resolve the forward ref used by SubDossieBlock.descriptor.
SubDossieBlock.model_rebuild()


# ════════════════════════════════════════════════════════════════════════════
# A2 — ui-hints: an agent's output_schema declares which block each field becomes
# ════════════════════════════════════════════════════════════════════════════
#
# The hint rides on the Pydantic field's ``json_schema_extra`` so structure and
# presentation stay together (single source). The descriptor builder reads these
# to map an agent's typed output onto blocks. Existing agent schemas are NOT
# retrofitted here — they get annotated in Etapa 2 when migrated behind the
# renderer.

STRATA_BLOCK_KEY = "strata_block"


def block_hint(block_type: BlockType, **field_kwargs: Any) -> Any:
    """Annotate a Pydantic field with the block it should render as.

    Usage in an agent output_schema::

        class RevenueAnalysis(BaseModel):
            resumo_executivo: str = block_hint("conclusao_agente")
            pontos_de_atencao: list[...] = block_hint("apontamentos", default_factory=list)
    """
    extra = field_kwargs.pop("json_schema_extra", {}) or {}
    if not isinstance(extra, dict):  # pragma: no cover - defensive
        raise TypeError("json_schema_extra must be a dict to merge a block hint")
    extra = {**extra, STRATA_BLOCK_KEY: block_type}
    return Field(json_schema_extra=extra, **field_kwargs)


def read_block_hints(model: type[BaseModel]) -> dict[str, BlockType]:
    """Return {field_name: block_type} for fields annotated via ``block_hint``."""
    hints: dict[str, BlockType] = {}
    for name, field in model.model_fields.items():
        extra = field.json_schema_extra
        if isinstance(extra, dict) and STRATA_BLOCK_KEY in extra:
            hints[name] = extra[STRATA_BLOCK_KEY]  # type: ignore[assignment]
    return hints
