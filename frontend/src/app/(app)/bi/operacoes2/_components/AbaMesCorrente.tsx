// src/app/(app)/bi/operacoes2/_components/AbaMesCorrente.tsx
//
// Aba 0 da pagina /bi/operacoes2 — Mes Corrente (variance decomposition).
//
// Layout:
//   Linha 1: Narrative master sentence (1 frase multi-KPI) +
//            SegmentSwitch de dimensao (Por produto / Por UA / Por faixa de ticket)
//   Linha 2: grid 2x3 de cards de decomposicao
//     [VOP variance bridge]   [Receita variance bridge]   [Taxa PVM bridge]
//     [Prazo PVM bridge]      [Mix dumbbell]              [Concentracao HHI]
//   Linha 3: footer com paridade DU + label de comparacao
//
// Click num driver de VOP/Receita abre DrillDownSheet com bridge MTD +
// projecao lado a lado. Click em Mix/Intra de Taxa/Prazo abre sheet com
// top contributors detalhados.

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"

import { Card } from "@/components/tremor/Card"
import {
  ConcentracaoDeltaCard,
  MixDeltaBarCard,
  PvmBridgeCard,
  SegmentSwitch,
  VarianceBridgeCard,
  type SegmentDef,
} from "@/design-system/components"
import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"
import { cardTokens } from "@/design-system/tokens/card"
import { biOperacoes2 } from "@/lib/api-client"
import type {
  Operacoes2DriverContribution,
  Operacoes2Dimension,
  Operacoes2PvmBridgeData,
  Operacoes2VarianceBridgeData,
  Operacoes2ProjectionBridgeData,
} from "@/lib/api-client"
import { useBiFilters } from "@/lib/hooks/useBiFilters"
import { cx } from "@/lib/utils"

// ─── Formatadores ──────────────────────────────────────────────────────────

const fmtBRLCompact = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 2,
})

const fmtBRLFull = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
})

// ─── SegmentSwitch options ─────────────────────────────────────────────────
//
// "Por faixa de ticket" foi removido em 2026-05-09: gerava ruido e raramente
// era util frente a "Por produto" / "Por UA". Backend ainda suporta o valor
// no enum (`Operacoes2Dimension`) — apenas escondido na UI.

const DIMENSION_OPTIONS: SegmentDef<Operacoes2Dimension>[] = [
  { value: "produto", label: "Produto" },
  { value: "ua", label: "UA" },
]

// ─── DrillDown content (per-KPI views) ─────────────────────────────────────

type DrillState =
  | { kind: "variance"; kpi: "VOP" | "Receita"; data: Operacoes2VarianceBridgeData; projection: Operacoes2ProjectionBridgeData | null }
  | { kind: "pvm"; kpi: "Taxa" | "Prazo"; effect: "mix" | "intra"; data: Operacoes2PvmBridgeData }

function VarianceDrillDownContent({
  state,
}: {
  state: Extract<DrillState, { kind: "variance" }>
}) {
  const allDrivers = [...state.data.drivers]
  if (state.data.outros_rollup) allDrivers.push(state.data.outros_rollup)
  return (
    <div className="flex flex-col gap-4 p-6">
      <section>
        <h4 className="mb-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
          Decomposição completa do delta {state.kpi} MTD
        </h4>
        <ul className="divide-y divide-gray-100 dark:divide-gray-900">
          {allDrivers.map((d) => (
            <DriverRow key={d.member_id} driver={d} />
          ))}
        </ul>
      </section>
      {state.projection && (
        <section>
          <h4 className="mb-2 text-sm font-semibold text-gray-900 dark:text-gray-100">
            Projeção de fechamento (linear)
          </h4>
          <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
            Atual: {fmtBRLFull.format(state.projection.current_anchor_value)} ·
            Projetado: {fmtBRLFull.format(state.projection.projected_close_value)} (
            {state.projection.delta_pct !== null
              ? `${state.projection.delta_pct >= 0 ? "+" : ""}${state.projection.delta_pct.toFixed(1).replace(".", ",")}%`
              : "—"}
            )
          </p>
          <ul className="divide-y divide-gray-100 dark:divide-gray-900">
            {state.projection.drivers.map((d) => (
              <DriverRow key={`proj-${d.member_id}`} driver={d} mode="projection" />
            ))}
            {state.projection.outros_rollup && (
              <DriverRow
                driver={state.projection.outros_rollup}
                mode="projection"
              />
            )}
          </ul>
        </section>
      )}
    </div>
  )
}

