// src/app/(app)/bi/operacoes3/_components/HeroVopMes.tsx
//
// Hero (L2) da pagina /bi/operacoes3 — VOP do mes corrente em dois cards
// complementares:
//   - VOP DIARIO (col-span-2 ~66%): "como esta o ritmo no calendario"
//     + FilterChip no header do card "UA: Todas | FIDC | Securitizadora ..."
//       (client-side, sem refetch — pivota `vopDiarioPorUa` ja no bundle).
//     + Header KPI se adapta a UA selecionada (valor_mtd + Δ VOP-DU da UA
//       em `vop_mtd_por_ua`); "Todas" usa o agregado do `vop`.
//   - VOP WATERFALL (col-span-1 ~33%): "quem moveu o ponteiro"
//     + SegmentSwitch DENTRO do card (slot actions do header) "Produto | UA"
//       controla `dimension` global, refetch via `onDimensionChange`.
//     + Footer "Ver detalhes →" abre DrillDownSheet com decomposicao
//       completa (drivers + projecao de fechamento).
//
// Click numa barra do VOP DIARIO -> DrillDownSheet "operacoes do dia X".

"use client"

import * as React from "react"
import { RiBuilding2Line } from "@remixicon/react"

import {
  EvolucaoDiariaCard,
  FilterChip,
  SegmentSwitch,
  VarianceBridgeCard,
  type EvolucaoDiariaPonto,
  type SegmentDef,
} from "@/design-system/components"
import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"
import type {
  Operacoes2Dimension,
  Operacoes2VarianceBridgeData,
  Operacoes2VopDiarioPonto,
  Operacoes2VopDiarioPorUaPonto,
  Operacoes2VopMtdPorUa,
} from "@/lib/api-client"
import { cx } from "@/lib/utils"

import { DrillOperacoesDoDia } from "./DrillOperacoesDoDia"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
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

const _MESES_LONGO_PT = [
  "Janeiro",
  "Fevereiro",
  "Março",
  "Abril",
  "Maio",
  "Junho",
  "Julho",
  "Agosto",
  "Setembro",
  "Outubro",
  "Novembro",
  "Dezembro",
]

function presetLabelFromIso(iso: string): string {
  const [y, m] = iso.split("-").map(Number)
  if (!y || !m) return ""
  return `${_MESES_LONGO_PT[m - 1]}/${y}`
}

function dataLongPt(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number)
  if (!y || !m || !d) return iso
  const dt = new Date(y, m - 1, d)
  return dt.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  })
}

// Waterfall: dimensoes que controlam a decomposicao do bridge (refetch).
// `faixa_ticket` continua no enum do backend mas escondido na UI v3 (decisao
// de 2026-05-09 no v2 — gera ruido e raramente e util frente a produto/ua).
const WATERFALL_DIM_OPTIONS: SegmentDef<Operacoes2Dimension>[] = [
  { value: "produto", label: "Produto" },
  { value: "ua", label: "UA" },
]

// ─── Helpers ───────────────────────────────────────────────────────────────

/**
 * Filtra `vopDiarioPorUa` para uma UA especifica e retorna a serie no
 * formato de `EvolucaoDiariaPonto[]` (compativel com o card single).
 * Mantem todas as datas do calendario — dias sem op da UA viram 0 (passado)
 * ou null (futuro), respeitando `eh_futuro`.
 */
function serieDaUa(
  vopDiarioPorUa: Operacoes2VopDiarioPorUaPonto[],
  uaId: number,
): EvolucaoDiariaPonto[] {
  return vopDiarioPorUa
    .filter((p) => p.ua_id === uaId)
    .map((p) => ({
      data: p.data,
      valor: p.vop,
      ehDiaUtil: p.eh_dia_util,
      ehFuturo: p.eh_futuro,
    }))
}

// ─── HeroVopMes ────────────────────────────────────────────────────────────

