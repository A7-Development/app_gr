import * as React from "react"
import { RiErrorWarningLine } from "@remixicon/react"

import { cx } from "@/lib/utils"

type ErrorStateProps = {
  title?: string
  description?: string
  /** Slot para acao (ex.: botao de tentar novamente). */
  action?: React.ReactNode
  className?: string
}

export function ErrorState({
  title = "Ocorreu um erro",
  description = "Nao foi possivel carregar as informacoes. Tente novamente em alguns instantes.",
  action,
  className,
}: ErrorStateProps) {
  return (
    <div
      role="alert"
      className={cx(
        "flex flex-col items-center justify-center gap-3 rounded-lg border border-red-200 bg-red-50 px-6 py-12 text-center",
        "dark:border-red-900/40 dark:bg-red-950/30",
        className,
      )}
    >
      <div className="flex size-12 items-center justify-center rounded-full bg-red-100 dark:bg-red-900/40">
        <RiErrorWarningLine
          aria-hidden="true"
          className="size-6 text-red-600 dark:text-red-400"
        />
      </div>
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
          {title}
        </h2>
        <p className="text-sm text-gray-600 dark:text-gray-400">
          {description}
        </p>
      </div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}
