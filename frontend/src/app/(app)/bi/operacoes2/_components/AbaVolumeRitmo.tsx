// src/app/(app)/bi/operacoes2/_components/AbaVolumeRitmo.tsx
//
// Aba 1 da pagina /bi/operacoes2 — Volume & Ritmo.
//
// Estrutura (refatorada 2026-05-06):
//   Linha 1  · 3 colunas: Hero combo Evolucao Mensal (50%) +
//              QuebraTrendCard "VOP por UA" (25%) +
//              QuebraTrendCard "VOP por Produto" (25%). Hero tem seletor
//              LOCAL de UA (filtragem client-side a partir de
//              `evolucao_12m_por_ua` — sem nova ida ao backend).
//   Linha 2  · Hero Ritmo do mes corrente (50%) com lista textual de UAs
//              + card unificado "Projecao fim do mes" (25%) com Pace por
//              DU embutido na dl + KpisSecundariosTrendCard "Indicadores
//              secundarios" (25%): 4 KPIs (Nº ops, Ticket op., Ticket tit.,
//              VOP/DU) condensados em tabela densa com Δ MoM + sparkline
//              12M fechados. (degraded quando wh_dim_dia_util vazia)
//
// QuebraTrendCard / KpisSecundariosTrendCard: tabela densa com sparkline
// 12M FECHADOS (M-12 a M-1, exclui mes corrente parcial pra evitar queda
// brusca no ultimo ponto) + seta de tendencia. Modos:
//   - "share":   Produto — slope absoluto (pp/mes), threshold 0.3 pp/mes.
//                Detecta drift de mix entre categorias.
//   - "absolute": UA + KPIs secundarios — slope relativo (% sobre a media
//                 da propria serie), threshold 0.5%/mes. Apropriado quando
//                 categorias tem trajetoria propria de crescimento (UA) ou
//                 escalas heterogeneas (count vs BRL vs BRL/DU).

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import {
  RiArrowDownLine,
  RiArrowUpLine,
  RiBuilding2Line,
  RiCalendarEventLine,
  RiInformationLine,
  RiSubtractLine,
} from "@remixicon/react"
import type { EChartsOption } from "echarts"

import { Card } from "@/components/tremor/Card"
import { cardTokens } from "@/design-system/tokens/card"
import { EChartsCard } from "@/design-system/components/EChartsCard"
import {
  EvolucaoMensalCard,
  type EvolucaoMensalPonto,
} from "@/design-system/components/EvolucaoMensalCard"
import { tableTokens } from "@/design-system/tokens/table"
import { biOperacoes2 } from "@/lib/api-client"
import type {
  Operacoes2EvolucaoMensalPonto,
  Operacoes2EvolucaoPorUaPonto,
  Operacoes2KpiSecundario,
  Operacoes2KpisSecundariosVolume,
  Operacoes2MesDestaque,
  Operacoes2PaceDiario,
  Operacoes2QuebraDimensaoLinha,
  Operacoes2RitmoMesCorrente,
  Operacoes2RitmoUaItem,
} from "@/lib/api-client"
import { useBiFilters, type PresetKey } from "@/lib/hooks/useBiFilters"
import { cx } from "@/lib/utils"

// ─── Formatadores ──────────────────────────────────────────────────────────

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 2,
})
// Variante compact com 2 casas FORCADAS — usado no Pace diario do card
// "Projecao fim do mes" para evitar arredondamento enganoso (R$ 1,5 mi vs
// R$ 1,55 mi sao 50 mil de diferenca por DU).
const fmtBRL2 = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
const fmtBRLFull = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
})
const fmtInt = new Intl.NumberFormat("pt-BR")
const fmtPct1 = (v: number) => `${v.toFixed(1).replace(".", ",")}%`
// Formatador fixo em milhoes (sempre "X,XX mi") — usado quando a tabela
// precisa que TODAS as linhas tenham a mesma unidade, mesmo que isso resulte
// em "0,86 mi" para valores < 1 milhao. `notation: compact` adapta a unidade
// linha-a-linha ("864 mil" + "4,03 mi") e quebra a comparacao visual.
const fmtBRLMi = (v: number) =>
  `R$ ${(v / 1_000_000).toFixed(2).replace(".", ",")} mi`

/**
 * Linha de tendencia por regressao linear (minimos quadrados).
 * Devolve um array do mesmo tamanho de `values`, onde cada posicao i
 * contem o valor predito pela reta y = a + b*i.
 * Para n < 2 ou variancia zero em x, devolve uma linha horizontal na media.
 */
function computeLinearTrend(values: number[]): number[] {
  const n = values.length
  if (n === 0) return []
  if (n === 1) return [values[0]]
  let sumX = 0,
    sumY = 0,
    sumXY = 0,
    sumX2 = 0
  for (let i = 0; i < n; i++) {
    sumX += i
    sumY += values[i]
    sumXY += i * values[i]
    sumX2 += i * i
  }
  const denom = n * sumX2 - sumX * sumX
  if (denom === 0) {
    const mean = sumY / n
    return values.map(() => mean)
  }
  const slope = (n * sumXY - sumX * sumY) / denom
  const intercept = (sumY - slope * sumX) / n
  return values.map((_, i) => intercept + slope * i)
}

const PRESET_TO_LABEL: Record<PresetKey, string> = {
  ytd: "Ano até hoje",
  "3m": "Últimos 3 meses",
  "6m": "Últimos 6 meses",
  "12m": "Últimos 12 meses",
  "24m": "Últimos 24 meses",
  "36m": "Últimos 36 meses",
  all: "Todo histórico",
}

