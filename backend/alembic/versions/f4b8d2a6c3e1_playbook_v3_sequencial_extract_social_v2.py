"""playbook v3 (ordem sequencial) + extract.social_contract v2 (cláusulas)

Dois ajustes do primeiro uso real da esteira (Ricardo, 2026-06-12):

1. PLAYBOOK `credit.onboarding_faturamento` vN+1 — ORDEM SEQUENCIAL.
   O grafo v2 intercalava: a análise cadastral rodava DEPOIS do checkpoint
   de faturamento (herança do seed v1), então a estação Cadastral ficava
   "meio feita" enquanto a Faturamento trabalhava — e a condução pulava
   2→3→2. Decisão: condução sequencial, mesmo que o analista espere.
   Nova ordem: identificação → dados básicos → análise cadastral +
   conferência → faturamento (coleta → análise → conferência) → contrato
   social (coleta → cruzamentos → análise → conferência) → parecer.
   Lê o graph ATIVO atual, REORDENA as edges (nodes intactos), grava como
   versão N+1, flipa o pointer e arquiva a anterior.

2. PROMPT `extract.social_contract` v2 — CLÁUSULAS, não só ficha.
   A v1 extraía só a ficha (CNPJ, sócios, capital...) — cláusulas de
   poderes de assinatura e ALÇADAS (ex.: "transações acima de 20% do
   capital exigem aprovação dos administradores + ¾ das cotas") nunca
   chegavam ao agente, que analisava no escuro. A v2 extrai também:
   administradores (sócio ou não), poderes de assinatura, restrições
   estatutárias/alçadas e a última alteração contratual. Tudo cai em
   extracted_fields → ficha de conferência → read-tool → agente.

Idempotente (guardas por presença).

Revision ID: f4b8d2a6c3e1
Revises: e2f5a8c1b9d4
Create Date: 2026-06-12
"""
import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f4b8d2a6c3e1"
down_revision: str | None = "e2f5a8c1b9d4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WF_NAME = "credit.onboarding_faturamento"
_NEW_DEF_ID = "f4b8d2a6-c3e1-4a00-8000-000000000001"

_SEQ_CHAIN = [
    "trigger",
    "identificacao",
    "dados_basicos",
    "analise_cadastral",
    "checkpoint_cadastral",
    "coleta_faturamento",
    "analise_faturamento",
    "checkpoint_faturamento",
    "coleta_contrato_social",
    "check_contrato_social",
    "check_socios",
    "analise_contrato_social",
    "checkpoint_contrato_social",
    "parecer",
    "checkpoint_final",
    "output",
]

_EXTRACT_MODEL = "claude-sonnet-4-5"

_EXTRACT_V2 = (
    "Voce e um extrator de documentos financeiros/societarios de uma esteira "
    "de credito FIDC. O documento esta anexado (PDF/imagem). Leia-o e extraia "
    "os dados pedidos.\n\n"
    "REGRAS DURAS:\n"
    "- Extraia APENAS o que esta no documento. Campo ausente => null. "
    "NUNCA invente ou estime.\n"
    "- Valores monetarios: numero com ponto decimal, sem separador de milhar, "
    "sem simbolo. Ex.: 1234567.00.\n"
    "- Datas no formato YYYY-MM-DD.\n"
    "- `confidence` (0..1): quao legivel/confiavel foi a leitura.\n"
    "- Responda APENAS um objeto JSON dentro de ```json ... ``` no formato:\n"
    '{"document_type":"<tipo>","extracted_fields":{...},"confidence":0.0,'
    '"notes":"observacoes ou null"}\n\n'
    "TIPO: Contrato Social (e alteracoes).\n"
    "extracted_fields deve conter (null se ausente):\n"
    "- cnpj, razao_social, capital_social (numero), data_constituicao "
    "(YYYY-MM-DD), objeto_social (texto), endereco (texto)\n"
    "- socios: lista de {nome, cpf, participacao_pct}\n"
    "- administradores: lista de {nome, cpf, socio (true/false), "
    "forma_atuacao (ex.: 'isolada', 'conjunta', ou descricao curta)}\n"
    "- poderes_assinatura: lista de {quem, forma, descricao} — quem assina "
    "pela sociedade e em que condicoes (isolada/conjunta, limites)\n"
    "- restricoes_estatutarias: lista de {tema, resumo, referencia} — TODA "
    "clausula que CONDICIONE ou RESTRINJA operacoes da sociedade. Inclui "
    "obrigatoriamente: alcadas de aprovacao (ex.: transacoes acima de X% do "
    "capital exigem aprovacao de administradores e/ou quorum de cotas), "
    "vedacao/condicao para aval-fianca-garantias, alienacao de bens, "
    "emprestimos, quorum qualificado para deliberacoes. `referencia` = "
    "clausula/paragrafo no documento; `resumo` = 1-2 frases fieis ao texto.\n"
    "- numero_alteracao (ex.: '11a alteracao' => 11) e data_ultima_alteracao "
    "(YYYY-MM-DD) quando o documento for uma alteracao contratual.\n\n"
    "As restricoes_estatutarias sao o insumo mais importante para a analise "
    "de credito — leia as clausulas administrativas com atencao redobrada."
)

_EXTRACT_DESC = (
    "Extrai contrato social v2: ficha + administradores + poderes de "
    "assinatura + restricoes/alcadas estatutarias."
)


