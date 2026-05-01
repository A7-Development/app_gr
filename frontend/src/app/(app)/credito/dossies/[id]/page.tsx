// src/app/(app)/credito/dossies/[id]/page.tsx
//
// Tela do dossie de credito — leitura do state real do workflow.
//
// Layout:
//   PageHeader (titulo + status + acoes)
//   ↓
//   Timeline do workflow (1 row por node_run, com status/duracao/custo)
//   ↓
//   Dialog automatico quando ha node_run em WAITING_INPUT — renderiza
//   DynamicForm com os fields do `human_input`/`human_review` para o
//   analista preencher e submeter.
//
// Polling: refetchInterval de 3s enquanto o run estiver RUNNING/PAUSED para
// pegar updates do background runner (futuro). Para agora, basta para
// reagir ao retorno do submit.

"use client"

import * as React from "react"
import { useParams, useRouter } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  RiAlertLine,
  RiArrowLeftLine,
  RiCheckboxCircleFill,
  RiCheckLine,
  RiErrorWarningLine,
  RiFilePdf2Line,
  RiLoader4Line,
  RiPauseCircleLine,
  RiPauseLine,
  RiPlayCircleLine,
  RiSkipForwardLine,
  type RemixiconComponentType,
} from "@remixicon/react"
import { toast } from "sonner"

import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/tremor/Dialog"
import { DynamicForm, PageHeader } from "@/design-system/components"
import { cardTokens } from "@/design-system/tokens/card"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"
import {
  credito,
  DOSSIER_STATUS_LABEL,
  DOSSIER_STATUS_TONE,
  type FormField,
  type NodeRunSummary,
  type NodeStatus,
} from "@/lib/credito-client"

// ─── Status visuals ─────────────────────────────────────────────────────

const NODE_STATUS_META: Record<
  NodeStatus,
  {
    label: string
    icon: RemixiconComponentType
    color: string // icon color
    tone: string  // badge bg+fg classes
  }
> = {
  pending: {
    label: "Pendente",
    icon: RiPauseCircleLine,
    color: "text-gray-400",
    tone: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
  },
  running: {
    label: "Executando",
    icon: RiLoader4Line,
    color: "text-blue-500 animate-spin",
    tone: "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300",
  },
  waiting_input: {
    label: "Aguardando input",
    icon: RiPauseLine,
    color: "text-amber-500",
    tone: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
  },
  completed: {
    label: "Completo",
    icon: RiCheckboxCircleFill,
    color: "text-emerald-500",
    tone: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
  },
  failed: {
    label: "Falhou",
    icon: RiErrorWarningLine,
    color: "text-red-500",
    tone: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
  },
  skipped: {
    label: "Skip",
    icon: RiSkipForwardLine,
    color: "text-gray-400",
    tone: "bg-gray-100 text-gray-500 dark:bg-gray-900 dark:text-gray-500",
  },
}

// ─── Page ───────────────────────────────────────────────────────────────

