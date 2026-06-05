// VariacaoDiariaCard.tsx — coluna MASTER da aba "Resumo do dia" (/controladoria/cota-sub).
//
// Grafico de COLUNAS da variacao diaria da cota sub (R$ por dia, dentro da
// competencia), no padrao canonico: reusa `EvolucaoDiariaCard` (DS) -> EChartsCard.
// E o MASTER do master-detail: clicar num dia chama `onSelectDia(dataISO)`, que
// a pagina usa pra re-chavear `useVariacaoResumo(fundoId, dia)` — o waterfall
// (`VariacaoWaterfall`) e a tabela (`ResumoGrupos`) re-renderizam pro dia escolhido.
//
// Variacao diaria pode ser NEGATIVA — `EvolucaoDiariaCard` trata barras abaixo
// do zero. Dias sem apuracao (fim de semana, feriado, futuro) entram como
// `valor: null` (slot reservado no eixo X, sem barra).

"use client"

import * as React from "react"

import { EvolucaoDiariaCard, type EvolucaoDiariaPonto } from "@/design-system/components"
import type { VariacaoDiariaSeriePonto } from "@/lib/api-client"

const fmtBRLFull = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 2,
})

// Eixo Y / labels — milhares compactos com sinal, sem prefixo "R$" (a unidade
// fica implicita no header). Zero suprimido pra nao poluir a origem.
function fmtMilharesAxis(v: number): string {
  if (v === 0) return "0"
  const k = v / 1000
  const s = v > 0 ? "+" : "−"
  return `${s}${Math.abs(k).toFixed(0)}k`
}
function fmtMilharesLabel(v: number): string {
  if (!v) return ""
  return fmtMilharesAxis(v)
}

const _MESES = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]
function competenciaLabel(iso: string): string {
  const [y, m] = iso.split("-").map(Number)
  if (!y || !m) return ""
  return `${_MESES[m - 1]}/${y}`
}

export type VariacaoDiariaCardProps = {
  /** Serie diaria da competencia (uma entrada por dia do mes). */
  serie: VariacaoDiariaSeriePonto[]
  /** Dia atualmente selecionado (ISO "YYYY-MM-DD"). Destaca a coluna. */
  diaSelecionado: string
  /** Callback ao clicar num dia — a pagina re-chaveia o resumo. */
  onSelectDia: (dataISO: string) => void
  loading?: boolean
}

export function VariacaoDiariaCard({
  serie,
  diaSelecionado,
  onSelectDia,
  loading,
}: VariacaoDiariaCardProps) {
  const data = React.useMemo<EvolucaoDiariaPonto[]>(
    () =>
      serie.map((p) => ({
        data: p.data,
        valor: p.variacao_cota, // R$ (pode ser negativo); null = sem apuracao
        ehDiaUtil: p.eh_dia_util,
        ehFuturo: p.eh_futuro,
      })),
    [serie],
  )

  // KPI do header = variacao do dia selecionado.
  const selPonto = serie.find((p) => p.data === diaSelecionado)
  const selValor = selPonto?.variacao_cota ?? null
  const competencia = serie.length > 0 ? competenciaLabel(serie[0].data) : ""

  // Δ% do dia sobre o PL Sub D-1 (vem do ponto, se disponivel).
  const headerKpi = {
    value: selValor != null ? fmtBRLFull.format(selValor) : "—",
    delta:
      selPonto?.variacao_pct != null
        ? {
            value: selPonto.variacao_pct,
            suffix: "%",
            good: (selValor ?? 0) >= 0,
            fractionDigits: 2,
          }
        : undefined,
    deltaSub: selPonto
      ? `dia ${selPonto.data.slice(8, 10)}/${selPonto.data.slice(5, 7)}`
      : undefined,
  }

  return (
    <EvolucaoDiariaCard
      title="VARIAÇÃO DIÁRIA DA COTA"
      presetLabel={`${competencia} · R$ por dia · clique num dia`}
      data={data}
      headerKpi={headerKpi}
      valueFormatter={(v) => fmtBRLFull.format(v)}
      axisFormatter={fmtMilharesAxis}
      dataLabelFormatter={fmtMilharesLabel}
      gridLeft={40}
      axisLabelFontSize={10}
      showTrendLine={false}
      highlightToday={false}        // destaque e o dia SELECIONADO, nao "hoje"
      selectedDate={diaSelecionado}
      height={300}
      loading={loading}
      onPointClick={onSelectDia}
    />
  )
}
