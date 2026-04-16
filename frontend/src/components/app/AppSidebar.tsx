"use client"
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
import {
  RiArrowDownSFill,
  RiContactsBookLine,
  RiExchangeFundsLine,
  RiHome5Line,
  RiInboxLine,
  RiLayoutGridLine,
  RiPieChart2Line,
} from "@remixicon/react"
import { usePathname } from "next/navigation"
import * as React from "react"
import { Logo } from "@/components/app/Logo"
import { UserProfile } from "@/components/app/UserProfile"

const navigation = [
  {
    name: "Inicio",
    href: "/",
    icon: RiHome5Line,
    notifications: false,
    active: false,
  },
  {
    name: "Caixa de entrada",
    href: "#",
    icon: RiInboxLine,
    notifications: 3,
    active: false,
  },
] as const

const navigation2 = [
  {
    name: "Operacoes",
    href: "#",
    icon: RiExchangeFundsLine,
    children: [
      { name: "Contratos", href: "#", active: false },
      { name: "Pagamentos", href: "#", active: false },
      { name: "Recebimentos", href: "#", active: false },
    ],
  },
  {
    name: "Cadastros",
    href: "#",
    icon: RiContactsBookLine,
    children: [
      { name: "Clientes", href: "#", active: false },
      { name: "Fornecedores", href: "#", active: false },
      { name: "Produtos", href: "#", active: false },
    ],
  },
  {
    name: "Relatorios",
    href: "#",
    icon: RiPieChart2Line,
    children: [
      { name: "Visao geral", href: "#", active: false },
      { name: "Fluxo de caixa", href: "#", active: false },
      { name: "Inadimplencia", href: "#", active: false },
    ],
  },
  {
    name: "Templates",
    href: "#",
    icon: RiLayoutGridLine,
    children: [
      { name: "Indice", href: "/templates", active: false },
      { name: "Listagem", href: "/templates/list", active: false },
      { name: "Formulario", href: "/templates/form", active: false },
      { name: "Detalhe", href: "/templates/detail", active: false },
      { name: "Dashboard", href: "/templates/dashboard", active: false },
      { name: "Wizard", href: "/templates/wizard", active: false },
    ],
  },
] as const

export function AppSidebar({ ...props }: React.ComponentProps<typeof Sidebar>) {
  const pathname = usePathname()
  const [openMenus, setOpenMenus] = React.useState<string[]>([
    navigation2[0].name,
    navigation2[1].name,
    navigation2[2].name,
    navigation2[3].name,
  ])
  const toggleMenu = (name: string) => {
    setOpenMenus((prev: string[]) =>
      prev.includes(name)
        ? prev.filter((item: string) => item !== name)
        : [...prev, name],
    )
  }
  return (
    <Sidebar {...props} className="bg-gray-50 dark:bg-gray-925">
      <SidebarHeader className="px-3 py-4">
        <div className="flex items-center gap-3">
          <Logo className="size-9" />
          <div>
            <span className="block text-sm font-semibold text-gray-900 dark:text-gray-50">
              A7 Credit
            </span>
            <span className="block text-xs text-gray-900 dark:text-gray-50">
              Controladoria financeira
            </span>
          </div>
        </div>
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
                    isActive={
                      item.href !== "#" && pathname === item.href
                    }
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
            <SidebarMenu className="space-y-4">
              {navigation2.map((item) => (
                <SidebarMenuItem key={item.name}>
                  <button
                    onClick={() => toggleMenu(item.name)}
                    className={cx(
                      "flex w-full items-center justify-between gap-x-2.5 rounded-md p-2 text-base text-gray-900 transition hover:bg-gray-200/50 sm:text-sm dark:text-gray-400 hover:dark:bg-gray-900 hover:dark:text-gray-50",
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
                        openMenus.includes(item.name)
                          ? "rotate-0"
                          : "-rotate-90",
                        "size-5 shrink-0 transform text-gray-400 transition-transform duration-150 ease-in-out dark:text-gray-600",
                      )}
                      aria-hidden="true"
                    />
                  </button>
                  {item.children && openMenus.includes(item.name) && (
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
