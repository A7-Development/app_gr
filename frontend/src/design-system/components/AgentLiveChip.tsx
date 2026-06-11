// src/design-system/components/AgentLiveChip.tsx
//
// Chip vivo de agente trabalhando (handoff Proveniência, T2 · Pulso —
// a temperatura RECOMENDADA): pill h22 indigo 8% com dot 6px pulsante
// (halo 3px a 18%, ciclo 1,2s) + copy "Agente ativo · 2/3 fontes".
//
// O dot sozinho (sem pill) é usado na sidebar de estações — exportado
// como <AgentPulseDot>. Animação respeita prefers-reduced-motion
// (keyframe agent-pulse em globals.css).

"use client"

import * as React from "react"

import { agentContainerTokens, provenanceTokens } from "@/design-system/tokens/provenance"
import { cx } from "@/lib/utils"

export function AgentPulseDot({ size = 6, className }: { size?: number; className?: string }) {
  const indigo = provenanceTokens.agente
  return (
    <span
      className={cx("inline-block shrink-0 rounded-full motion-safe:animate-agent-pulse", className)}
      style={{
        width: size,
        height: size,
        background: indigo.color,
        boxShadow: `0 0 0 3px ${agentContainerTokens.pulseHalo}`,
      }}
      aria-hidden
    />
  )
}

export type AgentLiveChipProps = {
  /** Copy do chip (ex.: "Agente ativo · 2/3 fontes"). */
  children: React.ReactNode
  className?: string
}

export function AgentLiveChip({ children, className }: AgentLiveChipProps) {
  const indigo = provenanceTokens.agente
  return (
    <span
      className={cx(
        "inline-flex h-[22px] items-center gap-1.5 rounded-full px-[9px] text-[11px] font-medium leading-none",
        className,
      )}
      style={{ background: indigo.chipBg, color: indigo.chipText }}
    >
      <AgentPulseDot />
      {children}
    </span>
  )
}
