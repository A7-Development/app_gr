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

import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"
import type { StatusConciliacaoBoleto } from "@/lib/api-client"

export type StatusMeta = {
  label: string
  /** Badge COMPLETO (tableTokens.badge*) — usar direto no className, sem
   *  compor com tableTokens.badge no callsite. */
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
    tone: tableTokens.badgeSuccess,
    textTone: "text-emerald-700 dark:text-emerald-400",
    icon: RiCheckboxCircleFill,
    iconTone: "text-emerald-500",
  },
  divergencia_valor: {
    label: "Divergência de valor",
    tone: tableTokens.badgeDanger,
    textTone: "text-red-700 dark:text-red-400",
    icon: RiErrorWarningFill,
    iconTone: "text-red-500",
  },
  divergencia_vencimento: {
    label: "Divergência de vencimento",
    tone: tableTokens.badgeWarning,
    textTone: "text-amber-700 dark:text-amber-400",
    icon: RiErrorWarningFill,
    iconTone: "text-amber-500",
  },
  so_em_bitfin: {
    label: "Só em BITFIN",
    tone: tableTokens.badgeNeutral,
    textTone: "text-gray-700 dark:text-gray-300",
    icon: RiCloseCircleFill,
    iconTone: "text-gray-400 dark:text-gray-500",
  },
  enviado_nao_confirmado: {
    // MOTIVO: estado "em transito" (nem success/warning/danger/neutral) —
    // nao ha token semantico azul; compoe tableTokens.badge + tone blue.
    label: "Enviado, aguardando confirmação",
    tone: cx(tableTokens.badge, "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-400"),
    textTone: "text-blue-700 dark:text-blue-400",
    icon: RiSendPlaneFill,
    iconTone: "text-blue-500",
  },
  so_em_banco: {
    label: "Só em banco",
    tone: tableTokens.badgeWarning,
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

// ── Situacao do titulo no sistema (wh_titulo, codigo Bitfin) ─────────────────
// So preenchida em linhas "so_em_banco". Rotulos confirmados na descricao
// oficial do Bitfin (wh_titulo_snapshot.situacao_descricao): 0="Em aberto",
// 1="Liq. Normal", 5="Recomprado"; 3/7/9 chegam como "Outros".
const SITUACAO_TITULO_LABEL: Record<number, string> = {
  0: "Em aberto",
  1: "Liquidado",
  5: "Recomprado",
}

/** Rotulo da situacao do titulo no sistema (linhas "so_em_banco"). */
export function situacaoTituloLabel(s: number | null | undefined): string {
  if (s == null) return "Sem título"
  return SITUACAO_TITULO_LABEL[s] ?? `Outros (cód ${s})`
}

/** Titulo encerrado no sistema com boleto ativo no banco -> cabe baixa. */
export function situacaoTituloCabeBaixa(s: number | null | undefined): boolean {
  return s === 1 || s === 5
}

// ── Pipeline de protesto/cartorio (wh_boleto_evento.tipo_evento) ─────────────
// Ultimo evento de protesto do boleto. Eventos "info" no fold — a conciliacao
// e o unico lugar que os mostra. Em cartorio/instruido = acao em curso (red);
// sustado/retirado = pipeline interrompido (gray).
export const PROTESTO_META: Record<string, { label: string; tone: string }> = {
  protesto_instruido: { label: "Instruído", tone: tableTokens.badgeDanger },
  encaminhado_cartorio: { label: "Em cartório", tone: tableTokens.badgeDanger },
  protesto_sustado: { label: "Sustado", tone: tableTokens.badgeNeutral },
  retirado_cartorio: { label: "Retirado", tone: tableTokens.badgeNeutral },
}

export function protestoLabel(tipo: string | null | undefined): string {
  if (tipo == null) return "—"
  return PROTESTO_META[tipo]?.label ?? tipo
}

// ── Aging do "Enviado, aguardando confirmacao" ───────────────────────────────
// Dias corridos desde a remessa de registro. <=2 normal (D-1/D-2 de retorno),
// 3-9 atencao, >=10 stuck (banco nunca confirmou — gap real).
export function diasAguardando(enviadoEm: string | null | undefined): number | null {
  if (!enviadoEm) return null
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(enviadoEm)
  if (!m) return null
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  return Math.max(0, Math.floor((Date.now() - d.getTime()) / 86_400_000))
}

export function agingTone(dias: number): string {
  if (dias >= 10) return "text-red-600 dark:text-red-400"
  if (dias >= 3) return "text-amber-600 dark:text-amber-400"
  return "text-gray-500 dark:text-gray-400"
}

// Badge curto (cabe na coluna Status do detalhe + legenda dos charts).
export const STATUS_BADGE_LABEL: Record<StatusConciliacaoBoleto, string> = {
  conciliado: "Conciliado",
  divergencia_valor: "Dif. valor",
  divergencia_vencimento: "Dif. venc.",
  so_em_bitfin: "Só BITFIN",
  enviado_nao_confirmado: "Enviado",
  so_em_banco: "Só banco",
}
