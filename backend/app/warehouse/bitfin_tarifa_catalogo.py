"""wh_bitfin_tarifa_catalogo -- catalogo de tarifas/encargos do Bitfin (dim).

Espelho de `UNLTD_<cliente>.dbo.OrganizacaoTarifa` (template da organizacao).
Cada item = (Categoria, Descricao) com um `Tipo` nativo do Bitfin:
    Tipo 1 = tarifa fixa (TED, Registros, "Tarifa de X", ...)
    Tipo 2 = encargo variavel/calculado (Desagio, Juros, Multa, Ad Valorem,
             Imposto, Custas, ...)

Serve a classificacao por NATUREZA do DRE (ver wh_bitfin_dre_natureza_rule):
a `Descricao` aqui e vocabulario CONTROLADO de catalogo, nao texto livre --
e o ancoradouro que substitui a heuristica de keyword. Tambem permite
detectar item de catalogo NOVO (presente aqui, ausente nas regras de
natureza -> flag de "nao classificado").

Per-tenant: cada tenant Bitfin tem seu proprio OrganizacaoTarifa. Ingerido
pelo adapter (sync_bitfin_tarifa_catalogo); proveniencia em colunas proprias
(camada de referencia ingerida, nao usa Auditable).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WhBitfinTarifaCatalogo(Base):
    """Item do catalogo de tarifas Bitfin (OrganizacaoTarifa), por tenant."""

    __tablename__ = "wh_bitfin_tarifa_catalogo"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "categoria",
            "descricao",
            name="uq_wh_bitfin_tarifa_catalogo",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    categoria: Mapped[str] = mapped_column(String(50), nullable=False)
    descricao: Mapped[str] = mapped_column(String(80), nullable=False)
    # Tipo nativo do Bitfin: 1 = tarifa fixa, 2 = encargo variavel.
    tipo: Mapped[int] = mapped_column(Integer, nullable=False)
    comissionada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Proveniencia (camada de referencia ingerida).
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    fetched_by_version: Mapped[str] = mapped_column(String(30), nullable=False)
