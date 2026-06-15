// Header (titulo) de uma raia de segmento no organograma. Nao-interativo
// (draggable/selectable=false na definicao do node). So rotula a coluna.

"use client"

import * as React from "react"
import type { NodeProps } from "@xyflow/react"

import type { SegHeaderData } from "../_lib/layout"

function SegHeaderImpl({ data }: NodeProps) {
  const d = data as SegHeaderData
  return (
    <div className="pointer-events-none w-[216px] select-none">
      <div
        className="text-[12px] font-semibold uppercase tracking-wide"
        style={{ color: d.color }}
      >
        {d.label}
      </div>
      <div className="mt-0.5 h-0.5 w-full rounded-full" style={{ backgroundColor: d.color }} />
      <div className="mt-1 text-[11px] text-gray-400">{d.count} entidades</div>
    </div>
  )
}

export const SegHeaderNode = React.memo(SegHeaderImpl)
