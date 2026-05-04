"""SQLAlchemy models for the credito module."""

from app.modules.credito.models.analysis import CreditDossierAnalysis
from app.modules.credito.models.analysis_item import CreditAnalysisItem, CreditDossierCheck
from app.modules.credito.models.bureau_query import CreditDossierBureauQuery
from app.modules.credito.models.company import CreditDossierCompany
from app.modules.credito.models.document import CreditDossierDocument
from app.modules.credito.models.document_template import CreditDocumentTemplate
from app.modules.credito.models.dossier import CreditDossier
from app.modules.credito.models.dossier_attachment import DossierAttachment
from app.modules.credito.models.dossier_step_link import DossierStepLink
from app.modules.credito.models.dossier_step_note import DossierStepNote
from app.modules.credito.models.financial import CreditDossierFinancial
from app.modules.credito.models.opinion import CreditDossierOpinion
from app.modules.credito.models.person import CreditDossierPerson
from app.modules.credito.models.pleito import CreditDossierPleito
from app.modules.credito.models.red_flag import CreditDossierRedFlag

__all__ = [
    "CreditAnalysisItem",
    "CreditDocumentTemplate",
    "CreditDossier",
    "CreditDossierAnalysis",
    "CreditDossierBureauQuery",
    "CreditDossierCheck",
    "CreditDossierCompany",
    "CreditDossierDocument",
    "CreditDossierFinancial",
    "CreditDossierOpinion",
    "CreditDossierPerson",
    "CreditDossierPleito",
    "CreditDossierRedFlag",
    "DossierAttachment",
    "DossierStepLink",
    "DossierStepNote",
]
