// src/app/(app)/bi/operacoes3/_components/TermometroStrip.tsx
//
// Termometro do mes corrente — L1 da pagina /bi/operacoes3.
//
// 5 KpiCards canonicos (do Strata Design System, sem extensao):
//   - VOP, Receita: valor em BRL + delta_vop_du_pct (principal) + deltaSub
//     textual com MOM normalizado por DU
//   - Taxa, Prazo: media MTD + delta_vop_du_pct + deltaSub com MOM direto
//     (medias nao normalizam por DU)
//   - Potencial: absoluto (valor + sub descritivo das 3 parcelas), sem delta.
//
// O canon do KpiCard aceita 1 delta + 1 string sub — usamos:
//   delta    = Δ VOP-DU (apples-to-apples temporal, "termometro do mes")
//   deltaSub = string composta "· +X,X% MOM" (comparacao secundaria)

"use client"

import * as React from "react"

import { KpiCard, KpiStrip } from "@/design-system/components"
import type {
  Operacoes2MesCorrenteKpiCell,
  Operacoes2MesCorrentePotencialCell,
  Operacoes2MesCorrenteTermometro,
} from "@/lib/api-client"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 2,
})

const fmtPct1 = (v: number): string =>
  `${v.toFixed(1).replace(".", ",")}%`

const fmtDias1 = (v: number): string =>
  `${v.toFixed(1).replace(".", ",")} d`

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

/**
 * Label do delta principal — apenas VOP-DU (paridade DU).
 *
 * O canon do KpiCard nao tem slot para rotular o numero do delta principal,
 * entao soldamos a label "VOP-DU" no `deltaSub`. MOM foi removido da UI em
 * 2026-05-19 a pedido do Ricardo — campo `delta_mom_pct` permanece no
 * backend para reuso futuro (ex.: tooltip ou movimentos na PR2).
 *
 * VOP-DU = MTD corrente vs MTD do mes anterior nos mesmos N DUs (paridade).
 */
const DELTA_LABEL = "VOP-DU"

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
      deltaSub={DELTA_LABEL}
      sub={cell.mes_label}
    />
  )
}

function PotencialCell({
  cell,
}: {
  cell: Operacoes2MesCorrentePotencialCell
}) {
  // Sublabel descritivo das 3 parcelas — substitui o delta para o Potencial.
  const sub = `${fmtBRL.format(cell.realizado)} real · ${fmtBRL.format(
    cell.caixa,
  )} caixa · ${fmtBRL.format(cell.a_liquidar)} a liquidar`
  return (
    <KpiCard label="Potencial" value={fmtBRL.format(cell.valor)} sub={sub} />
  )
}

export function TermometroStrip({
  data,
}: {
  data: Operacoes2MesCorrenteTermometro
}) {
  return (
    <KpiStrip cols={5}>
      <PrimaryCell label="VOP" cell={data.vop} />
      <PrimaryCell label="Receita" cell={data.receita} />
      <PrimaryCell label="Taxa média" cell={data.taxa} />
      <PrimaryCell label="Prazo médio" cell={data.prazo} />
      <PotencialCell cell={data.potencial} />
    </KpiStrip>
  )
}
