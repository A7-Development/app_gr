# App GR -- Regras do Projeto

> Sistema de inteligencia de dados para FIDC (pt-BR). Monorepo com `frontend/` (Next.js 14 + Tremor Raw — entregue) e `backend/` (FastAPI + PostgreSQL, multi-tenant — em construcao). Este arquivo governa o comportamento do Claude Code em todas as sessoes deste repositorio.
>
> **Palavras-chave do sistema:** multi-tenant, adapter pattern por fonte de dados, modelo canonico entity-centric, DNA de auditabilidade (proveniencia + explicabilidade + versionamento), laboratorio de teses em dados historicos.

---

## 🎨 POLITICA PERMANENTE DE ITERACAO VISUAL E EXPLORACAO (promovida 2026-07-06)

> Ex-banners "MODO ITERACAO DE DESIGN" (2026-04-27) e "MODO DESIGN EXPLORATORIO" (2026-05-11). A auditoria de 2026-07-06 mostrou que o codigo consolidou esse estado (~1.100 valores arbitrarios em 180 arquivos; a propria §7.1 canoniza `h-[30px]`/`text-[13px]`) — o "temporario" virou politica oficial por decisao do Ricardo. O plano antigo de batch-refactor + promocao em massa a tokens foi aposentado.

### Iteracao visual (fidelidade a handoff e polish)

1. **Valores arbitrarios de Tailwind sao permitidos em qualquer camada** (`text-[13px]`, `h-[42px]`, `p-[7px]`, `rounded-[4px]`, larguras/espacamentos especificos do design).
2. **Hex literals, `rgba(...)` e inline styles `style={{...}}` sao permitidos** quando Tailwind nao resolve bem (gradientes complexos, `EChartsOption`, positioning pontual) — preferindo `tokens.*` quando existir equivalente.
3. **Cores Tailwind fora das categorias da §4** (`orange-*`, `purple-*`, `yellow-*`, etc) sao permitidas quando vierem de handoff ou proposta aprovada. Em series de chart, continue via `chartUtils`; badge semantico de status usa `tableTokens.badge*` (§6).
4. **Preferencia de mecanismo** (do mais sistemico ao mais pontual): (a) editar tokens em `design-system/tokens/*.ts` quando a mudanca e sistemica ("cards padrao", "raio default", "tipografia de cell"); (b) criar/alterar CSS vars no `@theme` do `globals.css`; (c) compor wrapper em `design-system/components/` (§3); (d) classe ad-hoc na callsite. **Promocao a token e OPORTUNISTA**: valor recorrente vira token quando a area for tocada — nao ha varredura em batch.
5. **Continua bloqueado**: editar `components/tremor/*` e `components/charts/*` (camadas verbatim — fork muda a relacao com o upstream Tremor). Se ESTRITAMENTE precisar mexer no primitivo, pare e discuta antes.

### Exploracao estrutural (propor antes de aplicar pattern)

Proponha **2-3 alternativas de layout/UX/estrutura** (ASCII mock ou bullets curtos com tradeoffs, sempre comparadas ao pattern canonico mais proximo) e espere a escolha do Ricardo ANTES de codar, quando:

- **Greenfield estrutural** (primeira pagina de modulo novo) · **dado incomum** (rede de relacionamentos, matriz NxM, timeline ramificada, sequencia com bifurcacao) · **surfaces de marca** (login, 404, onboarding) · **hero zones** de dashboard (Z1/Z2) · **empty/error states ricos** de dominio;
- O pattern canonico encaixar mal (forcaria 3+ `// MOTIVO:` ou esconderia a dimensao mais importante do dado);
- Ricardo sinalizar: "ousada", "criativa", "diferente", "alternativa", "me da 2-3 opcoes", "ta pobre", "achatado" — ou reclamar do que acabou de ser produzido.

Sinalize com `**[exploratorio ON]**` na primeira linha e espere a escolha; depois implemente respeitando §7 e as regras estruturais. Se a estrutura escolhida servir a outras telas, proponha promove-la a `design-system/patterns/`. **Propor libs fora da §2 tambem e livre** — implementar continua exigindo autorizacao explicita. Fora desses casos (bug fix, refactor mecanico, rename, CRUD clone de outro CRUD, "faz igual a tela Y"), aplique o pattern canonico direto, sem brainstorm.

### O que continua inviolavel

§2 stack (instalar lib nova exige autorizacao) · §3 camadas e regras de import (`tremor/` e `charts/` verbatim) · §7 patterns canonicos como referencia · §10 multi-tenant absoluto · §11.1 enum fechado de 9 modulos · §11.3 bounded contexts · §11.6 navegacao 3 niveis · §13 adapter pattern · §14 proveniencia + auditabilidade · UI em pt-BR, alias `@/*`, `cx()`, icones Remix, fonte Inter.

*(O hook `PostToolUse` `audit-design-system.cjs` fica desligado enquanto esta politica existir — gate le este titulo. A skill `/audit-page-consistency` continua disponivel manualmente.)*

---

## 1. Palavra de ordem: **padrao e consistencia visual**

> As regras desta secao valem na fase de **implementacao**. Na fase de **proposta** (greenfield, dado incomum, hero/surface, ou quando Ricardo sinalizar), aplica-se a exploracao estrutural da politica permanente do topo — 2-3 alternativas antes de cair na ordem de escolha abaixo.

O sistema usa **Tremor Raw** como **ponto de partida** de design system. Ele cobre ~90% dos casos; quando cobrir, use verbatim.

> **Componente de UI mora em uma destas camadas: `components/tremor/`, `components/charts/`, `design-system/`, `components/<dominio>/` ou `_components/` colocalizado na propria rota.** Componente solto fora dessas camadas nao existe.

Ordem de escolha quando for montar uma tela:

1. Existe em `tremor/` ou `charts/`? Use direto.
2. Existe no Tremor Raw upstream mas ainda nao foi copiado? Copie verbatim de https://tremor.so/docs e use.
3. Existe em `src/design-system/components/`? Use direto via barrel `@/design-system/components`.
4. E especifico DESTA pagina/rota? **Componha em `(app)/<rota>/_components/`** (colocalizado) a partir de DS + tremor. Regra de promocao: quando uma 2a pagina precisar do mesmo componente, suba-o para `design-system/components/` (reutilizavel neutro) ou `components/<dominio>/` (reutilizavel do dominio).
5. E reutilizavel desde o nascimento? **Componha em `src/design-system/components/`** a partir de primitivos Tremor + Radix. Um componente novo e aceito se:
   - **(a)** Prefere tokens da §4/§6 (cores, tipografia, spacing, radius); valores arbitrarios sao permitidos pela politica do topo, com promocao oportunista a token.
   - **(b)** Reutiliza Radix UI quando houver equivalente (Dialog, Popover, Dropdown, Tooltip, etc) — nunca reimplementar a mecanica de acessibilidade.
   - **(c)** E registrado no catalogo [`design-system/components/README.md`](frontend/src/design-system/components/README.md) (proposito + quando usar/nao usar). A rota `/design` e vitrine dev-only — adicionar demo la e desejavel, nao gate.
6. Se a proposta quebrar uma das regras acima OU introduzir uma primitiva que o Tremor ja oferece com outro nome, **pare e discuta antes de escrever codigo.**

Tremor Raw e referencia, nao cela. Quando "fazer como o Tremor faz" conflitar com "resolver melhor o problema do usuario", vence o segundo — desde que (a), (b) e (c) sejam respeitados. Design system e vivo.

---

## 2. Stack obrigatoria (sem substituicoes)

> Claude pode **propor** libs fora desta tabela quando uma alternativa for genuinamente melhor pro caso de uso (politica permanente do topo). **Implementar** continua exigindo autorizacao explicita do Ricardo.

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
| Toasts | `sonner` (via `Toaster` no root layout) | react-hot-toast, react-toastify, toast manual |
| Tema (dark mode) | `next-themes` (`ThemeProvider` no root layout) | toggling manual de classe `dark`, prefers-color-scheme ad-hoc |
| Table engine | `@tanstack/react-table` — **apenas por dentro de `DataTable`/`DataTableShell`/`DenseTable`** (nunca cru em pagina) | AG Grid, data grids externos, `useReactTable` direto em page.tsx |
| Export planilha | `xlsx` (SheetJS) para exportar dados | exceljs, csv manual concatenado |
| Markdown (output IA) | `react-markdown` + `remark-gfm` — uso restrito a `<AIPanel />` e telas de auditoria de IA | uso de markdown em tabelas/forms regulares; renderizacao manual ad-hoc de markdown |
| LLM gateway (backend) | adapter proprio em `app/modules/integracoes/adapters/llm/<provider>/`; LiteLLM aceito por baixo se virar multi-provider real | chamadas diretas ao SDK do provider em codigo de dominio que NAO seja o adapter |
| PII redaction (backend) | regex CPF/CNPJ com check digit (MVP) → `presidio-analyzer` + `presidio-anonymizer` na Fase 2 | enviar payload bruto a LLM externo |
| Cache + rate limit (backend) | em-processo no MVP; Redis em Phase 2 (tenant token bucket multi-dim TPM/RPM/BRL/dia) | `threading.Timer`, sleeps, locks ad-hoc |
| Specialist agents / motor agentico (backend) | `anthropic >= 0.71` (SDK oficial Anthropic Messages API com tool use + prompt caching nativos). Vive em `app/agentic/engine/runtime.py` (refator de §19 executado). | reimplementar tool loop a mao com httpx; usar subprocess do Claude Code CLI (quebra em `SelectorEventLoop` no Windows) |
| Workflow engine (backend) | Graph declarativo imutavel + variable bindings tipados — vive em `app/agentic/workflows/` (primitivo horizontal). Ver §19.10. | codigo imperativo passo-a-passo; reimplementar grafo a mao |
| Workflow visual editor (frontend) | `@xyflow/react` (React Flow v12+) — autorizado 2026-04-30. Usado pelo editor de workflows (renderiza `StrataNode`, `AgentInputBindingsField`, chips de `producedVars`). | reimplementar canvas drag-and-drop manualmente; libs alternativas (rete, dagre standalone) |

