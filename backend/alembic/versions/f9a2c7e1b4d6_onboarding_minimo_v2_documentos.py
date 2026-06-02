"""onboarding_minimo v2 — node document_request (coleta de documentos)

Promove `credit.onboarding_minimo` para v2 inserindo o node `coleta_documentos`
(document_request) entre o cadastro e o gate de elegibilidade:

    trigger -> cadastro -> coleta_documentos -> gate_elegibilidade -> ...

O node pausa o fluxo enquanto faltarem os documentos obrigatorios (DRE, balanco,
faturamento, contrato social) — o analista sobe via o painel do cockpit
(DocumentWorkspace), clica "Processar" (extracao multimodal sob demanda) e
"Continuar"; o node re-checa `credit_dossier_document` e so avanca quando os
obrigatorios chegaram. Os opcionais (SCR, endividamento, curva ABC, IR socio)
ficam disponiveis mas nao bloqueiam.

Troca de versao = 1 UPDATE no active pointer (rollback de 1 click). v1 fica
preservada (audit trail).

Revision ID: f9a2c7e1b4d6
Revises: c3f8b1d6e4a2
Create Date: 2026-06-02
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "f9a2c7e1b4d6"
down_revision: str | None = "c3f8b1d6e4a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DEF_ID_V1 = "44444444-4444-4444-4444-000000000001"
_DEF_ID_V2 = "44444444-4444-4444-4444-000000000002"
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

ONBOARDING_MINIMO_GRAPH_V2 = {
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
            "id": "coleta_documentos",
            "type": "document_request",
            "label": "Coleta de documentos",
            "config": {
                "required": ["dre", "balance_sheet", "revenue_report", "social_contract"],
                "optional": ["scr", "indebtedness", "abc_curve", "income_tax_pf"],
            },
            "position": {"x": 80, "y": 290},
        },
        {
            "id": "gate_elegibilidade",
            "type": "deterministic_check",
            "label": "Elegibilidade (idade da empresa)",
            "config": {"check": "company_founding_age", "policy_name": "default"},
            "position": {"x": 80, "y": 430},
        },
        {
            "id": "cruzamento_socios",
            "type": "deterministic_check",
            "label": "Cruzamento: soma das participacoes",
            "config": {"check": "ownership_sum", "tolerance_pct": 0.5},
            "position": {"x": 280, "y": 550},
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
            "position": {"x": 80, "y": 690},
        },
    ],
    "edges": [
        {"id": "e_trigger_cad", "source": "trigger", "target": "cadastro"},
        # cadastro -> coleta de documentos -> gate (novo no v2)
        {"id": "e_cad_docs", "source": "cadastro", "target": "coleta_documentos"},
        {"id": "e_docs_gate", "source": "coleta_documentos", "target": "gate_elegibilidade"},
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
                "id": _DEF_ID_V2,
                "tenant_id": None,
                "name": _WF_NAME,
                "version": 2,
                "description": (
                    "Onboarding minimo v2 (Fatia 1 + documentos): cadastro -> "
                    "coleta de documentos (DRE/balanco/faturamento/contrato) -> "
                    "gate de elegibilidade -> cruzamento de participacoes -> "
                    "conferencia do analista. Editavel no builder."
                ),
                "category": "credit",
                "graph": ONBOARDING_MINIMO_GRAPH_V2,
                "status": "ACTIVE",
                "created_by": None,
            }
        ],
    )

    # Active pointer aponta para v2 (rollback de 1 click).
    op.execute(
        sa.text(
            "UPDATE workflow_definition_active "
            "SET active_definition_id = CAST(:v2 AS uuid) "
            "WHERE id = CAST(:active AS uuid)"
        ).bindparams(v2=_DEF_ID_V2, active=_ACTIVE_ID)
    )


def downgrade() -> None:
    op.execute(
        sa.text(
            "UPDATE workflow_definition_active "
            "SET active_definition_id = CAST(:v1 AS uuid) "
            "WHERE id = CAST(:active AS uuid)"
        ).bindparams(v1=_DEF_ID_V1, active=_ACTIVE_ID)
    )
    op.execute(
        sa.text("DELETE FROM workflow_definition WHERE id = CAST(:i AS uuid)").bindparams(
            i=_DEF_ID_V2
        )
    )
