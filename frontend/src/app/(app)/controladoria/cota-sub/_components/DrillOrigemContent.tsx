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

import { RiInboxLine, RiStackLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { useDrillOrigem } from "@/lib/hooks/controladoria"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { Button } from "@/components/tremor/Button"
import {
  DrillClosureBadge,
  DrillSectionTitle,
  drillRowBorder,
  drillTableWrap,
  drillThead,
  drillTfootRow,
  fmtBRL,
  fmtBRLSigned,
} from "./drillKit"

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
      <DrillClosureBadge
        fecha={d.fecha}
        sub={!d.fecha ? `balanço ${fmtBRL.format(d.valor_balanco)} · soma ${fmtBRL.format(d.soma)}` : undefined}
      >
        {d.fecha
          ? `Fecha · ${d.linhas.length} linha(s)-fonte somam ${fmtBRL.format(d.valor_balanco)}`
          : `Diverge ${fmtBRLSigned(d.diferenca)} · soma das linhas ≠ valor do balanço`}
      </DrillClosureBadge>

      {/* ── Linhas-fonte ── */}
      <section>
        <DrillSectionTitle
          icon={RiStackLine}
          label="Linhas-fonte"
          counter={<span className="font-mono">{d.fonte}</span>}
        />

        {d.linhas.length === 0 ? (
          <EmptyState
            icon={RiInboxLine}
            title="Sem linhas-fonte nesta data"
            description="A linha está zerada em D0 — nenhum registro na tabela de origem."
            className="mt-2"
          />
        ) : (
          <div className={cx("mt-2", drillTableWrap)}>
            <table className="w-full text-[12px] tabular-nums">
              <thead className={drillThead}>
                <tr>
                  <th className="px-3 py-1.5 text-left">Identificador</th>
                  <th className="px-3 py-1.5 text-left">Descrição</th>
                  {hasDetalhe && <th className="px-3 py-1.5 text-left">Detalhe</th>}
                  <th className="px-3 py-1.5 text-right">Valor</th>
                </tr>
              </thead>
              <tbody>
                {d.linhas.map((ln, idx) => (
                  <tr key={`${ln.identificador}-${idx}`} className={drillRowBorder}>
                    <td className="px-3 py-1.5 font-mono text-[11px] text-gray-700 dark:text-gray-200">
                      <span className="block max-w-[140px] truncate" title={ln.identificador}>{ln.identificador}</span>
                    </td>
                    <td className="px-3 py-1.5 text-gray-700 dark:text-gray-200">
                      <span className="block max-w-[260px] truncate" title={ln.descricao}>{ln.descricao}</span>
                    </td>
                    {hasDetalhe && (
                      <td className="px-3 py-1.5 font-mono text-[11px] text-gray-500 dark:text-gray-400">
                        {ln.detalhe ?? "—"}
                      </td>
                    )}
                    <td className="px-3 py-1.5 text-right text-gray-900 dark:text-gray-50">
                      {fmtBRL.format(ln.valor)}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className={drillTfootRow}>
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
