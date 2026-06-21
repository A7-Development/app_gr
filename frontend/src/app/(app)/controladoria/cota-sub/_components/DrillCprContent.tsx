"use client"

/**
 * DrillCprContent — conteudo do drill da categoria CPR.
 *
 * 3 secoes:
 *   1. Totais D-1 / D0 / Δ
 *   2. Aportes engaiolados detectados (badge destacado se houver)
 *   3. Agrupamento por natureza com top lines de cada grupo
 *
 * 2026-05-29: as tabelas "Por natureza" migraram do `<table>` artesanal para a
 * DataTable canonica `density="ultra"` (h-7/28px) — regra dura de consistencia
 * dos drills da Cota Sub. Cada natureza e uma DataTable com Total no
 * `renderFooter` somando suas linhas (o backend ja entrega top_linhas completas
 * por natureza; sem corte). O orient (`o`) do lado pagar/receber e preservado.
 */

import * as React from "react"
import {
  RiBubbleChartLine,
  RiCoinsLine,
  RiInformationLine,
  RiInboxLine,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import { useDrillCpr } from "@/lib/hooks/controladoria"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { Button } from "@/components/tremor/Button"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"
import {
  DrillClosureBadge,
  DrillSectionTitle,
  drillTableWrap,
  fmtBRL,
  fmtBRLSigned,
  toneClass,
} from "./drillKit"

const ESTADO_LABEL: Record<"entrou" | "devolvido" | "persiste", { label: string; tone: string }> = {
  entrou:    { label: "Novo em D0",     tone: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300" },
  devolvido: { label: "Devolvido em D0", tone: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300" },
  persiste:  { label: "Persiste",        tone: "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300" },
}

// Props compartilhadas das DataTables do drill — ultra, sem toolbar.
const DT_PROPS = {
  density:           "ultra",
  virtualize:        false,
  showColumnManager: false,
  showDensityToggle: false,
  showExport:        false,
} as const

const FOOT_ROW = "border-t-2 border-t-gray-300 dark:border-t-gray-700"

// Linha de rubrica dentro de uma natureza. `o` (orient) ja aplicado a cada
// valor no momento da construcao das rows — celulas exibem a magnitude correta.
type RubricaRow = {
  descricao:           string
  historico_traduzido: string | null
  valor_d1:            number
  valor_d0:            number
  delta_valor:         number
}

const rubCol = createColumnHelper<RubricaRow>()

const RUBRICA_COLUMNS: ColumnDef<RubricaRow, unknown>[] = [
  rubCol.accessor((r) => r.historico_traduzido || r.descricao, {
    id: "rubrica", header: "Rubrica", size: 340,
    cell: (info) => (
      <span className={cx("block max-w-[320px] truncate", tableTokens.cellText)} title={info.row.original.descricao}>
        {info.getValue<string>()}
      </span>
    ),
  }) as ColumnDef<RubricaRow, unknown>,
  rubCol.accessor("valor_d1", {
    id: "valor_d1", header: "D-1", size: 120, meta: { align: "right" },
    cell: (info) => <div className={cx("text-right", tableTokens.cellNumberSecondary)}>{fmtBRL.format(info.getValue<number>())}</div>,
  }) as ColumnDef<RubricaRow, unknown>,
  rubCol.accessor("valor_d0", {
    id: "valor_d0", header: "D0", size: 120, meta: { align: "right" },
    cell: (info) => <div className={cx("text-right", tableTokens.cellNumber)}>{fmtBRL.format(info.getValue<number>())}</div>,
  }) as ColumnDef<RubricaRow, unknown>,
  rubCol.accessor("delta_valor", {
    id: "delta", header: "Δ", size: 120, meta: { align: "right" },
    cell: (info) => <div className={cx("text-right text-xs font-medium tabular-nums", toneClass(info.getValue<number>()))}>{fmtBRLSigned(info.getValue<number>())}</div>,
  }) as ColumnDef<RubricaRow, unknown>,
]

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

  // Fechamento: as naturezas particionam o total da linha. Σ(natureza D0) deve
  // bater o total D0 (= valor da linha Contas a Receber/Pagar no balanco).
  const linhaLabel = side === "pagar" ? "Contas a Pagar" : side === "receber" ? "Contas a Receber" : "CPR"
  const valorLinha = o(d.cpr_total_d0)
  const somaNaturezas = d.naturezas.reduce((s, n) => s + o(n.sum_valor_d0), 0)
  const fecha = Math.abs(valorLinha - somaNaturezas) < 0.01

  return (
    <div className="flex flex-col gap-5">
      {/* ── Selo de fechamento ── */}
      <DrillClosureBadge
        fecha={fecha}
        sub={!fecha ? `linha ${fmtBRL.format(valorLinha)} · naturezas ${fmtBRL.format(somaNaturezas)}` : undefined}
      >
        {fecha
          ? `Fecha · ${d.naturezas.length} natureza(s) compõem ${linhaLabel} ${fmtBRL.format(valorLinha)}`
          : `Diverge · soma das naturezas ≠ ${linhaLabel}`}
      </DrillClosureBadge>

      {/* ── Totais ── */}
      <section>
        <DrillSectionTitle icon={RiCoinsLine} label={totaisLabel} />
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
              toneClass(o(d.cpr_total_delta)),
            )}>{fmtBRLSigned(o(d.cpr_total_delta))}</p>
          </div>
        </div>
      </section>

      {/* ── Aportes engaiolados ── */}
      {temAporteEngaiolado && (
        <section>
          <DrillSectionTitle
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
                        toneClass(o(ev.delta_valor)),
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
        <DrillSectionTitle icon={RiBubbleChartLine} label="Por natureza" />
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
            {d.naturezas.map((n) => {
              // `o` ja aplicado em cada valor — a tabela exibe a magnitude correta.
              const rows: RubricaRow[] = n.top_linhas.map((ln) => ({
                descricao:           ln.descricao,
                historico_traduzido: ln.historico_traduzido,
                valor_d1:            o(ln.valor_d1),
                valor_d0:            o(ln.valor_d0),
                delta_valor:         o(ln.delta_valor),
              }))
              return (
                <div key={n.natureza} className={drillTableWrap}>
                  <div className="border-b border-gray-100 px-3 py-1.5 dark:border-gray-900">
                    <span className="text-[12px] font-medium text-gray-900 dark:text-gray-50">{n.label}</span>
                    <span className="ml-1.5 text-[10px] text-gray-500 dark:text-gray-400">· {n.qtd_linhas} linha(s)</span>
                  </div>
                  <DataTable<RubricaRow>
                    {...DT_PROPS}
                    data={rows}
                    columns={RUBRICA_COLUMNS}
                    renderFooter={() => (
                      <tr className={FOOT_ROW}>
                        <td className="px-3"><span className={tableTokens.cellStrong}>Total</span></td>
                        <td className="px-3"><div className={cx("text-right", tableTokens.cellNumberSecondary)}>{fmtBRL.format(o(n.sum_valor_d1))}</div></td>
                        <td className="px-3"><div className={cx("text-right", tableTokens.cellStrong)}>{fmtBRL.format(o(n.sum_valor_d0))}</div></td>
                        <td className="px-3"><div className={cx("text-right text-xs font-semibold tabular-nums", toneClass(o(n.sum_delta)))}>{fmtBRLSigned(o(n.sum_delta))}</div></td>
                      </tr>
                    )}
                  />
                </div>
              )
            })}
          </div>
        )}
      </section>
    </div>
  )
}
