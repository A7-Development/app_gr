# Strata Design System

Design system canonico do projeto GR. Tudo que aparece na UI vem daqui ou de `@/components/tremor/` (primitivos verbatim) ou `@/components/charts/` (charts Tremor verbatim).

> **Regra absoluta** (CLAUDE.md §1): nada fora destas 3 fontes pode aparecer na UI. Sem ad-hoc, sem cores arbitrarias, sem Tailwind cru de cor.

---

## 1. Mapa da pasta

```
src/design-system/
├── tokens/         # Tokens TS espelhando CSS vars do globals.css
│   ├── index.ts            # Objeto principal: brand, status, chart, delta, fonts, spacing, radius, motion
│   ├── echarts-theme.ts    # getEChartsTheme(mode) + useEChartsTheme() hook
│   ├── typography.ts       # fmt.{currency,percent,number,...} + tabular/monoId/caption/kpiHero classes
│   ├── spacing.ts          # sidebar, layout, drawer, rowHeight, rowHeightClass()
│   └── motion.ts           # duration, easing, transition(), motionClasses, echartsMotion
│
├── primitives/     # Re-export curado de Tremor Raw + Sheet
│   ├── index.ts            # Barrel: Button, Card, Input, Select, Tabs, Dialog, Drawer, Tooltip, Popover, Sheet, ...
│   └── Sheet.tsx           # Right-side drawer (Radix Dialog) -- containerizacao de drill-down
│
├── components/     # 37 componentes -- Strata canonicos + composites A7
│   ├── index.ts            # Barrel oficial
│   ├── ApprovalQueueBadge/ # Badge vermelho que pulsa, p/ filas pendentes
│   ├── CommandPalette/     # cmdk + Provider + 8 secoes + recents (cmd+K)
│   ├── DataTable/          # TanStack Table v8 + Virtual + 9 cells tipados
│   ├── DrillDownSheet/     # Compound API: .Header, .Hero, .Tabs, .PropertyList, .LinkedObjects, .Timeline, .Footer
│   ├── EChartsCard/        # Wrapper ECharts com theme + ResizeObserver
│   ├── FilterBar/          # FilterBar + FilterChip + FilterSearch + RemovableChip + MoreFiltersButton + SavedViewsDropdown
│   ├── KpiStrip/           # KpiCard (3 variants) + Sparkline + IntensityBars + FIDC_KPI_META presets
│   ├── Sidebar/            # AppSidebar (collapsed mode + Avatar + tooltips), wired ao usePathname/getActiveModule
│   ├── StatusPill/         # FIDC lifecycle (em-dia/atrasado/inadimplente/recomprado/liquidado)
│   ├── AIButton.tsx        # Botao "Perguntar a IA" (unico uso de violet fora de chart)
│   ├── AIDrawer.tsx        # Drawer lateral com chat IA contextualizado
│   ├── AdapterStatusBadge.tsx  # Badge de status de adapter (ok/falha/sincronizando)
│   ├── AuthGuard.tsx       # Auth wrapper para rotas (app)/*
│   ├── Breadcrumbs.tsx     # HeaderBreadcrumbs (sticky, 3 niveis)
│   ├── CardMenu.tsx        # Menu "..." canonico p/ VizCard / EChartsCard
│   ├── ChartSkeleton.tsx   # Loading skeleton p/ charts
│   ├── CompactSeriesTable.tsx  # Tabela compacta p/ series temporais FIDC (Austin-style)
│   ├── DropdownUserProfile.tsx # Menu do user no rodape da Sidebar
│   ├── EmptyState.tsx      # Estado vazio com ilustracao + CTA
│   ├── ErrorState.tsx      # Estado de erro com retry
│   ├── FilterPill.tsx      # Multi-select com Apply/Reset (diferente do FilterChip single-select)
│   ├── InfoTooltip.tsx     # Icon "?" com tooltip (uso em headers de KPI/colunas)
│   ├── Insight.tsx         # Insight + InsightBar (Z4 do BI Framework)
│   ├── JsonPreview.tsx     # Bloco <pre> p/ JSON formatado
│   ├── LastSyncCell.tsx    # "ultima sync ha X min" com tooltip
│   ├── Logo.tsx            # A7 Credit logo
│   ├── ModuleSwitcher.tsx  # Dropdown L1 (modulo ativo) -- Avatar colorido + nome + permissao
│   ├── MonthRangePicker.tsx # Range mes-a-mes p/ filtros temporais
│   ├── OriginDot.tsx       # Dot 12x12 com tooltip de proveniencia (em KpiCard/VizCard)
│   ├── OverrideChip.tsx    # Chip "Top 10 × resetar" em VizCard quando override aplicado
│   ├── PageHeader.tsx      # Header de pagina (titulo + subtitle + botoes secundarios + AIButton)
│   ├── PeriodoPresets.tsx  # Presets rapidos (7d, 30d, 90d, 12M, YTD)
│   ├── SecretInput.tsx     # Input de senha com mostrar/ocultar
│   ├── Stepper.tsx         # Wizard horizontal (multi-step)
│   ├── UserProfile.tsx     # Card de perfil no rodape da Sidebar
│   └── VizCard.tsx         # Card generico com header + menu (irmao do EChartsCard)
│
└── patterns/       # Templates copy-paste-edit
    ├── index.ts            # Barrel: DashboardOperacional, ListagemComDrilldown
    ├── DashboardOperacional.tsx  # PageHeader + FilterBar + KpiStrip + Grid 2x2 + DataTable de atividade recente
    └── ListagemComDrilldown.tsx  # PageHeader + FilterBar + DataTable + DrillDownSheet (URL-synced)
```

