"""Unit tests for the DossierDescriptor builder (A1, Etapa 4 core).

Pure — no DB. Run with:
    pytest tests/agentic/test_dossier_descriptor_builder.py --noconftest
"""

from __future__ import annotations

from typing import Any

from app.agentic.playbooks.schemas.dossier_descriptor_builder import (
    NodeStep,
    build_dossier_descriptor,
)

_REVENUE_OUTPUT: dict[str, Any] = {
    "resumo_executivo": "Crescente.",
    "tendencia": {"direcao": "crescente", "intensidade": "forte", "leitura": "x"},
    "sazonalidade": {"detectada": False, "confiavel": True, "padrao": None},
    "pontos_de_atencao": [],
    "qualidade_do_dado": {"soma_confere": True, "n_meses": 12, "meses_faltantes": [], "observacao": "ok"},
    "credibilidade_documento": {"assinado": True, "nivel": "alto", "leitura": "x", "ressalvas": []},
    "leitura_para_credito": "ok",
}


def _flow() -> list[NodeStep]:
    """Fluxo faturamento + cadastral + parecer (espelha onboarding real)."""
    return [
        NodeStep(id="identificacao", label="Identificação", node_type="human_input", state="completed"),
        NodeStep(id="dados_basicos", label="Dados básicos", node_type="cadastral_enrichment", state="completed"),
        NodeStep(id="coleta_fat", label="Documento", node_type="document_request", state="completed"),
        NodeStep(id="extrai_fat", label="Extração", node_type="document_extractor", state="completed"),
        NodeStep(
            id="analise_fat", label="Análise", node_type="specialist_agent", state="completed",
            config={"agent": "revenue_analyst"}, output=_REVENUE_OUTPUT,
        ),
        NodeStep(
            id="check_fat", label="Homologação", node_type="human_review", state="waiting_input",
            config={"review_of": "revenue_analyst"},
        ),
        NodeStep(
            id="analise_cad", label="Análise", node_type="specialist_agent", state="pending",
            config={"agent": "cadastral_analyst"},
        ),
        NodeStep(
            id="parecer", label="Parecer", node_type="specialist_agent", state="pending",
            config={"agent": "opinion_writer"},
        ),
        NodeStep(id="check_final", label="Homologação", node_type="human_review", state="pending"),
        NodeStep(id="saida", label="Saída", node_type="output_generator", state="pending"),
    ]


def test_fusion_and_labels() -> None:
    d = build_dossier_descriptor("DC-2026-0001", _flow())
    labels = [s.label for s in d.stations]
    # output_generator é trilha (não vira estação). A estação ancora no nó de
    # COLETA: cadastral_enrichment (dados_basicos) vem antes do document_request,
    # então "Cadastral" precede "Faturamento". revenue_analyst funde e batiza
    # "Faturamento"; cadastral_analyst → "Cadastral"; opinion_writer +
    # check_final → "Parecer". (Fiel ao buildEstacoes do frontend.)
    assert labels == ["Identificação", "Cadastral", "Faturamento", "Parecer"]

    faturamento = next(s for s in d.stations if s.label == "Faturamento")
    # estação aguardando homologação do agente
    assert faturamento.state == "homologar"
    # seção do agente montada (revenue concluído)
    assert len(faturamento.sections) == 1
    assert faturamento.sections[0].station_id == "faturamento"
    assert faturamento.sections[0].blocks[0].type == "conclusao_agente"


def test_recommended_next_is_first_open() -> None:
    d = build_dossier_descriptor("DC-2026-0001", _flow())
    rec = [s for s in d.stations if s.is_recommended_next]
    assert len(rec) == 1
    # Bússola interim = 1ª estação não-fechada na ordem (espelha pickFocusEstacao).
    # Identificação fechou; Cadastral (dados_basicos ok, análise pendente) é a 1ª
    # aberta. A versão dep-based fina vem com as edges declaradas no grafo.
    assert rec[0].label == "Cadastral"


def test_dependencies_are_linear() -> None:
    d = build_dossier_descriptor("DC-2026-0001", _flow())
    assert d.stations[0].depends_on == []
    for prev, cur in zip(d.stations, d.stations[1:], strict=False):
        assert cur.depends_on == [prev.id]


def test_analyst_fuses_by_document_not_agent_name() -> None:
    """Decoupling (Fatia 2a): um analista que segue um document_request(revenue_report)
    funde na estação do documento MESMO sem afinidade nomeada (ex.: financial_analyst).
    A estação herda o aspecto "Faturamento" do tipo de documento, não do agente.
    Espelha a BLB (DC-2026-0043), onde o nó foi fiado a financial_analyst.
    """
    steps = [
        NodeStep(id="ident", label="Identificação", node_type="human_input", state="completed"),
        NodeStep(
            id="coleta", label="Documento", node_type="document_request", state="completed",
            config={"required": ["revenue_report"]},
        ),
        NodeStep(id="extrai", label="Extração", node_type="document_extractor", state="completed"),
        NodeStep(
            id="analise", label="Análise", node_type="specialist_agent", state="completed",
            config={"agent": "financial_analyst"}, output={"summary": "ok"},
        ),
        NodeStep(
            id="parecer", label="Parecer", node_type="specialist_agent", state="pending",
            config={"agent": "opinion_writer"},
        ),
    ]
    d = build_dossier_descriptor("DC-2026-0043", steps)
    labels = [s.label for s in d.stations]
    assert labels == ["Identificação", "Faturamento", "Parecer"]
    fat = next(s for s in d.stations if s.label == "Faturamento")
    # documento + extração + analista (sem afinidade nomeada) na MESMA estação
    assert fat.member_node_ids == ["coleta", "extrai", "analise"]
    # opinion_writer nunca funde na fonte
    parecer = next(s for s in d.stations if s.label == "Parecer")
    assert parecer.member_node_ids == ["parecer"]


def test_trilha_nodes_excluded() -> None:
    steps = [
        NodeStep(id="trig", label="t", node_type="trigger", state="completed"),
        NodeStep(id="hi", label="Identificação", node_type="human_input", state="completed"),
        NodeStep(id="out", label="o", node_type="output_generator", state="pending"),
    ]
    d = build_dossier_descriptor("DC-2026-0002", steps)
    assert [s.id for s in d.stations] == ["hi"]


def test_serializes_camelcase_for_frontend() -> None:
    """O endpoint serializa by_alias (FastAPI default) → camelCase, alinhado aos
    tipos TS. Trava o gotcha #1 do auto-review (snake x camel no wiring)."""
    d = build_dossier_descriptor("DC-2026-0001", _flow())
    dumped = d.model_dump(by_alias=True)
    st = dumped["stations"][0]
    assert "dependsOn" in st and "depends_on" not in st
    assert "isRecommendedNext" in st
    # seção camelCase
    fat = next(s for s in dumped["stations"] if s["label"] == "Faturamento")
    sec = fat["sections"][0]
    assert "stationId" in sec and "generatesDossierSection" in sec
    # construção por nome snake ainda funciona (populate_by_name)
    assert d.stations[0].depends_on == []
