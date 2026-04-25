"use client"

//
// Integracoes · Catalogo — lista todas as fontes do source_catalog + status
// por tenant no ambiente selecionado (sandbox vs production).
//
// Hierarquia de navegacao (CLAUDE.md 11.6):
//   L1 (dropdown): Integracoes
//     L2 (sidebar): Catalogo → /integracoes/catalogo
//       L3 (TabNavigation): n/a — lista unica (o detalhe por source vive em /catalogo/[source_type])
//

import Link from "next/link"
import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { RiArrowRightLine, RiStackLine } from "@remixicon/react"

import { PageHeader } from "@/design-system/components/PageHeader"
import {
  AdapterStatusBadge,
  statusFrom,
} from "@/design-system/components/AdapterStatusBadge"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { LastSyncCell } from "@/design-system/components/LastSyncCell"
import { Button } from "@/components/tremor/Button"
import { Select, SelectItem, SelectTrigger, SelectValue, SelectContent } from "@/components/tremor/Select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRoot,
  TableRow,
} from "@/components/tremor/Table"
import { useSources } from "@/lib/hooks/integracoes"
import type { Environment } from "@/lib/api-client"

const PAGE_INFO =
  "Fontes externas (ERPs, admin APIs, bureaus) configuradas para este tenant. Configure credenciais, teste conexao e acompanhe o historico de sincronizacoes."

function useEnvironment(): [Environment, (e: Environment) => void] {
  const sp = useSearchParams()
  const router = useRouter()
  const current: Environment =
    sp.get("environment") === "sandbox" ? "sandbox" : "production"
  const set = (e: Environment) => {
    const params = new URLSearchParams(sp?.toString() ?? "")
    if (e === "production") params.delete("environment")
    else params.set("environment", e)
    const qs = params.toString()
    router.replace(qs ? `/integracoes/catalogo?${qs}` : "/integracoes/catalogo")
  }
  return [current, set]
}

export default function CatalogoPage() {
  const [environment, setEnvironment] = useEnvironment()
  const { data, isLoading, isError, refetch } = useSources(environment)

  return (
    <div className="flex flex-col gap-6 px-12 py-6 pb-28">
      <PageHeader
        title="Integracoes · Catalogo"
        info={PAGE_INFO}
        actions={
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Ambiente
            </span>
            <Select
              value={environment}
              onValueChange={(v) => setEnvironment(v as Environment)}
            >
              <SelectTrigger className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="production">Producao</SelectItem>
                <SelectItem value="sandbox">Sandbox</SelectItem>
              </SelectContent>
            </Select>
          </div>
        }
      />

      {isError && (
        <ErrorState
          title="Nao foi possivel carregar o catalogo"
          description="Verifique se a API esta no ar e se seu usuario tem permissao admin no modulo Integracoes."
          action={
            <Button variant="secondary" onClick={() => refetch()}>
              Tentar novamente
            </Button>
          }
        />
      )}

      {!isError && !isLoading && data && data.length === 0 && (
        <EmptyState
          icon={RiStackLine}
          title="Nenhuma fonte cadastrada"
          description="Nenhum registro em source_catalog. Cadastre fontes via migration antes de configurar credenciais."
        />
      )}

      {!isError && (isLoading || (data && data.length > 0)) && (
        <div className="rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
          <TableRoot>
            <Table>
              <TableHead>
                <TableRow>
                  <TableHeaderCell>Fonte</TableHeaderCell>
                  <TableHeaderCell>Categoria</TableHeaderCell>
                  <TableHeaderCell>Provedor</TableHeaderCell>
                  <TableHeaderCell>Status</TableHeaderCell>
                  <TableHeaderCell>Ultimo sync</TableHeaderCell>
                  <TableHeaderCell className="w-12 text-right">
                    <span className="sr-only">Acoes</span>
                  </TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {isLoading &&
                  Array.from({ length: 3 }).map((_, i) => (
                    <TableRow key={`skeleton-${i}`}>
                      <TableCell colSpan={6}>
                        <div className="h-6 w-full animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
                      </TableCell>
                    </TableRow>
                  ))}
                {!isLoading &&
                  data?.map((row) => {
                    const status = statusFrom(row.configured, row.enabled)
                    const href = `/integracoes/catalogo/${encodeURIComponent(
                      row.source_type,
                    )}?environment=${environment}`
                    return (
                      <TableRow key={row.source_type}>
                        <TableCell className="font-medium text-gray-900 dark:text-gray-50">
                          <div className="flex flex-col">
                            <span>{row.label}</span>
                            <span className="font-mono text-xs text-gray-500 dark:text-gray-400">
                              {row.source_type}
                            </span>
                          </div>
                        </TableCell>
                        <TableCell className="capitalize">
                          {row.category}
                        </TableCell>
                        <TableCell>{row.owner_org ?? "—"}</TableCell>
                        <TableCell>
                          <AdapterStatusBadge status={status} />
                        </TableCell>
                        <TableCell>
                          <LastSyncCell iso={row.last_sync_at} />
                        </TableCell>
                        <TableCell className="text-right">
                          <Button variant="ghost" asChild>
                            <Link href={href} aria-label={`Abrir ${row.label}`}>
                              <RiArrowRightLine
                                className="size-4"
                                aria-hidden
                              />
                            </Link>
                          </Button>
                        </TableCell>
                      </TableRow>
                    )
                  })}
              </TableBody>
            </Table>
          </TableRoot>
        </div>
      )}
    </div>
  )
}
