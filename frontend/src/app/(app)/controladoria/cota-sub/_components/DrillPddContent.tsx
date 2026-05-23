"use client"

/**
 * DrillPddContent — conteudo do drill da categoria PDD.
 *
 * 4 secoes:
 *   1. PDD consolidado (fonte do balanco) + divergencia vs granular
 *   2. Matriz de migracao A/B/C/D/E/F/G/H ↔ WOP/NOVO (heatmap visual)
 *   3. Papeis em WOP (write-off — perda do PDD constituido)
 *   4. Top N papeis por |Δ valor_pdd|
 */

import * as React from "react"
import {
  RiBarChartHorizontalLine,
  RiErrorWarningLine,
  RiPieChartLine,
  RiArrowLeftRightLine,
  RiInboxLine,
  type RemixiconComponentType,
} from "@remixicon/react"

import { cx } from "@/lib/utils"
import { useDrillPdd } from "@/lib/hooks/controladoria"
import type { DrillPddPapel, PddFaixaKey } from "@/lib/api-client"
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

// Ordem visual da matriz — eixo Y (de) e X (para).
const FAIXAS_DE: PddFaixaKey[] = ["NOVO", "A", "B", "C", "D", "E", "F", "G", "H"]
const FAIXAS_PARA: PddFaixaKey[] = ["A", "B", "C", "D", "E", "F", "G", "H", "WOP"]

// Cor de dot por faixa (paleta tailwind ad-hoc — Modo Iteracao de Design ativo).
const FAIXA_DOT: Record<PddFaixaKey, string> = {
  A:    "bg-emerald-500",
  B:    "bg-lime-500",
  C:    "bg-yellow-500",
  D:    "bg-orange-500",
  E:    "bg-red-500",
  F:    "bg-red-700",
  G:    "bg-red-800",
  H:    "bg-rose-900",
  WOP:  "bg-gray-500",
  NOVO: "bg-blue-500",
}

export type DrillPddContentProps = {
  fundoId:       string
  data:          string
  dataAnterior?: string
}

export function DrillPddContent({ fundoId, data, dataAnterior }: DrillPddContentProps) {
  const q = useDrillPdd(fundoId, data, { dataAnterior, thresholdBrl: 100, topN: 20 })

  if (q.isError) {
    return (
      <ErrorState
        title="Falha ao carregar drill PDD"
        description={(q.error as Error)?.message ?? "Erro desconhecido"}
        action={<Button onClick={() => q.refetch()}>Tentar novamente</Button>}
      />
    )
  }

  if (q.isLoading || !q.data) {
    return (
      <div className="flex h-40 items-center justify-center text-[12px] text-gray-500 dark:text-gray-400">
        Carregando drill PDD…
      </div>
    )
  }

  const d = q.data
  const granularDelta = d.pdd_granular_d0 - d.pdd_granular_d1
  const divergenciaGranularVsConsolidado = granularDelta - d.pdd_consolidado_delta
  const temDivergencia = Math.abs(divergenciaGranularVsConsolidado) > 1

  return (
    <div className="flex flex-col gap-5">
      {/* ── PDD consolidado vs granular ── */}
      <section>
        <SectionTitle icon={RiPieChartLine} label="PDD consolidado · fonte do balanço" />
        <div className="mt-2 grid grid-cols-2 gap-2">
          <Card label="Consolidado (wh_posicao_outros_ativos · PDD)">
            <ValueGrid d1={d.pdd_consolidado_d1} d0={d.pdd_consolidado_d0} delta={d.pdd_consolidado_delta} />
          </Card>
          <Card label="Granular (Σ wh_estoque_recebivel.valor_pdd)">
            <ValueGrid d1={d.pdd_granular_d1} d0={d.pdd_granular_d0} delta={granularDelta} />
          </Card>
        </div>
        {temDivergencia && (
          <div className="mt-2 flex items-start gap-2 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300">
            <RiErrorWarningLine className="mt-0.5 size-3.5 shrink-0" aria-hidden />
            <div>
              <strong>Divergência granular vs consolidado: {fmtBRLSigned(divergenciaGranularVsConsolidado)}.</strong>{" "}
              Possíveis causas: defasagem na publicação do estoque pela QiTech, write-off
              fantasma (papel saiu do estoque sem aparecer aqui), ou ajuste contábil de
              PDD aplicado fora do estoque granular.
            </div>
          </div>
        )}
      </section>

      {/* ── Matriz de migracao ── */}
      <section>
        <SectionTitle icon={RiArrowLeftRightLine} label="Matriz de migração entre faixas" />
        <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
          Cada célula mostra <em>qtd papéis</em> e <em>Σ Δ PDD</em>. Diagonal (mesma faixa)
          = papéis que permaneceram. Coluna <strong>WOP</strong> = write-off (papel sumiu
          do estoque). Linha <strong>NOVO</strong> = papel entrou em D0 sem existir em D-1.
        </p>
        {d.motivo_indisponivel ? (
          <EmptyState
            icon={RiErrorWarningLine}
            title="Estoque granular indisponível"
            description={d.motivo_indisponivel}
            className="mt-2"
          />
        ) : (
          <MatrizHeatmap matriz={d.matriz} />
        )}
      </section>

      {/* ── WOP destacado ── */}
      {d.papeis_wop.length > 0 && (
        <section>
          <SectionTitle
            icon={RiErrorWarningLine}
            label="Papéis em write-off (WOP)"
            counter={`${d.papeis_wop.length} papel(eis) · Σ PDD perdido ${fmtBRL.format(d.papeis_wop_total_pdd_d1)}`}
          />
          <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
            Papéis que existiam em D-1 mas sumiram em D0 sem aparecer em wh_liquidacao_recebivel.
            O PDD constituído cai como perda definitiva.
          </p>
          <PapeisTable papeis={d.papeis_wop} highlightDelta={false} />
        </section>
      )}

      {/* ── Top N papeis ── */}
      <section>
        <SectionTitle
          icon={RiBarChartHorizontalLine}
          label="Top papéis por |Δ PDD|"
          counter={
            d.top_papeis_total_acima_threshold > d.top_papeis.length
              ? `${d.top_papeis.length} de ${d.top_papeis_total_acima_threshold} acima de ${fmtBRL.format(d.top_papeis_threshold_brl)}`
              : `${d.top_papeis.length} papel(eis) acima de ${fmtBRL.format(d.top_papeis_threshold_brl)}`
          }
        />
        {d.top_papeis.length === 0 ? (
          <EmptyState
            icon={RiInboxLine}
            title="Sem variação relevante"
            description={`Nenhum papel teve |Δ PDD| > ${fmtBRL.format(d.top_papeis_threshold_brl)} entre D-1 e D0.`}
            className="mt-2"
          />
        ) : (
          <PapeisTable papeis={d.top_papeis} highlightDelta />
        )}
      </section>
    </div>
  )
}

