/**
 * Lamina FIDC -- calculos de display e formatadores (pt-BR).
 *
 * Portado do handoff de design (Claude Design). Todas as transformacoes sao
 * puras sobre os arrays deterministicos vindos das silver QiTech (LaminaResponse):
 * acumulado composto, % do CDI, razao de garantia, PDD/carteira. Cores =
 * tokens do Strata DS (navy/blue/gray-scale).
 */

import type {
  LaminaClasse,
  LaminaClasseSerie,
  LaminaResponse,
} from "@/lib/api-client"

// ── Formatadores ─────────────────────────────────────────────────────────────
export const fmt = (v: number | null | undefined): string =>
  v == null ? "—" : v.toLocaleString("pt-BR", { maximumFractionDigits: 0 })
export const fmtMi = (v: number): string =>
  (v / 1e6).toLocaleString("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })
export const p2 = (v: number | null | undefined): string =>
  v == null
    ? "—"
    : v.toLocaleString("pt-BR", {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
      })
export const p1 = (v: number | null | undefined): string =>
  v == null
    ? "—"
    : v.toLocaleString("pt-BR", {
        minimumFractionDigits: 1,
        maximumFractionDigits: 1,
      })

// ── Calculos ─────────────────────────────────────────────────────────────────
export const pctCDI = (r: number | null, c: number): number | null =>
  r == null || !c ? null : (r / c) * 100

export function compound(a: (number | null)[]): number {
  let p = 1
  for (const x of a) {
    if (x == null) continue
    p *= 1 + x / 100
  }
  return (p - 1) * 100
}

// ── Tokens de cor (Strata DS) ────────────────────────────────────────────────
export const CLASSE_COLOR: Record<LaminaClasse, string> = {
  sr: "#93C5FD", // blue-300
  mez: "#3B82F6", // blue-500
  sub: "#1B2B4B", // brand navy
}
// Rotulos abreviados de exibicao (lamina) — consistentes com os KPIs.
export const CLASSE_SHORT: Record<LaminaClasse, string> = {
  sr: "Sênior",
  mez: "Sub Mez",
  sub: "Sub Jr",
}
export const COL = {
  cdiLine: "#9CA3AF", // gray-400
  subLine: "#2563EB", // blue-600
  alert: "#DC2626", // red-600 (PDD)
  garantia: "#E9D400", // amarelo da lamina (faixa do topo / wordmark) -- razao de garantia
  vencido: "#D97706", // amber-600
  caixa: "#D1D5DB", // gray-300
  grid: "#F3F4F6", // gray-100
  axis: "#9CA3AF",
  strong: "#111827",
  muted: "#6B7280",
  faint: "#9CA3AF",
  pos: "#059669", // emerald-600
  neg: "#DC2626",
} as const

// ── Derivacao do payload ─────────────────────────────────────────────────────
export type LaminaKpi = {
  plTotal: number
  sen12: number | null
  sen12Cdi: number | null
  mez12: number | null
  mez12Cdi: number | null
  sub12: number | null
  sub12Cdi: number | null
  razao: number
  pddPl: number
}

export type LaminaDerived = {
  byClasse: Partial<Record<LaminaClasse, LaminaClasseSerie>>
  last: number
  c12: number
  totals: number[]
  razaoMensal: number[]
  pddPlPct: number[]
  kpi: LaminaKpi
}

export function derive(d: LaminaResponse): LaminaDerived {
  const byClasse: Partial<Record<LaminaClasse, LaminaClasseSerie>> = {}
  for (const c of d.classes) byClasse[c.classe] = c

  const last = Math.max(0, d.meses.length - 1)
  const c12 = compound(d.cdi)
  const cl12 = (cl: LaminaClasse): number | null => {
    const c = byClasse[cl]
    return c ? compound(c.var_mensal) : null
  }
  const cdiPct = (r: number | null): number | null =>
    r == null || !c12 ? null : (r / c12) * 100

  const totals: number[] = []
  const razaoMensal: number[] = []
  for (let i = 0; i < d.meses.length; i++) {
    let tot = 0
    let sub = 0
    let mez = 0
    for (const c of d.classes) {
      const v = c.patrimonio[i] ?? 0
      tot += v
      if (c.classe === "sub") sub = v
      if (c.classe === "mez") mez = v
    }
    totals.push(tot)
    razaoMensal.push(tot ? ((sub + mez) / tot) * 100 : 0)
  }

  const ag = d.aging
  // PDD sobre o PL (ex-WOP -- o backend ja exclui WOP do PDD/carteira).
  const pddPlPct = totals.map((pl, i) => (pl ? ((ag.pdd[i] ?? 0) / pl) * 100 : 0))

  const sen12 = cl12("sr")
  const mez12 = cl12("mez")
  const sub12 = cl12("sub")

  return {
    byClasse,
    last,
    c12,
    totals,
    razaoMensal,
    pddPlPct,
    kpi: {
      plTotal: d.pl_total,
      sen12,
      sen12Cdi: cdiPct(sen12),
      mez12,
      mez12Cdi: cdiPct(mez12),
      sub12,
      sub12Cdi: cdiPct(sub12),
      razao: razaoMensal[last] ?? 0,
      pddPl: pddPlPct[last] ?? 0,
    },
  }
}
