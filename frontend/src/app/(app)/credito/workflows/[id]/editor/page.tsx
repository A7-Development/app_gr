// src/app/(app)/credito/workflows/[id]/editor/page.tsx
//
// Editor visual de fluxo de credito — Fase 1 do redesenho no-code.
//
// Mudancas vs estado anterior:
//  - Vocabulario amigavel em todo lugar (etapa, conexao, ...) via glossary.
//  - Palette reorganizada por JORNADA (Inicio / Coletar / Enriquecer / IA /
//    Decisao / Notificar) em vez de categoria tecnica.
//  - Inspector com forms dedicados por tipo (FieldsBuilder, DocumentsBuilder,
//    ConditionBuilder, AgentInspector) — substitui textareas de JSON.
//  - Validacao continua: badge no header + halos no canvas + mensagens em
//    domain language. Erros visiveis sem precisar salvar.
//  - "Salvar mudancas" cria nova versao em DRAFT (autosave fica para Fase 2).

"use client"

import * as React from "react"
import { useParams, useRouter } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  addEdge,
  Background,
  ConnectionMode,
  Controls,
  MarkerType,
  MiniMap,
  type Connection,
  type Edge,
  type EdgeMouseHandler,
  type Node,
  type NodeMouseHandler,
  type NodeTypes,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  useReactFlow,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import {
  RiAlertLine,
  RiArrowLeftLine,
  RiCheckboxCircleLine,
  RiCheckLine,
  RiDatabase2Line,
  RiEditLine,
  RiErrorWarningLine,
  RiFilePdf2Line,
  RiFileSearchLine,
  RiFlashlightLine,
  RiGitBranchLine,
  RiGlobalLine,
  RiNotification3Line,
  RiPlayCircleLine,
  RiRobot2Line,
  RiSaveLine,
  RiShieldStarLine,
  RiUploadCloud2Line,
  type RemixiconComponentType,
} from "@remixicon/react"
import { toast } from "sonner"

import { Button } from "@/components/tremor/Button"
import { PageHeader } from "@/design-system/components"
import {
  credito,
  type NodeTypeMeta,
  type WorkflowDefinitionRead,
  type WorkflowGraph,
} from "@/lib/credito-client"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

import { EdgeConditionPopover } from "./_components/EdgeConditionPopover"
import { NodeInspector } from "./_components/NodeInspector"
import {
  StrataNode,
  type StrataNodeData,
  type ValidationStatus,
} from "./_components/StrataNode"
import { TestRunDrawer } from "./_components/TestRunDrawer"
import { VariablesPill } from "./_components/VariablesPill"
import { glossary } from "./_lib/glossary"
import {
  type PaletteEntry,
  buildPaletteEntries,
  groupByJourney,
  JOURNEY_HINT,
  JOURNEY_LABEL,
  JOURNEY_ORDER,
} from "./_lib/etapas"
import {
  blockingErrors,
  statusByNode,
  summarize,
  validateGraph,
  type ValidationError,
} from "./_lib/validate"

// React Flow needs a stable nodeTypes mapping
const NODE_RENDERERS: NodeTypes = {
  strata: StrataNode,
}

const ICON_MAP: Record<string, RemixiconComponentType> = {
  RiPlayCircleLine,
  RiEditLine,
  RiCheckboxCircleLine,
  RiUploadCloud2Line,
  RiFileSearchLine,
  RiDatabase2Line,
  RiRobot2Line,
  RiFilePdf2Line,
  RiGitBranchLine,
  RiGlobalLine,
  RiNotification3Line,
}

// Drag-and-drop payload key — encoded JSON pra carregar nodeType + initialConfig.
const DND_KEY = "application/strata-palette-entry"

// ─── Convert WorkflowGraph -> React Flow ──────────────────────────────

