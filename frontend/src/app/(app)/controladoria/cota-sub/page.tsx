// src/app/(app)/controladoria/cota-sub/page.tsx
//
// Controladoria · Cota Subordinada — analise diaria comparativa (D-1 vs D0).
// Pagina derivada do pattern `DashboardBiPadrao`, alinhada com o shell canonico
// consolidado em `bi/operacoes2` (toolbar unificada 52px com TabNavigation +
// FilterBar lado a lado, scroll-shadow, ProvenanceFooter).
//
// Equacao do dia: ΔCota Sub = ΔAtivo − ΔPassivo Contabil − ΔEquity (Mez+Sr)
//
// Arquitetura de abas (4):
//   1. "Eventos do dia"  (default, hero) — KpiStrip + Waterfall + Insights +
//                                          BalanceTable evoluida (foco no Δ)
//   2. "Balanco"                         — BalanceTable contabil + Pagamentos
//   3. "Movimentacoes"                   — tabela movimentacoes + charts
//   4. "Cotistas"                        — placeholder (futuro)
//
// HOW TO ADAPT (mocks → queries reais):
//   1. MOCK_MOVIMENTACOES → useQuery `/controladoria/cota-sub/movimentacoes`
//   2. Series ECharts da aba "Movimentacoes" → wh_posicao_cota_fundo +
//      wh_movimentacao_cotista (silver)
//   3. IA da pagina: chat-investigador (ChatVariacaoDrawer) ligado ao botao
//      "IA" do DashboardHeaderActions + atalho Cmd/Ctrl+I. Endpoint real:
//      controladoria.cotaSubVariacaoChat. Sem FAB, sem AIPanel stub.

"use client"

import * as React from "react"
import {
  RiAlertLine,
  RiCalendarLine,
  RiCheckLine,
  RiCloudOffLine,
  RiDownloadLine,
  RiEqualizerLine,
  RiFundsLine,
  RiPlayLine,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import type { EChartsOption } from "echarts"

import { format } from "date-fns"
import { ptBR } from "date-fns/locale"
import { useQueryState } from "nuqs"

import { cx, focusRing } from "@/lib/utils"
import { Button } from "@/components/tremor/Button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/tremor/Popover"
import {
  TabNavigation,
  TabNavigationLink,
} from "@/components/tremor/TabNavigation"

import { PageHeader } from "@/design-system/components/PageHeader"
import { DashboardHeaderActions } from "@/design-system/components/DashboardHeaderActions"
import { VizParam } from "@/design-system/components/VizParam"
import {
  EChartsCard,
} from "@/design-system/components/EChartsCard"
import {
  FilterChip,
  RemovableChip,
  SavedViewsDropdown,
} from "@/design-system/components/FilterBar"
import { EmptyState } from "@/design-system/components/EmptyState"
import { Insight, InsightBar } from "@/design-system/components/Insight"
import { useUAs } from "@/lib/hooks/cadastros"
import {
  COTA_SUB_REPORTS,
  useBalancoEstrutural,
  useCotaSubReadiness,
  useDatasDisponiveis,
} from "@/lib/hooks/controladoria"
import { useCreateBackfill } from "@/lib/hooks/integracoes"
import {
  QiTechCoverageStrip,
  type CoverageStripEntry,
} from "@/design-system/components/QiTechCoverageStrip"
import {
  CurrencyCell,
  DataTable,
  DateCell,
  IdCell,
  StatusCell,
} from "@/design-system/components/DataTable"
import {
  DrillDownSheet,
  type TimelineEventDef,
} from "@/design-system/components/DrillDownSheet"
import { type AIInsight } from "@/design-system/components/AIPanel"
import { tokens, type StatusKey } from "@/design-system/tokens"
import { useScrollShadow } from "@/lib/hooks/use-scroll-shadow"

import { toast } from "sonner"

import { ActiveBackfillJobsPanel } from "./_components/ActiveBackfillJobsPanel"
import { AtencoesDoDia } from "./_components/AtencoesDoDia"
import { CotaSubStatusBand } from "./_components/CotaSubStatusBand"
import { BalancoPatrimonialHero } from "./_components/BalancoPatrimonialHero"
import { NaoReconhecidosPanel } from "./_components/NaoReconhecidosPanel"
import { CategoriaDrillSheet } from "./_components/CategoriaDrillSheet"
import { DrillCprContent } from "./_components/DrillCprContent"
import { DrillDcContent } from "./_components/DrillDcContent"
import { ChatVariacaoDrawer } from "./_components/ChatVariacaoDrawer"
import { ResumoGrupos } from "./_components/ResumoGrupos"
import { DrillContasAPagarContent } from "./_components/DrillContasAPagarContent"
import { DrillCotasContent } from "./_components/DrillCotasContent"
import { DrillOrigemContent } from "./_components/DrillOrigemContent"
import { DrillAplicacoesContent } from "./_components/DrillAplicacoesContent"
import { DrillDisponibilidadesContent } from "./_components/DrillDisponibilidadesContent"
import { DrillPddContent } from "./_components/DrillPddContent"
import { VariacaoWaterfall } from "./_components/VariacaoWaterfall"
import { VariacaoDiariaCard } from "./_components/VariacaoDiariaCard"
import { useVariacaoResumo, useVariacaoDiariaSerie } from "@/lib/hooks/controladoria"
import type {
  BalancoEstruturalResponse,
  CategoriaPatrimonial,
  CategoriaPatrimonialKey,
} from "@/lib/api-client"

/**
 * Mapeia a linha drilada do balanco estrutural pro shape `CategoriaPatrimonial`
 * que o BalancoInspector/CategoriaDrillSheet consomem (header do drill).
 * O drill usa `drill_key`. CPR foi separado por sinal em duas linhas/chaves
 * (`cpr_receber`=ativo / `cpr_pagar`=passivo, 2026-05-27) — cada chave casa
 * com exatamente uma linha, entao o ramo generico ja resolve label + tipo.
 */
function toInspectorCategoria(
  data: BalancoEstruturalResponse | undefined,
  drill: CategoriaPatrimonialKey | null,
): CategoriaPatrimonial | undefined {
  if (!data || !drill) return undefined
  const matches = [...data.ativos, ...data.passivos].filter((l) => l.drill_key === drill)
  if (matches.length === 0) return undefined
  const l = matches[0]
  return {
    key:    drill,
    label:  l.label,
    tipo:   l.natureza === "passivo" ? "passivo" : "ativo",
    d1:     l.d1,
    d0:     l.d0,
    delta:  l.delta,
    source: l.source,
    contra: l.natureza === "contra_ativo",
  }
}

// Linhas com drill generico "ver origem" (listagem de linhas-fonte +
// prova de fechamento). DC/PDD/CPR tem drills ricos proprios e ficam fora.
const ORIGEM_KEYS: ReadonlySet<CategoriaPatrimonialKey> = new Set<CategoriaPatrimonialKey>([
  "titulos_publicos", "op_estruturadas", "fundos_di", "compromissada",
  "outros_ativos", "tesouraria", "saldo_conta_corrente",
])
// Linhas de Cota/Passivo de cotista -> drill rico do Auditor de Cotas (2026-05-31).
const COTAS_KEYS: ReadonlySet<CategoriaPatrimonialKey> = new Set<CategoriaPatrimonialKey>([
  "senior", "mezanino", "cpr_obrigacoes_cotistas",
])

// Grupos do waterfall que NAO sao linha do balanco — drill sintetico (header
// montado do resumo, nao do balanco estrutural). Ver drilledCategoriaObj.
type DrillKey = CategoriaPatrimonialKey | "aplicacoes" | "disponibilidades"

// ───────────────────────────────────────────────────────────────────────────
// Tipos + Mocks
// ───────────────────────────────────────────────────────────────────────────

type MovimentacaoTipo = "subscricao" | "resgate"

type MovimentacaoRow = {
  id:      string
  cotista: string
  classe:  "Mezanino" | "Junior"
  tipo:    MovimentacaoTipo
  valor:   number
  data:    string
  status:  StatusKey
}

const MOCK_MOVIMENTACOES: MovimentacaoRow[] = [
  { id: "MOV-2026-000821", cotista: "Aurora Capital",        classe: "Mezanino", tipo: "subscricao", valor:   850_000, data: "2026-04-22", status: "liquidado" },
  { id: "MOV-2026-000822", cotista: "Vanguard FII",          classe: "Junior",   tipo: "subscricao", valor:   320_000, data: "2026-04-20", status: "em-dia" },
  { id: "MOV-2026-000823", cotista: "Helios Asset",          classe: "Mezanino", tipo: "resgate",    valor:   180_000, data: "2026-04-18", status: "em-dia" },
  { id: "MOV-2026-000824", cotista: "Atlas Investimentos",   classe: "Junior",   tipo: "resgate",    valor:    95_000, data: "2026-04-15", status: "liquidado" },
  { id: "MOV-2026-000825", cotista: "Aurora Capital",        classe: "Mezanino", tipo: "subscricao", valor: 1_200_000, data: "2026-04-10", status: "liquidado" },
  { id: "MOV-2026-000826", cotista: "Polaris Family Office", classe: "Junior",   tipo: "subscricao", valor:   540_000, data: "2026-04-08", status: "liquidado" },
]

const MOCK_INSIGHTS: AIInsight[] = [
  { text: "Subordinacao efetiva em 15,0% (+0,3pp), acima do minimo regulamentar de 10%. Margem confortavel para absorver perdas." },
  { text: "Rentabilidade da Cota Sub em 118,2% do CDI — 3 meses consecutivos batendo o benchmark." },
  { text: "Top 3 cotistas concentram 62% do PL subordinado — acima do alerta interno de 50%. Considerar diversificacao." },
]

// ───────────────────────────────────────────────────────────────────────────
// L3 Tabs
// ───────────────────────────────────────────────────────────────────────────

const TABS = [
  { key: "resumo",        label: "Resumo do dia" },
  { key: "balanco",       label: "Balanço" },
  { key: "movimentacoes", label: "Movimentações" },
  { key: "cotistas",      label: "Cotistas" },
] as const

type TabKey = (typeof TABS)[number]["key"]

// ───────────────────────────────────────────────────────────────────────────
// Filtros
// ───────────────────────────────────────────────────────────────────────────

const CLASSE_OPTIONS = ["Todas", "Subordinada Mezanino", "Subordinada Junior"] as const

type ClasseOption = (typeof CLASSE_OPTIONS)[number]

// Filtros dinamicos (adicionados via "Mais filtros"). Default values
// definem o "Todos/Nenhum" do filtro — quando o user troca, o chip vira
// active e ganha botao de remover.
type DynamicFilterKey = "Cotista" | "Status" | "Classe op." | "Origem"

const DYNAMIC_FILTER_OPTIONS: Record<DynamicFilterKey, readonly string[]> = {
  Cotista:     ["Todos", "Aurora Capital", "Vanguard FII", "Helios Asset", "Atlas Investimentos", "Polaris Family Office"],
  Status:      ["Todos", "Em dia", "Liquidado", "Atrasado", "Inadimplente"],
  "Classe op.": ["Todas", "Multiclasse", "Padronizado", "Nao-padronizado"],
  Origem:      ["Todas", "QiTech", "Bitfin", "Manual"],
}

type DynamicFilter = { key: DynamicFilterKey; value: string }

// Filtros inline na tabela de movimentacoes (escopo: tabela apenas)
const TABLE_STATUS_OPTIONS  = DYNAMIC_FILTER_OPTIONS.Status
const TABLE_COTISTA_OPTIONS = DYNAMIC_FILTER_OPTIONS.Cotista

// ───────────────────────────────────────────────────────────────────────────
// ECharts options (mock — substituir pelas series reais)
// ───────────────────────────────────────────────────────────────────────────

const MONTHS = ["Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez", "Jan", "Fev", "Mar", "Abr"]
const CHART_COLORS = tokens.colors.chart

const plCotaSubOption: EChartsOption = {
  grid: { top: 12, right: 12, bottom: 28, left: 52 },
  xAxis: { type: "category", data: MONTHS, axisTick: { show: false } },
  yAxis: { type: "value", min: 14, axisLabel: { formatter: "R$ {value}M" } },
  series: [
    {
      type: "line", smooth: true, symbol: "none",
      data: [14.8, 15.2, 15.6, 15.9, 16.2, 16.5, 16.8, 17.1, 17.4, 17.9, 18.3, 18.7],
      lineStyle: { color: "#3B82F6", width: 2 },
      areaStyle: {
        color: {
          type: "linear", x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: "rgba(59,130,246,0.20)" },
            { offset: 1, color: "rgba(59,130,246,0)" },
          ],
        },
      },
    },
  ],
  tooltip: { trigger: "axis" },
}

