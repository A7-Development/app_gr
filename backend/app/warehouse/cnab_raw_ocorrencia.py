"""wh_cnab_raw_ocorrencia -- registros de detalhe CNAB (raw estruturado).

Segunda camada do bronze de cobranca (ver `wh_cnab_raw_arquivo`). Aqui cada
row e UM registro de detalhe do arquivo CNAB, ja quebrado em campos nomeados
(snake_case) no `payload` JSONB -- mas **sem normalizacao semantica**: o
codigo de ocorrencia continua cru (ex.: "06"), o valor continua no formato do
arquivo, datas no formato CNAB. A traducao "codigo de ocorrencia -> estado",
a resolucao de vigencia (ultima instrucao por titulo) e o casamento de tipos
acontecem no mapper que popula `wh_boleto`.

A separacao arquivo/ocorrencia da: replay (reparsear sem rebuscar o arquivo),
auditoria (qual linha de qual arquivo gerou qual boleto) e observabilidade
(quantos registros por arquivo).

NAO usa `Auditable` (raw e a fonte). Proveniencia herdada do arquivo pai via
`arquivo_id` + `fetched_at`/`fetched_by_version` proprios.
"""

from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CnabRawOcorrencia(Base):
    """Um registro de detalhe CNAB, raw estruturado em JSONB."""

    __tablename__ = "wh_cnab_raw_ocorrencia"
    __table_args__ = (
        # Acesso canonico: todas as ocorrencias de um arquivo, em ordem.
        Index(
            "ix_wh_cnab_raw_ocorrencia_arquivo_linha",
            "arquivo_id",
            "linha_num",
        ),
        Index("ix_wh_cnab_raw_ocorrencia_tenant", "tenant_id"),
    )

    id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid4
    )
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Arquivo CNAB de origem. CASCADE: reprocessar/limpar o arquivo limpa as
    # ocorrencias junto.
    arquivo_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_cnab_raw_arquivo.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Denormalizado do arquivo pai para filtro rapido sem join.
    banco: Mapped[str] = mapped_column(String(20), nullable=False)
    tipo_arquivo: Mapped[str] = mapped_column(String(10), nullable=False)

    # Posicao do registro dentro do arquivo (1-based). Auditoria/replay.
    linha_num: Mapped[int] = mapped_column(Integer, nullable=False)
    # Tipo/segmento do registro CNAB (ex.: "1" no CNAB400, "T"/"U" no 240).
    tipo_registro: Mapped[str] = mapped_column(String(20), nullable=False)

    # Campos do registro 1:1, snake_case, SEM normalizacao semantica. O mapper
    # de silver le daqui. Chaves tipicas: numero_documento, nosso_numero,
    # sacado_nome, sacado_documento, valor, vencimento, codigo_ocorrencia,
    # data_ocorrencia, valor_pago, data_pagamento.
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)

    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    fetched_by_version: Mapped[str] = mapped_column(String(128), nullable=False)
