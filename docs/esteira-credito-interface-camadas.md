# Esteira de Crédito — Arquitetura da Interface (3 camadas)

> **Status:** documento vivo. Direção desenhada em conversa Ricardo × Claude
> (2026-06-13). É o par do [`esteira-credito-ia-map.md`](./esteira-credito-ia-map.md):
> aquele responde *"o que o processo faz"* (processo → primitivos → playbooks);
> **este responde "como o processo VIRA TELA"* sem ruptura visual entre etapas.
> Tratar como referência viva, não especificação fechada. Nada aqui está
> implementado ainda — é a espinha da próxima conversa de design.

---

## 0. O problema que esta arquitetura resolve

> **Objetivo do Ricardo (verbatim, reformulado):** um frontend padronizado onde
> *todas* as etapas da construção do dossiê pareçam a mesma coisa — sem dar a
> impressão de que o usuário "saiu de uma filosofia visual pra outra em função
> da etapa". Fluidez. E, ao mesmo tempo, **liberdade** pra montar o fluxo como
> ele quiser, sem que a interface perca a consistência.

Esses dois desejos (consistência + liberdade) normalmente brigam. A indústria
chama a solução de **Server-Driven UI / Schema-Driven Rendering** (blocos do
Notion, SDUI do Airbnb, o par JSON-Schema + UI-Schema). É o pattern exato pra
"telas que se montam sozinhas a partir de dados, mas dentro de um vocabulário
fechado".

### O diagnóstico do estado atual (2026-06-13)

O que existe hoje (`(foco)/credito/dossies/[id]/page.tsx`, ~2100 linhas):

- ✅ **Chassi macro fixo** (FocusRail + StationsSidebar + StationHeader + zonas +
  ClosureBar) — **isso está certo e fica.**
- ❌ **Conteúdo por view bespoke** (`RevenueAnalysisView`, `CadastralAnalysisView`,
  `SocialContractAnalysisView`, `OpinionView`…). Cada tipo = uma tela à mão.
  **Consistência por disciplina, não por construção.** Degrada a cada etapa nova.
- ❌ **Estações derivadas por heurística hardcoded no frontend**
  (`AGENT_STATION_AFFINITY`, switch por `nodeType`). Agente novo no builder não
  vira estação nem renderiza com a cara certa → **a "liberdade" é parcialmente
  ilusória** (construir ≠ ver).
- ❌ **Dois renderizadores pro mesmo conteúdo** (workbench usa as views bespoke;
  dossiê monta seções por outro código) → ruptura na transição trabalhar↔ler.

> **Veredito:** a filosofia está **pela metade**. O chassi (metade certa) está
> pronto; o vocabulário de blocos dirigido por contrato (a outra metade certa)
> está **pendente**. As views bespoke são um andaime provisório que, se virar
> permanente, **garante a ruptura que queremos evitar.** Não é refundar — é terminar.

---

## 1. As 3 camadas da interface

```
┌──────────────────────────────────────────────────────────────────────────┐
│  CAMADA A — CHASSI MACRO  (fixo, já existe, mantém)                        │
│                                                                            │
│   ┌─────┬──────────────┬──────────────────────────────────┐               │
│   │Focus│ Stations     │  Workbench (zonas)                │               │
│   │Rail │ Sidebar      │  ┌────────────────────────────┐   │               │
│   │56px │ (árvore*)    │  │  [ SectionDescriptor render ]│  │ <- Camada B   │
│   │     │              │  │  ┌──────────────────────┐  │   │               │
│   │     │ ▸ Faturamento│  │  │ Bloco · Bloco · Bloco│  │   │ <- Camada C   │
│   │     │ ▸ Cadastral  │  │  └──────────────────────┘  │   │               │
│   │     │ ▸ Contrato   │  └────────────────────────────┘   │               │
│   │     │   ▸ grupo: X*│  ┌────────────────────────────┐   │               │
│   │     │              │  │  ClosureBar (sticky)        │   │               │
│   └─────┴──────────────┴──┴────────────────────────────┴───┘               │
│                                            * = cresce com o sonho (cap. 4)  │
└──────────────────────────────────────────────────────────────────────────┘
                                   ▲
                                   │ alimenta as zonas
┌──────────────────────────────────────────────────────────────────────────┐
│  CAMADA B — SectionDescriptor  (o contrato universal — A PEÇA QUE FALTA)   │
│                                                                            │
│   Todo node — agente OU NÃO — expõe:                                       │
│                                                                            │
│     SectionDescriptor = {                                                  │
│       station: string          // a que estação pertence (vem do GRAFO)    │
│       title:   string                                                      │
│       blocks:  Block[]         // lista ordenada de blocos                 │
│     }                                                                      │
│                                                                            │
│   Um ÚNICO renderizador consome isso. Ele NÃO sabe (nem precisa saber)     │
│   se veio de um agente, de uma consulta, de um check ou de um documento.   │
└──────────────────────────────────────────────────────────────────────────┘
                                   ▲
                                   │ é feito de
┌──────────────────────────────────────────────────────────────────────────┐
│  CAMADA C — VOCABULÁRIO DE BLOCOS  (finito, fechado — a consistência mora aqui)│
│                                                                            │
│   Block = { type, data, provenance }                                       │
│                                                                            │
│   DISPLAY            INTERATIVOS                                            │
│   ───────            ───────────                                           │
│   • Ficha de campos  • Conferência editável (IA-propôs × no-dossiê)        │
│   • Tabela           • Fonte+Origem (PDF/iframe + citações)                │
│   • Gráfico (KpiChartCard)                                                 │
│   • Conclusão de agente   ┌─ recursivo (cap. 4):                           │
│   • Lista de apontamentos │  • Sub-dossiê (uma SectionDescriptor aninhada) │
│   • Texto livre           └─                                               │
└──────────────────────────────────────────────────────────────────────────┘
```

