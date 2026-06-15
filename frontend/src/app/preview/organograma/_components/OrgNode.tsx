// Custom React Flow node — entidade do grupo economico no organograma.
//
// Layout top-down (Layout A): handle target em cima, source em baixo.
//   ┌────────────────────────────────┐
//   │ [PJ]  ★                        │  ← chip de natureza + estrela (raiz)
//   │ RAZAO SOCIAL / NOME            │
//   │ 00.000.000/0000-00             │
//   └────────────────────────────────┘
//
// Cor por natureza (PJ azul / PF cinza-esverdeado). Raiz com realce.
// Encerrado = opacidade reduzida + borda tracejada (toggle na pagina).

"use client"

import * as React from "react"
import { Handle, Position, type NodeProps } from "@xyflow/react"
import { RiBuilding2Line, RiUserLine, RiVipCrownLine } from "@remixicon/react"

import { cx } from "@/lib/utils"

export type OrgNodeData = {
  name: string
  doc: string
  kind: "PJ" | "PF"
  active: boolean
  isRoot: boolean
  /** Cor do segmento de atuacao (faixa lateral). */
  segmentColor?: string
}

export const ORG_NODE_W = 216
export const ORG_NODE_H = 72

function OrgNodeImpl({ data }: NodeProps) {
  const d = data as OrgNodeData
  const isPJ = d.kind === "PJ"
  const Icon = isPJ ? RiBuilding2Line : RiUserLine

  return (
    <div
      style={{
        width: ORG_NODE_W,
        minHeight: ORG_NODE_H,
        borderLeft: d.segmentColor ? `4px solid ${d.segmentColor}` : undefined,
      }}
      className={cx(
        "rounded-md border bg-white px-3 py-2 shadow-sm dark:bg-gray-950",
        d.isRoot
          ? "border-blue-500 ring-2 ring-blue-500/30 dark:border-blue-400"
          : isPJ
            ? "border-blue-200 dark:border-blue-900"
            : "border-gray-200 dark:border-gray-800",
        !d.active && "border-dashed opacity-60",
      )}
    >
      <Handle
        type="target"
        position={Position.Top}
        className="!h-1.5 !w-1.5 !border-0 !bg-gray-300 dark:!bg-gray-700"
      />

      <div className="mb-1 flex items-center gap-1.5">
        <span
          className={cx(
            "inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
            isPJ
              ? "bg-blue-50 text-blue-700 dark:bg-blue-950 dark:text-blue-300"
              : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
          )}
        >
          <Icon className="size-3" aria-hidden />
          {d.kind}
        </span>
        {d.isRoot && (
          <RiVipCrownLine className="size-3.5 text-blue-500" aria-hidden />
        )}
        {!d.active && (
          <span className="ml-auto text-[10px] font-medium text-gray-400">encerrado</span>
        )}
      </div>

      <div
        className="truncate text-[13px] font-medium leading-tight text-gray-900 dark:text-gray-100"
        title={d.name}
      >
        {d.name}
      </div>
      <div className="mt-0.5 font-mono text-[11px] tabular-nums text-gray-500 dark:text-gray-400">
        {d.doc}
      </div>

      <Handle
        type="source"
        position={Position.Bottom}
        className="!h-1.5 !w-1.5 !border-0 !bg-gray-300 dark:!bg-gray-700"
      />
    </div>
  )
}

export const OrgNode = React.memo(OrgNodeImpl)