// ─── Componente principal ──────────────────────────────────────────────────

export function AbaVolumeRitmo() {
  const { filtersWithFocus, preset } = useBiFilters()
  const q = useQuery({
    queryKey: ["bi", "operacoes2", "aba1", filtersWithFocus],
    queryFn: () => biOperacoes2.abaVolumeRitmo(filtersWithFocus),
  })

  if (q.isLoading) return <AbaSkeleton />
  if (!q.data) return null
  const data = q.data.data

  return (
    <div className="flex flex-col gap-6">
      <Linha1HeroComUa
        evolucao={data.evolucao_12m}
        evolucaoPorUa={data.evolucao_12m_por_ua}
        melhorMes={data.melhor_mes}
        piorMes={data.pior_mes}
        ritmoDeltaPct={data.ritmo?.delta_pct ?? null}
        porUa={data.por_ua}
        porProduto={data.por_produto}
        presetLabel={preset ? PRESET_TO_LABEL[preset] : "Personalizado"}
      />
      <Linha2Ritmo
        ritmo={data.ritmo}
        pace={data.pace_diario}
        kpis={data.kpis_secundarios}
      />
    </div>
  )
}

function AbaSkeleton() {
  return (
    <div className="flex flex-col gap-6">
      {/* Linha 1: Hero Evolucao 50% + Quebra UA 25% + Quebra Produto 25% */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        <div className="h-64 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900 lg:col-span-2" />
        <div className="h-64 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
        <div className="h-64 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
      </div>
      {/* Linha 2: Hero Ritmo 50% + Projecao 25% + Indicadores 25% */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        <div className="h-72 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900 lg:col-span-2" />
        <div className="h-72 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
        <div className="h-72 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
      </div>
    </div>
  )
}

// ─── Linha 1 — 3 colunas: Hero Evolucao + Quebra UA + Quebra Produto ──────

function Linha1HeroComUa({
  evolucao,
  evolucaoPorUa,
  melhorMes,
  piorMes,
  ritmoDeltaPct,
  porUa,
  porProduto,
  presetLabel,
}: {
  evolucao: Operacoes2EvolucaoMensalPonto[]
  evolucaoPorUa: Operacoes2EvolucaoPorUaPonto[]
  melhorMes: Operacoes2MesDestaque | null
  piorMes: Operacoes2MesDestaque | null
  /**
   * MTD same-period: mes corrente N DUs vs mes anterior nos mesmos N DUs.
   * Vem de `ritmo.delta_pct`. `null` = sem base de comparacao.
   */
  ritmoDeltaPct: number | null
  porUa: Operacoes2QuebraDimensaoLinha[]
  porProduto: Operacoes2QuebraDimensaoLinha[]
  presetLabel: string
}) {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
      <div className="lg:col-span-2">
        <HeroEvolucao
          evolucao={evolucao}
          evolucaoPorUa={evolucaoPorUa}
          melhorMes={melhorMes}
          piorMes={piorMes}
          ritmoDeltaPct={ritmoDeltaPct}
          presetLabel={presetLabel}
        />
      </div>
      <QuebraTrendCard
        title="VOP por Unidade Administrativa"
        rows={porUa}
        topN={5}
        mode="absolute"
      />
      <QuebraTrendCard
        title="VOP por Produto"
        rows={porProduto}
        topN={5}
        mode="share"
      />
    </div>
  )
}

function HeroEvolucao({
  evolucao,
  evolucaoPorUa,
  melhorMes,
  piorMes,
  ritmoDeltaPct,
  presetLabel,
}: {
  evolucao: Operacoes2EvolucaoMensalPonto[]
  evolucaoPorUa: Operacoes2EvolucaoPorUaPonto[]
  melhorMes: Operacoes2MesDestaque | null
  piorMes: Operacoes2MesDestaque | null
  /** MTD same-period vs mes anterior. Vem de `ritmo.delta_pct`. */
  ritmoDeltaPct: number | null
  presetLabel: string
}) {
  // Seletor LOCAL de UA — nao mexe no filtro global (que ja existe na toolbar).
  // Funciona como "lente" para visualizar a evolucao 12M de uma UA especifica
  // ou agregada (Todas). Filtragem client-side a partir de `evolucaoPorUa`.
  const [selectedUaId, setSelectedUaId] = React.useState<number | null>(null)

  // Lista unica de UAs disponiveis (extraida da serie segmentada).
  const uaOptions = React.useMemo(() => {
    const map = new Map<number, string>()
    for (const p of evolucaoPorUa) {
      if (!map.has(p.ua_id)) map.set(p.ua_id, p.ua_nome)
    }
    return Array.from(map.entries())
      .map(([id, nome]) => ({ id, nome }))
      .sort((a, b) => a.nome.localeCompare(b.nome, "pt-BR"))
  }, [evolucaoPorUa])

  // Adapta a serie de dominio para o ponto canonico do EvolucaoMensalCard.
  // `comparativo` recebe a linha de tendencia (regressao linear sobre o VOP),
  // substituindo a antiga MM 3M.
  // Quando UA selecionada, n_operacoes/ticket_medio nao sao apurados por UA
  // hoje — entao tooltipExtras e omitido nesse caso.
  const data = React.useMemo<EvolucaoMensalPonto[]>(() => {
    const base =
      selectedUaId === null
        ? evolucao.map((p) => ({
            periodo: p.periodo,
            vop: p.vop,
            tooltipExtras: [
              { label: "Operações", value: fmtInt.format(p.n_operacoes) },
              { label: "Ticket médio", value: fmtBRLFull.format(p.ticket_medio) },
            ] as Array<{ label: string; value: string }>,
          }))
        : evolucaoPorUa
            .filter((p) => p.ua_id === selectedUaId)
            .map((p) => ({
              periodo: p.periodo,
              vop: p.vop,
              tooltipExtras: undefined as
                | Array<{ label: string; value: string }>
                | undefined,
            }))

    const trend = computeLinearTrend(base.map((p) => p.vop))
    return base.map((p, i) => ({
      periodo: p.periodo,
      valor: p.vop,
      comparativo: trend[i],
      tooltipExtras: p.tooltipExtras,
    }))
  }, [evolucao, evolucaoPorUa, selectedUaId])

  // headerKpi: VOP do mes corrente (ultimo ponto da serie filtrada) +
  // delta MTD same-period. Delta vem de `ritmoDeltaPct` (global) — quando uma
  // UA esta selecionada, o delta nao se aplica (ritmo e calculado no
  // agregado), entao suprimimos para nao mostrar numero enganoso.
  const headerKpi = React.useMemo(() => {
    const last = data[data.length - 1]
    if (!last || last.valor == null) return undefined
    return {
      value: fmtBRLFull.format(last.valor),
      delta:
        selectedUaId === null && ritmoDeltaPct != null
          ? { value: ritmoDeltaPct, suffix: "%" }
          : undefined,
      deltaSub: selectedUaId === null && ritmoDeltaPct != null ? "MTD" : undefined,
    }
  }, [data, ritmoDeltaPct, selectedUaId])

  return (
    <EvolucaoMensalCard
      title="Evolução do VOP"
      presetLabel={presetLabel}
      data={data}
      headerKpi={headerKpi}
      dimension={{
        label: "UA",
        icon: RiBuilding2Line,
        options: uaOptions,
        value: selectedUaId,
        onChange: (v) => setSelectedUaId(v as number | null),
        allLabel: "Todas as UAs",
      }}
      comparativoLabel="Tendência"
      destaques={{
        melhor: melhorMes
          ? { periodo: melhorMes.periodo, valor: melhorMes.vop }
          : null,
        pior: piorMes
          ? { periodo: piorMes.periodo, valor: piorMes.vop }
          : null,
        vsMesAnterior:
          ritmoDeltaPct != null ? { pct: ritmoDeltaPct } : null,
      }}
      valueFormatter={(v) => fmtBRLFull.format(v)}
      axisFormatter={(v) => fmtBRL.format(v)}
      dataLabelFormatter={(v) =>
        (v / 1_000_000).toFixed(1).replace(".", ",")
      }
      height={248}
    />
  )
}

// ─── Linha 2 (Padrao B) — Ritmo + Projecao + Pace ─────────────────────────

function Linha2Ritmo({
  ritmo,
  pace,
  kpis,
}: {
  ritmo: Operacoes2RitmoMesCorrente | null
  pace: Operacoes2PaceDiario | null
  kpis: Operacoes2KpisSecundariosVolume
}) {
  if (!ritmo) {
    return <Linha2Empty />
  }
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
      <Linha2HeroRitmo ritmo={ritmo} className="lg:col-span-6" />
      <Linha2Projecao
        ritmo={ritmo}
        pace={pace}
        className="lg:col-span-3"
      />
      <KpisSecundariosTrendCard
        kpis={kpis}
        className="lg:col-span-3"
      />
    </div>
  )
}

