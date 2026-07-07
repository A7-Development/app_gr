"""Build a DossierDescriptor from a workflow run's node steps (A1, Etapa 4 core).

This is the BACKEND port of the cockpit's client-side `buildEstacoes` + section
dispatch (`(foco)/credito/dossies/[id]/page.tsx`). Decision A1: the backend
builds the descriptor; the cockpit (Etapa 4 wiring step) then consumes this
instead of deriving stations client-side, and `AGENT_STATION_AFFINITY` /
`buildEstacoes` are deleted from the frontend.

PURE: takes already-normalized node steps (no ORM, no DB) and returns a
``DossierDescriptor``. The endpoint that fetches the graph + node_runs and calls
this is the wiring step (needs DB / live test) — kept out of this module so the
fusion logic stays unit-testable in isolation.

INTERIM affinity: while the graph does not yet declare ``station`` /
``§ gera seção`` / block-contract per node (the migration step of Etapa 4), this
ports the same affinity heuristic the frontend used. When the graph declares it,
this reads the declaration instead of guessing — same output shape.

See docs/esteira-credito-interface-camadas.md §5 (Etapa 4).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from app.agentic.engine.output_schemas import (
    CadastralAnalysis,
    RevenueAnalysis,
    SocialContractAnalysis,
)
from app.agentic.workflows.schemas.section_builders import (
    cadastral_to_section,
    revenue_to_section,
    social_contract_to_section,
)
from app.agentic.workflows.schemas.section_descriptor import (
    DossierDescriptor,
    SectionDescriptor,
    StationDescriptor,
    StationState,
)

# ─── Input shape (normalized node step; mirrors WizardMultiStepStep) ──────────


class NodeStep(BaseModel):
    """One node of the run, already ordered topologically by the caller."""

    model_config = ConfigDict(extra="ignore")

    id: str
    label: str
    node_type: str
    # pending | running | completed | failed | skipped | waiting_input
    state: str
    output: dict[str, Any] | None = None
    input: dict[str, Any] | None = None
    config: dict[str, Any] | None = None


# Nós que não viram estação — são bastidor ("só trilha"). Espelha TRILHA_TYPES.
_TRILHA_TYPES = frozenset(
    {"trigger", "notification", "output_generator", "http_request", "conditional_branch"}
)

# Afinidade agente → fonte da seção (interim até o grafo declarar § gera seção).
_AGENT_STATION_AFFINITY = {
    "revenue_analyst": "document_request",
    "cadastral_analyst": "cadastral_enrichment",
    "social_contract_analyst": "document_request",
}
_AGENT_STATION_LABEL = {
    "revenue_analyst": "Faturamento",
    "cadastral_analyst": "Cadastral",
    "social_contract_analyst": "Contrato social",
}

# O rótulo/aspecto da estação vem do DOCUMENTO que ela coleta, não do nome do
# agente (decoupling Fatia 2a). Espelha DOC_TYPE_STATION_LABEL do frontend.
_DOC_TYPE_STATION_LABEL = {
    "revenue_report": "Faturamento",
    "social_contract": "Contrato social",
}

# Receita de busca oficial → tipo de documento que ela produz. Uma busca oficial
# e o pedido manual do MESMO documento são uma estação só (Fatia 2c). Espelha
# OFFICIAL_FETCH_DOC_TYPE do frontend / RECIPES do node.
_OFFICIAL_FETCH_DOC_TYPE = {
    "social_contract_jucesp": "social_contract",
}


def _official_fetch_doc_type(step: NodeStep) -> str | None:
    recipe = (step.config or {}).get("document") if isinstance(step.config, dict) else None
    from_output = (step.output or {}).get("doc_type") if isinstance(step.output, dict) else None
    if isinstance(recipe, str) and recipe in _OFFICIAL_FETCH_DOC_TYPE:
        return _OFFICIAL_FETCH_DOC_TYPE[recipe]
    return from_output if isinstance(from_output, str) else None

# Agente → builder de seção (os 3 migrados na Etapa 2). Outros: seção vazia
# (camada determinística / outros produtores ainda não portados).
_SECTION_BUILDER_BY_AGENT = {
    "revenue_analyst": lambda o: revenue_to_section(RevenueAnalysis.model_validate(o)),
    "cadastral_analyst": lambda o: cadastral_to_section(CadastralAnalysis.model_validate(o)),
    "social_contract_analyst": lambda o: social_contract_to_section(
        SocialContractAnalysis.model_validate(o)
    ),
}


def _agent_of(step: NodeStep) -> str | None:
    for src in (step.input, step.config):
        if isinstance(src, dict) and isinstance(src.get("agent"), str):
            return src["agent"]
    return None


def _review_of(step: NodeStep) -> str | None:
    if isinstance(step.config, dict) and isinstance(step.config.get("review_of"), str):
        return step.config["review_of"]
    return None


def _required_doc_types(step: NodeStep) -> list[str]:
    """Tipos de documento exigidos por um document_request (config ou output)."""
    for src in (step.config, step.output):
        if isinstance(src, dict) and isinstance(src.get("required"), list):
            return [str(t) for t in src["required"]]
    return []


class _Estacao:
    """Acumulador interno (espelha o type Estacao do frontend)."""

    def __init__(self, anchor: NodeStep, label: str) -> None:
        self.id = anchor.id
        self.label = label
        self.members: list[NodeStep] = [anchor]


def _anchor_for(step: NodeStep, estacoes: list[_Estacao]) -> _Estacao | None:
    """Porte fiel de buildEstacoes.anchorFor — a que estação o nó se funde."""
    if step.node_type == "deterministic_check":
        return estacoes[-1] if estacoes else None
    if step.node_type == "document_request":
        # Pedido manual que é fallback de uma busca oficial do MESMO documento
        # funde na estação dela (Fatia 2c). Só a última estação.
        req = _required_doc_types(step)
        last = estacoes[-1] if estacoes else None
        if last is not None:
            fetch_types = [
                t
                for m in last.members
                if m.node_type == "official_document_fetch"
                for t in [_official_fetch_doc_type(m)]
                if t is not None
            ]
            if any(t in req for t in fetch_types):
                return last
        return None
    if step.node_type == "document_extractor":
        for e in reversed(estacoes):
            if any(m.node_type == "document_request" for m in e.members):
                return e
        return None
    if step.node_type == "specialist_agent":
        agent = _agent_of(step)
        # opinion_writer é o sintetizador → estação "Parecer" própria.
        if agent == "opinion_writer":
            return None
        affinity = _AGENT_STATION_AFFINITY.get(agent) if agent else None
        if affinity:
            for e in reversed(estacoes):
                if any(m.node_type == affinity for m in e.members):
                    return e
        # Fallback decoupled (Fatia 2a): analista que continua um pipeline de
        # documento funde na estação dele, independente do nome do agente. Só a
        # última estação, e só se ela coleta documento e ainda não tem analista.
        last = estacoes[-1] if estacoes else None
        if (
            last is not None
            and any(m.node_type == "document_request" for m in last.members)
            and not any(m.node_type == "specialist_agent" for m in last.members)
        ):
            return last
        return None
    if step.node_type == "human_review":
        target = _review_of(step)
        if target:
            for e in estacoes:
                if any(_agent_of(m) == target or m.id == target for m in e.members):
                    return e
            return None
        # Checkpoint final → estação do opinion_writer ("Parecer").
        for e in estacoes:
            if any(_agent_of(m) == "opinion_writer" for m in e.members):
                return e
        return None
    return None


def _estacao_state(members: list[NodeStep]) -> StationState:
    """Porte fiel de estacaoState."""
    if any(m.state == "failed" for m in members):
        return "falhou"
    waiting = next((m for m in members if m.state == "waiting_input"), None)
    if waiting is not None:
        if waiting.node_type == "human_review":
            return "homologar"
        if waiting.node_type == "document_request":
            return "aguardando_documento"
        return "sua_vez"
    if any(m.state == "running" for m in members):
        return "rodando"
    if all(m.state in ("completed", "skipped") for m in members):
        return "fechada"
    return "bloqueada"


_CLOSED = frozenset({"fechada", "fechada_com_ressalva"})


def _build_sections(members: list[NodeStep]) -> list[SectionDescriptor]:
    """Seções da estação: por ora só a de agente migrado (Etapa 2)."""
    sections: list[SectionDescriptor] = []
    for m in members:
        if m.node_type != "specialist_agent" or m.state != "completed" or not m.output:
            continue
        agent = _agent_of(m)
        builder = _SECTION_BUILDER_BY_AGENT.get(agent) if agent else None
        if builder is None:
            continue
        try:
            sections.append(builder(m.output))
        except Exception:
            continue
    return sections


def build_dossier_descriptor(code: str, steps: list[NodeStep]) -> DossierDescriptor:
    """node steps (topologicamente ordenados) → DossierDescriptor.

    `code` = DC-AAAA-NNNN. `steps` na ordem do grafo (o caller ordena).
    """
    estacoes: list[_Estacao] = []
    for step in steps:
        if step.node_type in _TRILHA_TYPES:
            continue
        host = _anchor_for(step, estacoes)
        if host is not None:
            host.members.append(step)
            agent = _agent_of(step)
            if step.node_type == "specialist_agent" and agent and agent in _AGENT_STATION_LABEL:
                host.label = _AGENT_STATION_LABEL[agent]
            continue
        # Nova estação. opinion_writer / human_review solto → "Parecer".
        label = (
            "Parecer"
            if _agent_of(step) == "opinion_writer" or step.node_type == "human_review"
            else step.label
        )
        estacoes.append(_Estacao(step, label))

    # Rótulo pelo ASPECTO do documento coletado (decoupled do nome do agente):
    # override quando o document_request declara um tipo conhecido.
    for e in estacoes:
        doc_req = next((m for m in e.members if m.node_type == "document_request"), None)
        if doc_req is None:
            continue
        aspect = next(
            (
                _DOC_TYPE_STATION_LABEL[t]
                for t in _required_doc_types(doc_req)
                if t in _DOC_TYPE_STATION_LABEL
            ),
            None,
        )
        if aspect:
            e.label = aspect

    stations: list[StationDescriptor] = []
    prev_id: str | None = None
    for e in estacoes:
        state = _estacao_state(e.members)
        stations.append(
            StationDescriptor(
                id=e.id,
                label=e.label,
                state=state,
                # Prontidão por dependência: linear (estação anterior). Quando o
                # grafo declarar deps explícitas, troca-se aqui.
                depends_on=[prev_id] if prev_id else [],
                member_node_ids=[m.id for m in e.members],
                sections=_build_sections(e.members),
            )
        )
        prev_id = e.id

    # Bússola: 1ª não-fechada é a recomendada (espelha pickRecommendedNext).
    rec = next((s for s in stations if s.state not in _CLOSED), None)
    if rec is not None:
        rec.is_recommended_next = True

    return DossierDescriptor(code=code, stations=stations)


__all__ = ["NodeStep", "build_dossier_descriptor"]
