"""wh_entidade + wh_entidade_fonte + wh_entidade_papel — party model canonico.

A ancora de identidade do warehouse: **1 linha por (tenant, documento)**,
onde documento e o CPF/CNPJ normalizado (11/14 digitos). Cedente, sacado,
avalista, socio e fornecedor sao PAPEIS (`wh_entidade_papel`), nao cadastros
separados — o mesmo CNPJ acumula N papeis e as lentes de risco consolidam
atraves deles.

Hierarquia PJ derivada do proprio documento (deterministica, sem curadoria):
`documento_raiz` (8 dig.) identifica a pessoa juridica; filiais compartilham
a raiz. Consolidacao por raiz e LENTE DE CONSULTA (GROUP BY documento_raiz),
nunca merge fisico — cada estabelecimento mantem sua linha (endereco,
titulos e ocorrencias sao fatos por estabelecimento).

`wh_entidade_fonte` e o crosswalk de resolucao de identidade multi-fonte:
(source_type, id na fonte) -> entidade canonica. Linhas com
`entidade_id IS NULL` sao a QUARENTENA (documento ausente/invalido na
fonte) — visivel, nunca descartada em silencio.

Ver app/shared/documento.py para a politica de normalizacao.
"""

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
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.core.enums import EntidadePapel, SourceType, TipoPessoa
from app.shared.auditable import Auditable


