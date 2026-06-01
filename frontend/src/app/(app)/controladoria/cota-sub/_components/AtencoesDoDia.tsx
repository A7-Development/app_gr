"use client"

/**
 * AtencoesDoDia — a faixa "consciencia" do topo da aba Resumo do dia.
 *
 * Mutacao silenciosa / pagamento sem provisao / WOP / capital / reconciliacao —
 * cada atencao e ancorada ao grupo-casa (chip), abre o drill no clique, e quando
 * investigavel oferece o chat. NAO e categoria fora do balanco: e uma LENTE sobre
 * valores que ja estao no waterfall (nao soma duas vezes). Vazio = dia limpo.
 */

import { RiAlertLine, RiCheckLine, RiArrowRightSLine, RiSparkling2Line } from "@remixicon/react"

import { cx } from "@/lib/utils"
import type { AtencaoResumo } from "@/lib/api-client"

const fmtBRL = (v: number) =>
  "R$ " + Math.abs(v).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }).replace(",00", "")

export type AtencoesDoDiaProps = {
  atencoes?:     AtencaoResumo[]
  loading?:      boolean
  onDrillGrupo?: (drillKey: string) => void
  onInvestigar?: (pergunta: string) => void
}

export function AtencoesDoDia({ atencoes, loading, onDrillGrupo, onInvestigar }: AtencoesDoDiaProps) {
  if (loading) return null
  const itens = atencoes ?? []

  if (itens.length === 0) {
    return (
      <div className="flex items-center gap-2 rounded-[6px] border border-emerald-200 bg-emerald-50/50 px-3 py-1.5 text-[12px] text-emerald-700 dark:border-emerald-900/50 dark:bg-emerald-950/20 dark:text-emerald-400">
        <RiCheckLine className="size-3.5 shrink-0" aria-hidden="true" />
        Nenhuma atenção no dia — variação dentro da rotina
      </div>
    )
  }

  return (
    <div className="rounded-[6px] border border-amber-200 bg-amber-50/50 px-3 py-2 dark:border-amber-900/50 dark:bg-amber-950/20">
      <div className="flex items-center gap-1.5 text-[12px] font-semibold text-amber-800 dark:text-amber-300">
        <RiAlertLine className="size-3.5 shrink-0" aria-hidden="true" />
        {itens.length} {itens.length === 1 ? "atenção" : "atenções"} do dia
        <span className="ml-1 text-[11px] font-normal text-amber-600 dark:text-amber-500">— clique para ver a prova</span>
      </div>
      <div className="mt-1.5 flex flex-col gap-1">
        {itens.map((a, i) => {
          const drillable = !!a.drill_key && !!onDrillGrupo
          const investigavel = !drillable && a.investigavel && !!onInvestigar
          const clickable = drillable || investigavel
          return (
            <button
              key={i}
              type="button"
              disabled={!clickable}
              onClick={
                drillable ? () => onDrillGrupo!(a.drill_key!)
                : investigavel ? () => onInvestigar!(a.descricao)
                : undefined
              }
              className={cx(
                "group flex items-center gap-2 rounded px-1 py-0.5 text-left",
                clickable ? "hover:bg-amber-100/50 dark:hover:bg-amber-900/30" : "cursor-default",
              )}
            >
              <span className="size-1 shrink-0 rounded-full bg-amber-500" aria-hidden="true" />
              <span className="flex-1 text-[12px] text-amber-900 dark:text-amber-200">
                {a.descricao}
                <span className="ml-1 font-semibold tabular-nums">{fmtBRL(a.valor)}</span>
              </span>
              {a.grupo_label && (
                <span className="shrink-0 rounded border border-gray-300 bg-white px-1.5 py-0.5 text-[10px] text-gray-600 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300">
                  {a.grupo_label}
                </span>
              )}
              {investigavel
                ? <RiSparkling2Line className="size-3.5 shrink-0 text-violet-500 group-hover:text-violet-600" aria-hidden="true" />
                : <RiArrowRightSLine className={cx("size-3.5 shrink-0", drillable ? "text-amber-400 group-hover:text-blue-500" : "text-transparent")} aria-hidden="true" />
              }
            </button>
          )
        })}
      </div>
    </div>
  )
}
