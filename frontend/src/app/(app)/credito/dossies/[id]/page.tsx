// src/app/(app)/credito/dossies/[id]/page.tsx
//
// Wizard V2 do dossie de credito. Substitui a versao antiga (`[320px stepper |
// 1fr workspace]` + painel hardcoded) pelo pattern <WizardMultiStep>:
//
//   - Top sticky com titulo + linear progress + SaveIndicator + acoes
//   - Side micro colapsavel com lista detalhada de etapas
//   - Workspace central que comuta views por step.state
//   - Right rail Evidencias (anexos + notas + links + inconsistencias)
//
// URL como fonte da verdade: `?step=<nodeId>` define o step focado;
// `?panel=<docs|notes|links>` controla scope (futuro).
//
// Auto-save granular: useStepDraft debounce 500ms quando o step e
// waiting_input — o SaveIndicator renderiza no top rail.

"use client"

import * as React from "react"
import { useParams, useRouter, useSearchParams } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { RiFilePdf2Line } from "@remixicon/react"
import { toast } from "sonner"

import { Button } from "@/components/tremor/Button"
import { DynamicForm } from "@/design-system/components/DynamicForm"
import {
  WizardMultiStep,
  type WizardMultiStepStep,
} from "@/design-system/patterns/WizardMultiStep"
import {
  AgentLiveStatus,
  AgentOutputRenderer,
  OpinionView,
  type EvidenceFilterScope,
  type FileListItem,
  type IndebtednessAnalysis,
  type LinkListItem,
  type OpinionDraft,
  type StepNoteListItem,
} from "@/design-system/components"
import { fetchMe } from "@/lib/api-client"
import {
  credito,
  DOSSIER_STATUS_LABEL,
  DOSSIER_STATUS_TONE,
  type AttachmentRead,
  type EdgeSpec,
  type FormField,
  type LinkRead,
  type NodeRunSummary,
  type NodeSpec,
  type NoteRead,
} from "@/lib/credito-client"
import {
  useDossierAttachments,
  useDossierLinks,
  useDossierNotes,
  useDossierState,
  useStepDraft,
  useUploadAttachment,
  useDeleteAttachment,
  useCreateNote,
  useDeleteNote,
  useUpdateNote,
  useCreateLink,
  useDeleteLink,
} from "@/lib/hooks/credito"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

// ─── Page ──────────────────────────────────────────────────────────────────

