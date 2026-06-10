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


def test_bitfin_catalog_has_3_endpoints():
    """Documenta o tamanho atual do catalogo Bitfin. Trocar este numero
    exige batalha consciente (adicionar endpoint = atualizar este teste +
    snapshot da migration).

    Composicao atual (2026-06-10):
        - bitfin.full_sync (ERP monolitico — )
        - bitfin.entidades (party model: wh_entidade + papeis + grupos)
        - bitfin.serasa_relay (replica ConsultaFinanceira -> wh_serasa_pj_*)
    """
    assert [ep.name for ep in BITFIN_ENDPOINTS] == [
        "bitfin.full_sync",
        "bitfin.entidades",
        "bitfin.serasa_relay",
    ]


def test_bitfin_catalog_index_matches_tuple():
    assert len(BITFIN_ENDPOINTS_BY_NAME) == len(BITFIN_ENDPOINTS)
    for ep in BITFIN_ENDPOINTS:
        assert BITFIN_ENDPOINTS_BY_NAME[ep.name] is ep


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
    ("bitfin.entidades", "interval", "360"),
    ("bitfin.serasa_relay", "interval", "15"),
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
            admin_code="test",
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
            admin_code="test",
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
            admin_code="test",
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
            admin_code="test",
            name="x.y",
            label="X",
            description="D",
            default_schedule_kind=ScheduleKind.ON_DEMAND,
            default_schedule_value="60",  # should be None
            canonical_table="t",
        )


def test_endpoint_spec_accepts_on_demand_with_null():
    ep = EndpointSpec(
        admin_code="test",
        name="x.y",
        label="X",
        description="D",
        default_schedule_kind=ScheduleKind.ON_DEMAND,
        default_schedule_value=None,
        canonical_table="t",
    )
    assert ep.default_schedule_kind == ScheduleKind.ON_DEMAND


# ─────────────────────────────────────────────────────────────────────────────
# admin_code + global_id (2026-05-18) — identidade cross-admin do endpoint
# ─────────────────────────────────────────────────────────────────────────────


def test_endpoint_spec_global_id_format():
    """global_id = <admin_code>.<name> — sem espacos, sem maiusculas."""
    ep = QITECH_ENDPOINTS_BY_NAME["market.fidc_estoque"]
    assert ep.admin_code == "qitech"
    assert ep.global_id == "qitech.market.fidc_estoque"


def test_endpoint_spec_tenant_endpoint_handle():
    """Handle exposto na UI admin: <tenant_slug>.<admin_code>.<name>."""
    ep = QITECH_ENDPOINTS_BY_NAME["market.fidc_estoque"]
    handle = ep.tenant_endpoint_handle("realinvest")
    assert handle == "realinvest.qitech.market.fidc_estoque"


def test_endpoint_spec_rejects_empty_admin_code():
    with pytest.raises(ValueError, match="admin_code must be"):
        EndpointSpec(
            admin_code="",
            name="x.y",
            label="X",
            description="D",
            default_schedule_kind=ScheduleKind.ON_DEMAND,
            default_schedule_value=None,
            canonical_table="t",
        )


def test_endpoint_spec_rejects_uppercase_admin_code():
    with pytest.raises(ValueError, match="admin_code must be"):
        EndpointSpec(
            admin_code="QiTech",
            name="x.y",
            label="X",
            description="D",
            default_schedule_kind=ScheduleKind.ON_DEMAND,
            default_schedule_value=None,
            canonical_table="t",
        )


def test_endpoint_spec_rejects_admin_code_with_dot():
    with pytest.raises(ValueError, match="admin_code must be"):
        EndpointSpec(
            admin_code="qitech.foo",
            name="x.y",
            label="X",
            description="D",
            default_schedule_kind=ScheduleKind.ON_DEMAND,
            default_schedule_value=None,
            canonical_table="t",
        )


def test_qitech_all_have_admin_code_qitech():
    """Todos os specs do catalogo QiTech declaram admin_code='qitech'."""
    assert all(ep.admin_code == "qitech" for ep in QITECH_ENDPOINTS)


def test_bitfin_all_have_admin_code_bitfin():
    assert all(ep.admin_code == "bitfin" for ep in BITFIN_ENDPOINTS)


def test_global_ids_unique_across_admins():
    """Combinacao admin_code+name nao colide entre QiTech e Bitfin."""
    all_specs = [*QITECH_ENDPOINTS, *BITFIN_ENDPOINTS]
    ids = [ep.global_id for ep in all_specs]
    assert len(ids) == len(set(ids)), f"Colisao em global_id: {ids}"


