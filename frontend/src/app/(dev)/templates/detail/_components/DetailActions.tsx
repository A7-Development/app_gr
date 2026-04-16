"use client"

import * as React from "react"
import {
  RiMoreLine,
  RiEditLine,
  RiFilePdfLine,
  RiArchiveLine,
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

export function DetailActions() {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="secondary">
          <RiMoreLine className="mr-1.5 size-4" aria-hidden />
          Mais acoes
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-44">
        <DropdownMenuItem>
          <RiEditLine className="mr-2 size-4" aria-hidden /> Editar
        </DropdownMenuItem>
        <DropdownMenuItem>
          <RiFilePdfLine className="mr-2 size-4" aria-hidden /> Exportar PDF
        </DropdownMenuItem>
        <DropdownMenuItem>
          <RiArchiveLine className="mr-2 size-4" aria-hidden /> Arquivar
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem className="text-red-600 dark:text-red-500">
          <RiDeleteBinLine className="mr-2 size-4" aria-hidden /> Excluir
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
