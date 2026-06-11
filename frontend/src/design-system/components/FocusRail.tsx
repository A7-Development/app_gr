// src/design-system/components/FocusRail.tsx
//
// Rail de 56px do modo foco (handoff Conceito D, frame D0).
// Dentro de uma análise, a AppSidebar canônica colapsa para este rail:
// logo 30×30 no topo, ícones 18px com tooltip, item ativo = fundo
// blue-500/10 + pill azul 2×18 à esquerda, avatar 30px no rodapé.
//
// Clicar no ícone ativo (ou Esc, ou o link "← Fila" da sidebar de etapas)
// sai do modo foco. Clicar em outro item navega normalmente.

"use client"

import * as React from "react"
import Link from "next/link"
import type { RemixiconComponentType } from "@remixicon/react"

import { StrataIcon } from "@/design-system/components/StrataIcon"
import { cx } from "@/lib/utils"

export type FocusRailItem = {
  href: string
  label: string
  icon: RemixiconComponentType
  active?: boolean
  disabled?: boolean
}

export type FocusRailProps = {
  items: FocusRailItem[]
  /** Iniciais do usuário no avatar do rodapé (ex.: "MC"). */
  userInitials?: string
  userName?: string
  className?: string
}

export function FocusRail({ items, userInitials, userName, className }: FocusRailProps) {
  return (
    <aside
      aria-label="Navegação (modo foco)"
      className={cx(
        "flex h-screen w-14 shrink-0 flex-col items-center gap-1.5 border-r border-gray-200 bg-gray-50 py-3 dark:border-gray-800 dark:bg-gray-925",
        className,
      )}
    >
      <Link
        href="/"
        title="Início"
        className="mb-2.5 flex size-[30px] items-center justify-center rounded-md bg-white shadow-xs dark:bg-gray-900"
      >
        <StrataIcon className="size-5" />
      </Link>

      {items.map((item) => {
        const Icon = item.icon
        if (item.disabled) {
          return (
            <span
              key={item.href}
              title={item.label}
              className="flex size-9 items-center justify-center rounded-md opacity-40"
            >
              <Icon className="size-[18px] text-gray-500 dark:text-gray-400" aria-hidden />
            </span>
          )
        }
        return (
          <Link
            key={item.href}
            href={item.href}
            title={item.label}
            aria-label={item.label}
            aria-current={item.active ? "page" : undefined}
            className={cx(
              "relative flex size-9 items-center justify-center rounded-md transition-colors duration-100",
              item.active
                ? "bg-blue-500/10"
                : "hover:bg-gray-100 dark:hover:bg-gray-900",
            )}
          >
            {item.active && (
              <span
                className="absolute -left-2.5 top-1/2 h-[18px] w-0.5 -translate-y-1/2 rounded-full bg-blue-500"
                aria-hidden
              />
            )}
            <Icon
              className={cx(
                "size-[18px]",
                item.active
                  ? "text-blue-600 dark:text-blue-400"
                  : "text-gray-500 dark:text-gray-400",
              )}
              aria-hidden
            />
          </Link>
        )
      })}

      <span
        title={userName}
        className="mt-auto flex size-[30px] items-center justify-center rounded-full bg-gray-800 text-[10px] font-semibold text-white dark:bg-gray-700"
      >
        {userInitials ?? "—"}
      </span>
    </aside>
  )
}
