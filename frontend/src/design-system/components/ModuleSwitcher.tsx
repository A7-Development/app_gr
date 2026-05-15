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
            // Trigger ghost-style (handoff Strata v3 v2): sem border/bg em
            // estado idle; aparece em hover ou data-state=open.
            "flex w-full items-center gap-2 rounded-md border px-1.5 py-1 transition-colors duration-150",
            "border-transparent bg-transparent",
            "hover:border-gray-200 hover:bg-gray-50 dark:hover:border-gray-800 dark:hover:bg-gray-900",
            "data-[state=open]:border-gray-200 data-[state=open]:bg-white dark:data-[state=open]:border-gray-800 dark:data-[state=open]:bg-gray-950",
            focusInput,
          )}
        >
          {/* Avatar inline 22px (handoff Strata v3) — alinhado a uma unica
              linha de label. ModuleAvatar canonica continua em size-7/size-5
              para outros consumidores; aqui o trigger usa dimensao propria. */}
          <span
            className={cx(
              "flex size-[22px] shrink-0 items-center justify-center rounded-[5px] text-[10px] font-bold text-white",
              MODULE_AVATAR_COLORS[activeModule.color],
            )}
            aria-hidden="true"
          >
            {activeModule.initials}
          </span>
          <span className="flex-1 truncate text-left text-[13px] font-medium text-gray-900 dark:text-gray-50">
            {activeModule.name}
          </span>
          <RiArrowDownSLine
            className="size-3.5 shrink-0 text-gray-400"
            aria-hidden="true"
          />
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
