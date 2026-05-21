"""F2.b.1: agent_definition + agent_persona + agent_expertise (catalogo central)

Revision ID: a7b3c9f2e1d4
Revises: c8a3d2b1f7e9
Create Date: 2026-05-21 11:00:00.000000

Cria 6 tabelas pro catalogo central de agentes (CLAUDE.md §19.12):
    agent_persona            + agent_persona_active
    agent_expertise          + agent_expertise_active
    agent_definition         + agent_definition_active

Parent: `c8a3d2b1f7e9` (qitech silvers add_raw_id_fk) — HEAD aplicado em
prod no momento desta migration. As outras 2 branches divergentes
(`7f1a9c4e2d83` COSIF grupo3 e `c1e7b2a4d5f3` DRE classification rule)
ficam como branches separadas — quem criou aplica + faz seu proprio
merge quando for re-anexar a chain principal.

Seed inicial (idempotente via ON CONFLICT DO NOTHING):
- 10 personas placeholder (1:1 com agentes do CATALOG atual em
  app/agentic/engine/catalog.py). role_block e curto e generico — o
  curador edita depois via /admin/ia/personas (F2.c).
- 0 expertises — tabela criada vazia. Curador semeia conforme demanda.
- 10 agent_definition globais (tenant_id=NULL) referenciando as
  personas. expertise_ids=NULL por enquanto.

Por que tudo numa migration so:
- Schema + seed sao atomicos no upgrade — DB recem-aplicado ja chega
  pronto pra ser lido por endpoint /admin/ia/agents (mesmo que UI seja
  read-only no F2.b.1).
- Rollback (downgrade) apaga schema e seed juntos. Sem orfaos.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision = "a7b3c9f2e1d4"
down_revision = "c8a3d2b1f7e9"
branch_labels = None
depends_on = None


# ─── UUIDs determinsticos pro seed ─────────────────────────────────────────
# Formato: <kind>-<index>-4000-8000-000000000000. UUID v4 valido.
#   kind: 11111111 = persona, 22222222 = definition
#   index: 0001..0010 = ordem dos agentes do CATALOG

_AGENTS = [
    # (agent_name, persona_name, persona_display, prompt_name, role_block_summary)
    (
        "social_contract_analyst",
        "credito.analista_contrato_social",
        "Analista de Contrato Social",
        "agent.social_contract",
        "Voce e Analista de Contrato Social FIDC. Avalia firmas, poderes "
        "de assinatura, alteracoes de QSA e objeto social. Sinaliza red "
        "flags juridicos sobre representacao.",
    ),
    (
        "financial_analyst",
        "credito.analista_financial",
        "Analista Financeiro",
        "agent.financial",
        "Voce e Analista Financeiro Senior. Domina DRE, balanco e "
        "fluxo de caixa. Calcula indicadores (margem, ebitda, debt-to-"
        "equity), identifica tendencias e sinaliza vulnerabilidades.",
    ),
    (
        "indebtedness_analyst",
        "credito.analista_endividamento",
        "Analista de Endividamento",
        "agent.indebtedness",
        "Voce e Analista de Endividamento. Avalia SCR Bacen, dividas "
        "declaradas, concentracao bancaria e capacidade de servico de "
        "divida. Compara declarado vs SCR.",
    ),
    (
        "legal_analyst",
        "credito.analista_juridico",
        "Analista Juridico",
        "agent.legal",
        "Voce e Analista Juridico de credito. Classifica risco de "
        "processos judiciais ativos, valor em disputa, protestos "
        "cartoriais. Distingue trabalhista de fiscal de civel.",
    ),
    (
        "partner_analyst",
        "credito.analista_socios",
        "Analista de Socios",
        "agent.partners",
        "Voce e Analista de Socios. Avalia QSA, patrimonio dos socios, "
        "processos contra socios, ligacoes empresariais. Sinaliza socio-"
        "laranja, sucessao opaca.",
    ),
    (
        "commercial_visit_analyst",
        "credito.analista_visita_comercial",
        "Analista de Visita Comercial",
        "agent.commercial_visit",
        "Voce e Analista de Visita Comercial. Avalia relatorio de visita "
        "in loco contra dados declarados. Sinaliza inconsistencia "
        "operacional (endereco, instalacoes, estoque).",
    ),
    (
        "cross_reference_analyst",
        "credito.analista_cruzamento",
        "Analista de Cruzamento de Dados",
        "agent.cross_reference",
        "Voce e Analista de Cruzamento. Le saidas de outros specialist "
        "agents e identifica contradicoes (faturamento declarado vs "
        "DRE, socios declarados vs QSA, etc).",
    ),
    (
        "opinion_writer",
        "credito.parecerista",
        "Parecerista Senior de Credito",
        "agent.opinion",
        "Voce e Parecerista Senior de Credito. Consolida analises "
        "anteriores em parecer estruturado com recomendacao final "
        "(aprovar / aprovar com restricao / rejeitar) e justificativa.",
    ),
    (
        "document_extractor",
        "credito.extrator_documentos",
        "Extrator de Documentos",
        "extract.document",
        "Voce e Extrator de Documentos. Le PDFs/imagens via Vision e "
        "extrai dados estruturados em JSON conforme schema. Reporta "
        "campos ilegiveis honestamente.",
    ),
    (
        "pleito_extractor",
        "credito.extrator_pleito",
        "Extrator de Pleito",
        "extract.pleito_informal",
        "Voce e Extrator de Pleito. Le emails/textos informais do "
        "comercial e extrai campos canonicos: CNPJ, valor pleiteado, "
        "produto, prazo, observacoes.",
    ),
]


def _persona_uuid(idx: int) -> str:
    return f"11111111-{idx:04d}-4000-8000-000000000000"


def _definition_uuid(idx: int) -> str:
    return f"22222222-{idx:04d}-4000-8000-000000000000"


def upgrade() -> None:
    # ─── agent_persona ──────────────────────────────────────────────────
    op.create_table(
        "agent_persona",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("role_block", sa.Text, nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("expertise_domains", postgresql.ARRAY(sa.String), nullable=True),
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
            server_default=sa.func.now(),
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("name", "version", name="uq_agent_persona_name_version"),
    )
    op.create_index("ix_agent_persona_name", "agent_persona", ["name"])

    # ─── agent_persona_active ───────────────────────────────────────────
    op.create_table(
        "agent_persona_active",
        sa.Column("name", sa.String(128), primary_key=True),
        sa.Column(
            "persona_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_persona.id"),
            nullable=False,
        ),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "activated_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )

    # ─── agent_expertise ────────────────────────────────────────────────
    op.create_table(
        "agent_expertise",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("domain", sa.String(64), nullable=False),
        sa.Column("knowledge_text", sa.Text, nullable=False),
        sa.Column("reference_urls", postgresql.JSONB, nullable=True),
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
            server_default=sa.func.now(),
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("name", "version", name="uq_agent_expertise_name_version"),
    )
    op.create_index("ix_agent_expertise_name", "agent_expertise", ["name"])
    op.create_index("ix_agent_expertise_domain", "agent_expertise", ["domain"])

    # ─── agent_expertise_active ─────────────────────────────────────────
    op.create_table(
        "agent_expertise_active",
        sa.Column("name", sa.String(128), primary_key=True),
        sa.Column(
            "expertise_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_expertise.id"),
            nullable=False,
        ),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "activated_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )

    # ─── agent_definition ───────────────────────────────────────────────
    op.create_table(
        "agent_definition",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=True,  # NULL = global, NOT NULL = custom de tenant
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("module", sa.String(32), nullable=False),
        sa.Column(
            "persona_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_persona.id"),
            nullable=True,
        ),
        sa.Column(
            "expertise_ids",
            postgresql.ARRAY(postgresql.UUID(as_uuid=True)),
            nullable=True,
        ),
        sa.Column("prompt_name", sa.String(128), nullable=False),
        sa.Column("model", sa.String(64), nullable=True),
        sa.Column("fallback_model", sa.String(64), nullable=True),
        sa.Column("temperature", sa.Numeric(3, 2), nullable=True),
        sa.Column("max_tokens", sa.Integer, nullable=True),
        sa.Column(
            "cross_module",
            sa.Boolean,
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("credit_hint", sa.Integer, nullable=True),
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
            server_default=sa.func.now(),
        ),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id", "name", "version",
            name="uq_agent_definition_tenant_name_version",
        ),
    )
    op.create_index(
        "ix_agent_definition_tenant_name", "agent_definition",
        ["tenant_id", "name"],
    )
    op.create_index("ix_agent_definition_module", "agent_definition", ["module"])

    # ─── agent_definition_active ────────────────────────────────────────
    op.create_table(
        "agent_definition_active",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tenants.id"),
            nullable=True,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "definition_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("agent_definition.id"),
            nullable=False,
        ),
        sa.Column(
            "activated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "activated_by_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "tenant_id", "name",
            name="uq_agent_definition_active_tenant_name",
        ),
    )

    # ─── Seed: 10 personas + 10 agent_definitions (globais) ─────────────
    for idx, (agent_name, persona_name, persona_display, prompt_name, role_block) in enumerate(
        _AGENTS, start=1
    ):
        persona_id = _persona_uuid(idx)
        definition_id = _definition_uuid(idx)

        op.execute(
            sa.text(
                "INSERT INTO agent_persona "
                "(id, name, version, display_name, role_block, description, expertise_domains) "
                "VALUES (CAST(:id AS uuid), :name, 1, :display_name, :role_block, :description, "
                "ARRAY['credito']::varchar[]) "
                "ON CONFLICT DO NOTHING"
            ).bindparams(
                id=persona_id,
                name=persona_name,
                display_name=persona_display,
                role_block=role_block,
                description="Persona placeholder seedada em F2.b.1. Editar via /admin/ia/personas (F2.c).",
            )
        )
        op.execute(
            sa.text(
                "INSERT INTO agent_persona_active (name, persona_id) "
                "VALUES (:name, CAST(:persona_id AS uuid)) "
                "ON CONFLICT DO NOTHING"
            ).bindparams(name=persona_name, persona_id=persona_id)
        )
        op.execute(
            sa.text(
                "INSERT INTO agent_definition "
                "(id, tenant_id, name, version, module, persona_id, prompt_name, cross_module) "
                "VALUES (CAST(:id AS uuid), NULL, :name, 1, 'credito', "
                "CAST(:persona_id AS uuid), :prompt_name, false) "
                "ON CONFLICT DO NOTHING"
            ).bindparams(
                id=definition_id,
                name=f"credito.{agent_name}",
                persona_id=persona_id,
                prompt_name=prompt_name,
            )
        )
        op.execute(
            sa.text(
                "INSERT INTO agent_definition_active "
                "(id, tenant_id, name, definition_id) "
                "VALUES (gen_random_uuid(), NULL, :name, CAST(:definition_id AS uuid)) "
                "ON CONFLICT DO NOTHING"
            ).bindparams(
                name=f"credito.{agent_name}",
                definition_id=definition_id,
            )
        )


def downgrade() -> None:
    # Ordem reversa (FKs).
    op.drop_table("agent_definition_active")
    op.drop_index("ix_agent_definition_module", table_name="agent_definition")
    op.drop_index("ix_agent_definition_tenant_name", table_name="agent_definition")
    op.drop_table("agent_definition")
    op.drop_table("agent_expertise_active")
    op.drop_index("ix_agent_expertise_domain", table_name="agent_expertise")
    op.drop_index("ix_agent_expertise_name", table_name="agent_expertise")
    op.drop_table("agent_expertise")
    op.drop_table("agent_persona_active")
    op.drop_index("ix_agent_persona_name", table_name="agent_persona")
    op.drop_table("agent_persona")
