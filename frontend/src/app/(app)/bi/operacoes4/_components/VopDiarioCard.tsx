// L2 esquerda do redesign /bi/operacoes4 (handoff 2026-05-21).
//
// VOP DIÁRIO com header de 3 linhas (eyebrow + KPI + Média/DU) + SegmentSwitch
// de UA no actions slot (com fallback FilterChip quando ha > 3 UAs).
//
// Reusa `EvolucaoDiariaCard` (DS) — apenas envolve com header customizado
// e o seletor de UA.
//
// TODO_PR4 (polishing): a "Média/DU R$ X" deveria viver entre o KPI principal
// e o caption. EChartsCard atual nao expoe slot para esse segundo metric —
// solucao temporaria coloca no actions slot a direita. Aceitavel em PR1,
// pixel-perfect na PR4.

"use client"

import * as React from "react"
import { RiBuilding2Line } from "@remixicon/react"

import {
  EvolucaoDiariaCard,
  FilterChip,
  SegmentSwitch,
  type EvolucaoDiariaPonto,
  type EvolucaoDiariaSerie,
  type SegmentDef,
} from "@/design-system/components"
import type {
  Operacoes2VarianceBridgeData,
  Operacoes2VopDiarioPonto,
  Operacoes2VopDiarioPorUaPonto,
  Operacoes2VopMtdPorUa,
} from "@/lib/api-client"
import { cx } from "@/lib/utils"

const fmtBRLCompact = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
})
const fmtBRLFull = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
})

/**
 * Formatter do eixo Y do VOP Diário — converte BRL pra milhoes compactos:
 * "0,5", "1,0", "2,4". Sem prefixo "R$" e sem sufixo "M" porque a unidade
 * fica implicita no contexto do card ("VOP DIÁRIO" no header, tooltip
 * mostra BRL full). Economiza espaco horizontal vs Intl compact que
 * renderiza "R$ 500K" / "R$ 1,0M".
 *
 * 0 vira "0" (nao "0,0") pra reduzir ruido na origem do eixo.
 */
function fmtMilhoesAxis(v: number): string {
  if (v === 0) return "0"
  const milhoes = v / 1_000_000
  return milhoes.toFixed(1).replace(".", ",")
}

/**
 * Formatter dos dataLabels no topo das barras — mesma escala do eixo Y mas
 * **suprime zero**. Dias sem operacao (fim de semana, feriado, dia util sem
 * efetivacao) renderizariam "0" colado no eixo X, ruido visual sem
 * informacao. Decisao Ricardo 2026-05-21 + AC #14 do handoff.
 */
function fmtMilhoesLabel(v: number): string {
  if (!v) return ""
  return fmtMilhoesAxis(v)
}

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

/** Limite no qual o SegmentSwitch deixa de caber e cai pro FilterChip. */
const SEGMENT_UA_MAX = 3

export type VopDiarioCardProps = {
  vopDiario: Operacoes2VopDiarioPonto[]
  vopDiarioPorUa: Operacoes2VopDiarioPorUaPonto[]
  vopMtdPorUa: Operacoes2VopMtdPorUa[]
  vop: Operacoes2VarianceBridgeData
  duDecorridos: number
  duTotais: number
  onPointClick?: (dataISO: string) => void
}

