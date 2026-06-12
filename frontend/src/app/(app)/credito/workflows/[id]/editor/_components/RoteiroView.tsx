// src/app/(app)/credito/workflows/[id]/editor/_components/RoteiroView.tsx
//
// Modo Roteiro (F6, 2026-06-12) — overlay read-only que cobre o canvas: o
// fluxo como narrativa numerada em português. Pra quem pensa em checklist,
// não em grafo. Clicar num passo volta pro canvas com o node selecionado.

"use client"

import * as React from "react"
import { RiFlowChart, RiGitMergeLine } from "@remixicon/react"
import type { Edge, Node } from "@xyflow/react"

import type { AgentMeta } from "@/lib/credito-client"
import { cx } from "@/lib/utils"

import { primitiveTypeFor } from "../_lib/etapas"
import { buildRoteiro } from "../_lib/roteiro"

export function RoteiroView({
  nodes,
  edges,
  agentCatalog,
  onGoToNode,
}: {
  nodes: Node[]
  edges: Edge[]
  agentCatalog: AgentMeta[]
  /** Clique num passo: volta pro canvas com o node selecionado. */
  onGoToNode: (nodeId: string) => void
}) {
  const grupos = React.useMemo(
    () => buildRoteiro(nodes, edges, agentCatalog),
    [nodes, edges, agentCatalog],
  )

  return (
    <div className="absolute inset-0 z-20 overflow-y-auto bg-white dark:bg-gray-950">
      <div className="mx-auto max-w-2xl px-6 py-6">
        <div className="mb-4 flex items-center gap-2">
          <RiFlowChart className="size-4 text-gray-400" aria-hidden />
          <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            Roteiro do playbook
          </h2>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            o fluxo em palavras — clique num passo pra editá-lo no canvas
          </span>
        </div>

        {grupos.length === 0 && (
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Fluxo vazio — volte ao canvas e arraste etapas da paleta.
          </p>
        )}

        <ol className="space-y-4">
          {grupos.map((g) => (
            <li key={g.numero} className="flex gap-3">
              <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-gray-900 text-[11px] font-bold text-white dark:bg-gray-100 dark:text-gray-900">
                {g.numero}
              </span>
              <div className="min-w-0 flex-1 space-y-2">
                {g.paralelo && (
                  <p className="flex items-center gap-1.5 text-[11px] font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500">
                    <RiGitMergeLine className="size-3.5" aria-hidden />
                    ao mesmo tempo
                  </p>
                )}
                {g.itens.map((item) => {
                  const prim = primitiveTypeFor(item.nodeType)
                  return (
                    <button
                      key={item.nodeId}
                      type="button"
                      onClick={() => onGoToNode(item.nodeId)}
                      className={cx(
                        "block w-full rounded-md border border-gray-200 p-3 text-left transition-colors hover:border-blue-400 dark:border-gray-800 dark:hover:border-blue-500/60",
                        g.paralelo && "ml-1",
                      )}
                    >
                      <span className="flex items-center gap-2">
                        <span
                          className={cx("size-2 shrink-0 rounded-full", prim.bar)}
                          aria-hidden
                        />
                        <span className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                          {item.titulo}
                        </span>
                        <span className="text-[11px] text-gray-400 dark:text-gray-500">
                          {item.tipoLabel}
                        </span>
                      </span>
                      {item.condicoesEntrada.map((c, i) => (
                        <span
                          key={i}
                          className="mt-1 block text-xs font-medium text-emerald-700 dark:text-emerald-400"
                        >
                          ↳ só acontece {c}
                        </span>
                      ))}
                      <span className="mt-1 block text-xs leading-relaxed text-gray-600 dark:text-gray-400">
                        {item.faz}
                      </span>
                    </button>
                  )
                })}
              </div>
            </li>
          ))}
        </ol>

        <p className="mt-6 text-[11px] italic text-gray-400 dark:text-gray-500">
          Gerado automaticamente do fluxo — sempre em dia. A ordem segue a execução
          do motor; passos &quot;ao mesmo tempo&quot; aparecem na esteira do analista
          como estações em sequência.
        </p>
      </div>
    </div>
  )
}
