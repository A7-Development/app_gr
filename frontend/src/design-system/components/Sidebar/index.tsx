// src/design-system/components/Sidebar/index.tsx
// FIDC platform sidebar — Strata adoption.
// Wires to our existing routing: usePathname + getActiveModule + lib/modules.
// Adds: collapsed 56px mode, Radix Tooltip on collapsed items, Radix Avatar in footer.

"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname } from "next/navigation"
import * as TooltipPrimitive from "@radix-ui/react-tooltip"
import * as AvatarPrimitive from "@radix-ui/react-avatar"
import {
  RiHome5Line,
  RiSettings3Line,
  RiLayoutLeftLine,
  RiLayoutRightLine,
} from "@remixicon/react"
import { cx, focusRing } from "@/lib/utils"
import { getActiveModule, MODULE_AVATAR_COLORS } from "@/lib/modules"
import { Button } from "@/components/tremor/Button"
import { ApprovalQueueBadge } from "@/design-system/components/ApprovalQueueBadge"
import { ModuleSwitcher } from "@/design-system/components/ModuleSwitcher"
import { Logo } from "@/design-system/components/Logo"
import { useSidebarCollapsed } from "./useSidebarCollapsed"

export type BadgeCounts = Partial<Record<string, number>>

function UserAvatar({
  name,
  imageUrl,
  size = "sm",
}: {
  name: string
  imageUrl?: string
  size?: "sm" | "md"
}) {
  const initials = name
    .split(" ")
    .slice(0, 2)
    .map((w) => w[0])
    .join("")
    .toUpperCase()

  const dim = size === "sm" ? "size-7" : "size-9"

  return (
    <AvatarPrimitive.Root className={cx("relative flex shrink-0 overflow-hidden rounded-full", dim)}>
      {imageUrl && (
        <AvatarPrimitive.Image
          src={imageUrl}
          alt={name}
          className="aspect-square size-full object-cover"
        />
      )}
      <AvatarPrimitive.Fallback
        className={cx(
          "flex size-full items-center justify-center rounded-full",
          "bg-blue-500 text-white",
          size === "sm" ? "text-xs font-semibold" : "text-sm font-semibold",
        )}
      >
        {initials}
      </AvatarPrimitive.Fallback>
    </AvatarPrimitive.Root>
  )
}

function NavTooltip({
  label,
  shortcut,
  children,
}: {
  label: string
  shortcut?: string
  children: React.ReactNode
}) {
  return (
    <TooltipPrimitive.Provider delayDuration={300}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            side="right"
            sideOffset={8}
            className={cx(
              "z-50 flex items-center gap-2 rounded px-2.5 py-1.5",
              "bg-gray-900 dark:bg-gray-800 text-white",
              "text-xs font-medium shadow-lg",
              "animate-slide-right-and-fade",
            )}
          >
            {label}
            {shortcut && (
              <span className="font-mono text-[10px] text-gray-400">{shortcut}</span>
            )}
            <TooltipPrimitive.Arrow className="fill-gray-900 dark:fill-gray-800" />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  )
}

function NavLinkExpanded({
  label,
  href,
  icon: Icon,
  isActive,
  badgeCount = 0,
  disabled = false,
  trailing,
}: {
  label:       string
  href:        string
  icon:        React.ElementType
  isActive:    boolean
  badgeCount?: number
  disabled?:   boolean
  trailing?:   React.ReactNode
}) {
  const className = cx(
    "relative flex h-8 w-full items-center gap-2.5 rounded px-2 text-sm",
    "transition-colors duration-100",
    isActive && "border-l-2 border-l-blue-500 pl-[6px]",
    !isActive && "border-l-2 border-l-transparent",
    isActive
      ? "bg-blue-500/10 text-blue-600 dark:text-blue-400"
      : disabled
      ? "pointer-events-none text-gray-400 dark:text-gray-600"
      : "text-gray-700 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-900 hover:text-gray-900 dark:hover:text-gray-50",
    focusRing,
  )

  const content = (
    <>
      <Icon className="size-[18px] shrink-0" aria-hidden="true" />
      <span className="flex-1 truncate">{label}</span>
      {trailing}
      <ApprovalQueueBadge count={badgeCount} />
    </>
  )

  if (disabled) {
    return (
      <span className={className} aria-disabled="true">
        {content}
      </span>
    )
  }

  return (
    <Link href={href} aria-current={isActive ? "page" : undefined} className={className}>
      {content}
    </Link>
  )
}

