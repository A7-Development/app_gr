"""seed Fatia 1 — credit_policy default + playbook credit.onboarding_minimo

Semeia o que torna a Fatia 1 EXECUTAVEL (nao e codigo de pipeline; e uma
composicao de exemplo dos blocos, editavel no builder):

  1. credit_policy 'default' v1 (por tenant existente) — regra inicial:
     tempo de fundacao > 3 anos (min_company_age_years=3) + active pointer.

  2. playbook `credit.onboarding_minimo` (template global, tenant_id NULL):
        trigger
          -> cadastro (human_input: cnpj, razao_social, data_fundacao, socios[])
          -> gate_elegibilidade (deterministic_check: company_founding_age)
               --result truthy--> cruzamento_socios (deterministic_check: ownership_sum)
                                    -> checkpoint (human_review, join_mode=any)
               --result == False--> checkpoint  (reprovado pula o cruzamento)
     Termina no checkpoint humano — o parecer rascunho (credit_dossier_opinion)
     e criado pelo wizard na finalizacao (Fatia 1, deterministico, sem LLM).

Routing por edge condition: aprovacao usa template puro `{{...result}}` (bool
cru -> truthy); reprovacao usa `== False` (casa com str(False)). O checkpoint
converge os dois ramos com join_mode="any".

Revision ID: d3b7f1a9c2e5
Revises: b6f2d8a0c4e7
Create Date: 2026-06-01
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "d3b7f1a9c2e5"
down_revision: str | None = "b6f2d8a0c4e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DEF_ID = "44444444-4444-4444-4444-000000000001"
_ACTIVE_ID = "44444444-4444-4444-4444-0000000000a1"
_WF_NAME = "credit.onboarding_minimo"

CADASTRO_FIELDS = [
    {"key": "cnpj", "type": "cnpj", "label": "CNPJ", "required": True,
     "placeholder": "00.000.000/0000-00"},
    {"key": "razao_social", "type": "string", "label": "Razao social", "required": True},
    {"key": "data_fundacao", "type": "date", "label": "Data de fundacao", "required": True},
    {
        "key": "socios",
        "type": "json",
        "label": "Socios (array de {nome, cpf, participacao_pct})",
        "placeholder": '[{"nome":"...","cpf":"...","participacao_pct":50}]',
        "required": True,
    },
]

ONBOARDING_MINIMO_GRAPH = {
    "nodes": [
        {
            "id": "trigger",
            "type": "trigger",
            "label": "Inicio",
            "config": {"kind": "manual"},
            "position": {"x": 80, "y": 40},
        },
        {
            "id": "cadastro",
            "type": "human_input",
            "label": "Cadastro da empresa e socios",
            "config": {
                "form_id": "cadastro",
                "title": "Cadastro da empresa-alvo",
                "description": (
                    "Identifique a empresa, a data de fundacao e o quadro de "
                    "socios com participacao."
                ),
                "fields": CADASTRO_FIELDS,
                "submit_label": "Salvar e prosseguir",
            },
            "position": {"x": 80, "y": 160},
        },
        {
            "id": "gate_elegibilidade",
            "type": "deterministic_check",
            "label": "Elegibilidade (idade da empresa)",
            "config": {"check": "company_founding_age", "policy_name": "default"},
            "position": {"x": 80, "y": 300},
        },
        {
            "id": "cruzamento_socios",
            "type": "deterministic_check",
            "label": "Cruzamento: soma das participacoes",
            "config": {"check": "ownership_sum", "tolerance_pct": 0.5},
            "position": {"x": 280, "y": 420},
        },
        {
            "id": "checkpoint",
            "type": "human_review",
            "label": "Conferencia do analista",
            "config": {
                "scope": "fatia1_onboarding",
                "title": "Conferencia da analise",
                "description": (
                    "Revise o resultado da elegibilidade e as flags de "
                    "cruzamento. Edite o que for necessario e finalize o "
                    "parecer."
                ),
            },
            "join_mode": "any",
            "position": {"x": 80, "y": 560},
        },
    ],
    "edges": [
        {"id": "e_trigger_cad", "source": "trigger", "target": "cadastro"},
        {"id": "e_cad_gate", "source": "cadastro", "target": "gate_elegibilidade"},
        # Aprovado (result truthy) -> roda o cruzamento de socios.
        {
            "id": "e_gate_cruz",
            "source": "gate_elegibilidade",
            "target": "cruzamento_socios",
            "condition": "{{node.gate_elegibilidade.output.result}}",
        },
        # Reprovado (result == False) -> pula o cruzamento, vai ao checkpoint.
        {
            "id": "e_gate_check",
            "source": "gate_elegibilidade",
            "target": "checkpoint",
            "condition": "{{node.gate_elegibilidade.output.result}} == False",
        },
        {"id": "e_cruz_check", "source": "cruzamento_socios", "target": "checkpoint"},
    ],
}


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. credit_policy default (por tenant) — idade > 3 anos ──────────
    bind.execute(
        sa.text(
            "INSERT INTO credit_policy "
            "(id, tenant_id, name, version, min_company_age_years, description, "
            " created_at, updated_at) "
            "SELECT gen_random_uuid(), t.id, 'default', 'v1', 3, "
            "'Politica inicial: tempo de fundacao > 3 anos.', now(), now() "
            "FROM tenants t"
        )
    )
    bind.execute(
        sa.text(
            "INSERT INTO credit_policy_active (tenant_id, name, active_version, changed_at) "
            "SELECT t.id, 'default', 'v1', now() FROM tenants t"
        )
    )

    # ── 2. playbook credit.onboarding_minimo (template global) ──────────
    wf_def = sa.table(
        "workflow_definition",
        sa.column("id", sa.UUID()),
        sa.column("tenant_id", sa.UUID()),
        sa.column("name", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("description", sa.Text()),
        sa.column("category", sa.String()),
        sa.column("graph", postgresql.JSONB()),
        sa.column("status", sa.String()),
        sa.column("created_by", sa.UUID()),
    )
    op.bulk_insert(
        wf_def,
        [
            {
                "id": _DEF_ID,
                "tenant_id": None,
                "name": _WF_NAME,
                "version": 1,
                "description": (
                    "Onboarding minimo (Fatia 1): cadastro -> gate de elegibilidade "
                    "(idade da empresa) -> cruzamento de participacoes -> conferencia "
                    "do analista. Composicao de exemplo dos blocos; editavel no builder."
                ),
                "category": "credit",
                "graph": ONBOARDING_MINIMO_GRAPH,
                "status": "ACTIVE",
                "created_by": None,
            }
        ],
    )

    wf_active = sa.table(
        "workflow_definition_active",
        sa.column("id", sa.UUID()),
        sa.column("name", sa.String()),
        sa.column("tenant_id", sa.UUID()),
        sa.column("active_definition_id", sa.UUID()),
    )
    op.bulk_insert(
        wf_active,
        [
            {
                "id": _ACTIVE_ID,
                "name": _WF_NAME,
                "tenant_id": None,
                "active_definition_id": _DEF_ID,
            }
        ],
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM workflow_definition_active WHERE id = CAST(:i AS uuid)").bindparams(
            i=_ACTIVE_ID
        )
    )
    op.execute(
        sa.text("DELETE FROM workflow_definition WHERE id = CAST(:i AS uuid)").bindparams(
            i=_DEF_ID
        )
    )
    op.execute(
        sa.text(
            "DELETE FROM credit_policy_active WHERE name = 'default' AND active_version = 'v1'"
        )
    )
    op.execute(
        sa.text("DELETE FROM credit_policy WHERE name = 'default' AND version = 'v1'")
    )