function PvmDrillDownContent({
  state,
}: {
  state: Extract<DrillState, { kind: "pvm" }>
}) {
  const list =
    state.effect === "mix"
      ? [...state.data.top_mix_contributors,
         ...(state.data.outros_mix_rollup ? [state.data.outros_mix_rollup] : [])]
      : [...state.data.top_intra_contributors,
         ...(state.data.outros_intra_rollup ? [state.data.outros_intra_rollup] : [])]
  const unitLabel = state.data.delta_unidade === "pp" ? "pp" : "d"

  return (
    <div className="flex flex-col gap-3 p-6">
      <h4 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
        {state.kpi} —{" "}
        {state.effect === "mix"
          ? "Mix (mudança de composição)"
          : "Categoria (variação dentro da categoria)"}
      </h4>
      <p className="text-xs text-gray-500 dark:text-gray-400">
        {state.effect === "mix"
          ? "Membros que mudaram de share entre os períodos, ponderados pela média prior."
          : "Membros cujo valor médio mudou no período atual, ponderados pelo share atual."}
      </p>
      <ul className="divide-y divide-gray-100 dark:divide-gray-900">
        {list.map((d) => {
          const sinal = d.contribution_brl >= 0 ? "+" : "−"
          const abs = Math.abs(d.contribution_brl)
          const valueText =
            unitLabel === "pp"
              ? `${sinal}${abs.toFixed(2).replace(".", ",")}pp`
              : `${sinal}${abs.toFixed(1).replace(".", ",")}d`
          return (
            <li
              key={d.member_id}
              className="flex items-center justify-between gap-3 py-2"
            >
              <span className="truncate text-sm text-gray-700 dark:text-gray-300">
                {d.member_label}
              </span>
              <span
                className={cx(
                  "shrink-0 text-sm tabular-nums",
                  d.contribution_brl >= 0
                    ? "text-emerald-600 dark:text-emerald-400"
                    : "text-red-600 dark:text-red-400",
                )}
              >
                {valueText}
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function DriverRow({
  driver,
  mode = "variance",
}: {
  driver: Operacoes2DriverContribution
  mode?: "variance" | "projection"
}) {
  const sinal = driver.contribution_brl >= 0 ? "+" : "−"
  const colorClass =
    driver.contribution_brl >= 0
      ? "text-emerald-600 dark:text-emerald-400"
      : "text-red-600 dark:text-red-400"
  return (
    <li className="flex items-center justify-between gap-3 py-2">
      <div className="min-w-0">
        <p className="truncate text-sm text-gray-900 dark:text-gray-100">
          {driver.member_label}
        </p>
        <p className="text-[11px] text-gray-500 dark:text-gray-500">
          {mode === "projection" ? "Atual" : "Anterior"}:{" "}
          {fmtBRLCompact.format(driver.prior_value)} →{" "}
          {mode === "projection" ? "Projetado" : "Atual"}:{" "}
          {fmtBRLCompact.format(driver.current_value)}
        </p>
      </div>
      <div className="flex shrink-0 flex-col items-end">
        <span className={cx("text-sm tabular-nums font-medium", colorClass)}>
          {sinal} {fmtBRLCompact.format(Math.abs(driver.contribution_brl))}
        </span>
        {driver.contribution_pct !== null && (
          <span className="text-[11px] text-gray-500 dark:text-gray-500">
            {Math.abs(driver.contribution_pct).toFixed(1).replace(".", ",")}% do |Δ|
          </span>
        )}
      </div>
    </li>
  )
}

// ─── AbaMesCorrente ────────────────────────────────────────────────────────

export function AbaMesCorrente() {
  const { filtersWithFocus } = useBiFilters()
  const [dimension, setDimension] =
    React.useState<Operacoes2Dimension>("produto")
  const [drill, setDrill] = React.useState<DrillState | null>(null)

  const q = useQuery({
    queryKey: ["bi", "operacoes2", "aba1-mes-corrente", filtersWithFocus, dimension],
    queryFn: () => biOperacoes2.abaMesCorrente(filtersWithFocus, dimension),
  })

  const data = q.data?.data

  if (q.isLoading) {
    return <AbaSkeleton />
  }
  if (q.isError || !data) {
    return (
      <div className="flex flex-col items-center justify-center gap-2 py-16">
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Não foi possível carregar a decomposição do mês corrente.
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4">
      {/* Linha 1 — SegmentSwitch (lente da decomposicao). Sem card.
          Narrative sentence dropada em 2026-05-09: KPIs ja vivem no headerKpi
          de cada chart-card; a frase em prosa duplicava informacao. Ver
          docs/bi-patterns-presentacao-dados.md §1.2 e diagnostico do user
          em sessao de 2026-05-09. */}
      <div className="flex items-center gap-3 px-1">
        <span className="text-xs text-gray-500 dark:text-gray-400">
          Decompor por:
        </span>
        <SegmentSwitch
          options={DIMENSION_OPTIONS}
          value={data.dimension_active}
          onChange={setDimension}
          ariaLabel="Dimensão da decomposição"
        />
      </div>

      {/* Linha 2 — grid 2x3 de cards */}
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        <VarianceBridgeCard
          data={data.vop}
          title="VOP"
          onDriverClick={() =>
            setDrill({
              kind: "variance",
              kpi: "VOP",
              data: data.vop,
              projection: data.vop_projecao,
            })
          }
          footer={
            data.vop_projecao && (
              <button
                type="button"
                className="text-xs text-blue-600 hover:underline dark:text-blue-400"
                onClick={() =>
                  setDrill({
                    kind: "variance",
                    kpi: "VOP",
                    data: data.vop,
                    projection: data.vop_projecao,
                  })
                }
              >
                Ver projeção de fechamento →
              </button>
            )
          }
        />
        <VarianceBridgeCard
          data={data.receita}
          title="Receita contratada"
          onDriverClick={() =>
            setDrill({
              kind: "variance",
              kpi: "Receita",
              data: data.receita,
              projection: data.receita_projecao,
            })
          }
          footer={
            data.receita_projecao && (
              <button
                type="button"
                className="text-xs text-blue-600 hover:underline dark:text-blue-400"
                onClick={() =>
                  setDrill({
                    kind: "variance",
                    kpi: "Receita",
                    data: data.receita,
                    projection: data.receita_projecao,
                  })
                }
              >
                Ver projeção de fechamento →
              </button>
            )
          }
        />
        <PvmBridgeCard
          data={data.taxa}
          title="Taxa média"
          onEffectClick={(kind) =>
            setDrill({ kind: "pvm", kpi: "Taxa", effect: kind, data: data.taxa })
          }
        />
        <PvmBridgeCard
          data={data.prazo}
          title="Prazo médio"
          // Override explicito do good: prazo subindo NAO e bom (operacoes mais
          // longas). Auto-derivacao default usa good=delta>=0; aqui invertemos.
          headerKpi={{
            value: `${data.prazo.current_anchor_value.toFixed(1).replace(".", ",")} d`,
            delta: {
              value: data.prazo.delta,
              suffix: "d",
              good: data.prazo.delta < 0,
            },
            deltaSub: data.prazo.current_anchor_label,
          }}
          onEffectClick={(kind) =>
            setDrill({ kind: "pvm", kpi: "Prazo", effect: kind, data: data.prazo })
          }
        />
        <MixDeltaBarCard data={data.mix} title="Mix de produtos" />
        <ConcentracaoDeltaCard data={data.concentracao} />
      </div>

      {/* Footer com metadata de comparacao */}
      <p className="text-[11px] text-gray-500 dark:text-gray-500">
        {data.comparacao_label_pt}
        {data.du_disponivel && data.vop_projecao
          ? " · projeção linear (linear-pace)"
          : ""}
      </p>

      {/* DrillDownSheet — conteudo dinamico por tipo de drill */}
      <DrillDownSheet
        open={drill !== null}
        onClose={() => setDrill(null)}
        title={
          drill?.kind === "variance"
            ? `${drill.kpi} — variação MTD + projeção`
            : drill?.kind === "pvm"
              ? `${drill.kpi} — efeito ${drill.effect}`
              : "Detalhe"
        }
      >
        {drill?.kind === "variance" && <VarianceDrillDownContent state={drill} />}
        {drill?.kind === "pvm" && <PvmDrillDownContent state={drill} />}
      </DrillDownSheet>
    </div>
  )
}

function AbaSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <Card className={cx(cardTokens.body, "h-16 animate-pulse")} />
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <Card key={i} className="h-72 animate-pulse" />
        ))}
      </div>
    </div>
  )
}
