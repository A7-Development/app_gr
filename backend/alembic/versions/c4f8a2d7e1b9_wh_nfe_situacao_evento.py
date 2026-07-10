"""warehouse: silver wh_nfe_situacao + wh_nfe_evento (estado vivo via SERPRO).

Revision ID: c4f8a2d7e1b9
Revises: b3e8d1c6f4a2
Create Date: 2026-07-10 21:00:00.000000

Re-encadeada de a9d1c7e4f2b8 -> b3e8d1c6f4a2 (2026-07-10): a sessao do
ref_bacen_agencia (#554) mergeou antes com o mesmo pai; rebase da
down_revision evita bifurcacao de heads (aviso cruzado entre sessoes).

Silver do estado da NF-e derivado dos snapshots SERPRO (bronze
wh_serpro_raw_nfe). Perda zero: escalares em colunas + subarvores
verbatim em JSONB. Auditable completo (source_type=data:serpro_nfe).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4f8a2d7e1b9"
down_revision: str | None = "b3e8d1c6f4a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _auditable_columns() -> list[sa.Column]:
    return [
        sa.Column("source_type", sa.String(64), nullable=False),
        sa.Column("source_id", sa.String(255), nullable=False),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("hash_origem", sa.String(64), nullable=True),
        sa.Column("ingested_by_version", sa.String(128), nullable=False),
        sa.Column("trust_level", sa.String(16), nullable=False),
        sa.Column("collected_by", UUID(as_uuid=True), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "wh_nfe_evento",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "raw_id",
            UUID(as_uuid=True),
            sa.ForeignKey("wh_serpro_raw_nfe.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("chave_acesso", sa.String(44), nullable=False),
        sa.Column("id_evento", sa.String(60), nullable=True),
        sa.Column("c_orgao", sa.String(2), nullable=True),
        sa.Column("tp_amb", sa.Integer, nullable=True),
        sa.Column("autor_cnpj", sa.String(14), nullable=True),
        sa.Column("autor_cpf", sa.String(11), nullable=True),
        sa.Column("dh_evento", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tp_evento", sa.Integer, nullable=False),
        sa.Column("n_seq_evento", sa.Integer, nullable=False),
        sa.Column("ver_evento", sa.String(10), nullable=True),
        sa.Column("desc_evento", sa.String(120), nullable=True),
        sa.Column("x_just", sa.Text, nullable=True),
        sa.Column("x_correcao", sa.Text, nullable=True),
        sa.Column("det_n_prot", sa.String(20), nullable=True),
        sa.Column("ret_ver_aplic", sa.String(30), nullable=True),
        sa.Column("ret_c_orgao", sa.String(2), nullable=True),
        sa.Column("ret_c_stat", sa.Integer, nullable=True),
        sa.Column("ret_x_motivo", sa.String(255), nullable=True),
        sa.Column("ret_x_evento", sa.String(120), nullable=True),
        sa.Column("ret_cnpj_dest", sa.String(14), nullable=True),
        sa.Column("ret_cpf_dest", sa.String(11), nullable=True),
        sa.Column("ret_email_dest", sa.String(120), nullable=True),
        sa.Column("ret_dh_reg_evento", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ret_n_prot", sa.String(20), nullable=True),
        sa.Column("evento_json", JSONB, nullable=False),
        sa.Column("ret_evento_json", JSONB, nullable=True),
        *_auditable_columns(),
        sa.UniqueConstraint(
            "tenant_id",
            "chave_acesso",
            "tp_evento",
            "n_seq_evento",
            name="uq_wh_nfe_evento_identidade",
        ),
    )
    op.create_index("ix_wh_nfe_evento_tenant_id", "wh_nfe_evento", ["tenant_id"])
    op.create_index(
        "ix_wh_nfe_evento_tenant_chave",
        "wh_nfe_evento",
        ["tenant_id", "chave_acesso"],
    )
    op.create_index(
        "ix_wh_nfe_evento_tenant_tipo", "wh_nfe_evento", ["tenant_id", "tp_evento"]
    )
    op.create_index(
        "ix_wh_nfe_evento_source_type", "wh_nfe_evento", ["source_type"]
    )
    op.create_index("ix_wh_nfe_evento_source_id", "wh_nfe_evento", ["source_id"])

    op.create_table(
        "wh_nfe_situacao",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "last_raw_id",
            UUID(as_uuid=True),
            sa.ForeignKey("wh_serpro_raw_nfe.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("chave_acesso", sa.String(44), nullable=False),
        sa.Column("nfe_proc_versao", sa.String(8), nullable=True),
        sa.Column("prot_tp_amb", sa.Integer, nullable=True),
        sa.Column("prot_ver_aplic", sa.String(30), nullable=True),
        sa.Column("prot_dh_recbto", sa.DateTime(timezone=True), nullable=True),
        sa.Column("prot_n_prot", sa.String(20), nullable=True),
        sa.Column("prot_dig_val", sa.String(44), nullable=True),
        sa.Column("prot_c_stat", sa.Integer, nullable=True),
        sa.Column("prot_x_motivo", sa.String(255), nullable=True),
        sa.Column("prot_id", sa.String(60), nullable=True),
        sa.Column("prot_json", JSONB, nullable=True),
        sa.Column("situacao", sa.String(32), nullable=False),
        sa.Column("cancelada", sa.Boolean, nullable=False),
        sa.Column("dh_cancelamento", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manifestacao", sa.String(24), nullable=True),
        sa.Column("dh_manifestacao", sa.DateTime(timezone=True), nullable=True),
        sa.Column("qtd_eventos", sa.Integer, nullable=False),
        sa.Column("dh_ultimo_evento", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consultado_em", sa.DateTime(timezone=True), nullable=True),
        *_auditable_columns(),
        sa.UniqueConstraint(
            "tenant_id", "chave_acesso", name="uq_wh_nfe_situacao_tenant_chave"
        ),
    )
    op.create_index(
        "ix_wh_nfe_situacao_tenant_id", "wh_nfe_situacao", ["tenant_id"]
    )
    op.create_index(
        "ix_wh_nfe_situacao_tenant_situacao",
        "wh_nfe_situacao",
        ["tenant_id", "situacao"],
    )
    op.create_index(
        "ix_wh_nfe_situacao_source_type", "wh_nfe_situacao", ["source_type"]
    )
    op.create_index(
        "ix_wh_nfe_situacao_source_id", "wh_nfe_situacao", ["source_id"]
    )


def downgrade() -> None:
    op.drop_table("wh_nfe_situacao")
    op.drop_table("wh_nfe_evento")
