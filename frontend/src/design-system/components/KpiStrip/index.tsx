// src/design-system/components/KpiStrip/index.tsx
//
// KpiCard canonico do projeto (Strata Design System / iteracao 2026-04-29).
//
// Layout default: side-by-side — texto na esquerda (label, value, delta),
// chart lateral compacto na direita, OriginDot ancorado no rodape esquerdo.
// Inspiracao: handoff "Total Revenue" + escolha de densidade 4-col do
// usuario (ver preview/kpicard-v2 para historico de iteracao).
//
// 3 variantes: compact (18px / 70x36) · default (20px / 100x44) · hero (30px / 130x56)
// 2 layouts:   side (default) · stacked (chart abaixo do conteudo)
//
// Features:
//   - intensity bars opcionais ao lado do value
//   - alert badge (warn / critical) ao lado do label quando threshold cruzado
//   - callout pill no pico do sparkline (para destacar magnitude do delta)
//   - endpoint dot opcional
//   - source + updatedAtISO via OriginDot
//
// Compat: a `Sparkline` exportada e mantida (full-width, 80x28) porque
// `DataTable/cells/SparklineCell` depende dela. O sparkline novo
// (side-mounted com callout) e o `KpiSparkline` interno deste modulo.

"use client"

import * as React from "react"
import {
  RiArrowUpLine,
  RiArrowDownLine,
  RiAlertLine,
  RiErrorWarningLine,
} from "@remixicon/react"
import { cx } from "@/lib/utils"
import { OriginDot } from "@/design-system/components/OriginDot"

// ════════════════════════════════════════════════════════════════════════
// IntensityBars
// ════════════════════════════════════════════════════════════════════════

export type IntensityTone = "pos" | "neg" | "neu" | "info"
export type IntensityLevel = "low" | "mid" | "high" | "critical"

const TONE_FILLED: Record<IntensityTone, string> = {
  pos: "bg-[#059669]",
  neg: "bg-[#DC2626]",
  neu: "bg-[#D97706]",
  info: "bg-[#2563EB]",
}

const TONE_EMPTY = "bg-gray-200 dark:bg-gray-700"

const DEFAULT_THRESHOLDS: Record<
  IntensityTone,
  { mid: number; high: number; critical: number }
> = {
  neg: { mid: 33, high: 66, critical: 90 },
  pos: { mid: 33, high: 66, critical: 90 },
  neu: { mid: 33, high: 66, critical: 90 },
  info: { mid: 33, high: 66, critical: 90 },
}

export interface IntensityBarsProps {
  tone: IntensityTone
  level?: IntensityLevel
  currentValue?: number
  thresholds?: { mid: number; high: number; critical: number }
  className?: string
}

function calcLevel(
  value: number,
  tone: IntensityTone,
  thresholds?: IntensityBarsProps["thresholds"],
): IntensityLevel {
  const t = thresholds ?? DEFAULT_THRESHOLDS[tone]
  if (value >= t.critical) return "critical"
  if (value >= t.high) return "high"
  if (value >= t.mid) return "mid"
  return "low"
}

