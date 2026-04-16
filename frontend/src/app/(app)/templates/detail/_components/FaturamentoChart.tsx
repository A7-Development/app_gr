"use client"

import * as React from "react"

import { AreaChart } from "@/components/charts/AreaChart"

const moedaBR = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
})

type Ponto = { mes: string; Receita: number }

type Props = {
  data: Ponto[]
}

export function FaturamentoChart({ data }: Props) {
  return (
    <AreaChart
      data={data}
      index="mes"
      categories={["Receita"]}
      colors={["blue"]}
      valueFormatter={(value) => moedaBR.format(value)}
      showLegend={false}
      className="h-72"
    />
  )
}
