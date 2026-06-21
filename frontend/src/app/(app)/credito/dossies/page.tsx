// src/app/(app)/credito/dossies/page.tsx
//
// Fila de analises — modo TRIAGEM (preset `queue` do DataTableShell).
// Handoff "Tabela canonica" v2 (2026-06-20): a fila forkada (grid CSS) foi
// migrada para o motor canonico. Triagem = DataTableShell com filtros pill +
// coluna Situacao de workflow + linha "esperando por mim" destacada
// (bg azul + trilho azul a esquerda + nome 600 + microlink "abrir ->").
// Clicar numa linha entra no MODO FOCO da analise (onRowClick -> router.push).

"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import type { ColumnDef } from "@tanstack/react-table"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  RiAddLine,
  RiArrowRightLine,
  RiCheckboxCircleFill,
  RiDeleteBinLine,
  RiFileUploadLine,
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
import { AgentPulseDot } from "@/design-system/components"
import { DataTableShell } from "@/design-system/components/DataTableShell"
import { tableTokens } from "@/design-system/tokens/table"
import { fetchMe } from "@/lib/api-client"
import { credito, type DossierListItem } from "@/lib/credito-client"
import { cx } from "@/lib/utils"

// ─── Helpers ────────────────────────────────────────────────────────────────

/** "2500000" → "R$ 2,5 mi" (compacto pt-BR, tabular). */
function formatBRLCompact(raw: string | null): string {
  if (!raw) return "—"
  const v = Number(raw)
  if (!Number.isFinite(v) || v === 0) return "—"
  const fmt = (n: number) =>
    n.toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 1 })
  if (Math.abs(v) >= 1_000_000_000) return `R$ ${fmt(v / 1_000_000_000)} bi`
  if (Math.abs(v) >= 1_000_000) return `R$ ${fmt(v / 1_000_000)} mi`
  if (Math.abs(v) >= 1_000) return `R$ ${fmt(v / 1_000)} mil`
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
}

function relativeMinutes(iso: string | null): string | null {
  if (!iso) return null
  const ts = Date.parse(iso)
  if (Number.isNaN(ts)) return null
  const diffMin = Math.max(0, Math.round((Date.now() - ts) / 60_000))
  if (diffMin < 1) return "agora"
  if (diffMin < 60) return `há ${diffMin} min`
  const h = Math.round(diffMin / 60)
  if (h < 24) return `há ${h} h`
  return `há ${Math.round(h / 24)} d`
}

/** Linha "esperando por mim" — destacada na fila. */
function isWaitingForMe(r: DossierListItem): boolean {
  return r.next_action_kind === "human_input" || r.next_action_kind === "ready_to_finalize"
}

function waiting(r: DossierListItem): boolean {
  return r.status !== "finalized" && isWaitingForMe(r)
}

// ─── Célula de situação (4 variantes do workflow) ──────────────────────────

function SituacaoCell({ r }: { r: DossierListItem }) {
  if (r.status === "finalized") {
    return (
      <span className="flex items-center gap-1.5 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
        <RiCheckboxCircleFill className="size-3 shrink-0" aria-hidden />
        assinada
      </span>
    )
  }
  if (r.status === "cancelled") {
    return <span className="text-[11px] text-gray-400 dark:text-gray-500">cancelada</span>
  }
  if (isWaitingForMe(r)) {
    return (
      <span className="inline-flex h-[18px] items-center rounded-full bg-blue-50 px-2 text-[10px] font-semibold leading-none text-blue-700 dark:bg-blue-500/10 dark:text-blue-300">
        sua vez
      </span>
    )
  }
  if (r.next_action_kind === "agent_running") {
    return (
      <span className="flex items-center gap-1.5 text-[11px] text-indigo-600 dark:text-indigo-400">
        <AgentPulseDot size={6} />
        agente ativo
      </span>
    )
  }
  // blocked / aguardando insumo externo
  return (
    <span className="flex items-center gap-1.5 text-[11px] text-gray-500 dark:text-gray-400">
      <RiFileUploadLine className="size-3 shrink-0" aria-hidden />
      {r.next_action_label || "aguardando"}
    </span>
  )
}

