"""Rating deterministico de integridade de liquidacao (framework 2026-07-10).

Dois graos na MESMA tabela:
    - PAR cedente x sacado (`sacado_documento` preenchido) — o grao onde o
      "titulo frio" mora; drill natural da tela.
    - CEDENTE (`sacado_documento` NULL) — rollup ponderado por valor; e a
      variavel exportavel para o futuro rating composto do cedente.

Principios (fechados com Ricardo 2026-07-11):
    - Sinal de integridade agrega pelo lado do CEDENTE (quem controla o
      fluxo de liquidacao) — NUNCA penaliza o sacado globalmente.
    - Score 0-100 (maior = melhor) calculado SO sobre eventos com alegacao
      de pagamento do sacado (canais bancaria + baixa_manual); recompra /
      perda / baixa administrativa ficam FORA do score e DENTRO da
      cobertura (dimensao de credito, nao de integridade).
    - Assimetria estatistica: sinal ruim vale com qualquer n (fato e fato);
      grade boa (A/B) exige n e cobertura minimos — senao exibe NC
      ("sem classificacao"), nunca um A imerecido.
    - Letra e apresentacao; o primitivo componivel e o score numerico +
      metadados (n, cobertura, valor).

Recalculo = full refresh por tenant (delete + insert) apos o scoring
noturno; memoria de calculo completa em `componentes` (§14.3).
"""

from datetime import datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
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


class RatingLiquidacao(Base):
    """Snapshot vigente do rating (1 linha por par + 1 rollup por cedente)."""

    __tablename__ = "rating_liquidacao"
    __table_args__ = (
        # NULLS NOT DISTINCT: o rollup do cedente (sacado NULL) tambem e unico.
        UniqueConstraint(
            "tenant_id",
            "cedente_documento",
            "sacado_documento",
            name="uq_rating_liquidacao_escopo",
            postgresql_nulls_not_distinct=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    tenant_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("tenants.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    cedente_documento: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    cedente_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # NULL = rollup do cedente (grao cedente); preenchido = grao par.
    sacado_documento: Mapped[str | None] = mapped_column(String(20), nullable=True)
    sacado_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Score 0-100 (maior = melhor). NULL quando nao ha evento de pagamento
    # alegado na janela (par so-recompra/perda: cobertura conta a historia).
    score: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    # A|B|C|D|E|NC — NC = sem classificacao (base insuficiente p/ grade boa
    # ou nenhum evento atestavel). Letra e APRESENTACAO do score.
    grade: Mapped[str] = mapped_column(String(2), nullable=False)
    tem_critico: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Base do score: eventos com alegacao de pagamento do sacado na janela.
    n_eventos_score: Mapped[int] = mapped_column(Integer, nullable=False)
    # Universo completo de desfechos na janela (denominador da cobertura).
    n_desfechos: Mapped[int] = mapped_column(Integer, nullable=False)
    valor_desfechos: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    # % do valor de desfechos que passou pelo trilho bancario (atestavel).
    cobertura: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)

    # Memoria de calculo (§14.3): mix por canal, deducoes por sinal (codigo
    # do catalogo + n + valor), parametros usados, grade bruta pre-portao.
    componentes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    formula_version: Mapped[str] = mapped_column(String(40), nullable=False)

    calculado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        alvo = self.sacado_documento or "(cedente)"
        return f"<RatingLiquidacao {self.cedente_documento}x{alvo} {self.grade}>"
