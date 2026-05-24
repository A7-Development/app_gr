"use client"

/**
 * BalancoPatrimonialHero — Balance hero da Cota Sub (F1 do redesign, 2026-05-22).
 *
 * Formato balancete denso (iteracao Alt A revisada 2026-05-22): tabela
 * 4 colunas (label | D-1 | D0 | Δ) com dot de identidade por categoria,
 * densidade compact pra caber 100% na vertical em 50% de largura sem
 * scroll. Datas no header das colunas. Linha de Identidade no rodape:
 *   - residuo ≈ 0      → fechamento ok (badge verde)
 *   - residuo < R$ 1k  → arredondamento (badge âmbar)
 *   - residuo >= R$ 1k → desalinhamento (badge vermelho)
 *
 * Drill chevron (▸) por linha placeholder — F2 liga DrillDownSheet para
 * DC, PDD e CPR. Resto fica nao-clicavel ate F3.
 *
 * Aposenta na page.tsx:
 *   AnaliseVariacaoCard, WaterfallEventosCard, ReconciliacaoWaterfallCard,
 *   DriversCard, BridgeCard, ResiduoAlertCard, StatusHeadlineCompact.
 */

import * as React from "react"
import {
  RiCheckLine,
  RiAlertLine,
  RiErrorWarningLine,
  RiArrowRightSLine,
  RiCalendarLine,
} from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { Button } from "@/components/tremor/Button"
import type {
  BalancoPatrimonialResponse,
  CategoriaPatrimonial,
  CategoriaPatrimonialKey,
} from "@/lib/api-client"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style:                 "currency",
  currency:              "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const fmtBRLSigned = (v: number): string => {
  if (Math.abs(v) < 0.005) return "0,00"
  const sign = v > 0 ? "+" : "−"
  return `${sign}${fmtBRL.format(Math.abs(v))}`
}

