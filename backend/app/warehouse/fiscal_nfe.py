"""NF-e coletada via landing zone fiscal (Strata Collector) -- raw + silver.

Tres camadas por documento (decisao Ricardo 2026-07-07, "consumir tudo"):

1. Bronze: o ZIP inteiro em `file_landing` + StorageBackend (imutavel, com PDFs).
2. `wh_nfe_raw_documento` (raw estruturado): o XML integral convertido em JSONB
   canonico, 1 linha por nfeProc -- "tudo consultavel" para Data Science sem
   modelagem previa. Subtree `Signature` omitida (assinatura digital, sem valor
   analitico; o XML original permanece no zip do bronze). `procEventoNFe` e
   DESCARTADO no ETL (eventos virao de outra origem -- decisao 2026-07-07).
3. `wh_nfe` + `wh_nfe_duplicata` (silver curado): conceitos >=95% de cobertura
   normalizados (regra da curadoria) -- nucleo de lastro/inadimplencia.

Raw nao usa `Auditable` (excecao CLAUDE.md 14.1): proveniencia em colunas
proprias. Silver usa `Auditable` (source_type=document:nfe).
"""

from datetime import date, datetime
from decimal import Decimal
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
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base
from app.shared.auditable import Auditable


class NfeRawDocumento(Base):
    """XML da NF-e integral em JSONB canonico (1 linha por nfeProc)."""

    __tablename__ = "wh_nfe_raw_documento"
    __table_args__ = (
        UniqueConstraint("tenant_id", "chave_acesso", name="uq_wh_nfe_raw_tenant_chave"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chave_acesso: Mapped[str] = mapped_column(String(44), nullable=False)
    schema_versao: Mapped[str | None] = mapped_column(String(8), nullable=True)
    # XML -> JSONB canonico: tag repetida vira lista, atributo vira "@attr",
    # texto de folha vira valor string. Signature omitida.
    documento: Mapped[dict] = mapped_column(JSONB, nullable=False)

    # Proveniencia raw (sem Auditable -- excecao 14.1)
    file_landing_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("file_landing.id", ondelete="SET NULL"),
        nullable=True,
    )
    nome_arquivo_xml: Mapped[str] = mapped_column(String(512), nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    fetched_by_version: Mapped[str] = mapped_column(String(32), nullable=False)


class Nfe(Auditable, Base):
    """Silver curado da NF-e -- nucleo de lastro (conceitos >=95% normalizados)."""

    __tablename__ = "wh_nfe"
    __table_args__ = (
        UniqueConstraint("tenant_id", "chave_acesso", name="uq_wh_nfe_tenant_chave"),
        Index("ix_wh_nfe_tenant_emitente", "tenant_id", "emitente_documento"),
        Index("ix_wh_nfe_tenant_destinatario", "tenant_id", "destinatario_documento"),
        Index("ix_wh_nfe_tenant_emissao", "tenant_id", "data_emissao"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    raw_documento_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_nfe_raw_documento.id", ondelete="RESTRICT"),
        nullable=False,
    )

    chave_acesso: Mapped[str] = mapped_column(String(44), nullable=False)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    serie: Mapped[int | None] = mapped_column(Integer, nullable=True)
    modelo: Mapped[str | None] = mapped_column(String(2), nullable=True)
    natureza_operacao: Mapped[str | None] = mapped_column(String(120), nullable=True)
    data_emissao: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # tpNF: 0=entrada 1=saida
    tipo_operacao: Mapped[str | None] = mapped_column(String(1), nullable=True)
    # finNFe: 1=normal 2=complementar 3=ajuste 4=devolucao
    finalidade: Mapped[str | None] = mapped_column(String(1), nullable=True)

    emitente_documento: Mapped[str] = mapped_column(String(14), nullable=False)
    emitente_nome: Mapped[str | None] = mapped_column(String(120), nullable=True)
    emitente_uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    emitente_municipio: Mapped[str | None] = mapped_column(String(80), nullable=True)
    destinatario_documento: Mapped[str | None] = mapped_column(String(14), nullable=True)
    # pj|pf (CNPJ vs CPF no XML)
    destinatario_tipo_pessoa: Mapped[str | None] = mapped_column(String(2), nullable=True)
    destinatario_nome: Mapped[str | None] = mapped_column(String(120), nullable=True)
    destinatario_uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    destinatario_municipio: Mapped[str | None] = mapped_column(String(80), nullable=True)

    valor_produtos: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    valor_frete: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    valor_desconto: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    valor_total: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
    valor_tributos: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)

    modalidade_frete: Mapped[str | None] = mapped_column(String(1), nullable=True)
    # tPag do primeiro detPag (01=dinheiro, 15=boleto...)
    meio_pagamento: Mapped[str | None] = mapped_column(String(2), nullable=True)
    numero_fatura: Mapped[str | None] = mapped_column(String(60), nullable=True)
    valor_fatura_liquido: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)

    # Transporte (<transp>): transportadora + veiculo (1:1 com a nota).
    transportadora_documento: Mapped[str | None] = mapped_column(String(14), nullable=True)
    transportadora_nome: Mapped[str | None] = mapped_column(String(120), nullable=True)
    veiculo_placa: Mapped[str | None] = mapped_column(String(8), nullable=True)
    veiculo_uf: Mapped[str | None] = mapped_column(String(2), nullable=True)

    # Autorizacao SEFAZ (protNFe): nota nao autorizada NAO e lastro valido.
    cstat: Mapped[int | None] = mapped_column(Integer, nullable=True)
    autorizada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    protocolo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    data_autorizacao: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class NfeDuplicata(Base):
    """Duplicata da NF-e (<cobr><dup>) -- O elo nota <-> titulo do lastro."""

    __tablename__ = "wh_nfe_duplicata"
    __table_args__ = (
        UniqueConstraint("nfe_id", "numero", name="uq_wh_nfe_duplicata_nfe_numero"),
        Index("ix_wh_nfe_duplicata_tenant_venc", "tenant_id", "vencimento"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nfe_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_nfe.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    numero: Mapped[str] = mapped_column(String(60), nullable=False)
    vencimento: Mapped[date | None] = mapped_column(Date, nullable=True)
    valor: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)


class NfeItem(Base):
    """Item/produto da NF-e (<det><prod>) -- o que foi vendido, linha a linha."""

    __tablename__ = "wh_nfe_item"
    __table_args__ = (
        UniqueConstraint("nfe_id", "n_item", name="uq_wh_nfe_item_nfe_n"),
        Index("ix_wh_nfe_item_tenant_nfe", "tenant_id", "nfe_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    nfe_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_nfe.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # nItem: posicao do item na nota (1-based).
    n_item: Mapped[int] = mapped_column(Integer, nullable=False)
    codigo: Mapped[str | None] = mapped_column(String(60), nullable=True)
    descricao: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ncm: Mapped[str | None] = mapped_column(String(8), nullable=True)
    cfop: Mapped[str | None] = mapped_column(String(4), nullable=True)
    ean: Mapped[str | None] = mapped_column(String(14), nullable=True)
    quantidade: Mapped[Decimal | None] = mapped_column(Numeric(15, 4), nullable=True)
    unidade: Mapped[str | None] = mapped_column(String(6), nullable=True)
    # vUnCom tem ate 10 casas decimais no leiaute NF-e.
    valor_unitario: Mapped[Decimal | None] = mapped_column(Numeric(21, 10), nullable=True)
    valor_total: Mapped[Decimal | None] = mapped_column(Numeric(15, 2), nullable=True)
