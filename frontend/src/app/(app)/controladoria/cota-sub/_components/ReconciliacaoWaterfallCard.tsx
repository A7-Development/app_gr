"use client"

/**
 * ReconciliacaoWaterfallCard — Z2 hero da Aba "Eventos do dia".
 *
 * Visualiza a equacao de reconciliacao da Cota Sub:
 *
 *   ΔPL Sub esperado = ΔPL Total − ΔCotas Sr emitidas − ΔCotas Mez emitidas
 *   Residuo          = ΔPL Sub real − ΔPL Sub esperado   (~ 0)
 *
 * Layout: 3 variance bars de contribuicao (esquerda) + separador + 3 totals
 * (direita).
 *
 *   [+ΔPL Total]  [−ΔCotas Sr]  [−ΔCotas Mez]  ‖  [=Esperado]  [Real]  [Residuo]
 *
 * Cor codifica contribuicao na Cota Sub:
 *   - ΔPL Total cresceu       → contribuicao = +Δ (verde)
 *   - ΔCotas Sr/Mez cresceu   → contribuicao = -Δ (vermelho)
 *
 * Bloco da direita usa cinza (saldo neutro). Residuo: ambar/vermelho se
 * fora de tolerancia.
 */

import * as React from "react"
import type { EChartsOption } from "echarts"

import { EChartsCard } from "@/design-system/components/EChartsCard"
import type { CosifNode, Reconciliacao } from "@/lib/api-client"

// Paleta semantica — hex permitido em EChartsOption (CLAUDE.md §4 excecao).
const COLOR_POSITIVE    = "#10B981"  // emerald-500
const COLOR_NEGATIVE    = "#F43F5E"  // rose-500
const COLOR_NEUTRAL     = "#475569"  // slate-600
const COLOR_RESIDUO_OK  = "#10B981"
const COLOR_RESIDUO_AMB = "#F59E0B"  // amber-500
const COLOR_RESIDUO_ERR = "#EF4444"  // red-500
const COLOR_BG_INPUT    = "rgba(59,130,246,0.04)"    // azul translucido (esquerda)
const COLOR_BG_RECON    = "rgba(71,85,105,0.05)"     // slate translucido (direita)
const COLOR_GROUP_LABEL = "#475569"
const COLOR_AXIS        = "#9CA3AF"
const COLOR_SPLITLINE   = "#E5E7EB"

const fmtBRLCompact = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL",
  notation: "compact", maximumFractionDigits: 2,
})
const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL",
  minimumFractionDigits: 2, maximumFractionDigits: 2,
})

// Tolerancia do residuo — alinhada com plano (CLAUDE.md §pendente):
//   <0,1pp do PL Sub D-1: verde
//   0,1pp – 1pp         : ambar
//   >1pp                : vermelho
const TOL_PP_OK    = 0.001  // 0,1pp = 0.1%
const TOL_PP_AMBER = 0.01   // 1pp = 1%

type StepKind = "input" | "gap" | "expected" | "real" | "residuo"

type Step = {
  kind:      StepKind
  label:     string
  labelFull: string
  value:     number
  color:     string
  /** Tooltip linha 2 — explica a contribuicao. */
  hint:      string
}

function residuoColor(absPp: number): string {
  if (absPp <= TOL_PP_OK) return COLOR_RESIDUO_OK
  if (absPp <= TOL_PP_AMBER) return COLOR_RESIDUO_AMB
  return COLOR_RESIDUO_ERR
}

/**
 * Extrai delta agregado por grupo COSIF (1=Ativo, 4=Passivo, 6=PL, 7+8=Resultado)
 * a partir dos nodes nivel 1 do balancete. Soma de todos os 4 deve casar com
 * `reconciliacao.delta_pl_total` (modulo grupos 3/9 de compensacao e pendentes).
 */
function deltasPorGrupo(nodes: readonly CosifNode[]): {
  ativo: number
  passivo: number
  pl: number
  resultado: number  // soma 7 + 8
} {
  let ativo = 0, passivo = 0, pl = 0, resultado = 0
  for (const n of nodes) {
    if (n.nivel !== 1) continue
    if (n.grupo === 1) ativo += n.delta
    else if (n.grupo === 4) passivo += n.delta
    else if (n.grupo === 6) pl += n.delta
    else if (n.grupo === 7 || n.grupo === 8) resultado += n.delta
  }
  return { ativo, passivo, pl, resultado }
}

