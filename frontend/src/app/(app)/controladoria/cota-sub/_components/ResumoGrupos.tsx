"use client"

/**
 * ResumoGrupos — o detalhamento por grupo de balanco da aba Resumo do dia (60%).
 *
 * Espelha 1:1 o waterfall: os mesmos 6 grupos, na mesma ordem. Direitos Creditorios
 * e (−) PDD & WOP sao itens de topo ABERTOS (atomicos, linhas=[]); Aplicacoes /
 * Disponibilidades / Obrigacoes e Provisoes / Cotas Prioritarias agregam suas
 * linhas (completas, inclusive zeradas = prova de que nada foi esquecido). Clicar
 * abre o drill. Fecho "= Variacao do PL Sub" prova o fechamento. Zero LLM.
 *
 * Layout = "extrato institucional tree-line" (VariantB do handoff Strata):
 * cabecalho de secao com regua + subtotal · linha flat com tick (barra por
 * magnitude) · filhos ligados por linha-guia vertical + conector horizontal.
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
function toneBg(v: number): string {
  if (Math.abs(v) < 1) return "bg-gray-300 dark:bg-gray-600"
  return v > 0 ? "bg-emerald-500" : "bg-red-500"
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

// Barra vertical (tick) por magnitude — 4..16px, escala pelo maior |impacto| da
// tabela. Cor por sinal (emerald sobe / red cai), opacidade baixa pra nao
// competir com o numero.
function Tick({ v, maxAbs }: { v: number; maxAbs: number }) {
  const h = Math.max(4, Math.min(16, (Math.abs(v) / maxAbs) * 16))
  return (
    <span
      className={cx("ml-1 mr-2 inline-block w-[3px] shrink-0 rounded-[2px] opacity-[0.55]", toneBg(v))}
      style={{ height: h }}
      aria-hidden="true"
    />
  )
}

// Cabecalho de secao: eyebrow + regua flex + subtotal colorido (tabular).
function SectionHead({ label, subtotal, first }: { label: string; subtotal: number; first?: boolean }) {
  return (
    <div className={cx("flex items-center gap-2.5 mb-1.5", first ? "mt-1.5" : "mt-4")}>
      <span className="text-[10px] font-bold uppercase tracking-[0.08em] text-gray-500 dark:text-gray-400">{label}</span>
      <span className="h-px flex-1 bg-gray-200 dark:bg-gray-800" aria-hidden="true" />
      <span className={cx("text-[11px] font-semibold tabular-nums", toneClass(subtotal))}>{fmtK(subtotal)}</span>
    </div>
  )
}

// Filho (sublinha) ligado por tree-line: conector horizontal + valor alinhado a
// coluna do pai. Drillavel quando ha drill_key.
function SubLinha({ linha, onDrill }: { linha: GrupoResumoLinha; onDrill?: (k: string) => void }) {
  const drillable = !!linha.drill_key && !!onDrill
  const zero = Math.abs(linha.impacto_pl_sub) < 1
  return (
    <button
      type="button"
      disabled={!drillable}
      onClick={drillable ? () => onDrill!(linha.drill_key!) : undefined}
      className={cx(
        "group relative flex w-full items-center rounded py-1.5 pr-2 pl-1 text-left",
        drillable ? "hover:bg-gray-50 dark:hover:bg-gray-900/50" : "cursor-default",
      )}
    >
      {/* conector horizontal ate a linha-guia vertical do container */}
      <span className="absolute -left-3.5 top-1/2 h-px w-2.5 -translate-y-1/2 bg-gray-200 dark:bg-gray-700" aria-hidden="true" />
      <span className={cx("flex-1 truncate text-[12px]", zero ? "text-gray-400 dark:text-gray-500" : "text-gray-600 dark:text-gray-400")}>
        {linha.label}
      </span>
      <span className={cx("w-[84px] shrink-0 text-right text-[12px] font-medium tabular-nums", zero ? "text-gray-400 dark:text-gray-500" : toneClass(linha.impacto_pl_sub))}>
        {zero ? "—" : fmtK(linha.impacto_pl_sub)}
      </span>
      <Seta active={drillable} />
    </button>
  )
}

