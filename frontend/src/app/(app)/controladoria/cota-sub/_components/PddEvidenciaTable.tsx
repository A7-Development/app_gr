"use client"

/**
 * PddEvidenciaTable — tabela compacta de papeis com variacao de PDD.
 *
 * Consumida pelo AnaliseVariacaoCard na categoria "Eventos contabeis"
 * quando ha PddExplanation com evidencias. 1 linha = 1 papel cujo
 * |Δ valor_pdd| ultrapassou o threshold (default R$ 100).
 *
 * Agrupamento por cedente (decidido 2026-05-13 apos investigar reclassificacoes
 * massivas A→B no fundo REALINVEST): quando >= 2 papeis compartilham
 * `cedente_doc`, renderiza uma row "header" do grupo com totais agregados +
 * rows dos papeis abaixo (com Cedente em branco pra economizar largura).
 * Cedentes com 1 papel ficam como row normal (sem header).
 *
 * Colunas (8 fixas, `table-fixed` pra caber sem scroll horizontal):
 *   Cedente | Sacado | NU Doc | Faixa | Nominal | PDD D-1 | PDD D0 | Δ PL Sub
 *
 * Sinal da coluna "Δ PL Sub": negativo quando PDD aumentou (PL Sub caiu),
 * positivo quando PDD reverteu (PL Sub subiu). Some-se a coluna = soma do
 * impacto no PL Sub mostrado no header do card.
 *
 * Valores monetarios sem decimais nas cells (`title` no hover mostra valor
 * exato).
 *
 * Plano: backend/docs/cota-sub-explainers-heuristicos.md
 */

import { Fragment } from "react"

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

const fmtBRLCompact = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 0,
  maximumFractionDigits: 0,
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

// ─── Agrupamento por cedente ─────────────────────────────────────────────────

type Grupo = {
  cedenteDoc:    string
  cedenteNome:   string
  papeis:        PddEvidencia[]
  totalNominal:  number
  totalPddD1:    number
  totalPddD0:    number
  totalDeltaPlSub: number  // -Σ delta_valor_pdd
}

function agruparPorCedente(evidencias: readonly PddEvidencia[]): Grupo[] {
  const mapa = new Map<string, Grupo>()
  for (const e of evidencias) {
    let g = mapa.get(e.cedente_doc)
    if (!g) {
      g = {
        cedenteDoc:      e.cedente_doc,
        cedenteNome:     e.cedente_nome,
        papeis:          [],
        totalNominal:    0,
        totalPddD1:      0,
        totalPddD0:      0,
        totalDeltaPlSub: 0,
      }
      mapa.set(e.cedente_doc, g)
    }
    g.papeis.push(e)
    g.totalNominal    += e.valor_nominal
    g.totalPddD1      += e.valor_pdd_d1
    g.totalPddD0      += e.valor_pdd_d0
    g.totalDeltaPlSub += -e.delta_valor_pdd
  }
  // Ordena grupos por |Δ total| DESC; dentro do grupo, papeis ja vem por |Δ| DESC do backend.
  return Array.from(mapa.values()).sort(
    (a, b) => Math.abs(b.totalDeltaPlSub) - Math.abs(a.totalDeltaPlSub),
  )
}

// ─── Props ───────────────────────────────────────────────────────────────────

export type PddEvidenciaTableProps = {
  evidencias:          readonly PddEvidencia[]
  evidenciasTotal:     number
  evidenciasMostradas: number
  outrosDeltaBrl:      number
}

// ─── Componente ──────────────────────────────────────────────────────────────

