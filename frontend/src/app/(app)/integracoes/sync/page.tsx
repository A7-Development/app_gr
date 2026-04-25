"use client"

//
// Integracoes · Sync — agregado cross-source.
//
// Tabela com todas as fontes configuradas + ultimo sync + botao rapido
// "Sincronizar agora". O historico detalhado continua em /catalogo/[source_type].
//
// Hierarquia (CLAUDE.md 11.6):
//   L1 Integracoes > L2 Sync
//     L3 (TabNavigation): Todas | Configuradas | Habilitadas
//

import Link from "next/link"
import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"
import {
  RiArrowRightLine,
  RiLoader4Line,
  RiRefreshLine,
  RiStackLine,
} from "@remixicon/react"

import { PageHeader } from "@/design-system/components/PageHeader"
import {
  AdapterStatusBadge,
  statusFrom,
} from "@/design-system/components/AdapterStatusBadge"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { LastSyncCell } from "@/design-system/components/LastSyncCell"
import { Button } from "@/components/tremor/Button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import {
  TabNavigation,
  TabNavigationLink,
} from "@/components/tremor/TabNavigation"
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
import { integracoes } from "@/lib/api-client"
import type { Environment, SourceListItem } from "@/lib/api-client"

const PAGE_INFO =
  "Visao consolidada de sincronizacoes por fonte. Dispare ciclos manuais ou abra o detalhe para ajustar credenciais."

const TABS = [
  { key: "todas", label: "Todas" },
  { key: "configuradas", label: "Configuradas" },
  { key: "habilitadas", label: "Habilitadas" },
] as const
type TabKey = (typeof TABS)[number]["key"]

function filterByTab(rows: SourceListItem[], tab: TabKey): SourceListItem[] {
  if (tab === "configuradas") return rows.filter((r) => r.configured)
  if (tab === "habilitadas") return rows.filter((r) => r.configured && r.enabled)
  return rows
}

export default function SyncPage() {
  const sp = useSearchParams()
  const router = useRouter()
  const environment: Environment =
    sp.get("environment") === "sandbox" ? "sandbox" : "production"
  const activeTab: TabKey = (TABS.find((t) => t.key === sp.get("tab"))?.key ??
    "todas") as TabKey

  const { data, isLoading, isError, refetch } = useSources(environment)

  function setSearch(next: Record<string, string | null>) {
    const qs = new URLSearchParams(sp?.toString() ?? "")
    for (const [k, v] of Object.entries(next)) {
      if (v === null) qs.delete(k)
      else qs.set(k, v)
    }
    const s = qs.toString()
    router.replace(s ? `/integracoes/sync?${s}` : "/integracoes/sync")
  }

  const filtered = data ? filterByTab(data, activeTab) : []

  return (
    <div className="flex flex-col gap-6 px-12 py-6 pb-28">
      <PageHeader
        title="Integracoes · Sync"
        info={PAGE_INFO}
        breadcrumbs={[
          { label: "Integracoes", href: "/integracoes/catalogo" },
          { label: "Sync" },
        ]}
        actions={
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Ambiente
            </span>
            <Select
              value={environment}
              onValueChange={(v) =>
                setSearch({
                  environment: v === "production" ? null : v,
                })
              }
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
          title="Nao foi possivel carregar as fontes"
          action={
            <Button variant="secondary" onClick={() => refetch()}>
              Tentar novamente
            </Button>
          }
        />
      )}

      {!isError && (
        <>
          <TabNavigation>
            {TABS.map((t) => (
              <TabNavigationLink
                key={t.key}
                asChild
                active={activeTab === t.key}
              >
                <button
                  type="button"
                  onClick={() =>
                    setSearch({ tab: t.key === "todas" ? null : t.key })
                  }
                >
                  {t.label}
                </button>
              </TabNavigationLink>
            ))}
          </TabNavigation>

          {!isLoading && filtered.length === 0 && (
            <EmptyState
              icon={RiStackLine}
              title="Nenhuma fonte nesta visao"
              description={
                activeTab === "habilitadas"
                  ? "Nenhuma fonte habilitada no momento. Habilite no catalogo."
                  : activeTab === "configuradas"
                    ? "Nenhuma fonte configurada ainda."
                    : "O catalogo de fontes esta vazio."
              }
            />
          )}

          {(isLoading || filtered.length > 0) && (
            <div className="rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
              <TableRoot>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableHeaderCell>Fonte</TableHeaderCell>
                      <TableHeaderCell>Categoria</TableHeaderCell>
                      <TableHeaderCell>Status</TableHeaderCell>
                      <TableHeaderCell>Ultimo sync</TableHeaderCell>
                      <TableHeaderCell className="w-48 text-right">
                        Acoes
                      </TableHeaderCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {isLoading &&
                      Array.from({ length: 3 }).map((_, i) => (
                        <TableRow key={`skeleton-${i}`}>
                          <TableCell colSpan={5}>
                            <div className="h-6 w-full animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
                          </TableCell>
                        </TableRow>
                      ))}
                    {!isLoading &&
                      filtered.map((row) => (
                        <SyncRow
                          key={row.source_type}
                          row={row}
                          environment={environment}
                          onRefresh={() => refetch()}
                        />
                      ))}
                  </TableBody>
                </Table>
              </TableRoot>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function SyncRow({
  row,
  environment,
  onRefresh,
}: {
  row: SourceListItem
  environment: Environment
  onRefresh: () => void
}) {
  const [running, setRunning] = React.useState(false)

  async function handleSyncNow() {
    setRunning(true)
    try {
      await integracoes.sync(row.source_type, environment)
      toast.success(`Sync de ${row.label} concluido.`)
      onRefresh()
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Falha ao executar sync.",
      )
    } finally {
      setRunning(false)
    }
  }

  const detailHref = `/integracoes/catalogo/${encodeURIComponent(
    row.source_type,
  )}?environment=${environment}&tab=historico`

  return (
    <TableRow>
      <TableCell className="font-medium text-gray-900 dark:text-gray-50">
        <div className="flex flex-col">
          <span>{row.label}</span>
          <span className="font-mono text-xs text-gray-500 dark:text-gray-400">
            {row.source_type}
          </span>
        </div>
      </TableCell>
      <TableCell className="capitalize">{row.category}</TableCell>
      <TableCell>
        <AdapterStatusBadge status={statusFrom(row.configured, row.enabled)} />
      </TableCell>
      <TableCell>
        <LastSyncCell iso={row.last_sync_at} />
      </TableCell>
      <TableCell className="text-right">
        <div className="flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="secondary"
            disabled={!row.configured || running}
            onClick={handleSyncNow}
          >
            {running ? (
              <RiLoader4Line
                className="mr-1.5 size-4 animate-spin"
                aria-hidden
              />
            ) : (
              <RiRefreshLine className="mr-1.5 size-4" aria-hidden />
            )}
            Sync agora
          </Button>
          <Button variant="ghost" asChild>
            <Link href={detailHref} aria-label={`Abrir ${row.label}`}>
              <RiArrowRightLine className="size-4" aria-hidden />
            </Link>
          </Button>
        </div>
      </TableCell>
    </TableRow>
  )
}
