"use client"

import Link from "next/link"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import * as React from "react"
import { RiEyeLine } from "@remixicon/react"
import type { ColumnDef } from "@tanstack/react-table"

import { Input } from "@/components/tremor/Input"
import { Button } from "@/components/tremor/Button"
import { Checkbox } from "@/components/tremor/Checkbox"
import { Badge } from "@/components/tremor/Badge"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"
import type { FundoRow } from "@/lib/api-client"

import { formatCNPJ, moedaCompacta, numero, percent1 } from "./formatters"
import { useSelectedFundos } from "../_hooks/useBenchmarkUrl"
import { cnpjDigits, useFundosBusca } from "../_hooks/useFundosBusca"

const SEARCH_DEBOUNCE_MS = 300

//
// Lista de fundos — busca server-side via /bi/benchmark/fundos (CVM real).
// Input -> 300ms debounce -> URL ?q= -> useFundosBusca -> React Query.
// Checkbox alimenta a selecao (max 5) usada no Comparativo; selecao usa
// CNPJ so-digitos (normalizado de "26.208.328/0001-91" -> "26208328000191").
//
export function ListaFundosTab() {
  const router = useRouter()
  const pathname = usePathname()
  const sp = useSearchParams()
  const qParam = sp.get("q") ?? ""
  const { selected, toggle, isFull, max } = useSelectedFundos()

  const [termo, setTermo] = React.useState(qParam)

  React.useEffect(() => {
    setTermo(qParam)
  }, [qParam])

  React.useEffect(() => {
    if (termo === qParam) return
    const id = window.setTimeout(() => {
      const next = new URLSearchParams(sp.toString())
      if (termo.trim()) next.set("q", termo.trim())
      else next.delete("q")
      router.replace(`${pathname}?${next.toString()}`, { scroll: false })
    }, SEARCH_DEBOUNCE_MS)
    return () => window.clearTimeout(id)
  }, [termo, qParam, sp, pathname, router])

  const { fundos, total, competencia, loading, error } = useFundosBusca(qParam)

  const fichaHref = React.useCallback(
    (cnpjDigitsValue: string) => {
      const n = new URLSearchParams(sp.toString())
      n.set("tab", "ficha")
      n.set("cnpj", cnpjDigitsValue)
      return `${pathname}?${n.toString()}`
    },
    [sp, pathname],
  )

  const columns = React.useMemo<ColumnDef<FundoRow, unknown>[]>(
    () => [
      {
        id: "select",
        header: "",
        enableSorting: false,
        cell: ({ row }) => {
          const cnpjKey = cnpjDigits(row.original.cnpj_fundo)
          const isSel = selected.includes(cnpjKey)
          const disabled = !isSel && isFull
          return (
            <Checkbox
              checked={isSel}
              disabled={disabled}
              onCheckedChange={() => toggle(cnpjKey)}
              aria-label={`Selecionar ${
                row.original.denominacao_social ?? cnpjKey
              }`}
            />
          )
        },
      },
      {
        id: "fundo",
        header: "Fundo",
        accessorFn: (r) => r.denominacao_social ?? "(sem denominacao)",
        cell: ({ row }) => (
          <span className={cx(tableTokens.cellText, "font-medium")}>
            {row.original.denominacao_social ?? "(sem denominacao)"}
          </span>
        ),
      },
      {
        id: "cnpj",
        header: "CNPJ",
        accessorFn: (r) => cnpjDigits(r.cnpj_fundo),
        cell: ({ row }) => (
          <span className={tableTokens.cellTextMono}>
            {formatCNPJ(cnpjDigits(row.original.cnpj_fundo))}
          </span>
        ),
      },
      {
        id: "classe",
        header: "Classe",
        accessorFn: (r) => r.classe_anbima ?? "-",
        cell: ({ row }) => (
          <span className={tableTokens.cellText}>
            {row.original.classe_anbima ?? "-"}
          </span>
        ),
      },
      {
        id: "pl",
        header: "PL",
        accessorFn: (r) => r.patrimonio_liquido,
        meta: { align: "right" },
        cell: ({ row }) => (
          <span className={cx(tableTokens.cellNumber, "block text-right")}>
            {moedaCompacta.format(row.original.patrimonio_liquido)}
          </span>
        ),
      },
      {
        id: "inad_total",
        header: "% Inad. total",
        accessorFn: (r) => r.percentual_pdd,
        meta: { align: "right" },
        cell: ({ row }) => (
          <span className={cx(tableTokens.cellNumber, "block text-right")}>
            {row.original.percentual_pdd != null
              ? percent1(row.original.percentual_pdd)
              : "-"}
          </span>
        ),
      },
      {
        id: "inad_longo",
        header: "% Inad. >120d",
        accessorFn: (r) => r.indice_inadimplencia,
        meta: { align: "right" },
        cell: ({ row }) => (
          <span className={cx(tableTokens.cellNumber, "block text-right")}>
            {row.original.indice_inadimplencia != null
              ? percent1(row.original.indice_inadimplencia)
              : "-"}
          </span>
        ),
      },
      {
        id: "acao",
        header: "",
        enableSorting: false,
        cell: ({ row }) => {
          const cnpjKey = cnpjDigits(row.original.cnpj_fundo)
          return (
            <Button variant="ghost" asChild>
              <Link
                href={fichaHref(cnpjKey)}
                className="inline-flex items-center gap-1"
              >
                <RiEyeLine className="size-3.5" aria-hidden="true" />
                Ver ficha
              </Link>
            </Button>
          )
        },
      },
    ],
    [selected, isFull, toggle, fichaHref],
  )

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-3">
        <Input
          type="search"
          placeholder="Buscar por nome ou CNPJ..."
          value={termo}
          onChange={(e) => setTermo(e.target.value)}
          className="max-w-md"
        />
        <Badge variant={selected.length === 0 ? "neutral" : "default"}>
          {selected.length}/{max} selecionados
        </Badge>
        {competencia && (
          <Badge variant="neutral">Competencia {competencia}</Badge>
        )}
      </div>

      <div className="text-xs text-gray-500 dark:text-gray-400">
        {loading
          ? "Buscando..."
          : `Exibindo ${fundos.length} de ${numero.format(total)} fundos${
              qParam.trim() ? ` para "${qParam.trim()}"` : ""
            }. Marque ate ${max} fundos para habilitar o comparativo.`}
      </div>

      <div className="rounded border border-gray-200 dark:border-gray-800">
        <DataTable
          data={fundos}
          columns={columns}
          loading={loading && fundos.length === 0}
          error={error ? "Erro ao carregar fundos. Verifique sua sessao e tente novamente." : null}
          showDensityToggle={false}
          showColumnManager={false}
          renderEmpty={() => (
            <span className="text-sm text-gray-500">
              {qParam.trim()
                ? `Nenhum fundo encontrado para "${qParam.trim()}".`
                : "Nenhum fundo disponivel na competencia atual."}
            </span>
          )}
        />
      </div>
    </div>
  )
}
