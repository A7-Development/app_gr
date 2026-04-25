"""UnidadeAdministrativa -- cadastro primario do tenant.

Conceito: UA e a entidade operacional do tenant (FIDC, securitizadora,
gestora, factoring, consultoria). Tenant pode ter 1 (empresa unica) ou
varias (grupo). Pre-requisito pra muita coisa: BI consegue agrupar/filtrar
sem string-matching de CNPJ; integracoes referenciam UA por id; futuro
modulo de operacoes amarra contratos a uma UA especifica.

Por que UA primaria + UA do Bitfin separadas (CLAUDE.md secao 11.1, este
modulo `cadastros.UnidadeAdministrativa` vs `wh_dim_unidade_administrativa`):

1. Nem toda UA tem fonte externa. Pode ser UA em formacao, sem integracao
   ainda; UA com integracao so QiTech (sem Bitfin); UA puramente interna.
2. Multiplas fontes veem a mesma UA com IDs diferentes -- Bitfin chama
   "UA 5", QiTech identifica por CNPJ. Cadastro primario e o no central.
3. Operador edita: nome amigavel, status, tags. Nao deve ser ditado pelo ERP.
4. UA pertence ao tenant -- persiste atraves de mudanca de fonte.

Limitacao conhecida (Sprint UA, 2026-04-25):
    Por ora cada tenant tem 1 conjunto de credenciais QiTech via
    `tenant_source_config`. Como QiTech e "1 token por entidade", isso
    cobre apenas 1 UA por tenant na QiTech. Outras UAs do mesmo tenant
    podem existir aqui no cadastro mas nao terao integracao QiTech ate
    `tenant_source_config` ganhar coluna `unidade_administrativa_id`
    (Opcao 3.2 da discussao de 2026-04-25). Sem prazo definido --
    entrara quando 1o tenant cadastrar a 2a UA com QiTech.
"""

from __future__ import annotations

import enum
from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class TipoUnidadeAdministrativa(enum.StrEnum):
    """Tipos de UA reconhecidos no MVP.

    Lista intencionalmente curta -- expandir somente quando aparecer
    necessidade real (cada tipo novo demanda decisao de produto: que
    KPIs/regras/relatorios fazem sentido pra ele?).
    """

    FIDC = "fidc"
    CONSULTORIA = "consultoria"
    SECURITIZADORA = "securitizadora"
    FACTORING = "factoring"
    GESTORA = "gestora"


class UnidadeAdministrativa(Base):
    """UA primaria do tenant -- editavel via UI, independente de fonte."""

    __tablename__ = "cadastros_unidade_administrativa"
    __table_args__ = (
        # Nome unico por tenant. Evita duplicar "REALINVEST FIDC" duas vezes.
        UniqueConstraint(
            "tenant_id", "nome", name="uq_cadastros_ua_tenant_nome"
        ),
        # CNPJ unico por tenant *quando preenchido*. Partial index pra
        # deixar nullable + unique. Postgres-only -- ok porque MVP exige PG.
        Index(
            "uq_cadastros_ua_tenant_cnpj",
            "tenant_id",
            "cnpj",
            unique=True,
            postgresql_where=text("cnpj IS NOT NULL"),
        ),
        Index(
            "ix_cadastros_ua_tenant_ativa",
            "tenant_id",
            "ativa",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        # server_default permite INSERT direto via SQL bruto / MCP / scripts
        # ad-hoc sem precisar gerar UUID na aplicacao. ORM continua usando
        # `default=uuid4` (mais rapido — evita round-trip pro DB).
        server_default=text("gen_random_uuid()"),
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # -- Identidade -----------------------------------------------------
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    # CNPJ digits-only (14 chars). Opcional pra permitir UA em formacao
    # ou UA puramente interna sem CNPJ proprio.
    cnpj: Mapped[str | None] = mapped_column(String(14), nullable=True)
    tipo: Mapped[TipoUnidadeAdministrativa] = mapped_column(
        SAEnum(
            TipoUnidadeAdministrativa,
            name="tipo_unidade_administrativa",
            native_enum=False,
            length=32,
        ),
        nullable=False,
        index=True,
    )
    ativa: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )

    # -- Vinculos com fontes externas (opcionais) -----------------------
    # `bitfin_ua_id` referencia o ID inteiro da `wh_dim_unidade_administrativa`
    # (que veio do Bitfin). NAO e FK formal porque a tabela espelho e zona
    # warehouse com lifecycle proprio (truncate/refresh). Match e logico:
    # `bitfin_ua_id == wh_dim_unidade_administrativa.ua_id` no mesmo tenant.
    bitfin_ua_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # -- Audit ----------------------------------------------------------
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:
        return (
            f"<UnidadeAdministrativa id={self.id} "
            f"tenant={self.tenant_id} nome={self.nome!r} tipo={self.tipo.value}>"
        )
