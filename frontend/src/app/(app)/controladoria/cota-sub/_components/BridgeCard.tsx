"use client"

/**
 * BridgeCard — hero do split. Waterfall horizontal por categoria de
 * variacao, do PL Cota Sub D-1 ao PL Cota Sub D0.
 *
 *   [PL D-1] [+ Fluxo cotista] [+ Carteira] [+ Eventos contabeis] [+ MtM] [PL D0]
 *
 * Portado de `analise-cota/project/shared.jsx::CategoryBridge` (handoff
 * Claude Design 2026-05-14). Cores das categorias casam com a paleta
 * de `AnaliseVariacaoCard.tsx` (fluxo=emerald, carteira=blue,
 * eventos=violet, mtm=amber).
 *
 * Categorias sem dado real chegam com delta=0 — bar fica minuscula e
 * label exibe "Em construcao". "Outros (nao classificado)" aparece como
 * coluna extra quando `indeterminado_brl` esta fora de tolerancia.
 */

import * as React from "react"

import { cx } from "@/lib/utils"

export type BridgeCategoryId =
  | "fluxo_caixa"
  | "movimento_carteira"
  | "pdd"
  | "ajustes_contabeis"
  | "marcacao_mercado"
  | "remuneracao_sr_mez"
  | "outros"

export type BridgeDriver = {
  id:          BridgeCategoryId
  label:       string
  /** Label no eixo X (linha 1). Manter cognato com o titulo do card a direita. */
  shortLabel:  string
  /** Linha 2 opcional. Use quando o nome do card tem 2 palavras e nao cabe em 1 linha. */
  shortLabel2?: string
  /** Delta R$ na categoria. 0 = sem dado / categoria neutra. */
  delta:       number
  /** Quando true, a coluna entra cinza pontilhada (categoria sem dado real). */
  placeholder?: boolean
}

// Waterfall usa cor semantica (verde positivo / vermelho negativo) para as
// barras de delta. A identidade por categoria (violet=eventos, emerald=fluxo,
// blue=carteira, amber=mtm) continua viva no DriversCard a direita (avatar +
// mini bar) — separamos "cor de impacto" (waterfall) de "cor de identidade"
// (drivers list). Decisao 2026-05-14 (Ricardo): waterfall fica mais legivel
// com sinais coerentes, identidade nao se perde porque os drivers do lado
// continuam coloridos.
const COLOR_POSITIVE = "#10B981"  // emerald-500
const COLOR_NEGATIVE = "#EF4444"  // red-500

const GRAY_TOTAL_BAR    = "#F3F4F6"  // gray-100
const GRAY_TOTAL_STROKE = "#9CA3AF"  // gray-400
const GRAY_GRID         = "#EAECEF"  // ~g150
const GRAY_AXIS         = "#6B7280"  // gray-500
const GRAY_PLACEHOLDER  = "#D1D5DB"  // gray-300

const fmtBRLk = (v: number) => {
  const abs = Math.abs(v)
  const sign = v < 0 ? "−" : v > 0 ? "+" : ""
  if (abs >= 1_000_000) return `${sign}R$ ${(abs / 1_000_000).toFixed(2).replace(".", ",")}M`
  if (abs >= 1_000)     return `${sign}R$ ${(abs / 1_000).toFixed(1).replace(".", ",")}k`
  return `${sign}R$ ${abs.toFixed(0)}`
}
const fmtBRLkSigned = (v: number) => (v > 0 ? "+" : "") + fmtBRLk(v).replace("+", "")

const fmtBRLFull = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL",
  minimumFractionDigits: 2, maximumFractionDigits: 2,
})
// 4 casas decimais — Cota Sub mexe em centesimos de pp; 2 casas perde sinal.
const fmtPctSigned = (pct: number): string => {
  const sign = pct > 0 ? "+" : pct < 0 ? "−" : ""
  return `${sign}${Math.abs(pct).toFixed(4).replace(".", ",")}%`
}

export type BridgeCardProps = {
  startTotal: number
  endTotal:   number
  drivers:    BridgeDriver[]
  dataD1:     string
  dataD0:     string
  /** Toggle visual; nao altera os deltas — apenas o sufixo de tooltip. */
  unit?:      "R$" | "pp"
  onUnitChange?: (u: "R$" | "pp") => void
  /** Altura desejada do svg. */
  height?:    number
}

