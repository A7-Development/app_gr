/**
 * Lamina FIDC -- graficos SVG inline.
 *
 * MOTIVO: superficie de impressao (PDF/A4). SVG manual da controle de pixel e
 * imprime nitido; ECharts (canvas) nao imprime bem e Recharts (ResponsiveContainer)
 * nao casa com layout fixo A4. Linguagem editorial (FT/Economist): sem moldura,
 * eixos discretos, rotulagem direta do ultimo ponto. Cores = tokens (calc.ts COL).
 */

import * as React from "react"

import type { LaminaClasse, LaminaClasseSerie } from "@/lib/api-client"

import { CLASSE_COLOR, COL, p1 } from "./calc"

const GRID = COL.grid

function gridLines(
  p: number,
  w: number,
  rp: number,
  ys: (v: number) => number,
  vals: number[],
  fmtLabel: (v: number) => string,
): React.ReactNode[] {
  const out: React.ReactNode[] = []
  vals.forEach((v, i) => {
    out.push(
      <line key={`g${i}`} x1={p} y1={ys(v)} x2={w - rp} y2={ys(v)} stroke={GRID} strokeWidth={1} />,
    )
    out.push(
      <text key={`gt${i}`} x={p - 4} y={ys(v) + 3} fill={COL.axis} fontSize={7.5} textAnchor="end">
        {fmtLabel(v)}
      </text>,
    )
  })
  return out
}

const pts = (a: [number, number][]): string => a.map((d) => d.join(",")).join(" ")

// ── Rentabilidade historica acumulada (Sub JR vs CDI) ────────────────────────
export function RentHistChart({
  meses,
  varSub,
  cdi,
}: {
  meses: string[]
  varSub: (number | null)[]
  cdi: number[]
}) {
  const W = 360, H = 160, P = 30, RP = 10
  const cs: number[] = [100]
  const cc: number[] = [100]
  varSub.forEach((v, i) => {
    cs.push(cs[cs.length - 1] * (1 + (v ?? 0) / 100))
    cc.push(cc[cc.length - 1] * (1 + (cdi[i] ?? 0) / 100))
  })
  const max = Math.max(...cs, ...cc)
  const min = 100
  const span = max - min || 1
  const xs = (k: number) => P + (k * (W - P - RP)) / (cs.length - 1)
  const ys = (v: number) => H - 24 - ((v - min) / span) * (H - 42)
  const grid = [0, 1, 2, 3, 4].map((i) => min + (span * i) / 4)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" preserveAspectRatio="xMidYMid meet" style={{ display: "block" }}>
      {gridLines(P, W, RP, ys, grid, (v) => `+${(v - 100).toFixed(0)}%`)}
      <polyline points={pts(cc.map((v, k) => [xs(k), ys(v)]))} fill="none" stroke={COL.cdiLine} strokeWidth={1.5} strokeLinejoin="round" />
      <polyline points={pts(cs.map((v, k) => [xs(k), ys(v)]))} fill="none" stroke={COL.subLine} strokeWidth={2.2} strokeLinejoin="round" />
      <circle cx={xs(cs.length - 1)} cy={ys(cs[cs.length - 1])} r={2.6} fill={COL.subLine} />
      <text x={xs(cs.length - 1) - 3} y={ys(cs[cs.length - 1]) - 6} fill={COL.subLine} fontSize={9.5} fontWeight={700} textAnchor="end">
        {`+${(cs[cs.length - 1] - 100).toFixed(1)}%`}
      </text>
      <text x={xs(cc.length - 1) - 3} y={ys(cc[cc.length - 1]) + 11} fill={COL.muted} fontSize={8.5} fontWeight={600} textAnchor="end">
        {`+${(cc[cc.length - 1] - 100).toFixed(1)}%`}
      </text>
      {meses.map((m, k) => (k % 2 === 0 ? <text key={k} x={xs(k + 1)} y={H - 7} fill={COL.axis} fontSize={7.5} textAnchor="middle">{m}</text> : null))}
    </svg>
  )
}