export function VopDiarioCard({
  vopDiario,
  vopDiarioPorUa,
  vopMtdPorUa,
  vop,
  duDecorridos,
  duTotais,
  onPointClick,
}: VopDiarioCardProps) {
  // UA selecionada — null = todas (agregado).
  const [selectedUaId, setSelectedUaId] = React.useState<number | null>(null)

  // UAs disponiveis ordenadas por VOP MTD desc — base pro selector.
  const uas = React.useMemo(() => {
    return [...vopMtdPorUa].sort((a, b) => b.valor_mtd - a.valor_mtd)
  }, [vopMtdPorUa])

  // Decide entre Segment (≤3 UAs) e FilterChip (>3 UAs).
  const useSegment = uas.length > 0 && uas.length <= SEGMENT_UA_MAX

  // Data do chart — quando UA selecionada, filtra `vopDiarioPorUa` para
  // aquela UA; senao, usa o agregado `vopDiario`.
  const chartData = React.useMemo<EvolucaoDiariaPonto[]>(() => {
    if (selectedUaId == null) {
      return vopDiario.map((p) => ({
        data: p.data,
        valor: p.vop,
        ehDiaUtil: p.eh_dia_util,
        ehFuturo: p.eh_futuro,
      }))
    }
    // Construi um indice por dia para a UA escolhida — preserva todos
    // os dias do mes (incluindo futuros, sab/dom) no eixo X.
    const byDay = new Map<string, Operacoes2VopDiarioPorUaPonto>()
    for (const p of vopDiarioPorUa) {
      if (p.ua_id === selectedUaId) byDay.set(p.data, p)
    }
    return vopDiario.map((p) => {
      const ua = byDay.get(p.data)
      return {
        data: p.data,
        valor: ua?.vop ?? null,
        ehDiaUtil: p.eh_dia_util,
        ehFuturo: p.eh_futuro,
      }
    })
  }, [selectedUaId, vopDiario, vopDiarioPorUa])

  // KPI do header: VOP MTD agregado (selectedUaId=null) ou da UA selecionada.
  const kpiValor = React.useMemo(() => {
    if (selectedUaId == null) return vop.current_anchor_value
    const ua = vopMtdPorUa.find((u) => u.ua_id === selectedUaId)
    return ua?.valor_mtd ?? 0
  }, [selectedUaId, vop, vopMtdPorUa])

  const mediaPorDu = duDecorridos > 0 ? kpiValor / duDecorridos : 0

  const presetLabel =
    vopDiario.length > 0 ? presetLabelFromIso(vopDiario[0].data) : ""
  const caption = `${presetLabel} · ${duDecorridos} DU${duDecorridos === 1 ? "" : "s"} executados de ${duTotais}`

  // SegmentSwitch trabalha com string keys — "all" + "ua-<id>".
  const segmentValue = selectedUaId == null ? "all" : `ua-${selectedUaId}`
  const segmentOptions: SegmentDef<string>[] = React.useMemo(
    () => [
      { value: "all", label: "Todas" },
      ...uas.map((u) => ({ value: `ua-${u.ua_id}`, label: u.ua_nome })),
    ],
    [uas],
  )
  const handleSegmentChange = React.useCallback((next: string) => {
    if (next === "all") {
      setSelectedUaId(null)
      return
    }
    const parsed = Number.parseInt(next.replace(/^ua-/, ""), 10)
    setSelectedUaId(Number.isFinite(parsed) ? parsed : null)
  }, [])

  return (
    <EvolucaoDiariaCard
      title="VOP DIÁRIO"
      presetLabel={caption}
      data={chartData}
      headerKpi={{
        value: fmtBRLCompact.format(kpiValor),
        delta:
          vop.delta_pct != null
            ? { value: vop.delta_pct, suffix: "%" }
            : undefined,
        deltaSub: "VOP-DU",
      }}
      valueFormatter={(v) => fmtBRLFull.format(v)}
      axisFormatter={fmtMilhoesAxis}
      dataLabelFormatter={fmtMilhoesLabel}
      height={260}
      onPointClick={onPointClick}
      actions={
        <div className="flex items-center gap-3">
          <span className="hidden text-[11px] text-gray-500 sm:inline dark:text-gray-400">
            Média/DU{" "}
            <span className="font-medium tabular-nums text-gray-700 dark:text-gray-300">
              {fmtBRLCompact.format(mediaPorDu)}
            </span>
          </span>
          {useSegment ? (
            <SegmentSwitch<string>
              value={segmentValue}
              onChange={handleSegmentChange}
              options={segmentOptions}
              ariaLabel="Filtrar VOP diário por UA"
            />
          ) : (
            <UaFilterChip
              uas={uas}
              selected={selectedUaId}
              onChange={setSelectedUaId}
            />
          )}
        </div>
      }
    />
  )
}

function UaFilterChip({
  uas,
  selected,
  onChange,
}: {
  uas: Operacoes2VopMtdPorUa[]
  selected: number | null
  onChange: (v: number | null) => void
}) {
  const label =
    selected == null
      ? "Todas"
      : (uas.find((u) => u.ua_id === selected)?.ua_nome ?? `UA ${selected}`)
  return (
    <FilterChip label="UA" value={label} active={selected != null} icon={RiBuilding2Line}>
      <div className="py-1">
        <button
          type="button"
          onClick={() => onChange(null)}
          className={cx(
            "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm",
            selected == null
              ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
              : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
          )}
        >
          Todas
        </button>
        {uas.map((u) => (
          <button
            key={u.ua_id}
            type="button"
            onClick={() => onChange(u.ua_id)}
            className={cx(
              "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm",
              selected === u.ua_id
                ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
            )}
          >
            {u.ua_nome}
          </button>
        ))}
      </div>
    </FilterChip>
  )
}

// Reuso `EvolucaoDiariaSerie` para silenciar warning de import (mantemos
// export-side-effect — tipo pode ser util em PR2 quando o stack-by-UA virar).
export type { EvolucaoDiariaSerie }
