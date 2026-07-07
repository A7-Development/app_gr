# Arquitetura Agentica — historia, racional e roadmap

> Companion do CLAUDE.md §19. O §19 descreve o **estado vigente** (regras que mudam o comportamento de qualquer sessao); este doc guarda a **historia das decisoes, o racional detalhado e o roadmap** — conteudo que informa, mas nao e regra de sessao. Criado em 2026-07-06 na reescrita estrutural do CLAUDE.md (auditoria de 196 regras).

## 1. Linha do tempo das decisoes

| Data | Decisao |
|---|---|
| 2026-04-30 | IA tratada como **capability transversal**, nao decimo modulo — enum `Module` continua fechado em 9. Nascem `tenant_ai_subscription`, `user_ai_permission`, `require_ai`, prompt library DB-backed (`ai_prompt` + `ai_prompt_active`). |
| 2026-05-02 | Specialist agents migram do `claude-agent-sdk` (subprocess do Claude Code CLI — quebrava no Windows com `SelectorEventLoop`) para o **SDK oficial `anthropic`** (Messages API com tool use nativo). |
| 2026-05-20 | A capability IA e reposicionada como **camada agentica estrutural** com 4 blocos (agents, tools, workflows, memory) e catalogo central de agentes. Anunciado o refator para `app/agentic/`. |
| ~2026-06 | Refator executado (commit `a176dcc`): `app/agentic/` nasce com engine, agents, tools, workflows (ex-`modules/credito/workflows/`), memory. `AnalysisSession` entregue e persistida. |
| 2026-07-06 | **Vocabulario: "workflow" em tudo** — classes Python, tabelas DB, rotas, docs e copy da UI. "Playbook" (experimento de vocabulario 2026-05→07) aposentado; classes `Playbook*` renomeadas para `Workflow*`. "Skill" continua reservado a comandos Claude Code. |

## 2. Por que o catalogo de agentes e CENTRAL (nao espalhado por modulo)

- A camada agentica e **horizontal por tese** — espalhar agentes fisicamente pelos 9 modulos contradiz a arquitetura.
- `ai_prompt` ja e um catalogo central flat (namespace `<categoria>.<nome>`); replicar o modelo mantem a governanca coesa.
- A UI admin (`/admin/ia/agents`) lista flat com filtro por modulo — codigo espalhado obrigaria agregar de N pastas.
- Marketplace de custom agents por tenant (linhas `tenant_id NOT NULL` em `agent_definition`; registry resolve tenant-especifico > global) exige catalogo central por natureza.
- Reuso cross-modulo: agente pensado para risco pode ser invocado por controladoria via `cross_module=true` + auditoria reforcada.

## 3. Modelagem detalhada

### agent_definition (DB-first; models em `app/shared/ai/models/`)

Campos principais: `name`, `version` (imutavel; edicao cria versao nova), `module` (tag), `persona_id` (FK `agent_persona`), `expertise_ids` (FKs `agent_expertise`), `prompt_name` (aponta pra `ai_prompt`), `allowed_tools`, overrides de `model`/`fallback_model`/`temperature`/`max_tokens`, `cross_module`, `credit_hint`, `tenant_id` (NULL = global), `archived_at`. Ativacao via `agent_definition_active` (1 UPDATE = rollback).

**Semantica de `allowed_tools`** (editavel pela UI sem deploy):
- `NULL` → usa o default do `CATALOG` (`SpecialistAgentSpec.tools`) — preserva agentes curados em codigo.
- `[]` → agente SEM tools (conversacional puro, explicito).
- `[...]` → override explicito (nomes ou wildcard de modulo, ex.: `"controladoria.*"`), resolvido em runtime via `ToolRegistry.get_available(scope, allowed=...)`.

### SpecialistAgentSpec (codigo; `app/agentic/engine/catalog.py`)

