// Tremor chartUtils [v0.2.0] — paleta A7 Credit (blue → slate migration)
//
// Ordenacao canonica (design system A7 Credit):
//   slate -> sky -> teal -> emerald -> amber -> rose -> violet -> indigo
//
// Racional:
// - primeira serie ancora na cor da marca (slate, azul-acinzentado sobrio)
// - cool-to-warm em escala sinaliza risco de forma natural
// - emerald / rose dobram como ↑ / ↓ para KPIs
//
// Gray fica disponivel mas FORA do iterador default (so por override).
// `blue` fica em `chartColors` por back-compat mas NAO itera no default.

export type ColorUtility = "bg" | "stroke" | "fill" | "text"

export const chartColors = {
  blue: {
    bg: "bg-blue-500",
    stroke: "stroke-blue-500",
    fill: "fill-blue-500",
    text: "text-blue-500",
  },
  sky: {
    bg: "bg-sky-500",
    stroke: "stroke-sky-500",
    fill: "fill-sky-500",
    text: "text-sky-500",
  },
  teal: {
    bg: "bg-teal-500",
    stroke: "stroke-teal-500",
    fill: "fill-teal-500",
    text: "text-teal-500",
  },
  emerald: {
    bg: "bg-emerald-500",
    stroke: "stroke-emerald-500",
    fill: "fill-emerald-500",
    text: "text-emerald-500",
  },
  amber: {
    bg: "bg-amber-500",
    stroke: "stroke-amber-500",
    fill: "fill-amber-500",
    text: "text-amber-500",
  },
  rose: {
    bg: "bg-rose-500",
    stroke: "stroke-rose-500",
    fill: "fill-rose-500",
    text: "text-rose-500",
  },
  violet: {
    bg: "bg-violet-500",
    stroke: "stroke-violet-500",
    fill: "fill-violet-500",
    text: "text-violet-500",
  },
  slate: {
    bg: "bg-slate-500",
    stroke: "stroke-slate-500",
    fill: "fill-slate-500",
    text: "text-slate-500",
  },
  // Acento secundario introduzido na migracao blue→slate para fechar
  // a rotacao de 8 cores (slate promovido a 1a posicao, blue fora).
  indigo: {
    bg: "bg-indigo-500",
    stroke: "stroke-indigo-500",
    fill: "fill-indigo-500",
    text: "text-indigo-500",
  },
  // Neutros — disponibilizados via override (nao iteram no default).
  gray: {
    bg: "bg-gray-500",
    stroke: "stroke-gray-500",
    fill: "fill-gray-500",
    text: "text-gray-500",
  },
  // Legacy (Tremor default) — mantidos para back-compat. Nao iteram no default.
  cyan: {
    bg: "bg-cyan-500",
    stroke: "stroke-cyan-500",
    fill: "fill-cyan-500",
    text: "text-cyan-500",
  },
  pink: {
    bg: "bg-pink-500",
    stroke: "stroke-pink-500",
    fill: "fill-pink-500",
    text: "text-pink-500",
  },
  lime: {
    bg: "bg-lime-500",
    stroke: "stroke-lime-500",
    fill: "fill-lime-500",
    text: "text-lime-500",
  },
  fuchsia: {
    bg: "bg-fuchsia-500",
    stroke: "stroke-fuchsia-500",
    fill: "fill-fuchsia-500",
    text: "text-fuchsia-500",
  },
} as const satisfies {
  [color: string]: {
    [key in ColorUtility]: string
  }
}

export type AvailableChartColorsKeys = keyof typeof chartColors

/**
 * Sequencia A7 Credit (8 cores). `blue`, `gray`, `cyan`, `pink`, `lime`,
 * `fuchsia` ficam FORA da iteracao default (disponiveis em `chartColors`
 * apenas por override). `slate` foi promovido a 1a posicao na migracao
 * do acento blue → slate (v0.2.0).
 */
export const AvailableChartColors: AvailableChartColorsKeys[] = [
  "slate",
  "sky",
  "teal",
  "emerald",
  "amber",
  "rose",
  "violet",
  "indigo",
]

export const constructCategoryColors = (
  categories: string[],
  colors: AvailableChartColorsKeys[],
): Map<string, AvailableChartColorsKeys> => {
  const categoryColors = new Map<string, AvailableChartColorsKeys>()
  categories.forEach((category, index) => {
    categoryColors.set(category, colors[index % colors.length])
  })
  return categoryColors
}

export const getColorClassName = (
  color: AvailableChartColorsKeys,
  type: ColorUtility,
): string => {
  const fallbackColor = {
    bg: "bg-gray-500",
    stroke: "stroke-gray-500",
    fill: "fill-gray-500",
    text: "text-gray-500",
  }
  return chartColors[color]?.[type] ?? fallbackColor[type]
}

// Tremor getYAxisDomain [v0.0.0]

export const getYAxisDomain = (
  autoMinValue: boolean,
  minValue: number | undefined,
  maxValue: number | undefined,
) => {
  const minDomain = autoMinValue ? "auto" : (minValue ?? 0)
  const maxDomain = maxValue ?? "auto"
  return [minDomain, maxDomain]
}

// Tremor hasOnlyOneValueForKey [v0.1.0]

export function hasOnlyOneValueForKey(
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  array: any[],
  keyToCheck: string,
): boolean {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const val: any[] = []

  for (const obj of array) {
    if (Object.prototype.hasOwnProperty.call(obj, keyToCheck)) {
      val.push(obj[keyToCheck])
      if (val.length > 1) {
        return false
      }
    }
  }

  return true
}
