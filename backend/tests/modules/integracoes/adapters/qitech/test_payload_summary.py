"""payload_summary -- sumario semantico do payload QiTech para tooltip.

Fixtures espelham raws reais observados em 2026-05-19 (caso motivador):
- MEC com Subordinada `patrimonio=0, variacaoDiaria=-100` (snapshot
  intermediario publicado pela QiTech).
- Tesouraria com 2 carteiras (faltou Sub) em vez das 3 normais.

Heuristica nao escala completeness (decisao 2026-05-20). Sentinela so
sinaliza visualmente via `suspicious=True` no item correspondente.
"""

from __future__ import annotations

from decimal import Decimal

from app.modules.integracoes.adapters.admin.qitech.payload_summary import (
    ItemSummary,
    PayloadSummary,
    summarize_payload,
)

# ── MEC ────────────────────────────────────────────────────────────────────


def test_mec_complete_3_carteiras_normais():
    """Snapshot saudavel: Sub, Mez e Sen com patrimonio > 0 e Δ pequeno."""
    payload = {
        "relatórios": {
            "mec": [
                {
                    "clienteId": "REALINVEST",
                    "clienteNome": "REALINVEST FIDC",
                    "patrimonio": 11900016.85,
                    "variaçãoDiaria": 0.2187,
                },
                {
                    "clienteId": "REALINVEST MEZ",
                    "clienteNome": "REALINVEST FIDC MEZANINO 1",
                    "patrimonio": 2549329.65,
                    "variaçãoDiaria": 0.0765,
                },
                {
                    "clienteId": "REALINVEST SEN",
                    "clienteNome": "REALINVEST FIDC SENIOR 1",
                    "patrimonio": 12493117.70,
                    "variaçãoDiaria": 0.0709,
                },
            ]
        }
    }
    s = summarize_payload(
        tipo_de_mercado="mec",
        payload=payload,
        ua_nome="REALINVEST FIDC",
        http_status=200,
    )
    assert s is not None
    assert s.total_items == 3
    assert s.expected_items == 3
    assert s.suspicious_count == 0
    # Ordenacao por valor desc — Senior primeiro (12,5M)
    assert s.items[0].name == "REALINVEST FIDC SENIOR 1 (Sen)"
    assert s.items[0].value == Decimal("12493117.70")
    # Todos nao-suspicious
    assert all(not it.suspicious for it in s.items)


def test_mec_sub_zerada_2026_05_19_marca_suspicious():
    """Caso real 2026-05-19: Sub veio com patrimonio=0 e variacaoDiaria=-100.
    Heuristica detecta e marca como suspicious (sem mudar completeness)."""
    payload = {
        "relatórios": {
            "mec": [
                {
                    "clienteId": "REALINVEST SEN",
                    "clienteNome": "REALINVEST FIDC SENIOR 1",
                    "patrimonio": 12510833.53,
                    "variaçãoDiaria": 0.0709,
                },
                {
                    "clienteId": "REALINVEST",
                    "clienteNome": "REALINVEST FIDC",
                    "patrimonio": 0,
                    "variaçãoDiaria": -100,
                },
                {
                    "clienteId": "REALINVEST MEZ",
                    "clienteNome": "REALINVEST FIDC MEZANINO 1",
                    "patrimonio": 2553233.51,
                    "variaçãoDiaria": 0.0765,
                },
            ]
        }
    }
    s = summarize_payload(
        tipo_de_mercado="mec",
        payload=payload,
        ua_nome="REALINVEST FIDC",
        http_status=200,
    )
    assert s is not None
    assert s.total_items == 3
    assert s.expected_items == 3
    assert s.suspicious_count == 1
    # Identifica qual item esta suspicious
    sub_item = next(it for it in s.items if "(Sub)" in it.name)
    assert sub_item.value == Decimal("0")
    assert sub_item.delta_pct == Decimal("-100")
    assert sub_item.suspicious is True
    assert sub_item.suspicious_reason is not None
    assert "publicacao parcial" in sub_item.suspicious_reason.lower()


def test_mec_array_vazio():
    payload = {"relatórios": {"mec": []}}
    s = summarize_payload(
        tipo_de_mercado="mec",
        payload=payload,
        ua_nome="REALINVEST FIDC",
        http_status=200,
    )
    assert s is not None
    assert s.total_items == 0
    assert s.suspicious_count == 0