const subscRescOption: EChartsOption = {
  grid: { top: 8, right: 12, bottom: 28, left: 48 },
  xAxis: { type: "category", data: MONTHS, axisTick: { show: false } },
  yAxis: { type: "value", axisLabel: { formatter: "R$ {value}M" } },
  series: [
    { name: "Subscricao", type: "bar", data: [1.2, 0.8, 1.4, 1.0, 1.6, 1.3, 1.5, 1.1, 1.8, 1.4, 2.1, 2.4], itemStyle: { color: "#10B981" } },
    { name: "Resgate",    type: "bar", data: [0.3, 0.5, 0.4, 0.6, 0.4, 0.5, 0.7, 0.6, 0.5, 0.8, 0.6, 0.7], itemStyle: { color: "#EF4444" } },
  ],
  legend:  { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
  tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
}

const rentabSubOption: EChartsOption = {
  grid: { top: 12, right: 12, bottom: 28, left: 48 },
  xAxis: { type: "category", data: MONTHS, axisTick: { show: false } },
  yAxis: { type: "value", min: 100, axisLabel: { formatter: "{value}%" } },
  series: [
    {
      name: "Cota Sub", type: "line", smooth: true, symbol: "none",
      data: [102, 104, 107, 109, 110, 112, 113, 114, 115, 116, 117, 118],
      lineStyle: { color: "#3B82F6", width: 2 },
    },
    {
      name: "CDI", type: "line", smooth: true, symbol: "none",
      data: [101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112],
      lineStyle: { color: "#9CA3AF", width: 1.5, type: "dashed" },
    },
  ],
  legend:  { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
  tooltip: { trigger: "axis" },
}

const topCotistasOption: EChartsOption = {
  grid: { top: 8, right: 24, bottom: 8, left: 110 },
  xAxis: { type: "value", axisLabel: { formatter: "{value}%" } },
  yAxis: {
    type: "category",
    data: ["Outros", "Polaris FO", "Atlas Inv.", "Helios Asset", "Vanguard FII", "Aurora Capital"],
    axisTick: { show: false },
  },
  series: [
    {
      type: "bar", barMaxWidth: 18,
      data: [
        { value: 12, itemStyle: { color: "#9CA3AF",       borderRadius: [0, 3, 3, 0] } },
        { value: 8,  itemStyle: { color: CHART_COLORS[5], borderRadius: [0, 3, 3, 0] } },
        { value: 8,  itemStyle: { color: CHART_COLORS[4], borderRadius: [0, 3, 3, 0] } },
        { value: 10, itemStyle: { color: CHART_COLORS[3], borderRadius: [0, 3, 3, 0] } },
        { value: 22, itemStyle: { color: CHART_COLORS[2], borderRadius: [0, 3, 3, 0] } },
        { value: 40, itemStyle: { color: CHART_COLORS[0], borderRadius: [0, 3, 3, 0] } },
      ],
    },
  ],
  tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: "{b}: {c}%" },
}

// ───────────────────────────────────────────────────────────────────────────
// labelForStatus — mapeia StatusKey canonico para o rotulo do filtro inline
// ───────────────────────────────────────────────────────────────────────────

const STATUS_LABEL: Record<StatusKey, string> = {
  "em-dia":       "Em dia",
  "liquidado":    "Liquidado",
  "atrasado-30":  "Atrasado",
  "atrasado-60":  "Atrasado",
  "inadimplente": "Inadimplente",
  "recomprado":   "Liquidado",
}

function labelForStatus(s: StatusKey): string {
  return STATUS_LABEL[s] ?? "Em dia"
}

// ───────────────────────────────────────────────────────────────────────────
// AddFilterMenu — Popover de "Mais filtros" (lista dimensoes disponiveis)
// MOTIVO: MoreFiltersButton canonico hoje nao aceita asChild para Popover
// wrapping; trigger custom espelha a anatomy. Followup: estender o canonico.
// ───────────────────────────────────────────────────────────────────────────

function AddFilterMenu({
  available,
  onAdd,
  disabled = false,
}: {
  available: DynamicFilterKey[]
  onAdd:     (k: DynamicFilterKey) => void
  disabled?: boolean
}) {
  const [open, setOpen] = React.useState(false)
  if (available.length === 0) return null

  if (disabled) {
    return (
      <button
        type="button"
        disabled
        className={cx(
          "inline-flex h-[26px] shrink-0 items-center gap-1.5 whitespace-nowrap rounded-[4px] border px-2.5 text-[13px]",
          "cursor-not-allowed border-gray-200 bg-white opacity-50",
          "dark:border-gray-800 dark:bg-gray-950",
        )}
      >
        <RiEqualizerLine className="size-3.5 shrink-0 text-gray-500 dark:text-gray-400" aria-hidden="true" />
        <span className="font-medium text-gray-900 dark:text-gray-50">Mais filtros</span>
      </button>
    )
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cx(
            "inline-flex h-[26px] shrink-0 items-center gap-1.5 whitespace-nowrap rounded-[4px] border px-2.5 text-[13px] transition-colors duration-100",
            "border-gray-200 bg-white hover:bg-gray-50",
            "dark:border-gray-800 dark:bg-gray-950 dark:hover:bg-gray-900",
            focusRing,
          )}
        >
          <RiEqualizerLine className="size-3.5 shrink-0 text-gray-500 dark:text-gray-400" aria-hidden="true" />
          <span className="font-medium text-gray-900 dark:text-gray-50">Mais filtros</span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" sideOffset={6} className="min-w-44 p-1">
        <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600">
          Dimensao
        </p>
        {available.map((dim) => (
          <button
            key={dim}
            type="button"
            onClick={() => { setOpen(false); onAdd(dim) }}
            className={cx(
              "block w-full rounded px-2 py-1.5 text-left text-sm transition-colors",
              "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
              focusRing,
            )}
          >
            {dim}
          </button>
        ))}
      </PopoverContent>
    </Popover>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Aba "Movimentacoes" — InsightBar (mock) + Charts ECharts + Tabela
// ───────────────────────────────────────────────────────────────────────────

function MovimentacoesTab({
  rows,
  tableStatus,
  setTableStatus,
  tableCotista,
  setTableCotista,
  onRowClick,
}: {
  rows:            MovimentacaoRow[]
  tableStatus:     string
  setTableStatus:  (v: string) => void
  tableCotista:    string
  setTableCotista: (v: string) => void
  onRowClick:      (row: MovimentacaoRow) => void
}) {
  const [plPeriod, setPlPeriod] = React.useState("12M")
  const [subPeriod, setSubPeriod] = React.useState("12M")
  const [insightsDismissed, setInsightsDismissed] = React.useState(false)

  return (
    <div className="flex flex-col gap-4">
      {!insightsDismissed && (
        <InsightBar onDismiss={() => setInsightsDismissed(true)}>
          {MOCK_INSIGHTS.map((ins, i) => (
            <Insight key={i} tone="violet" text={ins.text} />
          ))}
        </InsightBar>
      )}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <EChartsCard
          title="Evolucao do PL Cota Sub"
          caption="Patrimonio liquido subordinado · Bitfin"
          option={plCotaSubOption}
          height={160}
          className="lg:col-span-2"
          actions={
            <VizParam
              options={["12M", "6M", "3M", "1M"]}
              value={plPeriod}
              onChange={setPlPeriod}
            />
          }
        />
        <EChartsCard
          title="Rentabilidade Sub vs CDI"
          caption="Base 100 · mai/25"
          option={rentabSubOption}
          height={160}
        />
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <EChartsCard
          title="Subscricao vs Resgate"
          caption="Movimentacoes mensais (R$ mi)"
          option={subscRescOption}
          height={180}
          actions={
            <VizParam
              options={["12M", "6M", "3M"]}
              value={subPeriod}
              onChange={setSubPeriod}
            />
          }
        />
        <EChartsCard
          title="Top cotistas subordinados"
          caption="Top 5 + Outros · participacao %"
          option={topCotistasOption}
          height={180}
        />
      </div>

      <div className="rounded border border-gray-200 dark:border-gray-800 overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-gray-200 px-4 py-2.5 dark:border-gray-800">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
            Movimentacoes recentes
          </h3>
          <span className="rounded-full border border-gray-200 bg-gray-50 px-1.5 text-[11px] text-gray-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
            {rows.length}
          </span>

          <div className="ml-2 flex items-center gap-1.5">
            <FilterChip
              label="Status"
              value={tableStatus}
              active={tableStatus !== "Todos"}
            >
              <div className="py-1">
                {TABLE_STATUS_OPTIONS.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setTableStatus(opt)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      tableStatus === opt
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{opt}</span>
                    {tableStatus === opt && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                  </button>
                ))}
              </div>
            </FilterChip>

            <FilterChip
              label="Cotista"
              value={tableCotista}
              active={tableCotista !== "Todos"}
            >
              <div className="py-1">
                {TABLE_COTISTA_OPTIONS.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setTableCotista(opt)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      tableCotista === opt
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{opt}</span>
                    {tableCotista === opt && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                  </button>
                ))}
              </div>
            </FilterChip>
          </div>

          <Button variant="ghost" className="ml-auto">
            <RiDownloadLine className="size-3.5" aria-hidden="true" />
            Exportar
          </Button>
        </div>
        <DataTable
          data={rows}
          columns={MOVIMENTACOES_COLUMNS}
          density="compact"
          showColumnManager={false}
          showDensityToggle={false}
          showExport={false}
          virtualize={false}
          onRowClick={onRowClick}
        />
      </div>
    </div>
  )
}

