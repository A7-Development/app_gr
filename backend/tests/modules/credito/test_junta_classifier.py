"""Classificador de documento societário JUCESP (Infosimples) — Fatia 1 do
seletor de contrato social. Fixtures = dados REAIS da blb (DC-2026-0043).

pytest tests/modules/credito/test_junta_classifier.py --noconftest
"""

from __future__ import annotations

from app.modules.credito.services.junta import (
    _pick_latest_societario,
    _searchable_text,
)

# Lista REAL de arquivamentos da "blb" (campo `texto` da consulta completa),
# encurtado mantendo as palavras-chave que classificam o ato.
_BLB = [
    {"numdoc": "850.310/18-0", "sessao": "03/01/2018", "texto": "ARQUIVAMENTO DE PROCURAÇÃO PÚBLICA."},
    {"numdoc": "415.509/20-8", "sessao": "04/11/2020", "texto": "ALTERAÇÃO DA ATIVIDADE. CONSOLIDAÇÃO CONTRATUAL DA MATRIZ."},
    {"numdoc": "1.074.745/26-7", "sessao": "07/02/2026", "texto": "ARQUIVAMENTO DE A.R.Q. DISTRIBUICAO DOS LUCROS."},
    {"numdoc": "1.043.907/25-7", "sessao": "14/02/2025", "texto": "ARQUIVAMENTO DE A.R.D. EMISSAO DE NOTAS COMERCIAIS."},
    {"numdoc": "827.633/15-4", "sessao": "18/11/2015", "texto": "DECLARAÇÃO DE ENQUADRAMENTO DE EPP."},
    {"numdoc": "417.748/24-3", "sessao": "19/12/2024", "texto": "ENCERRAMENTO DA FILIAL. CONSOLIDAÇÃO CONTRATUAL DA MATRIZ."},
    {"numdoc": "869.714/16-8", "sessao": "23/08/2016", "texto": "ARQUIVAMENTO DE PROCURAÇÃO PÚBLICA."},
    {"numdoc": "464.674/16-5", "sessao": "28/11/2016", "texto": "ABERTURA DE FILIAL. ALTERAÇÃO DA ATIVIDADE. CONSOLIDAÇÃO CONTRATUAL DA MATRIZ."},
]


def test_searchable_text_le_o_campo_texto() -> None:
    # antes lia só descricao/tipo (null) → vazio. Agora lê `texto`.
    doc = {"numdoc": "1", "texto": "CONSOLIDAÇÃO CONTRATUAL", "descricao": None, "tipo": None}
    assert "CONSOLIDA" in _searchable_text(doc).upper()


def test_blb_sugere_consolidacao_mais_recente() -> None:
    # blb tem 3 docs com CONSOLIDAÇÃO (2016, 2020, 2024). A mais recente (2024)
    # é a sugerida — é o contrato consolidado vigente (carregado no filing de
    # encerramento). O analista vê a lista (B) e pode preferir a de 2020.
    picked = _pick_latest_societario(_BLB)
    assert picked is not None
    assert picked["numdoc"] == "417.748/24-3"


def test_sem_ato_constitutivo_retorna_none() -> None:
    # Empresa só com procuração/encerramento/EPP/deliberação → None → found=false
    # → o fluxo pede pro analista anexar (era o que falhava: fallback pegava qualquer).
    so_outros = [d for d in _BLB if "CONSOLIDA" not in d["texto"].upper() and "ALTERA" not in d["texto"].upper()]
    assert _pick_latest_societario(so_outros) is None


def test_prefere_consolidacao_sobre_alteracao_simples() -> None:
    docs = [
        {"numdoc": "10", "sessao": "01/01/2024", "texto": "ALTERAÇÃO DE CONTRATO SOCIAL."},
        {"numdoc": "20", "sessao": "01/01/2020", "texto": "CONSOLIDAÇÃO CONTRATUAL."},
    ]
    # consolidação (2020) preferida mesmo sendo mais antiga que a alteração (2024).
    assert _pick_latest_societario(docs)["numdoc"] == "20"


def test_constituicao_pura_e_pega() -> None:
    docs = [{"numdoc": "5", "sessao": "10/05/2019", "texto": "CONSTITUIÇÃO DE SOCIEDADE LIMITADA."}]
    assert _pick_latest_societario(docs)["numdoc"] == "5"


def test_lista_vazia_none() -> None:
    assert _pick_latest_societario([]) is None
