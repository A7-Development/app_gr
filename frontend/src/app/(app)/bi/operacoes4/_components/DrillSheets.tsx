// src/app/(app)/bi/operacoes4/_components/DrillSheets.tsx
//
// 3 drill-down sheets da pagina /bi/operacoes4 (PR4):
//   - DrillReceitaTipoContent: linha da composicao L3
//   - DrillMovimentoContent:   MovementCard L5 (Novos / Sumidos / Top Movers)
//   - (reusa DrillOperacoesDoDia de operacoes3 para drill do dia em L7)
//
// Cada sheet recebe os dados ja em cache no caller — sem fetch novo para
// evitar duplicar payloads que ja estao no React Query da pagina.

"use client"

import * as React from "react"

import { Card } from "@/components/tremor/Card"
import { cardTokens } from "@/design-system/tokens/card"
import { cx } from "@/lib/utils"
import { tokens } from "@/design-system/tokens"
import type {
  Operacoes2CedenteMtdItem,
  Operacoes4ReceitaComposicaoItem,
  Operacoes4ReceitaTipo,
} from "@/lib/api-client"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 2,
})
const fmtBRLFull = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
})

function fmtPctSigned(v: number | null): string {
  if (v === null) return "—"
  const sign = v > 0 ? "+" : ""
  return `${sign}${v.toFixed(1).replace(".", ",")}%`
}

const TIPO_LABEL: Record<Operacoes4ReceitaTipo, string> = {
  desagio: "Deságio",
  tarifa_cessao: "Tarifa de cessão",
  tarifas_operacionais: "Tarifas operacionais",
  outras: "Outras",
}

const TIPO_DESC: Record<Operacoes4ReceitaTipo, string> = {
  desagio:
    "Receita principal — juros embutidos na operação (total_de_juros do Bitfin). Cresce com volume cedido e taxa média ponderada.",
  tarifa_cessao:
    "Tarifa cobrada por comunicado de cessão emitido a sacados. Volume típico baixo — sobe com operações que envolvem grandes lotes de títulos.",
  tarifas_operacionais:
    "Soma de tarifas operacionais: consultas financeiras, consultas fiscais, registros bancários e documentos digitais. Pulveriza em vários itens pequenos por operação.",
  outras:
    "Ad-valorem + rebate. Hoje zero em produção — placeholder para tipos que apareçam no futuro.",
}

// Cor do bucket: replica a paleta da ReceitaCompositionBar para coerencia
// visual entre L3 e o sheet.
const BUCKET_COLOR: Record<Operacoes4ReceitaTipo, string> = {
  desagio: tokens.colors.chart[0],
  tarifa_cessao: tokens.colors.chart[1],
  tarifas_operacionais: tokens.colors.chart[2],
  outras: "#CBD5E1",
}

// ─── Sheet do bucket de receita (L3) ────────────────────────────────────────

export function DrillReceitaTipoContent({
  bucket,
  total_mtd,
  total_parity,
}: {
  bucket: Operacoes4ReceitaComposicaoItem
  total_mtd: number
  total_parity: number
}) {
  const valor =
    typeof bucket.valor === "string" ? Number(bucket.valor) : bucket.valor

  return (
    <div className="flex flex-col gap-4 p-6">
      {/* Header KPI */}
      <Card className={cx(cardTokens.body)}>
        <div className="flex items-start gap-3">
          <span
            aria-hidden="true"
            className="mt-1.5 inline-block size-3 shrink-0 rounded-sm"
            style={{ background: BUCKET_COLOR[bucket.tipo] }}
          />
          <div className="min-w-0 flex-1">
            <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Receita por tipo · MTD
            </p>
            <h2 className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-50">
              {TIPO_LABEL[bucket.tipo]}
            </h2>
            <p className="mt-2 text-[20px] font-semibold leading-none tabular-nums text-gray-900 dark:text-gray-50">
              {fmtBRLFull.format(valor)}
            </p>
            <p className="mt-2 flex flex-wrap gap-x-3 text-xs text-gray-500 dark:text-gray-400">
              <span>
                Share:{" "}
                <span className="font-medium tabular-nums text-gray-900 dark:text-gray-100">
                  {bucket.share_pct.toFixed(1).replace(".", ",")}%
                </span>
              </span>
              <span>
                Δ paridade:{" "}
                <span
                  className={cx(
                    "font-medium tabular-nums",
                    bucket.delta_pct === null
                      ? "text-gray-400 dark:text-gray-600"
                      : bucket.delta_pct >= 0
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-red-600 dark:text-red-400",
                  )}
                >
                  {fmtPctSigned(bucket.delta_pct)}
                </span>
              </span>
            </p>
          </div>
        </div>
      </Card>

      {/* Contexto descritivo */}
      <Card className={cx(cardTokens.body)}>
        <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
          Sobre este tipo
        </p>
        <p className="mt-2 text-sm leading-relaxed text-gray-700 dark:text-gray-300">
          {TIPO_DESC[bucket.tipo]}
        </p>
      </Card>

      {/* Contribuicao relativa */}
      <Card className={cx(cardTokens.body)}>
        <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
          Posição no total MTD
        </p>
        <div className="mt-3 flex flex-col gap-2">
          <div className="flex items-baseline justify-between gap-2 text-[12px] tabular-nums">
            <span className="text-gray-600 dark:text-gray-300">
              Este bucket
            </span>
            <span className="font-medium text-gray-900 dark:text-gray-100">
              {fmtBRLFull.format(valor)}
            </span>
          </div>
          <div className="flex items-baseline justify-between gap-2 text-[12px] tabular-nums">
            <span className="text-gray-600 dark:text-gray-300">
              Total receita MTD
            </span>
            <span className="font-medium text-gray-900 dark:text-gray-100">
              {fmtBRLFull.format(total_mtd)}
            </span>
          </div>
          <div className="flex items-baseline justify-between gap-2 text-[12px] tabular-nums">
            <span className="text-gray-600 dark:text-gray-300">
              Paridade DU mês ant.
            </span>
            <span className="font-medium text-gray-900 dark:text-gray-100">
              {fmtBRLFull.format(total_parity)}
            </span>
          </div>
        </div>
      </Card>

      {/* Followup do SPEC: top 10 contribuintes — precisa de endpoint novo */}
      <p className="text-[10.5px] italic text-gray-400 dark:text-gray-600">
        Top 10 cedentes e produtos contribuindo para este tipo virão em
        iteração futura (depende de endpoint novo no backend).
      </p>
    </div>
  )
}

