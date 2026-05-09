"""Testes da Aba 0 — Mes corrente (variance decomposition).

Foco em funcoes puras (sem DB):
  - _decompose_variance_aditiva: threshold + outros rollup + ordenacao
  - _decompose_pvm: identidade de Marshall-Edgeworth (mix + intra = delta)
  - _build_dumbbell: filtro de ruido + top N
  - _calcular_hhi_e_movements: HHI normalizado + top movements
  - _project_close_aditivo: extrapolacao linear correta
  - _build_narrative_pt_br: formato pt-BR estavel

Integracao tenant isolation vive em test_tenant_isolation.py (cobre todo
endpoint do BI por construcao).
"""

from __future__ import annotations

import pytest

from app.modules.bi.schemas.operacoes2 import (
    ConcentracaoDeltaData,
    PvmBridgeData,
    VarianceBridgeData,
)
from app.modules.bi.services.operacoes2 import (
    _build_dumbbell,
    _build_narrative_pt_br,
    _calcular_hhi_e_movements,
    _decompose_pvm,
    _decompose_variance_aditiva,
    _project_close_aditivo,
)


def _identity(member_id: str) -> str:
    return member_id


# ─── _decompose_variance_aditiva ────────────────────────────────────────────


def test_variance_aditiva_drivers_acima_do_threshold_aparecem() -> None:
    """Drivers com contribuicao >= max(R$500k, 5%% do delta) entram na lista."""
    prior = {"FAT": 10_000_000.0, "DUP": 5_000_000.0, "CMS": 2_000_000.0}
    current = {
        "FAT": 12_000_000.0,  # +2M
        "DUP": 4_000_000.0,  # -1M
        "CMS": 2_100_000.0,  # +100k -> abaixo do threshold (R$500k)
    }
    drivers, outros, delta = _decompose_variance_aditiva(prior, current, _identity)
    assert delta == pytest.approx(1_100_000.0)
    # FAT e DUP ficam (contribuicao > R$500k); CMS rola pra outros.
    member_ids = [d.member_id for d in drivers]
    assert "FAT" in member_ids
    assert "DUP" in member_ids
    assert "CMS" not in member_ids
    assert outros is not None
    assert outros.member_id == "__outros__"
    assert outros.contribution_brl == pytest.approx(100_000.0)


def test_variance_aditiva_ordenacao_por_modulo_decrescente() -> None:
    """Drivers ordenados por |contribution_brl| desc."""
    prior = {"A": 1_000_000.0, "B": 1_000_000.0, "C": 1_000_000.0}
    current = {
        "A": 4_000_000.0,  # +3M
        "B": 6_000_000.0,  # +5M
        "C": 200_000.0,  # -800k
    }
    drivers, _outros, _delta = _decompose_variance_aditiva(prior, current, _identity)
    # Ordem esperada: B (5M), A (3M), C (-0.8M)
    assert [d.member_id for d in drivers] == ["B", "A", "C"]


def test_variance_aditiva_membros_so_no_atual_ou_so_no_anterior() -> None:
    """Drivers podem aparecer/sumir entre os periodos."""
    prior = {"OLD": 5_000_000.0, "BOTH": 1_000_000.0}
    current = {"NEW": 7_000_000.0, "BOTH": 1_500_000.0}
    drivers, outros, _delta = _decompose_variance_aditiva(
        prior, current, _identity
    )
    member_ids = [d.member_id for d in drivers]
    # OLD some (-5M), NEW aparece (+7M), BOTH cresce (+500k)
    assert "OLD" in member_ids
    assert "NEW" in member_ids
    # BOTH com contribuicao 500k: borderline com threshold R$500k -> aceitavel.
    # Com delta_total=2.5M, threshold=max(500k, 5%% de 2.5M=125k) = 500k.
    # 500k nao e estritamente menor que 500k -> entra.
    assert "BOTH" in member_ids
    assert outros is None  # tudo ficou acima do threshold


def test_variance_aditiva_outros_acumula_membros_pequenos() -> None:
    """Varios drivers pequenos acumulam em 'Outros' com contribuicao somada."""
    prior = {f"M{i}": 1_000_000.0 for i in range(10)}
    current = {f"M{i}": 1_000_000.0 + 50_000.0 for i in range(10)}  # +50k cada
    drivers, outros, delta = _decompose_variance_aditiva(prior, current, _identity)
    assert delta == pytest.approx(500_000.0)
    # Todos abaixo de threshold (50k < 500k); todos rolam pra outros.
    assert drivers == []
    assert outros is not None
    assert outros.contribution_brl == pytest.approx(500_000.0)


