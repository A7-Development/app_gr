"use client"

import { cx } from "@/lib/utils"
import type { KPI } from "@/lib/api-client"

const moeda = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
})
const moedaCompacta = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 2,
})
const numero = new Intl.NumberFormat("pt-BR")
const decimal1 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 })

export function formatKPIValue(k: KPI, compact = false): string {
  switch (k.unidade) {
    case "BRL":
      return compact && k.valor >= 10_000
        ? moedaCompacta.format(k.valor)
        : moeda.format(k.valor)
    case "%":
      return `${decimal1.format(k.valor)}%`
    case "dias":
      return `${decimal1.format(k.valor)} dias`
    default:
      return numero.format(k.valor)
  }
}

//
// KpiHero — 3 metricas "hero" em linha, sem Card wrapper, valores grandes.
// Inspirado em src/components/ui/homepage/MetricsCards.tsx do template Tremor:
// <dl flex flex-wrap gap-x-12 gap-y-6> com <dt> label + <dd> valor inline.
//

function KpiHeroItem({ kpi }: { kpi: KPI | undefined }) {
  return (
    <div className="flex flex-col gap-1">
      <dt className="text-xs font-medium text-gray-500 dark:text-gray-400">
        {kpi?.label ?? "--"}
      </dt>
      <dd className="text-2xl font-semibold tabular-nums text-gray-900 dark:text-gray-50">
        {kpi ? formatKPIValue(kpi, true) : "--"}
      </dd>
      {kpi?.detalhe && (
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {kpi.detalhe}
        </span>
      )}
    </div>
  )
}

export function KpiHero({
  kpis,
  className,
}: {
  kpis: (KPI | undefined)[]
  className?: string
}) {
  return (
    <dl
      className={cx(
        "flex flex-wrap items-start gap-x-12 gap-y-6",
        className,
      )}
    >
      {kpis.map((k, i) => (
        <KpiHeroItem key={i} kpi={k} />
      ))}
    </dl>
  )
}

//
// KpiSecondary — metricas complementares, linha horizontal menor.
// Valor em text-base, label em text-xs inline (label e valor na mesma linha
// quando tiver espaco, empilhados no mobile).
//

function KpiSecondaryItem({ kpi }: { kpi: KPI | undefined }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs font-medium text-gray-500 dark:text-gray-400">
        {kpi?.label ?? "--"}
      </dt>
      <dd className="text-base font-semibold tabular-nums text-gray-900 dark:text-gray-50">
        {kpi ? formatKPIValue(kpi, true) : "--"}
      </dd>
    </div>
  )
}

export function KpiSecondary({
  kpis,
  className,
}: {
  kpis: (KPI | undefined)[]
  className?: string
}) {
  return (
    <dl
      className={cx(
        "flex flex-wrap items-start gap-x-10 gap-y-4",
        className,
      )}
    >
      {kpis.map((k, i) => (
        <KpiSecondaryItem key={i} kpi={k} />
      ))}
    </dl>
  )
}
