# Components

Camada de composicao -- 38 componentes que compoem `tremor/*` + `charts/*` + `tokens/*` em algo de dominio FIDC. Esta e a unica fonte de componentes para a UI da aplicacao alem dos primitivos Tremor.

## Mapa por categoria

### Strata canonicos (entregues no handoff v2)

| Componente | Pasta | Proposito |
|---|---|---|
| **StatusPill** | `StatusPill/` | Lifecycle FIDC: em-dia, atrasado-30, atrasado-60, inadimplente, recomprado, liquidado. Variantes `pill` e `dot`. |
| **ApprovalQueueBadge** | `ApprovalQueueBadge/` | Badge vermelho que pulsa, p/ filas pendentes (Sidebar, headers). |
| **KpiBand** | `KpiBand/` | **KPI CANONICO Strata (decisao Ricardo 2026-06-12)**: banda CONTINUA de N KPIs equivalentes (`items[]`) — eyebrow 10px uppercase tracking 0.05em; valor 22px semibold tabular SEMPRE NEUTRO (decisao 2026-05-21: so o delta carrega cor, tone positive/negative/neutral); sub 12px gray; divider PARCIAL entre colunas (top-3/bottom-3, gray-100); mobile empilha. NAO sao cards individuais; sem sparkline. KPI cujo numero e de um grafico -> `headerKpi` no card do chart (nunca duplicar). Variante local com status pills: CotaSubStatusBand (cota-sub). |
| **KpiCard / KpiStrip / Sparkline / KpiIntensity** | `KpiStrip/` | LEGADO para paginas-resumo com sparkline e "Metricas Complementares" (variant compact, handoff). Para KPI padrao de pagina BI use `KpiTile`. KPI antigo Strata: layout side-by-side (texto esquerda · sparkline lateral compacto direita · OriginDot rodape). 3 variantes (compact/default/hero). Sparkline com callout pill opcional + endpoint dot. **KpiStrip canonico**: card full-width (encosta nas bordas do container pai, sem `mx-auto`/`max-w-*`); em xl usa `flex justify-between` — KPIs com largura natural e espaco distribuido uniformemente entre eles; em <xl cai para grid (1 col mobile, 2 cols sm). Prop `cols` (default 5) e anotacao semantica — em xl o layout nao depende dela. Presets em `FIDC_KPI_META`. |
| **FilterBar / FilterChip / FilterSearch / RemovableChip / MoreFiltersButton / SavedViewsDropdown** | `FilterBar/` | Z3 dos patterns DashboardBiPadrao/DashboardOperacional/ListagemComDrilldown. **Anatomy** (refinamento 2026-05-01): Card branco em faixa sticky `bg-gray-50` com `shadow-xs` quando scrolled — mesma estrutura de `/credito/workflows`. **Controles canonicos**: todos a `h-[30px] px-2.5 text-[13px]` (alinhado com `HEADER_BTN_CLASS`). **Per-element coloring**: cor no `<button>` raiz e proibida — aplique no ícone (`text-gray-500`/`text-blue-500`), label (`text-[11px] text-gray-500`) e valor (`font-medium text-gray-900`/`text-blue-700`) separadamente. SavedViews em localStorage. **Limitacao conhecida**: `MoreFiltersButton` ainda nao suporta `asChild` — paginas que precisam de Popover trigger duplicam a anatomy (ver CLAUDE.md §7.1). |
| **DataTable + 9 cells** | `DataTable/` | TanStack Table v8 + TanStack Virtual (auto > 100 rows). 3 densidades, ColumnManager (Popover), ExportMenu. Cells: `CurrencyCell`, `PercentageCell`, `DateCell`, `StatusCell`, `IdCell`, `CpfCnpjCell`, `RelationshipCell` (HoverCard), `SparklineCell`, `ProgressCell`. **Todas as cells canonicas usam `tableTokens.*` para tipografia/cor — ver `tokens/table.ts`.** |
| **DataTableShell** | `DataTableShell/` | Wrapper canonico de **listagens CRUD/admin tabulares** (Provedores, Usuarios, Etiquetas...). Encapsula `Card + FilterSearch + SegmentSwitch + counter + DataTable` num unico componente. Props: `data`, `columns`, `search`, `segments` (opcoes com `filter` predicado), `itemNoun`, `emptyState`, `onRowClick`. Garante layout/gap/ordem identicos entre paginas. **Use quando cada entidade tem identidade tabular (compara linha-a-linha)** e listagem e ~5-200 rows. Para entidades com identidade VISUAL (workflows, agentes, dashboards salvos), use o pattern `ListagemCrudCards` em `design-system/patterns/` — cards em vez de tabela. Decisao em CLAUDE.md §7. Demo isolada: `/preview/data-table-shell`. |
| **DrillDownSheet** | `DrillDownSheet/` | Compound API: `.Header`, `.Hero`, `.Tabs`, `.Body`, `.PropertyList`, `.LinkedObjects`, `.Timeline`, `.SectionLabel`, `.Footer`, `.Skeleton`. Eventos FIDC tipados em `FIDCEventType`. |
| **CommandPaletteProvider / CommandPaletteModal / useCommandPalette** | `CommandPalette/` | cmdk + Radix Dialog. `Cmd+K` open, `Cmd+Shift+K` close. 8 secoes canonicas. Recents em localStorage. Numbered `Cmd+1..9`. |
| **EChartsCard / SparkChart / useEChartsTheme** | `EChartsCard/` | Wrapper de echarts-for-react com ResizeObserver, theme dark/light auto, error/retry. Aceita prop `provenance?: Provenance` (CLAUDE.md §14.1) que renderiza dot pinned no rodape direito do card; mock = nao passar. |
| **AppSidebar / useSidebarCollapsed** | `Sidebar/` | Sidebar wired ao `usePathname` + `getActiveModule`. Colapsa para 56px. Avatar Radix no rodape. Tooltips em modo colapsado. |