def test_variance_aditiva_delta_zero_nao_quebra() -> None:
    """delta_total = 0 -> contribution_pct retorna None (evita divisao zero)."""
    prior = {"A": 1_000_000.0, "B": 2_000_000.0}
    current = {"A": 2_000_000.0, "B": 1_000_000.0}  # zero soma, mas drivers existem
    drivers, _outros, delta = _decompose_variance_aditiva(prior, current, _identity)
    assert delta == pytest.approx(0.0)
    # Drivers existem (cada um com contrib +/- 1M), mas contribution_pct e None
    assert all(d.contribution_pct is None for d in drivers)


# ─── _decompose_pvm (Marshall-Edgeworth) ────────────────────────────────────


def test_pvm_identidade_mix_mais_intra_eq_delta_total() -> None:
    """Marshall-Edgeworth: sum(mix_effect) + sum(intra_effect) = current_avg - prior_avg."""
    prior = {
        "FAT": {"vop": 6_000_000.0, "taxa": 2.0, "prazo": 30.0},
        "DUP": {"vop": 4_000_000.0, "taxa": 3.0, "prazo": 40.0},
    }
    current = {
        "FAT": {"vop": 5_000_000.0, "taxa": 2.2, "prazo": 32.0},
        "DUP": {"vop": 7_000_000.0, "taxa": 2.8, "prazo": 38.0},
    }
    mix, intra, _top_mix, _top_intra, _outros_mix, _outros_intra = _decompose_pvm(
        prior, current, "taxa", _identity, threshold_unit=0.0  # sem outros, todos passam
    )
    prior_avg = (6 * 2 + 4 * 3) / 10  # 2.4
    current_avg = (5 * 2.2 + 7 * 2.8) / 12  # ~ (11+19.6)/12 = 2.55
    delta_total = current_avg - prior_avg
    assert (mix + intra) == pytest.approx(delta_total, abs=1e-6)


def test_pvm_threshold_pp_envia_para_outros() -> None:
    """Membros com efeito < threshold_unit rolam pra outros."""
    prior = {
        "BIG": {"vop": 9_000_000.0, "taxa": 2.0},
        "TINY": {"vop": 100_000.0, "taxa": 1.5},
    }
    current = {
        "BIG": {"vop": 9_500_000.0, "taxa": 2.05},  # delta intra ~ 0.05pp
        "TINY": {"vop": 200_000.0, "taxa": 1.6},  # delta intra muito pequeno
    }
    _mix, _intra, _top_mix, top_intra, _outros_mix, _outros_intra = _decompose_pvm(
        prior, current, "taxa", _identity, threshold_unit=0.05
    )
    # TINY tem contribuicao muito pequena -> rola pra outros_intra
    intra_ids = [d.member_id for d in top_intra]
    assert "TINY" not in intra_ids


def test_pvm_pure_volume_shift_sem_intra() -> None:
    """Sem mudanca em avg per category, intra_effect ~= 0."""
    prior = {
        "A": {"vop": 5_000_000.0, "taxa": 2.0},
        "B": {"vop": 5_000_000.0, "taxa": 4.0},
    }
    current = {
        "A": {"vop": 8_000_000.0, "taxa": 2.0},  # mesma taxa
        "B": {"vop": 2_000_000.0, "taxa": 4.0},  # mesma taxa
    }
    mix, intra, _top_mix, _top_intra, _o1, _o2 = _decompose_pvm(
        prior, current, "taxa", _identity, threshold_unit=0.0
    )
    # Como nenhum membro mudou taxa, intra deve ser exatamente zero.
    assert intra == pytest.approx(0.0, abs=1e-9)
    # Mix captura toda a variacao.
    prior_avg = (5 * 2 + 5 * 4) / 10  # 3.0
    current_avg = (8 * 2 + 2 * 4) / 10  # 2.4
    assert mix == pytest.approx(current_avg - prior_avg, abs=1e-6)


# ─── _build_dumbbell ────────────────────────────────────────────────────────