// ─── Sheet de movimentos (L5: Novos / Sumidos / Top Movers) ─────────────────

type CategoriaMovimento = "novos" | "sumidos" | "movers"

const CATEGORIA_TITULO: Record<CategoriaMovimento, string> = {
  novos: "Cedentes novos no mês",
  sumidos: "Cedentes sumidos",
  movers: "Top movers do mês",
}

const CATEGORIA_DESC: Record<CategoriaMovimento, string> = {
  novos:
    "Cedentes cuja 1ª operação histórica caiu dentro do MTD — entraram na carteira agora.",
  sumidos:
    "Cedentes que operaram no mês anterior (mesmos N DUs) mas têm volume zero no MTD.",
  movers:
    "Cedentes recorrentes com maior variação absoluta de volume MTD vs paridade DU.",
}

export function DrillMovimentoContent({
  categoria,
  items,
}: {
  categoria: CategoriaMovimento
  items: Operacoes2CedenteMtdItem[]
}) {
  return (
    <div className="flex flex-col gap-4 p-6">
      <Card className={cx(cardTokens.body)}>
        <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
          {CATEGORIA_TITULO[categoria]}
        </p>
        <p className="mt-2 text-[20px] font-semibold leading-none tabular-nums text-gray-900 dark:text-gray-50">
          {items.length} cedentes
        </p>
        <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
          {CATEGORIA_DESC[categoria]}
        </p>
      </Card>

      {items.length === 0 ? (
        <p className="py-6 text-center text-xs text-gray-500 dark:text-gray-400">
          Nenhum cedente nesta categoria.
        </p>
      ) : (
        <Card className={cx(cardTokens.body)}>
          <table className="w-full text-left text-[12px] tabular-nums">
            <thead>
              <tr className="border-b border-gray-200 text-[10.5px] uppercase tracking-wider text-gray-500 dark:border-gray-800 dark:text-gray-400">
                <th className="py-1.5 pr-2 font-medium">Cedente</th>
                <th className="py-1.5 pr-2 text-right font-medium">
                  Volume MTD
                </th>
                <th className="py-1.5 pr-2 text-right font-medium">
                  Δ paridade
                </th>
                <th className="py-1.5 pr-2 text-right font-medium">N ops</th>
                <th className="py-1.5 text-right font-medium">Taxa</th>
              </tr>
            </thead>
            <tbody>
              {items.map((c) => (
                <tr
                  key={c.cedente_nome}
                  className="border-b border-gray-100 last:border-b-0 dark:border-gray-900"
                >
                  <td className="py-1.5 pr-2 text-gray-900 dark:text-gray-100">
                    {c.cedente_nome}
                  </td>
                  <td className="py-1.5 pr-2 text-right text-gray-900 dark:text-gray-100">
                    {c.volume_mtd !== null ? fmtBRL.format(c.volume_mtd) : "—"}
                  </td>
                  <td
                    className={cx(
                      "py-1.5 pr-2 text-right",
                      c.delta_vs_mes_ant_pct === null
                        ? "text-gray-400 dark:text-gray-600"
                        : c.delta_vs_mes_ant_pct >= 0
                          ? "text-emerald-600 dark:text-emerald-400"
                          : "text-red-600 dark:text-red-400",
                    )}
                  >
                    {fmtPctSigned(c.delta_vs_mes_ant_pct)}
                  </td>
                  <td className="py-1.5 pr-2 text-right text-gray-500 dark:text-gray-400">
                    {c.n_op ?? "—"}
                  </td>
                  <td className="py-1.5 text-right text-gray-500 dark:text-gray-400">
                    {c.taxa_media !== null
                      ? `${c.taxa_media.toFixed(2).replace(".", ",")}%`
                      : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </div>
  )
}

export type { CategoriaMovimento }
