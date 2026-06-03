# Esteira de Crédito — Mapa de Processo, Primitivos e Playbooks

> **Status:** documento vivo. Direção geral aprovada por Ricardo (2026-06-01);
> reestruturado em 3 camadas (2026-06-03) para virar a espinha das conversas de
> design. Cada etapa é aprofundada uma por vez, no **gabarito** da seção 3.
> Tratar como referência viva, não especificação fechada.

---

## 0. Princípio-chave (reconcilia apelo de IA + auditabilidade)

> **Os agentes não calculam os números. Eles chamam tools/checks
> determinísticos, recebem o fato verificável, e raciocinam em cima.**
> O número é auditável (CVM-ready); a investigação, a narrativa e a decisão são
> agênticas (o que encanta cliente e investidor).

O determinístico **não é o produto** — é o trilho de segurança embaixo dos
agentes. O produto são os agentes. Corolário operacional:

> **O processo define o primitivo.** Não se desenha a cesta de tools no
> abstrato — ela cai de mapear o que cada etapa do processo precisa. Por isso
> este doc vai de cima pra baixo: Processo (Camada 0) → Primitivos (Camada 1) →
> Playbooks (Camada 2).

### Legenda

- 🟦 **Check** — determinístico, Python puro, sem LLM; emite flag estruturada
- 🟩 **Tool** — função que o agente chama no loop (cálculo ou consulta externa)
- 🟪 **Agente** — raciocínio LLM (julgamento, narrativa, priorização)
- ⬜ **Humano** — input / homologação / checkpoint
- Status: ✅ pronto (prod) · 🟡 parcial · ❌ a construir

### O decoder ring (pra cada passo, qual primitivo é)

1. Produz número/fato determinístico? → 🟩 **tool de cálculo**
2. Vem de fonte externa (custa)? → 🟩 **tool externa** (`cost_hint`)
3. Compara declarado × oficial e emite flag? → 🟦 **check**
4. É julgamento/narrativa/priorização? → 🟪 **agente**
5. Precisa de pessoa (input ou homologação)? → ⬜ **humano**

### O simplificador

Quase **nenhum tipo de node novo** é necessário — o builder já cobre tudo. O
trabalho de design é **encher a cesta de tools e agentes**; os node types
existentes os carregam:

| O que a etapa faz | Node que carrega |
|---|---|
| pessoa digita / homologa | `human_input` / `human_review` |
| determinístico, emite flag | `deterministic_check` (carrega 🟦/🟩) |
| consulta externa | `bureau_query` (carrega 🟩 externa) |
| julgamento / narrativa / cruzamento | `specialist_agent` (carrega 🟪) |
| barra / roteia | `conditional_branch` |
| empacota artefato | `output_generator` |

---

## 1. Camada 0 — O PROCESSO (fluxo ordenado)

O território, em linguagem de negócio. Sequência por fases; dependências e
bifurcações explícitas. Status reflete o que já existe no sistema.

### Fase A — Abertura & Elegibilidade
| # | Etapa | Executor | Bifurcação | Status |
|---|---|---|---|---|
| A1 | Perímetro + identidade (target CNPJ, grupo econômico, sócios+%) | ⬜ Humano + persistência grafo | — | ✅ |
| A2 | Gate de elegibilidade (idade, CNAE vetado, capital mín., RJ, porte) | 🟦 Check (política versionada) | **reprova → encerra** antes de gastar | idade ✅ · resto ❌ |

### Fase B — Coleta & Estruturação
| # | Etapa | Executor | Bifurcação | Status |
|---|---|---|---|---|
| B1 | Coleta de documentos (kit banco) | ⬜ Humano (upload + tipo) | falta obrigatório → **pausa** | ✅ |
| B2 | Extração → silver homologado (DRE/Balanço/Faturamento/Contrato/SCR/ABC/IR) | 🟪 Agente Vision + ⬜ homologação | — | 🟡 (faturamento ✅) |

