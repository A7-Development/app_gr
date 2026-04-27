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
import { RiArrowDownSLine, RiCheckLine } from "@remixicon/react"
import { usePathname, useRouter } from "next/navigation"
import * as React from "react"

type AvatarProps = {
  module: ModuleDefinition
  size?: "xs" | "sm" | "md"
  active?: boolean
}

function ModuleAvatar({ module, size = "md", active = false }: AvatarProps) {
  const sizeClass = size === "xs" ? "size-5" : size === "sm" ? "size-7" : "size-8"
  const textClass = size === "xs" ? "text-[9px] font-bold" : "text-[11px] font-semibold tracking-wide"
  return (
    <span
      className={cx(
        MODULE_AVATAR_COLORS[module.color],
        sizeClass,
        textClass,
        "flex aspect-square shrink-0 items-center justify-center rounded-sm text-white",
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
  const [open, setOpen] = React.useState(false)
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
    <DropdownMenu modal={false} open={open} onOpenChange={setOpen}>
      {/* <button> cru aqui e o pattern Radix asChild — o trigger precisa ser um elemento focavel customizado, e Button do Tremor agredindo border/padding/hover proprios significa override em cima de override. Excecao documentada (CLAUDE.md §6). */}
      <DropdownMenuTrigger asChild>
        <button
          className={cx(
            "flex w-full items-center gap-x-2.5 rounded-md border border-gray-300 bg-white px-2 py-1.5 text-sm shadow-sm transition-all hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-950 hover:dark:bg-gray-900",
            focusInput,
          )}
        >
          <ModuleAvatar module={activeModule} size="sm" />
          <div className="flex w-full items-center justify-between gap-x-4 truncate">
            <div className="truncate text-left">
              <p className="truncate whitespace-nowrap text-sm font-medium text-gray-900 dark:text-gray-50">
                {activeModule.name}
              </p>
              <p className="whitespace-nowrap text-xs text-gray-700 dark:text-gray-300">
                {PERMISSION_LABEL[activeModule.permission]}
              </p>
            </div>
            <RiArrowDownSLine
              className={cx(
                "size-4 shrink-0 text-gray-400 transition-transform duration-150",
                open && "rotate-180",
              )}
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
                  <ModuleAvatar module={module} size="xs" active={isCurrent} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-50">
                      {module.name}
                    </p>
                    <p className="text-xs text-gray-700 dark:text-gray-400">
                      {PERMISSION_LABEL[module.permission]}
                    </p>
                  </div>
                  {isCurrent && (
                    <RiCheckLine
                      className="size-3.5 shrink-0 text-blue-600 dark:text-blue-400"
                      aria-hidden="true"
                    />
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
                    <ModuleAvatar module={module} size="xs" />
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
