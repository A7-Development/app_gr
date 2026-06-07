"use client"

/**
 * ResumoConciliacaoCharts — visual da carteira ao lado da tabela-resumo (50/50).
 *
 * Dois mini-charts empilhados, ambos no MESMO conjunto filtrado da pagina (re-
 * escopo total: UA/Status/Banco/Produto/Cedente) — bate com a tabela-resumo e o
 * detalhe (§7.2/§14.6):
 *
 *   1. Donut por QUANTIDADE de titulos (composicao por status) + legenda.
 *   2. Barra de RECONCILIACAO por VALOR: a carteira aberta (R$ BITFIN) decomposta
 *      por status; centro da historia = quanto ja esta conciliado.
 *
 * Cores via STATUS_CHART (casam com as fatias do donut e com a semantica do
 * badge). Recebe o `resumo` ja computado das linhas filtradas — nao refaz conta.
 */

import * as React from "react"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import { DonutChart } from "@/components/charts/DonutChart"
import { cardTokens } from "@/design-system/tokens/card"
import type { ResumoStatusConciliacao } from "@/lib/api-client"

import { STATUS_BADGE_LABEL, STATUS_CHART, STATUS_META, STATUS_ORDER } from "./status"

const fmtInt = new Intl.NumberFormat("pt-BR")

/** R$ compacto (39,6M / 812,4k / 950) — cabe no rotulo do total. */
function fmtBRLcompact(v: number): string {
  const abs = Math.abs(v)
  if (abs >= 1_000_000) return `R$ ${(v / 1_000_000).toFixed(1).replace(".", ",")}M`
  if (abs >= 1_000) return `R$ ${(v / 1_000).toFixed(1).replace(".", ",")}k`
  return `R$ ${fmtInt.format(Math.round(v))}`
}

export function ResumoConciliacaoCharts({
  resumo,
}: {
  resumo: ResumoStatusConciliacao[]
}) {
  // Ordena pela ordem canonica; ignora status ausentes no escopo filtrado.
  const ordered = React.useMemo(
    () =>
      STATUS_ORDER.map((s) => resumo.find((r) => r.status === s)).filter(
        (r): r is ResumoStatusConciliacao => r != null,
      ),
    [resumo],
  )

  // Donut: composicao por quantidade (so status com qtd > 0).
  const donutRows = ordered.filter((r) => r.quantidade > 0)
  const donutData = donutRows.map((r) => ({
    key: r.status,
    label: STATUS_BADGE_LABEL[r.status],
    qtd: r.quantidade,
  }))
  const donutColors = donutRows.map((r) => STATUS_CHART[r.status].color)
  const totalQtd = donutRows.reduce((a, r) => a + r.quantidade, 0)

  // Barra de reconciliacao: carteira aberta (valor BITFIN) por status (> 0).
  const barRows = ordered.filter((r) => r.valor_bitfin > 0)
  const totalValor = barRows.reduce((a, r) => a + r.valor_bitfin, 0)
  const conciliadoValor =
    barRows.find((r) => r.status === "conciliado")?.valor_bitfin ?? 0
  const pctConciliado = totalValor > 0 ? (conciliadoValor / totalValor) * 100 : 0

  if (ordered.length === 0) {
    return (
      <Card className={cx(cardTokens.body, "flex items-center justify-center")}>
        <p className="text-sm text-gray-400 dark:text-gray-600">Sem dados no escopo.</p>
      </Card>
    )
  }

  return (
    <Card className={cardTokens.body}>
      {/* 1 — Donut por quantidade + legenda */}
      <div className="flex items-center gap-5">
        <DonutChart
          data={donutData}
          category="label"
          value="qtd"
          colors={donutColors}
          variant="donut"
          showLabel
          label={fmtInt.format(totalQtd)}
          valueFormatter={(v) => `${fmtInt.format(v)} títulos`}
          className="size-36 shrink-0"
        />
        <ul className="flex-1 space-y-1.5">
          {ordered.map((r) => (
            <li key={r.status} className="flex items-center gap-2 text-[13px]">
              <span
                aria-hidden="true"
                className={cx("size-2.5 shrink-0 rounded-sm", STATUS_CHART[r.status].swatch)}
              />
              <span className="flex-1 truncate text-gray-700 dark:text-gray-300">
                {STATUS_META[r.status].label}
              </span>
              <span className="shrink-0 tabular-nums font-medium text-gray-900 dark:text-gray-50">
                {fmtInt.format(r.quantidade)}
              </span>
              <span className="w-10 shrink-0 text-right tabular-nums text-gray-400 dark:text-gray-500">
                {r.percentual.toFixed(0)}%
              </span>
            </li>
          ))}
        </ul>
      </div>

      <div className="my-4 border-t border-gray-100 dark:border-gray-800" />

      {/* 2 — Barra de reconciliacao por valor (carteira aberta BITFIN) */}
      <div>
        <div className="mb-2 flex items-baseline justify-between">
          <span className="text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-500">
            Carteira aberta
          </span>
          <span className="text-sm font-semibold tabular-nums text-gray-900 dark:text-gray-50">
            {fmtBRLcompact(totalValor)}
          </span>
        </div>
        <div className="flex h-3 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
          {barRows.map((r) => (
            <div
              key={r.status}
              className={cx("h-full", STATUS_CHART[r.status].swatch)}
              style={{ width: `${(r.valor_bitfin / totalValor) * 100}%` }}
              title={`${STATUS_META[r.status].label}: ${fmtBRLcompact(r.valor_bitfin)}`}
            />
          ))}
        </div>
        <p className="mt-2 text-[11px] text-gray-500 dark:text-gray-400">
          <span className="font-semibold text-emerald-700 dark:text-emerald-400">
            {pctConciliado.toFixed(0)}% conciliado
          </span>{" "}
          · {(100 - pctConciliado).toFixed(0)}% a conciliar (em valor)
        </p>
      </div>
    </Card>
  )
}
