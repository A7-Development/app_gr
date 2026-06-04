// src/app/(app)/credito/dossies/page.tsx
//
// Listagem de dossies de credito.
// Pattern canonico: <DataTableShell> (CLAUDE.md §6) — encapsula
// Card + FilterSearch + SegmentSwitch + counter + DataTable.
//
// Click numa row navega para /credito/dossies/{id} (tela do dossie real).
//
// Gate de admin: a coluna de acoes (DropdownMenu com Excluir) so renderiza
// quando `user_permissions.credito === "admin"`. Backend valida sempre via
// `require_module(Module.CREDITO, Permission.ADMIN)` no DELETE — defense in depth.

"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import {
  RiAddLine,
  RiArticleLine,
  RiDeleteBinLine,
  RiHandCoinLine,
  RiMoreLine,
} from "@remixicon/react"
import { toast } from "sonner"

import { Button } from "@/components/tremor/Button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/tremor/Dialog"
import { Divider } from "@/components/tremor/Divider"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/tremor/DropdownMenu"
import {
  DataTableShell,
  DateCell,
  NextActionCell,
  PageHeader,
  StepProgressCell,
} from "@/design-system/components"
import {
  credito,
  DOSSIER_STATUS_LABEL,
  DOSSIER_STATUS_TONE,
  type DossierListItem,
} from "@/lib/credito-client"
import { fetchMe } from "@/lib/api-client"
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

function CnpjCell({ value }: { value: string | null }) {
  if (!value) return <span className={tableTokens.cellMuted}>—</span>
  return <span className={tableTokens.cellTextMono}>{value}</span>
}