function Linha2Empty() {
  return (
    <Card className="flex flex-col items-center justify-center gap-2 px-6 py-10 text-center">
      <RiCalendarEventLine
        className="size-8 text-gray-300 dark:text-gray-700"
        aria-hidden="true"
      />
      <p className="text-sm font-medium text-gray-700 dark:text-gray-200">
        Ritmo do mês corrente · indisponível
      </p>
      <p className="max-w-md text-xs text-gray-500 dark:text-gray-400">
        Esta análise depende de <code>wh_dim_dia_util</code>. Rode{" "}
        <code className="rounded bg-gray-100 px-1 py-0.5 dark:bg-gray-800">
          python -m scripts.populate_dia_util --tenant a7-credit
        </code>{" "}
        para popular o calendário (feriados nacionais via Bitfin).
      </p>
    </Card>
  )
}

function Linha2HeroRitmo({
  ritmo,
  className,
}: {
  ritmo: Operacoes2RitmoMesCorrente
  className?: string
}) {
  const deltaTxt =
    ritmo.delta_pct == null
      ? "—"
      : `${ritmo.delta_pct >= 0 ? "+" : ""}${fmtPct1(ritmo.delta_pct)}`
  const isAhead = (ritmo.delta_pct ?? 0) >= 0
  const badgeClass = isAhead
    ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
    : "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300"

  // Mini chart acumulado dia-a-dia.
  // `legend: { show: false }` suprime a legenda nativa do ECharts — o tema
  // default (echarts-theme.ts) injeta um `legend` style que ECharts renderiza
  // no rodape e duplica os chips abaixo. As labels viram <ChartLegendChip />
  // acima do canvas, liberando ~30px verticais. Cores aqui DEVEM bater com
  // os strokes dos chips (#2A4D7A solido + #9CA3AF tracejado).
  const option: EChartsOption = {
    grid: { top: 8, right: 8, bottom: 24, left: 56 },
    legend: { show: false },
    tooltip: { trigger: "axis" },
    xAxis: {
      type: "category",
      data: ritmo.acumulado_dia_a_dia.map((p) => `DU ${p.du_index}`),
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      axisLabel: { formatter: (v: number) => fmtBRL.format(v) },
    },
    series: [
      {
        name: "Mês corrente",
        type: "line",
        smooth: true,
        symbol: "none",
        data: ritmo.acumulado_dia_a_dia.map((p) => p.corrente),
        lineStyle: { color: "#2A4D7A", width: 2 },
      },
      {
        name: "Mês anterior",
        type: "line",
        smooth: true,
        symbol: "none",
        data: ritmo.acumulado_dia_a_dia.map((p) => p.anterior),
        lineStyle: { color: "#9CA3AF", width: 1.5, type: "dashed" },
      },
    ],
  }

  return (
    <Card className={cx("flex flex-col gap-3 p-5", className)}>
      <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
        Ritmo do mês corrente
      </p>
      <p className="text-[18px] font-semibold leading-snug text-gray-900 dark:text-gray-50">
        Estamos{" "}
        <span
          className={cx(
            "inline-flex items-center rounded px-1.5 py-0.5 text-[16px] tabular-nums",
            badgeClass,
          )}
        >
          {deltaTxt}
        </span>{" "}
        <span className="text-gray-700 dark:text-gray-300">
          {isAhead ? "à frente" : "atrás"}
        </span>{" "}
        do mês anterior nos mesmos {ritmo.du_corridos} dias úteis.
      </p>
      {ritmo.ritmo_por_ua.length > 0 && (
        <p className="text-[11px] text-gray-500 dark:text-gray-400">
          {ritmo.ritmo_por_ua.map((ua, idx) => (
            <React.Fragment key={ua.ua_id}>
              {idx > 0 && (
                <span className="mx-2 text-gray-300 dark:text-gray-700">
                  |
                </span>
              )}
              <RitmoUaInline ua={ua} />
            </React.Fragment>
          ))}
        </p>
      )}
      <div className="flex items-center gap-3 text-[11px] text-gray-600 dark:text-gray-300">
        <ChartLegendChip stroke="#2A4D7A" label="Mês corrente" />
        <ChartLegendChip stroke="#9CA3AF" label="Mês anterior" dashed />
      </div>
      <div className="-mx-2 mt-1">
        <EChartsCardInline option={option} height={200} />
      </div>
    </Card>
  )
}

