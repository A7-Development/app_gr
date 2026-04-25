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
import { RiArrowRightUpLine } from "@remixicon/react"
import * as React from "react"

export type DropdownUserProfileProps = {
  children: React.ReactNode
  align?: "center" | "start" | "end"
}

export function DropdownUserProfile({
  children,
  align = "start",
}: DropdownUserProfileProps) {
  const [mounted, setMounted] = React.useState(false)
  React.useEffect(() => {
    setMounted(true)
  }, [])

  if (!mounted) {
    return null
  }
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>{children}</DropdownMenuTrigger>
      <DropdownMenuContent
        align={align}
        className="sm:!min-w-[calc(var(--radix-dropdown-menu-trigger-width))]"
      >
        <DropdownMenuLabel>ricardo@a7credit.com.br</DropdownMenuLabel>
        <DropdownMenuGroup>
          <DropdownMenuItem>Perfil</DropdownMenuItem>
          <DropdownMenuItem>Configuracoes</DropdownMenuItem>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuItem>
            Documentacao
            <RiArrowRightUpLine
              className="mb-1 ml-1 size-3 shrink-0 text-gray-500 dark:text-gray-500"
              aria-hidden="true"
            />
          </DropdownMenuItem>
          <DropdownMenuItem>
            Suporte
            <RiArrowRightUpLine
              className="mb-1 ml-1 size-3 shrink-0 text-gray-500"
              aria-hidden="true"
            />
          </DropdownMenuItem>
        </DropdownMenuGroup>
        <DropdownMenuSeparator />
        <DropdownMenuGroup>
          <DropdownMenuItem>
            <a href="#" className="w-full">
              Sair
            </a>
          </DropdownMenuItem>
        </DropdownMenuGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
