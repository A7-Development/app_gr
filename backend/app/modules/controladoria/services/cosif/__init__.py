"""Service de classificacao COSIF — cascata override -> rule -> pendente.

Uso:
    from app.modules.controladoria.services.cosif import (
        classify,
        load_catalog_tree,
    )
"""

from app.modules.controladoria.services.cosif.classifier import (
    CosifResolution,
    classify,
    load_catalog_tree,
    load_overrides,
    load_rules_cache,
)

__all__ = [
    "CosifResolution",
    "classify",
    "load_catalog_tree",
    "load_overrides",
    "load_rules_cache",
]