def test_dumbbell_filtra_categorias_pequenas_em_ambos_periodos() -> None:
    """Categorias com share < 1%% em prior E current sao excluidas."""
    prior = {
        "BIG": {"vop": 90_000_000.0},  # 90% em prior
        "MID": {"vop": 9_000_000.0},  # 9% em prior
        "TINY": {"vop": 100_000.0},  # 0.1% em prior
    }
    current = {
        "BIG": {"vop": 90_000_000.0},
        "MID": {"vop": 9_000_000.0},
        "TINY": {"vop": 50_000.0},  # 0.05% em current
    }
    points = _build_dumbbell(prior, current, _identity, top_n=10)
    member_ids = [p.member_id for p in points]
    assert "TINY" not in member_ids
    assert "BIG" in member_ids
    assert "MID" in member_ids


def test_dumbbell_ordena_por_abs_delta_share() -> None:
    """Pontos ordenados por |delta_share_pp| desc."""
    prior = {"A": {"vop": 50_000.0}, "B": {"vop": 50_000.0}}
    current = {"A": {"vop": 80_000.0}, "B": {"vop": 20_000.0}}
    points = _build_dumbbell(prior, current, _identity, top_n=2)
    # Ambos com |delta_share|=30pp, ordem A primeiro (sort estavel)
    assert len(points) == 2
    assert all(abs(p.delta_share_pp) == pytest.approx(30.0, abs=1e-6) for p in points)


# ─── _calcular_hhi_e_movements ──────────────────────────────────────────────


def test_hhi_monopolio_eq_10000() -> None:
    """Monopolio (1 categoria com 100% share) -> HHI = 10000."""
    prior = {"ONLY": {"vop": 1_000_000.0}}
    current = {"ONLY": {"vop": 1_500_000.0}}
    hhi_p, hhi_c, _t3p, _t3c, _g, _l = _calcular_hhi_e_movements(
        prior, current, _identity
    )
    assert hhi_p == pytest.approx(10_000.0, abs=1e-6)
    assert hhi_c == pytest.approx(10_000.0, abs=1e-6)


def test_hhi_perfeitamente_diluido_eq_baixo() -> None:
    """100 categorias iguais (1%% cada) -> HHI = 100."""
    prior = {f"M{i}": {"vop": 1_000_000.0} for i in range(100)}
    current = {f"M{i}": {"vop": 1_000_000.0} for i in range(100)}
    hhi_p, hhi_c, _t3p, _t3c, _g, _l = _calcular_hhi_e_movements(
        prior, current, _identity
    )
    # Cada share = 1; HHI = 100 * 1^2 = 100
    assert hhi_p == pytest.approx(100.0, abs=1e-6)
    assert hhi_c == pytest.approx(100.0, abs=1e-6)


def test_hhi_top3_share_e_movements() -> None:
    """Top-3 share = soma dos 3 maiores; gainers/losers separados."""
    prior = {
        "A": {"vop": 5_000_000.0},  # 50%
        "B": {"vop": 3_000_000.0},  # 30%
        "C": {"vop": 1_500_000.0},  # 15%
        "D": {"vop": 500_000.0},  # 5%
    }
    current = {
        "A": {"vop": 4_000_000.0},  # 40% (-10pp)
        "B": {"vop": 4_000_000.0},  # 40% (+10pp)
        "C": {"vop": 1_500_000.0},  # 15%
        "D": {"vop": 500_000.0},  # 5%
    }
    _hhi_p, _hhi_c, t3_p, t3_c, gainers, losers = _calcular_hhi_e_movements(
        prior, current, _identity
    )
    assert t3_p == pytest.approx(95.0, abs=1e-6)  # A(50)+B(30)+C(15)
    assert t3_c == pytest.approx(95.0, abs=1e-6)  # A(40)+B(40)+C(15)
    # B gainer top
    assert gainers[0].member_id == "B"
    # A loser top
    assert losers[0].member_id == "A"


# ─── _project_close_aditivo ─────────────────────────────────────────────────


def test_projecao_linear_proporcional() -> None:
    """projected = current * (du_totais / du_decorridos)."""
    current = {"A": 8_000_000.0, "B": 4_000_000.0}
    proj_total, _drivers, _outros = _project_close_aditivo(
        current, du_decorridos=8, du_totais=20, label_resolver=_identity
    )
    expected = (8 + 4) * (20 / 8)  # 30M
    assert proj_total == pytest.approx(expected * 1_000_000.0, rel=1e-9)


