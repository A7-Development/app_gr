// src/design-system/tokens/node-category.ts
//
// Vocabulario canonico para identidade VISUAL das categorias de no do
// workflow editor (`@/lib/credito-client::NodeTypeMeta.category`).
//
// Por que isso e um TOKEN e nao chute:
//   Originalmente eu (Claude) chutei classes Tailwind diretas
//   (`bg-emerald-500`, `bg-amber-500`...) em `credito-client.ts` para colorir
//   a palette e os custom nodes do editor. Isso e violacao da CLAUDE.md §4
//   (cores de chart series fora de chart context). Promovendo a token aqui:
//
//   1. Caller fala `nodeCategoryTokens.color(category)` — nao chuta classe
//   2. Token tem responsabilidade unica e auditavel
//   3. Quando o "modo iteracao de design ativo" (CLAUDE.md banner) terminar,
//      este arquivo vira ponto unico de revisao das cores
//
// Decisao 2026-05-01: cores escolhidas para diferenciar visualmente as 6
// categorias no canvas/palette. NAO sao cores semanticas (nao significam
// "sucesso", "erro" — sao identidade de tipo de no). Mesmo padrao do
// MODULE_AVATAR_COLORS (CLAUDE.md §11.6).

import type { NodeTypeMeta } from "@/lib/credito-client"

type Category = NodeTypeMeta["category"]

/** Cor de fundo do tile (usado em palette + custom node header). */
const CATEGORY_BG: Record<Category, string> = {
  triggers: "bg-emerald-500",
  humano: "bg-blue-500",
  coleta: "bg-amber-500",
  agentes: "bg-violet-500",
  logica: "bg-indigo-500",
  integracao: "bg-rose-500",
  output: "bg-gray-700",
}

/** Cor de borda hover (sutil, indicando interatividade). */
const CATEGORY_BORDER_HOVER: Record<Category, string> = {
  triggers: "hover:border-emerald-500",
  humano: "hover:border-blue-500",
  coleta: "hover:border-amber-500",
  agentes: "hover:border-violet-500",
  logica: "hover:border-indigo-500",
  integracao: "hover:border-rose-500",
  output: "hover:border-gray-700",
}

export const nodeCategoryTokens = {
  /** Classe `bg-X-N` do tile colorido por categoria. */
  color: (category: Category): string => CATEGORY_BG[category] ?? "bg-gray-500",
  /** Classe `hover:border-X-N` para feedback hover. */
  borderHover: (category: Category): string =>
    CATEGORY_BORDER_HOVER[category] ?? "hover:border-gray-500",
} as const

/** Backwards-compat: re-export do mapping antigo. Prefira `nodeCategoryTokens.color()`. */
export const NODE_CATEGORY_COLOR = CATEGORY_BG
