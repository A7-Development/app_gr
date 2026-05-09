"use client"

/**
 * WaterfallEventosCard — chart hero da Aba "Eventos do dia".
 *
 * Decompoe Δ Cota Sub do dia em 3 grupos visuais no eixo X:
 *   1. ATIVO   — 10 linhas (Bancos, Compromissada, NTN, NC, FDI, DC,
 *                PDD, Liquidacoes, Desp. Antecip., Outros Ativos)
 *   2. PASSIVO — 5 linhas (IOF, Prov. Pgto, Val. Adm + Cota Mez, Cota Sr)
 *   3. Δ       — saldo final (Total Δ Cota Sub)
 *
 * Cada barra ancorada em zero (variance bar): positivos acima (verde =
 * contribuiu), negativos abaixo (vermelho = subtraiu). Cor codifica
 * contribuicao na Cota Sub (NAO o sinal cru do delta da linha):
 *   - Linha de Ativo crescendo  → contribuicao = +Δ (verde)
 *   - Linha de Passivo crescendo → contribuicao = -Δ (vermelho)
 *
 * Grupos delimitados visualmente por:
 *   - markArea com cor de fundo MUITO sutil (opacity 0.04) por grupo
 *   - Label "Ativo"/"Passivo"/"Δ" no topo de cada area
 *   - Coluna vazia (gap) entre grupos
 *
 * Por que NAO um waterfall classico (stacked com placeholder transparente):
 * ECharts agrupa stacks por sinal — positivos somam pra cima, negativos pra
 * baixo, perdendo a ordem temporal quando ha mistura de sinais. Resultado:
 * barras renderizam no lado errado do eixo Y. Variance bar e mais simples e
 * comunica corretamente o que importa: magnitude e direcao por linha.
 */

import * as React from "react"
import type { EChartsOption } from "echarts"

import { EChartsCard } from "@/design-system/components/EChartsCard"

import type {
  DecomposicaoLinhas,
  LinhaContribuicao,
} from "../_lib/agregacao-buckets"

// Paleta semantica — hex permitido em EChartsOption (CLAUDE.md §4 excecao).
const COLOR_POSITIVE     = "#10B981"  // emerald-500
const COLOR_NEGATIVE     = "#F43F5E"  // rose-500
const COLOR_TOTAL        = "#475569"  // slate-600 — saldo final neutro
const COLOR_BG_ATIVO     = "rgba(16,185,129,0.05)"   // emerald translucido
const COLOR_BG_PASSIVO   = "rgba(244,63,94,0.05)"    // rose translucido
const COLOR_BG_TOTAL     = "rgba(71,85,105,0.05)"    // slate translucido
const COLOR_GROUP_LABEL  = "#475569"  // slate-600
const COLOR_AXIS         = "#9CA3AF"  // gray-400
const COLOR_SPLITLINE    = "#E5E7EB"  // gray-200

const fmtBRLCompact = new Intl.NumberFormat("pt-BR", {
  style:                 "currency",
  currency:              "BRL",
  notation:              "compact",
  maximumFractionDigits: 2,
})
const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style:                 "currency",
  currency:              "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

// ─── Normalizacao de labels longos do balancete ──────────────────────────────

/** Title-Case simplificado para os labels que vem em ALL CAPS do backend.
 * Mantem a grafia original quando ja eh "natural" (ex.: "Direitos Creditorios"). */
function normalizarLabel(raw: string): string {
  if (!raw) return raw
  // Heuristica: se ja tem letras minusculas, devolve como veio.
  if (raw !== raw.toUpperCase()) return raw
  return raw
    .toLowerCase()
    .split(" ")
    .map((tk) => {
      if (tk.length <= 2) return tk.toUpperCase()  // siglas: IOF, NTN, A, etc.
      return tk.charAt(0).toUpperCase() + tk.slice(1)
    })
    .join(" ")
}

/** Trunca label longo para caber no eixo X (rotacionado). Tooltip mostra completo. */
function truncarLabel(s: string, max = 24): string {
  if (s.length <= max) return s
  return s.slice(0, max - 1).trimEnd() + "…"
}

// ─── Steps do chart (categorias do eixo X) ───────────────────────────────────

type Step = {
  label:     string  // exibido no eixo X (truncado/normalizado)
  labelFull: string  // mostrado no tooltip (original)
  /** bucket = linha do balancete; total = saldo final; gap = vazio. */
  kind:      "bucket" | "total" | "gap"
  /** Lado: define o markArea de fundo. Para gap/total, usado apenas no tooltip. */
  lado:      "ativo" | "passivo" | "total" | "gap"
  /** Valor com sinal (positivo acima de zero, negativo abaixo). Para gap, 0. */
  value:     number
  color:     string
}

