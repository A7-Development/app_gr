"""Unit tests for deterministic producers (Passo 2-A). Pure — no DB.

pytest tests/agentic/test_deterministic_producers.py --noconftest
"""

from __future__ import annotations

from app.agentic.workflows.schemas.deterministic_producers import (
    cadastral_card_to_section,
    faturamento_to_section,
    societario_to_section,
)
from app.agentic.workflows.schemas.section_descriptor import (
    ApontamentosBlock,
    FichaBlock,
    TabelaBlock,
)


def _card() -> dict:
    return {
        "encontrado": True,
        "enriquecido": True,
        "cnpj": "02379828000128",
        "campos": [
            {"field_path": "razao_social", "label": "Razão social", "valor": "ACTION LINE LTDA", "novo": False},
            {"field_path": "situacao", "label": "Situação", "valor": "ATIVA", "novo": False},
            {"field_path": "cnaes", "label": "CNAEs", "valor": ["8220200", "8211300"], "novo": False},
            {"field_path": "mei", "label": "MEI", "valor": False, "novo": True},
            {"field_path": "vazio", "label": "Vazio", "valor": None, "novo": False},
        ],
    }


def test_cadastral_card_builds_ficha() -> None:
    sec = cadastral_card_to_section(_card(), station_id="dados_basicos")
    assert sec is not None
    assert sec.station_id == "dados_basicos"
    assert sec.id == "det-dados_basicos"
    assert len(sec.blocks) == 1
    ficha = sec.blocks[0]
    assert isinstance(ficha, FichaBlock)
    # campo None é pulado -> 4 de 5
    assert len(ficha.campos) == 4
    labels = [c.label for c in ficha.campos]
    assert "Razão social" in labels and "Vazio" not in labels
    # lista coerida + bool coerido
    cnaes = next(c for c in ficha.campos if c.label == "CNAEs")
    assert cnaes.valor == "8220200, 8211300"
    mei = next(c for c in ficha.campos if c.label == "MEI")
    assert mei.valor == "Não"
    # proveniencia = fonte externa
    assert ficha.provenance is not None and ficha.provenance.origin == "fonte"


def test_cadastral_not_found_returns_none() -> None:
    assert cadastral_card_to_section({"encontrado": False}, "x") is None
    assert cadastral_card_to_section({}, "x") is None
    # só campos vazios -> None
    assert cadastral_card_to_section(
        {"encontrado": True, "campos": [{"label": "X", "valor": None}]}, "x"
    ) is None


def _societario() -> dict:
    return {
        "encontrado": True,
        "homologado": True,
        "contrato": {
            "capital_social": 250000.0,
            "data_constituicao": "1998-02-27",
            "socios": [
                {"nome": "João Silva", "cpf_ultimos4": "1234", "participacao_pct": 60.0},
                {"nome": "Maria Souza", "cpf_ultimos4": "5678", "participacao_pct": 40.0},
            ],
        },
        "estrutura": {
            "n_socios": 2,
            "idade_empresa_anos": 28,
            "controlador": {"nome": "João Silva", "participacao_pct": 60.0, "controle_majoritario": True},
        },
        "cruzamentos": [
            {"campo": "razao_social", "contrato": "A LTDA", "oficial": "A LTDA", "confere": True, "detalhe": "ok"},
            {"campo": "cnpj", "contrato": "111", "oficial": "222", "confere": False, "detalhe": "CNPJ diverge"},
        ],
    }


def test_societario_builds_ficha_tabela_apontamentos() -> None:
    sec = societario_to_section(_societario(), station_id="doc_node")
    assert sec is not None and sec.station_id == "doc_node"
    types = [b.type for b in sec.blocks]
    assert types == ["ficha", "tabela", "apontamentos"]
    ficha = sec.blocks[0]
    assert isinstance(ficha, FichaBlock)
    cap = next(c for c in ficha.campos if c.label == "Capital social")
    assert cap.valor == "R$ 250.000,00"
    tabela = sec.blocks[1]
    assert isinstance(tabela, TabelaBlock)
    assert len(tabela.linhas) == 2
    # CPF redactado
    assert tabela.linhas[0]["cpf"].valor == "***.***.***-34"
    # só o cruzamento que NÃO confere vira apontamento
    apont = sec.blocks[2]
    assert isinstance(apont, ApontamentosBlock)
    assert len(apont.itens) == 1 and "CNPJ diverge" in apont.itens[0].titulo


def test_societario_not_found_none() -> None:
    assert societario_to_section({"encontrado": False}, "x") is None


def _faturamento() -> dict:
    return {
        "encontrado": True,
        "analytics": {
            "agregados": {"total": 1200000.0, "media": 100000.0, "n_meses": 12},
            "serie": [
                {"mes": "2025-11", "receita_bruta": 110000.0},
                {"mes": "2025-12", "receita_bruta": 162000.0},
            ],
            "tendencia": {"direcao": "crescente", "variacao_periodo_pct": 15.9},
            "qualidade": {"soma_confere": True},
        },
        "atestacao": {"assinado": True},
    }


def test_faturamento_builds_ficha_e_serie() -> None:
    sec = faturamento_to_section(_faturamento(), station_id="fat_node")
    assert sec is not None
    types = [b.type for b in sec.blocks]
    assert types == ["ficha", "tabela"]
    ficha = sec.blocks[0]
    assert isinstance(ficha, FichaBlock)
    total = next(c for c in ficha.campos if c.label == "Total")
    assert total.valor == "R$ 1.200.000,00"
    serie = sec.blocks[1]
    assert isinstance(serie, TabelaBlock)
    assert len(serie.linhas) == 2
    assert serie.colunas[1].formato == "brl"


def test_faturamento_not_found_none() -> None:
    assert faturamento_to_section({"encontrado": False}, "x") is None
