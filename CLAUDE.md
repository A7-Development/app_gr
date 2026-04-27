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
> **Regras que CONTINUAM em vigor (nao sao suspensas):**
>
> - §2 **stack obrigatoria** — sem novas libs sem autorizacao explicita do usuario.
> - §3 **arquitetura em 6 camadas** — `tremor/` continua nao-editavel, `surfaces/` continua sem importar de `components/dashboard`, etc.
> - §11.1 **enum de modulos fechado** — sem modulo novo sem autorizacao.
> - §11.3 **bounded contexts (backend)** — cross-import entre modulos so via `public.py`.
> - §11.6 **hierarquia 3 niveis** de navegacao (L1/L2/L3) — sidebar nao aninha, max 3 niveis.
> - §10 **multi-tenant absoluto** (backend) — toda tabela tem `tenant_id`, toda query escopada.
> - §13 **adapter pattern** (backend).
> - §14 **proveniencia + auditabilidade** (DNA do sistema).
> - Idioma da UI em pt-BR, alias `@/*` nos imports, `cx()` em vez de `cn()`, icones Remix, fonte Geist.
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

---

## 1. Palavra de ordem: **padrao e consistencia visual**

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

| Area | Obrigatorio | Proibido |
|---|---|---|
| Framework | Next.js 14.2.x (App Router) | pages/ router, Remix, Vite |
| Design System | Tremor Raw | shadcn/ui, MUI, Chakra, Ant, Bootstrap, Mantine |
| Styling | Tailwind CSS v4 + tokens do Tremor | CSS-in-JS, styled-components, emotion, CSS modules |
| Utilitario de classes | `cx()` de `@/lib/utils` | `cn()`, `clsx()` direto, `classnames` |
| Variantes | `tailwind-variants` | `class-variance-authority`, objetos de variantes manuais |
| Icones | `@remixicon/react` (Ri*) | `lucide-react`, `react-icons`, `heroicons`, SVG ad-hoc |
| Fonte | `GeistSans` | Inter, Roboto, Arial, qualquer outra |
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

Instalar qualquer biblioteca fora desta tabela exige autorizacao explicita do usuario no chat.

---

## 3. Arquitetura em 6 camadas (Strata Design System)

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
                                       DataTable, DrillDownSheet, CommandPalette, EChartsCard,
                                       ApprovalQueueBadge, Sidebar.
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
- **Transacionais** (cessoes, cedentes, sacados, listagens grandes) — usar `DataTable` em `src/design-system/components/DataTable/` (TanStack Table v8 + TanStack Virtual + 3 densidades + ColumnManager + ExportMenu + 9 cell renderers tipados). Virtualizacao automatica se rows > 100.
- **Series temporais FIDC** (PL, cotas, rentabilidade mes a mes) — usar `CompactSeriesTable` em `src/design-system/components/CompactSeriesTable.tsx` (Austin-style, density compact default).
- Nunca AG Grid, nunca data grid externo, nunca `Table` do Tremor cru em pagina (Tremor `Table` so como primitivo dentro de DataTable/CompactSeriesTable).

---

## 7. Paginas e rotas — Patterns canonicos e Surfaces

Toda **pagina autenticada** (`src/app/(app)/*`) **deve preferir** comecar de um dos patterns canonicos em `src/design-system/patterns/`:

- **DashboardBiPadrao** — Pagina canonica do BI (handoff bi-padrao 2026-04-26). 5 zonas: Z1 PageHeader (titulo + IA + acoes) · Z2 TabNavigation L3 · Z3 FilterBar sticky · Z4 conteudo (InsightBar + KpiStrip 5 KPIs + grid 2/3+1/3 + grid 3-col + DataTable) · Z5 ProvenanceFooter. Lateral: AIPanel violeta in-layout + DrillDownSheet. Use para qualquer dashboard analitico (BI, Controladoria, Risco) que envolva KPIs + charts + tabela com drill-down.
- **DashboardOperacional** — PageHeader + FilterBar + KpiStrip (4 KPIs) + Grid 2×2 EChartsCards + DataTable de atividade recente. Use para dashboards mais simples sem AI panel (`/bi/operacoes` legado, telas operacionais).
- **ListagemComDrilldown** — PageHeader + FilterBar + DataTable + DrillDownSheet (URL-synced via `?selected=ID`). Use para Cessoes, Cedentes, Sacados, Cobranca, Reconciliacao, Eventos.