**A regra de ouro:** a consistência mora na **Camada C** (o que o olho vê). A
**derivação** (como cada node monta seus blocos — Camada B) pode ser heterogênea,
porque é invisível. Forçar um mecanismo único de derivação seria over-engineering;
forçar um vocabulário único de blocos é o que entrega a fluidez.

> **Citação NÃO é bloco — é atributo de proveniência** (decisão 2026-06-13).
> Citação é a cauda mais profunda da proveniência: o mesmo `provenance` + um
> **localizador** discriminado por origem — `{kind:'doc', doc_id, page, bbox}` ·
> `{kind:'silver', table, field}` · `{kind:'agent_step', …}`. Por que contida e
> não bloco próprio: (1) tem que viajar **junto do valor** que justifica (espírito
> §14.6 — afirmação + prova juntas); (2) o visualizador já é o bloco **Fonte+Origem**
> (abre o PDF no trecho); (3) a afordância inline já é o **sup de lastro** (9px/600,
> cor = a assinatura: D verde / F cyan / IA indigo / A grafite) → clicar abre o
> Fonte+Origem no localizador. Consequência: `Provenance` ganha `locator?` opcional
> no Etapa 1. Vocabulário continua **6 display + 2 interativos + 1 recursivo**.

### 1.1 Modelo de condução — bússola, não cadeado (decisão 2026-06-13)

> Substitui a "condução sequencial estrita" (decisão 2026-06-12, onde
> `pickFocusEstacao` = primeira estação não fechada e não havia teleporte).
> Entra no item **1.0** da Fase 1 — é cheap agora e muro caro de derrubar depois.

A esteira **não impõe sequência**; ela impõe **dependência**. A distinção é tudo:

- **Linear obrigatório (aposentado):** "faça as estações nesta ordem exata, uma
  de cada vez." A sequência *é* a regra.
- **Prontidão por dependência (canônico):** "uma estação fica *disponível* quando
  suas dependências estão satisfeitas. Entre as disponíveis, o analista escolhe.
  O sistema *sugere* a próxima, mas não *proíbe* as outras. Fechar trava o que
  depende dela."

Guiado, mas não engaiolado — a diferença entre um *wizard* (linha forçada) e uma
*bancada com caminho recomendado* (DAG de dependência + sugestão destacada).

**Por que abrir mão do linear obrigatório:**

1. **O sonho (Fase 2) exige.** Grafo que cresce é árvore/frontier, não linha. O
   sub-dossiê do CNPJ do grupo é um **ramo**, não "estação N+1". Linear obrigatório
   = muro contra a Fase 2.
2. **Investigação não é linear** (a analogia do ultrassom). Linear é ótimo pra
   *coleta* (precisa do doc antes de analisar), ruim pra *julgamento*.
3. **O que importa é dependência, não ordem.** Edges do grafo já modelam isso;
   sequência é proxy grosseiro.
4. **Paralelismo:** cadastral e faturamento são independentes — podem estar prontas
   ao mesmo tempo.