# ─────────────────────────────────────────────────────────────────────────────
# Payload shape docs (Fase 2 do refactor, 2026-05-18) — todo endpoint QiTech
# tem .md correspondente. Arquivo + spec apontam pro mesmo caminho.
# ─────────────────────────────────────────────────────────────────────────────


def test_qitech_all_have_payload_shape_doc_relpath():
    """Cada spec QiTech declara o relpath do .md de shape."""
    missing = [ep.name for ep in QITECH_ENDPOINTS if not ep.payload_shape_doc_relpath]
    assert missing == [], f"Specs sem payload_shape_doc_relpath: {missing}"


def test_qitech_payload_shape_doc_relpath_format():
    """Relpath segue convencao `.../payload_shapes/<name>.md`."""
    for ep in QITECH_ENDPOINTS:
        relpath = ep.payload_shape_doc_relpath
        assert relpath is not None
        assert relpath.endswith(f"/{ep.name}.md"), (
            f"{ep.name}: relpath={relpath!r} nao termina em /{ep.name}.md"
        )
        assert "payload_shapes/" in relpath, (
            f"{ep.name}: relpath={relpath!r} nao contem payload_shapes/"
        )


def test_qitech_payload_shape_doc_files_exist():
    """Cada relpath aponta pra arquivo .md real no disco."""
    import os
    from pathlib import Path

    # Resolver raiz do repo: subir ate achar `backend/`.
    here = Path(__file__).resolve()
    repo_root = here
    while repo_root.name != "backend":
        repo_root = repo_root.parent
    repo_root = repo_root.parent  # subir mais 1 — repo_root = .../app_gr

    missing = []
    for ep in QITECH_ENDPOINTS:
        full_path = repo_root / ep.payload_shape_doc_relpath
        if not full_path.is_file():
            missing.append(f"{ep.name}: {full_path}")
    assert missing == [], f"Arquivos .md faltando:\n  " + "\n  ".join(missing)


def test_bitfin_has_no_payload_shape_doc_yet():
    """Bitfin ainda nao publicou shape catalog — None e aceitavel."""
    # Quando publicar, atualizar este teste pra exigir.
    assert BITFIN_ENDPOINTS[0].payload_shape_doc_relpath is None


# ─────────────────────────────────────────────────────────────────────────────
# Tolerance window primitives (2026-05-15) — expected/tolerance/give_up
# ─────────────────────────────────────────────────────────────────────────────


def test_endpoint_spec_defaults_tolerance_window():
    """Defaults sao 1/3/10 — coerentes com market reports tipicos QiTech."""
    ep = EndpointSpec(
        admin_code="test",
        name="x.y",
        label="X",
        description="D",
        default_schedule_kind=ScheduleKind.DAILY_AT,
        default_schedule_value="08:00",
        canonical_table="t",
    )
    assert ep.default_expected_lag_business_days == 1
    assert ep.default_tolerance_business_days == 3
    assert ep.default_give_up_business_days == 10


def test_endpoint_spec_rejects_negative_expected():
    with pytest.raises(ValueError, match="expected_lag must be >= 0"):
        EndpointSpec(
            admin_code="test",
            name="x.y",
            label="X",
            description="D",
            default_schedule_kind=ScheduleKind.DAILY_AT,
            default_schedule_value="08:00",
            canonical_table="t",
            default_expected_lag_business_days=-1,
        )


def test_endpoint_spec_rejects_tolerance_below_expected():
    with pytest.raises(ValueError, match="tolerance .* must be >= expected"):
        EndpointSpec(
            admin_code="test",
            name="x.y",
            label="X",
            description="D",
            default_schedule_kind=ScheduleKind.DAILY_AT,
            default_schedule_value="08:00",
            canonical_table="t",
            default_expected_lag_business_days=3,
            default_tolerance_business_days=2,
        )


def test_endpoint_spec_rejects_give_up_below_tolerance():
    with pytest.raises(ValueError, match="give_up .* must be >= tolerance"):
        EndpointSpec(
            admin_code="test",
            name="x.y",
            label="X",
            description="D",
            default_schedule_kind=ScheduleKind.DAILY_AT,
            default_schedule_value="08:00",
            canonical_table="t",
            default_tolerance_business_days=5,
            default_give_up_business_days=3,
        )


