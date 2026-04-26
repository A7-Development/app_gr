# BI Framework -- detalhe de implementacao

Referencia detalhada para CLAUDE.md §19. Aqui vivem composicao por componente, exemplos de codigo, e tabelas de decisao para ambiguidades. As 7 zonas e as regras duras estao no CLAUDE.md.

> **Fonte de verdade dos componentes:** `src/design-system/components/` (barrel `@/design-system/components`). Estilos e tokens em `src/design-system/tokens/`. Patterns prontos em `src/design-system/patterns/`. Exploracao viva em `/design` (rota dev-only).

---

## 1. As 7 zonas em componentes Strata

| Zona | Componente | Import | Notas |
|---|---|---|---|
| **Z1 -- FilterBar** | `<FilterBar>` envolvendo `<FilterChip>` / `<FilterSearch>` / `<RemovableChip>` / `<MoreFiltersButton>` / `<SavedViewsDropdown>` | `@/design-system/components/FilterBar` | Sticky `top-0 z-10`, scroll-shadow via IntersectionObserver. `FilterChip` aceita `icon`, `active`, e popover via `children`. |
| **Z2 -- PageHeader** | `<PageHeader>` (legacy A7) com `<AIButton>` ao final | `@/design-system/components/PageHeader` + `AIButton` | `subtitle` opcional. Botoes secundarios `Compartilhar` / `Exportar` antes do AIButton. |
| **Z3 -- KpiStrip** | `<KpiStrip>` com **6 `<KpiCard>`** | `@/design-system/components/KpiStrip` | Cada card recebe `intensity` (3 barrinhas) + `source`/`updatedAtISO` (renderiza OriginDot). **Nao usar `sparkData` em Z3** -- viola regra §19.1. |
| **Z4 -- InsightBar** | `<InsightBar>` envolvendo `<Insight>` × N | `@/design-system/components/Insight` | `tone`: `violet` (IA neutra) / `amber` (atencao) / `blue` (informativo). Max 3 insights visiveis. |
| **Z5 -- TabNavigation** | `<TabNavigation>` + `<TabNavigationLink>` | `@/components/tremor/TabNavigation` | 3-6 abas. URL-synced via `searchParams.tab`. Active = `border-bottom blue-500`. |
| **Z6 -- Grid de visualizacoes** | `<EChartsCard>` (charts) ou `<VizCard>` (custom) | `@/design-system/components/EChartsCard` ou `VizCard` | Hero 3:2 obrigatorio. Cada card tem menu "..." canonico (§3 abaixo). |
| **Z7 -- ProvenanceFooter** | `<ProvenanceFooter>` (em `components/bi/`) | `@/components/bi/ProvenanceFooter` | Sem borda, grid 3 colunas (fonte / atualizado / SLA). |

---

## 2. Anatomia de uma pagina BI Strata (exemplo completo)

