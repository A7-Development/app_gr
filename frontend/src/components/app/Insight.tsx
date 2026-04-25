"use client"

import * as React from "react"
import {
  RiCloseLine,
  RiSparklingFill,
  type RemixiconComponentType,
} from "@remixicon/react"

import { cx } from "@/lib/utils"

//
// Insight + InsightBar -- faixa de insights gerados por IA (Zona Z4).
//
// Handoff v2 (bi-framework-minimal-v2):
// - 1 linha por insight, dismissivel, max 3 visiveis.
// - border-left 2px com cor semantica (violet default / amber warning /
//   blue info). Icone combina com o tom (violet=sparkling, amber=alert,
//   blue=info).
// - CTA pequeno a direita (ex.: "Ver no grafico").
//
// O tom nao e cor decorativa \u2014 sinaliza intencao do insight:
//   violet: gerado por IA, neutro (default)
//   amber:  atencao (concentracao, limite quase estourado, tendencia desfavoravel)
//   blue:   informativo (crescimento, oportunidade, noticia neutra)
//

export type InsightTone = "violet" | "amber" | "blue"

type ToneStyles = {
  border: string
  iconBg: string
  iconText: string
}

const TONE_STYLES: Record<InsightTone, ToneStyles> = {
  violet: {
    border: "border-l-violet-500 dark:border-l-violet-500",
    iconBg: "bg-violet-500/15 dark:bg-violet-500/20",
    iconText: "text-violet-600 dark:text-violet-400",
  },
  amber: {
    border: "border-l-amber-500 dark:border-l-amber-500",
    iconBg: "bg-amber-500/15 dark:bg-amber-500/20",
    iconText: "text-amber-600 dark:text-amber-400",
  },
  blue: {
    border: "border-l-blue-500 dark:border-l-blue-500",
    iconBg: "bg-blue-500/15 dark:bg-blue-500/20",
    iconText: "text-blue-600 dark:text-blue-400",
  },
}

type InsightProps = {
  text: string
  /** Tom do insight. Default: "violet" (IA neutra). */
  tone?: InsightTone
  /** Icone custom (sobrescreve o default por tom). */
  icon?: RemixiconComponentType
  cta?: { label: string; onClick?: () => void; href?: string }
  onDismiss?: () => void
  className?: string
}

export function Insight({
  text,
  tone = "violet",
  icon: IconProp,
  cta,
  onDismiss,
  className,
}: InsightProps) {
  const styles = TONE_STYLES[tone]
  const Icon = IconProp ?? RiSparklingFill

  return (
    <div
      className={cx(
        "relative flex items-center gap-2.5 rounded border border-gray-200 border-l-2",
        styles.border,
        "bg-white px-3 py-1.5 pr-9 text-xs text-gray-900",
        "dark:border-gray-800 dark:bg-gray-950 dark:text-gray-50",
        className,
      )}
    >
      <span
        aria-hidden="true"
        className={cx(
          "inline-flex size-4 shrink-0 items-center justify-center rounded-sm",
          styles.iconBg,
          styles.iconText,
        )}
      >
        <Icon className="size-3" />
      </span>
      <p className="flex-1 truncate tabular-nums">{text}</p>
      {cta && (
        cta.href ? (
          <a
            href={cta.href}
            className="shrink-0 text-[11px] font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
          >
            {cta.label}
          </a>
        ) : (
          <button
            type="button"
            onClick={cta.onClick}
            className="shrink-0 text-[11px] font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400 dark:hover:text-blue-300"
          >
            {cta.label}
          </button>
        )
      )}
      {onDismiss && (
        <button
          type="button"
          aria-label="Fechar insight"
          onClick={onDismiss}
          className="absolute right-1.5 top-1/2 inline-flex size-5 -translate-y-1/2 items-center justify-center rounded-sm text-gray-400 hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-800 dark:hover:text-gray-300"
        >
          <RiCloseLine className="size-3.5" />
        </button>
      )}
    </div>
  )
}

type InsightBarProps = {
  children: React.ReactNode
  className?: string
}

export function InsightBar({ children, className }: InsightBarProps) {
  return (
    <div className={cx("flex flex-col gap-1.5", className)}>{children}</div>
  )
}