export default function DossieDetailPage() {
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const dossierId = params.id
  const queryClient = useQueryClient()

  const { data: state, isLoading } = useQuery({
    queryKey: ["credito", "dossie-state", dossierId],
    queryFn: () => credito.dossies.getState(dossierId),
    enabled: Boolean(dossierId),
    // Polling enquanto roda; para quando finalizar.
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data?.run) return false
      if (["completed", "failed", "cancelled"].includes(data.run.status)) {
        return false
      }
      return 3000
    },
  })

  const submitMutation = useMutation({
    mutationFn: (vars: { nodeId: string; values: Record<string, unknown> }) =>
      credito.dossies.submitNodeInput(dossierId, vars.nodeId, vars.values),
    onSuccess: () => {
      toast.success("Salvo. Workflow avancando.")
      queryClient.invalidateQueries({
        queryKey: ["credito", "dossie-state", dossierId],
      })
    },
    onError: (e) => toast.error(`Erro ao salvar: ${(e as Error).message}`),
  })

  if (isLoading || !state) {
    return (
      <div className="px-6 py-6">
        <p className={tableTokens.cellSecondary}>Carregando dossie...</p>
      </div>
    )
  }

  const { dossier, run, node_runs: nodeRuns, pending_node: pendingNode } = state

  return (
    <div className="px-6 py-6">
      <PageHeader
        title={`Dossie · ${dossier.target_name}`}
        subtitle={`CNPJ ${dossier.target_cnpj}`}
        actions={
          <div className="flex items-center gap-2">
            <span
              className={cx(
                tableTokens.badge,
                DOSSIER_STATUS_TONE[dossier.status],
              )}
            >
              {DOSSIER_STATUS_LABEL[dossier.status]}
            </span>
            <Button variant="ghost" disabled title="PDF disponivel quando finalizar">
              <RiFilePdf2Line className="size-4" aria-hidden />
              Exportar PDF
            </Button>
            <Button variant="ghost" onClick={() => router.push("/credito/dossies")}>
              <RiArrowLeftLine className="size-4" aria-hidden />
              Voltar
            </Button>
          </div>
        }
      />

      {run && (
        <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-gray-600 dark:text-gray-400">
          <span className="flex items-center gap-1">
            <RiPlayCircleLine className="size-4" aria-hidden />
            Run iniciado em{" "}
            {run.started_at
              ? new Date(run.started_at).toLocaleString("pt-BR")
              : "—"}
          </span>
          <span>·</span>
          <span>{nodeRuns.length} nos executados</span>
          {run.error_detail && (
            <span className="flex items-center gap-1 text-red-600 dark:text-red-400">
              <RiAlertLine className="size-4" aria-hidden />
              Erro: {run.error_detail}
            </span>
          )}
        </div>
      )}

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-[2fr_3fr]">
        <Timeline nodeRuns={nodeRuns} />
        <NodeDetail nodeRuns={nodeRuns} />
      </div>

      <PendingInputDialog
        pendingNode={pendingNode}
        triggerData={run?.trigger_data ?? {}}
        onSubmit={(nodeId, values) => submitMutation.mutate({ nodeId, values })}
        submitting={submitMutation.isPending}
      />
    </div>
  )
}

// ─── Timeline ──────────────────────────────────────────────────────────

function Timeline({ nodeRuns }: { nodeRuns: NodeRunSummary[] }) {
  if (nodeRuns.length === 0) {
    return (
      <Card>
        <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
          <RiLoader4Line
            className="size-8 animate-spin text-gray-400"
            aria-hidden
          />
          <p className={tableTokens.cellSecondary}>
            Aguardando o primeiro no executar...
          </p>
        </div>
      </Card>
    )
  }

  return (
    <Card>
      <div className={cardTokens.header}>
        <p className={cardTokens.headerTitle}>Timeline</p>
        <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
          Execucao do workflow
        </p>
      </div>
      <ol className="divide-y divide-gray-100 dark:divide-gray-900">
        {nodeRuns.map((nr) => {
          const meta = NODE_STATUS_META[nr.status]
          const Icon = meta.icon
          return (
            <li key={nr.id} className={cardTokens.listItem}>
              <Icon
                className={cx("mt-0.5 size-4 shrink-0", meta.color)}
                aria-hidden
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {nr.node_id}
                  </span>
                  <code className="rounded bg-gray-100 px-1 py-0.5 font-mono text-[10px] text-gray-600 dark:bg-gray-900 dark:text-gray-400">
                    {nr.node_type}
                  </code>
                  <span className={cx(tableTokens.badge, meta.tone)}>
                    {meta.label}
                  </span>
                </div>
                <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
                  {nr.duration_ms !== null && nr.duration_ms !== undefined && (
                    <>{(nr.duration_ms / 1000).toFixed(1)}s</>
                  )}
                  {Number(nr.cost_brl) > 0 && (
                    <>
                      {" "}· R$ {Number(nr.cost_brl).toFixed(4)}
                    </>
                  )}
                </p>
                {nr.error_detail && (
                  <p className="mt-1 text-xs text-red-600 dark:text-red-400">
                    {nr.error_detail}
                  </p>
                )}
              </div>
            </li>
          )
        })}
      </ol>
    </Card>
  )
}

// ─── Node detail ───────────────────────────────────────────────────────

