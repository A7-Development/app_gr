// src/app/(app)/credito/workflows/page.tsx
//
// Listagem de workflows do modulo Credito.
// Mostra templates Strata (tenant_id=NULL) + workflows do tenant.
//
// Pattern canonico: `ListagemCrudCards` (ver
// `frontend/src/design-system/patterns/ListagemCrudCards.tsx`).
//
// PageHeader (title + info + subtitle + "+ Novo workflow")
// ↓
// EmptyState | (Card[FilterSearch + SegmentSwitch + counter] + grid de WorkflowCard)
// ↓
// DrillDownSheet de criar (?action=new) — CreateWorkflowForm dentro
// (delete: futuro — backend ainda nao tem DELETE definitivo)
//
// Divergencia justificada do pattern:
//   * EDIT NAO usa DrillDownSheet inline. Click no card REDIRECIONA pra
//     `/credito/workflows/{id}/editor` (editor visual React Flow).
//     Workflows sao entidades visuais — DrillDownSheet com graph embutido
//     nao caberia. Por isso nao consumimos `?selected=<id>` aqui.

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  RiAddLine,
  RiDeleteBinLine,
  RiFlowChart,
  RiMoreLine,
  RiPencilLine,
  RiShieldStarLine,
} from "@remixicon/react"
import { toast } from "sonner"

import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/tremor/DropdownMenu"
import {
  DrillDownSheet,
  EmptyState,
  FilterSearch,
  PageHeader,
  SegmentSwitch,
} from "@/design-system/components"
import { cardTokens } from "@/design-system/tokens/card"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"
import {
  credito,
  type WorkflowCreatePayload,
  type WorkflowDefinitionRead,
} from "@/lib/credito-client"

import { CreateWorkflowForm } from "./_components/CreateWorkflowForm"

type Segment = "todos" | "meus" | "strata" | "ativos" | "drafts"