### A7 Credit composites (migrados de `components/app/`)

| Componente | Arquivo | Proposito |
|---|---|---|
| **AdapterStatusBadge** | `AdapterStatusBadge.tsx` | Badge de status de adapter (ok / falha / sincronizando). |
| **AuthGuard** | `AuthGuard.tsx` | Auth wrapper para `(app)/*`. Redireciona para `/login` se nao autenticado. |
| **HeaderBreadcrumbs** | `Breadcrumbs.tsx` | Breadcrumbs sticky no header (3 niveis: Modulo > Secao > Pagina). |
| **CardMenu** | `CardMenu.tsx` | Menu "..." canonico p/ VizCard / EChartsCard com 3 secoes (Agrupar / Recorte / Tipo). |
| **ChartSkeleton** | `ChartSkeleton.tsx` | Loading skeleton p/ charts. |
| **CompactSeriesTable** | `CompactSeriesTable.tsx` | Tabela compacta p/ series temporais FIDC (Austin-style, density compact default). |
| **DashboardHeaderActions** | `DashboardHeaderActions.tsx` | Set canonico de acoes do header de dashboard (handoff bi-padrao): `[DarkToggle, Compartilhar, Exportar, Mais, IA]`. Slot `actions` obrigatorio em paginas derivadas de `DashboardBiPadrao` (CLAUDE.md §7). |
| **DropdownUserProfile** | `DropdownUserProfile.tsx` | Menu do user no rodape da Sidebar (logout, configuracoes). |
| **EmptyState** | `EmptyState.tsx` | Estado vazio com ilustracao + CTA. |
| **ErrorState** | `ErrorState.tsx` | Estado de erro com retry button. |
| **EntidadeLink** | `EntidadeLink/` | Torna qualquer nome de cedente/sacado clicavel: seta `?entidade=<documento>` (nuqs) e abre o `EntidadePeek` global. `history="push"` (default, voltar fecha) ou `"replace"` (navegacao peek->peek). Sem documento = texto plano (nunca link morto). |
| **EntidadePeek** | `EntidadePeek/` | Drawer global da Ficha da Entidade (party model). Montado 1x no `(app)/layout`; escuta `?entidade=`. Blocos: Hero (papeis+RJ) / Carteira Ativa [F1] / Limites [F1] / Performance [F1] / Consultas Serasa (real) / Operacoes 12M (real) / Grupo / Estabelecimentos. Deep-linkavel: a URL carrega pagina+filtros+peek. |
| **FilterPill** | `FilterPill.tsx` | Multi-select pendente com Apply/Reset (DIFERENTE do FilterChip single-select). |
| **InfoTooltip** | `InfoTooltip.tsx` | Icon "?" com tooltip (uso em headers de KPI/colunas). |
| **Insight + InsightBar** | `Insight.tsx` | Insights da IA -- Z4 do BI Framework. `tone`: violet/amber/blue. |
| **JsonPreview** | `JsonPreview.tsx` | Bloco `<pre>` p/ JSON formatado (debug). |
| **LastSyncCell** | `LastSyncCell.tsx` | "ultima sync ha X min" com tooltip mostrando timestamp absoluto. |
| **Logo** | `Logo.tsx` | Strata logo (icon-only ou full wordmark). |
| **ModuleSwitcher** | `ModuleSwitcher.tsx` | Dropdown L1 (modulo ativo) -- Avatar colorido (gray/blue/emerald/teal/amber/red/violet/slate) + nome + permissao. |
| **SegmentSwitch** | `SegmentSwitch.tsx` | Filtro segment-style (single-select pill toggle) com badge opcional de contagem. Use no topo de listagens p/ "Todos / Ativos / Suspensos". Nao confundir com `<TabNavigation>` (L3 da hierarquia, deep-linkavel) nem `<FilterChip>` (multi-select com Popover). Maximo ~5 opcoes. |
| **MonthRangePicker** | `MonthRangePicker.tsx` | Range mes-a-mes p/ filtros temporais. |
| **OriginDot** | `OriginDot.tsx` | Dot de proveniencia com 3 variants (`inline`/`pinned`/`dot`). API canonica: `<OriginDot provenance={p} variant="..." />` — recebe `Provenance` (ver `design-system/types/provenance.ts`), cor do dot pelo `trustLevel` (high=emerald / medium=amber / low=red), tooltip mostra fonte + adapter@versao + sincronizado + confianca. API legacy `source` + `updatedAtISO` continua funcionando. Mock = passar `provenance={undefined}` -> nada renderiza. Integrado nativamente em `<KpiCard>` (inline ao lado do label), `<EChartsCard>` (pinned no rodape direito) e `<DataTableShell>` (pinned no rodape direito do Card). |
| **Provenance** (tipo) | `types/provenance.ts` | Tipo canonico de proveniencia que espelha o mixin `Auditable` do backend (CLAUDE.md §14.1). Campos: `sourceType` (`erp:bitfin`, `bureau:serasa_pj`, `public:cvm`, ...), `adapterName`, `adapterVersion`, `ingestedAt`, `trustLevel`. Helpers exportados: `formatAdapterId(p)` -> `"bitfin@1.0.0"`, `formatSourceLabel(p)` -> `"Bitfin"`, `formatProvenanceTooltip(p)` -> 4 linhas, `dedupeProvenances(arr)` -> mantem o mais recente por adapter+versao. |
| **OverrideChip** | `OverrideChip.tsx` | Chip "Top 10 × resetar" em VizCard quando override aplicado via CardMenu. |
| **PageHeader** | `PageHeader.tsx` | Header de pagina: titulo + subtitle + botoes secundarios. |
| **PeriodoPresets** | `PeriodoPresets.tsx` | Presets rapidos (7d, 30d, 90d, 12M, YTD). |
| **SecretInput** | `SecretInput.tsx` | Input de senha com toggle mostrar/ocultar. |
| **Stepper** | `Stepper.tsx` | Wizard horizontal multi-step. |
| **UserProfile** | `UserProfile.tsx` | Card de perfil no rodape da Sidebar (nome + email + avatar). |
| **VizCard** | `VizCard.tsx` | Card generico com header + menu (irmao do EChartsCard, p/ conteudo nao-chart). |

