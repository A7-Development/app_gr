"""qitech_ua_classe: catalogo de classes de cota por UA (sanidade de completude)

Cria o cadastro previo de classes de cota (clienteId) por UA, usado pelo
assessor de completude QiTech (`adapters/admin/qitech/completeness.py`) para
decidir `complete | partial` de forma robusta (ancorada em `clienteId` +
sanidade de valor), em vez da heuristica fragil de nome. Plano em
`~/.claude/plans/purrfect-marinating-glacier.md`.

Tabela `qitech_ua_classe` (config/referencia — NAO Auditable):
  - 1 linha por (tenant, UA, clienteId)
  - papel via String + CheckConstraint (espelha enum PapelCota)
  - vigencia via ativo_desde/ativo_ate (classe encerrada deixa de ser esperada)

Seed GUARDADO da UA REALINVEST (3 classes) — so insere se o tenant + UA
existirem neste banco (CI/DB novo nao quebra), idempotente via ON CONFLICT.

Revision ID: a9f4c2e7b1d8
Revises: e3b9a1c7d2f4
Create Date: 2026-05-27
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a9f4c2e7b1d8"
down_revision: str | None = "e3b9a1c7d2f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Seed da UA REALINVEST (a unica UA QiTech ativa hoje). ids confirmados no
# banco; o seed e guardado por existencia + ON CONFLICT, entao e seguro/idempotente.
_SEED_TENANT_ID = "7f00cc2b-8bb4-483f-87b7-b1db24d20902"
_SEED_UA_ID = "6170ce55-b566-42ba-a3e7-5ea8dde56b64"
_SEED_FUNDO_CNPJ = "42449234000160"
# (cliente_id, cliente_nome, papel) — nomes exatos lidos de wh_mec_evolucao_cotas.
_SEED_CLASSES: list[tuple[str, str, str]] = [
    ("REALINVEST", "REALINVEST FIDC", "SUBORDINADA"),
    ("REALINVEST MEZ", "REALINVEST FIDC MEZANINO 1", "MEZANINO"),
    ("REALINVEST SEN", "REALINVEST FIDC SENIOR 1", "SENIOR"),
]


def _seed_realinvest() -> None:
    bind = op.get_bind()
    exists = bind.execute(
        sa.text(
            "SELECT EXISTS(SELECT 1 FROM tenants WHERE id = :t) "
            "AND EXISTS(SELECT 1 FROM cadastros_unidade_administrativa WHERE id = :u)"
        ),
        {"t": _SEED_TENANT_ID, "u": _SEED_UA_ID},
    ).scalar()
    if not exists:
        return
    for cliente_id, cliente_nome, papel in _SEED_CLASSES:
        bind.execute(
            sa.text(
                "INSERT INTO qitech_ua_classe "
                "(id, tenant_id, unidade_administrativa_id, cliente_id, "
                " cliente_nome, fundo_cnpj, papel, ativo_desde) "
                "VALUES (gen_random_uuid(), :t, :u, :cid, :nome, :cnpj, :papel, "
                " DATE '2021-01-01') "
                "ON CONFLICT ON CONSTRAINT uq_qitech_ua_classe DO NOTHING"
            ),
            {
                "t": _SEED_TENANT_ID,
                "u": _SEED_UA_ID,
                "cid": cliente_id,
                "nome": cliente_nome,
                "cnpj": _SEED_FUNDO_CNPJ,
                "papel": papel,
            },
        )


def upgrade() -> None:
    op.create_table(
        "qitech_ua_classe",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("unidade_administrativa_id", sa.UUID(), nullable=False),
        sa.Column("cliente_id", sa.String(length=50), nullable=False),
        sa.Column("cliente_nome", sa.String(length=200), nullable=False),
        sa.Column("fundo_cnpj", sa.String(length=14), nullable=False),
        sa.Column("papel", sa.String(length=20), nullable=False),
        sa.Column(
            "ativo_desde",
            sa.Date(),
            server_default=sa.text("CURRENT_DATE"),
            nullable=False,
        ),
        sa.Column("ativo_ate", sa.Date(), nullable=True),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "unidade_administrativa_id",
            "cliente_id",
            name="uq_qitech_ua_classe",
        ),
        sa.CheckConstraint(
            "papel IN ('SUBORDINADA','MEZANINO','SENIOR','UNICA')",
            name="ck_qitech_ua_classe_papel",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["unidade_administrativa_id"],
            ["cadastros_unidade_administrativa.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_qitech_ua_classe_lookup",
        "qitech_ua_classe",
        ["tenant_id", "unidade_administrativa_id"],
        unique=False,
    )

    _seed_realinvest()


def downgrade() -> None:
    op.drop_index(
        "ix_qitech_ua_classe_lookup", table_name="qitech_ua_classe"
    )
    op.drop_table("qitech_ua_classe")
