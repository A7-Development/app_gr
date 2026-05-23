// src/app/(app)/credito/workflows/[id]/editor/_components/VariablesPill.tsx
//
// Overlay no topo do canvas que mostra TODAS as variáveis disponíveis
// upstream do nó selecionado — clicáveis pra copiar a expressão de
// template (`{{node.X.output.Y}}` ou `{{trigger.Y}}`).
//
// Por que existe:
// O analista que edita um nó (ex.: `bureau_query.entity_ref`) precisa
// saber quais variáveis pode referenciar. Sem isso, ele decora caminhos
// dotted ou abre o canvas em outra aba pra ver o que cada nó upstream
// publica. A pill resolve isso visualmente: lista chips coloridos por
// tipo, com label do nó de origem.
//
// Source: o backend retorna `produced_by_node` (Fase 3a) — caminhamos
// upstream a partir do nó selecionado e juntamos tudo que ancestrais
// publicam, incluindo o trigger.

"use client"

import * as React from "react"
import { RiFileCopyLine, RiInformationLine } from "@remixicon/react"
import type { Edge, Node } from "@xyflow/react"

import { varTypeMeta } from "@/design-system/tokens/var-type"
import { cx } from "@/lib/utils"

import type { StrataNodeData } from "./StrataNode"

type AvailableVar = {
  /** Caminho dotted resolvido em runtime (ex.: `node.hi1.output.cnpj`). */
  expr: string
  /** Template completo pra copy/paste no Inspector. */
  template: string
  /** Nome curto da variável (ex.: "cnpj"). */
  name: string
  /** Tipo semântico declarado (string vindo do backend). */
  varType: string
  /** Label do nó de origem (ex.: "Colher CNPJ" ou "Início"). */
  sourceLabel: string
  /** Tipo do nó de origem (ex.: "trigger", "human_input"). */
  sourceType: string
}

export function VariablesPill({
  selectedNodeId,
  nodes,
  edges,
  producedByNode,
}: {
  selectedNodeId: string | null
  nodes: Node[]
  edges: Edge[]
  producedByNode: Record<string, Record<string, string>>
}) {
  const [copied, setCopied] = React.useState<string | null>(null)

  const available = React.useMemo<AvailableVar[]>(
    () => collectUpstream(selectedNodeId, nodes, edges, producedByNode),
    [selectedNodeId, nodes, edges, producedByNode],
  )

  if (!selectedNodeId) {
    return null
  }

  if (available.length === 0) {
    return (
      <div className="absolute left-3 top-3 z-10 flex items-center gap-2 rounded-md border border-gray-200 bg-white/95 px-3 py-1.5 text-xs text-gray-500 shadow-sm backdrop-blur-sm dark:border-gray-800 dark:bg-gray-950/95 dark:text-gray-400">
        <RiInformationLine className="size-3.5" aria-hidden />
        Nenhuma variável upstream — este nó é a raiz do playbook.
      </div>
    )
  }

  async function copyTemplate(template: string) {
    try {
      await navigator.clipboard.writeText(template)
      setCopied(template)
      setTimeout(() => setCopied(null), 1500)
    } catch {
      // Browser bloqueou clipboard, ignora.
    }
  }

  return (
    <div className="absolute left-3 top-3 z-10 max-w-[calc(100%-1.5rem)] rounded-md border border-gray-200 bg-white/95 px-2 py-1.5 shadow-sm backdrop-blur-sm dark:border-gray-800 dark:bg-gray-950/95">
      <div className="mb-1 flex items-center gap-1.5 px-1 text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
        <RiInformationLine className="size-3" aria-hidden />
        Variáveis disponíveis ({available.length})
      </div>
      <div className="flex flex-wrap gap-1">
        {available.map((v) => {
          const meta = varTypeMeta(v.varType)
          const isCopied = copied === v.template
          return (
            <button
              key={v.expr}
              type="button"
              onClick={() => copyTemplate(v.template)}
              title={`${v.template}\n(de ${v.sourceLabel} · ${meta.description})\n\nClick pra copiar`}
              className={cx(
                "group inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium transition-colors",
                meta.chipClass,
                "hover:ring-1 hover:ring-blue-400 dark:hover:ring-blue-500",
              )}
            >
              <span aria-hidden className={cx("size-1.5 rounded-full", meta.dotClass)} />
              <span className="font-mono">{v.name}</span>
              <span className="text-gray-500 dark:text-gray-500">·</span>
              <span className="text-[9px] text-gray-600 dark:text-gray-400">
                {v.sourceLabel}
              </span>
              {isCopied ? (
                <span className="ml-0.5 text-[9px] text-emerald-600 dark:text-emerald-400">
                  copiado!
                </span>
              ) : (
                <RiFileCopyLine
                  className="ml-0.5 size-2.5 opacity-0 transition-opacity group-hover:opacity-100"
                  aria-hidden
                />
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}

/**
 * Faz BFS reverso do `selectedNodeId` pelo grafo de edges, coletando
 * todas as variáveis publicadas por nós ancestrais (e pelo trigger).
 */
function collectUpstream(
  selectedNodeId: string | null,
  nodes: Node[],
  edges: Edge[],
  producedByNode: Record<string, Record<string, string>>,
): AvailableVar[] {
  if (!selectedNodeId) return []

  // Build reverse adjacency: target -> [sources]
  const incoming = new Map<string, string[]>()
  for (const n of nodes) incoming.set(n.id, [])
  for (const e of edges) {
    const list = incoming.get(e.target)
    if (list && !list.includes(e.source)) list.push(e.source)
  }

  // BFS pra ancestrais.
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

  // Pra cada ancestral, listar produces.
  const result: AvailableVar[] = []
  const nodeById = new Map(nodes.map((n) => [n.id, n]))
  for (const ancestorId of Array.from(ancestorIds)) {
    const ancestorNode = nodeById.get(ancestorId)
    if (!ancestorNode) continue
    const ancestorData = ancestorNode.data as unknown as StrataNodeData
    const ancestorVars = producedByNode[ancestorId] ?? {}
    const sourceLabel = ancestorData.label || ancestorData.nodeType
    for (const [name, varType] of Object.entries(ancestorVars)) {
      // Trigger usa template `{{trigger.X}}` (sem prefixo `node`).
      const isTrigger = ancestorData.nodeType === "trigger"
      const expr = isTrigger ? `trigger.${name}` : `node.${ancestorId}.output.${name}`
      const template = `{{${expr}}}`
      result.push({
        expr,
        template,
        name,
        varType,
        sourceLabel,
        sourceType: ancestorData.nodeType,
      })
    }
  }
  // Ordena: trigger primeiro, depois alfabético por sourceLabel + name.
  result.sort((a, b) => {
    if (a.sourceType === "trigger" && b.sourceType !== "trigger") return -1
    if (a.sourceType !== "trigger" && b.sourceType === "trigger") return 1
    const cmp = a.sourceLabel.localeCompare(b.sourceLabel)
    if (cmp !== 0) return cmp
    return a.name.localeCompare(b.name)
  })
  return result
}
