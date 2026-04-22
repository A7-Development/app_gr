"""Catalog of external data sources (global registry).

Per-tenant source configuration lives in `app.modules.integracoes.models.tenant_source_config`.
"""

from app.shared.catalog.source_catalog import SourceCatalog

__all__ = ["SourceCatalog"]