export function HeroVopMes({
  vopDiario,
  vopDiarioPorUa,
  vopMtdPorUa,
  vop,
  dimension,
  onDimensionChange,
}: {
  vopDiario: Operacoes2VopDiarioPonto[]
  vopDiarioPorUa: Operacoes2VopDiarioPorUaPonto[]
  vopMtdPorUa: Operacoes2VopMtdPorUa[]
  vop: Operacoes2VarianceBridgeData
  /** Dimensao ativa do waterfall (controlado pelo pai pra refetch). */
  dimension: Operacoes2Dimension
  onDimensionChange: (d: Operacoes2Dimension) => void
}) {
  // null = "Todas" (consolidado), numero = ua_id especifica.
  const [selectedUaId, setSelectedUaId] = React.useState<number | null>(null)
  const [drillDate, setDrillDate] = React.useState<string | null>(null)

  // Opcoes do FilterChip = UAs presentes em vop_mtd_por_ua (ordem ja vem
  // por valor desc do backend).
  const uaOptions = React.useMemo(
    () => vopMtdPorUa.map((u) => ({ id: u.ua_id, nome: u.ua_nome })),
    [vopMtdPorUa],
  )

  // Serie diaria — alternada entre consolidada (Todas) e filtrada por UA.
  const diarioData: EvolucaoDiariaPonto[] = React.useMemo(() => {
    if (selectedUaId === null) {
      return vopDiario.map((p) => ({
        data: p.data,
        valor: p.vop,
        ehDiaUtil: p.eh_dia_util,
        ehFuturo: p.eh_futuro,
      }))
    }
    return serieDaUa(vopDiarioPorUa, selectedUaId)
  }, [selectedUaId, vopDiario, vopDiarioPorUa])

  const presetLabel = React.useMemo(() => {
    const first = vopDiario[0]
    return first ? presetLabelFromIso(first.data) : ""
  }, [vopDiario])

  // Header KPI: VOP MTD + Δ VOP-DU.
  // - Todas: usa o agregado do `vop` (current_anchor_value + delta_pct).
  // - UA especifica: usa o entry correspondente em `vop_mtd_por_ua`.
  const headerKpi = React.useMemo(() => {
    if (selectedUaId === null) {
      return {
        value: fmtBRLFull.format(vop.current_anchor_value),
        delta:
          vop.delta_pct != null
            ? { value: vop.delta_pct, suffix: "%" }
            : undefined,
        deltaSub: "VOP-DU",
      }
    }
    const uaEntry = vopMtdPorUa.find((u) => u.ua_id === selectedUaId)
    if (!uaEntry) {
      return undefined
    }
    return {
      value: fmtBRLFull.format(uaEntry.valor_mtd),
      delta:
        uaEntry.delta_vop_du_pct != null
          ? { value: uaEntry.delta_vop_du_pct, suffix: "%" }
          : undefined,
      deltaSub: "VOP-DU",
    }
  }, [selectedUaId, vop, vopMtdPorUa])

  // FilterChip "Todas | <UA>" no header do card VOP DIARIO.
  const selectedLabel =
    selectedUaId === null
      ? "Todas"
      : uaOptions.find((o) => o.id === selectedUaId)?.nome ?? "(n/d)"

  const diarioActions = React.useMemo(
    () => (
      <FilterChip
        label="UA"
        value={selectedLabel}
        active={selectedUaId !== null}
        icon={RiBuilding2Line}
      >
        <div className="py-1">
          <UaPickerItem
            label="Todas"
            selected={selectedUaId === null}
            onSelect={() => setSelectedUaId(null)}
          />
          {uaOptions.map((o) => (
            <UaPickerItem
              key={o.id}
              label={o.nome}
              selected={selectedUaId === o.id}
              onSelect={() => setSelectedUaId(o.id)}
            />
          ))}
        </div>
      </FilterChip>
    ),
    [selectedUaId, selectedLabel, uaOptions],
  )

  // SegmentSwitch do waterfall — vai DENTRO do card (slot actions).
  const waterfallActions = React.useMemo(
    () => (
      <SegmentSwitch
        options={WATERFALL_DIM_OPTIONS}
        value={dimension}
        onChange={onDimensionChange}
        ariaLabel="Dimensão da decomposição do VOP Waterfall"
      />
    ),
    [dimension, onDimensionChange],
  )

  return (
    <>
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        {/* VOP DIARIO — col-span-2 em xl (~66%) */}
        <div className="xl:col-span-2">
          <EvolucaoDiariaCard
            title="VOP DIÁRIO"
            presetLabel={presetLabel}
            data={diarioData}
            headerKpi={headerKpi}
            valueFormatter={(v) => fmtBRLFull.format(v)}
            axisFormatter={(v) => fmtBRL.format(v)}
            dataLabelFormatter={(v) =>
              (v / 1_000_000).toFixed(1).replace(".", ",")
            }
            height={300}
            actions={diarioActions}
            onPointClick={setDrillDate}
          />
        </div>

        {/* VOP WATERFALL — col-span-1 em xl (~33%). SegmentSwitch agora
            vive DENTRO do card via slot `actions`. Altura do canvas igualada
            ao VOP DIARIO (300px) — cards ficam visualmente alinhados. */}
        <div className="xl:col-span-1">
          <VarianceBridgeCard
            data={vop}
            title="VOP"
            caption="Drivers que moveram o ponteiro"
            actions={waterfallActions}
            height={300}
          />
        </div>
      </div>

      {/* Drill: operacoes do dia (click numa barra do diario) */}
      <DrillDownSheet
        open={drillDate !== null}
        onClose={() => setDrillDate(null)}
        size="lg"
        title={drillDate ? `Operações de ${dataLongPt(drillDate)}` : "Operações do dia"}
      >
        {drillDate && <DrillOperacoesDoDia dataISO={drillDate} />}
      </DrillDownSheet>
    </>
  )
}

// ─── Picker item canonico (mesma anatomia do EvolucaoMensalCard) ──────────

function UaPickerItem({
  label,
  selected,
  onSelect,
}: {
  label: string
  selected: boolean
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cx(
        "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
        selected
          ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
          : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
      )}
    >
      <span className="flex-1 truncate text-left">{label}</span>
    </button>
  )
}

