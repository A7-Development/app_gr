"use client"

/**
 * VariacaoWaterfall — o "O que moveu a cota" da aba Resumo do dia (2026-06-01).
 *
 * Wrapper FINO sobre o `VarianceBridgeCard` canonico (mesmo waterfall do
 * bi/operacoes2) — NAO reinventa o chart. Mapeia os 6 grupos do resumo para
 * `Operacoes2VarianceBridgeData`:
 *   - ancoras = PL Sub D-1 / D0 CALCULADO por nos (pl_sub_calc), nao o MEC.
 *     Σ drivers == cota_delta == calc_d0 - calc_d1, entao o bridge fecha exato
 *     na ancora calc (sem barra de residuo). A comparacao com o MEC oficial
 *     (Variacao MEC + Residuo) vive no footer.
 *   - cada grupo = 1 driver (contribution_brl = impacto giro-limpo no PL Sub)
 * Header KPI = Δ da cota; reconciliacao + giro no footer. Click numa barra de
 * grupo abre o drill (residuo nao e clicavel).
 */

import * as React from "react"

import { Card } from "@/components/tremor/Card"
import { VarianceBridgeCard } from "@/design-system/components/VarianceBridgeCard"
import type {
  Operacoes2DriverContribution,
  Operacoes2VarianceBridgeData,
  VariacaoResumoResponse,
} from "@/lib/api-client"

const fmtBRLFull = (v: number) =>
  "R$ " + Math.abs(v).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const fmtSigned = (v: number) => (v >= 0 ? "+" : "−") + fmtBRLFull(v)

// ISO "YYYY-MM-DD" -> "DD/MM" via slice (sem Date, evita drift de fuso).
const ddmm = (iso: string | null | undefined) =>
  iso && iso.length >= 10 ? `${iso.slice(8, 10)}/${iso.slice(5, 7)}` : (iso ?? "")

export type VariacaoWaterfallProps = {
  data?:         VariacaoResumoResponse
  loading?:      boolean
  onDrillGrupo?: (drillKey: string) => void
}

export function VariacaoWaterfall({ data, loading, onDrillGrupo }: VariacaoWaterfallProps) {
  const bridge = React.useMemo<Operacoes2VarianceBridgeData | null>(() => {
    if (!data) return null
    const drivers: Operacoes2DriverContribution[] = data.grupos.map((g) => ({
      member_id:        g.key,
      member_label:     g.label,
      contribution_brl: g.impacto_pl_sub,
      contribution_pct: null,
      prior_value:      0,
      current_value:    0,
    }))
    // Bridge CALCULADO: ancoras = PL Sub calculado por nos (pl_sub_calc), nao o
    // MEC. Os drivers sao a NOSSA decomposicao e Σ drivers == cota_delta ==
    // pl_sub_calc_d0 - pl_sub_calc_d1 (disponibilidades e o plug), entao o
    // waterfall fecha EXATO na ancora calc — sem barra de "Residuo". A
    // comparacao com o MEC oficial (Variacao MEC + Residuo) fica no footer.
    return {
      prior_anchor_label:   `PL ${ddmm(data.data_anterior)}`,
      prior_anchor_value:   data.pl_sub_calc_d1,
      current_anchor_label: `PL ${ddmm(data.data)}`,
      current_anchor_value: data.pl_sub_calc_d0,
      delta_brl:            data.cota_delta,
      delta_pct:            data.pl_sub_calc_d1 ? (data.cota_delta / data.pl_sub_calc_d1) * 100 : null,
      drivers,
      outros_rollup:        null,
      unidade:              "BRL",
    }
  }, [data])

  const handleDriverClick = React.useCallback((driver: Operacoes2DriverContribution) => {
    if (!data || !onDrillGrupo) return
    const g = data.grupos.find((x) => x.key === driver.member_id)
    if (g?.drill_key) onDrillGrupo(g.drill_key)
  }, [data, onDrillGrupo])

  if (loading && !data) {
    return (
      <Card className="flex h-[420px] animate-pulse flex-col gap-3">
        <div className="h-5 w-40 rounded bg-gray-200 dark:bg-gray-800" />
        <div className="h-8 w-48 rounded bg-gray-200 dark:bg-gray-800" />
        <div className="flex-1 rounded bg-gray-100 dark:bg-gray-900" />
      </Card>
    )
  }
  if (!data || !bridge) return null

  return (
    <VarianceBridgeCard
      data={bridge}
      zoomToActivity
      title="O que moveu a cota"
      caption={`PL ${ddmm(data.data_anterior)} → transformações → PL ${ddmm(data.data)} (calculado)`}
      headerKpi={{
        value: fmtSigned(data.cota_delta),
        delta: bridge.delta_pct != null
          ? { value: bridge.delta_pct, suffix: "%", good: data.cota_delta >= 0, fractionDigits: 2 }
          : undefined,
        deltaSub: "variação do dia",
      }}
      onDriverClick={handleDriverClick}
      height={300}
      footer={<WaterfallFooter data={data} />}
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
          <span className="font-medium tabular-nums text-gray-900 dark:text-gray-100">{fmtSigned(r.variacao_apresentada)}</span>
        </div>
        <div className="flex items-center justify-between text-[11px]">
          <span className="text-gray-500 dark:text-gray-400">Variação MEC <span className="text-gray-400 dark:text-gray-600">· QiTech, oficial</span></span>
          <span className="font-medium tabular-nums text-gray-900 dark:text-gray-100">{fmtSigned(r.variacao_mec)}</span>
        </div>
        <div className="mt-1 flex items-center justify-between border-t border-gray-200 pt-1 text-[11px] dark:border-gray-800">
          <span className="font-medium text-gray-700 dark:text-gray-300">Resíduo não explicado</span>
          <span className={r.fecha ? "font-semibold tabular-nums text-emerald-600 dark:text-emerald-400" : "font-semibold tabular-nums text-amber-600 dark:text-amber-400"}>
            {fmtSigned(r.residuo)} {r.fecha ? "✓" : "⚠"}
          </span>
        </div>
      </div>
    </div>
  )
}
