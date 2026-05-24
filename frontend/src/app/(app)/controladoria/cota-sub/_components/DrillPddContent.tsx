"use client"

/**
 * DrillPddContent — conteudo do drill da categoria PDD.
 *
 * 3 secoes:
 *   1. PDD consolidado (fonte do balanco) + divergencia vs granular
 *   2. Papeis em WOP (write-off — perda do PDD constituido)
 *   3. Top N papeis por |Δ valor_pdd|
 *
 * Matriz de migracao A/B/C/D/E/F/G/H ↔ WOP/NOVO removida em 2026-05-24
 * (a pedido do Ricardo — densa demais pro slot direito, baixo valor pratico
 * frente ao detalhamento por papel das secoes 2 e 3).
 */

import * as React from "react"
import {
  RiBarChartHorizontalLine,
  RiErrorWarningLine,
  RiPieChartLine,
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
  // Sem override de threshold/top_n — usa defaults do backend (0.01 / 1000).
  // Confirmado 2026-05-24: detalhamento mostra TODOS os papeis com variacao,
  // nao apenas top. Caso 13/05 REALINVEST: filtro >= R$ 100 escondia 49
  // dos 51 papeis com Δ real.
  const q = useDrillPdd(fundoId, data, { dataAnterior })

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
  const pddAtivoDelta = d.pdd_granular_ex_wop_d0 - d.pdd_granular_ex_wop_d1
  const wopDelta = d.pdd_granular_wop_d0 - d.pdd_granular_wop_d1

  return (
    <div className="flex flex-col gap-5">
      {/* ── PDD granular separado por bucket (PDD ativo vs WOP) ── */}
      <section>
        <SectionTitle icon={RiPieChartLine} label="Composição da PDD" />
        <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
          Σ <code className="font-mono">valor_pdd</code> de <code className="font-mono">wh_estoque_recebivel</code>,
          separado por bucket. PDD ativo (faixas A-H) é o que entra no
          balanço da Cota Sub Jr. WOP já está fora — informativo.
        </p>
        <div className="mt-2 grid grid-cols-2 gap-2">
          <Card label="PDD ativo (faixas A-H · entra no balanço)">
            <ValueGrid d1={d.pdd_granular_ex_wop_d1} d0={d.pdd_granular_ex_wop_d0} delta={pddAtivoDelta} />
          </Card>
          <Card label="WOP (write-off · já fora do balanço)" muted>
            <ValueGrid d1={d.pdd_granular_wop_d1} d0={d.pdd_granular_wop_d0} delta={wopDelta} />
          </Card>
        </div>
      </section>

      {d.motivo_indisponivel && (
        <div className="flex items-start gap-2 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300">
          <RiErrorWarningLine className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          <div>
            <strong>Estoque granular indisponível:</strong> {d.motivo_indisponivel}.
            Papéis em write-off e variações por papel ficam vazios — só
            os totais acima são confiáveis.
          </div>
        </div>
      )}

      {/* ── WOP destacado ── */}
      {d.papeis_wop.length > 0 && (
        <section>
          <SectionTitle
            icon={RiErrorWarningLine}
            label="Papéis que viraram WOP no dia"
            counter={`${d.papeis_wop.length} papel(eis) · Σ PDD perdido ${fmtBRL.format(d.papeis_wop_total_pdd_d1)}`}
          />
          <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
            Papéis que existiam em D-1 (faixa A-H) e migraram para WOP em D0
            sem aparecer em <code className="font-mono">wh_liquidacao_recebivel</code>.
            O PDD constituído cai como perda definitiva.
          </p>
          <PapeisTable papeis={d.papeis_wop} highlightDelta={false} />
        </section>
      )}

      {/* ── Todos os papeis com variacao de PDD ── */}
      <section>
        <SectionTitle
          icon={RiBarChartHorizontalLine}
          label="Papéis com variação de PDD"
          counter={
            d.top_papeis_total_acima_threshold > d.top_papeis.length
              ? `${d.top_papeis.length} listados · ${d.top_papeis_total_acima_threshold} no total`
              : `${d.top_papeis.length} papel(eis)`
          }
        />
        <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
          Todos os papéis ex-WOP cujo <code className="font-mono">valor_pdd</code>{" "}
          mudou entre D-1 e D0 (write-off do dia já listado na seção anterior).
          Ordenado por magnitude decrescente.
          {d.top_papeis_total_acima_threshold > d.top_papeis.length && (
            <> Lista cortada nos {d.top_papeis.length} primeiros — há mais {d.top_papeis_total_acima_threshold - d.top_papeis.length} papéis com variação menor abaixo desse corte.</>
          )}
        </p>
        {d.top_papeis.length === 0 ? (
          <EmptyState
            icon={RiInboxLine}
            title="Sem variação"
            description="Nenhum papel teve alteração de PDD entre D-1 e D0."
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

function Card({ label, children, muted }: { label: string; children: React.ReactNode; muted?: boolean }) {
  return (
    <div className={cx(
      "rounded border p-3",
      muted
        ? "border-gray-200 bg-gray-50/40 dark:border-gray-800 dark:bg-gray-900/20"
        : "border-gray-200 dark:border-gray-800",
    )}>
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
