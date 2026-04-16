"use client"

import { siteConfig } from "@/app/siteConfig"
import { RiArrowRightSLine } from "@remixicon/react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import * as React from "react"

type Segment = {
  name: string
  href: string
  isCurrent: boolean
}

// Rotulos amigaveis em pt-BR para segmentos de URL conhecidos.
// Rotas novas caem no fallback (capitaliza o slug).
const LABELS: Record<string, string> = {
  "": "Inicio",
}

function humanize(segment: string) {
  if (LABELS[segment] !== undefined) return LABELS[segment]
  const decoded = decodeURIComponent(segment).replace(/-/g, " ")
  return decoded.charAt(0).toUpperCase() + decoded.slice(1)
}

/**
 * Breadcrumbs auto-gerados a partir da URL atual, exibidos no header
 * do shell (app) layout. Nao confundir com o `Breadcrumbs` interno do
 * `PageHeader`, que e manual e por pagina.
 */
export function HeaderBreadcrumbs() {
  const pathname = usePathname() ?? "/"
  const parts = pathname.split("/").filter(Boolean)

  const segments: Segment[] = [
    {
      name: humanize(""),
      href: siteConfig.baseLinks.home,
      isCurrent: parts.length === 0,
    },
    ...parts.map((part, idx) => ({
      name: humanize(part),
      href: "/" + parts.slice(0, idx + 1).join("/"),
      isCurrent: idx === parts.length - 1,
    })),
  ]

  return (
    <nav aria-label="Breadcrumb" className="ml-2">
      <ol role="list" className="flex items-center space-x-3 text-sm">
        {segments.map((segment, idx) => (
          <React.Fragment key={segment.href}>
            {idx > 0 && (
              <RiArrowRightSLine
                className="size-4 shrink-0 text-gray-600 dark:text-gray-400"
                aria-hidden="true"
              />
            )}
            <li className="flex">
              {segment.isCurrent ? (
                <span
                  aria-current="page"
                  className="text-gray-900 dark:text-gray-50"
                >
                  {segment.name}
                </span>
              ) : (
                <Link
                  href={segment.href}
                  className="text-gray-500 transition hover:text-gray-700 dark:text-gray-400 hover:dark:text-gray-300"
                >
                  {segment.name}
                </Link>
              )}
            </li>
          </React.Fragment>
        ))}
      </ol>
    </nav>
  )
}