function RitmoUaInline({ ua }: { ua: Operacoes2RitmoUaItem }) {
  const hasDelta = ua.delta_pct != null
  const isUp = hasDelta && ua.delta_pct! >= 0
  const colorClass = !hasDelta
    ? "text-gray-400 dark:text-gray-600"
    : isUp
      ? "text-emerald-600 dark:text-emerald-400"
      : "text-red-600 dark:text-red-400"
  const deltaTxt = !hasDelta
    ? "sem base de comparação"
    : `${isUp ? "+" : ""}${fmtPct1(ua.delta_pct!)} ${isUp ? "à frente" : "atrás"}`
  return (
    <>
      <strong className="text-gray-900 dark:text-gray-50">{ua.ua_nome}</strong>
      :{" "}
      <strong className="tabular-nums text-gray-900 dark:text-gray-50">
        {fmtBRLMi(ua.vop_corrente)}
      </strong>{" "}
      ·{" "}
      <span
        className={cx("tabular-nums font-medium", colorClass)}
        title={hasDelta ? "vs mesmo nº DUs do mês anterior" : undefined}
      >
        {deltaTxt}
      </span>
    </>
  )
}

function Linha2Projecao({
  ritmo,
  pace,
  className,
}: {
  ritmo: Operacoes2RitmoMesCorrente
  pace: Operacoes2PaceDiario | null
  className?: string
}) {
  const restantes = Math.max(0, ritmo.du_total_mes - ritmo.du_corridos)
  return (
    <Card className={cx("flex flex-col gap-3 p-5", className)}>
      <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
        Projeção fim do mês
      </p>
      <p className="text-[24px] font-semibold leading-none tabular-nums text-gray-900 dark:text-gray-50">
        {fmtBRLFull.format(ritmo.projecao_fim_mes)}
      </p>
      <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[11px]">
        <dt className="text-gray-500 dark:text-gray-400">VOP atual</dt>
        <dd className="text-right tabular-nums text-gray-900 dark:text-gray-50">
          {fmtBRL.format(ritmo.vop_acumulado)}
        </dd>

        <dt className="text-gray-500 dark:text-gray-400">Pace por DU</dt>
        <dd
          className="flex items-baseline justify-end gap-1.5"
          title={
            pace
              ? `Mês anterior: ${fmtBRL2.format(pace.vop_du_anterior)} / DU`
              : "Indisponível"
          }
        >
          {pace ? (
            <>
              <span className="tabular-nums text-gray-900 dark:text-gray-50">
                {fmtBRL2.format(pace.vop_du_corrente)}
              </span>
              <PaceMomBadge value={pace.delta_pct} />
            </>
          ) : (
            <span className="tabular-nums text-gray-400 dark:text-gray-600">
              —
            </span>
          )}
        </dd>

        <dt className="text-gray-500 dark:text-gray-400">DUs corridos</dt>
        <dd className="text-right tabular-nums text-gray-900 dark:text-gray-50">
          {ritmo.du_corridos} / {ritmo.du_total_mes}
        </dd>
        <dt className="text-gray-500 dark:text-gray-400">DUs restantes</dt>
        <dd className="text-right tabular-nums text-gray-900 dark:text-gray-50">
          {restantes}
        </dd>
      </dl>
    </Card>
  )
}

