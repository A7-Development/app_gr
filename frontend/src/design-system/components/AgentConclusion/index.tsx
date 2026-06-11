// src/design-system/components/AgentConclusion/index.tsx
//
// Container canônico de conclusão de agente IA (handoff Conceito D).
// Conclusões NÃO homologadas vivem em borda 1.5px dashed lavanda
// (#C7D2FE) + fundo indigo a 35% — a assinatura visual de "julgamento
// provisório". Ao homologar, o conteúdo "assenta" (borda some — o caller
// troca o container, fade 150ms).
//
// Anatomia: header (eyebrow indigo + meta à direita) · divisor #E0E7FF ·
// corpo (children) · rodapé opcional (nota) · barra de ações opcional.

"use client"

import * as React from "react"
import { RiSparkling2Line } from "@remixicon/react"

import { agentContainerTokens, provenanceTokens } from "@/design-system/tokens/provenance"
import { cx } from "@/lib/utils"

export type AgentConclusionProps = {
  /** Eyebrow indigo uppercase (ex.: "LEITURA DO AGENTE DE FATURAMENTO"). */
  eyebrow: string
  /** Meta à direita do header (ex.: "v1.8 · gerada após a extração"). */
  meta?: string
  /** Tag curta à direita (ex.: "julgamento · editável"). */
  tag?: string
  children: React.ReactNode
  /** Nota de rodapé (ex.: "1 trecho ajustado por você — original na trilha."). */
  footnote?: React.ReactNode
  /** Barra de ações (botões — 1 primária, 1 secundária, resto em ···). */
  actions?: React.ReactNode
  className?: string
}

export function AgentConclusion({
  eyebrow,
  meta,
  tag,
  children,
  footnote,
  actions,
  className,
}: AgentConclusionProps) {
  const indigo = provenanceTokens.agente
  return (
    <section
      className={cx("rounded", className)}
      style={{ border: agentContainerTokens.border, background: agentContainerTokens.bg }}
    >
      <header
        className="flex flex-wrap items-center gap-x-3 gap-y-1 px-5 py-3"
        style={{ borderBottom: `1px solid ${agentContainerTokens.divider}` }}
      >
        <span
          className="inline-flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-[0.06em]"
          style={{ color: indigo.chipText }}
        >
          <RiSparkling2Line className="size-3.5" aria-hidden />
          {eyebrow}
        </span>
        {meta && (
          <span className="text-[11.5px] text-gray-400 dark:text-gray-500">{meta}</span>
        )}
        {tag && (
          <span className="ml-auto text-[10px] text-gray-400 dark:text-gray-500">{tag}</span>
        )}
      </header>

      <div className="px-5 py-4 text-[13.5px] leading-[1.8] text-gray-700 dark:text-gray-300">
        {children}
      </div>

      {footnote && (
        <div
          className="mx-5 flex items-start gap-1.5 pb-3 pt-2.5 text-[11.5px] text-gray-500 dark:text-gray-400"
          style={{ borderTop: `1px solid ${agentContainerTokens.divider}` }}
        >
          {footnote}
        </div>
      )}

      {actions && (
        <div className="flex flex-wrap items-center gap-2 px-5 pb-4">{actions}</div>
      )}
    </section>
  )
}
