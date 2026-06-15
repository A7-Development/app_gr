// Preview /preview/organograma — PROTOTIPO (organograma de grupo economico).
//
// Render @xyflow/react a partir do retorno REAL do BDC `economic_group_relationships`.
// Multiplas empresas (registry _data/index.ts) via ?empresa=<slug>.
//
// Recursos:
//   - RAIAS POR SEGMENTO de atuacao (heuristica por razao social — sem CNAE real);
//   - nos ARRASTAVEIS (conectores bezier seguem) + botao "Reorganizar" (reseta);
//   - filtro de papel: Todos | Socios | Administradores;
//   - toggle ativos x todos.
//
// Limitacao: sem % de participacao (dataset on-demand -1203 disabled) e segmento
// inferido do nome (nao do CNAE). Ambos viram dado real quando o backend ligar.

"use client"

import * as React from "react"
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  type NodeTypes,
} from "@xyflow/react"
import "@xyflow/react/dist/style.css"
import { RiBuilding2Line, RiResetLeftLine, RiUserLine } from "@remixicon/react"

import { cx } from "@/lib/utils"

import { OrgNode } from "./_components/OrgNode"
import { SegHeaderNode } from "./_components/SegHeaderNode"
import { buildGraph, SEGMENTS, type LayoutMode, type RoleFilter } from "./_lib/layout"
import { EMPRESAS, getEmpresa } from "./_data"

const NODE_TYPES: NodeTypes = { org: OrgNode, segHeader: SegHeaderNode }

const ROLE_OPTIONS: { value: RoleFilter; label: string }[] = [
  { value: "all", label: "Todos" },
  { value: "socio", label: "Sócios" },
  { value: "admin", label: "Administradores" },
]

// Canvas isolado — useNodesState permite arrastar e o estado persiste.
// O `key` no pai remonta este componente quando empresa/filtro mudam,
// reaplicando o layout em raias + fitView.
function OrgCanvas({
  initialNodes,
  initialEdges,
}: {
  initialNodes: ReturnType<typeof buildGraph>["nodes"]
  initialEdges: ReturnType<typeof buildGraph>["edges"]
}) {
  const [nodes, , onNodesChange] = useNodesState(initialNodes)
  const [edges, , onEdgesChange] = useEdgesState(initialEdges)

  return (
    <ReactFlowProvider>
      <ReactFlow
        nodes={nodes}
        edges={edges}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        nodeTypes={NODE_TYPES}
        fitView
        fitViewOptions={{ padding: 0.12 }}
        minZoom={0.05}
        maxZoom={1.6}
        proOptions={{ hideAttribution: true }}
      >
        <Background gap={20} className="!bg-gray-50 dark:!bg-gray-900" />
        <Controls showInteractive={false} />
        <MiniMap
          pannable
          zoomable
          nodeColor={(n) => (n.data as { segmentColor?: string }).segmentColor ?? "#cbd5e1"}
          maskColor="rgba(0,0,0,0.04)"
        />
      </ReactFlow>
    </ReactFlowProvider>
  )
}

