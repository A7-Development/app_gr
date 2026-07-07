// src/app/(app)/credito/workflows/[id]/editor/_components/VariablePicker.tsx
//
// Popover compacto pra inserir um template `{{...}}` num input. Mostra
// SOMENTE variáveis que (a) existem upstream do nó atual e (b) são do
// tipo esperado pelo campo (filtro opcional por VarType).
//
// Uso típico:
//   <VariablePicker
//     selectedNodeId={nodeId}
//     nodes={nodes}
//     edges={edges}
//     producedByNode={producedByNode}
//     filterType="cnpj"            // só CNPJs aparecem
//     onPick={(template) => {
//       // template = "{{node.X.output.cnpj}}" ou "{{trigger.cnpj}}"
//       setValue(currentValue + template)
//     }}
//   />
//
// Acompanha um botão "{ }" pequeno renderizado pelo caller; o popover
// abre on click. Se não houver variáveis compatíveis, mostra mensagem
// amigável e o botão fica disabled.

"use client"

import * as React from "react"
import { RiBracesLine, RiInformationLine } from "@remixicon/react"
import type { Edge, Node } from "@xyflow/react"

import { Button } from "@/components/tremor/Button"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/tremor/Popover"
import { varTypeMeta } from "@/design-system/tokens/var-type"
import { cx } from "@/lib/utils"

import type { StrataNodeData } from "./StrataNode"

type AvailableVar = {
  expr: string          // "node.X.output.cnpj" ou "trigger.cnpj"
  template: string      // "{{node.X.output.cnpj}}"
  name: string          // "cnpj"
  varType: string       // "cnpj"
  sourceLabel: string
  sourceType: string    // "trigger" | "human_input" | ...
}

export function VariablePicker({
  selectedNodeId,
  nodes,
  edges,
  producedByNode,
  filterType,
  onPick,
  disabled = false,
}: {
  selectedNodeId: string
  nodes: Node[]
  edges: Edge[]
  producedByNode: Record<string, Record<string, string>>
  /** Se passado, filtra pra só variáveis do tipo. */
  filterType?: string
  onPick: (template: string) => void
  disabled?: boolean
}) {
  const [open, setOpen] = React.useState(false)
  const [query, setQuery] = React.useState("")

  const allVars = React.useMemo(
    () => collectUpstream(selectedNodeId, nodes, edges, producedByNode),
    [selectedNodeId, nodes, edges, producedByNode],
  )

  const filtered = React.useMemo(() => {
    let vars = allVars
    if (filterType) {
      // STRING/OBJECT/LIST não filtra (esses são wildcards).
      const wildcards = new Set(["string", "object", "list"])
      if (!wildcards.has(filterType)) {
        vars = vars.filter(
          (v) => v.varType === filterType || wildcards.has(v.varType),
        )
      }
    }
    if (query.trim()) {
      const q = query.toLowerCase()
      vars = vars.filter(
        (v) =>
          v.name.toLowerCase().includes(q) ||
          v.sourceLabel.toLowerCase().includes(q),
      )
    }
    return vars
  }, [allVars, filterType, query])

  const noVars = allVars.length === 0
  const noMatches = allVars.length > 0 && filtered.length === 0

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          type="button"
          variant="ghost"
          disabled={disabled || noVars}
          className="h-8 shrink-0 px-2"
          title={
            noVars
              ? "Nenhuma variável disponível upstream"
              : filterType
                ? `Inserir variável (filtro: ${filterType})`
                : "Inserir variável upstream"
          }
        >
          <RiBracesLine className="size-3.5" aria-hidden />
          <span className="ml-1 text-[11px] font-mono">{`{ }`}</span>
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-80 p-0" align="end">
        <div className="border-b border-gray-100 p-2 dark:border-gray-900">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filtrar variáveis…"
            className="w-full rounded border border-gray-200 px-2 py-1 text-xs focus:border-blue-500 focus:outline-none dark:border-gray-800 dark:bg-gray-950"
            autoFocus
          />
          {filterType && (
            <p className="mt-1 flex items-center gap-1 text-[10px] text-gray-500 dark:text-gray-400">
              <RiInformationLine className="size-3" aria-hidden />
              Mostrando apenas tipo{" "}
              <span className="font-mono font-medium">{filterType}</span> +
              wildcards.
            </p>
          )}
        </div>
        <div className="max-h-72 overflow-y-auto py-1">
          {noVars && (
            <p className="px-3 py-4 text-center text-xs text-gray-500 dark:text-gray-400">
              Nenhuma variável upstream — este nó é a raiz do workflow.
            </p>
          )}
          {noMatches && (
            <p className="px-3 py-4 text-center text-xs text-gray-500 dark:text-gray-400">
              Nenhuma variável bate com o filtro.
            </p>
          )}
          {filtered.map((v) => {
            const meta = varTypeMeta(v.varType)
            return (
              <button
                key={v.expr}
                type="button"
                onClick={() => {
                  onPick(v.template)
                  setOpen(false)
                  setQuery("")
                }}
                className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs hover:bg-blue-50 dark:hover:bg-blue-500/5"
              >
                <span aria-hidden className={cx("size-2 shrink-0 rounded-full", meta.dotClass)} />
                <span className="font-mono text-gray-900 dark:text-gray-100">
                  {v.name}
                </span>
                <span className={cx("rounded px-1 py-0.5 text-[10px] font-medium", meta.chipClass)}>
                  {meta.label}
                </span>
                <span className="ml-auto truncate text-[10px] text-gray-500 dark:text-gray-400">
                  {v.sourceLabel}
                </span>
              </button>
            )
          })}
        </div>
        <div className="border-t border-gray-100 px-3 py-1.5 text-[10px] text-gray-500 dark:border-gray-900 dark:text-gray-400">
          Click pra inserir <span className="font-mono">{"{{...}}"}</span> no campo.
        </div>
      </PopoverContent>
    </Popover>
  )
}