function PlaceholderTab({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16">
      <div className="size-10 rounded-full bg-gray-100 dark:bg-gray-800" aria-hidden="true" />
      <p className="text-sm font-medium text-gray-600 dark:text-gray-400">
        Visao &quot;{label}&quot;
      </p>
      <p className="text-xs text-gray-400 dark:text-gray-600">
        Adapte esta aba para o contexto analitico correspondente.
      </p>
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// DataTable columns (movimentacoes)
// ───────────────────────────────────────────────────────────────────────────

const col = createColumnHelper<MovimentacaoRow>()

const MOVIMENTACOES_COLUMNS: ColumnDef<MovimentacaoRow, unknown>[] = [
  col.accessor("id", {
    header: "ID",
    size:   150,
    cell:   (info) => <IdCell value={info.getValue<string>()} />,
  }) as ColumnDef<MovimentacaoRow, unknown>,
  col.accessor("cotista", {
    header: "Cotista",
    size:   180,
  }) as ColumnDef<MovimentacaoRow, unknown>,
  col.accessor("classe", {
    header: "Classe",
    size:   110,
    cell:   (info) => (
      <span className="text-sm text-gray-500 dark:text-gray-400">
        {info.getValue<string>()}
      </span>
    ),
  }) as ColumnDef<MovimentacaoRow, unknown>,
  col.accessor("tipo", {
    header: "Tipo",
    size:   110,
    cell:   (info) => {
      const tipo  = info.getValue<MovimentacaoTipo>()
      const isSub = tipo === "subscricao"
      return (
        <span className={cx(
          "inline-flex items-center rounded-sm px-1.5 py-0.5 text-[11px] font-medium",
          isSub
            ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
            : "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
        )}>
          {isSub ? "Subscricao" : "Resgate"}
        </span>
      )
    },
  }) as ColumnDef<MovimentacaoRow, unknown>,
  col.accessor("valor", {
    header: "Valor",
    size:   140,
    cell:   (info) => <CurrencyCell value={info.getValue<number>()} />,
  }) as ColumnDef<MovimentacaoRow, unknown>,
  col.accessor("data", {
    header: "Data",
    size:   110,
    cell:   (info) => <DateCell value={info.getValue<string>()} />,
  }) as ColumnDef<MovimentacaoRow, unknown>,
  col.accessor("status", {
    header: "Status",
    size:   140,
    cell:   (info) => <StatusCell value={info.getValue<StatusKey>()} />,
  }) as ColumnDef<MovimentacaoRow, unknown>,
]

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

// Label de competencia "YYYY-MM" -> "Junho/2026" (mes capitalizado).
function fmtCompetenciaLabel(ym: string): string {
  const [y, m] = ym.split("-").map(Number)
  if (!y || !m) return ym
  const s = format(new Date(y, m - 1, 1), "MMMM/yyyy", { locale: ptBR })
  return s.charAt(0).toUpperCase() + s.slice(1)
}

function CotaSubPageInner() {
  const [search, setSearch] = React.useState("")
  // Dia: pagina inteira analisa um unico dia por vez. URL = fonte da verdade
  // (?dia=YYYY-MM-DD, §11.6) — torna o dia deep-linkavel/compartilhavel e e o
  // que o master-detail da aba "Resumo do dia" altera ao clicar no grafico.
  // Fallback = hoje. `day`/`setDay` mantem a assinatura Date pros callsites.
  const today = React.useMemo(() => new Date(), [])
  const [diaParam, setDiaParam] = useQueryState("dia")
  const day = React.useMemo<Date>(() => {
    if (diaParam && /^\d{4}-\d{2}-\d{2}$/.test(diaParam)) {
      const d = new Date(`${diaParam}T00:00:00`)
      if (!isNaN(d.getTime())) return d
    }
    return today
  }, [diaParam, today])
  const setDay = React.useCallback(
    (d: Date) => { void setDiaParam(format(d, "yyyy-MM-dd")) },
    [setDiaParam],
  )
  // Fundo: opcoes vem de Cadastros · UAs do tipo FIDC. "Todos" implica EmptyState.
  const fundosQuery = useUAs({ tipo: "fidc", ativa: true })
  const fundoOptions = React.useMemo(
    () => ["Todos", ...(fundosQuery.data?.map((ua) => ua.nome) ?? [])],
    [fundosQuery.data],
  )
  const [fundo,  setFundo]  = React.useState<string>("Todos")
  const [classe, setClasse] = React.useState<ClasseOption>("Todas")

  // Filtros dinamicos (adicionados via "Mais filtros")
  const [dynamicFilters, setDynamicFilters] = React.useState<DynamicFilter[]>([])

  // Filtros inline da DataTable (escopo: tabela apenas, nao charts)
  const [tableStatus,  setTableStatus]  = React.useState<string>("Todos")
  const [tableCotista, setTableCotista] = React.useState<string>("Todos")

  const [activeTab, setActiveTab] = React.useState<TabKey>("resumo")

  // Atalhos Cmd/Ctrl + 1..4 para tabs (CLAUDE.md §11.6)
  React.useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && ["1", "2", "3", "4"].includes(e.key)) {
        const idx = Number(e.key) - 1
        if (TABS[idx]) {
          e.preventDefault()
          setActiveTab(TABS[idx].key)
        }
      }
    }
    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [])

  const [selected, setSelected] = React.useState<MovimentacaoRow | null>(null)

  // Drill da F2 — abre Sheet lateral direito com DrillDcContent/PddContent/CprContent.
  // Habilitado so pras 3 categorias da F2 via DRILL_ENABLED_F2 do BalancoPatrimonialHero.
  const [drilledCategoria, setDrilledCategoria] = React.useState<DrillKey | null>(null)


  // Lookup do UUID da UA selecionada (endpoint backend exige fundo_id).
  const fundoId = React.useMemo(() => {
    if (fundo === "Todos") return null
    return fundosQuery.data?.find((ua) => ua.nome === fundo)?.id ?? null
  }, [fundo, fundosQuery.data])

  const dayIso          = React.useMemo(() => format(day, "yyyy-MM-dd"), [day])
  const balancoEstruturalQuery = useBalancoEstrutural(fundoId, dayIso)
  // Resumo do dia (redesign 2026-06-01) — waterfall por grupo + atencoes. 0 LLM.
  const resumoQuery = useVariacaoResumo(fundoId, dayIso)
  // Serie diaria da competencia (mes do dia selecionado) — master do
  // master-detail da aba "Resumo do dia". 1 request por competencia.
  const competencia = React.useMemo(() => format(day, "yyyy-MM"), [day])
  const diariaQuery = useVariacaoDiariaSerie(fundoId, competencia)
  // Chat-investigador (Camada 2) — summonable, o UNICO LLM da pagina.
  // Entrada canonica: botao "IA" do DashboardHeaderActions + atalho Cmd/Ctrl+I.
  // (Sem FAB flutuante — CLAUDE.md §7: header e o lar das acoes do dashboard.)
  const [chatOpen, setChatOpen] = React.useState(false)

  // Atalho Cmd/Ctrl+I abre/fecha o chat-investigador (paridade com o botao IA).
  React.useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "i") {
        e.preventDefault()
        setChatOpen((o) => !o)
      }
    }
    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [])
  const drilledCategoriaObj = React.useMemo<CategoriaPatrimonial | undefined>(() => {
    // Aplicacoes/Disponibilidades NAO sao linha do balanco — header sintetico a
    // partir do grupo do resumo (delta = impacto giro-limpo da barra).
    if (drilledCategoria === "aplicacoes" || drilledCategoria === "disponibilidades") {
      const g = resumoQuery.data?.grupos.find((x) => x.key === drilledCategoria)
      if (!g) return undefined
      return {
        key:    drilledCategoria as CategoriaPatrimonial["key"],
        label:  g.label,
        tipo:   "ativo",
        d1:     0,
        d0:     0,
        delta:  g.impacto_pl_sub,
        source: drilledCategoria === "aplicacoes" ? "wh_posicao_cota_fundo" : "wh_movimento_caixa",
        contra: false,
        // Aplicacoes/Disponibilidades nao sao linha de balanco com posicao D0/D-1
        // — o header mostra so o IMPACTO giro-limpo (= delta), sem "vs D-1".
        impactOnly: true,
      }
    }
    return toInspectorCategoria(balancoEstruturalQuery.data, drilledCategoria as CategoriaPatrimonialKey | null)
  }, [balancoEstruturalQuery.data, drilledCategoria, resumoQuery.data])
  const fundoSelecionado = fundoId !== null

  // Datas em que a QiTech publicou snapshot — Calendar bloqueia tudo o que nao
  // esta nesta lista. Trata fim de semana, feriado e falha de ETL de forma
  // uniforme (CLAUDE.md §14: explicabilidade > inferencia).
  const datasDisponiveisQuery = useDatasDisponiveis(fundoId)
  const datasDisponiveisSet = React.useMemo(
    () => new Set(datasDisponiveisQuery.data ?? []),
    [datasDisponiveisQuery.data],
  )

  // Competencias (meses) com snapshot disponivel — alimentam o seletor do topo.
  // datasDisponiveisQuery.data ja vem desc; mapeia mes -> data mais recente nele
  // (preserva a ordem de insercao = desc). O dia (?dia) e a fonte da verdade;
  // escolher uma competencia "salta" pra data mais recente daquele mes.
  const competenciaOptions = React.useMemo(() => {
    const latestByMonth = new Map<string, string>()
    for (const iso of datasDisponiveisQuery.data ?? []) {
      const ym = iso.slice(0, 7)
      if (!latestByMonth.has(ym)) latestByMonth.set(ym, iso)
    }
    return latestByMonth
  }, [datasDisponiveisQuery.data])

  const handleSelectCompetencia = React.useCallback(
    (ym: string) => {
      const iso = competenciaOptions.get(ym)
      if (!iso) return
      const d = new Date(`${iso}T00:00:00`)
      if (!isNaN(d.getTime())) setDay(d)
    },
    [competenciaOptions, setDay],
  )

  // Readiness QiTech — gate da pagina. Toda Cota Sub depende de 8 reports
  // (tesouraria, conta-corrente, rf, rf_compromissadas, outros-fundos,
  // outros-ativos, cpr, mec). So renderiza analise quando os 8 estao em
  // ready/may_change. Outros estados (in_progress/blocked/na) bloqueiam.
  const readiness = useCotaSubReadiness(fundoId, dayIso)
  const backfillMutation = useCreateBackfill("admin:qitech")

  const handleForceBackfill = React.useCallback(
    async (endpointName: string) => {
      if (!dayIso) return
      const reportLabel =
        COTA_SUB_REPORTS.find((r) => r.name === endpointName)?.shortLabel
        ?? endpointName
      const dateBr = (() => {
        const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dayIso)
        return m ? `${m[3]}/${m[2]}` : dayIso
      })()
      try {
        const job = await backfillMutation.mutateAsync({
          endpointName,
          payload: {
            dates:                     [dayIso],
            environment:               "production",
            unidade_administrativa_id: fundoId ?? undefined,
          },
        })
        toast.success(
          `Sync de ${reportLabel} (${dateBr}) enfileirado — job ${job.id.slice(0, 8)}`,
          { description: "Acompanhe no painel logo abaixo. Strip vira verde quando concluir." },
        )
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        toast.error(`Falha ao enfileirar sync de ${reportLabel} (${dateBr})`, {
          description: msg,
        })
      }
    },
    [backfillMutation, dayIso, fundoId],
  )

  // Quando o fundo troca: se o "day" atual nao existe nas datas disponiveis,
  // recua para a mais recente da lista (data top, ja vem ordenada desc do
  // backend). Evita estado inconsistente apos trocar de UA.
  React.useEffect(() => {
    if (!datasDisponiveisQuery.data) return
    if (datasDisponiveisQuery.data.length === 0) return
    if (datasDisponiveisSet.has(dayIso)) return
    const maisRecente = datasDisponiveisQuery.data[0]
    const d = new Date(maisRecente)
    if (!isNaN(d.getTime())) setDay(d)
  }, [datasDisponiveisQuery.data, datasDisponiveisSet, dayIso, setDay])


  const handleShare = React.useCallback(() => {
    void navigator.clipboard?.writeText(window.location.href)
  }, [])

  const handleExport = React.useCallback(() => {
    // Stub — wire to real export endpoint (CSV/XLSX).
    // eslint-disable-next-line no-console
    console.log("export pagina cota-sub", { day, fundo, classe, dynamicFilters })
  }, [day, fundo, classe, dynamicFilters])

  // Linhas filtradas da DataTable (escopo: filtros inline da tabela)
  const filteredRows = React.useMemo(
    () => MOCK_MOVIMENTACOES.filter((r) => {
      if (tableStatus !== "Todos" && labelForStatus(r.status) !== tableStatus) return false
      if (tableCotista !== "Todos" && r.cotista !== tableCotista) return false
      if (search && !r.cotista.toLowerCase().includes(search.toLowerCase()) && !r.id.toLowerCase().includes(search.toLowerCase())) return false
      return true
    }),
    [tableStatus, tableCotista, search],
  )

  // Adicionar / remover filtro dinamico
  const addDynamicFilter = React.useCallback((key: DynamicFilterKey) => {
    setDynamicFilters((curr) => {
      if (curr.some((f) => f.key === key)) return curr
      const opts = DYNAMIC_FILTER_OPTIONS[key]
      return [...curr, { key, value: opts[0] }]
    })
  }, [])
  const removeDynamicFilter = React.useCallback((key: DynamicFilterKey) => {
    setDynamicFilters((curr) => curr.filter((f) => f.key !== key))
  }, [])
  const setDynamicFilterValue = React.useCallback((key: DynamicFilterKey, value: string) => {
    setDynamicFilters((curr) => curr.map((f) => f.key === key ? { ...f, value } : f))
  }, [])

  const usedDynamicKeys = dynamicFilters.map((f) => f.key)
  const availableDynamicKeys = (Object.keys(DYNAMIC_FILTER_OPTIONS) as DynamicFilterKey[])
    .filter((k) => !usedDynamicKeys.includes(k))

  // Saved views — params atuais + handler
  const currentViewParams = React.useMemo<Record<string, string>>(() => ({
    day:     format(day, "yyyy-MM-dd"),
    fundo,
    classe,
    search,
    ...Object.fromEntries(dynamicFilters.map((f) => [f.key, f.value])),
  }), [day, fundo, classe, search, dynamicFilters])

  const handleApplyView = React.useCallback((view: { params: Record<string, string> }) => {
    const p = view.params
    if (p.fundo)  setFundo(p.fundo)
    if (p.classe) setClasse(p.classe as ClasseOption)
    if (p.search) setSearch(p.search)
    if (p.day) {
      const d = new Date(p.day)
      if (!isNaN(d.getTime())) setDay(d)
    }
    const restored: DynamicFilter[] = []
    for (const k of Object.keys(DYNAMIC_FILTER_OPTIONS) as DynamicFilterKey[]) {
      if (p[k]) restored.push({ key: k, value: p[k] as string })
    }
    setDynamicFilters(restored)
  }, [setDay])

  // Sombra canonica na toolbar quando o conteudo (Z4) esta scrollado.
  const [scrollRef, scrolled] = useScrollShadow<HTMLDivElement>()

  return (
    <div className="flex h-[calc(100vh-3rem)] overflow-hidden">
      {/* Coluna principal */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">

        {/* Title row (70px) — banda branca unificada com a toolbar abaixo */}
        <div className="shrink-0 bg-white px-6 pt-3.5 pb-3 dark:bg-gray-950">
          <PageHeader
            title="Variacao da Cota"
            info="Analise diaria comparativa (D-1 vs D0). ΔCota Sub = ΔAtivo − ΔPassivo Contabil − ΔEquity (Mez+Sr). Foco em explicar visualmente o saldo do dia e os eventos que mais contribuiram."
            subtitle="Controladoria · Patrimonio e Cotas"
            actions={
              <DashboardHeaderActions
                ai={{ open: chatOpen, onToggle: () => setChatOpen((o) => !o) }}
                onShare={handleShare}
                onExport={handleExport}
              />
            }
          />
        </div>

        {/* Toolbar unificada (52px) — tabs L3 + filtros + saved views */}
        <div
          className={cx(
            "shrink-0 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
            scrolled && "scroll-shadow",
          )}
        >
          <div className="flex h-[52px] items-center gap-2 px-6">
            <TabNavigation className="border-0">
              {TABS.map((t, i) => (
                <TabNavigationLink
                  key={t.key}
                  href="#"
                  active={activeTab === t.key}
                  onClick={(e) => {
                    e.preventDefault()
                    setActiveTab(t.key)
                  }}
                  title={`Cmd/Ctrl + ${i + 1}`}
                >
                  {t.label}
                </TabNavigationLink>
              ))}
            </TabNavigation>

            <div
              aria-hidden="true"
              className="mx-1 h-5 w-px bg-gray-200 dark:bg-gray-800"
            />

            {/* UA (fundo) = filtro PRIMARIO. A pagina analisa um FIDC por vez;
                sem selecionar a UA nada carrega (ver EmptyState). Por isso vem
                antes da competencia na ordem da toolbar. */}
            <FilterChip
              label="UA"
              value={fundo}
              active={fundo !== "Todos"}
            >
              <div className="py-1">
                {fundosQuery.isLoading && (
                  <div className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400">
                    Carregando UAs...
                  </div>
                )}
                {fundosQuery.isError && (
                  <div className="px-3 py-1.5 text-xs text-red-600 dark:text-red-400">
                    Falha ao carregar UAs
                  </div>
                )}
                {!fundosQuery.isLoading && !fundosQuery.isError && fundoOptions.length === 1 && (
                  <div className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400">
                    Nenhuma UA do tipo FIDC cadastrada
                  </div>
                )}
                {fundoOptions.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setFundo(opt)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      fundo === opt
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{opt}</span>
                    {fundo === opt && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                  </button>
                ))}
              </div>
            </FilterChip>

            {/* Competencia (mes) = filtro secundario. O DIA e escolhido clicando
                no grafico "Variacao diaria da cota" (master-detail). Selecionar
                um mes salta pra data disponivel mais recente dele. */}
            <FilterChip
              label="Competência"
              value={fmtCompetenciaLabel(competencia)}
              active={competencia !== format(today, "yyyy-MM")}
              icon={RiCalendarLine}
            >
              <div className="py-1">
                {datasDisponiveisQuery.isLoading && (
                  <div className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400">
                    Carregando competências...
                  </div>
                )}
                {!datasDisponiveisQuery.isLoading && competenciaOptions.size === 0 && (
                  <div className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400">
                    Nenhuma competência disponível
                  </div>
                )}
                {Array.from(competenciaOptions.keys()).map((ym) => (
                  <button
                    key={ym}
                    type="button"
                    onClick={() => handleSelectCompetencia(ym)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      ym === competencia
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{fmtCompetenciaLabel(ym)}</span>
                    {ym === competencia && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                  </button>
                ))}
              </div>
            </FilterChip>

            {/* Classe nao se aplica ao "Resumo do dia" (resumo/balanco sao por UA,
                nao por classe) — desativado nessa tab. */}
            <FilterChip
              label="Classe"
              value={classe}
              active={classe !== "Todas" && activeTab !== "resumo"}
              disabled={activeTab === "resumo"}
            >
              <div className="py-1">
                {CLASSE_OPTIONS.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setClasse(opt)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      classe === opt
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{opt}</span>
                    {classe === opt && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                  </button>
                ))}
              </div>
            </FilterChip>

            {/* Filtros dinamicos */}
            {dynamicFilters.map((f) => (
              <FilterChip
                key={f.key}
                label={f.key}
                value={f.value}
                active={f.value !== DYNAMIC_FILTER_OPTIONS[f.key][0]}
              >
                <div className="py-1">
                  {DYNAMIC_FILTER_OPTIONS[f.key].map((opt) => (
                    <button
                      key={opt}
                      type="button"
                      onClick={() => setDynamicFilterValue(f.key, opt)}
                      className={cx(
                        "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                        f.value === opt
                          ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                          : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                      )}
                    >
                      <span className="flex-1 text-left">{opt}</span>
                      {f.value === opt && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => removeDynamicFilter(f.key)}
                    className={cx(
                      "mt-1 flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      "text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-500/10",
                    )}
                  >
                    Remover filtro
                  </button>
                </div>
              </FilterChip>
            ))}

            {search && (
              <RemovableChip
                label="Busca"
                value={search}
                onRemove={() => setSearch("")}
              />
            )}

            {/* "Mais filtros" desativado no Resumo do dia (so UA + competencia). */}
            <AddFilterMenu
              available={availableDynamicKeys}
              onAdd={addDynamicFilter}
              disabled={activeTab === "resumo"}
            />

            <div className="ml-auto flex items-center gap-2">
              {/* Visualizacoes (saved views) nao se aplicam ao Resumo do dia. */}
              {activeTab !== "resumo" && (
                <SavedViewsDropdown
                  currentParams={currentViewParams}
                  onApplyView={handleApplyView}
                />
              )}
              <span className="shrink-0 text-[11px] text-gray-500 dark:text-gray-400">
                {balancoEstruturalQuery.isFetching ? "Atualizando…" : "Atualizado"}
              </span>
            </div>
          </div>
        </div>

        {/* Conteudo da aba — scroll container observado por useScrollShadow */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4">
          {!fundoSelecionado ? (
            <EmptyState
              icon={RiFundsLine}
              title="Selecione uma UA para comecar"
              description='A pagina Cota Sub analisa um FIDC por vez. Escolha a UA no filtro "UA" acima para carregar a decomposicao do dia, balanco e movimentacoes.'
              className="mt-4"
            />
          ) : (
            <div className="flex flex-col gap-3">
              {/* Strip de saude QiTech — nas tabs SEM band de KPI. No "Resumo do
                  dia" o status dos reports (9/9) ja aparece como pill no band, entao
                  o strip e redundante e fica oculto. */}
              {activeTab !== "resumo" && (
                <QiTechCoverageStrip
                  date={dayIso}
                  entries={readiness.entries}
                  loading={readiness.isLoading}
                  onBackfill={handleForceBackfill}
                />
              )}

              <ActiveBackfillJobsPanel fundoId={fundoId} dayIso={dayIso} />

              {!readiness.allReady && !readiness.isLoading ? (
                <CoverageGateEmpty
                  blocking={readiness.blocking}
                  onBackfill={handleForceBackfill}
                />
              ) : (
                <>
                  {activeTab === "resumo" && (
                    <div className="flex flex-col gap-3">
                      {/* Z1 — band de KPI (handoff): PL Sub · Variação do dia ·
                          Variação % (todos MEC) + status pills (reports + MEC) e
                          resumo de atenções à direita. */}
                      <CotaSubStatusBand
                        resumo={resumoQuery.data}
                        reportEntries={readiness.entries}
                        dataD0={dayIso}
                        loading={resumoQuery.isLoading}
                      />
                      {/* Faixa "consciencia": mutacao / sem-provisao / WOP, ancoradas
                          ao grupo-casa. Clicar abre o drill; investigavel abre o chat. */}
                      <AtencoesDoDia
                        atencoes={resumoQuery.data?.atencoes}
                        loading={resumoQuery.isLoading}
                        onDrillGrupo={(k) => setDrilledCategoria(k as DrillKey)}
                        onInvestigar={() => setChatOpen(true)}
                      />
                      {/* Master-detail (handoff 2026-06-05): 3 colunas iguais.
                          Esquerda = grafico de variacao diaria (MASTER); clicar
                          num dia re-chaveia o resumo (?dia) -> waterfall + lista
                          re-renderizam pro dia. minmax(0,1fr) impede que os
                          labels longos do ResumoGrupos estourem a fracao. */}
                      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[repeat(3,minmax(0,1fr))]">
                        {/* MASTER — variacao diaria da cota na competencia. */}
                        <VariacaoDiariaCard
                          serie={diariaQuery.data ?? []}
                          diaSelecionado={dayIso}
                          onSelectDia={(iso) => {
                            const d = new Date(`${iso}T00:00:00`)
                            if (!isNaN(d.getTime())) setDay(d)
                          }}
                          loading={diariaQuery.isLoading}
                        />
                        {/* DETAIL — waterfall PL Sub D-1 (MEC) -> grupos -> D0. */}
                        <VariacaoWaterfall
                          data={resumoQuery.data}
                          loading={resumoQuery.isLoading}
                          onDrillGrupo={(k) => setDrilledCategoria(k as DrillKey)}
                        />
                        {/* DETAIL — detalhamento por grupo de balanco (lista). */}
                        <ResumoGrupos
                          data={resumoQuery.data}
                          loading={resumoQuery.isLoading}
                          onDrillGrupo={(k) => setDrilledCategoria(k as DrillKey)}
                        />
                      </div>
                    </div>
                  )}
                  {activeTab === "balanco" && (
                    <div className="flex flex-col gap-3">
                      {/* O balancete (posicao + prova) + reconciliacao MEC + nao-reconhecidos. */}
                      <BalancoPatrimonialHero
                        data={balancoEstruturalQuery.data}
                        loading={balancoEstruturalQuery.isLoading}
                        errorMessage={
                          balancoEstruturalQuery.isError
                            ? `Erro: ${(balancoEstruturalQuery.error as Error)?.message ?? "desconhecido"}`
                            : undefined
                        }
                        onRetry={() => balancoEstruturalQuery.refetch()}
                        onDrillCategoria={setDrilledCategoria}
                      />
                      <NaoReconhecidosPanel
                        itens={balancoEstruturalQuery.data?.nao_reconhecidos}
                        loading={balancoEstruturalQuery.isLoading}
                      />
                    </div>
                  )}
                  {activeTab === "movimentacoes" && (
                    <MovimentacoesTab
                      rows={filteredRows}
                      tableStatus={tableStatus}
                      setTableStatus={setTableStatus}
                      tableCotista={tableCotista}
                      setTableCotista={setTableCotista}
                      onRowClick={setSelected}
                    />
                  )}
                  {activeTab === "cotistas" && <PlaceholderTab label="Cotistas" />}
                </>
              )}
            </div>
          )}
        </div>

      </div>

      {/* DrillDown — F2: categoria do Balance hero (DC / PDD / CPR).
          F3 redesign 2026-05-24: Sheet vira FALLBACK pra < xl. Em xl+ o slot
          direito da grid renderiza o BalancoInspector com o mesmo conteudo. */}
      <CategoriaDrillSheet
        open={drilledCategoria !== null}
        onClose={() => setDrilledCategoria(null)}
        categoria={drilledCategoriaObj}
        fundoNome={balancoEstruturalQuery.data?.fundo_nome ?? ""}
        data={balancoEstruturalQuery.data?.data ?? dayIso}
        dataAnterior={balancoEstruturalQuery.data?.data_anterior ?? ""}
      >
        {drilledCategoria === "dc" && fundoId && (
          <DrillDcContent
            fundoId={fundoId}
            data={balancoEstruturalQuery.data?.data ?? dayIso}
            dataAnterior={balancoEstruturalQuery.data?.data_anterior}
          />
        )}
        {drilledCategoria === "pdd" && fundoId && (
          <DrillPddContent
            fundoId={fundoId}
            data={balancoEstruturalQuery.data?.data ?? dayIso}
            dataAnterior={balancoEstruturalQuery.data?.data_anterior}
          />
        )}
        {drilledCategoria === "cpr_receber" && fundoId && (
          <DrillCprContent
            fundoId={fundoId}
            data={balancoEstruturalQuery.data?.data ?? dayIso}
            dataAnterior={balancoEstruturalQuery.data?.data_anterior}
            side="receber"
          />
        )}
        {drilledCategoria === "cpr_pagar" && fundoId && (
          <DrillContasAPagarContent
            fundoId={fundoId}
            data={balancoEstruturalQuery.data?.data ?? dayIso}
            dataAnterior={balancoEstruturalQuery.data?.data_anterior}
          />
        )}
        {drilledCategoria && COTAS_KEYS.has(drilledCategoria as CategoriaPatrimonialKey) && fundoId && (
          <DrillCotasContent
            fundoId={fundoId}
            data={balancoEstruturalQuery.data?.data ?? dayIso}
            dataAnterior={balancoEstruturalQuery.data?.data_anterior}
          />
        )}
        {drilledCategoria && ORIGEM_KEYS.has(drilledCategoria as CategoriaPatrimonialKey) && fundoId && (
          <DrillOrigemContent
            fundoId={fundoId}
            data={balancoEstruturalQuery.data?.data ?? dayIso}
            linha={drilledCategoria as CategoriaPatrimonialKey}
          />
        )}
        {drilledCategoria === "aplicacoes" && fundoId && (
          <DrillAplicacoesContent
            fundoId={fundoId}
            data={balancoEstruturalQuery.data?.data ?? dayIso}
            dataAnterior={balancoEstruturalQuery.data?.data_anterior}
          />
        )}
        {drilledCategoria === "disponibilidades" && (
          <DrillDisponibilidadesContent
            rendimento={resumoQuery.data?.grupos.find((g) => g.key === "disponibilidades")?.impacto_pl_sub ?? 0}
            giroCapital={resumoQuery.data?.giro_capital ?? []}
          />
        )}
      </CategoriaDrillSheet>

      {/* DrillDown — movimentacao individual */}
      <DrillDownSheet
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={selected?.id ?? "Movimentacao"}
      >
        {selected && (
          <>
            <DrillDownSheet.Header
              breadcrumb={["Cota Sub", selected.id]}
              statusSlot={
                <span className={cx(
                  "inline-flex items-center rounded-sm px-1.5 py-0.5 text-[11px] font-medium",
                  selected.tipo === "subscricao"
                    ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
                    : "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
                )}>
                  {selected.tipo === "subscricao" ? "Subscricao" : "Resgate"}
                </span>
              }
            />
            <DrillDownSheet.Hero
              id={selected.id}
              title={selected.cotista}
              value={selected.valor}
              delta={{ value: selected.tipo === "subscricao" ? 1.8 : -0.6, label: "vs ultima movimentacao" }}
            />
            <DrillDownSheet.Tabs
              tabs={[
                {
                  value:   "geral",
                  label:   "Visao geral",
                  content: (
                    <>
                      <DrillDownSheet.PropertyList
                        items={[
                          { label: "Cotista",      value: selected.cotista },
                          { label: "Classe",       value: selected.classe },
                          { label: "Tipo",         value: selected.tipo === "subscricao" ? "Subscricao" : "Resgate" },
                          { label: "Valor",        value: selected.valor, type: "currency" },
                          { label: "Data",         value: selected.data, type: "date" },
                          { label: "Status",       value: STATUS_LABEL[selected.status] },
                          { label: "Origem",       value: "QiTech" },
                          { label: "Liquidacao",   value: selected.status === "liquidado" ? "D+0" : "D+1 (estimada)" },
                        ]}
                      />
                      <div className="mt-6">
                        <DrillDownSheet.SectionLabel>Linha do tempo</DrillDownSheet.SectionLabel>
                        <DrillDownSheet.Timeline
                          events={buildTimeline(selected)}
                        />
                      </div>
                    </>
                  ),
                },
                { value: "historico",  label: "Historico",   content: <PlaceholderSheetTab label="Historico" /> },
                { value: "documentos", label: "Documentos",  content: <PlaceholderSheetTab label="Documentos" /> },
                { value: "atividade",  label: "Atividade",   content: <PlaceholderSheetTab label="Atividade" /> },
              ]}
              defaultValue="geral"
            />
            <DrillDownSheet.Footer>
              <Button variant="secondary">Exportar PDF</Button>
              <Button variant="secondary">Ver historico</Button>
              <div className="flex-1" />
              <Button variant="primary">Registrar evento</Button>
            </DrillDownSheet.Footer>
          </>
        )}
      </DrillDownSheet>

      {/* Chat-investigador (Camada 2) — pré-carregado (backend) com o resumo do dia.
          Entrada: botão "IA" do header + atalho Cmd/Ctrl+I (sem FAB). */}
      <ChatVariacaoDrawer
        fundoId={fundoId}
        data={dayIso}
        open={chatOpen}
        onClose={() => setChatOpen(false)}
      />

    </div>
  )
}

function PlaceholderSheetTab({ label }: { label: string }) {
  return (
    <div className="flex h-full items-center justify-center py-10 text-sm text-gray-500 dark:text-gray-400">
      Em desenvolvimento — aba &quot;{label}&quot;
    </div>
  )
}

// ─── CoverageGateEmpty ──────────────────────────────────────────────────────
// Bloqueia a renderizacao da analise quando algum dos 8 reports QiTech esta
// em estado bloqueante (in_progress/blocked/na) para o dia selecionado.
// Lista os reports faltantes + CTA "Forcar sync de N reports".

function CoverageGateEmpty({
  blocking,
  onBackfill,
}: {
  blocking: CoverageStripEntry[]
  onBackfill: (endpointName: string) => void
}) {
  const handleSyncAll = React.useCallback(() => {
    for (const entry of blocking) onBackfill(entry.name)
  }, [blocking, onBackfill])

  const blockedCount = blocking.filter((e) => e.health === "blocked").length
  const inProgressCount = blocking.filter((e) => e.health === "in_progress").length
  const naCount = blocking.filter((e) => e.health === "na").length

  return (
    <div className="flex flex-col items-center gap-4 rounded border border-gray-200 bg-white px-6 py-10 text-center dark:border-gray-800 dark:bg-gray-950">
      <div className="flex size-12 items-center justify-center rounded-full bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300">
        <RiCloudOffLine className="size-6" aria-hidden="true" />
      </div>

      <div className="max-w-xl">
        <h3 className="text-base font-semibold text-gray-900 dark:text-gray-50">
          Dados ainda nao disponiveis para esta data
        </h3>
        <p className="mt-1 text-[13px] text-gray-600 dark:text-gray-400">
          A analise da Cota Sub precisa que os 8 reports QiTech estejam
          publicados. {blocking.length} report{blocking.length === 1 ? "" : "s"}
          {" "}ainda nao{blocking.length === 1 ? " atende" : " atendem"} —{" "}
          {[
            blockedCount && `${blockedCount} bloqueado${blockedCount > 1 ? "s" : ""}`,
            inProgressCount && `${inProgressCount} em curso`,
            naCount && `${naCount} N/A`,
          ].filter(Boolean).join(", ")}
          . Verifique no strip acima qual e cada um.
        </p>
      </div>

      <ul className="flex max-w-md flex-col gap-1 text-left">
        {blocking.map((entry) => (
          <li
            key={entry.name}
            className="flex items-center justify-between gap-3 rounded border border-gray-200 bg-gray-50 px-3 py-1.5 text-[12px] dark:border-gray-800 dark:bg-gray-900"
          >
            <span className="flex items-center gap-2">
              <span
                className={cx(
                  "inline-block size-2 rounded-full",
                  entry.health === "blocked"
                    ? "bg-red-500"
                    : entry.health === "in_progress"
                    ? "bg-blue-400"
                    : "bg-gray-300 dark:bg-gray-700",
                )}
                aria-hidden="true"
              />
              <span className="font-medium text-gray-700 dark:text-gray-200">
                {entry.fullLabel ?? entry.shortLabel}
              </span>
              <span className="font-mono text-[11px] text-gray-500 dark:text-gray-500">
                {entry.name}
              </span>
            </span>
            {entry.health !== "na" && (
              <button
                type="button"
                onClick={() => onBackfill(entry.name)}
                className="inline-flex items-center gap-1 rounded border border-gray-200 bg-white px-2 py-0.5 text-[11px] font-medium text-gray-700 transition-colors hover:bg-gray-100 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-300 dark:hover:bg-gray-800"
              >
                <RiPlayLine className="size-3" aria-hidden="true" />
                Forcar
              </button>
            )}
          </li>
        ))}
      </ul>

      {blocking.some((e) => e.health !== "na") && (
        <Button variant="primary" onClick={handleSyncAll}>
          <RiAlertLine className="size-3.5" aria-hidden="true" />
          Forcar sync de {blocking.filter((e) => e.health !== "na").length} report
          {blocking.filter((e) => e.health !== "na").length === 1 ? "" : "s"}
        </Button>
      )}
    </div>
  )
}

function buildTimeline(row: MovimentacaoRow): TimelineEventDef[] {
  const baseDate = format(new Date(row.data), "dd/MM/yyyy")
  const events: TimelineEventDef[] = [
    { type: "cedida",    date: baseDate, actor: "Front-office",  description: `${row.tipo === "subscricao" ? "Subscricao" : "Resgate"} solicitada pelo cotista` },
    { type: "lastreada", date: baseDate, actor: "Back-office",   description: "Pedido validado e enviado a administradora" },
  ]
  if (row.status === "liquidado") {
    events.push({ type: "liquidada", date: baseDate, actor: "QiTech", description: "Liquidacao efetivada", current: true })
  } else if (row.status === "atrasado-30" || row.status === "atrasado-60") {
    events.push({ type: "atrasada", date: baseDate, actor: "Sistema", description: "Aguardando confirmacao do cotista", current: true })
  } else {
    events.push({ type: "a-vencer", date: "—", actor: "Sistema", description: "Aguardando liquidacao", current: true })
  }
  return events
}

// O componente le search params (?dia via nuqs/useSearchParams). Next exige um
// boundary <Suspense> pra essas paginas durante o prerender estatico (CSR
// bailout). Pagina autenticada nunca e estatica, mas o wrapper satisfaz o build
// (e a rota /preview/cota-sub que reexporta este default).
export default function CotaSubPage() {
  return (
    <React.Suspense fallback={null}>
      <CotaSubPageInner />
    </React.Suspense>
  )
}