function NameCell({ value }: { value: string | null }) {
  if (!value)
    return <span className={tableTokens.cellMuted}>(sem identidade)</span>
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
  const queryClient = useQueryClient()

  // Gate de admin: /auth/me ja foi chamado pelo AuthGuard, aqui so reusamos
  // a query (staleTime alto). Backend continua sendo a fonte da verdade.
  const meQuery = useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    staleTime: 5 * 60 * 1000,
  })
  const isAdmin = meQuery.data?.user_permissions?.credito === "admin"

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["credito", "dossies"],
    queryFn: () => credito.dossies.list(),
  })

  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState<string>("todos")

  // Confirmacao de delete: dossier inteiro em estado local (precisamos do
  // nome / cnpj pra exibir no Dialog). Fora da URL — operacao efemera.
  const [pendingDelete, setPendingDelete] =
    React.useState<DossierListItem | null>(null)

  const deleteMut = useMutation({
    mutationFn: (dossierId: string) => credito.dossies.remove(dossierId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["credito", "dossies"] })
    },
  })

  const handleDelete = React.useCallback(async () => {
    if (!pendingDelete) return
    const label = pendingDelete.target_name || pendingDelete.target_cnpj || "dossie"
    try {
      await deleteMut.mutateAsync(pendingDelete.id)
      toast.success(`Dossie '${label}' excluido.`)
      setPendingDelete(null)
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Falha ao excluir dossie.",
      )
    }
  }, [deleteMut, pendingDelete])

  const rows = data ?? []

  const columns = React.useMemo<ColumnDef<DossierListItem, unknown>[]>(
    () => {
      const base: ColumnDef<DossierListItem, unknown>[] = [
        col.accessor("target_name", {
          header: "Empresa",
          size: 240,
          cell: (info) => <NameCell value={info.getValue()} />,
        }) as ColumnDef<DossierListItem, unknown>,
        col.accessor("target_cnpj", {
          header: "CNPJ",
          size: 160,
          cell: (info) => <CnpjCell value={info.getValue()} />,
        }) as ColumnDef<DossierListItem, unknown>,
        col.accessor("status", {
          header: "Status",
          size: 120,
          cell: (info) => <StatusBadge status={info.getValue()} />,
        }) as ColumnDef<DossierListItem, unknown>,
        col.display({
          id: "progresso",
          header: "Progresso",
          size: 140,
          cell: (info) => {
            const r = info.row.original
            const state =
              r.status === "finalized"
                ? "finalized"
                : r.status === "draft"
                  ? "draft"
                  : "in_progress"
            return (
              <StepProgressCell
                completed={r.completed_steps}
                total={r.total_steps}
                state={state}
                tooltip={r.next_action_label}
              />
            )
          },
        }) as ColumnDef<DossierListItem, unknown>,
        col.display({
          id: "proxima_acao",
          header: "Proxima acao",
          size: 180,
          cell: (info) => {
            const r = info.row.original
            return (
              <NextActionCell
                kind={r.next_action_kind}
                label={r.next_action_label}
              />
            )
          },
        }) as ColumnDef<DossierListItem, unknown>,
        col.accessor("operation_type", {
          header: "Operacao",
          size: 130,
          cell: (info) => <NullableCell value={info.getValue()} />,
        }) as ColumnDef<DossierListItem, unknown>,
        col.accessor("updated_at", {
          header: "Atualizado",
          size: 120,
          cell: (info) => <DateCell value={info.getValue()} />,
        }) as ColumnDef<DossierListItem, unknown>,
      ]

      base.push(
        col.display({
          id: "ver_parecer",
          header: "",
          size: 44,
          cell: ({ row }) => {
            if (row.original.status !== "finalized") return null
            const label =
              row.original.target_name ?? row.original.target_cnpj ?? row.original.id
            return (
              <div className="flex justify-end">
                <Button
                  variant="ghost"
                  className="size-7 p-0"
                  aria-label={`Ver parecer de ${label}`}
                  title="Ver parecer"
                  onClick={(e) => {
                    e.stopPropagation()
                    router.push(`/credito/dossies/${row.original.id}`)
                  }}
                >
                  <RiArticleLine className="size-4" aria-hidden />
                </Button>
              </div>
            )
          },
        }) as ColumnDef<DossierListItem, unknown>,
      )

      if (isAdmin) {
        base.push(
          col.display({
            id: "actions",
            header: "",
            size: 56,
            cell: ({ row }) => (
              <div className="flex justify-end">
                {/* modal={false}: a tabela tem onRowClick (navega pro dossie).
                    Com o dropdown modal (default Radix), o clique no item
                    "Excluir" fazia CLICK-THROUGH pra linha embaixo -> navegava
                    pro dossie em vez de abrir o dialog. modal={false} corta o
                    replay do evento. */}
                <DropdownMenu modal={false}>
                  <DropdownMenuTrigger asChild>
                    <Button
                      variant="ghost"
                      className="size-7 p-0"
                      aria-label={`Acoes do dossie ${row.original.target_name ?? row.original.id}`}
                      onClick={(e) => e.stopPropagation()}
                    >
                      <RiMoreLine className="size-4" aria-hidden />
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end" sideOffset={4}>
                    <DropdownMenuItem
                      onSelect={() => setPendingDelete(row.original)}
                      className="text-red-600 focus:text-red-700 dark:text-red-400 dark:focus:text-red-300"
                    >
                      <RiDeleteBinLine className="mr-2 size-4" aria-hidden />
                      Excluir
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </div>
            ),
          }) as ColumnDef<DossierListItem, unknown>,
        )
      }

      return base
    },
    [isAdmin],
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
            {
              value: "aguardando_voce",
              label: "Aguardando voce",
              filter: (r) => r.next_action_kind === "human_input",
            },
            { value: "draft", label: "Rascunho", filter: (r) => r.status === "draft" },
            { value: "collecting", label: "Coletando", filter: (r) => r.status === "collecting" },
            { value: "analyzing", label: "Analisando", filter: (r) => r.status === "analyzing" },
            { value: "review", label: "Revisao", filter: (r) => r.status === "review" },
            { value: "finalized", label: "Finalizado", filter: (r) => r.status === "finalized" },
          ],
        }}
        itemNoun={{ singular: "dossie", plural: "dossies" }}
        onRowClick={(row) => {
          // Deep-link no proximo step actionable quando ha um — usuario retoma do
          // ponto exato em que parou. Sem next_node_id, abre o topo do dossie.
          const target = row.next_node_id
            ? `/credito/dossies/${row.id}?step=${encodeURIComponent(row.next_node_id)}`
            : `/credito/dossies/${row.id}`
          router.push(target)
        }}
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

      {/* Confirmacao destrutiva — admin only */}
      <Dialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && !deleteMut.isPending && setPendingDelete(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir dossie</DialogTitle>
            <DialogDescription>
              Esta acao remove permanentemente o dossie{" "}
              <span className="font-medium text-gray-900 dark:text-gray-50">
                {pendingDelete?.target_name ||
                  pendingDelete?.target_cnpj ||
                  pendingDelete?.id}
              </span>
              , junto com todos os anexos, notas, consultas a bureaus,
              analises e historico de execucao do workflow. Nao pode ser
              desfeito.
            </DialogDescription>
          </DialogHeader>

          <Divider />

          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => setPendingDelete(null)}
              disabled={deleteMut.isPending}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleteMut.isPending}
            >
              <RiDeleteBinLine className="mr-1.5 size-4" aria-hidden />
              Excluir dossie
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