// ── Evolucao do PL (area empilhada por classe) ───────────────────────────────
export function PLStackedChart({
  meses,
  classes,
}: {
  meses: string[]
  classes: LaminaClasseSerie[]
}) {
  const W = 360, H = 160, P = 32, RP = 10
  const n = meses.length
  const get = (cl: LaminaClasse) => classes.find((c) => c.classe === cl)
  const patOf = (cl: LaminaClasse, i: number) => get(cl)?.patrimonio[i] ?? 0
  const tot = meses.map((_, i) => patOf("sub", i) + patOf("mez", i) + patOf("sr", i))
  const max = Math.max(...tot, 1) * 1.08
  const xs = (k: number) => P + (k * (W - P - RP)) / (n - 1 || 1)
  const ys = (v: number) => H - 24 - (v / max) * (H - 42)
  const area = (top: number[]): string =>
    pts([[xs(0), ys(0)], ...top.map((v, k) => [xs(k), ys(v)] as [number, number]), [xs(n - 1), ys(0)]])
  const lvlSub = meses.map((_, i) => patOf("sub", i))
  const lvlMez = meses.map((_, i) => patOf("sub", i) + patOf("mez", i))
  const grid = [0, 1, 2, 3, 4].map((i) => (max * i) / 4)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" preserveAspectRatio="xMidYMid meet" style={{ display: "block" }}>
      {gridLines(P, W, RP, ys, grid, (v) => `${(v / 1e6).toFixed(0)} mi`)}
      <polygon points={area(tot)} fill={CLASSE_COLOR.sr} />
      <polygon points={area(lvlMez)} fill={CLASSE_COLOR.mez} />
      <polygon points={area(lvlSub)} fill={CLASSE_COLOR.sub} />
      <text x={W - RP} y={ys(tot[n - 1]) - 6} fill={COL.strong} fontSize={9.5} fontWeight={700} textAnchor="end">
        {`${(tot[n - 1] / 1e6).toFixed(1)} mi`}
      </text>
      {meses.map((m, k) => (k % 2 === 0 ? <text key={k} x={xs(k)} y={H - 7} fill={COL.axis} fontSize={7.5} textAnchor="middle">{m}</text> : null))}
    </svg>
  )
}

// ── Razao de garantia (% PL empilhado + linha (Sub+Mez)/PL) ──────────────────
export function GarantiaChart({
  meses,
  classes,
  totals,
  razao,
}: {
  meses: string[]
  classes: LaminaClasseSerie[]
  totals: number[]
  razao: number[]
}) {
  const W = 712, H = 168, P = 30, RP = 8
  const n = meses.length
  const slot = (W - P - RP) / n
  const bw = slot * 0.62
  const xs = (k: number) => P + k * slot + (slot - bw) / 2
  const ys = (v: number) => H - 22 - (v / 100) * (H - 40)
  const get = (cl: LaminaClasse) => classes.find((c) => c.classe === cl)
  const pctOf = (cl: LaminaClasse, i: number) => (totals[i] ? ((get(cl)?.patrimonio[i] ?? 0) / totals[i]) * 100 : 0)
  const grid = [0, 1, 2, 3, 4].map((i) => 25 * i)
  const bars: React.ReactNode[] = []
  for (let k = 0; k < n; k++) {
    let y0 = ys(0)
    const order: LaminaClasse[] = ["sub", "mez", "sr"]
    order.forEach((cl) => {
      const h = (pctOf(cl, k) / 100) * (H - 40)
      bars.push(<rect key={`${cl}${k}`} x={xs(k)} y={y0 - h} width={bw} height={Math.max(0, h)} fill={CLASSE_COLOR[cl]} />)
      y0 -= h
    })
    if (k % 2 === 0) bars.push(<text key={`x${k}`} x={xs(k) + bw / 2} y={H - 7} fill={COL.axis} fontSize={7.5} textAnchor="middle">{meses[k]}</text>)
  }
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" preserveAspectRatio="xMidYMid meet" style={{ display: "block" }}>
      {gridLines(P, W, RP, ys, grid, (v) => `${v}%`)}
      {bars}
      <polyline points={pts(razao.map((v, k) => [xs(k) + bw / 2, ys(v)]))} fill="none" stroke={COL.alert} strokeWidth={2} strokeLinejoin="round" />
      {razao.map((v, k) => <circle key={k} cx={xs(k) + bw / 2} cy={ys(v)} r={2} fill={COL.alert} />)}
      <text x={xs(n - 1) + bw / 2} y={ys(razao[n - 1]) - 7} fill={COL.alert} fontSize={9} fontWeight={700} textAnchor="end">{`${p1(razao[n - 1])}%`}</text>
    </svg>
  )
}