### Fase C — Enriquecimento externo
| # | Etapa | Executor | Bifurcação | Status |
|---|---|---|---|---|
| C1 | Serasa PJ/PF · Receita/QSA · SCR Bacen · processos · protestos · NFe | 🟩 Tools externas (adapters) | sem dado → segue com lacuna sinalizada | Serasa adapter ✅ · resto ❌ |

### Fase D — Análises especialistas (uma por aspecto)
| # | Etapa | Executor | Status |
|---|---|---|---|
| D1 | **Financeira / Faturamento** (indicadores, tendência, capacidade) | 🟪 financial_analyst + 🟩 tools | 🟡 *(seção 4 — etapa-piloto)* |
| D2 | Endividamento / capacidade de pagamento (SCR + declarado) | 🟪 indebtedness_analyst + 🟩 | ❌ |
| D3 | Societária (QSA, poderes, restrições do contrato) | 🟪 social_contract_analyst | 🟡 |
| D4 | Jurídica (processos, protestos — risco) | 🟪 legal_analyst | ❌ |
| D5 | Concentração por sacado (curva ABC, HHI, top-N) | 🟦 Check → 🟩 tool + 🟪 | ❌ |

### Fase E — Cruzamentos (detecção de veracidade — o coração)
| # | Etapa | Executor | Status |
|---|---|---|---|
| E1 | **Família 1** — declarado × oficial (endivid.×SCR · fatur.×NFe/capacidade) | 🟪 detetive + 🟩 tools | ❌ |
| E2 | **Família 2** — cross-fonte (endereço/datas/QSA/capital/soma %) | 🟪 cross_reference + 🟦 | 🟡 (soma % ✅) |
| E3 | **Família 3** — materialidade (satélite/fachada/site/WHOIS) | 🟪 agente multimodal | ❌ |

> Saída das Famílias = **flags estruturadas** `{check_type, source, field, expected, actual, severity}` — a *unidade-produto* da esteira.

### Fase F — Síntese & Decisão
| # | Etapa | Executor | Bifurcação | Status |
|---|---|---|---|---|
| F1 | Parecer consolidado (flags → recomendação + justificativa) | 🟪 opinion_writer | — | 🟡 (rascunho) |
| F2 | Homologação (analista edita o parecer da IA) | ⬜ Humano (checkpoint) | aprova / condicional / recusa | ✅ |
| F3 | Decisão + limite de cessão + outcome | 🟦 persistência (decision ledger) | — | 🟡 |
| F4 | Output / formalização (PDF do parecer homologado) | `output_generator` | — | 🟡 |

### Fase G — Pós-decisão
| # | Etapa | Executor | Status |
|---|---|---|---|
| G1 | Monitoramento / reavaliação recorrente (gatilho schedule) | 🟪 + 🟩 | ❌ |
| G2 | Medição de acerto das recomendações (decision ledger no tempo) | 🟦 | 🟡 |

---

## 2. Camada 1 — A CESTA DE PRIMITIVOS (catálogo)

Derivada da Camada 0. **Seeds** abaixo; cada deep-dive (seção 3) preenche e
adiciona. Assinaturas se fecham na etapa correspondente.

### 2.1 Tools (🟦 checks + 🟩 cálculo/externa)
| Tool | Tipo | Input (silver) | Output | Custo | Flag? | Status |
|---|---|---|---|---|---|---|
| `company_founding_age` | 🟦 check | founding_date, policy | result(bool) + flag | — | sim | ✅ |
| `ownership_sum` | 🟦 check | sócios[].pct | result + flag | — | sim | ✅ |
| `compute_revenue_trend` | 🟩 calc | faturamento.monthly[] | total/média/YoY/sazonalidade/tendência | — | não | ❌ *(D1)* |
| `compute_financial_indicators` | 🟩 calc | dre, balanço | liquidez/endiv/margens/ICR | — | não | ❌ *(D1)* |
| `compute_leverage` | 🟩 calc | dre, balanço, scr | Dív.Líq/EBITDA, DSCR | — | não | ❌ *(D1/D2)* |
| `compute_abc_concentration` | 🟩 calc | abc_curve | HHI, top-N%, classe | — | não | ❌ *(D5)* |
| `query_serasa_pj` | 🟩 externa | cnpj | report estruturado | $$ | — | adapter ✅ · tool ❌ |
| `cross_declared_vs_scr` | 🟦 check | dívida declarada, SCR | flag de omissão | — | sim | ❌ *(E1)* |
| `compare_values` / `calculate_metric` | 🟩 genérica | — | — | — | — | ✅ |

