// src/design-system/tokens/provenance.ts
//
// Linguagem de proveniência da esteira de crédito (handoff Conceito D,
// 2026-06-10). QUATRO assinaturas canônicas — codificação sempre dupla
// (ícone + cor + forma de linha), nunca cor sozinha (colorblind-safe).
//
// Cores deliberadamente FORA da dupla azul (ação) / laranja (filtro):
//   fonte externa  → cyan      (ri-bank-line,        linha contínua)
//   agente IA      → indigo    (ri-sparkling-2-line, pontilhada → contínua ao homologar)
//   documento      → verde     (ri-file-text-line,   tracejada)
//   analista       → grafite   (ri-quill-pen-line,   dupla)
//
// Ícones moram em design-system/components/Provenance (tokens não importam
// libs externas — CLAUDE.md §3).

import type * as React from "react"

export type ProvenanceOrigin = "fonte" | "agente" | "documento" | "analista"

export type ProvenanceOriginToken = {
  /** Cor base da assinatura (glifos, sublinhas, sups, dots). */
  color: string
  /** Cor de texto dentro de chips/pills (1 stop mais escuro). */
  chipText: string
  /** Fundo de chip (8%). */
  chipBg: string
  /** Fundo de tile 32×32 (10%). */
  tileBg: string
  /** Forma de linha da assinatura (border-bottom do valor). */
  line: "continua" | "pontilhada" | "tracejada" | "dupla"
  /** Prefixo do código de lastro sobrescrito (F1, IA1, D1, A1). */
  supPrefix: string
  /** Nome humano da origem (pt-BR, sentence case). */
  label: string
}

export const provenanceTokens: Record<ProvenanceOrigin, ProvenanceOriginToken> = {
  fonte: {
    color: "#0891B2",
    chipText: "#0E7490",
    chipBg: "rgba(8,145,178,0.08)",
    tileBg: "rgba(8,145,178,0.10)",
    line: "continua",
    supPrefix: "F",
    label: "Fonte externa",
  },
  agente: {
    color: "#6366F1",
    chipText: "#4F46E5",
    chipBg: "rgba(99,102,241,0.08)",
    tileBg: "rgba(99,102,241,0.10)",
    line: "pontilhada",
    supPrefix: "IA",
    label: "Agente IA",
  },
  documento: {
    color: "#059669",
    chipText: "#047857",
    chipBg: "rgba(5,150,105,0.08)",
    tileBg: "rgba(5,150,105,0.10)",
    line: "tracejada",
    supPrefix: "D",
    label: "Documento",
  },
  analista: {
    color: "#1F2937",
    chipText: "#374151",
    chipBg: "#F3F4F6",
    tileBg: "#F3F4F6",
    line: "dupla",
    supPrefix: "A",
    label: "Analista",
  },
} as const

/** Container de conclusão de agente NÃO homologada (indigo dashed). */
export const agentContainerTokens = {
  border: "1.5px dashed #C7D2FE",
  bg: "rgba(238,242,255,0.35)",
  divider: "#E0E7FF",
  /** Glow do dot pulsante de agente ativo. */
  pulseHalo: "rgba(99,102,241,0.18)",
} as const

/** CSS de border-bottom por forma de linha (assinatura E3 — sublinha). */
export function provenanceUnderline(origin: ProvenanceOrigin, homologado = true): React.CSSProperties {
  const t = provenanceTokens[origin]
  if (origin === "analista" || t.line === "dupla") {
    // Linha dupla grafite — border dupla via border-bottom double.
    return { borderBottom: `3px double ${t.color}`, paddingBottom: 1 }
  }
  if (origin === "agente" && !homologado) {
    return { borderBottom: `2px dotted ${t.color}`, paddingBottom: 1 }
  }
  const style =
    t.line === "tracejada" ? "dashed" : t.line === "pontilhada" && !homologado ? "dotted" : "solid"
  return { borderBottom: `2px ${style} ${t.color}`, paddingBottom: 1 }
}
