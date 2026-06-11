"use client"

// Picker de fundo do Comparador — popover com busca server-side em
// /bi/benchmark/fundos (~4k fundos CVM). Standalone (controlado por props),
// diferente do FundoCombobox do /bi/benchmark que e acoplado a URL daquela
// pagina. Debounce interno de 300ms.

import * as React from "react"
import { RiAddLine, RiCloseLine, RiSearchLine } from "@remixicon/react"
import { useQuery } from "@tanstack/react-query"

import { cx, focusInput } from "@/lib/utils"
import { Input } from "@/components/tremor/Input"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/tremor/Popover"
import { biBenchmark } from "@/lib/api-client"

const DEBOUNCE_MS = 300

export type FundoSelecionado = { cnpj: string; nome: string }

export function ComparadorFundoPicker({
  selecionado,
  onSelect,
  onRemove,
  disabledCnpjs,
}: {
  /** Fundo no slot (null = slot vazio, mostra "+ adicionar"). */
  selecionado: FundoSelecionado | null
  onSelect: (f: FundoSelecionado) => void
  onRemove: () => void
  /** CNPJs ja escolhidos nos outros slots (escondidos da busca). */
  disabledCnpjs: string[]
}) {
  const [open, setOpen] = React.useState(false)
  const [termo, setTermo] = React.useState("")
  const [debounced, setDebounced] = React.useState("")

  React.useEffect(() => {
    const id = window.setTimeout(() => setDebounced(termo), DEBOUNCE_MS)
    return () => window.clearTimeout(id)
  }, [termo])

  const q = useQuery({
    queryKey: ["bi", "benchmark", "fundos-busca", debounced],
    queryFn: () => biBenchmark.fundos({ busca: debounced || undefined }),
    enabled: open,
    staleTime: 5 * 60 * 1000,
  })
  const fundos = (q.data?.data?.fundos ?? []).filter(
    (f) => !disabledCnpjs.includes(f.cnpj_fundo.replace(/\D/g, "")),
  )

  if (selecionado) {
    return (
      <span className="flex h-[30px] items-center gap-1.5 rounded border border-blue-200 bg-blue-50 px-2.5 text-[13px] font-medium text-blue-700 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-300">
        <span className="max-w-[220px] truncate" title={selecionado.nome}>
          {selecionado.nome}
        </span>
        <button
          type="button"
          onClick={onRemove}
          aria-label={`Remover ${selecionado.nome}`}
          className="rounded p-0.5 hover:bg-blue-100 dark:hover:bg-blue-500/20"
        >
          <RiCloseLine className="size-3.5" aria-hidden="true" />
        </button>
      </span>
    )
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cx(
            "flex h-[30px] items-center gap-1.5 rounded border border-dashed border-gray-300 px-2.5 text-[13px] font-medium text-gray-500 transition-colors hover:border-gray-400 hover:text-gray-700 dark:border-gray-700 dark:text-gray-400 dark:hover:border-gray-600 dark:hover:text-gray-200",
          )}
        >
          <RiAddLine className="size-3.5" aria-hidden="true" />
          Adicionar fundo
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-80 p-2">
        <div className="relative">
          <RiSearchLine
            className="absolute left-2 top-1/2 size-4 -translate-y-1/2 text-gray-400"
            aria-hidden="true"
          />
          <Input
            autoFocus
            value={termo}
            onChange={(e) => setTermo(e.target.value)}
            placeholder="Nome ou CNPJ…"
            className={cx("pl-8", focusInput)}
          />
        </div>
        <ul className="mt-2 max-h-72 overflow-y-auto">
          {q.isLoading && (
            <li className="px-2 py-3 text-xs text-gray-400">Buscando…</li>
          )}
          {!q.isLoading && fundos.length === 0 && (
            <li className="px-2 py-3 text-xs text-gray-400">
              Nenhum fundo encontrado.
            </li>
          )}
          {fundos.slice(0, 50).map((f) => (
            <li key={f.cnpj_fundo}>
              <button
                type="button"
                className="w-full rounded px-2 py-1.5 text-left text-[12px] text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-900"
                onClick={() => {
                  onSelect({
                    cnpj: f.cnpj_fundo.replace(/\D/g, ""),
                    nome: f.denominacao_social ?? f.cnpj_fundo,
                  })
                  setOpen(false)
                  setTermo("")
                }}
              >
                <span className="block truncate font-medium">
                  {f.denominacao_social ?? "—"}
                </span>
                <span className="block text-[11px] tabular-nums text-gray-400">
                  {f.cnpj_fundo}
                </span>
              </button>
            </li>
          ))}
        </ul>
      </PopoverContent>
    </Popover>
  )
}
