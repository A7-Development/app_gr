# Especificação Técnico-Arquitetural
## Controle de Custos de IA — medição, visibilidade e limites em 3 níveis

> **Tipo:** Spec-driven development — documento de referência da rodada.
> **Autor:** engenharia. **Status:** v1 — RASCUNHO (primeira versão, 2026-07-23). A lapidar com o Ricardo; nada implementado.
> **Contexto:** o Strata AI (Copiloto) entrou em produção em 2026-07-23 (spec `specs/done/copiloto-mcp.md`) com allowlist AMPLA do BDC (157 tools, decisão Ricardo) — o guard de custo passou a ser caps, não allowlist. A função é boa demais para morrer de susto na fatura: precisamos de controle rigoroso ANTES do uso escalar.
> **Origem:** pedido do Ricardo (2026-07-23): "controle rigoroso dos custos — como mantenedor, como admin do tenant e como usuário".

---

## 0. Sumário executivo

Três atores, três perguntas:

| Ator | Pergunta que precisa responder | Hoje |
|---|---|---|
| **Mantenedor (Strata)** | "Quanto cada tenant me custa vs quanto me paga?" | Só a metade LLM, sem painel |
| **Admin do tenant** | "Quem do meu time está gastando, em quê, e como limito?" | Nada por usuário; quota única do tenant |
| **Usuário** | "Quanto custou ESTA pergunta?" | Só o saldo global no indicador |

**O furo estrutural: o custo de vendor (BDC) não é medido.** `ai_usage_event` registra tokens de LLM (R$ estimado + créditos); a chamada MCP a dataset PAGO só deixa rastro qualitativo no `decision_log.inputs_ref.tools_called`. Caps existem (5 consultas externas/turno por servidor + `hard_cap_brl`/dia — que hoje só soma LLM), mas **ninguém sabe o valor em R$**. Sem medição não há controle: a rodada começa por medir.

**Princípio de produto (herda do §19.8):** o usuário e o tenant pensam em **créditos**, nunca em tokens ou tarifas de vendor. R$ é vocabulário exclusivo do mantenedor.

---

## 1. O que já existe (inventário honesto)

| Peça | Onde | O que cobre |
|---|---|---|
| `ai_usage_event` | `app/shared/ai/models/usage_event.py` | 1 linha por chamada LLM: tokens in/out/cached, `cost_brl_provider` (estimativa), `cost_credits_billed`, feature, model, user, tenant, `decision_log_id` |
| `ai_credit_balance` | metering (`_bump_consumed`) | consumo mensal em créditos por tenant (`period_yyyymm`; granted/consumed/carryover/topup) |
| `tenant_ai_subscription` | shared/ai | `monthly_credit_quota`, `hard_cap_brl` (cap DIÁRIO em BRL — enforced em `rate_limit.check_daily_cost_cap`, **só LLM hoje**) |
| Rate limits | `services/rate_limit.py` | RPM / TPM / BRL-dia, em processo, por tenant |
| Caps MCP | `mcp_server.max_calls_per_turn` (5) + `tool_result_max_chars` | por TURNO e por servidor — não há cap diário nem por usuário |
| Preço por dataset BDC | `provedor_dados_dataset_price_history` (fonte `bdc_pricing_api`) | preço unitário por dataset — **existe mas não é usado no metering** |
| Créditos → tokens | `chat.py::_credits_for_tokens` | `1 crédito ≈ 1000 tokens in ou 100 out` — hardcoded |
| UI de saldo | `<AIQuotaIndicator />` (compact no header do Copiloto) | saldo mensal; amber 75% / red 90%; sem detalhe por uso |
| Kill-switch MCP | `/admin/ia/mcp` (arquivar / ativar versão) | desligar um vendor inteiro em 1 clique, sem deploy |
| Trilha qualitativa | `decision_log.inputs_ref.tools_called` | QUAIS tools rodaram no turno (sem valor) |

**Gaps:** custo vendor não medido · nada por usuário (nem medição nem limite) · consulta externa não debita crédito próprio (só os tokens que ela gera) · painéis inexistentes (mantenedor e tenant) · usuário não vê custo por turno · conversão crédito↔R$ hardcoded.

