"use client"

import Link from "next/link"
import { usePathname, useSearchParams } from "next/navigation"
import { RiCloseLine, RiScales3Line } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { Badge } from "@/components/tremor/Badge"

import { FUNDO_COR_CLASSES, FUNDO_CORES } from "../_fixtures/indicadores"
import { FICHAS } from "../_fixtures/fundos"
import { useSelectedFundos } from "../_hooks/useBenchmarkUrl"

//
// Barra sticky inferior que aparece quando ha pelo menos 1 fundo selecionado.
// Some na tab Comparativo (ja estamos la). Clique em "Comparar" navega para
// ?tab=comparativo preservando os cnpjs selecionados.
//
export function SelecaoStickyBar() {
  const { selected, remove, clear, max } = useSelectedFundos()
  const pathname = usePathname()
  const sp = useSearchParams()
  const activeTab = sp.get("tab") ?? "mercado"

  if (selected.length === 0 || activeTab === "comparativo") return null

  const compararHref = (() => {
    const n = new URLSearchParams(sp.toString())
    n.set("tab", "comparativo")
    return `${pathname}?${n.toString()}`
  })()

  return (
    <div
      role="region"
      aria-label="Selecao de fundos para comparativo"
      className="fixed inset-x-0 bottom-0 z-30 border-t border-gray-200 bg-white/95 shadow-lg backdrop-blur dark:border-gray-800 dark:bg-gray-950/95"
    >
      <div className="flex flex-wrap items-center gap-3 px-12 py-3">
        <div className="flex items-center gap-2">
          <span className="inline-flex size-7 items-center justify-center rounded-full bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400">
            <RiScales3Line className="size-4" aria-hidden="true" />
          </span>
          <span className="text-sm font-semibold text-gray-900 dark:text-gray-50">
            {selected.length}/{max} fundos selecionados
          </span>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {selected.map((cnpj, i) => {
            const nome =
              FICHAS[cnpj]?.identidade.denominacao_social ?? cnpj
            const cor = FUNDO_CORES[i] ?? "slate"
            return (
              <span
                key={cnpj}
                className="inline-flex items-center gap-1.5 rounded border border-gray-200 bg-gray-50 py-1 pl-2 pr-1 text-xs font-medium text-gray-900 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-50"
              >
                <span
                  className={`inline-block size-2.5 rounded-full ${FUNDO_COR_CLASSES[cor].dot}`}
                  aria-hidden="true"
                />
                <span className="max-w-[240px] truncate">{nome}</span>
                <button
                  type="button"
                  onClick={() => remove(cnpj)}
                  className="rounded p-0.5 text-gray-500 transition hover:bg-gray-200 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-50"
                  aria-label={`Remover ${nome}`}
                >
                  <RiCloseLine className="size-3.5" aria-hidden="true" />
                </button>
              </span>
            )
          })}
        </div>

        <div className="ml-auto flex items-center gap-2">
          <Button variant="ghost" onClick={clear}>
            Limpar
          </Button>
          <Button variant="primary" asChild disabled={selected.length < 2}>
            <Link
              href={selected.length < 2 ? "#" : compararHref}
              aria-disabled={selected.length < 2}
            >
              <RiScales3Line className="-ml-1 size-4" aria-hidden="true" />
              Comparar
            </Link>
          </Button>
        </div>
      </div>
      {selected.length < 2 && (
        <div className="px-12 pb-2">
          <Badge variant="neutral">
            Selecione pelo menos 2 fundos para habilitar o comparativo.
          </Badge>
        </div>
      )}
    </div>
  )
}
