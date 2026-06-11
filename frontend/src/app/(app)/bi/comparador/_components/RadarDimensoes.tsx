"use client"

// Radar de 5 dimensoes do Comparador: score da dimensao = media dos percentis
// ORIENTADOS (100 = melhor do universo na direcao do indicador) dos
// indicadores do grupo. Veredito visual em 2s; a matriz ao lado explica.

import * as React from "react"

import { EChartsCard } from "@/design-system/components"
import type { ComparadorIndicadoresFundo } from "@/lib/api-client"

import { GRUPOS, INDICADORES, rankOrientado } from "./indicadores"

// Paleta de series A7 (ordem canonica slate -> sky -> teal). Hex inline e
// permitido em EChartsOption (canvas — CLAUDE.md §4).
const SERIES_HEX = ["#64748B", "#0EA5E9", "#14B8A6"]

function scoreDimensao(
  fundo: ComparadorIndicadoresFundo,
  grupo: string,
  direcao: Record<string, boolean>,
): number | null {
  const ranks: number[] = []
  for (const ind of INDICADORES) {
    if (ind.grupo !== grupo) continue
    const rank = fundo[`${ind.key}_rank` as keyof ComparadorIndicadoresFundo]
    const orientado = rankOrientado(
      typeof rank === "number" ? rank : null,
      direcao[ind.key],
    )
    if (orientado !== null) ranks.push(orientado)
  }
  if (ranks.length === 0) return null
  return ranks.reduce((a, b) => a + b, 0) / ranks.length
}

export function RadarDimensoes({
  fundos,
  direcao,
}: {
  fundos: ComparadorIndicadoresFundo[]
  direcao: Record<string, boolean>
}) {
  const option = React.useMemo(
    () => ({
      legend: {
        bottom: 0,
        itemWidth: 10,
        itemHeight: 10,
        textStyle: { fontSize: 11 },
        data: fundos.map((f) => f.denom_social ?? f.cnpj),
      },
      tooltip: { trigger: "item" as const },
      radar: {
        indicator: GRUPOS.map((g) => ({ name: g, max: 100 })),
        radius: "62%",
        splitNumber: 4,
        axisName: { fontSize: 10.5, color: "#6B7280" },
      },
      series: [
        {
          type: "radar" as const,
          data: fundos.map((f, idx) => ({
            name: f.denom_social ?? f.cnpj,
            value: GRUPOS.map((g) =>
              Math.round(scoreDimensao(f, g, direcao) ?? 0),
            ),
            itemStyle: { color: SERIES_HEX[idx % SERIES_HEX.length] },
            lineStyle: { color: SERIES_HEX[idx % SERIES_HEX.length], width: 2 },
            areaStyle: { opacity: 0.08 },
          })),
        },
      ],
    }),
    [fundos, direcao],
  )

  return (
    <EChartsCard
      title="Score por dimensão"
      caption="Percentil orientado no universo (100 = melhor)"
      option={option}
      height={300}
    />
  )
}
