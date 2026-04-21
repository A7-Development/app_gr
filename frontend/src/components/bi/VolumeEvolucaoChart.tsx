"use client"

// OpcoesMenu removido temporariamente (Onda 1) — volta quando backend entregar
// granularidade trimestral/anual, overlays de apoio (taxa/prazo/ticket) ou
// comparacao MoM/YoY. Menu com 5+ items "em breve" gerava expectativa sem
// entrega — melhor omitir ate ter algo real. Imports e state desse fluxo
// (RiMore2Line, DropdownMenu*, granularidade, comparar) foram podados junto.

import * as React from "react"
import { useRouter, useSearchParams, usePathname } from "next/navigation"

import { AreaChart } from "@/components/charts/AreaChart"
import { BarChart } from "@/components/charts/BarChart"
import { LineChart } from "@/components/charts/LineChart"
import type { BarChartEventProps } from "@/components/charts/BarChart"
import { ChartSkeleton } from "@/components/app/ChartSkeleton"
import { cx, focusRing } from "@/lib/utils"
import type {
  PointDim,
  Point,
  SeriesEVolume,
} from "@/lib/api-client"

//
// Tipos dos toggles
//

type ViewBy = "total" | "produto" | "ua"
type Formato = "bar" | "line" | "area" | "percent"

const DEFAULT_BY: ViewBy = "total"
const DEFAULT_FMT: Formato = "bar"

//
// Formatters
//

// Formatter usado no eixo Y + tooltip do chart principal. Sem decimais
// porque o eixo Y e uma escala de leitura — arredondar mantem a linha
// grid limpa ("R$ 118 mi" em vez de "R$ 117,84 mi"). A precisao maior
// fica nos data labels das barras (ver `milhoes1` abaixo, 1 casa decimal).
const moedaCompacta = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 0,
})

/**
 * "118,2" — valor em milhoes com 1 casa decimal, sem prefixo "R$" nem
 * sufixo "mi". Pensado para data labels sobre barras — o contexto de
 * moeda/unidade ja fica claro pelo titulo do card, eixo Y e tooltip.
 * Omitir "mi" reduz poluicao visual nos rotulos.
 */