class WhEntidade(Auditable, Base):
    """Entidade canonica (pessoa fisica ou juridica) por tenant."""

    __tablename__ = "wh_entidade"
    __table_args__ = (
        UniqueConstraint("tenant_id", "documento", name="uq_wh_entidade_documento"),
        Index("ix_wh_entidade_tenant_raiz", "tenant_id", "documento_raiz"),
        Index("ix_wh_entidade_tenant_grupo", "tenant_id", "grupo_economico_source_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # --- Identidade (ver app/shared/documento.py) ---
    documento: Mapped[str] = mapped_column(String(14), nullable=False)
    tipo_pessoa: Mapped[TipoPessoa] = mapped_column(
        SAEnum(
            TipoPessoa,
            name="tipo_pessoa",
            native_enum=False,
            length=4,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )
    # PJ: raiz (8 dig.) = pessoa juridica; filial_numero "0001" = matriz.
    # PF: os tres ficam NULL.
    documento_raiz: Mapped[str | None] = mapped_column(String(8), nullable=True)
    filial_numero: Mapped[str | None] = mapped_column(String(4), nullable=True)
    is_matriz: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # --- Cadastro ---
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    cnae_chave: Mapped[str | None] = mapped_column(String(10), nullable=True)
    cnae_denominacao: Mapped[str | None] = mapped_column(String(255), nullable=True)
    porte: Mapped[str | None] = mapped_column(String(50), nullable=True)
    data_constituicao: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    em_recuperacao_judicial: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    data_recuperacao_judicial: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # --- Endereco (por estabelecimento — filial tem endereco proprio) ---
    logradouro: Mapped[str | None] = mapped_column(String(255), nullable=True)
    endereco_numero: Mapped[str | None] = mapped_column(String(30), nullable=True)
    complemento: Mapped[str | None] = mapped_column(String(255), nullable=True)
    bairro: Mapped[str | None] = mapped_column(String(120), nullable=True)
    localidade: Mapped[str | None] = mapped_column(String(120), nullable=True)
    estado: Mapped[str | None] = mapped_column(String(2), nullable=True)
    cep: Mapped[str | None] = mapped_column(String(8), nullable=True)
    pais: Mapped[str | None] = mapped_column(String(60), nullable=True)
    endereco_verificado: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # --- Grupo economico (referencia curada da fonte; membros detalhados
    # em wh_grupo_economico_membro) ---
    grupo_economico_source_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Metadados da fonte ---
    data_cadastro_fonte: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WhEntidadeFonte(Base):
    """Crosswalk de identidade: (fonte, id na fonte) -> entidade canonica.

    Proveniencia em colunas proprias (tabela de mapeamento, nao de fato —
    mesmo racional do wh_bitfin_entidade). `entidade_id IS NULL` = quarentena
    (documento ausente/invalido), com motivo legivel.
    """

    __tablename__ = "wh_entidade_fonte"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_type", "source_entity_id", name="uq_wh_entidade_fonte"
        ),
        Index("ix_wh_entidade_fonte_entidade", "tenant_id", "entidade_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source_type: Mapped[SourceType] = mapped_column(
        SAEnum(SourceType, name="source_type", native_enum=False, length=64),
        nullable=False,
    )
    # Id do registro na fonte (Bitfin: EntidadeId; bureaus: o proprio documento).
    source_entity_id: Mapped[str] = mapped_column(String(64), nullable=False)

    entidade_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_entidade.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Quarentena: o que veio da fonte + por que nao resolveu.
    documento_bruto: Mapped[str | None] = mapped_column(String(50), nullable=True)
    motivo_quarentena: Mapped[str | None] = mapped_column(String(100), nullable=True)

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_by_version: Mapped[str] = mapped_column(String(30), nullable=False)


class WhEntidadePapel(Auditable, Base):
    """Papel que uma entidade exerce na operacao (fato, nao subtipo).

    source_id (Auditable) = id do papel na fonte (Bitfin: ClienteId para
    cedente, SacadoId para sacado) — e a ponte para os fatos existentes
    (`wh_operacao.cedente_id`, `wh_titulo.sacado_id`) sem alterar essas
    tabelas.
    """

    __tablename__ = "wh_entidade_papel"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_type", "papel", "source_id", name="uq_wh_entidade_papel"
        ),
        Index("ix_wh_entidade_papel_entidade", "tenant_id", "entidade_id", "papel"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    entidade_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_entidade.id", ondelete="CASCADE"),
        nullable=False,
    )
    papel: Mapped[EntidadePapel] = mapped_column(
        SAEnum(
            EntidadePapel,
            name="entidade_papel",
            native_enum=False,
            length=16,
            values_callable=lambda e: [m.value for m in e],
        ),
        nullable=False,
    )

    # Estado do papel na fonte (Bitfin Cliente.Status/Situacao; Sacado nao tem).
    status_fonte: Mapped[str | None] = mapped_column(String(50), nullable=True)
    data_cadastro_fonte: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WhGrupoEconomico(Auditable, Base):
    """Grupo economico curado na fonte (Bitfin GrupoEconomico)."""

    __tablename__ = "wh_grupo_economico"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_type", "source_id", name="uq_wh_grupo_economico"
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    segmento: Mapped[str | None] = mapped_column(String(120), nullable=True)
    quantidade_membros: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_cadastro_fonte: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class WhGrupoEconomicoMembro(Auditable, Base):
    """Vinculo entidade <-> grupo economico (aresta do grafo).

    source_id (Auditable) = "<grupo_id>:<entidade_id_fonte>" — chave composta
    da aresta na fonte. `entidade_id` resolvido via crosswalk; NULL quando a
    entidade membro esta em quarentena (aresta preservada para auditoria).
    """

    __tablename__ = "wh_grupo_economico_membro"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_type", "source_id", name="uq_wh_grupo_economico_membro"
        ),
        Index("ix_wh_grupo_membro_entidade", "tenant_id", "entidade_id"),
        Index("ix_wh_grupo_membro_grupo", "tenant_id", "grupo_economico_id"),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    grupo_economico_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_grupo_economico.id", ondelete="CASCADE"),
        nullable=False,
    )
    entidade_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_entidade.id", ondelete="SET NULL"),
        nullable=True,
    )
    vinculo: Mapped[str | None] = mapped_column(String(120), nullable=True)
    data_cadastro_fonte: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
