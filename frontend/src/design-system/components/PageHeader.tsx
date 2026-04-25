import * as React from "react"
import { RiArrowRightSLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { InfoTooltip } from "@/design-system/components/InfoTooltip"

//
// Tipos
//

export type Breadcrumb = {
  label: string
  href?: string
}

type PageHeaderProps = {
  title: string
  /**
   * Texto explicativo compacto. Renderizado via <InfoTooltip /> (icone "i"
   * ao lado do titulo). Preserva explicabilidade sem consumir altura vertical.
   * Padrao novo (Tremor-style).
   */
  info?: string
  /**
   * Subtitulo visivel abaixo do titulo. Legado — mantido por compatibilidade
   * com paginas de template. Para modulos novos prefira `info`.
   */
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
      className="flex items-center gap-1 text-xs text-gray-500 dark:text-gray-400"
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
                className="size-3.5 shrink-0 text-gray-400 dark:text-gray-600"
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
// Convergencia visual ao Tremor Template Planner:
// - H1 em text-lg (antes text-xl/2xl)
// - Subtitulo virou tooltip (InfoTooltip) — antes era <p> explicito
// - Sem border-bottom separador (antes pb-6 + border-b)
//

export function PageHeader({
  title,
  info,
  subtitle,
  breadcrumbs,
  actions,
  className,
}: PageHeaderProps) {
  return (
    <header
      className={cx(
        "flex flex-col gap-2",
        "sm:flex-row sm:items-center sm:justify-between",
        className,
      )}
    >
      <div className="flex flex-col gap-1">
        {breadcrumbs && breadcrumbs.length > 0 && (
          <Breadcrumbs items={breadcrumbs} />
        )}
        <div className="flex items-center gap-2">
          <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-50">
            {title}
          </h1>
          {info && <InfoTooltip content={info} />}
        </div>
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
