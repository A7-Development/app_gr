// src/design-system/components/TablePagination.tsx
//
// TablePagination — pager canonico da familia de tabelas (handoff "Tabela
// canonica v2", DataTableShell v2.dc.html, rodape do card).
//
// LOCAL CANONICO: linha propria no RODAPE do Card, FORA da <table> (nunca
// dentro de <tfoot> — la so entra <tr> de totais/reconciliacao). Esquerda =
// contexto ("1–50 de 93.081 · atualizando…" ou proveniencia); direita =
// chevron 26x26 + chips de pagina (26px, ativa azul, reticencias) + chevron.
//
// Use com paginacao SERVER-SIDE (curadoria, historicos). Listagem client-side
// pequena nao pagina (DataTableShell) e lista grande client-side virtualiza.

"use client"

import * as React from "react"
import { RiArrowLeftSLine, RiArrowRightSLine } from "@remixicon/react"

import { cx, focusRing } from "@/lib/utils"

export type TablePaginationProps = {
  /** Pagina corrente (1-based). */
  page: number
  totalPages: number
  onPageChange: (page: number) => void
  /** Desabilita navegacao (ex.: durante fetch). */
  disabled?: boolean
  /** Slot esquerdo — range/contexto ("1–50 de 93.081 · atualizando…"). */
  info?: React.ReactNode
  className?: string
}

/** Janela de paginas com reticencias: 1 … c-1 c c+1 … N (spec dc.html). */
function pageWindow(page: number, total: number): (number | "…")[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1)
  const pages = new Set<number>([1, 2, page - 1, page, page + 1, total])
  const sorted = Array.from(pages)
    .filter((p) => p >= 1 && p <= total)
    .sort((a, b) => a - b)
  const out: (number | "…")[] = []
  let prev = 0
  for (const p of sorted) {
    if (p - prev > 1) out.push("…")
    out.push(p)
    prev = p
  }
  return out
}

const CHIP =
  "inline-flex h-[26px] min-w-[26px] items-center justify-center rounded px-1.5 text-xs tabular-nums transition-colors duration-100"

export function TablePagination({
  page,
  totalPages,
  onPageChange,
  disabled = false,
  info,
  className,
}: TablePaginationProps) {
  const go = (p: number) => onPageChange(Math.min(Math.max(1, p), totalPages))

  return (
    <div
      className={cx(
        "flex flex-wrap items-center justify-between gap-3 border-t border-t-gray-100 px-4 py-2 dark:border-t-gray-900",
        className,
      )}
    >
      <span className="text-[11px] tabular-nums text-gray-500 dark:text-gray-400">
        {info}
      </span>

      <nav className="flex items-center gap-1" aria-label="Paginação">
        <button
          type="button"
          aria-label="Página anterior"
          disabled={disabled || page <= 1}
          onClick={() => go(page - 1)}
          className={cx(
            CHIP,
            "text-gray-500 hover:bg-gray-100 disabled:pointer-events-none disabled:text-gray-300",
            "dark:text-gray-400 dark:hover:bg-gray-800 dark:disabled:text-gray-700",
            focusRing,
          )}
        >
          <RiArrowLeftSLine className="size-4" aria-hidden />
        </button>

        {pageWindow(page, totalPages).map((p, i) =>
          p === "…" ? (
            <span key={`e${i}`} className="px-0.5 text-xs text-gray-300 dark:text-gray-700" aria-hidden>
              …
            </span>
          ) : (
            <button
              key={p}
              type="button"
              aria-label={`Página ${p}`}
              aria-current={p === page ? "page" : undefined}
              disabled={disabled}
              onClick={() => go(p)}
              className={cx(
                CHIP,
                p === page
                  ? "bg-blue-50 font-semibold text-blue-600 dark:bg-blue-500/10 dark:text-blue-400"
                  : "text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800",
                disabled && "pointer-events-none",
                focusRing,
              )}
            >
              {p.toLocaleString("pt-BR")}
            </button>
          ),
        )}

        <button
          type="button"
          aria-label="Próxima página"
          disabled={disabled || page >= totalPages}
          onClick={() => go(page + 1)}
          className={cx(
            CHIP,
            "text-gray-500 hover:bg-gray-100 disabled:pointer-events-none disabled:text-gray-300",
            "dark:text-gray-400 dark:hover:bg-gray-800 dark:disabled:text-gray-700",
            focusRing,
          )}
        >
          <RiArrowRightSLine className="size-4" aria-hidden />
        </button>
      </nav>
    </div>
  )
}
