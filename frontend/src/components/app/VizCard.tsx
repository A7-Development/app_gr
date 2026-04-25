"use client"

import * as React from "react"

import { cx } from "@/lib/utils"
import { CardMenu, type MenuSection } from "@/components/app/CardMenu"
import { OverrideChip } from "@/components/app/OverrideChip"
import { OriginDot } from "@/components/app/OriginDot"

//
// VizCard -- card padrao de visualizacao na Zona Z6.
//
// Composicao: header (titulo + subtitulo + OverrideChip + CardMenu) +
// body (children). Reutilizavel em qualquer modulo, nao so BI.
//
// Regras:
// - CardMenu so aparece se houver pelo menos uma secao (agrupar/recorte/tipo).
// - OverrideChip so aparece se `override` for passado.
// - Nao trata sparkline ou chart internamente: o consumidor monta o chart
//   dentro de `children`.
//

type VizCardProps = {
  title: string
  subtitle?: string
  agrupar?: MenuSection
  recorte?: MenuSection
  tipo?: MenuSection
  override?: { label: string; onReset: () => void }
  source?: string
  updatedAtISO?: string | null
  children: React.ReactNode
  className?: string
  bodyClassName?: string
}

export function VizCard({
  title,
  subtitle,
  agrupar,
  recorte,
  tipo,
  override,
  source,
  updatedAtISO,
  children,
  className,
  bodyClassName,
}: VizCardProps) {
  const hasMenu = Boolean(agrupar || recorte || tipo)

  return (
    <section
      className={cx(
        "relative flex flex-col rounded border border-gray-200 bg-white shadow-xs",
        "dark:border-gray-800 dark:bg-gray-950",
        className,
      )}
    >
      <header className="flex items-start justify-between gap-3 px-4 pt-3 pb-2">
        <div className="flex min-w-0 flex-col gap-0.5">
          <div className="flex items-center gap-2">
            <h3 className="truncate text-sm font-semibold text-gray-900 dark:text-gray-50">
              {title}
            </h3>
            {override && (
              <OverrideChip
                label={override.label}
                onReset={override.onReset}
              />
            )}
          </div>
          {subtitle && (
            <p className="text-xs text-gray-500 dark:text-gray-400">
              {subtitle}
            </p>
          )}
        </div>
        {hasMenu && (
          <CardMenu agrupar={agrupar} recorte={recorte} tipo={tipo} />
        )}
      </header>
      <div className={cx("px-4 pb-4", bodyClassName)}>{children}</div>
      {source && <OriginDot source={source} updatedAtISO={updatedAtISO} />}
    </section>
  )
}
