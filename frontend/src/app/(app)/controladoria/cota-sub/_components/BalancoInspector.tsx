"use client"

/**
 * BalancoInspector -- detalhamento de categoria do balanco no slot direito
 * da grid `xl:grid-cols-2` da pagina Cota Sub (F3 do redesign, 2026-05-24).
 *
 * Substitui o `CategoriaDrillSheet` (drawer overlay) em telas >= xl. Em
 * telas menores, o page.tsx continua caindo no Sheet (preserva UX em
 * laptops apertados).
 *
 * Diferenca de UX vs Sheet:
 *   - Permanente (parte da grid), nao overlay
 *   - Trocar categoria selecionada atualiza o conteudo IMEDIATAMENTE,
 *     sem fechar/reabrir
 *   - Coexiste com AIPanel (que continua sendo overlay temporario)
 *   - Empty state quando nada selecionado: convida o usuario a clicar
 *
 * Anatomia (alinhada com CategoriaDrillSheet pra familiaridade visual):
 *   Header   -- breadcrumb + close + tipo badge
 *   Hero     -- titulo + valor D0 + delta
 *   Body     -- {children} (DrillDcContent / DrillPddContent / DrillCprContent)
 *   Footer   -- fundo + datas + fonte
 */

import * as React from "react"
import { RiArchive2Line, RiCloseLine, RiInformationLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import { EmptyState } from "@/design-system/components/EmptyState"
import type { CategoriaPatrimonial } from "@/lib/api-client"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style:                 "currency",
  currency:              "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const fmtBRLSigned = (v: number): string => {
  if (Math.abs(v) < 0.005) return "0,00"
  const sign = v > 0 ? "+" : "−"
  return `${sign}${fmtBRL.format(Math.abs(v))}`
}

const fmtDate = (iso: string): string => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[3]}/${m[2]}` : iso
}

export type BalancoInspectorProps = {
  categoria?:     CategoriaPatrimonial
  fundoNome:      string
  data:           string
  dataAnterior:   string
  onClose:        () => void
  children?:      React.ReactNode
}

export function BalancoInspector({
  categoria,
  fundoNome,
  data,
  dataAnterior,
  onClose,
  children,
}: BalancoInspectorProps) {
  if (!categoria) {
    return (
      <Card className="flex h-full min-h-[480px] flex-col items-center justify-center p-6">
        <EmptyState
          icon={RiInformationLine}
          title="Selecione uma linha do balanço"
          description="Clique em Direitos Creditórios, PDD, Contas a Receber ou Contas a Pagar para abrir a explicação da variação D-1 → D0 aqui."
        />
      </Card>
    )
  }

  const isAtivo = categoria.tipo === "ativo"
  const isZero = Math.abs(categoria.delta) < 0.005
  // PDD e contra-ativo (redutor): subir piora o PL Sub -> positivo=vermelho.
  const bom = categoria.contra ? categoria.delta < 0 : categoria.delta > 0

  return (
    <Card className="flex h-full flex-col p-0">
      {/* Header */}
      <div className="flex items-center justify-between gap-2 border-b border-gray-100 px-3 py-2 dark:border-gray-900">
        <div className="flex items-center gap-2 min-w-0">
          <span className="truncate text-[11px] uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600">
            Cota Sub · {categoria.label}
          </span>
          <TipoBadge tipo={categoria.tipo} />
        </div>
        <button
          type="button"
          onClick={onClose}
          className={cx(
            "rounded p-1 text-gray-400 transition-colors",
            "hover:bg-gray-100 hover:text-gray-700",
            "dark:hover:bg-gray-800 dark:hover:text-gray-200",
          )}
          aria-label="Fechar detalhamento"
        >
          <RiCloseLine className="size-4" aria-hidden="true" />
        </button>
      </div>

      {/* Hero */}
      <div className="flex items-end justify-between gap-3 px-3 py-2.5">
        <div className="flex flex-col min-w-0">
          <h3 className="truncate text-[13px] font-semibold text-gray-900 dark:text-gray-50">
            {categoria.label}
          </h3>
          <span className="text-[11px] text-gray-500 dark:text-gray-400">
            {isAtivo ? "Ativo" : "Passivo · redutor"} · D0 {fmtDate(data)}
          </span>
        </div>
        <div className="flex flex-col items-end">
          <span className="text-[18px] font-semibold tabular-nums text-gray-900 dark:text-gray-50">
            {fmtBRL.format(categoria.d0)}
          </span>
          <span
            className={cx(
              "text-[11px] tabular-nums",
              isZero
                ? "text-gray-400 dark:text-gray-600"
                : bom
                  ? "text-emerald-700 dark:text-emerald-400"
                  : "text-red-700 dark:text-red-400",
            )}
          >
            {fmtBRLSigned(categoria.delta)} vs {fmtDate(dataAnterior)}
          </span>
        </div>
      </div>

      {/* Body */}
      <div className="flex-1 overflow-y-auto border-t border-gray-100 px-3 py-3 dark:border-gray-900">
        {children}
      </div>

      {/* Footer */}
      <div className="flex flex-wrap items-center gap-1.5 border-t border-gray-100 px-3 py-1.5 text-[11px] text-gray-500 dark:border-gray-900 dark:text-gray-400">
        <RiArchive2Line className="size-3.5" aria-hidden="true" />
        <span>
          {fundoNome} · D-1 {fmtDate(dataAnterior)} → D0 {fmtDate(data)}
        </span>
        <span aria-hidden="true">·</span>
        <span className="font-mono text-[10px] text-gray-400 dark:text-gray-600">
          {categoria.source}
        </span>
      </div>
    </Card>
  )
}

function TipoBadge({ tipo }: { tipo: "ativo" | "passivo" }) {
  const isAtivo = tipo === "ativo"
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-sm px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.04em]",
        isAtivo
          ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
          : "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
      )}
    >
      {isAtivo ? "Ativo" : "Passivo"}
    </span>
  )
}
