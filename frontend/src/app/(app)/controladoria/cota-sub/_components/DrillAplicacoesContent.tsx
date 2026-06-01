"use client"

/**
 * DrillAplicacoesContent — drill do grupo Aplicacoes do waterfall.
 *
 * Aprofunda Fundos DI externo (onde o fundo estaciona caixa ocioso): por fundo,
 * separa VALORIZACAO (rendimento DI = impacto na cota) de CAPITAL (aplicacao/
 * resgate = neutro, vai pra "Giro e capital") + linhas menores (TPF/Compr/Outros).
 *
 * Reusa compute_movimento_aplicacoes via /drill/aplicacoes. Op. Estruturadas (NC)
 * entra na barra de Aplicacoes mas tem auditor proprio (sublinha no Detalhamento).
 */

import { RiBankLine, RiCoinsLine, RiInboxLine, RiLineChartLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { useDrillAplicacoes } from "@/lib/hooks/controladoria"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { Button } from "@/components/tremor/Button"
import {
  DrillSectionTitle,
  drillRowBorder,
  drillTableWrap,
  drillThead,
  fmtBRL,
  fmtBRLSigned,
  toneClass,
} from "./drillKit"

type Props = { fundoId: string; data: string; dataAnterior?: string | null }

export function DrillAplicacoesContent({ fundoId, data, dataAnterior }: Props) {
  const q = useDrillAplicacoes(fundoId, data, dataAnterior)

  if (q.isError) {
    return (
      <ErrorState
        title="Falha ao carregar drill de Aplicações"
        description={(q.error as Error)?.message ?? "Erro desconhecido"}
        action={<Button variant="secondary" onClick={() => q.refetch()}>Tentar de novo</Button>}
      />
    )
  }
  if (q.isLoading || !q.data) {
    return (
      <div className="flex animate-pulse flex-col gap-2">
        {[0, 1, 2].map((i) => <div key={i} className="h-8 rounded bg-gray-100 dark:bg-gray-900" />)}
      </div>
    )
  }
  const d = q.data
  const menores = d.outras_linhas.filter((l) => Math.abs(l.delta) >= 1)

  return (
    <div className="flex flex-col gap-5">
      {/* Resumo: rendimento (impacto) vs capital (neutro) */}
      <div className="flex items-start gap-2 rounded border border-blue-200 bg-blue-50/50 px-3 py-2 dark:border-blue-900/60 dark:bg-blue-950/20">
        <RiLineChartLine className="mt-0.5 size-4 shrink-0 text-blue-600 dark:text-blue-400" aria-hidden />
        <div className="flex flex-col">
          <span className="text-[12px] font-medium text-blue-800 dark:text-blue-300">
            Rendimento dos fundos DI: {fmtBRLSigned(d.total_valorizacao)}
          </span>
          <span className="text-[11px] text-gray-600 dark:text-gray-400">
            Só o rendimento afeta a cota.
            {Math.abs(d.total_capital_liquido) >= 1 && (
              <> Capital aplicado/resgatado{" "}
                <strong className="text-gray-900 dark:text-gray-100">{fmtBRLSigned(d.total_capital_liquido)}</strong>
                {" "}é neutro (vai pra Giro e capital).</>
            )}
          </span>
        </div>
      </div>

      {/* ── Fundos DI: valorizacao vs capital ── */}
      <section>
        <DrillSectionTitle
          icon={RiBankLine}
          label="Fundos DI — rendimento vs capital"
          help="Caixa ocioso estacionado em fundos DI. Valorização = rendimento do dia (impacto na cota); capital = aplicação/resgate de caixa (neutro)."
        />
        {d.fundos_di.length === 0 ? (
          <EmptyState
            className="mt-2"
            icon={RiInboxLine}
            title="Sem fundos DI"
            description="Nenhuma posição em fundo DI externo no dia."
          />
        ) : (
          <div className={cx("mt-2", drillTableWrap)}>
            <table className="w-full whitespace-nowrap text-[12px] tabular-nums">
              <thead className={drillThead}>
                <tr>
                  <th className="px-3 py-1.5 text-left font-medium">Fundo</th>
                  <th className="px-3 py-1.5 text-right font-medium">Valorização</th>
                  <th className="px-3 py-1.5 text-right font-medium">Capital (neutro)</th>
                  <th className="px-3 py-1.5 text-right font-medium">ΔSaldo</th>
                </tr>
              </thead>
              <tbody>
                {d.fundos_di.map((f, i) => (
                  <tr key={`${f.fundo_nome}-${i}`} className={drillRowBorder}>
                    <td className="px-3 py-1.5 text-left text-gray-900 dark:text-gray-100">{f.fundo_nome}</td>
                    <td className={cx("px-3 py-1.5 text-right font-semibold", toneClass(f.valorizacao))}>{fmtBRLSigned(f.valorizacao)}</td>
                    <td className="px-3 py-1.5 text-right text-gray-500 dark:text-gray-400">
                      {Math.abs(f.aplicacao_resgate) < 1 ? "—" : fmtBRLSigned(f.aplicacao_resgate)}
                    </td>
                    <td className="px-3 py-1.5 text-right text-gray-600 dark:text-gray-300">{fmtBRLSigned(f.delta_valor)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── Linhas menores ── */}
      {menores.length > 0 && (
        <section>
          <DrillSectionTitle
            icon={RiCoinsLine}
            label="Outras linhas"
            help="TPF / Compromissada / Outros — ΔSaldo do dia (geralmente imaterial)."
          />
          <div className={cx("mt-2", drillTableWrap)}>
            <table className="w-full whitespace-nowrap text-[12px] tabular-nums">
              <thead className={drillThead}>
                <tr>
                  <th className="px-3 py-1.5 text-left font-medium">Linha</th>
                  <th className="px-3 py-1.5 text-right font-medium">Saldo D-1</th>
                  <th className="px-3 py-1.5 text-right font-medium">Saldo D0</th>
                  <th className="px-3 py-1.5 text-right font-medium">Δ</th>
                </tr>
              </thead>
              <tbody>
                {menores.map((l) => (
                  <tr key={l.linha} className={drillRowBorder}>
                    <td className="px-3 py-1.5 text-left text-gray-900 dark:text-gray-100">{l.label}</td>
                    <td className="px-3 py-1.5 text-right text-gray-500 dark:text-gray-400">{fmtBRL.format(l.valor_d1)}</td>
                    <td className="px-3 py-1.5 text-right text-gray-600 dark:text-gray-300">{fmtBRL.format(l.valor_d0)}</td>
                    <td className={cx("px-3 py-1.5 text-right", toneClass(l.delta))}>{fmtBRLSigned(l.delta)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <p className="text-[11px] text-gray-500 dark:text-gray-400">
        Op. Estruturadas (carrego de notas comerciais) também entra na barra de Aplicações — detalhe próprio na carteira.
      </p>
    </div>
  )
}