---

## 2. Imports canonicos

```ts
// Tokens
import { tokens, type StatusKey, type ChartColor } from "@/design-system/tokens"
import { fmt, fmtDate, fmtCPF, fmtCNPJ, tabular, monoId, caption } from "@/design-system/tokens/typography"
import { rowHeightClass, type DensityMode } from "@/design-system/tokens/spacing"
import { duration, easing, transition } from "@/design-system/tokens/motion"
import { useEChartsTheme, getEChartsTheme } from "@/design-system/tokens/echarts-theme"

// Primitives (Tremor Raw + Sheet)
import {
  Button, Card, Input, Badge, Divider, Label, Textarea,
  Checkbox, Switch, RadioGroup, RadioGroupItem,
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
  Tabs, TabsContent, TabsList, TabsTrigger,
  TabNavigation, TabNavigationLink,
  Dialog, DialogContent, DialogTitle, ...,
  Drawer, DrawerContent, ...,
  Tooltip, Popover, PopoverContent, PopoverTrigger,
  DropdownMenu, ..., Calendar, DatePicker, DateRangePicker,
  Table, TableBody, TableCell, TableHead, ...,
  Sheet, SheetContent, SheetHeader, SheetBody, SheetFooter,
  type SheetSize,
} from "@/design-system/primitives"

// Components (barrel oficial)
import {
  // Strata canonicos
  StatusPill, ApprovalQueueBadge,
  KpiCard, KpiStrip, KpiIntensity, Sparkline, FIDC_KPI_META,
  FilterBar, FilterSearch, FilterChip, RemovableChip, MoreFiltersButton, SavedViewsDropdown,
  DataTable, CurrencyCell, PercentageCell, DateCell, StatusCell, IdCell, CpfCnpjCell, RelationshipCell, SparklineCell, ProgressCell,
  AppSidebar, useSidebarCollapsed,
  DrillDownSheet,
  CommandPaletteProvider, CommandPaletteModal, useCommandPalette,
  EChartsCard, SparkChart, useEChartsTheme,

  // A7 Credit composites
  AIButton, AIDrawer,
  AdapterStatusBadge, AuthGuard, HeaderBreadcrumbs,
  CardMenu, ChartSkeleton, CompactSeriesTable,
  DropdownUserProfile, EmptyState, ErrorState,
  FilterPill, InfoTooltip,
  Insight, InsightBar,
  JsonPreview, LastSyncCell, Logo,
  ModuleSwitcher, MonthRangePicker,
  OriginDot, OverrideChip,
  PageHeader, PeriodoPresets, SecretInput, Stepper,
  UserProfile, VizCard,

  // Tipos
  type StatusKey, type KpiCardProps, type DataTableProps, type SheetSize, ...
} from "@/design-system/components"

// Patterns
import { DashboardOperacional, ListagemComDrilldown } from "@/design-system/patterns"
```

