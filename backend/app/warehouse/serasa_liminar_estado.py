"""lab_serasa_liminar_estado -- estado persistido da suspeita de liminar.

Maquina de estados por (tenant, CNPJ) da regra serasa_liminar_v1. Uma vez
que um CNPJ recebeu "NADA CONSTA" (supressao judicial de apontamentos),
ele entra aqui e NUNCA sai silenciosamente — so transiciona, e toda
transicao gera entrada em `decision_log` (sentinela, ver
app/modules/integracoes/services/serasa_liminar_sentinela.py).

Por que estado materializado (e nao replay do decision_log): o detector
roda a cada ingestao de consulta — precisa de lookup barato do estado
anterior. O log de transicoes continua no decision_log (append-only);
esta tabela e o snapshot corrente, mesmo padrao estado/trace do
playbook_run.

Estados:
    suspeita_ativa     ultima consulta veio com "NADA CONSTA"
    liminar_caida      era NADA CONSTA; nova consulta mostra negativos
                       (o que estava escondido voltou — alerta de credito)
    transicao_ambigua  era NADA CONSTA; nova consulta limpa SEM carimbo
                       (liminar expirou OU Serasa mudou o marcador — a
                       sentinela sistemica decide pelo agregado)

NAO usa mixin `Auditable`: e estado derivado interno (nao dado ingerido);
proveniencia vem dos raw_ids de evidencia + regra_version.
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SerasaLiminarEstado(Base):
    """Estado corrente da suspeita de liminar de um CNPJ (1 linha por CNPJ)."""

    __tablename__ = "lab_serasa_liminar_estado"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "cnpj", name="uq_lab_serasa_liminar_estado"
        ),
        # Carteira: "quais CNPJs estao em cada estado" (badge + sentinela).
        Index(
            "ix_lab_serasa_liminar_estado_tenant_estado",
            "tenant_id",
            "estado",
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
    cnpj: Mapped[str] = mapped_column(String(14), nullable=False)

    # Valores em serasa_liminar_sentinela.ESTADOS — String (nao SAEnum)
    # deliberado: enum nativo ja causou gotcha de leitura por NAME (PR#124).
    estado: Mapped[str] = mapped_column(String(32), nullable=False)

    # Primeira evidencia de "NADA CONSTA" (entrada na maquina de estados).
    primeira_evidencia_raw_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_serasa_pj_raw_relatorio.id", ondelete="RESTRICT"),
        nullable=False,
    )
    primeira_evidencia_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Ultima consulta AVALIADA pelo detector (qualquer classificacao) —
    # guarda de ordem cronologica em replay/backfill.
    ultima_consulta_raw_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("wh_serasa_pj_raw_relatorio.id", ondelete="RESTRICT"),
        nullable=False,
    )
    ultima_consulta_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    ultima_transicao_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    # Versao da regra que produziu o estado corrente (serasa_liminar_v1).
    regra_version: Mapped[str] = mapped_column(String(32), nullable=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
