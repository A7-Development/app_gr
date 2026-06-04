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
    Operacoes4LensPrazoData,
    Operacoes4LensReceitasData,
    Operacoes4LensTaxasData,
    Operacoes4Mover,
    Operacoes4Movers,
    Operacoes4PrazoBucket,
    Operacoes4ReceitaComposicaoItem,
    Operacoes4ReceitaTipo,
    Operacoes4TaxaBucket,
    Operacoes4TaxaPorProdutoItem,
    Operacoes4YieldPonto,
)
from app.modules.bi.services.operacoes import _alocar_receita_por_cedente
from app.modules.bi.services.operacoes4 import (
    _BUCKET_TO_ENUM,
    _BUCKETS_ORDER,
    _PRAZO_BUCKET_LABELS,
    _TAXA_BUCKET_LABELS,
    _is_atypical,
    _pick_movers,
    _prazo_bucket_index,
    _taxa_bucket_index,
    _weighted_median,
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


# ─── _taxa_bucket_index ────────────────────────────────────────────────────


def test_taxa_bucket_index_cobre_5_faixas() -> None:
    """Bordas (2,0 / 2,5 / 3,0 / 3,5) classificam nas 5 faixas esperadas."""
    assert _taxa_bucket_index(0.0) == 0  # <2,0 (inclui taxa zero)
    assert _taxa_bucket_index(1.99) == 0
    assert _taxa_bucket_index(2.0) == 1  # borda inferior pertence a faixa
    assert _taxa_bucket_index(2.49) == 1
    assert _taxa_bucket_index(2.5) == 2
    assert _taxa_bucket_index(2.99) == 2
    assert _taxa_bucket_index(3.0) == 3
    assert _taxa_bucket_index(3.49) == 3
    assert _taxa_bucket_index(3.5) == 4  # cauda
    assert _taxa_bucket_index(9.9) == 4
    # indices cobrem exatamente os labels disponiveis
    assert _taxa_bucket_index(9.9) == len(_TAXA_BUCKET_LABELS) - 1


# ─── _prazo_bucket_index ───────────────────────────────────────────────────


def test_prazo_bucket_index_cobre_6_faixas() -> None:
    """Bordas (15/30/45/60/90) classificam nas 6 faixas de prazo esperadas."""
    assert _prazo_bucket_index(0.0) == 0  # 0-15
    assert _prazo_bucket_index(14.9) == 0
    assert _prazo_bucket_index(15.0) == 1  # 15-30
    assert _prazo_bucket_index(29.9) == 1
    assert _prazo_bucket_index(30.0) == 2
    assert _prazo_bucket_index(45.0) == 3
    assert _prazo_bucket_index(60.0) == 4  # 60-90
    assert _prazo_bucket_index(89.9) == 4
    assert _prazo_bucket_index(90.0) == 5  # cauda >90
    assert _prazo_bucket_index(365.0) == 5
    assert _prazo_bucket_index(365.0) == len(_PRAZO_BUCKET_LABELS) - 1


# ─── _weighted_median ──────────────────────────────────────────────────────


def test_weighted_median_pondera_por_vop() -> None:
    """Mediana ponderada: 50% do peso abaixo. Peso alto puxa a mediana."""
    # taxa 3,0 carrega 80% do volume -> mediana cai em 3,0, nao em 2,0.
    pairs = [(2.0, 100.0), (3.0, 900.0)]
    assert _weighted_median(pairs) == pytest.approx(3.0)


def test_weighted_median_ignora_peso_zero_e_vazio() -> None:
    """Pesos zero nao contam; lista sem peso positivo -> 0.0."""
    assert _weighted_median([(2.5, 0.0), (3.0, 0.0)]) == pytest.approx(0.0)
    assert _weighted_median([]) == pytest.approx(0.0)
    # taxa com peso zero nao desloca a mediana das demais
    assert _weighted_median([(1.0, 0.0), (2.8, 500.0)]) == pytest.approx(2.8)


# ─── schemas (validacao basica) ────────────────────────────────────────────


def test_lens_taxas_schema_aceita_5_faixas() -> None:
    """Schema valida histograma de 5 faixas + wavg/mediana/delta."""
    data = Operacoes4LensTaxasData(
        histograma=[
            Operacoes4TaxaBucket(
                label=label,
                vop_mtd=Decimal("1000.00"),
                is_tail=(i == len(_TAXA_BUCKET_LABELS) - 1),
            )
            for i, label in enumerate(_TAXA_BUCKET_LABELS)
        ],
        por_produto=[],
        wavg_pct=2.45,
        mediana_pct=2.70,
        delta_pp=-0.10,
        n_operacoes=36,
        mes_label="jun/26",
        du_decorridos=3,
        du_totais_mes=21,
        du_disponivel=True,
    )
    assert len(data.histograma) == 5
    assert data.histograma[-1].is_tail is True
    assert data.wavg_pct == pytest.approx(2.45)


def test_lens_taxas_schema_por_produto() -> None:
    """por_produto aceita quebra por produto com taxa wavg + vop."""
    data = Operacoes4LensTaxasData(
        histograma=[
            Operacoes4TaxaBucket(label=lbl, vop_mtd=Decimal("0"))
            for lbl in _TAXA_BUCKET_LABELS
        ],
        por_produto=[
            Operacoes4TaxaPorProdutoItem(
                produto="FAT", taxa_wavg_pct=2.29, vop_mtd=Decimal("2126193")
            ),
            Operacoes4TaxaPorProdutoItem(
                produto="CBV", taxa_wavg_pct=0.0, vop_mtd=Decimal("324379")
            ),
        ],
        wavg_pct=2.45,
        mediana_pct=2.70,
        delta_pp=None,
        n_operacoes=36,
        mes_label="jun/26",
        du_decorridos=3,
        du_totais_mes=21,
        du_disponivel=True,
    )
    assert data.por_produto[0].produto == "FAT"
    assert data.por_produto[1].taxa_wavg_pct == pytest.approx(0.0)


def test_lens_prazo_schema_aceita_6_faixas() -> None:
    """Schema de prazo valida histograma de 6 faixas + wavg/delta em dias."""
    data = Operacoes4LensPrazoData(
        histograma=[
            Operacoes4PrazoBucket(
                label=label,
                vop_mtd=Decimal("1000.00"),
                is_tail=(i == len(_PRAZO_BUCKET_LABELS) - 1),
            )
            for i, label in enumerate(_PRAZO_BUCKET_LABELS)
        ],
        wavg_dias=29.9,
        delta_dias=1.6,
        n_operacoes=36,
        mes_label="jun/26",
        du_decorridos=3,
        du_totais_mes=21,
        du_disponivel=True,
    )
    assert len(data.histograma) == 6
    assert data.histograma[-1].is_tail is True
    assert data.wavg_dias == pytest.approx(29.9)


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
