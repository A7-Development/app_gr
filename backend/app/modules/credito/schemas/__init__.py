"""Pydantic schemas for the credito API."""

from app.modules.credito.schemas.checklist import (
    ChecklistItemRead,
    ChecklistItemUpsert,
)
from app.modules.credito.schemas.dossier import (
    DossierCreate,
    DossierListItem,
    DossierRead,
    DossierStateResponse,
    DossierUpdate,
    NodeSubmitPayload,
)
from app.modules.credito.schemas.pleito import (
    PleitoExtractRequest,
    PleitoRead,
    PleitoUpsert,
)
from app.modules.credito.schemas.template import (
    DocumentTemplateRead,
    DocumentTemplateUpsert,
)

__all__ = [
    "ChecklistItemRead",
    "ChecklistItemUpsert",
    "DocumentTemplateRead",
    "DocumentTemplateUpsert",
    "DossierCreate",
    "DossierListItem",
    "DossierRead",
    "DossierStateResponse",
    "DossierUpdate",
    "NodeSubmitPayload",
    "PleitoExtractRequest",
    "PleitoRead",
    "PleitoUpsert",
]
