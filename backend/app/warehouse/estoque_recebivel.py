"""wh_estoque_recebivel -- estoque de recebiveis cedidos ao FIDC.

Granularidade: 1 linha por recebivel (duplicata, NF, CCB, etc) cedido ao
FIDC numa data de referencia. Cada linha corresponde a uma cessao
individual — o nivel mais fino de operacao do FIDC de credito.

Fonte: QiTech /v2/queue/scheduler/report/fidc-estoque (assincrono via
job + callback). CSV separado por ';', locale BR (decimal ',', data
dd/mm/yyyy).

Dimensoes:
- **Fundo (FIDC)**: `fundo_doc` (CNPJ) + `fundo_nome`
- **Gestor**: quem administra o FIDC (ex: A7 Credit) — `gestor_doc/nome`
- **Originador**: empresa que originou os creditos — `originador_doc/nome`
- **Cedente**: empresa que vende ao FIDC — `cedente_doc/nome`
- **Sacado**: empresa que paga o titulo — `sacado_doc/nome`
- **Recebivel**: `seu_numero` + `numero_documento` + `tipo_recebivel`
- **Quando**: `data_referencia`

Fatos:
- Valores: nominal, presente, aquisicao, PDD
- Risco: faixa_pdd (A-H Bacen), situacao_recebivel (A Vencer/Vencido/...)
- Taxas: taxa_cessao, taxa_recebivel
- Datas operacionais: emissao, aquisicao, vencimento original/ajustada

UQ: `(tenant_id, source_id)` com source_id = "{docFundo}|{docCedente}|
{seuNumero}|{numeroDocumento}|{data_referencia}".

Indices criticos pra BI:
- (tenant, fundo_doc, data_ref) -- "estoque do fundo X em D"
- (tenant, fundo_doc, sacado_doc, data_ref) -- concentracao por sacado
- (tenant, fundo_doc, faixa_pdd, data_ref) -- distribuicao de risco
"""

from datetime import date
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    Date,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.auditable import Auditable


class EstoqueRecebivel(Auditable, Base):
    """1 recebivel cedido no estoque do FIDC numa data de referencia."""

    __tablename__ = "wh_estoque_recebivel"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_estoque_recebivel"
        ),
        Index(
            "ix_wh_estoque_recebivel_tenant_fundo_data",
            "tenant_id",
            "fundo_doc",
            "data_referencia",
        ),
        Index(
            "ix_wh_estoque_recebivel_tenant_fundo_sacado_data",
            "tenant_id",
            "fundo_doc",
            "sacado_doc",
            "data_referencia",
        ),
        Index(
            "ix_wh_estoque_recebivel_tenant_fundo_pdd",
            "tenant_id",
            "fundo_doc",
            "faixa_pdd",
            "data_referencia",
        ),
        Index(
            "ix_wh_estoque_recebivel_tenant_fundo_cedente",
            "tenant_id",
            "fundo_doc",
            "cedente_doc",
            "data_referencia",
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

    # ---- Quando ----
    data_referencia: Mapped[date] = mapped_column(
        Date, nullable=False, index=True
    )

    # ---- Fundo (FIDC) ----
    fundo_doc: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    fundo_nome: Mapped[str] = mapped_column(String(200), nullable=False)
    # `dataFundo` -- data de "constituicao/operacao" do fundo no relatorio.
    # Pode coincidir com data_referencia (dia da consulta) ou ser diferente.
    data_fundo: Mapped[date | None] = mapped_column(Date, nullable=True)

    # ---- Gestor / Originador / Cedente / Sacado ----
    gestor_doc: Mapped[str] = mapped_column(String(14), nullable=False)
    gestor_nome: Mapped[str] = mapped_column(String(200), nullable=False)

    originador_doc: Mapped[str] = mapped_column(String(14), nullable=False)
    originador_nome: Mapped[str] = mapped_column(String(200), nullable=False)

    cedente_doc: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    cedente_nome: Mapped[str] = mapped_column(String(200), nullable=False)

    sacado_doc: Mapped[str] = mapped_column(String(14), nullable=False, index=True)
    sacado_nome: Mapped[str] = mapped_column(String(200), nullable=False)

    # ---- Recebivel (identificacao) ----
    seu_numero: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    numero_documento: Mapped[str] = mapped_column(String(100), nullable=False)
    tipo_recebivel: Mapped[str] = mapped_column(String(50), nullable=False, index=True)

    # ---- Fatos: valores monetarios (BRL) ----
    valor_nominal: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valor_presente: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    valor_aquisicao: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # PDD = Provisao para Devedores Duvidosos. Pode ser zero (faixa A).
    valor_pdd: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # Faixa Bacen Resolucao 2682: A | B | C | D | E | F | G | H
    # Mantido como String(5) pra absorver eventuais novas categorias.
    faixa_pdd: Mapped[str] = mapped_column(String(5), nullable=False, index=True)

    # ---- Datas operacionais ----
    data_vencimento_original: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_vencimento_ajustada: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_emissao: Mapped[date | None] = mapped_column(Date, nullable=True)
    data_aquisicao: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Prazo em dias (corridos provavelmente; QiTech nao especifica claramente).
    prazo: Mapped[int] = mapped_column(Integer, nullable=False)
    # `prazoAnual` -- valor inteiro pequeno no sample (13 com prazo de 28 dias).
    # Provavelmente prazo medio ponderado anualizado em fracao de ano.
    # Mantido como Numeric(8,4) pra suportar fracao se vier no futuro.
    prazo_anual: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)

    # ---- Estado / Risco ----
    # "A Vencer" | "Vencido" | "Liquidado" | etc -- mantido string aberto.
    situacao_recebivel: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True
    )
    # Taxas decimais (ex.: 0,4692739943 = ~0,47% no sample). 10 decimais.
    taxa_cessao: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)
    taxa_recebivel: Mapped[Decimal] = mapped_column(Numeric(12, 8), nullable=False)

    # Coobrigacao = cedente garante credito? "SIM"/"NAO" no CSV.
    coobrigacao: Mapped[bool] = mapped_column(Boolean, nullable=False)