```tsx
"use client"
import { useState } from "react"
import { RiCalendarLine, RiFundsLine } from "@remixicon/react"

import {
  PageHeader,
  AIButton,
  FilterBar, FilterChip, MoreFiltersButton,
  KpiCard, KpiStrip, FIDC_KPI_META,
  InsightBar, Insight,
  EChartsCard,
} from "@/design-system/components"
import { TabNavigation, TabNavigationLink } from "@/components/tremor/TabNavigation"
import { Button } from "@/components/tremor/Button"
import { ProvenanceFooter } from "@/components/bi/ProvenanceFooter"

export default function BiCarteiraPage() {
  const [periodo, setPeriodo] = useState("12M")
  const [tab, setTab] = useState("visao-geral")

  return (
    <>
      {/* Z1 -- FilterBar sticky */}
      <FilterBar
        extraActions={<MoreFiltersButton count={0} />}
      >
        <FilterChip icon={RiCalendarLine} label="Periodo" value={periodo} active={periodo !== "12M"} />
        <FilterChip icon={RiFundsLine}    label="Tipo de fundo" value="Todos" />
      </FilterBar>

      {/* Z2 -- PageHeader */}
      <PageHeader title="Carteira" subtitle="Visao consolidada por produto e prazo">
        <Button variant="secondary">Compartilhar</Button>
        <Button variant="secondary">Exportar</Button>
        <AIButton />
      </PageHeader>

      {/* Z3 -- KpiStrip (6 KPIs) */}
      <KpiStrip>
        <KpiCard
          {...FIDC_KPI_META.pl}
          value="R$ 124,5M"
          sub="abr/26"
          delta={{ value: 2.34, suffix: "%" }}
          intensity={{ tone: "info", level: "high" }}
          source="QiTech"
          updatedAtISO="2026-04-26T10:00:00Z"
        />
        {/* ... +5 KpiCards */}
      </KpiStrip>

      {/* Z4 -- Insights IA (opcional) */}
      <InsightBar>
        <Insight tone="violet" text="PL cresceu 3,2% acima da media setor" />
        <Insight tone="amber" text="Concentracao no top-3 sacados subiu 1,1pp" />
      </InsightBar>

      {/* Z5 -- L3 Tabs */}
      <TabNavigation value={tab} onValueChange={setTab}>
        <TabNavigationLink value="visao-geral">Visao geral</TabNavigationLink>
        <TabNavigationLink value="por-produto">Por produto</TabNavigationLink>
        <TabNavigationLink value="por-cedente">Por cedente</TabNavigationLink>
        <TabNavigationLink value="aging">Aging</TabNavigationLink>
      </TabNavigation>

      {/* Z6 -- Grid Hero 3:2 + Cards */}
      <div className="grid grid-cols-5 gap-5">
        <EChartsCard className="col-span-3" title="Evolucao do PL" option={...} height={320} />
        <EChartsCard className="col-span-2" title="Distribuicao por produto" option={...} height={320} />
      </div>

      {/* Z7 -- Provenance Footer */}
      <ProvenanceFooter
        source="QiTech + warehouse canonico"
        updatedAtISO="2026-04-26T10:00:00Z"
        sla="Dados atualizados a cada 4h"
      />
    </>
  )
}
```

---

## 3. Menu "..." canonico em cada card de Z6

Todo `<EChartsCard>` ou `<VizCard>` em Z6 expoe um menu identico, com 3 secoes:

1. **Agrupar por** -- Segmento / Regiao / Canal / Produto / Cedente (conforme dominio)
2. **Recorte** -- Toda a carteira / Top 10 / Top 20 / Segmento X / ...
3. **Tipo de visualizacao** -- Barras / Linhas / Area / Tabela

Quando usuario aplica override via menu, o card mostra `<OverrideChip />` ("Top 10 × resetar") no card-head. Click no chip reseta override daquele card.

```tsx
import { CardMenu } from "@/design-system/components/CardMenu"
import { OverrideChip } from "@/design-system/components/OverrideChip"

<EChartsCard
  title="Volume de Cessoes"
  caption={overrideAtivo ? <OverrideChip label="Top 10" onReset={...} /> : undefined}
  actions={<CardMenu agrupar={...} recorte={...} tipo={...} />}
  option={...}
/>
```

---

## 4. Tabela de decisao -- "qual componente usar?"

### Status / labels

| Caso de uso | Use | Nao use |
|---|---|---|
| Lifecycle de cessao (Em dia / Atrasado / Inadimplente / Recomprado / Liquidado) | `<StatusPill status="em-dia" />` | `<Badge>` Tremor (cores semanticas, mas nao do dominio FIDC) |
| Rotulo de status sistemico (Ativo, Sincronizado, Pendente) sem ser de cessao | `<Badge variant="success/warning/error/neutral">` Tremor | `<StatusPill>` (so para FIDC lifecycle) |
| Adapter rodando vs falho | `<AdapterStatusBadge>` | inventar |
| Fila de aprovacao com contagem que pulsa | `<ApprovalQueueBadge count={N}>` | `<Badge>` |
| "Em breve" / dev-only flag | `<span class="rounded bg-gray-200 px-1.5 text-[10px]...">breve</span>` (ja no Sidebar) | `<Badge>` |

### KPIs

