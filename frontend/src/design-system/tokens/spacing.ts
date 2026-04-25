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
  headerH:    56,
  filterBarH: 48,
} as const

export const drawer = {
  sm: 400,
  md: 560,
  lg: 720,
} as const

export const rowHeight = {
  compact:     32,
  default:     40,
  comfortable: 48,
} as const

export type DensityMode = keyof typeof rowHeight

/**
 * Returns Tailwind height class for table row density.
 */
export function rowHeightClass(density: DensityMode): string {
  return {
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