function PaceMomBadge({ value }: { value: number | null }) {
  if (value == null) {
    return (
      <span className="tabular-nums text-[10px] font-medium text-gray-400 dark:text-gray-600">
        —
      </span>
    )
  }
  const isUp = value >= 0
  const colorClass = isUp
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-red-600 dark:text-red-400"
  return (
    <span
      className={cx("tabular-nums text-[10px] font-medium", colorClass)}
      title="vs mês anterior"
    >
      {isUp ? "+" : ""}
      {fmtPct1(value)}
    </span>
  )
}

// ─── QuebraTrendCard — Tabela trend densa por categoria ──────────────────
//
// Substitui o donut + lista vitrine antigos. Mostra top N categorias do mes
// corrente com sparkline 12M + seta de tendencia. "Outros" agregado no
// rodape sem sparkline.
//
// Dois modos de analise (escolhidos por dimensao):
//
//   mode="share" (Produto): o que importa e o DRIFT DE MIX entre categorias
//     dentro de uma carteira que cresce no agregado. Coluna "%Mes" mostra
//     share do mes; sparkline = share% mes a mes (12M); slope absoluto em
//     pp/mes. Threshold 0.3 pp/mes filtra ruido mensal.
//
//   mode="absolute" (UA): cada categoria tem TRAJETORIA propria — RealInvest
//     cresce com mercado de capitais, A7 fica estavel como securitizadora.
//     Share dentro do total da carteira da falso negativo (RealInvest puxa
//     A7 pra baixo em share mesmo quando A7 mantem VOP). Coluna "VOP Mes"
//     mostra valor absoluto BRL; sparkline = VOP absoluto mes a mes; slope
//     RELATIVO a media da propria serie (% sobre a media), permitindo
//     comparar UAs de escalas muito diferentes. Threshold 0.5%/mes (~6%/ano).
//
// Por que nao DataTableShell aqui: aquele componente traz toolbar, filtro
// global e SegmentSwitch — overhead total para uma vitrine de 5 linhas
// dentro de coluna de 25%. Mantemos um grid de divs alinhados (mesma
// abordagem da QuebraCard antiga, justificada na §6 do CLAUDE.md).

type QuebraTrendMode = "share" | "absolute"

// ECharts nao alcanca o canvas do SVG inline da sparkline (renderizamos a
// linha em <svg> direto). Os 3 hex sao da paleta canonica do CLAUDE.md
// §4 (emerald-600, red-600, gray-400) — espelhados aqui pra usar como
// stroke do <path>, mesma excecao usada nas EChartsOption.
const TREND_STROKE_UP = "#059669"
const TREND_STROKE_DOWN = "#DC2626"
const TREND_STROKE_FLAT = "#9CA3AF"

// Threshold em unidades absolutas (pp/mes) para slope sobre share%.
const TREND_THRESHOLD_PP_PER_MONTH = 0.3
// Threshold em % sobre a media da serie (%/mes) para slope sobre VOP
// absoluto. ~0.5%/mes corresponde a ~6%/ano linear — abaixo disso considera
// estavel pra absorver ruido sazonal de carteira.
const TREND_THRESHOLD_REL_PER_MONTH = 0.5

// Larguras fixas em col 3 (numero) e col 4 (Tend.) para garantir alinhamento
// vertical entre header e data rows. Header e cada data row sao grids
// independentes — `auto` deixava as colunas dimensionando ao conteudo da
// propria row, desalinhando label do header com numero da celula.
//   - 72px em col 3: cabe "100,0%" e tambem "R$ 100,0 mi" em 12px tabular.
//   - 72px em col 4: sparkline 48px + gap 4px + seta 14px (size-3.5) = 66px,
//     com folga pro overflow-visible do SVG.
const TREND_ROW_GRID =
  "grid grid-cols-[16px_minmax(0,1fr)_72px_72px] items-center gap-x-2"