### 2.2 Agentes (🟪)
| Agente | Persona | Lê (inputs) | Tools permitidas | Produz | Status |
|---|---|---|---|---|---|
| `document_extractor` | Extrator multimodal | arquivo (PDF/img) | — | extracted_fields | ✅ |
| `financial_analyst` | Analista Financeiro FIDC | extração homologada + tools D1 | compute_* (D1) | financial_assessment + flags | 🟡 *(D1)* |
| `indebtedness_analyst` | Analista de Endividamento | SCR + dívida declarada | compute_leverage, cross_* | capacity_assessment | ❌ *(D2)* |
| `cross_reference_analyst` | Detetive de Veracidade | todas as fontes | checks de cruzamento | flags narradas | 🟡 *(E1/E2)* |
| `opinion_writer` | Parecerista | todas as análises + flags | — | parecer + recomendação | 🟡 *(F1)* |

### 2.3 Tipos de node (builder) — referência
`trigger` ✅ · `human_input` ✅ · `deterministic_check` ✅ · `bureau_query` ✅ ·
`specialist_agent` ✅ · `conditional_branch` ✅ · `human_review` ✅ ·
`output_generator` ✅ · `consolidator` ✅. **Sem node novo previsto** — só se
nenhum encaixar (raro).

---

## 3. O gabarito de etapa (todo deep-dive preenche isto)

```
Etapa <ID> — <nome>
  • Objetivo            : o que a etapa entrega
  • Pergunta            : a pergunta de crédito que responde
  • Inputs              : de onde vêm (silver homologado, outputs upstream)
  • Fontes/consultas    : internas / externas (+ custo)
  • Cálculos/checks     : determinístico → tools/flags (assinatura)
  • Julgamento          : agente + persona + output_schema
  • Toque humano        : input? homologação? gate?
  • Produz              : variáveis/flags/artefato (producedVars)
  • Node(s)             : qual node do builder carrega cada peça
  • Bifurcações         : quando ramifica/encerra
  • Decisões em aberto  : o que precisa do Ricardo pra fechar
```

---

## 4. Etapa-piloto a fundo — **D1: Análise Financeira / Faturamento**

> Escolhida como referência por já termos a extração de faturamento em prod.
> As demais etapas seguem este mesmo nível de detalhe.

- **Objetivo:** transformar o faturamento (e DRE/balanço, quando houver) em uma
  leitura de crédito — porte, tendência, qualidade da receita, e insumo de
  capacidade — com indicadores auditáveis.
- **Pergunta:** "Esta empresa fatura o que diz, de forma saudável e sustentável,
  num nível compatível com a operação pretendida?"
- **Inputs:** `extracted_fields` **homologados** do faturamento
  (`monthly[]`, `revenue`, `period`, `cnpj`); quando existirem, DRE e balanço
  homologados. *(Nunca re-lê o PDF — usa o que o analista aprovou.)*
- **Fontes/consultas:** internas (silver). Externas entram no cruzamento (E1):
  NFe (fatur. real) e SCR (capacidade) — fora desta etapa, citadas como gancho.
- **Cálculos/checks (🟩/🟦 → tools):**
  - `compute_revenue_trend(monthly[])` → total 12m, média mensal, YoY (se
    multi-período), índice de sazonalidade, tendência (cresc./estável/queda),
    maior/menor mês. *(já fazemos parte disso no card — promover a tool.)*
  - `compute_revenue_quality(monthly[])` 🟦 → flags: mês zero/negativo, outlier
    (>2,5× ou <0,4× média), nº de meses ≠ 12.
  - *(com DRE/balanço)* `compute_financial_indicators` → liquidez (corrente/seca),
    endividamento, margens (bruta/EBITDA/líquida), ICR.
  - *(com DRE/balanço/SCR)* `compute_leverage` → Dív.Líq/EBITDA, DSCR.
