// src/app/(app)/credito/dossies/page.tsx
//
// Listagem de dossies de credito.
// Pattern canonico: <DataTableShell> (CLAUDE.md §6) — encapsula
// Card + FilterSearch + SegmentSwitch + counter + DataTable.
//
// Click numa row navega para /credito/dossies/{id} (tela do dossie real).

"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useQuery } from "@tanstack/react-query"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import { RiAddLine, RiHandCoinLine } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import {
  DataTableShell,
  DateCell,
  PageHeader,
} from "@/design-system/components"
import {
  credito,
  DOSSIER_STATUS_LABEL,
  DOSSIER_STATUS_TONE,
  type DossierListItem,
} from "@/lib/credito-client"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

// ─── Cells custom ─────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: DossierListItem["status"] }) {
  return (
    <span className={cx(tableTokens.badge, DOSSIER_STATUS_TONE[status])}>
      {DOSSIER_STATUS_LABEL[status]}
    </span>
  )
}

function CnpjCell({ value }: { value: string }) {
  return <span className={tableTokens.cellTextMono}>{value}</span>
}

function NameCell({ value }: { value: string }) {
  return <span className={tableTokens.cellStrong}>{value}</span>
}

function NullableCell({ value }: { value: string | null }) {
  if (!value) return <span className={tableTokens.cellMuted}>—</span>
  return <span className={tableTokens.cellText}>{value}</span>
}

// ─── Page ────────────────────────────────────────────────────────────────

const col = createColumnHelper<DossierListItem>()

export default function DossiesPage() {
  const router = useRouter()

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["credito", "dossies"],
    queryFn: () => credito.dossies.list(),
  })

  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState<string>("todos")

  const rows = data ?? []

  const columns = React.useMemo<ColumnDef<DossierListItem, unknown>[]>(
    () => [
      col.accessor("target_name", {
        header: "Empresa",
        size: 280,
        cell: (info) => <NameCell value={info.getValue()} />,
      }) as ColumnDef<DossierListItem, unknown>,
      col.accessor("target_cnpj", {
        header: "CNPJ",
        size: 180,
        cell: (info) => <CnpjCell value={info.getValue()} />,
      }) as ColumnDef<DossierListItem, unknown>,
      col.accessor("status", {
        header: "Status",
        size: 130,
        cell: (info) => <StatusBadge status={info.getValue()} />,
      }) as ColumnDef<DossierListItem, unknown>,
      col.accessor("operation_type", {
        header: "Operacao",
        size: 140,
        cell: (info) => <NullableCell value={info.getValue()} />,
      }) as ColumnDef<DossierListItem, unknown>,
      col.accessor("updated_at", {
        header: "Atualizado",
        size: 130,
        cell: (info) => <DateCell value={info.getValue()} />,
      }) as ColumnDef<DossierListItem, unknown>,
    ],
    [],
  )

  return (
    <div className="flex flex-col gap-6 px-6 pb-6 pt-5">
      <PageHeader
        title="Dossies de credito"
        subtitle="Analises de credito B2B em curso e finalizadas."
        actions={
          <Button asChild>
            <Link href="/credito/dossies/novo">
              <RiAddLine className="mr-1 size-4" aria-hidden />
              Novo dossie
            </Link>
          </Button>
        }
      />

      <DataTableShell<DossierListItem>
        data={rows}
        columns={columns}
        loading={isLoading}
        error={error as Error | null}
        onRetry={() => refetch()}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: "Buscar por empresa ou CNPJ...",
        }}
        segments={{
          value: segment,
          onChange: setSegment,
          options: [
            { value: "todos", label: "Todos", filter: () => true },
            { value: "draft", label: "Rascunho", filter: (r) => r.status === "draft" },
            { value: "collecting", label: "Coletando", filter: (r) => r.status === "collecting" },
            { value: "analyzing", label: "Analisando", filter: (r) => r.status === "analyzing" },
            { value: "review", label: "Revisao", filter: (r) => r.status === "review" },
            { value: "finalized", label: "Finalizado", filter: (r) => r.status === "finalized" },
          ],
        }}
        itemNoun={{ singular: "dossie", plural: "dossies" }}
        onRowClick={(row) => router.push(`/credito/dossies/${row.id}`)}
        emptyState={{
          icon: RiHandCoinLine,
          title: "Nenhum dossie ainda",
          description:
            "Comece criando seu primeiro dossie de analise de credito.",
          action: (
            <Button asChild>
              <Link href="/credito/dossies/novo">
                <RiAddLine className="mr-1 size-4" aria-hidden />
                Criar primeiro dossie
              </Link>
            </Button>
          ),
        }}
      />
    </div>
  )
}
