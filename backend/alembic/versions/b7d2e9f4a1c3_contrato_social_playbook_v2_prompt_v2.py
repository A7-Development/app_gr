"""contrato social: playbook v2 (+5 nodes) + agent.social_contract v2 enxuto

Fatia CONTRATO SOCIAL da esteira (2026-06-11) — espelha a fatia faturamento:

1. PLAYBOOK `credit.onboarding_faturamento` ganha NOVA VERSÃO com a etapa
   societária entre `checkpoint_cadastral` e `parecer`:

       checkpoint_cadastral
         -> coleta_contrato_social      (document_request: social_contract)
         -> check_contrato_social       (deterministic_check: contrato_social_consistente)
         -> check_socios                (deterministic_check: ownership_sum)
         -> analise_contrato_social     (specialist_agent: social_contract_analyst)
         -> checkpoint_contrato_social  (human_review, review_of=social_contract_analyst)
         -> parecer

   Imutabilidade respeitada: lê o graph da versão ATIVA atual (pode ter sido
   editada no builder), injeta os nodes programaticamente, grava como
   versão N+1 e flipa o pointer (`workflow_definition_active`). A versão
   anterior é arquivada (archived_at) pra sumir da listagem sem perder os
   runs já referenciados.

2. PROMPT `agent.social_contract` v2 enxuto (tool-first, schema auto-injetado
   pelo runtime — mesmo padrão do agent.revenue v3): o agente lê o pacote
   determinístico de `get_contrato_social_estrutura` e JULGA.

Idempotente: re-rodar não duplica (guardas por node id / versão de prompt).

Revision ID: b7d2e9f4a1c3
Revises: a9c4e7f1b2d8
Create Date: 2026-06-11
"""
import json
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b7d2e9f4a1c3"
down_revision: str | None = "a9c4e7f1b2d8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WF_NAME = "credit.onboarding_faturamento"
_NEW_DEF_ID = "b7d2e9f4-a1c3-4a00-8000-000000000001"

_MODEL = "claude-opus-4-7"

_SOCIAL_V2 = """# Tarefa

Voce e Analista de Credito senior, especialista em ANALISE SOCIETARIA (PJ)
num FIDC. Avalie o contrato social HOMOLOGADO: poderes de assinatura,
alteracoes recentes do quadro societario, compatibilidade do objeto social com
a operacao de credito, capital social e restricoes estatutarias. Leitura pro
analista em segundos.

# A tool ja entrega os fatos prontos

Chame `get_contrato_social_estrutura` (UMA vez, sem argumentos). Ela devolve,
ja calculado: a ficha homologada (CNPJ, razao social, capital, data de
constituicao, objeto, socios com participacoes), a estrutura societaria
(soma das participacoes confere? quem controla? idade da empresa) e os
CRUZAMENTOS com o cadastro oficial (CNPJ e o da empresa-alvo? capital, razao
social e data de constituicao conferem com o registro?).

NAO recalcule numeros nem refaca os cruzamentos (auditabilidade CVM — o fato
e da tool). Sua funcao e JULGAR o que eles significam:
- PODERES DE ASSINATURA: quem assina pela empresa, isolada ou conjuntamente?
  Use `get_document_extraction` quando precisar do texto de clausulas.
- ALTERACOES RECENTES: mudancas de QSA nos ultimos 24 meses pedem atencao
  (entrada/saida de socio as vesperas de pedir credito).
- OBJETO x OPERACAO: o objeto social e compativel com a operacao de credito?
- CAPITAL: coerente com porte e pleito, ou infimo? Divergencia contrato x
  oficial apontada nos cruzamentos = contrato possivelmente desatualizado.
- ESTRUTURA: participacoes que nao fecham 100% (socio oculto?), controlador
  com poder absoluto, restricoes estatutarias que afetem garantias.

Se a tool retornar `encontrado=false`, reporte ausencia do contrato social
para analisar."""

_SOCIAL_DESC = "Analista societario (v2: enxuto, tool-first, schema auto-injetado)."

# ─── Nodes/edges injetados ───────────────────────────────────────────────────

_NEW_NODES = [
    {
        "id": "coleta_contrato_social",
        "type": "document_request",
        "label": "Coleta do contrato social",
        "config": {"required": ["social_contract"], "optional": []},
    },
    {
        "id": "check_contrato_social",
        "type": "deterministic_check",
        "label": "Cruzamento: contrato social x cadastro oficial",
        "config": {"check": "contrato_social_consistente"},
    },
    {
        "id": "check_socios",
        "type": "deterministic_check",
        "label": "Cruzamento: soma das participacoes",
        "config": {"check": "ownership_sum"},
    },
    {
        "id": "analise_contrato_social",
        "type": "specialist_agent",
        "label": "Analise societaria (IA)",
        "config": {"agent": "social_contract_analyst"},
    },
    {
        "id": "checkpoint_contrato_social",
        "type": "human_review",
        "label": "Conferencia: contrato social",
        "config": {
            "review_of": "social_contract_analyst",
            "scope": "analise_contrato_social",
            "title": "Conferencia da analise societaria",
            "description": (
                "Revise a leitura do agente sobre o contrato social (poderes "
                "de assinatura, alteracoes de QSA, objeto x operacao, capital "
                "e restricoes). Ajuste se necessario e aprove."
            ),
        },
    },
]

