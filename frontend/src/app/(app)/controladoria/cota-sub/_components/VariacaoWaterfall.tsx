"use client"

/**
 * VariacaoWaterfall — o "O que moveu a cota" da aba Resumo do dia (2026-06-01).
 *
 * Waterfall de NIVEL: PL Sub D-1 (MEC) -> 6 transformacoes (os grupos de balanco,
 * impacto giro-limpo) -> PL Sub D0 (MEC). Ancoras = MEC (oficial); se a variacao
 * apresentada (Σ grupos) divergir da do MEC, o gap aparece como barra de RESIDUO.
 *
 * Sinal pela natureza (ja resolvido no backend em impacto_pl_sub): ativo que sobe
 * = verde; PDD/passivo que sobe = vermelho. Giro = nota neutra (nao e barra).
 * Clicar numa barra de grupo abre o drill. Zero LLM.
 */

import * as React from "react"
import type { EChartsOption } from "echarts"

import { EChartsCard } from "@/design-system/components/EChartsCard"
import type { VariacaoResumoResponse } from "@/lib/api-client"

const POS = "#10B981"      // emerald-500 — ajudou a cota
const NEG = "#F43F5E"      // rose-500 — pressionou
const ANCHOR = "#475569"   // slate-600 — ancoras MEC (visivel em light/dark)
const RESIDUO = "#94A3B8"  // slate-400 — gap nao explicado vs MEC

// Labels curtos do eixo X (2 linhas) por chave de grupo.
const AXIS_LABEL: Record<string, string> = {
  direitos_creditorios: "Direitos\nCreditórios",
  pdd_wop:              "(−) PDD\n& WOP",
  aplicacoes:           "Aplicações",
  disponibilidades:     "Disponi-\nbilidades",
  obrigacoes_provisoes: "Obrig. e\nProvisões",
  cotas_prioritarias:   "Cotas\nPrioritárias",
}

