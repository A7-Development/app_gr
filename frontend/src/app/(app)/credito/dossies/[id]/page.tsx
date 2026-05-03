// src/app/(app)/credito/dossies/[id]/page.tsx
//
// Página de execução de análise (StrataFlow). Reformulada na Fase 1 como
// um wizard guiado: o analista vê TODAS as etapas do fluxo (passadas,
// atual e futuras) num stepper vertical à esquerda, e o painel direito
// é contextual à etapa atual.
//
// Estados do painel direito:
// - human_input atual + WAITING_INPUT → form embedded (não dialog modal)
// - bureau_query / specialist_agent atual + RUNNING → status "consultando"
// - última etapa completed → preview do output
// - workflow finalizou → OpinionCard renderizado acima do wizard
//
// Polling: refetchInterval de 3s enquanto run está RUNNING ou PAUSED.

"use client"

import * as React from "react"
import { useParams, useRouter } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  RiAlertLine,
  RiArrowLeftLine,
  RiCheckLine,
  RiErrorWarningLine,
  RiFilePdf2Line,
  RiLoader4Line,
  RiPlayCircleLine,
  type RemixiconComponentType,
} from "@remixicon/react"
import { toast } from "sonner"

import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import { DynamicForm, PageHeader } from "@/design-system/components"
import { cardTokens } from "@/design-system/tokens/card"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"
import {
  credito,
  DOSSIER_STATUS_LABEL,
  DOSSIER_STATUS_TONE,
  type EdgeSpec,
  type FormField,
  type NodeRunSummary,
  type NodeSpec,
  type NodeStatus,
} from "@/lib/credito-client"

import {
  OpinionCard,
  type IndebtednessAnalysis,
  type OpinionDraft,
} from "./_components/OpinionCard"

// ─── Step model ─────────────────────────────────────────────────────────

type StepState = "pending" | "running" | "waiting_input" | "completed" | "failed" | "skipped"

type Step = {
  id: string
  type: string
  label: string
  state: StepState
  duration_ms?: number | null
  cost_brl?: number
  error_detail?: string | null
  // Backing data (when state != pending):
  output?: Record<string, unknown>
  input?: Record<string, unknown>
  // For waiting_input:
  formDescriptor?: {
    form_id?: string
    title?: string
    description?: string
    fields?: FormField[]
    submit_label?: string
  }
}

const STEP_STATE_META: Record<
  StepState,
  { label: string; bullet: string; tone: string; icon: RemixiconComponentType }
> = {
  pending: {
    label: "Pendente",
    bullet: "border-gray-300 bg-white text-gray-400 dark:border-gray-700 dark:bg-gray-950",
    tone: "text-gray-500 dark:text-gray-400",
    icon: RiPlayCircleLine,
  },
  running: {
    label: "Em execução",
    bullet:
      "border-blue-500 bg-blue-50 text-blue-600 dark:border-blue-500 dark:bg-blue-500/10 dark:text-blue-300",
    tone: "text-blue-700 dark:text-blue-300",
    icon: RiLoader4Line,
  },
  waiting_input: {
    label: "Aguardando você",
    bullet:
      "border-amber-500 bg-amber-50 text-amber-700 dark:border-amber-500 dark:bg-amber-500/10 dark:text-amber-300",
    tone: "text-amber-700 dark:text-amber-300",
    icon: RiAlertLine,
  },
  completed: {
    label: "Concluído",
    bullet:
      "border-emerald-500 bg-emerald-500 text-white dark:border-emerald-500 dark:bg-emerald-500 dark:text-white",
    tone: "text-emerald-700 dark:text-emerald-400",
    icon: RiCheckLine,
  },
  failed: {
    label: "Falhou",
    bullet:
      "border-red-500 bg-red-500 text-white dark:border-red-500 dark:bg-red-500 dark:text-white",
    tone: "text-red-700 dark:text-red-400",
    icon: RiErrorWarningLine,
  },
  skipped: {
    label: "Pulado",
    bullet: "border-gray-300 bg-gray-100 text-gray-400 dark:border-gray-800 dark:bg-gray-900",
    tone: "text-gray-500 dark:text-gray-500",
    icon: RiPlayCircleLine,
  },
}