function NavLinkCollapsed({
  label,
  href,
  icon: Icon,
  isActive,
  badgeCount = 0,
  disabled = false,
}: {
  label:       string
  href:        string
  icon:        React.ElementType
  isActive:    boolean
  badgeCount?: number
  disabled?:   boolean
}) {
  const className = cx(
    "relative flex size-9 items-center justify-center rounded",
    "transition-colors duration-100",
    isActive
      ? "bg-blue-500/10 text-blue-600 dark:text-blue-400"
      : disabled
      ? "pointer-events-none text-gray-300 dark:text-gray-700"
      : "text-gray-500 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-900 hover:text-gray-900 dark:hover:text-gray-50",
    focusRing,
  )

  const inner = (
    <>
      <Icon className="size-[18px] shrink-0" aria-hidden="true" />
      {badgeCount > 0 && (
        <span aria-hidden="true" className="absolute right-0.5 top-0.5 size-2 rounded-full bg-red-500" />
      )}
    </>
  )

  return (
    <NavTooltip label={label}>
      {disabled ? (
        <span className={className} aria-disabled="true">
          {inner}
        </span>
      ) : (
        <Link href={href} aria-current={isActive ? "page" : undefined} className={className}>
          {inner}
        </Link>
      )}
    </NavTooltip>
  )
}

export interface AppSidebarProps {
  user?: { name: string; email?: string; imageUrl?: string }
  badgeCounts?: BadgeCounts
  className?: string
}

