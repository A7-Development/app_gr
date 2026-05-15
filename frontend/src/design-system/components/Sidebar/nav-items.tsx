// src/design-system/components/Sidebar/nav-items.tsx
// Nav primitives for the v3 hybrid sidebar:
//
//   NavFlatItem  — top-level flat link (icon + label + optional badge).
//                  Active state: blue pill on the left + bg-blue-500/10 + text-blue-600.
//
//   NavParent    — collapsible group header (icon + label + chevron).
//                  When collapsed AND has-active-child: font-semibold + blue dot.
//                  Resolves the Tremor weakness where a closed group with an
//                  active child showed zero feedback.
//
//   NavSubLink   — sub-item under a NavParent.
//                  Active state: WHITE CARD + ring-1 + shadow-xs + text-blue-600,
//                  PLUS a blue pill that REPLACES a segment of the gray tree-line.
//
//   NavTreeLine  — 1px vertical gray line that runs through expanded children.
//
// Adapted from the handoff to consume our `ModuleSection` shape (router-driven,
// not callback-driven). All links render as Next <Link> so prefetch and active
// state work via usePathname.

"use client"

import * as React from "react"
import Link from "next/link"
import { RiArrowDownSLine } from "@remixicon/react"
import { cx, focusRing } from "@/lib/utils"
import { ApprovalQueueBadge } from "@/design-system/components/ApprovalQueueBadge"
import type { ModuleSection } from "@/lib/modules"

// ─── Flat top-level item ───────────────────────────────────────────────────

