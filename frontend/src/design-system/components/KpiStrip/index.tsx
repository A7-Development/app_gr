// src/design-system/components/KpiStrip/index.tsx
//
// KpiCard canonico do projeto — Strata DS, iteracao 2026-05-05.
//
// ── Diagramacao canonica (3 linhas) ───────────────────────────────────────
//   L1: label uppercase pequeno + OriginDot (opcional) + AlertBadge (opcional)
//   L2: value sozinho — grande, bold, tabular-nums, leading-none
//   L3: sub + delta (↑ X%) + deltaSub — inline na mesma linha, items-baseline.
//       Ex.: "R$ 3,7 mi no mês  ↑ 4,2%  MTD"
//
// Esta e a forma DEFAULT do KpiCard. O sub fica na linha do delta (nao
// junto do value como no handoff original). Diagramacao escolhida por dar
// mais peso editorial ao value e leitura coesa do "sub + comparacao" como
// uma narrativa unica do mes corrente.
//
// ── Variants de tamanho ───────────────────────────────────────────────────
//   compact · value 18px · gap-1   (Metricas Complementares)
//   default · value 20px · gap-1.5 (KPIs Principais — strip de 5)
//   hero    · value 30px · gap-2   (KPIs unicos, telas executivas)
//
// ── Sparkline (opcional) ──────────────────────────────────────────────────
// Default = sem chart. Quando o consumidor passa `sparkData`, o sparkline
// aparece a direita (`layout="side"`, default) ou abaixo (`layout="stacked"`).
// Sem `sparkData` o card e puramente textual.
//
// ── Features adicionais ──────────────────────────────────────────────────
//   - intensity bars (KpiIntensity) opcionais ao lado do value
//   - alert badge (warn / critical) na L1 quando threshold cruzado
//   - callout pill no pico do sparkline (so com sparkData)
//   - endpoint dot opcional (so com sparkData)
//   - provenance canonica (§14.1) ou source legacy via OriginDot
//
// ── Divergencia do handoff Strata original ───────────────────────────────
// O handoff Strata v1 tinha `value+sub` na mesma linha e sparkline lateral
// como parte do default. Esta versao move `sub` para baixo (junto do
// delta) e torna o sparkline opcional. Ver feedback_kpicard_variants.md
// para historico da decisao.
//
// ── Compat ────────────────────────────────────────────────────────────────
// A `Sparkline` exportada (full-width, 80x28) e mantida porque
// `DataTable/cells/SparklineCell` depende dela. O sparkline interno do
// KpiCard (side-mounted, com callout) e o `KpiSparkline`.

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
import type { Provenance } from "@/design-system/types/provenance"

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
  /**
   * Proveniencia canonica (preferida — CLAUDE.md §14.1).
   * Renderiza OriginDot inline ao lado do label com cor pelo trust level.
   * Mock = nao passar (dot some).
   */
  provenance?: Provenance | null
  /** Fonte do dado (LEGACY — use `provenance` em vez disso). */
  source?: string
  /** Timestamp ISO da ultima atualizacao (LEGACY — use `provenance` em vez disso). */
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
  provenance,
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
        {/* OriginDot inline ao lado do label — metadata visual sem competir
            com o sparkline (ver wrapper para historico do design).
            Prefere `provenance` canonico (§14.1); cai em `source` legacy
            quando provenance nao foi passada. Mock (nada passado) = nao renderiza. */}
        {provenance ? (
          <OriginDot provenance={provenance} variant="dot" />
        ) : source ? (
          <OriginDot source={source} updatedAtISO={updatedAtISO} variant="dot" />
        ) : null}
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
      </div>

      {(sub || delta) && (
        <p
          className={cx(
            "flex flex-wrap items-baseline gap-x-1.5 tabular-nums text-gray-500 dark:text-gray-400",
            s.subSize,
          )}
        >
          {sub && (
            <span className="text-gray-400 dark:text-gray-500">{sub}</span>
          )}
          {delta && (
            <>
              <span
                className={cx(
                  "whitespace-nowrap font-medium",
                  deltaColor,
                )}
              >
                {/* Icone como inline (nao inline-flex) para preservar a
                    baseline do texto no <p items-baseline> parent. O
                    vertical-align em em-units acompanha a escala da
                    tipografia (compact/default/hero). */}
                <ArrowIcon
                  className={cx(
                    s.arrowSize,
                    "mr-0.5 inline shrink-0 align-[-0.125em]",
                  )}
                  aria-hidden="true"
                />
                {Math.abs(delta.value).toLocaleString("pt-BR", {
                  maximumFractionDigits: 2,
                })}
                {delta.suffix ?? ""}
              </span>
              <span>{deltaSub}</span>
            </>
          )}
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
    // OriginDot vai INLINE no header do contentColumn (ao lado do label e
    // de eventual AlertBadge), nao no canto superior direito do card.
    // Motivacao: em layout=side com sparkline de tendencia, o canto direito
    // colide com o endpoint da linha — o dot acaba lendo como ponto de dados
    // do grafico, nao metadado. Inline com label associa o dot ao label
    // semanticamente (ambos sao "cabecalho" do card) e fica longe do chart.
    // Ganho de altura preservado: dot ocupa o slot vertical do label, zero
    // altura extra (~18-20px de economia vs modo inline legado).
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
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════
// KpiStrip — container full-width, KPIs com largura natural
// ════════════════════════════════════════════════════════════════════════
//
// Densidade canonica = 5 KPIs em xl (densidade natural de dashboard FIDC
// operacional: PL, Subordinacao, Rentabilidade, Concentracao, Resgates).
// Para dashboards executivos / "hero feel" usa cols={4}.
//
// Layout em xl: `flex justify-between` — card encosta nas bordas do
// container pai (sem max-w / mx-auto), cada KpiCard mantem largura
// natural (label + value + sparkline = ~conteudo intrinseco), e o
// espaco entre os cards distribui uniformemente. Telas <xl caem para
// grid (1 col mobile, 2 cols sm).
//
// Prop `cols` continua existindo como anotacao semantica (5 = canonico,
// 4 = hero feel, 6 = sugere variant=compact). Em xl ele nao dita largura
// — quem dita e o conteudo de cada KpiCard. Em telas pequenas continua
// caindo em grid 1/2 colunas.

export type KpiStripCols = 3 | 4 | 5 | 6

export function KpiStrip({
  children,
  className,
}: {
  children: React.ReactNode
  /**
   * Anotacao semantica do numero de KPIs (default 5 = canonico).
   * Em xl o layout e flex justify-between independente do valor.
   */
  cols?: KpiStripCols
  className?: string
}) {
  return (
    <div
      className={cx(
        // <xl: grid responsivo (1 col mobile, 2 cols sm+)
        "grid grid-cols-1 gap-5 sm:grid-cols-2",
        // xl+: flex full-width, KPIs com largura natural, espaco uniforme entre
        "xl:flex xl:flex-nowrap xl:items-start xl:justify-between xl:gap-4",
        "w-full",
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
