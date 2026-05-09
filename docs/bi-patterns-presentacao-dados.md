# BI — patterns de apresentacao de dados

> Documento de fundamentacao para o **2o pattern de BI** (working name: `DashboardBiAnalise`). Nao implementa nada. Vira base do PR que cria o pattern em `frontend/src/design-system/patterns/`. Le em ~25 min.

---

## 1. Contexto e problema

### 1.1 Sintoma

Toda pagina de BI hoje nasce do pattern canonico [`DashboardBiPadrao`](../frontend/src/design-system/patterns/DashboardBiPadrao.tsx) (CLAUDE.md §7). A area util da pagina abre com `<KpiStrip>` carregando 5 KPIs em tile horizontal. Em `/bi/operacoes2`, `/bi/operacoes` e qualquer pagina derivada do pattern, o usuario reporta que **pula o strip e vai direto pros charts e tabelas abaixo**. Os tiles nao puxam a analise — decoram a pagina.

### 1.2 Caso real — `operacoes2`

Olhando o codigo da pagina:

| Z3 ([`page.tsx:417-500`](../frontend/src/app/(app)/bi/operacoes2/page.tsx)) | Z4 ([`AbaMesCorrente.tsx:264-342`](../frontend/src/app/(app)/bi/operacoes2/_components/AbaMesCorrente.tsx)) |
|---|---|
| `KpiStrip` com 5 tiles | Grid 2×3 com 6 cards de **decomposicao** |
| VOP (valor + delta MTD) | VarianceBridgeCard de **VOP** com drivers detalhados |
| Receita contratada (valor + delta MTD) | VarianceBridgeCard de **Receita** com drivers detalhados |
| Taxa media (valor + delta MTD) | PvmBridgeCard de **Taxa** (mix vs intra) |
| Prazo medio (valor + delta MTD) | PvmBridgeCard de **Prazo** (mix vs intra) |
| Produto top (sigla + share %) | DumbbellCard de **Mix de produtos** |
| — | ConcentracaoDeltaCard (HHI delta) |

**4 dos 5 tiles repetem exatamente o que a Aba decompoe logo abaixo.** O usuario le o tile com "VOP R$ 3,7 mi (+4,2% MTD)", desce 200px e encontra o mesmo numero com decomposicao por driver em formato bridge. O tile vira preambulo redundante.

Ainda pior: o `<KpiStrip>` em `operacoes2/page.tsx` esta em "modo leve" — sem sparkline, sem callout pill, sem intensity bar — entao o tile tem **menos contexto** do que o chart embaixo. E preambulo redundante *e* mais pobre.

### 1.3 Hipotese

