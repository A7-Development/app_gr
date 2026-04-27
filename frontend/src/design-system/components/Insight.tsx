"use client"

import * as React from "react"
import {
  RiCloseLine,
  RiSparkling2Line,
  RiSparklingFill,
  type RemixiconComponentType,
} from "@remixicon/react"

import { cx } from "@/lib/utils"

//
// Insight + InsightBar -- faixa de insights gerados por IA (Zona Z4).
//
// Dois modos de renderizacao no `InsightBar`:
//
// - variant="panel" (DEFAULT, alinhado com handoff bi-padrao 2026-04-26):
//   Single box violeta com eyebrow "ANALISE IA · AUTO" + bullets `>`.
//   Cada filho (string ou {text}) vira uma linha bullet. Use quando a
//   pagina derivar de DashboardBiPadrao.
//
// - variant="stacked" (legacy, handoff bi-framework-minimal-v2):
//   Stack de cards <Insight /> separados, multi-tone (violet/amber/blue),
//   dismissivel + CTA. Use em paginas onde os insights sao acoes
//   independentes (ex.: alertas do Risco com CTAs distintos).
//
// O tom no Insight individual nao e cor decorativa -- sinaliza intencao:
//   violet: gerado por IA, neutro (default)
//   amber:  atencao (concentracao, limite quase estourado)
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

export type InsightBarVariant = "panel" | "stacked"

/** Item de bullet do `InsightBar` em modo panel. Texto puro ou objeto. */
export type InsightBarItem = string | { text: string }

type InsightBarProps = {
  /**
   * Conteudo. No modo `panel`: aceita array `items` OU `<Insight />` filhos
   * (filhos sao convertidos em bullets pelo texto). No modo `stacked`:
   * passe `<Insight />` filhos.
   */
  children?: React.ReactNode
  items?: InsightBarItem[]
  /** Default: "panel" (handoff bi-padrao). "stacked" = legacy multi-tone. */
  variant?: InsightBarVariant
  /** Eyebrow do panel. Default: "ANALISE IA · AUTO". */
  eyebrow?: string
  className?: string
}

function PanelEyebrow({ text }: { text: string }) {
  return (
    <div className="mb-1.5 flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.06em] text-violet-600 dark:text-violet-400">
      <span>{text}</span>
    </div>
  )
}

function PanelBullet({ text }: { text: string }) {
  return (
    <div className="flex gap-1.5 text-[12px] leading-[1.5] text-gray-900 dark:text-gray-50">
      <span aria-hidden="true" className="shrink-0 text-violet-600 dark:text-violet-400">
        ›
      </span>
      <span>{text}</span>
    </div>
  )
}

function extractTextsFromChildren(children: React.ReactNode): string[] {
  const texts: string[] = []
  React.Children.forEach(children, (child) => {
    if (!React.isValidElement(child)) return
    const props = child.props as { text?: string }
    if (typeof props.text === "string") texts.push(props.text)
  })
  return texts
}

export function InsightBar({
  children,
  items,
  variant = "panel",
  eyebrow = "ANALISE IA · AUTO",
  className,
}: InsightBarProps) {
  if (variant === "stacked") {
    return <div className={cx("flex flex-col gap-1.5", className)}>{children}</div>
  }

  // Panel mode (handoff bi-padrao).
  const bullets = items
    ? items.map((it) => (typeof it === "string" ? it : it.text))
    : extractTextsFromChildren(children)

  if (bullets.length === 0) return null

  return (
    <div
      className={cx(
        "flex gap-2.5 rounded-[6px] border px-3.5 py-2.5",
        "border-violet-200 bg-violet-50",
        "dark:border-violet-700/40 dark:bg-violet-500/[0.08]",
        className,
      )}
    >
      <RiSparkling2Line
        aria-hidden="true"
        className="mt-0.5 size-4 shrink-0 text-violet-600 dark:text-violet-400"
      />
      <div className="flex flex-1 flex-col">
        <PanelEyebrow text={eyebrow} />
        <div className="flex flex-col gap-1">
          {bullets.map((text, i) => (
            <PanelBullet key={i} text={text} />
          ))}
        </div>
      </div>
    </div>
  )
}