const NODE_TYPE_LABEL: Record<string, string> = {
  trigger: "Início",
  human_input: "Coleta humana",
  bureau_query: "Consulta a bureau",
  specialist_agent: "Análise por agente IA",
  document_request: "Solicitação de documento",
  document_extractor: "Extração de documento",
  conditional_branch: "Decisão condicional",
  human_review: "Revisão humana",
  http_request: "Requisição HTTP",
  output_generator: "Saída final",
  notification: "Notificação",
}

// ─── Helpers ────────────────────────────────────────────────────────────

/**
 * Faz topological order do grafo (Kahn) pra dar uma sequência estável às
 * etapas — espelha a ordem de execução do engine no backend.
 */
function topologicalOrder(nodes: NodeSpec[], edges: EdgeSpec[]): string[] {
  const inDegree = new Map<string, number>()
  const adjacency = new Map<string, string[]>()
  for (const n of nodes) {
    inDegree.set(n.id, 0)
    adjacency.set(n.id, [])
  }
  for (const e of edges) {
    if (!inDegree.has(e.source) || !inDegree.has(e.target)) continue
    inDegree.set(e.target, (inDegree.get(e.target) ?? 0) + 1)
    adjacency.get(e.source)!.push(e.target)
  }
  const queue: string[] = []
  inDegree.forEach((deg, id) => {
    if (deg === 0) queue.push(id)
  })
  queue.sort()
  const result: string[] = []
  while (queue.length > 0) {
    const id = queue.shift()!
    result.push(id)
    for (const next of adjacency.get(id) ?? []) {
      inDegree.set(next, inDegree.get(next)! - 1)
      if (inDegree.get(next) === 0) {
        queue.push(next)
        queue.sort()
      }
    }
  }
  // Safety: append any disconnected nodes the topological pass missed.
  for (const n of nodes) {
    if (!result.includes(n.id)) result.push(n.id)
  }
  return result
}

function buildSteps(
  graph: { nodes: NodeSpec[]; edges: EdgeSpec[] },
  nodeRuns: NodeRunSummary[],
  pendingNode: NodeRunSummary | null,
): Step[] {
  const order = topologicalOrder(graph.nodes, graph.edges)
  const nodeRunByNodeId = new Map<string, NodeRunSummary>()
  for (const nr of nodeRuns) nodeRunByNodeId.set(nr.node_id, nr)

  return order.map((nodeId) => {
    const spec = graph.nodes.find((n) => n.id === nodeId)
    if (!spec) {
      return {
        id: nodeId,
        type: "unknown",
        label: nodeId,
        state: "pending" as StepState,
      }
    }
    const label =
      spec.label ?? NODE_TYPE_LABEL[spec.type] ?? spec.type ?? spec.id
    const run = nodeRunByNodeId.get(nodeId)

    if (!run) {
      return { id: nodeId, type: spec.type, label, state: "pending" }
    }

    const state: StepState = stepStateFromRun(run, pendingNode)
    return {
      id: nodeId,
      type: spec.type,
      label,
      state,
      duration_ms: run.duration_ms,
      cost_brl: Number(run.cost_brl) || 0,
      error_detail: run.error_detail,
      output: run.output_data,
      input: run.input_data,
      formDescriptor:
        state === "waiting_input"
          ? (run.output_data as Step["formDescriptor"])
          : undefined,
    }
  })
}

function stepStateFromRun(
  run: NodeRunSummary,
  pendingNode: NodeRunSummary | null,
): StepState {
  if (pendingNode && pendingNode.id === run.id) return "waiting_input"
  switch (run.status) {
    case "waiting_input":
      return "waiting_input"
    case "running":
      return "running"
    case "completed":
      return "completed"
    case "failed":
      return "failed"
    case "skipped":
      return "skipped"
    default:
      return "pending"
  }
}

function pickFocusStep(steps: Step[]): Step | null {
  // Priority: waiting_input > failed > running > last completed > first.
  return (
    steps.find((s) => s.state === "waiting_input") ??
    steps.find((s) => s.state === "failed") ??
    steps.find((s) => s.state === "running") ??
    [...steps].reverse().find((s) => s.state === "completed") ??
    steps[0] ??
    null
  )
}

function extractAgentOutput<T>(
  steps: Step[],
  agentName: string,
): T | null {
  const match = steps.find(
    (s) =>
      s.state === "completed" &&
      s.type === "specialist_agent" &&
      ((s.input as { agent?: string } | undefined)?.agent === agentName ||
        s.id === agentName ||
        s.id === agentName.replace(/_analyst$/, "") ||
        s.id === agentName.replace(/_writer$/, "")),
  )
  if (!match || !match.output || Object.keys(match.output).length === 0) {
    return null
  }
  return match.output as T
}

