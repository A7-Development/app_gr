// src/design-system/components/KpiStrip/index.tsx
// KPI strip with 3 variants (compact/default/hero), Sparkline, IntensityBars,
// and FIDC canonical presets.

"use client"

import * as React from "react"
import { RiArrowUpLine, RiArrowDownLine, RiAlertLine, RiErrorWarningLine } from "@remixicon/react"
import { tv, type VariantProps } from "tailwind-variants"
import { cx } from "@/lib/utils"
import { OriginDot } from "@/design-system/components/OriginDot"

export type IntensityTone  = "pos" | "neg" | "neu" | "info"
export type IntensityLevel = "low" | "mid" | "high" | "critical"

const TONE_FILLED: Record<IntensityTone, string> = {
  pos:  "bg-[#059669]",
  neg:  "bg-[#DC2626]",
  neu:  "bg-[#D97706]",
  info: "bg-[#2563EB]",
}

const TONE_EMPTY = "bg-gray-200 dark:bg-gray-700"

const DEFAULT_THRESHOLDS: Record<IntensityTone, { mid: number; high: number; critical: number }> = {
  neg:  { mid: 33, high: 66, critical: 90 },
  pos:  { mid: 33, high: 66, critical: 90 },
  neu:  { mid: 33, high: 66, critical: 90 },
  info: { mid: 33, high: 66, critical: 90 },
}

export interface IntensityBarsProps {
  tone:          IntensityTone
  level?:        IntensityLevel
  currentValue?: number
  thresholds?: {
    mid:      number
    high:     number
    critical: number
  }
  className?: string
}

function calcLevel(
  value: number,
  tone: IntensityTone,
  thresholds?: IntensityBarsProps["thresholds"],
): IntensityLevel {
  const t = thresholds ?? DEFAULT_THRESHOLDS[tone]
  if (value >= t.critical) return "critical"
  if (value >= t.high)     return "high"
  if (value >= t.mid)      return "mid"
  return "low"
}

export function KpiIntensity({
  tone,
  level: levelProp,
  currentValue,
  thresholds,
  className,
}: IntensityBarsProps) {
  const level = currentValue != null
    ? calcLevel(currentValue, tone, thresholds)
    : (levelProp ?? "low")

  const fills: [boolean, boolean, boolean] =
    level === "critical" || level === "high" ? [true, true, true]
    : level === "mid"                        ? [true, true, false]
    :                                          [true, false, false]

  const isCritical = level === "critical"
  const filled = TONE_FILLED[tone]

  return (
    <span
      aria-hidden="true"
      className={cx("inline-flex shrink-0 items-end gap-[2px] mb-[2px] mr-[1px]", className)}
      style={{ height: 12 }}
    >
      {([4, 8, 12] as const).map((h, i) => (
        <span
          key={i}
          className={cx(
            "w-[3px] rounded-[1px]",
            fills[i] ? filled : TONE_EMPTY,
            isCritical && i === 2 && fills[i] && "motion-safe:animate-pulse",
          )}
          style={{ height: h }}
        />
      ))}
    </span>
  )
}

export interface SparklineProps {
  data:       number[]
  color?:     string
  height?:    number
  className?: string
}

