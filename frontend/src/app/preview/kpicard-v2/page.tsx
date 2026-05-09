"use client"

// Preview page (NAO mexe no componente real) — mock de alta fidelidade
// para iteracao de design do KpiCard.
//
// Versoes propostas (todas LOCAIS neste arquivo, nada exportado):
//   - v2: sparkline no canto superior-direito (compacto/discreto)
//   - v3: sparkline lateral GRANDE com callout opcional (proposta principal)
//
// Quando o usuario aprovar, promovemos pra
// src/design-system/components/KpiStrip/index.tsx.

import * as React from "react"
import {
  RiArrowUpLine,
  RiArrowDownLine,
  RiAlertLine,
  RiErrorWarningLine,
} from "@remixicon/react"
import { cx } from "@/lib/utils"
import {
  KpiCard,
  KpiStrip,
  KpiIntensity,
  FIDC_KPI_META,
  type IntensityBarsProps,
  type KpiDelta,
  type AlertThreshold,
} from "@/design-system/components/KpiStrip"
import { OriginDot } from "@/design-system/components/OriginDot"

// ──────────────────────────────────────────────────────────────────────────
// SparklineMini — versao compacta para canto superior-direito (v2)
// 40-56px largura, 16-24px altura
// ──────────────────────────────────────────────────────────────────────────
function SparklineMini({
  data,
  color = "#2563EB",
  width = 48,
  height = 20,
  className,
}: {
  data: number[]
  color?: string
  width?: number
  height?: number
  className?: string
}) {
  const id = React.useId().replace(/:/g, "")
  if (data.length < 2) return null

  const min = Math.min(...data)
  const max = Math.max(...data)
  const rng = max - min || 1

  const pts = data.map((v, i) => {
    const x = (i / (data.length - 1)) * width
    const y = height - ((v - min) / rng) * (height - 3) - 1.5
    return `${x.toFixed(1)},${y.toFixed(1)}`
  })

  const linePoints = pts.join(" ")
  const lastX = pts[pts.length - 1].split(",")[0]
  const fillPoly = `${pts[0].split(",")[0]},${height} ${linePoints} ${lastX},${height}`

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      aria-hidden="true"
      className={cx("shrink-0", className)}
    >
      <defs>
        <linearGradient id={`sparkmini-${id}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.18} />
          <stop offset="100%" stopColor={color} stopOpacity={0} />
        </linearGradient>
      </defs>
      <polygon points={fillPoly} fill={`url(#sparkmini-${id})`} />
      <polyline
        points={linePoints}
        fill="none"
        stroke={color}
        strokeWidth="1.25"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// SparklineSide — versao GRANDE lateral (v3, inspirada no reference)
// 100-160px largura, 48-72px altura
// + endpoint dot opcional + callout opcional (pill com valor de delta no pico)
// ──────────────────────────────────────────────────────────────────────────
function SparklineSide({
  data,
  color = "#10B981",
  width = 130,
  height = 56,
  showEndDot = true,
  callout,
  calloutColor,
  className,
}: {
  data: number[]
  color?: string
  width?: number
  height?: number
  showEndDot?: boolean
  callout?: string
  calloutColor?: string
  className?: string
}) {
  const id = React.useId().replace(/:/g, "")
  if (data.length < 2) return null

  const min = Math.min(...data)
  const max = Math.max(...data)
  const rng = max - min || 1

  // Reservar espaco no topo para callout
  const calloutSpace = callout ? 18 : 4
  const bottomPad = 4
  const chartH = height - calloutSpace - bottomPad

  const pts = data.map<[number, number]>((v, i) => {
    const x = (i / (data.length - 1)) * width
    const y = calloutSpace + (chartH - ((v - min) / rng) * chartH)
    return [x, y]
  })

  const linePoints = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ")
  const fillPoly =
    `${pts[0][0].toFixed(1)},${height} ` +
    linePoints +
    ` ${pts[pts.length - 1][0].toFixed(1)},${height}`

  // Pico (para posicionar callout)
  const peakIdx = data.indexOf(max)
  const peakX = pts[peakIdx][0]
  const peakY = pts[peakIdx][1]

  // Endpoint
  const lastX = pts[pts.length - 1][0]
  const lastY = pts[pts.length - 1][1]

  const calloutBg = calloutColor ?? color
  // Posicao do callout: centrado no pico, mas clampeado dentro da largura
  const calloutWidthEstimate = Math.max(40, callout ? callout.length * 6.5 : 0)
  const calloutLeft = Math.max(
    0,
    Math.min(width - calloutWidthEstimate, peakX - calloutWidthEstimate / 2),
  )

  return (
    <div className={cx("relative", className)} style={{ width, height }}>
      <svg
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        aria-hidden="true"
      >
        <defs>
          <linearGradient id={`sparkside-${id}`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.22} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <polygon points={fillPoly} fill={`url(#sparkside-${id})`} />
        <polyline
          points={linePoints}
          fill="none"
          stroke={color}
          strokeWidth="1.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {/* Linha vertical pontilhada no pico (apenas se tem callout) */}
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
        {/* Dot no pico */}
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
        {/* Endpoint dot (se ativado e nao colidir com peak) */}
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

// ──────────────────────────────────────────────────────────────────────────
// AlertBadgeV2 — copia da versao do KpiStrip
// ──────────────────────────────────────────────────────────────────────────
function AlertBadgeV2({ threshold }: { threshold: AlertThreshold }) {
  const isWarn = threshold.severity === "warn"
  const Icon = isWarn ? RiAlertLine : RiErrorWarningLine
  return (
    <span
      role="status"
      aria-label={threshold.message ?? (isWarn ? "Atencao" : "Critico")}
      title={threshold.message}
      className={cx(
        "inline-flex shrink-0 items-center gap-1 rounded-full px-2 py-px",
        "text-[10px] font-semibold leading-none",
        isWarn
          ? "bg-[rgba(202,138,4,.12)] text-[#CA8A04]"
          : cx("bg-[rgba(220,38,38,.12)] text-[#DC2626]", "motion-safe:animate-pulse"),
      )}
    >
      <Icon className="size-2.5 shrink-0" aria-hidden="true" />
      {isWarn ? "Atencao" : "Critico"}
    </span>
  )
}

// ══════════════════════════════════════════════════════════════════════════
// KpiCardV2 — sparkline no canto superior-direito (versao COMPACTA)
// ══════════════════════════════════════════════════════════════════════════

type V2Variant = "compact" | "default" | "hero"

interface KpiCardV2Props {
  label: string
  value: string
  sub?: string
  delta?: KpiDelta
  deltaSub?: string
  intensity?: Omit<IntensityBarsProps, "className">
  sparkData?: number[]
  sparkColor?: string
  alertThreshold?: AlertThreshold
  currentValue?: number
  source?: string
  updatedAtISO?: string | null
  variant?: V2Variant
  className?: string
}

const V2_SIZES: Record<V2Variant, {
  rootGap: string
  labelSize: string
  valueSize: string
  subSize: string
  deltaSize: string
  arrowSize: string
  sparkW: number
  sparkH: number
}> = {
  compact: {
    rootGap: "gap-0.5",
    labelSize: "text-[10px] tracking-[0.05em]",
    valueSize: "text-[18px] leading-none",
    subSize: "text-[11px]",
    deltaSize: "text-[10px]",
    arrowSize: "size-3",
    sparkW: 40,
    sparkH: 16,
  },
  default: {
    rootGap: "gap-1",
    labelSize: "text-[11px] tracking-[0.05em]",
    valueSize: "text-[22px] leading-none",
    subSize: "text-[12px]",
    deltaSize: "text-[11px]",
    arrowSize: "size-3",
    sparkW: 48,
    sparkH: 20,
  },
  hero: {
    rootGap: "gap-1.5",
    labelSize: "text-sm tracking-[0.04em]",
    valueSize: "text-4xl leading-none",
    subSize: "text-sm",
    deltaSize: "text-xs",
    arrowSize: "size-4",
    sparkW: 64,
    sparkH: 24,
  },
}

function KpiCardV2({
  label,
  value,
  sub,
  delta,
  deltaSub = "vs mes anterior",
  intensity,
  sparkData,
  sparkColor = "#2563EB",
  alertThreshold,
  currentValue,
  source,
  updatedAtISO,
  variant = "default",
  className,
}: KpiCardV2Props) {
  const s = V2_SIZES[variant]

  const dir = delta?.direction ?? (delta && delta.value >= 0 ? "up" : "down")
  const good = delta?.good ?? dir === "up"
  const ArrowIcon = dir === "up" ? RiArrowUpLine : RiArrowDownLine
  const deltaColor = good
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-red-600 dark:text-red-400"

  const showAlert =
    alertThreshold != null && currentValue != null && currentValue >= alertThreshold.value

  const hasSpark = sparkData && sparkData.length > 1

  return (
    <div className={cx("relative flex flex-col", s.rootGap, className)}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex min-w-0 flex-1 items-center gap-2">
          <span className={cx("font-medium uppercase leading-tight text-gray-500 dark:text-gray-400 truncate", s.labelSize)}>
            {label}
          </span>
          {source && variant !== "hero" && (
            <span className="shrink-0 -my-0.5">
              <OriginDot source={source} updatedAtISO={updatedAtISO} />
            </span>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {showAlert && alertThreshold && <AlertBadgeV2 threshold={alertThreshold} />}
          {hasSpark && (
            <SparklineMini data={sparkData!} color={sparkColor} width={s.sparkW} height={s.sparkH} />
          )}
        </div>
      </div>

      <div className={cx("flex flex-wrap items-end", variant === "hero" ? "gap-2" : "gap-1.5")}>
        {intensity && <KpiIntensity {...intensity} />}
        <span className={cx("font-semibold leading-none tracking-tight tabular-nums text-gray-900 dark:text-gray-50", s.valueSize)}>
          {value}
        </span>
        {sub && (
          <span className={cx("tabular-nums text-gray-400 dark:text-gray-500 self-end ml-1", s.subSize)}>
            <span aria-hidden="true" className="mr-0.5 text-gray-300 dark:text-gray-600">—</span>
            {sub}
          </span>
        )}
      </div>

      {delta && (
        <p className={cx("tabular-nums text-gray-500 dark:text-gray-400", s.deltaSize)}>
          <span className={cx("inline-flex items-center gap-0.5 font-medium", deltaColor)}>
            <ArrowIcon className={cx(s.arrowSize, "shrink-0")} aria-hidden="true" />
            {Math.abs(delta.value).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}
            {delta.suffix ?? ""}
          </span>
          <span aria-hidden="true" className="mx-1.5 text-gray-300 dark:text-gray-700">·</span>
          <span>{deltaSub}</span>
        </p>
      )}

      {source && variant === "hero" && (
        <div className="mt-0.5">
          <OriginDot source={source} updatedAtISO={updatedAtISO} />
        </div>
      )}
    </div>
  )
}

// ══════════════════════════════════════════════════════════════════════════
// KpiCardV3 — layout side-by-side: conteudo a esquerda, sparkline GRANDE a direita
// Inspirado no reference do Total Revenue ($98,450 + chart com callout +$12,180)
// ══════════════════════════════════════════════════════════════════════════

type V3Variant = "compact" | "default" | "hero"
type V3Layout = "side" | "stacked"

interface KpiCardV3Props {
  label: string
  value: string
  sub?: string
  delta?: KpiDelta
  deltaSub?: string
  intensity?: Omit<IntensityBarsProps, "className">
  sparkData?: number[]
  sparkColor?: string
  alertThreshold?: AlertThreshold
  currentValue?: number
  source?: string
  updatedAtISO?: string | null
  variant?: V3Variant
  /** "side" (default) = chart a direita; "stacked" = chart abaixo do conteudo */
  layout?: V3Layout
  /** Override das dimensoes do sparkline (util em layouts apertados) */
  sparkOverride?: { width: number; height: number }
  /** Mostra callout pill no pico do sparkline (ex.: "+R$ 12,4M") */
  calloutText?: string
  /** Mostra dot no endpoint do sparkline */
  showEndDot?: boolean
  className?: string
}

const V3_SIZES: Record<V3Variant, {
  rootGap: string
  labelSize: string
  valueSize: string
  subSize: string
  deltaSize: string
  arrowSize: string
  sparkW: number
  sparkH: number
}> = {
  compact: {
    rootGap: "gap-0.5",
    labelSize: "text-[10px] tracking-[0.05em]",
    valueSize: "text-[20px] leading-none",
    subSize: "text-[11px]",
    deltaSize: "text-[10px]",
    arrowSize: "size-3",
    sparkW: 100,
    sparkH: 44,
  },
  default: {
    rootGap: "gap-1",
    labelSize: "text-[11px] tracking-[0.05em]",
    valueSize: "text-[26px] leading-none",
    subSize: "text-[12px]",
    deltaSize: "text-[11px]",
    arrowSize: "size-3",
    sparkW: 130,
    sparkH: 56,
  },
  hero: {
    rootGap: "gap-1.5",
    labelSize: "text-sm tracking-[0.04em]",
    valueSize: "text-[36px] leading-none",
    subSize: "text-sm",
    deltaSize: "text-xs",
    arrowSize: "size-4",
    sparkW: 180,
    sparkH: 72,
  },
}

function KpiCardV3({
  label,
  value,
  sub,
  delta,
  deltaSub = "vs mes anterior",
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
  showEndDot = true,
  className,
}: KpiCardV3Props) {
  const s = V3_SIZES[variant]

  const dir = delta?.direction ?? (delta && delta.value >= 0 ? "up" : "down")
  const good = delta?.good ?? dir === "up"
  const ArrowIcon = dir === "up" ? RiArrowUpLine : RiArrowDownLine
  const deltaColor = good
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-red-600 dark:text-red-400"
  const calloutBgColor = good ? "#10B981" : "#DC2626"

  const showAlert =
    alertThreshold != null && currentValue != null && currentValue >= alertThreshold.value

  const hasSpark = sparkData && sparkData.length > 1

  // Sparkline dimensions: usa override se passado, senao usa preset do variant
  const sparkW = sparkOverride?.width ?? s.sparkW
  const sparkH = sparkOverride?.height ?? s.sparkH

  // Content column: label + value + delta (origin foi pra baixo)
  const contentColumn = (
    <div className={cx("flex min-w-0 flex-1 flex-col", s.rootGap)}>
      <div className="flex items-center gap-2">
        <span className={cx("font-medium uppercase leading-tight text-gray-500 dark:text-gray-400 truncate", s.labelSize)}>
          {label}
        </span>
        {showAlert && alertThreshold && <AlertBadgeV2 threshold={alertThreshold} />}
      </div>

      <div className={cx("flex flex-wrap items-end", variant === "hero" ? "gap-2" : "gap-1.5")}>
        {intensity && <KpiIntensity {...intensity} />}
        <span className={cx("font-semibold leading-none tracking-tight tabular-nums text-gray-900 dark:text-gray-50", s.valueSize)}>
          {value}
        </span>
        {sub && (
          <span className={cx("tabular-nums text-gray-400 dark:text-gray-500 self-end ml-1", s.subSize)}>
            <span aria-hidden="true" className="mr-0.5 text-gray-300 dark:text-gray-600">—</span>
            {sub}
          </span>
        )}
      </div>

      {delta && (
        <p className={cx("tabular-nums text-gray-500 dark:text-gray-400", s.deltaSize)}>
          <span className={cx("inline-flex items-center gap-0.5 font-medium", deltaColor)}>
            <ArrowIcon className={cx(s.arrowSize, "shrink-0")} aria-hidden="true" />
            {Math.abs(delta.value).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}
            {delta.suffix ?? ""}
          </span>
          <span aria-hidden="true" className="mx-1.5 text-gray-300 dark:text-gray-700">·</span>
          <span>{deltaSub}</span>
        </p>
      )}
    </div>
  )

  const sparkChart = hasSpark ? (
    <SparklineSide
      data={sparkData!}
      color={sparkColor}
      width={sparkW}
      height={sparkH}
      showEndDot={showEndDot}
      callout={calloutText}
      calloutColor={calloutBgColor}
      className="shrink-0"
    />
  ) : null

  return (
    <div className={cx("flex flex-col gap-1.5", className)}>
      {layout === "side" ? (
        <div className="flex items-center gap-4">
          {contentColumn}
          {sparkChart}
        </div>
      ) : (
        <>
          {contentColumn}
          {sparkChart && <div className="-mx-1">{sparkChart}</div>}
        </>
      )}

      {/* Origin sempre no rodape, alinhado a esquerda */}
      {source && (
        <div className="mt-0.5">
          <OriginDot source={source} updatedAtISO={updatedAtISO} />
        </div>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// KpiStrip wrappers (cada versao tem padding/grid proprios)
// ──────────────────────────────────────────────────────────────────────────

function KpiStripV2({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div
      className={cx(
        "grid grid-cols-2 gap-5 min-[720px]:grid-cols-3 xl:grid-cols-6",
        "rounded border border-gray-200 bg-white px-5 py-3 shadow-xs",
        "dark:border-gray-800 dark:bg-gray-925",
        className,
      )}
    >
      {children}
    </div>
  )
}

function KpiStripV3({ children, className }: { children: React.ReactNode; className?: string }) {
  // v3 = card mais largo (chart lateral). Default de 3 colunas em xl.
  return (
    <div
      className={cx(
        "grid grid-cols-1 gap-4 min-[720px]:grid-cols-2 xl:grid-cols-3",
        "rounded border border-gray-200 bg-white px-5 py-4 shadow-xs",
        "dark:border-gray-800 dark:bg-gray-925",
        className,
      )}
    >
      {children}
    </div>
  )
}

// ──────────────────────────────────────────────────────────────────────────
// MOCK DATA
// ──────────────────────────────────────────────────────────────────────────

const SPARK_PL = [120.1, 121.4, 122.0, 122.8, 123.2, 124.0, 125.8, 124.8, 125.1, 124.9, 125.3, 124.5]
const SPARK_RENT = [98, 99, 101, 100, 103, 105, 104, 107, 108, 110, 109, 112]
const SPARK_INAD = [4.1, 4.3, 4.0, 3.8, 3.9, 4.2, 4.4, 4.5, 4.3, 4.1, 4.0, 3.9]
const SPARK_PDD = [1.8, 1.9, 2.0, 2.1, 2.0, 2.2, 2.3, 2.1, 2.0, 1.9, 1.8, 1.7]
const SPARK_CESS = [22, 25, 28, 24, 26, 30, 32, 28, 26, 24, 22, 28]
const SPARK_REV = [82, 84, 86, 88, 90, 95, 98, 96, 92, 90, 95, 98]

const ISO_NOW = "2026-04-29T10:30:00Z"
const ISO_TODAY = "2026-04-29T08:00:00Z"

// ──────────────────────────────────────────────────────────────────────────
// Sections
// ──────────────────────────────────────────────────────────────────────────

function SectionHeader({
  title,
  subtitle,
  badge,
}: {
  title: string
  subtitle?: string
  badge?: string
}) {
  return (
    <div className="mb-4 flex items-baseline gap-3">
      <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">{title}</h2>
      {badge && (
        <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
          {badge}
        </span>
      )}
      {subtitle && <span className="text-xs text-gray-500 dark:text-gray-400">{subtitle}</span>}
    </div>
  )
}

export default function PreviewKpiCardV2() {
  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <div className="mx-auto max-w-[1280px] px-6 py-10">
        {/* PAGE HEADER */}
        <div className="mb-10 border-b border-gray-200 pb-6 dark:border-gray-800">
          <h1 className="text-2xl font-semibold tracking-tight text-gray-900 dark:text-gray-50">
            KpiCard — iteracao de design
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-gray-600 dark:text-gray-400">
            Mock de alta fidelidade. <strong>v3 e a nova proposta principal</strong> (gráfico
            lateral grande + callout opcional, inspirado no reference Total Revenue). v2
            (sparkline no canto, mais compacta) fica como alternativa para quando o card
            tem largura apertada.
          </p>
        </div>

        {/* ════════════════════════════════════════════════════════════════ */}
        {/* SECTION 0 — proposta principal v3 (matching reference) */}
        {/* ════════════════════════════════════════════════════════════════ */}
        <section className="mb-12">
          <SectionHeader
            title="Proposta v3 — sparkline lateral + callout"
            subtitle="Inspirado no reference: chart visivel, dot no pico, pill com delta"
            badge="NOVA"
          />

          {/* Cards individuais com destaque */}
          <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-925">
              <KpiCardV3
                label="PL DO FUNDO"
                value="R$ 124,5M"
                sub="abr/26"
                delta={{ value: 2.4, suffix: "%" }}
                sparkData={SPARK_PL}
                sparkColor="#10B981"
                source="QiTech"
                updatedAtISO={ISO_NOW}
                calloutText="+R$ 4,2M"
              />
            </div>

            <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-925">
              <KpiCardV3
                label="RENTABILIDADE VS CDI"
                value="112%"
                sub="CDI"
                delta={{ value: 4.0, suffix: "pp" }}
                sparkData={SPARK_RENT}
                sparkColor="#10B981"
                source="QiTech"
                updatedAtISO={ISO_NOW}
                calloutText="+12pp"
              />
            </div>

            <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-925">
              <KpiCardV3
                label="INADIMPLENCIA"
                value="3,9%"
                delta={{ value: -0.2, suffix: "pp" }}
                sparkData={SPARK_INAD}
                sparkColor="#DC2626"
                source="Bitfin"
                updatedAtISO={ISO_TODAY}
                showEndDot={true}
              />
            </div>

            <div className="rounded-lg border border-gray-200 bg-white p-5 shadow-sm dark:border-gray-800 dark:bg-gray-925">
              <KpiCardV3
                label="RECEITA"
                value="R$ 98,4M"
                sub="abr/26"
                delta={{ value: 12.5, suffix: "%" }}
                deltaSub="vs mes anterior"
                sparkData={SPARK_REV}
                sparkColor="#10B981"
                source="QiTech"
                updatedAtISO={ISO_NOW}
                calloutText="+R$ 12,2M"
              />
            </div>
          </div>
        </section>

        {/* ════════════════════════════════════════════════════════════════ */}
        {/* SECTION 1 — Comparacao direta v3 vs Atual */}
        {/* ════════════════════════════════════════════════════════════════ */}
        <section className="mb-12">
          <SectionHeader
            title="1. Comparacao direta — Atual vs v3"
            subtitle="Layout 3 colunas para comportar o chart lateral"
          />

          <div className="space-y-3">
            <div>
              <div className="mb-2 flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-gray-500">
                  Atual (xl:grid-cols-6, sparkline empilhada)
                </span>
              </div>
              <KpiStrip>
                <KpiCard
                  {...FIDC_KPI_META.pl}
                  value="R$ 124,5M"
                  sub="abr/26"
                  delta={{ value: 2.4, suffix: "%" }}
                  sparkData={SPARK_PL}
                  sparkColor="#10B981"
                  source="QiTech"
                  updatedAtISO={ISO_NOW}
                />
                <KpiCard
                  {...FIDC_KPI_META.rentabilidade}
                  value="112%"
                  sub="CDI"
                  delta={{ value: 4.0, suffix: "pp" }}
                  currentValue={112}
                  sparkData={SPARK_RENT}
                  source="QiTech"
                  updatedAtISO={ISO_NOW}
                />
                <KpiCard
                  {...FIDC_KPI_META.inadimplencia}
                  value="3,9%"
                  delta={{ value: -0.2, suffix: "pp" }}
                  currentValue={3.9}
                  sparkData={SPARK_INAD}
                  source="Bitfin"
                  updatedAtISO={ISO_TODAY}
                />
                <KpiCard
                  label="RECEITA"
                  value="R$ 98,4M"
                  sub="abr/26"
                  delta={{ value: 12.5, suffix: "%" }}
                  sparkData={SPARK_REV}
                  sparkColor="#10B981"
                  source="QiTech"
                  updatedAtISO={ISO_NOW}
                />
              </KpiStrip>
            </div>

            <div>
              <div className="mb-2 flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-emerald-700">
                  v3 (xl:grid-cols-3, sparkline lateral) — NOVA
                </span>
              </div>
              <KpiStripV3 className="!grid-cols-1 min-[720px]:!grid-cols-2 xl:!grid-cols-2">
                <KpiCardV3
                  label="PL DO FUNDO"
                  value="R$ 124,5M"
                  sub="abr/26"
                  delta={{ value: 2.4, suffix: "%" }}
                  sparkData={SPARK_PL}
                  sparkColor="#10B981"
                  source="QiTech"
                  updatedAtISO={ISO_NOW}
                  calloutText="+R$ 4,2M"
                />
                <KpiCardV3
                  label="RENTABILIDADE VS CDI"
                  value="112%"
                  sub="CDI"
                  delta={{ value: 4.0, suffix: "pp" }}
                  sparkData={SPARK_RENT}
                  sparkColor="#10B981"
                  source="QiTech"
                  updatedAtISO={ISO_NOW}
                />
                <KpiCardV3
                  label="INADIMPLENCIA"
                  value="3,9%"
                  delta={{ value: -0.2, suffix: "pp" }}
                  sparkData={SPARK_INAD}
                  sparkColor="#DC2626"
                  source="Bitfin"
                  updatedAtISO={ISO_TODAY}
                />
                <KpiCardV3
                  label="RECEITA"
                  value="R$ 98,4M"
                  sub="abr/26"
                  delta={{ value: 12.5, suffix: "%" }}
                  sparkData={SPARK_REV}
                  sparkColor="#10B981"
                  source="QiTech"
                  updatedAtISO={ISO_NOW}
                  calloutText="+R$ 12,2M"
                />
              </KpiStripV3>
            </div>
          </div>
        </section>

        {/* ════════════════════════════════════════════════════════════════ */}
        {/* SECTION 2 — 3 Variantes do v3 */}
        {/* ════════════════════════════════════════════════════════════════ */}
        <section className="mb-12">
          <SectionHeader title="2. v3 nas 3 variantes" subtitle="compact / default / hero" />

          <div className="grid grid-cols-1 gap-6">
            {(["compact", "default", "hero"] as const).map((v) => (
              <div key={v}>
                <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                  variant=&quot;{v}&quot;
                </div>
                <div className="rounded-lg border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-925">
                  <KpiCardV3
                    label="RECEITA TOTAL"
                    value="R$ 98,4M"
                    sub="abr/26"
                    delta={{ value: 12.5, suffix: "%" }}
                    sparkData={SPARK_REV}
                    sparkColor="#10B981"
                    source="QiTech"
                    updatedAtISO={ISO_NOW}
                    calloutText="+R$ 12,2M"
                    variant={v}
                  />
                </div>
              </div>
            ))}
          </div>
        </section>

        {/* ════════════════════════════════════════════════════════════════ */}
        {/* SECTION 3 — Combinacoes do v3 (com / sem callout / endDot) */}
        {/* ════════════════════════════════════════════════════════════════ */}
        <section className="mb-12">
          <SectionHeader
            title="3. v3 — combinacoes"
            subtitle="Com callout, sem callout, com endDot, sem chart"
          />

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="rounded-lg border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-925">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                Com callout (delta no pico)
              </div>
              <KpiCardV3
                label="PL DO FUNDO"
                value="R$ 124,5M"
                delta={{ value: 2.4, suffix: "%" }}
                sparkData={SPARK_PL}
                sparkColor="#10B981"
                source="QiTech"
                updatedAtISO={ISO_NOW}
                calloutText="+R$ 4,2M"
              />
            </div>

            <div className="rounded-lg border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-925">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                Sem callout, com endpoint dot
              </div>
              <KpiCardV3
                label="PL DO FUNDO"
                value="R$ 124,5M"
                delta={{ value: 2.4, suffix: "%" }}
                sparkData={SPARK_PL}
                sparkColor="#10B981"
                source="QiTech"
                updatedAtISO={ISO_NOW}
                showEndDot={true}
              />
            </div>

            <div className="rounded-lg border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-925">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                Sem callout, sem dot (mais limpo)
              </div>
              <KpiCardV3
                label="PL DO FUNDO"
                value="R$ 124,5M"
                delta={{ value: 2.4, suffix: "%" }}
                sparkData={SPARK_PL}
                sparkColor="#10B981"
                source="QiTech"
                updatedAtISO={ISO_NOW}
                showEndDot={false}
              />
            </div>

            <div className="rounded-lg border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-925">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                Sem chart (texto puro)
              </div>
              <KpiCardV3
                label="ATIVOS TOTAIS"
                value="R$ 245M"
                delta={{ value: 1.8, suffix: "%" }}
                source="QiTech"
                updatedAtISO={ISO_NOW}
              />
            </div>

            <div className="rounded-lg border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-925">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                Delta negativo (chart vermelho)
              </div>
              <KpiCardV3
                label="INADIMPLENCIA"
                value="3,9%"
                delta={{ value: -0.2, suffix: "pp" }}
                sparkData={SPARK_INAD}
                sparkColor="#DC2626"
                source="Bitfin"
                updatedAtISO={ISO_TODAY}
                calloutText="-0,5pp"
              />
            </div>

            <div className="rounded-lg border border-gray-200 bg-white p-5 dark:border-gray-800 dark:bg-gray-925">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                Com alert threshold + intensity
              </div>
              <KpiCardV3
                {...FIDC_KPI_META.cessoesPendentes}
                value="42"
                delta={{ value: 35, suffix: "" }}
                currentValue={42}
                sparkData={SPARK_CESS}
                source="QiTech"
                updatedAtISO={ISO_NOW}
                calloutText="+12"
              />
            </div>
          </div>
        </section>

        {/* ════════════════════════════════════════════════════════════════ */}
        {/* SECTION 4 — densidade comparativa: 6 KPIs (caso real BI) */}
        {/* ════════════════════════════════════════════════════════════════ */}
        <section className="mb-12">
          <SectionHeader
            title="4. Densidade — 6 KPIs (caso real DashboardBiPadrao)"
            subtitle="Trade-off: v3 e mais expressivo mas pede 3 colunas em vez de 6"
            badge="Trade-off"
          />

          <div className="space-y-4">
            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">
                Atual (6 colunas)
              </div>
              <KpiStrip>
                <KpiCard label="PL" value="R$ 124,5M" delta={{ value: 2.4, suffix: "%" }} sparkData={SPARK_PL} sparkColor="#10B981" source="QiTech" updatedAtISO={ISO_NOW} />
                <KpiCard label="RENTAB." value="112%" sub="CDI" delta={{ value: 4.0, suffix: "pp" }} sparkData={SPARK_RENT} source="QiTech" updatedAtISO={ISO_NOW} />
                <KpiCard label="INAD." value="3,9%" delta={{ value: -0.2, suffix: "pp" }} sparkData={SPARK_INAD} sparkColor="#DC2626" source="Bitfin" updatedAtISO={ISO_TODAY} />
                <KpiCard label="PDD" value="1,7%" delta={{ value: -0.1, suffix: "pp" }} sparkData={SPARK_PDD} source="Bitfin" updatedAtISO={ISO_TODAY} />
                <KpiCard label="CESSOES" value="28" delta={{ value: 12, suffix: "" }} sparkData={SPARK_CESS} source="QiTech" updatedAtISO={ISO_NOW} />
                <KpiCard label="LIQUIDEZ" value="98%" delta={{ value: 0.5, suffix: "pp" }} sparkData={SPARK_RENT} source="QiTech" updatedAtISO={ISO_NOW} />
              </KpiStrip>
            </div>

            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-emerald-700">
                v3 (3 colunas — mais respiro, chart visivel)
              </div>
              <KpiStripV3>
                <KpiCardV3 label="PL" value="R$ 124,5M" delta={{ value: 2.4, suffix: "%" }} sparkData={SPARK_PL} sparkColor="#10B981" source="QiTech" updatedAtISO={ISO_NOW} variant="compact" />
                <KpiCardV3 label="RENTAB." value="112%" sub="CDI" delta={{ value: 4.0, suffix: "pp" }} sparkData={SPARK_RENT} sparkColor="#10B981" source="QiTech" updatedAtISO={ISO_NOW} variant="compact" />
                <KpiCardV3 label="INAD." value="3,9%" delta={{ value: -0.2, suffix: "pp" }} sparkData={SPARK_INAD} sparkColor="#DC2626" source="Bitfin" updatedAtISO={ISO_TODAY} variant="compact" />
                <KpiCardV3 label="PDD" value="1,7%" delta={{ value: -0.1, suffix: "pp" }} sparkData={SPARK_PDD} sparkColor="#DC2626" source="Bitfin" updatedAtISO={ISO_TODAY} variant="compact" />
                <KpiCardV3 label="CESSOES" value="28" delta={{ value: 12, suffix: "" }} sparkData={SPARK_CESS} sparkColor="#10B981" source="QiTech" updatedAtISO={ISO_NOW} variant="compact" />
                <KpiCardV3 label="LIQUIDEZ" value="98%" delta={{ value: 0.5, suffix: "pp" }} sparkData={SPARK_RENT} sparkColor="#10B981" source="QiTech" updatedAtISO={ISO_NOW} variant="compact" />
              </KpiStripV3>
            </div>

            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-blue-700">
                v2 (6 colunas, sparkline no canto) — alternativa quando densidade e prioridade
              </div>
              <KpiStripV2>
                <KpiCardV2 label="PL" value="R$ 124,5M" delta={{ value: 2.4, suffix: "%" }} sparkData={SPARK_PL} sparkColor="#10B981" source="QiTech" updatedAtISO={ISO_NOW} />
                <KpiCardV2 label="RENTAB." value="112%" sub="CDI" delta={{ value: 4.0, suffix: "pp" }} sparkData={SPARK_RENT} source="QiTech" updatedAtISO={ISO_NOW} />
                <KpiCardV2 label="INAD." value="3,9%" delta={{ value: -0.2, suffix: "pp" }} sparkData={SPARK_INAD} sparkColor="#DC2626" source="Bitfin" updatedAtISO={ISO_TODAY} />
                <KpiCardV2 label="PDD" value="1,7%" delta={{ value: -0.1, suffix: "pp" }} sparkData={SPARK_PDD} source="Bitfin" updatedAtISO={ISO_TODAY} />
                <KpiCardV2 label="CESSOES" value="28" delta={{ value: 12, suffix: "" }} sparkData={SPARK_CESS} source="QiTech" updatedAtISO={ISO_NOW} />
                <KpiCardV2 label="LIQUIDEZ" value="98%" delta={{ value: 0.5, suffix: "pp" }} sparkData={SPARK_RENT} source="QiTech" updatedAtISO={ISO_NOW} />
              </KpiStripV2>
            </div>
          </div>
        </section>

        {/* ════════════════════════════════════════════════════════════════ */}
        {/* SECTION 6 — v3 forcada em densidade 6-col */}
        {/* ════════════════════════════════════════════════════════════════ */}
        <section className="mb-12">
          <SectionHeader
            title="6. v3 em densidade 6 colunas — 3 estrategias"
            subtitle="Card largura ~190px (mesma da grid atual). Como o v3 se comporta?"
            badge="Pedido"
          />

          <div className="space-y-6">
            {/* 6.1 — chart lateral pequeno */}
            <div>
              <div className="mb-2 flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-emerald-700">
                  6.1 — chart lateral compacto (60×32px)
                </span>
                <span className="text-[10px] text-gray-400">
                  Mantem layout side-by-side, chart vira mini decoracao
                </span>
              </div>
              <div className="grid grid-cols-2 gap-5 min-[720px]:grid-cols-3 xl:grid-cols-6 rounded border border-gray-200 bg-white px-5 py-4 shadow-xs dark:border-gray-800 dark:bg-gray-925">
                <KpiCardV3
                  label="PL"
                  value="R$ 124,5M"
                  delta={{ value: 2.4, suffix: "%" }}
                  sparkData={SPARK_PL}
                  sparkColor="#10B981"
                  source="QiTech"
                  updatedAtISO={ISO_NOW}
                  variant="compact"
                  sparkOverride={{ width: 60, height: 32 }}
                  showEndDot={false}
                />
                <KpiCardV3
                  label="RENTAB."
                  value="112%"
                  sub="CDI"
                  delta={{ value: 4.0, suffix: "pp" }}
                  sparkData={SPARK_RENT}
                  sparkColor="#10B981"
                  source="QiTech"
                  updatedAtISO={ISO_NOW}
                  variant="compact"
                  sparkOverride={{ width: 60, height: 32 }}
                  showEndDot={false}
                />
                <KpiCardV3
                  label="INAD."
                  value="3,9%"
                  delta={{ value: -0.2, suffix: "pp" }}
                  sparkData={SPARK_INAD}
                  sparkColor="#DC2626"
                  source="Bitfin"
                  updatedAtISO={ISO_TODAY}
                  variant="compact"
                  sparkOverride={{ width: 60, height: 32 }}
                  showEndDot={false}
                />
                <KpiCardV3
                  label="PDD"
                  value="1,7%"
                  delta={{ value: -0.1, suffix: "pp" }}
                  sparkData={SPARK_PDD}
                  sparkColor="#DC2626"
                  source="Bitfin"
                  updatedAtISO={ISO_TODAY}
                  variant="compact"
                  sparkOverride={{ width: 60, height: 32 }}
                  showEndDot={false}
                />
                <KpiCardV3
                  label="CESSOES"
                  value="28"
                  delta={{ value: 12, suffix: "" }}
                  sparkData={SPARK_CESS}
                  sparkColor="#10B981"
                  source="QiTech"
                  updatedAtISO={ISO_NOW}
                  variant="compact"
                  sparkOverride={{ width: 60, height: 32 }}
                  showEndDot={false}
                />
                <KpiCardV3
                  label="LIQUIDEZ"
                  value="98%"
                  delta={{ value: 0.5, suffix: "pp" }}
                  sparkData={SPARK_RENT}
                  sparkColor="#10B981"
                  source="QiTech"
                  updatedAtISO={ISO_NOW}
                  variant="compact"
                  sparkOverride={{ width: 60, height: 32 }}
                  showEndDot={false}
                />
              </div>
            </div>

            {/* 6.2 — chart empilhado abaixo */}
            <div>
              <div className="mb-2 flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-emerald-700">
                  6.2 — chart empilhado abaixo (full-width × 36px) com callout
                </span>
                <span className="text-[10px] text-gray-400">
                  layout=&quot;stacked&quot; · chart preserva visibilidade horizontal
                </span>
              </div>
              <div className="grid grid-cols-2 gap-5 min-[720px]:grid-cols-3 xl:grid-cols-6 rounded border border-gray-200 bg-white px-5 py-4 shadow-xs dark:border-gray-800 dark:bg-gray-925">
                <KpiCardV3
                  label="PL"
                  value="R$ 124,5M"
                  delta={{ value: 2.4, suffix: "%" }}
                  sparkData={SPARK_PL}
                  sparkColor="#10B981"
                  source="QiTech"
                  updatedAtISO={ISO_NOW}
                  variant="compact"
                  layout="stacked"
                  sparkOverride={{ width: 150, height: 36 }}
                  calloutText="+R$ 4,2M"
                />
                <KpiCardV3
                  label="RENTAB."
                  value="112%"
                  sub="CDI"
                  delta={{ value: 4.0, suffix: "pp" }}
                  sparkData={SPARK_RENT}
                  sparkColor="#10B981"
                  source="QiTech"
                  updatedAtISO={ISO_NOW}
                  variant="compact"
                  layout="stacked"
                  sparkOverride={{ width: 150, height: 36 }}
                />
                <KpiCardV3
                  label="INAD."
                  value="3,9%"
                  delta={{ value: -0.2, suffix: "pp" }}
                  sparkData={SPARK_INAD}
                  sparkColor="#DC2626"
                  source="Bitfin"
                  updatedAtISO={ISO_TODAY}
                  variant="compact"
                  layout="stacked"
                  sparkOverride={{ width: 150, height: 36 }}
                />
                <KpiCardV3
                  label="PDD"
                  value="1,7%"
                  delta={{ value: -0.1, suffix: "pp" }}
                  sparkData={SPARK_PDD}
                  sparkColor="#DC2626"
                  source="Bitfin"
                  updatedAtISO={ISO_TODAY}
                  variant="compact"
                  layout="stacked"
                  sparkOverride={{ width: 150, height: 36 }}
                />
                <KpiCardV3
                  label="CESSOES"
                  value="28"
                  delta={{ value: 12, suffix: "" }}
                  sparkData={SPARK_CESS}
                  sparkColor="#10B981"
                  source="QiTech"
                  updatedAtISO={ISO_NOW}
                  variant="compact"
                  layout="stacked"
                  sparkOverride={{ width: 150, height: 36 }}
                />
                <KpiCardV3
                  label="LIQUIDEZ"
                  value="98%"
                  delta={{ value: 0.5, suffix: "pp" }}
                  sparkData={SPARK_RENT}
                  sparkColor="#10B981"
                  source="QiTech"
                  updatedAtISO={ISO_NOW}
                  variant="compact"
                  layout="stacked"
                  sparkOverride={{ width: 150, height: 36 }}
                />
              </div>
            </div>

            {/* 6.3 — sem chart (puro texto) */}
            <div>
              <div className="mb-2 flex items-center gap-2">
                <span className="text-xs font-semibold uppercase tracking-wider text-emerald-700">
                  6.3 — sem chart (so texto + origin)
                </span>
                <span className="text-[10px] text-gray-400">
                  Mais limpo de todos · perde a tendencia visual
                </span>
              </div>
              <div className="grid grid-cols-2 gap-5 min-[720px]:grid-cols-3 xl:grid-cols-6 rounded border border-gray-200 bg-white px-5 py-4 shadow-xs dark:border-gray-800 dark:bg-gray-925">
                <KpiCardV3 label="PL" value="R$ 124,5M" delta={{ value: 2.4, suffix: "%" }} source="QiTech" updatedAtISO={ISO_NOW} variant="compact" />
                <KpiCardV3 label="RENTAB." value="112%" sub="CDI" delta={{ value: 4.0, suffix: "pp" }} source="QiTech" updatedAtISO={ISO_NOW} variant="compact" />
                <KpiCardV3 label="INAD." value="3,9%" delta={{ value: -0.2, suffix: "pp" }} source="Bitfin" updatedAtISO={ISO_TODAY} variant="compact" />
                <KpiCardV3 label="PDD" value="1,7%" delta={{ value: -0.1, suffix: "pp" }} source="Bitfin" updatedAtISO={ISO_TODAY} variant="compact" />
                <KpiCardV3 label="CESSOES" value="28" delta={{ value: 12, suffix: "" }} source="QiTech" updatedAtISO={ISO_NOW} variant="compact" />
                <KpiCardV3 label="LIQUIDEZ" value="98%" delta={{ value: 0.5, suffix: "pp" }} source="QiTech" updatedAtISO={ISO_NOW} variant="compact" />
              </div>
            </div>
          </div>
        </section>

        {/* ════════════════════════════════════════════════════════════════ */}
        {/* SECTION 7 — v3 em densidade 4 colunas (sweet spot) */}
        {/* ════════════════════════════════════════════════════════════════ */}
        <section className="mb-12">
          <SectionHeader
            title="7. v3 em densidade 4 colunas — chart lateral compacto"
            subtitle="Card largura ~295px · variant=compact · chart ~100×44px"
            badge="Sweet spot"
          />

          <div className="space-y-6">
            {/* 7.1 — 4 cards principais com callout */}
            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-emerald-700">
                4 KPIs principais (com callout)
              </div>
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4 rounded border border-gray-200 bg-white px-5 py-4 shadow-xs dark:border-gray-800 dark:bg-gray-925">
                <KpiCardV3
                  label="PL DO FUNDO"
                  value="R$ 124,5M"
                  sub="abr/26"
                  delta={{ value: 2.4, suffix: "%" }}
                  sparkData={SPARK_PL}
                  sparkColor="#10B981"
                  source="QiTech"
                  updatedAtISO={ISO_NOW}
                  variant="compact"
                  calloutText="+R$ 4,2M"
                />
                <KpiCardV3
                  label="RENTABILIDADE"
                  value="112%"
                  sub="CDI"
                  delta={{ value: 4.0, suffix: "pp" }}
                  sparkData={SPARK_RENT}
                  sparkColor="#10B981"
                  source="QiTech"
                  updatedAtISO={ISO_NOW}
                  variant="compact"
                  calloutText="+12pp"
                />
                <KpiCardV3
                  label="INADIMPLENCIA"
                  value="3,9%"
                  delta={{ value: -0.2, suffix: "pp" }}
                  sparkData={SPARK_INAD}
                  sparkColor="#DC2626"
                  source="Bitfin"
                  updatedAtISO={ISO_TODAY}
                  variant="compact"
                />
                <KpiCardV3
                  label="RECEITA"
                  value="R$ 98,4M"
                  sub="abr/26"
                  delta={{ value: 12.5, suffix: "%" }}
                  sparkData={SPARK_REV}
                  sparkColor="#10B981"
                  source="QiTech"
                  updatedAtISO={ISO_NOW}
                  variant="compact"
                  calloutText="+R$ 12,2M"
                />
              </div>
            </div>

            {/* 7.2 — 4 cards sem callout (visual mais limpo) */}
            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-emerald-700">
                Variante sem callout — só endpoint dot (mais limpo)
              </div>
              <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4 rounded border border-gray-200 bg-white px-5 py-4 shadow-xs dark:border-gray-800 dark:bg-gray-925">
                <KpiCardV3
                  label="PL DO FUNDO"
                  value="R$ 124,5M"
                  sub="abr/26"
                  delta={{ value: 2.4, suffix: "%" }}
                  sparkData={SPARK_PL}
                  sparkColor="#10B981"
                  source="QiTech"
                  updatedAtISO={ISO_NOW}
                  variant="compact"
                  showEndDot={true}
                />
                <KpiCardV3
                  label="RENTABILIDADE"
                  value="112%"
                  sub="CDI"
                  delta={{ value: 4.0, suffix: "pp" }}
                  sparkData={SPARK_RENT}
                  sparkColor="#10B981"
                  source="QiTech"
                  updatedAtISO={ISO_NOW}
                  variant="compact"
                  showEndDot={true}
                />
                <KpiCardV3
                  label="INADIMPLENCIA"
                  value="3,9%"
                  delta={{ value: -0.2, suffix: "pp" }}
                  sparkData={SPARK_INAD}
                  sparkColor="#DC2626"
                  source="Bitfin"
                  updatedAtISO={ISO_TODAY}
                  variant="compact"
                  showEndDot={true}
                />
                <KpiCardV3
                  label="RECEITA"
                  value="R$ 98,4M"
                  sub="abr/26"
                  delta={{ value: 12.5, suffix: "%" }}
                  sparkData={SPARK_REV}
                  sparkColor="#10B981"
                  source="QiTech"
                  updatedAtISO={ISO_NOW}
                  variant="compact"
                  showEndDot={true}
                />
              </div>
            </div>

            {/* 7.3 — Comparacao com 4 KPIs lado-a-lado: atual vs v3 4-col */}
            <div>
              <div className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500">
                Comparacao direta — Atual (6 col) vs v3 4-col (mesmo conjunto de 4 KPIs)
              </div>
              <div className="space-y-3">
                <div>
                  <div className="mb-1 text-[10px] uppercase tracking-wider text-gray-400">
                    Atual em 4 colunas (referencia)
                  </div>
                  <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4 rounded border border-gray-200 bg-white px-5 py-[18px] shadow-xs dark:border-gray-800 dark:bg-gray-925">
                    <KpiCard label="PL DO FUNDO" value="R$ 124,5M" sub="abr/26" delta={{ value: 2.4, suffix: "%" }} sparkData={SPARK_PL} sparkColor="#10B981" source="QiTech" updatedAtISO={ISO_NOW} />
                    <KpiCard label="RENTABILIDADE" value="112%" sub="CDI" delta={{ value: 4.0, suffix: "pp" }} sparkData={SPARK_RENT} source="QiTech" updatedAtISO={ISO_NOW} />
                    <KpiCard label="INADIMPLENCIA" value="3,9%" delta={{ value: -0.2, suffix: "pp" }} sparkData={SPARK_INAD} sparkColor="#DC2626" source="Bitfin" updatedAtISO={ISO_TODAY} />
                    <KpiCard label="RECEITA" value="R$ 98,4M" sub="abr/26" delta={{ value: 12.5, suffix: "%" }} sparkData={SPARK_REV} sparkColor="#10B981" source="QiTech" updatedAtISO={ISO_NOW} />
                  </div>
                </div>
                <div>
                  <div className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-emerald-700">
                    v3 compact em 4 colunas (proposta)
                  </div>
                  <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-4 rounded border border-gray-200 bg-white px-5 py-4 shadow-xs dark:border-gray-800 dark:bg-gray-925">
                    <KpiCardV3 label="PL DO FUNDO" value="R$ 124,5M" sub="abr/26" delta={{ value: 2.4, suffix: "%" }} sparkData={SPARK_PL} sparkColor="#10B981" source="QiTech" updatedAtISO={ISO_NOW} variant="compact" calloutText="+R$ 4,2M" />
                    <KpiCardV3 label="RENTABILIDADE" value="112%" sub="CDI" delta={{ value: 4.0, suffix: "pp" }} sparkData={SPARK_RENT} sparkColor="#10B981" source="QiTech" updatedAtISO={ISO_NOW} variant="compact" />
                    <KpiCardV3 label="INADIMPLENCIA" value="3,9%" delta={{ value: -0.2, suffix: "pp" }} sparkData={SPARK_INAD} sparkColor="#DC2626" source="Bitfin" updatedAtISO={ISO_TODAY} variant="compact" />
                    <KpiCardV3 label="RECEITA" value="R$ 98,4M" sub="abr/26" delta={{ value: 12.5, suffix: "%" }} sparkData={SPARK_REV} sparkColor="#10B981" source="QiTech" updatedAtISO={ISO_NOW} variant="compact" calloutText="+R$ 12,2M" />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* ════════════════════════════════════════════════════════════════ */}
        {/* SECTION 5 — resumo */}
        {/* ════════════════════════════════════════════════════════════════ */}
        <section className="mb-12">
          <SectionHeader title="5. Resumo das mudancas" />

          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="rounded-lg border border-gray-200 bg-gray-50/50 p-4 dark:border-gray-800 dark:bg-gray-900/40">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-gray-500">
                Atual
              </div>
              <h3 className="mb-2 text-sm font-semibold text-gray-900 dark:text-gray-50">
                Sparkline empilhada
              </h3>
              <ul className="space-y-1 text-xs text-gray-700 dark:text-gray-300">
                <li>· Chart full-width abaixo do delta</li>
                <li>· 5 linhas verticais</li>
                <li>· ~120px altura</li>
                <li>· 6 colunas confortaveis</li>
                <li>· Chart pequeno e quase invisivel</li>
              </ul>
            </div>

            <div className="rounded-lg border-2 border-emerald-300 bg-emerald-50/30 p-4 dark:border-emerald-800 dark:bg-emerald-950/30">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-emerald-700">
                v3 — proposta principal
              </div>
              <h3 className="mb-2 text-sm font-semibold text-gray-900 dark:text-gray-50">
                Sparkline lateral grande
              </h3>
              <ul className="space-y-1 text-xs text-gray-700 dark:text-gray-300">
                <li>· Chart 130x56px ao lado direito</li>
                <li>· Layout horizontal: texto + chart</li>
                <li>· Callout opcional com delta no pico</li>
                <li>· Endpoint dot opcional</li>
                <li>· 3 colunas (cards mais largos)</li>
                <li>· Chart bonito e informativo</li>
              </ul>
            </div>

            <div className="rounded-lg border border-blue-200 bg-blue-50/30 p-4 dark:border-blue-900 dark:bg-blue-950/20">
              <div className="mb-2 text-[10px] font-semibold uppercase tracking-wider text-blue-700">
                v2 — alternativa
              </div>
              <h3 className="mb-2 text-sm font-semibold text-gray-900 dark:text-gray-50">
                Sparkline no canto
              </h3>
              <ul className="space-y-1 text-xs text-gray-700 dark:text-gray-300">
                <li>· Chart 48x20px no canto superior-direito</li>
                <li>· 3 linhas verticais</li>
                <li>· ~70px altura (mais compacto)</li>
                <li>· 6 colunas mantidas</li>
                <li>· Chart e so um indicador discreto</li>
                <li>· Bom quando a densidade vence o destaque</li>
              </ul>
            </div>
          </div>
        </section>
      </div>
    </div>
  )
}