const fmtBRLFull = (v: number) =>
  "R$ " + v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const fmtMi = (v: number) =>
  (v / 1e6).toLocaleString("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 }) + " mi"
const fmtK = (v: number) => {
  const s = v >= 0 ? "+" : "−"
  return `${s}R$ ${Math.abs(v / 1000).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}k`
}

type BarKind = "anchor" | "step" | "residuo"
type Bar = {
  category: string
  base:     number
  bar:      number
  color:    string
  real:     number
  kind:     BarKind
  drillKey: string | null
}

function buildBars(data: VariacaoResumoResponse): Bar[] {
  const mecD1 = data.pl_sub_mec_d1
  const mecD0 = data.pl_sub_mec_d0
  const residuo = data.reconciliacao.residuo // calc − MEC
  const resStep = Math.abs(residuo) >= 1 ? -residuo : 0 // leva o running ate o MEC D0

  // 1a passada: pontos do running para achar piso/teto.
  const pts: number[] = [mecD1]
  let run = mecD1
  for (const g of data.grupos) { run += g.impacto_pl_sub; pts.push(run) }
  if (resStep) { run += resStep; pts.push(run) }
  pts.push(mecD0)
  const lo = Math.min(...pts), hi = Math.max(...pts)
  const pad = (hi - lo) * 0.18 || 1000
  const piso = lo - pad

  const bars: Bar[] = []
  bars.push({ category: "PL Sub\nD-1", base: piso, bar: mecD1 - piso, color: ANCHOR, real: mecD1, kind: "anchor", drillKey: null })
  run = mecD1
  for (const g of data.grupos) {
    const v = g.impacto_pl_sub
    const positive = v >= 0
    bars.push({
      category: AXIS_LABEL[g.key] ?? g.label,
      base: positive ? run : run + v,
      bar: Math.abs(v),
      color: positive ? POS : NEG,
      real: v,
      kind: "step",
      drillKey: g.drill_key,
    })
    run += v
  }
  if (resStep) {
    const positive = resStep >= 0
    bars.push({
      category: "Resíduo", base: positive ? run : run + resStep, bar: Math.abs(resStep),
      color: RESIDUO, real: resStep, kind: "residuo", drillKey: null,
    })
    run += resStep
  }
  bars.push({ category: "PL Sub\nD0", base: piso, bar: mecD0 - piso, color: ANCHOR, real: mecD0, kind: "anchor", drillKey: null })
  return bars
}

export type VariacaoWaterfallProps = {
  data?:         VariacaoResumoResponse
  loading?:      boolean
  onDrillGrupo?: (drillKey: string) => void
}

export function VariacaoWaterfall({ data, loading, onDrillGrupo }: VariacaoWaterfallProps) {
  const bars = React.useMemo(() => (data ? buildBars(data) : []), [data])

  const option: EChartsOption = React.useMemo(() => ({
    grid: { top: 24, right: 12, bottom: 54, left: 56 },
    xAxis: {
      type: "category",
      data: bars.map((b) => b.category),
      axisLabel: {
        fontSize: 9, interval: 0, lineHeight: 11,
        formatter: (v: string, i: number) => (bars[i]?.kind === "anchor" ? `{a|${v}}` : v),
        rich: { a: { fontWeight: "bold", fontSize: 9, lineHeight: 11 } },
      },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      scale: true,
      axisLabel: {
        fontSize: 9,
        formatter: (v: number) => (v / 1e6).toFixed(2).replace(".", ",") + "M",
      },
      splitLine: { lineStyle: { type: "dashed", opacity: 0.4 } },
    },
    tooltip: {
      trigger: "item",
      formatter: (p: unknown) => {
        const { seriesName, dataIndex } = p as { seriesName: string; dataIndex: number }
        if (seriesName === "base") return ""
        const b = bars[dataIndex]
        if (!b) return ""
        const label = b.category.replace(/\n/g, " ")
        if (b.kind === "anchor") return `<b>${label}</b><br/>${fmtBRLFull(b.real)}`
        if (b.kind === "residuo") return `<b>Resíduo não explicado</b><br/>${fmtBRLFull(b.real)} (gap vs MEC)`
        if (Math.abs(b.real) < 1) return `<b>${label}</b><br/>impacto 0 (giro neutro)`
        return `<b>${label}</b><br/>${fmtK(b.real)} na cota`
      },
    },
    series: [
      {
        name: "base", type: "bar", stack: "w", silent: true,
        itemStyle: { color: "rgba(0,0,0,0)" }, emphasis: { disabled: true },
        data: bars.map((b) => b.base),
      },
      {
        name: "v", type: "bar", stack: "w", barCategoryGap: "34%", cursor: "pointer",
        data: bars.map((b) => ({ value: b.bar, itemStyle: { color: b.color, borderRadius: 2 } })),
        label: {
          show: true, position: "top", fontSize: 9,
          formatter: (p: { dataIndex: number }) => {
            const b = bars[p.dataIndex]
            if (!b) return ""
            if (b.kind === "anchor") return fmtMi(b.real)
            if (Math.abs(b.real) < 1) return "0"
            return fmtK(b.real)
          },
        },
      },
    ],
  }), [bars])

  const handleEvents = React.useMemo(() => ({
    click: (params: { componentType: string; dataIndex: number }) => {
      if (params.componentType !== "series") return
      const b = bars[params.dataIndex]
      if (b?.kind === "step" && b.drillKey && onDrillGrupo) onDrillGrupo(b.drillKey)
    },
  }), [bars, onDrillGrupo])

  const headerKpi = data
    ? {
        value: (data.cota_delta >= 0 ? "+" : "−") + fmtBRLFull(Math.abs(data.cota_delta)),
        delta: data.pl_sub_mec_d1
          ? { value: (data.cota_delta / data.pl_sub_mec_d1) * 100, suffix: "%", good: data.cota_delta >= 0 }
          : undefined,
        deltaSub: "variação do dia",
      }
    : undefined

  return (
    <EChartsCard
      title="O que moveu a cota"
      caption="PL Sub D-1 (MEC) → transformações → PL Sub D0 (MEC)"
      headerKpi={headerKpi}
      option={option}
      height={300}
      loading={loading}
      echartsProps={{ onEvents: handleEvents }}
      footer={data ? <WaterfallFooter data={data} /> : undefined}
    />
  )
}

function WaterfallFooter({ data }: { data: VariacaoResumoResponse }) {
  const r = data.reconciliacao
  return (
    <div className="mt-1 flex flex-col gap-2 border-t border-gray-100 pt-2.5 dark:border-gray-900">
      <div className="flex items-center text-[11px] text-gray-500 dark:text-gray-400">
        <span className="inline-flex items-center gap-1 rounded bg-gray-100 px-1.5 py-0.5 text-gray-600 dark:bg-gray-800 dark:text-gray-300">
          ↺ giro {fmtBRLFull(data.giro_total).replace(",00", "")}
        </span>
        <span className="ml-1.5">movimentou, impacto na cota = 0</span>
      </div>
      <div className="rounded-md border border-gray-200 bg-gray-50/70 px-3 py-2 dark:border-gray-800 dark:bg-gray-900/40">
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-gray-500 dark:text-gray-400">Variação apresentada (decomposta)</span>
          <span className="font-medium tabular-nums text-gray-900 dark:text-gray-100">{fmtBRLFull(r.variacao_apresentada)}</span>
        </div>
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-gray-500 dark:text-gray-400">Variação MEC <span className="text-gray-400 dark:text-gray-600">· QiTech, oficial</span></span>
          <span className="font-medium tabular-nums text-gray-900 dark:text-gray-100">{fmtBRLFull(r.variacao_mec)}</span>
        </div>
        <div className="mt-1 flex items-center justify-between border-t border-gray-200 pt-1 text-[11px] dark:border-gray-800">
          <span className="font-medium text-gray-700 dark:text-gray-300">Resíduo não explicado</span>
          <span className={r.fecha ? "font-semibold tabular-nums text-emerald-600 dark:text-emerald-400" : "font-semibold tabular-nums text-amber-600 dark:text-amber-400"}>
            {fmtBRLFull(r.residuo)} {r.fecha ? "✓" : "⚠"}
          </span>
        </div>
      </div>
    </div>
  )
}
