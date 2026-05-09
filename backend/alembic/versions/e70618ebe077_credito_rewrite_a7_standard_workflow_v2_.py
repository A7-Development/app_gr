"""credito: rewrite A7 standard workflow v2 with 13 nodes in 4 phases

Revision ID: e70618ebe077
Revises: e2f1a8b3c4d5
Create Date: 2026-05-01 14:02:21.307858

Reescreve o workflow `credit.a7_standard` para v2 com a sequencia tipica
de uma analise de credito B2B em 4 fases:

    Fase 1 — Identificacao
        trigger -> cadastro_empresa -> enriquecimento_receita
        -> grupo_economico -> socios_representantes

    Fase 2 — Coleta
        doc_request -> [bureaus paralelo] (bureau_query placeholders)

    Fase 3 — Processamento
        extract_docs -> [6 specialist_agents paralelo] -> cross_ref

    Fase 4 — Decisao
        human_review -> pleito_formal -> opinion -> output

Cada `human_input` agora carrega `fields` no config (form descriptor),
para o frontend renderizar dinamicamente sem hardcode por form_id.

Mantem v1 historico, atualiza `workflow_definition_active` para apontar
para v2.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e70618ebe077"
down_revision: str | None = "e2f1a8b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ─── Form schemas (shared with frontend via API state) ────────────────────

CADASTRO_EMPRESA_FIELDS = [
    {"key": "cnpj", "type": "cnpj", "label": "CNPJ", "required": True, "placeholder": "00.000.000/0000-00"},
    {"key": "razao_social", "type": "string", "label": "Razao social", "required": True},
    {"key": "nome_fantasia", "type": "string", "label": "Nome fantasia"},
    {"key": "atividade_principal", "type": "string", "label": "Atividade principal (CNAE/descricao)"},
    {"key": "data_fundacao", "type": "date", "label": "Data de fundacao"},
    {"key": "endereco", "type": "textarea", "label": "Endereco completo"},
    {"key": "telefone", "type": "string", "label": "Telefone"},
    {"key": "email", "type": "email", "label": "E-mail comercial"},
    {"key": "site", "type": "string", "label": "Site"},
]

GRUPO_ECONOMICO_FIELDS = [
    {"key": "tem_grupo", "type": "boolean", "label": "A empresa faz parte de um grupo economico?"},
    {
        "key": "outros_cnpjs",
        "type": "textarea",
        "label": "Outros CNPJs do grupo (um por linha)",
        "placeholder": "12.345.678/0001-90\n98.765.432/0001-10",
    },
    {"key": "observacoes", "type": "textarea", "label": "Observacoes sobre o grupo"},
]

SOCIOS_FIELDS = [
    {
        "key": "socios",
        "type": "json",
        "label": "Socios (array de {nome, cpf, participacao_pct})",
        "placeholder": '[{"nome":"...","cpf":"...","participacao_pct":50}]',
        "required": True,
    },
    {
        "key": "representantes",
        "type": "json",
        "label": "Representantes legais (array de {nome, cpf, cargo, poder_assinatura})",
        "placeholder": '[{"nome":"...","cpf":"...","cargo":"Diretor","poder_assinatura":"isolada"}]',
    },
    {
        "key": "avalistas",
        "type": "json",
        "label": "Avalistas, se houver (array)",
    },
]

PLEITO_FORMAL_FIELDS = [
    {
        "key": "produto",
        "type": "select",
        "label": "Produto",
        "required": True,
        "options": ["cessao", "antecipacao", "garantia", "misto"],
    },
    {"key": "volume_brl", "type": "number", "label": "Volume pretendido (R$)", "required": True},
    {"key": "taxa", "type": "string", "label": "Taxa proposta", "placeholder": "ex: CDI + 6% a.a."},
    {"key": "prazo_dias", "type": "number", "label": "Prazo (dias)"},
    {"key": "garantias", "type": "textarea", "label": "Garantias oferecidas"},
    {"key": "condicoes", "type": "textarea", "label": "Condicoes adicionais"},
    {
        "key": "urgencia",
        "type": "select",
        "label": "Urgencia",
        "options": ["baixa", "media", "alta"],
    },
]


# ─── Workflow A7 standard v2 graph ────────────────────────────────────────

A7_STANDARD_V2_GRAPH = {
    "nodes": [
        # Fase 1 — Identificacao
        {
            "id": "trigger",
            "type": "trigger",
            "label": "Inicio",
            "config": {"kind": "manual"},
            "position": {"x": 80, "y": 40},
        },
        {
            "id": "cadastro_empresa",
            "type": "human_input",
            "label": "Cadastro da empresa",
            "config": {
                "form_id": "cadastro_empresa",
                "title": "Cadastro basico da empresa",
                "description": "Identifique a empresa-alvo da analise de credito.",
                "fields": CADASTRO_EMPRESA_FIELDS,
                "submit_label": "Salvar e prosseguir",
            },
            "position": {"x": 80, "y": 160},
        },
        {
            "id": "enriquecimento_receita",
            "type": "http_request",
            "label": "Enriquecer (Receita Federal)",
            "config": {
                "method": "GET",
                "url": "https://api.exemplo.receita/cnpj/{{node.cadastro_empresa.output.cnpj}}",
                "headers": {"Accept": "application/json"},
                "timeout_seconds": 15,
            },
            "position": {"x": 80, "y": 280},
        },
        {
            "id": "grupo_economico",
            "type": "human_input",
            "label": "Grupo economico",
            "config": {
                "form_id": "grupo_economico",
                "title": "Grupo economico",
                "description": "Outros CNPJs relacionados (deixe em branco se nao houver grupo).",
                "fields": GRUPO_ECONOMICO_FIELDS,
                "submit_label": "Continuar",
            },
            "position": {"x": 80, "y": 400},
        },
        {
            "id": "socios_representantes",
            "type": "human_input",
            "label": "Socios e representantes",
            "config": {
                "form_id": "socios_representantes",
                "title": "Socios, representantes e avalistas",
                "description": "Cadastro das pessoas fisicas envolvidas.",
                "fields": SOCIOS_FIELDS,
                "submit_label": "Continuar",
            },
            "position": {"x": 80, "y": 520},
        },
        # Fase 2 — Coleta
        {
            "id": "doc_request",
            "type": "document_request",
            "label": "Solicitar documentos",
            "config": {
                "required": ["dre", "balance_sheet", "revenue_report", "social_contract"],
                "optional": [
                    "income_tax_pf",
                    "cnh",
                    "commercial_visit",
                    "photo",
                    "abc_curve",
                    "scr",
                    "indebtedness",
                ],
            },
            "position": {"x": 80, "y": 660},
        },
        {
            "id": "bureau_serasa",
            "type": "bureau_query",
            "label": "Serasa PJ",
            "config": {"adapter": "serasa_pj", "entity_type": "company", "entity_ref": "{{node.cadastro_empresa.output.cnpj}}"},
            "position": {"x": -200, "y": 800},
        },
        {
            "id": "bureau_bigdata",
            "type": "bureau_query",
            "label": "BigDataCorp (processos)",
            "config": {"adapter": "bigdatacorp", "entity_type": "company", "entity_ref": "{{node.cadastro_empresa.output.cnpj}}"},
            "position": {"x": -50, "y": 800},
        },
        {
            "id": "bureau_infosimples",
            "type": "bureau_query",
            "label": "InfoSimples (protestos)",
            "config": {"adapter": "infosimples", "entity_type": "company", "entity_ref": "{{node.cadastro_empresa.output.cnpj}}"},
            "position": {"x": 100, "y": 800},
        },
        # Fase 3 — Processamento
        {
            "id": "extract_docs",
            "type": "document_extractor",
            "label": "Extrair documentos",
            "config": {"for_each": "uploaded_documents", "agent": "document_extractor"},
            "position": {"x": 80, "y": 940},
        },
        {
            "id": "social_analysis",
            "type": "specialist_agent",
            "label": "Contrato social",
            "config": {"agent": "social_contract_analyst"},
            "position": {"x": -300, "y": 1080},
        },
        {
            "id": "financial_analysis",
            "type": "specialist_agent",
            "label": "Financeiro",
            "config": {"agent": "financial_analyst"},
            "position": {"x": -150, "y": 1080},
        },
        {
            "id": "indebt_analysis",
            "type": "specialist_agent",
            "label": "Endividamento",
            "config": {"agent": "indebtedness_analyst"},
            "position": {"x": 0, "y": 1080},
        },
        {
            "id": "legal_analysis",
            "type": "specialist_agent",
            "label": "Juridico",
            "config": {"agent": "legal_analyst"},
            "position": {"x": 150, "y": 1080},
        },
        {
            "id": "partner_analysis",
            "type": "specialist_agent",
            "label": "Socios",
            "config": {"agent": "partner_analyst"},
            "position": {"x": 300, "y": 1080},
        },
        {
            "id": "visit_analysis",
            "type": "specialist_agent",
            "label": "Visita comercial",
            "config": {"agent": "commercial_visit_analyst"},
            "position": {"x": 450, "y": 1080},
        },
        {
            "id": "cross_ref",
            "type": "specialist_agent",
            "label": "Cross-reference",
            "config": {"agent": "cross_reference_analyst"},
            "position": {"x": 80, "y": 1240},
        },
        # Fase 4 — Decisao
        {
            "id": "human_review",
            "type": "human_review",
            "label": "Revisao do analista",
            "config": {"scope": "all_analyses"},
            "position": {"x": 80, "y": 1380},
        },
        {
            "id": "pleito_formal",
            "type": "human_input",
            "label": "Pleito formal",
            "config": {
                "form_id": "pleito_formal",
                "title": "Pleito formal para o comite",
                "description": (
                    "Com base nas analises, formalize o pleito que sera apresentado "
                    "ao comite de credito (produto, volume, taxa, prazo, garantias)."
                ),
                "fields": PLEITO_FORMAL_FIELDS,
                "submit_label": "Salvar pleito",
            },
            "position": {"x": 80, "y": 1500},
        },
        {
            "id": "opinion",
            "type": "specialist_agent",
            "label": "Parecer",
            "config": {"agent": "opinion_writer"},
            "position": {"x": 80, "y": 1620},
        },
        {
            "id": "output",
            "type": "output_generator",
            "label": "Gerar PDF",
            "config": {"format": "pdf"},
            "position": {"x": 80, "y": 1740},
        },
    ],
    "edges": [
        # Fase 1
        {"id": "e_t_cad", "source": "trigger", "target": "cadastro_empresa"},
        {"id": "e_cad_enriq", "source": "cadastro_empresa", "target": "enriquecimento_receita"},
        {"id": "e_enriq_grupo", "source": "enriquecimento_receita", "target": "grupo_economico"},
        {"id": "e_grupo_socios", "source": "grupo_economico", "target": "socios_representantes"},
        # Fase 2
        {"id": "e_socios_doc", "source": "socios_representantes", "target": "doc_request"},
        {"id": "e_socios_serasa", "source": "socios_representantes", "target": "bureau_serasa"},
        {"id": "e_socios_bigdata", "source": "socios_representantes", "target": "bureau_bigdata"},
        {"id": "e_socios_info", "source": "socios_representantes", "target": "bureau_infosimples"},
        # Fase 3 (extract_docs depende de doc_request; analyses dependem de extract + bureaus)
        {"id": "e_doc_extract", "source": "doc_request", "target": "extract_docs"},
        {"id": "e_extract_social", "source": "extract_docs", "target": "social_analysis"},
        {"id": "e_extract_fin", "source": "extract_docs", "target": "financial_analysis"},
        {"id": "e_extract_indebt", "source": "extract_docs", "target": "indebt_analysis"},
        {"id": "e_extract_legal", "source": "extract_docs", "target": "legal_analysis"},
        {"id": "e_extract_partner", "source": "extract_docs", "target": "partner_analysis"},
        {"id": "e_extract_visit", "source": "extract_docs", "target": "visit_analysis"},
        {"id": "e_serasa_indebt", "source": "bureau_serasa", "target": "indebt_analysis"},
        {"id": "e_bigdata_legal", "source": "bureau_bigdata", "target": "legal_analysis"},
        {"id": "e_info_legal", "source": "bureau_infosimples", "target": "legal_analysis"},
        {"id": "e_social_cross", "source": "social_analysis", "target": "cross_ref"},
        {"id": "e_fin_cross", "source": "financial_analysis", "target": "cross_ref"},
        {"id": "e_indebt_cross", "source": "indebt_analysis", "target": "cross_ref"},
        {"id": "e_legal_cross", "source": "legal_analysis", "target": "cross_ref"},
        {"id": "e_partner_cross", "source": "partner_analysis", "target": "cross_ref"},
        {"id": "e_visit_cross", "source": "visit_analysis", "target": "cross_ref"},
        # Fase 4
        {"id": "e_cross_review", "source": "cross_ref", "target": "human_review"},
        {"id": "e_review_pleito", "source": "human_review", "target": "pleito_formal"},
        {"id": "e_pleito_opinion", "source": "pleito_formal", "target": "opinion"},
        {"id": "e_opinion_output", "source": "opinion", "target": "output"},
    ],
}


def upgrade() -> None:
    A7_V2_ID = "33333333-3333-3333-3333-000000000002"

    # 1. Insert v2 of credit.a7_standard
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
                "id": A7_V2_ID,
                "tenant_id": None,
                "name": "credit.a7_standard",
                "version": 2,
                "description": (
                    "Processo padrao A7 Credit v2 — sequencia tipica de analise de "
                    "credito B2B em 4 fases (identificacao, coleta, processamento, "
                    "decisao). Pleito agora vem APOS a analise (formalizado pelo "
                    "analista com base nos achados). Forms genericos (config.fields) "
                    "renderizados pelo frontend."
                ),
                "category": "credit",
                # NOTE (bug-fix em `4dfbd64002b5`): pass dict direto, NAO json.dumps.
                "graph": A7_STANDARD_V2_GRAPH,
                "status": "ACTIVE",
                "created_by": None,
            }
        ],
    )

    # 2. Update active pointer to v2 (cast UUIDs explicitly)
    op.execute(
        sa.text(
            "UPDATE workflow_definition_active "
            "SET active_definition_id = CAST(:new_id AS uuid), activated_at = now() "
            "WHERE name = :name AND tenant_id IS NULL"
        ).bindparams(new_id=A7_V2_ID, name="credit.a7_standard")
    )

    # 3. Mark v1 as ARCHIVED (kept for history)
    op.execute(
        sa.text(
            "UPDATE workflow_definition "
            "SET status = 'ARCHIVED', archived_at = now() "
            "WHERE id = CAST(:v1_id AS uuid)"
        ).bindparams(v1_id="33333333-3333-3333-3333-000000000001")
    )


def downgrade() -> None:
    # Revert: point active back to v1, unarchive v1, delete v2.
    op.execute(
        sa.text(
            "UPDATE workflow_definition_active "
            "SET active_definition_id = CAST(:v1_id AS uuid), activated_at = now() "
            "WHERE name = :name AND tenant_id IS NULL"
        ).bindparams(
            v1_id="33333333-3333-3333-3333-000000000001",
            name="credit.a7_standard",
        )
    )
    op.execute(
        sa.text(
            "UPDATE workflow_definition "
            "SET status = 'ACTIVE', archived_at = NULL "
            "WHERE id = CAST(:v1_id AS uuid)"
        ).bindparams(v1_id="33333333-3333-3333-3333-000000000001")
    )
    op.execute(
        sa.text(
            "DELETE FROM workflow_definition WHERE id = CAST(:v2_id AS uuid)"
        ).bindparams(v2_id="33333333-3333-3333-3333-000000000002")
    )
