"""CreditDossierCompany — companies linked to a dossier (target + economic group)."""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Date, ForeignKey, Numeric, String
from sqlalchemy import Enum as SAEnum
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

    # Data de fundacao/constituicao. Na Fatia 1 vem auto-declarada do cadastro
    # (source self_declared); quando a Receita entrar, o adapter valida/cruza
    # (familia cross-fonte). Lida pelo check `company_founding_age` (gate de
    # elegibilidade: idade > N anos).
    founding_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ── Cadastral silver — enriquecido pela fonte externa (BDC cadastral). ──
    # Lidos pelos checks do gate A2 (NAO parseados de raw no check, §13.2.1).
    # tax_status: situacao cadastral (ATIVA/BAIXADA/INAPTA/SUSPENSA) <- BDC
    #   TaxIdStatus. Lido pelo check `company_status_active`.
    tax_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # cnaes: lista de {code, is_main, name?} (principal + secundarias) <- BDC
    #   Activities[]. Lido pelo check `cnae_permitido` (vs policy.forbidden_cnae).
    cnaes: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    # capital_social (BRL) <- BDC AdditionalOutputData.CapitalRS. Insumo do
    #   cross-check de proporcionalidade (nao e gate).
    capital_social: Mapped[Decimal | None] = mapped_column(
        Numeric(precision=18, scale=2), nullable=True
    )

    # Optional canonical data from Receita Federal / Junta Comercial
    receita_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    junta_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<CreditDossierCompany cnpj={self.cnpj} role={self.role.value}>"
