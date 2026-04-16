import * as React from "react"
import { RiArrowRightSLine } from "@remixicon/react"

import { cx } from "@/lib/utils"

//
// Tipos
//

export type Breadcrumb = {
  label: string
  href?: string
}

type PageHeaderProps = {
  title: string
  subtitle?: string
  breadcrumbs?: Breadcrumb[]
  /** Acoes exibidas a direita do titulo (botoes, dropdowns). */
  actions?: React.ReactNode
  className?: string
}

//
// Breadcrumb
//

function Breadcrumbs({ items }: { items: Breadcrumb[] }) {
  return (
    <nav
      aria-label="Navegacao estrutural"
      className="flex items-center gap-1 text-sm text-gray-500 dark:text-gray-400"
    >
      {items.map((item, index) => {
        const isLast = index === items.length - 1
        return (
          <React.Fragment key={`${item.label}-${index}`}>
            {item.href && !isLast ? (
              <a
                href={item.href}
                className="transition hover:text-gray-900 dark:hover:text-gray-50"
              >
                {item.label}
              </a>
            ) : (
              <span
                className={cx(
                  isLast && "font-medium text-gray-900 dark:text-gray-50",
                )}
                aria-current={isLast ? "page" : undefined}
              >
                {item.label}
              </span>
            )}
            {!isLast && (
              <RiArrowRightSLine
                aria-hidden="true"
                className="size-4 shrink-0 text-gray-400 dark:text-gray-600"
              />
            )}
          </React.Fragment>
        )
      })}
    </nav>
  )
}

//
// PageHeader
//

export function PageHeader({
  title,
  subtitle,
  breadcrumbs,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <header
      className={cx(
        "flex flex-col gap-4 border-b border-gray-200 pb-6 dark:border-gray-800",
        "sm:flex-row sm:items-end sm:justify-between",
        className,
      )}
    >
      <div className="flex flex-col gap-2">
        {breadcrumbs && breadcrumbs.length > 0 && (
          <Breadcrumbs items={breadcrumbs} />
        )}
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-50 sm:text-2xl">
          {title}
        </h1>
        {subtitle && (
          <p className="text-sm text-gray-500 dark:text-gray-400">{subtitle}</p>
        )}
      </div>

      {actions && (
        <div className="flex flex-wrap items-center gap-2 sm:justify-end">
          {actions}
        </div>
      )}
    </header>
  )
}