---

## 3. Quando usar X vs Y -- decisoes ambiguas

### Status / labels

| Caso | Use | Nao use |
|---|---|---|
| Lifecycle FIDC (em-dia, inadimplente, ...) | `<StatusPill status>` | `<Badge>` |
| Status sistemico (Ativo, Sincronizado) | `<Badge variant>` Tremor | `<StatusPill>` |
| Adapter rodando vs falho | `<AdapterStatusBadge>` | `<Badge>` cru |
| Fila com contagem que pulsa | `<ApprovalQueueBadge count>` | `<Badge>` |

### KPIs

| Caso | Componente | Variante |
|---|---|---|
| KPI strip Z3 do BI (6 cards) | `<KpiCard>` | `default` |
| KPI compacto (sidebar, footer, header) | `<KpiCard>` | `compact` |
| KPI hero solo no topo | `<KpiCard>` | `hero` |
| Tendencia visual em KPI | passar `sparkData` + `sparkColor` | (so fora da Z3) |
| Sinalizar threshold critico | passar `currentValue` + `alertThreshold` | -- |
| Proveniencia (fonte + timestamp) | passar `source` + `updatedAtISO` | OriginDot e renderizado automaticamente |

### Tabelas

| Caso | Use | Por que |
|---|---|---|
| Listagem transacional (cessoes, sacados) | `<DataTable>` | TanStack Table v8 + Virtual; > 100 rows virtualiza auto |
| Series temporais FIDC (PL mes-a-mes) | `<CompactSeriesTable>` | Austin-style, density compact |
| Tabela ad-hoc (< 10 rows, dentro de DrillDownSheet) | `<Table>` Tremor cru | DataTable e overkill |

### Filtros

| Caso | Use |
|---|---|
| Single-select com valor visivel | `<FilterChip label value active icon>` |
| Multi-select com Apply pendente | `<FilterPill title options value onChange>` |
| Busca livre | `<FilterSearch value onChange onClear>` |
| Chip removivel | `<RemovableChip label value onRemove>` |
| "Mais filtros" com badge | `<MoreFiltersButton count>` |
| Salvar visao | `<SavedViewsDropdown>` |
| Range mes-a-mes | `<MonthRangePicker>` |
| Presets rapidos (7d/30d/90d/12M/YTD) | `<PeriodoPresets>` |

### Cards de chart

| Caso | Use |
|---|---|
| Chart ECharts (linha, barra, pizza, ...) | `<EChartsCard option title caption actions footer>` |
| Card sem chart com header padrao | `<VizCard title menu>` |
| Card "limpo" sem header | `<Card>` Tremor |
| Sparkline mini | `<Sparkline data color>` (importado de KpiStrip) |
| Mini-chart em celula de tabela | `<SparklineCell data>` (cell renderer) |

### Drawer / Modal / Sheet

| Caso | Use |
|---|---|
| Drill-down de linha de tabela | `<DrillDownSheet>` (compound API) |
| Form lateral / chat IA | `<Drawer>` Tremor |
| Modal centrado | `<Dialog>` Tremor |
| Sheet customizado sem drill-down | `<Sheet>` primitivo |

---

## 4. Tokens -- onde acessar

