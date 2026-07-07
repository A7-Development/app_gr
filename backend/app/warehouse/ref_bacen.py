"""ref_bacen_* -- referencia publica de instituicoes e agencias bancarias (Bacen).

Dicionario geografico/institucional do Sentinela CNAB (F2): traduz o par
(banco, agencia) que vem no retorno CNAB (posicoes 166-173) em instituicao,
segmento e praca (municipio/UF) -- INDEPENDENTE do cadastro de agencias do ERP
(que descarta a agencia quando nao a conhece; caso MFL 2026-07-07).

Fontes (dados abertos do Bacen, sem tenant/credencial):
  - Participantes do STR (CSV diario): ISPB, nome, codigo Compe do banco.
  - Informes_Agencias (API Olinda, mensal): agencias de bancos com municipio.

Tabelas GLOBAIS -- sem tenant_id (excecao da regra multi-tenant, CLAUDE.md
sec 10: dado publico de referencia, como `source_catalog`). NAO usam
`Auditable` (sao a propria fonte de referencia): proveniencia em colunas
proprias (fetched_at, fetched_by_version).

Politica de refresh: UPSERT sem delete -- agencia que sai do snapshot do Bacen
(fechada/renumerada) PERMANECE aqui, porque o acervo CNAB historico ainda
referencia agencias extintas. `posicao` marca o snapshot em que a linha foi
vista pela ultima vez.
"""

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Segmentos canonicos (heuristica sobre o nome extenso do STR; refinamento via
# BcBase/EntidadesSupervisionadas e follow-up). Dirigem o classificador de
# canal em `adapters/cobranca/canal.py`.
SEGMENTO_BANCO = "banco"
SEGMENTO_BANCO_COOPERATIVO = "banco_cooperativo"  # Bancoob 756, Sicredi 748, Ailos 085
SEGMENTO_COOPERATIVA = "cooperativa"
SEGMENTO_IP = "ip"  # instituicao de pagamento
SEGMENTO_SCD = "scd"  # sociedade de credito direto
SEGMENTO_FINANCEIRA = "financeira"
SEGMENTO_OUTROS = "outros"


class RefBacenInstituicao(Base):
    """Instituicao participante do STR, chaveada pelo codigo Compe (o codigo
    de banco que trafega no CNAB)."""

    __tablename__ = "ref_bacen_instituicao"

    # Codigo Compe do banco ("237", "756", "323"). PK: e a chave de join com o
    # CNAB. Instituicoes sem codigo ("n/a" no STR) nao entram -- inalcancaveis
    # via CNAB.
    codigo_compe: Mapped[str] = mapped_column(String(3), primary_key=True)
    ispb: Mapped[str] = mapped_column(String(8), nullable=False, index=True)
    nome_reduzido: Mapped[str] = mapped_column(String(120), nullable=False)
    nome_extenso: Mapped[str | None] = mapped_column(String(255), nullable=True)
    participa_compe: Mapped[bool] = mapped_column(Boolean, nullable=False)
    segmento: Mapped[str] = mapped_column(String(30), nullable=False)
    # De onde veio o segmento ("heuristica_nome" | "bcbase" | "manual").
    segmento_fonte: Mapped[str] = mapped_column(String(20), nullable=False)
    inicio_operacao: Mapped[date | None] = mapped_column(Date, nullable=True)

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_by_version: Mapped[str] = mapped_column(String(64), nullable=False)


class RefBacenAgencia(Base):
    """Agencia bancaria com praca (municipio/UF), chaveada por (banco, agencia)
    no formato do CNAB (agencia com 5 digitos, zeros a esquerda)."""

    __tablename__ = "ref_bacen_agencia"
    __table_args__ = (
        UniqueConstraint(
            "banco_compe", "agencia_codigo", name="uq_ref_bacen_agencia_banco_ag"
        ),
        Index("ix_ref_bacen_agencia_municipio", "municipio_ibge"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    # Codigo Compe do banco dono da agencia (join CNAB). Derivado no ETL:
    # Informes_Agencias da o CnpjBase; o STR liga CnpjBase(=ISPB) -> compe.
    banco_compe: Mapped[str] = mapped_column(String(3), nullable=False)
    cnpj_base: Mapped[str] = mapped_column(String(8), nullable=False)
    nome_if: Mapped[str] = mapped_column(String(255), nullable=False)
    # Codigo da agencia normalizado a 5 digitos zero-padded ("03372"), como o
    # CNAB entrega nas posicoes 169-173.
    agencia_codigo: Mapped[str] = mapped_column(String(5), nullable=False)
    nome_agencia: Mapped[str | None] = mapped_column(String(255), nullable=True)
    municipio: Mapped[str | None] = mapped_column(String(120), nullable=True)
    municipio_ibge: Mapped[int | None] = mapped_column(Integer, nullable=True)
    uf: Mapped[str | None] = mapped_column(String(2), nullable=True)
    data_inicio: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Data-posicao do snapshot Bacen em que a linha foi vista pela ultima vez.
    # Linha ausente de snapshots novos NAO e apagada (CNAB historico).
    posicao: Mapped[date | None] = mapped_column(Date, nullable=True)

    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    fetched_by_version: Mapped[str] = mapped_column(String(64), nullable=False)