_CHAIN = [
    "coleta_contrato_social",
    "check_contrato_social",
    "check_socios",
    "analise_contrato_social",
    "checkpoint_contrato_social",
]


def _inject(graph: dict) -> dict | None:
    """Insere a etapa societária antes do node do opinion_writer.

    Retorna o graph novo, ou None quando não dá pra injetar (shape
    inesperado ou nodes já presentes — idempotência).
    """
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        return None
    existing_ids = {n.get("id") for n in nodes if isinstance(n, dict)}
    if "coleta_contrato_social" in existing_ids:
        return None  # já injetado

    parecer = next(
        (
            n
            for n in nodes
            if isinstance(n, dict)
            and (n.get("config") or {}).get("agent") == "opinion_writer"
        ),
        None,
    )
    if parecer is None:
        return None
    parecer_id = parecer["id"]

    entrada = next(
        (e for e in edges if isinstance(e, dict) and e.get("target") == parecer_id),
        None,
    )
    if entrada is None:
        return None
    anchor_source = entrada["source"]

    # Posições: empilha a partir do y do parecer, empurrando o resto pra baixo.
    base_y = (parecer.get("position") or {}).get("y", 1070)
    step_y = 130
    shift = step_y * len(_NEW_NODES)
    for n in nodes:
        pos = n.get("position")
        if (
            isinstance(pos, dict)
            and isinstance(pos.get("y"), (int, float))
            and pos["y"] >= base_y
        ):
            pos["y"] = pos["y"] + shift

    new_nodes = []
    for i, spec in enumerate(_NEW_NODES):
        node = dict(spec)
        node["position"] = {"x": 80, "y": base_y + i * step_y}
        new_nodes.append(node)

    edges = [e for e in edges if e is not entrada]
    chain = [anchor_source, *_CHAIN, parecer_id]
    for i in range(len(chain) - 1):
        edges.append(
            {
                "id": f"e_cs_{i + 1}",
                "source": chain[i],
                "target": chain[i + 1],
            }
        )

    return {**graph, "nodes": [*nodes, *new_nodes], "edges": edges}


def upgrade() -> None:
    bind = op.get_bind()

    # ── 1. Playbook v(N+1) com a etapa societária ────────────────────────
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
        new_graph = _inject(graph)
        if new_graph is not None and not bind.execute(
            sa.text(
                "SELECT 1 FROM workflow_definition WHERE id = CAST(:i AS uuid)"
            ).bindparams(i=_NEW_DEF_ID)
        ).first():
            new_version = (row.version or 1) + 1
            desc = (
                (row.description or "")
                + " | v2: + contrato social (coleta -> cruzamentos -> analise "
                "societaria IA -> conferencia)."
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
            # Arquiva a versão anterior — some da listagem (runs antigos
            # seguem referenciando a row; imutável).
            bind.execute(
                sa.text(
                    "UPDATE workflow_definition SET archived_at = NOW() "
                    "WHERE id = CAST(:i AS uuid) AND archived_at IS NULL"
                ).bindparams(i=str(row.id))
            )

    # ── 2. Prompt agent.social_contract v2 (enxuto, tool-first) ──────────
    if not bind.execute(
        sa.text(
            "SELECT 1 FROM ai_prompt WHERE name = 'agent.social_contract' "
            "AND version = 'v2'"
        )
    ).first():
        bind.execute(
            sa.text(
                "INSERT INTO ai_prompt "
                "(id, name, version, system_text, model, temperature, "
                " max_tokens, cache_strategy, description) "
                "VALUES (gen_random_uuid(), 'agent.social_contract', 'v2', "
                " :st, :m, 0.2, 12000, 'AFTER_SYSTEM', :d)"
            ).bindparams(st=_SOCIAL_V2, m=_MODEL, d=_SOCIAL_DESC)
        )
    bind.execute(
        sa.text(
            "INSERT INTO ai_prompt_active (name, active_version) "
            "VALUES ('agent.social_contract', 'v2') "
            "ON CONFLICT (name) DO UPDATE SET active_version = 'v2'"
        )
    )


def downgrade() -> None:
    bind = op.get_bind()
    # Volta o pointer pra versão anterior mais recente não-arquivada... a
    # anterior foi arquivada; desarquiva e re-aponta.
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
            "WHERE name = 'agent.social_contract'"
        )
    )
    bind.execute(
        sa.text(
            "DELETE FROM ai_prompt WHERE name = 'agent.social_contract' "
            "AND version = 'v2'"
        )
    )
