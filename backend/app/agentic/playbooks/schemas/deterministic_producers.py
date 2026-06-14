"""Deterministic producers — silver payload -> SectionDescriptor (Passo 2-A).

A camada "consulta/silver" do dossiê (cadastral, faturamento, societário) vira
seções de bloco no descritor, ao lado das seções de agente. Decisão A1: o
backend constrói; estes mappers espelham os painéis determinísticos das
AnalysisViews do cockpit.

PUROS: payload (dict, como os services `build_*` devolvem) -> SectionDescriptor.
Sem DB — o endpoint busca o payload e chama estes. Cada produtor anexa sua seção
à estação do nó-fonte (id da estação == id do nó âncora). Começo: cadastral
(campos já projetados pelo Contrato de Dados). Faturamento/societário: próximos.

See docs/esteira-credito-interface-camadas.md §5 (Passo 2-A).
"""

from __future__ import annotations

from typing import Any

from app.agentic.playbooks.schemas.section_descriptor import (
    FichaBlock,
    FichaCampo,
    ProvenanceRef,
    SectionDescriptor,
)


def _coerce_display(value: Any) -> str | None:
    """Valor cru -> texto display-safe (None se vazio)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return "Sim" if value else "Não"
    if isinstance(value, list):
        parts = [str(x).strip() for x in value if x is not None and str(x).strip()]
        return ", ".join(parts) or None
    text = str(value).strip()
    return text or None


def cadastral_card_to_section(card: dict, station_id: str) -> SectionDescriptor | None:
    """Projeção cadastral (build_cadastral_card_projection) -> seção Ficha.

    `card.campos` já vem com label pt-BR + valor (projetado pelo Contrato de
    Dados). Campos `novo` (fora do contrato) ganham badge. Proveniência = fonte
    externa (cyan). Retorna None quando não há dado (estação fica só com o agente).
    """
    if not card or not card.get("encontrado"):
        return None

    campos: list[FichaCampo] = []
    for c in card.get("campos") or []:
        valor = _coerce_display(c.get("valor"))
        if valor is None:
            continue
        campos.append(
            FichaCampo(
                label=c.get("label") or c.get("field_path") or "—",
                valor=valor,
                badge=None,  # 'novo' (🆕) é destaque de QA da tela cadastral, não do dossiê
                provenance=ProvenanceRef(origin="fonte"),
            )
        )

    if not campos:
        return None

    return SectionDescriptor(
        id=f"det-{station_id}",
        station_id=station_id,
        titulo="Identificação e cadastro",
        blocks=[
            FichaBlock(
                id=f"det-{station_id}-ficha",
                campos=campos,
                provenance=ProvenanceRef(origin="fonte"),
            )
        ],
        generates_dossier_section=True,
    )


__all__ = ["cadastral_card_to_section"]
