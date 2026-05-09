"""CreditDossierPerson — natural persons linked to a dossier (partners, representatives, guarantors)."""

from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Enum as SAEnum
from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import PersonRole


class CreditDossierPerson(Base):
    """A natural person linked to a dossier (socio, representante, avalista, related)."""

    __tablename__ = "credit_dossier_person"

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

    # Privacy: only last 4 digits stored. Full CPF lives in the original
    # document (encrypted) and isn't queryable by index.
    cpf_redacted: Mapped[str | None] = mapped_column(String(20), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    role: Mapped[PersonRole] = mapped_column(
        SAEnum(
            PersonRole,
            name="person_role",
            native_enum=False,
            length=32,
        ),
        nullable=False,
    )

    # Free-form description of the relationship.
    relationship_to_company: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Which CNPJ from credit_dossier_company they're tied to.
    company_cnpj: Mapped[str | None] = mapped_column(String(20), nullable=True)

    ownership_pct: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=5, scale=2), nullable=True
    )

    def __repr__(self) -> str:
        return f"<CreditDossierPerson name={self.name!r} role={self.role.value}>"