export default function DossierDetailPage() {
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const sp = useSearchParams()
  const dossierId = params.id

  const stepFromUrl = sp.get("step")
  const scopeFromUrl =
    (sp.get("panel") === "dossier" ? "dossier" : "step") as EvidenceFilterScope

  const queryClient = useQueryClient()

  // ── Queries ─────────────────────────────────────────────────────────────
  const { data: state, isLoading } = useDossierState(dossierId)
  const { data: workflow } = useQuery({
    queryKey: ["credito", "workflow-def", state?.dossier?.workflow_definition_id],
    queryFn: () =>
      credito.workflows.get(state!.dossier.workflow_definition_id),
    enabled: Boolean(state?.dossier?.workflow_definition_id),
  })
  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    staleTime: 5 * 60 * 1000,
  })

  // ── Steps (topological + state) ─────────────────────────────────────────
  const steps: WizardMultiStepStep[] = React.useMemo(() => {
    if (!state) return []
    if (workflow?.graph) {
      return buildSteps(workflow.graph, state.node_runs, state.pending_node)
    }
    return state.node_runs.map((nr) => stepFromNodeRun(nr, state.pending_node))
  }, [state, workflow])

  const focusedStep = React.useMemo(() => {
    if (stepFromUrl) {
      const direct = steps.find((s) => s.id === stepFromUrl)
      if (direct) return direct
    }
    return pickFocusStep(steps)
  }, [steps, stepFromUrl])

  const currentNodeId = focusedStep?.id ?? null

  // ── URL helpers ──────────────────────────────────────────────────────────
  const updateQuery = React.useCallback(
    (next: { step?: string | null; panel?: string | null }) => {
      const params = new URLSearchParams(sp.toString())
      if (next.step !== undefined) {
        if (next.step) params.set("step", next.step)
        else params.delete("step")
      }
      if (next.panel !== undefined) {
        if (next.panel) params.set("panel", next.panel)
        else params.delete("panel")
      }
      const qs = params.toString()
      router.replace(qs ? `?${qs}` : "?")
    },
    [router, sp],
  )

  const onStepSelect = React.useCallback(
    (nodeId: string) => updateQuery({ step: nodeId }),
    [updateQuery],
  )

  // ── Submit do step (waiting_input) ──────────────────────────────────────
  const submitMutation = useMutation({
    mutationFn: (vars: { nodeId: string; values: Record<string, unknown> }) =>
      credito.dossies.submitNodeInput(dossierId, vars.nodeId, vars.values),
    onSuccess: () => {
      toast.success("Salvo. Analise prossegue.")
      queryClient.invalidateQueries({
        queryKey: ["credito", "dossie-state", dossierId],
      })
    },
    onError: (e) => toast.error(`Erro ao salvar: ${(e as Error).message}`),
  })

  // ── Auto-save de rascunho ───────────────────────────────────────────────
  const draft = useStepDraft(
    dossierId,
    focusedStep?.state === "waiting_input" ? focusedStep.id : null,
  )

  // ── Evidence ────────────────────────────────────────────────────────────
  // Filtro por step quando scope === "step"; senao traz tudo do dossie.
  const evidenceNodeId =
    scopeFromUrl === "step" ? currentNodeId ?? undefined : undefined

  const attachmentsQuery = useDossierAttachments(dossierId, evidenceNodeId)
  const notesQuery = useDossierNotes(dossierId, evidenceNodeId)
  const linksQuery = useDossierLinks(dossierId, evidenceNodeId)

  const uploadMut = useUploadAttachment(dossierId)
  const deleteAttachMut = useDeleteAttachment(dossierId)
  const createNoteMut = useCreateNote(dossierId)
  const updateNoteMut = useUpdateNote(dossierId)
  const deleteNoteMut = useDeleteNote(dossierId)
  const createLinkMut = useCreateLink(dossierId)
  const deleteLinkMut = useDeleteLink(dossierId)

  const stepLabelById = React.useMemo(() => {
    const m: Record<string, string> = {}
    for (const s of steps) m[s.id] = s.label
    return m
  }, [steps])

  // ── Loading ─────────────────────────────────────────────────────────────
  if (isLoading || !state) {
    return (
      <div className="px-6 py-6">
        <p className={tableTokens.cellSecondary}>Carregando analise...</p>
      </div>
    )
  }

  const { dossier } = state

  // ── Helpers de render ───────────────────────────────────────────────────
  const titleLabel =
    dossier.target_name ??
    (dossier.target_cnpj
      ? `CNPJ ${dossier.target_cnpj}`
      : "Analise sem identidade")
  const subtitle = dossier.target_cnpj
    ? `StrataFlow · CNPJ ${dossier.target_cnpj}`
    : "StrataFlow · analise iniciada"

  const totalCost = state.node_runs.reduce(
    (acc, nr) => acc + (Number(nr.cost_brl) || 0),
    0,
  )
  const startedAtMs = state.run?.started_at
    ? Date.parse(state.run.started_at)
    : null
  const durationMin = startedAtMs
    ? Math.max(0, (Date.now() - startedAtMs) / 60000)
    : null
  const completedSteps = steps.filter((s) => s.state === "completed").length

  const opinion = extractAgentOutput<OpinionDraft>(steps, "opinion_writer")
  const indebtedness = extractAgentOutput<IndebtednessAnalysis>(
    steps,
    "indebtedness_analyst",
  )

  // ── Render hooks pro Workspace ──────────────────────────────────────────
  const renderWaitingInput = (step: WizardMultiStepStep) => {
    const descriptor = (step.formDescriptor ?? {}) as {
      fields?: FormField[]
      submit_label?: string
    }
    const fields = descriptor.fields ?? []
    const triggerData = state.run?.trigger_data ?? {}
    const initialValues: Record<string, unknown> = {}
    for (const f of fields) {
      if ((triggerData as Record<string, unknown>)[f.key] !== undefined) {
        initialValues[f.key] = (triggerData as Record<string, unknown>)[f.key]
      }
    }
    if (fields.length === 0) {
      return (
        <div className="flex justify-end">
          <Button
            onClick={() =>
              submitMutation.mutate({ nodeId: step.id, values: {} })
            }
            isLoading={submitMutation.isPending}
          >
            Continuar
          </Button>
        </div>
      )
    }
    return (
      <DynamicForm
        fields={fields}
        initialValues={initialValues}
        onSubmit={async (values) => {
          await draft.flushNow()
          submitMutation.mutate({ nodeId: step.id, values })
        }}
        submitting={submitMutation.isPending}
        submitLabel={descriptor.submit_label ?? "Salvar e prosseguir"}
      />
    )
  }

  const renderRunning = (step: WizardMultiStepStep) => {
    const inputData = (step.input ?? {}) as {
      agent?: string
      tools_log?: Array<{
        iso_at: string
        kind: "tool_use" | "tool_result"
        tool_name?: string
        duration_ms?: number
      }>
    }
    return (
      <AgentLiveStatus
        agentLabel={inputData.agent}
        startedAt={state.run?.started_at ?? null}
        toolsLog={inputData.tools_log}
        tokensInput={
          state.node_runs.find((nr) => nr.node_id === step.id)?.tokens_input
        }
        tokensOutput={
          state.node_runs.find((nr) => nr.node_id === step.id)?.tokens_output
        }
        costBrl={Number(
          state.node_runs.find((nr) => nr.node_id === step.id)?.cost_brl ?? 0,
        )}
      />
    )
  }

  const renderCompleted = (step: WizardMultiStepStep) => {
    const inputData = (step.input ?? {}) as { agent?: string }
    const agentName = inputData.agent ?? null
    if (agentName === "opinion_writer" && opinion) {
      return <OpinionView output={opinion} indebtedness={indebtedness} />
    }
    return <AgentOutputRenderer agentName={agentName} output={step.output} />
  }

  // ── Top actions ─────────────────────────────────────────────────────────
  const topActions = (
    <>
      <span
        className={cx(
          tableTokens.badge,
          DOSSIER_STATUS_TONE[dossier.status],
        )}
      >
        {DOSSIER_STATUS_LABEL[dossier.status]}
      </span>
      <Button
        variant="ghost"
        disabled
        title="PDF disponivel quando finalizar"
      >
        <RiFilePdf2Line className="size-4" aria-hidden />
        Exportar PDF
      </Button>
    </>
  )

  // ── Render final ────────────────────────────────────────────────────────
  return (
    <div className="px-6 py-6 pb-20">
      <WizardMultiStep
        dossierTitle={`Analise · ${titleLabel}`}
        dossierSubtitle={subtitle}
        steps={steps}
        currentNodeId={currentNodeId}
        onStepSelect={onStepSelect}
        meta={{
          completedSteps,
          totalSteps: steps.length,
          totalCostBrl: totalCost,
          durationMinutes: durationMin,
        }}
        saveState={draft.state}
        lastSavedAt={draft.lastSavedAt}
        saveErrorMessage={draft.errorMessage}
        onSaveRetry={() => void draft.flushNow()}
        onBack={() => router.push("/credito/dossies")}
        topActions={topActions}
        renderWaitingInput={renderWaitingInput}
        renderRunning={renderRunning}
        renderCompleted={renderCompleted}
        evidence={{
          scope: scopeFromUrl,
          onScopeChange: (s) =>
            updateQuery({ panel: s === "dossier" ? "dossier" : null }),
          attachments: (attachmentsQuery.data ?? []).map((a) =>
            attachmentToFileListItem(a, stepLabelById, dossierId),
          ),
          onUploadAttachment: async (file) => {
            await uploadMut.mutateAsync({
              file,
              node_id: scopeFromUrl === "step" ? currentNodeId : null,
            })
          },
          onDeleteAttachment: (id) => deleteAttachMut.mutate(id),
          notes: (notesQuery.data ?? []).map((n) =>
            noteToStepNoteListItem(n, me?.user.name),
          ),
          onCreateNote: async (body, pinned) => {
            if (!currentNodeId) return
            await createNoteMut.mutateAsync({
              node_id: currentNodeId,
              body_md: body,
              pinned,
            })
          },
          onEditNote: (note) => {
            // MVP: edit inline ainda nao implementado — TODO seguir com modal
            // de edicao. Por enquanto, edit via PATCH simples (toggle pinned).
            updateNoteMut.mutate({
              noteId: note.id,
              payload: { pinned: !note.pinned },
            })
          },
          onDeleteNote: (id) => deleteNoteMut.mutate(id),
          links: (linksQuery.data ?? []).map(linkToLinkListItem),
          onCreateLink: async (vals) => {
            await createLinkMut.mutateAsync({
              node_id: scopeFromUrl === "step" ? currentNodeId : null,
              ...vals,
            })
          },
          onDeleteLink: (id) => deleteLinkMut.mutate(id),
          inconsistencies: undefined, // TODO: extrair do cross_reference_analyst
          currentUserId: me?.user.id,
        }}
      />
    </div>
  )
}