function graphToReactFlow(
  graph: WorkflowGraph,
  nodeTypes: NodeTypeMeta[],
): { nodes: Node[]; edges: Edge[] } {
  const metaByType = new Map(nodeTypes.map((nt) => [nt.type, nt]))
  const nodes: Node[] = graph.nodes.map((n, i) => ({
    id: n.id,
    type: "strata",
    position: n.position ?? { x: 80, y: i * 120 },
    data: {
      label: n.label ?? n.id,
      nodeType: n.type,
      config: n.config,
      meta: metaByType.get(n.type),
    } satisfies StrataNodeData,
  }))
  const edges: Edge[] = graph.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    // `default` = curva bezier suave (React Flow default). Mais orgânica
    // que `smoothstep` (degraus 90° arredondados). markerEnd setado aqui
    // garante seta direcional em edges CARREGADAS do DB — defaultEdgeOptions
    // do <ReactFlow> só aplica em edges NOVAS criadas via onConnect.
    type: "default",
    markerEnd: {
      type: MarkerType.ArrowClosed,
      width: 16,
      height: 16,
    },
    label: e.condition ? `se: ${e.condition.slice(0, 40)}` : undefined,
    data: { condition: e.condition },
    labelStyle: {
      fontSize: 10,
      fill: "rgb(107 114 128)",
      fontFamily: "var(--font-geist-mono)",
    },
    labelBgPadding: [4, 2],
    labelBgBorderRadius: 4,
    labelBgStyle: { fill: "white", fillOpacity: 0.9 },
    animated: false,
  }))
  return { nodes, edges }
}

// React Flow → WorkflowGraph (for save).
function reactFlowToGraph(nodes: Node[], edges: Edge[]): WorkflowGraph {
  return {
    nodes: nodes.map((n) => {
      const d = n.data as unknown as StrataNodeData
      return {
        id: n.id,
        type: d.nodeType,
        label: d.label ?? null,
        config: d.config ?? {},
        position: { x: n.position.x, y: n.position.y },
      }
    }),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      condition: ((e.data as { condition?: string } | undefined)?.condition) ?? null,
    })),
  }
}

// ─── Page ────────────────────────────────────────────────────────────────

export default function WorkflowEditorPage() {
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const workflowId = params.id

  const { data: workflow, isLoading } = useQuery({
    queryKey: ["credito", "workflow", workflowId],
    queryFn: () => credito.workflows.get(workflowId),
    enabled: Boolean(workflowId),
  })

  const { data: nodeTypes } = useQuery({
    queryKey: ["credito", "node-types"],
    queryFn: () => credito.workflows.nodeTypes(),
  })

  const { data: activeWorkflow } = useQuery({
    queryKey: ["credito", "workflow-active", workflow?.name],
    queryFn: () => credito.workflows.getActive(workflow!.name),
    enabled: Boolean(workflow?.name),
    retry: false,
  })

  if (isLoading || !workflow) {
    return (
      <div className="px-6 py-6">
        <p className={tableTokens.cellSecondary}>Carregando fluxo...</p>
      </div>
    )
  }

  return (
    <div className="flex h-[calc(100vh-65px)] flex-col">
      <ReactFlowProvider>
        <EditorBody
          workflow={workflow}
          activeWorkflow={activeWorkflow ?? null}
          nodeTypes={nodeTypes ?? []}
          onBack={() => router.push("/credito/workflows")}
        />
      </ReactFlowProvider>
    </div>
  )
}

// ─── EditorBody — needs ReactFlowProvider context ───────────────────────