export function AppSidebar({
  user = { name: "João Silva", email: "joao@a7credit.com.br" },
  badgeCounts = {},
  className,
}: AppSidebarProps) {
  const pathname = usePathname()
  const activeModule = React.useMemo(() => getActiveModule(pathname), [pathname])
  const { collapsed, toggle } = useSidebarCollapsed()

  const w = collapsed ? "w-[56px]" : "w-[240px]"

  return (
    <aside
      className={cx(
        "relative flex min-h-svh flex-col shrink-0 overflow-hidden",
        "bg-gray-50 dark:bg-gray-925",
        "border-r border-gray-200 dark:border-gray-800",
        "transition-[width] duration-150 ease-in-out",
        w,
        className,
      )}
    >
      <div className={cx(
        "shrink-0 border-b border-gray-200 dark:border-gray-800",
        collapsed ? "px-2 py-3" : "px-3 py-3",
      )}>
        {!collapsed ? (
          <>
            <div className="mb-3 flex items-center gap-2.5">
              <Logo className="size-8" />
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-gray-900 dark:text-gray-50">A7 Credit</p>
                <p className="text-[11px] text-gray-500 dark:text-gray-400">Plataforma GR</p>
              </div>
            </div>
            <ModuleSwitcher />
          </>
        ) : (
          <NavTooltip label={activeModule.name}>
            <Link
              href={activeModule.basePath}
              className={cx(
                "flex size-9 items-center justify-center rounded mx-auto",
                "hover:bg-gray-100 dark:hover:bg-gray-900 transition-colors duration-100",
                focusRing,
              )}
            >
              <span
                className={cx(
                  "flex size-6 items-center justify-center rounded-sm text-[10px] font-bold text-white",
                  MODULE_AVATAR_COLORS[activeModule.color],
                )}
              >
                {activeModule.initials}
              </span>
            </Link>
          </NavTooltip>
        )}
      </div>

      <nav
        aria-label="Navegação principal"
        className={cx(
          "flex-1 overflow-y-auto py-2",
          collapsed ? "px-1.5" : "px-2",
        )}
      >
        <div className={cx("mb-1 flex flex-col", collapsed ? "items-center gap-0.5" : "gap-0.5")}>
          {collapsed ? (
            <NavLinkCollapsed
              label="Início"
              href="/"
              icon={RiHome5Line}
              isActive={pathname === "/"}
            />
          ) : (
            <NavLinkExpanded
              label="Início"
              href="/"
              icon={RiHome5Line}
              isActive={pathname === "/"}
            />
          )}
        </div>

        <div className="my-2 h-px bg-gray-200 dark:bg-gray-800" />

        {!collapsed && !activeModule.sections.some((s) => s.groupLabel) && (
          <p className="px-2 pb-1 pt-1 text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600">
            {activeModule.name}
          </p>
        )}
        <div className={cx("flex flex-col", collapsed ? "items-center gap-0.5" : "gap-0.5")}>
          {activeModule.sections.map((section, idx) => {
            const isActive =
              section.enabled &&
              section.href !== "#" &&
              pathname.startsWith(section.href)
            const Icon = section.icon ?? activeModule.icon

            // Renderizar caption tipografico quando groupLabel muda em
            // relacao ao item anterior. Nao e grupo colapsavel — apenas
            // separador visual permitido por CLAUDE.md §11.6.
            const prevGroup = idx > 0 ? activeModule.sections[idx - 1].groupLabel : undefined
            const showGroupCaption =
              !collapsed && section.groupLabel && section.groupLabel !== prevGroup
            const showCollapsedDivider = collapsed && idx > 0 &&
              section.groupLabel && section.groupLabel !== prevGroup

            return (
              <React.Fragment key={section.name}>
                {showGroupCaption && (
                  <p className={cx(
                    "px-2 pb-1 text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600",
                    idx === 0 ? "pt-1" : "pt-3",
                  )}>
                    {section.groupLabel}
                  </p>
                )}
                {showCollapsedDivider && (
                  <div className="my-1 h-px w-6 bg-gray-200 dark:bg-gray-800" aria-hidden="true" />
                )}
                {collapsed ? (
                  <NavLinkCollapsed
                    label={section.name}
                    href={section.enabled ? section.href : "#"}
                    icon={Icon}
                    isActive={isActive}
                    disabled={!section.enabled}
                    badgeCount={badgeCounts[section.href] ?? 0}
                  />
                ) : (
                  <NavLinkExpanded
                    label={section.name}
                    href={section.enabled ? section.href : "#"}
                    icon={Icon}
                    isActive={isActive}
                    disabled={!section.enabled}
                    badgeCount={badgeCounts[section.href] ?? 0}
                    trailing={
                      !section.enabled ? (
                        <span className="rounded bg-gray-200 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                          breve
                        </span>
                      ) : undefined
                    }
                  />
                )}
              </React.Fragment>
            )
          })}
        </div>
      </nav>

      <div className={cx(
        "shrink-0 border-t border-gray-200 dark:border-gray-800",
        collapsed ? "flex justify-center px-2 py-2.5" : "flex items-center gap-2 px-3 py-2.5",
      )}>
        {collapsed ? (
          <NavTooltip label={user.name}>
            <Button variant="ghost" className="size-7 rounded-full p-0">
              <UserAvatar name={user.name} imageUrl={user.imageUrl} />
            </Button>
          </NavTooltip>
        ) : (
          <>
            <UserAvatar name={user.name} imageUrl={user.imageUrl} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-medium text-gray-900 dark:text-gray-50">{user.name}</p>
              {user.email && (
                <p className="truncate text-[11px] text-gray-500 dark:text-gray-400">{user.email}</p>
              )}
            </div>
            <Button
              variant="ghost"
              aria-label="Configurações"
              className="size-7 shrink-0 p-0 text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
            >
              <RiSettings3Line className="size-4" aria-hidden="true" />
            </Button>
          </>
        )}
      </div>

      {/* <button> cru intencional: este e um affordance posicional (chip de toggle anexado a borda da sidebar, half-translate na borda) com geometria size-5 + rounded-full + border, fora do paradigma do Button do Tremor. Usar Button aqui significa lutar contra base styles dele (px-3 py-2, rounded, shadow-xs). Excecao documentada (CLAUDE.md §6). */}
      <button
        type="button"
        onClick={toggle}
        aria-label={collapsed ? "Expandir sidebar" : "Recolher sidebar"}
        className={cx(
          "absolute bottom-14 right-0 translate-x-1/2",
          "flex size-5 items-center justify-center rounded-full",
          "border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
          "text-gray-400 hover:text-gray-700 dark:hover:text-gray-200",
          "shadow-sm transition-colors duration-100",
          focusRing,
        )}
      >
        {collapsed
          ? <RiLayoutRightLine className="size-2.5" aria-hidden="true" />
          : <RiLayoutLeftLine className="size-2.5" aria-hidden="true" />}
      </button>
    </aside>
  )
}

export { useSidebarCollapsed }
