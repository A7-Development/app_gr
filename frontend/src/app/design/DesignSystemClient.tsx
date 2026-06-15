"use client"

// src/app/design/DesignSystemClient.tsx
// Live design system showcase — compact version covering tokens + components + patterns.

import * as React from "react"
import Link from "next/link"
import { useTheme } from "next-themes"
import {
  RiMoonLine, RiSunLine, RiFileCopyLine, RiCheckLine,
  RiCalendarLine, RiFundsLine,
} from "@remixicon/react"
import { tokens } from "@/design-system/tokens"
import { StatusPill, type StatusKey } from "@/design-system/components/StatusPill"
import { ApprovalQueueBadge } from "@/design-system/components/ApprovalQueueBadge"
import { KpiCard, KpiStrip, FIDC_KPI_META } from "@/design-system/components/KpiStrip"
import { KpiBand } from "@/design-system/components/KpiBand"
import { FilterBar, FilterChip, FilterSearch, RemovableChip } from "@/design-system/components/FilterBar"
import { InsightStrip } from "@/design-system/components/InsightStrip"
import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"
import { CommandPaletteProvider, useCommandPalette } from "@/design-system/components/CommandPalette"
import { EChartsCard } from "@/design-system/components/EChartsCard"
import {
  PeriodComparisonTable,
  DecompositionTable,
} from "@/design-system/components/FinancialTable"
import { DenseTable } from "@/design-system/components/DenseTable"
import { Button } from "@/components/tremor/Button"
import { Badge } from "@/components/tremor/Badge"
import { Input } from "@/components/tremor/Input"

const STATUS_KEYS: StatusKey[] = [
  "em-dia", "atrasado-30", "atrasado-60", "inadimplente", "recomprado", "liquidado",
]

const NAV = [
  { id: "tokens",     label: "Tokens" },
  { id: "primitives", label: "Primitives" },
  { id: "components", label: "Components" },
  { id: "patterns",   label: "Patterns" },
]

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = React.useState(false)
  function copy() {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }
  return (
    <button
      type="button"
      onClick={copy}
      className="inline-flex items-center gap-1 rounded bg-gray-100 dark:bg-gray-800 px-2 py-0.5 text-[10px] font-medium text-gray-500 dark:text-gray-400 hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
    >
      {copied ? <RiCheckLine className="size-3 text-emerald-500" /> : <RiFileCopyLine className="size-3" />}
      {copied ? "Copiado" : text}
    </button>
  )
}

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24 space-y-4">
      <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-50">{title}</h2>
      {children}
    </section>
  )
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded border border-gray-200 dark:border-gray-900 bg-white dark:bg-[#090E1A] p-5 shadow-xs">
      <p className="mb-3 text-[11px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600">{title}</p>
      {children}
    </div>
  )
}

function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const dark = resolvedTheme === "dark"
  return (
    <button
      type="button"
      onClick={() => setTheme(dark ? "light" : "dark")}
      className="flex size-8 items-center justify-center rounded border border-gray-200 dark:border-gray-800 hover:bg-gray-50 dark:hover:bg-gray-900"
      aria-label="Alternar tema"
    >
      {dark ? <RiSunLine className="size-4" /> : <RiMoonLine className="size-4" />}
    </button>
  )
}

function CommandPaletteTrigger() {
  const { setOpen } = useCommandPalette()
  return (
    <Button variant="secondary" onClick={() => setOpen(true)}>
      Abrir command palette (⌘K)
    </Button>
  )
}

