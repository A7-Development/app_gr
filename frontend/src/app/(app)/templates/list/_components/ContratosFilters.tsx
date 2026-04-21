"use client"

import * as React from "react"
import { ptBR } from "date-fns/locale"

import { Input } from "@/components/tremor/Input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import { DateRangePicker, type DateRange } from "@/components/tremor/DatePicker"

export function ContratosFilters() {
  const [busca, setBusca] = React.useState("")
  const [status, setStatus] = React.useState<string>("todos")
  const [periodo, setPeriodo] = React.useState<DateRange | undefined>(undefined)

  return (
    <div className="flex flex-col gap-3 rounded border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-950 sm:flex-row sm:items-center">
      <div className="w-full sm:max-w-sm">
        <Input
          type="search"
          placeholder="Buscar contratos..."
          value={busca}
          onChange={(event) => setBusca(event.target.value)}
        />
      </div>

      <div className="w-full sm:w-48">
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger>
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todos">Todos</SelectItem>
            <SelectItem value="ativo">Ativo</SelectItem>
            <SelectItem value="pausado">Pausado</SelectItem>
            <SelectItem value="encerrado">Encerrado</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="w-full sm:ml-auto sm:w-72">
        <DateRangePicker
          value={periodo}
          onChange={setPeriodo}
          locale={ptBR}
          placeholder="Periodo de vencimento"
          translations={{
            cancel: "Cancelar",
            apply: "Aplicar",
            start: "Inicio",
            end: "Fim",
            range: "Periodo",
          }}
        />
      </div>
    </div>
  )
}
