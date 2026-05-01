// src/app/(app)/credito/workflows/[id]/editor/_components/EdgeConditionPopover.tsx
//
// Popover que abre ao clicar numa conexao do canvas.
// Permite editar a `condition` via ConditionBuilder (dropdowns campo+
// operador+valor) ou remover a conexao.
//
// Posicionado em coordenadas de tela (clientX/Y do click). Fecha no clique
// fora ou no Cancelar.

"use client"

import * as React from "react"
import { type Edge, type Node } from "@xyflow/react"
import { RiDeleteBinLine } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

import { getEtapaLabel } from "../_lib/glossary"
import type { StrataNodeData } from "./StrataNode"

import { ConditionBuilder } from "./ConditionBuilder"

type Props = {
  x: number
  y: number
  edge: Edge
  nodes: Node[]
  edges: Edge[]
  onSave: (condition: string | null) => void
  onClose: () => void
  onDelete: () => void
}

export function EdgeConditionPopover({
  x,
  y,
  edge,
  nodes,
  edges,
  onSave,
  onClose,
  onDelete,
}: Props) {
  const initialCondition =
    (edge.data as { condition?: string | null } | undefined)?.condition ?? null
  const [value, setValue] = React.useState<string | null>(initialCondition)

  const ref = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as HTMLElement)) {
        onClose()
      }
    }
    document.addEventListener("mousedown", onDocClick)
    return () => document.removeEventListener("mousedown", onDocClick)
  }, [onClose])

  // Position the popover near the click but stay within the viewport.
  const popX = Math.min(x, window.innerWidth - 480)
  const popY = Math.min(y, window.innerHeight - 320)

  // Labels amigaveis das pontas (em vez do id cru).
  const sourceLabel = labelOfNode(nodes, edge.source)
  const targetLabel = labelOfNode(nodes, edge.target)

  return (
    <div
      ref={ref}
      style={{ left: popX, top: popY }}
      className="fixed z-20 w-[460px] rounded-md border border-gray-200 bg-white p-4 shadow-lg dark:border-gray-800 dark:bg-gray-950"
    >
      <div className="space-y-3">
        <div>
          <p className={tableTokens.header}>Conexao</p>
          <p className="mt-0.5 text-xs text-gray-700 dark:text-gray-300">
            <span className="font-medium">{sourceLabel}</span>
            <span className="mx-1.5 text-gray-400">→</span>
            <span className="font-medium">{targetLabel}</span>
          </p>
        </div>

        <ConditionBuilder
          value={value}
          onChange={setValue}
          targetNodeId={edge.source}
          nodes={nodes}
          edges={edges}
          hint="Sem condicao = a conexao sempre e seguida."
        />

        <div className="flex items-center justify-between gap-2 border-t border-gray-200 pt-3 dark:border-gray-800">
          <Button
            type="button"
            variant="ghost"
            onClick={() => {
              if (confirm("Remover esta conexao?")) onDelete()
            }}
          >
            <RiDeleteBinLine className="size-4" aria-hidden />
            Remover conexao
          </Button>
          <div className="flex items-center gap-2">
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancelar
            </Button>
            <Button type="button" onClick={() => onSave(value)}>
              Salvar
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}

function labelOfNode(nodes: Node[], nodeId: string): string {
  const n = nodes.find((nd) => nd.id === nodeId)
  if (!n) return nodeId
  const data = n.data as unknown as StrataNodeData
  return data.label || getEtapaLabel(data.nodeType, data.config ?? {})
}

// Helper export para outros callers.
export { cx as _cx }
