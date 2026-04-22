"use client"

import * as React from "react"
import { RiArrowDownSLine, RiCheckLine, RiSearchLine } from "@remixicon/react"

import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/tremor/Popover"
import { Input } from "@/components/tremor/Input"

import { useFundoCnpj } from "../_hooks/useBenchmarkUrl"
import { cnpjDigits, useFundosBusca } from "../_hooks/useFundosBusca"
import { formatCNPJ } from "./formatters"
import { cx, focusInput } from "@/lib/utils"

const DEBOUNCE_MS = 300

//
// Seletor de fundo com busca — vive no PageHeader.actions quando activeTab=ficha.
// Busca server-side via /bi/benchmark/fundos (CVM real, ~4k fundos).
// Debounce interno de 300ms no termo antes de consultar.
//
export function FundoCombobox() {
  const { cnpj, setCnpj } = useFundoCnpj()
  const [open, setOpen] = React.useState(false)
  const [termo, setTermo] = React.useState("")
  const [debounced, setDebounced] = React.useState("")
  const inputRef = React.useRef<HTMLInputElement>(null)

  React.useEffect(() => {
    const id = window.setTimeout(() => setDebounced(termo), DEBOUNCE_MS)
    return () => window.clearTimeout(id)
  }, [termo])

  const { fundos, total, loading } = useFundosBusca(debounced)

  // Mantem o fundo atualmente selecionado visivel mesmo fora do resultado da busca.
  // Ex.: usuario selecionou VALECRED, depois digita "REAL" — chip continua "VALECRED".
  const [selectedLabel, setSelectedLabel] = React.useState<string | null>(null)
  React.useEffect(() => {
    if (!cnpj) {
      setSelectedLabel(null)
      return
    }
    const hit = fundos.find((f) => cnpjDigits(f.cnpj_fundo) === cnpj)
    if (hit?.denominacao_social) setSelectedLabel(hit.denominacao_social)
  }, [cnpj, fundos])

  React.useEffect(() => {
    if (open) {
      setTermo("")
      setDebounced("")
      queueMicrotask(() => inputRef.current?.focus())
    }
  }, [open])

  const selecionar = (valorDigits: string) => {
    setCnpj(valorDigits)
    setOpen(false)
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cx(
            "inline-flex w-[320px] select-none items-center justify-between gap-x-2 truncate rounded border px-2 py-1.5 text-xs font-medium shadow-xs transition",
            "border-gray-300 dark:border-gray-800",
            "bg-white text-gray-900 dark:bg-gray-950 dark:text-gray-50",
            "hover:bg-gray-50 dark:hover:bg-gray-950/50",
            focusInput,
          )}
        >
          <span className={cx("truncate", !selectedLabel && "text-gray-500")}>
            {selectedLabel ?? (cnpj ? formatCNPJ(cnpj) : "Selecione um fundo...")}
          </span>
          <RiArrowDownSLine
            className="size-4 shrink-0 text-gray-500"
            aria-hidden="true"
          />
        </button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        className="w-[520px] p-0"
        onOpenAutoFocus={(e) => e.preventDefault()}
      >
        <div className="border-b border-gray-200 p-2 dark:border-gray-800">
          <div className="relative">
            <RiSearchLine
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-gray-500"
              aria-hidden="true"
            />
            <Input
              ref={inputRef}
              type="search"
              placeholder="Buscar por nome ou CNPJ..."
              value={termo}
              onChange={(e) => setTermo(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && fundos[0]) {
                  e.preventDefault()
                  selecionar(cnpjDigits(fundos[0].cnpj_fundo))
                }
              }}
              className="pl-9"
            />
          </div>
        </div>
        <div className="max-h-[360px] overflow-y-auto p-1">
          {loading ? (
            <div className="px-3 py-6 text-center text-sm text-gray-500">
              Buscando...
            </div>
          ) : fundos.length === 0 ? (
            <div className="px-3 py-6 text-center text-sm text-gray-500">
              {debounced.trim()
                ? `Nenhum fundo encontrado para "${debounced.trim()}".`
                : "Nenhum fundo disponivel."}
            </div>
          ) : (
            fundos.map((f) => {
              const key = cnpjDigits(f.cnpj_fundo)
              const isSel = key === cnpj
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => selecionar(key)}
                  className={cx(
                    "flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm",
                    "hover:bg-gray-100 dark:hover:bg-gray-900",
                    isSel && "bg-blue-50 dark:bg-blue-500/10",
                  )}
                >
                  <RiCheckLine
                    className={cx(
                      "size-4 shrink-0",
                      isSel ? "text-blue-600 dark:text-blue-400" : "text-transparent",
                    )}
                    aria-hidden="true"
                  />
                  <div className="min-w-0 flex-1">
                    <div className="truncate font-medium text-gray-900 dark:text-gray-50">
                      {f.denominacao_social ?? "(sem denominacao)"}
                    </div>
                    <div className="flex items-center gap-2 text-xs text-gray-500">
                      <span className="font-mono">{formatCNPJ(key)}</span>
                      {f.classe_anbima && (
                        <>
                          <span>·</span>
                          <span className="truncate">{f.classe_anbima}</span>
                        </>
                      )}
                    </div>
                  </div>
                </button>
              )
            })
          )}
        </div>
        <div className="border-t border-gray-200 px-3 py-1.5 text-xs text-gray-500 dark:border-gray-800">
          {fundos.length} de {total} fundos
          {debounced.trim() && ` (buscando "${debounced.trim()}")`}
        </div>
      </PopoverContent>
    </Popover>
  )
}