export function KpiIntensity({
  tone,
  level: levelProp,
  currentValue,
  thresholds,
  className,
}: IntensityBarsProps) {
  const level =
    currentValue != null
      ? calcLevel(currentValue, tone, thresholds)
      : (levelProp ?? "low")

  const fills: [boolean, boolean, boolean] =
    level === "critical" || level === "high"
      ? [true, true, true]
      : level === "mid"
        ? [true, true, false]
        : [true, false, false]

  const isCritical = level === "critical"
  const filled = TONE_FILLED[tone]

  return (
    <span
      aria-hidden="true"
      className={cx(
        "inline-flex shrink-0 items-end gap-[2px] mb-[2px] mr-[1px]",
        className,
      )}
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

// ════════════════════════════════════════════════════════════════════════
// Sparkline (LEGACY) — full-width, 80xN. Mantido para SparklineCell.
// ════════════════════════════════════════════════════════════════════════

export interface SparklineProps {
  data: number[]
  color?: string
  height?: number
  className?: string
}

export function Sparkline({
  data,
  color = "#2563EB",
  height = 28,
  className,
}: SparklineProps) {
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
          <stop offset="0%" stopColor={color} stopOpacity={0.12} />
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

// ════════════════════════════════════════════════════════════════════════
// KpiSparkline (interno) — side-mounted, dimensoes fixas, callout opcional
// ════════════════════════════════════════════════════════════════════════

interface KpiSparklineProps {
  data: number[]
  color?: string
  width: number
  height: number
  showEndDot?: boolean
  callout?: string
  calloutColor?: string
  className?: string
}

function KpiSparkline({
  data,
  color = "#10B981",
  width,
  height,
  showEndDot = false,
  callout,
  calloutColor,
  className,
}: KpiSparklineProps) {
  const id = React.useId().replace(/:/g, "")
  if (data.length < 2) return null

  const min = Math.min(...data)
  const max = Math.max(...data)
  const rng = max - min || 1

  const calloutSpace = callout ? 18 : 4
  const bottomPad = 4
  const chartH = height - calloutSpace - bottomPad

  const pts = data.map<[number, number]>((v, i) => {
    const x = (i / (data.length - 1)) * width
    const y = calloutSpace + (chartH - ((v - min) / rng) * chartH)
    return [x, y]
  })

  const linePoints = pts
    .map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`)
    .join(" ")
  const fillPoly =
    `${pts[0][0].toFixed(1)},${height} ` +
    linePoints +
    ` ${pts[pts.length - 1][0].toFixed(1)},${height}`

  const peakIdx = data.indexOf(max)
  const peakX = pts[peakIdx][0]
  const peakY = pts[peakIdx][1]
  const lastX = pts[pts.length - 1][0]
  const lastY = pts[pts.length - 1][1]

  const calloutBg = calloutColor ?? color
  const calloutWidthEstimate = Math.max(40, callout ? callout.length * 6.5 : 0)
  const calloutLeft = Math.max(
    0,
    Math.min(width - calloutWidthEstimate, peakX - calloutWidthEstimate / 2),
  )

  return (
    <div className={cx("relative shrink-0", className)} style={{ width, height }}>
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <defs>
          <linearGradient
            id={`kpisparkline-${id}`}
            x1="0"
            y1="0"
            x2="0"
            y2="1"
          >
            <stop offset="0%" stopColor={color} stopOpacity={0.22} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <polygon points={fillPoly} fill={`url(#kpisparkline-${id})`} />
        <polyline
          points={linePoints}
          fill="none"
          stroke={color}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {callout && (
          <line
            x1={peakX}
            y1={peakY + 4}
            x2={peakX}
            y2={height - bottomPad}
            stroke={color}
            strokeWidth="0.75"
            strokeDasharray="2 2"
            opacity="0.4"
          />
        )}
        {callout && (
          <circle
            cx={peakX}
            cy={peakY}
            r="3"
            fill={color}
            stroke="#fff"
            strokeWidth="1.5"
          />
        )}
        {showEndDot && peakIdx !== data.length - 1 && (
          <circle
            cx={lastX}
            cy={lastY}
            r="2.5"
            fill={color}
            stroke="#fff"
            strokeWidth="1.25"
          />
        )}
      </svg>
      {callout && (
        <span
          className="absolute rounded px-1.5 py-0.5 text-[10px] font-semibold leading-none text-white shadow-sm"
          style={{
            backgroundColor: calloutBg,
            top: 0,
            left: calloutLeft,
          }}
        >
          {callout}
        </span>
      )}
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════
// AlertThreshold + AlertBadge
// ════════════════════════════════════════════════════════════════════════

export interface AlertThreshold {
  value: number
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
        "inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-px",
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

// ════════════════════════════════════════════════════════════════════════
// KpiCard
// ════════════════════════════════════════════════════════════════════════

export type KpiVariant = "compact" | "default" | "hero"
export type KpiLayout = "side" | "stacked"

interface KpiSizeProfile {
  rootGap: string
  contentGap: string
  labelSize: string
  valueSize: string
  subSize: string
  deltaSize: string
  arrowSize: string
  sparkW: number
  sparkH: number
  sideGap: string
}

const KPI_SIZES: Record<KpiVariant, KpiSizeProfile> = {
  compact: {
    rootGap: "gap-1",
    contentGap: "gap-0.5",
    labelSize: "text-[10px] tracking-[0.05em]",
    valueSize: "text-[18px] leading-none",
    subSize: "text-[11px]",
    deltaSize: "text-[10px]",
    arrowSize: "size-3",
    sparkW: 70,
    sparkH: 36,
    sideGap: "gap-3",
  },
  default: {
    rootGap: "gap-1.5",
    contentGap: "gap-1",
    labelSize: "text-[11px] tracking-[0.05em]",
    valueSize: "text-[20px] leading-none",
    subSize: "text-[12px]",
    deltaSize: "text-[11px]",
    arrowSize: "size-3",
    sparkW: 100,
    sparkH: 44,
    sideGap: "gap-4",
  },
  hero: {
    rootGap: "gap-2",
    contentGap: "gap-1.5",
    labelSize: "text-sm tracking-[0.04em]",
    valueSize: "text-[30px] leading-none",
    subSize: "text-sm",
    deltaSize: "text-xs",
    arrowSize: "size-4",
    sparkW: 130,
    sparkH: 56,
    sideGap: "gap-5",
  },
}

export interface KpiDelta {
  value: number
  suffix?: string
  direction?: "up" | "down"
  good?: boolean
}

export interface KpiCardProps {
  label: string
  value: string
  sub?: string
  delta?: KpiDelta
  /** Texto descritivo a direita do delta. Default: "vs mês anterior". */
  deltaSub?: string
  /** Barras de intensidade ao lado do value. */
  intensity?: Omit<IntensityBarsProps, "className">
  /** Serie temporal para o sparkline lateral. */
  sparkData?: number[]
  /** Cor do sparkline (default: emerald #10B981). */
  sparkColor?: string
  /** Threshold que dispara AlertBadge ao lado do label. */
  alertThreshold?: AlertThreshold
  /** Valor numerico atual (usado pelo intensity + alert). */
  currentValue?: number
  /** Fonte do dado (renderiza OriginDot no rodape). */
  source?: string
  /** Timestamp ISO da ultima atualizacao (tooltip do OriginDot). */
  updatedAtISO?: string | null
  /** Tamanho do card. Default: "default". */
  variant?: KpiVariant
  /** "side" (default) chart a direita / "stacked" chart abaixo do conteudo. */
  layout?: KpiLayout
  /** Override das dimensoes do sparkline (uso em layouts apertados). */
  sparkOverride?: { width: number; height: number }
  /** Callout pill no pico do sparkline (ex.: "+R$ 4,2M"). */
  calloutText?: string
  /** Mostra dot no endpoint do sparkline. Default: false. */
  showEndDot?: boolean
  className?: string
}

export function KpiCard({
  label,
  value,
  sub,
  delta,
  deltaSub = "vs mês anterior",
  intensity,
  sparkData,
  sparkColor = "#10B981",
  alertThreshold,
  currentValue,
  source,
  updatedAtISO,
  variant = "default",
  layout = "side",
  sparkOverride,
  calloutText,
  showEndDot = false,
  className,
}: KpiCardProps) {
  const s = KPI_SIZES[variant]

  const dir = delta?.direction ?? (delta && delta.value >= 0 ? "up" : "down")
  const good = delta?.good ?? dir === "up"
  const ArrowIcon = dir === "up" ? RiArrowUpLine : RiArrowDownLine
  const deltaColor = good
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-red-600 dark:text-red-400"
  const calloutBgColor = good ? "#10B981" : "#DC2626"

  const showAlert =
    alertThreshold != null &&
    currentValue != null &&
    currentValue >= alertThreshold.value

  const hasSpark = sparkData != null && sparkData.length > 1

  const sparkW = sparkOverride?.width ?? s.sparkW
  const sparkH = sparkOverride?.height ?? s.sparkH

  const contentColumn = (
    <div className={cx("flex min-w-0 flex-col", s.contentGap)}>
      <div className="flex items-center gap-2">
        <span
          className={cx(
            "font-medium uppercase leading-tight text-gray-500 dark:text-gray-400 truncate",
            s.labelSize,
          )}
        >
          {label}
        </span>
        {showAlert && alertThreshold && <AlertBadge threshold={alertThreshold} />}
      </div>

      <div
        className={cx(
          "flex flex-wrap items-end",
          variant === "hero" ? "gap-2" : "gap-1.5",
        )}
      >
        {intensity && <KpiIntensity {...intensity} />}
        <span
          className={cx(
            "font-semibold leading-none tracking-tight tabular-nums text-gray-900 dark:text-gray-50",
            s.valueSize,
          )}
        >
          {value}
        </span>
        {sub && (
          <span
            className={cx(
              "tabular-nums text-gray-400 dark:text-gray-500 self-end ml-1",
              s.subSize,
            )}
          >
            <span
              aria-hidden="true"
              className="mr-0.5 text-gray-300 dark:text-gray-600"
            >
              —
            </span>
            {sub}
          </span>
        )}
      </div>

      {delta && (
        <p
          className={cx(
            "tabular-nums text-gray-500 dark:text-gray-400",
            s.deltaSize,
          )}
        >
          <span
            className={cx(
              "inline-flex items-center gap-0.5 font-medium",
              deltaColor,
            )}
          >
            <ArrowIcon
              className={cx(s.arrowSize, "shrink-0")}
              aria-hidden="true"
            />
            {Math.abs(delta.value).toLocaleString("pt-BR", {
              maximumFractionDigits: 2,
            })}
            {delta.suffix ?? ""}
          </span>
          <span
            aria-hidden="true"
            className="mx-1.5 text-gray-300 dark:text-gray-700"
          >
            ·
          </span>
          <span>{deltaSub}</span>
        </p>
      )}
    </div>
  )

  const sparkChart = hasSpark ? (
    <KpiSparkline
      data={sparkData}
      color={sparkColor}
      width={sparkW}
      height={sparkH}
      showEndDot={showEndDot}
      callout={calloutText}
      calloutColor={calloutBgColor}
    />
  ) : null

  return (
    <div className={cx("flex flex-col", s.rootGap, className)}>
      {layout === "side" ? (
        <div className={cx("flex items-center", s.sideGap)}>
          {contentColumn}
          {sparkChart}
        </div>
      ) : (
        <>
          {contentColumn}
          {sparkChart && <div className="-mx-1">{sparkChart}</div>}
        </>
      )}

      {source && (
        <div className="mt-0.5">
          <OriginDot source={source} updatedAtISO={updatedAtISO} />
        </div>
      )}
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════
// KpiStrip — container com cols configuravel
// ════════════════════════════════════════════════════════════════════════
//
// Densidade canonica = 5 KPIs em xl (densidade natural de dashboard FIDC
// operacional: PL, Subordinacao, Rentabilidade, Concentracao, Resgates).
// Para dashboards executivos / "hero feel" usa cols={4}.
//
// Cada cols tem um max-w que garante que `variant="default"` (chart 100x44,
// value 20px) caiba sem squeeze em todos os cards do strip.

export type KpiStripCols = 3 | 4 | 5 | 6

const STRIP_COLS_CONFIG: Record<
  KpiStripCols,
  { gridCls: string; maxWCls: string }
> = {
  3: { gridCls: "xl:grid-cols-3", maxWCls: "max-w-[960px]" },
  4: { gridCls: "xl:grid-cols-4", maxWCls: "max-w-[1280px]" },
  5: { gridCls: "xl:grid-cols-5", maxWCls: "max-w-[1480px]" }, // canonico
  6: { gridCls: "xl:grid-cols-6", maxWCls: "max-w-[1680px]" }, // sugere variant=compact
}

export function KpiStrip({
  children,
  cols = 5,
  className,
}: {
  children: React.ReactNode
  /** Numero de colunas em xl. Default 5 (canonico). 4 = "hero feel". */
  cols?: KpiStripCols
  className?: string
}) {
  const config = STRIP_COLS_CONFIG[cols]
  return (
    <div
      className={cx(
        "grid grid-cols-1 gap-5 sm:grid-cols-2",
        config.gridCls,
        "mx-auto w-full",
        config.maxWCls,
        "rounded border border-gray-200 bg-white px-5 py-4 shadow-xs",
        "dark:border-gray-800 dark:bg-gray-925",
        className,
      )}
    >
      {children}
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════
// FIDC_KPI_META — presets canonicos para o dominio
// ════════════════════════════════════════════════════════════════════════

export const FIDC_KPI_META = {
  pl: {
    label: "PL do Fundo",
    deltaSub: "vs mês anterior",
  },
  rentabilidade: {
    label: "Rentabilidade vs CDI",
    deltaSub: "vs benchmark",
    intensity: {
      tone: "pos" as IntensityTone,
      thresholds: { mid: 90, high: 100, critical: 115 },
    },
    sparkColor: "#2563EB",
  },
  inadimplencia: {
    label: "Inadimplência",
    deltaSub: "vs mês anterior",
    intensity: {
      tone: "neg" as IntensityTone,
      thresholds: { mid: 2, high: 5, critical: 10 },
    },
    sparkColor: "#DC2626",
  },
  pdd: {
    label: "PDD",
    deltaSub: "vs mês anterior",
    intensity: {
      tone: "neg" as IntensityTone,
      thresholds: { mid: 1, high: 3, critical: 7 },
    },
  },
  cessoesPendentes: {
    label: "Cessões Pendentes",
    deltaSub: "vs semana anterior",
    intensity: {
      tone: "neg" as IntensityTone,
      thresholds: { mid: 10, high: 30, critical: 100 },
    },
    alertThreshold: {
      value: 30,
      severity: "warn" as const,
      message: "Acima do volume usual — verifique a fila de aprovação",
    },
  },
} as const
