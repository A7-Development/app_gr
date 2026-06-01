"use client"

/**
 * DetalhamentoPanel — o painel dos 60% da pagina Cota Sub.
 *
 * Um card por AREA do balanco (Ativo e Passivo), cada um com o resumo de 1 linha
 * da sua tool + o delta (impacto no PL Sub). Clicar abre o drill profundo daquela
 * area. E o nivel intermediario: o balancete (40%) diz a posicao, este diz "o que
 * cada area fez", e o drill diz "a prova papel-a-papel".
 *
 * 100% estruturado (vem de /variacao/detalhamento, orquestracao das tools).
 */

import { RiAlertLine, RiArrowRightLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import type {
  AreaDetalhe,
  CategoriaPatrimonialKey,
  DetalhamentoDiaResponse,
} from "@/lib/api-client"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL", minimumFractionDigits: 0, maximumFractionDigits: 0,
})
const fmtSigned = (v: number) => (v >= 0 ? "+" : "−") + fmtBRL.format(Math.abs(v))
const toneClass = (v: number) =>
  v >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"

export type DetalhamentoPanelProps = {
  data?:             DetalhamentoDiaResponse
  loading?:          boolean
  onDrillCategoria?: (key: CategoriaPatrimonialKey) => void
}

function AreaRow({ area, onDrill }: { area: AreaDetalhe; onDrill?: (k: CategoriaPatrimonialKey) => void }) {
  const drillable = !!area.drill_key && !!onDrill
  return (
    <button
      type="button"
      disabled={!drillable}
      onClick={drillable ? () => onDrill!(area.drill_key as CategoriaPatrimonialKey) : undefined}
      className={cx(
        "group flex w-full items-start gap-3 rounded border border-transparent px-2 py-2 text-left",
        drillable
          ? "cursor-pointer hover:border-gray-200 hover:bg-gray-50 dark:hover:border-gray-800 dark:hover:bg-gray-900/50"
          : "cursor-default",
      )}
    >
      {area.severidade === "atencao" ? (
        <RiAlertLine className="mt-0.5 size-4 shrink-0 text-amber-500" aria-hidden />
      ) : (
        <span className="mt-0.5 size-4 shrink-0" />
      )}
      <div className="min-w-0 flex-1">
        <div className="flex items-baseline justify-between gap-3">
          <span className="truncate text-[13px] font-medium text-gray-900 dark:text-gray-100">{area.label}</span>
          <span className={cx("shrink-0 text-[13px] font-semibold tabular-nums", toneClass(area.delta))}>
            {fmtSigned(area.delta)}
          </span>
        </div>
        <span className="mt-0.5 block truncate text-[11px] text-gray-500 dark:text-gray-400">{area.resumo}</span>
      </div>
      {drillable && (
        <RiArrowRightLine className="mt-0.5 size-3.5 shrink-0 text-gray-300 transition-colors group-hover:text-blue-500 dark:text-gray-600" aria-hidden />
      )}
    </button>
  )
}

export function DetalhamentoPanel({ data, loading, onDrillCategoria }: DetalhamentoPanelProps) {
  if (loading) {
    return (
      <Card className="flex animate-pulse flex-col gap-2">
        <div className="h-5 w-40 rounded bg-gray-200 dark:bg-gray-800" />
        {[0, 1, 2, 3, 4].map((i) => <div key={i} className="h-10 rounded bg-gray-100 dark:bg-gray-900" />)}
      </Card>
    )
  }
  if (!data) return null
  const ativo = data.areas.filter((a) => a.grupo === "ativo")
  const passivo = data.areas.filter((a) => a.grupo === "passivo")

  return (
    <Card className="flex flex-col gap-3">
      <div className="flex items-baseline justify-between">
        <h3 className="text-[13px] font-semibold text-gray-900 dark:text-gray-100">Detalhamento do dia</h3>
        <span className="text-[11px] text-gray-400 dark:text-gray-500">clique numa área para o detalhe</span>
      </div>

      <div className="flex flex-col gap-1">
        <span className="px-2 text-[10px] font-medium uppercase tracking-[0.06em] text-gray-400 dark:text-gray-500">Ativo</span>
        {ativo.map((a) => <AreaRow key={a.key} area={a} onDrill={onDrillCategoria} />)}
      </div>

      <div className="flex flex-col gap-1 border-t border-gray-100 pt-2 dark:border-gray-900">
        <span className="px-2 text-[10px] font-medium uppercase tracking-[0.06em] text-gray-400 dark:text-gray-500">Passivo</span>
        {passivo.map((a) => <AreaRow key={a.key} area={a} onDrill={onDrillCategoria} />)}
      </div>
    </Card>
  )
}