def test_mec_payload_corrompido():
    s = summarize_payload(
        tipo_de_mercado="mec",
        payload=None,
        ua_nome="REALINVEST FIDC",
        http_status=200,
    )
    assert s is not None
    assert s.total_items == 0


# ── Tesouraria ─────────────────────────────────────────────────────────────


def test_tesouraria_3_carteiras_normal():
    payload = {
        "relatórios": {
            "tesouraria": [
                {
                    "clienteId": "REALINVEST",
                    "clienteNome": "REALINVEST FIDC",
                    "valor": 927.64,
                    "descrição": "Saldo em Tesouraria",
                },
                {
                    "clienteId": "REALINVEST MEZ",
                    "clienteNome": "REALINVEST FIDC MEZANINO 1",
                    "valor": 0,
                    "descrição": "Saldo em Tesouraria",
                },
                {
                    "clienteId": "REALINVEST SEN",
                    "clienteNome": "REALINVEST FIDC SENIOR 1",
                    "valor": 0,
                    "descrição": "Saldo em Tesouraria",
                },
            ]
        }
    }
    s = summarize_payload(
        tipo_de_mercado="tesouraria",
        payload=payload,
        ua_nome="REALINVEST FIDC",
        http_status=200,
    )
    assert s is not None
    assert s.total_items == 3
    assert s.suspicious_count == 0
    # Sub veio com label enriquecida
    assert any("(Sub)" in it.name for it in s.items)
    assert any("(Mez)" in it.name for it in s.items)
    assert any("(Sen)" in it.name for it in s.items)


def test_tesouraria_sub_ausente_2026_05_19():
    """Caso real 2026-05-19: payload veio com apenas 2 carteiras (Mez + Sen).
    Falta a Sub — pseudo-item de aviso aparece como suspicious."""
    payload = {
        "relatórios": {
            "tesouraria": [
                {
                    "clienteId": "REALINVEST MEZ",
                    "clienteNome": "REALINVEST FIDC MEZANINO 1",
                    "valor": 0,
                },
                {
                    "clienteId": "REALINVEST SEN",
                    "clienteNome": "REALINVEST FIDC SENIOR 1",
                    "valor": 0,
                },
            ]
        }
    }
    s = summarize_payload(
        tipo_de_mercado="tesouraria",
        payload=payload,
        ua_nome="REALINVEST FIDC",
        http_status=200,
    )
    assert s is not None
    # total_items conta o array real, nao o pseudo-item.
    assert s.total_items == 2
    assert s.expected_items == 3
    assert s.suspicious_count == 1
    sub = next(it for it in s.items if it.suspicious)
    assert sub.suspicious_reason is not None
    assert "subordinada ausente" in sub.suspicious_reason.lower()


# ── RF ─────────────────────────────────────────────────────────────────────


def test_rf_com_principal():
    payload = {
        "relatórios": {
            "rf": [
                {
                    "clienteId": "REALINVEST",
                    "nomeDoPapel": "LFT 23/03/2027",
                    "valorBruto": 1000000.50,
                },
                {
                    "clienteId": "REALINVEST",
                    "nomeDoPapel": "NTNB 15/05/2030",
                    "valorBruto": 500000.00,
                },
            ]
        }
    }
    s = summarize_payload(
        tipo_de_mercado="rf",
        payload=payload,
        ua_nome="REALINVEST FIDC",
        http_status=200,
    )
    assert s is not None
    assert s.total_items == 2
    assert s.suspicious_count == 0


def test_rf_sem_principal_marca_suspicious():
    """Caso 2026-04-30 / 12-05: RF chega sem clienteId casando com principal."""
    payload = {
        "relatórios": {
            "rf": [
                {
                    "clienteId": "OUTRO_FUNDO",
                    "nomeDoPapel": "LFT 23/03/2027",
                    "valorBruto": 1000000.50,
                },
            ]
        }
    }
    s = summarize_payload(
        tipo_de_mercado="rf",
        payload=payload,
        ua_nome="REALINVEST FIDC",
        http_status=200,
    )
    assert s is not None
    assert s.suspicious_count == 1
    susp = next(it for it in s.items if it.suspicious)
    assert susp.suspicious_reason is not None
    assert "fundo principal" in susp.suspicious_reason.lower()


# ── HTTP != 200 ────────────────────────────────────────────────────────────