def _reorder(graph: dict) -> dict | None:
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return None
    ids = {n.get("id") for n in nodes if isinstance(n, dict)}
    if not set(_SEQ_CHAIN).issubset(ids):
        return None  # grafo customizado — não arrisca reordenar
    # Já está na ordem? (edge checkpoint_cadastral->coleta_faturamento existe)
    for e in edges:
        if (
            isinstance(e, dict)
            and e.get("source") == "checkpoint_cadastral"
            and e.get("target") == "coleta_faturamento"
        ):
            return None

    by_id = {n["id"]: n for n in nodes if isinstance(n, dict)}
    for i, nid in enumerate(_SEQ_CHAIN):
        by_id[nid]["position"] = {"x": 80, "y": 40 + i * 130}

    # Edges fora da cadeia (ex.: atalhos custom) são descartadas — o template
    # global é estritamente sequencial por decisão de produto.
    new_edges = [
        {"id": f"e_seq_{i + 1}", "source": _SEQ_CHAIN[i], "target": _SEQ_CHAIN[i + 1]}
        for i in range(len(_SEQ_CHAIN) - 1)
    ]
    return {**graph, "nodes": nodes, "edges": new_edges}


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. Playbook v(N+1) sequencial ─────────────────────────────────────
    row = bind.execute(
        sa.text(
            "SELECT d.id, d.version, d.graph, d.description "
            "FROM workflow_definition_active a "
            "JOIN workflow_definition d ON d.id = a.active_definition_id "
            "WHERE a.name = :n AND a.tenant_id IS NULL"
        ).bindparams(n=_WF_NAME)
    ).first()

    if row is not None:
        graph = row.graph if isinstance(row.graph, dict) else json.loads(row.graph)
        new_graph = _reorder(graph)
        if new_graph is not None and not bind.execute(
            sa.text(
                "SELECT 1 FROM workflow_definition WHERE id = CAST(:i AS uuid)"
            ).bindparams(i=_NEW_DEF_ID)
        ).first():
            new_version = (row.version or 1) + 1
            desc = (
                (row.description or "")
                + " | v3: ordem SEQUENCIAL (cadastral antes do faturamento; "
                "conducao 1->N sem intercalar)."
            )
            bind.execute(
                sa.text(
                    "INSERT INTO workflow_definition "
                    "(id, tenant_id, name, version, description, category, "
                    " graph, status, created_by) "
                    "VALUES (CAST(:id AS uuid), NULL, :name, :ver, :desc, "
                    " 'credit', CAST(:graph AS jsonb), 'ACTIVE', NULL)"
                ).bindparams(
                    id=_NEW_DEF_ID,
                    name=_WF_NAME,
                    ver=new_version,
                    desc=desc[:1000],
                    graph=json.dumps(new_graph, ensure_ascii=False),
                )
            )
            bind.execute(
                sa.text(
                    "UPDATE workflow_definition_active "
                    "SET active_definition_id = CAST(:i AS uuid) "
                    "WHERE name = :n AND tenant_id IS NULL"
                ).bindparams(i=_NEW_DEF_ID, n=_WF_NAME)
            )
            bind.execute(
                sa.text(
                    "UPDATE workflow_definition SET archived_at = NOW() "
                    "WHERE id = CAST(:i AS uuid) AND archived_at IS NULL"
                ).bindparams(i=str(row.id))
            )

    # ── 2. extract.social_contract v2 (cláusulas) ─────────────────────────
    if not bind.execute(
        sa.text(
            "SELECT 1 FROM ai_prompt WHERE name = 'extract.social_contract' "
            "AND version = 'v2'"
        )
    ).first():
        bind.execute(
            sa.text(
                "INSERT INTO ai_prompt "
                "(id, name, version, system_text, model, temperature, "
                " max_tokens, cache_strategy, description) "
                "VALUES (gen_random_uuid(), 'extract.social_contract', 'v2', "
                " :st, :m, 0.1, 6144, 'AFTER_SYSTEM', :d)"
            ).bindparams(st=_EXTRACT_V2, m=_EXTRACT_MODEL, d=_EXTRACT_DESC)
        )
    bind.execute(
        sa.text(
            "INSERT INTO ai_prompt_active (name, active_version) "
            "VALUES ('extract.social_contract', 'v2') "
            "ON CONFLICT (name) DO UPDATE SET active_version = 'v2'"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    prev = bind.execute(
        sa.text(
            "SELECT id FROM workflow_definition "
            "WHERE name = :n AND tenant_id IS NULL "
            "AND id <> CAST(:i AS uuid) ORDER BY version DESC LIMIT 1"
        ).bindparams(n=_WF_NAME, i=_NEW_DEF_ID)
    ).first()
    if prev is not None:
        bind.execute(
            sa.text(
                "UPDATE workflow_definition SET archived_at = NULL "
                "WHERE id = CAST(:i AS uuid)"
            ).bindparams(i=str(prev.id))
        )
        bind.execute(
            sa.text(
                "UPDATE workflow_definition_active "
                "SET active_definition_id = CAST(:i AS uuid) "
                "WHERE name = :n AND tenant_id IS NULL "
                "AND active_definition_id = CAST(:cur AS uuid)"
            ).bindparams(i=str(prev.id), n=_WF_NAME, cur=_NEW_DEF_ID)
        )
    bind.execute(
        sa.text(
            "DELETE FROM workflow_definition WHERE id = CAST(:i AS uuid)"
        ).bindparams(i=_NEW_DEF_ID)
    )
    bind.execute(
        sa.text(
            "UPDATE ai_prompt_active SET active_version = 'v1' "
            "WHERE name = 'extract.social_contract'"
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM ai_prompt WHERE name = 'extract.social_contract' "
            "AND version = 'v2'"
        )
    )
