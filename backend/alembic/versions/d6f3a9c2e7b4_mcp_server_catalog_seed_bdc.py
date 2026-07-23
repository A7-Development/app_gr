"""Camada MCP: mcp_server/_active + agent_definition.mcp_toolsets + seed BDC

Revision ID: d6f3a9c2e7b4
Revises: e8b5d1f7a3c9
Create Date: 2026-07-23

Spec: specs/active/copiloto-mcp.md (v3), Fase 1b.

1. Tabelas `mcp_server` + `mcp_server_active` (catalogo DB-first,
   versionado, active pointer — espelha agent_definition).
2. `agent_definition.mcp_toolsets` (JSONB) — toolsets de MCP concedidos.
3. Seed do servidor `bigdatacorp` (global): credencial REUSA a row ativa
   de `provedor_dados_credencial` do provider BIGDATACORP (INSERT..SELECT
   — um segredo, um ponto de rotacao); allowlist ENXUTA de credito (10
   das 166 tools); caps default (5 chamadas/turno, 20k chars/resultado).
4. Concede o toolset ao agente `credito.strata_ai`.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "d6f3a9c2e7b4"
down_revision = "e8b5d1f7a3c9"
branch_labels = None
depends_on = None


_SERVER_ID = "44444444-0004-4000-8000-000000000000"
_SERVER_NAME = "bigdatacorp"
_SERVER_URL = "https://app.bigdatacorp.com.br/bigia/mcp"

# Allowlist enxuta de credito (sondada em 2026-07-23 via tools/list — 166
# tools no total). PJ: cadastral, QSA, grupo economico, processos,
# cobrancas, divida ativa, KYC. PF (socios): cadastral, KYC.
_ALLOWED_TOOLS = [
    "companies_basic_data_tool",
    "companies_registration_data_tool",
    "companies_dynamic_qsa_data_tool",
    "companies_economic_group_first_level_tool",
    "companies_processes_tool",
    "companies_collections_tool",
    "companies_government_debtors_tool",
    "companies_kyc_tool",
    "people_basic_data_tool",
    "people_kyc_tool",
]


def upgrade() -> None:
    op.create_table(
        "mcp_server",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=True,
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("url", sa.String(255), nullable=False),
        sa.Column("transport", sa.String(16), nullable=False),
        sa.Column("module", sa.String(32), nullable=True),
        sa.Column(
            "credential_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("provedor_dados_credencial.id"),
            nullable=True,
        ),
        sa.Column("auth_header_map", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("allowed_tools", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column(
            "cost_hint", sa.String(16), nullable=False, server_default="expensive"
        ),
        sa.Column(
            "max_calls_per_turn", sa.Integer(), nullable=False, server_default="5"
        ),
        sa.Column(
            "tool_result_max_chars",
            sa.Integer(),
            nullable=False,
            server_default="20000",
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "created_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("name", "version", name="uq_mcp_server_name_version"),
    )
    op.create_index(
        "ix_mcp_server_tenant_name", "mcp_server", ["tenant_id", "name"]
    )
    op.create_index("ix_mcp_server_module", "mcp_server", ["module"])

    op.create_table(
        "mcp_server_active",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=True,
        ),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column(
            "server_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("mcp_server.id"),
            nullable=False,
        ),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "activated_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "tenant_id", "name", name="uq_mcp_server_active_tenant_name"
        ),
    )

    op.add_column(
        "agent_definition",
        sa.Column(
            "mcp_toolsets", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )

    # ─── Seed BDC (global). Credencial: reusa a row ativa do provider
    # BIGDATACORP — se nao existir, o INSERT..SELECT nao insere nada e o
    # seed do server/active/toolset fica no-op (ambiente sem BDC).
    import json

    op.execute(
        sa.text(
            "INSERT INTO mcp_server "
            "(id, tenant_id, name, version, url, transport, module, "
            "credential_id, auth_header_map, allowed_tools, mode, cost_hint, "
            "max_calls_per_turn, tool_result_max_chars, description) "
            # GOTCHA SAEnum (native_enum=False) armazena o NOME do enum
            # ('HTTP'/'EPHEMERAL'), nao o value — 4a ocorrencia no projeto.
            "SELECT CAST(:id AS uuid), NULL, :name, 1, :url, 'HTTP', 'credito', "
            "c.id, CAST(:header_map AS jsonb), CAST(:allowed AS jsonb), "
            "'EPHEMERAL', 'expensive', 5, 20000, :description "
            "FROM provedor_dados_credencial c "
            "JOIN provedor_dados p ON p.id = c.provider_id "
            "WHERE p.slug = 'BIGDATACORP' AND c.active "
            "ORDER BY c.created_at DESC LIMIT 1 "
            "ON CONFLICT DO NOTHING"
        ).bindparams(
            id=_SERVER_ID,
            name=_SERVER_NAME,
            url=_SERVER_URL,
            header_map=json.dumps(
                {"access_token": "AccessToken", "token_id": "TokenId"}
            ),
            allowed=json.dumps(_ALLOWED_TOOLS),
            description=(
                "Fontes de mercado (Strata Hub) — cadastral, QSA, grupo "
                "economico, processos, cobrancas, divida ativa e KYC de "
                "PJ/PF. Allowlist enxuta de credito (10 tools). Datasets "
                "PAGOS — caps por turno e allowlist sao guard-rails de custo."
            ),
        )
    )
    op.execute(
        sa.text(
            "INSERT INTO mcp_server_active (id, tenant_id, name, server_id) "
            "SELECT gen_random_uuid(), NULL, :name, s.id "
            "FROM mcp_server s WHERE s.id = CAST(:server_id AS uuid) "
            "ON CONFLICT DO NOTHING"
        ).bindparams(name=_SERVER_NAME, server_id=_SERVER_ID)
    )
    # Concede o toolset ao Strata AI (tools=null -> allowlist do servidor).
    op.execute(
        sa.text(
            "UPDATE agent_definition "
            "SET mcp_toolsets = CAST(:toolsets AS jsonb) "
            "WHERE name = 'credito.strata_ai' AND version = 1 "
            "AND EXISTS (SELECT 1 FROM mcp_server WHERE id = CAST(:server_id AS uuid))"
        ).bindparams(
            toolsets=json.dumps(
                [{"mcp_server_name": _SERVER_NAME, "tools": None}]
            ),
            server_id=_SERVER_ID,
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE agent_definition SET mcp_toolsets = NULL "
            "WHERE name = 'credito.strata_ai' AND version = 1"
        )
    )
    op.drop_column("agent_definition", "mcp_toolsets")
    op.drop_table("mcp_server_active")
    op.drop_index("ix_mcp_server_module", table_name="mcp_server")
    op.drop_index("ix_mcp_server_tenant_name", table_name="mcp_server")
    op.drop_table("mcp_server")