function GrupoBloco({ grupo, maxAbs, onDrill }: { grupo: GrupoResumo; maxAbs: number; onDrill?: (k: string) => void }) {
  const drillable = !!grupo.drill_key && !!onDrill
  const atencao = grupo.severidade === "atencao"
  const temLinhas = grupo.linhas.length > 0

  return (
    <div>
      <button
        type="button"
        disabled={!drillable}
        onClick={drillable ? () => onDrill!(grupo.drill_key!) : undefined}
        className={cx(
          "group flex w-full items-center rounded px-1 py-2 text-left",
          drillable ? "hover:bg-gray-50 dark:hover:bg-gray-900/50" : "cursor-default",
        )}
      >
        <span className="flex flex-1 items-center gap-1.5 truncate text-[13px] font-semibold text-gray-900 dark:text-gray-100">
          {atencao && <RiAlertLine className="size-3.5 shrink-0 text-amber-500" aria-hidden="true" />}
          {displayLabel(grupo)}
        </span>
        <Tick v={grupo.impacto_pl_sub} maxAbs={maxAbs} />
        <span className={cx("w-[84px] shrink-0 text-right text-[13px] font-bold tabular-nums", toneClass(grupo.impacto_pl_sub))}>
          {fmtK(grupo.impacto_pl_sub)}
        </span>
        <Seta active={drillable} />
      </button>
      {temLinhas && (
        <div className="relative mb-1 ml-4 pl-3.5">
          {/* linha-guia vertical do grupo */}
          <span className="absolute left-0 top-0.5 bottom-2 w-px bg-gray-200 dark:bg-gray-700" aria-hidden="true" />
          {grupo.linhas.map((l) => <SubLinha key={l.key} linha={l} onDrill={onDrill} />)}
        </div>
      )}
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
  const subAtivo = ativos.reduce((s, g) => s + g.impacto_pl_sub, 0)
  const subPassivo = passivos.reduce((s, g) => s + g.impacto_pl_sub, 0)

  // Escala dos ticks = maior |impacto| entre grupos e sublinhas.
  const maxAbs = Math.max(
    1,
    ...data.grupos.flatMap((g) => [Math.abs(g.impacto_pl_sub), ...g.linhas.map((l) => Math.abs(l.impacto_pl_sub))]),
  )

  return (
    <Card className="flex flex-col gap-0.5 p-5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-[13px] font-semibold text-gray-900 dark:text-gray-100">Detalhamento por grupo de balanço</h3>
        <span className="text-[11px] text-gray-400 dark:text-gray-500">impacto na cota · clique para a prova</span>
      </div>

      <SectionHead label="Ativo" subtotal={subAtivo} first />
      {ativos.map((g) => <GrupoBloco key={g.key} grupo={g} maxAbs={maxAbs} onDrill={onDrillGrupo} />)}

      <SectionHead label="Passivo" subtotal={subPassivo} />
      {passivos.map((g) => <GrupoBloco key={g.key} grupo={g} maxAbs={maxAbs} onDrill={onDrillGrupo} />)}

      <div className="mt-3 flex items-center justify-between rounded-md border border-blue-200 bg-blue-50/50 px-3 py-2 dark:border-blue-900/50 dark:bg-blue-950/20">
        <span className="text-[13px] font-semibold text-gray-900 dark:text-gray-100">= Variação do PL Sub</span>
        <span className={cx("text-[13px] font-semibold tabular-nums", toneClass(data.cota_delta))}>{fmtBRL(data.cota_delta)}</span>
      </div>

      {data.giro_capital.length > 0 && (
        <div className="mt-3 rounded-md border border-dashed border-gray-300 bg-gray-50/50 px-3 py-2 dark:border-gray-700 dark:bg-gray-900/30">
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
