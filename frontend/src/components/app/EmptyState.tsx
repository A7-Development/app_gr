import * as React from "react"
import type { RemixiconComponentType } from "@remixicon/react"

import { cx } from "@/lib/utils"

type EmptyStateProps = {
  /** Icone Remix (componente), ex.: RiInboxLine. */
  icon: RemixiconComponentType
  title: string
  description?: string
  /** Slot para acao primaria (geralmente um Button do Tremor). */
  action?: React.ReactNode
  className?: string
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  action,
  className,
}: EmptyStateProps) {
  return (
    <div
      role="status"
      className={cx(
        "flex flex-col items-center justify-center gap-3 rounded-lg border border-dashed border-gray-200 bg-white px-6 py-12 text-center",
        "dark:border-gray-800 dark:bg-gray-950",
        className,
      )}
    >
      <div className="flex size-12 items-center justify-center rounded-full bg-gray-100 dark:bg-gray-900">
        <Icon
          aria-hidden="true"
          className="size-6 text-gray-500 dark:text-gray-400"
        />
      </div>
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
          {title}
        </h2>
        {description && (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {description}
          </p>
        )}
      </div>
      {action && <div className="mt-2">{action}</div>}
    </div>
  )
}