def test_qitech_state_machine_enabled_set():
    """Documenta o conjunto exato de endpoints sob state machine (F3, 2026-05-21).

    Trocar este conjunto exige batalha consciente — ligar/desligar endpoint
    na state machine afeta o caminho de sync (legado vs state_machine_dispatcher).
    Ver `project_qitech_sync_state_machine` memory.

    Excluidos por desenho:
    - `bank_account.balance`: DAILY_AT 19:00 com expected_lag=0. Candidato
      futuro; nao incluido na F3 inicial.
    - `bank_account.statement`: INTERVAL 60min. Coverage UNSUPPORTED, fluxo
      diferente. Nao se aplica.

    Caso especial:
    - `market.fidc_estoque`: fluxo assincrono job+webhook. Migrado pra state
      machine em 2026-05-29 via branch assincrono do dispatcher
      (`is_async_report=True`) — guard de in-flight + backoff de tolerancia,
      substituindo o cap cego de 8 tentativas do reconciler legado. Ver
      `project_qitech_max_attempts_cap`.
    """
    enabled = {ep.name for ep in QITECH_ENDPOINTS if ep.state_machine_enabled}
    expected = {
        # Piloto F1.5 (2026-05-19)
        "market.conta_corrente",
        # F3 rollout (2026-05-21): 9 market.* sincronos restantes
        "market.outros_fundos",
        "market.tesouraria",
        "market.outros_ativos",
        "market.demonstrativo_caixa",
        "market.cpr",
        "market.mec",
        "market.rentabilidade",
        "market.rf",
        "market.rf_compromissadas",
        # F3 rollout (2026-05-21): 4 custodia.*
        "custodia.aquisicao_consolidada",
        "custodia.liquidados_baixados",
        "custodia.movimento_aberto",
        "custodia.detalhes_operacoes",
        # Async (2026-05-29): migrado do reconciler legado via branch assincrono
        "market.fidc_estoque",
    }
    assert enabled == expected, (
        f"State machine set divergiu: enabled={enabled} expected={expected}"
    )


def test_qitech_fidc_estoque_in_state_machine_async():
    """fidc_estoque (async job+webhook) foi migrado pra state machine em
    2026-05-29 com `is_async_report=True` — o dispatcher usa o branch
    assincrono (guard de in-flight + backoff). Substituiu o caminho legado
    do reconciler, cujo cap de 8 tentativas/data gerava furo silencioso
    quando a QiTech publicava tarde. Ver `project_qitech_max_attempts_cap`."""
    spec = QITECH_ENDPOINTS_BY_NAME["market.fidc_estoque"]
    assert spec.state_machine_enabled is True
    assert spec.is_async_report is True


def test_qitech_catalog_tolerance_overrides():
    """Endpoints com tolerancia customizada — mantem o desvio explicito.

    fidc_estoque: 1/2/7 (mais apertado, assincrono).
    bank_account.balance: 0/1/5 (mesmo dia).
    """
    by_name = QITECH_ENDPOINTS_BY_NAME
    assert by_name["market.fidc_estoque"].default_tolerance_business_days == 2
    assert by_name["market.fidc_estoque"].default_give_up_business_days == 7
    assert (
        by_name["bank_account.balance"].default_expected_lag_business_days == 0
    )
    assert by_name["bank_account.balance"].default_give_up_business_days == 5
    # Market reports continuam no default 1/3/10.
    assert by_name["market.conta_corrente"].default_expected_lag_business_days == 1
    assert by_name["market.conta_corrente"].default_tolerance_business_days == 3
    assert by_name["market.conta_corrente"].default_give_up_business_days == 10


# ─────────────────────────────────────────────────────────────────────────────
# Public contract endpoint_catalog()
# ─────────────────────────────────────────────────────────────────────────────


def test_endpoint_catalog_qitech():
    cat = endpoint_catalog(SourceType.ADMIN_QITECH)
    assert len(cat) == 17
    assert cat[0].name == "market.outros_fundos"


def test_endpoint_catalog_bitfin():
    cat = endpoint_catalog(SourceType.ERP_BITFIN)
    assert len(cat) == 3
    assert cat[0].name == "bitfin.full_sync"


def test_endpoint_catalog_serasa_pj_empty():
    """Serasa nao participa de scheduling — query sob demanda."""
    assert endpoint_catalog(SourceType.BUREAU_SERASA_PJ) == []


def test_endpoint_catalog_serasa_pf_empty():
    assert endpoint_catalog(SourceType.BUREAU_SERASA_PF) == []
