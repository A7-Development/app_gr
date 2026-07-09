"""wh_boleto_evento -- timeline de eventos do boleto (silver).

Fonte da verdade da carteira de cobranca. Cada row e UM evento na vida de um
boleto no banco (entrada, liquidacao, baixa, prorrogacao, abatimento, protesto,
cartorio, tarifa...), decodificado a partir do registro de detalhe CNAB
(`wh_cnab_raw_ocorrencia`). 1:1 com o bronze: cada ocorrencia decodifica num
evento.

O estado VIGENTE de cada boleto (tabela `wh_boleto`) e uma PROJECAO desta
timeline -- o "saldo" do "extrato". A timeline e o "extrato": preserva a
historia inteira para auditoria (§14) e permite reconstruir a posicao em
qualquer data (fold dos eventos ate X).

`efeito_estado` dirige o fold:
  - "abre"     entrada confirmada -> boleto passa a ativo
  - "fecha"    liquidacao/baixa   -> boleto sai de ativo
  - "modifica" prorrogacao/abatimento/alteracao -> mantem estado, muda atributo
  - "rejeita"  entrada rejeitada  -> nunca ficou ativo
  - "info"     tarifa/confirmacao de instrucao -> neutro (nao move estado)

Proveniencia (§14) por colunas proprias (como o bronze): `arquivo_id` +
`ocorrencia_id` (lineage exato ate a linha CNAB) + `decoded_by_version`. NAO
usa `Auditable` -- e projecao decodificada do bronze, nao ingestao de fonte.

Chave de cruzamento com a carteira: `numero_documento` <-> `wh_titulo.numero`.
Chave de identidade do boleto no banco (fold): `nosso_numero`.
"""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

# Origem do evento (qual fluxo CNAB o gerou).
ORIGEM_RETORNO = "retorno"  # o que o banco confirma (verdade do estado)
ORIGEM_REMESSA = "remessa"  # o que enviamos (intencao -- futuro)
ORIGEM_POSICAO = "posicao"  # snapshot de posicao do banco (ancora -- futuro)


class BoletoEvento(Base):
    """Um evento na timeline de um boleto (decodificado do CNAB)."""

    __tablename__ = "wh_boleto_evento"
    __table_args__ = (
        # Idempotencia: um evento por ocorrencia bronze. Re-decode faz upsert.
        UniqueConstraint(
            "tenant_id", "ocorrencia_id", name="uq_wh_boleto_evento_ocorrencia"
        ),
        # Fold + drill "historia do titulo": eventos de um boleto em ordem.
        Index(
            "ix_wh_boleto_evento_fold",
            "tenant_id",
            "banco_origem",
            "nosso_numero",
            "data_ocorrencia",
        ),
        # Escopo por UA.
        Index("ix_wh_boleto_evento_ua", "tenant_id", "ua_id"),
        # Cruzamento por numero do documento.
        Index(
            "ix_wh_boleto_evento_numero",
            "tenant_id",
            "numero_documento",
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

    # Banco cobrador (BANCO_* em cnab_raw_arquivo).
    banco_origem: Mapped[str] = mapped_column(String(20), nullable=False)

    # UA (Unidade Administrativa) -- escopo da analise. Resolvida do header do
    # arquivo CNAB (nome da empresa) no decode. Nullable ate o mapeamento
    # empresa->UA cobrir o arquivo.
    ua_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ua_nome: Mapped[str | None] = mapped_column(String(200), nullable=True)

    # Identidade do boleto no banco (chave do fold) + cruzamento com carteira.
    nosso_numero: Mapped[str] = mapped_column(String(50), nullable=False)
    numero_documento: Mapped[str] = mapped_column(String(50), nullable=False)
    # Identidade resolvida do titulo (Bitfin TituloId, via wh_titulo). O
    # nosso_numero COLIDE entre cedentes (decisao Ricardo 2026-07-09: usar
    # ID unico); resolvido por numero_documento -> titulo, desempate por
    # valor. Espinha de identidade — join limpo evento->titulo->cedente.
    titulo_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Sacado (confirmacao do vinculo).
    sacado_documento: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sacado_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Evento: codigo CNAB cru + decodificacao canonica.
    codigo_ocorrencia: Mapped[str] = mapped_column(String(10), nullable=False)
    tipo_evento: Mapped[str] = mapped_column(String(40), nullable=False)
    efeito_estado: Mapped[str] = mapped_column(String(12), nullable=False)

    data_ocorrencia: Mapped[date] = mapped_column(Date, nullable=False)
    # Atributos do boleto NO MOMENTO do evento (mudam com prorrogacao/abatimento).
    data_vencimento: Mapped[date | None] = mapped_column(Date, nullable=True)
    valor_titulo: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 4), nullable=True
    )
    valor_pago: Mapped[Decimal | None] = mapped_column(Numeric(18, 4), nullable=True)
    data_pagamento: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Onde o boleto foi pago (so em liquidacoes; None nos demais eventos).
    # FONTE PRIMARIA da analise de praca/antifraude (Sentinela CNAB): vem das
    # posicoes 166-168/169-173/296-301 do retorno CNAB400 -- independe do
    # cadastro de agencias do ERP. banco = codigo Febraban ("756"); agencia =
    # codigo sem digito, zeros a esquerda preservados ("07723").
    banco_pagador: Mapped[str | None] = mapped_column(String(3), nullable=True)
    agencia_pagadora: Mapped[str | None] = mapped_column(String(10), nullable=True)
    data_credito: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Fluxo CNAB de origem (ORIGEM_*).
    origem: Mapped[str] = mapped_column(String(12), nullable=False)

    # Lineage (§14): arquivo CNAB + linha exata.
    arquivo_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_cnab_raw_arquivo.id", ondelete="CASCADE"),
        nullable=False,
    )
    ocorrencia_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_cnab_raw_ocorrencia.id", ondelete="CASCADE"),
        nullable=False,
    )

    decoded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    decoded_by_version: Mapped[str] = mapped_column(String(128), nullable=False)