function EditorBody({
  workflow,
  activeWorkflow,
  nodeTypes,
  onBack,
}: {
  workflow: WorkflowDefinitionRead
  activeWorkflow: WorkflowDefinitionRead | null
  nodeTypes: NodeTypeMeta[]
  onBack: () => void
}) {
  const queryClient = useQueryClient()
  const router = useRouter()
  const reactFlow = useReactFlow()
  const reactFlowWrapper = React.useRef<HTMLDivElement>(null)

  const { nodes: initialNodes, edges: initialEdges } = React.useMemo(
    () => graphToReactFlow(workflow.graph, nodeTypes),
    [workflow.graph, nodeTypes],
  )
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges)
  const [selectedNodeId, setSelectedNodeId] = React.useState<string | null>(null)
  const [selectedEdgeId, setSelectedEdgeId] = React.useState<string | null>(null)
  const [edgePopover, setEdgePopover] = React.useState<{ edgeId: string; x: number; y: number } | null>(null)
  const [dirty, setDirty] = React.useState(false)
  const [showValidationDetails, setShowValidationDetails] = React.useState(false)
  const [testDrawerOpen, setTestDrawerOpen] = React.useState(false)

  // Re-sync when workflow changes (after save).
  React.useEffect(() => {
    setNodes(initialNodes)
    setEdges(initialEdges)
    setDirty(false)
  }, [initialNodes, initialEdges, setNodes, setEdges])

  // ── Validacao continua ─────────────────────────────────────────────
  // Etapa 1 (sincrona): regras estruturais + per-tipo (validate.ts).
  // Etapa 2 (assincrona): validação semântica do backend (Fase 2) —
  // produces/requires tipados por nó, percorre o grafo e checa fluxo de
  // dados. Roda quando nodes/edges mudam; React Query desduplica calls.
  const localValidationErrors = React.useMemo<ValidationError[]>(
    () => validateGraph(nodes, edges, nodeTypes),
    [nodes, edges, nodeTypes],
  )

  const graphForValidation = React.useMemo(
    () => reactFlowToGraph(nodes, edges),
    [nodes, edges],
  )
  const graphSignature = React.useMemo(
    () => JSON.stringify(graphForValidation),
    [graphForValidation],
  )
  const { data: semanticResult } = useQuery({
    queryKey: ["credito", "workflow-validate", graphSignature],
    queryFn: () => credito.workflows.validate(graphForValidation),
    enabled: nodes.length > 0,
    staleTime: 30_000,
    retry: false,
  })
  const semanticValidationErrors: ValidationError[] = React.useMemo(
    () =>
      (semanticResult?.errors ?? []).map((e) => ({
        level: e.severity === "error" ? "error" : "warning",
        nodeId: e.node_id,
        message: e.message,
      })),
    [semanticResult],
  )

  const validationErrors = React.useMemo(
    () => [...localValidationErrors, ...semanticValidationErrors],
    [localValidationErrors, semanticValidationErrors],
  )
  const summary = React.useMemo(() => summarize(validationErrors), [validationErrors])
  const nodeStatusMap = React.useMemo(() => statusByNode(validationErrors), [validationErrors])

  // Mapa de produced vars por node — vem do backend semântico (Fase 3a).
  const producedByNode = React.useMemo<Record<string, Record<string, string>>>(
    () => semanticResult?.produced_by_node ?? {},
    [semanticResult],
  )

  // Aplica validationStatus + producedVars a cada node antes de passar pro
  // ReactFlow. StrataNode renderiza chips coloridos no rodapé com o que o
  // nó publica em runtime.
  const nodesWithStatus = React.useMemo<Node[]>(
    () =>
      nodes.map((n) => {
        const status = nodeStatusMap.get(n.id)
        const data = n.data as unknown as StrataNodeData
        const newStatus: ValidationStatus = status?.status ?? "ok"
        const newProduced = producedByNode[n.id] ?? undefined
        if (
          data.validationStatus === newStatus &&
          data.validationMessage === status?.message &&
          data.producedVars === newProduced
        ) {
          return n
        }
        return {
          ...n,
          data: {
            ...data,
            validationStatus: newStatus,
            validationMessage: status?.message,
            producedVars: newProduced,
          } satisfies StrataNodeData,
        }
      }),
    [nodes, nodeStatusMap, producedByNode],
  )

  const isActiveVersion = activeWorkflow?.id === workflow.id
  const canEdit = workflow.status !== "archived"
  const wfName = workflow.name

  // ─── Selection handlers ──────────────────────────────────────────────

  const handleNodeClick: NodeMouseHandler = (_e, node) => {
    setSelectedNodeId(node.id)
    setSelectedEdgeId(null)
    setEdgePopover(null)
  }

  const handleEdgeClick: EdgeMouseHandler = (e, edge) => {
    setSelectedEdgeId(edge.id)
    setSelectedNodeId(null)
    setEdgePopover({ edgeId: edge.id, x: e.clientX, y: e.clientY })
  }

  const handlePaneClick = () => {
    setSelectedNodeId(null)
    setSelectedEdgeId(null)
    setEdgePopover(null)
  }

  // ─── Edit handlers ───────────────────────────────────────────────────

  const updateNodeConfig = React.useCallback(
    (nodeId: string, config: Record<string, unknown>) => {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === nodeId
            ? { ...n, data: { ...(n.data as StrataNodeData), config } }
            : n,
        ),
      )
      setDirty(true)
    },
    [setNodes],
  )

  const updateNodeLabel = React.useCallback(
    (nodeId: string, label: string) => {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === nodeId
            ? { ...n, data: { ...(n.data as StrataNodeData), label } }
            : n,
        ),
      )
      setDirty(true)
    },
    [setNodes],
  )

  const updateEdgeCondition = React.useCallback(
    (edgeId: string, condition: string | null) => {
      setEdges((eds) =>
        eds.map((e) =>
          e.id === edgeId
            ? {
                ...e,
                data: { ...(e.data ?? {}), condition },
                label: condition ? `se: ${condition.slice(0, 40)}` : undefined,
              }
            : e,
        ),
      )
      setDirty(true)
    },
    [setEdges],
  )

  // ─── Adicionar etapa ao canvas (compartilhado por drag-drop e click) ─

  const addNodeFromEntry = React.useCallback(
    (entry: PaletteEntry, position?: { x: number; y: number }) => {
      if (!canEdit) {
        toast.error("Este fluxo esta arquivado e nao pode ser editado.")
        return
      }

      const meta = nodeTypes.find((nt) => nt.type === entry.nodeType)
      if (!meta) {
        toast.error(`Tipo de etapa "${entry.nodeType}" desconhecido.`)
        return
      }
      if (!meta.available) {
        toast.error(
          `"${entry.label}" esta marcado como em breve — ainda nao pode ser usado.`,
        )
        return
      }

      // Default position: centro da viewport visivel se nao foi passado.
      const finalPosition =
        position ??
        (() => {
          // screenToFlowPosition do centro do wrapper.
          const rect = reactFlowWrapper.current?.getBoundingClientRect()
          if (rect) {
            return reactFlow.screenToFlowPosition({
              x: rect.left + rect.width / 2,
              y: rect.top + rect.height / 3,
            })
          }
          return { x: 100, y: 100 }
        })()

      const newId = `${entry.nodeType}_${Math.random().toString(36).slice(2, 8)}`
      const initialConfig: Record<string, unknown> = { ...(entry.initialConfig ?? {}) }
      // Required string fields comecam vazios.
      for (const f of meta.config_schema ?? []) {
        if (f.required && f.type === "string" && initialConfig[f.key] === undefined) {
          initialConfig[f.key] = ""
        }
      }

      const newNode: Node = {
        id: newId,
        type: "strata",
        position: finalPosition,
        data: {
          label: entry.label,
          nodeType: entry.nodeType,
          config: initialConfig,
          meta,
        } satisfies StrataNodeData,
      }

      setNodes((nds) => [...nds, newNode])
      setSelectedNodeId(newId)
      setDirty(true)
    },
    [canEdit, nodeTypes, reactFlow, setNodes],
  )

  // ─── Drag-and-drop palette → canvas ──────────────────────────────────

  const onDragOver = React.useCallback((e: React.DragEvent) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = "move"
  }, [])

  const onDrop = React.useCallback(
    (event: React.DragEvent) => {
      event.preventDefault()

      const raw = event.dataTransfer.getData(DND_KEY)
      if (!raw) return
      let entry: PaletteEntry
      try {
        entry = JSON.parse(raw) as PaletteEntry
      } catch {
        return
      }

      const position = reactFlow.screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      })
      addNodeFromEntry(entry, position)
    },
    [addNodeFromEntry, reactFlow],
  )

  // ─── Connect edges ───────────────────────────────────────────────────

  const onConnect = React.useCallback(
    (connection: Connection) => {
      if (!canEdit) return
      if (!connection.source || !connection.target) return
      if (connection.source === connection.target) {
        toast.error("Nao da pra conectar uma etapa a ela mesma.")
        return
      }
      setEdges((eds) =>
        addEdge(
          {
            ...connection,
            id: `e_${connection.source}_${connection.target}_${Math.random().toString(36).slice(2, 6)}`,
            type: "smoothstep",
            data: { condition: null },
          },
          eds,
        ),
      )
      setDirty(true)
    },
    [canEdit, setEdges],
  )

  // ─── Delete on keydown ───────────────────────────────────────────────

  React.useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null
      if (
        target &&
        ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName) ||
        (target as HTMLElement | null)?.isContentEditable
      ) {
        return
      }
      if (e.key !== "Delete" && e.key !== "Backspace") return
      if (!canEdit) return

      if (selectedNodeId) {
        e.preventDefault()
        setNodes((nds) => nds.filter((n) => n.id !== selectedNodeId))
        setEdges((eds) =>
          eds.filter((e) => e.source !== selectedNodeId && e.target !== selectedNodeId),
        )
        setSelectedNodeId(null)
        setDirty(true)
      } else if (selectedEdgeId) {
        e.preventDefault()
        setEdges((eds) => eds.filter((e) => e.id !== selectedEdgeId))
        setSelectedEdgeId(null)
        setEdgePopover(null)
        setDirty(true)
      }
    }
    window.addEventListener("keydown", onKeyDown)
    return () => window.removeEventListener("keydown", onKeyDown)
  }, [canEdit, selectedNodeId, selectedEdgeId, setNodes, setEdges])

  // ─── Save (PATCH → new version) ──────────────────────────────────────

  const saveMutation = useMutation({
    mutationFn: () =>
      credito.workflows.update(workflow.id, {
        graph: reactFlowToGraph(nodes, edges),
        description: workflow.description,
      }),
    onSuccess: (newWorkflow) => {
      toast.success(`Salvo como v${newWorkflow.version}.`)
      queryClient.invalidateQueries({ queryKey: ["credito", "workflow"] })
      queryClient.invalidateQueries({ queryKey: ["credito", "workflows"] })
      router.push(`/credito/workflows/${newWorkflow.id}/editor`)
    },
    onError: (e) => toast.error(`Erro ao salvar: ${(e as Error).message}`),
  })

  function handleSave() {
    const blocking = blockingErrors(validationErrors)
    if (blocking.length > 0) {
      setShowValidationDetails(true)
      toast.error(
        `${blocking.length} ${blocking.length === 1 ? "problema bloqueador" : "problemas bloqueadores"}. Corrija antes de salvar.`,
      )
      return
    }
    saveMutation.mutate()
  }

  // ─── Activate this version ───────────────────────────────────────────

  const activateMutation = useMutation({
    mutationFn: () => credito.workflows.activate(wfName, workflow.id),
    onSuccess: () => {
      toast.success(`v${workflow.version} publicada — novos dossies vao usar esta versao.`)
      queryClient.invalidateQueries({ queryKey: ["credito", "workflow-active"] })
      queryClient.invalidateQueries({ queryKey: ["credito", "workflows"] })
    },
    onError: (e) => {
      // Backend bloqueia ativação com 422 quando há erros semânticos.
      // ApiError.detail preserva o payload estruturado: { message, validation }.
      const err = e as Error & { detail?: unknown }
      let msg = `Erro ao publicar: ${err.message}`
      if (
        err.detail &&
        typeof err.detail === "object" &&
        "message" in err.detail
      ) {
        const detailMsg = (err.detail as { message?: unknown }).message
        if (typeof detailMsg === "string") msg = detailMsg
      }
      toast.error(msg)
      setShowValidationDetails(true)
    },
  })

  // ─── Selected items for Inspector / popover ──────────────────────────

  const selectedNode = React.useMemo(
    () => (selectedNodeId ? nodesWithStatus.find((n) => n.id === selectedNodeId) ?? null : null),
    [nodesWithStatus, selectedNodeId],
  )
  const selectedEdge = React.useMemo(
    () => (selectedEdgeId ? edges.find((e) => e.id === selectedEdgeId) ?? null : null),
    [edges, selectedEdgeId],
  )

  // Track node moves → mark dirty.
  const handleNodesChange = React.useCallback(
    (changes: Parameters<typeof onNodesChange>[0]) => {
      onNodesChange(changes)
      const positionMoved = changes.some(
        (c) => c.type === "position" && c.dragging === false,
      )
      if (positionMoved) setDirty(true)
    },
    [onNodesChange],
  )

  // ─── Palette entries (build once from nodeTypes) ─────────────────────
  const paletteEntries = React.useMemo(
    () => buildPaletteEntries(nodeTypes),
    [nodeTypes],
  )

  return (
    <>
      {/* Header */}
      <div className="border-b border-gray-200 px-6 py-4 dark:border-gray-800">
        <PageHeader
          title={`${workflow.name} (v${workflow.version})`}
          subtitle={workflow.description ?? "Editor visual de fluxo de credito"}
          actions={
            <div className="flex items-center gap-2">
              <ValidationBadge
                summary={summary}
                onClick={() => setShowValidationDetails((v) => !v)}
              />
              {isActiveVersion && (
                <span
                  className={cx(
                    tableTokens.badge,
                    "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
                  )}
                  title="Esta versao esta publicada e em uso por novos dossies."
                >
                  <RiShieldStarLine className="mr-1 inline size-3" aria-hidden />
                  {glossary.statusActive}
                </span>
              )}
              {workflow.status === "draft" && (
                <span
                  className={cx(
                    tableTokens.badge,
                    "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
                  )}
                >
                  {glossary.statusDraft}
                </span>
              )}
              {workflow.status === "archived" && (
                <span className={cx(tableTokens.badge, "bg-gray-100 text-gray-500")}>
                  {glossary.statusArchived}
                </span>
              )}
              <Button
                variant="ghost"
                onClick={() => setTestDrawerOpen(true)}
                title="Roda o fluxo em modo sandbox sem chamar Serasa nem Anthropic."
              >
                <RiFlashlightLine className="size-4" aria-hidden />
                Testar
              </Button>
              {!isActiveVersion && workflow.status !== "archived" && (
                <Button
                  variant="secondary"
                  onClick={() => activateMutation.mutate()}
                  isLoading={activateMutation.isPending}
                  title="Publica esta versao — novos dossies vao usar ela."
                >
                  <RiShieldStarLine className="size-4" aria-hidden />
                  {glossary.publish}
                </Button>
              )}
              <Button
                onClick={handleSave}
                disabled={!dirty || !canEdit || saveMutation.isPending}
                isLoading={saveMutation.isPending}
                title={
                  !dirty
                    ? "Nenhuma mudanca pra salvar"
                    : "Salva uma nova versao em rascunho com o estado atual"
                }
              >
                <RiSaveLine className="size-4" aria-hidden />
                {glossary.saveAsNewVersion}
              </Button>
              <Button variant="ghost" onClick={onBack}>
                <RiArrowLeftLine className="size-4" aria-hidden />
                {glossary.back}
              </Button>
            </div>
          }
        />
      </div>

      <div className="flex flex-1 overflow-hidden">
        {/* Palette */}
        <Palette
          entries={paletteEntries}
          canEdit={canEdit}
          onAdd={(entry) => addNodeFromEntry(entry)}
        />

        {/* Canvas */}
        <div className="relative flex-1 bg-gray-50 dark:bg-gray-950" ref={reactFlowWrapper}>
          {dirty && (
            <div className="absolute right-3 top-3 z-10 rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
              {glossary.unsavedChanges}
            </div>
          )}
          <VariablesPill
            selectedNodeId={selectedNodeId}
            nodes={nodesWithStatus}
            edges={edges}
            producedByNode={producedByNode}
          />
          {showValidationDetails && validationErrors.length > 0 && (
            <ValidationDetailsPanel
              errors={validationErrors}
              onClose={() => setShowValidationDetails(false)}
            />
          )}
          <ReactFlow
            nodes={nodesWithStatus}
            edges={edges}
            onNodesChange={handleNodesChange}
            onEdgesChange={onEdgesChange}
            onNodeClick={handleNodeClick}
            onEdgeClick={handleEdgeClick}
            onPaneClick={handlePaneClick}
            onConnect={onConnect}
            onDrop={onDrop}
            onDragOver={onDragOver}
            nodeTypes={NODE_RENDERERS}
            // Loose: permite ligação entre handles do mesmo tipo (todos os
            // 4 handles do StrataNode são `source`). Sem isso o usuário só
            // poderia ligar source→target, e cada nó precisaria de 8 handles
            // (4 de cada tipo) — overkill visual.
            connectionMode={ConnectionMode.Loose}
            // Toda edge nasce com seta apontando o sentido (source→target)
            // e como curva bezier suave (`default`). Coerente com edges
            // carregadas do DB (graphToReactFlow seta o mesmo type).
            defaultEdgeOptions={{
              type: "default",
              markerEnd: {
                type: MarkerType.ArrowClosed,
                width: 16,
                height: 16,
              },
            }}
            fitView
            proOptions={{ hideAttribution: true }}
          >
            <Background gap={16} size={1} />
            <Controls />
          </ReactFlow>

          {edgePopover && selectedEdge && (
            <EdgeConditionPopover
              x={edgePopover.x}
              y={edgePopover.y}
              edge={selectedEdge}
              nodes={nodes}
              edges={edges}
              onSave={(cond) => {
                updateEdgeCondition(edgePopover.edgeId, cond)
                setEdgePopover(null)
              }}
              onClose={() => setEdgePopover(null)}
              onDelete={() => {
                setEdges((eds) => eds.filter((e) => e.id !== edgePopover.edgeId))
                setEdgePopover(null)
                setSelectedEdgeId(null)
                setDirty(true)
              }}
            />
          )}
        </div>

        {/* Inspector */}
        <aside className="w-80 overflow-y-auto border-l border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-950">
          <NodeInspector
            selectedNode={selectedNode}
            nodes={nodes}
            edges={edges}
            nodeTypes={nodeTypes}
            producedByNode={producedByNode}
            onUpdateConfig={updateNodeConfig}
            onUpdateLabel={updateNodeLabel}
          />
        </aside>
      </div>

      {/* Test drawer (dry-run sandbox) */}
      <TestRunDrawer
        open={testDrawerOpen}
        onOpenChange={setTestDrawerOpen}
        workflowId={workflow.id}
        workflowName={`${workflow.name} v${workflow.version}`}
        hasUnsavedChanges={dirty}
      />
    </>
  )
}

