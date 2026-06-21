"use client"

/**
 * DrillPddContent — conteudo do drill da categoria PDD.
 *
 * 4 secoes (refatorado 2026-06-02):
 *   0. Selo de fechamento (PDD ativo A-H que entra no balanco)
 *   1. Reconciliacao do Δ PDD ativo: Constituicao − Reversao − Saida WOP = Δ
 *      (fecha com o headline; nenhum papel com variacao fica de fora)
 *   2. Papeis em WOP — transferencia DC↔PDD (mostra % provisionado em D-1 +
 *      impacto na cota; quando 100% provisionado e neutro)
 *   3. Papeis com variacao de PDD + coluna "Motivo" (Proprio vencido / Arrasto
 *      vagao / Liquidado) derivada de `efeito_vagao` + situacao do papel
 *
 * Matriz de migracao A/B/C/D/E/F/G/H ↔ WOP/NOVO removida em 2026-05-24
 * (densa demais pro slot direito).
 *
 * 2026-05-29: WopTable + PapeisTable migraram do `<table>` artesanal para a
 * DataTable canonica `density="ultra"` (h-7/28px) — regra dura de consistencia
 * dos drills da Cota Sub. Totais via `renderFooter`; sem corte (lista TODOS os
 * papeis — backend usa defaults 0/1000). A Reconciliacao continua em tabela
 * inline (3 linhas fixas, nao e uma lista de dados).
 */