export function BridgeCard({
  startTotal,
  endTotal,
  drivers,
  dataD1,
  dataD0,
  unit = "pp",
  onUnitChange,
  height = 360,
}: BridgeCardProps) {
  return (
    <section
      className={cx(
        "flex h-full flex-col gap-2 rounded border px-4 py-3",
        "border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
      )}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-2">
        <div>
          <h3 className="text-[13.5px] font-semibold leading-tight tracking-[-0.01em] text-gray-900 dark:text-gray-50">
            Decomposição da variação
          </h3>
          <p className="mt-0.5 text-[11.5px] text-gray-500 dark:text-gray-400">
            Contribuições por categoria
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <VariacaoChip startTotal={startTotal} endTotal={endTotal} />
          <div className="flex gap-1">
            <UnitChip active={unit === "R$"}  onClick={() => onUnitChange?.("R$")}>R$</UnitChip>
            <UnitChip active={unit === "pp"}  onClick={() => onUnitChange?.("pp")}>pp do PL</UnitChip>
          </div>
        </div>
      </div>

      <div className="mt-1 min-w-0 flex-1">
        <CategoryBridgeSvg
          startTotal={startTotal}
          endTotal={endTotal}
          drivers={drivers}
          dataD1={dataD1}
          dataD0={dataD0}
          height={height}
          unit={unit}
        />
      </div>
    </section>
  )
}

function VariacaoChip({
  startTotal,
  endTotal,
}: {
  startTotal: number
  endTotal:   number
}) {
  const delta = endTotal - startTotal
  const deltaPct = startTotal !== 0 ? (delta / startTotal) * 100 : 0
  const color = delta === 0 ? "#6B7280" : delta > 0 ? COLOR_POSITIVE : COLOR_NEGATIVE
  const sign = delta > 0 ? "+" : delta < 0 ? "−" : ""
  return (
    <div className="flex items-baseline gap-1.5">
      <span className="text-[10px] uppercase tracking-[0.04em] text-gray-500 dark:text-gray-400">
        Variação dia
      </span>
      <span
        className="text-[14px] font-semibold tabular-nums leading-none"
        style={{ color }}
      >
        {sign}{fmtBRLFull.format(Math.abs(delta)).replace("R$ ", "R$ ")}
      </span>
      <span
        className="text-[11px] font-medium tabular-nums leading-none"
        style={{ color }}
      >
        {fmtPctSigned(deltaPct)}
      </span>
    </div>
  )
}

function UnitChip({
  active,
  onClick,
  children,
}: {
  active:   boolean
  onClick?: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cx(
        "inline-flex h-[22px] items-center rounded-[3px] border px-2 text-[11px] transition-colors",
        active
          ? "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900/60 dark:bg-blue-500/10 dark:text-blue-300"
          : "border-gray-200 bg-white text-gray-600 hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-300 dark:hover:bg-gray-900",
      )}
    >
      {children}
    </button>
  )
}

// ─── SVG ─────────────────────────────────────────────────────────────────────

type BarSpec = {
  kind:        "total" | "segment"
  label:       string
  shortLabel?: string
  shortLabel2?: string
  sublabel:    string
  value:       number
  color:       string
  /** Categoria nao implementada (em construcao). */
  placeholder?: boolean
  /** Categoria implementada mas delta=0 (sem impacto no dia). */
  isZero?:      boolean
  x:           number
  barTop:      number
  barBottom:   number
}

