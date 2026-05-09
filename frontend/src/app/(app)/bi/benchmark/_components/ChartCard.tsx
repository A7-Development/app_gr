import * as React from "react"

import { cx } from "@/lib/utils"
import { InfoTooltip } from "@/design-system/components/InfoTooltip"

//
// Wrapper leve de titulo + chart — espelha exatamente o ChartCard interno
// de `/bi/operacoes` para manter consistencia visual (CLAUDE.md §1).
//
export function ChartCard({
  title,
  info,
  children,
  className,
  actions,
}: {
  title: string
  info?: string
  children: React.ReactNode
  className?: string
  actions?: React.ReactNode
}) {
  return (
    <div
      className={cx(
        "flex flex-col gap-3 rounded border border-gray-200 p-4 dark:border-gray-800",
        className,
      )}
    >
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
            {title}
          </h3>
          {info && <InfoTooltip content={info} />}
        </div>
        {actions}
      </div>
      {children}
    </div>
  )
}