// ─── Page ───────────────────────────────────────────────────────────────

export default function AnaliseDetailPage() {
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const dossierId = params.id
  const queryClient = useQueryClient()

  const { data: state, isLoading } = useQuery({
    queryKey: ["credito", "dossie-state", dossierId],
    queryFn: () => credito.dossies.getState(dossierId),
    enabled: Boolean(dossierId),
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data?.run) return false
      if (["completed", "failed", "cancelled"].includes(data.run.status)) {
        return false
      }
      return 3000
    },
  })

  const { data: workflow } = useQuery({
    queryKey: [
      "credito",
      "workflow-def",
      state?.dossier?.workflow_definition_id,
    ],
    queryFn: () =>
      credito.workflows.get(state!.dossier.workflow_definition_id),
    enabled: Boolean(state?.dossier?.workflow_definition_id),
  })

  const submitMutation = useMutation({
    mutationFn: (vars: { nodeId: string; values: Record<string, unknown> }) =>
      credito.dossies.submitNodeInput(dossierId, vars.nodeId, vars.values),
    onSuccess: () => {
      toast.success("Salvo. Análise prossegue.")
      queryClient.invalidateQueries({
        queryKey: ["credito", "dossie-state", dossierId],
      })
    },
    onError: (e) => toast.error(`Erro ao salvar: ${(e as Error).message}`),
  })

  if (isLoading || !state) {
    return (
      <div className="px-6 py-6">
        <p className={tableTokens.cellSecondary}>Carregando análise…</p>
      </div>
    )
  }

  const { dossier, run, node_runs: nodeRuns, pending_node: pendingNode } = state

  const steps: Step[] = workflow?.graph
    ? buildSteps(workflow.graph, nodeRuns, pendingNode)
    : nodeRuns.map((nr) => ({
        id: nr.node_id,
        type: nr.node_type,
        label: nr.node_id,
        state: stepStateFromRun(nr, pendingNode),
        duration_ms: nr.duration_ms,
        cost_brl: Number(nr.cost_brl) || 0,
        error_detail: nr.error_detail,
        output: nr.output_data,
        input: nr.input_data,
      }))

  const focus = pickFocusStep(steps)
  const opinion = extractAgentOutput<OpinionDraft>(steps, "opinion_writer")
  const indebtedness = extractAgentOutput<IndebtednessAnalysis>(
    steps,
    "indebtedness_analyst",
  )

  const titleLabel =
    dossier.target_name ??
    (dossier.target_cnpj ? `CNPJ ${dossier.target_cnpj}` : "Análise sem identidade")
  const subtitle = dossier.target_cnpj
    ? `StrataFlow · CNPJ ${dossier.target_cnpj}`
    : "StrataFlow · análise iniciada"

  return (
    <div className="flex flex-col gap-6 px-6 py-6 pb-20">
      <PageHeader
        title={`Análise · ${titleLabel}`}
        subtitle={subtitle}
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
            <Button variant="ghost" disabled title="PDF disponível quando finalizar">
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
        <div className="flex flex-wrap items-center gap-3 text-xs text-gray-600 dark:text-gray-400">
          <span className="flex items-center gap-1">
            <RiPlayCircleLine className="size-4" aria-hidden />
            Iniciada em{" "}
            {run.started_at
              ? new Date(run.started_at).toLocaleString("pt-BR")
              : "—"}
          </span>
          <span>·</span>
          <span>
            {steps.filter((s) => s.state === "completed").length} de {steps.length} etapas concluídas
          </span>
          {run.error_detail && (
            <span className="flex items-center gap-1 text-red-600 dark:text-red-400">
              <RiAlertLine className="size-4" aria-hidden />
              {run.error_detail}
            </span>
          )}
        </div>
      )}

      {opinion && (
        <OpinionCard opinion={opinion} indebtedness={indebtedness} />
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[320px_1fr]">
        <Stepper steps={steps} focusId={focus?.id ?? null} />
        <FocusPanel
          step={focus}
          submitting={submitMutation.isPending}
          onSubmit={(nodeId, values) =>
            submitMutation.mutate({ nodeId, values })
          }
          triggerData={run?.trigger_data ?? {}}
        />
      </div>
    </div>
  )
}

// ─── Stepper ────────────────────────────────────────────────────────────

