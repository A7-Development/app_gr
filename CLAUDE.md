# App GR -- Regras do Projeto

> Sistema de inteligencia de dados para FIDC (pt-BR). Monorepo com `frontend/` (Next.js 14 + Tremor Raw — entregue) e `backend/` (FastAPI + PostgreSQL, multi-tenant — em construcao). Este arquivo governa o comportamento do Claude Code em todas as sessoes deste repositorio.
>
> **Palavras-chave do sistema:** multi-tenant, adapter pattern por fonte de dados, modelo canonico entity-centric, DNA de auditabilidade (proveniencia + explicabilidade + versionamento), laboratorio de teses em dados historicos.

---

## 🔓 STATUS — MODO ITERACAO DE DESIGN ATIVO (2026-04-27 → ?)

> Sistema em alinhamento com handoffs Strata (bi-padrao, hero-split-auth, futuros). Durante este periodo as regras visuais abaixo estao **temporariamente suspensas** para liberar fidelidade pixel ao handoff sem brigar com tokens.
>
> **Regras suspensas:**
>
> 1. **Valores arbitrarios de Tailwind sao permitidos** em qualquer camada (`tremor/`, `charts/`, `design-system/*`, `app/<dominio>/*`, `surfaces/`):
>    - `text-[13px]`, `text-[18px]`, `p-[7px]`, `gap-[3px]`, `w-[180px]`, `h-[42px]`, etc.
>    - `rounded-[4px]`, `rounded-[2px]` fora da escala Tremor.
>    - Espacamentos e larguras especificas do handoff.
> 2. **Hex literals e `rgba(...)` em componentes / surfaces sao permitidos** alem dos que ja vivem em `tokens/`. Cor solta em codigo de UI nao reprova PR neste periodo.
> 3. **Inline styles `style={{...}}` sao permitidos** em qualquer camada quando o handoff exigir efeito que Tailwind nao resolve bem (gradientes complexos, positioning especifico, transformacoes pontuais).
> 4. **Cores Tailwind fora das categorias da §4 sao permitidas** (`orange-*`, `purple-*`, `yellow-*`, `stone-*`, `zinc-*`, `neutral-*`) quando vierem do handoff. Continuam como cor de DADOS apenas em chart series.
>
> **Liberdade explicita durante este modo (4 niveis de customizacao do Tremor):**
>
> Para nao haver duvida, durante a janela de iteracao voce TEM liberdade total para:
>
> 1. **Aplicar classes Tailwind ad-hoc na callsite** (qualquer pagina/componente):
>    valores arbitrarios (`h-[42px]`, `text-[13px]`, `p-[7px]`), hex literals
>    (`bg-[#0F1A2C]`), `style={{...}}`, e cores Tailwind fora da paleta canonica
>    (`orange-*`, `purple-*`, etc) — quando o handoff exigir. Coberto pelos
>    bullets 1-4 acima.
> 2. **Editar tokens em `frontend/src/design-system/tokens/*.ts`** (`colors`,
>    `spacing`, `radius`, `motion`, `card`, `table`, `typography`, etc).
>    Mudancas propagam para tudo que consome o token. **Esta e a forma
>    preferida** de mudanca sistemica de "cards padrao", "altura de header",
>    "raio default", "tipografia de cell", "duration de animacao".
> 3. **Editar `frontend/src/app/globals.css` `@theme`** para criar/alterar CSS
>    vars que viram utilities Tailwind v4 (`--color-brand-secondary`,
>    `--header-h`, novos keyframes, etc). Mudanca de paleta global e nova
>    utility nascem aqui.
> 4. **Criar wrappers customizados em `frontend/src/design-system/components/`**
>    embrulhando primitivos `tremor/*` ou `charts/*` com defaults proprios
>    (ex.: `<HeroCard>` = `<Card>` + gradiente + padding diferente; `<DenseDataTable>`
>    = `<DataTable>` com row height menor por padrao). Esta e exatamente a
>    camada de composicao do design system — feita pra isso.
>
> **O que continua bloqueado mesmo neste modo:**
>
> Editar diretamente `frontend/src/components/tremor/*.tsx` ou
> `frontend/src/components/charts/*.tsx` (camadas verbatim — fork do
> primitivo). Para customizacao de primitivo, **componha um wrapper na camada
> `design-system/components/`** (nivel 4 acima). Se voce ESTRITAMENTE precisa
> mexer no primitivo, pare e discuta antes — fork muda a relacao com o
> upstream Tremor (toda atualizacao Tremor passa a ser merge manual).
>
> **Regras que CONTINUAM em vigor (nao sao suspensas):**
>
> - §2 **stack obrigatoria** — sem novas libs sem autorizacao explicita do usuario.
> - §3 **arquitetura em 6 camadas** — `tremor/` continua nao-editavel, `surfaces/` continua sem importar de `components/dashboard`, etc.
> - §11.1 **enum de modulos fechado** — sem modulo novo sem autorizacao.
> - §11.3 **bounded contexts (backend)** — cross-import entre modulos so via `public.py`.
> - §11.6 **hierarquia 3 niveis** de navegacao (L1/L2/L3) — sidebar pode aninhar 1 nivel (L2 com children), nunca mais. Max 3 niveis logicos.
> - §10 **multi-tenant absoluto** (backend) — toda tabela tem `tenant_id`, toda query escopada.
> - §13 **adapter pattern** (backend).
> - §14 **proveniencia + auditabilidade** (DNA do sistema).
> - Idioma da UI em pt-BR, alias `@/*` nos imports, `cx()` em vez de `cn()`, icones Remix, fonte Inter.
>
> **Quando este modo se desliga:**
>
> Quando os handoffs principais (bi-padrao, listagens, formularios, surfaces de marca) tiverem suas implementacoes estabilizadas e visualmente aprovadas. No fim desta janela:
>
> 1. Auditoria automatica varre o codigo coletando todos os valores arbitrarios usados (`text-[Npx]`, `rounded-[Npx]`, hex literals, espacamentos especificos).
> 2. Valores recorrentes sao **promovidos a tokens nomeados** em `frontend/src/design-system/tokens/` + escala Tailwind config.
> 3. Codigo e refatorado para usar os tokens.
> 4. **Regras §4 e §5 voltam a vigorar com forca total**: zero magic numbers em codigo novo, zero hex solto fora de tokens.
> 5. Este banner e removido. CLAUDE.md volta ao estado restritivo, mas agora com vocabulario expandido.
>
> **Para Claude Code (qualquer sessao):** durante este modo, NAO bloqueie iteracao visual citando §4 ou §5. NAO sugira "promover a token agora" toda vez que vir uma classe arbitraria — isso vai ser feito em batch no fim. Foque em fidelidade ao handoff. As outras regras (especialmente §2, §3, §10-§14) continuam invioiaveis.

---

## 🎨 STATUS — MODO DESIGN EXPLORATORIO ATIVO (2026-05-11 → ?)

> Modo paralelo ao "MODO ITERACAO DE DESIGN" acima. O modo de iteracao trata de **polimento visual** (cores arbitrarias, magic numbers, inline styles para casar com handoff). Este trata de **inovacao estrutural** — vem como contrapeso a um efeito colateral percebido pelo Ricardo: o sistema de regras inteiro empurra Claude pra "buscar pattern existente" como reflexo primario, e isso castra propostas mais ousadas onde elas seriam bem-vindas.
>
> **Licenca explicita durante este modo:**
>
> 1. **Propor 2-3 alternativas de layout/UX/estrutura ANTES de aplicar pattern canonico.** Implementacao espera escolha do Ricardo. ASCII mock, bullets curtos com tradeoffs, referencias a produtos de mercado — tudo valido.
> 2. **Propor libs fora da §2** (sem implementar — Ricardo aprova ou recusa). Reduz o reflexo de "se nao esta na tabela, nao existe". Pra implementar, continua precisando do OK; pra **propor**, esta liberado.
> 3. **Propor componentes novos em `design-system/components/`** (nivel 4 da §1) sem precisar passar pela busca exaustiva em `tremor/`/upstream primeiro. Se for util, vira composite estavel; se nao, jogamos fora — mas a proposta nasce sem atrito.
> 4. **Usar paleta tailwind completa em propostas** (`orange-*`, `purple-*`, `teal-*`, etc) e gradientes/efeitos visuais arrojados em surfaces e hero zones. Promocao a token nomeado acontece pos-aprovacao, junto com a varredura da §4 quando o MODO ITERACAO DE DESIGN se desligar.
>
> ### Quando o modo esta ATIVO por default (Claude liga sozinho)
>
> - **Greenfield estrutural:** primeira pagina de um modulo novo (Risco, Credito quando comecou, futuro Laboratorio). Nao tem shorthand do dominio ainda — brainstorm e o caminho.
> - **Pattern canonico encaixa mal:** quando aplicar `ListagemComDrilldown` / `DashboardBiPadrao` forcaria 3+ comentarios `// MOTIVO:` ou esconderia a dimensao mais importante do dado.
> - **Estrutura de dado incomum:** rede de relacionamentos, sequencia de estados com bifurcacao, matriz NxM, timeline ramificada, dados multi-dimensionais que tabela+chart canonico nao expressam bem.
> - **Surfaces de marca:** login, splash, 404/500, onboarding, landing. "Voz" importa mais que consistencia transacional — e a §4.1/§4.2 ja libera paleta brand + tipografia hero ali.
> - **Hero zones de dashboard:** os blocos topo (Z1/Z2 do `DashboardBiPadrao`) sao onde diferenciacao agrega mais. Linha de baixo (KPIs, tabelas, ProvenanceFooter) segue pattern.
> - **Empty/error states ricos:** quando o vazio comunica algo de dominio (ex.: "fonte ainda nao configurada", "carteira ainda nao recebeu primeira sincronizacao") vs vazio mecanico ("sem resultados pra esse filtro").
>
> ### Quando Ricardo ATIVA explicitamente
>
> Palavras-trigger no chat: **"ousada"**, **"criativa"**, **"diferente"**, **"alternativa"**, **"outra forma"**, **"ta pobre"**, **"achatado"**, **"sem graca"**, **"me da 2-3 opcoes"**, **"modo exploratorio"**. Reclamacao sobre algo que Claude acabou de produzir tambem ativa ("isso ficou seco demais", "ta achatado").
>
> ### Quando o modo NAO esta ativo (segue regras duras §1-§7 normalmente)
>
> - Bug fix, refactor mecanico, rename, migration, edicao de copy/label/tooltip.
> - CRUD admin que e clone visual de outro CRUD admin ja em prod.
> - Sub-componente de pagina que ja segue pattern (ex.: nova tab dentro de pagina canonica como [`integracoes/catalogo/[source_type]`](frontend/src/app/(app)/integracoes/catalogo/[source_type]/page.tsx)).
> - Ricardo disse explicitamente "**faz igual a tela Y**" ou "**copia o pattern X**".
>
> ### Como Claude sinaliza ativacao
>
> Primeira linha da resposta: `**[exploratorio ON]**` + 2-3 alternativas em ASCII mock ou bullets curtos com tradeoffs claros (o que ganha, o que perde, referencia a produto/exemplo de mercado). Espera escolha antes de codar.
>
> ### Como Claude desliga
>
> Apos escolha do Ricardo, modo OFF na mesma resposta — implementacao volta a respeitar §7 (pattern canonico) e demais regras estruturais. Se a estrutura escolhida ficou util pra outras telas, Claude propoe promover a `design-system/patterns/` como pattern novo.
>
> ### O que continua INVIOLAVEL mesmo neste modo
>
> - §7 **patterns canonicos** continuam sendo a referencia obrigatoria — mesmo quando proponho alternativa, ela e comparada contra o pattern mais proximo no tradeoff que apresento.
> - §10 **multi-tenant absoluto** (backend) — toda tabela tem `tenant_id`, toda query escopada.
> - §11.3 **bounded contexts (backend)** — cross-import entre modulos so via `public.py`.
> - §13 **adapter pattern** (backend).
> - §14 **proveniencia + auditabilidade** (DNA do sistema).
> - Idioma da UI em pt-BR, alias `@/*` nos imports, `cx()` em vez de `cn()`, icones Remix, fonte Inter.
>
> ### Hook `audit-page-consistency`
>
> Enquanto este modo estiver ativo, o hook automatico `PostToolUse:Edit` que dispara a auditoria em todo edit em `(app)/` e `design-system/components/` esta **desligado**. A skill continua disponivel via invocacao manual (`/audit-page-consistency`) quando Ricardo quiser uma varredura.
>
> ### Quando este modo se desliga
>
> Quando o catalogo de patterns canonicos cobrir todos os tipos de pagina previstos no roadmap (BI, Controladoria, Risco, Credito, Laboratorio, Admin) e a busca por estrutura nova virar excecao rara. Ate la, **exploration e o default em situacoes greenfield**.
>
> **Para Claude Code (qualquer sessao):** durante este modo, NAO se autocensure citando §1/§2/§3/§4 ao propor estrutura. NAO caia direto em "qual pattern aplica?" sem antes considerar se a feature pede brainstorm. As regras estruturais (§7, §10, §11.3, §13, §14) continuam vinculantes — esse modo abre a fase de **proposta**, nao a de implementacao.

---

## 1. Palavra de ordem: **padrao e consistencia visual**

> ⚠️ **Modo Design Exploratorio ativo:** as regras desta secao valem na fase de **implementacao**. Na fase de **proposta** (greenfield, dado incomum, hero/surface, ou quando Ricardo sinalizar), Claude tem licenca pra propor 2-3 estruturas alternativas antes de cair na ordem de escolha abaixo. Ver banner no topo.

O sistema usa **Tremor Raw** como **ponto de partida** de design system. Ele cobre ~90% dos casos; quando cobrir, use verbatim.

> **Nada que nao esteja em `frontend/src/components/tremor/`, `frontend/src/components/charts/` ou `frontend/src/design-system/` pode aparecer na UI.**

Ordem de escolha quando for montar uma tela:

1. Existe em `tremor/` ou `charts/`? Use direto.
2. Existe no Tremor Raw upstream mas ainda nao foi copiado? Copie verbatim de https://tremor.so/docs e use.
3. Existe em `src/design-system/components/`? Use direto via barrel `@/design-system/components`.
4. Nao existe ainda? **Componha em `src/design-system/components/`** a partir de primitivos Tremor + Radix. Um componente novo e aceito se:
   - **(a)** Usa apenas tokens desta secao §4 (cores, tipografia, spacing, radius). Zero valor arbitrario.
   - **(b)** Reutiliza Radix UI quando houver equivalente (Dialog, Popover, Dropdown, Tooltip, etc) — nunca reimplementar a mecanica de acessibilidade.
   - **(c)** E documentado na rota `/design` (dev-only) com proposito + exemplo + quando usar/nao usar, antes de ir pra producao.
4. Se a proposta quebrar uma das 3 regras acima OU introduzir uma primitiva que o Tremor ja oferece com outro nome, **pare e discuta antes de escrever codigo.**

Tremor Raw e referencia, nao cela. Quando "fazer como o Tremor faz" conflitar com "resolver melhor o problema do usuario", vence o segundo — desde que (a), (b) e (c) sejam respeitados. Design system e vivo.

---

## 2. Stack obrigatoria (sem substituicoes)

