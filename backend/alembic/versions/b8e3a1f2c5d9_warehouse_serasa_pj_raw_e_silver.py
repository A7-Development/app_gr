"""warehouse: serasa_pj raw + silver (consulta, socio, restricao, participacao, endereco)

Revision ID: b8e3a1f2c5d9
Revises: 4dfbd64002b5
Create Date: 2026-05-01 18:30:00.000000

Cria 1 tabela bronze + 5 tabelas silver para o adapter Serasa PJ.

CLAUDE.md secao 13.2 — bronze e imutavel (sem Auditable; carrega
proveniencia em colunas dedicadas). Silver herda colunas do mixin
Auditable (source_type, source_id, ingested_at, etc) replicadas
explicitamente aqui.

Modelo de granularidade:
    - 1 consulta = 1 linha em raw + 1 linha em consulta + N linhas
      em socio/restricao/participacao/endereco.
    - source_id determinista: silver usa "<raw_id>" no header e
      "<raw_id>|<dimension>|<index>" nas tabelas filhas, garantindo
      idempotencia em re-mapeamento.
    - Re-mapear (sem re-consultar Serasa) e barato: bronze imutavel +
      mapper idempotente + UQ (tenant_id, source_id) faz upsert.

Tenant scoping (CLAUDE.md secao 10):
    - tenant_id em TODA tabela.
    - tenant_id denormalizado em filhas (socio, restricao, etc) — evita
      JOIN ate consulta para queries escopadas e protege contra leak
      cross-tenant ate em queries mal-escritas.

Indices:
    - (tenant_id, cnpj, fetched_at/consulted_at DESC) — "ultima consulta
      do CNPJ X no tenant".
    - Partial indexes por has_refin/has_pefin para queries de carteira
      ("quais empresas em monitoramento tem PEFIN?").
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b8e3a1f2c5d9"
down_revision: str | None = "4dfbd64002b5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Lista canonica de SourceType (replica enum em codigo). Toda migration
# que cria coluna source_type via Auditable replica isto.
_SOURCE_TYPE_VALUES = (
    "ERP_BITFIN",
    "ADMIN_QITECH",
    "BUREAU_SERASA_PJ",
    "BUREAU_SERASA_PF",
    "BUREAU_SCR_BACEN",
    "DOCUMENT_NFE",
    "SELF_DECLARED",
    "PEER_DECLARED",
    "INTERNAL_NOTE",
    "DERIVED",
)

_TRUST_LEVEL_VALUES = ("HIGH", "MEDIUM", "LOW")
_ENVIRONMENT_VALUES = ("SANDBOX", "PRODUCTION")


def _auditable_columns() -> list[sa.Column]:
    """Replica colunas do mixin `Auditable` (CLAUDE.md secao 14.1)."""
    return [
        sa.Column(
            "source_type",
            sa.Enum(
                *_SOURCE_TYPE_VALUES,
                name="source_type",
                native_enum=False,
                length=64,
            ),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(length=255), nullable=False),
        sa.Column(
            "source_updated_at", sa.DateTime(timezone=True), nullable=True
        ),
        sa.Column(
            "ingested_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("hash_origem", sa.String(length=64), nullable=True),
        sa.Column(
            "ingested_by_version", sa.String(length=128), nullable=False
        ),
        sa.Column(
            "trust_level",
            sa.Enum(
                *_TRUST_LEVEL_VALUES,
                name="trust_level",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("collected_by", sa.UUID(), nullable=True),
    ]


def upgrade() -> None:
    # ─── Bronze: wh_serasa_pj_raw_relatorio ────────────────────────────────
    # Imutavel; carrega proveniencia em colunas dedicadas (sem Auditable).
    op.create_table(
        "wh_serasa_pj_raw_relatorio",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("cnpj", sa.String(length=14), nullable=False),
        sa.Column(
            "requested_report", sa.String(length=64), nullable=False
        ),
        sa.Column(
            "actual_report_returned", sa.String(length=64), nullable=False
        ),
        sa.Column(
            "environment",
            sa.Enum(
                *_ENVIRONMENT_VALUES,
                name="environment",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("status_code", sa.SmallInteger(), nullable=False),
        sa.Column("cost_center", sa.String(length=12), nullable=True),
        sa.Column("triggered_by", sa.String(length=255), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("latency_ms", sa.Numeric(precision=10, scale=1), nullable=True),
        sa.Column(
            "fetched_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "fetched_by_version", sa.String(length=128), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_wh_serasa_pj_raw_relatorio_tenant_id",
        "wh_serasa_pj_raw_relatorio",
        ["tenant_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_raw_relatorio_cnpj",
        "wh_serasa_pj_raw_relatorio",
        ["cnpj"],
    )
    op.create_index(
        "ix_wh_serasa_pj_raw_relatorio_payload_sha256",
        "wh_serasa_pj_raw_relatorio",
        ["payload_sha256"],
    )
    # "Ultima consulta do CNPJ X no tenant Y" — query critica para o
    # modulo credito (cache de janela), gestao de risco (time-series) e
    # dashboards.
    op.create_index(
        "ix_wh_serasa_pj_raw_relatorio_tenant_cnpj_fetched",
        "wh_serasa_pj_raw_relatorio",
        [
            "tenant_id",
            "cnpj",
            sa.text("fetched_at DESC"),
        ],
    )

    # ─── Silver: wh_serasa_pj_consulta ─────────────────────────────────────
    # Header da consulta: dados cadastrais + score + contadores agregados.
    # 1:1 com bronze; existe pra dar shape estavel ao dossie / dashboard.
    op.create_table(
        "wh_serasa_pj_consulta",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("raw_id", sa.UUID(), nullable=False),
        sa.Column("cnpj", sa.String(length=14), nullable=False),
        sa.Column(
            "consulted_at", sa.DateTime(timezone=True), nullable=False
        ),
        sa.Column(
            "requested_report", sa.String(length=64), nullable=False
        ),
        sa.Column(
            "actual_report_returned", sa.String(length=64), nullable=False
        ),
        sa.Column(
            "reciprocity_downgrade",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        # Cadastrais
        sa.Column("razao_social", sa.Text(), nullable=True),
        sa.Column("nome_fantasia", sa.Text(), nullable=True),
        sa.Column("situacao_cadastral", sa.String(length=64), nullable=True),
        sa.Column("data_constituicao", sa.Date(), nullable=True),
        sa.Column("capital_social", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column(
            "faturamento_presumido",
            sa.Numeric(precision=20, scale=2),
            nullable=True,
        ),
        sa.Column(
            "atividade_principal_cnae", sa.String(length=10), nullable=True
        ),
        sa.Column(
            "atividade_principal_descricao", sa.Text(), nullable=True
        ),
        # Score
        sa.Column("score_h4pj", sa.Numeric(precision=7, scale=2), nullable=True),
        sa.Column("score_classe", sa.String(length=8), nullable=True),
        sa.Column("score_descricao", sa.Text(), nullable=True),
        # Contadores
        sa.Column(
            "has_refin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "has_pefin",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "has_protesto",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "has_cheque",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "count_refin",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "count_pefin",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "count_protesto",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "count_cheque",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "valor_total_restricoes",
            sa.Numeric(precision=20, scale=2),
            nullable=True,
        ),
        *_auditable_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        # RESTRICT para nao permitir apagar bronze sem antes apagar silver.
        sa.ForeignKeyConstraint(
            ["raw_id"],
            ["wh_serasa_pj_raw_relatorio.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_serasa_pj_consulta"
        ),
    )
    op.create_index(
        "ix_wh_serasa_pj_consulta_tenant_id",
        "wh_serasa_pj_consulta",
        ["tenant_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_consulta_cnpj",
        "wh_serasa_pj_consulta",
        ["cnpj"],
    )
    op.create_index(
        "ix_wh_serasa_pj_consulta_raw_id",
        "wh_serasa_pj_consulta",
        ["raw_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_consulta_source_type",
        "wh_serasa_pj_consulta",
        ["source_type"],
    )
    op.create_index(
        "ix_wh_serasa_pj_consulta_source_id",
        "wh_serasa_pj_consulta",
        ["source_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_consulta_tenant_cnpj_consulted",
        "wh_serasa_pj_consulta",
        ["tenant_id", "cnpj", sa.text("consulted_at DESC")],
    )
    # Partial indexes para queries de risco/monitoramento ("empresas em
    # carteira com REFIN/PEFIN") — caem direto nas linhas relevantes,
    # ignoram a maioria que esta limpa.
    op.create_index(
        "ix_wh_serasa_pj_consulta_tenant_has_refin",
        "wh_serasa_pj_consulta",
        ["tenant_id", "cnpj"],
        postgresql_where=sa.text("has_refin = true"),
    )
    op.create_index(
        "ix_wh_serasa_pj_consulta_tenant_has_pefin",
        "wh_serasa_pj_consulta",
        ["tenant_id", "cnpj"],
        postgresql_where=sa.text("has_pefin = true"),
    )

    # ─── Silver: wh_serasa_pj_socio ────────────────────────────────────────
    op.create_table(
        "wh_serasa_pj_socio",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("consulta_id", sa.UUID(), nullable=False),
        sa.Column("documento", sa.String(length=14), nullable=False),
        # 'cpf' | 'cnpj' | 'unknown' (caso a Serasa nao identifique).
        sa.Column("documento_tipo", sa.String(length=8), nullable=False),
        sa.Column("nome", sa.Text(), nullable=True),
        sa.Column("qualificacao", sa.Text(), nullable=True),
        sa.Column("percentual", sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column("data_entrada", sa.Date(), nullable=True),
        *_auditable_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["consulta_id"],
            ["wh_serasa_pj_consulta.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_serasa_pj_socio"
        ),
    )
    op.create_index(
        "ix_wh_serasa_pj_socio_tenant_id",
        "wh_serasa_pj_socio",
        ["tenant_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_socio_consulta_id",
        "wh_serasa_pj_socio",
        ["consulta_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_socio_documento",
        "wh_serasa_pj_socio",
        ["documento"],
    )
    op.create_index(
        "ix_wh_serasa_pj_socio_source_id",
        "wh_serasa_pj_socio",
        ["source_id"],
    )

    # ─── Silver: wh_serasa_pj_restricao ────────────────────────────────────
    op.create_table(
        "wh_serasa_pj_restricao",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("consulta_id", sa.UUID(), nullable=False),
        # 'refin' | 'pefin' | 'protesto' | 'cheque' | (futuros).
        sa.Column("tipo", sa.String(length=16), nullable=False),
        sa.Column("valor", sa.Numeric(precision=20, scale=2), nullable=True),
        sa.Column("credor", sa.Text(), nullable=True),
        sa.Column("data_ocorrencia", sa.Date(), nullable=True),
        sa.Column("data_baixa", sa.Date(), nullable=True),
        # Detalhe livre por tipo (ex.: cidade do protesto, banco do cheque).
        # Nao e payload bruto — sao campos derivados que nao cabem em colunas
        # tipadas. Bronze continua sendo a fonte da verdade.
        sa.Column(
            "detalhe", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
        *_auditable_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["consulta_id"],
            ["wh_serasa_pj_consulta.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_serasa_pj_restricao"
        ),
    )
    op.create_index(
        "ix_wh_serasa_pj_restricao_tenant_id",
        "wh_serasa_pj_restricao",
        ["tenant_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_restricao_consulta_id",
        "wh_serasa_pj_restricao",
        ["consulta_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_restricao_tipo",
        "wh_serasa_pj_restricao",
        ["tipo"],
    )
    op.create_index(
        "ix_wh_serasa_pj_restricao_tenant_tipo",
        "wh_serasa_pj_restricao",
        ["tenant_id", "tipo"],
    )

    # ─── Silver: wh_serasa_pj_participacao ─────────────────────────────────
    op.create_table(
        "wh_serasa_pj_participacao",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("consulta_id", sa.UUID(), nullable=False),
        # CNPJ da empresa em que a target participa.
        sa.Column(
            "documento_empresa", sa.String(length=14), nullable=False
        ),
        sa.Column("razao_social", sa.Text(), nullable=True),
        sa.Column("percentual", sa.Numeric(precision=7, scale=4), nullable=True),
        sa.Column("qualificacao", sa.Text(), nullable=True),
        *_auditable_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["consulta_id"],
            ["wh_serasa_pj_consulta.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_serasa_pj_participacao"
        ),
    )
    op.create_index(
        "ix_wh_serasa_pj_participacao_tenant_id",
        "wh_serasa_pj_participacao",
        ["tenant_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_participacao_consulta_id",
        "wh_serasa_pj_participacao",
        ["consulta_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_participacao_documento_empresa",
        "wh_serasa_pj_participacao",
        ["documento_empresa"],
    )

    # ─── Silver: wh_serasa_pj_endereco ─────────────────────────────────────
    op.create_table(
        "wh_serasa_pj_endereco",
        sa.Column(
            "id",
            sa.UUID(),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("consulta_id", sa.UUID(), nullable=False),
        # 'comercial', 'residencial', 'fiscal', etc.
        sa.Column("tipo", sa.String(length=32), nullable=True),
        sa.Column("logradouro", sa.Text(), nullable=True),
        sa.Column("numero", sa.String(length=16), nullable=True),
        sa.Column("complemento", sa.Text(), nullable=True),
        sa.Column("bairro", sa.Text(), nullable=True),
        sa.Column("cidade", sa.Text(), nullable=True),
        sa.Column("uf", sa.String(length=2), nullable=True),
        sa.Column("cep", sa.String(length=8), nullable=True),
        *_auditable_columns(),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["consulta_id"],
            ["wh_serasa_pj_consulta.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id", "source_id", name="uq_wh_serasa_pj_endereco"
        ),
    )
    op.create_index(
        "ix_wh_serasa_pj_endereco_tenant_id",
        "wh_serasa_pj_endereco",
        ["tenant_id"],
    )
    op.create_index(
        "ix_wh_serasa_pj_endereco_consulta_id",
        "wh_serasa_pj_endereco",
        ["consulta_id"],
    )


def downgrade() -> None:
    # Ordem reversa: filhas antes da mae (consulta) antes da raw.
    op.drop_index(
        "ix_wh_serasa_pj_endereco_consulta_id",
        table_name="wh_serasa_pj_endereco",
    )
    op.drop_index(
        "ix_wh_serasa_pj_endereco_tenant_id",
        table_name="wh_serasa_pj_endereco",
    )
    op.drop_table("wh_serasa_pj_endereco")

    op.drop_index(
        "ix_wh_serasa_pj_participacao_documento_empresa",
        table_name="wh_serasa_pj_participacao",
    )
    op.drop_index(
        "ix_wh_serasa_pj_participacao_consulta_id",
        table_name="wh_serasa_pj_participacao",
    )
    op.drop_index(
        "ix_wh_serasa_pj_participacao_tenant_id",
        table_name="wh_serasa_pj_participacao",
    )
    op.drop_table("wh_serasa_pj_participacao")

    op.drop_index(
        "ix_wh_serasa_pj_restricao_tenant_tipo",
        table_name="wh_serasa_pj_restricao",
    )
    op.drop_index(
        "ix_wh_serasa_pj_restricao_tipo",
        table_name="wh_serasa_pj_restricao",
    )
    op.drop_index(
        "ix_wh_serasa_pj_restricao_consulta_id",
        table_name="wh_serasa_pj_restricao",
    )
    op.drop_index(
        "ix_wh_serasa_pj_restricao_tenant_id",
        table_name="wh_serasa_pj_restricao",
    )
    op.drop_table("wh_serasa_pj_restricao")

    op.drop_index(
        "ix_wh_serasa_pj_socio_source_id",
        table_name="wh_serasa_pj_socio",
    )
    op.drop_index(
        "ix_wh_serasa_pj_socio_documento",
        table_name="wh_serasa_pj_socio",
    )
    op.drop_index(
        "ix_wh_serasa_pj_socio_consulta_id",
        table_name="wh_serasa_pj_socio",
    )
    op.drop_index(
        "ix_wh_serasa_pj_socio_tenant_id",
        table_name="wh_serasa_pj_socio",
    )
    op.drop_table("wh_serasa_pj_socio")

    op.drop_index(
        "ix_wh_serasa_pj_consulta_tenant_has_pefin",
        table_name="wh_serasa_pj_consulta",
    )
    op.drop_index(
        "ix_wh_serasa_pj_consulta_tenant_has_refin",
        table_name="wh_serasa_pj_consulta",
    )
    op.drop_index(
        "ix_wh_serasa_pj_consulta_tenant_cnpj_consulted",
        table_name="wh_serasa_pj_consulta",
    )
    op.drop_index(
        "ix_wh_serasa_pj_consulta_source_id",
        table_name="wh_serasa_pj_consulta",
    )
    op.drop_index(
        "ix_wh_serasa_pj_consulta_source_type",
        table_name="wh_serasa_pj_consulta",
    )
    op.drop_index(
        "ix_wh_serasa_pj_consulta_raw_id",
        table_name="wh_serasa_pj_consulta",
    )
    op.drop_index(
        "ix_wh_serasa_pj_consulta_cnpj",
        table_name="wh_serasa_pj_consulta",
    )
    op.drop_index(
        "ix_wh_serasa_pj_consulta_tenant_id",
        table_name="wh_serasa_pj_consulta",
    )
    op.drop_table("wh_serasa_pj_consulta")

    op.drop_index(
        "ix_wh_serasa_pj_raw_relatorio_tenant_cnpj_fetched",
        table_name="wh_serasa_pj_raw_relatorio",
    )
    op.drop_index(
        "ix_wh_serasa_pj_raw_relatorio_payload_sha256",
        table_name="wh_serasa_pj_raw_relatorio",
    )
    op.drop_index(
        "ix_wh_serasa_pj_raw_relatorio_cnpj",
        table_name="wh_serasa_pj_raw_relatorio",
    )
    op.drop_index(
        "ix_wh_serasa_pj_raw_relatorio_tenant_id",
        table_name="wh_serasa_pj_raw_relatorio",
    )
    op.drop_table("wh_serasa_pj_raw_relatorio")