function Stepper({
  steps,
  focusId,
}: {
  steps: Step[]
  focusId: string | null
}) {
  return (
    <Card>
      <div className={cardTokens.header}>
        <p className={cardTokens.headerTitle}>Etapas do fluxo</p>
        <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
          {steps.length} {steps.length === 1 ? "etapa" : "etapas"} no total
        </p>
      </div>
      <ol className="relative px-4 py-4">
        {steps.map((step, idx) => {
          const meta = STEP_STATE_META[step.state]
          const Icon = meta.icon
          const isLast = idx === steps.length - 1
          const isFocus = step.id === focusId
          return (
            <li
              key={step.id}
              className={cx(
                "relative flex gap-3 pb-5",
                isLast && "pb-0",
              )}
            >
              {!isLast && (
                <span
                  aria-hidden
                  className="absolute left-[14px] top-7 h-[calc(100%-12px)] w-px bg-gray-200 dark:bg-gray-800"
                />
              )}
              <div
                className={cx(
                  "relative z-10 flex size-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold",
                  meta.bullet,
                )}
                aria-hidden
              >
                {step.state === "completed" || step.state === "failed" ? (
                  <Icon className="size-3.5" />
                ) : step.state === "running" ? (
                  <Icon className="size-3.5 animate-spin" />
                ) : (
                  idx + 1
                )}
              </div>
              <div className="min-w-0 flex-1 pt-0.5">
                <p
                  className={cx(
                    "text-sm font-medium",
                    isFocus
                      ? "text-gray-900 dark:text-gray-50"
                      : "text-gray-700 dark:text-gray-300",
                  )}
                >
                  {step.label}
                </p>
                <p className={cx("mt-0.5 text-xs", meta.tone)}>
                  {meta.label}
                  {step.duration_ms != null && step.state === "completed" && (
                    <> · {(step.duration_ms / 1000).toFixed(1)}s</>
                  )}
                  {step.cost_brl != null && step.cost_brl > 0 && (
                    <> · R$ {step.cost_brl.toFixed(4)}</>
                  )}
                </p>
                {step.error_detail && (
                  <p className="mt-1 text-xs text-red-600 dark:text-red-400">
                    {step.error_detail}
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

// ─── Focus panel ────────────────────────────────────────────────────────

function FocusPanel({
  step,
  submitting,
  onSubmit,
  triggerData,
}: {
  step: Step | null
  submitting: boolean
  onSubmit: (nodeId: string, values: Record<string, unknown>) => void
  triggerData: Record<string, unknown>
}) {
  if (!step) {
    return (
      <Card>
        <div className="flex items-center justify-center px-6 py-12">
          <p className={tableTokens.cellSecondary}>
            Aguardando o fluxo iniciar…
          </p>
        </div>
      </Card>
    )
  }

  if (step.state === "waiting_input") {
    return <WaitingInputPanel step={step} submitting={submitting} onSubmit={onSubmit} triggerData={triggerData} />
  }

  if (step.state === "running") {
    return <RunningPanel step={step} />
  }

  if (step.state === "failed") {
    return <FailedPanel step={step} />
  }

  if (step.state === "completed") {
    return <CompletedPanel step={step} />
  }

  return (
    <Card>
      <div className={cardTokens.header}>
        <p className={cardTokens.headerTitle}>{step.label}</p>
        <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
          {NODE_TYPE_LABEL[step.type] ?? step.type}
        </p>
      </div>
      <div className={cardTokens.body}>
        <p className={tableTokens.cellSecondary}>
          Esta etapa ainda não foi alcançada pelo fluxo.
        </p>
      </div>
    </Card>
  )
}

function WaitingInputPanel({
  step,
  submitting,
  onSubmit,
  triggerData,
}: {
  step: Step
  submitting: boolean
  onSubmit: (nodeId: string, values: Record<string, unknown>) => void
  triggerData: Record<string, unknown>
}) {
  const formDescriptor = step.formDescriptor ?? {}
  const fields = formDescriptor.fields ?? []
  const title = formDescriptor.title ?? step.label
  const description =
    formDescriptor.description ??
    "Preencha os campos abaixo para o fluxo prosseguir."

  // Pre-fill: campos cuja `key` bate com o trigger_data.
  const initialValues: Record<string, unknown> = {}
  for (const f of fields) {
    if (triggerData[f.key] !== undefined) {
      initialValues[f.key] = triggerData[f.key]
      continue
    }
    if (f.key === "cnpj" && triggerData.target_cnpj !== undefined) {
      initialValues.cnpj = triggerData.target_cnpj
    }
    if (f.key === "razao_social" && triggerData.target_name !== undefined) {
      initialValues.razao_social = triggerData.target_name
    }
  }

  return (
    <Card>
      <div className={cardTokens.header}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className={cardTokens.headerTitle}>{title}</p>
            <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>{description}</p>
          </div>
          <span
            className={cx(
              tableTokens.badge,
              "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
            )}
          >
            Aguardando você
          </span>
        </div>
      </div>
      <div className={cardTokens.body}>
        {fields.length === 0 ? (
          <div>
            <p className={tableTokens.cellSecondary}>
              Esta etapa não tem campos configurados. Continue para prosseguir.
            </p>
            <div className="mt-4 flex justify-end">
              <Button
                onClick={() => onSubmit(step.id, {})}
                isLoading={submitting}
              >
                <RiCheckLine className="size-4" aria-hidden />
                Continuar
              </Button>
            </div>
          </div>
        ) : (
          <DynamicForm
            fields={fields}
            initialValues={initialValues}
            onSubmit={(values) => onSubmit(step.id, values)}
            submitting={submitting}
            submitLabel={formDescriptor.submit_label ?? "Salvar e prosseguir"}
          />
        )}
      </div>
    </Card>
  )
}

function RunningPanel({ step }: { step: Step }) {
  const message = runningMessage(step.type, step.label)
  return (
    <Card>
      <div className={cardTokens.header}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className={cardTokens.headerTitle}>{step.label}</p>
            <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
              {NODE_TYPE_LABEL[step.type] ?? step.type}
            </p>
          </div>
          <span
            className={cx(
              tableTokens.badge,
              "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300",
            )}
          >
            Em execução
          </span>
        </div>
      </div>
      <div className={cardTokens.body}>
        <div className="flex flex-col items-center gap-3 py-8 text-center">
          <RiLoader4Line className="size-8 animate-spin text-blue-500" aria-hidden />
          <p className="text-sm text-gray-700 dark:text-gray-300">{message}</p>
          <p className={tableTokens.cellSecondary}>
            Esta tela atualiza sozinha quando a etapa concluir.
          </p>
        </div>
      </div>
    </Card>
  )
}

function FailedPanel({ step }: { step: Step }) {
  return (
    <Card>
      <div className={cardTokens.header}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className={cardTokens.headerTitle}>{step.label}</p>
            <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
              {NODE_TYPE_LABEL[step.type] ?? step.type}
            </p>
          </div>
          <span
            className={cx(
              tableTokens.badge,
              "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
            )}
          >
            Falhou
          </span>
        </div>
      </div>
      <div className={cardTokens.body}>
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200">
          <p className="font-medium">Erro nesta etapa</p>
          <p className="mt-1 font-mono text-xs">{step.error_detail ?? "(sem detalhe)"}</p>
        </div>
      </div>
    </Card>
  )
}

function CompletedPanel({ step }: { step: Step }) {
  const hasOutput = step.output && Object.keys(step.output).length > 0
  return (
    <Card>
      <div className={cardTokens.header}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className={cardTokens.headerTitle}>{step.label}</p>
            <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
              {NODE_TYPE_LABEL[step.type] ?? step.type}
              {step.duration_ms != null && (
                <> · {(step.duration_ms / 1000).toFixed(1)}s</>
              )}
            </p>
          </div>
          <span
            className={cx(
              tableTokens.badge,
              "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
            )}
          >
            Concluído
          </span>
        </div>
      </div>
      <div className={cardTokens.body}>
        {hasOutput ? (
          <pre className="overflow-x-auto rounded bg-gray-50 p-3 font-mono text-[11px] text-gray-700 dark:bg-gray-900 dark:text-gray-300">
            {JSON.stringify(step.output, null, 2)}
          </pre>
        ) : (
          <p className={tableTokens.cellSecondary}>(sem output)</p>
        )}
      </div>
    </Card>
  )
}

function runningMessage(type: string, label: string): string {
  switch (type) {
    case "bureau_query":
      return `Consultando bureau · ${label}…`
    case "specialist_agent":
      return `Agente analisando · ${label}…`
    case "document_extractor":
      return "Extraindo dados do documento…"
    case "http_request":
      return "Chamando serviço externo…"
    case "output_generator":
      return "Gerando saída final…"
    default:
      return `Executando · ${label}…`
  }
}
