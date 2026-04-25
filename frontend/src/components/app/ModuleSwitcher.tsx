"use client"

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuGroup,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/tremor/DropdownMenu"
import {
  MODULES,
  MODULE_AVATAR_COLORS,
  PERMISSION_LABEL,
  getActiveModule,
  getVisibleModules,
  type ModuleDefinition,
} from "@/lib/modules"
import { cx, focusInput } from "@/lib/utils"
import { RiExpandUpDownLine } from "@remixicon/react"
import { usePathname, useRouter } from "next/navigation"
import * as React from "react"

type AvatarProps = {
  module: ModuleDefinition
  size?: "sm" | "md"
  active?: boolean
}

function ModuleAvatar({ module, size = "md", active = false }: AvatarProps) {
  const sizeClass = size === "sm" ? "size-7" : "size-8"
  return (
    <span
      className={cx(
        MODULE_AVATAR_COLORS[module.color],
        sizeClass,
        "flex aspect-square shrink-0 items-center justify-center rounded-sm text-[11px] font-semibold tracking-wide text-white",
        active && "ring-2 ring-blue-500 ring-offset-1 ring-offset-white dark:ring-offset-gray-950",
      )}
      aria-hidden="true"
    >
      {module.initials}
    </span>
  )
}

export function ModuleSwitcher() {
  const pathname = usePathname()
  const router = useRouter()
  const activeModule = React.useMemo(
    () => getActiveModule(pathname),
    [pathname],
  )
  const visibleModules = React.useMemo(() => getVisibleModules(), [])
  const upcomingModules = React.useMemo(
    () => MODULES.filter((m) => !m.enabled || m.permission === "none"),
    [],
  )

  return (
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <button
          className={cx(
            "flex w-full items-center gap-x-2.5 rounded-md border border-gray-300 bg-white p-2 text-sm shadow-sm transition-all hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-950 hover:dark:bg-gray-900",
            focusInput,
          )}
        >
          <ModuleAvatar module={activeModule} />
          <div className="flex w-full items-center justify-between gap-x-4 truncate">
            <div className="truncate text-left">
              <p className="truncate whitespace-nowrap text-sm font-medium text-gray-900 dark:text-gray-50">
                {activeModule.name}
              </p>
              <p className="whitespace-nowrap text-xs text-gray-700 dark:text-gray-300">
                {PERMISSION_LABEL[activeModule.permission]}
              </p>
            </div>
            <RiExpandUpDownLine
              className="size-5 shrink-0 text-gray-500"
              aria-hidden="true"
            />
          </div>
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-64">
        <DropdownMenuGroup>
          <DropdownMenuLabel>
            Modulos ({visibleModules.length})
          </DropdownMenuLabel>
          {visibleModules.map((module) => {
            const firstSection = module.sections.find((s) => s.enabled)
            const href = firstSection?.href ?? module.basePath
            const isCurrent = module.id === activeModule.id
            return (
              <DropdownMenuItem
                key={module.id}
                onSelect={() => router.push(href)}
              >
                <div className="flex w-full items-center gap-x-2.5">
                  <ModuleAvatar module={module} active={isCurrent} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-50">
                      {module.name}
                    </p>
                    <p className="text-xs text-gray-700 dark:text-gray-400">
                      {PERMISSION_LABEL[module.permission]}
                    </p>
                  </div>
                  {isCurrent && (
                    <span
                      className="text-blue-600 dark:text-blue-400"
                      aria-hidden="true"
                    >
                      <svg
                        className="size-3.5"
                        viewBox="0 0 24 24"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2.5"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      >
                        <path d="M5 12l5 5 10-10" />
                      </svg>
                    </span>
                  )}
                </div>
              </DropdownMenuItem>
            )
          })}
        </DropdownMenuGroup>
        {upcomingModules.length > 0 && (
          <>
            <DropdownMenuSeparator />
            <DropdownMenuLabel>Em breve</DropdownMenuLabel>
            <DropdownMenuGroup>
              {upcomingModules.map((module) => (
                <DropdownMenuItem
                  key={module.id}
                  disabled
                  className="cursor-not-allowed opacity-60"
                >
                  <div className="flex w-full items-center gap-x-2.5">
                    <ModuleAvatar module={module} />
                    <div>
                      <p className="text-sm font-medium text-gray-900 dark:text-gray-50">
                        {module.name}
                      </p>
                      <p className="text-xs text-gray-500 dark:text-gray-500">
                        Em breve
                      </p>
                    </div>
                  </div>
                </DropdownMenuItem>
              ))}
            </DropdownMenuGroup>
          </>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
