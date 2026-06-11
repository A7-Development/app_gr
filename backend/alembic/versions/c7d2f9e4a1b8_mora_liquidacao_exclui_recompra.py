"""Streams mora_liquidacao v2: exclui recompra-liquidacao (dupla contagem).

Descoberta 2026-06-11: titulo liquidado POR RECOMPRA fica Situacao=1 com
ValorDoPagamento = recomprado + encargos DE RECOMPRA — o mesmo encargo ja
entra via stream recompra (RecompraItem). v1 dos streams mora_liquidacao_*
contava 2x (~R$ 206k em 2026). v2 adiciona `exclui_recompra_liquidacao` ao
criterio (o ETL v2.7.1 aplica o NOT EXISTS correspondente).

Revision ID: c7d2f9e4a1b8
Revises: b3f7a2c9e4d1
Create Date: 2026-06-11
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

from alembic import op

revision: str = "c7d2f9e4a1b8"
down_revision: str | Sequence[str] | None = "b3f7a2c9e4d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_HOJE = date(2026, 6, 11)

_NOTES = (
    "v2 (2026-06-11): exclui titulos liquidados por recompra (Situacao=1 "
    "com RecompraItem Efetivada+Liquidacao) — encargo deles e da regua de "
    "recompra e ja entra via stream recompra. Populacao real: FAT/DMS; a "
    "'mora da Comissaria' era 100% recompra. Regua ProcedimentoDeCobranca "
    "adere 98,5% pos-expurgo."
)


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            "SELECT id, stream_key, familia, natureza, fonte_tabela, criterio, "
            "grao, retido_na_fonte, descricao "
            "FROM wh_bitfin_receita_stream "
            "WHERE stream_key IN ('mora_liquidacao_juros', 'mora_liquidacao_multa') "
            "AND tenant_id IS NULL AND valid_until IS NULL"
        )
    ).mappings().all()

    table = sa.table(
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

    now = datetime.now(UTC)
    for r in rows:
        conn.execute(
            sa.text(
                "UPDATE wh_bitfin_receita_stream SET valid_until = :hoje "
                "WHERE id = :id"
            ),
            {"hoje": _HOJE, "id": r["id"]},
        )
        criterio = dict(r["criterio"])
        criterio["exclui_recompra_liquidacao"] = True
        op.bulk_insert(
            table,
            [
                {
                    "id": uuid4(),
                    "tenant_id": None,
                    "version": 2,
                    "stream_key": r["stream_key"],
                    "familia": r["familia"],
                    "natureza": r["natureza"],
                    "fonte_tabela": r["fonte_tabela"],
                    "criterio": criterio,
                    "grao": r["grao"],
                    "retido_na_fonte": r["retido_na_fonte"],
                    "descricao": r["descricao"],
                    "notes": _NOTES,
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
            "WHERE stream_key IN ('mora_liquidacao_juros', 'mora_liquidacao_multa') "
            "AND tenant_id IS NULL AND version = 2"
        )
    )
    conn.execute(
        sa.text(
            "UPDATE wh_bitfin_receita_stream SET valid_until = NULL "
            "WHERE stream_key IN ('mora_liquidacao_juros', 'mora_liquidacao_multa') "
            "AND tenant_id IS NULL AND version = 1"
        )
    )
