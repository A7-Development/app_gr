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

export const rowHeight = {
  ultra:       28,
  compact:     32,
  default:     40,
  comfortable: 48,
} as const

export type DensityMode = keyof typeof rowHeight

/**
 * Returns Tailwind height class for table row density.
 * `ultra` (h-7/28px) é um ponto abaixo de `compact` — densifica a linha SEM
 * reduzir a fonte (cell continua 12px via tableTokens). Útil em tabelas que
 * precisam caber em colunas estreitas (ex.: balanço em 40% da largura).
 */
export function rowHeightClass(density: DensityMode): string {
  return {
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