// ─── Helpers ───────────────────────────────────────────────────────────────

const NODE_TYPE_LABEL: Record<string, string> = {
  trigger: "Inicio",
  human_input: "Coleta humana",
  bureau_query: "Consulta a bureau",
  specialist_agent: "Analise por agente IA",
  document_request: "Solicitacao de documento",
  document_extractor: "Extracao de documento",
  conditional_branch: "Decisao condicional",
  human_review: "Revisao humana",
  http_request: "Requisicao HTTP",
  output_generator: "Saida final",
  notification: "Notificacao",
}

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
  for (const n of nodes) {
    if (!result.includes(n.id)) result.push(n.id)
  }
  return result
}

function stepFromNodeRun(
  nr: NodeRunSummary,
  pendingNode: NodeRunSummary | null,
): WizardMultiStepStep {
  const state = stepStateFromRun(nr, pendingNode)
  return {
    id: nr.node_id,
    label: nr.node_id,
    state,
    nodeType: nr.node_type,
    durationMs: nr.duration_ms,
    errorDetail: nr.error_detail,
    output: nr.output_data,
    input: nr.input_data,
    costBrl: Number(nr.cost_brl) || 0,
    formDescriptor:
      state === "waiting_input"
        ? (nr.output_data as Record<string, unknown>)
        : undefined,
  }
}

