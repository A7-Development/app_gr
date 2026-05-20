// src/app/(app)/bi/operacoes4/_components/charts/_mock.ts
//
// Mock data plausivel para a preview/QA dos charts da pagina /bi/operacoes4.
// Os valores nao sao reais — servem apenas para smoke do hi-fi visual.
// Quando PR3 amarrar os charts ao backend, este arquivo fica apenas como
// referencia de shape pros tipos do api-client.

import type { ReceitaBucket } from "./ReceitaCompositionBar"
import type { YieldPonto } from "./YieldChart"
import type { HistogramBucket } from "./HistogramWithParity"
import type { ProjectionScenario } from "./ProjectionFan"
import type { MovementItem } from "./MovementCard"

// ── Composicao da receita (4 buckets, paleta canonica chartUtils) ───────────
// SEM navy `#1B2B4B` (decisao 2026-05-20 — substituido pela escala canonica
// de chart. Ver CLAUDE.md §4 + handoff SPEC).

export const mockComposicao: ReceitaBucket[] = [
  {
    tipo: "desagio",
    label: "Deságio",
    valor: 283310,
    sharePct: 84.5,
    deltaPct: 7.4,
    flagAtypical: false,
  },
  {
    tipo: "tarifa_cessao",
    label: "Tarifa de cessão",
    valor: 396,
    sharePct: 0.1,
    deltaPct: -12.1,
    flagAtypical: false,
  },
  {
    tipo: "tarifas_operacionais",
    label: "Tarifas operacionais",
    valor: 12245,
    sharePct: 3.7,
    deltaPct: 24.3,
    flagAtypical: true,
  },
  {
    tipo: "outras",
    label: "Outras",
    valor: 35012,
    sharePct: 10.6,
    deltaPct: 52.0,
    flagAtypical: true,
  },
]

// ── Yield por DU (mes corrente vs paridade DU) ──────────────────────────────

export const mockYieldDu: YieldPonto[] = Array.from({ length: 12 }, (_, i) => {
  const du = i + 1
  const v = 2.15 + Math.sin(du * 0.4) * 0.1 + (du > 8 ? 0.08 : 0)
  const p = 2.13 + Math.sin(du * 0.4) * 0.08
  return {
    du,
    yieldPct: Number(v.toFixed(3)),
    yieldParityPct: Number(p.toFixed(3)),
    today: du === 12,
  }
})

// ── Histograma de taxas + paridade ──────────────────────────────────────────

export const mockHistTaxas: HistogramBucket[] = [
  { label: "<1,5", atual: 0.4, parity: 0.6 },
  { label: "1,5-1,75", atual: 2.1, parity: 2.8 },
  { label: "1,75-2,0", atual: 6.3, parity: 7.1 },
  { label: "2,0-2,25", atual: 18.7, parity: 17.4 },
  { label: "2,25-2,5", atual: 14.2, parity: 13.1 },
  { label: "2,5-2,75", atual: 8.6, parity: 7.9 },
  { label: "2,75-3,0", atual: 3.8, parity: 3.5 },
  { label: "3,0-3,5", atual: 2.1, parity: 1.6 },
  { label: ">3,5", atual: 1.1, parity: 0.5, tailFlag: true },
]

// ── Histograma de prazos + paridade ─────────────────────────────────────────

export const mockHistPrazos: HistogramBucket[] = [
  { label: "0-15", atual: 1.2, parity: 1.8 },
  { label: "15-30", atual: 4.8, parity: 6.2 },
  { label: "30-45", atual: 15.2, parity: 14.6 },
  { label: "45-60", atual: 22.6, parity: 20.1 },
  { label: "60-75", atual: 9.4, parity: 8.1 },
  { label: "75-90", atual: 3.2, parity: 2.4 },
  { label: ">90", atual: 0.9, parity: 0.3, tailFlag: true },
]

// ── Projecao fim de mes — VOP acumulado + 3 cenarios ────────────────────────

export const mockProjectionRealizado: number[] = [
  // Acumulado em milhoes ao longo dos 12 DUs do MTD
  4.2, 9.3, 13.1, 21.0, 25.7, 31.0, 35.9, 37.7, 43.2, 49.3, 54.1, 57.3,
]
export const mockProjectionDuLabels: string[] = Array.from(
  { length: 22 },
  (_, i) => `DU ${i + 1}`,
)
export const mockProjectionCenarios: ProjectionScenario[] = [
  { label: "Pessimista", finalValor: 94 },
  { label: "Realista", finalValor: 105 },
  { label: "Otimista", finalValor: 118 },
]
export const mockProjectionDuCorrente = 12 // 1-indexed

// ── MovementCards (Novos / Sumidos / Top Movers) ────────────────────────────

export const mockNovos: { count: number; items: MovementItem[] } = {
  count: 8,
  items: [
    { primaryLabel: "Confecções Vega ME", valueLabel: "R$ 7,8M" },
    { primaryLabel: "Têxtil Andrómeda EIRELI", valueLabel: "R$ 4,8M" },
    { primaryLabel: "Mecânica Vela Ltda", valueLabel: "R$ 2,1M" },
  ],
}

export const mockSumidos: { count: number; items: MovementItem[] } = {
  count: 3,
  items: [
    { primaryLabel: "Indústria Cassiopeia", valueLabel: "R$ 4,2M (antes)" },
    { primaryLabel: "Eletro Norma SA", valueLabel: "R$ 2,8M (antes)" },
    { primaryLabel: "Distribuidora Halo", valueLabel: "R$ 1,1M (antes)" },
  ],
}

export const mockMovers: { count: number; items: MovementItem[] } = {
  count: 5,
  items: [
    {
      primaryLabel: "Indústria Ômega",
      valueLabel: "+R$ 1,9M",
      deltaLabel: "+18%",
      tone: "pos",
    },
    {
      primaryLabel: "Metalúrgica Sigma",
      valueLabel: "−R$ 2,2M",
      deltaLabel: "−24%",
      tone: "neg",
    },
    {
      primaryLabel: "Atacado Caravela",
      valueLabel: "−R$ 0,6M",
      deltaLabel: "−8%",
      tone: "neg",
    },
  ],
}