## Tabelas de decisao

Veja `src/design-system/README.md` ou `docs/BI_FRAMEWORK.md` para tabelas completas "quando usar X vs Y".

## Imports

```ts
// Barrel oficial (recomendado)
import { StatusPill, KpiCard, KpiStrip, FilterBar, DataTable, ... } from "@/design-system/components"

// Subpasta especifica (quando precisa do tipo interno)
import type { StatusKey } from "@/design-system/components/StatusPill"
```

## Adicionar componente novo

CLAUDE.md §1 ordem de escolha:

1. Existe em `tremor/` ou `charts/`? Use direto via `@/design-system/primitives` ou `@/components/charts`.
2. Existe Tremor Raw upstream nao copiado? Copie verbatim para `@/components/tremor/`.
3. Existe ja em `design-system/components/`? Use via barrel.
4. **Nao existe?** Crie aqui, respeitando:
   - **(a)** Tokens da §4 do CLAUDE.md (zero cor arbitraria)
   - **(b)** Reutiliza Radix UI quando ha equivalente -- nunca reimplementar a11y
   - **(c)** Documentar em `/design` route + adicionar a este README

Se (a)/(b)/(c) falham, **pare e discuta**.

## Proibido

- Inline styles `style={{...}}` (excecao: `style={{ color }}` em paleta dinamica)
- Cor arbitraria (`text-[#abc]`)
- Importar de outro modulo de dominio (ex.: `bi/*` componente nao importa `cadastros/*`)
- Inventar primitivo que Tremor ja cobre