export function Sparkline({ data, color = "#2563EB", height = 28, className }: SparklineProps) {
  const id = React.useId().replace(/:/g, "")

  if (data.length < 2) return null

  const W = 80
  const min = Math.min(...data)
  const max = Math.max(...data)
  const rng = max - min || 1

  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * W
    const y = height - ((v - min) / rng) * (height - 4) - 2
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })

  const linePoints = pts.join(" ")
  const lastXY = pts[pts.length - 1]
  const lastX = lastXY.split(",")[0]
  const fillPoly = `${pts[0].split(",")[0]},${height} ${linePoints} ${lastX},${height}`

  return (
    <svg
      viewBox={`0 0 ${W} ${height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
      className={cx("w-full", className)}
      style={{ height }}
    >
      <defs>
        <linearGradient id={`spark-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor={color} stopOpacity={0.12} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <polygon points={fillPoly} fill={`url(#spark-${id})`} />
      <polyline
        points={linePoints}
        fill="none"
        stroke={color}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

export interface AlertThreshold {
  value:    number
  severity: "warn" | "critical"
  message?: string
}

function AlertBadge({ threshold }: { threshold: AlertThreshold }) {
  const isWarn = threshold.severity === "warn"
  const Icon = isWarn ? RiAlertLine : RiErrorWarningLine

  return (
    <span
      role="status"
      aria-label={threshold.message ?? (isWarn ? "Atenção" : "Crítico")}
      title={threshold.message}
      className={cx(
        "inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-0.5",
        "text-[10px] font-semibold leading-none",
        isWarn
          ? "bg-[rgba(202,138,4,.12)] text-[#CA8A04]"
          : cx(
              "bg-[rgba(220,38,38,.12)] text-[#DC2626]",
              "motion-safe:animate-pulse",
            ),
      )}
    >
      <Icon className="size-2.5 shrink-0" aria-hidden="true" />
      {isWarn ? "Atenção" : "Crítico"}
    </span>
  )
}

const kpiCardVariants = tv({
  slots: {
    root:      "relative flex flex-col",
    labelCls:  "font-medium uppercase leading-tight text-gray-500 dark:text-gray-400",
    valueWrap: "flex flex-wrap items-end",
    valueCls:  "font-semibold leading-none tracking-tight tabular-nums text-gray-900 dark:text-gray-50",
    subCls:    "tabular-nums text-gray-400 dark:text-gray-500 self-end",
    deltaCls:  "tabular-nums text-gray-500 dark:text-gray-400",
    deltaDot:  "text-gray-300 dark:text-gray-700",
  },
  variants: {
    variant: {
      compact: {
        root:      "gap-1",
        labelCls:  "text-[10px] tracking-[0.05em]",
        valueWrap: "gap-1",
        valueCls:  "text-[18px]",
        subCls:    "text-[11px]",
        deltaCls:  "text-[11px]",
      },
      default: {
        root:      "gap-1.5",
        labelCls:  "text-[11px] tracking-[0.05em]",
        valueWrap: "gap-1.5",
        valueCls:  "text-[22px]",
        subCls:    "text-[12px]",
        deltaCls:  "text-[11px]",
      },
      hero: {
        root:      "gap-2",
        labelCls:  "text-sm tracking-[0.04em]",
        valueWrap: "gap-2",
        valueCls:  "text-4xl",
        subCls:    "text-sm",
        deltaCls:  "text-xs",
      },
    },
  },
  defaultVariants: { variant: "default" },
})

export interface KpiDelta {
  value:      number
  suffix?:    string
  direction?: "up" | "down"
  good?:      boolean
}

export interface KpiCardProps extends VariantProps<typeof kpiCardVariants> {
  label:           string
  value:           string
  sub?:            string
  delta?:          KpiDelta
  deltaSub?:       string
  intensity?:      Omit<IntensityBarsProps, "className">
  sparkData?:      number[]
  sparkColor?:     string
  alertThreshold?: AlertThreshold
  currentValue?:   number
  /** Provenance: data source label (e.g., "QiTech", "CVM"). Renders OriginDot when set. */
  source?:         string
  /** ISO timestamp of last data refresh. Shown in OriginDot tooltip. */
  updatedAtISO?:   string | null
  className?:      string
}

export function KpiCard({
  label,
  value,
  sub,
  delta,
  deltaSub   = "vs mês anterior",
  intensity,
  sparkData,
  sparkColor = "#2563EB",
  alertThreshold,
  currentValue,
  source,
  updatedAtISO,
  variant    = "default",
  className,
}: KpiCardProps) {
  const {
    root, labelCls, valueWrap, valueCls, subCls, deltaCls, deltaDot,
  } = kpiCardVariants({ variant })

  const dir = delta?.direction ?? (delta && delta.value >= 0 ? "up" : "down")
  const good = delta?.good ?? dir === "up"

  const ArrowIcon = dir === "up" ? RiArrowUpLine : RiArrowDownLine
  const deltaColor = good
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-red-600 dark:text-red-400"
  const arrowSize = variant === "hero" ? "size-4" : "size-3"

  const showAlert = alertThreshold != null && currentValue != null
    && currentValue >= alertThreshold.value

  return (
    <div className={cx(root(), className)}>
      <div className={cx(showAlert ? "flex items-center justify-between gap-1.5" : "")}>
        <span className={labelCls()}>{label}</span>
        {showAlert && alertThreshold && <AlertBadge threshold={alertThreshold} />}
      </div>

      <div className={valueWrap()}>
        {intensity && <KpiIntensity {...intensity} />}
        <span className={valueCls()}>{value}</span>
        {sub && (
          <span className={cx(subCls(), "ml-1")}>
            <span aria-hidden="true" className="mr-0.5 text-gray-300 dark:text-gray-600">—</span>
            {sub}
          </span>
        )}
      </div>

      {delta && (
        <p className={deltaCls()}>
          <span className={cx("inline-flex items-center gap-0.5 font-medium", deltaColor)}>
            <ArrowIcon className={cx(arrowSize, "shrink-0")} aria-hidden="true" />
            {Math.abs(delta.value).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}
            {delta.suffix ?? ""}
          </span>
          <span aria-hidden="true" className={cx("mx-1.5", deltaDot())}>·</span>
          <span>{deltaSub}</span>
        </p>
      )}

      {sparkData && sparkData.length > 1 && (
        <div className="mt-0.5">
          <Sparkline data={sparkData} color={sparkColor} />
        </div>
      )}

      {source && <OriginDot source={source} updatedAtISO={updatedAtISO} />}
    </div>
  )
}

export function KpiStrip({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cx("grid grid-cols-2 gap-5 min-[720px]:grid-cols-3 xl:grid-cols-6", className)}>
      {children}
    </div>
  )
}

export const FIDC_KPI_META = {
  pl: {
    label:    "PL do Fundo",
    deltaSub: "vs mês anterior",
  },
  rentabilidade: {
    label:    "Rentabilidade vs CDI",
    deltaSub: "vs benchmark",
    intensity: {
      tone:       "pos" as IntensityTone,
      thresholds: { mid: 90, high: 100, critical: 115 },
    },
    sparkColor: "#2563EB",
  },
  inadimplencia: {
    label:    "Inadimplência",
    deltaSub: "vs mês anterior",
    intensity: {
      tone:       "neg" as IntensityTone,
      thresholds: { mid: 2, high: 5, critical: 10 },
    },
    sparkColor: "#DC2626",
  },
  pdd: {
    label:    "PDD",
    deltaSub: "vs mês anterior",
    intensity: {
      tone:       "neg" as IntensityTone,
      thresholds: { mid: 1, high: 3, critical: 7 },
    },
  },
  cessoesPendentes: {
    label:    "Cessões Pendentes",
    deltaSub: "vs semana anterior",
    intensity: {
      tone:       "neg" as IntensityTone,
      thresholds: { mid: 10, high: 30, critical: 100 },
    },
    alertThreshold: {
      value:    30,
      severity: "warn" as const,
      message:  "Acima do volume usual — verifique a fila de aprovação",
    },
  },
} as const
