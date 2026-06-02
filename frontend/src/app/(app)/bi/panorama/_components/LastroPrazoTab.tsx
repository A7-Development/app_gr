// Aba Lastro & Prazo — distribuicao da carteira a vencer por faixa de prazo.
//
// Decisao metodologica (conversa 2026-06-01): distribuicao por faixa, NUNCA
// prazo medio em dias — a faixa +1080d e aberta/censurada.

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import type { EChartsOption } from "echarts"

import { EChartsCard } from "@/design-system/components/EChartsCard"
import { biPanorama } from "@/lib/api-client"
import type { PanoramaFilters } from "@/lib/api-client"

import { fmtBRLCompact, fmtPct } from "./format"
import { TabSkeleton, TabError } from "./_state"

export function LastroPrazoTab({ filters }: { filters: PanoramaFilters }) {
  const q = useQuery({
    queryKey: ["bi", "panorama", "lastro-prazo", filters],
    queryFn: () => biPanorama.lastroPrazo(filters),
  })

  if (q.isLoading) return <TabSkeleton />
  if (q.isError || !q.data) return <TabError onRetry={() => q.refetch()} />

  const { distribuicao_prazo, total_a_vencer } = q.data.data

  // Barras horizontais: % da carteira a vencer por faixa. +1080d destacada
  // (faixa aberta) em cor distinta.
  const labels = distribuicao_prazo.map((f) => f.faixa)
  const option: EChartsOption = {
    grid: { top: 12, right: 48, bottom: 16, left: 76 },
    xAxis: {
      type: "value",
      axisLabel: { fontSize: 11, color: "#6B7280", formatter: "{value}%" },
      splitLine: { lineStyle: { color: "rgba(107,114,128,0.15)" } },
    },
    yAxis: {
      type: "category",
      data: labels,
      inverse: true,
      axisTick: { show: false },
      axisLabel: { fontSize: 11, color: "#6B7280" },
    },
    series: [
      {
        type: "bar",
        data: distribuicao_prazo.map((f) => ({
          value: f.pct,
          // +1080d e a faixa aberta/censurada — cor de atencao (slate) p/ sinalizar.
          itemStyle: {
            color: f.faixa === "+1080d" ? "#94A3B8" : "#3B82F6",
            borderRadius: [0, 3, 3, 0],
          },
        })),
        barWidth: "62%",
        label: {
          show: true,
          position: "right",
          fontSize: 11,
          color: "#6B7280",
          formatter: (p: unknown) =>
            `${(p as { value: number }).value.toFixed(1).replace(".", ",")}%`,
        },
      },
    ],
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params: unknown) => {
        const p = (params as Array<{ dataIndex: number }>)[0]
        const f = distribuicao_prazo[p.dataIndex]
        return `${f.faixa}<br/>${fmtPct(f.pct, 1)} · ${fmtBRLCompact(f.valor)}`
      },
    },
  }

  return (
    <>
      <EChartsCard
        title="PERFIL DE PRAZO DA CARTEIRA"
        caption={`Distribuição da carteira a vencer por faixa de vencimento · total ${fmtBRLCompact(total_a_vencer)}`}
        option={option}
        height={320}
      />
      <p className="px-1 text-[12px] leading-relaxed text-gray-500 dark:text-gray-400">
        Mostramos a <strong>distribuição por faixa</strong>, não um “prazo médio” em dias:
        a última faixa (<strong>+1080d</strong>, destacada) é <em>aberta</em> — não tem teto,
        então qualquer média seria um artefato. Carteiras concentradas em ≤90d são de
        antecipação de curtíssimo prazo; concentração em +1080d indica financiamento longo.
      </p>
    </>
  )
}
