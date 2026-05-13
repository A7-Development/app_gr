"""Catalogo declarativo de endpoints — sanidade.

Garante que:
1. Cada catalogo (QiTech, Bitfin) carrega sem erros (validacoes de
   `EndpointSpec.__post_init__` rodam no module load — typo em
   default_schedule_value derruba o import).
2. Catalogos no codigo nao divergem do snapshot inline da migration sem
   batalha consciente — protege contra alteracao de default que esquece de
   atualizar o seed.
3. EndpointSpec e frozen dataclass (mutacao acidental detectada).
4. `endpoint_catalog()` em public.py espelha o catalogo para sources com
   entrada e retorna [] para sources sem (Serasa, etc).
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.core.enums import SourceType
from app.modules.integracoes.adapters.admin.qitech.endpoint_catalog import (
    QITECH_ENDPOINTS,
    QITECH_ENDPOINTS_BY_NAME,
)
from app.modules.integracoes.adapters.erp.bitfin.endpoint_catalog import (
    BITFIN_ENDPOINTS,
    BITFIN_ENDPOINTS_BY_NAME,
)
from app.modules.integracoes.public import endpoint_catalog
from app.shared.endpoint_catalog import EndpointSpec, ScheduleKind

# ─────────────────────────────────────────────────────────────────────────────
# Sanidade dos catalogos
# ─────────────────────────────────────────────────────────────────────────────


def test_qitech_catalog_has_17_endpoints():
    """Documenta o tamanho atual do catalogo. Trocar este numero exige
    batalha consciente — adicionar endpoint = atualizar este teste +
    snapshot da migration.

    Composicao atual (2026-05-12):
        - 10 market reports sincronos (`etl.py`)
        - 1 market report async callback (`market.fidc_estoque`)
        - 4 custodia reports on-demand (`custodia.py` — fidc-custodia/*)
        - 2 bank-account reports (`bank_account_sync.py`)
    """
    assert len(QITECH_ENDPOINTS) == 17


def test_qitech_catalog_names_unique():
    names = [ep.name for ep in QITECH_ENDPOINTS]
    assert len(names) == len(set(names)), f"Duplicates: {names}"


def test_qitech_catalog_index_matches_tuple():
    assert len(QITECH_ENDPOINTS_BY_NAME) == len(QITECH_ENDPOINTS)
    for ep in QITECH_ENDPOINTS:
        assert QITECH_ENDPOINTS_BY_NAME[ep.name] is ep


def test_bitfin_catalog_has_1_endpoint():
    """Bitfin e monolitico hoje — 1 endpoint so (`bitfin.full_sync`)."""
    assert len(BITFIN_ENDPOINTS) == 1
    assert BITFIN_ENDPOINTS[0].name == "bitfin.full_sync"


def test_bitfin_catalog_index_matches_tuple():
    assert len(BITFIN_ENDPOINTS_BY_NAME) == 1


# ─────────────────────────────────────────────────────────────────────────────
# Catalogo no codigo == snapshot da migration
# ─────────────────────────────────────────────────────────────────────────────
#
# Migration `d5bf3669b8a0_endpoint_scheduling.py` hardcoda os defaults para
# nao importar codigo de adapter (CLAUDE.md migration rule). Este teste
# fecha o ciclo: garante que codigo no adapter == snapshot persistido. Se
# divergir, alguem tem que decidir conscientemente "estou aceitando a
# divergencia porque ja rolou em prod" OU "vou sincronizar os dois lados".

# Snapshot duplicado aqui (intencional — proxy do que esta na migration).
EXPECTED_QITECH_SNAPSHOT = [
    ("market.outros_fundos", "daily_at", "07:00"),
    ("market.conta_corrente", "daily_at", "07:30"),
    ("market.tesouraria", "daily_at", "07:30"),
    ("market.outros_ativos", "daily_at", "08:00"),
    ("market.demonstrativo_caixa", "daily_at", "08:00"),
    ("market.cpr", "daily_at", "08:30"),
    ("market.mec", "daily_at", "08:30"),
    ("market.rentabilidade", "daily_at", "09:00"),
    ("market.rf", "daily_at", "08:00"),
    ("market.rf_compromissadas", "daily_at", "08:00"),
    # Adicionado em 2026-05-10 — seed via migration `c4b9e8f2a1d3_seed_qitech_fidc_estoque_endpoint.py`.
    # Promovido de on_demand para daily_at 09:00 em 2026-05-13 — migration
    # `f2a8c7e1b9d3_promote_qitech_fidc_estoque_to_daily.py` com base em info da
    # QiTech ("fundo processa entre 8h-9h; automatize a partir das 9h, retry
    # depois das 10h"). Reconciler cobre o retry implicito.
    ("market.fidc_estoque", "daily_at", "09:00"),
    # Adicionados em 2026-05-12 — seed via migration `a3c5d1e7b8f2_seed_qitech_custodia_endpoints.py`.
    # Familia /v2/fidc-custodia/report/* — antes acessivel apenas via REST proprio
    # (`routers/qitech_custodia.py`), agora centralizada no catalogo.
    # Promovidos de on_demand para daily_at em 2026-05-12 — migration
    # `b5e9d3a1f7c4_promote_qitech_custodia_to_daily.py` (cobertura continua,
    # janelas rolantes naturalmente curtas resolvidas pelo handler).
    ("custodia.aquisicao_consolidada", "daily_at", "09:30"),
    ("custodia.liquidados_baixados", "daily_at", "09:45"),
    ("custodia.movimento_aberto", "daily_at", "10:00"),
    ("custodia.detalhes_operacoes", "daily_at", "10:00"),
    ("bank_account.balance", "daily_at", "19:00"),
    ("bank_account.statement", "interval", "60"),
]

EXPECTED_BITFIN_SNAPSHOT = [
    ("bitfin.full_sync", "interval", "30"),
]


def test_qitech_catalog_matches_migration_snapshot():
    actual = [
        (ep.name, ep.default_schedule_kind.value, ep.default_schedule_value)
        for ep in QITECH_ENDPOINTS
    ]
    assert actual == EXPECTED_QITECH_SNAPSHOT


def test_bitfin_catalog_matches_migration_snapshot():
    actual = [
        (ep.name, ep.default_schedule_kind.value, ep.default_schedule_value)
        for ep in BITFIN_ENDPOINTS
    ]
    assert actual == EXPECTED_BITFIN_SNAPSHOT


# ─────────────────────────────────────────────────────────────────────────────
# EndpointSpec primitives
# ─────────────────────────────────────────────────────────────────────────────


def test_endpoint_spec_is_frozen():
    ep = QITECH_ENDPOINTS[0]
    with pytest.raises(FrozenInstanceError):
        ep.label = "nope"  # type: ignore[misc]


def test_endpoint_spec_rejects_interval_out_of_range():
    with pytest.raises(ValueError, match="INTERVAL value must be"):
        EndpointSpec(
            name="x.y",
            label="X",
            description="D",
            default_schedule_kind=ScheduleKind.INTERVAL,
            default_schedule_value="10",  # < 15
            canonical_table="t",
        )


def test_endpoint_spec_rejects_interval_non_integer():
    with pytest.raises(ValueError, match="INTERVAL requires"):
        EndpointSpec(
            name="x.y",
            label="X",
            description="D",
            default_schedule_kind=ScheduleKind.INTERVAL,
            default_schedule_value="60min",
            canonical_table="t",
        )


def test_endpoint_spec_rejects_daily_at_bad_format():
    with pytest.raises(ValueError, match="DAILY_AT requires"):
        EndpointSpec(
            name="x.y",
            label="X",
            description="D",
            default_schedule_kind=ScheduleKind.DAILY_AT,
            default_schedule_value="7:00",  # missing leading zero
            canonical_table="t",
        )


def test_endpoint_spec_rejects_on_demand_with_value():
    with pytest.raises(ValueError, match="ON_DEMAND must have"):
        EndpointSpec(
            name="x.y",
            label="X",
            description="D",
            default_schedule_kind=ScheduleKind.ON_DEMAND,
            default_schedule_value="60",  # should be None
            canonical_table="t",
        )


def test_endpoint_spec_accepts_on_demand_with_null():
    ep = EndpointSpec(
        name="x.y",
        label="X",
        description="D",
        default_schedule_kind=ScheduleKind.ON_DEMAND,
        default_schedule_value=None,
        canonical_table="t",
    )
    assert ep.default_schedule_kind == ScheduleKind.ON_DEMAND


# ─────────────────────────────────────────────────────────────────────────────
# Public contract endpoint_catalog()
# ─────────────────────────────────────────────────────────────────────────────


def test_endpoint_catalog_qitech():
    cat = endpoint_catalog(SourceType.ADMIN_QITECH)
    assert len(cat) == 17
    assert cat[0].name == "market.outros_fundos"


def test_endpoint_catalog_bitfin():
    cat = endpoint_catalog(SourceType.ERP_BITFIN)
    assert len(cat) == 1
    assert cat[0].name == "bitfin.full_sync"


def test_endpoint_catalog_serasa_pj_empty():
    """Serasa nao participa de scheduling — query sob demanda."""
    assert endpoint_catalog(SourceType.BUREAU_SERASA_PJ) == []


def test_endpoint_catalog_serasa_pf_empty():
    assert endpoint_catalog(SourceType.BUREAU_SERASA_PF) == []