def test_http_4xx_devolve_none():
    s = summarize_payload(
        tipo_de_mercado="mec",
        payload={},
        ua_nome="REALINVEST FIDC",
        http_status=404,
    )
    assert s is None


# ── CSV report (fidc-estoque) ─────────────────────────────────────────────


def test_csv_report_complete():
    payload = {
        "qitech_job_id": "a1b2c3d4-1234-5678-9012-abcdef012345",
        "bytes": 1148660,
        "rows_estimate": 2888,
        "format": "csv",
    }
    s = summarize_payload(
        tipo_de_mercado="fidc-estoque",
        payload=payload,
        ua_nome=None,
        http_status=200,
    )
    assert s is not None
    assert s.total_items == 2888
    # Itens informativos: bytes + job_id (so o que tem valor entra)
    bytes_item = next(it for it in s.items if "bytes" in it.name.lower())
    assert bytes_item.value == Decimal(1148660)


def test_csv_report_empty():
    payload = {
        "qitech_job_id": "a1b2c3d4-1234-5678-9012-abcdef012345",
        "bytes": 0,
        "rows_estimate": 0,
    }
    s = summarize_payload(
        tipo_de_mercado="fidc-estoque",
        payload=payload,
        ua_nome=None,
        http_status=200,
    )
    assert s is not None
    assert s.total_items == 0


# ── Default permissivo ─────────────────────────────────────────────────────


def test_default_summarize_conta_corrente_sem_perfil_dedicado():
    """conta-corrente tem summarizer dedicado — basta contar items."""
    payload = {
        "relatórios": {
            "conta-corrente": [
                {
                    "descrição": "CC - BRADESCO",
                    "valorTotal": 453624.70,
                },
                {
                    "descrição": "CREDITOS A CONCILIAR",
                    "valorTotal": -514991.21,
                },
            ]
        }
    }
    s = summarize_payload(
        tipo_de_mercado="conta-corrente",
        payload=payload,
        ua_nome="REALINVEST FIDC",
        http_status=200,
    )
    assert s is not None
    assert s.total_items == 2
    # Ordena por |valor| desc — "CREDITOS A CONCILIAR" (514k) vem antes
    # de "CC - BRADESCO" (453k).
    assert s.items[0].name == "CREDITOS A CONCILIAR"


# ── Truncamento (top N) ────────────────────────────────────────────────────


def test_truncate_top_10():
    """Quando array passa de 10 items, summary trunca pra 10 mas mantem total."""
    items_raw = [
        {
            "clienteId": "X",
            "nomeDoPapel": f"PAPEL {i}",
            "valorBruto": (15 - i) * 1000,
        }
        for i in range(15)
    ]
    # Adiciona o principal pra nao acionar sentinela
    items_raw.append(
        {"clienteId": "REALINVEST", "nomeDoPapel": "MAIN", "valorBruto": 1000000}
    )
    payload = {"relatórios": {"rf": items_raw}}
    s = summarize_payload(
        tipo_de_mercado="rf",
        payload=payload,
        ua_nome="REALINVEST FIDC",
        http_status=200,
    )
    assert s is not None
    assert s.total_items == 16
    assert len(s.items) == 10
    # MAIN (1M) tem que estar no topo
    assert s.items[0].name == "MAIN"


# ── Imutabilidade ──────────────────────────────────────────────────────────


def test_summary_e_dataclass_frozen():
    """PayloadSummary e ItemSummary sao frozen — protege contra mutacao
    acidental durante serializacao."""
    item = ItemSummary(
        name="x",
        value=Decimal(1),
        delta_pct=None,
        suspicious=False,
        suspicious_reason=None,
    )
    summary = PayloadSummary(
        total_items=1,
        expected_items=None,
        suspicious_count=0,
        items=[item],
    )
    import dataclasses

    try:
        dataclasses.replace(item, name="y")  # ok — produz nova instance
    except dataclasses.FrozenInstanceError:
        msg = "replace nao deveria falhar"
        raise AssertionError(msg) from None
    # Mas tentar setar atributo direto falha:
    import pytest as _pytest

    with _pytest.raises(dataclasses.FrozenInstanceError):
        item.name = "y"  # type: ignore[misc]
    with _pytest.raises(dataclasses.FrozenInstanceError):
        summary.total_items = 9  # type: ignore[misc]
