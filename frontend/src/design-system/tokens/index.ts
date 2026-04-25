// src/design-system/tokens/index.ts
// Canonical design tokens as typed TS object.
// CSS vars in globals.css are the source of truth;
// this file mirrors them for use in TypeScript contexts (ECharts, etc.)

export const tokens = {
  colors: {
    brand: {
      navy:        "#1B2B4B",
      navyDark:    "#050814",
      orange:      "#F05A28",
      orangeLight: "#FF7A4D",
      blue:        "#3B82F6",
      blueHover:   "#2563EB",
    },
    status: {
      "em-dia":       { fg: "#16A34A", bg: "rgba(22,163,74,.10)",   fgDark: "#4ADE80", bgDark: "rgba(74,222,128,.10)" },
      "atrasado-30":  { fg: "#CA8A04", bg: "rgba(202,138,4,.10)",   fgDark: "#FCD34D", bgDark: "rgba(252,211,77,.10)" },
      "atrasado-60":  { fg: "#EA580C", bg: "rgba(234,88,12,.10)",   fgDark: "#FB923C", bgDark: "rgba(251,146,60,.10)" },
      "inadimplente": { fg: "#DC2626", bg: "rgba(220,38,38,.10)",   fgDark: "#F87171", bgDark: "rgba(248,113,113,.10)" },
      "recomprado":   { fg: "#737373", bg: "rgba(115,115,115,.10)", fgDark: "#A3A3A3", bgDark: "rgba(163,163,163,.10)" },
      "liquidado":    { fg: "#0891B2", bg: "rgba(8,145,178,.10)",   fgDark: "#22D3EE", bgDark: "rgba(34,211,238,.10)" },
    } as const,
    chart: ["#64748B", "#0EA5E9", "#14B8A6", "#10B981", "#F59E0B", "#F43F5E", "#8B5CF6", "#6366F1"] as const,
    delta: {
      pos: { light: "#059669", dark: "#34D399" },
      neg: { light: "#DC2626", dark: "#F87171" },
      neu: { light: "#D97706", dark: "#FCD34D" },
    },
  },
  fonts: {
    sans:    "var(--font-sans)",
    mono:    "var(--font-mono)",
    display: "var(--font-display)",
  },
  spacing: {
    sidebarExpanded:  "240px",
    sidebarCollapsed: "56px",
    headerH:          "56px",
    filterBarH:       "48px",
    drawerSm:         "400px",
    drawerMd:         "560px",
    drawerLg:         "720px",
    rowCompact:       "32px",
    rowDefault:       "40px",
    rowComfortable:   "48px",
  },
  radius: {
    sm:   "2px",
    base: "4px",
    md:   "6px",
    lg:   "8px",
    full: "9999px",
  },
  motion: {
    duration: { instant: 0, fast: 100, base: 150, slow: 250, slower: 400 },
    easing: {
      standard:   "cubic-bezier(0.4, 0, 0.2, 1)",
      decelerate: "cubic-bezier(0.16, 1, 0.3, 1)",
      accelerate: "cubic-bezier(0.4, 0, 1, 1)",
    },
  },
} as const

export type StatusKey = keyof typeof tokens.colors.status
export type ChartColor = typeof tokens.colors.chart[number]