function QuebraTrendCard({
  title,
  rows,
  topN,
  mode,
}: {
  title: string
  rows: Operacoes2QuebraDimensaoLinha[]
  topN: number
  mode: QuebraTrendMode
}) {
  const { top, outros, outrosValor } = React.useMemo(() => {
    const sortKey: keyof Operacoes2QuebraDimensaoLinha =
      mode === "share" ? "pct_mes_corrente" : "vop_mes_corrente"
    const sorted = [...rows].sort(
      (a, b) => (b[sortKey] as number) - (a[sortKey] as number),
    )
    const _top = sorted.slice(0, topN)
    const _outros = sorted.slice(topN)
    const _outrosValor = _outros.reduce(
      (acc, r) => acc + (r[sortKey] as number),
      0,
    )
    return { top: _top, outros: _outros, outrosValor: _outrosValor }
  }, [rows, topN, mode])

  const headerCol3 = mode === "share" ? "%Mês" : "VOP Mês"
  const subtitle =
    mode === "share"
      ? "participação % · tendência 12M fechados"
      : "VOP do mês · tendência 12M fechados (vs própria média)"
  const fmtOutros = (v: number) =>
    mode === "share" ? fmtPct1(v) : fmtBRLMi(v)

  if (top.length === 0) {
    return (
      <Card className="flex flex-col p-0">
        <div className={cardTokens.header}>
          <h3 className={cardTokens.headerTitle}>{title}</h3>
        </div>
        <div className={cardTokens.body}>
          <p className={cx(tableTokens.cellMuted, "py-6 text-center")}>
            Sem dados no período.
          </p>
        </div>
      </Card>
    )
  }

  return (
    <Card className="flex flex-col p-0">
      <div className={cardTokens.header}>
        <h3 className={cardTokens.headerTitle}>{title}</h3>
        <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
          Top {top.length} · {subtitle}
        </p>
      </div>

      <div className={cx(cardTokens.body, "flex flex-col gap-2")}>
        {/* Header row */}
        <div
          className={cx(
            TREND_ROW_GRID,
            "border-b border-gray-100 pb-1.5 text-gray-500 dark:border-gray-900 dark:text-gray-400",
            tableTokens.header,
          )}
        >
          <span className="text-right">#</span>
          <span>Categoria</span>
          <span className="text-right">{headerCol3}</span>
          <span
            className="flex items-center justify-end gap-0.5"
            title="Tendência calculada sobre os últimos 12 meses fechados (M-12 a M-1). O mês corrente parcial fica fora do cálculo para evitar distorção em consultas no início do mês — o valor MTD aparece na coluna ao lado."
          >
            Tend.
            <RiInformationLine
              aria-hidden="true"
              className="size-3 text-gray-400 dark:text-gray-600"
            />
          </span>
        </div>

        {/* Data rows */}
        <div className="flex flex-col gap-1">
          {top.map((r, i) => (
            <TrendRow key={r.categoria_id} row={r} rank={i + 1} mode={mode} />
          ))}
          {outros.length > 0 && outrosValor > 0 && (
            <div
              className={cx(
                TREND_ROW_GRID,
                "border-t-gray-100 dark:border-t-gray-900 border-t pt-1.5",
              )}
            >
              <span aria-hidden="true" />
              <span className={cx(tableTokens.cellSecondary, "truncate")}>
                Outros ({outros.length})
              </span>
              <span
                className={cx(tableTokens.cellNumberSecondary, "text-right")}
              >
                {fmtOutros(outrosValor)}
              </span>
              <span aria-hidden="true" />
            </div>
          )}
        </div>
      </div>
    </Card>
  )
}

function TrendRow({
  row,
  rank,
  mode,
}: {
  row: Operacoes2QuebraDimensaoLinha
  rank: number
  mode: QuebraTrendMode
}) {
  const values =
    mode === "share"
      ? row.sparkline_share_12m.map((p) => p.valor)
      : row.sparkline_vop_12m.map((p) => p.valor)
  const trend = computeTrendDirection(
    values,
    mode === "share"
      ? TREND_THRESHOLD_PP_PER_MONTH
      : TREND_THRESHOLD_REL_PER_MONTH,
    mode === "share" ? "absolute" : "relative",
  )
  const stroke =
    trend.direction === "up"
      ? TREND_STROKE_UP
      : trend.direction === "down"
        ? TREND_STROKE_DOWN
        : TREND_STROKE_FLAT
  const trendTextClass =
    trend.direction === "up"
      ? "text-emerald-600 dark:text-emerald-400"
      : trend.direction === "down"
        ? "text-red-600 dark:text-red-400"
        : "text-gray-400 dark:text-gray-600"
  const ArrowIcon =
    trend.direction === "up"
      ? RiArrowUpLine
      : trend.direction === "down"
        ? RiArrowDownLine
        : RiSubtractLine
  const slopeTxt =
    mode === "share"
      ? `${trend.measure >= 0 ? "+" : ""}${trend.measure.toFixed(2).replace(".", ",")} pp/mês (12M)`
      : `${trend.measure >= 0 ? "+" : ""}${trend.measure.toFixed(1).replace(".", ",")}% / mês (12M, vs média)`
  const numberCell =
    mode === "share"
      ? fmtPct1(row.pct_mes_corrente)
      : fmtBRLMi(row.vop_mes_corrente)

  return (
    <div className={cx(TREND_ROW_GRID, "py-0.5")}>
      <span className={cx(tableTokens.cellNumberSecondary, "text-right")}>
        {rank}
      </span>
      <span className={cx(tableTokens.cellText, "truncate")} title={row.categoria}>
        {row.categoria}
      </span>
      <span className={cx(tableTokens.cellNumber, "text-right")}>
        {numberCell}
      </span>
      <span
        className="inline-flex items-center justify-end gap-1"
        title={slopeTxt}
      >
        <MiniSparkline values={values} stroke={stroke} />
        <ArrowIcon
          className={cx("size-3.5", trendTextClass)}
          aria-label={slopeTxt}
        />
      </span>
    </div>
  )
}