// ─── ValidationBadge — chip persistente no header ────────────────────────

function ValidationBadge({
  summary,
  onClick,
}: {
  summary: { errors: number; warnings: number; total: number; blocking: boolean }
  onClick: () => void
}) {
  if (summary.total === 0) {
    return (
      <span
        className={cx(
          tableTokens.badge,
          "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
        )}
        title="Nenhum problema detectado"
      >
        <RiCheckLine className="mr-1 inline size-3" aria-hidden />
        {glossary.validationOk}
      </span>
    )
  }

  if (summary.blocking) {
    return (
      <button
        type="button"
        onClick={onClick}
        className={cx(
          tableTokens.badge,
          "cursor-pointer bg-red-50 text-red-700 hover:bg-red-100 dark:bg-red-500/10 dark:text-red-300 dark:hover:bg-red-500/20",
        )}
        title="Click para ver detalhes"
      >
        <RiErrorWarningLine className="mr-1 inline size-3" aria-hidden />
        {summary.errors} {summary.errors === 1 ? "erro" : "erros"}
        {summary.warnings > 0 && ` · ${summary.warnings} aviso(s)`}
      </button>
    )
  }

  return (
    <button
      type="button"
      onClick={onClick}
      className={cx(
        tableTokens.badge,
        "cursor-pointer bg-amber-50 text-amber-700 hover:bg-amber-100 dark:bg-amber-500/10 dark:text-amber-300 dark:hover:bg-amber-500/20",
      )}
      title="Click para ver detalhes"
    >
      <RiAlertLine className="mr-1 inline size-3" aria-hidden />
      {glossary.validationProblems(summary.total)}
    </button>
  )
}

