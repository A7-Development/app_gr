"use client"

import Link from "next/link"
import { usePathname, useRouter, useSearchParams } from "next/navigation"
import * as React from "react"
import { RiEyeLine } from "@remixicon/react"

import { Input } from "@/components/tremor/Input"
import { Button } from "@/components/tremor/Button"
import { Checkbox } from "@/components/tremor/Checkbox"
import { Badge } from "@/components/tremor/Badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRoot,
  TableRow,
} from "@/components/tremor/Table"

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

  const fichaHref = (cnpjDigitsValue: string) => {
    const n = new URLSearchParams(sp.toString())
    n.set("tab", "ficha")
    n.set("cnpj", cnpjDigitsValue)
    return `${pathname}?${n.toString()}`
  }

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

      <TableRoot className="rounded border border-gray-200 dark:border-gray-800">
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell className="w-10"></TableHeaderCell>
              <TableHeaderCell>Fundo</TableHeaderCell>
              <TableHeaderCell>CNPJ</TableHeaderCell>
              <TableHeaderCell>Classe</TableHeaderCell>
              <TableHeaderCell className="text-right">PL</TableHeaderCell>
              <TableHeaderCell className="text-right">
                % Inad. total
              </TableHeaderCell>
              <TableHeaderCell className="text-right">
                % Inad. &gt;120d
              </TableHeaderCell>
              <TableHeaderCell className="w-24"></TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {error ? (
              <TableRow>
                <TableCell
                  colSpan={8}
                  className="py-8 text-center text-sm text-red-600"
                >
                  Erro ao carregar fundos. Verifique sua sessao e tente
                  novamente.
                </TableCell>
              </TableRow>
            ) : fundos.length === 0 && !loading ? (
              <TableRow>
                <TableCell
                  colSpan={8}
                  className="py-8 text-center text-sm text-gray-500"
                >
                  {qParam.trim()
                    ? `Nenhum fundo encontrado para "${qParam.trim()}".`
                    : "Nenhum fundo disponivel na competencia atual."}
                </TableCell>
              </TableRow>
            ) : (
              fundos.map((f) => {
                const cnpjKey = cnpjDigits(f.cnpj_fundo)
                const isSel = selected.includes(cnpjKey)
                const disabled = !isSel && isFull
                return (
                  <TableRow key={cnpjKey}>
                    <TableCell>
                      <Checkbox
                        checked={isSel}
                        disabled={disabled}
                        onCheckedChange={() => toggle(cnpjKey)}
                        aria-label={`Selecionar ${
                          f.denominacao_social ?? cnpjKey
                        }`}
                      />
                    </TableCell>
                    <TableCell className="font-medium text-gray-900 dark:text-gray-50">
                      {f.denominacao_social ?? "(sem denominacao)"}
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {formatCNPJ(cnpjKey)}
                    </TableCell>
                    <TableCell className="text-xs">
                      {f.classe_anbima ?? "-"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {moedaCompacta.format(f.patrimonio_liquido)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {f.percentual_pdd != null ? percent1(f.percentual_pdd) : "-"}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {f.indice_inadimplencia != null
                        ? percent1(f.indice_inadimplencia)
                        : "-"}
                    </TableCell>
                    <TableCell>
                      <Button variant="ghost" asChild>
                        <Link
                          href={fichaHref(cnpjKey)}
                          className="inline-flex items-center gap-1"
                        >
                          <RiEyeLine className="size-3.5" aria-hidden="true" />
                          Ver ficha
                        </Link>
                      </Button>
                    </TableCell>
                  </TableRow>
                )
              })
            )}
          </TableBody>
        </Table>
      </TableRoot>
    </div>
  )
}
