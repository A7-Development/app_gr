"use client"

/**
 * ResumoConciliacaoCharts — "Carteira por banco cobrador" (ao lado da tabela).
 *
 * A tabela-resumo e por STATUS. Este chart abre uma dimensao que ela NAO tem: o
 * BANCO. Por banco cobrador (+ "Sem boleto" = Só BITFIN, titulos que nunca foram
 * a banco nenhum), a carteira aberta (R$ BITFIN) em barras conciliado vs a
 * conciliar. Escancara ONDE falta conciliar — ex.: o gap de "enviado" da Vortx.
 *
 * Le as MESMAS linhas filtradas da pagina (re-escopo total, §7.2/§14.6). Barras
 * escaladas ao maior total; ordenadas pelo valor A CONCILIAR (pior primeiro).
 */

import * as React from "react"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import { cardTokens } from "@/design-system/tokens/card"
import type { LinhaConciliacaoBoleto } from "@/lib/api-client"

const fmtInt = new Intl.NumberFormat("pt-BR")

/** R$ compacto (39,6M / 812,4k / 950). */
function fmtBRLcompact(v: number): string {
  const abs = Math.abs(v)
  if (abs >= 1_000_000) return `R$ ${(v / 1_000_000).toFixed(1).replace(".", ",")}M`
  if (abs >= 1_000) return `R$ ${(v / 1_000).toFixed(1).replace(".", ",")}k`
  return `R$ ${fmtInt.format(Math.round(v))}`
}

// Rotulo amigavel do banco (linhas trazem "bradesco"/"vortx"/"bmp"/"itau").
const BANCO_LABEL: Record<string, string> = {
  bradesco: "Bradesco",
  vortx: "Vórtx",
  bmp: "BMP",
  itau: "Itaú",
}
const SEM_BOLETO = "Sem boleto"

type BancoAgg = { banco: string; conciliado: number; aConciliar: number; total: number }

export function ResumoConciliacaoCharts({
  linhas,
}: {
  linhas: LinhaConciliacaoBoleto[]
}) {
  const grupos = React.useMemo<BancoAgg[]>(() => {
    const by = new Map<string, BancoAgg>()
    for (const l of linhas) {
      const v = l.valor_bitfin ?? 0
      if (v === 0) continue // so_em_banco (sem titulo) nao tem valor BITFIN
      // "Só BITFIN" nao tem boleto/banco -> bucket "Sem boleto".
      const key = l.banco ? (BANCO_LABEL[l.banco] ?? l.banco) : SEM_BOLETO
      const g = by.get(key) ?? { banco: key, conciliado: 0, aConciliar: 0, total: 0 }
      if (l.status === "conciliado") g.conciliado += v
      else g.aConciliar += v // div. valor/venc, enviado, so_em_bitfin
      g.total += v
      by.set(key, g)
    }
    // Pior primeiro: mais valor A CONCILIAR no topo.
    return Array.from(by.values()).sort((a, b) => b.aConciliar - a.aConciliar)
  }, [linhas])

  const maxTotal = grupos.reduce((m, g) => Math.max(m, g.total), 0)
  const totalGeral = grupos.reduce((a, g) => a + g.total, 0)
  const conciliadoGeral = grupos.reduce((a, g) => a + g.conciliado, 0)
  const pctConciliado = totalGeral > 0 ? (conciliadoGeral / totalGeral) * 100 : 0

  if (grupos.length === 0) {
    return (
      <Card className={cx(cardTokens.body, "flex items-center justify-center")}>
        <p className="text-sm text-gray-400 dark:text-gray-600">Sem dados no escopo.</p>
      </Card>
    )
  }

  return (
    <Card className={cardTokens.body}>
      {/* Cabecalho: titulo + legenda */}
      <div className="mb-4 flex items-baseline justify-between">
        <div>
          <h3 className="text-[13px] font-semibold text-gray-900 dark:text-gray-50">
            Carteira por banco cobrador
          </h3>
          <p className="text-[11px] text-gray-400 dark:text-gray-500">Valor aberto (R$ BITFIN)</p>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-gray-500 dark:text-gray-400">
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-emerald-500" aria-hidden="true" />
            conciliado
          </span>
          <span className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm bg-amber-400" aria-hidden="true" />
            a conciliar
          </span>
        </div>
      </div>

      {/* Barras por banco (escaladas ao maior total; conciliado | a conciliar) */}
      <ul className="space-y-3">
        {grupos.map((g) => {
          const pctAConciliar = g.total > 0 ? (g.aConciliar / g.total) * 100 : 0
          return (
            <li key={g.banco}>
              <div className="mb-1 flex items-baseline justify-between gap-2 text-[12px]">
                <span className="truncate font-medium text-gray-700 dark:text-gray-300">
                  {g.banco}
                </span>
                <span className="shrink-0 tabular-nums text-gray-500 dark:text-gray-400">
                  {fmtBRLcompact(g.total)}
                  {g.aConciliar > 0 && (
                    <span className="ml-1.5 text-amber-600 dark:text-amber-400">
                      · {pctAConciliar.toFixed(0)}% a conciliar
                    </span>
                  )}
                </span>
              </div>
              {/* Track full width; porcao preenchida = total/maxTotal, dividida
                  em conciliado (emerald) + a conciliar (amber). */}
              <div className="h-2.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
                <div
                  className="flex h-full overflow-hidden rounded-full"
                  style={{ width: `${maxTotal > 0 ? (g.total / maxTotal) * 100 : 0}%` }}
                  title={`${g.banco}: ${fmtBRLcompact(g.conciliado)} conciliado · ${fmtBRLcompact(g.aConciliar)} a conciliar`}
                >
                  <div
                    className="h-full bg-emerald-500"
                    style={{ width: `${g.total > 0 ? (g.conciliado / g.total) * 100 : 0}%` }}
                  />
                  <div
                    className="h-full bg-amber-400"
                    style={{ width: `${g.total > 0 ? (g.aConciliar / g.total) * 100 : 0}%` }}
                  />
                </div>
              </div>
            </li>
          )
        })}
      </ul>

      {/* Rodape: total da carteira aberta + % conciliado (reconcilia §14.6) */}
      <div className="mt-4 flex items-baseline justify-between border-t border-gray-100 pt-3 dark:border-gray-800">
        <span className="text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-500">
          Carteira aberta
        </span>
        <span className="text-[12px] text-gray-500 dark:text-gray-400">
          <span className="font-semibold tabular-nums text-gray-900 dark:text-gray-50">
            {fmtBRLcompact(totalGeral)}
          </span>{" "}
          ·{" "}
          <span className="font-semibold text-emerald-700 dark:text-emerald-400">
            {pctConciliado.toFixed(0)}% conciliado
          </span>
        </span>
      </div>
    </Card>
  )
}