const SAMPLE_CHART = {
  grid: { top: 16, right: 8, bottom: 32, left: 48 },
  xAxis: { type: "category" as const, data: ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun"] },
  yAxis: { type: "value" as const },
  series: [{
    type: "line" as const,
    data: [100, 105, 108, 112, 110, 115],
    smooth: true,
    symbol: "none",
    areaStyle: { opacity: 0.08 },
    itemStyle: { color: tokens.colors.chart[0] },
  }],
  tooltip: { trigger: "axis" as const },
}

export function DesignSystemClient() {
  const [search, setSearch] = React.useState("")
  const [statusFilter, setStatusFilter] = React.useState<StatusKey | "all">("all")
  const [drillOpen, setDrillOpen] = React.useState(false)

  return (
    <CommandPaletteProvider>
      <div className="min-h-screen bg-gray-50 dark:bg-gray-925 text-gray-900 dark:text-gray-50">
        <header className="sticky top-0 z-20 flex items-center gap-4 border-b border-gray-200 dark:border-gray-800 bg-white/80 dark:bg-gray-950/80 backdrop-blur px-6 py-3">
          <Link href="/" className="text-sm font-semibold">Strata Design System</Link>
          <span className="text-xs text-gray-500">/design</span>
          <nav className="ml-6 flex items-center gap-3">
            {NAV.map((s) => (
              <a key={s.id} href={`#${s.id}`} className="text-xs text-gray-500 hover:text-gray-900 dark:hover:text-gray-50">
                {s.label}
              </a>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <ThemeToggle />
          </div>
        </header>

        <main className="mx-auto max-w-5xl space-y-12 px-6 py-10">

          <Section id="tokens" title="1. Tokens">
            <Card title="Brand colors">
              <div className="grid grid-cols-3 gap-3">
                {Object.entries(tokens.colors.brand).map(([k, v]) => (
                  <div key={k} className="space-y-1">
                    <div className="h-12 w-full rounded" style={{ background: v }} />
                    <div className="flex items-center justify-between text-xs">
                      <span className="font-medium">{k}</span>
                      <CopyButton text={v} />
                    </div>
                  </div>
                ))}
              </div>
            </Card>

            <Card title="Chart palette (8-color rotation)">
              <div className="flex gap-1.5">
                {tokens.colors.chart.map((c, i) => (
                  <div key={i} className="flex flex-1 flex-col items-center gap-1">
                    <div className="h-10 w-full rounded" style={{ background: c }} />
                    <span className="text-[10px] font-mono text-gray-500">{c}</span>
                  </div>
                ))}
              </div>
            </Card>

            <Card title="Status colors">
              <div className="flex flex-wrap gap-2">
                {STATUS_KEYS.map((k) => (
                  <StatusPill key={k} status={k} />
                ))}
              </div>
            </Card>

            <Card title="Typography & spacing">
              <div className="space-y-2 text-sm">
                <p>Inter (next/font, variable). Tabular nums on numbers. Mono on IDs.</p>
                <p className="font-mono tabular-nums text-blue-600 dark:text-blue-400">CCB-2024-001234</p>
                <p className="tabular-nums">R$ 1.234.567,89 — 12,34%</p>
                <p className="text-xs text-gray-500">
                  sidebar:&nbsp;{tokens.spacing.sidebarExpanded} / {tokens.spacing.sidebarCollapsed} ·
                  header:&nbsp;{tokens.spacing.headerH} ·
                  filterBar:&nbsp;{tokens.spacing.filterBarH}
                </p>
              </div>
            </Card>
          </Section>

          <Section id="primitives" title="2. Primitives (Tremor Raw)">
            <Card title="Buttons">
              <div className="flex flex-wrap gap-2">
                <Button variant="primary">Primary</Button>
                <Button variant="secondary">Secondary</Button>
                <Button variant="ghost">Ghost</Button>
                <Button variant="destructive">Destructive</Button>
                <Button variant="primary" disabled>Disabled</Button>
              </div>
            </Card>

            <Card title="Badges">
              <div className="flex flex-wrap gap-2">
                <Badge variant="default">Default</Badge>
                <Badge variant="success">Success</Badge>
                <Badge variant="warning">Warning</Badge>
                <Badge variant="error">Error</Badge>
                <Badge variant="neutral">Neutral</Badge>
              </div>
            </Card>

            <Card title="Input">
              <Input placeholder="Buscar cessões..." className="max-w-sm" />
            </Card>
          </Section>

          <Section id="components" title="3. Components">
            <Card title="StatusPill — pill + dot variants">
              <div className="space-y-3">
                <div className="flex flex-wrap gap-2">
                  {STATUS_KEYS.map((k) => <StatusPill key={k} status={k} />)}
                </div>
                <div className="flex flex-wrap gap-3">
                  {STATUS_KEYS.map((k) => <StatusPill key={k} status={k} variant="dot" />)}
                </div>
              </div>
            </Card>

            <Card title="ApprovalQueueBadge">
              <div className="flex items-center gap-4">
                <span className="text-sm">Pendentes:</span>
                <ApprovalQueueBadge count={3} />
                <ApprovalQueueBadge count={42} />
                <ApprovalQueueBadge count={150} />
              </div>
            </Card>

            <Card title="KpiBand — banda de KPI CANONICA Strata (decisao Ricardo 2026-06-12)">
              <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
                UMA banda continua (nao cards individuais): eyebrow 10px uppercase ·
                valor 22px semibold NEUTRO · delta 12px colorido (tone) · sub 12px gray ·
                divider parcial entre colunas. KPI cujo numero e de um grafico usa o
                headerKpi do proprio chart (mesma familia visual). Familia cota-sub
                (CotaSubStatusBand e a variante local com pills de status).
              </p>
              <KpiBand
                items={[
                  { eyebrow: "PL Sub (MEC) · 10/06/2026", value: "R$ 4,57 mi" },
                  { eyebrow: "Variação do dia", value: "+R$ 32,8 mil", delta: { value: "+0,72%", tone: "positive" }, sub: "vs D-1" },
                  { eyebrow: "Mora do mês", value: "R$ 189,4 mil", delta: { value: "+12,4%", tone: "negative" }, sub: "vs mês ant." },
                  { eyebrow: "Perdões totais", value: "245" },
                ]}
              />
            </Card>

            <Card title="KpiStrip — legado (so para Metricas Complementares / paginas-resumo com sparkline)">
              <KpiStrip>
                <KpiCard {...FIDC_KPI_META.pl} value="R$ 124,5M" sub="abr/26" delta={{ value: 2.34, suffix: "%" }} variant="default" />
                <KpiCard {...FIDC_KPI_META.rentabilidade} value="112,4%" delta={{ value: 3.1, suffix: "pp" }} variant="default" />
                <KpiCard
                  {...FIDC_KPI_META.inadimplencia}
                  value="3,2%"
                  delta={{ value: 0.4, suffix: "pp", direction: "up", good: false }}
                  currentValue={3.2}
                  variant="default"
                />
                <KpiCard
                  {...FIDC_KPI_META.pdd}
                  value="2,1%"
                  delta={{ value: 0.1, suffix: "pp", direction: "up", good: false }}
                  currentValue={2.1}
                  variant="default"
                />
                <KpiCard
                  {...FIDC_KPI_META.cessoesPendentes}
                  value="42"
                  currentValue={42}
                  variant="default"
                />
              </KpiStrip>
            </Card>

            <Card title="KpiStrip — hero feel (cols=4)">
              <KpiStrip cols={4}>
                <KpiCard {...FIDC_KPI_META.pl} value="R$ 124,5M" sub="abr/26" delta={{ value: 2.34, suffix: "%" }} variant="default" />
                <KpiCard {...FIDC_KPI_META.rentabilidade} value="112,4%" delta={{ value: 3.1, suffix: "pp" }} variant="default" />
                <KpiCard
                  {...FIDC_KPI_META.inadimplencia}
                  value="3,2%"
                  delta={{ value: 0.4, suffix: "pp", direction: "up", good: false }}
                  currentValue={3.2}
                  variant="default"
                />
                <KpiCard
                  {...FIDC_KPI_META.cessoesPendentes}
                  value="42"
                  currentValue={42}
                  variant="default"
                />
              </KpiStrip>
            </Card>

            <Card title="FilterBar">
              <FilterBar>
                <FilterSearch
                  placeholder="Buscar..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  onClear={() => setSearch("")}
                />
                <FilterChip
                  icon={RiCalendarLine}
                  label="Período"
                  value="30 dias"
                />
                <FilterChip
                  icon={RiFundsLine}
                  label="Status"
                  value={statusFilter === "all" ? "Todos" : statusFilter}
                  active={statusFilter !== "all"}
                />
                {statusFilter !== "all" && (
                  <RemovableChip label="Status" value={statusFilter} onRemove={() => setStatusFilter("all")} />
                )}
              </FilterBar>
            </Card>

            <Card title="InsightStrip — slim AI insight (handoff A1b)">
              <p className="mb-3 text-xs text-gray-500 dark:text-gray-400">
                Single-line 38px violeta. Primeiro insight inline + popover &quot;+N analises&quot; + dismiss-localStorage.
              </p>
              <InsightStrip
                insights={[
                  { id: "1", text: "Inadimplencia de 3,2% (+0,4pp) concentrada em Acme Ltda — acima do limite de 25%." },
                  { id: "2", text: "PDD caiu 5,2% apos recuperacao de R$ 110k no cedente Nexus em mar/26." },
                  { id: "3", text: "Volume de cessoes crescendo pelo 4o mes consecutivo." },
                ]}
                storageKey="strata:design-system:insight-strip-demo"
              />
            </Card>

            <Card title="EChartsCard">
              <EChartsCard
                title="Rentabilidade vs CDI"
                caption="Últimos 6 meses"
                option={SAMPLE_CHART}
                height={180}
              />
            </Card>

            <Card title="PeriodComparisonTable (IBCS T01/T02)">
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                Comparativo de períodos com notação IBCS: cenários (PY/PL/AC/FC) identificados
                por barra no header, variâncias nomeadas pela fórmula, cor exclusiva da variância.
                <strong> Use</strong> para métricas × períodos/cenários com Δ.
                <strong> Não use</strong> para listagem transacional (DataTable) nem série longa (CompactSeriesTable).
              </p>
              <PeriodComparisonTable
                title={{ entity: "REALINVEST FIDC", measure: "Volume operado", unit: "R$ mil", note: "2026 PY, AC" }}
                scenarios={["PY", "AC"]}
                blocks={[{ key: "mes", label: "Mai/26" }, { key: "ytd", label: "Jan–Mai/26" }]}
                variance="abs+pct"
                rows={[
                  { label: "Antecipação de recebíveis", values: { mes: { PY: 1180, AC: 1310 }, ytd: { PY: 5420, AC: 6105 } } },
                  { label: "Conta garantida", values: { mes: { PY: 412, AC: 388 }, ytd: { PY: 2010, AC: 1956 } }, annotation: 1 },
                  { label: "Cheque", values: { mes: { PY: 96, AC: 74 }, ytd: { PY: 470, AC: 391 } } },
                  { label: "Total", emphasis: "total", values: { mes: { PY: 1688, AC: 1772 }, ytd: { PY: 7900, AC: 8452 } } },
                ]}
                annotations={[{ ref: 1, text: "Queda por encerramento de limite de 2 cedentes em abr/26." }]}
              />
              <div className="mt-3">
                <CopyButton text={`import { PeriodComparisonTable } from "@/design-system/components"`} />
              </div>
            </Card>

            <Card title="DecompositionTable (IBCS T03/T04)">
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                Esquema de cálculo nas linhas (+/−/=) com reconciliação automática (§14.6):
                linha &quot;=&quot; divergente da soma exibe chip de resíduo; cauda longa colapsa em
                &quot;Outros (N)&quot; — nunca corta. <strong>Use</strong> para drill/decomposição de headline e
                demonstrativos. <strong>Não use</strong> quando não há total a reconciliar.
              </p>
              <DecompositionTable
                title={{ entity: "REALINVEST FIDC", measure: "Receita de aquisição", unit: "R$ mil", note: "Mai/26 AC" }}
                collapseAfter={2}
                rows={[
                  { op: "+", label: "Deságio", values: 842 },
                  { op: "+", label: "Multa", values: 37 },
                  { op: "+", label: "Mora", values: 21 },
                  { op: "+", label: "Tarifas", values: 12 },
                  { op: "=", label: "Receita bruta", values: 912 },
                  { op: "-", label: "Recompras", values: 64 },
                  { op: "=", label: "Receita líquida", values: 848 },
                ]}
              />
              <div className="mt-3">
                <CopyButton text={`import { DecompositionTable } from "@/design-system/components"`} />
              </div>
            </Card>

            <Card title="DenseTable">
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-3">
                Tabela densa &quot;limpa&quot; de LEITURA — preenche o gap entre a
                pesada <strong>DataTable</strong> (toolbar/sort/export/virtualização) e a
                <strong> CompactSeriesTable</strong> (série transposta). Colunas tipadas
                (`texto`/`numero`/`brl`/`pct`/`data`) com alinhamento e `tableTokens`;
                rodapé de reconciliação opcional (§14.6). <strong>Use</strong> em blocos de
                dossiê, fichas e breakdowns mês × valor. <strong>Não use</strong> para
                listagem grande (DataTable) nem série temporal longa (CompactSeriesTable).
              </p>
              <DenseTable
                caption="Faturamento mensal"
                columns={[
                  { key: "mes", label: "Mês", format: "data" },
                  { key: "receita", label: "Receita", format: "brl" },
                  { key: "share", label: "% do total", format: "pct" },
                ]}
                rows={[
                  { mes: "2026-01", receita: 184000, share: 18.2 },
                  { mes: "2026-02", receita: 201500, share: 19.9 },
                  { mes: "2026-03", receita: 173200, share: 17.1 },
                  { mes: "2026-04", receita: 252800, share: 25.0 },
                ]}
                footer={{ mes: "Total", receita: 811500, share: 80.2 }}
              />
              <div className="mt-3">
                <CopyButton text={`import { DenseTable } from "@/design-system/components"`} />
              </div>
            </Card>

            <Card title="DrillDownSheet">
              <Button variant="primary" onClick={() => setDrillOpen(true)}>Abrir drill-down</Button>
              <DrillDownSheet open={drillOpen} onClose={() => setDrillOpen(false)} size="md" title="Cessão CCB-001234">
                <DrillDownSheet.Header
                  breadcrumb={["Cessões", "CCB-001234"]}
                  statusSlot={<StatusPill status="em-dia" />}
                />
                <DrillDownSheet.Hero
                  id="CCB-2024-001234"
                  title="Metalúrgica São Paulo Ltda"
                  value={185400}
                  delta={{ value: 2.5, label: "vs mês anterior" }}
                />
                <DrillDownSheet.Body>
                  <DrillDownSheet.PropertyList items={[
                    { label: "Sacado", value: "Auto Peças Brasil" },
                    { label: "Vencimento", value: "15/06/2026" },
                    { label: "Prazo", value: 45, suffix: "dias", type: "number" },
                    { label: "Inadimpl.", value: 0, type: "percentage" },
                  ]} />
                </DrillDownSheet.Body>
                <DrillDownSheet.Footer>
                  <Button variant="ghost" onClick={() => setDrillOpen(false)}>Fechar</Button>
                </DrillDownSheet.Footer>
              </DrillDownSheet>
            </Card>

            <Card title="CommandPalette (⌘K)">
              <CommandPaletteTrigger />
            </Card>
          </Section>

          <Section id="patterns" title="4. Patterns">
            <Card title="DashboardBiPadrao (A1b · 2026-05-02)">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                Composição (chrome 152px): Title row 70px (PageHeader com subtitle visível) → Toolbar unificada 44px sticky (tabs L3 + filtros) → InsightStrip 38px (violeta, dismiss-localStorage) → Conteúdo (KpiStrip + tabs + DataTable) → ProvenanceFooter. AIPanel + DrillDownSheet laterais.
              </p>
              <p className="text-xs text-gray-500 dark:text-gray-400 mb-2">
                FilterChip active state: dot laranja 5×5 (<code className="font-mono">--color-active-indicator</code>) + value font-semibold. Sem fundo azul.
              </p>
              <code className="text-xs font-mono text-blue-600 dark:text-blue-400">
                {`import { DashboardBiPadrao } from "@/design-system/patterns"`}
              </code>
            </Card>

            <Card title="DashboardOperacional">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                Composição: PageHeader → FilterBar → KpiStrip (4 KPIs) → 2×2 EChartsCards → DataTable. Para dashboards mais simples sem AI panel.
              </p>
              <code className="text-xs font-mono text-blue-600 dark:text-blue-400">
                {`import { DashboardOperacional } from "@/design-system/patterns"`}
              </code>
            </Card>

            <Card title="ListagemComDrilldown">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                Composição: PageHeader → FilterBar → DataTable → DrillDownSheet (URL-synced via ?selected). Para listagens de DADOS de domínio (cessões, cedentes, sacados).
              </p>
              <code className="text-xs font-mono text-blue-600 dark:text-blue-400">
                {`import { ListagemComDrilldown } from "@/design-system/patterns"`}
              </code>
            </Card>

            <Card title="ListagemCrudInline">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                Composição: PageHeader (com &quot;+ Novo&quot;) → DataTableShell → DrillDownSheet (?action=new / ?selected) → Dialog destrutivo. Para CRUD ADMIN com identidade tabular (usuários, etiquetas, credenciais). Primeira instância: /admin/ia/providers.
              </p>
              <code className="text-xs font-mono text-blue-600 dark:text-blue-400">
                {`import { ListagemCrudInline } from "@/design-system/patterns"`}
              </code>
            </Card>

            <Card title="ListagemCrudExpand">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                Variante de ListagemCrudInline com linhas que expandem inline (em vez de drawer lateral). Use quando o detail couber numa expansão e o usuário ganhar com comparação lado-a-lado.
              </p>
              <code className="text-xs font-mono text-blue-600 dark:text-blue-400">
                {`import { ListagemCrudExpand } from "@/design-system/patterns"`}
              </code>
            </Card>

            <Card title="ListagemCrudCards">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                Composição: PageHeader (title + info tooltip + subtitle eyebrow + &quot;+ Novo&quot;) → Card[FilterSearch + SegmentSwitch + counter] → grid 1/2/3 de EntityCard → DrillDownSheet → Dialog destrutivo. Para CRUD ADMIN com identidade VISUAL (workflows, agentes, dashboards salvos, conexões). Primeira instância: /credito/workflows.
              </p>
              <code className="text-xs font-mono text-blue-600 dark:text-blue-400">
                {`import { ListagemCrudCards } from "@/design-system/patterns"`}
              </code>
            </Card>
          </Section>

          <footer className="border-t border-gray-200 dark:border-gray-800 pt-6 text-center text-xs text-gray-400">
            <p>Strata Design System · /design route is dev-only</p>
            <p>Tokens, components and patterns under <code className="font-mono">@/design-system/*</code></p>
          </footer>
        </main>
      </div>
    </CommandPaletteProvider>
  )
}
