"""Rating de integridade de liquidacao — matematica pura + guarda da API.

Contratos sob teste (formula v1, 2026-07-11):
    - deducoes por severidade do catalogo; critico NAO deduz, TRAVA (teto);
    - lente praca indistinguivel: PRC-02/03 so com cidades divergentes;
    - portao de confianca assimetrico: nota boa exige n/cobertura, nota
      ruim vale com qualquer n;
    - endpoint exige RISCO/READ (403 sem permissao — §10.4).
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.modules.risco.services.deteccao_parametros import DEFAULTS
from app.modules.risco.services.rating_liquidacao import (
    _aplicar_portao,
    _grade,
    score_evento,
)

pytestmark = pytest.mark.asyncio

P = DEFAULTS  # formula v1 usa os defaults como parametros


def test_evento_limpo_score_100() -> None:
    score, critico, acesos = score_evento({}, regra_dura=False, params=P)
    assert (score, critico, acesos) == (100.0, False, [])


def test_prc01_e_critico_nao_deduz_trava() -> None:
    score, critico, acesos = score_evento(
        {"match_agencia_conta_cedente": 1.0, "cidade_pgto_neq_sacado": 1.0},
        regra_dura=False,
        params=P,
    )
    assert critico is True
    assert "PRC-01" in acesos
    # nao deduz pelo PRC-01 (critico trava no consolidado); PRC-03 acende junto
    assert score == 100.0 - 5.0


def test_prc01_mesma_cidade_nao_acende() -> None:
    """Cidade pequena: sacado local paga na unica agencia da praca, que por
    acaso e a do cedente — sem poder discriminante (Ricardo 2026-07-11;
    Fricock 107/107 mesma cidade)."""
    _, critico, acesos = score_evento(
        {"match_agencia_conta_cedente": 1.0, "cidade_pgto_neq_sacado": 0.0},
        regra_dura=False,
        params=P,
    )
    assert critico is False
    assert "PRC-01" not in acesos


def test_regra_dura_sem_match_conta_e_cnv90() -> None:
    _, critico, acesos = score_evento({}, regra_dura=True, params=P)
    assert critico is True
    assert acesos == ["CNV-90"]


def test_lente_praca_indistinguivel_desliga_prc02() -> None:
    # pago na cidade do cedente MAS sacado e da mesma cidade -> nao acende
    feats = {"cidade_pgto_eq_cedente": 1.0, "cidade_pgto_neq_sacado": 0.0}
    score, critico, acesos = score_evento(feats, regra_dura=False, params=P)
    assert acesos == []
    assert score == 100.0


def test_deducoes_alta_e_media_somam() -> None:
    # PRC-02 (alta 15) + PRC-03 (media 5) + FGP-01 (media 5) = -25
    feats = {
        "cidade_pgto_eq_cedente": 1.0,
        "cidade_pgto_neq_sacado": 1.0,
        "quebra_fingerprint": 0.7,
    }
    score, critico, acesos = score_evento(feats, regra_dura=False, params=P)
    assert critico is False
    assert set(acesos) == {"PRC-02", "PRC-03", "FGP-01"}
    assert score == 100.0 - 15.0 - 5.0 - 5.0


def test_mec01_acende_em_qualquer_produto() -> None:
    # golden case MFL era DMS (boleto permitido) — MEC-01 nao depende da lente
    score, _, acesos = score_evento({"baixa_confirmada": 1.0}, regra_dura=False, params=P)
    assert acesos == ["MEC-01"]
    assert score == 85.0


def test_grade_cortes() -> None:
    assert _grade(None, P) == "NC"
    assert _grade(90.0, P) == "A"
    assert _grade(72.0, P) == "B"
    assert _grade(55.0, P) == "C"
    assert _grade(35.0, P) == "D"
    assert _grade(10.0, P) == "E"


def test_portao_confianca_assimetrico() -> None:
    # nota boa sem base -> NC; nota ruim com base minima -> vale
    assert _aplicar_portao("A", n_eventos=3, cobertura=0.9, params=P) == "NC"
    assert _aplicar_portao("A", n_eventos=50, cobertura=0.2, params=P) == "NC"
    assert _aplicar_portao("A", n_eventos=50, cobertura=0.9, params=P) == "A"
    assert _aplicar_portao("E", n_eventos=1, cobertura=0.0, params=P) == "E"
    assert _aplicar_portao("C", n_eventos=1, cobertura=0.0, params=P) == "C"


async def test_endpoint_exige_autenticacao() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/risco/rating-liquidacao")
    assert resp.status_code in (401, 403)
