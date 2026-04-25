"use client"

import * as React from "react"

import { cx } from "@/lib/utils"
import { OriginDot } from "@/design-system/components/OriginDot"

//
// KPICard -- Zona Z3 do BI Framework (handoff v2 minimal, 2026-04-24).
//
// Spec: bi-minimal-v2.css (.kpi-min2-*).
//
// Layout "flat" (sem card chrome):
//   [label 12px gray-500]
//   [bars] [value 19px g900] [— sub 13px g400]
//   [↑ delta colorido] · [sub 11px g500]
//
// - Sem borda de card, sem shadow, sem bg — o numero domina.
// - Intensity (<KPIIntensity />) a esquerda do valor, 3 barrinhas com tom.
// - Delta em texto simples com cor semantica (nao pill).
// - OriginDot absoluto no canto inferior direito.
//

export type KPIIntensityTone = "pos" | "neu" | "neg" | "info"
export type KPIIntensityLevel = "low" | "mid" | "high"

type KPIIntensityProps = {
  tone: KPIIntensityTone
  level: KPIIntensityLevel
  className?: string
}

// 3 barras verticais (40% / 70% / 100%) pintadas conforme `level`.
// Handoff v2: bi-minimal-v2.css linhas 44-71.
export function KPIIntensity({ tone, level, className }: KPIIntensityProps) {
  const toneClass =
    tone === "pos"
      ? "text-emerald-500"
      : tone === "neu"
        ? "text-amber-500"
        : tone === "neg"
          ? "text-red-500"
          : "text-blue-500"

  const fills: [boolean, boolean, boolean] =
    level === "high"
      ? [true, true, true]
      : level === "mid"
        ? [true, true, false]
        : [true, false, false]

  const barBase = "w-[3px] rounded-[1px] bg-gray-200 dark:bg-gray-800"
  const filled = "bg-current"

  return (
    <span
      aria-hidden="true"
      className={cx(
        "inline-flex h-[18px] shrink-0 items-end gap-[2px]",
        toneClass,
        className,
      )}
    >
      <span className={cx(barBase, "h-[40%]", fills[0] && filled)} />
      <span className={cx(barBase, "h-[70%]", fills[1] && filled)} />
      <span className={cx(barBase, "h-[100%]", fills[2] && filled)} />
    </span>
  )
}

type Delta = {
  value: number
  suffix?: string
  direction?: "up" | "down"
  /**
   * Se informado, indica se esse movimento (na direcao observada) e "bom".
   * Ex.: para "Taxa media", delta.direction="down" + good=true -> emerald.
   * Default: up=good, down=bad.
   */
  good?: boolean
}

type KPICardProps = {
  label: string
  value: string
  /** Texto inline apos o valor, precedido por em-dash automatico (ex.: "abr/26"). */
  sub?: string
  delta?: Delta
  /** Texto na linha abaixo do valor (default "vs mês anterior"). Usado com `delta`. */
  deltaSub?: string
  /** Indicador de intensidade (3 barrinhas). tom + nivel. */
  intensity?: { tone: KPIIntensityTone; level: KPIIntensityLevel }
  source?: string
  updatedAtISO?: string | null
  className?: string
}

export function KPICard({
  label,
  value,
  sub,
  delta,
  deltaSub = "vs mês anterior",
  intensity,
  source,
  updatedAtISO,
  className,
}: KPICardProps) {
  const dir = delta?.direction ?? (delta && delta.value >= 0 ? "up" : "down")
  const good = delta?.good ?? (dir === "up")
  const deltaColor = good
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-red-600 dark:text-red-400"
  const arrow = dir === "up" ? "↑" : "↓"

  return (
    <div
      className={cx(
        "relative flex flex-col gap-1.5",
        className,
      )}
    >
      <span className="text-xs font-medium leading-tight text-gray-500 dark:text-gray-400">
        {label}
      </span>
      <div className="flex flex-wrap items-center gap-2">
        {intensity && (
          <KPIIntensity tone={intensity.tone} level={intensity.level} />
        )}
        <span className="text-[19px] font-semibold leading-tight tracking-tight tabular-nums text-gray-900 dark:text-gray-50">
          {value}
        </span>
        {sub && (
          <span className="text-[13px] font-normal tabular-nums text-gray-400 dark:text-gray-500">
            <span aria-hidden="true" className="mr-1 text-gray-300 dark:text-gray-600">
              —
            </span>
            {sub}
          </span>
        )}
      </div>
      {delta && (
        <div className="text-[11px] leading-tight tabular-nums text-gray-500 dark:text-gray-400">
          <span className={cx("font-medium", deltaColor)}>
            {arrow}{" "}
            {Math.abs(delta.value).toLocaleString("pt-BR", {
              maximumFractionDigits: 2,
            })}
            {delta.suffix ?? ""}
          </span>
          <span aria-hidden="true" className="mx-1.5 text-gray-300 dark:text-gray-700">
            ·
          </span>
          <span>{deltaSub}</span>
        </div>
      )}
      {source && <OriginDot source={source} updatedAtISO={updatedAtISO} />}
    </div>
  )
}

//
// KPIStrip -- grid flat. Handoff v2: 5 colunas @ 1280, 3 @ 900, 2 abaixo.
// Aqui suportamos ate 6 (grid-cols-6 @ xl) para acomodar Benchmark.
//

type KPIStripProps = {
  children: React.ReactNode
  className?: string
}

export function KPIStrip({ children, className }: KPIStripProps) {
  return (
    <div
      className={cx(
        "grid grid-cols-2 gap-5",
        "min-[720px]:grid-cols-3 xl:grid-cols-6",
        className,
      )}
    >
      {children}
    </div>
  )
}