function buildSteps(decomp: DecomposicaoLinhas): Step[] {
  const steps: Step[] = []

  function pushLinha(linha: LinhaContribuicao, lado: "ativo" | "passivo") {
    const labelNorm = normalizarLabel(linha.label)
    const c = linha.contribuicao_cota_sub
    steps.push({
      label:     truncarLabel(labelNorm),
      labelFull: labelNorm,
      kind:      "bucket",
      lado,
      value:     c,
      color:     c >= 0 ? COLOR_POSITIVE : COLOR_NEGATIVE,
    })
  }

  // Grupo 1 — Ativo
  for (const linha of decomp.ativo) pushLinha(linha, "ativo")

  // Gap separador entre Ativo e Passivo
  steps.push({
    label: " ", labelFull: "", kind: "gap", lado: "gap",
    value: 0, color: "transparent",
  })

  // Grupo 2 — Passivo (inclui Equity)
  for (const linha of decomp.passivo) pushLinha(linha, "passivo")

  // Gap separador entre Passivo e Total
  steps.push({
    label: "  ", labelFull: "", kind: "gap", lado: "gap",
    value: 0, color: "transparent",
  })

  // Grupo 3 — Total Δ
  steps.push({
    label:     "Total Δ",
    labelFull: "Total Δ Cota Subordinada",
    kind:      "total",
    lado:      "total",
    value:     decomp.delta_cota_sub,
    color:     COLOR_TOTAL,
  })

  return steps
}

/** Indices [start, end] de cada grupo no array steps — usados em markArea. */
function groupRanges(steps: Step[]): {
  ativo:    [number, number] | null
  passivo:  [number, number] | null
  total:    [number, number] | null
} {
  const ativoIdx   = steps.map((s, i) => (s.lado === "ativo"   ? i : -1)).filter((i) => i >= 0)
  const passivoIdx = steps.map((s, i) => (s.lado === "passivo" ? i : -1)).filter((i) => i >= 0)
  const totalIdx   = steps.map((s, i) => (s.lado === "total"   ? i : -1)).filter((i) => i >= 0)
  return {
    ativo:   ativoIdx.length   ? [ativoIdx[0],   ativoIdx[ativoIdx.length - 1]]     : null,
    passivo: passivoIdx.length ? [passivoIdx[0], passivoIdx[passivoIdx.length - 1]] : null,
    total:   totalIdx.length   ? [totalIdx[0],   totalIdx[totalIdx.length - 1]]     : null,
  }
}