O problema nao e "tile". Stripe usa tiles ([4 cards: revenue + charges + payouts + disputes, com numero + delta + sparkline](https://artofstyleframe.com/blog/dashboard-design-patterns-web-apps/)) e funciona. PatternFly cataloga 5 variantes de card de KPI ([Aggregate Status / Trend / Utilization / Details / Events](https://www.patternfly.org/patterns/dashboard/design-guidelines/)). Tile e paradigma valido.

O problema **especifico do nosso caso** e mais estreito:

> Quando a area util da pagina **e** decomposicao analitica, o tile vira preambulo redundante.

Pagina existe pra responder uma pergunta. Se a pergunta e "qual o estado dos meus KPIs?", strip de tile responde direto. Se a pergunta e "por que VOP variou 4,2% MTD?", o strip duplica o que o chart de decomposicao explica melhor — vira ruido editorial.

**Solucao:** dois patterns coexistindo, com criterio objetivo de qual usar:

- **`DashboardBiPadrao`** (atual) — usado quando a area util **nao** repete os KPIs do strip. Tile responde "como esta", chart abaixo abre lente diferente (drill por entidade, serie temporal pura, ranking, etc).
- **`DashboardBiAnalise`** (novo) — usado quando a area util **e** decomposicao dos proprios KPIs. Tile saiu — KPI vive no titulo do chart, em anotacao no ponto, ou em frase narrativa.

`KpiStrip` e `KpiCard` continuam servindo o `DashboardBiPadrao` sem mudanca.

### 1.4 O que este doc NAO faz

- Nao implementa o `DashboardBiAnalise`
- Nao altera `KpiStrip`/`KpiCard` (continuam servindo o pattern atual)
- Nao migra paginas existentes
- Nao decide o destino dos KPIs de outras abas alem da Aba "Mes corrente"
- Nao estende o `EChartsCard` para receber KPI no header (PR separado, fora do escopo da pesquisa)

---

## 2. Diagnostico critico do KpiStrip atual

### 2.1 O componente

[`frontend/src/design-system/components/KpiStrip/index.tsx`](../frontend/src/design-system/components/KpiStrip/index.tsx) ja e bem desenhado. Tem:

- 3 variants (compact 18px / default 20px / hero 30px)
- Sparkline opcional (side ou stacked)
- IntensityBars opcionais
- AlertBadge opcional
- Callout pill no pico do sparkline
- Provenance dot (CLAUDE.md §14.1)
- Delta direcional com cor semantica

Quando todas as features estao ligadas, um KpiCard carrega ~8 sinais visuais ao mesmo tempo: label, value, sub, delta, deltaSub, sparkline, intensity, source. E rico.

### 2.2 O modo de falha

Em `operacoes2/page.tsx`, o KpiStrip esta em **modo leve**: so label + value + sub + delta. Sem sparkline (`sparkData` nao passado), sem intensity, sem alert. Um tile assim carrega ~3 sinais — menos do que a frase narrativa em [`AbaMesCorrente.tsx:253-254`](../frontend/src/app/(app)/bi/operacoes2/_components/AbaMesCorrente.tsx) ja entrega:

```tsx
<p className="...text-sm text-gray-800...">
  {data.narrative_sentence}
</p>
```

A `narrative_sentence` e uma frase como "VOP cresceu 4,2% MTD vs mês anterior, puxado por Lucratti (+R$ 850k) e parcialmente compensado por queda em Trade (-R$ 320k)". **Uma frase ja resolve o que 5 tiles tentam comunicar com gauges separadas.** E o backend ja gera essa frase.

### 2.3 Modos de falha ranqueados (Stephen Few, [13 mistakes](https://medium.com/@antonioneto_17307/thirteen-common-mistakes-in-dashboard-design-cc1a0dc07750))

Em ordem de gravidade na nossa pagina:

| # | Mistake (Few) | Como aparece no `KpiStrip` em modo leve |
|---|---|---|
| 11 | Cluttering with useless decoration | 5 tiles ocupam ~120px de altura entregando 3 sinais cada — densidade baixa |
| 10 | Highlighting important data ineffectively | Todos os 5 tiles tem o mesmo peso visual. Nenhum se destaca como "este e o mais importante" |
| 2 | Supplying inadequate context for data | "VOP R$ 3,7 mi" sem trajetoria (sem sparkline) ou benchmark (vs CDI? vs orcamento?) — usuario nao sabe se e bom |
| 9 | Arranging data poorly | Strip separado fisicamente da decomposicao quebra a leitura "metrica → causa". Ler tile + descer + ler bridge fragmenta a narrativa |

### 2.4 Conclusao do diagnostico

O `KpiStrip` em modo leve, na frente de uma aba de decomposicao, falha em 4 dos 13 itens do Few. Nao e bug do componente — e bug de **escolha de pattern**. A pagina nao deveria ter strip.

---

## 3. Fundamentacao teorica

Tres conceitos canonicos sustentam a recomendacao. Sintese pratica, nao revisao academica.

### 3.1 Data-ink ratio (Tufte)

Edward Tufte, [*The Visual Display of Quantitative Information* (1983, cap. 4)](https://thedoublethink.com/tuftes-principles-for-visualizing-quantitative-information/):

> "Above all else show data. Maximize the data-ink ratio. Erase non-data-ink. Erase redundant data-ink."

Data-ink ratio = pixels que codificam dado / pixels totais. Em `operacoes2`, o KpiStrip em modo leve tem ratio baixo: ~50% de borda + padding + label uppercase + espaco em branco. **A informacao por pixel e baixa.** Tufte chama o restante de **chartjunk** quando nao serve a leitura.

Aplicacao: a substituicao do tile precisa entregar **mais informacao no mesmo espaco** (sparkline embutida, anotacao no chart, frase narrativa) — nao remover o tile e deixar buraco.

### 3.2 Tile syndrome / cluttering decoration (Few)

Stephen Few, [*Information Dashboard Design* (2nd ed., 2013, cap. 4 e 5)](https://www.perceptualedge.com/articles/Whitepapers/Common_Pitfalls.pdf):

> "Unnecessary decorative elements, such as gauges, meters, and excessive borders, can distract users from analytical content. Instead of conveying information, they consume valuable real estate."

Few nao e contra tile — ele e contra **tile que nao puxa decisao**. O criterio dele: cada tile responde "qual a melhor acao agora?". Se tile nao chega na pergunta, vira moldura.

Aplicacao: cada KPI no novo pattern precisa carregar **acao implicita** ("VOP esta abaixo da meta — abrir drivers"). Se o numero so existe pra "saber", ele vive no titulo do chart, nao em tile separado.

### 3.3 Preattentive attributes + visual hierarchy (Knaflic)

Cole Nussbaumer Knaflic, [*Storytelling with Data* (2015, cap. 4)](https://readingraphics.com/book-summary-storytelling-with-data/):

> "If there's a conclusion you want them to reach, state it in words. Make them big. Make them bold. Put them in high-priority places."

Preattentive attributes (cor, tamanho, posicao) sao processados em ~250ms — antes do usuario "decidir olhar". Knaflic ataca diretamente o paradigma de strip uniforme: se todos os 5 tiles tem o mesmo tamanho/cor, nenhum e preattentive — o usuario tem que escolher onde olhar.

Aplicacao: o pattern novo deve ter **hierarquia visual explicita**. Um numero grande (hero), 2-3 numeros secundarios menores, e contexto em sparkline/anotacao. Nao 5 numeros do mesmo tamanho.

---

## 4. Catalogo de patterns alternativos

Oito patterns nomeados que substituem ou complementam o strip de tiles. Cada um com: quando usar, quando NAO usar, produto que aplica, mockup, referencia.

### 4.1 Big Number (BAN)

Nome canonico: **Big Ass Number** ([termo aceito na industria BI](https://www.simplekpi.com/Resources/Dashboard-Charts-And-Graphs)). Numero unico, grande, bold, no topo da pagina ou da secao.

**Quando usar:**
- Pagina ou secao tem **uma metrica que importa acima de todas** (PL do fundo, NPS, MRR)
- Numero responde uma pergunta direta sem ambiguidade

**Quando NAO usar:**
- Mais de 1-2 numeros competem pelo mesmo nivel de destaque
- Numero precisa de muito contexto pra ser interpretado (entao use Comparative Stat)

**Exemplo:** topo do `/credito/pipeline` mostrando "R$ 12,4 mi em propostas ativas" como BAN, com tudo embaixo decompondo. Stripe usa em [paginas de balance](https://docs.stripe.com/dashboard/basics).

**Mockup ASCII:**

```
┌────────────────────────────────────────────────────────────┐
│  PROPOSTAS ATIVAS                                          │
│  R$ 12,4 mi                                                │
│  +18% vs mês anterior                                      │
│                                                            │
│  [decomposicao por status / cedente / produto abaixo]     │
└────────────────────────────────────────────────────────────┘
```

**Traducao DS:** novo composite `<HeroNumber>` (em `design-system/components/`) ou `<KpiCard variant="hero">` ja existente, isolado em `<Card>` full-width. Nao precisa primitiva nova.

**Referencia:** [SimpleKPI — KPI Visualization Patterns](https://www.simplekpi.com/Resources/Dashboard-Charts-And-Graphs); [DataCamp — Effective Dashboard Design](https://www.datacamp.com/tutorial/dashboard-design-tutorial).

---

### 4.2 Stat-and-spark

Numero + sparkline acoplados na mesma cell. Sparkline e [palavra-grafica de Tufte](https://www.edwardtufte.com/notebook/sparkline-theory-and-practice-edward-tufte/) — embute trajetoria sem ocupar coluna separada.

**Quando usar:**
- Numero precisa de **trajetoria recente** pra ser interpretado (esta subindo? caindo? volatil?)
- Tile permanece na pagina mas precisa carregar mais sinal por pixel

**Quando NAO usar:**
- Tendencia nao e relevante (dado snapshot que nao varia)
- Sparkline tem < 6 pontos (vira ruido)

**Exemplo:** Stripe Dashboard ([revenue + charges + payouts + disputes](https://artofstyleframe.com/blog/dashboard-design-patterns-web-apps/)) — cada card e numero + delta + sparkline. PatternFly nomeia [Trend Cards](https://www.patternfly.org/patterns/dashboard/design-guidelines/).

**Mockup ASCII:**

```
┌────────────────────────────────┐
│  VOP                           │
│  R$ 3,7 mi    ╱╲    ↑ 4,2% MTD │
│             ╱  ╲╱╲             │
│           ╱      ╲             │
│  Bitfin · há 3min              │
└────────────────────────────────┘
```

**Traducao DS:** ja existe — `<KpiCard sparkData={...} layout="side" />`. **Esta e a forma rica do tile que CONTINUA valida no `DashboardBiPadrao`.** O bug nao e o stat-and-spark — e o strip de 5 stat-and-sparks repetindo o que vem abaixo.

**Referencia:** [Tufte — Sparkline theory and practice](https://www.edwardtufte.com/notebook/sparkline-theory-and-practice-edward-tufte/); [Wikipedia — Sparkline (Tufte 2006)](https://en.wikipedia.org/wiki/Sparkline).

---

### 4.3 Hero Chart com KPI no titulo

O **chart e o tile**. Numero + delta moram no header do EChartsCard ("VOP — R$ 3,7 mi · +4,2% MTD"), e a area de plot ocupa o espaco que seria do tile + chart separados.

**Quando usar:**
- A area util da pagina e analitica (decomposicao, serie temporal, ranking)
- Numero unico domina a leitura — o chart explica *por que*
- Quer eliminar redundancia "tile + chart do mesmo KPI"

**Quando NAO usar:**
- Pagina tem 5+ KPIs heterogeneos sem chart de decomposicao para cada (entao Pattern A e melhor)
- Numero principal nao se traduz num chart (ex.: produto top sigla)

**Exemplo:** Stripe revenue chart — header "Total volume · $245,628.42 (+8.4%)", chart embaixo. Vercel Analytics — pagina de paises/devices abre com header "Visitors · 1.2M (+12%)" e barchart embaixo.

**Mockup ASCII:**

```
┌──────────────────────────────────────────────────────────────┐
│  VOP                                          [exportar][...]│
│  R$ 3,7 mi   ↑ 4,2% MTD vs mês anterior                      │
│                                                              │
│   ▲                                                          │
│   │       ╱╲                            ╱──                  │
│   │     ╱   ╲       ╱╲                ╱                      │
│   │   ╱       ╲   ╱   ╲      ___    ╱                        │
│   │ ╱           ╲╱      ╲___╱   ╲__╱                         │
│   └─────────────────────────────────────────                 │
│   1   3   5   7   9  11  13  15  17  19  DU                  │
│                                                              │
│  Bitfin · atualizado há 3 min                                │
└──────────────────────────────────────────────────────────────┘
```

**Traducao DS:** estende `<EChartsCard>` para aceitar `bigNumber={{ value, delta, deltaSub }}` no header. Ja tem `title` e `subtitle` — adiciona slot de KPI editorial entre eles. Componente novo nao e necessario; e refactor de prop do existente. **PR separado, fora do escopo deste doc.**

**Referencia:** [DataCamp — Effective Dashboard Design](https://www.datacamp.com/tutorial/dashboard-design-tutorial) ("Lead with the decision-driving KPIs using size and position to make them unmissable"); padrao observavel em Stripe, Vercel, Linear.

---

### 4.4 In-Chart Annotation

Numero ou frase posicionada **diretamente sobre** o ponto relevante do chart — nao em legenda, nao em tile, nao em titulo. Funciona como callout grafico.

**Quando usar:**
- Existe um ponto especifico do chart que carrega a historia (pico, vale, evento)
- Quer eliminar a ida-e-volta entre chart e tabela de valores

**Quando NAO usar:**
- Multiplos pontos competem por anotacao (vira poluicao)
- Anotacao precisa de muito texto (entao vira tooltip)

**Exemplo:** [Observable — Five techniques to improve chart annotations](https://observablehq.com/blog/five-techniques-to-improve-chart-annotations); FT charts marcam picos com label inline (ex.: "+R$ 850k em 18/04 — Lucratti"). Datawrapper tem o pattern como recurso primario.

**Mockup ASCII:**

```
   ▲
   │              ┌─────────────────┐
   │              │ +R$ 850k        │
   │              │ Lucratti — 18/04│
   │              └────────┬────────┘
   │       ╱╲              ▼
   │     ╱   ╲            ╳
   │   ╱       ╲   ╱──────────
   │ ╱           ╲╱
   └────────────────────────────►
```

**Traducao DS:** ECharts ja suporta nativamente via `series[].markPoint` e `graphic` ([CLAUDE.md §4](../CLAUDE.md) explicita que hex literal em EChartsOption e permitido). Anotacao nao precisa de componente novo — vira preset em `tokens/echarts-theme` ou helper em `lib/chartUtils`.

**Referencia:** [Knaflic — Storytelling with Data, cap. 6](https://readingraphics.com/book-summary-storytelling-with-data/); [Observable](https://observablehq.com/blog/five-techniques-to-improve-chart-annotations).

---

### 4.5 Sentence-form KPI (frase narrativa)

Frase em prosa que carrega 2-4 numeros embutidos em texto explicativo. Substitui o strip inteiro com **uma linha**.

**Quando usar:**
- A historia da pagina e linear ("VOP subiu, puxado por X, freado por Y")
- Backend ja consegue gerar a frase (ja temos isso em `AbaMesCorrente` via `narrative_sentence`)

**Quando NAO usar:**
- Numeros nao tem relacao narrativa entre si (sao 5 KPIs independentes)
- Frase passa de ~140 caracteres (vira paragrafo, perde escaneabilidade)

**Exemplo:** [`AbaMesCorrente.tsx:253-254`](../frontend/src/app/(app)/bi/operacoes2/_components/AbaMesCorrente.tsx) **ja faz isso** dentro da aba (renderiza `data.narrative_sentence` no topo da Linha 1). O proprio backend ja serve a frase pronta. FT charts usam o pattern em deck/exec summaries; Knaflic recomenda explicitamente em [cap. 4](https://readingraphics.com/book-summary-storytelling-with-data/).

**Mockup ASCII:**

```
┌────────────────────────────────────────────────────────────┐
│  VOP cresceu 4,2% MTD (R$ 3,7 mi vs R$ 3,5 mi mês anterior),│
│  puxado por Lucratti (+R$ 850k) e parcialmente compensado  │
│  por queda em Trade (-R$ 320k).                            │
│                                                            │
│  [decomposicao detalhada abaixo]                           │
└────────────────────────────────────────────────────────────┘
```

**Traducao DS:** componente `<NarrativeBanner sentence={...} />` em `design-system/components/`. Wrapper de `<Card cardTokens.body>` com `<p text-sm>`. Aceita `Provenance` opcional. PR de implementacao — minutos, nao horas.

**Referencia:** [Knaflic — Storytelling with Data, cap. 4](https://readingraphics.com/book-summary-storytelling-with-data/); [phData — Dashboard Design Essentials](https://www.phdata.io/blog/dashboard-design-essentials-kpi-templates/).

---

### 4.6 Comparative Stat Block

Bloco de 2-3 numeros em hierarquia visual: um primario (grande), um ou dois secundarios (menores) que dao contexto pro primario. Versao "expandida" do BAN.

**Quando usar:**
- Numero so faz sentido com 1-2 comparacoes (ex.: "atual vs orcado vs ano passado")
- Quer evitar 3 tiles separados que mascaram a relacao

**Quando NAO usar:**
- Comparacao e implicita ja no delta (% MTD ja cobre — entao Stat-and-spark basta)
- Mais de 3 numeros competem (vira mini-strip que volta ao problema original)

**Exemplo:** [PatternFly Aggregate Status Card](https://www.patternfly.org/patterns/dashboard/design-guidelines/) — total + breakdown por estado (errors, warnings, ok) numa unica cell. IBM Carbon recomenda como [single number contextual](https://carbondesignsystem.com/data-visualization/dashboards/).

**Mockup ASCII:**

```
┌──────────────────────────────────┐
│  RECEITA                         │
│                                  │
│  R$ 1,2 mi                       │
│  ── 84% do orcado mensal         │
│  ── R$ 1,1 mi mesmo mes 2025     │
└──────────────────────────────────┘
```

**Traducao DS:** novo composite `<ComparativeStatBlock>` em `design-system/components/`. Composto de `<Card cardTokens.body>` + value-grande (text-xl/text-2xl tabular-nums) + 2-3 linhas de "marker + sub-label + sub-value". Nao precisa primitiva nova.

**Referencia:** [PatternFly Dashboard Patterns](https://www.patternfly.org/patterns/dashboard/design-guidelines/); [Carbon Design System — Dashboards](https://carbondesignsystem.com/data-visualization/dashboards/).

---

### 4.7 Stacked Number Hierarchy

Numero grande (hero) + 2-4 sub-stats menores **agregados visualmente** (relacao de filiacao explicita: o sub-stat e parte do hero). Diferenca pro Comparative: aqui os sub-stats DECOMPOEM o hero, nao comparam.

**Quando usar:**
- Numero principal e soma/agregacao dos sub-stats (PL = subord. + senior; VOP = produto A + B + C)
- Hierarquia matematica precisa ser preattentive

**Quando NAO usar:**
- Sub-stats nao decompoem o hero (relacao nao matematica) — use Comparative
- Decomposicao tem > 5 categorias (entao vira waterfall ou stacked bar)

**Exemplo:** Linear roadmap pages — numero de issues + breakdown por status (in-progress / blocked / done). Bloomberg Terminal — PL + breakdown por classe de ativo.

**Mockup ASCII:**

```
┌──────────────────────────────────────────┐
│  PL DO FUNDO                             │
│                                          │
│  R$ 248,5 mi                             │
│                                          │
│   ├ Cota senior        R$ 198,8 mi  80% │
│   ├ Cota subordinada   R$  37,3 mi  15% │
│   └ Caixa              R$  12,4 mi   5% │
└──────────────────────────────────────────┘
```

**Traducao DS:** novo composite `<StackedNumberHierarchy>` em `design-system/components/`. Card + value-hero + lista de rows com character `├ └`, label, value tabular-nums, share. Acessibilidade: lista semantica `<dl>` com `<dt>/<dd>`.

**Referencia:** [Datawrapper Academy — Dashboard layouts](https://www.datawirefra.me/blog/dashboard-layout-patterns); [PatternFly Aggregate Status](https://www.patternfly.org/patterns/dashboard/design-guidelines/).

---

### 4.8 Contextual Stat Block

Numero embutido em paragrafo de prosa curta (~2-3 linhas) com bold no que importa. Versao "hibrido" entre Sentence-form e Comparative.

**Quando usar:**
- Numero precisa de contexto narrativo curto (1-2 frases) que nao cabe em sub-label
- Pagina e exec-friendly — usuario le como noticia, nao como tabela

**Quando NAO usar:**
- Numero e parte de comparacao multipla (use Stacked ou Comparative)
- Tem que carregar 3+ numeros — vira paragrafo, perde escaneabilidade

**Exemplo:** [Pew Research — fact sheets](https://www.pewresearch.org/) — cada fato e paragrafo de 2 linhas com 1 numero em bold. Stripe billing reports.

**Mockup ASCII:**

```
┌──────────────────────────────────────────────────────────────┐
│  Inadimplencia                                               │
│                                                              │
│  Taxa media de **3,4%** este mes — alta de 0,6 pp vs media   │
│  trimestral. Movimento concentrado em **2 cedentes** (Lucratti│
│  + Trade) que somam **R$ 1,2 mi** em valor inadimplido.      │
└──────────────────────────────────────────────────────────────┘
```

**Traducao DS:** novo composite `<ContextualStatBlock>` em `design-system/components/`. Card + `<p>` com children que aceita `<strong>` para bold. Nao precisa primitiva nova.

**Referencia:** [Knaflic — Storytelling with Data, cap. 4-6](https://readingraphics.com/book-summary-storytelling-with-data/); [Pew Research style guide](https://www.pewresearch.org/).

---

## 5. Analise de produtos de referencia

Seis produtos escolhidos por (a) ter design publico documentado e (b) representar posturas distintas sobre a tensao tile-vs-integrado.

### 5.1 Stripe Dashboard

**Postura dominante:** **Stat-and-spark + Hero Chart com KPI no titulo.**

Stripe usa tiles ([4 cards: revenue + charges + payouts + disputes, com sparkline](https://artofstyleframe.com/blog/dashboard-design-patterns-web-apps/)), mas:

1. Tiles vem **acima** de uma area de chart **diferente do tile**. Nao se repete o mesmo numero abaixo.
2. Tiles **sempre** tem sparkline + delta — nunca sao "modo leve".
3. Quando usuario clica num tile, ele vai pra **outra pagina** que abre Hero Chart com KPI no header (nao mais um strip — agora a pagina inteira e sobre aquele numero).

**Licao para o GR:** se mantiver strip, exigir sparkline. Se pagina e analise de KPI especifico, dropar strip e usar Hero Chart.

**Referencia:** [Web Dashboard | Stripe Documentation](https://docs.stripe.com/dashboard/basics); [artofstyleframe analysis](https://artofstyleframe.com/blog/dashboard-design-patterns-web-apps/).

### 5.2 Vercel Analytics

**Postura dominante:** **Hero Chart + breakdown panels.**

Vercel Web Analytics ([docs](https://vercel.com/docs/analytics)) abre cada vista (Visitors / Page Views / Top Pages) com:

1. Hero number gigante no topo ("1,247,892 visitors") + delta vs periodo anterior
2. Chart de serie temporal embaixo ocupando ~50% da viewport
3. **Sem strip de tiles.** Painel lateral lista breakdowns (top pages, top countries, etc.) como tabelas-rank, nao tiles.

**Licao para o GR:** valida o `DashboardBiAnalise` quase literal — Hero Chart no topo + decomposicao em cards/tabelas lateralmente, zero strip.

**Referencia:** [Vercel Web Analytics Docs](https://vercel.com/docs/analytics).

### 5.3 Linear

**Postura dominante:** **Densidade tabular + Stacked Number Hierarchy.**

Linear evita strip de KPI completamente. Roadmap pages mostram: numero total + lista expansivel com status counts (Stacked Number Hierarchy 4.7). Issues view e tabela densa com filtros — sem KPI tile algum.

**Licao para o GR:** em paginas que sao **listagem com agregados**, Stacked Number no topo + tabela densa abaixo bate strip de tile em densidade de informacao.

**Referencia:** Linear UI publica (changelog em linear.app/changelog).

### 5.4 Bloomberg Terminal / Koyfin

**Postura dominante:** **Densidade extrema, zero KPI decorativo.**

Bloomberg Terminal e [Koyfin](https://www.koyfin.com/features/) — feitos pra profissional de mercado financeiro — **nao tem KPI tile** em quase nenhuma vista. Toda area util e chart, tabela, ou matrix de numeros densos. Hierarquia se da por:

- **Posicao** (numero importante no topo-esquerda, regra de leitura ocidental)
- **Cor** (verde/vermelho semantico em cells, nada decorativo)
- **Tamanho** (numero principal 2-3x maior que o resto, in-line, nao em tile separado)

Koyfin Macro Dashboards ([feature page](https://www.koyfin.com/features/)) usam o que descrevemos como Comparative Stat Block + Hero Chart — nunca strip de tile.

**Licao para o GR:** publico FIDC e proximo ao publico Bloomberg — analista que olha o dashboard horas por dia. Tile decorativo cansa. Densidade alta sem chartjunk e o que o publico-alvo prefere.

**Referencia:** [Koyfin Features](https://www.koyfin.com/features/); [Koyfin vs Bloomberg comparison](https://www.alpha-sense.com/compare/koyfin-vs-bloomberg/).

### 5.5 FT charts / Visual Vocabulary

**Postura dominante:** **In-Chart Annotation + Sentence-form KPI.**

FT publica o [Visual Vocabulary](https://github.com/Financial-Times/chart-doctor/tree/main/visual-vocabulary) — catalogo de tipos de chart organizado por **intencao** (deviation, correlation, ranking, distribution, change over time, part-to-whole, magnitude, spatial). Charts FT em si (no jornal e nas paginas analiticas) **quase sempre** carregam:

1. Titulo editorial completo ("Brent crude price hits $90/barrel for first time in 6 months")
2. Numero hero embutido no titulo
3. Anotacao in-chart no ponto relevante (callout sobre o pico)
4. **Sem strip de tile separado.**

**Licao para o GR:** o titulo do chart pode carregar o KPI. Combinacao Hero Chart com KPI no titulo (4.3) + In-Chart Annotation (4.4) e o paradigma FT por excelencia.

**Referencia:** [FT Visual Vocabulary GitHub](https://github.com/Financial-Times/chart-doctor/tree/main/visual-vocabulary); [PDF version](https://journalismcourses.org/wp-content/uploads/2020/07/Visual-vocabulary.pdf).

### 5.6 IBM Carbon Design System

**Postura documentada:** **Hierarquia explicita por tamanho e contraste.**

Carbon ([Dashboards](https://carbondesignsystem.com/data-visualization/dashboards/)) recomenda:

> "Prioritize data by importance and create a clear visual hierarchy, with the most important data having the highest contrast and occupying the largest area."

Carbon nao proibe tiles — ele exige **hierarquia entre tiles**. Strip de 5 tiles do mesmo tamanho e o anti-pattern. Eles oferecem [3 layouts](https://carbondesignsystem.com/data-visualization/dashboards/) (monitoring / exploration / analytical) com tile usado seletivamente, sempre com 1 tile dominante + 2-3 secundarios.

**Licao para o GR:** se mantiver strip, **quebrar a uniformidade**. Um KPI hero com `variant="hero"` + 2-3 secundarios `variant="compact"` resolve metade do problema sem trocar de pattern.

**Referencia:** [Carbon Design System — Dashboards](https://carbondesignsystem.com/data-visualization/dashboards/); [IBM Design Language — Data Viz](https://www.ibm.com/design/language/data-visualization/overview/).

---

## 6. Sintese — proposta de 2o pattern

### 6.1 Nome

**`DashboardBiAnalise`**. Captura o foco: pagina cuja area util **e** decomposicao analitica. Outros nomes considerados e descartados:

- ~~`DashboardBiNarrativo`~~ — ambiguo (todo dashboard tem narrativa)
- ~~`DashboardBiContextual`~~ — todo dashboard e contextual
- ~~`DashboardBiHero`~~ — implica que tem que ter hero number (nem sempre tera)
- ~~`DashboardBiDecomposicao`~~ — tecnicamente correto mas verboso

A ratificar pelo usuario antes do PR de implementacao.

### 6.2 Estrutura de zonas

Mantem o esqueleto de 5 zonas do `DashboardBiPadrao` (PageHeader / TabNav+Filtros / InsightStrip / Conteudo / ProvenanceFooter) — sem reinventar chrome — mas troca a Z4:

| Zona | DashboardBiPadrao | DashboardBiAnalise |
|---|---|---|
| Z1 | PageHeader (titulo + actions) | **Igual** |
| Z2 | Toolbar 52px (TabNav + FilterBar) | **Igual** |
| Z3 | InsightStrip (38px violeta) | **Igual** |
| Z4a | `KpiStrip` com 5 KpiCards | **Removido**. Em vez disso: `<NarrativeBanner>` (4.5) — 1 frase narrativa do backend |
| Z4b | Grid de charts/tabela | **Grid de cards-chart** (cada card e Hero Chart com KPI no titulo, 4.3) |
| Z5 | ProvenanceFooter | **Igual** |

### 6.3 Composicao recomendada por aba

**Padrao de aba "decomposicao":** Sentence-form KPI (4.5) no topo + grid de Hero Charts (4.3) cada um decompondo um KPI.

**Padrao de aba "ranking/listagem":** BAN ou Comparative (4.1 / 4.6) no topo + tabela densa abaixo (zero KPI tile).

**Padrao de aba "serie temporal":** Hero Chart unico full-width (4.3) ocupando ~70% da Z4 + In-Chart Annotation (4.4) nos pontos relevantes + tabela compacta de drilldown abaixo.

### 6.4 Criterio objetivo — `DashboardBiPadrao` vs `DashboardBiAnalise`

Use **`DashboardBiPadrao`** quando **todas** sao verdadeiras:

1. KPIs do strip sao **heterogeneos** (medem coisas diferentes — PL + Subordinacao + Rentabilidade + Resgates + Cessoes pendentes)
2. Conteudo da Z4 **nao decompoe** os KPIs do strip (mostra outra coisa — listagem de cessoes, drilldown por entidade, time series unica)
3. Strip sera servido com **sparkline + delta + provenance** (modo rico, nao leve)
4. Pagina e exec-readable em **< 30 segundos** (scan rapido)

Use **`DashboardBiAnalise`** quando **qualquer** for verdadeira:

1. Conteudo da Z4 e **decomposicao** dos numeros que iriam no strip (variance bridge, PVM, dumbbell, ranking de drivers)
2. Pagina tem **< 4 KPIs principais** que merecem destaque editorial — nao 5 uniformes
3. Strip foi cogitado em **modo leve** (sem sparkline) — sintoma de que o strip e preambulo, nao analise
4. Backend ja emite **`narrative_sentence`** que sintetiza o estado da pagina
5. Tempo medio de leitura esperado e **> 1 min** (analise, nao scan)

Em caso de duvida, vale a regra simples: **se o strip repete o que vem abaixo, dropa o strip → use Analise**.

### 6.5 Limites do pattern (o que ele NAO substitui)

`DashboardBiAnalise` **nao** elimina `KpiStrip`/`KpiCard`. Ambos continuam servindo `DashboardBiPadrao`. As paginas relevantes:

| Pagina | Pattern recomendado |
|---|---|
| `/bi/operacoes2` | `DashboardBiAnalise` (caso real do problema) |
| `/bi/operacoes` (legado) | `DashboardBiAnalise` quando migrar |
| `/bi/carteira` | `DashboardBiPadrao` (PL + subord + rent + resgates sao heterogeneos) |
| `/bi/fluxo-caixa` | `DashboardBiAnalise` (decomposicao de fluxo) |
| `/bi/benchmark` | `DashboardBiPadrao` (KPIs heterogeneos + drilldown por fundo) |
| `/risco/concentracao` | `DashboardBiAnalise` (decomposicao HHI / top-N) |
| `/credito/pipeline` | `DashboardBiPadrao` (counts heterogeneos + lista) |

---

## 7. Aplicacao experimental — `bi/operacoes2` Aba "Mes corrente"

Como ficaria a pagina sob `DashboardBiAnalise`. **Mockup textual, nao implementacao.**

### 7.1 Estado atual (problema)

```
┌─────────────────────────────────────────────────────────────────┐
│  BI · Operacoes                          [DarkToggle][AI][...]  │
├─────────────────────────────────────────────────────────────────┤
│  [Mes corrente] Volume&Ritmo  Produtos  Receita  Cedentes       │  <- Z2
│  Periodo: 12m  Produto: Todos  UA: Todas  ...  Atualizado       │
├─────────────────────────────────────────────────────────────────┤
│  i  VOP cresceu 4,2% — drivers: Lucratti, Trade        +N       │  <- Z3 InsightStrip
├─────────────────────────────────────────────────────────────────┤
│  ┌──────┬──────┬──────┬──────┬──────┐                           │  <- Z4a KpiStrip
│  │ VOP  │ Taxa │Prazo │Prod. │Recei │  (modo leve, 5 tiles      │
│  │R$3,7M│ 1,8% │ 32d  │ LCT  │R$1,2M│   uniformes, +redundante  │
│  │+4,2% │+0,1% │ -1d  │ 38%  │+3,1% │   com Z4b abaixo)         │
│  └──────┴──────┴──────┴──────┴──────┘                           │
│                                                                 │
│  ┌─ VOP variance ──┬─ Receita variance ──┬─ Taxa PVM ─────┐    │  <- Z4b
│  │ [bridge chart] │ [bridge chart]      │ [pvm chart]   │    │
│  │  driver detail │  driver detail       │  mix vs intra │    │
│  ├────────────────┼──────────────────────┼───────────────┤    │
│  │ Prazo PVM      │ Mix dumbbell         │ Concentracao │    │
│  │ [pvm chart]    │ [dumbbell]           │  HHI delta   │    │
│  └────────────────┴──────────────────────┴───────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

Problema: **Z4a repete 4 dos 5 numeros que Z4b decompoe.**

### 7.2 Sob `DashboardBiAnalise` (proposto)

```
┌─────────────────────────────────────────────────────────────────┐
│  BI · Operacoes                          [DarkToggle][AI][...]  │
├─────────────────────────────────────────────────────────────────┤
│  [Mes corrente] Volume&Ritmo  Produtos  Receita  Cedentes       │  <- Z2 igual
│  Periodo: 12m  Produto: Todos  UA: Todas  ...  Atualizado       │
├─────────────────────────────────────────────────────────────────┤
│  i  VOP cresceu 4,2% — drivers: Lucratti, Trade        +N       │  <- Z3 igual
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────┐    │  <- Z4a NOVO
│  │ VOP cresceu 4,2% MTD (R$ 3,7 mi vs R$ 3,5 mi mes ant.), │    │     NarrativeBanner
│  │ puxado por Lucratti (+R$ 850k) e parcialmente compen-   │    │     (1 frase, 38px alt)
│  │ sado por queda em Trade (-R$ 320k).      [Por produto▾] │    │
│  └─────────────────────────────────────────────────────────┘    │
│                                                                 │
│  ┌─ VOP — R$ 3,7 mi · ↑4,2% MTD ──────┬─ Receita — R$ 1,2 mi ─┐│  <- Z4b
│  │                                    │  ↑ 3,1% MTD            ││     Hero Charts:
│  │  [variance bridge — area maior]    │  [variance bridge]     ││     KPI no titulo
│  │  drivers: Lucratti, Trade, ...     │  drivers: ...          ││     (4.3 + 4.4)
│  ├────────────────────────────────────┼────────────────────────┤│
│  │ Taxa media — 1,8% · ↑0,1pp MTD    │ Prazo medio — 32d ...  ││
│  │ [PVM mix vs intra]                │ [PVM mix vs intra]     ││
│  ├────────────────────────────────────┼────────────────────────┤│
│  │ Mix de produtos                    │ Concentracao HHI       ││
│  │ Lucratti 38% (era 32%) +6pp       │ HHI 0,42 · ↑0,03 MTD   ││
│  │ [dumbbell]                         │ [delta visual]         ││
│  └────────────────────────────────────┴────────────────────────┘│
│                                                                 │
│  Bitfin · atualizado as 14:32 · 12 DU efetivados de 21         │  <- Z5 igual
└─────────────────────────────────────────────────────────────────┘
```

### 7.3 Mudancas pontuais

1. **`<KpiStrip>` removido.** Os 5 KpiCards somem.
2. **`<NarrativeBanner sentence={data.narrative_sentence}>` adicionado** entre Z3 e Z4. Componente novo em `design-system/components/`. Backend ja serve a frase ([`AbaMesCorrente.tsx:253-254`](../frontend/src/app/(app)/bi/operacoes2/_components/AbaMesCorrente.tsx)).
3. **Cards da grid 2×3 ganham `bigNumber={...}` no header** do `<EChartsCard>` (refactor de prop, PR separado). Cada card vira Hero Chart com KPI no titulo.
4. **Numero de KPIs no header dos cards: ate 4 caracteres bold + delta**. Mais que isso, vira tile.
5. **In-Chart Annotation** opcional nos picos das bridges (driver dominante) — pode entrar no PR de `EChartsCard.bigNumber` ou em PR proprio.

### 7.4 Ganho mensuravel

- **~120px de altura economizados** (KpiStrip default) — sobe analise pra fold.
- **Eliminada redundancia textual** de 4 KPIs (VOP / Taxa / Prazo / Receita) que viviam em strip + bridges.
- **Densidade informacional aumenta** — 1 frase narrativa carrega 4 numeros + 2 drivers em ~140 chars.
- **Hierarquia preattentive explicita** (Knaflic 3.3) — KPI principal e o que ta no titulo do chart aberto, nao um de 5 tiles iguais.

---

## 8. Proximos passos (fora do escopo deste doc)

1. **Revisao + aprovacao deste doc pelo usuario.** Ratificar nome `DashboardBiAnalise` ou propor alternativa.
2. **PR — `<NarrativeBanner>`.** Componente novo em `design-system/components/`. Pequeno (~50 linhas + tokens). Pre-requisito do pattern.
3. **PR — `<EChartsCard>` aceita `bigNumber={...}` no header.** Refactor de prop. Permite Hero Chart com KPI no titulo. Pre-requisito do pattern.
4. **PR — `DashboardBiAnalise.tsx` em `design-system/patterns/`.** Copia de `DashboardBiPadrao.tsx` com Z4a trocado. Documentar regras 6.4 no header do arquivo.
5. **PR — migrar `bi/operacoes2/page.tsx` para o novo pattern.** Aplicar 7.3. Esta e a prova de conceito.
6. **PR — atualizar skill `audit-page-consistency`** ([`frontend/.claude/skills/audit-page-consistency`](../frontend/.claude/skills)) para reconhecer ambos os patterns e validar o criterio 6.4.
7. **PR — atualizar [`CLAUDE.md` §7](../CLAUDE.md)** listando o segundo pattern, o criterio 6.4, e o checklist de §18 (frontend) com a checagem "pagina nasce de qual pattern e por que".

---

## 9. Referencias

### Livros
- Stephen Few — *Information Dashboard Design* (2nd ed., 2013) — caps. 3, 4, 5
- Edward Tufte — *The Visual Display of Quantitative Information* (1983, reprint 2001) — cap. 4 ("Data-Ink")
- Edward Tufte — *Beautiful Evidence* (2006) — cap. 2 ("Sparklines")
- Cole Nussbaumer Knaflic — *Storytelling with Data* (2015) — caps. 4-6

### Design systems
- [IBM Carbon — Data Visualization](https://carbondesignsystem.com/data-visualization/dashboards/)
- [PatternFly — Dashboard Design Guidelines](https://www.patternfly.org/patterns/dashboard/design-guidelines/)
- [Atlassian Design System — Charts](https://atlassian.design/components/charts/) (consulta pendente)

### Catalogos / guias
- [FT Visual Vocabulary (PDF)](https://journalismcourses.org/wp-content/uploads/2020/07/Visual-vocabulary.pdf) · [GitHub repo](https://github.com/Financial-Times/chart-doctor/tree/main/visual-vocabulary)
- [Datawrapper — Dashboard Layout Patterns](https://www.datawirefra.me/blog/dashboard-layout-patterns)
- [Observable — Five techniques to improve chart annotations](https://observablehq.com/blog/five-techniques-to-improve-chart-annotations)
- [Tufte — Sparkline theory and practice](https://www.edwardtufte.com/notebook/sparkline-theory-and-practice-edward-tufte/)

### Produtos
- [Stripe Dashboard](https://docs.stripe.com/dashboard/basics)
- [Vercel Web Analytics](https://vercel.com/docs/analytics)
- [Koyfin Features](https://www.koyfin.com/features/)
- [Linear changelog](https://linear.app/changelog)

### Resumos e analises secundarias
- [Antonio Neto — Thirteen Common Mistakes (Few summary)](https://medium.com/@antonioneto_17307/thirteen-common-mistakes-in-dashboard-design-cc1a0dc07750)
- [Reading Graphics — Storytelling with Data summary](https://readingraphics.com/book-summary-storytelling-with-data/)
- [DataCamp — Effective Dashboard Design](https://www.datacamp.com/tutorial/dashboard-design-tutorial)
- [SimpleKPI — KPI Visualization Patterns](https://www.simplekpi.com/Resources/Dashboard-Charts-And-Graphs)
- [Art of Styleframe — Dashboard Design Patterns 2026](https://artofstyleframe.com/blog/dashboard-design-patterns-web-apps/)
