// src/design-system/tokens/spacing.ts
// Layout + spacing constants as typed values.
// All CSS variables are defined in globals.css.
// This file provides TypeScript access to the same values.

export const sidebar = {
  widthExpanded:  "240px",
  widthCollapsed: "56px",
  cookieName: "sidebar:state",
} as const

export const layout = {
  headerH:    48,
  filterBarH: 48,
} as const

export const drawer = {
  sm: 400,
  md: 560,
  lg: 720,
} as const

// Escala unica de densidade da familia de tabelas (handoff v2 — Tabela canonica).
// Valores em px de altura de linha: 24 / 28 / 32 / 40 / 48.
// O default NATURAL da familia e 32px (key `compact`) — aplicado pelo default
// do <DataTable> / <DataTableShell> / <DenseTable>. O rename do enum para o
// vocabulario do handoff (Ultracompact/Compact/Default/Comfortable/Relaxed)
// fica para a varredura final do Modo Iteracao de Design.
export const rowHeight = {
  ultracompact: 24,
  ultra:       28,
  compact:     32,
  default:     40,
  comfortable: 48,
} as const

export type DensityMode = keyof typeof rowHeight

/**
 * Returns Tailwind height class for table row density.
 * `ultracompact` (h-6/24px) e o degrau mais denso — para grades de altissima
 * densidade (handoff v2). `ultra` (h-7/28px) e um ponto abaixo de `compact`.
 * Todos densificam a linha SEM reduzir a fonte (cell continua 12px via
 * tableTokens). Uteis em tabelas que precisam caber em colunas estreitas.
 */
export function rowHeightClass(density: DensityMode): string {
  return {
    ultracompact: "h-6",
    ultra:       "h-7",
    compact:     "h-8",
    default:     "h-10",
    comfortable: "h-12",
  }[density]
}

export const radius = {
  sm:   "2px",
  base: "4px",
  md:   "6px",
  lg:   "8px",
  full: "9999px",
} as const
