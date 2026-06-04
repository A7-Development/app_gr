// src/lib/fonts.ts
//
// Fonte global do projeto: Inter (next/font/google).
//
// next/font baixa a Inter no BUILD e a auto-hospeda no output (preload no
// <head>) — em runtime nao ha dependencia do Google. Centralizado aqui para
// que tanto o root layout (className/variable) quanto o tema ECharts
// (canvas, que NAO herda CSS) usem exatamente a mesma familia resolvida.
//
// Ver CLAUDE.md §2 (Inter e a fonte mandatoria do projeto).

import { Inter } from "next/font/google"

export const inter = Inter({
  subsets: ["latin"],
  display: "swap",
  variable: "--font-sans",
})

/**
 * Nome de familia resolvido pelo next/font (hasheado, ex.: `__Inter_xxx`).
 * Uso em contextos que NAO herdam CSS — principalmente `textStyle.fontFamily`
 * do ECharts (canvas). Ja inclui o fallback do proprio next/font.
 */
export const interFontFamily = inter.style.fontFamily