Instalar qualquer biblioteca fora desta tabela exige autorizacao explicita do usuario no chat.

---

## 3. Arquitetura em 6 camadas (Strata Design System)

> As camadas e regras de import sao vinculantes na **implementacao**. Na **fase de proposta**, Claude pode esbocar componentes novos em `design-system/components/` sem exaurir a busca em `tremor/`/upstream antes (politica permanente do topo). Aprovacao final do Ricardo valida onde mora.

```
src/components/tremor/             <- Primitivos Tremor Raw (verbatim da doc).
                                       Nao editar. Substitua apenas ao atualizar a versao upstream.

src/components/charts/             <- Charts do Tremor (verbatim). Mesma regra.

src/design-system/tokens/          <- Tokens TS espelhando CSS vars do globals.css.
                                       (spacing, motion, card, table, typography,
                                       echarts-theme, provenance, node-category, ...).
                                       Inclui paleta de marca Strata (navy, navy-dark, orange)
                                       e escala tipografica hero — uso restrito a surfaces/.

src/design-system/primitives/      <- Barrel re-exporta `tremor/*` + Sheet (right-side drawer).
                                       Ponto de entrada unico para primitivas.

src/design-system/components/      <- Componentes do Strata Design System (FIDC-domain).
                                       ~90 componentes — catalogo vivo no README.md da pasta.
                                       USA apenas tremor/ + charts/ + tokens/, nunca Tailwind
                                       bruto de cor / Radix cru.

src/design-system/patterns/        <- Composicoes copy-paste-edit (DashboardBiPadrao,
                                       DashboardOperacional, ListagemComDrilldown,
                                       ListagemCrudInline, ListagemCrudExpand,
                                       ListagemCrudCards, WizardMultiStep).
                                       Templates de pagina autenticada.

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

src/app/(app)/**/_components/      <- Componentes COLOCALIZADOS de uma pagina/rota
                                       especifica (camada legitima — decisao 2026-07-06).
                                       Compostos de design-system/ + tremor/ + charts/.
                                       Quando uma 2a pagina precisar, PROMOVA para
                                       design-system/components/ ou components/<dominio>/.