import {
  RiArrowRightDownLine,
  RiBarChartHorizontalLine,
  RiErrorWarningLine,
  RiInboxLine,
  RiScales3Line,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import { useDrillPdd } from "@/lib/hooks/controladoria"
import type { DrillPddPapel, DrillPddResponse, PddFaixaKey } from "@/lib/api-client"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { Button } from "@/components/tremor/Button"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"
import {
  DrillClosureBadge,
  DrillSectionTitle,
  drillRowBorder,
  drillTableWrap,
  drillTfootRow,
  fmtBRL,
  fmtBRLSigned,
  toneClass,
} from "./drillKit"

// Cor de dot por faixa (paleta tailwind ad-hoc — Modo Iteracao de Design ativo).
const FAIXA_DOT: Record<PddFaixaKey, string> = {
  A:         "bg-emerald-500",
  B:         "bg-lime-500",
  C:         "bg-yellow-500",
  D:         "bg-orange-500",
  E:         "bg-red-500",
  F:         "bg-red-700",
  G:         "bg-red-800",
  H:         "bg-rose-900",
  WOP:       "bg-gray-500",
  LIQUIDADO: "bg-emerald-600",  // verde escuro — cobranca normal, evento positivo
  NOVO:      "bg-blue-500",
}

// Rotulo amigavel pt-BR. PddFaixaKey vem do backend com strings cruas.
const FAIXA_LABEL: Record<PddFaixaKey, string> = {
  A: "A", B: "B", C: "C", D: "D", E: "E", F: "F", G: "G", H: "H",
  WOP:       "WOP",
  LIQUIDADO: "Liquidado",
  NOVO:      "Novo",
}

// Percentual pt-BR (% provisionado em D-1 no painel WOP).
const fmtPct = new Intl.NumberFormat("pt-BR", {
  style:                 "percent",
  minimumFractionDigits: 0,
  maximumFractionDigits: 1,
})

// Motivo da variacao de PDD por papel (pedido Ricardo 2026-06-02): distinguir
// PDD por inadimplencia do PROPRIO titulo vs PDD arrastado pelo efeito vagao
// (Resolucao 2682 — pior faixa do sacado contamina os demais titulos dele).
type Motivo = { label: string; cls: string; title: string }

const MOTIVO_TONE = {
  proprio:   "border-gray-200 bg-gray-50 text-gray-600 dark:border-gray-800 dark:bg-gray-900/40 dark:text-gray-300",
  arrasto:   "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300",
  liquidado: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-400",
  reversao:  "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/30 dark:text-emerald-400",
} as const

// Props compartilhadas das DataTables do drill — ultra, sem toolbar, container
// bordado (espelha o antigo drillTableWrap).
const DT_PROPS = {
  density:           "ultra",
  virtualize:        false,
  showColumnManager: false,
  showDensityToggle: false,
  showExport:        false,
  className:         "rounded border border-gray-200 dark:border-gray-800",
} as const

const FOOT_ROW = "border-t-2 border-t-gray-300 dark:border-t-gray-700"

// ── Celulas compartilhadas (cedente/sacado empilhados; titulo mono) ──────────

function CedenteSacadoCell({ p }: { p: DrillPddPapel }) {
  return (
    <div title={`${p.cedente_doc} / ${p.sacado_doc}`}>
      <div className={cx("max-w-[160px] truncate font-medium", tableTokens.cellText)}>{p.cedente_nome}</div>
      <div className="max-w-[160px] truncate text-[10px] text-gray-500 dark:text-gray-400">→ {p.sacado_nome}</div>
    </div>
  )
}

function TituloCell({ p }: { p: DrillPddPapel }) {
  return (
    <span className={cx("block truncate font-mono text-[11px]", tableTokens.cellSecondary)}>{p.numero_documento || "—"}</span>
  )
}

export type DrillPddContentProps = {
  fundoId:       string
  data:          string
  dataAnterior?: string
}

export function DrillPddContent({ fundoId, data, dataAnterior }: DrillPddContentProps) {
  // Sem override de threshold/top_n — usa defaults do backend (0 / 1000), que
  // listam TODOS os papeis com variacao (confirmado 2026-05-24 e 2026-06-02:
  // o detalhamento nao pode esconder papel que sofreu variacao).
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
  const pddDisponivel = !d.motivo_indisponivel

  // Split constituicao (Δ+) vs reversao (Δ−) p/ o contador — reversoes precisam
  // ser visiveis (pedido Ricardo 2026-06-02). Papeis liquidados entram como Δ<0.
  const nDown = d.top_papeis.filter((p) => p.delta_valor_pdd < 0).length
  const nUp = d.top_papeis.length - nDown

  // Sets do efeito vagao p/ rotular cada papel na coluna "Motivo".
  const arrastadoDocs = new Set<string>()
  const puxadorDocs = new Set<string>()
  for (const v of d.efeito_vagao) {
    puxadorDocs.add(v.documento_puxador)
    for (const doc of v.documentos_arrastados) arrastadoDocs.add(doc)
  }

  function motivoOf(p: DrillPddPapel): Motivo {
    // Datas ISO (YYYY-MM-DD) comparam lexicograficamente.
    const vencido = p.data_vencimento_ajustada != null && p.data_vencimento_ajustada < d.data
    if (p.faixa_pdd_d0 === "LIQUIDADO") {
      return { label: "Liquidado", cls: MOTIVO_TONE.liquidado, title: "Titulo saiu por liquidacao/recompra — PDD reverteu." }
    }
    if (arrastadoDocs.has(p.numero_documento)) {
      return { label: "Arrasto (vagao)", cls: MOTIVO_TONE.arrasto, title: "Ainda nao venceu — provisionado por arrasto do sacado (Resolucao 2682)." }
    }
    if (puxadorDocs.has(p.numero_documento)) {
      return { label: "Proprio (vencido)", cls: MOTIVO_TONE.proprio, title: "Titulo vencido que puxou o sacado para a faixa." }
    }
    if (p.delta_valor_pdd < 0) {
      return { label: "Reversao", cls: MOTIVO_TONE.reversao, title: "PDD do papel caiu entre D-1 e D0." }
    }
    if (vencido) {
      return { label: "Proprio (vencido)", cls: MOTIVO_TONE.proprio, title: "Provisao do proprio titulo (vencido)." }
    }
    return { label: "Propria evolucao", cls: MOTIVO_TONE.proprio, title: "Variacao de provisao do proprio papel (sem arrasto)." }
  }

  return (
    <div className="flex flex-col gap-5">
      {/* ── Selo de fechamento ── */}
      <DrillClosureBadge
        fecha={pddDisponivel}
        sub={!pddDisponivel ? "estoque granular indisponível — totais não confirmáveis" : undefined}
      >
        {pddDisponivel
          ? `Fecha · PDD ativo (faixas A-H) = ${fmtBRL.format(d.pdd_granular_ex_wop_d0)} (entra no balanço)`
          : "PDD não confirmável nesta data"}
      </DrillClosureBadge>

      {d.motivo_indisponivel && (
        <div className="flex items-start gap-2 rounded border border-amber-200 bg-amber-50 px-3 py-2 text-[11px] text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300">
          <RiErrorWarningLine className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          <div>
            <strong>Estoque granular indisponível:</strong> {d.motivo_indisponivel}.
            Papéis em write-off e variações por papel ficam vazios.
          </div>
        </div>
      )}

      {/* ── Reconciliação do Δ PDD ativo (fecha com o headline) ── */}
      {pddDisponivel && d.resumo && <ReconcileBlock d={d} />}

      {/* ── WOP destacado — transferência DC↔PDD ── */}
      {d.papeis_wop.length > 0 && (
        <section>
          <DrillSectionTitle
            icon={RiScales3Line}
            label="Papéis que viraram WOP no dia"
            counter={`${d.papeis_wop.length} papel(eis) · Σ PDD que saiu ${fmtBRL.format(d.papeis_wop_total_pdd_d1)}`}
          />
          <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
            Saiu de A-H para WOP: leva DC e PDD juntos — <strong>neutro na cota</strong> se já 100% provisionado.
          </p>
          <WopTable papeis={d.papeis_wop} />
        </section>
      )}

      {/* ── Todos os papeis com variacao de PDD ── */}
      <section>
        <DrillSectionTitle
          icon={RiBarChartHorizontalLine}
          label="Papéis com variação de PDD"
          counter={
            d.top_papeis_total_acima_threshold > d.top_papeis.length
              ? `${nUp}↑ ${nDown}↓ · ${d.top_papeis.length} de ${d.top_papeis_total_acima_threshold}`
              : `${nUp}↑ ${nDown}↓ · ${d.top_papeis.length} papel(eis)`
          }
        />
        <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
          Papéis ex-WOP com Δ de PDD — constituições (Δ+) <strong>e reversões (Δ−)</strong>. Motivo: próprio (vencido) vs arrasto (vagão).
          {d.top_papeis_total_acima_threshold > d.top_papeis.length && (
            <> Lista cortada nos {d.top_papeis.length} primeiros — há mais {d.top_papeis_total_acima_threshold - d.top_papeis.length} com variação menor.</>
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
          <PapeisTable papeis={d.top_papeis} highlightDelta motivoOf={motivoOf} />
        )}
      </section>
    </div>
  )
}

// ─── Sub-componentes ────────────────────────────────────────────────────────

/**
 * Bloco de reconciliacao do Δ PDD ativo (A-H) entre D-1 e D0. Decompoe o
 * delta do headline em 3 forcas, provando que fecha:
 *
 *   Δ = Constituicao (PDD subiu) − Reversao (amortizacao) − Saida WOP
 *
 * Tudo de campos que o backend ja entrega: `resumo` (constituicao/reversao
 * ex-WOP) + `papeis_wop_total_pdd_d1` (o que saiu p/ WOP). A reversao genuina
 * = resumo.reversao_total + saida_wop, porque o backend inclui a saida
 * WOP dentro de reversao_total (o papel sai do PDD ativo).
 *
 * Mantida como tabela inline (3 linhas fixas + total — nao e lista de dados
 * que justifique DataTable canonica).
 */
function ReconcileBlock({ d }: { d: DrillPddResponse }) {
  const resumo = d.resumo!
  const constituicao = resumo.constituicao_total            // >= 0 (PDD subiu)
  const saidaWop = d.papeis_wop_total_pdd_d1                 // >= 0 (saiu do ativo p/ WOP)
  const reversaoAmort = resumo.reversao_total + saidaWop     // <= 0 (amortizacao/baixa genuina)
  const deltaAtivo = d.pdd_granular_ex_wop_d0 - d.pdd_granular_ex_wop_d1
  const soma = constituicao + reversaoAmort - saidaWop
  const fecha = Math.abs(soma - deltaAtivo) < 0.02

  const linhas: { label: string; valor: number; tone: string; nota?: string }[] = [
    {
      label: "Constituição (PDD subiu)",
      valor: constituicao,
      tone:  toneClass(constituicao, false),
    },
    {
      label: "Reversão (amortização)",
      valor: reversaoAmort,
      tone:  toneClass(reversaoAmort, false),
    },
    {
      label: "Saída para WOP",
      valor: -saidaWop,
      tone:  "text-gray-500 dark:text-gray-400",
      nota:  "neutro na cota — papel já provisionado",
    },
  ]

  return (
    <section>
      <DrillSectionTitle
        icon={RiArrowRightDownLine}
        label="Reconciliação do Δ PDD ativo"
        counter={`${fmtBRL.format(d.pdd_granular_ex_wop_d1)} → ${fmtBRL.format(d.pdd_granular_ex_wop_d0)}`}
      />
      <div className={cx("mt-2", drillTableWrap)}>
        <table className="w-full whitespace-nowrap text-[12px] tabular-nums">
          <tbody>
            {linhas.map((l) => (
              <tr key={l.label} className={drillRowBorder}>
                <td className="px-3 py-1.5 text-gray-700 dark:text-gray-200">
                  {l.label}
                  {l.nota && (
                    <span className="ml-1.5 text-[10px] text-gray-400 dark:text-gray-500">· {l.nota}</span>
                  )}
                </td>
                <td className={cx("px-3 py-1.5 text-right font-medium", l.tone)}>
                  {fmtBRLSigned(l.valor)}
                </td>
              </tr>
            ))}
          </tbody>
          <tfoot>
            <tr className={drillTfootRow}>
              <td className="px-3 py-1.5 text-gray-700 dark:text-gray-200">
                = Δ PDD ativo (A-H)
                <span className={cx("ml-1.5 text-[10px] font-normal", fecha ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400")}>
                  {fecha ? "· fecha ✓" : "· não fecha ✗"}
                </span>
              </td>
              <td className={cx("px-3 py-1.5 text-right", toneClass(deltaAtivo, false))}>
                {fmtBRLSigned(deltaAtivo)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>
  )
}

/**
 * Tabela dos papeis que viraram WOP no dia. Mostra % provisionado em D-1 e o
 * impacto na cota (= valor_pdd_d1 − valor_pdd_d0, que e ZERO quando o papel ja
 * estava 100% provisionado). VP ≈ valor_pdd_d0 porque WOP carrega PDD em 100%
 * do VP por construcao QiTech.
 */
function WopTable({ papeis }: { papeis: DrillPddPapel[] }) {
  const totPddD1 = papeis.reduce((s, p) => s + p.valor_pdd_d1, 0)
  const totImpacto = papeis.reduce((s, p) => s + (p.valor_pdd_d1 - p.valor_pdd_d0), 0)

  const col = createColumnHelper<DrillPddPapel>()
  const columns: ColumnDef<DrillPddPapel, unknown>[] = [
    col.accessor((p) => p.cedente_nome, {
      id: "cedente_sacado", header: "Cedente / Sacado", size: 180,
      cell: (info) => <CedenteSacadoCell p={info.row.original} />,
    }) as ColumnDef<DrillPddPapel, unknown>,
    col.accessor("numero_documento", {
      id: "titulo", header: "Título", size: 150,
      cell: (info) => <TituloCell p={info.row.original} />,
    }) as ColumnDef<DrillPddPapel, unknown>,
    col.accessor((p) => p, {
      id: "pct", header: "% prov. D-1", size: 110, meta: { align: "right" },
      cell: (info) => {
        const p = info.row.original
        const base = p.valor_pdd_d0 || p.valor_nominal
        const pct = base > 0 ? p.valor_pdd_d1 / base : 0
        return <div className={cx("text-right", tableTokens.cellNumber)}>{fmtPct.format(pct)}</div>
      },
    }) as ColumnDef<DrillPddPapel, unknown>,
    col.accessor("valor_nominal", {
      id: "nominal", header: "Nominal", size: 120, meta: { align: "right" },
      cell: (info) => <div className={cx("text-right", tableTokens.cellNumberSecondary)}>{fmtBRL.format(info.getValue<number>())}</div>,
    }) as ColumnDef<DrillPddPapel, unknown>,
    col.accessor("valor_pdd_d1", {
      id: "pdd_d1", header: "PDD D-1", size: 120, meta: { align: "right" },
      cell: (info) => <div className={cx("text-right", tableTokens.cellNumberSecondary)}>{fmtBRL.format(info.getValue<number>())}</div>,
    }) as ColumnDef<DrillPddPapel, unknown>,
    col.accessor((p) => p.valor_pdd_d1 - p.valor_pdd_d0, {
      id: "impacto", header: "Impacto na cota", size: 130, meta: { align: "right" },
      cell: (info) => {
        const impacto = info.getValue<number>()  // <= 0; 0 = neutro
        const neutro = Math.abs(impacto) < 0.01
        return (
          <div className="text-right">
            {neutro ? (
              <span className="inline-flex items-center gap-1 text-[11px] text-gray-400 dark:text-gray-500">
                <span className="inline-block size-1.5 rounded-full bg-gray-400" aria-hidden />
                neutro
              </span>
            ) : (
              <span className="text-xs font-semibold tabular-nums text-red-600 dark:text-red-400">{fmtBRLSigned(impacto)}</span>
            )}
          </div>
        )
      },
    }) as ColumnDef<DrillPddPapel, unknown>,
  ]

  return (
    <div className="mt-2">
      <DataTable<DrillPddPapel>
        {...DT_PROPS}
        data={papeis}
        columns={columns}
        renderFooter={() => (
          <tr className={FOOT_ROW}>
            <td colSpan={4} className="px-3"><span className={tableTokens.cellStrong}>Total · {papeis.length} papel(eis)</span></td>
            <td className="px-3"><div className={cx("text-right", tableTokens.cellNumberSecondary)}>{fmtBRL.format(totPddD1)}</div></td>
            <td className="px-3">
              <div className="text-right">
                {Math.abs(totImpacto) < 0.01 ? (
                  <span className="text-[11px] text-gray-400 dark:text-gray-500">neutro</span>
                ) : (
                  <span className="text-xs font-semibold tabular-nums text-red-600 dark:text-red-400">{fmtBRLSigned(totImpacto)}</span>
                )}
              </div>
            </td>
          </tr>
        )}
      />
    </div>
  )
}

function PapeisTable({
  papeis, highlightDelta, motivoOf,
}: {
  papeis:        DrillPddPapel[]
  highlightDelta: boolean
  motivoOf?:     (p: DrillPddPapel) => Motivo
}) {
  const totNominal = papeis.reduce((s, p) => s + p.valor_nominal, 0)
  const totPddD1 = papeis.reduce((s, p) => s + p.valor_pdd_d1, 0)
  const totPddD0 = papeis.reduce((s, p) => s + p.valor_pdd_d0, 0)
  const totDelta = papeis.reduce((s, p) => s + p.delta_valor_pdd, 0)
  const showMotivo = motivoOf != null

  const col = createColumnHelper<DrillPddPapel>()
  const columns: ColumnDef<DrillPddPapel, unknown>[] = [
    col.accessor((p) => p.cedente_nome, {
      id: "cedente_sacado", header: "Cedente / Sacado", size: 180,
      cell: (info) => <CedenteSacadoCell p={info.row.original} />,
    }) as ColumnDef<DrillPddPapel, unknown>,
    col.accessor("numero_documento", {
      id: "titulo", header: "Título", size: 150,
      cell: (info) => <TituloCell p={info.row.original} />,
    }) as ColumnDef<DrillPddPapel, unknown>,
    col.accessor((p) => p, {
      id: "faixa", header: "Faixa", size: 130, meta: { align: "center" },
      cell: (info) => {
        const p = info.row.original
        return (
          <div className="text-center">
            <span className="inline-flex items-center gap-1 text-[10px]">
              <span className={cx("inline-block size-1.5 rounded-full", FAIXA_DOT[p.faixa_pdd_d1 ?? "NOVO"])} aria-hidden />
              <span className="text-gray-500">{FAIXA_LABEL[p.faixa_pdd_d1 ?? "NOVO"]}</span>
              <span className="text-gray-400">→</span>
              <span className={cx("inline-block size-1.5 rounded-full", FAIXA_DOT[p.faixa_pdd_d0 ?? "WOP"])} aria-hidden />
              <span className={cx(
                p.faixa_pdd_d0 === "LIQUIDADO"
                  ? "font-medium text-emerald-700 dark:text-emerald-400"
                  : "text-gray-900 dark:text-gray-50",
              )}>{FAIXA_LABEL[p.faixa_pdd_d0 ?? "WOP"]}</span>
            </span>
          </div>
        )
      },
    }) as ColumnDef<DrillPddPapel, unknown>,
  ]
  if (showMotivo) {
    columns.push(
      col.accessor((p) => p, {
        id: "motivo", header: "Motivo", size: 150,
        cell: (info) => {
          const motivo = motivoOf?.(info.row.original)
          return motivo ? (
            <span
              className={cx("inline-flex items-center rounded-sm border px-1.5 py-0.5 text-[10px] font-medium", motivo.cls)}
              title={motivo.title}
            >
              {motivo.label}
            </span>
          ) : null
        },
      }) as ColumnDef<DrillPddPapel, unknown>,
    )
  }
  columns.push(
    col.accessor("valor_nominal", {
      id: "nominal", header: "Nominal", size: 120, meta: { align: "right" },
      cell: (info) => <div className={cx("text-right", tableTokens.cellNumberSecondary)}>{fmtBRL.format(info.getValue<number>())}</div>,
    }) as ColumnDef<DrillPddPapel, unknown>,
    col.accessor("valor_pdd_d1", {
      id: "pdd_d1", header: "PDD D-1", size: 120, meta: { align: "right" },
      cell: (info) => <div className={cx("text-right", tableTokens.cellNumberSecondary)}>{fmtBRL.format(info.getValue<number>())}</div>,
    }) as ColumnDef<DrillPddPapel, unknown>,
    col.accessor("valor_pdd_d0", {
      id: "pdd_d0", header: "PDD D0", size: 120, meta: { align: "right" },
      cell: (info) => <div className={cx("text-right", tableTokens.cellNumber)}>{fmtBRL.format(info.getValue<number>())}</div>,
    }) as ColumnDef<DrillPddPapel, unknown>,
    col.accessor("delta_valor_pdd", {
      id: "delta", header: "Δ", size: 120, meta: { align: "right" },
      cell: (info) => (
        <div className={cx(
          "text-right tabular-nums text-xs",
          highlightDelta && "font-semibold",
          toneClass(info.getValue<number>(), false),
        )}>
          {fmtBRLSigned(info.getValue<number>())}
        </div>
      ),
    }) as ColumnDef<DrillPddPapel, unknown>,
  )

  return (
    <div className="mt-2">
      <DataTable<DrillPddPapel>
        {...DT_PROPS}
        data={papeis}
        columns={columns}
        renderFooter={() => (
          <tr className={FOOT_ROW}>
            <td colSpan={showMotivo ? 4 : 3} className="px-3"><span className={tableTokens.cellStrong}>Total · {papeis.length} papel(eis)</span></td>
            <td className="px-3"><div className={cx("text-right", tableTokens.cellNumberSecondary)}>{fmtBRL.format(totNominal)}</div></td>
            <td className="px-3"><div className={cx("text-right", tableTokens.cellNumberSecondary)}>{fmtBRL.format(totPddD1)}</div></td>
            <td className="px-3"><div className={cx("text-right", tableTokens.cellNumber)}>{fmtBRL.format(totPddD0)}</div></td>
            <td className="px-3"><div className={cx("text-right text-xs font-semibold tabular-nums", toneClass(totDelta, false))}>{fmtBRLSigned(totDelta)}</div></td>
          </tr>
        )}
      />
    </div>
  )
}
