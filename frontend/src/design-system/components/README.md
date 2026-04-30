# Components

Camada de composicao -- 38 componentes que compoem `tremor/*` + `charts/*` + `tokens/*` em algo de dominio FIDC. Esta e a unica fonte de componentes para a UI da aplicacao alem dos primitivos Tremor.

## Mapa por categoria

### Strata canonicos (entregues no handoff v2)

| Componente | Pasta | Proposito |
|---|---|---|
| **StatusPill** | `StatusPill/` | Lifecycle FIDC: em-dia, atrasado-30, atrasado-60, inadimplente, recomprado, liquidado. Variantes `pill` e `dot`. |
| **ApprovalQueueBadge** | `ApprovalQueueBadge/` | Badge vermelho que pulsa, p/ filas pendentes (Sidebar, headers). |
| **KpiCard / KpiStrip / Sparkline / KpiIntensity** | `KpiStrip/` | KPI canonico Strata: layout side-by-side (texto esquerda · sparkline lateral compacto direita · OriginDot rodape). 3 variantes (compact/default/hero). Sparkline com callout pill opcional + endpoint dot. **KpiStrip canonico**: card full-width (encosta nas bordas do container pai, sem `mx-auto`/`max-w-*`); em xl usa `flex justify-between` — KPIs com largura natural e espaco distribuido uniformemente entre eles; em <xl cai para grid (1 col mobile, 2 cols sm). Prop `cols` (default 5) e anotacao semantica — em xl o layout nao depende dela. Presets em `FIDC_KPI_META`. |
| **FilterBar / FilterChip / FilterSearch / RemovableChip / MoreFiltersButton / SavedViewsDropdown** | `FilterBar/` | Barra Z1 do BI Framework. Sticky com scroll-shadow. SavedViews em localStorage. |
| **DataTable + 9 cells** | `DataTable/` | TanStack Table v8 + TanStack Virtual (auto > 100 rows). 3 densidades, ColumnManager (Popover), ExportMenu. Cells: `CurrencyCell`, `PercentageCell`, `DateCell`, `StatusCell`, `IdCell`, `CpfCnpjCell`, `RelationshipCell` (HoverCard), `SparklineCell`, `ProgressCell`. **Todas as cells canonicas usam `tableTokens.*` para tipografia/cor — ver `tokens/table.ts`.** |
| **DataTableShell** | `DataTableShell/` | Wrapper canonico de **listagens CRUD/admin** (Provedores, Usuarios, Etiquetas...). Encapsula `Card + FilterSearch + SegmentSwitch + counter + DataTable` num unico componente. Props: `data`, `columns`, `search`, `segments` (opcoes com `filter` predicado), `itemNoun`, `emptyState`, `onRowClick`. Garante layout/gap/ordem identicos entre paginas. **Use sempre que for listagem CRUD pequena-media (~5-200 rows)** — fugir so com `// MOTIVO:` no caller. Demo isolada: `/preview/data-table-shell`. |
| **DrillDownSheet** | `DrillDownSheet/` | Compound API: `.Header`, `.Hero`, `.Tabs`, `.Body`, `.PropertyList`, `.LinkedObjects`, `.Timeline`, `.SectionLabel`, `.Footer`, `.Skeleton`. Eventos FIDC tipados em `FIDCEventType`. |
| **CommandPaletteProvider / CommandPaletteModal / useCommandPalette** | `CommandPalette/` | cmdk + Radix Dialog. `Cmd+K` open, `Cmd+Shift+K` close. 8 secoes canonicas. Recents em localStorage. Numbered `Cmd+1..9`. |
| **EChartsCard / SparkChart / useEChartsTheme** | `EChartsCard/` | Wrapper de echarts-for-react com ResizeObserver, theme dark/light auto, error/retry. |
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
| **FilterPill** | `FilterPill.tsx` | Multi-select pendente com Apply/Reset (DIFERENTE do FilterChip single-select). |
| **InfoTooltip** | `InfoTooltip.tsx` | Icon "?" com tooltip (uso em headers de KPI/colunas). |
| **Insight + InsightBar** | `Insight.tsx` | Insights da IA -- Z4 do BI Framework. `tone`: violet/amber/blue. |
| **JsonPreview** | `JsonPreview.tsx` | Bloco `<pre>` p/ JSON formatado (debug). |
| **LastSyncCell** | `LastSyncCell.tsx` | "ultima sync ha X min" com tooltip mostrando timestamp absoluto. |
| **Logo** | `Logo.tsx` | Strata logo (icon-only ou full wordmark). |
| **ModuleSwitcher** | `ModuleSwitcher.tsx` | Dropdown L1 (modulo ativo) -- Avatar colorido (gray/blue/emerald/teal/amber/red/violet/slate) + nome + permissao. |
| **SegmentSwitch** | `SegmentSwitch.tsx` | Filtro segment-style (single-select pill toggle) com badge opcional de contagem. Use no topo de listagens p/ "Todos / Ativos / Suspensos". Nao confundir com `<TabNavigation>` (L3 da hierarquia, deep-linkavel) nem `<FilterChip>` (multi-select com Popover). Maximo ~5 opcoes. |
| **MonthRangePicker** | `MonthRangePicker.tsx` | Range mes-a-mes p/ filtros temporais. |
| **OriginDot** | `OriginDot.tsx` | Dot 12x12 com tooltip de proveniencia (source + updatedAtISO). Integrado em `<KpiCard>` quando `source` e passado. |
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
