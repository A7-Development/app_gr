"use client"

/**
 * ResumoGrupos — o detalhamento por grupo de balanco da aba Resumo do dia (60%).
 *
 * Espelha 1:1 o waterfall: os mesmos 6 grupos, na mesma ordem. Direitos Creditorios
 * e (−) PDD & WOP sao itens de topo ABERTOS (atomicos, linhas=[]); Aplicacoes /
 * Disponibilidades / Obrigacoes e Provisoes / Cotas Prioritarias agregam suas
 * linhas (completas, inclusive zeradas = prova de que nada foi esquecido). Clicar
 * abre o drill. Fecho "= Variacao do PL Sub" prova o fechamento. Zero LLM.
 */

import { RiAlertLine, RiArrowRightSLine, RiRefreshLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import type { GrupoResumo, GrupoResumoLinha, VariacaoResumoResponse } from "@/lib/api-client"

function fmtK(v: number): string {
  if (Math.abs(v) < 1) return "R$ 0"
  const s = v >= 0 ? "+" : "−"
  const a = Math.abs(v)
  if (a >= 1000) return `${s}R$ ${(a / 1000).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}k`
  return `${s}R$ ${a.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}`
}
const fmtBRL = (v: number) =>
  (v >= 0 ? "+" : "−") + "R$ " + Math.abs(v).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })

function toneClass(v: number): string {
  if (Math.abs(v) < 1) return "text-gray-400 dark:text-gray-500"
  return v > 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400"
}

function displayLabel(g: GrupoResumo): string {
  return g.natureza === "contra_ativo" ? `(−) ${g.label}` : g.label
}

export type ResumoGruposProps = {
  data?:         VariacaoResumoResponse
  loading?:      boolean
  onDrillGrupo?: (drillKey: string) => void
}

function Seta({ active }: { active: boolean }) {
  return (
    <RiArrowRightSLine
      className={cx("size-3.5 shrink-0", active ? "text-gray-300 group-hover:text-blue-500 dark:text-gray-600" : "text-transparent")}
      aria-hidden="true"
    />
  )
}

function SubLinha({ linha, onDrill }: { linha: GrupoResumoLinha; onDrill?: (k: string) => void }) {
  const drillable = !!linha.drill_key && !!onDrill
  const zero = Math.abs(linha.impacto_pl_sub) < 1
  return (
    <button
      type="button"
      disabled={!drillable}
      onClick={drillable ? () => onDrill!(linha.drill_key!) : undefined}
      className={cx(
        "group flex w-full items-center justify-between rounded px-2 py-1.5 pl-6 text-left",
        drillable ? "hover:bg-gray-50 dark:hover:bg-gray-900/50" : "cursor-default",
      )}
    >
      <span className={cx("text-[12px]", zero ? "text-gray-400 dark:text-gray-500" : "text-gray-700 dark:text-gray-300")}>
        {linha.label}
      </span>
      <span className="flex items-center gap-1">
        <span className={cx("text-[12px] font-medium tabular-nums", zero ? "text-gray-400 dark:text-gray-500" : toneClass(linha.impacto_pl_sub))}>
          {zero ? "—" : fmtK(linha.impacto_pl_sub)}
        </span>
        <Seta active={drillable} />
      </span>
    </button>
  )
}

