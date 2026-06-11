"""Split pela regua + ENCARGO_NEGOCIADO + valor_referencia_regua.

Decisao 2026-06-11 (Ricardo rejeitou split proporcional): mora de
liquidacao decompoe juros x multa APENAS quando o pagamento seguiu a regua
contratual (|caixa - regua| <= R$1, 98,5% da populacao pos-expurgo);
pagamento negociado vira natureza unica ENCARGO_NEGOCIADO sem decomposicao,
com a regua de referencia gravada ao lado (desconto concedido = referencia
- valor). Recompra ganha a mesma referencia (regua contratual sobre dias
vencidos) — mora perdoada em negociacao entra com valor 0 + referencia.

Revision ID: d9e3a7c1f5b2
Revises: c7d2f9e4a1b8
Create Date: 2026-06-11
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "d9e3a7c1f5b2"
down_revision: str | Sequence[str] | None = "c7d2f9e4a1b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HOJE = date(2026, 6, 11)
_STREAMS_SPLIT = ("mora_liquidacao_juros", "mora_liquidacao_multa")

_NOTES_V3 = (
    "v3 (2026-06-11): split deixa de ser proporcional — decompoe APENAS "
    "quando |caixa - regua| <= tolerancia_brl (componentes exatos da regua, "
    "residuo de centavos no juros). Fora da tolerancia o titulo vai para o "
    "stream mora_liquidacao_negociado (sem decomposicao)."
)


def _table() -> sa.TableClause:
    return sa.table(
        "wh_bitfin_receita_stream",
        sa.column("id", sa.UUID()),
        sa.column("tenant_id", sa.UUID()),
        sa.column("version", sa.Integer()),
        sa.column("stream_key", sa.String()),
        sa.column("familia", sa.String()),
        sa.column("natureza", sa.String()),
        sa.column("fonte_tabela", sa.String()),
        sa.column("criterio", JSONB()),
        sa.column("grao", sa.String()),
        sa.column("retido_na_fonte", sa.Boolean()),
        sa.column("descricao", sa.String()),
        sa.column("notes", sa.Text()),
        sa.column("valid_from", sa.Date()),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )


def upgrade() -> None:
    op.add_column(
        "wh_receita_operacional",
        sa.Column("valor_referencia_regua", sa.Numeric(18, 2), nullable=True),
    )

    conn = op.get_bind()
    now = datetime.now(UTC)

    # v2 -> v3 dos streams de split (criterio ganha split=regua_exata).
    rows = conn.execute(
        sa.text(
            "SELECT id, stream_key, familia, natureza, fonte_tabela, criterio, "
            "grao, retido_na_fonte, descricao "
            "FROM wh_bitfin_receita_stream "
            "WHERE stream_key IN :keys AND tenant_id IS NULL "
            "AND valid_until IS NULL"
        ).bindparams(sa.bindparam("keys", expanding=True)),
        {"keys": list(_STREAMS_SPLIT)},
    ).mappings().all()
    for r in rows:
        conn.execute(
            sa.text(
                "UPDATE wh_bitfin_receita_stream SET valid_until = :hoje "
                "WHERE id = :id"
            ),
            {"hoje": _HOJE, "id": r["id"]},
        )
        criterio = dict(r["criterio"])
        criterio["split"] = "regua_exata"
        criterio["tolerancia_brl"] = 1.0
        op.bulk_insert(
            _table(),
            [
                {
                    "id": uuid4(),
                    "tenant_id": None,
                    "version": 3,
                    "stream_key": r["stream_key"],
                    "familia": r["familia"],
                    "natureza": r["natureza"],
                    "fonte_tabela": r["fonte_tabela"],
                    "criterio": criterio,
                    "grao": r["grao"],
                    "retido_na_fonte": r["retido_na_fonte"],
                    "descricao": r["descricao"],
                    "notes": _NOTES_V3,
                    "valid_from": _HOJE,
                    "created_at": now,
                }
            ],
        )

    # Stream novo: encargo negociado (fora da regua), sem decomposicao.
    op.bulk_insert(
        _table(),
        [
            {
                "id": uuid4(),
                "tenant_id": None,
                "version": 1,
                "stream_key": "mora_liquidacao_negociado",
                "familia": "mora_liquidacao",
                "natureza": "ENCARGO_NEGOCIADO",
                "fonte_tabela": "Titulo",
                "criterio": {
                    "situacao": 1,
                    "siglas": ["DM", "DS", "NP"],
                    "produto_de_risco": True,
                    "exclui_recompra_liquidacao": True,
                    "divergente_da_regua": True,
                    "tolerancia_brl": 1.0,
                },
                "grao": "titulo",
                "retido_na_fonte": False,
                "descricao": (
                    "Encargo de mora pago FORA da regua contratual (acordo) — "
                    "valor real sem decomposicao juros x multa"
                ),
                "notes": (
                    "Decompor acordo seria inferencia (decisao 2026-06-11). "
                    "valor_referencia_regua carrega a regua contratual; "
                    "desconto concedido = referencia - valor."
                ),
                "valid_from": _HOJE,
                "created_at": now,
            }
        ],
    )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM wh_bitfin_receita_stream "
            "WHERE stream_key = 'mora_liquidacao_negociado' AND tenant_id IS NULL"
        )
    )
    conn.execute(
        sa.text(
            "DELETE FROM wh_bitfin_receita_stream "
            "WHERE stream_key IN ('mora_liquidacao_juros', 'mora_liquidacao_multa') "
            "AND tenant_id IS NULL AND version = 3"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE wh_bitfin_receita_stream SET valid_until = NULL "
            "WHERE stream_key IN ('mora_liquidacao_juros', 'mora_liquidacao_multa') "
            "AND tenant_id IS NULL AND version = 2"
        )
    )
    op.drop_column("wh_receita_operacional", "valor_referencia_regua")
