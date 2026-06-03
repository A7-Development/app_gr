"""Regression tests for migration `d5bf3669b8a0_endpoint_scheduling`.

Bug historico (corrigido neste PR): `CATALOG_BY_SOURCE_TYPE` usava VALUES do
enum `SourceType` (`"admin:qitech"`, `"erp:bitfin"`) como keys, mas o backfill
le `tenant_source_config.source_type`, que armazena os NAMES do enum
(`"ADMIN_QITECH"`, `"ERP_BITFIN"`) — default do SQLAlchemy `sa.Enum` sem
`values_callable`. Mismatch silencioso → backfill `continue`-ava em toda linha
→ TSEC nunca era populada.

Estes testes garantem:
1. Cada key de `CATALOG_BY_SOURCE_TYPE` e um `SourceType.name` valido.
2. O catalogo cobre os sources que tem catalogo (QiTech, Bitfin) e somente
   esses — Bureaus / documentos nao entram.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from app.core.enums import SourceType

_MIGRATION_PATH = (
    Path(__file__).resolve().parents[3]
    / "alembic"
    / "versions"
    / "d5bf3669b8a0_endpoint_scheduling.py"
)


def _load_migration_module():
    """Load migration as a plain module (no Alembic runtime needed)."""
    spec = importlib.util.spec_from_file_location(
        "_migration_d5bf3669b8a0", _MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_catalog_keys_are_valid_source_type_names():
    """Cada key e um `SourceType.name` (= o que o DB armazena)."""
    mig = _load_migration_module()
    valid_names = {st.name for st in SourceType}
    for key in mig.CATALOG_BY_SOURCE_TYPE:
        assert key in valid_names, (
            f"CATALOG_BY_SOURCE_TYPE key {key!r} nao e um SourceType.name. "
            f"Validos: {sorted(valid_names)}. "
            f"Provavel uso de `.value` (admin:qitech) em vez de `.name` (ADMIN_QITECH)."
        )


def test_catalog_covers_qitech_and_bitfin():
    """QiTech e Bitfin tem catalogo nao-vazio; demais sources nao."""
    mig = _load_migration_module()
    assert SourceType.ADMIN_QITECH.name in mig.CATALOG_BY_SOURCE_TYPE
    assert SourceType.ERP_BITFIN.name in mig.CATALOG_BY_SOURCE_TYPE
    # Bureaus + documentos nao participam do scheduling periodico.
    for st in (
        SourceType.BUREAU_SERASA_PJ,
        SourceType.BUREAU_SERASA_PF,
        SourceType.BUREAU_SCR_BACEN,
        SourceType.DOCUMENT_NFE,
    ):
        assert st.name not in mig.CATALOG_BY_SOURCE_TYPE


def test_qitech_snapshot_endpoint_count():
    """Bate com `QITECH_ENDPOINTS` no adapter (12 hoje)."""
    mig = _load_migration_module()
    assert len(mig.QITECH_SNAPSHOT) == 12


def test_bitfin_snapshot_endpoint_count():
    mig = _load_migration_module()
    assert len(mig.BITFIN_SNAPSHOT) == 1