function buildSteps(r: Reconciliacao, nodes: readonly CosifNode[]): Step[] {
  const { ativo, passivo, pl, resultado } = deltasPorGrupo(nodes)
  // Contribuicoes na Cota Sub: 4 grupos do balancete + -ΔSr + -ΔMez.
  // Sinal aplicado AQUI — o valor exibido ja vem orientado pra Sub.
  const contribCotasSr = -r.delta_cotas_sr
  const contribCotasMez = -r.delta_cotas_mez

  // Residuo em pontos percentuais do PL Sub D-1
  const residuoPp =
    r.pl_cota_sub_d1 !== 0
      ? Math.abs(r.residuo) / Math.abs(r.pl_cota_sub_d1)
      : 0

  return [
    {
      kind:      "input",
      label:     "ΔAtivo",
      labelFull: "ΔAtivo (grupo 1)",
      value:     ativo,
      color:     ativo >= 0 ? COLOR_POSITIVE : COLOR_NEGATIVE,
      hint:      ativo >= 0
        ? "Ativo agregado cresceu — contribuicao positiva na Sub"
        : "Ativo agregado caiu — contribuicao negativa na Sub",
    },
    {
      kind:      "input",
      label:     "ΔPassivo",
      labelFull: "ΔPassivo (grupo 4)",
      value:     passivo,
      color:     passivo >= 0 ? COLOR_POSITIVE : COLOR_NEGATIVE,
      hint:      passivo >= 0
        ? "Passivo cresceu (mais obrigacoes) — atencao ao sinal contabil"
        : "Passivo reduziu (menos obrigacoes)",
    },
    {
      kind:      "input",
      label:     "ΔPL",
      labelFull: "ΔPatrimonio Liquido (grupo 6)",
      value:     pl,
      color:     pl >= 0 ? COLOR_POSITIVE : COLOR_NEGATIVE,
      hint:      pl >= 0
        ? "PL cresceu (mais aportes ou retencao de resultado)"
        : "PL reduziu (resgates ou prejuizo retido)",
    },
    {
      kind:      "input",
      label:     "ΔResultado",
      labelFull: "ΔResultado (grupos 7+8)",
      value:     resultado,
      color:     resultado >= 0 ? COLOR_POSITIVE : COLOR_NEGATIVE,
      hint:      resultado >= 0
        ? "Resultado do periodo positivo"
        : "Resultado do periodo negativo (despesa > receita)",
    },
    {
      kind:      "input",
      label:     "−ΔCotas Sr",
      labelFull: "Δ Cotas Senior emitidas",
      value:     contribCotasSr,
      color:     contribCotasSr >= 0 ? COLOR_POSITIVE : COLOR_NEGATIVE,
      hint:      r.delta_cotas_sr > 0
        ? "Senior aumentou emissao — sub diminui (sinal invertido)"
        : r.delta_cotas_sr < 0
          ? "Senior reduziu emissao — sub aumenta"
          : "Sem variacao em cotas Senior",
    },
    {
      kind:      "input",
      label:     "−ΔCotas Mez",
      labelFull: "Δ Cotas Mezanino emitidas",
      value:     contribCotasMez,
      color:     contribCotasMez >= 0 ? COLOR_POSITIVE : COLOR_NEGATIVE,
      hint:      r.delta_cotas_mez > 0
        ? "Mezanino aumentou emissao — sub diminui"
        : r.delta_cotas_mez < 0
          ? "Mezanino reduziu emissao — sub aumenta"
          : "Sem variacao em cotas Mezanino",
    },
    { kind: "gap", label: "", labelFull: "", value: 0, color: "transparent", hint: "" },
    {
      kind:      "expected",
      label:     "=Esperado",
      labelFull: "ΔPL Sub Esperado (= soma das 3 contribuicoes)",
      value:     r.delta_pl_cota_sub_esperado,
      color:     COLOR_NEUTRAL,
      hint:      "Soma das contribuicoes acima",
    },
    {
      kind:      "real",
      label:     "Real",
      labelFull: "ΔPL Sub Real (MEC — patrimonio da classe Sub)",
      value:     r.delta_pl_cota_sub_real,
      color:     COLOR_NEUTRAL,
      hint:      "Patrimonio da classe Sub no MEC (qtde × cota patrimonial), independente do balancete",
    },
    {
      kind:      "residuo",
      label:     "Residuo",
      labelFull: "Residuo (Real − Esperado)",
      value:     r.residuo,
      color:     residuoColor(residuoPp),
      hint:      residuoPp <= TOL_PP_OK
        ? "Dentro da tolerancia (<0,1pp) — balancete conciliado"
        : residuoPp <= TOL_PP_AMBER
          ? "Atencao — entre 0,1pp e 1pp do PL Sub"
          : "Acima da tolerancia (>1pp) — investigar pendentes/regras",
    },
  ]
}

