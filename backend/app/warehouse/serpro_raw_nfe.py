"""Bronze das consultas SERPRO NF-e -- 1 linha por SNAPSHOT distinto.

Grao: (tenant, chave, payload_sha256). Cada GET /v1/nfe/{chave} que retorna
um payload INEDITO (estado mudou: evento novo, cancelamento) vira uma linha;
reconsulta que devolve byte-a-byte o mesmo estado nao duplica (ON CONFLICT
DO NOTHING no dedup) — o historico de "quando consultei" pertence a tabela
de monitoracao (F3), nao ao bronze.

O payload preserva o JSON EXATO do gateway: o INSERT faz CAST(text AS jsonb)
direto do body da resposta, sem round-trip por float do Python (o gateway
pode emitir numeros grandes em notacao cientifica; jsonb guarda numeric de
precisao arbitraria).

Raw nao usa `Auditable` (excecao CLAUDE.md 14.1): proveniencia em colunas
proprias (`fetched_at`, `fetched_by_version`, `payload_sha256`).

Distincao de wh_nfe_raw_documento (landing fiscal): aquela e o XML da nota
no momento da AUTORIZACAO (documento estatico); esta e o ESTADO VIVO
consultado no SERPRO (protocolo atual + procEventoNFe).
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class SerproRawNfe(Base):
    """Snapshot cru de GET /v1/nfe/{chave} (nfeProc + procEventoNFe)."""

    __tablename__ = "wh_serpro_raw_nfe"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "chave_acesso",
            "payload_sha256",
            name="uq_wh_serpro_raw_nfe_dedup",
        ),
        Index("ix_wh_serpro_raw_nfe_tenant_chave", "tenant_id", "chave_acesso"),
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
    chave_acesso: Mapped[str] = mapped_column(String(44), nullable=False)

    # Resposta integral do gateway (nfeProc + procEventoNFe), byte-fiel.
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Triagem barata sem abrir o JSONB (imutaveis no fetch, como o payload).
    cstat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    qtd_eventos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Origem da consulta: "bancada" | "webhook" | "sweep" | "backfill".
    trigger: Mapped[str] = mapped_column(String(16), nullable=False)
    # Valor enviado no header x-request-tag (rateio na fatura SERPRO).
    request_tag: Mapped[str | None] = mapped_column(String(32), nullable=True)

    # Proveniencia raw (sem Auditable -- excecao 14.1)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fetched_by_version: Mapped[str] = mapped_column(String(32), nullable=False)
