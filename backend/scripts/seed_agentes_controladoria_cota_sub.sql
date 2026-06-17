-- Seed: agentes code-only da cota-sub no agent_definition (catalogo central §19.12).
--
-- Contexto: investigador_cota + 8 auditores existem so no CATALOG (codigo) e
-- rodam via AgentRegistry fallback. Nunca foram seedados em agent_definition,
-- entao nao aparecem na lista admin (/admin/ia/agents) nem sao editaveis/
-- rastreaveis pela UI. Os 9 prompts (agent.controladoria.*) JA existem em
-- ai_prompt (seedados via SQL antes) e estao ativos.
--
-- Fidelidade: todos os overrides ficam NULL (persona, expertise, model,
-- fallback, temperature, max_tokens, allowed_tools) + cross_module=false. Com
-- isso o ResolvedAgent da via-DB e IDENTICO ao do fallback do CATALOG —
-- comportamento de runtime nao muda (model resolve via resolve_models_for_agent
-- -> spec.preferred_model; allowed_tools=NULL -> usa spec.tools; thinking_budget
-- vem do spec nos dois caminhos). Verificado em registry.py.
--
-- Idempotente: tenant_id IS NULL faz a unique (tenant_id,name,version) NAO
-- disparar ON CONFLICT (NULLs sao distintos no Postgres), entao guardamos com
-- NOT EXISTS. Pode rodar de novo sem duplicar.
--
-- Por que SQL e nao Alembic: o repo tem 14 heads de migration divergentes e o
-- schema de prod e gerido por seed SQL manual (gr-deploy nao roda alembic) — os
-- proprios prompts chegaram assim. Migration aqui viraria mais um head orfao.
--
-- Como aplicar (na VM, gr_db):  psql "$GR_DB_URL" -f seed_agentes_controladoria_cota_sub.sql

BEGIN;

-- 1) agent_definition (v1, overrides NULL).
INSERT INTO agent_definition (id, tenant_id, name, version, module, prompt_name, cross_module)
SELECT gen_random_uuid(), NULL, v.name, 1, 'controladoria', v.prompt_name, false
FROM (VALUES
  ('controladoria.investigador_cota',        'agent.controladoria.investigador_cota'),
  ('controladoria.auditor_variacao_carteira','agent.controladoria.auditor_variacao_carteira'),
  ('controladoria.auditor_resultado',        'agent.controladoria.auditor_resultado'),
  ('controladoria.auditor_pdd',              'agent.controladoria.auditor_pdd'),
  ('controladoria.auditor_variacao_caixa',   'agent.controladoria.auditor_variacao_caixa'),
  ('controladoria.auditor_notas_comerciais', 'agent.controladoria.auditor_notas_comerciais'),
  ('controladoria.auditor_aplicacoes',       'agent.controladoria.auditor_aplicacoes'),
  ('controladoria.auditor_contas_a_pagar',   'agent.controladoria.auditor_contas_a_pagar'),
  ('controladoria.auditor_cotas',            'agent.controladoria.auditor_cotas')
) AS v(name, prompt_name)
WHERE NOT EXISTS (
  SELECT 1 FROM agent_definition d
  WHERE d.name = v.name AND d.version = 1 AND d.tenant_id IS NULL
);

-- 2) agent_definition_active (aponta pra v1 recem-criada).
INSERT INTO agent_definition_active (id, tenant_id, name, definition_id)
SELECT gen_random_uuid(), NULL, d.name, d.id
FROM agent_definition d
WHERE d.tenant_id IS NULL
  AND d.version = 1
  AND d.module = 'controladoria'
  AND d.name IN (
    'controladoria.investigador_cota',
    'controladoria.auditor_variacao_carteira',
    'controladoria.auditor_resultado',
    'controladoria.auditor_pdd',
    'controladoria.auditor_variacao_caixa',
    'controladoria.auditor_notas_comerciais',
    'controladoria.auditor_aplicacoes',
    'controladoria.auditor_contas_a_pagar',
    'controladoria.auditor_cotas'
  )
  AND NOT EXISTS (
    SELECT 1 FROM agent_definition_active a
    WHERE a.name = d.name AND a.tenant_id IS NULL
  );

COMMIT;

-- Conferencia (rode separado pra ver o resultado):
-- SELECT name, version FROM agent_definition WHERE name LIKE 'controladoria.auditor_%' OR name='controladoria.investigador_cota' ORDER BY name;
