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
  RiAiAgentLine,
  RiAlertLine,
  RiArrowDownSLine,
  RiArrowLeftLine,
  RiArrowRightSLine,
  RiBankLine,
  RiBarChart2Line,
  RiCheckboxCircleLine,
  RiCheckLine,
  RiCloseLine,
  RiDatabase2Line,
  RiEditLine,
  RiErrorWarningLine,
  RiFileList3Line,
  RiFilePdf2Line,
  RiFileSearchLine,
  RiFlashlightLine,
  RiGitBranchLine,
  RiGlobalLine,
  RiGovernmentLine,
  RiMapPin2Line,
  RiNodeTree,
  RiNotification3Line,
  RiPlayCircleLine,
  RiPriceTag3Line,
  RiQuillPenLine,
  RiRobot2Line,
  RiRouteLine,
  RiSaveLine,
  RiScales3Line,
  RiSearchLine,
  RiShieldStarLine,
  RiStarSmileLine,
  RiTeamLine,
  RiUploadCloud2Line,
  type RemixiconComponentType,
} from "@remixicon/react"
import { toast } from "sonner"

import { Button } from "@/components/tremor/Button"
import { PageHeader } from "@/design-system/components"
import {
  credito,
  type AgentMeta,
  type DataProduct,
  type NodeTypeMeta,
  type WorkflowDefinitionRead,
  type WorkflowGraph,
} from "@/lib/credito-client"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

import { AgentHoverCard } from "./_components/AgentHoverCard"
import { AgentCatalogContext } from "./_components/NodeContract"
import { EsteiraPreviewPanel } from "./_components/EsteiraPreviewPanel"
import { RoteiroView } from "./_components/RoteiroView"
import {
  decorateEdgesWithLabels,
  suggestBranchCondition,
} from "./_lib/edge-label"
import { computeLineage, type Lineage } from "./_lib/lineage"
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
  type JourneyCategory,
  type PaletteEntry,
  buildPaletteEntries,
  groupByJourney,
  JOURNEY_HINT,
  JOURNEY_LABEL,
  JOURNEY_ORDER,
  PRIMITIVE_TYPES,
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
  RiGovernmentLine,
  RiNotification3Line,
  // Per-agent icons (override do RiRobot2Line generico) — variedade visual
  // sinaliza riqueza do catalogo de specialist agents.
  RiBarChart2Line,
  RiBankLine,
  RiScales3Line,
  RiTeamLine,
  RiMapPin2Line,
  RiNodeTree,
  RiQuillPenLine,
  RiFileList3Line,
  RiPriceTag3Line,
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
      joinMode: n.join_mode,
    } satisfies StrataNodeData,
  }))
  const edges: Edge[] = graph.edges.map((e) => ({
    id: e.id,
    source: e.source,
    target: e.target,
    // Restaura a ancora persistida (top/right/bottom/left). Edges salvas ANTES
    // do fix de persistencia nao tem handle: em vez de cair todas no primeiro
    // handle ("top" -> bug visual), assume o fluxo vertical natural
    // (sai por baixo "bottom", entra por cima "top"). O usuario re-arrasta o
    // que quiser e salva — a partir dai a escolha dele persiste.
    sourceHandle: e.source_handle ?? "bottom",
    targetHandle: e.target_handle ?? "top",
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
    // Rotulo de dominio ("se score >= 700" / "senao") e aplicado de forma
    // centralizada por decorateEdgesWithLabels (F5) — aqui so o dado.
    data: { condition: e.condition },
    animated: false,
  }))
  return { nodes, edges }
}