function buildOption(steps: Step[]): EChartsOption {
  const categories = steps.map((s) => s.label)
  const ranges     = groupRanges(steps)

  const data = steps.map((s) => {
    const v = s.kind === "gap" ? 0 : s.value
    const position: "top" | "bottom" = v >= 0 ? "top" : "bottom"
    return {
      value:     v,
      itemStyle: { color: s.color },
      label:     { position },
    }
  })

  // markArea com label-header por grupo. label aparece em cima de cada area.
  // Tipo permissivo (unknown[][]) — o tipo interno do ECharts e complexo demais
  // pra anotar manualmente; passamos como `EChartsOption` no fim e ele aceita.
  const markAreaData: unknown[][] = []
  if (ranges.ativo) {
    markAreaData.push([
      {
        xAxis:     ranges.ativo[0],
        name:      "Ativo",
        itemStyle: { color: COLOR_BG_ATIVO },
        label:     {
          show:       true,
          position:   "insideTop",
          formatter:  "Ativo",
          color:      COLOR_GROUP_LABEL,
          fontSize:   12,
          fontWeight: "bold",
        },
      },
      { xAxis: ranges.ativo[1], itemStyle: { color: COLOR_BG_ATIVO } },
    ])
  }
  if (ranges.passivo) {
    markAreaData.push([
      {
        xAxis:     ranges.passivo[0],
        name:      "Passivo",
        itemStyle: { color: COLOR_BG_PASSIVO },
        label:     {
          show:       true,
          position:   "insideTop",
          formatter:  "Passivo",
          color:      COLOR_GROUP_LABEL,
          fontSize:   12,
          fontWeight: "bold",
        },
      },
      { xAxis: ranges.passivo[1], itemStyle: { color: COLOR_BG_PASSIVO } },
    ])
  }
  if (ranges.total) {
    markAreaData.push([
      {
        xAxis:     ranges.total[0],
        name:      "Δ",
        itemStyle: { color: COLOR_BG_TOTAL },
        label:     {
          show:       true,
          position:   "insideTop",
          formatter:  "Δ Cota Sub",
          color:      COLOR_GROUP_LABEL,
          fontSize:   12,
          fontWeight: "bold",
        },
      },
      { xAxis: ranges.total[1], itemStyle: { color: COLOR_BG_TOTAL } },
    ])
  }

  return {
    grid: { top: 48, right: 16, bottom: 110, left: 64 },
    xAxis: {
      type: "category",
      data: categories,
      axisTick: { show: false },
      axisLabel: {
        interval: 0,
        rotate:   -45,
        fontSize: 10,
      },
    },
    yAxis: {
      type: "value",
      axisLine:  { show: true, lineStyle: { color: COLOR_AXIS } },
      axisLabel: {
        formatter: (v: number) => fmtBRLCompact.format(v),
        fontSize:  11,
      },
      splitLine: { lineStyle: { color: COLOR_SPLITLINE, type: "dashed" } },
    },
    tooltip: {
      trigger: "axis",
      axisPointer: { type: "shadow" },
      formatter: (params: unknown) => {
        const list = params as Array<{ dataIndex: number }>
        if (!list || list.length === 0) return ""
        const idx = list[0].dataIndex
        const step = steps[idx]
        if (!step || step.kind === "gap") return ""
        const sinal = step.value >= 0 ? "+" : ""
        const linhaTitulo =
          step.kind === "total"
            ? "Saldo final do dia"
            : `Contribuicao na Cota Sub (${step.lado === "ativo" ? "Ativo" : "Passivo"})`
        return `<div style="font-size:12px"><strong>${step.labelFull}</strong><br/>${linhaTitulo}: ${sinal}${fmtBRL.format(step.value)}</div>`
      },
    },
    series: [
      {
        name: "valor",
        type: "bar",
        data,
        markArea: {
          silent: true,
          // Cast pontual: o tipo interno do ECharts para markArea data e
          // complexo demais (MarkArea2DDataItemOption[][]). Construimos o
          // array com a forma correta acima — o cast aqui apenas relaxa o
          // narrowing.
          data:   markAreaData as never,
        },
        label: {
          show:     true,
          fontSize: 9,
          formatter: (p: { dataIndex: number }) => {
            const step = steps[p.dataIndex]
            if (!step || step.kind === "gap") return ""
            const sinal = step.value >= 0 ? "+" : ""
            return `${sinal}${fmtBRLCompact.format(step.value)}`
          },
        },
      },
    ],
  }
}

// ─── Componente ──────────────────────────────────────────────────────────────

export type WaterfallEventosCardProps = {
  decomposicao?:  DecomposicaoLinhas
  loading?:       boolean
  error?:         string | null
  onRetry?:       () => void
  onLinhaClick?:  (linhaId: string) => void  // PR2 — drill-down
}

export function WaterfallEventosCard({
  decomposicao,
  loading,
  error,
  onRetry,
}: WaterfallEventosCardProps) {
  const steps = React.useMemo(
    () => (decomposicao ? buildSteps(decomposicao) : []),
    [decomposicao],
  )
  const option = React.useMemo(() => buildOption(steps), [steps])

  // Caption simplificado: "Variação Cota Sub: ±R$ X mil | ±Y,YY%". PL
  // absolutos D-1/D0 ficam disponiveis no tooltip do chart e na coluna
  // dedicada da BalanceTable abaixo.
  const caption = React.useMemo(() => {
    if (!decomposicao) return "Como cada linha do balancete contribuiu para Δ Cota Sub"
    const valorSinal = decomposicao.delta_cota_sub >= 0 ? "+" : ""
    const valor = `${valorSinal}${fmtBRLCompact.format(decomposicao.delta_cota_sub)}`
    const pct =
      decomposicao.cota_sub_d1 !== 0
        ? (decomposicao.delta_cota_sub / Math.abs(decomposicao.cota_sub_d1)) * 100
        : 0
    const pctSinal = pct >= 0 ? "+" : ""
    const pctTexto = `${pctSinal}${pct.toFixed(2).replace(".", ",")}%`
    return `Variação Cota Sub: ${valor} | ${pctTexto}`
  }, [decomposicao])

  return (
    <EChartsCard
      title="Eventos do dia · decomposicao da Cota Subordinada"
      caption={caption}
      option={option}
      height={460}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  )
}
