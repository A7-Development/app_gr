"""AgentCredential: token de maquina do Strata Collector (1 linha por agente).

O agente instalado no servidor do cliente se autentica no File Gateway
(`/api/v1/filedrop/*`) com um token opaco gerado aqui. Guardamos APENAS o
sha256 do token (como API key) — o plaintext e exibido uma unica vez na
criacao. Revogacao = `revoked_at` (1 UPDATE, sem mexer em IAM/VPN).

`watch_config` e a politica de coleta (pastas vigiadas -> source_label),
devolvida ao agente no `/ping`: o agente e burro, a politica mora no servidor.
Shape:
    {
      "scan_interval_minutes": 5,
      "watches": [
        {"path": "C:/Bitfin/Retorno", "glob": "*", "source_label": "cobranca_cnab"},
        {"path": "C:/Bitfin/XML",     "glob": "*.zip", "source_label": "bitfin_xml_operacoes",
         "container": "zip"}
      ]
    }

`container` (opcional) sinaliza ao CONSUMIDOR server-side que o arquivo e um
pacote a descompactar (cliente que armazena zipado por dia). O agente ignora
o campo de proposito: arquivo sobe sempre como esta (fidelidade bronze 13.2
— quem abre o zip e o servidor).
"""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class AgentCredential(Base):
    __tablename__ = "agent_credential"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # UA cujas fontes este agente coleta. Nullable: um agente pode servir o
    # tenant inteiro (multi-UA no mesmo servidor); nesse caso o source_label
    # + config de consumo resolvem a UA a jusante.
    unidade_administrativa_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("cadastros_unidade_administrativa.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    # Nome humano ("Servidor Bitfin A7", "VM financeiro"). Aparece na UI.
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    # sha256 hex do token plaintext. Lookup por igualdade — unico e indexado.
    token_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    watch_config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Ultima versao reportada pelo agente (heartbeat) — observabilidade §7.3.
    agent_version: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

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
        return f"<AgentCredential tenant={self.tenant_id} name={self.name!r}>"
