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
import { FilterBar, FilterChip, FilterSearch, RemovableChip } from "@/design-system/components/FilterBar"
import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"
import { CommandPaletteProvider, useCommandPalette } from "@/design-system/components/CommandPalette"
import { EChartsCard } from "@/design-system/components/EChartsCard"
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
                <p>Geist Sans (variable). Tabular nums on numbers. Mono on IDs.</p>
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

            <Card title="KpiStrip — 3 variants">
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

            <Card title="EChartsCard">
              <EChartsCard
                title="Rentabilidade vs CDI"
                caption="Últimos 6 meses"
                option={SAMPLE_CHART}
                height={180}
              />
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
            <Card title="DashboardOperacional">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                Composição: PageHeader → FilterBar → KpiStrip → 2×2 chart grid → DataTable
              </p>
              <code className="text-xs font-mono text-blue-600 dark:text-blue-400">
                {`import { DashboardOperacional } from "@/design-system/patterns"`}
              </code>
            </Card>

            <Card title="ListagemComDrilldown">
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                Composição: PageHeader → FilterBar → DataTable → DrillDownSheet (URL-synced)
              </p>
              <code className="text-xs font-mono text-blue-600 dark:text-blue-400">
                {`import { ListagemComDrilldown } from "@/design-system/patterns"`}
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
