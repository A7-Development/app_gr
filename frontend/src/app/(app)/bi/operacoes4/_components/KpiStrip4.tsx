// src/app/(app)/bi/operacoes4/_components/KpiStrip4.tsx
//
// L1 da pagina /bi/operacoes4 — 4 KpiCards (sem o Potencial, que migra
// pro card lateral de L2 conforme decisao do handoff SPEC + Ricardo
// 2026-05-20). Reusa o termometro do bundle abaMesCorrenteV3 ja
// existente; consome apenas as 4 cells aditivas/medianas.

"use client"

import * as React from "react"

import { KpiCard, KpiStrip } from "@/design-system/components"
import type {
  Operacoes2MesCorrenteKpiCell,
  Operacoes2MesCorrenteTermometro,
} from "@/lib/api-client"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 2,
})

const fmtPct1 = (v: number) => `${v.toFixed(1).replace(".", ",")}%`
const fmtDias1 = (v: number) => `${v.toFixed(1).replace(".", ",")} d`

function fmtValor(cell: Operacoes2MesCorrenteKpiCell): string {
  switch (cell.unidade) {
    case "BRL":
      return fmtBRL.format(cell.valor)
    case "%":
      return fmtPct1(cell.valor)
    case "dias":
      return fmtDias1(cell.valor)
    default:
      return String(cell.valor)
  }
}

function PrimaryCell({
  label,
  cell,
}: {
  label: string
  cell: Operacoes2MesCorrenteKpiCell
}) {
  const valor = fmtValor(cell)
  const deltaProp =
    cell.delta_vop_du_pct != null
      ? { value: cell.delta_vop_du_pct, suffix: "%" }
      : undefined
  return (
    <KpiCard
      label={label}
      value={valor}
      delta={deltaProp}
      deltaSub="VOP-DU"
      sub={cell.mes_label}
    />
  )
}

export function KpiStrip4({
  data,
  /** True quando MTD ainda nao teve DU util (1o dia do mes pre-abertura). */
  emptyMtd,
}: {
  data: Operacoes2MesCorrenteTermometro
  emptyMtd?: boolean
}) {
  return (
    <div className="flex flex-col gap-2">
      <KpiStrip cols={4}>
        <PrimaryCell label="VOP" cell={data.vop} />
        <PrimaryCell label="Receita" cell={data.receita} />
        <PrimaryCell label="Taxa média" cell={data.taxa} />
        <PrimaryCell label="Prazo médio" cell={data.prazo} />
      </KpiStrip>
      {emptyMtd && (
        <p className="text-[11px] italic text-gray-500 dark:text-gray-400">
          Aguardando primeiros DUs do mês — KPIs ainda zerados.
        </p>
      )}
    </div>
  )
}
