// src/app/(app)/credito/workflows/[id]/editor/_lib/edge-label.ts
//
// Conectores em linguagem de domínio (F5, 2026-06-12).
//
// O usuário via `se: {{node.score.output.value}} >= 700` cru na edge — agora
// vê "se value ≥ 700" (verde). Edge SEM condição saindo de um node que tem
// irmã COM condição vira "senão" (âmbar). Edge comum não ganha rótulo (ruído
// zero no caso normal).
//
// Funções puras — testáveis, sem React.

import type { Edge } from "@xyflow/react"

const OP_PT: Array<[RegExp, string]> = [
  [/>=/g, "≥"],
  [/<=/g, "≤"],
  [/==/g, "="],
  [/!=/g, "≠"],
]

/** "{{node.X.output.Y}} >= 700" → "se Y ≥ 700" (best-effort, fallback cru). */
export function friendlyCondition(condition: string): string {
  let s = condition.trim()
  // Template → só o nome da variável (a origem fica na linhagem/inspector).
  s = s.replace(/\{\{\s*node\.[^.}]+\.output\.([^}\s]+)\s*\}\}/g, "$1")
  s = s.replace(/\{\{\s*trigger\.([^}\s]+)\s*\}\}/g, "$1")
  for (const [re, pt] of OP_PT) s = s.replace(re, pt)
  // Booleans em pt.
  s = s.replace(/\s*=\s*true\b/g, " é sim").replace(/\s*=\s*false\b/g, " é não")
  s = s.replace(/\s+and\s+/gi, " e ").replace(/\s+or\s+/gi, " ou ")
  s = s.replace(/\s+/g, " ").trim()
  const text = `se ${s}`
  return text.length > 46 ? `${text.slice(0, 43)}…` : text
}

type EdgeKind = "cond" | "senao" | "none"

function kindOf(edge: Edge, siblings: Edge[]): EdgeKind {
  const cond = (edge.data as { condition?: string | null } | undefined)?.condition
  if (cond) return "cond"
  const hasCondSibling = siblings.some(
    (s) =>
      s.id !== edge.id &&
      Boolean((s.data as { condition?: string | null } | undefined)?.condition),
  )
  return hasCondSibling ? "senao" : "none"
}

const LABEL_STYLE_COND = { fontSize: 10, fill: "#047857", fontWeight: 600 }
const LABEL_STYLE_SENAO = { fontSize: 10, fill: "#B45309", fontWeight: 600 }

/** Decora TODAS as edges com rótulos de domínio — chamado via useMemo antes
 *  do render do React Flow (ids preservados; estado original intacto). */
export function decorateEdgesWithLabels(edges: Edge[]): Edge[] {
  const bySource = new Map<string, Edge[]>()
  for (const e of edges) {
    bySource.set(e.source, [...(bySource.get(e.source) ?? []), e])
  }
  return edges.map((e) => {
    const siblings = bySource.get(e.source) ?? []
    const kind = kindOf(e, siblings)
    if (kind === "cond") {
      const cond = (e.data as { condition?: string | null }).condition as string
      return {
        ...e,
        label: friendlyCondition(cond),
        labelStyle: LABEL_STYLE_COND,
        labelBgPadding: [5, 2] as [number, number],
        labelBgBorderRadius: 4,
        labelBgStyle: { fill: "#ECFDF5", fillOpacity: 0.95 },
      }
    }
    if (kind === "senao") {
      return {
        ...e,
        label: "senão",
        labelStyle: LABEL_STYLE_SENAO,
        labelBgPadding: [5, 2] as [number, number],
        labelBgBorderRadius: 4,
        labelBgStyle: { fill: "#FFFBEB", fillOpacity: 0.95 },
      }
    }
    return { ...e, label: undefined }
  })
}

/** Sugestão de par sim/não ao conectar a partir de um Branch Condicional:
 *  1ª saída ganha "resultado é sim", 2ª ganha "resultado é não". Retorna a
 *  condição sugerida ou null (usuário sempre pode editar no popover). */
export function suggestBranchCondition(
  sourceNodeId: string,
  existingOutgoing: Edge[],
): string | null {
  const conds = existingOutgoing
    .map((e) => (e.data as { condition?: string | null } | undefined)?.condition)
    .filter(Boolean)
  const base = `{{node.${sourceNodeId}.output.result}}`
  if (existingOutgoing.length === 0) return `${base} == true`
  if (existingOutgoing.length === 1 && conds.length >= 1) {
    // Já existe a perna "sim" — esta é a "não".
    return `${base} == false`
  }
  return null
}