> ⚠️ **Modo Design Exploratorio ativo:** Claude pode **propor** libs fora desta tabela quando uma alternativa for genuinamente melhor pro caso de uso. Implementar continua exigindo autorizacao explicita do Ricardo. Ver banner no topo.

| Area | Obrigatorio | Proibido |
|---|---|---|
| Framework | Next.js 14.2.x (App Router) | pages/ router, Remix, Vite |
| Design System | Tremor Raw | shadcn/ui, MUI, Chakra, Ant, Bootstrap, Mantine |
| Styling | Tailwind CSS v4 + tokens do Tremor | CSS-in-JS, styled-components, emotion, CSS modules |
| Utilitario de classes | `cx()` de `@/lib/utils` | `cn()`, `clsx()` direto, `classnames` |
| Variantes | `tailwind-variants` | `class-variance-authority`, objetos de variantes manuais |
| Icones | `@remixicon/react` (Ri*) | `lucide-react`, `react-icons`, `heroicons`, SVG ad-hoc |
| Fonte | `Inter` (via `next/font/google`, centralizada em `@/lib/fonts`; tema ECharts usa `interFontFamily` para o canvas) | GeistSans, Roboto, Arial, qualquer outra |
| Charts (core) | `src/components/charts/*` (Recharts por tras) | Nivo, Chart.js, Victory, Plotly |
| Charts (BI complexo) | ECharts **apenas** se o chart do Tremor nao suportar o caso | ECharts para qualquer chart que o Tremor ja tenha |
| Forms | `react-hook-form` + `zod` | Formik, uncontrolled manual |
| HTTP | `@tanstack/react-query` via `src/lib/api-client.ts` | fetch/axios direto em componentes |
| Estado global | `zustand` quando necessario | Redux, MobX, Recoil, Jotai |
| URL state | `nuqs` para search params tipados | qs, query-string, manipulacao manual de URLSearchParams |
| Datas | `date-fns` | moment, dayjs, luxon |
| Virtualizacao | `@tanstack/react-virtual` quando lista > ~100 itens | react-window, react-virtualized |
| Command palette | `cmdk` | reimplementacao manual de command menu |
| Primitivos Radix | `@radix-ui/react-avatar` e outros sem equivalente no Tremor | Radix cru para o que o Tremor ja cobre |
| Markdown (output IA) | `react-markdown` + `remark-gfm` — uso restrito a `<AIPanel />` e telas de auditoria de IA | uso de markdown em tabelas/forms regulares; renderizacao manual ad-hoc de markdown |
| LLM gateway (backend) | adapter proprio em `app/modules/integracoes/adapters/llm/<provider>/`; LiteLLM aceito por baixo se virar multi-provider real | chamadas diretas ao SDK do provider em codigo de dominio que NAO seja o adapter |
| PII redaction (backend) | regex CPF/CNPJ com check digit (MVP) → `presidio-analyzer` + `presidio-anonymizer` na Fase 2 | enviar payload bruto a LLM externo |
| Cache + rate limit (backend) | em-processo no MVP; Redis em Phase 2 (tenant token bucket multi-dim TPM/RPM/BRL/dia) | `threading.Timer`, sleeps, locks ad-hoc |
| Specialist agents / motor agentico (backend) | `anthropic >= 0.71` (SDK oficial Anthropic Messages API com tool use + prompt caching nativos). Mora HOJE em `app/shared/agents/runtime.py`; migra para `app/agentic/engine/runtime.py` quando o refator de §19 acontecer. | reimplementar tool loop a mao com httpx; usar subprocess do Claude Code CLI (quebra em `SelectorEventLoop` no Windows) |
| Playbook engine (backend) | Graph declarativo imutavel + variable bindings tipados — vive HOJE em `app/modules/credito/workflows/` (rebatizado de "workflow"), **promove a `app/agentic/playbooks/` como primitivo horizontal** (decisao 2026-05-20). Ver §19.10. | codigo imperativo passo-a-passo; reimplementar grafo a mao |
| Workflow / playbook visual editor (frontend) | `@xyflow/react` (React Flow v12+) — autorizado 2026-04-30. Usado pelo editor de playbooks (renderiza `StrataNode`, `AgentInputBindingsField`, chips de `producedVars`). | reimplementar canvas drag-and-drop manualmente; libs alternativas (rete, dagre standalone) |

Instalar qualquer biblioteca fora desta tabela exige autorizacao explicita do usuario no chat.

---

## 3. Arquitetura em 6 camadas (Strata Design System)

> ⚠️ **Modo Design Exploratorio ativo:** as camadas e regras de import permanecem vinculantes na **implementacao**. Na **fase de proposta**, Claude pode esbocar componentes novos em `design-system/components/` (nivel 4) sem precisar justificar com `// MOTIVO:` ou exaurir a busca em `tremor/`/upstream antes. Aprovacao final do Ricardo valida onde mora. Ver banner no topo.