- **Julgamento (🟪 `financial_analyst`):** lê os outputs das tools + os silver e
  produz `financial_assessment` (output_schema): `{ porte, tendencia,
  qualidade_receita, indicadores_chave[], pontos_fortes[], pontos_atencao[],
  semaforo (verde/amarelo/vermelho), narrativa }` + flags. **Não inventa número:
  cita o resultado da tool.**
- **Toque humano:** o parecer financeiro entra no checkpoint (F2) pra homologação.
- **Produz:** `financial_assessment{...}` + flags financeiras.
- **Node(s):** os `compute_*` como tools no loop do `specialist_agent`
  (financial_analyst); `compute_revenue_quality` pode também virar
  `deterministic_check` no grafo se quisermos o gate explícito.
- **Bifurcações:** se só há faturamento (sem DRE/balanço), a etapa roda em modo
  reduzido (porte+tendência) e **sinaliza** que capacidade/alavancagem ficam
  limitadas — não inventa o que falta.
- **Decisões em aberto (Ricardo):**
  1. Faturamento da declaração é **receita bruta** — usar como proxy de porte;
     quando confrontar com DRE (receita líquida), qual manda?
  2. Política de **outlier/sazonalidade**: cortes fixos (2,5×/0,4×) ou por setor?
  3. **Modo reduzido** (só faturamento) é aceitável pra seguir, ou exige DRE+balanço?
  4. `compute_*` como **tool no loop** (agente decide) vs **check no grafo**
     (gate fixo) — ou os dois (a decisão transversal da seção 5).

---

## 5. Decisões transversais em aberto

1. **Unificação tool/check/node:** "uma capacidade determinística, dois pontos
   de invocação" (node no grafo + tool no loop), ou manter checks/bureaus como
   nodes separados das tools? *(define se são 1 conceito ou 3.)*
2. **Consultas externas como tool** (agente decide puxar Serasa, com custo) vs
   **só como node** (gerente controla o gasto no grafo).
3. **Granularidade dos agentes:** um por aspecto (D1–D5) vs poucos agentes
   "grossos". *(monolito foi aposentado no cota-sub → tendência é especialistas.)*
4. **Score/recomendação:** determinístico (regra sobre flags) vs agêntico
   (opinion_writer decide) — provável híbrido (regra dá o piso, agente narra).

---

## 6. As 5 superfícies agênticas (a mágica — onde está o apelo)

1. Leitor de documentos (Vision) — ✅
2. Detetive de cruzamento (Família 1 — coração da fraude) — ❌
3. Materialidade multimodal — ❌
4. Sintetizador do parecer — 🟡
5. Investigador conversacional ("pergunte ao dossiê") — ❌ *(padrão existe no cota-sub)*

## 7. Sequência de construção (agentic-first)

1. Extração agêntica de documentos ✅ (destrava dado pros demais)
2. **Tools determinísticas expostas a agentes** ← *próximo* (capacidade,
   concentração, capital, bate-mercado) — começa pela etapa-piloto D1
3. Agente detetive de cruzamento (E1) — raciocina sobre docs + Serasa → flags
4. Investigador conversacional — o wow
5. Materialidade multimodal + integrações externas (Receita primeiro)

## 8. Já entregue (Fatia 1, em prod)

Política `credit_policy` · node `deterministic_check` + checks
(`company_founding_age`, `ownership_sum`) na paleta · persistência do grafo
societário · proveniência estruturada da flag · playbook `credit.onboarding_minimo`
· cockpit com flags visíveis + checkpoint c/ parecer + reprocessar · extração
multimodal de documentos + **painel de revisão/homologação** (formatado,
editável, checks de sanidade, ver documento).
