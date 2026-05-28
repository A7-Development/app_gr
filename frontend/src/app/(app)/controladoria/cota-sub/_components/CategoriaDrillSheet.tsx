"use client"

/**
 * CategoriaDrillSheet — carcaca compartilhada dos drills da F2 (DC, PDD, CPR).
 *
 * Envolve o DrillDownSheet canonico com:
 *   - Header: breadcrumb "Cota Sub · {label}" + close button + status pill
 *             (ativo/passivo)
 *   - Hero: titulo da categoria + valor D0 + delta absoluto em R$
 *   - Body: slot {children} pro conteudo especifico (DrillDcContent /
 *           DrillPddContent / DrillCprContent)
 *   - Footer: data + fundo + label "fonte" (proveniencia leve)
 *
 * Recebe `categoria` (linha do BalancoPatrimonialResponse) + `fundoNome` +
 * `data` + `dataAnterior` como contexto. Os conteudos internos sao
 * responsaveis por chamar seus proprios hooks com fundoId/data.
 */

import * as React from "react"
import { RiArchive2Line } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"
import type { CategoriaPatrimonial } from "@/lib/api-client"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style:                 "currency",
  currency:              "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const fmtDate = (iso: string): string => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[3]}/${m[2]}` : iso
}

export type CategoriaDrillSheetProps = {
  open:           boolean
  onClose:        () => void
  categoria?:     CategoriaPatrimonial
  fundoNome:      string
  data:           string
  dataAnterior:   string
  children?:      React.ReactNode
}

export function CategoriaDrillSheet({
  open,
  onClose,
  categoria,
  fundoNome,
  data,
  dataAnterior,
  children,
}: CategoriaDrillSheetProps) {
  return (
    <DrillDownSheet
      open={open}
      onClose={onClose}
      size="2xl"
      title={categoria?.label ?? "Detalhe"}
    >
      {categoria && (
        <>
          <DrillDownSheet.Header
            breadcrumb={["Cota Sub", categoria.label]}
            statusSlot={<TipoBadge tipo={categoria.tipo} />}
          />
          <DrillDownSheet.Hero
            title={categoria.label}
            value={categoria.d0}
            delta={{
              value:          categoria.delta,
              label:          `vs ${fmtDate(dataAnterior)} (${fmtBRL.format(categoria.d1)})`,
              format:         "currency",
              labelTone:      "muted",
              positiveIsGood: !categoria.contra,
            }}
          />
          <DrillDownSheet.Body>
            {children}
          </DrillDownSheet.Body>
          <DrillDownSheet.Footer>
            <div className="flex items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400">
              <RiArchive2Line className="size-3.5" aria-hidden="true" />
              <span>
                {fundoNome} · D-1 {fmtDate(dataAnterior)} → D0 {fmtDate(data)}
              </span>
              <span aria-hidden="true">·</span>
              <span className="font-mono">{categoria.source}</span>
            </div>
          </DrillDownSheet.Footer>
        </>
      )}
    </DrillDownSheet>
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