```

**Catalogo completo de componentes:** ver [`frontend/src/design-system/components/README.md`](frontend/src/design-system/components/README.md) — registro vivo dos ~90 componentes (canonicos do handoff Strata + A7 Credit composites como `PageHeader`, `ModuleSwitcher`, `AuthGuard`, `Breadcrumbs`, `OriginDot`, `FilterPill`, `CardMenu`, `DenseTable`, `AIPanel`, `AgentLiveStatus`, `FinancialTable`, etc.). Antes de criar componente novo, consulte este catalogo — provavelmente ja existe.

**Imports permitidos por camada:**

- `tremor/` importa: `@/lib/utils`, `@/lib/chartUtils`, `@remixicon/react`, `tailwind-variants`, Radix UI (interno), Recharts (interno).
- `charts/` importa: o mesmo que `tremor/` + `react`.
- `design-system/tokens/` importa: nada externo (apenas `react` para hooks).
- `design-system/primitives/` importa: `@/components/tremor/*` + nova `Sheet.tsx`.
- `design-system/components/` importa: `@/components/tremor/*`, `@/components/charts/*`, `@/design-system/tokens/*`, `@/design-system/primitives/*`, `@/lib/*`, `@remixicon/react`, primitivos Radix **sem equivalente no Tremor** (ex.: `@radix-ui/react-avatar`, `@radix-ui/react-hover-card`), `cmdk`, `echarts-for-react`. **Proibido**: Radix para o que o Tremor ja cobre, Recharts direto, classes de cor Tailwind ad-hoc.
- `design-system/patterns/` importa: `@/design-system/components/*` + `@/design-system/tokens/*` + `@/components/tremor/*`. **Sao templates copiaveis** — escopo: composicao + dados de exemplo.
- `design-system/surfaces/` importa: `@/components/tremor/*` + `@/design-system/primitives/*` + `@/design-system/tokens/*` (incluindo `tokens.colors.brand` e `tokens.typography.hero`) + `@remixicon/react` + assets de marca (logo SVG). **Proibido**: importar de `@/design-system/components/*` (componentes de dashboard nao pertencem a superficie de marca; excecao: `StrataIcon` — ver §4.1 regra 2), importar de `<dominio>/*`, hex literal solto fora de `tokens/`.
- `<dominio>/` importa: `@/design-system/*`, `@/components/tremor/*`, `@/components/charts/*`, hooks de dominio, types de dominio. **Nunca importa de outro dominio.**
- `(app)/**/_components/` (colocalizado) importa: o mesmo que `<dominio>/` + hooks/types da propria rota. **Nunca importa de `_components/` de OUTRA rota** — se precisou, e sinal de promocao pra camada compartilhada.

**Barrel oficial:** `import { ... } from "@/design-system/components"` re-exporta tudo.

---

## 4. Tokens e cores

> Esta secao define o **vocabulario canonico de cor** — o default de qualquer tela. A politica permanente do topo libera cores fora destas categorias **quando vierem de handoff ou proposta aprovada** (hero zones, surfaces, empty states ricos), com promocao oportunista a token. Em **listagens/dashboards transacionais ja estabelecidos**, mudar cor a esmo confunde o usuario — fique na paleta abaixo.

**Paleta Tremor — unicas cores brutas aceitas:**

| Categoria | Classes permitidas | Uso |
|---|---|---|
| Neutros | `gray-*` (todas as escalas + `dark:`, inclui `gray-925`) | textos, bordas, backgrounds, superficies |
| **Atencao / selecao** | `blue-*` (principalmente `blue-500` para bg/fill e `blue-600`/`blue-700` para texto em light; `blue-400`/`blue-500` em dark) | **chama os olhos do usuario** — estado ativo da sidebar, aba ativa (TabNavigation/Tabs), filtros com selecao aplicada (FilterPill, PeriodoPresets), botoes primary, focus rings (`focusInput`/`focusRing`), checkbox/radio/switch marcados, calendar selected, link "voltar/editar". **Nao** use como cor semantica de "sucesso/info" — para isso use `Badge variant`. |
| Destrutivo / erro | `red-*` (em qualquer escala + `dark:`) | ErrorState, Dialog destructive, Button destructive, validacao de form, toasts de erro |
| **Dados (chart)** — paleta A7 Credit | cores de `chartColors` em `@/lib/chartUtils`, na ordem canonica: `slate` → `sky` → `teal` → `emerald` → `amber` → `rose` → `violet` → `indigo`. `blue`/`gray`/`cyan`/`pink`/`lime`/`fuchsia` existem no dicionario mas **nao iteram no default** — use por override explicito. | **apenas em `src/components/charts/`** ou quando a cor vier dinamicamente de `getColorClassName()`. `slate` (1a serie) escolhido por ser azul-acinzentado de baixa saturacao — nao cansa durante horas de analise. |

**Proibido (independente da politica do topo):**
- **`slate-*` como cor de atencao/selecao** — use `blue-*`. `slate` e exclusivamente para dados de chart + neutros raros.
- **`blue-*` como cor de serie default em chart** — a 1a cor iteravel da paleta A7 e `slate`, nao `blue`. `blue` so como override explicito `<Chart colors={["blue"]}>`.
- **Cor semantica de status improvisada**: badge de status em tabela/lista usa os tokens nomeados `tableTokens.badgeSuccess` / `badgeWarning` / `badgeDanger` / `badgeNeutral` (§6) — nao recrie a receita `bg-emerald-50 text-emerald-700 ...` inline (codigo novo usa token; legado converte quando tocar). Fora de tabela, `Badge variant` do Tremor continua valendo.
- Gradientes manuais (`bg-gradient-to-*` com cores arbitrarias) em pagina autenticada — gradiente de marca so em `surfaces/` (§4.1).

**Permitido com criterio (politica do topo):** valores arbitrarios de cor (`bg-[#...]`) e cores fora das categorias acima, quando vierem de handoff/proposta aprovada — prefira token quando existir equivalente.

**Excecao explicita — ECharts option objects:** hex literals (`#3B82F6`, `#F59E0B`, `#10B981`, etc.) sao **permitidos** dentro de `EChartsOption` (em `series[].itemStyle.color`, `lineStyle.color`, `areaStyle.color.colorStops`, gradientes de eixo, etc.) porque Tailwind nao alcanca o renderer do canvas. Preferir, quando viavel, valores de `tokens.colors.chart` ou nomes Tremor mapeados — hex inline e aceitavel quando o tipo da `EChartsOption` exige string de cor.

**Dark mode:** sempre suportar. Usar as mesmas classes que o Tremor usa (`dark:bg-gray-950`, `dark:text-gray-50`, `dark:border-gray-800`). O `<html>` ja tem `dark:bg-gray-950` em `layout.tsx`.

**Espacamento, tipografia, radius:** herdar do Tremor como default. Valores arbitrarios (`text-[13px]`, `h-[30px]`, `p-[7px]`) sao permitidos pela politica do topo — os controles do FilterBar/header ja padronizam `h-[30px]`/`text-[13px]` (§7.1). Valor recorrente vira token quando a area for tocada.

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

Escala separada da Tremor, registrada em `tokens.typography.hero` (`display` 52px, `lede`, `eyebrow`, `formTitle`, `trust`, `wordmark` — valores exatos no arquivo de tokens). **Uso de `hero.*` fora de `surfaces/` e bloqueador de PR.** Pagina autenticada continua na escala Tremor (`text-sm`, `text-base`, `text-xl`, etc).

---

## 5. Regras de codigo

- **Idioma da UI:** sempre pt-BR. Strings voltadas para usuario em pt-BR. Mensagens de erro tecnicas (console/dev) podem ser em ingles.
- **Imports:** usar sempre alias `@/*` (nunca `../../../`).
- **Componentes:** `function Component() { return (...) }` exportado. Props tipadas com `type`, nao `interface`, a menos que precise de extends.
- **`use client`**: paginas de dados sao client components na pratica — consequencia direta do `react-query` exigido pela §2 (42/51 paginas hoje). A regra util: **nao vazar `use client` para componentes folha/presentacionais** que so recebem props — esses ficam server-compativeis por default.
- **Nenhum `any`** em codigo de dominio. Em codigo verbatim do Tremor, preservar com `// eslint-disable-next-line @typescript-eslint/no-explicit-any`.
- **Inline styles** (`style={{...}}`): evitar como default; permitidos pela politica do topo quando Tailwind nao expressa bem o efeito. Casos consagrados:
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
- **Series temporais FIDC** (PL, cotas, rentabilidade mes a mes) — usar `<DenseTable.Series>` (modo transposto da DenseTable: periodos como colunas, Austin-style, density compact default; absorveu a antiga CompactSeriesTable).
- **Tabelas hierarquicas** (BalanceTable, etc — multi-nivel com expand) — `<DataTable>` direta + `enableExpanding`/`getSubRows`/`expandedColumnId`. Nao cabe no `<DataTableShell>`.
- **Tipografia + cores em CELL renderers**: SEMPRE via **`tableTokens.*`** de `@/design-system/tokens/table` — NUNCA `text-xs`, `text-sm`, `text-[Npx]`, `text-gray-XXX` literais inline. Excecao com `// MOTIVO:` no proprio cell. Tokens disponiveis: `cellText` (12px texto), `cellTextMono` (12px mono), `cellSecondary` (12px gray-500), `cellMuted` (12px placeholder), `cellStrong` (12px semibold), `cellNumber`/`cellNumberSecondary`/`cellNumberPositive`/`cellNumberNegative` (tabular-nums), `badge`/`badgeWithDot` (11px), `badgeSuccess`/`badgeWarning`/`badgeDanger`/`badgeNeutral` (badge semantico de status — receita emerald/amber/red/gray canonica; codigo novo usa estes, nao a receita inline), `header` (10px eyebrow). Tudo 12px de base — cabe em row de density compact (h-8). **Texto principal em dark = `gray-100`, NAO `gray-50`.**
- **Bordas em `rowClassName` da DataTable**: use sempre `border-t-{color}` / `border-b-{color}` / `border-y-{color}` (forma com lado explicito) — NUNCA o shorthand `border-{color}`. O shorthand seta `border-color` nos 4 lados, sobrescrevendo a `border-bottom-color: gray-100` default que a DataTable aplica em todo `<tr>`. Resultado visual: linhas com `border-t border-gray-200` ficam parecendo "boxed" (borda tambem embaixo, na cor errada). Mesma regra para `subtotal`, `total`, `section` em tabelas hierarquicas.
- Nunca AG Grid, nunca data grid externo, nunca `Table` do Tremor cru em pagina (Tremor `Table` so como primitivo dentro de DataTable/DenseTable.Series).

---

## 7. Paginas e rotas — Patterns canonicos e Surfaces

Toda **pagina autenticada** (`src/app/(app)/*`) **deve preferir** comecar de um dos patterns canonicos em `src/design-system/patterns/`:

- **DashboardBiPadrao** — Pagina canonica do BI (handoff bi-padrao 2026-04-26). 5 zonas: Z1 PageHeader (titulo + IA + acoes) · Z2 TabNavigation L3 · Z3 FilterBar sticky **(anatomy FLAT — linha branca com `border-b`, ver §7.1)** · Z4 conteudo (InsightBar + KpiStrip 5 KPIs + grid 2/3+1/3 + grid 3-col + DataTable) · Z5 ProvenanceFooter. Lateral: AIPanel violeta in-layout + DrillDownSheet. Use para qualquer dashboard analitico (BI, Controladoria, Risco) que envolva KPIs + charts + tabela com drill-down.
- **DashboardOperacional** — PageHeader + FilterBar + KpiStrip (4 KPIs) + Grid 2×2 EChartsCards + DataTable de atividade recente. Use para dashboards mais simples sem AI panel (telas operacionais).
- **ListagemComDrilldown** — PageHeader + FilterBar + DataTable + DrillDownSheet (URL-synced via `?selected=ID`). Use para listagem de **dados de dominio** (gerados pelo sistema): Cessoes, Cedentes, Sacados, Cobranca, Reconciliacao, Eventos. Drill-down abre painel rico (PropertyList + Tabs + Timeline + LinkedObjects).
- **ListagemCrudInline** — PageHeader (com botao "+ Novo") + Card { `<FilterSearch>` + `<SegmentSwitch>` + contador `X de Y` + DataTable } + DrillDownSheet de criar (`?action=new`) + DrillDownSheet de editar (`?selected=<id>`) + Dialog destrutivo (state local). Use para **gestao administrativa** de cadastros pequenos a medios (~5-200 rows) onde **cada entidade tem identidade tabular** (compara linha-a-linha) e criar/editar/excluir acontecem inline: credenciais de provedor LLM, usuarios do tenant, etiquetas, templates de regra, fornecedores. Filtros sao **client-side** ate ~200 rows (busca via `globalFilter` do TanStack + segments locais); acima disso, copy-paste-edit + adicione `<FilterChip>` por coluna; acima de 2000 rows, migre para server-side (paginacao + busca debounced). Primeira instancia em producao: [`/admin/ia/providers`](frontend/src/app/(app)/admin/ia/providers/page.tsx).
- **ListagemCrudCards** — PageHeader (`title` + `info` tooltip + `subtitle` eyebrow + botao "+ Novo") + Card { `<FilterSearch>` + `<SegmentSwitch>` + contador `X de Y` } + grid responsivo `1/2/3` colunas de `EntityCard` + DrillDownSheet de criar (`?action=new`) + (opcional) DrillDownSheet de editar (`?selected=<id>`, omita se edit redireciona pra outra rota) + Dialog destrutivo. Use para **gestao administrativa** onde **cada entidade tem identidade visual** (icone + titulo + descricao + metadata heterogeneo + badges + acoes) e cabe melhor em CARD do que em linha de tabela: workflows, agentes IA, dashboards salvos, conexoes externas, templates de extracao. Volume tipico < ~50 cards (~3 paginas de scroll); acima de 200 items considere migrar pra `ListagemCrudInline`. **EntityCard canonico**: `<Card>` com `<div className={cardTokens.body}>`, hover `border-blue-500`, layout em 3 linhas (avatar+badges+dropdown / titulo+descricao / metadata com `·`), DropdownMenu de acoes com `e.stopPropagation()` no trigger. Cor do avatar via tokens nomeados (ex.: `nodeCategoryTokens`) — proibido `bg-X-N` solto. Primeira instancia em producao: [`/credito/workflows`](frontend/src/app/(app)/credito/workflows/page.tsx).
- **ListagemCrudExpand** — Variante hierarquica de `ListagemCrudInline`: mesma anatomia, mas DataTable com sub-rows expansiveis via chevron (`enableExpanding`/`getSubRows`). Use para cadastros pai-filho (plano de contas, categorias com sub-categorias). Filtro persiste o pai se algum descendente casa; excluir pai com filhos bloqueia.
- **WizardMultiStep** — Wizard enterprise 3 colunas + top rail sticky (side steps colapsavel · workspace central com views waiting/running/completed/failed/blocked · evidence panel a direita). Use para processos multi-step dirigidos por workflow (esteira de credito/dossie). URL state `?step=<nodeId>&panel=...`; recebe DADOS via props (queries ficam no caller); `AgentLiveStatus` via `renderRunning`.

Toda **pagina nao-autenticada / superficie de marca** (`src/app/(auth)/*`, `src/app/error.tsx`, `not-found.tsx`, futuras paginas publicas) nasce de um template em `src/design-system/surfaces/`:

- **HeroSplitAuth** — Layout 60/40 com hero zone (gradiente navy + glow laranja + pattern de linhas + logo + headline + trust signals) a esquerda e zona de form a direita. Use para `/login`, `/recover-password`, `/onboarding/welcome`.
- (futuros) `SplashScreen`, `ErrorPage404`, `ErrorPage500`, `MarketingHero`.

Patterns e surfaces sao **copy-paste-edit** — nao componentes black-box. Copie o pattern para a pasta da pagina, adapte titulo/copy/mocks/charts ao dominio. Os comentarios `HOW TO ADAPT:` no topo de cada arquivo guiam a customizacao. Pages que copiam um pattern e divergem do template sao esperadas, nao excecao.

**Header de dashboard — set canonico de acoes (handoff bi-padrao 2026-04-26):** toda pagina derivada de `DashboardBiPadrao` usa `<DashboardHeaderActions>` no slot `actions` do `<PageHeader>`. O composite renderiza, em ordem fixa: `[DarkToggle, Compartilhar, Exportar, Mais, IA]`. DarkToggle e IA sao sempre presentes; Share/Export/More sao omitidos quando o callback nao e passado. Substituir por `<Button>` solto ou conjunto custom de botoes e regressao — fecha a porta para que cada pagina invente seu proprio header. Para acoes secundarias (Copiar link, Duplicar, Imprimir, etc.), use o slot `more={[...]}`.

**Navegacao e aprofundamento de dados (como o usuario desce no detalhe):** ver [`docs/navegacao-aprofundamento.md`](./docs/navegacao-aprofundamento.md) — fonte de verdade para escolher entre inline / drawer / rota / modal. Resumo: exploracao → inline/drawer (preserva contexto); novo foco de trabalho → rota; decisao irreversivel → modal; form de config nunca em modal. Fronteira: **cedente/sacado/dossie viram rota** (`/.../[id]`); **cessao/titulo/operacao sao drawer** (`?selected` via nuqs, abrir=push / prev-next=replace); **parcela/evento/linha do agente sao inline**. Drawer/modal nao contam como nivel de navegacao (ortogonais a §11.6).

### 7.1 FilterBar (Z3) — anatomy canonica + controles

**Anatomy FLAT** (canonica 2026-06-02 — o antigo Card-em-faixa-cinza foi aposentado para dashboards): a Z3 renderiza como **linha branca sticky com `border-b`**, chips direto sobre a linha, `shadow-xs` ao scrollar. Implementacao oficial e fonte de verdade das classes: [`src/design-system/components/FilterBar/index.tsx`](frontend/src/design-system/components/FilterBar/index.tsx) — **nenhuma pagina recria essa estrutura inline**. Listagens CRUD de cards podem manter Card-em-faixa; a regra flat vale para os dashboards. (Tech-debt: `operacoes2/3/4` e `panorama` usam toolbar inline equivalente — unificar e follow-up.)

**Altura canonica dos controles (decisao 2026-07-08, Ricardo):** todo controle de **FILTRO** (search, select, chip, dropdown de status, segment) tem a MESMA altura do filtro de texto: **26px** / `text-[13px]` — regua exportada em `filterControlClass` (`design-system/components/FilterBar`); aplique em `SelectTrigger` de filtro via `cx(filterControlClass, "w-...")`. Filtro de texto novo = `<FilterSearch>` (nunca `Input` cru com altura ad-hoc). **Botoes de ACAO do header** (Pontuar, Sincronizar, DashboardHeaderActions) seguem `h-[30px]`/`text-[13px]`. Misturar alturas na mesma linha de filtros e bug visual.

**Per-element coloring em controles compostos (regra dura):** cor aplicada **por elemento** (icone / label / valor), nunca via `text-X` no elemento raiz — inheritance achata a hierarquia visual. Cores exatas da anatomy: `FilterChip` no proprio FilterBar/index.tsx. Botoes que parecem chip seguem a mesma anatomy (texto principal `gray-900`). `MoreFiltersButton` aceita `asChild` (Radix Slot) para Popover custom — nao escreva `<button>` cru duplicando.

Antes de escrever uma `page.tsx` nova, pergunte:
- E pagina autenticada? Qual **pattern** aplica?
  - Dashboard com KPIs + IA → `DashboardBiPadrao`
  - Dashboard simples sem IA → `DashboardOperacional`
  - Listagem de dados de dominio (drill-down de leitura) → `ListagemComDrilldown`
  - Gestao administrativa CRUD com identidade tabular (linha-a-linha) → `ListagemCrudInline`
  - Gestao administrativa CRUD hierarquica (pai-filho, sub-rows) → `ListagemCrudExpand`
  - Gestao administrativa CRUD com identidade visual (icone + descricao rica) → `ListagemCrudCards`
  - Processo multi-step dirigido por workflow → `WizardMultiStep`
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
2. Janela de tempo do agregado diverge do periodo da pagina (mini chart do mes corrente, sparkline 12M)? Monte `{**filters, "periodo_inicio": ..., "periodo_fim": ...}` e passe ao `_apply_filters` — as datas aceitam override; produto/UA/focus continuam aplicados.
3. **Helper que recebe `filters` e nao aplica e bug** (ja aconteceu em prod: mini chart somava o VOP total da empresa ao lado de um KPI filtrado). Toda funcao que toca `Operacao` em service de BI recebe E aplica `filters`.

**Em PR:** consumo de `Operacao` (ou warehouse derivado) em service de BI sem `_apply_filters` e bloqueador. Reviewer rejeita.

### 7.3 Feedback de progresso — FUNDAMENTO (regra dura, inviolavel)

> Decisao 2026-06-15 (Ricardo, recorrente): **o usuario NUNCA fica sem saber se o sistema esta travado ou trabalhando.** Vale pra TODA tela, sem excecao. Reincidencia e bug de prioridade alta, nao polish.

1. **Nenhum estado morto/ambiguo.** Operacao > ~400ms expoe indicador (spinner `isLoading`/`isPending`, skeleton, barra). Botao que dispara trabalho **sempre** entra em `isLoading`. Operacao longa **sempre** tem texto + expectativa de tempo ("Consultando a JUCESP — 1-2 min").
2. **Backend longo e VISIVEL ao vivo, nao so no fim.** Estado intermediario observavel pelo frontend **enquanto roda** — node `RUNNING` commitado e visivel ao polling, SSE de tool_use, ou status incremental. "Commita so no fim" e o bug recorrente — nao repetir. Cada etapa mostra pendente → rodando (com o que faz) → concluido/falhou, conforme acontece.
3. **Desfecho sempre explicito.** Sucesso confirma; vazio explica; erro mostra o que houve + o que fazer. Nada de "parou e nao sei por que".

**Ferramentas canonicas:** `isLoading`/`isPending` dos primitivos Tremor; `useQuery` com `refetchInterval` ate estado terminal; `AgentLiveStatus` (trace ao vivo); banners de fase; `prefers-reduced-motion` respeitado. **Em PR (bloqueador):** acao sem `isLoading` no gatilho; operacao longa sem texto; processo assincrono cujo estado nao chega ao vivo; "parou" sem desfecho.

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

**Relacao com `app_controladoria`:** backend legado em producao na VM, roda em paralelo. Dele copiamos **seletivamente** (copy-paste + refactor) — nunca importamos como dependencia, nunca evoluimos.

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
| ML / deteccao de anomalias | `scikit-learn` (logistic regression) + `pandas`/`numpy` — uso RESTRITO a treino/score dos modelos de deteccao do modulo risco (autorizado 2026-07-08); coeficientes persistidos em `deteccao_modelo_versao` (JSONB versionado, rollback 1 clique) | pickle/artefato binario de modelo; MLflow (v1); PyOD/mlxtend/GBM sem nova autorizacao; SMOTE/oversampling sintetico |
| HTTP client | httpx (async) | requests |
| Logging | `logging` stdlib (logger nomeado por modulo) | `print()` em codigo de dominio; structlog (removido — era dep morta) |
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
4. **Testes de isolamento — regra executavel por PR:** todo **endpoint novo** tem teste de 403 (user sem permissao de modulo); todo **service novo** que toca tabela multi-tenant tem teste de isolamento (tenant A nao ve dado de tenant B). Cobranca e incremental, no fluxo — nao ha exigencia retroativa de estoque por modulo.
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

**Agentes nao sao um decimo modulo.** Vivem em `app/agentic/` como **camada horizontal estrutural** — ver §19. O enum `Module` continua fechado em 9. Cada `AgentDefinition` / `WorkflowDefinition` / tool carrega `module: Module` como **tag** (RBAC, scope, billing, metricas agrupam por isso), nunca como pasta de modulo.

### 11.2 Estrutura fisica (bounded contexts)

```
app/
├── core/        # cross-cutting absoluto (config, db, security, middlewares, enums, guards)
├── shared/      # shared kernel: auditable.py (mixin), audit_log/ (decision_log,
│                #   premise_set), identity/ (Tenant, User, permissions), ai/ (models
│                #   da camada agentica), crypto, endpoint_catalog
├── agentic/     # camada HORIZONTAL (§19): engine/, agents/, tools/, workflows/, memory/
├── modules/     # 9 bounded contexts (bi, cadastros, operacoes, credito, controladoria,
│                #   risco, integracoes, laboratorio, admin) — cada um com public.py
│                #   (CONTRATO) + models/ services/ schemas/ api/;
│                #   integracoes/ contem adapters/ (§13)
├── warehouse/   # models silver/bronze compartilhados
└── main.py
```

### 11.3 Regras de import (bounded contexts)

- Modulo X pode importar **livremente** de `app/core/` e `app/shared/`.
- Modulo X pode importar de modulo Y **somente** via `app/modules/Y/public.py`. Imports de internals de Y (`modules/Y/models/*`, `modules/Y/services/*`) sao **proibidos**.
- Cada modulo expoe em `public.py` APENAS o que e contrato estavel. Mudar `public.py` e mudanca de API — exige reflexao.
- Modulo nao deve depender de mais de 1-2 outros modulos. Se depender de 3+, provavelmente precisa de shared kernel ou event bus.
- **BI** le do `warehouse` (dado canonico), nao importa de outros modulos.
- **Integracoes**: sync batch popula o warehouse — para dado historico/agregado, outros modulos leem o warehouse. **Consulta on-demand** (bureau, junta comercial, relatorio sob demanda durante um fluxo como a esteira de credito) e **permitida via `integracoes/public.py` ou node de workflow** — nunca importando internals dos adapters.
- **Tools de modulo X invocadas por agente de modulo Y** vao via `ToolRegistry.get_available(scope)`, **nunca via import direto**. Modulo X nao precisa expor tools no seu `public.py` — o registry filtra dinamicamente por `ScopedContext(tenant, empresa, user, module, permissions)`. Mesma regra vale para workflows invocados cross-modulo (resolucao por nome via `workflow_definition_active`, nunca import direto). Ver §19.

### 11.4 Estrutura de rotas do frontend

```
src/app/
├── layout.tsx                # root layout (html, ThemeProvider, QueryProvider, Toaster)
├── globals.css               # tokens CSS vars + Tailwind directives
│
├── (app)/                    # route group AUTENTICADO — envolvido por <AuthGuard>
│   ├── layout.tsx            # AuthGuard + SidebarProvider + AppSidebar + header sticky
│   ├── page.tsx              # home global (atalhos por modulo)
│   ├── bi/...                # rota /bi (operacoes2-5, panorama, benchmark, concentracao, ...)
│   ├── cadastros/...         # rota /cadastros
│   ├── credito/...           # rota /credito (dossies, workflows, checklist, templates, agentes)
│   ├── controladoria/...     # rota /controladoria (cota-sub, lamina, receitas, conciliacao, ...)
│   ├── integracoes/...       # rota /integracoes (fontes, operacao, catalogo)
│   └── admin/...             # rota /admin (ia/*, dados, ...)
│       # operacoes/, risco/ e laboratorio/ ainda NAO tem rota — modulos "Em breve"
│
├── (auth)/                   # route group PUBLICO — sem AuthGuard
│   ├── layout.tsx            # layout minimo (centra o card de login)
│   └── login/page.tsx        # rota /login
│
├── (foco)/                   # route group AUTENTICADO em "modo foco" — FocusRail (rail 56px)
│                             # no lugar da AppSidebar; usado por telas de trabalho imersivo
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

**A estrutura REAL da sidebar vive em [`src/lib/modules.ts`](frontend/src/lib/modules.ts) (`MODULES[]`) — em divergencia com qualquer exemplo em prosa, `modules.ts` vence.** Exemplo ilustrativo (retrato do modulo BI em 2026-07):

```
L1 (dropdown no topo): [BI ▾]
    L2 (sidebar): Visao geral     → /bi
                  ▾ Originacao    ← parent expansivel (clicar so abre/fecha, nao navega)
                      Drill por dimensao → /bi/operacoes5
                      Mes corrente ...   → /bi/operacoes2..4
                  Concentracao    → /bi/concentracao
                  ▾ Benchmark     ← parent expansivel
                      Panorama do mercado → /bi/panorama
                      Benchmark           → /bi/benchmark   (dados publicos CVM — docs/integracao-cvm-fidc.md)
```

Sub-itens **sao L2 logicamente** — a numeracao L1/L2/L3 reflete tipos de navegacao, nao profundidade de UI. Aninhamento e sintatico; conceitualmente "Padronizados" e "Espelho Adm" continuam sendo destinos L2 do modulo.

**Regras duras:**

1. **Maximo 3 niveis.** Se surgir L4, o modulo precisa ser dividido OU aquilo vira filtro/modal/drawer — nunca 4o nivel de navegacao.
2. **Sidebar pode aninhar 1 nivel (max 2 niveis de UI).** Secao L2 pode ter `children: ModuleSection[]` que renderizam como sub-itens com expand/collapse. Aninhamento de 2+ niveis (filho-de-filho) e **proibido** — vira L3 na pagina (TabNavigation), filtro/drawer, ou divisao de modulo. Sub-itens **sao L2 logicamente** — a numeracao L1/L2/L3 reflete tipos de navegacao, nao profundidade de UI.
   - **Parent expansivel = expand-only:** clicar so abre/fecha, nunca navega (o `href` e apenas prefixo de active-state; sem landing util, a rota 404 ou nao existe). Auto-expand em deep link (via pathname); collapse manual persiste (auto-expand so re-dispara em mudanca de pathname).
   - **Colapso da AppSidebar e binario** (some inteira; host renderiza o trigger de reabrir). Rail 56px existe apenas no modo foco (route group `(foco)/`, `FocusRail`).
   - **Captions (`groupLabel`) sao permitidos:** labels textuais nao-clicaveis separando grupos — nao introduzem hierarquia nem contam como nivel. Complementares ao nesting: caption agrupa itens autonomos; nesting quando o parent e um escopo natural ("Relatorios" engloba filhos).
3. **URL e a fonte unica da verdade.** Modulo, secao, tab e filtros sao todos deep-linkaveis (ex.: `/bi/carteira?tab=por-produto&periodo=30d`). O modulo ativo e inferido do pathname.
4. **Troca entre modulos (L1) e SEMPRE pelo `ModuleSwitcher`** (dropdown no topo da sidebar). O switcher lista os modulos com subscription + permissao; demais ficam em "Em breve" (disabled). Sem icon rail, sem module picker separado do header, sem tabs de modulo.
5. **Breadcrumbs sticky no header** mostram o path: `Modulo > Secao > Pagina` (L1 > L2 > L3).

**Active state:** implementado em `ModuleSwitcher` (via `getActiveModule(pathname)`), `SidebarLink` (`data-active`), auto-expand de parent por pathname (`expandedMap` na `AppSidebar`) e `TabNavigationLink` — a fonte de verdade da mecanica e o proprio codigo.

**Avatars de modulo — cor canonica (handoff v2, 2026-04-24):** definidas em `src/lib/modules.ts::MODULE_AVATAR_COLORS` (fonte de verdade; ex.: BI=`gray-800`, Credito=`indigo-500`, Integracoes=`red-600`). Regras: tiles retangulares `rounded-sm` com 2 iniciais (estilo Linear — separa "identidade de modulo" de "serie de chart"); estas cores sao **exclusivas do avatar** (nao reutilizar na UI, exceto chart series); `red-600` de Integracoes e identidade, nao "erro" — nao reutilizar `red-*` em chips/badges nao-destrutivos.

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

`tenant_module_subscription` (PK tenant+module: enabled, enabled_since/until, plan_ref) e `user_module_permission` (PK user+module: permission) — models em `app/shared/identity/`.

### 12.3 Dependency obrigatoria em todo endpoint de modulo

`Depends(require_module(Module.X, Permission.Y))` (`app/core/module_guard.py`): verifica subscription do tenant (falha = HTTP **402**) e depois permissao do user (falha = HTTP **403**). **Nenhum endpoint de modulo existe sem `require_module`.** Endpoints cross-cutting (auth, health, audit/ping) usam apenas `Depends(get_current_principal)` (`app/core/tenant_middleware.py`).

### 12.4 `/auth/me` e contrato com o frontend

Retorna (shape canonico em `MeResponse`, `backend/app/api/v1/schemas.py` — fonte de verdade):
```json
{
  "user": { "id": "...", "email": "...", "name": "..." },
  "tenant": { "id": "...", "slug": "...", "name": "...", "status": "active", "is_system_maintainer": false },
  "enabled_modules": ["bi", "cadastros", "admin"],
  "user_permissions": { "bi": "admin", "cadastros": "write", "admin": "admin" },
  "ai_enabled": false,
  "ai_permission": "none"
}
```

Frontend usa `enabled_modules` + `user_permissions` para renderizar sidebar e esconder areas. Ainda assim, backend valida em toda request (defense in depth).

---

## 13. Backend -- Adapter pattern (fontes externas)

Fontes de dados externas (ERPs, admin APIs, bureaus, parsers de documento) **NUNCA** sao chamadas diretamente de servicos de dominio. Sempre atraves de adapters.

**Camadas:**

```
app/modules/integracoes/adapters/<tipo>/<nome>/
    __init__.py
    connection.py / client.py    # como abrir conexao / sessao
    queries/ ou queries.py       # queries/requests especificos da fonte
    mappers/ ou mappers.py       # transforma dado da fonte para modelo canonico
    etl.py                       # orquestra extract + transform + load
    version.py                   # ADAPTER_VERSION
```

**Exemplos (em producao):**
- `adapters/erp/bitfin/` — leitura SQL Server do Bitfin
- `adapters/admin/qitech/` — API QiTech (catalogo de relatorios/endpoints)
- `adapters/bureau/serasa_pj/` — Serasa PJ (Relato/Business Information Report — CNPJ)
- `adapters/data/bigdatacorp/` — BigDataCorp (N datasets: CAD-PJ, QSA-PJ, KYC-PJ, ...)
- `adapters/data/infosimples/` — Infosimples (protestos, JUCESP)
- `adapters/cobranca/` — retorno/remessa CNAB dos bancos cobradores (Bradesco, ...)
- `adapters/llm/anthropic/` — cliente HTTP LLM (ver §19.3)

**Regras do adapter:**

1. **Um adapter por PROVEDOR/familia de API, com catalogo de endpoints/datasets interno** (decisao 2026-07-06 — a pratica venceu o "um adapter por endpoint" original). Ex.: `qitech` e 1 adapter com `endpoint_catalog` de N relatorios; `bigdatacorp` e 1 adapter com N datasets (CAD-PJ, QSA-PJ, KYC-PJ...) e `mappers/` por dataset. Separe em 2 adapters apenas quando o provedor tem familias de API genuinamente distintas (auth, formato e billing diferentes — ex.: `serasa_pj` vs um futuro `serasa_pf`).
2. **Versao embutida no adapter:** constante `ADAPTER_VERSION = "1.0.0"` registrada em toda linha ingerida (`ingested_by_version`).
3. **Output sempre em modelo canonico.** Adapter conhece a fonte e conhece o canonico; dominio nao conhece fontes.
4. **Config por tenant:** cada tenant tem seu registro de configuracao (connection string, credenciais, parametros) em tabela `tenant_source_config`. Adapter le config do tenant, nao ha hardcode.
5. **Proibido adapter em codigo de dominio.** Services de dominio leem APENAS do warehouse canonico.
6. **Observabilidade obrigatoria:** cada sync registra metricas (linhas lidas, tempo, erros) no `decision_log`.
7. **Custo + rate limit como metadados** em `source_catalog` quando fonte for paga (bureaus).
8. **Fonte Bitfin = apenas tabelas base** (`dbo.Titulo`, `dbo.Operacao`, ...). As views `dbo.VW_*` no SQL Server do Bitfin (`VW_CARTEIRA`, `VW_OPERACOES`, `VW_OPERACOES_RENTABILIDADE`, `VW_OPERACAO_SLA`, `VW_COHORT_*`, `VW_DIAS_UTEIS`, `VW_FERIADOS_NACIONAL`) sao **residuo do passado — proibido consumi-las em qualquer camada da solucao** (adapter, service, script, seed). Em PR, referencia a `VW_*` do Bitfin e bloqueador. Mesma regra para as views `control.vw_elig_*` (residuo, decisao 2026-07-07) — analise e KPI (ex.: indice de recompra) nascem no warehouse do GR, nunca em view no banco do ERP.

Adicionar uma fonte nova = novo adapter + registro em `source_catalog` + registro em `tenant_source_config`. **Zero refactor do core.**

### 13.1 Fontes externas federadas (postgres_fdw)

Nem toda fonte externa que popula o GR vira adapter no bounded context `integracoes`. Fontes **publicas** (sem `tenant_id`), com ciclo de ingestao proprio e volume significativo, podem viver em **DB separado no mesmo cluster Postgres** e serem lidas pelo `gr_db` via `postgres_fdw`.

**Criterios pra escolher esse padrao em vez de adapter interno:** dado **publico** (sem tenant — CVM, Receita, Bacen) + volume que justifica DB dedicada + cadencia de ingestao propria (cron) + ciclo de dev/deploy independente (repo proprio).

**Como funciona:** DB dedicada no Postgres da VM 27 (role propria), repo de ETL separado com deploy independente; `gr_db` le via `postgres_fdw` (`IMPORT FOREIGN SCHEMA <fonte> INTO <fonte>_remote`). Metrica derivada anota `source_type='public:<fonte>'` no `decision_log`. **Nao duplicar dado no `gr_db`** — se performance pedir, materialized view local ou indice no banco federado, nunca copy. Mecanica completa: [`docs/integracao-cvm-fidc.md`](./docs/integracao-cvm-fidc.md).

**O que NAO e fonte federada (continua adapter em `modules/integracoes`):** fonte com escopo de tenant (ERP, admin API, bureau pago), fonte transacional cuja sync dispara evento de dominio, ou fonte cuja config varia por tenant.

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

**Por que:** silver e o contrato estavel; bronze e o formato cru do vendor (instavel). Acoplar dominio ao raw acopla a feature ao vendor.

**Quando o silver nao tem o campo:** NAO leia do raw — adicione a coluna no silver, atualize o mapper, re-rode o ETL, e so entao o servico le. Re-mapeamento e barato (raw imutavel, mapper idempotente); acoplar ao raw e caro.

**Em PR:** consumo de raw fora dos mappers e bloqueador. Reviewer rejeita.

---

## 14. Backend -- Proveniencia e auditabilidade (DNA do sistema)

Em mercado financeiro regulado (CVM/ANBIMA/Bacen), **explicabilidade + rastreabilidade valem mais que sofisticacao**. Recomendacao sem trilha de auditoria nao passa em compliance. Isso nao e feature — e estrutural. Disciplina aplicada em TODAS as camadas desde o dia 1.

### 14.1 Modelo `Auditable` (mixin SQLAlchemy)

**Toda** tabela de dominio que armazena dado ingerido de fonte externa herda deste mixin (definicao canonica: `app/shared/auditable.py`). Campos obrigatorios: `source_type` (enum "erp:bitfin", "bureau:serasa_pj", "self_declared", "derived", ...), `source_id`, `source_updated_at`, `ingested_at`, `hash_origem` (SHA256 do payload — deteccao de mudanca), `ingested_by_version` (versao do adapter), `trust_level` (high/medium/low), `collected_by` (uuid nullable).

> **Excecao:** tabelas raw (`wh_<vendor>_raw_*`, ver §13.2) **nao** usam `Auditable` — elas SAO a fonte. Raw carrega proveniencia em colunas dedicadas (`fetched_at`, `fetched_by_version`, `payload_sha256`).

### 14.2 Tabela `decision_log` (append-only)

Toda decisao/calculo/sync registrado aqui, escopado por tenant. **Append-only** (sem UPDATE/DELETE; por convencao) — correcao e nova entrada que referencia a anterior via `supersedes`. Campos completos: ver `docs/AUDITABILIDADE.md` e `app/shared/audit_log/decision_log.py`.

### 14.3 Premissas, versionamento e explicabilidade

- **`premise_set`:** premissas de calculos (CDI, curva, cortes) vivem em tabelas versionadas, nunca em constantes. Cada edicao cria nova versao; projecao referencia o `premise_set_id` usado.
- **Versionamento de regras:** toda regra de negocio, formula ou modelo de score tem versao explicita. v2 coexiste com v1 — nao substitui.
- **Explicabilidade obrigatoria:** score, alerta ou recomendacao registra no `decision_log` os 3-5 fatores que geraram o output. Preferir modelos interpretaveis (regressao logistica, GBM + SHAP); se caixa-preta, registrar inputs + outputs + explicacao gerada.

### 14.5 Trust metadata visivel na UI

Componentes canonicos (existentes):
- **`<ProvenanceFooter />`** — rodape de dashboard ("Dados sincronizados em XX/XX as HH:MM a partir de Bitfin"). Ja canonico, usado nas paginas BI/Controladoria.
- **`<OriginDot />`** + tipo `Provenance` + prop de proveniencia em `KpiCard`/`EChartsCard`/`DataTableShell` — infra do DS pronta; integracao ponta-a-ponta (backend expor `source_type`/adapter no JSON e paginas propagarem) e follow-up em aberto.

Roadmap (ainda NAO implementado — nao referencie como existente): badge de proveniencia por KPI com tooltip completo (source, timestamp, versao do adapter, trust level) e botao "ver premissas" abrindo o `premise_set` usado.

### 14.6 Zero ocultacao na apresentacao — reconciliacao obrigatoria (regra dura)

> Decisao 2026-06-03 (Ricardo): nenhuma tabela, lista ou drill pode **excluir silenciosamente** linhas que um total/headline na mesma tela CONTA. Toda apresentacao de agregado **reconcilia on-screen**: soma do alcancavel = total mostrado. Em mercado regulado, numero que nao bate com o detalhe ao lado destroi a confianca em TODOS os numeros — bug funcional de auditabilidade, nao polish. (Origem: drill PDD que escondia linhas com `|Δ|<R$100` e nao batia com o headline.)

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
- **Sem `print`** em codigo de dominio (scripts CLI podem). Sempre `logging` stdlib com logger nomeado (`logging.getLogger(__name__)`).
- **Zero dependencia de caminho absoluto.** Config via env var.
- **Um endpoint = um responsability.** Nao ha endpoint "generico" que faz varias coisas.

---

## 16. Backend -- Dev workflow e deploy

Local: `.venv` + `.env` + `uvicorn app.main:app --reload`. **Atencao: dev e prod compartilham o MESMO Postgres (VM 27)** — migration "em dev" e migration em prod; tratar tudo com cuidado de producao. Prod: systemd + uvicorn na VM 26 (`gr-api`, `gr-frontend`). Deploy: `ssh gr-vm26 'sudo -n gr-deploy -y'` (idempotente; **NUNCA roda alembic** — `alembic upgrade head` e passo manual separado). **Nao ha CI** (`.github/` nao existe) — os gates sao manuais: `npx tsc --noEmit` + `npm run build` (frontend), `ruff check` + `pytest` (backend), antes de todo commit. Ver `docs/DEV_WORKFLOW.md`.

---

## 17. Banco de dados -- arquitetura

**Postgres dedicado na VM 27** (gr-api e gr-frontend rodam na VM 26), **databases separadas:**

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

- [ ] Componentes so das camadas da §1 (`tremor/`, `charts/`, `design-system/`, `<dominio>/`, `_components/` da rota)? Zero `surfaces/`, `tokens.colors.brand` ou `hero.*` em pagina autenticada (§4.1/§4.2)? Zero lib de UI fora da §2 (lucide, shadcn, @mui, ...)?
- [ ] `cx()` (nao `cn()`); icones `Ri*`; strings de UI em pt-BR; dark mode testado?
- [ ] Cores: paleta §4 como default; fora dela so com handoff/proposta aprovada; badge de status via `tableTokens.badge*` (nao receita inline nova)?
- [ ] Navegacao 3 niveis, sidebar aninha max 1 nivel, estado deep-linkavel via URL (§11.6)?
- [ ] Pagina nasce de pattern canonico da §7 — divergencia tem `// MOTIVO:` no header?
- [ ] Tabela certa pro caso (§6: DataTableShell / DataTable / DenseTable.Series / ExpandableTable) e cells custom com `tableTokens.*`? Fuga tem `// MOTIVO:`?
- [ ] Familia de tabela/filtro usa o CANONICO do catalogo — anatomia de card via `tableTokens.cardWrapper/filterBar/countLabel` (nunca Card p-0 + toolbar artesanal), pager via `TablePagination` no rodape do Card (nunca div em `renderFooter`), filtro na regua `filterControlClass`/`FilterSearch`, status multi via `ShellStatusFilter`, badge via `badge*`? **Se o canonico nao existe para a necessidade, PARE: crie o componente no DS primeiro (componente + README + demo), depois a pagina.**
- [ ] PageHeader com `info` + `subtitle` + `actions` — nao so `title` (§7)? Listagem de cards segue `ListagemCrudCards` com EntityCard canonico (§7)?
- [ ] Zero ocultacao: tabela/drill reconcilia com o headline; corte tem expand-revela-tudo ou linha "Outros (N) · valor"; nenhum contador maior que as linhas alcancaveis (§14.6)?
- [ ] Feedback de progresso em toda acao > ~400ms; backend assincrono visivel AO VIVO; desfecho explicito (§7.3)?
- [ ] `npx tsc --noEmit` + `npm run build` passam? (nao ha CI — o gate e manual, §16)

### Frontend (superficie de marca — `src/app/(auth)/*`, `error.tsx`, `not-found.tsx`)

- [ ] Composta sobre template de `surfaces/` (ex.: `HeroSplitAuth`)? Cores via `tokens.colors.brand`, tipografia via `tokens.typography.hero` — zero hex solto (§4.1/§4.2)?
- [ ] Inline styles so para efeitos nao-expressaveis em Tailwind, sempre referenciando tokens (§5)?
- [ ] Form com `react-hook-form` + `zod` + primitivos Tremor? `prefers-reduced-motion` respeitado? Dark mode testado?
- [ ] `npx tsc --noEmit` + `npm run build` passam?

### Backend (endpoint/servico)

- [ ] Endpoint autenticado (`get_current_principal`) + `require_module(Module.X, Permission.Y)` (§12)? Query escopada por tenant via dependency (§10)?
- [ ] Teste de 403 para endpoint novo + teste de isolamento para service novo que toca tabela multi-tenant (§10.4)?
- [ ] Dado de warehouse herda `Auditable`; decisao/calculo registra no `decision_log` (§14)?
- [ ] Le APENAS silver, nunca raw (§13.2.1)? Service de BI passa TODO agregado por `_apply_filters` (§7.2)?
- [ ] Zero ocultacao em drill/listagem analitica — default do endpoint mostra tudo (§14.6)?
- [ ] Import cruzado so via `modules/Y/public.py` (§11.3)? Modulo novo exige autorizacao + enum `Module` + §11.1?
- [ ] Type hints completos (zero `any`); secret novo no `.env.example`; migration Alembic se mudou modelo?
- [ ] `ruff check` + `pytest` passam?

### Adapter novo

- [ ] Segue o layout da §13 (client/queries/mappers/etl + `version.py` com `ADAPTER_VERSION` registrado em toda linha)?
- [ ] Output em modelo canonico; config via `tenant_source_config` (zero hardcode)?
- [ ] Sync registrado no `decision_log`; entrada em `source_catalog`; teste de integracao (mock/sandbox)?

### Endpoint / feature de IA / camada agentica (§19)

- [ ] Endpoint `/api/v1/ai/*` usa `require_ai(AICapability.X)` (nao `require_module`); admin global usa `require_system_maintainer` + `require_module(ADMIN, ADMIN)` (§19.1)?
- [ ] Toda chamada de IA grava `decision_log` + `ai_usage_event`; mensagem do usuario passa por redaction antes do LLM (§19.5/§19.9)?
- [ ] Credenciais via `ai_provider_credential` (Fernet); SSE via `fetch`+`ReadableStream` (nunca `EventSource`); markdown IA via `react-markdown`; creditos via `<AIQuotaIndicator />` (§19.3/§19.7/§19.8)?
- [ ] Vocabulario: `agents` / `tools` / `workflows` / `memory` — nunca "skill" (= comando Claude Code) nem "playbook" (aposentado 2026-07-06) (§19.0)?
- [ ] Agente novo: row em `agent_definition` + ativacao (`_active`) via migration; `SpecialistAgentSpec` no catalog quando ha `output_schema`; persona reusada; prompt versionado em `ai_prompt` (`<modulo>.<agente>`); `allowed_tools` declarado; `cross_module=true` so com justificativa (§19.12)?
- [ ] Tool nova: `@register_tool(module=, min_permission=, cost_hint=)` em `app/agentic/tools/<modulo>/` ou `shared/`; recebe `ScopedContext`; filtragem via registry, nao na tool (§19.0)?
- [ ] Workflow novo: graph JSONB declarativo em `workflow_definition` + active pointer; tag `module` no metadata; dry-run e `_validate` testados; execucao gera `workflow_run` + `workflow_node_run` + `decision_log` (§19.10)?
- [ ] Memoria: toda leitura filtra `tenant_id` PRIMEIRO; modulo X nao ve memoria de Y sem `cross_module`; trace via SSE (chat) ou `agent_session_step`/`workflow_node_run` (batch); pgvector so com caso de uso concreto (§19.11)?
- [ ] Cross-modulo: tools via `ToolRegistry.get_available(scope)`; workflows por nome via `workflow_definition_active` — nunca import direto (§11.3)?

Se qualquer item reprovar, **nao corrija pontualmente** — pare e revise a mudanca inteira.

---

## 19. Camada agentica -- arquitetura horizontal estrutural

> Strata e plataforma agentica. A camada agentica — **motor + tools + workflows + memoria + agentes** — e horizontal e atravessa todos os 9 modulos. Os modulos sao "pacotes de dominio" que registram tools e workflows proprios; o motor de agente e unico. Telas e relatorios sao interfaces sobre o nucleo, nao o nucleo. Implementacao que parecer "modulo X com chatbot dentro" esta errada — pare e revise.
>
> Decisao 2026-04-30: IA tratada como capability transversal (nao decimo modulo) — mantem enum `Module` fechado (§11.1). Decisao 2026-05-20: a "capability IA" e reposicionada como **camada agentica estrutural**. Decisao 2026-07-06 (Ricardo): o termo canonico do primitivo de orquestracao e **"workflow"** — em codigo, DB, rotas, doc e UI; "playbook" (experimento de vocabulario 2026-05→07) foi aposentado.

### 19.0 Vocabulario canonico e blocos da camada agentica

Quatro blocos. Use **exatamente** esses termos em codigo, tabela, endpoint, doc e comentario. Implementacao que invente nome novo (ex.: "skill" ou "playbook" para workflow, "ferramenta" para tool) deve ser refeita.

| Bloco | Definicao | Onde mora |
|---|---|---|
| **Agents** | Motor de raciocinio com persona + politica + escopo. Cada agente carrega `module: Module` como tag (nao como pasta). | DB-first: `agent_definition`/`_active` + `agent_persona`/`_active` + `agent_expertise`/`_active` (models em `app/shared/ai/models/`). Codigo: `app/agentic/engine/catalog.py` (`SpecialistAgentSpec` + output_schemas) + `app/agentic/agents/registry.py` |
| **Tools** | Funcoes atomicas — queries SQL pre-produzidas, calculos, equacoes regulatorias, APIs externas (Serasa, Quod, BACEN), MCPs, geradores de relatorio | `app/agentic/tools/<modulo>/` com decorator `@register_tool(module=, min_permission=, cost_hint=)` |
| **Workflows** | Orquestracoes declarativas versionadas (graph JSONB imutavel + active pointer apontando versao). Equivale ao "skill/playbook" do mercado — aqui o termo e workflow. | `app/agentic/workflows/` (engine, nodes, schemas, services) + `workflow_definition`/`_active` (DB) |
| **Memory** | Tres camadas: **session** (curto prazo, durante 1 analise — ENTREGUE) + **tenant** (medio prazo, preferencias + padroes — parcial) + **global** anonimizada (longo prazo, **futuro** com parecer juridico) | `app/agentic/memory/` |

**Vocabulario duro:**

- "**Skill**" no projeto = comando Claude Code (audit-page-consistency, create-list-page, etc — invocado via `Skill` tool). **NAO usar "skill" para workflow agentico** — sempre **"workflow"**. "**Playbook**" e termo aposentado (2026-07-06) — nao reintroduzir em codigo, doc ou UI.
- "**Persona**" = papel de negocio reutilizavel ("Controller Senior", "Analista de Credito FIDC"). Vive em `agent_persona` separada de `ai_prompt` para reuso entre agentes.
- "**Tag de modulo**" em agente/workflow nao limita invocacao; define o **scope default** (RBAC + tools disponiveis + persona). Chamada cross-modulo e explicita (`cross_module=true` + auditoria).

**Principio chave:** o motor nao conhece os agentes nem as tools. Em runtime, recebe `AgentDefinition` + `ScopedContext(tenant, empresa, user, module, permissions, db)` + objetivo, executa. Adicionar agente/tool/workflow novo = arquivo + seed em DB. **Zero mudanca no engine.**

### 19.1 Estrutura paralela ao modulo

- **`tenant_ai_subscription`** -- entitlement do tenant (enabled, plan_ref, monthly_credit_quota, hard_cap_brl). Espelha `tenant_module_subscription`.
- **`user_ai_permission`** -- permissao do user (NONE/READ/WRITE/ADMIN via enum `AICapability`). Espelha `user_module_permission`.
- **`require_ai(AICapability.X)`** em `app/core/ai_guard.py` -- guarda paralelo ao `require_module`. Aplica em endpoints sob `/api/v1/ai/*`.
- **`require_system_maintainer()`** em `app/core/system_maintainer_guard.py` -- gating de endpoints globais (gestao de keys + tier de tenants + prompt library). Compoe com `require_module(Module.ADMIN, Permission.ADMIN)`.

### 19.2 Tabela `tenants.is_system_maintainer` (excecao §10)

Coluna boolean com **partial unique index** garantindo no maximo 1 tenant marcado. Apenas membros desse tenant podem editar credenciais globais (`ai_provider_credential`) e gerir tier dos demais tenants. **Nao** confunda com role admin do proprio tenant.

### 19.3 Adapter LLM (segue §13)

Provedores externos (Anthropic, OpenAI) sao adapters versionados em `app/modules/integracoes/adapters/llm/<provider>/` (`ADAPTER_VERSION`). **Credenciais sao globais** (`ai_provider_credential`, sem `tenant_id`), cifradas com envelope Fernet (`app.shared.crypto`); ZDR exigido em prod (`zdr_enabled` bloqueia chamada quando false).

**Dois caminhos de invocacao Anthropic:** (1) **cliente HTTP custom** do adapter (httpx + SSE) para chat simples/insights com streaming ao frontend; (2) **SDK oficial `anthropic`** em `app/agentic/engine/runtime.py` para specialist agents — tool loop nativo `tool_use → tool_result` ate `end_turn` (cap `_MAX_TOOL_ITERATIONS=12`), tools = `AgentTool` (`app/agentic/tools/_base.py`). Ambos usam o mesmo storage de credencial e gravam `decision_log` + `ai_usage_event` (cache_read/cache_creation separados). Historia e roadmap (migracao de `llm/` para `app/agentic/engine/llm/`): [`docs/arquitetura-agentica.md`](./docs/arquitetura-agentica.md).

### 19.4 Prompt library versionada (DB-backed)

**Decisao 2026-04-30:** prompts saem do codigo e passam a viver em DB para curadoria continua sem deploy. Time de produto/IA pode iterar sem PR; rollback de 1 click.

- **Storage**: tabela `ai_prompt` (id, name, version, system_text, user_context_template, assistant_prime, model, fallback_model, temperature, max_tokens, cache_strategy, description, created_by, created_at, archived_at). Naming: `<categoria>.<nome>` (ex.: `chat.fidc_geral`, `insight.carteira_3bullets`).
- **Imutabilidade**: `(name, version)` UNIQUE. Toda edicao **cria nova versao** copiando a base + patches. Versao base nunca muda — preserva audit trail.
- **Versao ativa**: tabela `ai_prompt_active` (uma linha por nome) aponta para a versao em producao. Trocar = 1 UPDATE (rollback de 1 click sem deploy).
- **Soft-delete**: `archived_at` marca versao como nao-ativavel. Versao ativa nao pode ser arquivada (constraint).
- **Repository**: `app/agentic/engine/prompts/repository.py::resolve(db, name, version="active")` retorna `Prompt` instanciado a partir da row. Servicos chamam APENAS via repository — nunca leem `ai_prompt` direto.
- **Edicao**: via `/admin/ia/prompts` (system maintainer only). CRUD versionado + ativacao + archive + preview (render sem chamar LLM). Variaveis `{nome}` via `str.format` no `user_context_template`/`assistant_prime`.
- **Auditoria**: a versao usada vai automaticamente em `decision_log.rule_or_model_version` (`<adapter_version>+<prompt.full_id>`) e em `ai_usage_event.prompt_template_version`.

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
- **Admin**: rotas em `/admin/ia/{agents,expertises,personas,prompts,providers,tools}`. Visiveis somente quando `tenant.is_system_maintainer === true` (campo em `/auth/me`).

### 19.8 Billing (creditos abstraidos)

UI nunca expoe token-count -- expoe **creditos**. 1 chat ~= `tokens_input/1000 + tokens_output/100` creditos; 1 insight = 5 creditos (flat); 1 prompt-injection check = 1 credito. Tier mensal incluso em `monthly_credit_quota`; overage em `topup` (pre-pago avulso). Hard cap diario em BRL via `tenant_ai_subscription.hard_cap_brl`.

### 19.9 LGPD / dados pessoais

PII (CPF, CNPJ, conta-agencia, email) e redactada antes de subir ao LLM via `services/redaction.py` (regex + check digit no MVP, Microsoft Presidio na Fase 2). Mensagens armazenam `text_redacted` + `text_encrypted` (versao com PII original cifrada via envelope Fernet, acesso restrito a auditoria com trilha em `decision_log`).

### 19.10 Workflows (orquestracao declarativa)

O engine de workflows vive em **`app/agentic/workflows/`** (primitivo horizontal; `app/modules/credito/workflows/` nao existe mais). Cada modulo registra seus templates; o engine e unico (`services/engine.py`).

**Vocabulario (decisao 2026-07-06):** **"workflow" em TUDO** — classes Python (`WorkflowDefinition`, `WorkflowRun`, `WorkflowGraph`), tabelas DB (`workflow_*`), rotas (`/api/v1/credito/workflows/*`) e copy da UI ("Workflows"). "Playbook" foi aposentado; "skill" continua reservado a comandos Claude Code (§19.0).

**Modelagem (tabelas reais):** `workflow_definition` — name, version, module (tag), tenant_id NULL=global, graph JSONB (nodes + edges + variable bindings); `(name, version)` UNIQUE, **imutavel** (edicao = nova versao) — + `workflow_definition_active` (uma linha por tenant+name; rollback de 1 UPDATE, espelha `ai_prompt_active`). Tipos de node (`specialist_agent`, `bureau_query`, `consolidator`, `join` com `join_mode=all|any`, `conditional_branch`, `human_input`, ...): catalogo real em `app/agentic/workflows/nodes/`. Edges com `condition` via template (`{{node.X.output.value}} >= 700`); input bindings tipados resolvidos pelo template resolver. Custom workflows por tenant = `tenant_id NOT NULL`.

**Engine (endpoints reais):** CRUD/versionamento/ativacao em **`/api/v1/credito/workflows/*`**; execucao disparada via dossie de credito (cria/resume o run); **dry-run** em `POST .../workflows/{id}/dry-run` (sandbox com mocks — sem DB write, sem API paga); **validacao semantica** em `POST .../workflows/_validate` (erros + `produced_by_node`, consumido pelo editor visual). Endpoint generico cross-modulo ainda NAO existe (roadmap). Cada execucao gera `workflow_run` + `workflow_node_run` (trace per-node) + `decision_log` + `ai_usage_event`. **Engine e duravel** (suspend/resume em prod; `human_input` pausa o run). Nodes em nivel paralelo rodam **sequencialmente** (AsyncSession nao e concorrente — nao re-introduzir `gather`).

**Quando NAO usar workflow:** chat conversacional simples (sem orquestracao) — usa motor de agente direto, sem grafo. Insight pontual (1 tool call + sintese) — mesma coisa. Workflow e para **orquestracao multi-step com grafo**, nao para qualquer chamada de IA.

### 19.11 Memoria de sessao

**Estado: camada session ENTREGUE.** `AnalysisSession` vive em `app/agentic/memory/_base.py` (+ `scratchpad.py`, `step_cache.py`, `tools.py`, `persistence.py`), e criada pelo engine a cada execucao de run, e persiste em `agent_session` + `agent_session_step`.

| Camada | Escopo | Implementacao | Status |
|---|---|---|---|
| **Session** (curto prazo) | 1 analise / 1 dossie / 1 turn agentico | `AnalysisSession` (`memory/_base.py`): working memory + scratchpad + step cache (tool com mesmos parametros nao reexecuta) + step trace (alimenta `AgentLiveStatus`). Persistencia em `agent_session`/`agent_session_step` | ENTREGUE |
| **Tenant** (medio prazo) | Preferencias do tenant + padroes aprendidos + limites internos | So `ai_conversation_summary` existe (sumarizacao de chat). Tabela `tenant_memory` dedicada nao existe | PARCIAL |
| **Global** (longo prazo) | Padroes anonimizados cross-tenant | A definir + **parecer juridico LGPD/BACEN obrigatorio antes** | DEFERIDO |

**SSE em tempo real:** durante o tool loop, motor emite frames `tool_use` / `tool_result` no stream. Frontend renderiza via `AgentLiveStatus`.

**Isolamento (regra dura):**

- Toda leitura de session/tenant memory **filtra por `tenant_id`** antes de qualquer outra operacao. Vazamento entre tenants = falha critica de compliance.
- Memoria de modulo X nao e visivel a agente de modulo Y, exceto quando agente tem `cross_module=true`.
- Expiracao: session expira ao fim da analise (default 1h). Tenant memory persiste indefinidamente mas auditavel.

**Retrieval semantico (futuro):** quando virar prioridade, tabela ganha `embedding vector(1536)` (pgvector instalado, hoje nao usado em IA). **Nao implementar ate caso de uso concreto pedir.**

### 19.12 Catalogo central de agentes

Agentes sao **centralizados** (catalogo unico DB-first, **nao espalhados por modulo**). Cada agente carrega `module` como **tag** no metadata — RBAC, tools disponiveis, persona, billing, metricas agrupam por essa tag.

**Por que centralizar (decisao 2026-05-20):** camada horizontal por tese; governanca coesa com `ai_prompt`; UI admin lista flat; marketplace por tenant e reuso cross-modulo exigem catalogo unico. Racional completo: [`docs/arquitetura-agentica.md`](./docs/arquitetura-agentica.md).

**Modelagem hibrida (texto/config em DB + output_schema em codigo):**

- **Em DB** (`agent_definition` + `agent_definition_active`, models em `app/shared/ai/models/`): name, version, module (tag), persona_id (FK pra `agent_persona`), expertise_ids (FKs pra `agent_expertise`), prompt_name (aponta pra `ai_prompt`), allowed_tools (NULL=default do CATALOG / []=sem tools / [...]=override editavel pela UI sem deploy), overrides de model/fallback_model/temperature/max_tokens, cross_module bool, credit_hint, tenant_id NULL=global, archived_at.
- **Em codigo** (`app/agentic/engine/catalog.py`): `SpecialistAgentSpec` por agente — prompt, tools default, `output_schema` Pydantic (fica em codigo porque o orquestrador faz parsing tipado), modelo preferido, thinking budget, timeout. Registrado no `CATALOG`.
- **Persona separada** (`agent_persona`/`_active`): papel de negocio reutilizavel ("Controller Senior") com role_block injetado no prompt. **Expertise separada** (`agent_expertise`/`_active`): blocos de conhecimento componiveis. Ambas versionadas espelhando `ai_prompt`.

**Layout fisico (real):**

```
app/agentic/
├── _scope.py                # ScopedContext
├── engine/                  # runtime unico: runtime.py (tool loop SDK anthropic),
│   │                        #   catalog.py (CATALOG de SpecialistAgentSpec),
│   │                        #   output_schemas.py, prompts/ (repository), model_resolver.py
├── agents/                  # registry.py (AgentRegistry — resolve DB-first),
│   │                        #   _base.py (ResolvedAgent), _compose.py
├── workflows/               # engine de workflows: models/ (tabelas workflow_*),
│   │                        #   nodes/, services/ (engine, dry_run, graph_validator),
│   │                        #   schemas/, public.py
├── tools/                   # registry.py (ToolRegistry.get_available(scope)),
│   │                        #   _base.py (AgentTool + @register_tool),
│   │                        #   credito/, controladoria/, shared/
└── memory/                  # _base.py (AnalysisSession), scratchpad.py,
                             #   step_cache.py, tools.py, persistence.py
```

(Models SQLAlchemy da familia agentica vivem em `app/shared/ai/models/`; adapters LLM em `app/modules/integracoes/adapters/llm/` — ver §19.3.)

**Invocacao tipica:** `AgentRegistry.get(name, scope)` devolve um `ResolvedAgent` (row de `agent_definition` + persona + expertises + prompt + metadados do CATALOG), consumido por `runtime.run_specialist_agent(...)`. Trace de tool_use vai por SSE; audit grava `decision_log` + `ai_usage_event`.

**`decision_log.rule_or_model_version`** e a string composta `agente@versao + persona@versao + expertises@versao + prompt@versao` (`ResolvedAgent.audit_version`) — uma chave conta toda a historia da decisao.

Roadmap da camada (endpoint generico de workflow, tenant/global memory, pgvector, `tenant_agent_override`, migracao `llm/`): [`docs/arquitetura-agentica.md`](./docs/arquitetura-agentica.md) §6.
