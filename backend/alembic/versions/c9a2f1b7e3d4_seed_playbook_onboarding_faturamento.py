"""seed playbook credit.onboarding_faturamento (jornada faturamento + cadastral)

Esteira de credito (2026-06-05) — fatia faturamento, jornada ponta-a-ponta
provando "como o processo avanca" com os dois eventos que JA temos vivos:
ingestao da declaracao de faturamento (extracao multimodal) + consulta de
dados basicos (BigDataCorp cadastral, white-label).

Grafo SEQUENCIAL (Ricardo 2026-06-05: sequenciais + checkpoint por analise):

    trigger
      -> identificacao        (human_input: cnpj, razao_social)
      -> dados_basicos        (cadastral_enrichment, public_code=CAD-PJ) [auto]
      -> coleta_faturamento   (document_request: revenue_report)
      -> analise_faturamento  (specialist_agent: revenue_analyst)
      -> checkpoint_faturamento (human_review, review_of=revenue_analyst)
      -> analise_cadastral    (specialist_agent: cadastral_analyst)
      -> checkpoint_cadastral (human_review, review_of=cadastral_analyst)
      -> parecer              (specialist_agent: opinion_writer)
      -> checkpoint_final     (human_review: parecer rascunho + finalizar)
      -> output               (output_generator)

Os agentes leem o dado HOMOLOGADO via read-tools (get_declaracao_faturamento /
get_dados_cadastrais) — silver-first, provider-blind (§13.2.1 + white-label).
Template global (tenant_id NULL); editavel no builder.

Revision ID: c9a2f1b7e3d4
Revises: b2d9f4a7c1e6
Create Date: 2026-06-05
"""
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "c9a2f1b7e3d4"
down_revision: str | None = "b2d9f4a7c1e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_DEF_ID = "44444444-4444-4444-4444-000000000002"
_ACTIVE_ID = "44444444-4444-4444-4444-0000000000a2"
_WF_NAME = "credit.onboarding_faturamento"

IDENTIFICACAO_FIELDS = [
    {"key": "cnpj", "type": "cnpj", "label": "CNPJ", "required": True,
     "placeholder": "00.000.000/0000-00"},
    {"key": "razao_social", "type": "string", "label": "Razao social", "required": True},
]

GRAPH = {
    "nodes": [
        {
            "id": "trigger",
            "type": "trigger",
            "label": "Inicio",
            "config": {"kind": "manual"},
            "position": {"x": 80, "y": 40},
        },
        {
            "id": "identificacao",
            "type": "human_input",
            "label": "Identificacao da empresa",
            "config": {
                "form_id": "identificacao",
                "title": "Empresa-alvo",
                "description": "Informe o CNPJ e a razao social da empresa a analisar.",
                "fields": IDENTIFICACAO_FIELDS,
                "submit_label": "Salvar e prosseguir",
            },
            "position": {"x": 80, "y": 160},
        },
        {
            "id": "dados_basicos",
            "type": "cadastral_enrichment",
            "label": "Dados cadastrais (consulta oficial)",
            "config": {"public_code": "CAD-PJ"},
            "position": {"x": 80, "y": 290},
        },
        {
            "id": "coleta_faturamento",
            "type": "document_request",
            "label": "Coleta da declaracao de faturamento",
            "config": {"required": ["revenue_report"], "optional": []},
            "position": {"x": 80, "y": 420},
        },
        {
            "id": "analise_faturamento",
            "type": "specialist_agent",
            "label": "Analise de faturamento (IA)",
            "config": {"agent": "revenue_analyst"},
            "position": {"x": 80, "y": 550},
        },
        {
            "id": "checkpoint_faturamento",
            "type": "human_review",
            "label": "Conferencia: faturamento",
            "config": {
                "review_of": "revenue_analyst",
                "scope": "analise_faturamento",
                "title": "Conferencia da analise de faturamento",
                "description": (
                    "Revise a leitura do agente (tendencia, sazonalidade, "
                    "picos/vales e credibilidade do documento). Ajuste se "
                    "necessario e aprove para prosseguir."
                ),
            },
            "position": {"x": 80, "y": 680},
        },
        {
            "id": "analise_cadastral",
            "type": "specialist_agent",
            "label": "Analise cadastral (IA)",
            "config": {"agent": "cadastral_analyst"},
            "position": {"x": 80, "y": 810},
        },
        {
            "id": "checkpoint_cadastral",
            "type": "human_review",
            "label": "Conferencia: cadastral",
            "config": {
                "review_of": "cadastral_analyst",
                "scope": "analise_cadastral",
                "title": "Conferencia da analise cadastral",
                "description": (
                    "Revise a leitura do agente sobre a saude cadastral "
                    "(situacao, tempo de atividade, CNAE, capital). Ajuste se "
                    "necessario e aprove."
                ),
            },
            "position": {"x": 80, "y": 940},
        },
        {
            "id": "parecer",
            "type": "specialist_agent",
            "label": "Parecer consolidado (IA)",
            "config": {"agent": "opinion_writer"},
            "position": {"x": 80, "y": 1070},
        },
        {
            "id": "checkpoint_final",
            "type": "human_review",
            "label": "Conferencia final e parecer",
            "config": {
                "scope": "final_opinion",
                "title": "Conferencia final",
                "description": (
                    "Revise o parecer consolidado, ajuste a recomendacao e "
                    "finalize a analise."
                ),
            },
            "position": {"x": 80, "y": 1200},
        },
        {
            "id": "output",
            "type": "output_generator",
            "label": "Saida final",
            "config": {"format": "pdf"},
            "position": {"x": 80, "y": 1330},
        },
    ],
    "edges": [
        {"id": "e1", "source": "trigger", "target": "identificacao"},
        {"id": "e2", "source": "identificacao", "target": "dados_basicos"},
        {"id": "e3", "source": "dados_basicos", "target": "coleta_faturamento"},
        {"id": "e4", "source": "coleta_faturamento", "target": "analise_faturamento"},
        {"id": "e5", "source": "analise_faturamento", "target": "checkpoint_faturamento"},
        {"id": "e6", "source": "checkpoint_faturamento", "target": "analise_cadastral"},
        {"id": "e7", "source": "analise_cadastral", "target": "checkpoint_cadastral"},
        {"id": "e8", "source": "checkpoint_cadastral", "target": "parecer"},
        {"id": "e9", "source": "parecer", "target": "checkpoint_final"},
        {"id": "e10", "source": "checkpoint_final", "target": "output"},
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
                "id": _DEF_ID,
                "tenant_id": None,
                "name": _WF_NAME,
                "version": 1,
                "description": (
                    "Onboarding com faturamento + dados cadastrais: identificacao "
                    "-> enriquecimento cadastral -> coleta da declaracao de "
                    "faturamento -> analise de faturamento (IA) + conferencia -> "
                    "analise cadastral (IA) + conferencia -> parecer consolidado "
                    "-> conferencia final. Editavel no builder."
                ),
                "category": "credit",
                "graph": GRAPH,
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
        sa.text(
            "DELETE FROM workflow_definition_active WHERE id = CAST(:i AS uuid)"
        ).bindparams(i=_ACTIVE_ID)
    )
    op.execute(
        sa.text("DELETE FROM workflow_definition WHERE id = CAST(:i AS uuid)").bindparams(
            i=_DEF_ID
        )
    )