// ─── Sub-componentes ────────────────────────────────────────────────────────

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

function Card({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded border border-gray-200 p-3 dark:border-gray-800">
      <p className="text-[10px] uppercase tracking-[0.04em] text-gray-500 dark:text-gray-400">{label}</p>
      <div className="mt-1.5">{children}</div>
    </div>
  )
}

function ValueGrid({ d1, d0, delta }: { d1: number; d0: number; delta: number }) {
  return (
    <div className="grid grid-cols-3 gap-2 text-[12px] tabular-nums">
      <div>
        <p className="text-[10px] text-gray-400">D-1</p>
        <p className="text-gray-700 dark:text-gray-300">{fmtBRL.format(d1)}</p>
      </div>
      <div>
        <p className="text-[10px] text-gray-400">D0</p>
        <p className="font-medium text-gray-900 dark:text-gray-50">{fmtBRL.format(d0)}</p>
      </div>
      <div>
        <p className="text-[10px] text-gray-400">Δ</p>
        <p className={cx(
          "font-semibold",
          delta > 0 ? "text-red-700 dark:text-red-400"
            : delta < 0 ? "text-emerald-700 dark:text-emerald-400"
            : "text-gray-400 dark:text-gray-600",
        )}>{fmtBRLSigned(delta)}</p>
      </div>
    </div>
  )
}

