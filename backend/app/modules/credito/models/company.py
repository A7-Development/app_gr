"""CreditDossierCompany — companies linked to a dossier (target + economic group)."""

from uuid import UUID, uuid4

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import CompanyRole


class CreditDossierCompany(Base):
    """One company (CNPJ) linked to a dossier."""

    __tablename__ = "credit_dossier_company"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    dossier_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("credit_dossier.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    cnpj: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[CompanyRole] = mapped_column(
        SAEnum(
            CompanyRole,
            name="company_role",
            native_enum=False,
            length=32,
        ),
        nullable=False,
    )

    # Optional canonical data from Receita Federal / Junta Comercial
    receita_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    junta_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<CreditDossierCompany cnpj={self.cnpj} role={self.role.value}>"