function buildSteps(
  graph: { nodes: NodeSpec[]; edges: EdgeSpec[] },
  nodeRuns: NodeRunSummary[],
  pendingNode: NodeRunSummary | null,
): WizardMultiStepStep[] {
  const order = topologicalOrder(graph.nodes, graph.edges)
  const nodeRunByNodeId = new Map<string, NodeRunSummary>()
  for (const nr of nodeRuns) nodeRunByNodeId.set(nr.node_id, nr)

  return order.map((nodeId) => {
    const spec = graph.nodes.find((n) => n.id === nodeId)
    const label =
      spec?.label ??
      (spec ? NODE_TYPE_LABEL[spec.type] ?? spec.type : nodeId)
    const nodeType = spec?.type ?? "unknown"
    const run = nodeRunByNodeId.get(nodeId)

    if (!run) {
      return {
        id: nodeId,
        label,
        state: "pending",
        nodeType,
      }
    }
    const stepState = stepStateFromRun(run, pendingNode)
    return {
      id: nodeId,
      label,
      state: stepState,
      nodeType,
      durationMs: run.duration_ms,
      errorDetail: run.error_detail,
      output: run.output_data,
      input: run.input_data,
      costBrl: Number(run.cost_brl) || 0,
      formDescriptor:
        stepState === "waiting_input"
          ? (run.output_data as Record<string, unknown>)
          : undefined,
    }
  })
}

function stepStateFromRun(
  run: NodeRunSummary,
  pendingNode: NodeRunSummary | null,
): WizardMultiStepStep["state"] {
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

function pickFocusStep(steps: WizardMultiStepStep[]): WizardMultiStepStep | null {
  return (
    steps.find((s) => s.state === "waiting_input") ??
    steps.find((s) => s.state === "failed") ??
    steps.find((s) => s.state === "running") ??
    steps.find(
      (s) =>
        s.state === "completed" &&
        (s.input as { agent?: string } | undefined)?.agent === "opinion_writer",
    ) ??
    [...steps].reverse().find((s) => s.state === "completed") ??
    steps[0] ??
    null
  )
}

function extractAgentOutput<T>(
  steps: WizardMultiStepStep[],
  agentName: string,
): T | null {
  const match = steps.find(
    (s) =>
      s.state === "completed" &&
      s.nodeType === "specialist_agent" &&
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

function attachmentToFileListItem(
  a: AttachmentRead,
  stepLabelById: Record<string, string>,
  _dossierId: string,
): FileListItem {
  void _dossierId
  return {
    id: a.id,
    filename: a.filename,
    mime_type: a.mime_type,
    size_bytes: a.size_bytes,
    uploaded_at: a.uploaded_at,
    uploaded_by_label: null,
    node_id: a.node_id,
    node_label: a.node_id ? stepLabelById[a.node_id] ?? a.node_id : null,
    download_url: credito.attachments.downloadUrl(_dossierId, a.id),
  }
}

function noteToStepNoteListItem(
  n: NoteRead,
  currentUserName: string | undefined,
): StepNoteListItem {
  return {
    id: n.id,
    body_md: n.body_md,
    pinned: n.pinned,
    created_at: n.created_at,
    updated_at: n.updated_at,
    author_id: n.author_id,
    author_label: currentUserName ?? "Voce",
  }
}

function linkToLinkListItem(l: LinkRead): LinkListItem {
  return {
    id: l.id,
    url: l.url,
    title: l.title,
    description: l.description,
    added_at: l.added_at,
    added_by: l.added_by,
    added_by_label: null,
    node_id: l.node_id,
  }
}
