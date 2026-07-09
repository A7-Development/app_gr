"""ref_bacen_posto

Revision ID: c5e2b8d1f4a9
Revises: b3d9e1f4a7c2
Create Date: 2026-07-09

Postos de atendimento (PAB/PAE) do Bacen — 3o degrau da escada de resolucao
de praca (antes do ERP). Fonte publica Olinda Informes_PostosDeAtendimento.
Cobre unidades com codigo proprio de agencia no CNAB que na taxonomia Bacen
sao postos (AG Empresarial/Plataforma Empresas da CEF, PABs em orgaos
publicos) — hoje caem em banco_sem_praca. Chave natural (cnpj_base,
nome_posto); lookup do resolver (banco_compe, posto_codigo).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c5e2b8d1f4a9"
down_revision: str | Sequence[str] | None = "b3d9e1f4a7c2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "ref_bacen_posto",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("cnpj_base", sa.String(8), nullable=False),
        sa.Column("banco_compe", sa.String(3), nullable=True),
        sa.Column("nome_if", sa.String(255), nullable=True),
        sa.Column("nome_posto", sa.String(255), nullable=False),
        sa.Column("posto_codigo", sa.String(5), nullable=True),
        sa.Column("tipo_posto", sa.String(80), nullable=True),
        sa.Column("endereco", sa.String(255), nullable=True),
        sa.Column("bairro", sa.String(255), nullable=True),
        sa.Column("cep", sa.String(9), nullable=True),
        sa.Column("municipio", sa.String(120), nullable=True),
        sa.Column("municipio_ibge", sa.Integer(), nullable=True),
        sa.Column("uf", sa.String(2), nullable=True),
        sa.Column("primeira_posicao", sa.Date(), nullable=True),
        sa.Column("ultima_posicao", sa.Date(), nullable=True),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fetched_by_version", sa.String(64), nullable=False),
        sa.UniqueConstraint("cnpj_base", "nome_posto", name="uq_ref_bacen_posto"),
    )
    op.create_index(
        "ix_ref_bacen_posto_lookup",
        "ref_bacen_posto",
        ["banco_compe", "posto_codigo"],
    )


def downgrade() -> None:
    op.drop_index("ix_ref_bacen_posto_lookup", table_name="ref_bacen_posto")
    op.drop_table("ref_bacen_posto")
