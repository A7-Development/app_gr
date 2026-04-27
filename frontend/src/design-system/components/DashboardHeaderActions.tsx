// src/design-system/components/DashboardHeaderActions.tsx
//
// DashboardHeaderActions -- conjunto canonico de acoes do header de
// dashboards autenticados, alinhado com handoff bi-padrao 2026-04-26
// (page-padrao-bi/Components.jsx::AppHeader).
//
// Ordem fixa: [DarkToggle, Compartilhar, Exportar, Mais, IA].
// DarkToggle, Mais e IA sao SEMPRE presentes. Share/Export sao omitidos
// quando o callback nao e passado.
//
// "Mais" sempre tem ao menos "Copiar link" como item default. Itens extras
// (Imprimir, Duplicar dia, etc.) sao adicionados via `more={[...]}` e
// aparecem APOS o "Copiar link". Para suprimir o default e usar so seu
// proprio set, passe `moreReplaceDefault: true`.
//
// Toda pagina derivada de DashboardBiPadrao DEVE usar este composite no
// slot `actions` do PageHeader. Botoes soltos sao regressao (CLAUDE.md §7).
//

"use client"

import * as React from "react"
import { useTheme } from "next-themes"
import {
  RiDownloadLine,
  RiLinkM,
  RiMoonLine,
  RiMore2Fill,
  RiShareLine,
  RiSunLine,
} from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Button } from "@/components/tremor/Button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/tremor/DropdownMenu"
import { AIToggleButton } from "@/design-system/components/AIPanel"

export type DashboardHeaderMoreItem = {
  label:    string
  icon?:    React.ReactNode
  onClick:  () => void
  disabled?: boolean
}

export type DashboardHeaderActionsProps = {
  ai:        { open: boolean; onToggle: () => void }
  onShare?:  () => void
  onExport?: () => void
  /** Itens adicionais do menu "Mais". Adicionados APOS o "Copiar link" default. */
  more?:     DashboardHeaderMoreItem[]
  /** Substitui o item default "Copiar link" pelos itens passados em `more`. */
  moreReplaceDefault?: boolean
  className?: string
}

function defaultCopyLinkItem(): DashboardHeaderMoreItem {
  return {
    label: "Copiar link",
    icon:  <RiLinkM className="size-4 shrink-0" aria-hidden="true" />,
    onClick: () => {
      void navigator.clipboard?.writeText(window.location.href)
    },
  }
}

// ─── Estilo canonico do botao de header (handoff bi-padrao::HeaderBtn) ────
//
// Override sobre Button variant="secondary" para alinhar com o handoff:
//   padding: 5px 10px (vs Tremor px-3 py-2)
//   color  : muted gray (vs Tremor full black)
//   font   : 13px (vs Tremor text-sm = 14px)
//   radius : 4px (vs Tremor rounded = 6px)
//   shadow : none (vs Tremor shadow-xs)
// twMerge dentro do tv() do Button dedupe os conflitos com a base.
//
const HEADER_BTN_CLASS = cx(
  "gap-1 rounded-[4px] px-2.5 py-1 text-[13px] font-medium",
  "text-gray-600 dark:text-gray-400",
  "border-gray-200 dark:border-gray-800",
  "bg-white hover:bg-gray-50 dark:bg-gray-950 dark:hover:bg-gray-900/60",
  "shadow-none",
)

const HEADER_BTN_ICON_ONLY = cx(
  "rounded-[4px] p-1.5",
  "text-gray-600 dark:text-gray-400",
  "border-gray-200 dark:border-gray-800",
  "bg-white hover:bg-gray-50 dark:bg-gray-950 dark:hover:bg-gray-900/60",
  "shadow-none",
)

function DarkToggle() {
  const { resolvedTheme, setTheme } = useTheme()
  const [mounted, setMounted] = React.useState(false)
  React.useEffect(() => setMounted(true), [])

  const isDark = mounted && resolvedTheme === "dark"
  const Icon   = isDark ? RiSunLine : RiMoonLine
  const label  = isDark ? "Modo claro" : "Modo escuro"

  return (
    <Button
      variant="secondary"
      onClick={() => setTheme(isDark ? "light" : "dark")}
      title={label}
      aria-label={label}
      className={HEADER_BTN_ICON_ONLY}
    >
      <Icon className="size-4 shrink-0" aria-hidden="true" />
    </Button>
  )
}

function MoreMenu({ items }: { items: DashboardHeaderMoreItem[] }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="secondary"
          title="Mais acoes"
          aria-label="Mais acoes"
          className={HEADER_BTN_ICON_ONLY}
        >
          <RiMore2Fill className="size-4 shrink-0" aria-hidden="true" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" sideOffset={4}>
        {items.map((it, i) => (
          <DropdownMenuItem
            key={`${it.label}-${i}`}
            onClick={it.onClick}
            disabled={it.disabled}
          >
            {it.icon && <span className="mr-2 inline-flex shrink-0">{it.icon}</span>}
            {it.label}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

export function DashboardHeaderActions({
  ai,
  onShare,
  onExport,
  more,
  moreReplaceDefault = false,
  className,
}: DashboardHeaderActionsProps) {
  const moreItems = React.useMemo<DashboardHeaderMoreItem[]>(() => {
    const extra = more ?? []
    if (moreReplaceDefault) return extra
    return [defaultCopyLinkItem(), ...extra]
  }, [more, moreReplaceDefault])

  return (
    <div className={cx("flex flex-wrap items-center gap-2", className)}>
      <DarkToggle />

      {onShare && (
        <Button variant="secondary" onClick={onShare} className={HEADER_BTN_CLASS}>
          <RiShareLine className="size-3.5 shrink-0" aria-hidden="true" />
          Compartilhar
        </Button>
      )}

      {onExport && (
        <Button variant="secondary" onClick={onExport} className={HEADER_BTN_CLASS}>
          <RiDownloadLine className="size-3.5 shrink-0" aria-hidden="true" />
          Exportar
        </Button>
      )}

      {moreItems.length > 0 && <MoreMenu items={moreItems} />}

      <AIToggleButton open={ai.open} onClick={ai.onToggle} />
    </div>
  )
}