Toda **pagina nao-autenticada / superficie de marca** (`src/app/(auth)/*`, `src/app/error.tsx`, `not-found.tsx`, futuras paginas publicas) nasce de um template em `src/design-system/surfaces/`:

- **HeroSplitAuth** — Layout 60/40 com hero zone (gradiente navy + glow laranja + pattern de linhas + logo + headline + trust signals) a esquerda e zona de form a direita. Use para `/login`, `/recover-password`, `/onboarding/welcome`.
- (futuros) `SplashScreen`, `ErrorPage404`, `ErrorPage500`, `MarketingHero`.

Patterns e surfaces sao **copy-paste-edit** — nao componentes black-box. Copie o pattern para a pasta da pagina, adapte titulo/copy/mocks/charts ao dominio. Os comentarios `HOW TO ADAPT:` no topo de cada arquivo guiam a customizacao. Pages que copiam um pattern e divergem do template sao esperadas, nao excecao.

**Header de dashboard — set canonico de acoes (handoff bi-padrao 2026-04-26):** toda pagina derivada de `DashboardBiPadrao` usa `<DashboardHeaderActions>` no slot `actions` do `<PageHeader>`. O composite renderiza, em ordem fixa: `[DarkToggle, Compartilhar, Exportar, Mais, IA]`. DarkToggle e IA sao sempre presentes; Share/Export/More sao omitidos quando o callback nao e passado. Substituir por `<Button>` solto ou conjunto custom de botoes e regressao — fecha a porta para que cada pagina invente seu proprio header. Para acoes secundarias (Copiar link, Duplicar, Imprimir, etc.), use o slot `more={[...]}`.

Antes de escrever uma `page.tsx` nova, pergunte:
- E pagina autenticada? Qual **pattern** aplica? (BI/Controladoria/Risco com IA → `DashboardBiPadrao`. Listagem → `ListagemComDrilldown`.)
- E pagina nao-autenticada / pagina de erro / landing? Qual **surface** aplica?

Se nenhum pattern atual couber, componha direto a partir de `design-system/components/` + `tremor/`. Se a estrutura for util a outras telas, **promova-a a pattern** (novo arquivo em `patterns/`) — patterns nascem de pages reais, nao de especulacao.

A rota `/design` (dev-only via `process.env.NODE_ENV !== "production"`) mostra todos os tokens, primitives, components, patterns **e surfaces** ao vivo. Util como referencia rapida.

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

### 11.1 Os 8 modulos oficiais (enum fechado)

| Modulo | Proposito |
|---|---|
| `bi` | Dashboards, analises, cruzamentos (MVP) |
| `cadastros` | Empresas, pessoas, cedentes, sacados |
| `operacoes` | Contratos, titulos, pagamentos, recebimentos |
| `controladoria` | Contabilidade, plano de contas, DRE, balancete |
| `risco` | Scoring, limites, PDD, stress, concentracao |
| `integracoes` | Adapters, catalogo de fontes, sync, reconciliacao |
| `laboratorio` | Teses de dados, correlacoes, experimentos |
| `admin` | Tenants, users, roles, subscriptions, config sistemica |

Adicionar um nono modulo exige **autorizacao explicita** + atualizacao deste documento + atualizacao do enum `Module` em `app/core/enums.py`.

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
| **L1** | Modulo (um dos 8) | `ModuleSwitcher` no topo da sidebar (dropdown) | `DropdownMenu` |
| **L2** | Secao/funcionalidade do modulo | Lista plana de links na sidebar (do modulo ativo) | `SidebarLink` |
| **L3** | Abertura/drill-down/perspectiva | Tabs horizontais no topo da pagina | `TabNavigation` + `TabNavigationLink` |

**Exemplo canonico — modulo BI:**

```
L1 (dropdown no topo): [BI ▾]
    L2 (sidebar): Operacoes   → /bi/operacoes      → L3 tabs: Visao geral | Por produto | ...
                  Carteira    → /bi/carteira       → L3 tabs: Total | Por produto | Por cedente | Aging
                  Fluxo caixa → /bi/fluxo-caixa    → L3 tabs: ...
                  Benchmark   → /bi/benchmark      → L3 tabs: Visao geral | PDD | Evolucao | Fundos
                                (dados publicos CVM FIDC — ver docs/integracao-cvm-fidc.md)
```

**Regras duras:**