export default function OrganogramaPreviewPage() {
  const [slug, setSlug] = React.useState(EMPRESAS[0].slug)
  const [showInactive, setShowInactive] = React.useState(false)
  const [roleFilter, setRoleFilter] = React.useState<RoleFilter>("all")
  const [maxLevel, setMaxLevel] = React.useState(3)
  const [mode, setMode] = React.useState<LayoutMode>("hierarchy")
  const [resetKey, setResetKey] = React.useState(0)

  React.useEffect(() => {
    const q = new URLSearchParams(window.location.search).get("empresa")
    if (q && EMPRESAS.some((e) => e.slug === q)) setSlug(q)
  }, [])

  const selectEmpresa = React.useCallback((s: string) => {
    setSlug(s)
    const url = new URL(window.location.href)
    url.searchParams.set("empresa", s)
    window.history.replaceState(null, "", url.toString())
  }, [])

  const empresa = getEmpresa(slug)

  // niveis disponiveis no dataset (1..maxNivel) p/ o seletor
  const maxNivelDisponivel = React.useMemo(
    () => Math.max(1, ...empresa.nodes.map((n) => n.level)),
    [empresa],
  )

  const { nodes, edges } = React.useMemo(
    () =>
      buildGraph(empresa.nodes, empresa.edges, {
        rootId: empresa.rootId,
        showInactive,
        roleFilter,
        maxLevel,
        mode,
      }),
    [empresa, showInactive, roleFilter, maxLevel, mode],
  )

  const entidades = nodes.filter((n) => n.type === "org").length

  return (
    <div className="flex h-screen flex-col bg-gray-50 dark:bg-gray-950">
      {/* Header */}
      <header className="flex flex-col gap-2 border-b border-gray-200 bg-white px-6 py-3 dark:border-gray-800 dark:bg-gray-950">
        {/* Linha 1 — titulo + empresa + acoes */}
        <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
          <div className="mr-auto">
            <h1 className="text-[15px] font-semibold text-gray-900 dark:text-gray-50">
              Grupo Econômico — {empresa.label}
            </h1>
            <p className="text-[12px] text-gray-500 dark:text-gray-400">
              CNPJ {empresa.doc} · fonte: BigDataCorp ·{" "}
              <span className="font-medium">protótipo</span>
            </p>
          </div>

          {/* Modo de layout */}
          <div className="flex items-center gap-1 rounded-md border border-gray-200 p-0.5 dark:border-gray-800">
            {([
              { value: "hierarchy", label: "Hierarquia" },
              { value: "lanes", label: "Raias (A)" },
              { value: "radial", label: "Rede (B)" },
            ] as { value: LayoutMode; label: string }[]).map((o) => (
              <button
                key={o.value}
                type="button"
                onClick={() => setMode(o.value)}
                className={cx(
                  "h-[26px] rounded px-2.5 text-[12px] font-medium transition-colors",
                  o.value === mode
                    ? "bg-violet-500 text-white"
                    : "text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
                )}
              >
                {o.label}
              </button>
            ))}
          </div>

          {/* Seletor de empresa */}
          <div className="flex items-center gap-1 rounded-md border border-gray-200 p-0.5 dark:border-gray-800">
            {EMPRESAS.map((e) => (
              <button
                key={e.slug}
                type="button"
                onClick={() => selectEmpresa(e.slug)}
                className={cx(
                  "h-[26px] rounded px-2.5 text-[12px] font-medium transition-colors",
                  e.slug === slug
                    ? "bg-blue-500 text-white"
                    : "text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
                )}
              >
                {e.label}
              </button>
            ))}
          </div>

          {/* Filtro de papel */}
          <div className="flex items-center gap-1 rounded-md border border-gray-200 p-0.5 dark:border-gray-800">
            {ROLE_OPTIONS.map((o) => (
              <button
                key={o.value}
                type="button"
                onClick={() => setRoleFilter(o.value)}
                className={cx(
                  "h-[26px] rounded px-2.5 text-[12px] font-medium transition-colors",
                  o.value === roleFilter
                    ? "bg-gray-900 text-white dark:bg-gray-100 dark:text-gray-900"
                    : "text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
                )}
              >
                {o.label}
              </button>
            ))}
          </div>

          {/* Seletor de profundidade (niveis) */}
          <div className="flex items-center gap-1 rounded-md border border-gray-200 p-0.5 dark:border-gray-800">
            <span className="px-1.5 text-[11px] font-medium text-gray-400">Níveis</span>
            {Array.from({ length: maxNivelDisponivel }, (_, i) => i + 1).map((lvl) => (
              <button
                key={lvl}
                type="button"
                onClick={() => setMaxLevel(lvl)}
                title={lvl === 1 ? "Raiz + vínculos diretos" : `Raiz até o ${lvl}º nível`}
                className={cx(
                  "h-[26px] rounded px-2.5 text-[12px] font-medium transition-colors",
                  maxLevel === lvl
                    ? "bg-blue-500 text-white"
                    : "text-gray-600 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
                )}
              >
                {lvl === 1 ? "Nível 1" : `Até ${lvl}`}
              </button>
            ))}
          </div>

          {/* Toggle ativos/encerrados */}
          <button
            type="button"
            onClick={() => setShowInactive((v) => !v)}
            className={cx(
              "h-[28px] rounded-md border px-2.5 text-[12px] font-medium transition-colors",
              showInactive
                ? "border-blue-500 bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
                : "border-gray-300 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200",
            )}
          >
            {showInactive ? "Todos os vínculos" : "Apenas ativos"}
          </button>

          {/* Reorganizar */}
          <button
            type="button"
            onClick={() => setResetKey((k) => k + 1)}
            className="inline-flex h-[28px] items-center gap-1 rounded-md border border-gray-300 bg-white px-2.5 text-[12px] font-medium text-gray-700 hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-200"
            title="Reaplica o layout em raias e reposiciona tudo"
          >
            <RiResetLeftLine className="size-3.5" aria-hidden />
            Reorganizar
          </button>
        </div>

        {/* Linha 2 — legenda de segmentos + dicas + contador */}
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          {SEGMENTS.map((s) => (
            <span
              key={s.key}
              className="inline-flex items-center gap-1 text-[11px] text-gray-600 dark:text-gray-300"
            >
              <span className="size-2.5 rounded-sm" style={{ backgroundColor: s.color }} />
              {s.label}
            </span>
          ))}
          <span className="ml-auto inline-flex items-center gap-3 text-[11px] text-gray-400">
            <span className="inline-flex items-center gap-1">
              <RiBuilding2Line className="size-3" /> PJ
            </span>
            <span className="inline-flex items-center gap-1">
              <RiUserLine className="size-3" /> PF
            </span>
            <span className="tabular-nums">
              {entidades} entidades · {edges.length} vínculos
            </span>
            <span className="italic">arraste os nós p/ reorganizar</span>
          </span>
        </div>
      </header>

      {/* Canvas */}
      <div className="min-h-0 flex-1">
        <OrgCanvas
          key={`${slug}-${mode}-${roleFilter}-${showInactive}-${maxLevel}-${resetKey}`}
          initialNodes={nodes}
          initialEdges={edges}
        />
      </div>
    </div>
  )
}