export default function WorkflowsPage() {
  const router = useRouter()
  const queryClient = useQueryClient()
  const sp = useSearchParams()
  const action = sp.get("action") // "new" | null

  // ── Query ───────────────────────────────────────────────────────────────
  const { data: workflows, isLoading } = useQuery({
    queryKey: ["credito", "workflows"],
    queryFn: () => credito.workflows.list(),
  })

  // ── Filtros locais (search + segment) ───────────────────────────────────
  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState<Segment>("todos")

  const data = workflows ?? []

  const counts = React.useMemo(
    () => ({
      todos: data.length,
      meus: data.filter((w) => w.tenant_id !== null).length,
      strata: data.filter((w) => w.tenant_id === null).length,
      ativos: data.filter((w) => w.status === "active").length,
      drafts: data.filter((w) => w.status === "draft").length,
    }),
    [data],
  )

  const segmentFiltered = React.useMemo(() => {
    switch (segment) {
      case "meus":
        return data.filter((w) => w.tenant_id !== null)
      case "strata":
        return data.filter((w) => w.tenant_id === null)
      case "ativos":
        return data.filter((w) => w.status === "active")
      case "drafts":
        return data.filter((w) => w.status === "draft")
      default:
        return data
    }
  }, [data, segment])

  const visible = React.useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return segmentFiltered
    return segmentFiltered.filter(
      (w) =>
        w.name.toLowerCase().includes(term) ||
        (w.description ?? "").toLowerCase().includes(term),
    )
  }, [segmentFiltered, search])

  // ── Navegacao via URL (deep-linkavel) ───────────────────────────────────
  const setQuery = React.useCallback(
    (next: { action?: string | null }) => {
      const params = new URLSearchParams(sp.toString())
      if (next.action !== undefined) {
        if (next.action) params.set("action", next.action)
        else params.delete("action")
      }
      const qs = params.toString()
      router.push(qs ? `?${qs}` : "?")
    },
    [router, sp],
  )

  const openNew = React.useCallback(() => setQuery({ action: "new" }), [setQuery])
  const closeSheet = React.useCallback(() => setQuery({ action: null }), [setQuery])

  // ── Open editor (divergencia justificada do pattern: edit eh redirect) ──
  const openEditor = React.useCallback(
    (wf: WorkflowDefinitionRead) => {
      router.push(`/credito/workflows/${wf.id}/editor`)
    },
    [router],
  )

  // ── Mutations ───────────────────────────────────────────────────────────
  const createMutation = useMutation({
    mutationFn: (payload: WorkflowCreatePayload) => credito.workflows.create(payload),
    onSuccess: (newWorkflow) => {
      toast.success(`Workflow "${newWorkflow.name}" criado.`)
      queryClient.invalidateQueries({ queryKey: ["credito", "workflows"] })
      closeSheet()
      router.push(`/credito/workflows/${newWorkflow.id}/editor`)
    },
    onError: (e) => toast.error(`Erro ao criar workflow: ${(e as Error).message}`),
  })

  const isEmpty = !isLoading && data.length === 0
  const noResults = !isEmpty && visible.length === 0

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Fluxos"
        info="Templates Strata e fluxos do tenant. Cada análise executa um fluxo."
        subtitle="StrataFlow · Configuração"
        actions={
          <Button variant="primary" onClick={openNew} disabled={isLoading}>
            <RiAddLine className="mr-1 size-4" aria-hidden />
            Novo workflow
          </Button>
        }
      />

      {isLoading ? (
        <p className={tableTokens.cellSecondary}>Carregando...</p>
      ) : isEmpty ? (
        <EmptyState
          icon={RiFlowChart}
          title="Nenhum workflow ainda"
          description="Comece criando seu primeiro workflow ou clonando um template Strata."
          action={
            <Button variant="primary" onClick={openNew}>
              <RiAddLine className="mr-1 size-4" aria-hidden />
              Criar primeiro workflow
            </Button>
          }
        />
      ) : (
        <>
          {/* Faixa de filtros — mesma anatomia do DataTableShell */}
          <Card className="flex flex-wrap items-center gap-2 p-3">
            <FilterSearch
              value={search}
              onChange={(e) => setSearch(e.currentTarget.value)}
              onClear={() => setSearch("")}
              placeholder="Buscar por nome ou descricao..."
            />
            <SegmentSwitch
              options={[
                { value: "todos",  label: "Todos",            count: counts.todos },
                { value: "meus",   label: "Meus",             count: counts.meus },
                { value: "strata", label: "Templates Strata", count: counts.strata },
                { value: "ativos", label: "Ativos",           count: counts.ativos },
                { value: "drafts", label: "Drafts",           count: counts.drafts },
              ]}
              value={segment}
              onChange={setSegment}
            />
            <span
              className="ml-auto text-[11px] tabular-nums text-gray-500 dark:text-gray-400"
              aria-live="polite"
            >
              {visible.length === counts.todos
                ? `${visible.length} ${visible.length === 1 ? "workflow" : "workflows"}`
                : `${visible.length} de ${counts.todos}`}
            </span>
          </Card>

          {noResults ? (
            <div className="flex flex-col items-center justify-center gap-2 rounded border border-dashed border-gray-200 bg-white py-12 text-center dark:border-gray-800 dark:bg-gray-950">
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Nenhum resultado para esses filtros
              </p>
              <Button
                variant="ghost"
                onClick={() => {
                  setSearch("")
                  setSegment("todos")
                }}
              >
                Limpar filtros
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              {visible.map((wf) => (
                <WorkflowCard
                  key={wf.id}
                  workflow={wf}
                  onOpen={() => openEditor(wf)}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* Drawer: Novo */}
      <DrillDownSheet
        open={action === "new"}
        onClose={closeSheet}
        title="Novo workflow"
        size="md"
      >
        <div className="p-6">
          <CreateWorkflowForm
            templates={data}
            onSubmit={(payload) => createMutation.mutate(payload)}
            onCancel={closeSheet}
            submitting={createMutation.isPending}
          />
        </div>
      </DrillDownSheet>
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// WorkflowCard — anatomia segue o pattern ListagemCrudCards.
// Cores indigo (icone) e amber (badge Strata) sao IDENTIDADE, nao status.
// Modo Iteracao de Design ativo (CLAUDE.md banner) — apos a janela, estas
// classes serao promovidas a tokens em design-system/tokens/.
// ───────────────────────────────────────────────────────────────────────────

function WorkflowCard({
  workflow,
  onOpen,
}: {
  workflow: WorkflowDefinitionRead
  onOpen: () => void
}) {
  const isStrata = workflow.tenant_id === null
  const nodeCount = workflow.graph.nodes.length

  return (
    <Card
      onClick={onOpen}
      className={cx(
        "cursor-pointer transition-all hover:border-blue-500 hover:shadow-sm",
        "dark:hover:border-blue-500",
      )}
    >
      <div className={cx(cardTokens.body, "space-y-3")}>
        {/* Linha 1: avatar + badge Strata + dropdown */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex size-10 shrink-0 items-center justify-center rounded-md bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400">
            <RiFlowChart className="size-5" aria-hidden />
          </div>
          <div className="flex flex-1 flex-wrap items-center justify-end gap-2">
            {isStrata && (
              <span
                className={cx(
                  tableTokens.badge,
                  "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
                )}
                title="Template Strata — clonavel pelo tenant"
              >
                <RiShieldStarLine className="mr-1 inline size-3" aria-hidden />
                Template Strata
              </span>
            )}
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                className="size-7 shrink-0 p-0"
                aria-label={`Acoes de ${workflow.name}`}
                onClick={(e) => e.stopPropagation()}
              >
                <RiMoreLine className="size-4" aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" sideOffset={4}>
              <DropdownMenuItem onSelect={onOpen}>
                <RiPencilLine className="mr-2 size-4" aria-hidden />
                Abrir editor
              </DropdownMenuItem>
              {/* Excluir e Ativar versao virao quando endpoints estiverem prontos
                  (ver plan F.1.b e F.3 — DELETE /credito/workflows/{id} e
                  PUT /credito/workflows/{name}/active). */}
              {!isStrata && (
                <>
                  <DropdownMenuSeparator />
                  <DropdownMenuItem
                    disabled
                    title="Disponivel quando o backend expor DELETE"
                    className="text-red-600 focus:text-red-700 dark:text-red-400 dark:focus:text-red-300"
                  >
                    <RiDeleteBinLine className="mr-2 size-4" aria-hidden />
                    Excluir
                  </DropdownMenuItem>
                </>
              )}
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* Linha 2: titulo + descricao */}
        <div>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 line-clamp-1">
            {workflow.name}
          </h3>
          <p className={cx(tableTokens.cellSecondary, "mt-1 line-clamp-2")}>
            {workflow.description ?? "Sem descricao"}
          </p>
        </div>

        {/* Linha 3: metadados */}
        <div className={cx(tableTokens.cellSecondary, "flex items-center gap-3")}>
          <span>v{workflow.version}</span>
          <span aria-hidden>·</span>
          <span>
            {nodeCount} {nodeCount === 1 ? "no" : "nos"}
          </span>
          <span aria-hidden>·</span>
          <span className="capitalize">{workflow.status}</span>
        </div>
      </div>
    </Card>
  )
}
