/**
 * Insights heuristicos (nao-LLM) gerados a partir da agregacao de buckets.
 *
 * Regras simples para alimentar o InsightStrip da Aba "Eventos do dia" sem
 * depender de chamada IA. Quando a infra de useAIInsights for ligada nesta
 * pagina (followup), estes inputs viram contexto para o LLM em vez de saida.
 */

import type { BucketsAgregados } from "./agregacao-buckets"

export type InsightHeuristico = {
  id:   string
  text: string
}

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style:                 "currency",
  currency:              "BRL",
  notation:              "compact",
  maximumFractionDigits: 2,
})

const fmtPct = (v: number): string =>
  `${v >= 0 ? "+" : ""}${v.toFixed(2).replace(".", ",")}%`

export function gerarInsights(agg: BucketsAgregados): InsightHeuristico[] {
  const out: InsightHeuristico[] = []

  // 1. Resultado do dia — direcao + magnitude
  const sinal = agg.delta_cota_sub >= 0 ? "positivo" : "negativo"
  const valorAbs = Math.abs(agg.delta_cota_sub)
  const pct =
    agg.cota_sub_d1 !== 0
      ? (agg.delta_cota_sub / Math.abs(agg.cota_sub_d1)) * 100
      : 0
  out.push({
    id:   "saldo-dia",
    text: `Dia ${sinal} para a Cota Subordinada: Δ ${fmtBRL.format(agg.delta_cota_sub)} (${fmtPct(pct)} sobre o PL anterior).`,
  })

  // 2. Bucket dominante — quem mais explicou o resultado em valor absoluto
  const ranking = [...agg.buckets]
    .filter((b) => b.contribuicao_cota_sub !== 0)
    .sort(
      (a, b) =>
        Math.abs(b.contribuicao_cota_sub) - Math.abs(a.contribuicao_cota_sub),
    )

  if (ranking.length > 0) {
    const top = ranking[0]
    const pesoPct =
      agg.delta_cota_sub !== 0
        ? Math.abs(top.contribuicao_cota_sub / agg.delta_cota_sub) * 100
        : 0
    const direcao =
      top.contribuicao_cota_sub >= 0 ? "contribuiu +" : "subtraiu "
    out.push({
      id: "bucket-dominante",
      text: `${top.label} ${direcao}${fmtBRL.format(Math.abs(top.contribuicao_cota_sub))} no resultado do dia${
        Number.isFinite(pesoPct) && pesoPct > 0
          ? ` (cerca de ${pesoPct.toFixed(0)}% do delta total)`
          : ""
      }.`,
    })
  }

  // 3. Concentracao de risco — quando 1 bucket > 70% do delta
  if (ranking.length >= 2 && agg.delta_cota_sub !== 0) {
    const top = ranking[0]
    const pesoPct = Math.abs(top.contribuicao_cota_sub / agg.delta_cota_sub) * 100
    if (pesoPct >= 70) {
      out.push({
        id:   "concentracao",
        text: `Resultado concentrado em uma unica frente (${top.label}). Eventos atipicos nesse bucket merecem auditoria.`,
      })
    }
  }

  // 4. Forcas opostas — Ativo e Passivo se anularam
  if (
    agg.delta_ativo !== 0 &&
    agg.delta_passivo !== 0 &&
    Math.abs(agg.delta_cota_sub) <
      Math.min(Math.abs(agg.delta_ativo), Math.abs(agg.delta_passivo)) * 0.3
  ) {
    out.push({
      id: "forcas-opostas",
      text: `Crescimento do Ativo (${fmtBRL.format(agg.delta_ativo)}) absorvido por Passivo + Equity (${fmtBRL.format(agg.delta_passivo)}). Resultado liquido pequeno.`,
    })
  }

  return out
}
