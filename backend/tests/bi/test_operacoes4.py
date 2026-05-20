"""Testes de operacoes4 (Mes Corrente · controladoria).

Foco em funcoes puras (sem DB):
  - _is_atypical              -- flag visual da composicao
  - _pick_movers              -- cresceu mais / caiu mais
  - _alocar_receita_por_cedente -- alocacao proporcional title x op
  - schemas                   -- shape do payload + soma share ~100%

Integracao tenant isolation vive em test_tenant_isolation.py (cobre todo
endpoint do BI por construcao — auth + escopo de tenant + require_module).
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.modules.bi.schemas.operacoes4 import (
    Operacoes4LensReceitasData,
    Operacoes4Mover,
    Operacoes4Movers,
    Operacoes4ReceitaComposicaoItem,
    Operacoes4ReceitaTipo,
    Operacoes4YieldPonto,
)
from app.modules.bi.services.operacoes import _alocar_receita_por_cedente
from app.modules.bi.services.operacoes4 import (
    _BUCKET_TO_ENUM,
    _BUCKETS_ORDER,
    _is_atypical,
    _pick_movers,
)

# ─── _is_atypical ──────────────────────────────────────────────────────────


def test_atypical_delta_alto_sempre_flag() -> None:
    """|delta| > 20% liga flag, independente do share."""
    assert _is_atypical(delta_pct=24.0, share_pct=0.5) is True
    assert _is_atypical(delta_pct=-25.0, share_pct=0.5) is True


def test_atypical_share_alto_com_delta_perceptivel() -> None:
    """share > 5% E |delta| > 10% (mesmo sem passar 20%) liga flag."""
    assert _is_atypical(delta_pct=12.0, share_pct=8.0) is True
    assert _is_atypical(delta_pct=-12.0, share_pct=8.0) is True


def test_atypical_movimento_pequeno_em_bucket_pequeno_nao_flag() -> None:
    """share baixo + delta moderado = ruido, sem flag."""
    assert _is_atypical(delta_pct=8.0, share_pct=2.0) is False


def test_atypical_sem_base_de_comparacao() -> None:
    """delta_pct=None (sem paridade) -> sem flag."""
    assert _is_atypical(delta_pct=None, share_pct=80.0) is False


# ─── _pick_movers ──────────────────────────────────────────────────────────


def _composicao_helper(
    deltas: dict[str, float | None],
    valores: dict[str, float] | None = None,
) -> dict[str, dict[str, object]]:
    """Builder das composicao_dict que `_pick_movers` espera."""
    valores = valores or dict.fromkeys(_BUCKETS_ORDER, 1000.0)
    out: dict[str, dict[str, object]] = {}
    for b in _BUCKETS_ORDER:
        out[b] = {
            "valor": valores.get(b, 1000.0),
            "parity": 0.0,
            "share_pct": 25.0,
            "delta_pct": deltas.get(b),
        }
    out["_total"] = {"valor": 4000.0, "parity": 0.0, "delta_pct": 0.0}
    return out


def test_movers_pega_maior_delta_positivo_e_mais_negativo() -> None:
    composicao = _composicao_helper(
        {
            "desagio": 5.0,
            "tarifa_cessao": 50.0,
            "tarifas_operacionais": -30.0,
            "outras": -2.0,
        }
    )
    movers = _pick_movers(composicao)
    assert movers.cresceu is not None
    assert movers.cresceu.tipo == Operacoes4ReceitaTipo.TARIFA_CESSAO
    assert movers.cresceu.delta_pct == 50.0
    assert movers.caiu is not None
    assert movers.caiu.tipo == Operacoes4ReceitaTipo.TARIFAS_OPERACIONAIS
    assert movers.caiu.delta_pct == -30.0


def test_movers_quando_nenhum_negativo_caiu_eh_none() -> None:
    composicao = _composicao_helper(
        {
            "desagio": 8.0,
            "tarifa_cessao": 12.0,
            "tarifas_operacionais": 4.0,
            "outras": 1.0,
        }
    )
    movers = _pick_movers(composicao)
    assert movers.cresceu is not None
    assert movers.cresceu.delta_pct == 12.0
    assert movers.caiu is None


def test_movers_ignora_bucket_sem_paridade() -> None:
    """delta_pct=None (sem base) nao entra na competicao."""
    composicao = _composicao_helper(
        {
            "desagio": None,
            "tarifa_cessao": 5.0,
            "tarifas_operacionais": None,
            "outras": -8.0,
        }
    )
    movers = _pick_movers(composicao)
    assert movers.cresceu is not None
    assert movers.cresceu.tipo == Operacoes4ReceitaTipo.TARIFA_CESSAO
    assert movers.caiu is not None
    assert movers.caiu.tipo == Operacoes4ReceitaTipo.OUTRAS


# ─── _alocar_receita_por_cedente ───────────────────────────────────────────


def test_aloca_proporcional_por_volume_dentro_da_op() -> None:
    """Op A: 2 cedentes, 60/40 do volume -> receita 60/40."""
    titulos = [
        {"op_id": "OP1", "cedente_nome": "Alpha", "valor_base": 600.0},
        {"op_id": "OP1", "cedente_nome": "Beta", "valor_base": 400.0},
    ]
    receita_e_vop = {"OP1": (100.0, 1000.0)}  # receita 100, vop 1000
    out = _alocar_receita_por_cedente(titulos, receita_e_vop)
    assert out["Alpha"] == (pytest.approx(60.0), pytest.approx(600.0))
    assert out["Beta"] == (pytest.approx(40.0), pytest.approx(400.0))


def test_aloca_acumula_entre_ops_do_mesmo_cedente() -> None:
    """2 ops do mesmo cedente -> receita e volume somam."""
    titulos = [
        {"op_id": "OP1", "cedente_nome": "Alpha", "valor_base": 600.0},
        {"op_id": "OP1", "cedente_nome": "Beta", "valor_base": 400.0},
        {"op_id": "OP2", "cedente_nome": "Alpha", "valor_base": 200.0},
    ]
    receita_e_vop = {
        "OP1": (100.0, 1000.0),
        "OP2": (10.0, 200.0),  # 100% pra Alpha
    }
    out = _alocar_receita_por_cedente(titulos, receita_e_vop)
    # Alpha: 60 (de OP1) + 10 (de OP2) = 70; volume 600 + 200 = 800
    assert out["Alpha"][0] == pytest.approx(70.0)
    assert out["Alpha"][1] == pytest.approx(800.0)
    assert out["Beta"][0] == pytest.approx(40.0)
    assert out["Beta"][1] == pytest.approx(400.0)


def test_aloca_op_sem_receita_no_mapa_nao_quebra() -> None:
    """Op listada em titulos mas ausente do mapa receita -> aloca 0."""
    titulos = [{"op_id": "OP_X", "cedente_nome": "Gama", "valor_base": 500.0}]
    out = _alocar_receita_por_cedente(titulos, {})
    assert out["Gama"] == (pytest.approx(0.0), pytest.approx(500.0))


def test_aloca_unico_cedente_recebe_toda_a_receita_da_op() -> None:
    """Op com 1 cedente -> 100% da receita_op vai pra ele.

    O denominador da alocacao e a SOMA dos `valor_base` dos titulos
    (nao o `vop` da op). Cobre o caso degenerado onde wh_operacao.vop=0
    mas a op tem titulos: a alocacao continua proporcional ao volume
    dos titulos, e o cedente unico fica com tudo.
    """
    titulos = [{"op_id": "OP1", "cedente_nome": "Delta", "valor_base": 100.0}]
    out = _alocar_receita_por_cedente(titulos, {"OP1": (50.0, 0.0)})
    assert out["Delta"][0] == pytest.approx(50.0)
    assert out["Delta"][1] == pytest.approx(100.0)


# ─── schemas (validacao basica) ────────────────────────────────────────────


def test_buckets_order_bate_com_enum() -> None:
    """_BUCKETS_ORDER cobre os 4 valores do enum, na ordem do enum."""
    assert tuple(t.value for t in Operacoes4ReceitaTipo) == _BUCKETS_ORDER
    for b in _BUCKETS_ORDER:
        assert b in _BUCKET_TO_ENUM


def test_lens_receitas_schema_aceita_composicao_4_buckets() -> None:
    """Schema valida payload completo (4 buckets + 1 yield ponto + 0 movers)."""
    data = Operacoes4LensReceitasData(
        total_mtd=Decimal("1000.00"),
        total_parity=Decimal("900.00"),
        delta_pct=11.11,
        composicao=[
            Operacoes4ReceitaComposicaoItem(
                tipo=t,
                valor=Decimal("250.00"),
                share_pct=25.0,
                delta_pct=10.0,
                flag_atypical=False,
            )
            for t in Operacoes4ReceitaTipo
        ],
        yield_du=[
            Operacoes4YieldPonto(
                du=1, yield_pct=2.1, yield_parity_pct=2.0, today=True
            )
        ],
        yield_wavg=2.1,
        yield_delta_pp=0.1,
        yield_parity_wavg=2.0,
        movers=Operacoes4Movers(
            cresceu=Operacoes4Mover(
                tipo=Operacoes4ReceitaTipo.DESAGIO,
                delta_pct=15.0,
                valor=Decimal("250.00"),
            ),
            caiu=None,
        ),
        mes_label="mai/26",
        du_decorridos=12,
        du_totais_mes=22,
        du_disponivel=True,
    )
    # Sanity checks de payload publico.
    assert len(data.composicao) == 4
    assert sum(c.share_pct for c in data.composicao) == pytest.approx(100.0)
    assert data.yield_du[0].today is True
    assert data.movers.cresceu is not None
    assert data.movers.caiu is None