---

## 2. Princípios (propostos — validar com Ricardo)

1. **Medir antes de limitar.** Nenhum limite novo entra antes da telemetria que o justifica (F1 antes de F3).
2. **Créditos como moeda única do produto.** Consulta externa vira débito de créditos FLAT (espelha "1 insight = 5 créditos" do §19.8). Token e tarifa de vendor são detalhes internos do mantenedor.
3. **Todo custo tem dono.** Cada centavo (LLM ou vendor) é atribuível a tenant + usuário + conversa + turno — mesma disciplina de proveniência do §14, aplicada a dinheiro.
4. **Desfecho honesto em limite batido** (§7.3): cap atingido = mensagem clara com o que fazer ("fale com seu administrador"), nunca erro mudo ou degradação silenciosa.
5. **Transparência não vira atrito.** O usuário VÊ o que gasta (chip, tooltip), mas não é interrompido por confirmações a cada consulta — fricção só quando um limite de verdade está próximo/batido.
6. **Kill-switch em camadas.** Mantenedor desliga: um servidor MCP (existe), um tenant (cap), a plataforma inteira (circuit breaker global — novo).

---

## 3. Fundação — medição do custo externo (F1)

### 3.1 Tabela nova `mcp_call_event`

1 linha por `tools/call` executada pelo runtime (espelha `ai_usage_event`):

| Coluna | Descrição |
|---|---|
| `id`, `occurred_at` | pk, timestamp |
| `tenant_id`, `user_id` | atribuição (índice composto com tenant — §10) |
| `conversation_id`, `usage_event_id` | amarra ao turno (o `ai_usage_event` do turno) |
| `server_name`, `server_version`, `tool_name` | o que rodou (ex.: `bigdatacorp` v3, `people_related_people_tool`) |
| `dataset_ref` | dataset do vendor mapeado a partir da tool (p/ preço) |
| `duration_ms`, `status` | ok / error / capped |
| `cost_brl_vendor` | preço unitário via `provedor_dados_dataset_price_history` (as-of `occurred_at`); NULL quando desconhecido — **nunca chutar** |
| `cost_credits_billed` | créditos flat debitados por esta consulta |

Escrita no executor (`McpWrappedTool.execute` / dispatch do copiloto) — mesmo lugar que já emite `tool_status`.

**Questão em aberto (QA-1):** mapeamento tool→dataset→preço. As tools do MCP (`people_related_people_tool`) não têm o mesmo slug dos datasets da API REST no price history. Opções: (a) tabela de-para curada (seed + editável no admin); (b) heurística por nome + fallback NULL. Proposta: (a) — de-para explícito, NULL até curar (o painel mostra "sem preço" em vez de número errado).

### 3.2 Créditos por consulta externa

- `mcp_server` ganha `credits_per_call` (int, default **5** — QA-2: calibrar; a referência é o insight flat do §19.8).
- Débito no metering do turno: `cost_credits_billed_total = _credits_for_tokens(...) + Σ credits_per_call das consultas ok`.
- `ai_usage_event` ganha (ou deriva de `mcp_call_event`): `n_external_calls`, `cost_credits_external`.

### 3.3 Caps passam a enxergar o custo todo

- `rate_limit.record_cost` / `check_daily_cost_cap` somam `cost_brl_vendor` — o `hard_cap_brl` do tenant vira cap de custo REAL/dia.
- Frame SSE `done` ganha: `credits_billed`, `external_calls` (consumido pela F2-usuário).

---

## 4. Nível 1 — Mantenedor (Strata)

### 4.1 Painel `/admin/ia/custos` (system maintainer)

- **Margem por tenant:** R$ gasto (LLM + vendor) × créditos consumidos × quota do plano — por mês e por dia.
- **Quebras:** por feature (`copiloto_chat`, `chat`, `insight`, agentes/workflows), por modelo, por servidor MCP, por dataset (top N + "Outros" — §14.6).
- **Série diária** do mês corrente com projeção simples de fechamento.
- Fonte: `ai_usage_event` + `mcp_call_event` (agregações; sem tabela nova).

