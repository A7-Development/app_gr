"""Public contract of the credito module.

Other modules MUST import only from here. Internals (services, models)
are not contract.
"""

from app.modules.credito.models.dossier import CreditDossier
from app.modules.credito.schemas.dossier import (
    DossierCreate,
    DossierListItem,
    DossierRead,
)

__all__ = [
    "CreditDossier",
    "DossierCreate",
    "DossierListItem",
    "DossierRead",
]
