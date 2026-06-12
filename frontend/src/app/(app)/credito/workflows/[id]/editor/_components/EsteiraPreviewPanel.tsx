// src/app/(app)/credito/workflows/[id]/editor/_components/EsteiraPreviewPanel.tsx
//
// Painel "Prévia da esteira" (F4, 2026-06-12) — overlay à direita do canvas
// mostrando como o GRAFO vira as ESTAÇÕES que o analista percorre no modo
// foco: ordem, fusões (agente+check na estação da fonte), gates, ramos
// paralelos ("paralelo no motor, sequencial na esteira") e warnings de node
// que vai virar estação solta.

"use client"

import * as React from "react"
import { RiAlertLine, RiCloseLine, RiGitMergeLine, RiShieldCheckLine } from "@remixicon/react"
import type { Edge, Node } from "@xyflow/react"

import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

import { deriveEsteiraPreview } from "../_lib/esteira-preview"
import { ETAPA_LABEL } from "../_lib/glossary"

export function EsteiraPreviewPanel({
  nodes,
  edges,
  onClose,
  onFocusNode,
}: {
  nodes: Node[]
  edges: Edge[]
  onClose: () => void
  onFocusNode?: (nodeId: string) => void
}) {
  const preview = React.useMemo(
    () => deriveEsteiraPreview(nodes, edges),
    [nodes, edges],
  )

  return (
    <aside className="absolute right-3 top-3 z-20 flex max-h-[calc(100%-24px)] w-[340px] flex-col overflow-hidden rounded-md border border-gray-200 bg-white shadow-lg dark:border-gray-800 dark:bg-gray-950">
      <header className="flex items-center gap-2 border-b border-gray-100 px-4 py-2.5 dark:border-gray-900">
        <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-gray-600 dark:text-gray-300">
          Prévia da esteira
        </span>
        <span className={tableTokens.cellSecondary}>o que o analista vê</span>
        <button
          type="button"
          onClick={onClose}
          className="ml-auto rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-900"
          aria-label="Fechar prévia"
        >
          <RiCloseLine className="size-4" aria-hidden />
        </button>
      </header>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3">
        <p className="text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
          A esteira é <strong className="font-medium">sequencial</strong>: o analista
          fecha uma estação por vez, nesta ordem. Ramos paralelos do fluxo executam
          juntos no motor, mas aparecem como estações separadas.
        </p>

        {preview.estacoes.length === 0 && (
          <p className={tableTokens.cellSecondary}>
            Nenhuma estação ainda — arraste etapas de coleta/análise pro canvas.
          </p>
        )}

        <ol className="space-y-2">
          {preview.estacoes.map((est, i) => (
            <li
              key={`${est.label}-${i}`}
              className="rounded-md border border-gray-200 p-2.5 dark:border-gray-800"
            >
              <div className="flex items-center gap-2">
                <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-gray-900 text-[10px] font-bold text-white dark:bg-gray-100 dark:text-gray-900">
                  {i + 1}
                </span>
                <span className="text-xs font-semibold text-gray-900 dark:text-gray-100">
                  {est.label}
                </span>
                {est.temGate && (
                  <span
                    className="ml-auto inline-flex items-center gap-1 text-[10px] font-medium text-blue-600 dark:text-blue-400"
                    title="Tem checkpoint do analista (gate)"
                  >
                    <RiShieldCheckLine className="size-3" aria-hidden />
                    gate
                  </span>
                )}
              </div>
              <ul className="mt-1.5 space-y-0.5 pl-7">
                {est.members.map((m) => (
                  <li key={m.id}>
                    <button
                      type="button"
                      onClick={() => onFocusNode?.(m.id)}
                      className="text-left text-[11px] text-gray-600 hover:text-blue-600 dark:text-gray-400 dark:hover:text-blue-400"
                      title="Selecionar no canvas"
                    >
                      {m.label}
                      <span className="ml-1 text-gray-400 dark:text-gray-600">
                        · {ETAPA_LABEL[m.nodeType] ?? m.nodeType}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
              {est.paralelaCom.length > 0 && (
                <p className="mt-1.5 flex items-start gap-1 pl-7 text-[10px] text-gray-400 dark:text-gray-500">
                  <RiGitMergeLine className="mt-px size-3 shrink-0" aria-hidden />
                  executa em paralelo com {est.paralelaCom.join(", ")} — na esteira,
                  uma estação por vez
                </p>
              )}
            </li>
          ))}
        </ol>

        {preview.warnings.length > 0 && (
          <div className="space-y-1.5">
            {preview.warnings.map((w, i) => (
              <button
                key={i}
                type="button"
                onClick={() => onFocusNode?.(w.nodeId)}
                className="flex w-full items-start gap-2 rounded-md border border-amber-200 bg-amber-50/70 px-2.5 py-2 text-left dark:border-amber-500/30 dark:bg-amber-500/10"
              >
                <RiAlertLine
                  className="mt-0.5 size-3.5 shrink-0 text-amber-600 dark:text-amber-400"
                  aria-hidden
                />
                <span className="text-[11px] leading-snug text-amber-900 dark:text-amber-200">
                  <strong className="font-semibold">{w.label}:</strong> {w.motivo}
                </span>
              </button>
            ))}
          </div>
        )}

        {preview.trilha.length > 0 && (
          <div>
            <p className={cx(tableTokens.header, "mb-1")}>
              Bastidor (não vira estação — só trilha)
            </p>
            <p className={tableTokens.cellSecondary}>
              {preview.trilha.map((t) => t.label).join(" · ")}
            </p>
          </div>
        )}
      </div>
    </aside>
  )
}
