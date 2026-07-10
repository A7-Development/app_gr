// Reason chips + severidade — a explicação em resolução de LINHA (escaneável).
// Vocabulário fechado; cor por tier (alto = vermelho, médio = âmbar, contexto
// = neutro). Usados na tabela e no drawer.

import { cx } from "@/lib/utils"
import { tableTokens } from "@/design-system/tokens/table"
import type { CedentePerfilRow } from "@/lib/api-client"
import { reasonCodes, severidade, type ReasonCode, type Severidade } from "./leitura"

const TIER_CLS: Record<ReasonCode["tier"], string> = {
  alto: "bg-red-50 text-red-700 ring-red-600/10 dark:bg-red-500/10 dark:text-red-300 dark:ring-red-400/20",
  medio: "bg-amber-50 text-amber-700 ring-amber-600/10 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-400/20",
  contexto: "bg-gray-100 text-gray-600 ring-gray-500/10 dark:bg-gray-800 dark:text-gray-300 dark:ring-gray-400/10",
}

export function ReasonChips({ row }: { row: CedentePerfilRow }) {
  const codes = reasonCodes(row)
  if (codes.length === 0) return <span className={tableTokens.cellMuted}>—</span>
  return (
    <div className="flex flex-wrap items-center gap-1">
      {codes.map((c) => (
        <span
          key={c.code}
          title={c.label}
          className={cx(
            "inline-block rounded px-1.5 py-0.5 text-[10.5px] font-semibold ring-1 ring-inset tabular-nums",
            TIER_CLS[c.tier],
          )}
        >
          {c.code}
        </span>
      ))}
    </div>
  )
}

const SEV_META: Record<Severidade, { label: string; dot: string; text: string }> = {
  critico: { label: "Crítico", dot: "bg-red-500", text: "text-red-700 dark:text-red-300" },
  atencao: { label: "Atenção", dot: "bg-amber-500", text: "text-amber-700 dark:text-amber-300" },
  neutro: { label: "Neutro", dot: "bg-gray-300 dark:bg-gray-600", text: "text-gray-500 dark:text-gray-400" },
}

// Célula de Alerta na tabela: crítico mostra ⚠ + contagem; senão a severidade
// (ponto colorido) — encoda severidade + volume de alerta num só lugar.
export function SeverityCell({ row }: { row: CedentePerfilRow }) {
  const sev = severidade(row)
  if (row.n_alerta > 0) {
    const partes: string[] = []
    if (row.n_alerta_conta) partes.push(`${row.n_alerta_conta} conta+cidade`)
    if (row.n_alerta_multicedente) partes.push(`${row.n_alerta_multicedente} agência multi-cedente`)
    return (
      <span
        className={cx(tableTokens.badge, tableTokens.badgeDanger)}
        title={`Regra dura: ${partes.join(" · ")}`}
      >
        ⚠ {row.n_alerta}
      </span>
    )
  }
  const m = SEV_META[sev]
  return (
    <span className={cx("inline-flex items-center gap-1.5 text-[11px] font-medium", m.text)} title={m.label}>
      <span className={cx("size-2 rounded-full", m.dot)} aria-hidden />
      {sev === "neutro" ? "—" : m.label}
    </span>
  )
}

export function SeverityPill({ sev }: { sev: Severidade }) {
  const m = SEV_META[sev]
  return (
    <span className={cx("inline-flex items-center gap-2 text-sm font-semibold", m.text)}>
      <span className={cx("size-2.5 rounded-full", m.dot)} aria-hidden />
      {m.label}
    </span>
  )
}
