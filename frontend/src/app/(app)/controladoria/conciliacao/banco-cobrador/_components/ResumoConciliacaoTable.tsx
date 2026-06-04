"use client"

/**
 * ResumoConciliacaoTable — tabela-resumo do confronto do dia (Entrega 3, §2:
 * "Resumo consolidado por status: quantidade, percentual, valor BITFIN, valor
 * banco e diferenca"). Substitui o KpiStrip no topo da pagina.
 *
 * MOTIVO (fuga do DataTable canonico §6): e um resumo FIXO de 5 status + linha
 * Total, com footer de totais e linhas coloridas por status. As maquinas do
 * DataTable (sort, virtualizacao, column manager, busca) nao se aplicam — o
 * valor aqui e a RECONCILIACAO on-screen (§14.6): a soma das 5 linhas = a linha
 * Total. Render com <table> semantica + tableTokens.
 */

import * as React from "react"

import { cx } from "@/lib/utils"
import { tableTokens } from "@/design-system/tokens/table"
import type { ResumoStatusConciliacao } from "@/lib/api-client"
import { STATUS_META, STATUS_ORDER } from "./status"

const fmtInt = new Intl.NumberFormat("pt-BR")
const fmtBRL = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

/** Valor monetario; "—" quando estruturalmente zero (lado ausente do status). */
function brlOrDash(v: number): React.ReactNode {
  if (Math.abs(v) < 0.005) return <span className="text-gray-300 dark:text-gray-600">—</span>
  return fmtBRL.format(v)
}

/** Diferenca: "—" quando ~0; vermelho quando ha gap. */
function DiffValue({ v }: { v: number }) {
  if (Math.abs(v) < 0.005) return <span className="text-gray-300 dark:text-gray-600">—</span>
  return (
    <span className="font-medium text-red-600 dark:text-red-400">
      {v > 0 ? "+" : ""}
      {fmtBRL.format(v)}
    </span>
  )
}

export function ResumoConciliacaoTable({
  resumo,
}: {
  resumo: ResumoStatusConciliacao[]
}) {
  const byStatus = React.useMemo(() => {
    const m = new Map<string, ResumoStatusConciliacao>()
    for (const r of resumo) m.set(r.status, r)
    return m
  }, [resumo])

  // Total reconcilia (§14.6): soma das linhas exibidas = linha Total.
  const total = React.useMemo(() => {
    return resumo.reduce(
      (acc, r) => ({
        quantidade: acc.quantidade + r.quantidade,
        valor_bitfin: acc.valor_bitfin + r.valor_bitfin,
        valor_banco: acc.valor_banco + r.valor_banco,
        diferenca: acc.diferenca + r.diferenca,
      }),
      { quantidade: 0, valor_bitfin: 0, valor_banco: 0, diferenca: 0 },
    )
  }, [resumo])

  return (
    <div className="overflow-hidden rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
      {/* Header band (estilo card canonico — gray, nao brand) */}
      <div className="border-b border-gray-200 px-4 py-2.5 dark:border-gray-800">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
          Conciliação — Boleto BITFIN × Aberto banco · Resumo
        </h3>
      </div>

      <table className="w-full border-collapse text-[13px]">
        <thead className="bg-gray-50 dark:bg-gray-900/60">
          <tr className="text-gray-400 dark:text-gray-500">
            <th className={cx(tableTokens.header, "px-4 py-2 text-left")}>Status</th>
            <th className={cx(tableTokens.header, "px-4 py-2 text-right")}>Qtd</th>
            <th className={cx(tableTokens.header, "px-4 py-2 text-right")}>%</th>
            <th className={cx(tableTokens.header, "px-4 py-2 text-right")}>Valor BITFIN (R$)</th>
            <th className={cx(tableTokens.header, "px-4 py-2 text-right")}>Valor banco (R$)</th>
            <th className={cx(tableTokens.header, "px-4 py-2 text-right")}>Diferença (R$)</th>
          </tr>
        </thead>

        <tbody>
          {STATUS_ORDER.map((status) => {
            const m = STATUS_META[status]
            const r = byStatus.get(status)
            const Icon = m.icon
            const qtd = r?.quantidade ?? 0
            return (
              <tr
                key={status}
                className="border-t border-gray-100 dark:border-gray-900"
              >
                <td className="px-4 py-2">
                  <span className="inline-flex items-center gap-1.5">
                    <Icon className={cx("size-4 shrink-0", m.iconTone)} aria-hidden="true" />
                    <span className={cx("font-medium", m.textTone)}>{m.label}</span>
                  </span>
                </td>
                <td className={cx("px-4 py-2 text-right", tableTokens.cellNumber)}>
                  {qtd > 0 ? fmtInt.format(qtd) : <span className="text-gray-300 dark:text-gray-600">—</span>}
                </td>
                <td className={cx("px-4 py-2 text-right", tableTokens.cellNumberSecondary)}>
                  {r && r.percentual > 0 ? `${r.percentual.toFixed(1)}%` : <span className="text-gray-300 dark:text-gray-600">—</span>}
                </td>
                <td className={cx("px-4 py-2 text-right", tableTokens.cellNumber)}>
                  {brlOrDash(r?.valor_bitfin ?? 0)}
                </td>
                <td className={cx("px-4 py-2 text-right", tableTokens.cellNumber)}>
                  {brlOrDash(r?.valor_banco ?? 0)}
                </td>
                <td className="px-4 py-2 text-right tabular-nums">
                  <DiffValue v={r?.diferenca ?? 0} />
                </td>
              </tr>
            )
          })}
        </tbody>

        <tfoot>
          <tr className="border-t-2 border-gray-200 bg-gray-50 dark:border-gray-700 dark:bg-gray-900/60">
            <td className="px-4 py-2 text-[13px] font-semibold text-gray-900 dark:text-gray-50">
              Total
            </td>
            <td className={cx("px-4 py-2 text-right font-semibold", tableTokens.cellNumber)}>
              {fmtInt.format(total.quantidade)}
            </td>
            <td className={cx("px-4 py-2 text-right", tableTokens.cellNumberSecondary)}>
              {total.quantidade > 0 ? "100,0%" : "—"}
            </td>
            <td className={cx("px-4 py-2 text-right font-semibold", tableTokens.cellNumber)}>
              {brlOrDash(total.valor_bitfin)}
            </td>
            <td className={cx("px-4 py-2 text-right font-semibold", tableTokens.cellNumber)}>
              {brlOrDash(total.valor_banco)}
            </td>
            <td className="px-4 py-2 text-right tabular-nums font-semibold">
              <DiffValue v={total.diferenca} />
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  )
}