Por que output_schema fica em CODIGO e nao em DB: e uma Pydantic class que precisa casar com a logica de parsing do orquestrador. O prompt em si e editavel via DB (sem deploy). O runtime auto-injeta o `<output_format>` derivado do Pydantic no system text (`compose_system_text`) — o autor do prompt nao precisa conhecer o schema.

### ResolvedAgent (`app/agentic/agents/_base.py`)

Composto resolvido em runtime pelo `AgentRegistry.get(name, scope)`: row do DB + persona + expertises + prompt + metadados do CATALOG. `audit_version` compoe `agente@versao + persona@versao + expertises@versao + prompt@versao` — a string que vai em `decision_log.rule_or_model_version`.

## 4. Dois caminhos de invocacao LLM (detalhe)

1. **Cliente HTTP custom** (`adapters/llm/anthropic/`, httpx + SSE puro): chat simples (`AIPanel`, insights) onde o streaming linha-a-linha vai ao frontend via SSE proprio. Prompt caching via `cache_control` em system blocks.
2. **SDK oficial `anthropic`** (`app/agentic/engine/runtime.py`): specialist agents com tool execution loop (`tool_use → tool_result` ate `end_turn`, cap `_MAX_TOOL_ITERATIONS=12`) e prompt caching de system prompts compartilhados entre runs.

Ambos: mesmo storage de credencial (`get_active_anthropic_credential`), `decision_log` + `ai_usage_event` com cache_read/cache_creation separados.

## 5. Prompt library — detalhe operacional

Endpoints em `/admin/ia/prompts` (system maintainer): GET (list), GET /{id}, POST (nova familia = v1), PUT /{id} (nova versao), PUT /{name}/active (ativa), POST /{id}/archive (soft-delete; versao ativa nao arquiva), POST /{id}/preview (render sem chamar LLM; variavel ausente = 400). Seed inicial dos 4 prompts: migration `7c2dffe119a4_ai_prompt_db_managed.py`.

## 6. Roadmap (NAO implementado — nao referencie como existente)

| Item | Descricao | Gate |
|---|---|---|
| Endpoint generico de workflow | `POST /api/v1/workflows/{name}/run` cross-modulo substituindo o disparo via dossie/rotas de credito | quando um 2o modulo precisar disparar workflow |
| `sub_workflow` node | Workflow que invoca workflow | demanda real |
| Tenant memory dedicada | Tabela `tenant_memory` (preferencias + padroes aprendidos por tenant); hoje so existe `ai_conversation_summary` | caso de uso concreto |
| Global memory | Padroes anonimizados cross-tenant | **parecer juridico LGPD/BACEN obrigatorio antes** |
| Retrieval semantico | `embedding vector(1536)` (pgvector instalado, sem uso em IA) + busca por similaridade | caso de uso concreto |
| `tenant_agent_override` | Tenant ajusta modelo/temperature sem fork; parcialmente coberto por `agent_definition.tenant_id` | demanda de tenant externo |
| Migracao `llm/` → `app/agentic/engine/llm/` | Adapters LLM sao infra do motor, nao dominio de integracoes | oportunista (nao bloqueia nada) |
| PII redaction Fase 2 | `presidio-analyzer` + `presidio-anonymizer` substituindo regex+check-digit | volume/exigencia de compliance |
| Rate limit Fase 2 | Redis com token bucket multi-dim (TPM/RPM/BRL/dia) por tenant | multi-tenant real |
| `tenant_tool_registration` | Custom tools por tenant | marketplace |

## 7. Billing — formulas de credito

1 chat ≈ `tokens_input/1000 + tokens_output/100` creditos; 1 insight = 5 creditos (flat); 1 prompt-injection check = 1 credito. Tier mensal em `monthly_credit_quota`; overage pre-pago em `topup`; hard cap diario em BRL via `tenant_ai_subscription.hard_cap_brl`. UI so mostra creditos (`<AIQuotaIndicator />`), nunca token-count.