```
src/components/tremor/             <- Primitivos Tremor Raw (verbatim da doc).
                                       Nao editar. Substitua apenas ao atualizar a versao upstream.

src/components/charts/             <- Charts do Tremor (verbatim). Mesma regra.

src/design-system/tokens/          <- Tokens TS espelhando CSS vars do globals.css.
                                       (colors, fonts, spacing, radius, motion, echarts-theme).
                                       Inclui paleta de marca Strata (navy, navy-dark, orange)
                                       e escala tipografica hero — uso restrito a surfaces/.

src/design-system/primitives/      <- Barrel re-exporta `tremor/*` + Sheet (right-side drawer).
                                       Ponto de entrada unico para primitivas.

src/design-system/components/      <- Componentes do Strata Design System (FIDC-domain).
                                       Strata canonicos: StatusPill, KpiStrip, FilterBar,
                                       DataTable, DataTableShell, DrillDownSheet,
                                       CommandPalette, EChartsCard, ApprovalQueueBadge, Sidebar,
                                       SegmentSwitch.
                                       A7 Credit composites: PageHeader, EmptyState, ErrorState,
                                       OriginDot, CompactSeriesTable, etc.
                                       USA apenas tremor/ + charts/ + tokens/, nunca Tailwind
                                       bruto de cor / Radix cru.

src/design-system/patterns/        <- Composicoes copy-paste-edit (DashboardOperacional,
                                       ListagemComDrilldown). Templates de pagina autenticada.

src/design-system/surfaces/        <- Superficies de marca (NAO sao dashboards).
                                       Login, splash, 404/500, marketing/landing publica.
                                       Templates: HeroSplitAuth (e futuros).
                                       Unica camada com permissao de usar paleta Strata
                                       (navy/navy-dark/orange), gradientes de marca, e
                                       inline styles para efeitos nao-expressaveis em Tailwind
                                       (radial-gradient multi-stop, SVG pattern fills) —
                                       sempre referenciando tokens, zero hex literal solto.

src/components/<dominio>/          <- Componentes amarrados a um dominio especifico
                                       (ex.: "bi", "contratos", "fornecedores").
                                       Compostos de design-system/ + tremor/ + charts/.
```

**Catalogo completo de componentes:** ver [`frontend/src/design-system/components/README.md`](frontend/src/design-system/components/README.md) — registro vivo dos 37 componentes (9 canonicos do handoff Strata + 28 A7 Credit composites como `PageHeader`, `ModuleSwitcher`, `AuthGuard`, `Breadcrumbs`, `OriginDot`, `FilterPill`, `CardMenu`, `CompactSeriesTable`, etc.). Antes de criar componente novo, consulte este catalogo — provavelmente ja existe.

**Imports permitidos por camada:**

- `tremor/` importa: `@/lib/utils`, `@/lib/chartUtils`, `@remixicon/react`, `tailwind-variants`, Radix UI (interno), Recharts (interno).
- `charts/` importa: o mesmo que `tremor/` + `react`.
- `design-system/tokens/` importa: nada externo (apenas `react` para hooks).
- `design-system/primitives/` importa: `@/components/tremor/*` + nova `Sheet.tsx`.
- `design-system/components/` importa: `@/components/tremor/*`, `@/components/charts/*`, `@/design-system/tokens/*`, `@/design-system/primitives/*`, `@/lib/*`, `@remixicon/react`, primitivos Radix **sem equivalente no Tremor** (ex.: `@radix-ui/react-avatar`, `@radix-ui/react-hover-card`), `cmdk`, `echarts-for-react`. **Proibido**: Radix para o que o Tremor ja cobre, Recharts direto, classes de cor Tailwind ad-hoc.
- `design-system/patterns/` importa: `@/design-system/components/*` + `@/design-system/tokens/*` + `@/components/tremor/*`. **Sao templates copiaveis** — escopo: composicao + dados de exemplo.
- `design-system/surfaces/` importa: `@/components/tremor/*` + `@/design-system/primitives/*` + `@/design-system/tokens/*` (incluindo `tokens.colors.brand` e `tokens.typography.hero`) + `@remixicon/react` + assets de marca (logo SVG). **Proibido**: importar de `@/design-system/components/*` (componentes de dashboard nao pertencem a superficie de marca), importar de `<dominio>/*`, hex literal solto fora de `tokens/`.
- `<dominio>/` importa: `@/design-system/*`, `@/components/tremor/*`, `@/components/charts/*`, hooks de dominio, types de dominio. **Nunca importa de outro dominio.**

**Barrel oficial:** `import { ... } from "@/design-system/components"` re-exporta tudo.

---

## 4. Tokens e cores

> ⚠️ **Modo Design Exploratorio ativo:** em propostas (especialmente hero zones, surfaces de marca, empty states ricos), Claude pode usar a paleta tailwind completa (`orange-*`, `purple-*`, `teal-*`, gradientes arrojados). Promocao a token nomeado acontece pos-aprovacao, em batch junto com a varredura do MODO ITERACAO DE DESIGN. Ver banner no topo.
>
> Esta secao continua governando codigo de **listagens/dashboards transacionais** ja estabelecidos — onde mudar cor a esmo confunde o usuario.

**Paleta Tremor — unicas cores brutas aceitas:**

| Categoria | Classes permitidas | Uso |
|---|---|---|
| Neutros | `gray-*` (todas as escalas + `dark:`, inclui `gray-925`) | textos, bordas, backgrounds, superficies |
| **Atencao / selecao** | `blue-*` (principalmente `blue-500` para bg/fill e `blue-600`/`blue-700` para texto em light; `blue-400`/`blue-500` em dark) | **chama os olhos do usuario** — estado ativo da sidebar, aba ativa (TabNavigation/Tabs), filtros com selecao aplicada (FilterPill, PeriodoPresets), botoes primary, focus rings (`focusInput`/`focusRing`), checkbox/radio/switch marcados, calendar selected, link "voltar/editar". **Nao** use como cor semantica de "sucesso/info" — para isso use `Badge variant`. |
| Destrutivo / erro | `red-*` (em qualquer escala + `dark:`) | ErrorState, Dialog destructive, Button destructive, validacao de form, toasts de erro |
| **Dados (chart)** — paleta A7 Credit | cores de `chartColors` em `@/lib/chartUtils`, na ordem canonica: `slate` → `sky` → `teal` → `emerald` → `amber` → `rose` → `violet` → `indigo`. `blue`/`gray`/`cyan`/`pink`/`lime`/`fuchsia` existem no dicionario mas **nao iteram no default** — use por override explicito. | **apenas em `src/components/charts/`** ou quando a cor vier dinamicamente de `getColorClassName()`. `slate` (1a serie) escolhido por ser azul-acinzentado de baixa saturacao — nao cansa durante horas de analise. |

**Proibido:**
- Valores arbitrarios de cor em **classes Tailwind**: `text-[#123abc]`, `bg-[rgb(...)]`, `border-[hsl(...)]`.
- **`slate-*` como cor de atencao/selecao** — use `blue-*`. `slate` e exclusivamente para dados de chart + neutros raros.
- **`blue-*` como cor de serie default em chart** — a 1a cor iteravel da paleta A7 e `slate`, nao `blue`. `blue` so como override explicito `<Chart colors={["blue"]}>`.
- Cores Tailwind fora das categorias acima: `orange-*`, `purple-*`, `yellow-*`, `stone-*`, `zinc-*`, `neutral-*`. (`teal`, `sky`, `rose`, `indigo`, `violet` estao liberadas **somente para series de chart**, via `chartUtils`.)
- Usar cores de dados (`emerald`, `teal`, `rose`, etc) como cor semantica geral fora de charts (ex.: `bg-emerald-500` em badge de "ativo" — use `Badge variant="success"` do Tremor).
- Gradientes manuais (`bg-gradient-to-*` com cores arbitrarias).

**Excecao explicita — ECharts option objects:** hex literals (`#3B82F6`, `#F59E0B`, `#10B981`, etc.) sao **permitidos** dentro de `EChartsOption` (em `series[].itemStyle.color`, `lineStyle.color`, `areaStyle.color.colorStops`, gradientes de eixo, etc.) porque Tailwind nao alcanca o renderer do canvas. Preferir, quando viavel, valores de `tokens.colors.chart` ou nomes Tremor mapeados — hex inline e aceitavel quando o tipo da `EChartsOption` exige string de cor.

**Dark mode:** sempre suportar. Usar as mesmas classes que o Tremor usa (`dark:bg-gray-950`, `dark:text-gray-50`, `dark:border-gray-800`). O `<html>` ja tem `dark:bg-gray-950` em `layout.tsx`.

**Espacamento, tipografia, radius:** herdar do Tremor. Sem classes magicas (`text-[13px]`, `p-[7px]`). Se precisar de um tamanho que o Tremor nao cobre, pare e discuta.

### 4.1 Tokens de marca Strata (escopo restrito a `surfaces/`)

A paleta institucional da marca (navy + laranja Strata) e **separada** da paleta de produto (gray/blue/red + chart). Ela vive em `tokens.colors.brand`:

| Token | Hex | Uso |
|---|---|---|
| `tokens.colors.brand.navy` | `#1B2B4B` | Hero zone (background base) |
| `tokens.colors.brand.navyDark` | `#050814` | Hero zone (gradient stop final) |
| `tokens.colors.brand.orange` | `#F05A28` | Logo Strata (StrataIcon), eyebrow de marca, glow do hero |
| `tokens.colors.brand.orangeLight` | `#FF7A4D` | Highlight de marca (hover/destaque) |
| `tokens.colors.brand.blue` | `#3B82F6` | CTA primario em superficie de marca (alinhado com `blue-500` do produto) |
| `tokens.colors.brand.blueHover` | `#2563EB` | Hover do CTA |

**Regras duras:**

1. **Brand tokens sao permitidos APENAS em `src/design-system/surfaces/*`** (login, splash, 404/500, marketing). Pagina autenticada (`src/app/(app)/*`) **nao pode** importar `tokens.colors.brand` — la vale a paleta da §4 acima.
2. **StrataIcon (logo SVG com hexagono laranja)** e a unica excecao: pode aparecer em qualquer superficie como elemento de marca (ex.: header sticky do app), porque suas cores ja vem hardcoded no SVG e nao se propagam pra Tailwind.
3. **Gradientes de marca permitidos** em `surfaces/` quando todos os stops sao `tokens.colors.brand.*` ou `gray-*`. Exemplos validos: `linear-gradient(135deg, brand.navy 0%, brand.navyDark 100%)`, `radial-gradient(... brand.orange/.18 ...)`. Continua proibido gradiente com `purple-*`, `orange-500` Tailwind ou hex solto.
4. **`brand.orange` e identidade, nao status.** Nao reutilize laranja Strata para significar "alerta", "pendente", "atrasado-60" — para isso use `tokens.colors.status.atrasado-60` ou `Badge variant="warning"`.

### 4.2 Tipografia hero (escopo restrito a `surfaces/`)

Escala separada da escala Tremor padrao, registrada em `tokens.typography.hero`:

| Token | Tamanho / peso / line-height / tracking | Uso |
|---|---|---|
| `hero.display` | 52px / 600 / 1.08 / -0.025em | Headline principal do hero (ex.: "Inteligencia de fundos creditorios.") |
| `hero.lede` | 17px / 400 / 1.65 / 0 | Subhead descritivo abaixo da headline |
| `hero.eyebrow` | 12px / 500 / 1 / 0.08em uppercase | Caption sob o wordmark ("FIDC ANALYTICS") |
| `hero.formTitle` | 26px / 700 / 1.2 / -0.02em | Titulo do form ("Acesse sua conta") |
| `hero.trust` | 11px / 500 / 1 / 0.02em | Selos de compliance ("CVM compliant", "ISO 27001") |
| `hero.wordmark` | 30px / 700 / 1 / -0.03em | Wordmark "Strata" no lockup |

Uso de `hero.*` fora de `surfaces/` e bloqueador de PR. Pagina autenticada continua na escala Tremor (`text-sm`, `text-base`, `text-xl`, etc).

---

## 5. Regras de codigo

- **Idioma da UI:** sempre pt-BR. Strings voltadas para usuario em pt-BR. Mensagens de erro tecnicas (console/dev) podem ser em ingles.
- **Imports:** usar sempre alias `@/*` (nunca `../../../`).
- **Componentes:** `function Component() { return (...) }` exportado. Props tipadas com `type`, nao `interface`, a menos que precise de extends.
- **`use client`** so quando necessario (interatividade, hooks de browser). Por padrao, Server Components.
- **Nenhum `any`** em codigo de dominio. Em codigo verbatim do Tremor, preservar com `// eslint-disable-next-line @typescript-eslint/no-explicit-any`.
- **Nada de inline styles** (`style={{...}}`) exceto quando:
  - O Tremor exige (ex.: `style={{ color }}` em cores dinamicas via paleta).
  - Codigo em `src/design-system/surfaces/*` precisa expressar efeito **nao representavel em Tailwind** (radial-gradient multi-stop, SVG pattern fills, layered backgrounds com positioning especifico). Mesmo nesse caso, **todo valor referencia tokens** — proibido hex literal solto. Ex.: `background: \`linear-gradient(135deg, ${tokens.colors.brand.navy}, ${tokens.colors.brand.navyDark})\``.
  - Cores, gradientes e tipografia dentro de `EChartsOption` (series, axis, tooltip). Tailwind nao chega no canvas do ECharts. Preferir `tokens.colors.chart`; hex inline aceitavel quando o tipo exige.

---

## 6. Formularios e tabelas

**Formularios** sempre compoem apenas primitivos `tremor/`: `Input`, `Select`, `Textarea`, `Checkbox`, `Switch`, `RadioGroup`, `Label`, `DatePicker`, `NumberInput` (via Input com `type="number"`).

- Validacao: `react-hook-form` + `zod`.
- Layout: a definir em `src/design-system/patterns/` quando surgir necessidade.
- Botoes: sempre `Button` do Tremor, nunca `<button>` cru.

**Tabelas:**
- **Listagens CRUD/admin** (Provedores, Usuarios, Etiquetas, Templates — pequenas a medias, ~5-200 rows) — usar **`<DataTableShell>`** em `src/design-system/components/DataTableShell/`. Encapsula `Card + FilterSearch + SegmentSwitch + counter + DataTable` num so componente. Garante layout/gap/ordem identicos entre paginas. Demo isolada: `/preview/data-table-shell`.
- **Transacionais grandes** (cessoes, cedentes, sacados — milhares de rows com filtros complexos) — usar `<DataTable>` direta em `src/design-system/components/DataTable/`. Virtualization automatica se rows > 100.
- **Series temporais FIDC** (PL, cotas, rentabilidade mes a mes) — usar `<CompactSeriesTable>` (Austin-style, density compact default).
- **Tabelas hierarquicas** (BalanceTable, etc — multi-nivel com expand) — `<DataTable>` direta + `enableExpanding`/`getSubRows`/`expandedColumnId`. Nao cabe no `<DataTableShell>`.
- **Tipografia + cores em CELL renderers**: SEMPRE via **`tableTokens.*`** de `@/design-system/tokens/table` — NUNCA `text-xs`, `text-sm`, `text-[Npx]`, `text-gray-XXX` literais inline. Excecao com `// MOTIVO:` no proprio cell. Tokens disponiveis: `cellText` (12px texto), `cellTextMono` (12px mono), `cellSecondary` (12px gray-500), `cellMuted` (12px placeholder), `cellStrong` (12px semibold), `cellNumber`/`cellNumberSecondary`/`cellNumberPositive`/`cellNumberNegative` (tabular-nums), `badge`/`badgeWithDot` (11px), `header` (10px eyebrow). Tudo 12px de base — cabe em row de density compact (h-8). **Texto principal em dark = `gray-100`, NAO `gray-50`.**
- **Bordas em `rowClassName` da DataTable**: use sempre `border-t-{color}` / `border-b-{color}` / `border-y-{color}` (forma com lado explicito) — NUNCA o shorthand `border-{color}`. O shorthand seta `border-color` nos 4 lados, sobrescrevendo a `border-bottom-color: gray-100` default que a DataTable aplica em todo `<tr>`. Resultado visual: linhas com `border-t border-gray-200` ficam parecendo "boxed" (borda tambem embaixo, na cor errada). Mesma regra para `subtotal`, `total`, `section` em tabelas hierarquicas.
- Nunca AG Grid, nunca data grid externo, nunca `Table` do Tremor cru em pagina (Tremor `Table` so como primitivo dentro de DataTable/CompactSeriesTable).

---

## 7. Paginas e rotas — Patterns canonicos e Surfaces

Toda **pagina autenticada** (`src/app/(app)/*`) **deve preferir** comecar de um dos patterns canonicos em `src/design-system/patterns/`:

- **DashboardBiPadrao** — Pagina canonica do BI (handoff bi-padrao 2026-04-26). 5 zonas: Z1 PageHeader (titulo + IA + acoes) · Z2 TabNavigation L3 · Z3 FilterBar sticky **(Card branco em faixa cinza-50 — anatomy igual `/credito/workflows`, ver §7.1)** · Z4 conteudo (InsightBar + KpiStrip 5 KPIs + grid 2/3+1/3 + grid 3-col + DataTable) · Z5 ProvenanceFooter. Lateral: AIPanel violeta in-layout + DrillDownSheet. Use para qualquer dashboard analitico (BI, Controladoria, Risco) que envolva KPIs + charts + tabela com drill-down.
- **DashboardOperacional** — PageHeader + FilterBar + KpiStrip (4 KPIs) + Grid 2×2 EChartsCards + DataTable de atividade recente. Use para dashboards mais simples sem AI panel (`/bi/operacoes` legado, telas operacionais).
- **ListagemComDrilldown** — PageHeader + FilterBar + DataTable + DrillDownSheet (URL-synced via `?selected=ID`). Use para listagem de **dados de dominio** (gerados pelo sistema): Cessoes, Cedentes, Sacados, Cobranca, Reconciliacao, Eventos. Drill-down abre painel rico (PropertyList + Tabs + Timeline + LinkedObjects).
- **ListagemCrudInline** — PageHeader (com botao "+ Novo") + Card { `<FilterSearch>` + `<SegmentSwitch>` + contador `X de Y` + DataTable } + DrillDownSheet de criar (`?action=new`) + DrillDownSheet de editar (`?selected=<id>`) + Dialog destrutivo (state local). Use para **gestao administrativa** de cadastros pequenos a medios (~5-200 rows) onde **cada entidade tem identidade tabular** (compara linha-a-linha) e criar/editar/excluir acontecem inline: credenciais de provedor LLM, usuarios do tenant, etiquetas, templates de regra, fornecedores. Filtros sao **client-side** ate ~200 rows (busca via `globalFilter` do TanStack + segments locais); acima disso, copy-paste-edit + adicione `<FilterChip>` por coluna; acima de 2000 rows, migre para server-side (paginacao + busca debounced). Primeira instancia em producao: [`/admin/ia/providers`](frontend/src/app/(app)/admin/ia/providers/page.tsx).
- **ListagemCrudCards** — PageHeader (`title` + `info` tooltip + `subtitle` eyebrow + botao "+ Novo") + Card { `<FilterSearch>` + `<SegmentSwitch>` + contador `X de Y` } + grid responsivo `1/2/3` colunas de `EntityCard` + DrillDownSheet de criar (`?action=new`) + (opcional) DrillDownSheet de editar (`?selected=<id>`, omita se edit redireciona pra outra rota) + Dialog destrutivo. Use para **gestao administrativa** onde **cada entidade tem identidade visual** (icone + titulo + descricao + metadata heterogeneo + badges + acoes) e cabe melhor em CARD do que em linha de tabela: workflows, agentes IA, dashboards salvos, conexoes externas, templates de extracao. Volume tipico < ~50 cards (~3 paginas de scroll); acima de 200 items considere migrar pra `ListagemCrudInline`. **EntityCard canonico**: `<Card>` com `<div className={cardTokens.body}>`, hover `border-blue-500`, layout em 3 linhas (avatar+badges+dropdown / titulo+descricao / metadata com `·`), DropdownMenu de acoes com `e.stopPropagation()` no trigger. Cor do avatar via tokens nomeados (ex.: `nodeCategoryTokens`) — proibido `bg-X-N` solto. Primeira instancia em producao: [`/credito/workflows`](frontend/src/app/(app)/credito/workflows/page.tsx).

Toda **pagina nao-autenticada / superficie de marca** (`src/app/(auth)/*`, `src/app/error.tsx`, `not-found.tsx`, futuras paginas publicas) nasce de um template em `src/design-system/surfaces/`:

- **HeroSplitAuth** — Layout 60/40 com hero zone (gradiente navy + glow laranja + pattern de linhas + logo + headline + trust signals) a esquerda e zona de form a direita. Use para `/login`, `/recover-password`, `/onboarding/welcome`.
- (futuros) `SplashScreen`, `ErrorPage404`, `ErrorPage500`, `MarketingHero`.

Patterns e surfaces sao **copy-paste-edit** — nao componentes black-box. Copie o pattern para a pasta da pagina, adapte titulo/copy/mocks/charts ao dominio. Os comentarios `HOW TO ADAPT:` no topo de cada arquivo guiam a customizacao. Pages que copiam um pattern e divergem do template sao esperadas, nao excecao.

**Header de dashboard — set canonico de acoes (handoff bi-padrao 2026-04-26):** toda pagina derivada de `DashboardBiPadrao` usa `<DashboardHeaderActions>` no slot `actions` do `<PageHeader>`. O composite renderiza, em ordem fixa: `[DarkToggle, Compartilhar, Exportar, Mais, IA]`. DarkToggle e IA sao sempre presentes; Share/Export/More sao omitidos quando o callback nao e passado. Substituir por `<Button>` solto ou conjunto custom de botoes e regressao — fecha a porta para que cada pagina invente seu proprio header. Para acoes secundarias (Copiar link, Duplicar, Imprimir, etc.), use o slot `more={[...]}`.

### 7.1 FilterBar (Z3) — anatomy canonica + controles

**Estrutura visual** (canonica 2026-06-02 — anatomy FLAT): a Z3 do `DashboardBiPadrao` (e tambem `DashboardOperacional` e `ListagemComDrilldown`) renderiza como **linha branca sticky com `border-b`** — chips direto sobre a linha, SEM Card-em-faixa-cinza. Mais leve; os filtros lem como parte da pagina e sobra respiro vertical pro conteudo:

- Linha sticky: `sticky top-0 z-10 -mx-6 px-6 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950` + `shadow-xs` quando scrolled (`scroll-shadow`). E o shadow que mascara o conteudo passando por baixo durante scroll (antes era a faixa cinza).
- Toolbar interna: `flex min-h-[52px] flex-wrap items-center gap-2 py-2.5`. Chips/controles direto, `extraActions` empurrados pra direita (`ml-auto`).

> **Decisao 2026-06-02 (Ricardo):** o flat — que ja era de-facto em `operacoes2/3/4` e `panorama` — virou o canonico dos dashboards BI; o antigo **Card branco em faixa cinza-50** (refinamento 2026-05-01, estilo `/credito/workflows`) foi **aposentado** para dashboards. O `<FilterBar>` component foi achatado, entao todas as paginas que o consomem (benchmark, pagamento-diario, integracoes/operacao) convergiram automaticamente. Listagens CRUD de cards (`/credito/workflows` etc.) podem manter o Card-em-faixa se fizer sentido pra aquele pattern — a regra flat vale para os **dashboards** (Bi/Operacional).

Implementacao oficial em [`src/design-system/components/FilterBar/index.tsx`](frontend/src/design-system/components/FilterBar/index.tsx). Nenhuma pagina deve recriar essa estrutura inline — composer com `<FilterBar>` + filhos canonicos. (Tech-debt conhecido: `operacoes2/3/4` e `panorama` ainda usam uma toolbar inline equivalente em vez do componente — visual ja identico; unificar pro componente e follow-up.)

**Altura canonica dos controles** = ~30px (alinhada com `HEADER_BTN_CLASS` do `DashboardHeaderActions`). Todos os controles do FilterBar (FilterChip, FilterSearch, RemovableChip, MoreFiltersButton, SavedViewsDropdown) usam `h-[30px] px-2.5 text-[13px]` explicito. Botoes do header tambem chegam em ~30px via `py-1 text-[13px]`. Esses dois valores (`h-[30px]`, `text-[13px]`) sao candidatos a token (`tokens.controls.height`/`text`) na varredura final do Modo Iteracao de Design — por enquanto continuam como arbitrary values padronizados.

**Per-element coloring em controles compostos** (regra dura): em controles com multiplos elementos visuais (ícone + label + valor + chevron, etc), aplique cor **por elemento**, nunca via `text-X` no `<button>`/`<div>` raiz. Razao: cor no elemento raiz se propaga por inheritance e achata a hierarquia visual (label e valor ficam mesma cor). Padrao canonico do FilterChip:

- Ícone inactive: `text-gray-500 dark:text-gray-400`; active: `text-blue-500`
- Label `text-[11px]`: `text-gray-500 dark:text-gray-400`
- Valor `font-medium`: `text-gray-900 dark:text-gray-50`; active: `text-blue-700 dark:text-blue-300`

Botoes que parecem chip (ex.: `MoreFiltersButton`, qualquer Popover trigger custom) tambem seguem essa anatomy — texto principal em `gray-900` (nao `gray-600`/`700`) para nao parecerem "menores" que os chips reais.

**Antipattern: button cru duplicando MoreFiltersButton.** Quando uma pagina precisa de um trigger "Mais filtros" wrapped num Popover (lista de dimensoes para adicionar), e tentador escrever um `<button>` cru — o `MoreFiltersButton` canonico hoje nao aceita `asChild` para Popover wrapping. Se for inevitavel duplicar, **espelhe a anatomy completa** (mesmas classes, mesmas cores per-element). Followup: estender `MoreFiltersButton` com suporte a `asChild` para fechar essa porta.

Antes de escrever uma `page.tsx` nova, pergunte:
- E pagina autenticada? Qual **pattern** aplica?
  - Dashboard com KPIs + IA → `DashboardBiPadrao`
  - Dashboard simples sem IA → `DashboardOperacional`
  - Listagem de dados de dominio (drill-down de leitura) → `ListagemComDrilldown`
  - Gestao administrativa CRUD com identidade tabular (linha-a-linha) → `ListagemCrudInline`
  - Gestao administrativa CRUD com identidade visual (icone + descricao rica) → `ListagemCrudCards`
- E pagina nao-autenticada / pagina de erro / landing? Qual **surface** aplica?

Se nenhum pattern atual couber, componha direto a partir de `design-system/components/` + `tremor/`. Se a estrutura for util a outras telas, **promova-a a pattern** (novo arquivo em `patterns/`) — patterns nascem de pages reais, nao de especulacao.

A rota `/design` (dev-only via `process.env.NODE_ENV !== "production"`) mostra todos os tokens, primitives, components, patterns **e surfaces** ao vivo. Util como referencia rapida.

### 7.2 Filtros globais em paginas BI (regra dura)

**Toda pagina derivada de `DashboardBiPadrao` (e tambem `DashboardOperacional`) tem um conjunto de filtros globais** na FilterBar (Z3) — periodo, UA, produto, focus, etc. **Esses filtros devem ser aplicados a 100% dos agregados da pagina** — KPIs, charts, tabelas, mini-charts dentro de cards, sparklines, breakdowns. Nao existe agregado "fora do escopo do filtro" numa pagina BI.

**Por que e regra dura:** quando dois cards lado-a-lado mostram numeros que representam a "mesma coisa" (ex.: VOP do mes corrente) mas um aplicou o filtro e o outro nao, o usuario perde a confianca em todos os numeros da pagina. Isso e bug funcional, nao polish — equivale a o sistema mentir.

**Como aplicar — frontend:**

1. Use o hook canonico `useBiFilters()` (em `src/lib/hooks/useBiFilters.ts`) que retorna `filtersWithFocus` ja consolidado.
2. **Toda** chamada `useQuery` da pagina inclui `filtersWithFocus` no `queryKey` E passa para o service no `queryFn`. Padrao:

   ```ts
   const { filtersWithFocus } = useBiFilters()
   const q = useQuery({
     queryKey: ["bi", "<dominio>", "<bundle>", filtersWithFocus],
     queryFn: () => biService.bundle(filtersWithFocus),
   })
   ```

3. Filtros LOCAIS (lentes dentro de um card — ex.: seletor de UA dentro do hero de evolucao) operam **client-side sobre dados ja filtrados** pelos globais. Nao podem "abrir" o escopo. Comentario obrigatorio na callsite explicando que e lente.

**Como aplicar — backend:**

1. **Toda** query de agregado em `app/modules/bi/services/*.py` passa pelo helper `_apply_filters(stmt, tenant_id=..., **filters)` (em `services/operacoes.py`). Sem excecao para "esse aqui e mini chart" / "esse aqui e quebra auxiliar" / "ja filtra por data". `_apply_filters` aplica `tenant_id`, `efetivada=true`, `data_de_efetivacao` IS NOT NULL, `periodo_inicio/fim` E `produto_sigla/ua_id/...`. Pular o helper = pular filtros do usuario.
2. Quando a janela de tempo do agregado **diverge** do `periodo_inicio/fim` da pagina (ex.: mini chart de mes corrente, sparkline 12M historico fixo, comparacao MTD do mes anterior), monte `*_filters = {**filters, "periodo_inicio": ..., "periodo_fim": ...}` e passe esse dict para `_apply_filters`. As janelas de data do `_apply_filters` aceitam override; os filtros de produto/UA/focus do usuario continuam aplicados.
3. **Helpers que nao recebem filtros sao bug.** Ja vimos em producao (corrigido em `_acumulado_dia_a_dia` em 2026-05-06): a funcao recebia `filters: dict[str, Any]` mas montava o WHERE manualmente sem usar — resultado: o mini chart "Mes corrente vs Anterior" do card Ritmo somava o VOP total da empresa, enquanto o `vop_acumulado` ao lado refletia o filtro. Numeros lado-a-lado na mesma card divergindo. Toda funcao que toca `Operacao` em service de BI **deve** receber `filters` e aplica-los — mesmo quando aparentemente "ja filtra por outra coisa".

**Em PR:** consumo de `Operacao` (ou warehouse derivado) em service de BI sem `_apply_filters` e bloqueador. Reviewer rejeita.

---

## 8. Skills do projeto

Em `frontend/.claude/skills/` vivem skills que automatizam o nascimento de novo codigo ja alinhado a estas regras. Use-as sempre que for criar:

- `create-list-page` — nova pagina de listagem
- `create-form-page` — nova pagina de formulario
- `create-detail-page` — nova pagina de detalhe
- `create-dashboard-page` — novo dashboard
- `create-component` — novo componente reutilizavel em `design-system/components/`
- `audit-page-consistency` — verificar se uma pagina segue as regras acima

Quando o usuario pedir "cria uma pagina de X" ou "audita a tela Y", prefira invocar a skill ao inves de escrever do zero.

---

## 9. Backend -- Visao geral

**Repo:** `C:\app_gr\backend\` (greenfield, em construcao)

**Relacao com `app_controladoria`:** O backend em `C:\app_controladoria\backend\` e **legado em producao na VM** e continua rodando em paralelo. Dele copiamos **seletivamente** (via copy-paste + refactor), nunca importamos como dependencia, nunca evoluimos. Modelos reaproveitados: `Tenant`, `User`, `Empresa`. Servicos reaproveitados: `auth_service`, `dre_calculo_*` (quando reativarmos contabilidade). Tudo o mais e desenho novo.

**Stack obrigatoria:**

| Area | Obrigatorio | Proibido |
|---|---|---|
| Framework | FastAPI (>= 0.115) | Flask, Django, Express |
| Python | 3.11+ | <= 3.10 |
| ORM | SQLAlchemy 2.0 async + asyncpg | SQLAlchemy sync, Tortoise, Django ORM |
| Schemas | Pydantic v2 | Pydantic v1, marshmallow |
| Banco | PostgreSQL 16 | MySQL, SQLite em prod |
| Migrations | Alembic (migration REAL, nao `create_all`) | `create_all` em startup, migrations manuais ad-hoc |
| Linter/formatter | Ruff | black standalone, flake8, pylint |
| Testes | pytest + pytest-asyncio + httpx | unittest manual |
| Task scheduling | APScheduler (MVP); Celery/Temporal (futuro) | threading.Timer ad-hoc |
| HTTP client | httpx (async) | requests |
| Logging | `structlog` ou `logging` com JSON formatter | `print()` |
| Secrets | `.env` em dev, env vars no systemd em prod | hard-coded |
| Deploy | systemd + uvicorn na VM (sem Docker) | Docker em prod |

Instalar qualquer biblioteca fora desta tabela exige autorizacao explicita.

---

## 10. Backend -- Multi-tenant (regra absoluta)

O GR e **multi-tenant desde o dia 1**, mesmo rodando com 1 tenant real no MVP.

**Regras duras:**

1. **Toda tabela de dominio tem `tenant_id` NOT NULL.** Excecoes: tabelas globais como `tenant` e `source_catalog`. Essas sao claramente marcadas em comentario.
2. **Nenhuma query sem escopo de tenant.** O escopo e aplicado via dependency/middleware (`get_current_tenant_id`), nao por dev lembrar de filtrar.
3. **Middleware central** extrai `tenant_id` do JWT e injeta no contexto da request. Repository/service recebe o `tenant_id` explicitamente — nunca pega de session/thread-local global.
4. **Testes de isolamento obrigatorios:** para cada modulo, testes que verificam que tenant A nao ve dado de tenant B.
5. **Tenant_id em TODO indice composto** onde faz sentido. Queries lentas por "esqueci o indice com tenant_id" sao bug.

**Modelo de multi-tenancy:** shared DB + `tenant_id` (opcao simples, suficiente ate N pequeno de tenants). Quando escala pedir, evoluimos para schema-per-tenant com zero refactor de codigo de dominio — o adapter de DB muda, o dominio nao.

---

## 11. Backend -- Modularizacao (bounded contexts)

O GR e **modular** em 4 dimensoes simultaneas (UI, codigo, permissao, licenciamento). Modularizacao e **estrutural**, aplicada desde o Sprint 1. Retrofit e caro.

### 11.1 Os 9 modulos oficiais (enum fechado)

| Modulo | Proposito |
|---|---|
| `bi` | Dashboards, analises, cruzamentos (MVP) |
| `cadastros` | Empresas, pessoas, cedentes, sacados |
| `operacoes` | Contratos, titulos, pagamentos, recebimentos |
| `credito` | Analise de credito, politicas, limites de cessao |
| `controladoria` | Contabilidade, plano de contas, DRE, balancete |
| `risco` | Scoring, limites, PDD, stress, concentracao |
| `integracoes` | Adapters, catalogo de fontes, sync, reconciliacao |
| `laboratorio` | Teses de dados, correlacoes, experimentos |
| `admin` | Tenants, users, roles, subscriptions, config sistemica |

Adicionar um decimo modulo exige **autorizacao explicita** + atualizacao deste documento + atualizacao do enum `Module` em `app/core/enums.py`.

**Agentes nao sao um decimo modulo.** Vivem em `app/agentic/` como **camada horizontal estrutural** — ver §19. O enum `Module` continua fechado em 9. Cada `AgentDefinition` / `PlaybookDefinition` / tool carrega `module: Module` como **tag** (RBAC, scope, billing, metricas agrupam por isso), nunca como pasta de modulo.

### 11.2 Estrutura fisica (bounded contexts)

```
app/
├── core/                 # cross-cutting absoluto (config, db, security, middlewares, enums)
├── shared/               # shared kernel
│   ├── auditable.py      # mixin
│   ├── audit_log/        # decision_log, premise_set
│   └── identity/         # Tenant, User, UserModulePermission, TenantModuleSubscription
├── modules/
│   ├── bi/
│   │   ├── public.py     # CONTRATO publico do modulo
│   │   ├── models/
│   │   ├── services/
│   │   ├── schemas/
│   │   └── api/
│   ├── cadastros/
│   ├── operacoes/
│   ├── credito/
│   ├── controladoria/
│   ├── risco/
│   ├── integracoes/
│   │   └── adapters/
│   │       └── erp/bitfin/
│   ├── laboratorio/
│   └── admin/
└── main.py
```

### 11.3 Regras de import (bounded contexts)

- Modulo X pode importar **livremente** de `app/core/` e `app/shared/`.
- Modulo X pode importar de modulo Y **somente** via `app/modules/Y/public.py`. Imports de internals de Y (`modules/Y/models/*`, `modules/Y/services/*`) sao **proibidos**.
- Cada modulo expoe em `public.py` APENAS o que e contrato estavel. Mudar `public.py` e mudanca de API — exige reflexao.
- Modulo nao deve depender de mais de 1-2 outros modulos. Se depender de 3+, provavelmente precisa de shared kernel ou event bus.
- **BI** le do `warehouse` (dado canonico), nao importa de outros modulos.
- **Integracoes** popula warehouse; outros modulos leem warehouse, nunca chamam integracoes.
- **Tools de modulo X invocadas por agente de modulo Y** vao via `ToolRegistry.get_available(scope)`, **nunca via import direto**. Modulo X nao precisa expor tools no seu `public.py` — o registry filtra dinamicamente por `ScopedContext(tenant, empresa, user, module, permissions)`. Mesma regra vale para playbooks invocados cross-modulo (via `PlaybookRegistry`). Ver §19.

### 11.4 Estrutura de rotas do frontend

```
src/app/
├── layout.tsx                # root layout (html, ThemeProvider, QueryProvider, Toaster)
├── globals.css               # tokens CSS vars + Tailwind directives
│
├── (app)/                    # route group AUTENTICADO — envolvido por <AuthGuard>
│   ├── layout.tsx            # AuthGuard + SidebarProvider + AppSidebar + header sticky
│   ├── page.tsx              # home global (atalhos por modulo)
│   ├── bi/...                # rota /bi (operacoes, benchmark, ...)
│   ├── cadastros/...         # rota /cadastros
│   ├── operacoes/...         # rota /operacoes (futuro)
│   ├── credito/...           # rota /credito (futuro)
│   ├── controladoria/...     # rota /controladoria (futuro)
│   ├── risco/...             # rota /risco (futuro)
│   ├── integracoes/...       # rota /integracoes (catalogo, sync)
│   ├── laboratorio/...       # rota /laboratorio (futuro)
│   └── admin/...             # rota /admin (futuro)
│
├── (auth)/                   # route group PUBLICO — sem AuthGuard
│   ├── layout.tsx            # layout minimo (centra o card de login)
│   └── login/page.tsx        # rota /login
│
├── design/                   # rota /design — Strata Design System ao vivo (dev-only via NODE_ENV)
└── preview/                  # rota /preview/* — paginas de preview/QA (gated em layout)
```

**Sobre route groups (`(app)`, `(auth)`):** convencao do Next 14 — diretorios entre parenteses **nao entram na URL**. `src/app/(auth)/login/page.tsx` serve a rota `/login`, nao `/(auth)/login`. Servem para agrupar rotas que compartilham layout (no caso, `(app)` envolve com `<AuthGuard>` + sidebar; `(auth)` deixa rotas publicas sem auth).

**Onde achar coisas comuns** (atalho para skills/agents):
- Login: [`src/app/(auth)/login/page.tsx`](frontend/src/app/(auth)/login/page.tsx)
- Sidebar: [`src/design-system/components/Sidebar/index.tsx`](frontend/src/design-system/components/Sidebar/index.tsx) — `<AppSidebar />` self-wired (le `usePathname` + `getActiveModule`)
- Module switcher: [`src/design-system/components/ModuleSwitcher.tsx`](frontend/src/design-system/components/ModuleSwitcher.tsx)
- Registro de modulos: [`src/lib/modules.ts`](frontend/src/lib/modules.ts) — `MODULES[]`, `MODULE_AVATAR_COLORS`, `getActiveModule()`, `getVisibleModules()`
- Breadcrumbs do header: [`src/design-system/components/Breadcrumbs.tsx`](frontend/src/design-system/components/Breadcrumbs.tsx) — `<HeaderBreadcrumbs />`, auto-gerado do `pathname`
- Auth guard: [`src/design-system/components/AuthGuard.tsx`](frontend/src/design-system/components/AuthGuard.tsx)
- Catalogo de componentes: [`src/design-system/components/README.md`](frontend/src/design-system/components/README.md)

Cada modulo pode ter seu proprio `layout.tsx` interno e submenus proprios.

### 11.5 Regras do frontend

- Sidebar: um modulo ativo por vez (selecionado via `ModuleSwitcher`), lista plana das secoes L2 abaixo.
- Um modulo desabilitado (subscription `enabled=false`) ou sem permissao do usuario (`permission=none`) **nao aparece na lista principal** do `ModuleSwitcher` e **nao e acessivel** por rota direta.
- Pode aparecer numa secao secundaria "Em breve" do `ModuleSwitcher` (estado disabled, item nao clicavel) — opcional, usado para sinalizar roadmap ao usuario sem dar acesso. Coerente com §11.6 regra 4.
- Breadcrumbs hierarquicos: `Modulo > Funcionalidade > Recurso`.
- Pagina do modulo X nunca importa componentes especificos de modulo Y. Componentes compartilhados ficam em `src/design-system/components/`.

### 11.6 Navegacao — hierarquia de 3 niveis (regra oficial)

Toda navegacao do sistema respeita **3 niveis, nunca 4**. Usa apenas primitivos Tremor existentes — zero padrao inventado.

| Nivel | Significado | Onde vive | Primitivo Tremor |
|---|---|---|---|
| **L1** | Modulo (um dos 9) | `ModuleSwitcher` no topo da sidebar (dropdown) | `DropdownMenu` |
| **L2** | Secao/funcionalidade do modulo. Pode aninhar **1 nivel** de sub-itens (parent + children) — ver regra 2 abaixo. | Sidebar do modulo ativo | `SidebarLink` + parent expansivel custom |
| **L3** | Abertura/drill-down/perspectiva | Tabs horizontais no topo da pagina | `TabNavigation` + `TabNavigationLink` |

**Exemplo canonico — modulo BI (lista plana):**

```
L1 (dropdown no topo): [BI ▾]
    L2 (sidebar): Operacoes   → /bi/operacoes      → L3 tabs: Visao geral | Por produto | ...
                  Carteira    → /bi/carteira       → L3 tabs: Total | Por produto | Por cedente | Aging
                  Fluxo caixa → /bi/fluxo-caixa    → L3 tabs: ...
                  Benchmark   → /bi/benchmark      → L3 tabs: Visao geral | PDD | Evolucao | Fundos
                                (dados publicos CVM FIDC — ver docs/integracao-cvm-fidc.md)
```

**Exemplo de L2 com aninhamento — modulo Controladoria:**

```
L1 (dropdown no topo): [Controladoria ▾]
    L2 (sidebar): Cota Sub          → /controladoria/cota-sub
                  Pagamento Diario  → /controladoria/pagamento-diario
                  ▾ Relatorios      ← parent expansivel (clicar so abre/fecha, nao navega)
                      Padronizados  → /controladoria/relatorios/padronizados  → L3 tabs: ...
                      Espelho Adm   → /controladoria/relatorios/espelho       → L3 tabs: ...
```

Sub-itens **sao L2 logicamente** — a numeracao L1/L2/L3 reflete tipos de navegacao, nao profundidade de UI. Aninhamento e sintatico; conceitualmente "Padronizados" e "Espelho Adm" continuam sendo destinos L2 do modulo.

**Regras duras:**

1. **Maximo 3 niveis.** Se surgir L4, o modulo precisa ser dividido OU aquilo vira filtro/modal/drawer — nunca 4o nivel de navegacao.
2. **Sidebar pode aninhar 1 nivel (max 2 niveis de UI).** Secao L2 pode ter `children: ModuleSection[]` que renderizam como sub-itens com expand/collapse. Aninhamento de 2+ niveis (filho-de-filho) e **proibido** — vira L3 na pagina (TabNavigation), filtro/drawer, ou divisao de modulo. Sub-itens **sao L2 logicamente** — a numeracao L1/L2/L3 reflete tipos de navegacao, nao profundidade de UI.
   - **Parent expansivel = expand-only.** Clicar no parent **nao navega** (so abre/fecha). O `href` do parent serve apenas como prefixo de active-state propagation (auto-expand quando filho casa com pathname) — nunca como destino de URL real. Quando nao houver landing util pro parent, a rota correspondente deve 404 (ou nao existir).
   - **Auto-expand on deep link / navegacao:** quando user entra direto numa URL filha (refresh, link compartilhado, navegacao externa), o parent abre automaticamente via `useEffect` reagindo a mudanca de pathname.
   - **Collapse manual persiste:** depois do parent ja aberto, user pode recolher mesmo com filho ativo. Auto-expand so re-dispara em mudanca de pathname — nao briga com a vontade do usuario.
   - **Modo collapsed (56px):** filhos nao aparecem. Parent vira link pro primeiro filho habilitado (fallback de discoverability), tooltip mostra o nome do parent. Esta e a unica situacao em que parent "navega" — divergencia consciente da regra expand-only justificada pela impossibilidade de mostrar filhos em 56px.
   - **Captions tipograficos sao permitidos:** se `ModuleSection.groupLabel` for definido, a sidebar renderiza o texto como separador visual antes do primeiro item do grupo (ex.: "OPERACAO", "FINANCEIRO"). Captions sao **apenas labels textuais nao clicaveis** — nao introduzem hierarquia, nao expandem/colapsam, nao alteram a contagem de niveis. Servem para densificar listas longas dentro de um modulo (ex.: BI agrupa "Visao geral / Operacao / Financeiro / Analise"). **Aninhamento e captions sao mecanicas complementares**, nao mutuamente exclusivas — escolha por intencao: caption para agrupar itens autonomos; nesting quando o parent representa um escopo natural (ex.: "Relatorios" engloba "Padronizados" e "Espelho Adm").
3. **URL e a fonte unica da verdade.** Modulo, secao, tab e filtros sao todos deep-linkaveis (ex.: `/bi/carteira?tab=por-produto&periodo=30d`). O modulo ativo e inferido do pathname.
4. **Troca entre modulos (L1) e SEMPRE pelo `ModuleSwitcher`** (dropdown no topo da sidebar). O switcher lista os modulos com subscription + permissao; demais ficam em "Em breve" (disabled). Sem icon rail, sem module picker separado do header, sem tabs de modulo.
5. **Breadcrumbs sticky no header** mostram o path: `Modulo > Secao > Pagina` (L1 > L2 > L3).

**Active state (implementacao):**

- L1 ativo: `ModuleSwitcher` exibe o modulo inferido de `getActiveModule(pathname)` (em `src/lib/modules.ts`) com avatar colorido + nome + permissao.
- L2 ativo: `SidebarLink` com `isActive={pathname.startsWith(section.href)}` — borda/texto azul via `data-active=true`.
- L2 aninhado: parent expande automaticamente quando algum filho casa com `pathname.startsWith(child.href)`. Estado de expansao em memoria (`expandedMap` em `AppSidebar`) — inicializado via `useState(() => ...)` no mount para evitar flash, re-aplicado via `useEffect` em mudancas de pathname/modulo.
- L3 ativo: `TabNavigationLink active={pathname includes tab}` ou comparacao com search param.

**Avatars de modulo — cor canonica (handoff v2, 2026-04-24):**

| Modulo | Token | Classe | Hex |
|---|---|---|---|
| BI | `gray` | `bg-gray-800` | `#1F2937` |
| Cadastros | `blue` | `bg-blue-500` | `#3B82F6` |
| Operacoes | `emerald` | `bg-emerald-500` | `#10B981` |
| Credito | `indigo` | `bg-indigo-500` | `#6366F1` |
| Controladoria | `teal` | `bg-teal-500` | `#14B8A6` |
| Risco | `amber` | `bg-amber-500` | `#F59E0B` |
| Integracoes | `red` | `bg-red-600` | `#DC2626` |
| Laboratorio | `violet` | `bg-violet-500` | `#8B5CF6` |
| Admin | `slate` | `bg-slate-600` | `#475569` |

**Regras:**
- Avatars sao tiles retangulares (`rounded-sm` = 2px) com iniciais de 2 letras. Estilo Linear/Notion — escolha deliberada pra separar "identidade de modulo" de "series de chart".
- Estas cores sao **exclusivas do avatar de modulo**. `blue` aqui NAO conflita com §4 (blue de atencao/selecao) porque aparece so no tile; botoes, abas, filtros continuam usando `blue-500` da §4 como antes.
- `red-600` em Integracoes e intencional (nao e "erro" — e identidade). Nao reutilize `red-*` para chips/badges que nao sejam destrutivos.
- BI ancorado em `gray-800` reflete que e o modulo "principal"/"neutro" do sistema (estilo Linear).

Qualquer outro uso de cor nessa escala dentro de componentes `app/` e proibido (exceto chart series). Ver `src/lib/modules.ts::MODULE_AVATAR_COLORS`.

---

## 12. Backend -- RBAC + Subscription por modulo

Acesso a cada modulo e controlado em duas camadas independentes:

1. **Subscription (tenant-level):** o tenant contratou/habilitou o modulo?
2. **Permission (user-level):** o usuario tem permissao dentro daquele modulo?

### 12.1 Enums centralizados

`app/core/enums.py`:
- `Module` — um valor por modulo: `BI`, `CADASTROS`, `OPERACOES`, `CREDITO`, `CONTROLADORIA`, `RISCO`, `INTEGRACOES`, `LABORATORIO`, `ADMIN`
- `Permission` — escala: `NONE`, `READ`, `WRITE`, `ADMIN` (ordem crescente)

### 12.2 Tabelas

```sql
-- shared/identity
tenant_module_subscription (
  tenant_id uuid FK,
  module Module,
  enabled bool,
  enabled_since timestamptz,
  enabled_until timestamptz null,
  plan_ref text null,
  PRIMARY KEY (tenant_id, module)
)

user_module_permission (
  user_id uuid FK,
  module Module,
  permission Permission,
  PRIMARY KEY (user_id, module)
)
```

### 12.3 Dependency obrigatoria em todo endpoint de modulo

```python
from app.core.module_guard import require_module
from app.core.enums import Module, Permission

@router.get("/api/v1/bi/receita")
async def receita(
    _: None = Depends(require_module(Module.BI, Permission.READ)),
    ...
):
    ...
```

`require_module`:
1. Verifica `tenant_module_subscription.enabled` → se `false`, HTTP 402 (Payment Required).
2. Verifica `user_module_permission.permission >= Permission exigida` → se nao, HTTP 403.

**Nenhum endpoint de modulo pode existir sem `require_module`.** Endpoints cross-cutting (auth, health, audit/ping) podem usar `require_authenticated` simples.

### 12.4 `/auth/me` e contrato com o frontend

Retorna:
```json
{
  "user": { "id": "...", "email": "...", "name": "..." },
  "tenant": { "id": "...", "slug": "...", "name": "..." },
  "enabled_modules": ["bi", "cadastros", "admin"],
  "user_permissions": {
    "bi": "admin",
    "cadastros": "write",
    "admin": "admin"
  }
}
```

Frontend usa `enabled_modules` + `user_permissions` para renderizar sidebar e esconder areas. Ainda assim, backend valida em toda request (defense in depth).

---

## 13. Backend -- Adapter pattern (fontes externas)

Fontes de dados externas (ERPs, admin APIs, bureaus, parsers de documento) **NUNCA** sao chamadas diretamente de servicos de dominio. Sempre atraves de adapters.

**Camadas:**

```
app/adapters/<tipo>/<nome>/
    __init__.py
    connection.py      # como abrir conexao / sessao
    queries.py         # queries/requests especificos da fonte
    mappers.py         # transforma dado da fonte para modelo canonico
    etl.py             # orquestra extract + transform + load
```

**Exemplos (plano):**
- `app/adapters/erp/bitfin/` — leitura SQL Server do Bitfin
- `app/adapters/admin/qitech/` — API QiTech (pos-MVP)
- `app/adapters/bureau/serasa_pj/` — Serasa PJ (Business Information Report — endpoint CNPJ)
- `app/adapters/bureau/serasa_pf/` — Serasa PF (Person Information Report — endpoint CPF)
- `app/adapters/document/nfe/` — parser XML de NFe (pos-MVP)

**Regras do adapter:**

1. **Um adapter por ENDPOINT/API, nao por provedor.** `serasa_pj` (Business Information Report, CNPJ) e `serasa_pf` (Person Information Report, CPF) sao adapters separados mesmo sendo ambos Serasa — endpoints distintos, schemas distintos.
2. **Versao embutida no adapter:** constante `ADAPTER_VERSION = "1.0.0"` registrada em toda linha ingerida (`ingested_by_version`).
3. **Output sempre em modelo canonico.** Adapter conhece a fonte e conhece o canonico; dominio nao conhece fontes.
4. **Config por tenant:** cada tenant tem seu registro de configuracao (connection string, credenciais, parametros) em tabela `tenant_source_config`. Adapter le config do tenant, nao ha hardcode.
5. **Proibido adapter em codigo de dominio.** Services de dominio leem APENAS do warehouse canonico.
6. **Observabilidade obrigatoria:** cada sync registra metricas (linhas lidas, tempo, erros) no `decision_log`.
7. **Custo + rate limit como metadados** em `source_catalog` quando fonte for paga (bureaus).

Adicionar uma fonte nova = novo adapter + registro em `source_catalog` + registro em `tenant_source_config`. **Zero refactor do core.**

### 13.1 Fontes externas federadas (postgres_fdw)

Nem toda fonte externa que popula o GR vira adapter no bounded context `integracoes`. Fontes **publicas** (sem `tenant_id`), com ciclo de ingestao proprio e volume significativo, podem viver em **DB separado no mesmo cluster Postgres** e serem lidas pelo `gr_db` via `postgres_fdw`.

**Criterios pra escolher esse padrao em vez de adapter interno:**

1. Dado e **publico** — sem escopo de tenant (ex.: CVM dados abertos, Receita Federal, Bacen)
2. Volume justifica DB dedicada — backup, vacuum e lifecycle desacoplados do `gr_db`
3. Pipeline de ingestao tem cadencia propria (cron mensal, por exemplo) nao acoplada ao trafego transacional do GR
4. Ciclo de dev / deploy da ingestao faz sentido ser independente (repo proprio, CI propria)

**Como funciona:**

- DB dedicada na mesma instancia Postgres da VM 27 (ver §17). Role dona da DB isolada.
- Repo de ETL separado, deploy independente (sem Docker — venv + pip + cron ou systemd).
- `gr_db` le via `CREATE EXTENSION postgres_fdw` + `CREATE SERVER` + `IMPORT FOREIGN SCHEMA <fonte> INTO <fonte>_remote`.
- Backend GR trata as foreign tables como locais, mas **anota no `decision_log`** `source_type='public:<fonte>'` sempre que calcular metrica derivada. Badge de proveniencia no frontend mostra a origem publica + competencia + versao do adapter que ingeriu (CLAUDE.md §14.5).
- **Nao duplicar dado** no `gr_db`. Se performance pedir, usar materialized view local OU indices no banco federado. Nunca copy-to-gr_db.

**O que NAO e fonte federada (continua sendo adapter em `modules/integracoes`):**

- Qualquer fonte com escopo de tenant (ERP, admin API, bureau pago por consulta)
- Fontes transacionais cuja sincronizacao dispara evento de dominio (recebimento, conciliacao)
- Fontes cuja config varia por tenant (credenciais, filtros, parametros)

**Primeiro exemplo em producao:** CVM FIDC (Informes Mensais, dados abertos). Detalhes completos em [`docs/integracao-cvm-fidc.md`](./docs/integracao-cvm-fidc.md) — arquitetura, schema, ponte FDW, consumo pelo modulo BI.

### 13.2 Camada raw (bronze) -> canonico (silver) -- regra geral

**Toda fonte externa transacional ingerida via adapter** (ERP, admin API, bureau pago, parser de documento) **deve gravar em duas camadas no warehouse**:

| Camada | Nome da tabela | Conteudo | Mutabilidade |
|---|---|---|---|
| **Raw (bronze)** | `wh_<vendor>_raw_<entidade>` | Payload cru em JSONB, exatamente como a fonte devolveu | Imutavel apos gravacao (upsert por idempotencia, mas nunca reescrita semantica) |
| **Canonico (silver)** | `wh_<entidade>` (sem prefixo de vendor) | Dado normalizado, schema independente da fonte, populado por mapper a partir da raw | Reescrito por re-mapeamento — proveniencia preservada via `Auditable` |

Raw nao usa `Auditable` — carrega proveniencia em colunas proprias (`fetched_at`, `fetched_by_version`, `payload_sha256`). Fluxo ETL, schema minimo e excecoes: ver `docs/WAREHOUSE_LAYERS.md`.

**Convencao de nomes:**
- Raw inclui o vendor: `wh_qitech_raw_outros_fundos`, `wh_serasa_pj_raw_pj_analitico`
- Canonico nao inclui vendor: `wh_posicao_cota_fundo`, `wh_titulo`

### 13.2.1 Regra de consumo — silver-only (REGRA DURA)

**Servicos de dominio, endpoints, jobs analiticos, hooks do frontend e relatorios consomem APENAS da camada silver (canonico).** A camada bronze e fonte para o ETL e para auditoria/replay — nao e API.

**Proibido em codigo de servico/dominio/UI:**
- `SELECT ... FROM wh_<vendor>_raw_*` em service de modulo
- `payload->'relatorios'->...` (parsing de JSONB raw fora do mapper) em qualquer camada que nao seja `app/modules/integracoes/adapters/<vendor>/mappers/`
- Endpoint que retorna estrutura derivada do raw sem passar pelo silver

**Quem pode tocar bronze:**
- `app/modules/integracoes/adapters/<vendor>/mappers/*.py` — leem raw, gravam silver
- `app/modules/integracoes/adapters/<vendor>/etl.py` — orquestra a leitura do raw
- Scripts de auditoria/replay em `backend/scripts/` — leitura ad-hoc, nunca em endpoint
- Migrations de remapeamento (Alembic) — quando a regra do mapper muda e precisa reprocessar

**Por que:** silver e o **contrato estavel**. Bronze e formato cru do fornecedor, muda quando o vendor muda a API, tem campos com nomes em portugues com acento, valores em cents/string mistos, layout instavel. Acoplar dominio ao raw acopla a feature ao vendor — quebra a abstracao do adapter.

**Quando o silver nao tem o campo necessario:**
1. **Nao leia do raw direto.** Adicione a coluna no modelo silver canonico.
2. Atualize o mapper do adapter para popular a nova coluna (a partir do raw).
3. Re-rode o ETL para repopular o silver historico.
4. So entao o servico/endpoint le o campo novo.

Re-mapeamento e barato (raw e imutavel, mapper e idempotente). Acoplar dominio ao raw e caro (refactor cascateia).

**Em PR:** consumo de raw fora dos mappers e bloqueador. Reviewer rejeita.

---

## 14. Backend -- Proveniencia e auditabilidade (DNA do sistema)

Em mercado financeiro regulado (CVM/ANBIMA/Bacen), **explicabilidade + rastreabilidade valem mais que sofisticacao**. Recomendacao sem trilha de auditoria nao passa em compliance. Isso nao e feature — e estrutural. Disciplina aplicada em TODAS as camadas desde o dia 1.

### 14.1 Modelo `Auditable` (mixin SQLAlchemy)

**Toda** tabela de dominio que armazena dado ingerido de fonte externa herda deste mixin. Campos obrigatorios:

> **Excecao:** tabelas raw (`wh_<vendor>_raw_*`, ver §13.2) **nao** usam `Auditable` — elas sao a fonte, nao referenciam outra fonte upstream. Raw carrega proveniencia em colunas dedicadas (`fetched_at`, `fetched_by_version`, `payload_sha256`).

| Campo | Tipo | Proposito |
|---|---|---|
| `source_type` | enum | "erp:bitfin", "admin:qitech", "bureau:serasa_pj", "bureau:serasa_pf", "self_declared", "peer_declared", "internal_note", "derived" |
| `source_id` | text | ID do registro na fonte original |
| `source_updated_at` | timestamp | Quando o dado foi atualizado na fonte |
| `ingested_at` | timestamp | Quando foi lido para o warehouse |
| `hash_origem` | text | SHA256 do payload bruto (deteccao de mudanca) |
| `ingested_by_version` | text | Versao do adapter que ingeriu (ex.: "bitfin_adapter_v1.0.0") |
| `trust_level` | enum | "high", "medium", "low" |
| `collected_by` | uuid nullable | Usuario que coletou (aplica a self_declared, peer_declared) |

### 14.2 Tabela `decision_log` (append-only)

Toda decisao/calculo/sync registrado aqui, particionado por tenant + data. **Append-only** — correcao e nova entrada que referencia a anterior. Campos completos: ver `docs/AUDITABILIDADE.md`.

### 14.3 Premissas, versionamento e explicabilidade

- **`premise_set`:** premissas de calculos (CDI, curva, cortes) vivem em tabelas versionadas, nunca em constantes. Cada edicao cria nova versao; projecao referencia o `premise_set_id` usado.
- **Versionamento de regras:** toda regra de negocio, formula ou modelo de score tem versao explicita. v2 coexiste com v1 — nao substitui.
- **Explicabilidade obrigatoria:** score, alerta ou recomendacao registra no `decision_log` os 3-5 fatores que geraram o output. Preferir modelos interpretaveis (regressao logistica, GBM + SHAP); se caixa-preta, registrar inputs + outputs + explicacao gerada.

### 14.5 Trust metadata visivel na UI

Frontend exibe:
- Badge `<DataOriginBadge />` ao lado de cada KPI/numero: tooltip/click abre proveniencia (source, timestamp, versao do adapter, trust level)
- Botao `<ShowPremisesButton />` em qualquer visual que mostre calculo/projecao: abre modal com premissas usadas
- Rodape de cada dashboard: "Dados sincronizados em XX/XX as HH:MM a partir de Bitfin"

### 14.6 Zero ocultacao na apresentacao — reconciliacao obrigatoria (regra dura)

> Decisao 2026-06-03 (Ricardo): nenhuma tabela, lista ou drill exibido ao usuario pode **excluir silenciosamente** linhas que um total/headline na mesma tela CONTA. Toda apresentacao de agregado **reconcilia on-screen**: a soma do que o usuario consegue alcancar = o total mostrado. Em mercado regulado (CVM/ANBIMA/Bacen), um numero que nao bate com o detalhe ao lado **destroi a confianca em TODOS os numeros da ferramenta** — e bug funcional de auditabilidade, nao polish. Origem: drill PDD escondia papeis com `|Δ|<R$100` (headline R$6.250,36 vs tabela R$6.155,02, gap R$95,34).

**Proibido (ocultacao silenciosa):**

1. **Corte por VALOR** (`threshold`, `|delta| > X`, `min_*`, `> _ALERTA_BRL`) que remove linhas da tabela enquanto o total/headline soma a populacao inteira. Os itens abaixo do corte somem da tabela mas contam no total -> nao reconcilia.
2. **Corte por QUANTIDADE** (`top_n`, `LIMIT`, `[:N]`, `.slice(0,N)`) **sem** que (a) TODO o restante seja alcancavel (expand/paginacao) OU (b) exista uma linha explicita **"Outros (N itens) · R$ X"** agregando a cauda.
3. **Contador maior que linhas alcancaveis:** expor `qtd_*` / `total_*` / `*_total_acima_threshold` MAIOR que o numero de linhas que o usuario consegue ver/alcancar. Contador > linhas-alcancaveis = o sistema mentindo sobre o universo.
4. **Default de endpoint que corta** (ex.: `top_n=20`, `threshold_brl=100`) quando o frontend nao sobrescreve. **Default = mostrar tudo** (`threshold=0`, `top_n` alto o suficiente p/ nao cortar na pratica, alinhado com o default do service/tool).

**Permitido (reconcilia — use estes padroes):**

- **Render progressivo:** `.slice(0,N)` com botao "Mostrar todos os N" que revela a lista inteira E rodape (footer) somando o array **completo**. Ex.: `DrillDcContent` aquisicoes/mutacao.
- **Virtualizacao** (`@tanstack/react-virtual`): janela renderizada, dataset completo, footer soma tudo.
- **Linha "Outros (N) · valor":** top-N nomeados + 1 linha sintetica agregando a cauda, de modo que a soma visivel = total. Ex.: `AbaVolumeRitmo` (padrao canonico).
- **Paginacao real:** lista com `total` / `page` / `page_size` expostos onde o usuario navega ate o resto (historicos: syncs, jobs, relatorios do catalogo). Nao e drill de reconciliacao.
- **Top-N rotulado SEM total conflitante:** chart "Top 5 setores" explicitamente rotulado, sem um total ao lado que os 5 nao expliquem. Se houver um total que a selecao nao soma, vira caso (b) — precisa de "Outros".

**Onde se aplica com forca total:** drills de decomposicao (cota-sub DC / PDD / CPR / Cotas / Origem / Contas a Pagar), conferencias e qualquer "headline + tabela que explica a headline". Ali a soma da(s) tabela(s) TEM que bater o headline (residuo ~0) — inclusive quando uma perna mora em tabela vizinha (ex.: WOP em `papeis_wop`): e o **conjunto** das tabelas exibidas que reconcilia, e a tela deve deixar isso explicito.

**Em PR (bloqueador):** lista/drill que corta por valor ou quantidade sem reconciliar (sem "Outros", sem expand-revela-tudo, ou com contador > linhas alcancaveis) e rejeitado. Endpoint que retorna `top_*`/array capado junto de um `*_total` maior, sem o frontend ter como alcancar o resto, idem. Reviewer rejeita.

---

## 15. Backend -- Regras de codigo

- **Idioma:** comentarios e docstrings em ingles (padrao python community). Strings voltadas para API/usuario em pt-BR quando aplicavel.
- **Imports:** absolutos (`from app.services import ...`). Nunca relativos profundos (`from ....`).
- **Type hints obrigatorios** em todas as funcoes publicas. `any` proibido.
- **Async por padrao.** Qualquer I/O (DB, HTTP, filesystem) em async. Lib sync (pyodbc) roda em thread pool.
- **Functions > classes.** Use classes para models ORM, Pydantic schemas, adapters. Logica de dominio preferencialmente em funcoes puras.
- **Sem `print`.** Sempre logger estruturado.
- **Zero dependencia de caminho absoluto.** Config via env var.
- **Um endpoint = um responsability.** Nao ha endpoint "generico" que faz varias coisas.

---

## 16. Backend -- Dev workflow e deploy

Local: `.venv` + `.env` + `gr_db_dev` + `uvicorn app.main:app --reload`. Prod: systemd + uvicorn em `/opt/app_gr/backend/`, database `gr_db`. Deploy: `git pull` + `pip install` + `alembic upgrade head` + `systemctl restart gr-api`. CI: GitHub Actions (lint + pytest). Ver `docs/DEV_WORKFLOW.md`.

---

## 17. Banco de dados -- arquitetura

**Mesmo servidor Postgres da VM, databases separadas:**

| Database | Proposito |
|---|---|
| `gr_db` | GR — novo, construido neste projeto |
| `cvm_benchmark` | Dados publicos CVM FIDC — populado pelo ETL externo `etl-cvm` (repo `A7-Development/etl-cvm`, VM 26), lido pelo `gr_db` via `postgres_fdw` sob schema `cvm_remote`. Ver [`docs/integracao-cvm-fidc.md`](./docs/integracao-cvm-fidc.md) e §13.1 |
| (database legada) | app_controladoria — producao, nao tocar |

- Zero acoplamento direto entre os dois. Se GR precisar ler dado do app_controladoria no futuro, usar `postgres_fdw` (foreign data wrapper).
- Backups independentes.
- Migrations independentes.
- Roles de usuario Postgres separados (user do GR so acessa `gr_db`).

---

## 18. Checklist antes de commitar

### Frontend (pagina autenticada — `src/app/(app)/*`)

- [ ] Usa apenas componentes de `tremor/`, `charts/`, `design-system/components/` ou do proprio dominio?
- [ ] Zero import de `@/design-system/surfaces/*` (surfaces sao para paginas nao-autenticadas)?
- [ ] Zero import de `tokens.colors.brand` ou `tokens.typography.hero`?
- [ ] Zero `import` de `lucide-react`, `shadcn`, `@mui`, etc?
- [ ] `cx()` e nao `cn()`?
- [ ] Icones sao `Ri*` de `@remixicon/react`?
- [ ] Zero cor arbitraria (`text-[#...]`, `bg-red-500` fora da paleta Tremor)?
- [ ] Dark mode testado?
- [ ] Strings de UI em pt-BR?
- [ ] **Pagina respeita regra de 3 niveis (L1 sidebar grupo / L2 sidebar sub-item / L3 TabNavigation)?**
- [ ] **Sidebar aninha no maximo 1 nivel (parent + children — sem filho-de-filho)? L3 vai pra TabNavigation na pagina, nunca como 2o nivel de nesting na sidebar?**
- [ ] **Estado de navegacao (modulo/secao/tab/filtros) e deep-linkavel via URL?**
- [ ] **Pagina nasce de um pattern canonico em `src/design-system/patterns/` (DashboardBiPadrao / DashboardOperacional / ListagemComDrilldown / ListagemCrudInline / ListagemCrudExpand / ListagemCrudCards) — divergencia tem `// MOTIVO:` no header do arquivo?**
- [ ] **Listagem CRUD/admin tabular usa `<DataTableShell>` (nao monta `Card + FilterSearch + DataTable` manual)?**
- [ ] **Listagem CRUD/admin visual (workflows, agentes, dashboards salvos) segue pattern `ListagemCrudCards` com `<EntityCard>` canonico (avatar via tokens nomeados, hover `border-blue-500`, DropdownMenu com `e.stopPropagation()`)?**
- [ ] **PageHeader usa `info` (tooltip) + `subtitle` (eyebrow "Modulo · Categoria") + `actions` — nao so `title`?**
- [ ] **Cells custom (inline ou em `_components/<X>Table.tsx`) usam `tableTokens.*` (nao escrevem `text-xs|sm|[Npx]` ou `text-gray-XXX` literais)?**
- [ ] **Fuga do `<DataTableShell>`, do pattern, ou de `tableTokens.*` tem comentario `// MOTIVO:` no caller?**
- [ ] **Zero ocultacao (§14.6): toda tabela/drill reconcilia com o total/headline da tela? Se corta com `.slice`/top-N, ou (a) tem expand "Mostrar todos" + footer somando o array inteiro, ou (b) linha explicita "Outros (N) · valor". Nenhum contador (`qtd_*`) maior que as linhas alcancaveis?**
- [ ] `npx tsc --noEmit` passa?
- [ ] `npm run build` passa?

### Frontend (superficie de marca — `src/app/(auth)/*`, `error.tsx`, `not-found.tsx`)

- [ ] Composta sobre um template de `src/design-system/surfaces/*` (ex.: `HeroSplitAuth`)?
- [ ] Cores da marca (`brand.navy`, `brand.navyDark`, `brand.orange`) vem de `tokens.colors.brand` — zero hex literal solto?
- [ ] Tipografia hero (`hero.display`, `hero.lede`, etc) vem de `tokens.typography.hero`?
- [ ] Inline styles sao usados **apenas** para efeitos nao-expressaveis em Tailwind (radial-gradient multi-stop, SVG pattern fills) e referenciam tokens?
- [ ] Form usa `react-hook-form` + `zod` e primitivos Tremor (`Input`, `Label`, `Button`, `Checkbox`)?
- [ ] Animacoes respeitam `prefers-reduced-motion: reduce`?
- [ ] Dark mode testado?
- [ ] `npx tsc --noEmit` passa?
- [ ] `npm run build` passa?

### Backend (endpoint/servico)

- [ ] Endpoint e autenticado via `Depends(get_current_user)` (ou explicitamente marcado como publico)?
- [ ] **Endpoint de modulo usa `require_module(Module.X, Permission.Y)` como dependency obrigatoria?**
- [ ] Query escopa por `tenant_id` automaticamente via middleware/dependency?
- [ ] Teste de isolamento de tenant existe?
- [ ] **Teste de regressao de permissao de modulo existe (user sem permissao recebe 403)?**
- [ ] Se cria dado no warehouse, aplica mixin `Auditable` com proveniencia completa?
- [ ] Se e decisao/calculo, registra no `decision_log`?
- [ ] **Servico/endpoint le APENAS de silver (`wh_<entidade>`), nunca de raw (`wh_<vendor>_raw_*`)?** Ver §13.2.1.
- [ ] **Se for service de pagina BI: TODA query de agregado (KPI, chart, mini-chart, sparkline, breakdown) passa por `_apply_filters(stmt, tenant_id=..., **filters)` — zero query montando o WHERE a mao?** Ver §7.2.
- [ ] **Zero ocultacao (§14.6): drill/decomposicao/listagem analitica nao corta linhas por valor (`threshold`) nem quantidade (`top_n`/`LIMIT`/`[:N]`) de forma que a lista nao some o total/headline retornado. Default de endpoint = mostrar tudo (`threshold=0`, `top_n` sem corte pratico). Nenhum `*_total`/`qtd_*` maior que as linhas que o cliente consegue alcancar.**
- [ ] **Import cruzado entre modulos so passa por `modules/Y/public.py`? Zero import de internals de outro modulo?**
- [ ] **Se introduziu modulo novo, atualizou enum `Module` + CLAUDE.md secao 11.1?**
- [ ] Type hints completos? Zero `any`?
- [ ] Novo secret em `.env.example` (sem valor)?
- [ ] Migration Alembic criada se alterou modelo?
- [ ] `ruff check` passa?
- [ ] `pytest` passa?

### Adapter novo

- [ ] Extende a interface base de adapter?
- [ ] Constante `ADAPTER_VERSION` definida e registrada?
- [ ] Output em modelo canonico?
- [ ] Config vindo de `tenant_source_config`, zero hardcode?
- [ ] Registra sync no `decision_log`?
- [ ] Registro correspondente adicionado em `source_catalog`?
- [ ] Teste de integracao com fonte (mock ou sandbox) existe?

### Endpoint / feature de IA / camada agentica (§19)

**Basico (todo endpoint de IA):**

- [ ] Endpoint sob `/api/v1/ai/*` usa `require_ai(AICapability.X)` (NAO `require_module`)?
- [ ] Endpoint admin global (gestao de keys, tier, prompts, agentes, playbooks) usa **`require_system_maintainer` + `require_module(Module.ADMIN, Permission.ADMIN)`** combinados?
- [ ] Toda chamada de IA grava em `decision_log` (via `services/audit.py`) e `ai_usage_event` (via `services/metering.py`)?
- [ ] Mensagem do usuario passa por `services/redaction.py` antes de subir ao LLM (CPF/CNPJ redactados)?
- [ ] Adapter LLM usado tem `ADAPTER_VERSION` e suas credenciais sao lidas de `ai_provider_credential` (cifradas via envelope Fernet)?
- [ ] Frontend chama via SSE com `fetch` + `ReadableStream` (nao `EventSource` -- nao passa Bearer token)?
- [ ] Markdown nas respostas IA renderiza via `react-markdown` + `remark-gfm` (nao texto plano)?
- [ ] Saldo de creditos exibido no frontend e via `<AIQuotaIndicator />` (nunca token-count cru)?

**Camada agentica — vocabulario canonico (§19.0):**

- [ ] **Vocabulario respeitado?** Codigo/tabela/endpoint/comentario usa `agents` / `tools` / `playbooks` / `memory` — NUNCA "skill" para playbook agentico (skill = comando Claude Code).
- [ ] **Cada bloco no lugar certo?** Agente em `app/agentic/agents/catalog/<modulo>_<agente>.py` (tag de modulo, nao pasta de modulo). Tool em `app/agentic/tools/<modulo>/`. Playbook em `app/agentic/playbooks/catalog/`. Memoria em `app/agentic/memory/`.

**Agente novo (§19.12):**

- [ ] `AgentDefinition` instanciada em `app/agentic/agents/catalog/` com `module: Module` como tag (nao pasta)?
- [ ] Seed em `agent_definition` + ativacao em `agent_definition_active` via migration?
- [ ] Persona reaproveitada de `agent_persona` (nao duplicar texto entre agentes do mesmo papel)?
- [ ] Prompt task em `ai_prompt` versionado (nome `<modulo>.<agente>`)?
- [ ] `allowed_tools` declarado (subset do registry filtrado por `module + shared`)?
- [ ] `output_schema` Pydantic class definido quando aplicavel (specialist agents validados)?
- [ ] `memory_scopes` declarado (`[SESSION, TENANT]` tipico; `GLOBAL` so com aprovacao juridica)?
- [ ] `cross_module=true` apenas com justificativa explicita + auditoria reforcada?

**Tool nova (§19.0):**

- [ ] Decorada com `@register_tool(module=Module.X, min_permission=Permission.Y, cost_hint=...)`?
- [ ] Mora em `app/agentic/tools/<modulo>/` (tool de dominio) ou `app/agentic/tools/shared/` (cross-modulo) — nao em modulo de negocio?
- [ ] Recebe `ScopedContext` como parametro (nao usa closure global para tenant/empresa/db)?
- [ ] Filtragem por modulo + permissao + tenant acontece automaticamente via registry (nao codada na tool)?
- [ ] Custom tool por tenant (futuro) registrada em `tenant_tool_registration` com `tenant_id NOT NULL`?

**Playbook novo (§19.10):**

- [ ] Declarativo (graph JSONB em `playbook_definition`), nao codigo imperativo?
- [ ] Versionamento + active pointer (`playbook_definition_active`) espelha `ai_prompt`?
- [ ] Tag `module: Module` no metadata (nao pasta)?
- [ ] Endpoint que dispara usa `POST /api/v1/playbooks/{name}/run` generico (nao endpoint per-modulo ad-hoc)?
- [ ] Dry-run testado via `POST /api/v1/playbooks/{id}/dry-run` antes de ativar versao nova?
- [ ] Validacao semantica (`/_validate`) passa sem erros?
- [ ] Cada execucao gera `playbook_run` + `playbook_run_step` + entrada em `decision_log`?

**Memoria (§19.11):**

- [ ] Invocacao de agente passa por `AnalysisSession` (working memory + step cache + step trace) — nunca single-shot fora de testes?
- [ ] Leitura de session/tenant memory **filtra por `tenant_id`** antes de qualquer outra operacao?
- [ ] Memoria de modulo X nao e visivel a agente de modulo Y sem `cross_module=true`?
- [ ] Trace de tool_use vai por SSE em tempo real (chat) ou para `agent_session_step` / `playbook_run_step` (batch)?
- [ ] Pgvector usado so com caso de uso concreto + tabela tem `embedding vector(1536)` declarado explicitamente?

**Cross-module (§11.3):**

- [ ] Tools de modulo X invocadas por agente de modulo Y vao via `ToolRegistry.get_available(scope)`, **nunca via import direto**?
- [ ] Mesma regra para playbooks invocados cross-modulo (via `PlaybookRegistry`)?

Se qualquer item reprovar, **nao corrija pontualmente** — pare e revise a mudanca inteira.

---

## 19. Camada agentica -- arquitetura horizontal estrutural

> Strata e plataforma agentica. A camada agentica — **motor + tools + playbooks + memoria + agentes** — e horizontal e atravessa todos os 9 modulos. Os modulos sao "pacotes de dominio" que registram tools e playbooks proprios; o motor de agente e unico. Telas e relatorios sao interfaces sobre o nucleo, nao o nucleo. Implementacao que parecer "modulo X com chatbot dentro" esta errada — pare e revise.
>
> Decisao 2026-04-30: IA tratada como capability transversal (nao decimo modulo) — mantem enum `Module` fechado (§11.1). Decisao 2026-05-20: a "capability IA" e reposicionada como **camada agentica estrutural** com vocabulario canonico (agents, tools, playbooks, memory) — ver §19.0.

### 19.0 Vocabulario canonico e blocos da camada agentica

Quatro blocos. Use **exatamente** esses termos em codigo, tabela, endpoint, doc e comentario. Implementacao que invente nome novo (ex.: "skill" para playbook, "ferramenta" para tool, "habilidade" para playbook) deve ser refeita.

| Bloco | Definicao | Onde mora |
|---|---|---|
| **Agents** | Motor de raciocinio com persona + politica + escopo. Cada agente carrega `module: Module` como tag (nao como pasta). | `app/agentic/agents/catalog/` (codigo) + `agent_definition` + `agent_definition_active` (DB) |
| **Tools** | Funcoes atomicas — queries SQL pre-produzidas, calculos, equacoes regulatorias, APIs externas (Serasa, Quod, BACEN), MCPs, geradores de relatorio | `app/agentic/tools/<modulo>/` com decorator `@register_tool(module=, min_permission=, cost_hint=)` |
| **Playbooks** | Workflows declarativos versionados (graph JSONB imutavel + `playbook_definition_active` apontando versao). Substitui o termo "skill" do mercado. | `app/agentic/playbooks/catalog/` (codigo de templates) + `playbook_definition` + `playbook_definition_active` (DB) |
| **Memory** | Tres camadas: **session** (curto prazo, durante 1 analise) + **tenant** (medio prazo, preferencias + padroes) + **global** anonimizada (longo prazo, **futuro** com parecer juridico) | `app/agentic/memory/` |

**Vocabulario duro:**

- "**Skill**" no projeto = comando Claude Code (audit-page-consistency, create-list-page, etc — invocado via `Skill` tool). **NAO usar "skill" para playbook agentico** — sempre **"playbook"**.
- "**Persona**" = papel de negocio reutilizavel ("Controller Senior", "Analista de Credito FIDC"). Vive em `agent_persona` separada de `ai_prompt` para reuso entre agentes.
- "**Tag de modulo**" em agente/playbook nao limita invocacao; define o **scope default** (RBAC + tools disponiveis + persona). Chamada cross-modulo e explicita (`cross_module=true` + auditoria).

**Principio chave:** o motor nao conhece os agentes nem as tools. Em runtime, recebe `AgentDefinition` + `ScopedContext(tenant, empresa, user, module, permissions, db)` + objetivo, executa. Adicionar agente/tool/playbook novo = arquivo + seed em DB. **Zero mudanca no engine.**

### 19.1 Estrutura paralela ao modulo

- **`tenant_ai_subscription`** -- entitlement do tenant (enabled, plan_ref, monthly_credit_quota, hard_cap_brl). Espelha `tenant_module_subscription`.
- **`user_ai_permission`** -- permissao do user (NONE/READ/WRITE/ADMIN via enum `AICapability`). Espelha `user_module_permission`.
- **`require_ai(AICapability.X)`** em `app/core/ai_guard.py` -- guarda paralelo ao `require_module`. Aplica em endpoints sob `/api/v1/ai/*`.
- **`require_system_maintainer()`** em `app/core/system_maintainer_guard.py` -- gating de endpoints globais (gestao de keys + tier de tenants + prompt library). Compoe com `require_module(Module.ADMIN, Permission.ADMIN)`.

### 19.2 Tabela `tenants.is_system_maintainer` (excecao §10)

Coluna boolean com **partial unique index** garantindo no maximo 1 tenant marcado. Apenas membros desse tenant podem editar credenciais globais (`ai_provider_credential`) e gerir tier dos demais tenants. **Nao** confunda com role admin do proprio tenant.

### 19.3 Adapter LLM (segue §13)

Provedores externos (Anthropic, OpenAI) sao adapters versionados em `app/modules/integracoes/adapters/llm/<provider>/`, cada um com seu `ADAPTER_VERSION`. **Credenciais sao globais** (tabela `ai_provider_credential`, sem `tenant_id`) e cifradas com envelope Fernet (`app.shared.crypto`). ZDR contratado e exigido em prod (coluna `zdr_enabled` bloqueia chamada quando false em ambiente de producao).

> **Plano de migracao**: os adapters LLM migram de `app/modules/integracoes/adapters/llm/` para `app/agentic/engine/llm/` quando o refator do §19 acontecer (junto com `runtime.py` → `app/agentic/engine/`). LLM e infra estrutural do motor agentico — encaixa melhor sob `app/agentic/` que sob "integracoes" (que e dominio: ERPs, bureaus, ETL). Manter agnostico continua sendo principio nao-negociavel.

**Dois caminhos de invocacao Anthropic** (escolha por caso de uso):

1. **Cliente HTTP custom** em `adapters/llm/anthropic/` (httpx + SSE puro). Usado em **chat simples** (`AIPanel`, insights) onde streaming linha-a-linha vai pro frontend via SSE proprio. Tem prompt caching via `cache_control` em system blocks.
2. **SDK oficial `anthropic`** (`anthropic >= 0.71`) usado em `app/shared/agents/runtime.py` para **specialist agents** que precisam de tool use nativo + tool execution loop + prompt caching de system prompts compartilhados entre runs. Migracao decidida em 2026-05-02 — substituiu `claude-agent-sdk` (que era subprocess do Claude Code CLI e quebrava no Windows com `SelectorEventLoop`). Tools sao definidas como `AgentTool` (`app/shared/agents/tools/_base.py`) com JSON schema + handler async; runtime monta `tools=[...]` para o Messages API e roda o loop `tool_use → tool_result` ate `end_turn` (cap em `_MAX_TOOL_ITERATIONS=12`).

Ambos os caminhos usam o **mesmo storage de credencial** (`get_active_anthropic_credential`) e gravam em `decision_log` + `ai_usage_event` com cache_read e cache_creation tokens separados.

### 19.4 Prompt library versionada (DB-backed)

**Decisao 2026-04-30:** prompts saem do codigo e passam a viver em DB para curadoria continua sem deploy. Time de produto/IA pode iterar sem PR; rollback de 1 click.

- **Storage**: tabela `ai_prompt` (id, name, version, system_text, user_context_template, assistant_prime, model, fallback_model, temperature, max_tokens, cache_strategy, description, created_by, created_at, archived_at). Naming: `<categoria>.<nome>` (ex.: `chat.fidc_geral`, `insight.carteira_3bullets`).
- **Imutabilidade**: `(name, version)` UNIQUE. Toda edicao **cria nova versao** copiando a base + patches. Versao base nunca muda — preserva audit trail.
- **Versao ativa**: tabela `ai_prompt_active` (uma linha por nome) aponta para a versao em producao. Trocar = 1 UPDATE (rollback de 1 click sem deploy).
- **Soft-delete**: `archived_at` marca versao como nao-ativavel. Versao ativa nao pode ser arquivada (constraint).
- **Repository**: `app/shared/ai/prompts/repository.py::resolve(db, name, version="active")` retorna `Prompt` instanciado a partir da row. Servicos chamam APENAS via repository — nunca leem `ai_prompt` direto.
- **Edicao**: via `/admin/ia/prompts` (system maintainer only — `require_system_maintainer` + `require_module(ADMIN, ADMIN)`). Endpoints: GET (list), GET /{id}, POST (cria nova familia=v1), PUT /{id} (cria nova versao), PUT /{name}/active (ativa versao), POST /{id}/archive (soft-delete), POST /{id}/preview (render sem chamar LLM).
- **Variaveis**: `user_context_template` e `assistant_prime` aceitam `{nome}` via Python `str.format`. Variaveis ausentes em `context` retornam erro 400 no preview.
- **Auditoria**: a versao usada vai automaticamente em `decision_log.rule_or_model_version` (`<adapter_version>+<prompt.full_id>`) e em `ai_usage_event.prompt_template_version`.

Migration que seedou os 4 prompts iniciais (`chat.fidc_geral@v1`, `insight.carteira_3bullets@v1`, `system.prompt_injection_detector@v1`, `summary.conversation_compact@v1`): `7c2dffe119a4_ai_prompt_db_managed.py`.

### 19.5 Auditabilidade reusa `decision_log`

Toda chamada de IA grava entrada com:
- `decision_type = RECOMMENDATION`
- `rule_or_model = <model_id>` (ex.: `claude-opus-4-7`)
- `rule_or_model_version = <adapter_version>+<prompt_full_id>` (ex.: `anthropic_adapter_v1.0.0+chat.fidc_geral@v1`)
- `inputs_ref = {conversation_id, user_message_id, page, period, filters, redacted}`
- `output = {text_redacted, stop_reason, tokens}`

Sem tabela de audit nova. Tudo encaixa nativamente.

### 19.6 Multi-turn server-side

Historico em `ai_conversation` + `ai_message` (com `text_redacted` + `text_encrypted` para retencao 7 anos). Sumarizacao automatica em `ai_conversation_summary` quando `turn_count` excede o limite (default 20). Cache breakpoint apos `system` block para maximizar prompt caching cross-tenant (Anthropic).

### 19.7 Frontend

- **Single entry point**: `<AIPanel />` em `design-system/components/AIPanel/` (drawer violeta in-layout, atalho Cmd/Ctrl+I, mantido pelo handoff bi-padrao). Markdown nas respostas via `react-markdown` + `remark-gfm`.
- **Hooks**: `useAIChat`, `useAIInsights`, `useAIQuota`, `useAIConversations` em `src/lib/hooks/ai.ts`. SSE via `fetch` + `ReadableStream` (NAO `EventSource` -- nao passa Bearer token).
- **Quota**: `<AIQuotaIndicator />` em `design-system/components/AIQuotaIndicator/` (variant `compact` no header da pagina, `strip` dentro do AIPanel). Cor amber em 75%, red em 90%.
- **Admin**: rotas em `/admin/ia/{providers,subscriptions,prompts,usage,conversations}`. Visiveis somente quando `tenant.is_system_maintainer === true` (campo em `/auth/me`).

### 19.8 Billing (creditos abstraidos)

UI nunca expoe token-count -- expoe **creditos**. 1 chat ~= `tokens_input/1000 + tokens_output/100` creditos; 1 insight = 5 creditos (flat); 1 prompt-injection check = 1 credito. Tier mensal incluso em `monthly_credit_quota`; overage em `topup` (pre-pago avulso). Hard cap diario em BRL via `tenant_ai_subscription.hard_cap_brl`.

### 19.9 LGPD / dados pessoais

PII (CPF, CNPJ, conta-agencia, email) e redactada antes de subir ao LLM via `services/redaction.py` (regex + check digit no MVP, Microsoft Presidio na Fase 2). Mensagens armazenam `text_redacted` + `text_encrypted` (versao com PII original cifrada via envelope Fernet, acesso restrito a auditoria com trilha em `decision_log`).

### 19.10 Playbooks (workflows declarativos)

**Decisao 2026-05-20:** o "workflow builder" que vive em `app/modules/credito/workflows/` e a implementacao atual do conceito **playbook** e sera promovida a **primitivo horizontal em `app/agentic/playbooks/`**. Cada modulo registra seus templates; o engine de playbook e unico.

**Vocabulario:** "playbook" (NAO "skill" — ver §19.0). "Workflow" continua valido como sinonimo informal quando se discute editor visual (`@xyflow/react`), mas em codigo, tabela, endpoint, doc — **sempre playbook**.

**Modelagem:**

- **`playbook_definition`** (rebatizada de `workflow_definition`): id, name, version, module, tenant_id NULL=global, graph JSONB (nodes + edges + variable bindings), created_by, created_at, archived_at. `(name, version)` UNIQUE. Imutavel — toda edicao cria nova versao.
- **`playbook_definition_active`**: uma linha por `(tenant_id, name)`, FK para `playbook_definition_id`. Rollback de 1 click sem deploy (espelha `ai_prompt_active`).
- **Tipos de node** ja existentes (a migrar): `specialist_agent`, `bureau_query`, `consolidator`, `join` (fan-in com `join_mode=all|any`), `conditional_branch`, `human_input`, `sub_playbook` (pendente, ex-`sub_workflow`).
- **Edges** com `condition` opcional via template (`{{node.X.output.value}} >= 700`).
- **Input bindings** tipados: `config.input_bindings = {slot_name: "node.X.output.Y"}` resolvidos via template resolver em `_render_context_for_prompt`.
- **Imutabilidade + versionamento**: graph JSONB imutavel; modulo edita = nova versao. Active pointer troca em 1 UPDATE.

**Engine:**

- Endpoint generico **`POST /api/v1/playbooks/{name}/run`** substitui endpoints per-modulo. Modulo informa via `module: Module` na URL ou body (ainda a definir).
- Engine resolve `playbook_definition_active.{tenant, name}`, instancia nodes, invoca cada um com `NodeContext` (tenant_id, empresa_id, trigger_data, previous_outputs).
- `specialist_agent` node chama `runtime.run_specialist_agent(spec, ctx, db)` (motor unico do §19.3).
- Cada execucao gera `playbook_run` (estado) + `playbook_run_step` (trace per-node) + entrada em `decision_log` + serie de `ai_usage_event`.

**Dry-run:** **`POST /api/v1/playbooks/{id}/dry-run`** executa em sandbox com mocks (sem DB write, sem API paga). Usado pelo editor visual antes de ativar versao nova.

**Validacao semantica:** **`POST /api/v1/playbooks/_validate`** retorna lista de erros + `produced_by_node` (variaveis que cada node publica). Frontend `StrataNode` consome para renderizar chips de `producedVars` e alimentar o picker do `AgentInputBindingsField`.

**Custom playbooks por tenant:** linhas com `tenant_id NOT NULL` em `playbook_definition`. Globais = `tenant_id IS NULL`. Marketplace/upsell (§9 da filosofia agentica) nasce naturalmente desse modelo.

**Quando NAO usar playbook:** chat conversacional simples (sem orquestracao) — usa motor de agente direto com `playbook=None`. Insight pontual (1 tool call + sintese) — mesma coisa. Playbook e para **orquestracao multi-step com grafo**, nao para qualquer chamada de IA.

### 19.11 Memoria de sessao (bloqueador atual)

**Estado: a implementar.** Hoje cada `run_specialist_agent()` e **single-shot** — sem memoria entre invocacoes. Isso impede casos como "analisar exposicao top-5 cedentes" (cedente A precisa lembrar enquanto investiga B-E e cruzar tudo na sintese). **Sem memoria de sessao, agente multi-step e inviavel.**

**Tres camadas (vocabulario canonico §19.0):**

| Camada | Escopo | Implementacao | Status |
|---|---|---|---|
| **Session** (curto prazo) | 1 analise / 1 dossie / 1 turn agentico | `AnalysisSession` in-process; persiste em DB so se durar > N segundos | A IMPLEMENTAR |
| **Tenant** (medio prazo) | Preferencias do tenant + padroes aprendidos + limites internos | `tenant_memory` table + `ai_conversation_summary` ja existente | PARCIAL (skeleton) |
| **Global** (longo prazo) | Padroes anonimizados aprendidos cross-tenant | A definir + **parecer juridico LGPD/BACEN obrigatorio antes** | DEFERIDO |

**`AnalysisSession` proposta** (a viver em `app/agentic/memory/session.py`):

- **Working memory**: observacoes intermediarias do agente ("Cedente A: score 412, 2 protestos")
- **Scratchpad**: textual, agent-writeable, sobrevive entre tools dentro da mesma session
- **Step cache**: resultado de tool ja executada com mesmos parametros nao reexecuta (economia de tokens + custo de bureau)
- **Step trace**: lista ordenada de tool_use + tool_result + duracao + tokens — alimenta `AgentLiveStatus` no frontend

**SSE em tempo real:** durante o tool loop, motor emite frames `tool_use` / `tool_result` no stream. Frontend renderiza via `AgentLiveStatus` (componente ja existente, hoje so usado em dossie de credito). Quando chat virar agentico (usar tools), o mesmo componente cobre.

**Persistencia:** session in-process por padrao. Se exceder N segundos OU se for **conversa multi-turn** (chat), persiste em DB em tabela `agent_session_step` (append-only, particionada por tenant + data, paralela ao `decision_log`).

**Isolamento (regra dura):**

- Toda leitura de session/tenant memory **filtra por `tenant_id`** antes de qualquer outra operacao. Vazamento entre tenants = falha critica de compliance.
- Memoria de modulo X nao e visivel a agente de modulo Y, exceto quando agente tem `cross_module=true`.
- Expiracao: session expira ao fim da analise (default 1h). Tenant memory persiste indefinidamente mas auditavel.

**Retrieval semantico:** quando virar prioridade, tabela ganha `embedding vector(1536)` (pgvector ja instalado, hoje nao usado em IA). Service `app/agentic/memory/semantic.py` faz busca por similaridade. **Nao implementar ate caso de uso concreto pedir.**

### 19.12 Catalogo central de agentes

Agentes sao **centralizados** em `app/agentic/agents/catalog/`, **nao espalhados por modulo**. Cada `AgentDefinition` carrega `module: Module` como **tag** no metadata — RBAC, tools disponiveis, persona, billing, metricas agrupam por essa tag.

**Por que centralizar (decisao 2026-05-20):**

- Camada agentica e horizontal por tese (§19.0) — espalhar fisicamente contradiz.
- `ai_prompt` ja e central (flat, namespace `<categoria>.<nome>`) — replicar mantem governanca coesa.
- UI admin `/admin/ia/agents` lista flat com filtro por modulo — codigo espalhado obrigaria agregar de N pastas.
- Marketplace de custom agents por tenant exige catalogo central por natureza.
- Reuso cross-modulo: agente pensado pra risco pode ser invocado por controladoria via `cross_module=true`.

**Modelagem hibrida (estrutura em codigo + texto em DB):**

- **Em codigo** (`app/agentic/agents/catalog/<modulo>_<agente>.py`): `AgentDefinition` instance — name, module, allowed_tools pattern, allowed_playbooks pattern, modelo default, `output_schema` Python class quando ha (specialist agents validados via Pydantic).
- **Em DB** (`agent_definition` + `agent_definition_active`): persona_id (FK pra `agent_persona`), prompt_id (FK pra `ai_prompt`), overrides de modelo/temperature/max_tokens (opcionais), memory_scopes, credit_hint, cross_module bool, tenant_id NULL=global, archived_at.
- **Persona separada** (`agent_persona`): id, name (ex.: "Controller Senior"), description, role_block (bloco textual injetado no prompt), expertise_domains, versionamento espelhando `ai_prompt`. Reusavel — mesma persona serve N agentes do mesmo papel.

**Layout fisico:**

```
app/agentic/
├── engine/                          # runtime unico + LLM adapter + SSE streaming
│   ├── runtime.py
│   ├── llm/                         # ex-modules/integracoes/adapters/llm/
│   └── streaming.py
├── agents/
│   ├── registry.py                  # AgentRegistry.get(name, scope)
│   ├── _base.py                     # AgentDefinition, ScopedContext
│   ├── personas/                    # personas reutilizaveis
│   └── catalog/                     # flat, todos os agentes do produto
│       ├── credito_analista_dossie.py        # module=CREDITO
│       ├── credito_analista_financial.py     # module=CREDITO
│       ├── risco_top_cedentes.py             # module=RISCO
│       ├── controladoria_variacao_cota.py    # module=CONTROLADORIA
│       └── bi_chat_fidc_geral.py             # module=BI
├── playbooks/
│   ├── engine.py                    # ex-modules/credito/workflows/engine.py
│   ├── registry.py                  # PlaybookRegistry
│   ├── _base.py                     # PlaybookDefinition
│   └── catalog/                     # templates declarativos por modulo (flat)
├── tools/
│   ├── registry.py                  # ToolRegistry.get_available(scope)
│   ├── _base.py                     # AgentTool, decorator @register_tool
│   ├── credito/                     # tools de dominio do credito
│   ├── risco/
│   ├── controladoria/
│   └── shared/                      # tools cross-modulo (calc, reference)
└── memory/
    ├── session.py                   # AnalysisSession
    ├── tenant.py                    # TenantMemory
    └── semantic.py                  # pgvector retrieval (futuro)
```

**Invocacao tipica:**

```python
# Em qualquer endpoint/service que precisa rodar agente:
agent = AgentRegistry.get(
    name="credito.analista_dossie",
    scope=ScopedContext(tenant, empresa, user, module, permissions, db),
)
result = await engine.run(agent, objective="...", context={"dossier_id": X})
# Engine resolve persona + prompt + tools filtrados + session memory.
# Trace de tool_use vai por SSE em tempo real para frontend.
# Audit grava decision_log + ai_usage_event.
```

**`decision_log.rule_or_model_version`** vira `<agent.full_id>+<prompt.full_id>+<persona.full_id>` — uma string conta toda a historia da decisao.

**Tabela `tenant_agent_override`** (futuro, opcional): permite tenant ajustar modelo/temperature/max_tokens sem fork de codigo. So system maintainer ou tenant ADMIN pode editar.
