"""Unit tests for the section descriptor builders (A1 home, Phase 1/Etapa 4).

Pure functions — no DB, no conftest fixtures needed. Run with:
    pytest tests/agentic/test_section_builders.py --noconftest
"""

from __future__ import annotations

from app.agentic.engine.output_schemas import (
    CadastralAnalysis,
    CheckItem,
    CredibilidadeDocumento,
    PontoAtencaoCadastral,
    PontoAtencaoFaturamento,
    QualidadeFaturamento,
    RevenueAnalysis,
    SazonalidadeFaturamento,
    SocialContractAnalysis,
    TendenciaFaturamento,
)
from app.agentic.playbooks.schemas.section_builders import (
    cadastral_to_section,
    revenue_to_section,
    social_contract_to_section,
)
from app.agentic.playbooks.schemas.section_descriptor import (
    ApontamentosBlock,
    ConclusaoAgenteBlock,
    FichaBlock,
    TextoBlock,
)


def _block_types(section) -> list[str]:
    return [b.type for b in section.blocks]


def test_revenue_builds_expected_blocks() -> None:
    output = RevenueAnalysis(
        resumo_executivo="Faturamento crescente e consistente.",
        tendencia=TendenciaFaturamento(direcao="crescente", intensidade="forte", leitura="Sobe."),
        sazonalidade=SazonalidadeFaturamento(detectada=True, confiavel=False, padrao="varejo"),
        pontos_de_atencao=[
            PontoAtencaoFaturamento(
                mes="2025-12",
                tipo="pico",
                esperado_ou_anomalo="esperado",
                severidade="baixa",
                observacao="Pico de dezembro típico.",
            )
        ],
        qualidade_do_dado=QualidadeFaturamento(
            soma_confere=True, n_meses=12, meses_faltantes=[], observacao="Completo."
        ),
        credibilidade_documento=CredibilidadeDocumento(
            assinado=True, nivel="alto", leitura="Assinado por contador.", ressalvas=["sem ECD"]
        ),
        leitura_para_credito="Capacidade estável.",
    )

    section = revenue_to_section(output)

    assert section.station_id == "faturamento"
    assert section.generates_dossier_section is True
    # conclusão + ficha + pontos + ressalvas + texto
    assert _block_types(section) == [
        "conclusao_agente",
        "ficha",
        "apontamentos",
        "apontamentos",
        "texto",
    ]
    conclusao = section.blocks[0]
    assert isinstance(conclusao, ConclusaoAgenteBlock)
    assert conclusao.homologado is False
    ficha = section.blocks[1]
    assert isinstance(ficha, FichaBlock)
    # sazonalidade não confiável -> badge "leitura fraca"
    sazon = next(c for c in ficha.campos if c.label == "Sazonalidade")
    assert sazon.badge is not None and sazon.badge.texto == "leitura fraca"
    # texto final = leitura para crédito
    assert isinstance(section.blocks[-1], TextoBlock)


def test_revenue_clean_series_has_no_apontamentos() -> None:
    output = RevenueAnalysis(
        resumo_executivo="ok",
        tendencia=TendenciaFaturamento(direcao="estavel", intensidade="leve", leitura="x"),
        sazonalidade=SazonalidadeFaturamento(detectada=False, confiavel=True, padrao=None),
        pontos_de_atencao=[],
        qualidade_do_dado=QualidadeFaturamento(
            soma_confere=True, n_meses=24, meses_faltantes=[], observacao="ok"
        ),
        credibilidade_documento=CredibilidadeDocumento(
            assinado=True, nivel="medio", leitura="x", ressalvas=[]
        ),
        leitura_para_credito="ok",
    )
    section = revenue_to_section(output)
    assert "apontamentos" not in _block_types(section)


def test_cadastral_maps_situacao_badge() -> None:
    output = CadastralAnalysis(
        resumo_executivo="Empresa ativa há 12 anos.",
        situacao_cadastral="ativa",
        tempo_atividade_leitura="12 anos.",
        aderencia_atividade="CNAE compatível.",
        porte_capital_leitura="Capital coerente.",
        pontos_de_atencao=[
            PontoAtencaoCadastral(tipo="capital", severidade="media", observacao="x")
        ],
        leitura_para_credito="Saudável.",
    )
    section = cadastral_to_section(output)
    assert section.station_id == "cadastral"
    ficha = section.blocks[1]
    assert isinstance(ficha, FichaBlock)
    sit = ficha.campos[0]
    assert sit.badge is not None and sit.badge.tom == "ok"
    # severidade "media" -> "atencao"
    pontos = next(b for b in section.blocks if isinstance(b, ApontamentosBlock))
    assert pontos.itens[0].severidade == "atencao"


def test_social_contract_blocks_and_checklist_severity() -> None:
    output = SocialContractAnalysis(
        summary="Estrutura simples.",
        qsa_changes_recent=False,
        qsa_changes_detail=None,
        signing_powers={"João": "isolada"},
        object_compatible_with_operation=True,
        object_compatibility_rationale="Compatível.",
        capital_social={},
        statutory_restrictions=["Cessão de quotas vedada."],
        checklist_results=[
            CheckItem(
                code="SOC.001",
                description="QSA",
                status="critical",
                rationale="divergência",
                confidence=0.9,
            )
        ],
        red_flags=[],
    )
    section = social_contract_to_section(output)
    assert section.station_id == "contrato-social"
    # conclusão + ficha leituras + ficha poderes + texto restrições + checklist
    assert _block_types(section) == [
        "conclusao_agente",
        "ficha",
        "ficha",
        "texto",
        "apontamentos",
    ]
    checklist = section.blocks[-1]
    assert isinstance(checklist, ApontamentosBlock)
    assert checklist.itens[0].severidade == "critico"