// ─── Page ───────────────────────────────────────────────────────────────────

type FilterKey = "esperando" | "todas" | "assinadas"

export default function FilaAnalisesPage() {
  const router = useRouter()
  const queryClient = useQueryClient()

  const meQuery = useQuery({ queryKey: ["me"], queryFn: fetchMe, staleTime: 5 * 60 * 1000 })
  const isAdmin = meQuery.data?.user_permissions?.credito === "admin"

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["credito", "dossies"],
    queryFn: () => credito.dossies.list(),
  })

  const [filter, setFilter] = React.useState<FilterKey>("todas")
  const [pendingDelete, setPendingDelete] = React.useState<DossierListItem | null>(null)

  const deleteMut = useMutation({
    mutationFn: (dossierId: string) => credito.dossies.remove(dossierId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["credito", "dossies"] })
    },
  })

  const handleDelete = React.useCallback(async () => {
    if (!pendingDelete) return
    const label = pendingDelete.target_name || pendingDelete.target_cnpj || "análise"
    try {
      await deleteMut.mutateAsync(pendingDelete.id)
      toast.success(`Análise '${label}' excluída.`)
      setPendingDelete(null)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao excluir a análise.")
    }
  }, [deleteMut, pendingDelete])

  const rows = React.useMemo(() => data ?? [], [data])

  const waitingCount = rows.filter(waiting).length
  const signedCount = rows.filter((r) => r.status === "finalized").length

  const filtered = React.useMemo(() => {
    if (filter === "esperando") return rows.filter(waiting)
    if (filter === "assinadas") return rows.filter((r) => r.status === "finalized")
    return rows
  }, [rows, filter])

  const lastUpdated = React.useMemo(() => {
    const max = rows.reduce<string | null>(
      (acc, r) => (acc === null || r.updated_at > acc ? r.updated_at : acc),
      null,
    )
    return relativeMinutes(max)
  }, [rows])

  const openRow = React.useCallback(
    (row: DossierListItem) => {
      const target = row.next_node_id
        ? `/credito/dossies/${row.id}?step=${encodeURIComponent(row.next_node_id)}`
        : `/credito/dossies/${row.id}`
      router.push(target)
    },
    [router],
  )

  const pillOptions = [
    { value: "esperando", label: `Esperando por mim · ${waitingCount}` },
    { value: "todas", label: `Todas · ${rows.length}` },
    { value: "assinadas", label: signedCount > 0 ? `Assinadas · ${signedCount}` : "Assinadas" },
  ]

  // ── Colunas (modo Triagem) ───────────────────────────────────────────────
  const columns = React.useMemo<ColumnDef<DossierListItem, unknown>[]>(() => {
    const cols: ColumnDef<DossierListItem, unknown>[] = [
      {
        id: "cedente",
        header: "Cedente",
        cell: ({ row }) => {
          const r = row.original
          const w = waiting(r)
          const name = r.target_name || r.target_cnpj || "(sem identidade)"
          return (
            <span className="flex min-w-0 items-center gap-2.5">
              <span className={cx("truncate", tableTokens.cellText, w ? "font-semibold" : "font-medium")}>
                {name}
              </span>
              {r.code && (
                <span className={cx("shrink-0 tabular-nums", tableTokens.cellSecondary)}>
                  {r.code}
                </span>
              )}
              <span
                className={cx(
                  "flex shrink-0 items-center gap-0.5 text-[11px] font-medium text-blue-600 dark:text-blue-400",
                  w ? "" : "opacity-0 transition-opacity duration-100 group-hover:opacity-100",
                )}
              >
                abrir
                <RiArrowRightLine className="size-3" aria-hidden />
              </span>
            </span>
          )
        },
      },
      {
        id: "limite",
        header: "Limite",
        meta: { align: "right" },
        cell: ({ row }) => (
          <div className={cx("text-right font-medium", tableTokens.cellNumber)}>
            {formatBRLCompact(row.original.requested_amount)}
          </div>
        ),
      },
      {
        id: "situacao",
        header: "Situação",
        cell: ({ row }) => <SituacaoCell r={row.original} />,
      },
    ]
    if (isAdmin) {
      cols.push({
        id: "actions",
        header: "",
        meta: { align: "right" },
        cell: ({ row }) => {
          const r = row.original
          const name = r.target_name || r.target_cnpj || "análise"
          return (
            <div className="flex justify-end">
              <DropdownMenu modal={false}>
                <DropdownMenuTrigger asChild>
                  <Button
                    variant="ghost"
                    className="size-7 p-0 opacity-0 transition-opacity duration-100 group-hover:opacity-100 data-[state=open]:opacity-100"
                    aria-label={`Ações da análise ${name}`}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <RiMoreLine className="size-4" aria-hidden />
                  </Button>
                </DropdownMenuTrigger>
                {/* Portal do Radix borbulha eventos pela arvore React —
                    stopPropagation evita disparar o onRowClick (abrir dossie). */}
                <DropdownMenuContent align="end" sideOffset={4} onClick={(e) => e.stopPropagation()}>
                  <DropdownMenuItem
                    onSelect={() => setPendingDelete(r)}
                    onClick={(e) => e.stopPropagation()}
                    className="text-red-600 focus:text-red-700 dark:text-red-400 dark:focus:text-red-300"
                  >
                    <RiDeleteBinLine className="mr-2 size-4" aria-hidden />
                    Excluir
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          )
        },
      })
    }
    return cols
  }, [isAdmin])

  return (
    <div className="flex flex-col gap-4 px-5 pb-6 pt-4">
      {/* Header da fila */}
      <div className="flex h-12 items-center justify-between">
        <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-50">Fila de análises</h1>
        <Button asChild className="h-8">
          <Link href="/credito/dossies/novo">
            <RiAddLine className="mr-1 size-4" aria-hidden />
            Nova análise
          </Link>
        </Button>
      </div>

      {/* Tabela da fila — modo Triagem (preset queue) */}
      <DataTableShell<DossierListItem>
        data={filtered}
        columns={columns}
        loading={isLoading}
        error={error instanceof Error ? error : error ? String(error) : null}
        onRetry={refetch}
        pillFilters={{
          options: pillOptions,
          value: filter,
          onChange: (v) => setFilter(v as FilterKey),
          ariaLabel: "Filtrar a fila de análises",
        }}
        onRowClick={openRow}
        rowClassName={(r) =>
          cx(
            "group",
            waiting(r) &&
              "border-l-blue-500 bg-blue-50 hover:bg-blue-50 dark:bg-blue-500/[0.08] dark:hover:bg-blue-500/[0.08]",
          )
        }
        emptyState={{
          icon: RiHandCoinLine,
          title:
            rows.length === 0
              ? "Nenhuma análise ainda — comece criando a primeira."
              : "Nada aqui com esse filtro.",
          action:
            rows.length === 0 ? (
              <Button asChild className="h-8">
                <Link href="/credito/dossies/novo">
                  <RiAddLine className="mr-1 size-4" aria-hidden />
                  Nova análise
                </Link>
              </Button>
            ) : undefined,
        }}
      />

      {/* Rodapé de proveniência */}
      <p className="text-[11px] text-gray-400 dark:text-gray-500">
        Fonte: esteira de crédito{lastUpdated ? ` · última atividade ${lastUpdated}` : ""}
      </p>

      {/* Confirmação destrutiva — admin only */}
      <Dialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && !deleteMut.isPending && setPendingDelete(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir análise</DialogTitle>
            <DialogDescription>
              Esta ação remove permanentemente a análise{" "}
              <span className="font-medium text-gray-900 dark:text-gray-50">
                {pendingDelete?.target_name || pendingDelete?.target_cnpj || pendingDelete?.id}
              </span>
              , junto com todos os anexos, notas, consultas a bureaus, análises e histórico de
              execução do fluxo. Não pode ser desfeito.
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
            <Button variant="destructive" onClick={handleDelete} disabled={deleteMut.isPending}>
              <RiDeleteBinLine className="mr-1.5 size-4" aria-hidden />
              Excluir análise
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
