"use client"

/**
 * DrillCprContent — conteudo do drill da categoria CPR.
 *
 * 3 secoes:
 *   1. Totais D-1 / D0 / Δ
 *   2. Aportes engaiolados detectados (badge destacado se houver)
 *   3. Agrupamento por natureza com top lines de cada grupo
 */

import * as React from "react"
import {
  RiBubbleChartLine,
  RiCoinsLine,
  RiInformationLine,
  RiInboxLine,
  type RemixiconComponentType,
} from "@remixicon/react"

import { cx } from "@/lib/utils"
import { useDrillCpr } from "@/lib/hooks/controladoria"
import type { CprNaturezaKey } from "@/lib/api-client"
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

const NATUREZA_DOT: Record<CprNaturezaKey, string> = {
  diferimento:         "bg-violet-500",
  apropriacao_taxa:    "bg-indigo-500",
  apropriacao_despesa: "bg-blue-500",
  iof_ir:              "bg-amber-500",
  provisao_liquidacao: "bg-emerald-500",
  aporte_engaiolado:   "bg-rose-500",
  outros:              "bg-gray-400",
}

const ESTADO_LABEL: Record<"entrou" | "devolvido" | "persiste", { label: string; tone: string }> = {
  entrou:    { label: "Novo em D0",     tone: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300" },
  devolvido: { label: "Devolvido em D0", tone: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300" },
  persiste:  { label: "Persiste",        tone: "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300" },
}

export type DrillCprContentProps = {
  fundoId:       string
  data:          string
  dataAnterior?: string
  /**
   * Lado do CPR (split por sinal, 2026-05-27): "receber" (valor>0, ativo) ou
   * "pagar" (valor<0, passivo). Omitido = legado (CPR net). No lado "pagar" os
   * valores no banco sao negativos; a UI exibe MAGNITUDE positiva (decisao
   * Ricardo) — `orient` faz o flip. O Δ segue a mesma orientacao da linha do
   * balanco (crescimento de magnitude = positivo/verde).
   */
  side?:         "receber" | "pagar"
}

export function DrillCprContent({ fundoId, data, dataAnterior, side }: DrillCprContentProps) {
  const q = useDrillCpr(fundoId, data, dataAnterior, side)

  // Magnitude: no lado pagar os valores vem negativos do CPR; exibimos abs.
  const orient = side === "pagar" ? -1 : 1
  const o = React.useCallback((v: number) => orient * v, [orient])
  const totaisLabel =
    side === "pagar" ? "Contas a Pagar · totais D-1 → D0"
    : side === "receber" ? "Contas a Receber · totais D-1 → D0"
    : "CPR · totais D-1 → D0"

  if (q.isError) {
    return (
      <ErrorState
        title="Falha ao carregar drill CPR"
        description={(q.error as Error)?.message ?? "Erro desconhecido"}
        action={<Button onClick={() => q.refetch()}>Tentar novamente</Button>}
      />
    )
  }

  if (q.isLoading || !q.data) {
    return (
      <div className="flex h-40 items-center justify-center text-[12px] text-gray-500 dark:text-gray-400">
        Carregando drill CPR…
      </div>
    )
  }

  const d = q.data
  const temAporteEngaiolado = d.aportes_engaiolados.length > 0

  return (
    <div className="flex flex-col gap-5">
      {/* ── Totais ── */}
      <section>
        <SectionTitle icon={RiCoinsLine} label={totaisLabel} />
        <div className="mt-2 grid grid-cols-3 gap-2 rounded border border-gray-200 p-3 dark:border-gray-800">
          <div>
            <p className="text-[10px] uppercase tracking-[0.04em] text-gray-400">D-1 · {d.qtd_linhas_d1} linha(s)</p>
            <p className="text-[14px] tabular-nums text-gray-700 dark:text-gray-300">{fmtBRL.format(o(d.cpr_total_d1))}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.04em] text-gray-400">D0 · {d.qtd_linhas_d0} linha(s)</p>
            <p className="text-[14px] font-medium tabular-nums text-gray-900 dark:text-gray-50">{fmtBRL.format(o(d.cpr_total_d0))}</p>
          </div>
          <div>
            <p className="text-[10px] uppercase tracking-[0.04em] text-gray-400">Δ</p>
            <p className={cx(
              "text-[14px] font-semibold tabular-nums",
              o(d.cpr_total_delta) > 0 ? "text-emerald-700 dark:text-emerald-400"
                : o(d.cpr_total_delta) < 0 ? "text-red-700 dark:text-red-400"
                : "text-gray-400 dark:text-gray-600",
            )}>{fmtBRLSigned(o(d.cpr_total_delta))}</p>
          </div>
        </div>
      </section>

      {/* ── Aportes engaiolados ── */}
      {temAporteEngaiolado && (
        <section>
          <SectionTitle
            icon={RiInformationLine}
            label="Aportes engaiolados"
            counter={`${d.aportes_engaiolados.length} rubrica(s) ativa(s)`}
          />
          <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
            Rubrica <code className="font-mono text-[10px]">Aporte</code> no CPR sinaliza
            recurso recebido sem integralização em nenhuma classe — fica engaiolado
            (pendente) por N dias até ser devolvido ou integralizado. Caso REALINVEST
            07-14/05/2026: R$ 124.500 persistiu por 5 dias úteis.
          </p>
          <div className="mt-2 flex flex-col gap-2">
            {d.aportes_engaiolados.map((ev, idx) => {
              const estadoMeta = ESTADO_LABEL[ev.estado]
              return (
                <div
                  key={idx}
                  className="overflow-hidden rounded border border-rose-200 bg-rose-50/40 dark:border-rose-900/60 dark:bg-rose-950/20"
                >
                  <div className="flex items-center justify-between gap-2 px-3 py-1.5">
                    <span className="flex items-center gap-2 truncate text-[12px] text-gray-700 dark:text-gray-200">
                      <span className={cx("inline-flex shrink-0 items-center rounded-sm px-1.5 py-0.5 text-[10px] font-medium", estadoMeta.tone)}>
                        {estadoMeta.label}
                      </span>
                      <span className="truncate">{ev.descricao}</span>
                    </span>
                  </div>
                  <div className="grid grid-cols-3 gap-2 border-t border-rose-200 bg-rose-50/60 px-3 py-1 text-[11px] tabular-nums dark:border-rose-900/60 dark:bg-rose-950/30">
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.04em] text-rose-700/70 dark:text-rose-300/70">D-1</p>
                      <p className="text-gray-700 dark:text-gray-300">{fmtBRL.format(o(ev.valor_d1))}</p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.04em] text-rose-700/70 dark:text-rose-300/70">D0</p>
                      <p className="font-medium text-gray-900 dark:text-gray-50">{fmtBRL.format(o(ev.valor_d0))}</p>
                    </div>
                    <div>
                      <p className="text-[10px] uppercase tracking-[0.04em] text-rose-700/70 dark:text-rose-300/70">Δ</p>
                      <p className={cx(
                        "font-semibold",
                        o(ev.delta_valor) > 0 ? "text-emerald-700 dark:text-emerald-400"
                          : o(ev.delta_valor) < 0 ? "text-red-700 dark:text-red-400"
                          : "text-gray-400 dark:text-gray-600",
                      )}>{fmtBRLSigned(o(ev.delta_valor))}</p>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </section>
      )}

      {/* ── Naturezas ── */}
      <section>
        <SectionTitle icon={RiBubbleChartLine} label="Por natureza" />
        {d.naturezas.length === 0 ? (
          <EmptyState
            icon={RiInboxLine}
            title={
              side === "pagar" ? "Nenhuma conta a pagar"
              : side === "receber" ? "Nenhuma conta a receber"
              : "Nenhuma rubrica de CPR"
            }
            description="Sem rubricas para este lado em ambas as datas."
            className="mt-2"
          />
        ) : (
          <div className="mt-2 flex flex-col gap-3">
            {d.naturezas.map((n) => (
              <div key={n.natureza} className="overflow-hidden rounded border border-gray-200 dark:border-gray-800">
                <div className="flex items-center justify-between gap-2 border-b border-gray-100 bg-gray-50/60 px-3 py-1.5 dark:border-gray-900 dark:bg-gray-900/30">
                  <span className="flex items-center gap-1.5 text-[12px]">
                    <span className={cx("inline-block size-1.5 rounded-full", NATUREZA_DOT[n.natureza])} aria-hidden />
                    <span className="font-medium text-gray-900 dark:text-gray-50">{n.label}</span>
                    <span className="text-[10px] text-gray-500 dark:text-gray-400">· {n.qtd_linhas} linha(s)</span>
                  </span>
                  <span className={cx(
                    "text-[12px] font-semibold tabular-nums",
                    o(n.sum_delta) > 0 ? "text-emerald-700 dark:text-emerald-400"
                      : o(n.sum_delta) < 0 ? "text-red-700 dark:text-red-400"
                      : "text-gray-400 dark:text-gray-600",
                  )}>Δ {fmtBRLSigned(o(n.sum_delta))}</span>
                </div>
                <table className="w-full text-[12px] tabular-nums">
                  <thead className="text-[10px] uppercase tracking-[0.04em] text-gray-400 dark:text-gray-600">
                    <tr>
                      <th className="px-3 py-1 text-left">Rubrica</th>
                      <th className="px-3 py-1 text-right">D-1</th>
                      <th className="px-3 py-1 text-right">D0</th>
                      <th className="px-3 py-1 text-right">Δ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {n.top_linhas.map((ln, idx) => (
                      <tr key={`${n.natureza}-${idx}-${ln.descricao}`} className="border-t border-gray-100 dark:border-gray-900">
                        <td className="px-3 py-1 text-gray-700 dark:text-gray-200" title={ln.descricao}>
                          <span className="block truncate max-w-[320px]">{ln.historico_traduzido || ln.descricao}</span>
                        </td>
                        <td className="px-3 py-1 text-right text-gray-500 dark:text-gray-400">{fmtBRL.format(o(ln.valor_d1))}</td>
                        <td className="px-3 py-1 text-right text-gray-900 dark:text-gray-50">{fmtBRL.format(o(ln.valor_d0))}</td>
                        <td className={cx(
                          "px-3 py-1 text-right font-medium",
                          o(ln.delta_valor) > 0 ? "text-emerald-700 dark:text-emerald-400"
                            : o(ln.delta_valor) < 0 ? "text-red-700 dark:text-red-400"
                            : "text-gray-400",
                        )}>{fmtBRLSigned(o(ln.delta_valor))}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

function SectionTitle({
  icon: Icon, label, counter,
}: {
  icon: RemixiconComponentType
  label: string
  counter?: string
}) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <h4 className="flex items-center gap-1.5 text-[12px] font-semibold uppercase tracking-[0.04em] text-gray-700 dark:text-gray-300">
        <Icon className="size-3.5 text-gray-400 dark:text-gray-500" aria-hidden />
        {label}
      </h4>
      {counter && (
        <span className="text-[11px] text-gray-500 dark:text-gray-400 tabular-nums">{counter}</span>
      )}
    </div>
  )
}
