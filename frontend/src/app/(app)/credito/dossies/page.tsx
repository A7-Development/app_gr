// src/app/(app)/credito/dossies/page.tsx
//
// Fila de análises (handoff Conceito D, frame D0 — 2026-06-10).
// Substitui a listagem DataTableShell de dossiês (decisão Ricardo
// 2026-06-10: a fila substitui a listagem, mesma rota).
//
// MOTIVO: diverge dos patterns de listagem canônicos (DataTableShell /
// ListagemComDrilldown) — o handoff da esteira define uma fila própria:
// filtros pill, tabela Cedente/Limite/Situação com 4 variantes de status,
// row "esperando por mim" destacada com pill azul + microlink "abrir →",
// rodapé de proveniência. Clicar numa linha entra no MODO FOCO da análise.

"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
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

// ─── Célula de situação (4 variantes do D0) ────────────────────────────────

function SituacaoCell({ r }: { r: DossierListItem }) {
  if (r.status === "finalized") {
    return (
      <span className="flex items-center gap-1.5 text-[11px] font-medium" style={{ color: "#059669" }}>
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
      <span
        className="inline-flex h-[18px] items-center rounded-full px-2 text-[10px] font-semibold leading-none"
        style={{ background: "rgba(59,130,246,0.1)", color: "#2563EB" }}
      >
        sua vez
      </span>
    )
  }
  if (r.next_action_kind === "agent_running") {
    return (
      <span className="flex items-center gap-1.5 text-[11px]" style={{ color: "#4F46E5" }}>
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

  const waitingCount = rows.filter((r) => r.status !== "finalized" && isWaitingForMe(r)).length
  const signedCount = rows.filter((r) => r.status === "finalized").length

  const filtered = React.useMemo(() => {
    if (filter === "esperando")
      return rows.filter((r) => r.status !== "finalized" && isWaitingForMe(r))
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

  const FILTERS: Array<{ key: FilterKey; label: string }> = [
    { key: "esperando", label: `Esperando por mim · ${waitingCount}` },
    { key: "todas", label: `Todas · ${rows.length}` },
    { key: "assinadas", label: signedCount > 0 ? `Assinadas · ${signedCount}` : "Assinadas" },
  ]

  const gridCols = isAdmin ? "1fr 90px 130px 36px" : "1fr 90px 130px"

  return (
    <div className="flex flex-col gap-4 px-5 pb-6 pt-4">
      {/* Header da fila */}
      <div className="flex h-12 items-center justify-between">
        <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-50">
          Fila de análises
        </h1>
        <Button asChild className="h-8">
          <Link href="/credito/dossies/novo">
            <RiAddLine className="mr-1 size-4" aria-hidden />
            Nova análise
          </Link>
        </Button>
      </div>

      {/* Filtros pill */}
      <div className="flex flex-wrap items-center gap-2">
        {FILTERS.map((f) => {
          const active = filter === f.key
          return (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              className={cx(
                "inline-flex h-[26px] items-center rounded-full border px-2.5 text-xs font-medium tabular-nums transition-colors duration-100",
                active
                  ? "border-blue-500 text-blue-600 dark:text-blue-400"
                  : "border-gray-200 text-gray-500 hover:bg-gray-50 dark:border-gray-800 dark:text-gray-400 dark:hover:bg-gray-900",
              )}
              style={active ? { background: "rgba(59,130,246,0.08)" } : undefined}
            >
              {f.label}
            </button>
          )
        })}
      </div>

      {/* Tabela da fila */}
      <div className="overflow-hidden rounded border border-gray-200 dark:border-gray-800">
        <div
          className="grid items-center gap-3 border-b border-gray-200 bg-gray-50 px-3.5 py-2 dark:border-gray-800 dark:bg-gray-925"
          style={{ gridTemplateColumns: gridCols }}
        >
          {["Cedente", "Limite", "Situação"].map((h) => (
            <span
              key={h}
              className="text-[10px] font-semibold uppercase tracking-[0.05em] text-gray-400 dark:text-gray-500"
            >
              {h}
            </span>
          ))}
          {isAdmin && <span />}
        </div>

        {isLoading && (
          <div className="px-3.5 py-8 text-center text-[13px] text-gray-400">
            Carregando a fila…
          </div>
        )}

        {error != null && !isLoading && (
          <div className="flex flex-col items-center gap-2 px-3.5 py-8">
            <p className="text-[13px] text-gray-500">Não foi possível carregar a fila.</p>
            <Button variant="secondary" className="h-8" onClick={() => refetch()}>
              Tentar novamente
            </Button>
          </div>
        )}

        {!isLoading && !error && filtered.length === 0 && (
          <div className="flex flex-col items-center gap-3 px-3.5 py-12">
            <RiHandCoinLine className="size-7 text-gray-300 dark:text-gray-700" aria-hidden />
            <p className="text-[13px] text-gray-500">
              {rows.length === 0
                ? "Nenhuma análise ainda — comece criando a primeira."
                : "Nada aqui com esse filtro."}
            </p>
            {rows.length === 0 && (
              <Button asChild className="h-8">
                <Link href="/credito/dossies/novo">
                  <RiAddLine className="mr-1 size-4" aria-hidden />
                  Nova análise
                </Link>
              </Button>
            )}
          </div>
        )}

        {!isLoading &&
          !error &&
          filtered.map((r) => {
            const waiting = r.status !== "finalized" && isWaitingForMe(r)
            const name = r.target_name || r.target_cnpj || "(sem identidade)"
            return (
              <div
                key={r.id}
                role="button"
                tabIndex={0}
                onClick={() => openRow(r)}
                onKeyDown={(e) => {
                  // So navega quando o teclado esta NA linha — Enter dentro
                  // do menu de acoes (portal borbulha) nao pode abrir o dossie.
                  if (e.target !== e.currentTarget) return
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault()
                    openRow(r)
                  }
                }}
                className={cx(
                  "group relative grid cursor-pointer items-center gap-3 border-b border-gray-100 px-3.5 py-2.5 transition-colors duration-100 last:border-b-0 dark:border-gray-900",
                  waiting ? "" : "hover:bg-gray-50 dark:hover:bg-gray-900/60",
                )}
                style={
                  waiting ? { background: "rgba(59,130,246,0.05)", gridTemplateColumns: gridCols } : { gridTemplateColumns: gridCols }
                }
              >
                {waiting && (
                  <span
                    className="absolute bottom-2 left-0 top-2 w-0.5 rounded-full bg-blue-500"
                    aria-hidden
                  />
                )}
                <span className="flex min-w-0 items-center gap-2.5">
                  <span
                    className={cx(
                      "truncate text-[13px] text-gray-900 dark:text-gray-100",
                      waiting ? "font-semibold" : "font-medium",
                    )}
                  >
                    {name}
                  </span>
                  {r.code && (
                    <span className="shrink-0 text-[11px] text-gray-400 tabular-nums dark:text-gray-500">
                      {r.code}
                    </span>
                  )}
                  <span
                    className={cx(
                      "flex shrink-0 items-center gap-0.5 text-[11px] font-medium text-blue-600 dark:text-blue-400",
                      waiting ? "" : "opacity-0 transition-opacity duration-100 group-hover:opacity-100",
                    )}
                  >
                    abrir
                    <RiArrowRightLine className="size-3" aria-hidden />
                  </span>
                </span>
                <span className="text-[12.5px] font-medium text-gray-700 tabular-nums dark:text-gray-300">
                  {formatBRLCompact(r.requested_amount)}
                </span>
                <SituacaoCell r={r} />
                {isAdmin && (
                  <span className="flex justify-end">
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
                      {/* O portal do Radix ainda BORBULHA eventos pela arvore
                          React — sem stopPropagation aqui o clique no item
                          dispara o onClick da linha (navega pro dossie) antes
                          do dialogo abrir. */}
                      <DropdownMenuContent
                        align="end"
                        sideOffset={4}
                        onClick={(e) => e.stopPropagation()}
                      >
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
                  </span>
                )}
              </div>
            )
          })}
      </div>

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