function CategoryBridgeSvg({
  startTotal,
  endTotal,
  drivers,
  dataD1,
  dataD0,
  height,
  unit,
}: {
  startTotal: number
  endTotal:   number
  drivers:    BridgeDriver[]
  dataD1:     string
  dataD0:     string
  height:     number
  unit:       "R$" | "pp"
}) {
  // ResizeObserver -> stretch ao container
  const ref = React.useRef<HTMLDivElement>(null)
  const [w, setW] = React.useState(720)
  React.useEffect(() => {
    const el = ref.current
    if (!el) return
    const ro = new ResizeObserver((entries) => {
      const cw = entries[0]?.contentRect.width
      if (cw && cw > 100) setW(Math.floor(cw))
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const padLeft = 64
  const padRight = 16
  const padTop = 32
  // padBottom = 70: comporta 2 linhas de label (eixo X) + sublabel (pp / data).
  // Labels longos como "Marcação a mercado" e "Remuneração Sr/Mez" quebram em 2 linhas
  // pra manter cognato com os titulos dos cards a direita (single source of truth).
  const padBottom = 70
  const innerW = w - padLeft - padRight
  const innerH = height - padTop - padBottom

  // Sequencia de bars: [PL D-1, ...drivers, PL D0]
  const totalBars = 2 + drivers.length
  const slot = innerW / totalBars
  const barW = Math.min(slot * 0.55, 64)

  // Calcula min/max para escalar (com ~30% de padding)
  const valuesForExtent: number[] = [startTotal, endTotal]
  let running = startTotal
  const segmentRunning: { from: number; to: number }[] = []
  drivers.forEach((d) => {
    const from = running
    const to = running + d.delta
    running = to
    valuesForExtent.push(from, to)
    segmentRunning.push({ from, to })
  })
  const dataMax = Math.max(...valuesForExtent)
  const dataMin = Math.min(...valuesForExtent)
  const pad = Math.max((dataMax - dataMin) * 0.3, dataMax * 0.0008, 1)
  const yMin = dataMin - pad
  const yMax = dataMax + pad
  const yRange = yMax - yMin
  const yPos = (v: number) => padTop + ((yMax - v) / yRange) * innerH

  const bars: BarSpec[] = []

  // PL D-1
  bars.push({
    kind:      "total",
    label:     "PL D-1",
    sublabel:  dataD1,
    value:     startTotal,
    color:     GRAY_AXIS,
    x:         padLeft + slot * 0 + (slot - barW) / 2,
    barTop:    yPos(startTotal),
    barBottom: padTop + innerH,
  })

  // Drivers — cor pela direcao do impacto (verde positivo / vermelho negativo).
  // delta=0 e tratado como visualmente neutro (cinza), mesmo quando a
  // categoria nao e placeholder — uma barra sem contribuicao confunde
  // mais que ajuda no waterfall. Distinguimos:
  //   - placeholder: categoria nao implementada -> "em construcao"
  //   - delta=0 implementada: cinza, mas label embaixo fica "—" (nao "em construcao")
  drivers.forEach((d, i) => {
    const seg = segmentRunning[i]
    const top = Math.min(yPos(seg.from), yPos(seg.to))
    const bot = Math.max(yPos(seg.from), yPos(seg.to))
    const isZero = d.delta === 0 && !d.placeholder
    const isNeutral = d.placeholder || isZero
    const color = isNeutral
      ? GRAY_PLACEHOLDER
      : d.delta > 0
        ? COLOR_POSITIVE
        : COLOR_NEGATIVE
    bars.push({
      kind:        "segment",
      label:       d.label,
      shortLabel:  d.shortLabel,
      shortLabel2: d.shortLabel2,
      sublabel:    isNeutral
        ? "—"
        : fmtPctRelative(d.delta, startTotal),
      value:       d.delta,
      color,
      placeholder: d.placeholder,  // preserva o flag original
      isZero,
      x:           padLeft + slot * (i + 1) + (slot - barW) / 2,
      barTop:      top,
      barBottom:   bot,
    })
  })

  // PL D0
  bars.push({
    kind:      "total",
    label:     "PL D0",
    sublabel:  dataD0,
    value:     endTotal,
    color:     "#374151",  // gray-700
    x:         padLeft + slot * (totalBars - 1) + (slot - barW) / 2,
    barTop:    yPos(endTotal),
    barBottom: padTop + innerH,
  })

  // Connectores entre bars (linhas pontilhadas)
  const connectors: { x1: number; y1: number; x2: number; y2: number }[] = []
  for (let i = 0; i < bars.length - 1; i++) {
    const a = bars[i], b = bars[i + 1]
    const yA = a.kind === "total" ? a.barTop : a.value >= 0 ? a.barTop : a.barBottom
    connectors.push({
      x1: a.x + barW,
      y1: yA,
      x2: b.x,
      y2: yA,
    })
  }

  // Gridlines (3 horizontais)
  const gridY = [yMin + yRange * 0.25, yMin + yRange * 0.5, yMin + yRange * 0.75]
  // Ticks laterais 'extremos' — o tick do meio e substituido pela linha de
  // referencia do PL D-1 (zero relativo do waterfall), renderizada abaixo.
  const tickValues = [yMin + yRange * 0.1, yMin + yRange * 0.9]

  return (
    <div ref={ref} className="w-full">
      <svg
        width={w}
        height={height}
        viewBox={`0 0 ${w} ${height}`}
        role="img"
        aria-label="Waterfall de variação do PL Cota Sub por categoria"
        style={{ display: "block" }}
      >
        {/* Gridlines */}
        {gridY.map((v, i) => (
          <line
            key={i}
            x1={padLeft}
            x2={w - padRight}
            y1={yPos(v)}
            y2={yPos(v)}
            stroke={GRAY_GRID}
            strokeWidth={1}
            strokeDasharray="3 3"
          />
        ))}

        {/* Y-axis ticks */}
        {tickValues.map((v, i) => (
          <text
            key={i}
            x={padLeft - 8}
            y={yPos(v) + 3}
            textAnchor="end"
            fontSize={10}
            fill={GRAY_AXIS}
            fontFamily="inherit"
            style={{ fontVariantNumeric: "tabular-nums" }}
          >
            {fmtBRLk(v).replace(/^[+−]/, "")}
          </text>
        ))}

        {/* Linha de referencia PL D-1 — 'zero relativo' do waterfall.
            Tudo acima dela contribuiu positivamente no dia, tudo abaixo
            contribuiu negativamente. Mais forte que as gridlines para
            ancorar a leitura. */}
        <line
          x1={padLeft}
          x2={w - padRight}
          y1={yPos(startTotal)}
          y2={yPos(startTotal)}
          stroke="#374151"
          strokeWidth={1.5}
          strokeOpacity={0.9}
        />
        <text
          x={padLeft - 8}
          y={yPos(startTotal) - 4}
          textAnchor="end"
          fontSize={9}
          fontWeight={700}
          fill="#374151"
          fontFamily="inherit"
          style={{ letterSpacing: "0.04em" }}
        >
          PL D-1
        </text>
        <text
          x={padLeft - 8}
          y={yPos(startTotal) + 9}
          textAnchor="end"
          fontSize={10}
          fontWeight={600}
          fill="#374151"
          fontFamily="inherit"
          style={{ fontVariantNumeric: "tabular-nums" }}
        >
          {fmtBRLk(startTotal).replace(/^[+−]/, "")}
        </text>

        {/* Connectors */}
        {connectors.map((c, i) => (
          <line
            key={i}
            x1={c.x1}
            y1={c.y1}
            x2={c.x2}
            y2={c.y2}
            stroke="#D1D5DB"
            strokeWidth={1}
            strokeDasharray="3 2"
          />
        ))}

        {/* Bars */}
        {bars.map((b, i) => {
          const isTotal = b.kind === "total"
          const fill = isTotal ? GRAY_TOTAL_BAR : b.color
          return (
            <g key={i}>
              <rect
                x={b.x}
                y={b.barTop}
                width={barW}
                height={Math.max(b.barBottom - b.barTop, 2)}
                fill={fill}
                stroke={isTotal ? GRAY_TOTAL_STROKE : "none"}
                strokeWidth={isTotal ? 1 : 0}
                rx={2}
                opacity={(b.placeholder || b.isZero) ? 0.65 : 1}
              />

              {/* Value label */}
              <text
                x={b.x + barW / 2}
                y={
                  isTotal
                    ? b.barTop - 8
                    : b.value >= 0
                      ? b.barTop - 6
                      : b.barBottom + 14
                }
                textAnchor="middle"
                fontSize={isTotal ? 12 : 11}
                fontWeight={600}
                fill={isTotal ? "#111827" : b.color}
                style={{ fontVariantNumeric: "tabular-nums" }}
              >
                {isTotal
                  ? fmtBRLk(b.value).replace(/^\+/, "")
                  : (b.placeholder || b.isZero)
                    ? "—"
                    : fmtBRLkSigned(b.value)}
              </text>

              {/* X-axis label — quebra em 2 linhas quando shortLabel2 esta presente.
                  Cognato 1:1 com o titulo do card a direita (single source of truth). */}
              <text
                x={b.x + barW / 2}
                y={padTop + innerH + 18}
                textAnchor="middle"
                fontSize={11}
                fontWeight={isTotal ? 600 : 500}
                fill={isTotal ? "#111827" : "#374151"}
              >
                {b.shortLabel ?? b.label}
              </text>
              {b.shortLabel2 && (
                <text
                  x={b.x + barW / 2}
                  y={padTop + innerH + 31}
                  textAnchor="middle"
                  fontSize={11}
                  fontWeight={500}
                  fill="#374151"
                >
                  {b.shortLabel2}
                </text>
              )}
              <text
                x={b.x + barW / 2}
                y={padTop + innerH + (b.shortLabel2 ? 47 : 32)}
                textAnchor="middle"
                fontSize={10}
                fill={GRAY_AXIS}
                style={{ fontVariantNumeric: "tabular-nums" }}
              >
                {isTotal
                  ? formatBR(b.sublabel)
                  : b.placeholder
                    ? "em construção"
                    : b.isZero
                      ? "sem impacto"
                      : unit === "pp"
                        ? b.sublabel
                        : fmtBRLkSigned(b.value)}
              </text>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function fmtPctRelative(delta: number, base: number): string {
  if (!base) return "—"
  const pp = (delta / base) * 100
  const sign = pp > 0 ? "+" : pp < 0 ? "−" : ""
  return `${sign}${Math.abs(pp).toFixed(2).replace(".", ",")}pp`
}

function formatBR(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!m) return iso
  return `${m[3]}/${m[2]}/${m[1]}`
}
