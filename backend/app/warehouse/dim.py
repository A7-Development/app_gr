"""Dimensoes canonicas do warehouse (calendario + classificacao DRE)."""

from datetime import date
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class DimMes(Auditable, Base):
    """Calendario de competencias mensais.

    Fonte: `ANALYTICS.DimMes`.
    """

    __tablename__ = "wh_dim_mes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "mes_ano", name="uq_wh_dim_mes"),
        UniqueConstraint("tenant_id", "source_id", name="uq_wh_dim_mes_source"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    mes_ano: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    ano: Mapped[int] = mapped_column(Integer, nullable=False)
    mes: Mapped[int] = mapped_column(Integer, nullable=False)
    trimestre: Mapped[int] = mapped_column(Integer, nullable=False)
    semestre: Mapped[int] = mapped_column(Integer, nullable=False)
    ano_mes_texto: Mapped[str] = mapped_column(String(7), nullable=False)
    mes_nome: Mapped[str] = mapped_column(String(9), nullable=False)


class DimDreClassificacao(Auditable, Base):
    """Hierarquia de classificacao do DRE.

    Fonte: `ANALYTICS.DREClassificacao`.
    """

    __tablename__ = "wh_dim_dre_classificacao"
    __table_args__ = (
        UniqueConstraint("tenant_id", "classificacao_id", name="uq_wh_dim_dre_classificacao"),
        UniqueConstraint("tenant_id", "source_id", name="uq_wh_dim_dre_classificacao_source"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    classificacao_id: Mapped[int] = mapped_column(Integer, nullable=False)
    fonte: Mapped[str] = mapped_column(String(30), nullable=False)
    categoria: Mapped[str] = mapped_column(String(200), nullable=False)
    grupo_dre: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    subgrupo: Mapped[str] = mapped_column(String(100), nullable=False)
    ordem_grupo: Mapped[int] = mapped_column(Integer, nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class DimProduto(Auditable, Base):
    """Dimensao de Produto.

    Fonte: `Bitfin.Produto`. Serve para:
    - Mapear sigla extraida de `Operacao.modalidade` (ex.: 'FAT-DM' -> 'FAT')
      para o nome amigavel exibido na UI (ex.: 'Faturização').
    - Expor metadados de produto reutilizaveis (tipo de contrato, se e
      produto de risco) para filtros e analises futuras.

    `sigla` aparece em `wh_operacao.modalidade` como prefixo antes do `-`.
    `tipo_recebivel` fica fora dessa dim — cada linha da `Operacao.modalidade`
    cobre combinacao sigla x tipo, mas a entidade canonica (Bitfin.Produto)
    so conhece siglas.
    """

    __tablename__ = "wh_dim_produto"
    __table_args__ = (
        UniqueConstraint("tenant_id", "produto_id", name="uq_wh_dim_produto"),
        UniqueConstraint("tenant_id", "sigla", name="uq_wh_dim_produto_sigla"),
        UniqueConstraint("tenant_id", "source_id", name="uq_wh_dim_produto_source"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    produto_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    sigla: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    # Metadados opcionais (podem virar filtros/facets no futuro).
    tipo_de_contrato: Mapped[str | None] = mapped_column(String(100), nullable=True)
    produto_de_risco: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class DimUnidadeAdministrativa(Auditable, Base):
    """Dimensao de Unidade Administrativa (UA).

    Fonte: `Bitfin.UnidadeAdministrativa`. Serve para:
    - Mapear `wh_operacao.unidade_administrativa_id` -> nome amigavel em
      filtros/graficos BI (sem round-trip ao ERP em request-time).
    - Preparar outros L2 (Carteira, Fluxo) que tambem segmentam por UA.

    O campo `ua_id` corresponde ao `UnidadeAdministrativaId` no Bitfin.
    O `nome` vem de `Alias` (o campo display no ERP). `classe` mantido como
    metadado (Bitfin.UnidadeAdministrativa.Classe).
    """

    __tablename__ = "wh_dim_unidade_administrativa"
    __table_args__ = (
        UniqueConstraint("tenant_id", "ua_id", name="uq_wh_dim_ua"),
        UniqueConstraint("tenant_id", "source_id", name="uq_wh_dim_ua_source"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    ua_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    nome: Mapped[str] = mapped_column(String(200), nullable=False)
    ativa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    classe: Mapped[str | None] = mapped_column(String(50), nullable=True)