### 4.2 Guard-rails globais

- **Circuit breaker da plataforma** (QA-3): cap diário GLOBAL em R$ (config em DB, editável no admin). Batido → toda chamada de IA responde com desfecho honesto + alerta ao mantenedor. Protege contra runaway coletivo (bug, abuso, loop).
- **Alerta de anomalia:** linha no Painel de Saúde de Integrações (`/admin/dados/saude`): tenant com gasto do dia > N× a média móvel de 14 dias → destaque. (Padrão do incidente clássico: ninguém olha até doer.)
- **Kill-switch por servidor MCP:** já existe (arquivar) — documentar como runbook.

### 4.3 Pricing editável

- Conversão crédito↔token e crédito↔consulta externa saem do hardcode para config em DB (tabela `ai_pricing_config` versionada, padrão premise_set — auditável). Margem vira decisão de negócio com trilha, não constante em código.

---

## 5. Nível 2 — Admin do tenant

> Persona: admin do tenant (RBAC normal, `AICapability.ADMIN`) — NÃO o mantenedor. Primeira superfície de IA fora do gate `is_system_maintainer`.

### 5.1 Página de consumo do tenant (rota a definir — QA-4: `/admin/ia/consumo`? vive no módulo admin do próprio tenant)

- Mês corrente: créditos consumidos vs quota, projeção, topup.
- **Por usuário:** ranking de consumo (créditos, nº de consultas externas, nº de conversas) — quem gasta o quê.
- **Por tipo:** conversa interna (Lake) × consultas externas (Hub) — o Hub é o custo marginal real.
- Histórico simples por dia.

### 5.2 Limites por usuário — tabela `user_ai_limit`

| Campo | Descrição |
|---|---|
| `user_id` (pk) | — |
| `daily_credit_cap` | teto diário de créditos (NULL = sem teto individual) |
| `daily_external_calls_cap` | teto diário de consultas externas (NULL = sem teto) |
| `external_allowed` | bool — pode consultar fontes de mercado? (default true) |

- Enforcement no serviço do turno (copiloto e AIPanel): cap batido → desfecho honesto ("seu limite diário de consultas externas acabou — fale com o administrador"); `external_allowed=false` → cardápio monta **sem MCP** (mesma mecânica de permissão do §6.3 — filtragem silenciosa + agente responde só com dados internos).
- UI: na gestão de usuários do tenant (quando existir — dependência do projeto Admin Gestão Tenants/Usuários) ou página própria simples nesta rodada.

### 5.3 Alertas

- 75% / 90% da quota mensal → notificação ao(s) admin(s) do tenant (canal QA-5: e-mail? in-app? começar in-app/banner é o mais barato).

### 5.4 Gestão de PERMISSÃO de IA por usuário — gap real, anotado 2026-07-24

> **Incidente que motivou a nota:** Ricardo pediu à Mara (mara@a7credit.com.br) para testar o Strata AI e ela recebeu 403 ("Permissão insuficiente em IA... usuário tem 'none'"). Causa: `user_ai_permission` não tinha linha para ela — o guard (`ai_guard.py`) trata ausência como `NONE`. A correção foi INSERT manual via SQL (`READ`). Isso não pode ser o fluxo de onboarding de usuário na IA.

- **Hoje:** backend PRONTO (`PUT /api/v1/admin/ai/subscriptions/{tenant_id}` em `app/modules/admin/api/ai_subscriptions.py` faz upsert da subscription do tenant + permissões de IA por usuário), mas gated por `require_system_maintainer` e **nenhuma tela consome** — `/admin/usuarios` (convites) e `/admin/tenants` não tocam permissão de IA.
- **O que falta (detalhar na conversa; entra naturalmente junto da F3/`user_ai_limit`):**
  - UI para conceder/alterar `user_ai_permission` (NONE/READ/WRITE/ADMIN) — lugar natural: a mesma superfície do §5.2 (gestão de usuários do tenant), já que permissão e limite do usuário são duas faces do mesmo cadastro.
  - Decidir o ATOR: hoje o endpoint é maintainer-only; a tese do §5 é que o **admin do tenant** gerencia seu próprio time (via `AICapability.ADMIN`) — exigiria endpoint tenant-scoped novo ou relaxar o guard com escopo.
  - Default de onboarding (QA-8): usuário novo do tenant com IA habilitada nasce com `READ` ou `NONE`? Hoje nasce sem linha (= NONE, silencioso).