export function PddEvidenciaTable({
  evidencias,
  evidenciasTotal,
  evidenciasMostradas,
  outrosDeltaBrl,
}: PddEvidenciaTableProps) {
  const escondidos = evidenciasTotal - evidenciasMostradas
  const grupos = agruparPorCedente(evidencias)

  return (
    <TableRoot className="overflow-visible">
      <Table className="w-full table-fixed text-[11px]">
        <colgroup>
          <col className="w-[16%]" />
          <col className="w-[16%]" />
          <col className="w-[12%]" />
          <col className="w-[8%]" />
          <col className="w-[12%]" />
          <col className="w-[12%]" />
          <col className="w-[12%]" />
          <col className="w-[12%]" />
        </colgroup>
        <TableHead>
          <TableRow className="border-b border-gray-200 dark:border-gray-800">
            <TableHeaderCell className={cx(tableTokens.header, "px-1 py-1.5")}>
              Cedente
            </TableHeaderCell>
            <TableHeaderCell className={cx(tableTokens.header, "px-1 py-1.5")}>
              Sacado
            </TableHeaderCell>
            <TableHeaderCell className={cx(tableTokens.header, "px-1 py-1.5")}>
              NU Doc
            </TableHeaderCell>
            <TableHeaderCell className={cx(tableTokens.header, "px-1 py-1.5 text-center")}>
              Faixa
            </TableHeaderCell>
            <TableHeaderCell className={cx(tableTokens.header, "px-1 py-1.5 text-right")}>
              Nominal
            </TableHeaderCell>
            <TableHeaderCell className={cx(tableTokens.header, "px-1 py-1.5 text-right")}>
              PDD D-1
            </TableHeaderCell>
            <TableHeaderCell className={cx(tableTokens.header, "px-1 py-1.5 text-right")}>
              PDD D0
            </TableHeaderCell>
            <TableHeaderCell className={cx(tableTokens.header, "px-1 py-1.5 text-right")}>
              Δ PL Sub
            </TableHeaderCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {grupos.map((g) => {
            const ehGrupo = g.papeis.length >= 2
            const totalDeltaNeg = g.totalDeltaPlSub < 0
            return (
              <Fragment key={g.cedenteDoc}>
                {ehGrupo && (
                  <TableRow
                    className="border-b border-gray-200 bg-gray-50/60 dark:border-gray-800 dark:bg-gray-900/40"
                  >
                    <TableCell
                      colSpan={3}
                      className={cx(tableTokens.cellStrong, "px-1 py-1.5")}
                    >
                      <span title={g.cedenteNome}>
                        {truncar(g.cedenteNome, 44)}
                      </span>
                      <span className="ml-1 text-[10px] font-normal text-gray-500 dark:text-gray-400">
                        · {g.papeis.length} papeis
                      </span>
                    </TableCell>
                    <TableCell className="px-1 py-1.5" />
                    <TableCell
                      className={cx(tableTokens.cellNumber, "px-1 py-1.5 text-right")}
                      title={fmtBRL.format(g.totalNominal)}
                    >
                      {fmtBRLCompact.format(g.totalNominal)}
                    </TableCell>
                    <TableCell
                      className={cx(tableTokens.cellNumberSecondary, "px-1 py-1.5 text-right")}
                      title={fmtBRL.format(g.totalPddD1)}
                    >
                      {fmtBRLCompact.format(g.totalPddD1)}
                    </TableCell>
                    <TableCell
                      className={cx(tableTokens.cellNumber, "px-1 py-1.5 text-right")}
                      title={fmtBRL.format(g.totalPddD0)}
                    >
                      {fmtBRLCompact.format(g.totalPddD0)}
                    </TableCell>
                    <TableCell
                      className={cx(
                        "px-1 py-1.5 text-right text-[11px] font-semibold tabular-nums",
                        totalDeltaNeg
                          ? "text-red-700 dark:text-red-300"
                          : "text-emerald-700 dark:text-emerald-300",
                      )}
                      title={fmtBRL.format(g.totalDeltaPlSub)}
                    >
                      {g.totalDeltaPlSub > 0 ? "+" : ""}
                      {fmtBRLCompact.format(g.totalDeltaPlSub)}
                    </TableCell>
                  </TableRow>
                )}
                {g.papeis.map((e) => {
                  const mudouFaixa = e.faixa_pdd_d1 !== e.faixa_pdd_d0
                  const intensD0 = faixaIntensidade(e.faixa_pdd_d0)
                  const deltaPlSub = -e.delta_valor_pdd
                  const deltaNegativo = deltaPlSub < 0
                  return (
                    <TableRow
                      key={`${e.seu_numero}-${e.numero_documento}`}
                      className="border-b border-gray-100 dark:border-gray-900"
                    >
                      <TableCell className={cx(tableTokens.cellText, "px-1 py-1.5 truncate")}>
                        {ehGrupo ? (
                          <span className="text-gray-400 dark:text-gray-600">·</span>
                        ) : (
                          <span title={e.cedente_nome}>
                            {truncar(e.cedente_nome, 14)}
                          </span>
                        )}
                      </TableCell>
                      <TableCell className={cx(tableTokens.cellSecondary, "px-1 py-1.5 truncate")}>
                        <span title={e.sacado_nome}>
                          {truncar(e.sacado_nome, 14)}
                        </span>
                      </TableCell>
                      <TableCell className={cx(tableTokens.cellTextMono, "px-1 py-1.5 truncate")}>
                        <span title={e.numero_documento}>
                          {e.numero_documento}
                        </span>
                      </TableCell>
                      <TableCell className="px-1 py-1.5 text-center">
                        <span
                          className={cx(
                            "inline-flex items-center gap-0.5 rounded px-1 py-0.5 text-[10px] font-medium",
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
                      <TableCell
                        className={cx(tableTokens.cellNumberSecondary, "px-1 py-1.5 text-right")}
                        title={fmtBRL.format(e.valor_nominal)}
                      >
                        {fmtBRLCompact.format(e.valor_nominal)}
                      </TableCell>
                      <TableCell
                        className={cx(tableTokens.cellNumberSecondary, "px-1 py-1.5 text-right")}
                        title={fmtBRL.format(e.valor_pdd_d1)}
                      >
                        {fmtBRLCompact.format(e.valor_pdd_d1)}
                      </TableCell>
                      <TableCell
                        className={cx(tableTokens.cellNumber, "px-1 py-1.5 text-right")}
                        title={fmtBRL.format(e.valor_pdd_d0)}
                      >
                        {fmtBRLCompact.format(e.valor_pdd_d0)}
                      </TableCell>
                      <TableCell
                        className={cx(
                          "px-1 py-1.5 text-right text-[11px] font-medium tabular-nums",
                          deltaNegativo
                            ? "text-red-600 dark:text-red-400"
                            : "text-emerald-600 dark:text-emerald-400",
                        )}
                        title={fmtBRL.format(deltaPlSub)}
                      >
                        {deltaPlSub > 0 ? "+" : ""}
                        {fmtBRLCompact.format(deltaPlSub)}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </Fragment>
            )
          })}
          {escondidos > 0 && (
            <TableRow className="border-b border-gray-100 dark:border-gray-900">
              <TableCell
                colSpan={7}
                className={cx(tableTokens.cellMuted, "px-1 py-1.5 italic")}
              >
                +{escondidos} {escondidos === 1 ? "outro papel" : "outros papeis"} (fora do top {evidenciasMostradas})
              </TableCell>
              <TableCell
                className={cx(
                  "px-1 py-1.5 text-right text-[11px] italic tabular-nums",
                  outrosDeltaBrl < 0
                    ? "text-red-600 dark:text-red-400"
                    : "text-emerald-600 dark:text-emerald-400",
                )}
                title={fmtBRL.format(outrosDeltaBrl)}
              >
                {outrosDeltaBrl > 0 ? "+" : ""}
                {fmtBRLCompact.format(outrosDeltaBrl)}
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>
    </TableRoot>
  )
}
