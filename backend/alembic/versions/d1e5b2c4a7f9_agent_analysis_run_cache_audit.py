"""agent_analysis_run: cache + audit unificados das execucoes do agente

Revision ID: d1e5b2c4a7f9
Revises: c3d8f9e2a4b6
Create Date: 2026-05-25 10:00:00.000000

Substitui o approach de gravar em `decision_log` + `ai_usage_event`
separados por uma tabela unificada que serve aos 2 propositos:

  1. **Cache funcional**: lookup por `(tenant_id, agent_name, agent_version,
     inputs_hash)` evita pagar Anthropic 2x pra mesma analise (mesmo
     fundo + mesma data + mesma versao de prompt/persona).
  2. **Auditoria**: linhagem completa de cada invocacao (audit_version
     componente prompt+persona+expertises, modelo usado, tokens, custo,
     usuario que disparou, timestamp).

Por que unificar:
- Cache hit precisa do output completo + audit_version pra coerencia.
  Ja temos tudo isso pra audit. Duplicar em 2 tabelas e ruim.
- Invalidacao automatica via `inputs_hash` que INCLUI `audit_version`:
  quando prompt v2 e ativado, novo hash != cache antigo → re-roda.

Invalidacao manual via `invalidated_at` (soft-delete):
- ETL QiTech re-ingere data → invalidar runs daquela data (futuro)
- Botao "re-rodar analise" na UI → invalidar entrada especifica

Indices:
- UQ partial em (tenant, agent, version, inputs_hash) WHERE invalidated_at
  IS NULL — garante 1 unica entrada VIVA por chave de cache.
- Lookup index em (tenant, agent, inputs_hash, invalidated_at) cobre o
  cache check em O(log n).
- (tenant, agent, triggered_at desc) pra historico cronologico.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "d1e5b2c4a7f9"
down_revision = "c3d8f9e2a4b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_analysis_run",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        # ─── Identificacao do agente + versao ─────────────────────────────
        sa.Column("agent_name", sa.String(128), nullable=False),
        sa.Column("agent_version", sa.Integer, nullable=False),
        # Composto agent+persona+expertises+prompt — invalida cache quando
        # qualquer um muda. Ver ResolvedAgent.audit_version.
        sa.Column("audit_version", sa.Text, nullable=False),
        # ─── Chave de cache ───────────────────────────────────────────────
        # sha256 canonical de (audit_version + inputs_snapshot). Inclusao
        # do audit_version garante invalidacao auto quando prompt muda.
        sa.Column("inputs_hash", sa.String(64), nullable=False),
        # JSON legivel pra debug/auditoria — nao usado pra lookup.
        sa.Column(
            "inputs_snapshot",
            postgresql.JSONB,
            nullable=False,
            comment="Inputs que entraram no hash (ua_id, data_d0, user_context, etc)",
        ),
        # ─── Output + metadados de execucao ───────────────────────────────
        sa.Column(
            "output_data",
            postgresql.JSONB,
            nullable=True,
            comment="JSON validado contra spec.output_schema. NULL se status=error.",
        ),
        sa.Column("output_schema_name", sa.String(128), nullable=False),
        sa.Column("model_used", sa.String(128), nullable=False),
        sa.Column("tokens_input", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_output", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_cache_read", sa.Integer, nullable=False, server_default="0"),
        sa.Column("tokens_cache_creation", sa.Integer, nullable=False, server_default="0"),
        sa.Column(
            "cost_brl_estimated",
            sa.Numeric(10, 4),
            nullable=True,
            comment="Custo estimado em BRL no momento da execucao (FX rate aplicada).",
        ),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column(
            "status",
            sa.String(16),
            nullable=False,
            server_default="success",
            comment="'success' | 'error' | 'partial' (parou no nivel 1 por sanity falho)",
        ),
        sa.Column("error_message", sa.Text, nullable=True),
        # ─── Audit trail ──────────────────────────────────────────────────
        sa.Column(
            "triggered_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "triggered_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        # ─── Invalidacao (soft delete pra cache) ──────────────────────────
        sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "invalidated_reason",
            sa.String(64),
            nullable=True,
            comment="'prompt_published' | 'data_reingested' | 'manual' | etc",
        ),
    )

    # UQ partial: 1 entrada VIVA por (tenant, agent, version, inputs_hash).
    # Multiplas invalidadas + 1 viva e o pattern.
    op.execute(
        "CREATE UNIQUE INDEX uq_agent_analysis_run_active "
        "ON agent_analysis_run (tenant_id, agent_name, agent_version, inputs_hash) "
        "WHERE invalidated_at IS NULL"
    )

    # Lookup do cache check — usa o partial UQ index acima (cobertura O(log n)).
    # Index adicional pra historico cronologico:
    op.create_index(
        "ix_agent_analysis_run_history",
        "agent_analysis_run",
        ["tenant_id", "agent_name", sa.text("triggered_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_analysis_run_history", table_name="agent_analysis_run")
    op.execute("DROP INDEX IF EXISTS uq_agent_analysis_run_active")
    op.drop_table("agent_analysis_run")
