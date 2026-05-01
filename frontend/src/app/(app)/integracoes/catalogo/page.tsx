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
// CLAUDE.md §6: listagem CRUD/admin pequena -> usa <DataTableShell>.
//

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import type { ColumnDef } from "@tanstack/react-table"
import { RiStackLine } from "@remixicon/react"

import { PageHeader } from "@/design-system/components/PageHeader"
import {
  AdapterStatusBadge,
  statusFrom,
} from "@/design-system/components/AdapterStatusBadge"
import { DataTableShell } from "@/design-system/components/DataTableShell"
import { LastSyncCell } from "@/design-system/components/LastSyncCell"
import {
  Select,
  SelectItem,
  SelectTrigger,
  SelectValue,
  SelectContent,
} from "@/components/tremor/Select"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"
import { useSources } from "@/lib/hooks/integracoes"
import type { Environment, SourceListItem } from "@/lib/api-client"

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
  const router = useRouter()
  const [environment, setEnvironment] = useEnvironment()
  const { data, isLoading, isError, error, refetch } = useSources(environment)

  const columns = React.useMemo<ColumnDef<SourceListItem>[]>(
    () => [
      {
        id: "fonte",
        accessorKey: "label",
        header: "Fonte",
        cell: ({ row }) => (
          <div className="flex flex-col">
            <span className={tableTokens.cellStrong}>{row.original.label}</span>
            <span className={cx(tableTokens.cellTextMono, tableTokens.cellSecondary)}>
              {row.original.source_type}
            </span>
          </div>
        ),
      },
      {
        id: "categoria",
        accessorKey: "category",
        header: "Categoria",
        cell: ({ row }) => (
          <span className={cx(tableTokens.cellText, "capitalize")}>
            {row.original.category}
          </span>
        ),
      },
      {
        id: "provedor",
        accessorKey: "owner_org",
        header: "Provedor",
        cell: ({ row }) =>
          row.original.owner_org ? (
            <span className={tableTokens.cellText}>{row.original.owner_org}</span>
          ) : (
            <span className={tableTokens.cellMuted}>—</span>
          ),
      },
      {
        id: "status",
        header: "Status",
        cell: ({ row }) => (
          <AdapterStatusBadge
            status={statusFrom(row.original.configured, row.original.enabled)}
          />
        ),
      },
      {
        id: "ultimo_sync",
        accessorKey: "last_sync_at",
        header: "Ultimo sync",
        cell: ({ row }) => <LastSyncCell iso={row.original.last_sync_at} />,
      },
    ],
    [],
  )

  const handleRowClick = React.useCallback(
    (row: SourceListItem) => {
      const href = `/integracoes/catalogo/${encodeURIComponent(
        row.source_type,
      )}?environment=${environment}`
      router.push(href)
    },
    [router, environment],
  )

  return (
    <div className="flex flex-col gap-6 px-12 py-6 pb-28">
      <PageHeader
        title="Integracoes · Catalogo"
        info={PAGE_INFO}
        actions={
          <div className="flex items-center gap-2">
            <span className={tableTokens.cellSecondary}>Ambiente</span>
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

      <DataTableShell<SourceListItem>
        data={data ?? []}
        columns={columns}
        loading={isLoading}
        error={isError ? (error as Error) : null}
        onRetry={() => refetch()}
        itemNoun={{ singular: "fonte", plural: "fontes" }}
        onRowClick={handleRowClick}
        emptyState={{
          icon: RiStackLine,
          title: "Nenhuma fonte cadastrada",
          description:
            "Nenhum registro em source_catalog. Cadastre fontes via migration antes de configurar credenciais.",
        }}
      />
    </div>
  )
}
