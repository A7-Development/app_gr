// Aba REALINVEST vs Mercado — tear-sheet do fundo posicionado contra o mercado.
//
// Cockpit comparativo: nosso fundo (default REALINVEST) com cada metrica
// posicionada por percentil vs o universo CVM e vs os pares (mesmo
// condominio + porte). Nao usa os filtros globais — e sobre UM fundo.

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import type { EChartsOption } from "echarts"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import { EChartsCard } from "@/design-system/components/EChartsCard"
import { cardTokens } from "@/design-system/tokens/card"
import { biPanorama } from "@/lib/api-client"
import type { PanoramaFundoMetrica } from "@/lib/api-client"

import { competenciaShort, competenciaLong, fmtBRLCompact, fmtMetrica } from "./format"
import { TabSkeleton, TabError } from "./_state"

export function RealinvestTab() {
  const q = useQuery({
    queryKey: ["bi", "panorama", "fundo-comparativo"],
    queryFn: () => biPanorama.fundoComparativo(),
  })

  if (q.isLoading) return <TabSkeleton />
  if (q.isError || !q.data) return <TabError onRetry={() => q.refetch()} />

  const d = q.data.data
  if (!d.encontrado) {
    return (
      <Card className={cx(cardTokens.body, "py-12 text-center")}>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Fundo {d.cnpj} não reporta informe na competência {competenciaLong(d.competencia)}.
        </p>
      </Card>
    )
  }

  const plOption: EChartsOption = {
    grid: { top: 12, right: 12, bottom: 24, left: 52 },
    xAxis: {
      type: "category",
      data: d.evolucao_pl.map((p) => competenciaShort(p.competencia)),
      axisTick: { show: false },
      axisLabel: { fontSize: 10, color: "#6B7280" },
    },
    yAxis: {
      type: "value",
      axisLabel: {
        fontSize: 11,
        color: "#6B7280",
        formatter: (v: number) => `${(v / 1e6).toFixed(0)} mi`,
      },
      splitLine: { lineStyle: { color: "rgba(107,114,128,0.15)" } },
    },
    series: [
      {
        type: "line",
        smooth: false,
        symbol: "none",
        data: d.evolucao_pl.map((p) => p.pl),
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
    tooltip: { trigger: "axis", valueFormatter: (v) => fmtBRLCompact(Number(v)) },
  }

  return (
    <>
      {/* Identidade + PL hero */}
      <Card className={cardTokens.body}>
        <div className="flex flex-col gap-1">
          <span className="text-[11px] font-medium uppercase tracking-wider text-blue-600 dark:text-blue-400">
            Nosso fundo · vs mercado FIDC
          </span>
          <h2 className="text-[18px] font-semibold leading-tight text-gray-900 dark:text-gray-50">
            {d.nome}
          </h2>
          <p className="text-[12px] text-gray-500 dark:text-gray-400">
            CNPJ {d.cnpj}
            {d.condom ? ` · Condomínio ${d.condom.toLowerCase()}` : ""}
            {d.admin ? ` · ${d.admin}` : ""} · {competenciaLong(d.competencia)}
          </p>
        </div>
        <div className="mt-3">
          <EChartsCard
            title="EVOLUÇÃO DO PL"
            caption={`PL atual ${fmtBRLCompact(d.pl)}`}
            option={plOption}
            height={180}
            embedded
          />
        </div>
      </Card>

      {/* Metricas com posicionamento vs mercado/pares */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {d.metricas.map((m) => (
          <MetricaCard key={m.label} m={m} />
        ))}
      </section>
    </>
  )
}

function MetricaCard({ m }: { m: PanoramaFundoMetrica }) {
  const temPercentil = m.percentil_mercado != null
  return (
    <Card className={cardTokens.body}>
      <div className="flex flex-col gap-1.5">
        <span className="text-[10px] font-semibold uppercase tracking-[0.05em] text-gray-500 dark:text-gray-400">
          {m.label}
        </span>
        <span className="text-[20px] font-semibold leading-none tabular-nums text-gray-900 dark:text-gray-50">
          {fmtMetrica(m.valor, m.unidade)}
        </span>
        {m.mercado_mediana != null && (
          <span className="text-[12px] text-gray-500 dark:text-gray-400">
            mediana do mercado: {fmtMetrica(m.mercado_mediana, m.unidade)}
          </span>
        )}
        {temPercentil && (
          <div className="mt-1.5 flex flex-col gap-1">
            <PercentilBar label="mercado" pct={m.percentil_mercado!} />
            {m.percentil_pares != null && (
              <PercentilBar label="pares" pct={m.percentil_pares} />
            )}
          </div>
        )}
      </div>
    </Card>
  )
}

// Barra de percentil: posicao do fundo (0-100) na distribuicao do grupo.
function PercentilBar({ label, pct }: { label: string; pct: number }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-12 shrink-0 text-[10px] uppercase tracking-wide text-gray-400 dark:text-gray-500">
        {label}
      </span>
      <div className="relative h-1.5 flex-1 rounded-full bg-gray-100 dark:bg-gray-800">
        <div
          className="absolute inset-y-0 left-0 rounded-full bg-blue-500"
          style={{ width: `${Math.max(2, Math.min(100, pct))}%` }}
        />
      </div>
      <span className="w-16 shrink-0 text-right text-[11px] tabular-nums text-gray-600 dark:text-gray-300">
        pct {pct.toFixed(0)}
      </span>
    </div>
  )
}