const milhoes1 = (v: number) =>
  (v / 1_000_000).toLocaleString("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })

const pctFmt = (v: number) => `${v.toFixed(1)}%`

function labelForPeriodo(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number)
  if (d === 1) {
    return new Date(y, m - 1, 1).toLocaleString("pt-BR", {
      month: "short",
      year: "2-digit",
    })
  }
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}`
}

//
// Helpers — transformar PointDim[] em dados "pivotados" para chart multi-series
//

type PivotedRow = {
  periodo: string
  _iso: string
  [categoria: string]: number | string
}

function pivotPointsDim(
  points: PointDim[],
): { rows: PivotedRow[]; categories: string[] } {
  const byPeriodo = new Map<string, PivotedRow>()
  const catSet = new Set<string>()

  for (const p of points) {
    const key = p.periodo
    if (!byPeriodo.has(key)) {
      byPeriodo.set(key, {
        periodo: labelForPeriodo(p.periodo),
        _iso: p.periodo,
      })
    }
    const row = byPeriodo.get(key)!
    row[p.categoria] = ((row[p.categoria] as number) ?? 0) + p.valor
    catSet.add(p.categoria)
  }

  const rows = Array.from(byPeriodo.values()).sort((a, b) =>
    a._iso < b._iso ? -1 : 1,
  )
  const categories = Array.from(catSet)
  for (const row of rows) {
    for (const c of categories) {
      if (row[c] === undefined) row[c] = 0
    }
  }
  return { rows, categories }
}

function pointsToRows(
  points: Point[],
  label: string,
): { rows: PivotedRow[]; categories: string[] } {
  const rows = points.map((p) => ({
    periodo: labelForPeriodo(p.periodo),
    _iso: p.periodo,
    [label]: p.valor,
  }))
  return { rows, categories: [label] }
}

//
// Segmented control inline — decisoes visuais frequentes
//

function ControlSegmented<T extends string>({
  label,
  value,
  onChange,
  options,
}: {
  label: string
  value: T
  onChange: (v: T) => void
  options: { value: T; label: string }[]
}) {
  return (
    <div className="flex items-center gap-1.5">
      <span className="text-[11px] font-medium text-gray-500 dark:text-gray-400">
        {label}
      </span>
      <div
        role="radiogroup"
        className="inline-flex rounded border border-gray-200 bg-gray-50 p-0.5 dark:border-gray-800 dark:bg-gray-900"
      >
        {options.map((opt) => {
          const active = value === opt.value
          return (
            <button
              key={opt.value}
              type="button"
              role="radio"
              aria-checked={active}
              onClick={() => onChange(opt.value)}
              className={cx(
                "shrink-0 rounded px-2 py-0.5 text-xs font-medium transition",
                active
                  ? "bg-white text-blue-700 shadow-xs ring-1 ring-blue-500 dark:bg-blue-500/10 dark:text-blue-400 dark:ring-blue-400"
                  : "text-gray-600 hover:text-gray-900 dark:text-gray-400 hover:dark:text-gray-50",
                focusRing,
              )}
            >
              {opt.label}
            </button>
          )
        })}
      </div>
    </div>
  )
}

//
// URL params
//

function useVolumeControls() {
  const router = useRouter()
  const pathname = usePathname()
  const sp = useSearchParams()

  const by = (sp.get("v_by") as ViewBy | null) ?? DEFAULT_BY
  const fmt = (sp.get("v_fmt") as Formato | null) ?? DEFAULT_FMT

  const update = React.useCallback(
    (key: string, value: string, defaultValue: string) => {
      const next = new URLSearchParams(sp.toString())
      if (value === defaultValue) next.delete(key)
      else next.set(key, value)
      router.replace(`${pathname}?${next.toString()}`, { scroll: false })
    },
    [router, pathname, sp],
  )

  return {
    by,
    fmt,
    setBy: (v: ViewBy) => update("v_by", v, DEFAULT_BY),
    setFmt: (v: Formato) => update("v_fmt", v, DEFAULT_FMT),
  }
}

//
// VolumeEvolucaoChart
//

type Props = {
  data: SeriesEVolume | undefined
  loading?: boolean
  onBarClick?: (iso: string | null) => void
  className?: string
}

export function VolumeEvolucaoChart({
  data,
  loading,
  onBarClick,
  className,
}: Props) {
  const { by, fmt, setBy, setFmt } = useVolumeControls()

  const { rows, categories } = React.useMemo(() => {
    if (!data) return { rows: [] as PivotedRow[], categories: [] as string[] }
    if (by === "produto") return pivotPointsDim(data.evolucao_por_produto)
    if (by === "ua") return pivotPointsDim(data.evolucao_por_ua)
    return pointsToRows(data.evolucao, "Volume bruto")
  }, [data, by])

  const chartType: "default" | "stacked" | "percent" =
    fmt === "percent" ? "percent" : by !== "total" ? "stacked" : "default"

  const valueFormatter =
    fmt === "percent"
      ? pctFmt
      : (v: number) => moedaCompacta.format(v)

  /**
   * `maxValue` com 12% de folga — evita que os data labels (position="top")
   * sejam clipados na borda superior do SVG quando a barra mais alta encosta
   * no dominio Y automatico do Recharts.
   *
   * Em modo stacked (Produto/UA), o total da barra e a soma das categorias
   * naquele periodo — ponto maximo precisa levar em conta a soma.
   *
   * Em modo percent, Recharts normaliza para 0..1; deixamos undefined
   * (o default cuida).
   */
  const maxValue = React.useMemo<number | undefined>(() => {
    if (fmt === "percent" || rows.length === 0) return undefined
    let max = 0
    for (const row of rows) {
      let rowTotal = 0
      for (const cat of categories) {
        const v = row[cat]
        if (typeof v === "number") rowTotal += v
      }
      if (rowTotal > max) max = rowTotal
    }
    return max > 0 ? max * 1.12 : undefined
  }, [rows, categories, fmt])

  // Volume total exibido inline no header (delta vive no KPI inline acima).
  const headerValor =
    data?.resumo?.volume_total !== undefined
      ? moedaCompacta.format(data.resumo.volume_total)
      : null

  return (
    <div
      className={cx(
        "flex flex-col gap-4 rounded border border-gray-200 p-5 dark:border-gray-800",
        className,
      )}
    >
      {/* Header — titulo+subtitulo, controles e resumo numa unica linha
          (compacta vertical pra ceder espaco ao chart). */}
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="flex flex-col gap-0.5">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
            Evolução do volume
          </h3>
          <p className="text-[11px] text-gray-500 dark:text-gray-400">
            Volume operado ao longo do período filtrado
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <ControlSegmented
            label="Ver por"
            value={by}
            onChange={setBy}
            options={[
              { value: "total", label: "Total" },
              { value: "produto", label: "Produto" },
              { value: "ua", label: "UA" },
            ]}
          />
          <ControlSegmented
            label="Formato"
            value={fmt}
            onChange={setFmt}
            options={[
              { value: "bar", label: "Barra" },
              { value: "line", label: "Linha" },
              { value: "area", label: "Área" },
              { value: "percent", label: "% empilhado" },
            ]}
          />
          {headerValor && (
            <span className="pl-1 text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
              {headerValor}
            </span>
          )}
        </div>
      </div>

      {/* Chart */}
      {loading || !data ? (
        <ChartSkeleton
          variant={fmt === "line" ? "line" : fmt === "area" ? "area" : "bars"}
          className="h-80"
        />
      ) : rows.length === 0 ? (
        <div className="flex h-80 items-center justify-center text-sm text-gray-500">
          Sem dados no período selecionado.
        </div>
      ) : fmt === "line" ? (
        <LineChart
          data={rows}
          index="periodo"
          categories={categories}
          valueFormatter={valueFormatter}
          className="h-80"
          showLegend={by !== "total"}
          yAxisWidth={76}
        />
      ) : fmt === "area" ? (
        <AreaChart
          data={rows}
          index="periodo"
          categories={categories}
          valueFormatter={valueFormatter}
          className="h-80"
          showLegend={by !== "total"}
          type={chartType}
          yAxisWidth={76}
          maxValue={maxValue}
        />
      ) : (
        <BarChart
          data={rows}
          index="periodo"
          categories={categories}
          valueFormatter={valueFormatter}
          className="h-80"
          showLegend={by !== "total"}
          type={chartType}
          yAxisWidth={76}
          maxValue={maxValue}
          {...(by === "total" && fmt === "bar"
            ? {
                showLabels: true,
                labelFormatter: milhoes1,
                onValueChange: onBarClick
                  ? (e: BarChartEventProps) => {
                      if (!e) {
                        onBarClick(null)
                        return
                      }
                      const iso =
                        typeof e._iso === "string" ? e._iso : undefined
                      onBarClick(iso ?? null)
                    }
                  : undefined,
              }
            : {})}
        />
      )}
    </div>
  )
}