// React Flow → WorkflowGraph (for save).
function reactFlowToGraph(nodes: Node[], edges: Edge[]): WorkflowGraph {
  return {
    nodes: nodes.map((n) => {
      const d = n.data as unknown as StrataNodeData
      // join_mode so vai pro payload quando NAO e o default ("all"). Mantem
      // o JSONB do graph limpo — nodes sem fan-in nao carregam ruido.
      const joinMode = d.joinMode && d.joinMode !== "all" ? d.joinMode : undefined
      return {
        id: n.id,
        type: d.nodeType,
        label: d.label ?? null,
        config: d.config ?? {},
        position: { x: n.position.x, y: n.position.y },
        ...(joinMode ? { join_mode: joinMode } : {}),
      }
    }),
    edges: edges.map((e) => ({
      id: e.id,
      source: e.source,
      target: e.target,
      // Persiste a ancora (lado do node) que o usuario escolheu — sem isto,
      // ao recarregar todas as edges caem no primeiro handle ("top").
      source_handle: e.sourceHandle ?? null,
      target_handle: e.targetHandle ?? null,
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

  const { data: agentCatalog } = useQuery({
    queryKey: ["credito", "agent-catalog"],
    queryFn: () => credito.workflows.agentCatalog(),
  })

  const { data: dataProducts } = useQuery({
    queryKey: ["credito", "data-products"],
    queryFn: () => credito.workflows.dataProducts(),
  })

  const { data: activeWorkflow } = useQuery({
    queryKey: ["credito", "workflow-active", workflow?.name],
    queryFn: async () => {
      try {
        return await credito.workflows.getActive(workflow!.name)
      } catch (e) {
        // 404 é esperado quando nenhuma versão deste fluxo foi publicada
        // ainda (estado normal de DRAFT). Engole pra não poluir o console.
        if ((e as { status?: number }).status === 404) return null
        throw e
      }
    },
    enabled: Boolean(workflow?.name),
    retry: false,
  })

  if (isLoading || !workflow) {
    return (
      <div className="px-6 py-6">
        <p className={tableTokens.cellSecondary}>Carregando playbook...</p>
      </div>
    )
  }

  return (
    <div className="flex h-[calc(100vh-65px)] flex-col">
      <ReactFlowProvider>
        {/* Catálogo via context: o StrataNode (renderizado pelo React Flow)
            monta o RECEBE do contrato dos agentes sem inflar node.data. */}
        <AgentCatalogContext.Provider value={agentCatalog ?? []}>
          <EditorBody
            workflow={workflow}
            activeWorkflow={activeWorkflow ?? null}
            nodeTypes={nodeTypes ?? []}
            agentCatalog={agentCatalog ?? []}
            dataProducts={dataProducts ?? []}
            onBack={() => router.push("/credito/workflows")}
          />
        </AgentCatalogContext.Provider>
      </ReactFlowProvider>
    </div>
  )
}

// ─── EditorBody — needs ReactFlowProvider context ───────────────────────

function EditorBody({
  workflow,
  activeWorkflow,
  nodeTypes,
  agentCatalog,
  dataProducts,
  onBack,
}: {
  workflow: WorkflowDefinitionRead
  activeWorkflow: WorkflowDefinitionRead | null
  nodeTypes: NodeTypeMeta[]
  agentCatalog: AgentMeta[]
  dataProducts: DataProduct[]
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
  const [esteiraOpen, setEsteiraOpen] = React.useState(false)
  const [viewMode, setViewMode] = React.useState<"canvas" | "roteiro">("canvas")

  // Re-sync when playbook changes (after save).
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
  // F3: linhagem de dados do node selecionado — quem alimenta (refs no meu
  // config/edges) e quem consome (refs a node.<eu>.output.* nos outros).
  const lineage = React.useMemo<Lineage | null>(
    () => (selectedNodeId ? computeLineage(selectedNodeId, nodes, edges) : null),
    [selectedNodeId, nodes, edges],
  )

  const nodesWithStatus = React.useMemo<Node[]>(
    () =>
      nodes.map((n) => {
        const status = nodeStatusMap.get(n.id)
        const data = n.data as unknown as StrataNodeData
        const newStatus: ValidationStatus = status?.status ?? "ok"
        const newProduced = producedByNode[n.id] ?? undefined
        const newLineage = lineage?.roleOf(n.id)
        const newLineageVars = lineage
          ? (lineage.feeders.get(n.id) ?? lineage.consumers.get(n.id))
          : undefined
        if (
          data.validationStatus === newStatus &&
          data.validationMessage === status?.message &&
          data.producedVars === newProduced &&
          data.lineageRole === newLineage &&
          data.lineageVars === newLineageVars
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
            lineageRole: newLineage,
            lineageVars: newLineageVars,
          } satisfies StrataNodeData,
        }
      }),
    [nodes, nodeStatusMap, producedByNode, lineage],
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

  const updateNodeJoinMode = React.useCallback(
    (nodeId: string, joinMode: "any" | "all") => {
      setNodes((nds) =>
        nds.map((n) =>
          n.id === nodeId
            ? { ...n, data: { ...(n.data as StrataNodeData), joinMode } }
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
              }
            : e,
        ),
      )
      setDirty(true)
    },
    [setEdges],
  )

  // F5: rotulos de dominio nas conexoes ("se score ≥ 700" / "senao") —
  // derivados a cada mudanca; o estado original das edges fica intacto.
  const displayEdges = React.useMemo(() => decorateEdgesWithLabels(edges), [edges])

  // ─── Adicionar etapa ao canvas (compartilhado por drag-drop e click) ─

  const addNodeFromEntry = React.useCallback(
    (entry: PaletteEntry, position?: { x: number; y: number }) => {
      if (!canEdit) {
        toast.error("Este playbook esta arquivado e nao pode ser editado.")
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
      setEdges((eds) => {
        // F5: saindo de um Branch Condicional, sugere o par sim/nao — a 1a
        // saida ganha "resultado e sim", a 2a "resultado e nao". O usuario
        // edita no popover da conexao se quiser outra regra.
        const sourceNode = reactFlow.getNode(connection.source as string)
        const sourceType = (sourceNode?.data as { nodeType?: string } | undefined)
          ?.nodeType
        let condition: string | null = null
        if (sourceType === "conditional_branch") {
          const outgoing = eds.filter((e) => e.source === connection.source)
          condition = suggestBranchCondition(connection.source as string, outgoing)
          if (condition) {
            toast.info(
              `Conector sugerido: "${condition.includes("true") ? "se resultado e sim" : "senao"}" — clique na conexao pra ajustar.`,
            )
          }
        }
        return addEdge(
          {
            ...connection,
            id: `e_${connection.source}_${connection.target}_${Math.random().toString(36).slice(2, 6)}`,
            type: "smoothstep",
            data: { condition },
          },
          eds,
        )
      })
      setDirty(true)
    },
    [canEdit, setEdges, reactFlow],
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

  // ─── Save (PATCH → new version; template Strata → cria copia do tenant) ──
  //
  // Template global (tenant_id NULL) e imutavel por design — o PATCH recusa
  // com 404. Salvar a partir de um template cria um playbook NOVO do tenant
  // com o grafo editado (POST /workflows) e redireciona pro editor da copia.
  const isTemplate = workflow.tenant_id === null

  const saveMutation = useMutation({
    mutationFn: () => {
      const graph = reactFlowToGraph(nodes, edges)
      if (isTemplate) {
        return credito.workflows.create({
          name: `${workflow.name} (copia)`,
          description: workflow.description,
          category: workflow.category,
          graph,
        })
      }
      return credito.workflows.update(workflow.id, {
        graph,
        description: workflow.description,
      })
    },
    onSuccess: (newWorkflow) => {
      toast.success(
        isTemplate
          ? `Template e imutavel — salvo como copia sua: "${newWorkflow.name}".`
          : `Salvo como v${newWorkflow.version}.`,
      )
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
    () => buildPaletteEntries(nodeTypes, dataProducts),
    [nodeTypes, dataProducts],
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
              <div className="flex items-center overflow-hidden rounded-md border border-gray-200 dark:border-gray-800">
                {(["canvas", "roteiro"] as const).map((m) => (
                  <button
                    key={m}
                    type="button"
                    onClick={() => setViewMode(m)}
                    className={cx(
                      "px-2.5 py-1 text-xs font-medium transition-colors",
                      viewMode === m
                        ? "bg-blue-500 text-white"
                        : "bg-white text-gray-600 hover:bg-gray-50 dark:bg-gray-950 dark:text-gray-400 dark:hover:bg-gray-900",
                    )}
                    title={
                      m === "canvas"
                        ? "Editar o fluxo no canvas visual"
                        : "Ler o fluxo como roteiro numerado em portugues"
                    }
                  >
                    {m === "canvas" ? "Canvas" : "Roteiro"}
                  </button>
                ))}
              </div>
              <Button
                variant="ghost"
                onClick={() => setEsteiraOpen((o) => !o)}
                title="Mostra como este fluxo vira as estações que o analista percorre no dossiê."
              >
                <RiRouteLine className="size-4" aria-hidden />
                Esteira
              </Button>
              <Button
                variant="ghost"
                onClick={() => setTestDrawerOpen(true)}
                title="Roda o playbook em modo sandbox sem chamar Serasa nem Anthropic."
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
                    : isTemplate
                      ? "Template Strata e imutavel — salvar cria uma copia editavel sua"
                      : "Salva uma nova versao em rascunho com o estado atual"
                }
              >
                <RiSaveLine className="size-4" aria-hidden />
                {isTemplate ? "Salvar como copia" : glossary.saveAsNewVersion}
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
          agentCatalog={agentCatalog}
          onAdd={(entry) => addNodeFromEntry(entry)}
        />

        {/* Canvas */}
        <div className="relative flex-1 bg-gray-50 dark:bg-gray-950" ref={reactFlowWrapper}>
          {dirty && (
            <div className="absolute right-3 top-3 z-10 rounded-md border border-amber-200 bg-amber-50 px-3 py-1.5 text-xs font-medium text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
              {glossary.unsavedChanges}
            </div>
          )}
          {viewMode === "roteiro" && (
            <RoteiroView
              nodes={nodes}
              edges={edges}
              agentCatalog={agentCatalog}
              onGoToNode={(id) => {
                setViewMode("canvas")
                setSelectedNodeId(id)
              }}
            />
          )}
          {esteiraOpen && (
            <EsteiraPreviewPanel
              nodes={nodes}
              edges={edges}
              onClose={() => setEsteiraOpen(false)}
              onFocusNode={(id) => setSelectedNodeId(id)}
            />
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
            edges={displayEdges}
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
            agentCatalog={agentCatalog}
            producedByNode={producedByNode}
            onUpdateConfig={updateNodeConfig}
            onUpdateLabel={updateNodeLabel}
            onUpdateJoinMode={updateNodeJoinMode}
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
          {errors.length} {errors.length === 1 ? "problema" : "problemas"} no playbook
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
  agentCatalog,
  onAdd,
}: {
  entries: PaletteEntry[]
  canEdit: boolean
  /** Catalogo per-agente (vem de /credito/agent-catalog). Usado pelo
   *  AgentHoverCard para mostrar inputs declarados no tooltip do palette. */
  agentCatalog: AgentMeta[]
  /** Click no item — adiciona ao centro do canvas. Drag-and-drop ainda
   *  funciona em paralelo (drop handler do canvas processa o evento). */
  onAdd: (entry: PaletteEntry) => void
}) {
  const grouped = React.useMemo(() => groupByJourney(entries), [entries])
  const featured = React.useMemo(
    () => entries.filter((e) => e.featured),
    [entries],
  )

  // Filtro com debounce leve. "/" foca o input quando palette esta visivel
  // e o foco nao esta em outro field; Esc limpa.
  const [filterRaw, setFilterRaw] = React.useState("")
  const [filter, setFilter] = React.useState("")
  React.useEffect(() => {
    const handle = window.setTimeout(() => setFilter(filterRaw.trim().toLowerCase()), 150)
    return () => window.clearTimeout(handle)
  }, [filterRaw])

  const filterRef = React.useRef<HTMLInputElement>(null)
  React.useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const target = e.target as HTMLElement | null
      const isTyping =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      if (e.key === "/" && !isTyping) {
        e.preventDefault()
        filterRef.current?.focus()
      }
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [])

  // Estado de jornadas colapsadas (Set). Default: tudo expandido.
  const [collapsedJourneys, setCollapsedJourneys] = React.useState<
    Set<JourneyCategory>
  >(() => new Set())
  const toggleJourney = React.useCallback((j: JourneyCategory) => {
    setCollapsedJourneys((prev) => {
      const next = new Set(prev)
      if (next.has(j)) next.delete(j)
      else next.add(j)
      return next
    })
  }, [])

  const matchesFilter = React.useCallback(
    (entry: PaletteEntry) => {
      if (!filter) return true
      const haystack = `${entry.label} ${entry.description}`.toLowerCase()
      return haystack.includes(filter)
    },
    [filter],
  )

  return (
    <aside className="w-80 shrink-0 overflow-y-auto border-r border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-950">
      <p className={cx(tableTokens.header, "mb-1")}>Catalogo de etapas</p>
      <p className={cx(tableTokens.cellSecondary, "mb-3")}>
        Arraste para o canvas ou clique para inserir
      </p>

      {/* Filtro */}
      <div className="relative mb-4">
        <RiSearchLine
          className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-gray-400 dark:text-gray-500"
          aria-hidden
        />
        <input
          ref={filterRef}
          type="text"
          value={filterRaw}
          onChange={(e) => setFilterRaw(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Escape") {
              setFilterRaw("")
              filterRef.current?.blur()
            }
          }}
          placeholder="Filtrar etapas..."
          className="w-full rounded-md border border-gray-200 bg-white py-1.5 pl-7 pr-8 text-xs text-gray-900 placeholder:text-gray-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100 dark:placeholder:text-gray-500"
        />
        {filterRaw ? (
          <button
            type="button"
            onClick={() => {
              setFilterRaw("")
              filterRef.current?.focus()
            }}
            className="absolute right-2 top-1/2 -translate-y-1/2 rounded p-0.5 text-gray-400 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-500 dark:hover:bg-gray-800 dark:hover:text-gray-200"
            aria-label="Limpar filtro"
          >
            <RiCloseLine className="size-3.5" aria-hidden />
          </button>
        ) : (
          <kbd className="absolute right-2 top-1/2 -translate-y-1/2 rounded border border-gray-200 bg-gray-50 px-1 py-0.5 font-mono text-[10px] text-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400">
            /
          </kbd>
        )}
      </div>

      <div className="space-y-4">
        {/* Destaques — so quando o filtro esta vazio. Quando o user filtra,
         *  a entry aparece no seu grupo natural; nao duplicar. */}
        {!filter && featured.length > 0 && (
          <FeaturedGroup
            entries={featured}
            canEdit={canEdit}
            agentCatalog={agentCatalog}
            onAdd={onAdd}
          />
        )}

        {JOURNEY_ORDER.map((journey) => {
          const items = (grouped[journey] ?? []).filter(matchesFilter)
          if (items.length === 0) return null
          const isCollapsed = !filter && collapsedJourneys.has(journey)
          return (
            <div key={journey}>
              <button
                type="button"
                onClick={() => toggleJourney(journey)}
                className="group mb-1.5 flex w-full items-start gap-1.5 text-left"
              >
                {isCollapsed ? (
                  <RiArrowRightSLine
                    className="mt-0.5 size-3.5 shrink-0 text-gray-500 transition-colors group-hover:text-gray-900 dark:text-gray-400 dark:group-hover:text-gray-100"
                    aria-hidden
                  />
                ) : (
                  <RiArrowDownSLine
                    className="mt-0.5 size-3.5 shrink-0 text-gray-500 transition-colors group-hover:text-gray-900 dark:text-gray-400 dark:group-hover:text-gray-100"
                    aria-hidden
                  />
                )}
                <div className="flex-1">
                  <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-gray-700 dark:text-gray-300">
                    <span>{JOURNEY_LABEL[journey]}</span>
                    <span className="text-gray-400 dark:text-gray-500">
                      ({items.length})
                    </span>
                    {journey === "ia" && (
                      <span
                        className="inline-flex items-center gap-0.5 rounded bg-gradient-to-r from-blue-100 to-violet-100 px-1.5 py-0.5 text-[9px] font-bold tracking-wider text-blue-700 dark:from-blue-500/20 dark:to-violet-500/20 dark:text-blue-300"
                        title="Etapas baseadas em modelos de IA"
                      >
                        <RiAiAgentLine className="size-2.5" aria-hidden />
                        IA
                      </span>
                    )}
                  </p>
                  {!isCollapsed && (
                    <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
                      {JOURNEY_HINT[journey]}
                    </p>
                  )}
                </div>
              </button>
              {!isCollapsed && (
                <div className="space-y-1">
                  {items.map((entry) => (
                    <PaletteItem
                      key={entry.paletteId}
                      entry={entry}
                      canEdit={canEdit}
                      agentCatalog={agentCatalog}
                      onAdd={onAdd}
                    />
                  ))}
                </div>
              )}
            </div>
          )
        })}

        {/* Estado vazio quando filtro nao casa com nada */}
        {filter &&
          JOURNEY_ORDER.every(
            (j) => (grouped[j] ?? []).filter(matchesFilter).length === 0,
          ) && (
            <div className="rounded-md border border-dashed border-gray-200 bg-gray-50 p-4 text-center text-xs text-gray-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
              Nenhuma etapa bate com{" "}
              <span className="font-mono">&quot;{filterRaw}&quot;</span>.
            </div>
          )}
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
          <li>
            <kbd className="rounded border border-blue-200 bg-white px-1 py-0.5 font-mono text-[10px] dark:border-blue-500/30 dark:bg-blue-500/5">
              /
            </kbd>{" "}
            foca o filtro
          </li>
        </ul>
      </div>
    </aside>
  )
}

// ─── Featured group ──────────────────────────────────────────────────────
//
// Grupo virtual no topo da palette com entries marcados `featured: true`
// no `etapas.ts::buildPaletteEntries`. Curado a mao — sem tracking de uso.
// So aparece quando filtro vazio (com filtro, entries ja estao nos grupos
// naturais; duplicar confunde).

function FeaturedGroup({
  entries,
  canEdit,
  agentCatalog,
  onAdd,
}: {
  entries: PaletteEntry[]
  canEdit: boolean
  agentCatalog: AgentMeta[]
  onAdd: (entry: PaletteEntry) => void
}) {
  return (
    <div>
      <div className="mb-1.5 flex items-center gap-1.5">
        <RiStarSmileLine
          className="size-3.5 shrink-0 text-blue-600 dark:text-blue-400"
          aria-hidden
        />
        <p className="text-[11px] font-semibold uppercase tracking-wider text-blue-800 dark:text-blue-300">
          Destaques{" "}
          <span className="text-blue-400 dark:text-blue-500">
            ({entries.length})
          </span>
        </p>
      </div>
      <div className="space-y-1">
        {entries.map((entry) => (
          <PaletteItem
            key={`featured-${entry.paletteId}`}
            entry={entry}
            canEdit={canEdit}
            agentCatalog={agentCatalog}
            onAdd={onAdd}
            featured
          />
        ))}
      </div>
    </div>
  )
}

// ─── PaletteItem ─────────────────────────────────────────────────────────

function PaletteItem({
  entry,
  canEdit,
  agentCatalog,
  onAdd,
  featured = false,
}: {
  entry: PaletteEntry
  canEdit: boolean
  /** Catalogo per-agente — usado pelo AgentHoverCard quando entry e
   *  specialist_agent. Tupla vazia em entries nao-agente. */
  agentCatalog: AgentMeta[]
  onAdd: (entry: PaletteEntry) => void
  /** Quando renderizado dentro do grupo "Destaques", reforca visualmente
   *  com border azul mais forte e ring sutil. */
  featured?: boolean
}) {
  const Icon = ICON_MAP[entry.icon] ?? RiRobot2Line
  const enabled = entry.available && canEdit
  // Detecta entries de specialist_agent — paletteId no formato
  // "specialist_agent:<agent_name>". Nesses casos, o button vira trigger
  // de um AgentHoverCard rico (descricao, inputs declarados, outputs).
  const isAgent = entry.paletteId.startsWith("specialist_agent:")
  const agentName = isAgent
    ? entry.paletteId.slice("specialist_agent:".length)
    : null

  const button = (
    <button
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
          ? featured
            ? "cursor-grab border-blue-300 bg-blue-50/30 hover:border-blue-500 hover:bg-blue-50/60 active:cursor-grabbing dark:border-blue-500/40 dark:bg-blue-500/5 dark:hover:border-blue-500 dark:hover:bg-blue-500/10"
            : "cursor-grab border-gray-200 bg-white hover:border-blue-500 hover:bg-blue-50/40 active:cursor-grabbing dark:border-gray-800 dark:bg-gray-900 dark:hover:border-blue-500 dark:hover:bg-blue-500/5"
          : "cursor-not-allowed border-gray-100 bg-gray-50 opacity-60 dark:border-gray-900 dark:bg-gray-900",
      )}
      // Quando isAgent, o HoverCard substitui o tooltip nativo.
      title={isAgent ? undefined : entry.description}
    >
      {/* Barra de TIPO (agente/check/externo/...) — sinal de cor pre-atentivo. */}
      <span
        aria-hidden
        className={cx(
          "h-4 w-0.5 shrink-0 rounded-full",
          PRIMITIVE_TYPES[entry.primitiveType].bar,
          !enabled && "opacity-40",
        )}
      />
      <Icon
        className={cx(
          "size-4 shrink-0",
          enabled
            ? featured
              ? "text-blue-700 dark:text-blue-300"
              : "text-gray-700 dark:text-gray-300"
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
      {/* Chip de TIPO — texto pequeno e muted (cor fica na barra). */}
      <span className="shrink-0 text-[9px] font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500">
        {PRIMITIVE_TYPES[entry.primitiveType].label}
      </span>
      {!entry.available && (
        <span className="rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-amber-700 dark:bg-amber-500/10 dark:text-amber-300">
          em breve
        </span>
      )}
    </button>
  )

  if (isAgent && agentName && entry.available) {
    return (
      <AgentHoverCard
        agentName={agentName}
        agentLabel={entry.label}
        description={entry.description}
        agentCatalog={agentCatalog}
      >
        {button}
      </AgentHoverCard>
    )
  }

  return button
}

