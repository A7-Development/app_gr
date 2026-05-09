"use client"

import * as React from "react"
import { cx } from "@/lib/utils"

type StrataIconTone = "onLight" | "onDark"

type StrataIconProps = {
  height?: number
  /**
   * - `"onLight"` (padrao): bandas em navy. Use sobre fundo claro
   *   (header sticky no app, paginas brancas).
   * - `"onDark"`: bandas em branco. Use sobre fundo escuro (hero zone
   *   da `HeroSplitAuth`, splash screen).
   *
   * Os tips laranja (▲▼) sao identicos nos dois tones — sao a
   * assinatura cromatica da marca.
   */
  tone?: StrataIconTone
  className?: string
}

const SOURCES: Record<StrataIconTone, string> = {
  onLight: "/strata-icon.png",
  onDark: "/strata-icon-on-dark.png",
}

/**
 * Logo oficial da marca Strata FIDC Analytics — apenas o simbolo
 * (hexagono com tips laranja + 3 bandas horizontais).
 *
 * Renderizado a partir de PNG transparente em `public/`,
 * gerado da arte oficial do handoff (`assets/strata-logo.png`).
 */
export function StrataIcon({
  height = 64,
  tone = "onLight",
  className,
}: StrataIconProps) {
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={SOURCES[tone]}
      alt="Strata"
      width={height}
      height={height}
      className={cx("shrink-0 select-none", className)}
      draggable={false}
    />
  )
}