| Caso | Variante |
|---|---|
| KPI strip de 6 (Z3 do BI) | `<KpiCard variant="default">` (22px value) |
| KPI inline em sidebar/footer compacto | `<KpiCard variant="compact">` (18px value) |
| KPI hero solo no topo de uma pagina (raro) | `<KpiCard variant="hero">` (48px value) |
| Apenas valor + delta sem barrinhas | `<KpiCard>` sem prop `intensity` |
| Sinalizar nivel critico (passou threshold) | passar `currentValue={x}` + `alertThreshold={...}` -- KpiCard mostra `<AlertBadge>` automaticamente |
| Tendencia visual em KPI compacto fora da Z3 | passar `sparkData={[...]}` + `sparkColor` |

### Tabelas

| Caso | Use | Por que |
|---|---|---|
| Listagem transacional (cessoes, sacados, contratos) com filtro/sort/virtualizacao | `<DataTable>` (TanStack Table v8 + Virtual) | Virtualizacao automatica > 100 linhas; cells tipados (Currency, Status, Id, ...) |
| Series temporais FIDC (PL mes-a-mes, cotas, rentabilidade) | `<CompactSeriesTable>` (Austin-style, density compact) | Otimizada para colunas-mes verticais; ja respeita `tabular-nums` |
| Tabela ad-hoc dentro de DrillDownSheet ou card pequeno (< 10 linhas) | `<Table>` Tremor cru | DataTable e overkill |

### Filtros

| Caso | Use |
|---|---|
| Single-select com valor sempre visivel (Periodo, Status, Modulo) | `<FilterChip label value active>` |
| Multi-select pendente com botao Aplicar | `<FilterPill title options value onChange>` |
| Filtro de busca livre (texto) | `<FilterSearch value onChange onClear>` |
| Chip removivel mostrando filtro aplicado | `<RemovableChip label value onRemove>` |
| Botao "Mais filtros" com badge de contagem | `<MoreFiltersButton count>` |
| Salvar/aplicar visao salva | `<SavedViewsDropdown currentParams onApplyView>` |

### Cards de grafico / Cards genericos (Z6)

| Caso | Use |
|---|---|
| Chart com ECharts (linha, barra, pizza, area, heatmap) | `<EChartsCard option title caption actions footer>` |
| Card sem chart (KPI hero, lista, etc) com header padronizado | `<VizCard title menu>` |
| Card "limpo" sem header (compor manualmente) | `<Card>` Tremor cru |

### Drawer / Modal lateral

| Caso | Use |
|---|---|
| Drill-down de linha de tabela transacional | `<DrillDownSheet open onClose size>` (compound API: `.Header`, `.Hero`, `.Tabs`, `.PropertyList`, `.LinkedObjects`, `.Timeline`, `.Footer`) |
| Drawer simples (form lateral, AI chat) | `<Drawer>` Tremor (`@/components/tremor/Drawer`) |
| Modal centrado | `<Dialog>` Tremor |
| Sheet customizado sem features de drill-down | `<Sheet>` primitivo (`@/design-system/primitives`) |

### Charts

| Caso | Use |
|---|---|
| Sparkline (mini-tendencia em KPI) | `<Sparkline data color>` (em `KpiStrip`, exportado) |
| Chart full pra Z6 / dashboard | `<EChartsCard>` |
| Chart Tremor pre-fabricado (BarChart, LineChart) | `@/components/charts/*` (Tremor verbatim) |

---

## 5. Tokens -- quando usar TS, CSS var ou Tailwind

| Cenario | Acesso |
|---|---|
| Cor de serie em chart (ECharts) | `tokens.colors.chart[0]` (TS, em `@/design-system/tokens`) |
| Tema completo do ECharts (dark/light) | `useEChartsTheme()` hook (em `@/design-system/components/EChartsCard`) |
| Cor de fonte/borda/bg em componente Tailwind | classes Tailwind (`text-gray-900`, `bg-blue-500`, `dark:bg-gray-925`) |
| Animacao reusavel (sheet, dialog, accordion) | classes ja registradas em `globals.css` (`animate-drawer-slide-left-and-fade`, etc) |
| Layout fixo (sidebar width, header height, drawer sm/md/lg) | `tokens.spacing.*` (TS) ou CSS var `var(--sidebar-w)` |
| Status FIDC (em-dia, inadimplente, ...) | nao tocar -- usar `<StatusPill status>` que mapeia internamente |

