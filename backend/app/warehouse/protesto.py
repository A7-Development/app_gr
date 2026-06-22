"""wh_protesto -- protestos canonicos (silver), ingeridos via Infosimples (IEPTB/CENPROT).

Granularidade (espelha o par header+filha do Serasa):
- WhProtestoConsulta: 1 linha por consulta (header). Escopo + contadores +
  valor total. 1:1 com a raw (wh_infosimples_raw_consulta).
- WhProtestoTitulo: N linhas por consulta -- 1 por titulo protestado
  (cartorio, cidade, uf, data, valor, credor quando disponivel).

Re-mapear do raw e idempotente via UQ(tenant_id, source_id), onde
source_id = str(raw_id) (consulta) / f"{raw_id}:{idx}" (titulo). Bug no mapper
-> corrige + re-roda mapper -> silver atualizado sem novo round-trip pago.

CONTEXTO REGULATORIO (Provimento CNJ 225/2026): a identificacao do credor
('cnpj_credor_afetado') foi murada para o monitoramento judicial; a consulta
publica NACIONAL NAO traz credor. O campo `credor` so se popula quando a fonte
devolver (tipicamente o detalhe por cartorio de SP) -- por isso e nullable.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class WhProtestoConsulta(Auditable, Base):
    """Header de uma consulta de protesto -- escopo + contadores agregados."""

    __tablename__ = "wh_protesto_consulta"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_protesto_consulta"
        ),
        # "Ultima consulta de protesto do documento X" -- base de dossie/risco.
        Index(
            "ix_wh_protesto_consulta_tenant_doc_consultado",
            "tenant_id",
            "documento",
            text("consultado_em DESC"),
        ),
        # Carteira: "quais documentos constam protesto".
        Index(
            "ix_wh_protesto_consulta_tenant_constam",
            "tenant_id",
            "documento",
            postgresql_where=text("constam_protestos = true"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    raw_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_infosimples_raw_consulta.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    documento: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    # 'cnpj' | 'cpf'
    documento_tipo: Mapped[str] = mapped_column(String(8), nullable=False)
    # 'nacional' (IEPTB/CENPROT, todos os estados, agregados + titulos sem
    # credor) | 'sp_detalhe' (detalhe por cartorio de SP, pode trazer credor).
    escopo: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    # Preenchido no escopo sp_detalhe (UF do detalhe). Nulo no nacional.
    uf_consultada: Mapped[str | None] = mapped_column(String(2), nullable=True)

    consultado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    constam_protestos: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    qtd_total: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0")
    )
    valor_total: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    # False quando a fonte so devolveu a 1a pagina (cenprot-sp:
    # retornou_todos_os_protestos_do_site=false) -> os titulos sao parciais vs
    # qtd_total. A view avisa (§14.6). Default true (IEPTB nao pagina).
    completo: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    # True quando ao menos 1 titulo desta consulta veio com credor identificado.
    com_credor: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    observacoes: Mapped[str | None] = mapped_column(Text, nullable=True)


class WhProtestoTitulo(Auditable, Base):
    """Um titulo protestado listado numa consulta (cartorio + valor + credor)."""

    __tablename__ = "wh_protesto_titulo"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_protesto_titulo"
        ),
        Index(
            "ix_wh_protesto_titulo_tenant_consulta",
            "tenant_id",
            "consulta_id",
        ),
        # "Titulos protestados com credor identificado" (pos-Provimento 225,
        # tipicamente so SP) -- sinal raro e valioso pra analise de credito.
        Index(
            "ix_wh_protesto_titulo_tenant_com_credor",
            "tenant_id",
            "consulta_id",
            postgresql_where=text("credor IS NOT NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    consulta_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_protesto_consulta.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    cartorio: Mapped[str | None] = mapped_column(Text, nullable=True)
    cartorio_numero: Mapped[str | None] = mapped_column(String(16), nullable=True)
    cidade: Mapped[str | None] = mapped_column(String(128), nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True, index=True)

    data_protesto: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_vencimento: Mapped[date | None] = mapped_column(Date, nullable=True)
    valor: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    # Cancelamento/quitacao por titulo (cenprot-sp). Nulos no IEPTB. valor_
    # quitacao>0 = protesto pago; valor_cancelamento>0 = cancelado.
    valor_cancelamento: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    valor_quitacao: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )

    # Credor / cedente / apresentante / portador do titulo. Nulo quando a fonte
    # nao identifica (regra do Provimento 225 na consulta publica nacional).
    credor: Mapped[str | None] = mapped_column(Text, nullable=True)
    documento_credor: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    especie: Mapped[str | None] = mapped_column(String(64), nullable=True)

    # Subset derivado pelo mapper (campos que nao cabem em colunas tipadas).
    # A fonte da verdade continua o raw em wh_infosimples_raw_consulta.payload.
    detalhe: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