---

## 6. Nível 3 — Usuário

### 6.1 Custo por resposta (chip no chat)

- Rodapé discreto de cada resposta do Strata AI: **"3 créditos · 2 consultas externas"** (dados do frame `done` estendido — §3.3). Zero jargão: nunca "tokens".
- Consultas externas já são visíveis ao vivo (`tool_status` "Consultando o Strata Hub…") — o chip fecha o ciclo com o número.

### 6.2 Saldo em contexto

- `<AIQuotaIndicator />` ganha tooltip: "hoje: X créditos · N consultas externas" (+ "seu limite diário: Y" quando `user_ai_limit` existir).

### 6.3 Limites com desfecho honesto

- Já implementado no cap por turno; estender a mensagem para caps diários pessoais (§5.2) com orientação de próximo passo.

---

## 7. Fases de entrega (proposta)

| Fase | Entrega | Aceite (gate) |
|---|---|---|
| **F1 — Medição** | `mcp_call_event` + de-para tool→dataset→preço (QA-1) + `credits_per_call` no servidor + débito flat no metering + caps somando vendor + frame `done` com `credits_billed`/`external_calls` | todo turno com consulta externa gera N linhas de `mcp_call_event` com R$ (ou NULL honesto); crédito debitado confere; `hard_cap_brl` inclui vendor |
| **F2 — Visibilidade** | chip de custo no chat + tooltip do quota + painel mantenedor `/admin/ia/custos` + página de consumo do tenant | mantenedor responde "quanto o tenant X me custou este mês?" em 1 tela; admin vê ranking por usuário; usuário vê o custo de cada resposta |
| **F3 — Controles** | `user_ai_limit` (caps diários + `external_allowed`) + enforcement + circuit breaker global + alertas 75/90% + anomalia no Painel de Saúde + `ai_pricing_config` | limites batidos degradam com desfecho honesto; teste de isolamento (limite do user A não afeta B); alerta dispara em cenário simulado |

Migrations = passos manuais do Ricardo (dev==prod, §16). F1 é pequena e destrava tudo; F3 só entra com F2 dando números (princípio 1).

---

## 8. Questões em aberto (para a conversa de amanhã)

| # | Questão | Proposta inicial |
|---|---|---|
| QA-1 | De-para tool MCP → dataset → preço: curado ou heurístico? | Curado (seed + editável), NULL até curar — nunca preço chutado |
| QA-2 | Quantos créditos vale 1 consulta externa? | 5 flat (referência: insight §19.8); calibrar com o preço médio real do BDC × margem |
| QA-3 | Circuit breaker global: valor inicial do cap diário da plataforma? | Definir com base no painel F2 (ou chute conservador já na F3) |
| QA-4 | Onde vive a página do admin do tenant (rota/módulo)? | `/admin/ia/consumo` gated por `AICapability.ADMIN` (não maintainer) — primeira tela admin-de-tenant da capability IA |
| QA-5 | Canal de alerta 75/90%: in-app, e-mail, ambos? | In-app/banner primeiro (barato); e-mail na sequência |
| QA-6 | Cap diário de consultas externas por TENANT (além do BRL)? | Talvez redundante com `hard_cap_brl` somando vendor — decidir com dados da F2 |
| QA-7 | AIPanel (BI) entra no mesmo regime desde F1? | Sim para medição (é o mesmo metering); chip de custo no painel fica pra depois |
| QA-8 | Permissão de IA por usuário (§5.4): quem gerencia (maintainer vs admin do tenant) e qual o default de onboarding? | UI junto do §5.2; default proposto: `NONE` explícito com concessão em 1 clique — nunca linha ausente silenciosa |