function NodeDetail({ nodeRuns }: { nodeRuns: NodeRunSummary[] }) {
  // Show the latest completed node's output, or the failing one if any.
  const failed = nodeRuns.find((n) => n.status === "failed")
  const lastCompleted = [...nodeRuns]
    .reverse()
    .find((n) => n.status === "completed")
  const focus = failed ?? lastCompleted ?? nodeRuns[nodeRuns.length - 1]

  if (!focus) {
    return (
      <Card>
        <div className="flex items-center justify-center px-6 py-12">
          <p className={tableTokens.cellSecondary}>
            Outputs aparecem aqui conforme o workflow avanca.
          </p>
        </div>
      </Card>
    )
  }

  const focusMeta = NODE_STATUS_META[focus.status]
  const hasError = focus.status === "failed"
  const hasOutput = Object.keys(focus.output_data).length > 0

  return (
    <Card>
      <div className={cardTokens.header}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className={cardTokens.headerTitle}>Output: {focus.node_id}</p>
            <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
              <code className="font-mono">{focus.node_type}</code>
              {focus.duration_ms !== null && focus.duration_ms !== undefined && (
                <> · {(focus.duration_ms / 1000).toFixed(1)}s</>
              )}
              {Number(focus.cost_brl) > 0 && (
                <> · R$ {Number(focus.cost_brl).toFixed(4)}</>
              )}
            </p>
          </div>
          <span className={cx(tableTokens.badge, focusMeta.tone, "shrink-0")}>
            {focusMeta.label}
          </span>
        </div>
      </div>
      <div className={cardTokens.body}>
        {hasError && focus.error_detail && (
          <div className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-900 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200">
            <p className="font-medium">Erro</p>
            <p className="mt-1 font-mono">{focus.error_detail}</p>
          </div>
        )}
        {hasOutput ? (
          <pre className="overflow-x-auto rounded bg-gray-50 p-3 font-mono text-[11px] text-gray-700 dark:bg-gray-900 dark:text-gray-300">
            {JSON.stringify(focus.output_data, null, 2)}
          </pre>
        ) : (
          <p className={cx(tableTokens.cellSecondary)}>(sem output)</p>
        )}
      </div>
    </Card>
  )
}

// ─── Pending input dialog ─────────────────────────────────────────────

function PendingInputDialog({
  pendingNode,
  triggerData,
  onSubmit,
  submitting,
}: {
  pendingNode: NodeRunSummary | null
  triggerData: Record<string, unknown>
  onSubmit: (nodeId: string, values: Record<string, unknown>) => void
  submitting: boolean
}) {
  const isOpen = pendingNode !== null && pendingNode.node_type === "human_input"
  if (!isOpen || !pendingNode) return null

  const formDescriptor = pendingNode.output_data as {
    form_id?: string
    title?: string
    description?: string
    fields?: FormField[]
    submit_label?: string
  }

  const fields = formDescriptor.fields ?? []
  const title =
    formDescriptor.title ?? `Preencher input: ${pendingNode.node_id}`

  // Pre-fill: if a field's `key` matches a key in `triggerData`, use that
  // value as initial. Common case: cadastro_empresa.cnpj prefilled from
  // trigger_data.target_cnpj (and target_name for razao_social).
  const initialValues: Record<string, unknown> = {}
  for (const f of fields) {
    if (triggerData[f.key] !== undefined) {
      initialValues[f.key] = triggerData[f.key]
      continue
    }
    // Common aliases (helps the cadastro_empresa form).
    if (f.key === "cnpj" && triggerData.target_cnpj !== undefined) {
      initialValues.cnpj = triggerData.target_cnpj
    }
    if (f.key === "razao_social" && triggerData.target_name !== undefined) {
      initialValues.razao_social = triggerData.target_name
    }
  }

  return (
    <Dialog open={isOpen}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {formDescriptor.description && (
            <DialogDescription>{formDescriptor.description}</DialogDescription>
          )}
        </DialogHeader>

        {fields.length === 0 ? (
          <div className="py-4">
            <p className={tableTokens.cellSecondary}>
              Este no esta aguardando input mas nao tem fields configurados.
              Edite o workflow para adicionar fields no `config.fields` deste no.
            </p>
            <div className="mt-4 flex justify-end">
              <Button
                onClick={() => onSubmit(pendingNode.node_id, {})}
                isLoading={submitting}
              >
                <RiCheckLine className="size-4" aria-hidden />
                Continuar sem dados
              </Button>
            </div>
          </div>
        ) : (
          <DynamicForm
            fields={fields}
            initialValues={initialValues}
            onSubmit={(values) => onSubmit(pendingNode.node_id, values)}
            submitting={submitting}
            submitLabel={formDescriptor.submit_label ?? "Salvar e prosseguir"}
          />
        )}
      </DialogContent>
    </Dialog>
  )
}
