// src/design-system/components/Sidebar/index.tsx
// FIDC platform sidebar — Strata adoption (handoff v3, 2026-05-15).
//
// Hybrid hierarchy:
//   - flat top items ("Inicio")
//   - + active module's sections via lib/modules:: getActiveModule(pathname)
//   - + collapsible parents (sections with `children`) — expand-only, no nav.
//
// Binary collapse: when collapsed, returns null. The host (app shell) renders
// <SidebarTrigger /> in the topbar to bring it back. Cmd/Ctrl+B is registered
// globally by useSidebarCollapsed.
//
// Active sub-link visual: white card + ring + shadow + blue pill that replaces
// a segment of the gray tree-line. Parents with an active child get
// font-semibold (open or closed) — plus a small blue dot only when CLOSED.
// Fixes Tremor's original weakness.

"use client"

import * as React from "react"
import { usePathname, useRouter } from "next/navigation"
import { RiHome5Line, RiSearchLine } from "@remixicon/react"

import { cx, focusRing } from "@/lib/utils"
import { getActiveModule } from "@/lib/modules"
import { ModuleSwitcher } from "@/design-system/components/ModuleSwitcher"
import { useCommandPalette } from "@/design-system/components/CommandPalette"
import { logout } from "@/lib/api-client"
import { BrandCard } from "./BrandCard"
import { UserProfileDropdown, type UserCommand } from "./UserProfileDropdown"
import { NavFlatItem, NavParent } from "./nav-items"
import { useSidebarCollapsed } from "./useSidebarCollapsed"

export type BadgeCounts = Partial<Record<string, number>>

export interface AppSidebarProps {
  user?: { name: string; email?: string; imageUrl?: string }
  badgeCounts?: BadgeCounts
  /** Override the docs URL fired by the user dropdown. */
  docsUrl?: string
  className?: string
}

const HOME_SECTION = {
  name: "Inicio",
  href: "/",
  enabled: true,
  icon: RiHome5Line,
}