// ─── ValidationDetailsPanel — abre quando o badge eh clicado ─────────────

function ValidationDetailsPanel({
  errors,
  onClose,
}: {
  errors: ValidationError[]
  onClose: () => void
}) {
  return (
    <div className="absolute left-3 top-3 z-10 max-w-md rounded-md border border-gray-200 bg-white p-3 text-xs shadow-lg dark:border-gray-800 dark:bg-gray-950">
      <div className="mb-2 flex items-center justify-between">
        <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          {errors.length} {errors.length === 1 ? "problema" : "problemas"} no fluxo
        </p>
        <button
          type="button"
          onClick={onClose}
          className="rounded p-1 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
          aria-label="Fechar"
        >
          ✕
        </button>
      </div>
      <ul className="space-y-1.5">
        {errors.slice(0, 8).map((e, i) => (
          <li
            key={i}
            className={cx(
              "flex items-start gap-2 rounded-sm px-2 py-1",
              e.level === "error"
                ? "bg-red-50 text-red-900 dark:bg-red-500/10 dark:text-red-200"
                : "bg-amber-50 text-amber-900 dark:bg-amber-500/10 dark:text-amber-200",
            )}
          >
            {e.level === "error" ? (
              <RiErrorWarningLine className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            ) : (
              <RiAlertLine className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            )}
            <span className="flex-1">{e.message}</span>
          </li>
        ))}
        {errors.length > 8 && (
          <li className="px-2 py-1 text-gray-500 dark:text-gray-400">
            ...e mais {errors.length - 8} {errors.length - 8 === 1 ? "problema" : "problemas"}.
          </li>
        )}
      </ul>
    </div>
  )
}

