"use client"
import { Logo } from "@/components/app/Logo"
import { ModuleSwitcher } from "@/components/app/ModuleSwitcher"
import { UserProfile } from "@/components/app/UserProfile"
import { Divider } from "@/components/tremor/Divider"
import { Input } from "@/components/tremor/Input"
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarLink,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuSub,
  SidebarSubLink,
} from "@/components/tremor/Sidebar"
import { cx, focusRing } from "@/lib/utils"
import { getActiveModule } from "@/lib/modules"
import {
  RiArrowDownSFill,
  RiHome5Line,
  RiLayoutGridLine,
} from "@remixicon/react"
import type { RemixiconComponentType } from "@remixicon/react"
import { usePathname } from "next/navigation"
import * as React from "react"

type NavItem = {
  name: string
  href: string
  icon: RemixiconComponentType
  notifications?: boolean | number
}

type DevToolGroup = {
  name: string
  icon: RemixiconComponentType
  children: { name: string; href: string }[]
}

// L0 — atalhos de topo (nao-modulos)
const navigation: NavItem[] = [
  {
    name: "Inicio",
    href: "/",
    icon: RiHome5Line,
    notifications: false,
  },
]

// Ferramentas de desenvolvimento — fora de modulos, escondidas em prod futuramente.
const devTools: DevToolGroup[] = [
  {
    name: "Templates",
    icon: RiLayoutGridLine,
    children: [
      { name: "Indice", href: "/templates" },
      { name: "Listagem", href: "/templates/list" },
      { name: "Formulario", href: "/templates/form" },
      { name: "Detalhe", href: "/templates/detail" },
      { name: "Dashboard", href: "/templates/dashboard" },
      { name: "Wizard", href: "/templates/wizard" },
    ],
  },
]

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const pathname = usePathname()
  const activeModule = React.useMemo(
    () => getActiveModule(pathname),
    [pathname],
  )

  const [openDevTools, setOpenDevTools] = React.useState<string[]>([])
  const toggleDevTool = (name: string) => {
    setOpenDevTools((prev) =>
      prev.includes(name) ? prev.filter((n) => n !== name) : [...prev, name],
    )
  }

  return (
    <Sidebar {...props} className="bg-gray-50 dark:bg-gray-925">
      <SidebarHeader className="px-3 py-4">
        <div className="mb-3 flex items-center gap-2.5">
          <Logo className="size-8" />
          <div>
            <span className="block text-sm font-semibold text-gray-900 dark:text-gray-50">
              A7 Credit
            </span>
            <span className="block text-xs text-gray-500 dark:text-gray-400">
              Plataforma GR
            </span>
          </div>
        </div>
        <ModuleSwitcher />
      </SidebarHeader>
      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <Input
              type="search"
              placeholder="Buscar..."
              className="[&>input]:sm:py-1.5"
            />
          </SidebarGroupContent>
        </SidebarGroup>
        <SidebarGroup className="pt-0">
          <SidebarGroupContent>
            <SidebarMenu className="space-y-1">
              {navigation.map((item) => (
                <SidebarMenuItem key={item.name}>
                  <SidebarLink
                    href={item.href}
                    isActive={item.href !== "#" && pathname === item.href}
                    icon={item.icon}
                    notifications={item.notifications}
                  >
                    {item.name}
                  </SidebarLink>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <div className="px-3">
          <Divider className="my-0 py-0" />
        </div>
        <SidebarGroup>
          <SidebarGroupContent>
            <div className="px-2 pb-2 text-xs font-medium uppercase tracking-wider text-gray-500 dark:text-gray-500">
              {activeModule.name}
            </div>
            <SidebarMenu className="space-y-1">
              {activeModule.sections.map((section) => (
                <SidebarMenuItem key={section.name}>
                  <SidebarLink
                    href={section.enabled ? section.href : "#"}
                    isActive={
                      section.enabled &&
                      section.href !== "#" &&
                      pathname.startsWith(section.href)
                    }
                    icon={activeModule.icon}
                    className={cx(
                      !section.enabled &&
                        "pointer-events-none text-gray-400 dark:text-gray-600",
                    )}
                  >
                    <span className="flex items-center gap-2">
                      {section.name}
                      {!section.enabled && (
                        <span className="rounded bg-gray-200 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:bg-gray-800 dark:text-gray-400">
                          breve
                        </span>
                      )}
                    </span>
                  </SidebarLink>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
        <div className="px-3">
          <Divider className="my-0 py-0" />
        </div>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu className="space-y-2">
              {devTools.map((item) => (
                <SidebarMenuItem key={item.name}>
                  <button
                    onClick={() => toggleDevTool(item.name)}
                    className={cx(
                      "flex w-full items-center justify-between gap-x-2.5 rounded p-2 text-base text-gray-900 transition hover:bg-gray-200/50 sm:text-sm dark:text-gray-400 hover:dark:bg-gray-900 hover:dark:text-gray-50",
                      focusRing,
                    )}
                  >
                    <div className="flex items-center gap-2.5">
                      <item.icon
                        className="size-[18px] shrink-0"
                        aria-hidden="true"
                      />
                      {item.name}
                    </div>
                    <RiArrowDownSFill
                      className={cx(
                        openDevTools.includes(item.name)
                          ? "rotate-0"
                          : "-rotate-90",
                        "size-5 shrink-0 transform text-gray-400 transition-transform duration-150 ease-in-out dark:text-gray-600",
                      )}
                      aria-hidden="true"
                    />
                  </button>
                  {openDevTools.includes(item.name) && (
                    <SidebarMenuSub>
                      <div className="absolute inset-y-0 left-4 w-px bg-gray-300 dark:bg-gray-800" />
                      {item.children.map((child) => (
                        <SidebarMenuItem key={child.name}>
                          <SidebarSubLink
                            href={child.href}
                            isActive={
                              child.href !== "#" && pathname === child.href
                            }
                          >
                            {child.name}
                          </SidebarSubLink>
                        </SidebarMenuItem>
                      ))}
                    </SidebarMenuSub>
                  )}
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>
      <SidebarFooter>
        <div className="border-t border-gray-200 dark:border-gray-800" />
        <UserProfile />
      </SidebarFooter>
    </Sidebar>
  )
}