function GrupoBloco({ grupo, onDrill }: { grupo: GrupoResumo; onDrill?: (k: string) => void }) {
  const atomico = grupo.linhas.length === 0
  const atencao = grupo.severidade === "atencao"

  if (atomico) {
    const drillable = !!grupo.drill_key && !!onDrill
    return (
      <button
        type="button"
        disabled={!drillable}
        onClick={drillable ? () => onDrill!(grupo.drill_key!) : undefined}
        className={cx(
          "group flex w-full items-center justify-between rounded px-2 py-1.5 text-left",
          drillable ? "hover:bg-gray-50 dark:hover:bg-gray-900/50" : "cursor-default",
        )}
      >
        <span className="flex items-center gap-1.5 text-[12px] font-semibold text-gray-900 dark:text-gray-100">
          {atencao && <RiAlertLine className="size-3.5 shrink-0 text-amber-500" aria-hidden="true" />}
          {displayLabel(grupo)}
        </span>
        <span className="flex items-center gap-1">
          <span className={cx("text-[12px] font-semibold tabular-nums", toneClass(grupo.impacto_pl_sub))}>
            {fmtK(grupo.impacto_pl_sub)}
          </span>
          <Seta active={drillable} />
        </span>
      </button>
    )
  }

  return (
    <div className="mt-1">
      <div className="flex items-center justify-between rounded bg-gray-50/70 px-2 py-1 dark:bg-gray-900/40">
        <span className="flex items-center gap-1.5 text-[12px] font-semibold text-gray-800 dark:text-gray-200">
          {atencao && <RiAlertLine className="size-3.5 shrink-0 text-amber-500" aria-hidden="true" />}
          {displayLabel(grupo)}
        </span>
        <span className={cx("text-[12px] font-semibold tabular-nums", toneClass(grupo.impacto_pl_sub))}>
          {fmtK(grupo.impacto_pl_sub)}
        </span>
      </div>
      {grupo.linhas.map((l) => <SubLinha key={l.key} linha={l} onDrill={onDrill} />)}
    </div>
  )
}

export function ResumoGrupos({ data, loading, onDrillGrupo }: ResumoGruposProps) {
  if (loading) {
    return (
      <Card className="flex animate-pulse flex-col gap-2">
        <div className="h-5 w-48 rounded bg-gray-200 dark:bg-gray-800" />
        {[0, 1, 2, 3, 4].map((i) => <div key={i} className="h-9 rounded bg-gray-100 dark:bg-gray-900" />)}
      </Card>
    )
  }
  if (!data) return null

  const ativos = data.grupos.filter((g) => g.natureza !== "passivo")
  const passivos = data.grupos.filter((g) => g.natureza === "passivo")

  return (
    <Card className="flex flex-col gap-1 p-5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-[13px] font-semibold text-gray-900 dark:text-gray-100">Detalhamento por grupo de balanço</h3>
        <span className="text-[11px] text-gray-400 dark:text-gray-500">impacto na cota · clique para a prova</span>
      </div>

      <p className="mt-2 px-1 text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-500">Ativo</p>
      {ativos.map((g) => <GrupoBloco key={g.key} grupo={g} onDrill={onDrillGrupo} />)}

      <p className="mt-3 border-t border-gray-100 px-1 pt-2.5 text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:border-gray-900 dark:text-gray-500">Passivo</p>
      {passivos.map((g) => <GrupoBloco key={g.key} grupo={g} onDrill={onDrillGrupo} />)}

      <div className="mt-3 flex items-center justify-between rounded-md border border-blue-200 bg-blue-50/50 px-3 py-2 dark:border-blue-900/50 dark:bg-blue-950/20">
        <span className="text-[13px] font-semibold text-gray-900 dark:text-gray-100">= Variação do PL Sub</span>
        <span className={cx("text-[13px] font-semibold tabular-nums", toneClass(data.cota_delta))}>{fmtBRL(data.cota_delta)}</span>
      </div>

      {data.giro_capital.length > 0 && (
        <div className="mt-3 rounded-md border border-gray-200 bg-gray-50/50 px-3 py-2 dark:border-gray-800 dark:bg-gray-900/30">
          <div className="flex flex-wrap items-center gap-x-1.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
            <RiRefreshLine className="size-3.5" aria-hidden="true" />
            Giro e capital do dia
            <span className="font-normal normal-case tracking-normal text-gray-400 dark:text-gray-500">— movimentou caixa/posição, não afetou a cota</span>
          </div>
          <div className="mt-1.5 flex flex-col gap-1">
            {data.giro_capital.map((gc, i) => (
              <div key={i} className="flex items-baseline justify-between gap-3 px-1">
                <span className="text-[12px] text-gray-600 dark:text-gray-400">{gc.label}</span>
                <span className="shrink-0 text-[12px] font-medium tabular-nums text-gray-500 dark:text-gray-400">{fmtK(gc.valor)}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  )
}