// ─── Palette ────────────────────────────────────────────────────────────

function Palette({
  entries,
  canEdit,
  onAdd,
}: {
  entries: PaletteEntry[]
  canEdit: boolean
  /** Click no item — adiciona ao centro do canvas. Drag-and-drop ainda
   *  funciona em paralelo (drop handler do canvas processa o evento). */
  onAdd: (entry: PaletteEntry) => void
}) {
  const grouped = React.useMemo(() => groupByJourney(entries), [entries])

  return (
    <aside className="w-64 shrink-0 overflow-y-auto border-r border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-950">
      <p className={cx(tableTokens.header, "mb-1")}>{glossary.nodePlural}</p>
      <p className={cx(tableTokens.cellSecondary, "mb-3")}>
        Click pra adicionar ou arraste pro canvas
      </p>
      <div className="space-y-4">
        {JOURNEY_ORDER.map((journey) => {
          const items = grouped[journey] ?? []
          if (items.length === 0) return null
          return (
            <div key={journey}>
              <div className="mb-1.5">
                <p className="text-[11px] font-semibold uppercase tracking-wider text-gray-700 dark:text-gray-300">
                  {JOURNEY_LABEL[journey]}
                </p>
                <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
                  {JOURNEY_HINT[journey]}
                </p>
              </div>
              <div className="space-y-1">
                {items.map((entry) => {
                  const Icon = ICON_MAP[entry.icon] ?? RiRobot2Line
                  const enabled = entry.available && canEdit
                  return (
                    <button
                      key={entry.paletteId}
                      type="button"
                      draggable={entry.available}
                      disabled={!enabled}
                      onClick={() => {
                        if (!enabled) return
                        onAdd(entry)
                      }}
                      onDragStart={(e) => {
                        if (!entry.available) {
                          e.preventDefault()
                          return
                        }
                        e.dataTransfer.setData(DND_KEY, JSON.stringify(entry))
                        e.dataTransfer.effectAllowed = "move"
                      }}
                      className={cx(
                        "flex w-full items-center gap-2 rounded-md border px-2 py-1.5 text-left transition-colors",
                        enabled
                          ? "cursor-grab border-gray-200 bg-white hover:border-blue-500 hover:bg-blue-50/40 active:cursor-grabbing dark:border-gray-800 dark:bg-gray-900 dark:hover:border-blue-500 dark:hover:bg-blue-500/5"
                          : "cursor-not-allowed border-gray-100 bg-gray-50 opacity-60 dark:border-gray-900 dark:bg-gray-900",
                      )}
                      title={entry.description}
                    >
                      <Icon
                        className={cx(
                          "size-4 shrink-0",
                          enabled
                            ? "text-gray-700 dark:text-gray-300"
                            : "text-gray-400 dark:text-gray-600",
                        )}
                        aria-hidden
                      />
                      <span
                        className={cx(
                          "flex-1 truncate text-xs",
                          enabled
                            ? "text-gray-900 dark:text-gray-100"
                            : "text-gray-500 dark:text-gray-500",
                        )}
                      >
                        {entry.label}
                      </span>
                      {!entry.available && (
                        <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-amber-700 dark:bg-amber-500/10 dark:text-amber-300">
                          em breve
                        </span>
                      )}
                    </button>
                  )
                })}
              </div>
            </div>
          )
        })}
      </div>
      <div className="mt-6 rounded-md bg-blue-50 p-3 text-xs text-blue-900 dark:bg-blue-500/10 dark:text-blue-200">
        <p className="font-medium">Dicas</p>
        <ul className="mt-1 list-inside list-disc space-y-0.5">
          <li>Click numa etapa pra adicionar ao centro</li>
          <li>Ou arraste pro canvas pra posicionar onde quiser</li>
          <li>Arraste de uma etapa a outra pra conectar</li>
          <li>Click numa conexao pra editar a condicao</li>
          <li>Selecione + Delete remove etapa/conexao</li>
          <li>Ctrl+scroll pra zoom</li>
        </ul>
      </div>
    </aside>
  )
}