export function NavFlatItem({
  section,
  pathname,
  badgeCount = 0,
  exact = false,
}: {
  section: ModuleSection
  pathname: string
  badgeCount?: number
  /** When true, isActive uses strict equality; otherwise uses startsWith. */
  exact?: boolean
}) {
  const Icon = section.icon
  const href = section.enabled ? section.href : "#"
  const isActive = section.enabled
    ? exact
      ? pathname === section.href
      : pathname === section.href || pathname.startsWith(`${section.href}/`)
    : false
  const disabled = !section.enabled

  const className = cx(
    "relative flex w-full items-center gap-2.5 rounded-md px-2 py-1.5",
    "text-[13px] transition-colors duration-100",
    isActive
      ? "bg-blue-500/10 text-blue-600 dark:text-blue-400 font-medium"
      : disabled
      ? "pointer-events-none text-gray-400 dark:text-gray-600"
      : "text-gray-700 dark:text-gray-400 hover:bg-gray-200/50 hover:text-gray-900 dark:hover:bg-gray-900 dark:hover:text-gray-50",
    focusRing,
  )

  const content = (
    <>
      {isActive && (
        <span
          aria-hidden="true"
          className="absolute left-0 top-1/2 h-[18px] w-[2px] -translate-y-1/2 rounded-r bg-blue-500"
        />
      )}
      {Icon && (
        <Icon
          className={cx(
            "size-[18px] shrink-0",
            isActive ? "text-blue-600 dark:text-blue-400" : "text-gray-500 dark:text-gray-400",
          )}
          aria-hidden="true"
        />
      )}
      <span className="flex-1 truncate">{section.name}</span>
      {disabled ? (
        <span className="rounded bg-gray-200 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:bg-gray-800 dark:text-gray-400">
          breve
        </span>
      ) : (
        <ApprovalQueueBadge count={badgeCount} />
      )}
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

// ─── Collapsible parent + tree-line + sub-link ─────────────────────────────

export function NavParent({
  section,
  pathname,
  expanded,
  onToggle,
  badgeCounts,
  defaultIcon,
}: {
  section: ModuleSection
  pathname: string
  expanded: boolean
  onToggle: () => void
  badgeCounts: Record<string, number>
  /** Fallback icon when the section omits one. */
  defaultIcon: React.ElementType
}) {
  const Icon = section.icon ?? defaultIcon
  const children = section.children ?? []
  const hasActiveChild = children.some(
    (c) => c.enabled && (pathname === c.href || pathname.startsWith(`${c.href}/`)),
  )
  const dimmed = !expanded && hasActiveChild

  return (
    <div>
      {/* <button> cru intencional: trigger de expand/collapse com geometria identica ao NavFlatItem (h:py-1.5, rounded-md, gap-2.5). Usar Button do Tremor implicaria estilos de CTA. Excecao §6. */}
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={`sidebar-children-${section.name}`}
        className={cx(
          "flex w-full items-center gap-2.5 rounded-md px-2 py-1.5",
          "text-[13px] transition-colors duration-100",
          "hover:bg-gray-200/50 dark:hover:bg-gray-900",
          dimmed
            ? "font-semibold text-gray-900 dark:text-gray-50"
            : "text-gray-700 dark:text-gray-400",
          focusRing,
        )}
      >
        <Icon
          className={cx(
            "size-[18px] shrink-0",
            dimmed ? "text-gray-700 dark:text-gray-300" : "text-gray-500 dark:text-gray-400",
          )}
          aria-hidden="true"
        />
        <span className="flex-1 truncate text-left">{section.name}</span>
        {dimmed && (
          <span
            aria-hidden="true"
            className="size-1.5 shrink-0 rounded-full bg-blue-500"
          />
        )}
        <RiArrowDownSLine
          className={cx(
            "size-4 shrink-0 text-gray-400 transition-transform duration-150 ease-in-out",
            expanded ? "rotate-0" : "-rotate-90",
          )}
          aria-hidden="true"
        />
      </button>
      {expanded && (
        <div
          id={`sidebar-children-${section.name}`}
          className="relative mt-0.5 pb-1"
        >
          <NavTreeLine />
          <ul className="flex flex-col gap-0.5">
            {children.map((child) => (
              <NavSubLink
                key={child.href}
                child={child}
                pathname={pathname}
                badgeCount={badgeCounts[child.href] ?? 0}
              />
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

/** Gray 1px tree-line running through expanded children. Aligned at left-[19px]
 *  to sit on the same x-coordinate as the parent's icon center. The active
 *  sub-link's blue pill replaces the same x-coordinate, visually substituting a
 *  segment of this line. */
export function NavTreeLine() {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none absolute left-[19px] top-0 bottom-1 w-px bg-gray-200 dark:bg-gray-800"
    />
  )
}

export function NavSubLink({
  child,
  pathname,
  badgeCount = 0,
}: {
  child: ModuleSection
  pathname: string
  badgeCount?: number
}) {
  const isActive = child.enabled && (pathname === child.href || pathname.startsWith(`${child.href}/`))
  const disabled = !child.enabled

  const className = cx(
    "relative flex items-center gap-2 rounded-md py-1.5 pl-[34px] pr-2 text-[13px]",
    "transition-colors duration-100",
    isActive
      ? "bg-white text-blue-600 shadow-xs ring-1 ring-gray-200 font-medium dark:bg-gray-900 dark:text-blue-400 dark:ring-gray-800"
      : disabled
      ? "pointer-events-none text-gray-400 dark:text-gray-600"
      : "text-gray-700 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-50",
    focusRing,
  )

  const content = (
    <>
      {isActive && (
        <span
          aria-hidden="true"
          className="absolute left-[18px] top-1/2 h-[18px] w-[2px] -translate-x-1/2 -translate-y-1/2 rounded bg-blue-500"
        />
      )}
      <span className="flex-1 truncate">{child.name}</span>
      {disabled ? (
        <span className="rounded bg-gray-200 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:bg-gray-800 dark:text-gray-400">
          breve
        </span>
      ) : (
        <ApprovalQueueBadge count={badgeCount} />
      )}
    </>
  )

  return (
    <li>
      {disabled ? (
        <span className={className} aria-disabled="true">
          {content}
        </span>
      ) : (
        <Link
          href={child.href}
          aria-current={isActive ? "page" : undefined}
          className={className}
        >
          {content}
        </Link>
      )}
    </li>
  )
}