export function AppSidebar({
  user = { name: "Joao Silva", email: "joao@a7credit.com.br" },
  badgeCounts = {},
  docsUrl,
  className,
}: AppSidebarProps) {
  const pathname = usePathname()
  const router = useRouter()
  const cmdK = useCommandPalette()
  const { collapsed } = useSidebarCollapsed()
  const activeModule = React.useMemo(() => getActiveModule(pathname), [pathname])

  // Estado de expand/collapse por parent com children (CLAUDE.md §11.6).
  // Inicializa expandido quando algum filho ja casa com o pathname (deep
  // link / refresh). A partir dai e controle manual do usuario; o useEffect
  // abaixo so RE-expande quando o pathname muda (navegacao). Manual collapse
  // persiste entre cliques no chevron mesmo com filho ativo.
  const [expandedMap, setExpandedMap] = React.useState<Record<string, boolean>>(() => {
    const init: Record<string, boolean> = {}
    for (const section of activeModule.sections) {
      if (
        section.children &&
        section.children.some((c) => c.enabled && pathname.startsWith(c.href))
      ) {
        init[section.name] = true
      }
    }
    return init
  })

  React.useEffect(() => {
    setExpandedMap((prev) => {
      let next = prev
      for (const section of activeModule.sections) {
        if (
          section.children &&
          section.children.some((c) => c.enabled && pathname.startsWith(c.href))
        ) {
          if (!next[section.name]) {
            if (next === prev) next = { ...prev }
            next[section.name] = true
          }
        }
      }
      return next
    })
  }, [pathname, activeModule])

  const toggleExpanded = React.useCallback((name: string) => {
    setExpandedMap((prev) => ({ ...prev, [name]: !prev[name] }))
  }, [])

  const handleUserCommand = React.useCallback(
    (cmd: UserCommand) => {
      switch (cmd) {
        case "settings":
          router.push("/admin")
          break
        case "shortcuts":
          cmdK.setOpen(true)
          break
        case "docs":
          if (docsUrl) window.open(docsUrl, "_blank", "noopener,noreferrer")
          break
        case "signout":
          logout()
          router.replace("/login")
          break
      }
    },
    [router, cmdK, docsUrl],
  )

  if (collapsed) return null

  return (
    <aside
      aria-label="Navegacao principal"
      className={cx(
        "relative flex h-screen w-[256px] shrink-0 flex-col overflow-hidden",
        "bg-gray-50 dark:bg-gray-925",
        "border-r border-gray-200 dark:border-gray-800",
        className,
      )}
    >
      {/* Header: BrandCard + ModuleSwitcher */}
      <div className="shrink-0 border-b border-gray-200 px-3.5 pb-4 pt-3.5 dark:border-gray-800">
        <BrandCard className="mb-4" />
        <ModuleSwitcher />
      </div>

      {/* Command palette trigger */}
      <div className="shrink-0 px-2.5 pb-1 pt-2.5">
        <button
          type="button"
          onClick={() => cmdK.setOpen(true)}
          className={cx(
            "flex w-full items-center gap-2 rounded-md border px-2 py-1.5",
            "border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
            "hover:bg-gray-50 dark:hover:bg-gray-900",
            "transition-colors duration-100",
            focusRing,
          )}
        >
          <RiSearchLine className="size-3.5 shrink-0 text-gray-400" aria-hidden="true" />
          <span className="flex-1 truncate text-left text-xs text-gray-400 dark:text-gray-500">
            Buscar ou ir para...
          </span>
          <kbd className="rounded border border-gray-200 bg-gray-50 px-1 py-px text-[10px] font-mono text-gray-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
            ⌘K
          </kbd>
        </button>
      </div>

      {/* Nav: Inicio (flat) + active module sections */}
      <nav className="flex-1 overflow-y-auto px-2 py-2">
        <div className="mb-1 flex flex-col gap-0.5">
          <NavFlatItem section={HOME_SECTION} pathname={pathname} exact />
        </div>

        <div className="my-2 h-px bg-gray-200 dark:bg-gray-800" />

        {/* Module-level caption when no per-section groupLabel exists. */}
        {!activeModule.sections.some((s) => s.groupLabel) && (
          <p className="px-2 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600">
            {activeModule.name}
          </p>
        )}

        <div className="flex flex-col gap-0.5">
          {activeModule.sections.map((section, idx) => {
            const hasChildren = !!section.children && section.children.length > 0

            // Caption tipografico quando groupLabel muda em relacao ao item
            // anterior. Nao e grupo colapsavel — apenas separador visual
            // permitido por CLAUDE.md §11.6.
            const prevGroup = idx > 0 ? activeModule.sections[idx - 1].groupLabel : undefined
            const showGroupCaption = section.groupLabel && section.groupLabel !== prevGroup

            return (
              <React.Fragment key={section.name}>
                {showGroupCaption && (
                  <p
                    className={cx(
                      "px-2 pb-1 text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600",
                      idx === 0 ? "pt-1" : "pt-3",
                    )}
                  >
                    {section.groupLabel}
                  </p>
                )}
                {hasChildren ? (
                  <NavParent
                    section={section}
                    pathname={pathname}
                    expanded={!!expandedMap[section.name]}
                    onToggle={() => toggleExpanded(section.name)}
                    badgeCounts={badgeCounts as Record<string, number>}
                    defaultIcon={activeModule.icon}
                  />
                ) : (
                  <NavFlatItem
                    section={{ ...section, icon: section.icon ?? activeModule.icon }}
                    pathname={pathname}
                    badgeCount={badgeCounts[section.href] ?? 0}
                  />
                )}
              </React.Fragment>
            )
          })}
        </div>
      </nav>

      {/* Footer: user profile dropdown */}
      <div className="shrink-0 border-t border-gray-200 px-2 py-2 dark:border-gray-800">
        <UserProfileDropdown user={user} onCommand={handleUserCommand} />
      </div>
    </aside>
  )
}

export { useSidebarCollapsed, setSidebarCollapsed, toggleSidebarCollapsed } from "./useSidebarCollapsed"
export { SidebarTrigger, type SidebarTriggerProps } from "./SidebarTrigger"
export { BrandCard, type BrandCardProps } from "./BrandCard"
export { UserProfileDropdown, type UserProfileDropdownProps, type UserCommand } from "./UserProfileDropdown"