function MatrizHeatmap({ matriz }: { matriz: { faixa_de: PddFaixaKey; faixa_para: PddFaixaKey; qtd_papeis: number; sum_delta_pdd: number }[] }) {
  // Reconstroi grid bidimensional. Backend devolve so celulas preenchidas.
  const celulaPorChave = new Map<string, { qtd_papeis: number; sum_delta_pdd: number }>()
  for (const c of matriz) {
    celulaPorChave.set(`${c.faixa_de}|${c.faixa_para}`, c)
  }

  const maxDelta = matriz.reduce((acc, c) => Math.max(acc, Math.abs(c.sum_delta_pdd)), 0)

  return (
    <div className="mt-2 overflow-x-auto">
      <table className="text-[11px] tabular-nums">
        <thead>
          <tr>
            <th className="px-2 py-1 text-left text-[10px] uppercase tracking-[0.04em] text-gray-400">
              De \ Para
            </th>
            {FAIXAS_PARA.map((f) => (
              <th key={f} className="px-2 py-1 text-center text-[10px] font-medium text-gray-500 dark:text-gray-400">
                <span className="inline-flex items-center gap-1">
                  <span className={cx("inline-block size-1.5 rounded-full", FAIXA_DOT[f])} aria-hidden />
                  {f}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {FAIXAS_DE.map((fde) => (
            <tr key={fde}>
              <td className="px-2 py-1 text-left">
                <span className="inline-flex items-center gap-1 text-[10px] font-medium text-gray-500 dark:text-gray-400">
                  <span className={cx("inline-block size-1.5 rounded-full", FAIXA_DOT[fde])} aria-hidden />
                  {fde}
                </span>
              </td>
              {FAIXAS_PARA.map((fpara) => {
                const cel = celulaPorChave.get(`${fde}|${fpara}`)
                const isDiagonal = fde === fpara
                if (!cel) {
                  return (
                    <td key={fpara} className="px-2 py-1 text-center text-gray-300 dark:text-gray-800">·</td>
                  )
                }
                const intensity = maxDelta > 0 ? Math.min(1, Math.abs(cel.sum_delta_pdd) / maxDelta) : 0
                const bg = cel.sum_delta_pdd > 0
                  ? `rgba(220, 38, 38, ${0.08 + intensity * 0.45})`     // red (PDD aumentou)
                  : cel.sum_delta_pdd < 0
                  ? `rgba(16, 185, 129, ${0.08 + intensity * 0.45})`    // emerald (PDD diminuiu)
                  : "transparent"
                return (
                  <td
                    key={fpara}
                    style={{ backgroundColor: bg }}
                    className={cx(
                      "px-2 py-1 text-center",
                      isDiagonal && "ring-1 ring-inset ring-gray-200 dark:ring-gray-800",
                    )}
                    title={`${fde} → ${fpara}: ${cel.qtd_papeis} papel(eis), Δ ${fmtBRLSigned(cel.sum_delta_pdd)}`}
                  >
                    <div className="font-medium text-gray-900 dark:text-gray-50">{cel.qtd_papeis}</div>
                    {Math.abs(cel.sum_delta_pdd) >= 1 && (
                      <div className={cx(
                        "text-[10px]",
                        cel.sum_delta_pdd > 0 ? "text-red-700 dark:text-red-400" : "text-emerald-700 dark:text-emerald-400",
                      )}>
                        {fmtBRLSigned(cel.sum_delta_pdd)}
                      </div>
                    )}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function PapeisTable({ papeis, highlightDelta }: { papeis: DrillPddPapel[]; highlightDelta: boolean }) {
  return (
    <div className="mt-2 overflow-hidden rounded border border-gray-200 dark:border-gray-800">
      <table className="w-full text-[12px] tabular-nums">
        <thead className="bg-gray-50 text-[10px] font-medium uppercase tracking-[0.04em] text-gray-500 dark:bg-gray-900/30 dark:text-gray-400">
          <tr>
            <th className="px-3 py-1.5 text-left">Cedente / Sacado</th>
            <th className="px-3 py-1.5 text-left">Título</th>
            <th className="px-3 py-1.5 text-center">Faixa</th>
            <th className="px-3 py-1.5 text-right">Nominal</th>
            <th className="px-3 py-1.5 text-right">PDD D-1</th>
            <th className="px-3 py-1.5 text-right">PDD D0</th>
            <th className="px-3 py-1.5 text-right">Δ</th>
          </tr>
        </thead>
        <tbody>
          {papeis.map((p, idx) => (
            <tr key={`${p.cedente_doc}-${p.seu_numero}-${p.numero_documento}-${idx}`} className="border-t border-gray-100 dark:border-gray-900">
              <td className="px-3 py-1.5 text-gray-700 dark:text-gray-200" title={`${p.cedente_doc} / ${p.sacado_doc}`}>
                <div className="truncate max-w-[200px] font-medium text-gray-900 dark:text-gray-50">{p.cedente_nome}</div>
                <div className="truncate max-w-[200px] text-[10px] text-gray-500 dark:text-gray-400">→ {p.sacado_nome}</div>
              </td>
              <td className="px-3 py-1.5 font-mono text-[11px] text-gray-500 dark:text-gray-400" title={p.numero_documento}>
                {p.seu_numero}
              </td>
              <td className="px-3 py-1.5 text-center">
                <span className="inline-flex items-center gap-1 text-[10px]">
                  <span className={cx("inline-block size-1.5 rounded-full", FAIXA_DOT[p.faixa_pdd_d1 ?? "NOVO"])} aria-hidden />
                  <span className="text-gray-500">{p.faixa_pdd_d1 ?? "—"}</span>
                  <span className="text-gray-400">→</span>
                  <span className={cx("inline-block size-1.5 rounded-full", FAIXA_DOT[p.faixa_pdd_d0 ?? "WOP"])} aria-hidden />
                  <span className="text-gray-900 dark:text-gray-50">{p.faixa_pdd_d0 ?? "WOP"}</span>
                </span>
              </td>
              <td className="px-3 py-1.5 text-right text-gray-500 dark:text-gray-400">{fmtBRL.format(p.valor_nominal)}</td>
              <td className="px-3 py-1.5 text-right text-gray-500 dark:text-gray-400">{fmtBRL.format(p.valor_pdd_d1)}</td>
              <td className="px-3 py-1.5 text-right text-gray-900 dark:text-gray-50">{fmtBRL.format(p.valor_pdd_d0)}</td>
              <td className={cx(
                "px-3 py-1.5 text-right",
                highlightDelta && "font-semibold",
                p.delta_valor_pdd > 0 ? "text-red-700 dark:text-red-400"
                  : p.delta_valor_pdd < 0 ? "text-emerald-700 dark:text-emerald-400"
                  : "text-gray-400",
              )}>
                {fmtBRLSigned(p.delta_valor_pdd)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
