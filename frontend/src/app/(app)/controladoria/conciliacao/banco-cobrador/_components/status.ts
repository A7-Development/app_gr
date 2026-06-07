// Metadados de status da conciliacao de boletos — compartilhados entre a
// tabela-resumo (ResumoConciliacaoTable) e o detalhe titulo-a-titulo
// (ConciliacaoBoletoTable). Unica fonte de label/cor/icone por status, pra
// resumo e detalhe nao divergirem.

import {
  RiCheckboxCircleFill,
  RiCloseCircleFill,
  RiErrorWarningFill,
  RiSendPlaneFill,
  type RemixiconComponentType,
} from "@remixicon/react"

import type { AvailableChartColorsKeys } from "@/lib/chartUtils"
import type { StatusConciliacaoBoleto } from "@/lib/api-client"

export type StatusMeta = {
  label: string
  /** Classes de bg+texto do badge (combinam com tableTokens.badge, 11px). */
  tone: string
  /** Cor do texto/label na linha do resumo. */
  textTone: string
  icon: RemixiconComponentType
  /** Cor do icone no resumo. */
  iconTone: string
}

export const STATUS_META: Record<StatusConciliacaoBoleto, StatusMeta> = {
  conciliado: {
    label: "Conciliado",
    tone: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400",
    textTone: "text-emerald-700 dark:text-emerald-400",
    icon: RiCheckboxCircleFill,
    iconTone: "text-emerald-500",
  },
  divergencia_valor: {
    label: "Divergência de valor",
    tone: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-400",
    textTone: "text-red-700 dark:text-red-400",
    icon: RiErrorWarningFill,
    iconTone: "text-red-500",
  },
  divergencia_vencimento: {
    label: "Divergência de vencimento",
    tone: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400",
    textTone: "text-amber-700 dark:text-amber-400",
    icon: RiErrorWarningFill,
    iconTone: "text-amber-500",
  },
  so_em_bitfin: {
    label: "Só em BITFIN",
    tone: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
    textTone: "text-gray-700 dark:text-gray-300",
    icon: RiCloseCircleFill,
    iconTone: "text-gray-400 dark:text-gray-500",
  },
  enviado_nao_confirmado: {
    label: "Enviado, aguardando confirmação",
    tone: "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400",
    textTone: "text-blue-700 dark:text-blue-400",
    icon: RiSendPlaneFill,
    iconTone: "text-blue-500",
  },
  so_em_banco: {
    label: "Só em banco",
    tone: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400",
    textTone: "text-amber-700 dark:text-amber-400",
    icon: RiCloseCircleFill,
    iconTone: "text-amber-500",
  },
}

// Ordem canonica de exibicao (resumo + segmentos).
export const STATUS_ORDER: StatusConciliacaoBoleto[] = [
  "conciliado",
  "divergencia_valor",
  "divergencia_vencimento",
  "so_em_bitfin",
  "enviado_nao_confirmado",
  "so_em_banco",
]

// Badge curto (cabe na coluna Status do detalhe + legenda dos charts).
export const STATUS_BADGE_LABEL: Record<StatusConciliacaoBoleto, string> = {
  conciliado: "Conciliado",
  divergencia_valor: "Dif. valor",
  divergencia_vencimento: "Dif. venc.",
  so_em_bitfin: "Só BITFIN",
  enviado_nao_confirmado: "Enviado",
  so_em_banco: "Só banco",
}

// Cor por status nos charts do resumo (donut por quantidade + barra de
// reconciliacao por valor). `color` e a chave do palette Tremor (DonutChart);
// `swatch` e a classe bg-* equivalente (-500) para a legenda e os segmentos da
// barra casarem com as fatias do donut. Alinhadas com a semantica do badge
// (verde=ok, vermelho/ambar=divergencia, cinza=so bitfin, azul=enviado).
export const STATUS_CHART: Record<
  StatusConciliacaoBoleto,
  { color: AvailableChartColorsKeys; swatch: string }
> = {
  conciliado:             { color: "emerald", swatch: "bg-emerald-500" },
  divergencia_valor:      { color: "rose",    swatch: "bg-rose-500" },
  divergencia_vencimento: { color: "amber",   swatch: "bg-amber-500" },
  so_em_bitfin:           { color: "gray",    swatch: "bg-gray-400" },
  enviado_nao_confirmado: { color: "blue",    swatch: "bg-blue-500" },
  so_em_banco:            { color: "violet",  swatch: "bg-violet-500" },
}