5. **Coerência com a liberdade:** runtime que achata o DAG numa linha joga fora a
   expressividade do builder.

**O que NÃO se perde** (e por que o medo que motivou o sequencial estrito se resolve):
o "teleporte confuso" de 2026-06-12 era sintoma de **falta de modelo de prontidão
legível**, não de falta de linearidade. A cura é tornar o estado explícito:

- Estação **bloqueada** (deps não satisfeitas) → trancada. Isso é *correção*, não linearidade.
- Estação **pronta** → navegável, mesmo não sendo a sugerida.
- **Sempre há um "próximo recomendado"** destacado. `pickFocusEstacao` deixa de ser
  **cadeado** e vira **bússola** (sugestão default).
- **Semântica de fechar** intacta: fechar destrava as dependentes.

Régua: mantém-se o gating de **dependência** (real); remove-se o gating de
**sequência** (artificial). Estados canônicos da estação na sidebar:
`pronta · bloqueada (esperando X) · rodando · homologar · fechada`.

---

## 2. Quem produz os blocos (o agente é só UM dos produtores)

> Correção importante de enquadramento: a interface **não** se resolve "pelo
> schema do agente". O centro é o **vocabulário de blocos**. O `output_schema`
> do agente é apenas **um** produtor entre vários.

| Node | É agente? | De onde sai o `SectionDescriptor` | Vira que blocos |
|---|---|---|---|
| `specialist_agent` | sim | `output_schema` Pydantic + ui-hints (já auto-injetado, PR#210) | Conclusão + Lista de apontamentos + (Gráfico) |
| `cadastral_enrichment` / `bureau_query` | **não** | **Contrato de Dados** do dataset (campos marcados `superfície=tela`) — [`project_contratos_de_dados`] | **Ficha de campos** (ou Tabela) |
| `deterministic_check` | não | fixo no primitivo (`CheckResult{passed, flags}`) | Pílula de status + Lista de apontamentos |
| `document_request` / `official_document_fetch` | não | fixo no tipo de node | Fonte+Origem + Conferência editável |
| `human_input` | não | spec de campos do form (já no `FieldsBuilder`) | Ficha **editável** |

**Ponto que fecha a lógica pro caso não-agente:** o descritor de uma *consulta
simples* **já existe** — é o **Contrato de Dados** (`dataset_contract_field`),
que já roteia cada campo pra 5 superfícies, e **"tela" é uma delas**. Não há nada
a inventar: liga-se o contrato de dados (que já está em DB) ao renderizador de blocos.

### Prova de fechamento — consulta cadastral, sem agente

1. `cadastral_enrichment` roda → grava silver (`tax_status`, `cnaes`, `capital_social`…).
2. Descritor vem do Contrato CAD-PJ (campos `tela`) → **1 bloco Ficha**: razão
   social, CNPJ, situação, CNAE, capital, fundação. Proveniência = cyan / `ri-bank-line`.
3. Workbench renderiza com `<FichaBlock>`. Dossiê renderiza **o mesmo** `<FichaBlock>`.
4. Esse `<FichaBlock>` é **o mesmo** que `human_input` usa (editável) e que uma
   seção de agente usa quando tem sub-bloco de ficha. → **estação de consulta e
   estação de agente não têm como parecer filosofias diferentes.**

---

## 3. O que isso conserta (mapa crítica → solução)

| Ruptura atual | Como a arquitetura conserta |
|---|---|
| **R1 — consistência por disciplina** (view bespoke por tipo) | Só existem N blocos; cada um renderiza de um jeito só. Impossível divergir. |
| **R2 — liberdade ilusória** (agente novo não renderiza) | Node novo só emite `SectionDescriptor`; renderiza com a cara certa **sem frontend novo.** |
| **R3 — dois modelos mentais** (builder DAG vs analista estações, ligados por heurística) | `station` passa a ser **declaração no grafo**, não heurística. O builder agrupa nodes em estações. Construir = ver. |
| **R4 — workbench ≠ dossiê** (dois renderizadores) | Os dois consomem o **mesmo** vocabulário de blocos, em dois estados (editável / leitura). Trabalhar↔ler = a mesma coisa em dois modos. |

---

## 4. O sonho — builder que se autoconstrói (analogia do ultrassom)

> "Como um médico no ultrassom: ele vai achando coisas, marcando, medindo — não
> sabe de antemão tudo que vai encontrar. E cada marcação pode gerar outras
> consultas, outras análises." — Ricardo, 2026-06-13.
>
> Exemplo: durante a análise, descobre-se um CNPJ do grupo econômico que precisa
> entrar na análise também.

### Por que o sonho VALIDA a fundação

Um node que **nasce em runtime** não tem view feita à mão. Na arquitetura velha
(bespoke) o sonho é **impossível** (cairia no dump genérico). Na arquitetura nova
(`SectionDescriptor` → blocos) ele renderiza certo de graça. **A auto-construção
só é viável sobre a Camada B/C.** O sonho é o teste de estresse que confirma a direção.

### A dificuldade real NÃO é o conteúdo — é a estrutura

O conteúdo já está resolvido (a Ficha do CNPJ descoberto = a Ficha de um planejado).
O preço é cobrado na **navegação/estrutura**:

1. **Linear → árvore.** `pickFocusEstacao` ("primeira não fechada") e a sidebar
   plana assumem sequência. Grafo que cresce vira árvore.
2. **Modelo de dados.** `playbook_definition` é imutável + ponteiro ativo. Um run
   que cresce sozinho precisa que `playbook_run` **materialize o grafo executado**
   (que diverge da definição).
3. **Terminação + custo.** Grupo A↔B↔A = loop. Cada CNPJ = consulta paga. Exige
   **fronteira** (visited-set + teto de profundidade) e **guarda de orçamento** —
   exatamente o cap da transversal #2 do ia-map, que era "adiável" e agora vira pré-requisito.

### A sacada: o dossiê é FRACTAL

A sub-análise de um CNPJ descoberto (cadastral + faturamento + parecer) é, ela
mesma, **um mini-dossiê**. Estrutura auto-similar:

```
Dossiê (alvo)
 ├─ Seção: Faturamento
 ├─ Seção: Cadastral
 ├─ Seção: Contrato social
 └─ Bloco SUB-DOSSIÊ: "Empresa do grupo — XYZ LTDA"   ◄── achado expandido
      └─ (mesma anatomia, um nível abaixo)
          ├─ Seção: Cadastral
          ├─ Seção: ...
          └─ Bloco SUB-DOSSIÊ: ...   ◄── recursão (cap por orçamento)
```

Basta **um** movimento na Camada C: um **bloco "sub-dossiê"** = uma
`SectionDescriptor` aninhada. "Dar zoom no achado" (gesto do ultrassom) = entrar
num sub-dossiê que fala **a mesma gramática visual.** Consistência em **toda
profundidade**, por construção.

### O primitivo de UI novo: Painel de Achados

As "marcações do médico". Itens descobertos-mas-não-investigados ficam num painel,
cada um com **"incluir na análise"** → instancia o sub-ramo pré-declarado.

```
┌─ Achados ──────────────────────────────────────────────┐
│  ⚑ CNPJ do grupo: XYZ LTDA (sócia em comum)             │
│     fonte: ECONOMIC_GROUP_RELATIONSHIPS · ~R$0,05       │
│                              [ Ignorar ] [ Incluir ▸ ]  │
│  ⚑ Protesto encontrado em 2024 ...                      │
└─────────────────────────────────────────────────────────┘
```

### Espectro do "dinâmico" — e onde cravamos a honestidade

| Nível | O que é | Veredito (domínio regulado) |
|---|---|---|
| 1. DAG estático | tudo autorado antes | hoje |
| 2. Fan-out parametrizado | conjunto descoberto em runtime, **forma** de cada ramo pré-declarada | base do sonho |
| **3. Expansão sugerida + gated por humano** | detecta achado → analista clica "incluir" → dispara sub-protocolo versionado | **ALVO. É o ultrassom ao pé da letra.** |
| 4. Auto-construção autônoma total | agente compõe nodes/tools livremente | **briga com §14 (explicabilidade) + §13 (custo). Adiar — talvez nunca, no crédito.** |

O nível 3 entrega o sonho inteiro E é **auditável** (cada expansão = decisão
logada), **cortável** (gate + teto), **reproduzível** (`sub_playbook` versionado —
node type já planejado). Não precisa do nível 4 pra ser mágico.

### Consequência boa: o builder muda de natureza

Se o grafo cresce em runtime, o builder deixa de ser "desenhe cada node" e vira
"**defina o protocolo base + as regras de expansão**" ("quando achado =
membro_de_grupo, ofereça `sub_playbook = onboarding_light`"). Upgrade do modelo
mental — e resolve a R3 por cima (o que o usuário autora = o que governa o crescimento).

---

## 5. MVP vs Fase 2 (o que fazer quando)

### Régua das fases

> **Fase 1 = consistência por construção (estático). Fase 2 = o sonho
> (dinâmico/fractal). Adiado = auto-construção autônoma (nível 4).**

---

**FASE 1 — terminar a filosofia: consolidar a camada de conteúdo (B+C).**

Transforma views bespoke + heurística hardcoded em blocos dirigidos por
`SectionDescriptor`. Mata as 4 rupturas (R1–R4). Em ordem de valor:

- **1.0 (custo ~zero, abre a porta da Fase 2):** (a) desenhar o `SectionDescriptor`
  **já admitindo** o bloco "sub-dossiê" aninhado (mesmo sem ninguém emitir ainda);
  (b) tratar `sub_playbook` como cidadão de primeira classe no modelo; (c) trocar
  a condução sequencial estrita pela **bússola + prontidão por dependência** (§1.1)
  — `pickFocusEstacao` vira sugestão, não cadeado.
- **1.1.** Definir o **vocabulário de blocos** (6 display + 2 interativos) como
  contrato único — `Block = {type, data, provenance}`.
- **1.2.** `<SectionRenderer>` dirigido por `SectionDescriptor` substitui as
  `*AnalysisView`. Migrar as 3 existentes (revenue, cadastral, social) — prova
  que o kit cobre chart-sincronizado + conferência inline.
- **1.3.** Mover `station` + `§ gera seção` + bloco **pro grafo** (sai do
  `AGENT_STATION_AFFINITY`/switch). Builder passa a declarar.
- **1.4.** Unificar renderizador workbench/dossiê sobre o mesmo kit.
- **1.5.** Builder ganha "estação" como primitivo de agrupamento (fecha construir=ver).

> **1.1–1.2 sozinhos entregam ~70% do ganho de consistência SEM tocar no
> builder** — dá pra parar ali e já ter valor real. 1.3–1.5 destravam a liberdade
> (construir=ver) e exigem o workstream backend.
> **Fase 1 NÃO inclui** grafo que cresce, painel de achados, sub-dossiê
> instanciado — só deixa a porta aberta (item 1.0).

---

> **Descoberta na implementação (2026-06-13, Etapa 2→3):** o `DossierReadingView`
> (A4) é uma projeção **deliberadamente TERSA** — §Faturamento mostra o GRÁFICO
> mensal + UMA linha da leitura do agente, não o julgamento inteiro. Duas
> consequências: (a) `mode="read"` não é "os mesmos blocos sem chrome" — é uma
> projeção condensada, que precisa de **iteração visual** (superfície já
> validada); (b) §Faturamento mostra o gráfico **determinístico** → depende do
> produtor "consulta/silver" virar bloco `grafico` (Etapa 4). Logo, **Etapa 3
> (unificar o dossiê) entrelaça com a Etapa 4 e exige o loop visual** — o limpo é
> fazer 4 (produtor determinístico em blocos) + a sintonia do `mode="read"`
> juntas, com validação visual do Ricardo, e não 3 isolada/cega.

**ETAPAS 3–5 — workstream com validação live/visual (não code-only):**
- **Etapa 3** (unificar dossiê): precisa do `mode="read"` terso sintonizado à A4
  validada + depende do produtor determinístico (Etapa 4). Loop visual.
- **Etapa 4** (declaração no grafo + builder de descritor no backend + matar
  `AGENT_STATION_AFFINITY` + controles no `StrataNode`): schema JSONB do
  `playbook_definition` + migration Alembic (aplicar na VM) + endpoint que serve
  `DossierDescriptor`. Code-implementável; **validação exige DB + builder live**.
- **Etapa 5** (estação como primitivo do builder): UI do `@xyflow`; **teste live**.

**FASE 2 — o sonho (nível 3, versão segura):**
- Detecção barata de achado (BDC `ECONOMIC_GROUP_RELATIONSHIPS` ~R$0,05) → achado tipado.
- Painel de Achados + "incluir" → invoca `sub_playbook` **leve** (talvez só gate cadastral).
- Teto de expansões/dossiê + visited-set (mata loop e custo).
- `playbook_run` materializa o grafo executado.

**Adiar (crédito):** nível 4, auto-construção livre.

---

## 6. Fronteiras — onde a definição mora (pós-Fase 1) + export

### 6.1 Composição mora no builder; não há editor de layout (decisão 2026-06-13)

Depois da Fase 1, **layout deixa de ser definido por fluxo.** A definição reparte
em 3 donos:

1. **Chassi (layout macro)** — em código, uma vez (promovido pra `design-system/components`).
2. **Vocabulário de blocos (gramática visual)** — em código, uma vez (conjunto fechado).
3. **Composição (qual estação, quais blocos, em que ordem)** — em **dado**: o grafo
   (node declara `station` + `§ gera seção` + contrato de bloco) + descriptor-builder
   + Contratos de Dados + `output_schema`.

> Montar um fluxo novo = **compor no builder** (`@xyflow`, `workflows/[id]/editor/`),
> não desenhar layout. O `NodeInspector`/`StrataNode` ganha os controles
> (atribuir-a-estação · toggle "gera seção" · picker de contrato de bloco) — Etapas
> 4–5. O layout do dossiê daquele fluxo **emerge sozinho.** Como o dossiê passa a ser
> derivado do grafo, o `EsteiraPreviewPanel` vira **preview ao vivo do esqueleto do
> dossiê** sem precisar rodar.

**Não existe (nem existirá) um "editor de layout do dossiê" separado.** O layout é
derivado. Estilo de dossiê por tenant, se um dia, é **token** — não editor.

### 6.2 Unificado workbench↔dossiê = um motor, dois modos. Export = 3º renderizador.

"Unificar" (item 1.4) = **um** `<SectionRenderer>`, dois modos — não duas bases:
`mode="work"` (editável: conferência=input, gates acionáveis, ClosureBar) ·
`mode="read"` (projeção A4 read-only). Trabalhar numa estação e ler sua seção no
dossiê = **os mesmos blocos** em estados diferentes. O dossiê-artefato continua
existindo; só **para de ser um segundo renderizador**.

**O PDF (e talvez PPT) continua necessário no fim** — o comitê/arquivo/compliance
(§14) precisam de um artefato **congelado, assinado, portátil**, diferente da tela
HTML interativa. A unificação torna isso **mais fácil**: como o conteúdo agora é um
`SectionDescriptor` tipado, o gerador de PDF vira **um terceiro renderizador do mesmo
descritor** — `work` / `read` / **PDF server-side**. Mesmos blocos, três saídas →
**o artefato assinado = exatamente o que foi revisado, por construção** (zero drift).
PDF é o formato natural do dossiê de crédito; **PPT a definir** (outro caso de uso —
deck/resumo; se vier, é mais um renderizador, ou de um subset).

> **Escopo:** o PDF server-side **NÃO está na Fase 1** (hoje é `window.print`
> interino; o "de verdade" entra junto da assinatura/congelamento — Fase 4 do
> handoff Conceito D). A Fase 1 só o torna trivial depois.

---

## 7. Riscos a respeitar (não varrer pra debaixo do tapete)

- **Blocos interativos são o trabalho real.** Display é trivial; conferência-editável
  e fonte+origem têm interação + write-back. É aí que mora o esforço — não no motor.
- **Terminação/ciclos** no sonho: fronteira obrigatória (visited-set + cap de profundidade).
- **Custo:** o sonho é o caso de uso que **finalmente exige** o guarda de orçamento (transversal #2).
- **Auditabilidade do grafo dinâmico:** `decision_log` registra "expandiu porque
  achado X / analista Y decidiu"; `playbook_run` guarda o grafo executado.
- **Não é over-engineering** porque as análises são **homogêneas em forma** (agente
  lê silver → julgamento → homologa). Se fossem telas genuinamente diferentes, o
  block-renderer não pagaria. Pagam por causa da homogeneidade.

---

## 8. Próximo passo de design

Descer no **vocabulário de blocos concreto**: o contrato de dado de cada um dos
6 display + 2 interativos + o bloco sub-dossiê, e o tipo `SectionDescriptor` /
`Block` em TypeScript + como cada tipo de node o emite (com o gancho no Contrato
de Dados pras consultas). É a decisão que trava todo o resto.

---

**Relacionado:** [`esteira-credito-ia-map.md`](./esteira-credito-ia-map.md) ·
[`esteira-credito-vocabulario.md`](./esteira-credito-vocabulario.md) ·
memórias `project_esteira_credito_handoff_conceito_d`,
`project_esteira_credito_design_camadas`, `project_contratos_de_dados`,
`project_roadmap_agentes_power_law`.