const fmtDate = (iso: string): string => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[3]}/${m[2]}` : iso
}

const DRILL_ENABLED_F2: ReadonlySet<CategoriaPatrimonialKey> = new Set<CategoriaPatrimonialKey>([
  "dc",
  "cpr",
  "pdd",
])

const RESIDUO_AMBER_BRL = 1
const RESIDUO_RED_BRL = 1000

// Grid de colunas — single source of truth pra alinhar header + rows.
// Label fixo em 180px (cabe ate "Saldo Conta Corrente"); 3 colunas numericas
// dividem o restante em 1fr (evita encavalamento de valores grandes tipo
// "R$ 24.436.232,09" + delta).
const GRID = "grid grid-cols-[180px_1fr_1fr_1fr_14px] items-center gap-2"

export type BalancoPatrimonialHeroProps = {
  data?:         BalancoPatrimonialResponse
  loading?:      boolean
  errorMessage?: string
  onRetry?:      () => void
  onDrillCategoria?: (key: CategoriaPatrimonialKey) => void
}

export function BalancoPatrimonialHero({
  data,
  loading       = false,
  errorMessage,
  onRetry,
  onDrillCategoria,
}: BalancoPatrimonialHeroProps) {
  if (errorMessage && !loading) {
    return (
      <ErrorState
        title="Falha ao carregar o balanço"
        description={errorMessage}
        action={onRetry ? <Button onClick={onRetry}>Tentar novamente</Button> : undefined}
        className="mt-4"
      />
    )
  }

  if (loading && !data) {
    return (
      <Card className="flex h-[480px] items-center justify-center p-3">
        <span className="text-sm text-gray-500 dark:text-gray-400">
          Carregando balanço…
        </span>
      </Card>
    )
  }

  if (!data) {
    return (
      <EmptyState
        icon={RiCalendarLine}
        title="Sem dados para esta data"
        description="A QiTech não publicou snapshot deste fundo no dia selecionado."
        className="mt-4"
      />
    )
  }

  // F4.8 (2026-05-24): usa residuo do DELTA DO DIA, nao snapshot acumulado.
  // Snapshot D0 acumula arredondamento da QiTech ao longo do tempo (R$ 0,52
  // em 13/05); delta-dos-deltas isola o erro do dia (R$ 0,05 em 13/05),
  // que e o que importa pra avaliar fechamento.
  const residuo = data.residuo_identidade_delta
  const residuoAbs = Math.abs(residuo)
  const residuoStatus: "ok" | "warn" | "error" =
    residuoAbs < RESIDUO_AMBER_BRL ? "ok"
    : residuoAbs < RESIDUO_RED_BRL ? "warn"
    : "error"

  return (
    <Card className="flex flex-col p-0">
      {/* Header */}
      <div className="flex flex-wrap items-start justify-between gap-2 px-3 pt-2.5 pb-2">
        <div className="flex flex-col">
          <h3 className="text-[13px] font-semibold text-gray-900 dark:text-gray-50">
            Balanço · ótica Sub Jr
          </h3>
          <p className="text-[11px] text-gray-500 dark:text-gray-400">
            {data.fundo_nome}
          </p>
        </div>
        <IdentidadeBadge status={residuoStatus} residuo={residuo} />
      </div>

      {/* Cabeçalho das colunas */}
      <div className={cx(GRID, "border-y border-gray-100 bg-gray-50/60 px-3 py-1 text-[10px] font-medium uppercase tracking-[0.04em] text-gray-500 dark:border-gray-800 dark:bg-gray-900/30 dark:text-gray-400")}>
        <span></span>
        <span className="text-right">D-1<br /><span className="font-normal text-gray-400">{fmtDate(data.data_anterior)}</span></span>
        <span className="text-right">D0<br /><span className="font-normal text-gray-400">{fmtDate(data.data)}</span></span>
        <span className="text-right">Δ</span>
        <span></span>
      </div>

      {/* Seção ATIVOS */}
      <SectionLabel label="Ativos" />
      {data.ativos.map((cat) => (
        <BalanceRow
          key={cat.key}
          categoria={cat}
          onDrill={onDrillCategoria}
        />
      ))}
      <TotalRow
        label="Σ Ativos"
        d1={data.soma_ativos_d1}
        d0={data.soma_ativos_d0}
        delta={data.soma_ativos_delta}
      />

      {/* Seção PASSIVOS */}
      <SectionLabel label="Passivos · redutores" />
      {data.passivos.map((cat) => (
        <BalanceRow
          key={cat.key}
          categoria={cat}
          onDrill={onDrillCategoria}
        />
      ))}
      <TotalRow
        label="Σ Passivos"
        d1={data.soma_passivos_d1}
        d0={data.soma_passivos_d0}
        delta={data.soma_passivos_delta}
      />

      {/* Seção FECHAMENTO */}
      <PlRow
        label="PL Sub Jr · deduzido"
        sublabel="Σ Ativos − Σ Passivos"
        d1={data.pl_deduzido_d1}
        d0={data.pl_deduzido_d0}
        delta={data.pl_deduzido_delta}
        emphasize
      />
      <PlRow
        label="PL Sub Jr · fonte (wh_mec)"
        d1={data.pl_fonte_d1}
        d0={data.pl_fonte_d0}
        delta={data.pl_fonte_delta}
      />
      <IdentidadeRow
        residuoDelta={data.residuo_identidade_delta}
        residuoSnapshot={data.residuo_identidade_d0}
        status={residuoStatus}
      />
    </Card>
  )
}

// ─── Sub-componentes ────────────────────────────────────────────────────────

function SectionLabel({ label }: { label: string }) {
  return (
    <div className="border-t border-gray-100 bg-white px-3 pt-1.5 pb-0.5 text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-400">
      {label}
    </div>
  )
}

function BalanceRow({
  categoria,
  onDrill,
}: {
  categoria:   CategoriaPatrimonial
  onDrill?:    (key: CategoriaPatrimonialKey) => void
}) {
  const drillEnabled = DRILL_ENABLED_F2.has(categoria.key) && onDrill !== undefined
  const isZero = Math.abs(categoria.delta) < 0.005
  const isEmpty = Math.abs(categoria.d0) < 0.005 && isZero

  return (
    <div
      className={cx(
        GRID,
        "group border-t border-gray-50 px-3 py-1 transition-colors duration-100 text-[12px] tabular-nums",
        "dark:border-gray-900",
        drillEnabled && "cursor-pointer hover:bg-gray-50/80 dark:hover:bg-gray-900/40",
        isEmpty && "opacity-50",
      )}
      onClick={drillEnabled ? () => onDrill(categoria.key) : undefined}
      role={drillEnabled ? "button" : undefined}
      tabIndex={drillEnabled ? 0 : undefined}
      title={drillEnabled ? "Clique para detalhar" : undefined}
    >
      <span className="flex items-center min-w-0">
        <span className="truncate text-gray-900 dark:text-gray-50">
          {categoria.label}
        </span>
      </span>
      <span className="text-right text-gray-500 dark:text-gray-400">
        {fmtBRL.format(categoria.d1)}
      </span>
      <span className="text-right font-medium text-gray-900 dark:text-gray-50">
        {fmtBRL.format(categoria.d0)}
      </span>
      <DeltaCell delta={categoria.delta} />
      <span className="flex justify-end">
        {drillEnabled && (
          <RiArrowRightSLine
            className="size-3.5 text-gray-300 transition-colors group-hover:text-gray-500 dark:text-gray-700 dark:group-hover:text-gray-400"
            aria-hidden="true"
          />
        )}
      </span>
    </div>
  )
}

function TotalRow({
  label, d1, d0, delta,
}: {
  label: string
  d1: number; d0: number; delta: number
}) {
  return (
    <div className={cx(
      GRID,
      "border-t border-gray-200 bg-gray-50/40 px-3 py-1.5 text-[12px] font-semibold tabular-nums dark:border-gray-800 dark:bg-gray-900/30",
    )}>
      <span className="flex items-center min-w-0">
        <span className="truncate text-gray-900 dark:text-gray-50">
          {label}
        </span>
      </span>
      <span className="text-right text-gray-600 dark:text-gray-400">
        {fmtBRL.format(d1)}
      </span>
      <span className="text-right text-gray-900 dark:text-gray-50">
        {fmtBRL.format(d0)}
      </span>
      <DeltaCell delta={delta} bold />
      <span />
    </div>
  )
}

function PlRow({
  label, sublabel, d1, d0, delta, emphasize = false,
}: {
  label:     string
  sublabel?: string
  d1: number; d0: number; delta: number
  emphasize?: boolean
}) {
  return (
    <div className={cx(
      GRID,
      "border-t px-3 py-1.5 text-[12px] tabular-nums",
      emphasize
        ? "border-gray-300 bg-blue-50/40 dark:border-gray-700 dark:bg-blue-950/10"
        : "border-gray-100 dark:border-gray-800",
    )}>
      <span className="flex flex-col min-w-0">
        <span
          className={cx(
            "truncate text-[12px] text-gray-900 dark:text-gray-50",
            emphasize ? "font-semibold" : "font-medium",
          )}
        >
          {label}
        </span>
        {sublabel && (
          <span className="text-[10px] text-gray-400 dark:text-gray-600">
            {sublabel}
          </span>
        )}
      </span>
      <span
        className={cx(
          "text-right text-[12px]",
          emphasize ? "text-gray-700 dark:text-gray-300" : "text-gray-500 dark:text-gray-400",
        )}
      >
        {fmtBRL.format(d1)}
      </span>
      <span
        className={cx(
          "text-right text-[12px] text-gray-900 dark:text-gray-50",
          emphasize ? "font-semibold" : "font-medium",
        )}
      >
        {fmtBRL.format(d0)}
      </span>
      <DeltaCell delta={delta} bold={emphasize} />
      <span />
    </div>
  )
}

function IdentidadeRow({
  residuoDelta, residuoSnapshot, status,
}: {
  residuoDelta:    number
  residuoSnapshot: number
  status:          "ok" | "warn" | "error"
}) {
  // Tooltip mostra o snapshot acumulado pra quem quiser ver o "ruido total"
  // que se acumulou desde o inicio do fundo (geralmente centavos).
  const tooltip = `Erro do dia (ΔPL calculado − ΔPL fonte MEC). Snapshot D0 acumulado: ${fmtBRLSigned(residuoSnapshot)}.`
  return (
    <div className="flex items-center justify-between gap-2 border-t border-gray-200 px-3 py-1 text-[10px] dark:border-gray-800">
      <span
        className="cursor-help uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600"
        title={tooltip}
      >
        Resíduo identidade contábil (dia)
      </span>
      <span
        className={cx(
          "tabular-nums",
          status === "ok"    && "text-gray-500 dark:text-gray-400",
          status === "warn"  && "font-medium text-amber-700 dark:text-amber-400",
          status === "error" && "font-semibold text-red-700 dark:text-red-400",
        )}
        title={tooltip}
      >
        {fmtBRLSigned(residuoDelta)}
      </span>
    </div>
  )
}

function DeltaCell({
  delta,
  bold = false,
}: {
  delta: number
  bold?: boolean
}) {
  const isZero = Math.abs(delta) < 0.005
  if (isZero) {
    return <span className="text-right text-gray-300 dark:text-gray-700">—</span>
  }
  const isPositive = delta > 0
  return (
    <span
      className={cx(
        "text-right",
        bold && "font-semibold",
        isPositive
          ? "text-emerald-700 dark:text-emerald-400"
          : "text-red-700 dark:text-red-400",
      )}
    >
      {fmtBRLSigned(delta)}
    </span>
  )
}

function IdentidadeBadge({
  status, residuo,
}: {
  status: "ok" | "warn" | "error"
  residuo: number
}) {
  if (status === "ok") {
    return (
      <span className="inline-flex items-center gap-1 rounded border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/40 dark:text-emerald-300">
        <RiCheckLine className="size-3" aria-hidden="true" />
        Fechamento ok
      </span>
    )
  }
  if (status === "warn") {
    return (
      <span
        className="inline-flex items-center gap-1 rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300"
        title="Resíduo típico de arredondamento — investigar se persistir"
      >
        <RiAlertLine className="size-3" aria-hidden="true" />
        Resíduo {fmtBRLSigned(residuo)}
      </span>
    )
  }
  return (
    <span
      className="inline-flex items-center gap-1 rounded border border-red-200 bg-red-50 px-1.5 py-0.5 text-[10px] font-medium text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300"
      title="Desalinhamento entre PL deduzido e fonte — abrir investigação"
    >
      <RiErrorWarningLine className="size-3" aria-hidden="true" />
      Resíduo {fmtBRLSigned(residuo)}
    </span>
  )
}