function buildOption(steps: Step[]): EChartsOption {
  const categories = steps.map((s) => s.label)
  const data = steps.map((s) =>
    s.kind === "gap"
      ? { value: 0, itemStyle: { color: "transparent" } }
      : { value: s.value, itemStyle: { color: s.color, borderRadius: [3, 3, 3, 3] } },
  )

  // markArea: 2 grupos visuais (inputs e reconciliacao). Limites usam o
  // index do eixo X — primeira input = 0, ultima input = 5, gap = 6,
  // primeiro recon = 7, ultimo recon = 9.
  const markAreaData = [
    [
      {
        xAxis: categories[0],
        itemStyle: { color: COLOR_BG_INPUT },
        label: {
          show:       true,
          position:   "insideTop",
          color:      COLOR_GROUP_LABEL,
          fontSize:   11,
          fontWeight: 600,
          offset:     [0, 4],
          formatter:  "Contribuicoes",
        },
      },
      { xAxis: categories[5] },
    ],
    [
      {
        xAxis: categories[7],
        itemStyle: { color: COLOR_BG_RECON },
        label: {
          show:       true,
          position:   "insideTop",
          color:      COLOR_GROUP_LABEL,
          fontSize:   11,
          fontWeight: 600,
          offset:     [0, 4],
          formatter:  "Reconciliacao",
        },
      },
      { xAxis: categories[9] },
    ],
  ] as unknown

  return {
    grid: { top: 56, right: 20, bottom: 80, left: 72 },
    xAxis: {
      type: "category",
      data: categories,
      axisTick: { show: false },
      axisLabel: {
        interval: 0,
        fontSize: 10,
        fontWeight: 500,
        rotate: -30,
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
        const step = steps[list[0].dataIndex]
        if (!step || step.kind === "gap") return ""
        const sinal = step.value >= 0 ? "+" : ""
        return `<div style="font-size:12px"><strong>${step.labelFull}</strong><br/>${sinal}${fmtBRL.format(step.value)}<br/><span style="opacity:.7">${step.hint}</span></div>`
      },
    },
    series: [
      {
        name: "valor",
        type: "bar",
        barCategoryGap: "15%",
        data,
        markArea: { silent: true, data: markAreaData as never },
        label: {
          show:     true,
          fontSize: 10,
          fontWeight: 600,
          position: "top",
          formatter: (p: { dataIndex: number }) => {
            const s = steps[p.dataIndex]
            if (!s || s.kind === "gap") return ""
            const sinal = s.value >= 0 ? "+" : ""
            return `${sinal}${fmtBRLCompact.format(s.value)}`
          },
        },
      },
    ],
  }
}

export type ReconciliacaoWaterfallCardProps = {
  reconciliacao?: Reconciliacao
  /** Nodes do balancete — usados pra extrair Δ por grupo COSIF (1, 4, 6, 7+8). */
  nodes?:         readonly CosifNode[]
  loading?:       boolean
  error?:         string | null
  onRetry?:       () => void
  /** Quando false, renderiza overlay "Comparacao nao confiavel" + barras
   *  com opacity reduzida. Usuario ainda ve os valores mas com sinalizacao
   *  visual de que a comparacao pode estar distorcida. */
  comparable?:    boolean
  /** Mensagem detalhada do motivo (ex.: "D-1 (30/04) com snapshot parcial..."). */
  unreliableReason?: string | null
}

export function ReconciliacaoWaterfallCard({
  reconciliacao,
  nodes,
  loading,
  error,
  onRetry,
  comparable = true,
  unreliableReason,
}: ReconciliacaoWaterfallCardProps) {
  const steps = React.useMemo(
    () => (reconciliacao ? buildSteps(reconciliacao, nodes ?? []) : []),
    [reconciliacao, nodes],
  )
  const option = React.useMemo(() => buildOption(steps), [steps])

  const caption = React.useMemo(() => {
    if (!reconciliacao) return "Como o ΔPL Sub se decompoe e reconcilia"
    if (!comparable) {
      return "Comparacao nao confiavel — D-1 com snapshot parcial"
    }
    const sinal = reconciliacao.delta_pl_cota_sub_real >= 0 ? "+" : ""
    const valor = `${sinal}${fmtBRLCompact.format(reconciliacao.delta_pl_cota_sub_real)}`
    const pctSinal = reconciliacao.delta_pct_sobre_d1 >= 0 ? "+" : ""
    const pct = `${pctSinal}${reconciliacao.delta_pct_sobre_d1.toFixed(2).replace(".", ",")}%`
    return `Variacao Cota Sub: ${valor} | ${pct}`
  }, [reconciliacao, comparable])

  // Quando comparable=false, renderiza o card normalmente mas com:
  //   - opacity reduzida nas barras (sinaliza "nao confie")
  //   - badge no canto superior direito explicando
  // Solucao via wrapper relativo + ChartCard; EChartsCard nao expoe slot
  // overlay nativo, entao usamos position absolute.
  if (!comparable && reconciliacao) {
    return (
      <div
        className="relative"
        title={unreliableReason ?? "Comparacao nao confiavel"}
      >
        <div className="opacity-40 transition-opacity">
          <EChartsCard
            title="Reconciliacao da Cota Subordinada"
            caption={caption}
            option={option}
            height={300}
            loading={loading}
            error={error}
            onRetry={onRetry}
          />
        </div>
        <div className="pointer-events-none absolute right-3 top-3 z-10 inline-flex items-center gap-1 rounded-sm bg-red-50 px-2 py-0.5 text-[11px] font-medium text-red-700 dark:bg-red-500/10 dark:text-red-300">
          <span aria-hidden="true">⚠</span>
          Comparacao nao confiavel
        </div>
      </div>
    )
  }

  return (
    <EChartsCard
      title="Reconciliacao da Cota Subordinada"
      caption={caption}
      option={option}
      height={300}
      loading={loading}
      error={error}
      onRetry={onRetry}
    />
  )
}