1. **Maximo 3 niveis.** Se surgir L4, o modulo precisa ser dividido OU aquilo vira filtro/modal/drawer — nunca 4o nivel de navegacao.
2. **Sidebar nao aninha.** Sidebar mostra SO as secoes L2 do modulo ativo, como lista plana — sem grupos colapsaveis, sem arvore clicavel, sem expand/collapse. L3 sempre e `TabNavigation` na pagina.
   - **Captions tipograficos sao permitidos:** se `ModuleSection.groupLabel` for definido, a sidebar renderiza o texto como separador visual antes do primeiro item do grupo (ex.: "OPERACAO", "FINANCEIRO"). Captions sao **apenas labels textuais nao clicaveis** — nao introduzem hierarquia, nao expandem/colapsam, nao alteram a contagem de niveis. Servem para densificar listas longas dentro de um modulo (ex.: BI agrupa "Visao geral / Operacao / Financeiro / Analise").
3. **URL e a fonte unica da verdade.** Modulo, secao, tab e filtros sao todos deep-linkaveis (ex.: `/bi/carteira?tab=por-produto&periodo=30d`). O modulo ativo e inferido do pathname.
4. **Troca entre modulos (L1) e SEMPRE pelo `ModuleSwitcher`** (dropdown no topo da sidebar). O switcher lista os modulos com subscription + permissao; demais ficam em "Em breve" (disabled). Sem icon rail, sem module picker separado do header, sem tabs de modulo.
5. **Breadcrumbs sticky no header** mostram o path: `Modulo > Secao > Pagina` (L1 > L2 > L3).

**Active state (implementacao):**

- L1 ativo: `ModuleSwitcher` exibe o modulo inferido de `getActiveModule(pathname)` (em `src/lib/modules.ts`) com avatar colorido + nome + permissao.
- L2 ativo: `SidebarLink` com `isActive={pathname.startsWith(section.href)}` — borda/texto azul via `data-active=true`.
- L3 ativo: `TabNavigationLink active={pathname includes tab}` ou comparacao com search param.

**Avatars de modulo — cor canonica (handoff v2, 2026-04-24):**

| Modulo | Token | Classe | Hex |
|---|---|---|---|
| BI | `gray` | `bg-gray-800` | `#1F2937` |
| Cadastros | `blue` | `bg-blue-500` | `#3B82F6` |
| Operacoes | `emerald` | `bg-emerald-500` | `#10B981` |
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
- `Module` — um valor por modulo: `BI`, `CADASTROS`, `OPERACOES`, `CONTROLADORIA`, `RISCO`, `INTEGRACOES`, `LABORATORIO`, `ADMIN`
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
- `app/adapters/bureau/serasa_refinho/` — Serasa Refinho (pos-MVP)
- `app/adapters/document/nfe/` — parser XML de NFe (pos-MVP)

**Regras do adapter:**

1. **Um adapter por ENDPOINT/API, nao por provedor.** Refinho e PFIN sao adapters separados mesmo sendo ambos Serasa.
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
- Raw inclui o vendor: `wh_qitech_raw_outros_fundos`, `wh_serasa_refinho_raw_consulta`
- Canonico nao inclui vendor: `wh_posicao_cota_fundo`, `wh_titulo`

---

## 14. Backend -- Proveniencia e auditabilidade (DNA do sistema)

Em mercado financeiro regulado (CVM/ANBIMA/Bacen), **explicabilidade + rastreabilidade valem mais que sofisticacao**. Recomendacao sem trilha de auditoria nao passa em compliance. Isso nao e feature — e estrutural. Disciplina aplicada em TODAS as camadas desde o dia 1.

### 14.1 Modelo `Auditable` (mixin SQLAlchemy)

**Toda** tabela de dominio que armazena dado ingerido de fonte externa herda deste mixin. Campos obrigatorios:

> **Excecao:** tabelas raw (`wh_<vendor>_raw_*`, ver §13.2) **nao** usam `Auditable` — elas sao a fonte, nao referenciam outra fonte upstream. Raw carrega proveniencia em colunas dedicadas (`fetched_at`, `fetched_by_version`, `payload_sha256`).

| Campo | Tipo | Proposito |
|---|---|---|
| `source_type` | enum | "erp:bitfin", "admin:qitech", "bureau:serasa_refinho", "self_declared", "peer_declared", "internal_note", "derived" |
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
- [ ] **Sidebar nao aninha em 3+ niveis (L3 sempre como tabs na pagina, nunca sub-sub-item)?**
- [ ] **Estado de navegacao (modulo/secao/tab/filtros) e deep-linkavel via URL?**
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

Se qualquer item reprovar, **nao corrija pontualmente** — pare e revise a mudanca inteira.