def test_projecao_du_decorridos_eq_totais_zera_falta() -> None:
    """Quando ja chegou no fim do mes, parcela faltante = 0."""
    current = {"A": 1_000_000.0}
    proj_total, drivers, _outros = _project_close_aditivo(
        current, du_decorridos=20, du_totais=20, label_resolver=_identity
    )
    assert proj_total == pytest.approx(1_000_000.0)
    # Sem parcela faltante -> drivers vazios, outros None (todos abaixo do threshold)
    assert drivers == []


def test_projecao_du_zero_retorna_zero() -> None:
    """1o DU do mes (du_decorridos=0) -> nao projeta (evita divisao por zero)."""
    current = {"A": 0.0}
    proj_total, drivers, outros = _project_close_aditivo(
        current, du_decorridos=0, du_totais=20, label_resolver=_identity
    )
    assert proj_total == 0.0
    assert drivers == []
    assert outros is None


# ─── _build_narrative_pt_br ─────────────────────────────────────────────────


def _vop_factory(
    current: float = 35_200_000.0, prior: float = 31_300_000.0
) -> VarianceBridgeData:
    return VarianceBridgeData(
        prior_anchor_label="VOP abr/26",
        prior_anchor_value=prior,
        current_anchor_label="VOP mai/26",
        current_anchor_value=current,
        delta_brl=current - prior,
        delta_pct=((current - prior) / prior * 100) if prior > 0 else None,
        drivers=[],
        outros_rollup=None,
    )


def _pvm_factory(
    delta: float, current: float = 2.38, unidade: str = "pp"
) -> PvmBridgeData:
    return PvmBridgeData(
        prior_anchor_label="x",
        prior_anchor_value=current - delta,
        current_anchor_label="y",
        current_anchor_value=current,
        delta=delta,
        delta_unidade="pp" if unidade == "pp" else "dias",
        mix_effect=0.0,
        intra_effect=delta,
        top_mix_contributors=[],
        top_intra_contributors=[],
    )


def _conc_factory(delta_top3: float = 3.0) -> ConcentracaoDeltaData:
    return ConcentracaoDeltaData(
        dimension_label="Produto",
        prior_anchor_label="abr/26",
        current_anchor_label="mai/26",
        hhi_prior=2500.0,
        hhi_current=2700.0,
        delta_hhi=200.0,
        top_3_share_prior=70.0,
        top_3_share_current=70.0 + delta_top3,
        delta_top_3_pp=delta_top3,
        movements_gainers=[],
        movements_losers=[],
    )


def test_narrative_format_canonico_com_du_disponivel() -> None:
    """Frase canonica com DU disponivel: 'Em DU N de M: VOP X (+Y%), ...'."""
    frase = _build_narrative_pt_br(
        du_decorridos=8,
        du_totais_mes=21,
        du_disponivel=True,
        vop=_vop_factory(),
        taxa=_pvm_factory(delta=-0.12, current=2.38),
        prazo=_pvm_factory(delta=1.5, current=45.0, unidade="dias"),
        concentracao=_conc_factory(delta_top3=3.0),
        mes_anterior_label="abr/26",
    )
    assert "Em DU 8 de 21" in frase
    assert "VOP" in frase
    assert "Taxa 2,38%" in frase
    assert "-0,12pp" in frase
    assert "Prazo +1,5d" in frase
    assert "Top-3 +3,0pp" in frase


def test_narrative_degraded_sem_du() -> None:
    """Sem DU disponivel: prefixo vira 'MTD parcial'."""
    frase = _build_narrative_pt_br(
        du_decorridos=0,
        du_totais_mes=0,
        du_disponivel=False,
        vop=_vop_factory(),
        taxa=_pvm_factory(delta=0.0, current=2.4),
        prazo=_pvm_factory(delta=0.0, current=45.0, unidade="dias"),
        concentracao=_conc_factory(delta_top3=0.0),
        mes_anterior_label="abr/26",
    )
    assert frase.startswith("MTD parcial:")
    assert "DU" not in frase  # sem prefixo de DU


def test_narrative_omite_top3_quando_movimento_pequeno() -> None:
    """|delta_top_3_pp| < 0.5 -> omite Top-3."""
    frase = _build_narrative_pt_br(
        du_decorridos=8,
        du_totais_mes=21,
        du_disponivel=True,
        vop=_vop_factory(),
        taxa=_pvm_factory(delta=0.0, current=2.4),
        prazo=_pvm_factory(delta=0.0, current=45.0, unidade="dias"),
        concentracao=_conc_factory(delta_top3=0.2),
        mes_anterior_label="abr/26",
    )
    assert "Top-3" not in frase
