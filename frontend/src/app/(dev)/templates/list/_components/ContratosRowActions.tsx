"use client"

import * as React from "react"
import {
  RiMoreLine,
  RiEyeLine,
  RiEditLine,
  RiDeleteBinLine,
} from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/tremor/DropdownMenu"

type Props = {
  numero: string
}

export function ContratosRowActions({ numero }: Props) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          className="size-8 px-0"
          aria-label={`Acoes para o contrato ${numero}`}
        >
          <RiMoreLine className="size-4" aria-hidden />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-40">
        <DropdownMenuItem>
          <RiEyeLine className="mr-2 size-4" aria-hidden /> Visualizar
        </DropdownMenuItem>
        <DropdownMenuItem>
          <RiEditLine className="mr-2 size-4" aria-hidden /> Editar
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem className="text-red-600 dark:text-red-500">
          <RiDeleteBinLine className="mr-2 size-4" aria-hidden /> Excluir
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
