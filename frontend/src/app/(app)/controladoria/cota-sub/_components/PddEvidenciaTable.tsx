"use client"

/**
 * PddEvidenciaTable — tabela compacta de papeis com variacao de PDD.
 *
 * Consumida pelo AnaliseVariacaoCard na categoria "Eventos contabeis"
 * quando ha PddExplanation com evidencias. 1 linha = 1 papel cujo
 * |Δ valor_pdd| ultrapassou o threshold (default R$ 1.000).
 *
 * Colunas:
 *   Cedente | Sacado | Titulo | Faixa D-1→D0 | PDD D-1 | PDD D0 | Δ
 *
 * Plano: backend/docs/cota-sub-explainers-heuristicos.md
 */

import { cx } from "@/lib/utils"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRoot,
  TableRow,
} from "@/components/tremor/Table"
import { tableTokens } from "@/design-system/tokens/table"

import type { PddEvidencia } from "@/lib/api-client"

// ─── Formatadores ────────────────────────────────────────────────────────────

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style:                  "currency",
  currency:               "BRL",
  minimumFractionDigits:  2,
  maximumFractionDigits:  2,
})

function truncar(s: string, max: number): string {
  return s.length > max ? `${s.slice(0, max - 1)}…` : s
}

// Faixa Bacen 2682: A→H crescente em risco. Estilizamos faixas mais ruins.
function faixaIntensidade(faixa: string | null): "low" | "mid" | "high" {
  if (!faixa) return "low"
  const idx = "ABCDEFGH".indexOf(faixa.toUpperCase())
  if (idx < 0) return "low"
  if (idx <= 1) return "low"
  if (idx <= 4) return "mid"
  return "high"
}

// ─── Props ───────────────────────────────────────────────────────────────────

export type PddEvidenciaTableProps = {
  evidencias:       readonly PddEvidencia[]
  evidenciasTotal:  number
  evidenciasMostradas: number
  outrosDeltaBrl:   number
}

// ─── Componente ──────────────────────────────────────────────────────────────

export function PddEvidenciaTable({
  evidencias,
  evidenciasTotal,
  evidenciasMostradas,
  outrosDeltaBrl,
}: PddEvidenciaTableProps) {
  const escondidos = evidenciasTotal - evidenciasMostradas

  return (
    <TableRoot>
      <Table className="text-[12px]">
        <TableHead>
          <TableRow className="border-b border-gray-200 dark:border-gray-800">
            <TableHeaderCell className={cx(tableTokens.header, "py-1.5")}>
              Cedente
            </TableHeaderCell>
            <TableHeaderCell className={cx(tableTokens.header, "py-1.5")}>
              Sacado
            </TableHeaderCell>
            <TableHeaderCell className={cx(tableTokens.header, "py-1.5")}>
              Titulo
            </TableHeaderCell>
            <TableHeaderCell className={cx(tableTokens.header, "py-1.5 text-center")}>
              Faixa
            </TableHeaderCell>
            <TableHeaderCell className={cx(tableTokens.header, "py-1.5 text-right")}>
              PDD D-1
            </TableHeaderCell>
            <TableHeaderCell className={cx(tableTokens.header, "py-1.5 text-right")}>
              PDD D0
            </TableHeaderCell>
            <TableHeaderCell className={cx(tableTokens.header, "py-1.5 text-right")}>
              Δ
            </TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {evidencias.map((e) => {
            const mudouFaixa = e.faixa_pdd_d1 !== e.faixa_pdd_d0
            const intensD0 = faixaIntensidade(e.faixa_pdd_d0)
            const deltaPositivo = e.delta_valor_pdd > 0
            return (
              <TableRow
                key={`${e.seu_numero}-${e.numero_documento}`}
                className="border-b border-gray-100 dark:border-gray-900"
              >
                <TableCell className={cx(tableTokens.cellText, "py-1.5")}>
                  <span title={e.cedente_nome}>
                    {truncar(e.cedente_nome, 28)}
                  </span>
                </TableCell>
                <TableCell className={cx(tableTokens.cellSecondary, "py-1.5")}>
                  <span title={e.sacado_nome}>
                    {truncar(e.sacado_nome, 28)}
                  </span>
                </TableCell>
                <TableCell className={cx(tableTokens.cellTextMono, "py-1.5")}>
                  {e.seu_numero}
                </TableCell>
                <TableCell className="py-1.5 text-center">
                  <span
                    className={cx(
                      "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium",
                      mudouFaixa
                        ? intensD0 === "high"
                          ? "bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300"
                          : intensD0 === "mid"
                            ? "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300"
                            : "bg-gray-50 text-gray-700 dark:bg-gray-900 dark:text-gray-300"
                        : "bg-gray-50 text-gray-600 dark:bg-gray-900 dark:text-gray-400",
                    )}
                  >
                    {e.faixa_pdd_d1 ?? "—"}
                    {mudouFaixa && <span className="text-gray-400">→</span>}
                    {mudouFaixa && (e.faixa_pdd_d0 ?? "—")}
                  </span>
                </TableCell>
                <TableCell className={cx(tableTokens.cellNumberSecondary, "py-1.5 text-right")}>
                  {fmtBRL.format(e.valor_pdd_d1)}
                </TableCell>
                <TableCell className={cx(tableTokens.cellNumber, "py-1.5 text-right")}>
                  {fmtBRL.format(e.valor_pdd_d0)}
                </TableCell>
                <TableCell
                  className={cx(
                    "py-1.5 text-right text-[12px] font-medium tabular-nums",
                    deltaPositivo
                      ? "text-red-600 dark:text-red-400"
                      : "text-emerald-600 dark:text-emerald-400",
                  )}
                >
                  {deltaPositivo ? "+" : ""}
                  {fmtBRL.format(e.delta_valor_pdd)}
                </TableCell>
              </TableRow>
            )
          })}
          {escondidos > 0 && (
            <TableRow className="border-b border-gray-100 dark:border-gray-900">
              <TableCell
                colSpan={6}
                className={cx(tableTokens.cellMuted, "py-1.5 italic")}
              >
                +{escondidos} {escondidos === 1 ? "outro papel" : "outros papeis"} (fora do top {evidenciasMostradas})
              </TableCell>
              <TableCell
                className={cx(
                  "py-1.5 text-right text-[12px] italic tabular-nums",
                  outrosDeltaBrl < 0
                    ? "text-red-600 dark:text-red-400"
                    : "text-emerald-600 dark:text-emerald-400",
                )}
              >
                {outrosDeltaBrl > 0 ? "+" : ""}
                {fmtBRL.format(outrosDeltaBrl)}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </TableRoot>
  )
}