/**
 * BFS reverso a partir do node selecionado, coletando variáveis upstream.
 * Mesmo algoritmo do VariablesPill — duplicado pra desacoplar (componentes
 * distintos com responsabilidades distintas).
 */
function collectUpstream(
  selectedNodeId: string,
  nodes: Node[],
  edges: Edge[],
  producedByNode: Record<string, Record<string, string>>,
): AvailableVar[] {
  const incoming = new Map<string, string[]>()
  for (const n of nodes) incoming.set(n.id, [])
  for (const e of edges) {
    const list = incoming.get(e.target)
    if (list && !list.includes(e.source)) list.push(e.source)
  }
  const ancestorIds = new Set<string>()
  const queue = [...(incoming.get(selectedNodeId) ?? [])]
  while (queue.length > 0) {
    const id = queue.shift()!
    if (ancestorIds.has(id)) continue
    ancestorIds.add(id)
    for (const next of incoming.get(id) ?? []) {
      if (!ancestorIds.has(next)) queue.push(next)
    }
  }
  const result: AvailableVar[] = []
  const nodeById = new Map(nodes.map((n) => [n.id, n]))
  for (const ancestorId of Array.from(ancestorIds)) {
    const ancestorNode = nodeById.get(ancestorId)
    if (!ancestorNode) continue
    const ancestorData = ancestorNode.data as unknown as StrataNodeData
    const ancestorVars = producedByNode[ancestorId] ?? {}
    const sourceLabel = ancestorData.label || ancestorData.nodeType
    for (const [name, varType] of Object.entries(ancestorVars)) {
      const isTrigger = ancestorData.nodeType === "trigger"
      const expr = isTrigger ? `trigger.${name}` : `node.${ancestorId}.output.${name}`
      result.push({
        expr,
        template: `{{${expr}}}`,
        name,
        varType,
        sourceLabel,
        sourceType: ancestorData.nodeType,
      })
    }
  }
  result.sort((a, b) => {
    if (a.sourceType === "trigger" && b.sourceType !== "trigger") return -1
    if (a.sourceType !== "trigger" && b.sourceType === "trigger") return 1
    const cmp = a.sourceLabel.localeCompare(b.sourceLabel)
    if (cmp !== 0) return cmp
    return a.name.localeCompare(b.name)
  })
  return result
}
