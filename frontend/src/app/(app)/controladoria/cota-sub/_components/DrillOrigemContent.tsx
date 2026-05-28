"use client"

/**
 * DrillOrigemContent — drill "ver origem" das 9 linhas SEM drill rico
 * (RF/Op.Estruturadas/Fundos DI/Compromissada/Outros Ativos/Tesouraria/
 * Conta Corrente/Cota Senior/Cota Mezanino).
 *
 * Lista as linhas-fonte (snapshot D0) que compoem o valor da linha do balanco
 * e prova o fechamento: Σ(linhas) == valor_balanco. O selo verde/vermelho e a
 * conferenciabilidade (§14) — cada numero rastreavel ate o dado-fonte.
 *
 * Visual espelha DrillCprContent (tabela inline, mesma densidade/tipografia).
 */

import * as React from "react"
import {
  RiCheckboxCircleFill,
  RiErrorWarningFill,
  RiInboxLine,
  RiStackLine,
} from "@remixicon/react"

import { cx } from "@/lib/utils"
import { useDrillOrigem } from "@/lib/hooks/controladoria"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { Button } from "@/components/tremor/Button"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style:                 "currency",
  currency:              "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const fmtBRLSigned = (v: number): string => {
  if (Math.abs(v) < 0.005) return "R$ 0,00"
  const sign = v > 0 ? "+" : "−"
  return `${sign}${fmtBRL.format(Math.abs(v))}`
}

export type DrillOrigemContentProps = {
  fundoId: string
  data:    string
  linha:   string
}

export function DrillOrigemContent({ fundoId, data, linha }: DrillOrigemContentProps) {
  const q = useDrillOrigem(fundoId, data, linha)

  if (q.isError) {
    return (
      <ErrorState
        title="Falha ao carregar origem"
        description={(q.error as Error)?.message ?? "Erro desconhecido"}
        action={<Button onClick={() => q.refetch()}>Tentar novamente</Button>}
      />
    )
  }

  if (q.isLoading || !q.data) {
    return (
      <div className="flex h-40 items-center justify-center text-[12px] text-gray-500 dark:text-gray-400">
        Carregando origem…
      </div>
    )
  }

  const d = q.data
  const hasDetalhe = d.linhas.some((l) => !!l.detalhe)

  return (
    <div className="flex flex-col gap-4">
      {/* ── Selo de fechamento ── */}
      <div
        className={cx(
          "flex items-start gap-2 rounded border px-3 py-2",
          d.fecha
            ? "border-emerald-200 bg-emerald-50/50 dark:border-emerald-900/60 dark:bg-emerald-950/20"
            : "border-red-200 bg-red-50/50 dark:border-red-900/60 dark:bg-red-950/20",
        )}
      >
        {d.fecha ? (
          <RiCheckboxCircleFill className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400" aria-hidden />
        ) : (
          <RiErrorWarningFill className="mt-0.5 size-4 shrink-0 text-red-600 dark:text-red-400" aria-hidden />
        )}
        <div className="flex flex-col">
          <span className={cx(
            "text-[12px] font-medium",
            d.fecha ? "text-emerald-800 dark:text-emerald-300" : "text-red-800 dark:text-red-300",
          )}>
            {d.fecha
              ? `Fecha · ${d.linhas.length} linha(s)-fonte somam ${fmtBRL.format(d.valor_balanco)}`
              : `Diverge ${fmtBRLSigned(d.diferenca)} · soma das linhas ≠ valor do balanço`}
          </span>
          {!d.fecha && (
            <span className="text-[11px] tabular-nums text-gray-600 dark:text-gray-400">
              balanço {fmtBRL.format(d.valor_balanco)} · soma {fmtBRL.format(d.soma)}
            </span>
          )}
        </div>
      </div>

      {/* ── Linhas-fonte ── */}
      <section>
        <div className="flex items-baseline justify-between gap-2">
          <h4 className="flex items-center gap-1.5 text-[12px] font-semibold uppercase tracking-[0.04em] text-gray-700 dark:text-gray-300">
            <RiStackLine className="size-3.5 text-gray-400 dark:text-gray-500" aria-hidden />
            Linhas-fonte
          </h4>
          <span className="font-mono text-[10px] text-gray-400 dark:text-gray-600">{d.fonte}</span>
        </div>

        {d.linhas.length === 0 ? (
          <EmptyState
            icon={RiInboxLine}
            title="Sem linhas-fonte nesta data"
            description="A linha está zerada em D0 — nenhum registro na tabela de origem."
            className="mt-2"
          />
        ) : (
          <div className="mt-2 overflow-hidden rounded border border-gray-200 dark:border-gray-800">
            <table className="w-full text-[12px] tabular-nums">
              <thead className="text-[10px] uppercase tracking-[0.04em] text-gray-400 dark:text-gray-600">
                <tr>
                  <th className="px-3 py-1 text-left">Identificador</th>
                  <th className="px-3 py-1 text-left">Descrição</th>
                  {hasDetalhe && <th className="px-3 py-1 text-left">Detalhe</th>}
                  <th className="px-3 py-1 text-right">Valor</th>
                </tr>
              </thead>
              <tbody>
                {d.linhas.map((ln, idx) => (
                  <tr key={`${ln.identificador}-${idx}`} className="border-t border-gray-100 dark:border-gray-900">
                    <td className="px-3 py-1 font-mono text-[11px] text-gray-700 dark:text-gray-200">
                      <span className="block max-w-[140px] truncate" title={ln.identificador}>{ln.identificador}</span>
                    </td>
                    <td className="px-3 py-1 text-gray-700 dark:text-gray-200">
                      <span className="block max-w-[260px] truncate" title={ln.descricao}>{ln.descricao}</span>
                    </td>
                    {hasDetalhe && (
                      <td className="px-3 py-1 font-mono text-[11px] text-gray-500 dark:text-gray-400">
                        {ln.detalhe ?? "—"}
                      </td>
                    )}
                    <td className="px-3 py-1 text-right text-gray-900 dark:text-gray-50">
                      {fmtBRL.format(ln.valor)}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t-2 border-gray-200 font-semibold dark:border-gray-700">
                  <td className="px-3 py-1.5 text-gray-700 dark:text-gray-200" colSpan={hasDetalhe ? 3 : 2}>
                    Total
                  </td>
                  <td className="px-3 py-1.5 text-right text-gray-900 dark:text-gray-50">
                    {fmtBRL.format(d.soma)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