function MiniSparkline({
  values,
  stroke,
  width = 48,
}: {
  values: number[]
  stroke: string
  /** Largura em px do SVG. Default 48 (cabe em coluna trend de 72px). */
  width?: number
}) {
  const height = 16
  if (values.length < 2) {
    return (
      <span className={cx(tableTokens.cellMuted)} aria-hidden="true">
        —
      </span>
    )
  }
  const min = Math.min(...values)
  const max = Math.max(...values)
  const range = max - min || 1
  const stepX = width / (values.length - 1)
  const path = values
    .map((v, i) => {
      const x = i * stepX
      const y = height - ((v - min) / range) * height
      return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`
    })
    .join(" ")
  return (
    <svg
      width={width}
      height={height}
      className="overflow-visible"
      aria-hidden="true"
    >
      <path
        d={path}
        fill="none"
        stroke={stroke}
        strokeWidth="1.25"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

/**
 * Slope da regressao linear sobre os valores do sparkline 12M (eixo X =
 * indice mensal 0..N-1). Usado para classificar tendencia em up/down/flat.
 *
 * Dois modos de comparacao com o threshold:
 * - "absolute": compara o slope direto (em unidades da serie por mes — ex.:
 *   pp/mes para sparkline de share%). Apropriado quando a serie tem
 *   unidade comparavel entre categorias (todas sao share%).
 * - "relative": compara o slope normalizado pela MEDIA da propria serie,
 *   resultando em "% sobre a media por mes". Apropriado quando categorias
 *   tem escalas muito diferentes (ex.: VOP absoluto: RealInvest R$ 100M
 *   vs A7 R$ 20M — slope absoluto de R$ 1M/mes significa coisa muito
 *   diferente em cada). A comparacao "categoria vs ela mesma" e
 *   intrinsecamente relativa.
 *
 * `measure` no retorno e o valor usado contra o threshold (slope ou
 * slope normalizado), util pro tooltip mostrar "+0,42 pp/mes" ou
 * "+1,2% / mes".
 */
function computeTrendDirection(
  values: number[],
  threshold: number,
  compareMode: "absolute" | "relative",
): { direction: "up" | "down" | "flat"; measure: number } {
  if (values.length < 2) return { direction: "flat", measure: 0 }
  let sumX = 0,
    sumY = 0,
    sumXY = 0,
    sumX2 = 0
  for (let i = 0; i < values.length; i++) {
    sumX += i
    sumY += values[i]
    sumXY += i * values[i]
    sumX2 += i * i
  }
  const n = values.length
  const denom = n * sumX2 - sumX * sumX
  if (denom === 0) return { direction: "flat", measure: 0 }
  const slope = (n * sumXY - sumX * sumY) / denom
  let measure: number
  if (compareMode === "relative") {
    const mean = sumY / n
    if (mean === 0) return { direction: "flat", measure: 0 }
    measure = (slope / mean) * 100
  } else {
    measure = slope
  }
  if (measure > threshold) return { direction: "up", measure }
  if (measure < -threshold) return { direction: "down", measure }
  return { direction: "flat", measure }
}

// ─── KpisSecundariosTrendCard — 4 indicadores condensados em tabela ──────
//
// Substitui a antiga Linha 3 (4 cards horizontais com valor + Δ MoM).
// Cabe em coluna de 25% gracas a labels abreviadas + valor/MoM empilhados
// na mesma celula + sparkline reduzido (36px). Cada item tem `labelLong`
// no `title=` da row para acessibilidade quando o nome curto nao for obvio.
//
// Cada KPI tem unidade/escala diferente (count, BRL, BRL/titulo, BRL/DU),
// entao o slope da sparkline usa modo "relative" — % sobre a media da
// propria serie — analogo ao card "VOP por UA" (mode="absolute").
//
// `vop_du_medio` pode ser null em degraded mode (wh_dim_dia_util vazia) —
// row mostra hint inline cobrindo as 2 colunas finais.

// Grid de 5 colunas dimensionado para coluna de 25% (~210-260px uteis):
//   - 14px: rank
//   - flex: label abreviada (truncate em viewports apertados)
//   - 72px: valor (cabe "R$ 142.973" em fmtBRLFull com folga)
//   - 44px: Δ MoM (cabe "+41,1%" em ~42px tabular)
//   - 56px: sparkline (36px) + seta (14px) + gap 4px = 54px
//   - gap-x-2 (8px) entre colunas para respiro visivel
// Total fixo: 14+72+44+56 + 4*8 = 218px → sobra ~0-50px para label flex.
// Em viewport <=1280px, label pode truncar — alternativa e migrar Linha 5
// para `lg:grid-cols-3` (card em 33%) liberando ~50px adicionais.
const TREND_KPI_ROW_GRID =
  "grid grid-cols-[14px_minmax(0,1fr)_72px_44px_56px] items-center gap-x-2"
const TREND_KPI_SPARKLINE_W = 36

type KpiSecundarioItem = {
  id: string
  label: string
  labelLong: string
  kpi: Operacoes2KpiSecundario | null
  format: (v: number) => string
  unavailableHint?: string
}

function KpisSecundariosTrendCard({
  kpis,
  className,
}: {
  kpis: Operacoes2KpisSecundariosVolume
  className?: string
}) {
  const items: KpiSecundarioItem[] = [
    {
      id: "n-ops",
      label: "Nº Op.",
      labelLong: "Nº de operações",
      kpi: kpis.n_operacoes,
      format: (v) => fmtInt.format(v),
    },
    {
      id: "ticket-op",
      label: "TM Op.",
      labelLong: "Ticket médio (op.)",
      kpi: kpis.ticket_op,
      format: (v) => fmtBRLFull.format(v),
    },
    {
      id: "ticket-titulo",
      label: "TM Tit.",
      labelLong: "Ticket médio (título)",
      kpi: kpis.ticket_titulo,
      format: (v) => fmtBRLFull.format(v),
    },
    {
      id: "vop-du",
      label: "VOP DU",
      labelLong: "VOP por DU médio",
      kpi: kpis.vop_du_medio,
      format: (v) => fmtBRL.format(v),
      unavailableHint: "Depende de wh_dim_dia_util",
    },
  ]

  return (
    <Card className={cx("flex flex-col p-0", className)}>
      <div className={cardTokens.header}>
        <h3 className={cardTokens.headerTitle}>Indicadores secundários</h3>
        <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
          valor · Δ MoM · tendência 12M fech.
        </p>
      </div>

      <div className={cx(cardTokens.body, "flex flex-col gap-2")}>
        {/* Header row */}
        <div
          className={cx(
            TREND_KPI_ROW_GRID,
            "border-b border-gray-100 pb-1.5 text-gray-500 dark:border-gray-900 dark:text-gray-400",
            tableTokens.header,
          )}
        >
          <span className="text-right">#</span>
          <span>Indicador</span>
          <span className="text-right">Valor</span>
          <span className="text-right">MoM</span>
          <span
            className="flex items-center justify-end gap-0.5"
            title="Tendência calculada sobre os últimos 12 meses fechados (M-12 a M-1). O mês corrente parcial fica fora do cálculo. Slope relativo à média da própria série (cada KPI tem escala diferente)."
          >
            Tend.
            <RiInformationLine
              aria-hidden="true"
              className="size-3 text-gray-400 dark:text-gray-600"
            />
          </span>
        </div>

        {/* Data rows */}
        <div className="flex flex-col gap-1">
          {items.map((it, i) => (
            <KpiSecundarioRow key={it.id} item={it} rank={i + 1} />
          ))}
        </div>
      </div>
    </Card>
  )
}

function KpiSecundarioRow({
  item,
  rank,
}: {
  item: KpiSecundarioItem
  rank: number
}) {
  if (!item.kpi) {
    return (
      <div className={cx(TREND_KPI_ROW_GRID, "py-0.5")}>
        <span className={cx(tableTokens.cellNumberSecondary, "text-right")}>
          {rank}
        </span>
        <span
          className={cx(tableTokens.cellText, "truncate")}
          title={item.labelLong}
        >
          {item.label}
        </span>
        <span
          className={cx(
            tableTokens.cellMuted,
            "col-span-3 text-right italic truncate",
          )}
          title={item.unavailableHint ?? "—"}
        >
          {item.unavailableHint ?? "—"}
        </span>
      </div>
    )
  }

  const values = item.kpi.sparkline_12m.map((p) => p.valor)
  const trend = computeTrendDirection(
    values,
    TREND_THRESHOLD_REL_PER_MONTH,
    "relative",
  )
  const stroke =
    trend.direction === "up"
      ? TREND_STROKE_UP
      : trend.direction === "down"
        ? TREND_STROKE_DOWN
        : TREND_STROKE_FLAT
  const trendTextClass =
    trend.direction === "up"
      ? "text-emerald-600 dark:text-emerald-400"
      : trend.direction === "down"
        ? "text-red-600 dark:text-red-400"
        : "text-gray-400 dark:text-gray-600"
  const ArrowIcon =
    trend.direction === "up"
      ? RiArrowUpLine
      : trend.direction === "down"
        ? RiArrowDownLine
        : RiSubtractLine
  const slopeTxt = `${trend.measure >= 0 ? "+" : ""}${trend.measure.toFixed(1).replace(".", ",")}% / mês (12M, vs média)`

  const deltaPct = item.kpi.delta_pct
  const momTxt =
    deltaPct == null
      ? "—"
      : `${deltaPct >= 0 ? "+" : ""}${fmtPct1(deltaPct)}`
  const momClass =
    deltaPct == null
      ? "text-gray-400 dark:text-gray-600"
      : deltaPct >= 0
        ? "text-emerald-600 dark:text-emerald-400"
        : "text-red-600 dark:text-red-400"
  const valueMomTitle = `${item.labelLong} — Δ MoM ${momTxt}`

  return (
    <div className={cx(TREND_KPI_ROW_GRID, "py-0.5")}>
      <span className={cx(tableTokens.cellNumberSecondary, "text-right")}>
        {rank}
      </span>
      <span
        className={cx(tableTokens.cellText, "truncate")}
        title={item.labelLong}
      >
        {item.label}
      </span>
      <span
        className={cx(tableTokens.cellNumber, "text-right truncate")}
        title={valueMomTitle}
      >
        {item.format(item.kpi.valor)}
      </span>
      <span
        className={cx(
          "text-right tabular-nums text-xs font-medium truncate",
          momClass,
        )}
        title={`Δ MoM ${momTxt}`}
      >
        {momTxt}
      </span>
      <span
        className="inline-flex items-center justify-end gap-1"
        title={slopeTxt}
      >
        <MiniSparkline
          values={values}
          stroke={stroke}
          width={TREND_KPI_SPARKLINE_W}
        />
        <ArrowIcon
          className={cx("size-3.5", trendTextClass)}
          aria-label={slopeTxt}
        />
      </span>
    </div>
  )
}

// ─── EChartsCardInline (sem moldura — usado dentro de outras cards) ───────

function EChartsCardInline({
  option,
  height,
}: {
  option: EChartsOption
  height: number
}) {
  return (
    <EChartsCard
      option={option}
      height={height}
      className="border-0 bg-transparent p-0 shadow-none"
    />
  )
}

// ─── ChartLegendChip — label de serie fora do canvas ECharts ─────────────
//
// Substitui a `legend` nativa quando o card e estreito e a legenda nativa
// rouba area do grafico. SVG line reflete o stroke real da serie (cor +
// dashing) — o usuario associa visualmente. Hex literal e exceção §4 porque
// e a MESMA cor literal usada dentro do EChartsOption (chart canvas nao
// alcanca Tailwind), entao tokenizar na classe Tailwind quebraria a paridade.
function ChartLegendChip({
  stroke,
  label,
  dashed = false,
}: {
  stroke: string
  label: string
  dashed?: boolean
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <svg width="14" height="2" viewBox="0 0 14 2" aria-hidden="true">
        <line
          x1="0"
          y1="1"
          x2="14"
          y2="1"
          stroke={stroke}
          strokeWidth={dashed ? 1.5 : 2}
          strokeDasharray={dashed ? "3 2" : undefined}
        />
      </svg>
      {label}
    </span>
  )
}