**Proibido:** `text-[#123abc]`, `bg-[rgb(...)]`, valores arbitrarios fora dos tokens. CLAUDE.md §4.

---

## 6. Provenance + Auditabilidade na UI BI

Toda metrica/numero exibido em pagina BI **deve** carregar proveniencia visivel:

| Elemento | Componente |
|---|---|
| Dot de origem em KPI / VizCard | `<OriginDot source updatedAtISO>` -- ja integrado em `<KpiCard>` quando `source` e passado |
| Footer geral da pagina | `<ProvenanceFooter source updatedAtISO sla>` (Z7) |
| Botao "ver premissas" em projecoes/calculos | criar quando surgir necessidade (CLAUDE.md §14.5 menciona `<ShowPremisesButton />`) |

CLAUDE.md §14 e a fonte de verdade -- proveniencia e DNA do sistema, nao opcional.

---

## 7. Patterns prontos para BI

`src/design-system/patterns/DashboardOperacional.tsx` ja entrega Z1-Z3-Z6-tabela. Use como ponto de partida copy-paste-edit:

```tsx
// Em vez de copiar zona-por-zona, comece pelo pattern e adapte:
import { DashboardOperacional } from "@/design-system/patterns"
// Le os comentarios HOW TO ADAPT no topo do arquivo, troque os tipos de dominio.
```

**Quando usar pattern vs anatomia manual?**
- Pattern: a pagina segue exatamente as 7 zonas canonicas e os 4 KPIs sao previsiveis (PL, rentabilidade, inadimplencia, PDD).
- Anatomia manual: a pagina precisa de Z6 totalmente customizado (ex.: benchmark CVM com 4 abas e dados externos), ou tem zonas extras nao canonicas.

---

## 8. Checklist de criacao -- nova pagina BI

1. **Identifique o pattern** -- e `DashboardOperacional`? E `ListagemComDrilldown`? Ou e custom (raro -- discuta)?
2. **Crie a rota** -- `src/app/(app)/bi/<secao>/page.tsx`
3. **Atualize `lib/modules.ts`** -- registre a secao no array `MODULES.find(id="bi").sections` (CLAUDE.md §11.1)
4. **Componha as 7 zonas** -- na ordem, com os componentes Strata corretos (tabelas §1 e §4 deste doc)
5. **Adicione `<AIButton />`** no PageHeader (Z2) -- sempre ultimo botao
6. **Adicione `<ProvenanceFooter />`** (Z7) -- sem ele, e bug
7. **Verifique paleta** -- so cores da §4 do CLAUDE.md
8. **Teste dark mode** -- toggle no header
9. **Rode `tsc --noEmit` + `npm run build`** -- zero erros, zero warnings
10. **Audite** -- skill `audit-page-consistency` ou checklist §18 do CLAUDE.md

---

## 9. Anti-padroes (nao fazer)

- ❌ `<KpiCard sparkData={...}>` em Z3 (sparkline na strip de 6 KPIs viola §19.1)
- ❌ Z6 hero ocupando 100% da largura (sempre 3:2)
- ❌ Pagina BI sem `<ProvenanceFooter />` (Z7) -- viola auditabilidade
- ❌ `<Badge>` Tremor para status de cessao -- use `<StatusPill>`
- ❌ `<Table>` Tremor cru para listagem grande -- use `<DataTable>` (virtualiza > 100 rows)
- ❌ Cores ad-hoc: `bg-emerald-500` para badges de "ativo" -- use `<Badge variant="success">`
- ❌ Inventar 4o nivel de navegacao -- max 3 (CLAUDE.md §11.6)
- ❌ AIButton fora do PageHeader (sempre Z2, sempre ultimo)
- ❌ `KPICard` ou `KPIStrip` (legacy A7 v1 -- removidos no commit `c1d6d22`). Use `KpiCard` / `KpiStrip` Strata.
