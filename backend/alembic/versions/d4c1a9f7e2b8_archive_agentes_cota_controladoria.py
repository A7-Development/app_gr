"""Arquiva 9 agentes de cota/controladoria batch (uso real NULO desde a ativacao).

Revision ID: d4c1a9f7e2b8
Revises: b2d7e4a8c1f5
Create Date: 2026-07-07 00:00:00.000000

Contexto (decisao Ricardo, 2026-07-07): a analise de variacao de cota roda
~100% pelo caminho DETERMINISTICO (metodo gestor reconciliando a residuo R$0
exato + headline estruturado). O monolito `analista_variacao_cota` foi
explicitamente substituido pelo headline estruturado (ver comentario em
`api/cota_sub.py::variacao_headline`), e os 8 auditores nunca sao invocados como
AGENTE -- apenas as tools deles sao reusadas pelos endpoints de drill
deterministicos (`/drill/*`). Medicao no gr_db: decision_log tem 82.684 SYNC e
so 16 RECOMMENDATION (todas `BI/insight_auto`); ZERO destes 9 agentes.

NAO arquiva `controladoria.investigador_cota`: ele e o agente do chat VIVO
`POST /variacao/chat` (`run_standalone_agent`), em uso. Esse chat e single-turn
e nao persiste em ai_message/decision_log -- por isso nao aparece na medicao;
ausencia de rastro aqui NAO e ausencia de uso. Arquiva-lo quebraria o chat.

Decisao: arquivar os 9 batch (soft-delete). O arranjo "LLM=bisturi" venceu do
lado deterministico e esses 9 so cobram imposto de manutencao (§18: toda mudanca
de tool/schema/persona arrasta o checklist de agente) sem retorno.

REVERSIVEL: este upgrade NAO apaga nada -- so seta `archived_at` e remove o
ponteiro `_active`. As rows de `agent_definition` ficam preservadas; personas
(`controller_fidc_senior` e reusavel, e segue ativa via investigador_cota),
prompts (`ai_prompt`) e as tools (`app/agentic/tools/controladoria/*` -- wrappers
SQL baratos, compartilhados com os drills e com o chat) permanecem intactos.
`downgrade()` reativa a MESMA versao que estava ativa no arquivamento.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "d4c1a9f7e2b8"
down_revision = "b2d7e4a8c1f5"
branch_labels = None
depends_on = None


# name -> versao que estava ATIVA em 2026-07-07 (usada no downgrade pra reativar
# exatamente a mesma versao, nao a MAX). analista tinha v2 ativa com v1
# coexistindo. `investigador_cota` NAO entra aqui de proposito -- e o chat vivo.
_AGENTES_ATIVOS: dict[str, int] = {
    "controladoria.analista_variacao_cota": 2,
    "controladoria.auditor_aplicacoes": 1,
    "controladoria.auditor_contas_a_pagar": 1,
    "controladoria.auditor_cotas": 1,
    "controladoria.auditor_notas_comerciais": 1,
    "controladoria.auditor_pdd": 1,
    "controladoria.auditor_resultado": 1,
    "controladoria.auditor_variacao_caixa": 1,
    "controladoria.auditor_variacao_carteira": 1,
}


def upgrade() -> None:
    for name in _AGENTES_ATIVOS:
        # 1. Desativa: remove o ponteiro _active (todos os tenants).
        op.execute(
            sa.text(
                "DELETE FROM agent_definition_active WHERE name = :name"
            ).bindparams(name=name)
        )
        # 2. Arquiva TODAS as versoes desse agente (nao-ativavel). Ordem:
        # desativa antes de arquivar, caso haja constraint "ativa nao arquivavel".
        op.execute(
            sa.text(
                "UPDATE agent_definition SET archived_at = now() "
                "WHERE name = :name AND archived_at IS NULL"
            ).bindparams(name=name)
        )


def downgrade() -> None:
    for name, version in _AGENTES_ATIVOS.items():
        # 1. Desarquiva todas as versoes desse agente.
        op.execute(
            sa.text(
                "UPDATE agent_definition SET archived_at = NULL WHERE name = :name"
            ).bindparams(name=name)
        )
        # 2. Reativa a MESMA versao que estava ativa (global, tenant_id NULL).
        op.execute(
            sa.text(
                "INSERT INTO agent_definition_active "
                "(id, tenant_id, name, definition_id) "
                "SELECT gen_random_uuid(), NULL, :name, d.id "
                "FROM agent_definition d "
                "WHERE d.name = :name AND d.version = :version "
                "AND d.tenant_id IS NULL "
                "ON CONFLICT DO NOTHING"
            ).bindparams(name=name, version=version)
        )