// ── Evolucao do ativo (a vencer/vencido/caixa + PDD/carteira linha) ──────────
export function AtivoChart({
  meses,
  aVencer,
  vencido,
  caixa,
  pddPct,
}: {
  meses: string[]
  aVencer: number[]
  vencido: number[]
  caixa: number[]
  pddPct: number[]
}) {
  const W = 712, H = 168, P = 32, RP = 8
  const n = meses.length
  const slot = (W - P - RP) / n
  const bw = slot * 0.62
  const xs = (k: number) => P + k * slot + (slot - bw) / 2
  const tot = meses.map((_, i) => (aVencer[i] ?? 0) + (vencido[i] ?? 0) + (caixa[i] ?? 0))
  const max = Math.max(...tot, 1) * 1.08
  const ys = (v: number) => H - 22 - (v / max) * (H - 42)
  const grid = [0, 1, 2, 3, 4].map((i) => (max * i) / 4)
  const bars: React.ReactNode[] = []
  for (let k = 0; k < n; k++) {
    let y0 = ys(0)
    const stack: [number, string][] = [
      [aVencer[k] ?? 0, CLASSE_COLOR.mez],
      [vencido[k] ?? 0, COL.vencido],
      [caixa[k] ?? 0, COL.caixa],
    ]
    stack.forEach(([val, color], si) => {
      const h = (val / max) * (H - 42)
      bars.push(<rect key={`b${k}-${si}`} x={xs(k)} y={y0 - h} width={bw} height={Math.max(0, h)} fill={color} />)
      y0 -= h
    })
    if (k % 2 === 0) bars.push(<text key={`x${k}`} x={xs(k) + bw / 2} y={H - 7} fill={COL.axis} fontSize={7.5} textAnchor="middle">{meses[k]}</text>)
  }
  const pmax = Math.max(...pddPct, 0.01) * 1.5
  const yp = (v: number) => H - 22 - (v / pmax) * (H - 42)
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" preserveAspectRatio="xMidYMid meet" style={{ display: "block" }}>
      {gridLines(P, W, RP, ys, grid, (v) => `${(v / 1e6).toFixed(0)} mi`)}
      {bars}
      <polyline points={pts(pddPct.map((v, k) => [xs(k) + bw / 2, yp(v)]))} fill="none" stroke={COL.alert} strokeWidth={1.8} strokeLinejoin="round" />
      {pddPct.map((v, k) => <circle key={k} cx={xs(k) + bw / 2} cy={yp(v)} r={1.7} fill={COL.alert} />)}
      <text x={xs(n - 1) + bw / 2} y={yp(pddPct[n - 1]) - 6} fill={COL.alert} fontSize={8.5} fontWeight={700} textAnchor="end">{`${p1(pddPct[n - 1])}%`}</text>
    </svg>
  )
}

// ── Historico de concentracao (maior vs 10 maiores) ──────────────────────────
export function ConcHistChart({
  meses,
  maior,
  top10,
}: {
  meses: string[]
  maior: number[]
  top10: number[]
}) {
  const W = 360, H = 160, P = 28, RP = 8
  const n = meses.length
  const slot = (W - P - RP) / n
  const bw = slot * 0.34
  const ys = (v: number) => H - 20 - (v / 80) * (H - 38)
  const grid = [0, 1, 2, 3, 4].map((i) => 20 * i)
  const bars: React.ReactNode[] = []
  for (let k = 0; k < n; k++) {
    const x = P + k * slot + slot * 0.1
    bars.push(<rect key={`t${k}`} x={x} y={ys(top10[k] ?? 0)} width={bw} height={Math.max(0, ys(0) - ys(top10[k] ?? 0))} fill={CLASSE_COLOR.sr} />)
    bars.push(<rect key={`m${k}`} x={x + bw + 2} y={ys(maior[k] ?? 0)} width={bw} height={Math.max(0, ys(0) - ys(maior[k] ?? 0))} fill={CLASSE_COLOR.sub} />)
    if (k % 2 === 0) bars.push(<text key={`x${k}`} x={x + bw} y={H - 6} fill={COL.axis} fontSize={7} textAnchor="middle">{meses[k]}</text>)
  }
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" preserveAspectRatio="xMidYMid meet" style={{ display: "block" }}>
      {gridLines(P, W, RP, ys, grid, (v) => `${v}%`)}
      {bars}
    </svg>
  )
}