| Cenario | Acesso |
|---|---|
| Cor de serie de chart (ECharts) | `tokens.colors.chart[0..7]` (TS) |
| Tema completo do ECharts | `useEChartsTheme()` hook |
| Cor de fonte/borda/bg em componente | classes Tailwind (`text-gray-900`, `bg-blue-500`, `dark:bg-gray-925`) |
| Animacao reusavel | classes em `globals.css` (`animate-drawer-slide-left-and-fade`, etc) |
| Layout fixo (sidebar w, header h, drawer sm/md/lg) | `tokens.spacing.*` ou CSS var |
| Status FIDC | `<StatusPill>` ou `tokens.colors.status[StatusKey]` |
| Format pt-BR (currency, percent, ...) | `fmt.currency`, `fmt.percent`, `fmtCPF`, `fmtCNPJ`, `fmtDate` |
| Tabular nums em tabela/cell | classe `tabular` (de `typography.ts`) ou Tailwind `tabular-nums` |

---

## 5. Patterns -- ponto de partida para nova pagina

| Pattern | Quando usar | O que entrega |
|---|---|---|
| `DashboardOperacional` | Dashboard de KPIs + 4 charts (BI/Carteira/Rentabilidade) | Z2 + Z1 + Z3 + Grid 2×2 + DataTable de atividade recente |
| `ListagemComDrilldown` | Listagem com drill-down lateral (Cessoes, Cedentes, Sacados, Cobranca, Reconciliacao, Eventos) | Z2 + Z1 + DataTable + DrillDownSheet (URL-synced via `?selected=ID`) |

```tsx
// Copy-paste o arquivo do pattern, troque tipos de dominio, leia comentarios HOW TO ADAPT no topo.
import { DashboardOperacional } from "@/design-system/patterns"
```

---

## 6. CommandPalette -- integracao global

```tsx
// app/(app)/layout.tsx
import { CommandPaletteProvider } from "@/design-system/components"

export default function AppLayout({ children }) {
  return (
    <CommandPaletteProvider items={[/* extra domain items */]}>
      <div className="flex h-screen">
        <AppSidebar />
        <main>{children}</main>
      </div>
    </CommandPaletteProvider>
  )
}
```

Atalhos:
- `Cmd/Ctrl + K` -- abrir
- `Cmd/Ctrl + Shift + K` -- fechar sem persistir recente
- `Cmd/Ctrl + 1..9` -- atalho rapido para os 9 primeiros resultados quando ha busca

---

## 7. Rota `/design`

Documentacao viva em dev. Acessar via `npm run dev` + `http://localhost:3000/design`. Em producao retorna 404 (gated em `app/design/page.tsx`).

Mostra todos os tokens, primitives, components, e referencia aos patterns. Use como referencia rapida quando esquecer uma API.

---

## 8. Anti-padroes (nao fazer)

- Importar de `@/components/app/*` (pasta deletada -- use `@/design-system/components/*`)
- `KPICard` ou `KPIStrip` (legacy A7 v1 -- removidos -- use `KpiCard` / `KpiStrip`)
- Cores arbitrarias: `text-[#abc]`, `bg-[rgb(...)]`
- Radix cru para o que o Tremor ja cobre (Dialog, Popover, Tooltip, Tabs, ...)
- Recharts direto (so via `@/components/charts/*` que ja embrulha)
- Shadcn ou outro DS externo
- Inline styles `style={{...}}` (excecao: `style={{ color }}` em paleta dinamica)
- Inventar 4o nivel de navegacao (CLAUDE.md §11.6)
- Pagina BI sem `<ProvenanceFooter />` (Z7 obrigatoria)

---

## 9. Referencias

- **CLAUDE.md** -- regras gerais (§1-§19)
- **docs/BI_FRAMEWORK.md** -- detalhes das 7 zonas BI + tabelas de decisao + exemplos
- **/design** -- documentacao viva (dev)
- **`HOW TO ADAPT:`** comentarios no topo de cada pattern -- guia de customizacao
