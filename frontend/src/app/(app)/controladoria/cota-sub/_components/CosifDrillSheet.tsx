"use client"

/**
 * CosifDrillSheet — drill-down ao clicar conta analitica no BalanceteDiarioTable.
 *
 * Mostra:
 *   - Header com codigo COSIF + badge da origem (override/regra/pendente)
 *   - Hero com nome + saldo D0 + delta (vs D-1)
 *   - PropertyList: codigo, natureza, nivel, grupo, parent_codigo
 *   - SrMezSubBreakdown (quando aplicavel — conta carrega quebra por classe)
 *   - Slot ExplainerCard (preparado, backend Fase 1 ainda nao envia explainers
 *     — placeholder "Em desenvolvimento" quando vazio)
 */

import * as React from "react"

import { cx } from "@/lib/utils"
import { Badge } from "@/components/tremor/Badge"
import {
  DrillDownSheet,
} from "@/design-system/components/DrillDownSheet"

import type { ClasseBreakdown, CosifNode, CosifRow } from "@/lib/api-client"
import { useCosifRows } from "@/lib/hooks/controladoria"
import { sourceBadge } from "../_lib/cosif"

// ─────────────────────────────────────────────────────────────────────────────
// Formatters
// ─────────────────────────────────────────────────────────────────────────────

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL",
  minimumFractionDigits: 2, maximumFractionDigits: 2,
})

const fmtPct = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2, maximumFractionDigits: 2,
})

function fmtCurrency(v: number | null): string {
  if (v == null) return "—"
  if (v === 0) return "—"
  return fmtBRL.format(v)
}

function fmtDelta(v: number | null): string {
  if (v == null) return "—"
  if (v === 0) return "—"
  const sign = v > 0 ? "+" : ""
  return `${sign}${fmtBRL.format(v)}`
}

// ─────────────────────────────────────────────────────────────────────────────
// SrMezSubBreakdown — sub-tabela de classes Sr/Mez/Sub quando a conta carrega
// ─────────────────────────────────────────────────────────────────────────────

const CLASSE_LABEL: Record<string, string> = {
  senior:       "Senior",
  mezanino:     "Mezanino",
  subordinado:  "Subordinado",
  aporte:       "Aporte",
  compensacao:  "Compensacao",
}

function SrMezSubBreakdown({ items }: { items: ClasseBreakdown[] }) {
  if (items.length === 0) return null
  return (
    <div className="rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
      <div className="border-b border-gray-200 px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:border-gray-800 dark:text-gray-400">
        Quebra por classe
      </div>
      <table className="w-full text-xs">
        <thead className="bg-gray-50 dark:bg-gray-900/40">
          <tr className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
            <th className="px-3 py-1.5 text-left">Classe</th>
            <th className="px-3 py-1.5 text-right">D-1</th>
            <th className="px-3 py-1.5 text-right">D0</th>
            <th className="px-3 py-1.5 text-right">Δ</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
          {items.map((b, i) => (
            <tr key={`${b.classe}:${i}`}>
              <td className="px-3 py-1.5 text-gray-700 dark:text-gray-300">
                {CLASSE_LABEL[b.classe] ?? b.classe}
              </td>
              <td className="px-3 py-1.5 text-right font-mono tabular-nums text-gray-700 dark:text-gray-300">
                {fmtCurrency(b.d_minus_1)}
              </td>
              <td className="px-3 py-1.5 text-right font-mono tabular-nums text-gray-700 dark:text-gray-300">
                {fmtCurrency(b.d_zero)}
              </td>
              <td className={cx(
                "px-3 py-1.5 text-right font-mono tabular-nums",
                b.delta > 0 ? "text-emerald-600 dark:text-emerald-400" :
                b.delta < 0 ? "text-red-600 dark:text-red-400" :
                "text-gray-500 dark:text-gray-400",
              )}>
                {fmtDelta(b.delta)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// RowsSilverTab — tabela compacta dos papeis/lancamentos individuais que
// sustentam o saldo da conta COSIF. Adapta colunas conforme o silver_origin
// dominante (wh_posicao_renda_fixa mostra qtde+indexador; demais nao).
// ─────────────────────────────────────────────────────────────────────────────

const SILVER_LABEL: Record<string, string> = {
  wh_saldo_conta_corrente:    "Conta corrente",
  wh_saldo_tesouraria:        "Tesouraria",
  wh_posicao_compromissada:   "Compromissada",
  wh_posicao_renda_fixa:      "Renda fixa",
  wh_posicao_cota_fundo:      "Cota de fundo",
  wh_posicao_outros_ativos:   "Outros ativos",
  wh_cpr_movimento:           "CPR (movimento)",
}

function RowsSilverTab({
  node,
  loading,
  error,
  rows,
  totalValor,
}: {
  node:       CosifNode
  loading:    boolean
  error:      string | null
  rows:       CosifRow[]
  totalValor: number
}) {
  // Bucket pendente nao tem endpoint — exibir mensagem.
  if (!node.codigo) {
    return (
      <div className="flex h-full items-center justify-center py-10 text-center text-sm text-gray-500 dark:text-gray-400">
        Conta sem classificacao COSIF — nao ha drill-down disponivel.<br />
        Crie um override em /admin/controladoria/cosif para classificar.
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex flex-col gap-2 py-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-7 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
        ))}
      </div>
    )
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center py-10 text-center text-sm text-red-600 dark:text-red-400">
        Falha ao carregar rows do silver: {error}
      </div>
    )
  }

  if (rows.length === 0) {
    return (
      <div className="flex h-full items-center justify-center py-10 text-center text-sm text-gray-500 dark:text-gray-400">
        Nenhuma linha do silver para esta conta nesta data.
      </div>
    )
  }

  // Decide colunas: RF (com qtde) ou demais (so codigo+nome+valor).
  const hasRF = rows.some((r) => r.silver_origin === "wh_posicao_renda_fixa")

  return (
    <div className="rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
      <div className="flex items-center justify-between gap-2 border-b border-gray-200 px-3 py-1.5 dark:border-gray-800">
        <span className="text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Papeis nesta conta
        </span>
        <span className="text-[11px] tabular-nums text-gray-500 dark:text-gray-400">
          {rows.length} {rows.length === 1 ? "linha" : "linhas"} ·{" "}
          <span className="font-mono">{fmtBRL.format(totalValor)}</span>
        </span>
      </div>
      <table className="w-full text-xs">
        <thead className="bg-gray-50 dark:bg-gray-900/40">
          <tr className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
            <th className="px-3 py-1.5 text-left">Codigo</th>
            <th className="px-3 py-1.5 text-left">Papel / Descricao</th>
            {hasRF && <th className="px-3 py-1.5 text-right">Qtde</th>}
            {hasRF && <th className="px-3 py-1.5 text-left">Idx</th>}
            <th className="px-3 py-1.5 text-right">Valor</th>
            <th className="px-3 py-1.5 text-left">Silver</th>
            <th className="px-3 py-1.5 text-center">Origem</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
          {rows.map((r, i) => (
            <tr key={`${r.silver_origin}:${r.codigo}:${i}`}>
              <td className="px-3 py-1.5 font-mono text-[11px] tabular-nums text-gray-700 dark:text-gray-300">
                {r.codigo ?? "—"}
              </td>
              <td className="max-w-[260px] truncate px-3 py-1.5 text-gray-900 dark:text-gray-50" title={r.nome}>
                {r.nome}
              </td>
              {hasRF && (
                <td className="px-3 py-1.5 text-right font-mono tabular-nums text-gray-700 dark:text-gray-300">
                  {r.quantidade != null
                    ? new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 4 }).format(r.quantidade)
                    : "—"}
                </td>
              )}
              {hasRF && (
                <td className="px-3 py-1.5 text-gray-500 dark:text-gray-400">
                  {r.indexador ?? "—"}
                </td>
              )}
              <td className={cx(
                "px-3 py-1.5 text-right font-mono tabular-nums",
                r.valor > 0 ? "text-gray-900 dark:text-gray-50" :
                r.valor < 0 ? "text-red-600 dark:text-red-400" :
                "text-gray-500 dark:text-gray-400",
              )}>
                {fmtCurrency(r.valor)}
              </td>
              <td className="px-3 py-1.5 font-mono text-[10px] text-gray-500 dark:text-gray-400">
                {SILVER_LABEL[r.silver_origin] ?? r.silver_origin}
              </td>
              <td className="px-3 py-1.5 text-center">
                <SourceBadgeChip source={r.cosif_source} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Source badge
// ─────────────────────────────────────────────────────────────────────────────

function SourceBadgeChip({ source }: { source: string }) {
  const { label, tone } = sourceBadge(source)
  const variant =
    tone === "blue"    ? "default"  :
    tone === "green"   ? "success"  :
    tone === "amber"   ? "warning"  :
    tone === "red"     ? "error"    :
    "neutral"
  return <Badge variant={variant} className="px-2 py-0.5 text-[10px] ring-0">{label}</Badge>
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

const NATUREZA_LABEL: Record<string, string> = {
  D: "Devedora",
  C: "Credora",
  "?": "Pendente",
}

const GRUPO_LABEL: Record<number, string> = {
  1: "Ativo Circulante e Realizavel",
  3: "Compensacao (Ativo)",
  4: "Passivo Circulante e Exigivel",
  6: "Patrimonio Liquido",
  7: "Resultado Credoras",
  8: "Resultado Devedoras",
  9: "Compensacao (Passivo)",
  0: "Pendente",
}

export type CosifDrillSheetProps = {
  node:                CosifNode | null
  /** Quebra por classe Sr/Mez/Sub do backend, keyed por cosif_codigo. */
  classeBreakdown?:    ClasseBreakdown[]
  /** Fundo + data ISO — necessarios para o drill de rows silver. */
  fundoId?:            string | null
  dataPosicao?:        string | null
  onClose:             () => void
}

export function CosifDrillSheet({
  node,
  classeBreakdown,
  fundoId,
  dataPosicao,
  onClose,
}: CosifDrillSheetProps) {
  const open = node !== null

  // Rows silver — hook so dispara quando o sheet esta aberto, tem fundo+data
  // e o node tem codigo (bucket pendente nao tem endpoint).
  const rowsQuery = useCosifRows(
    fundoId ?? null,
    dataPosicao ?? null,
    open && node?.codigo ? node.codigo : null,
  )

  if (!node) {
    // DrillDownSheet exige children sempre — manter aberto:false implica
    // nao renderizar conteudo.
    return (
      <DrillDownSheet open={false} onClose={onClose} title="">
        <></>
      </DrillDownSheet>
    )
  }

  const title = node.codigo ?? "(pendente)"
  const breadcrumb = [
    "Balancete",
    `Grupo ${node.grupo === 0 ? "Pendente" : node.grupo}`,
    node.codigo ?? node.nome,
  ]

  return (
    <DrillDownSheet open={open} onClose={onClose} title={title}>
      <DrillDownSheet.Header
        breadcrumb={breadcrumb}
        statusSlot={<SourceBadgeChip source={node.cosif_source} />}
      />

      <DrillDownSheet.Hero
        id={node.codigo ?? "—"}
        title={node.nome}
        value={node.d_zero}
        delta={{
          value: node.delta,
          label: `vs D-1 (${fmtPct.format(node.delta_pct)}%)`,
        }}
      />

      <DrillDownSheet.Tabs
        tabs={[
          {
            value:   "geral",
            label:   "Visao geral",
            content: (
              <>
                <DrillDownSheet.PropertyList
                  items={[
                    { label: "Codigo COSIF",  value: node.codigo ?? "—" },
                    { label: "Natureza",      value: NATUREZA_LABEL[node.natureza] ?? node.natureza },
                    { label: "Nivel",         value: String(node.nivel) },
                    { label: "Grupo",         value: GRUPO_LABEL[node.grupo] ?? String(node.grupo) },
                    { label: "Conta pai",     value: node.parent_codigo ?? "—" },
                    { label: "Origem",        value: node.cosif_source || "—" },
                    { label: "D-1",           value: node.d_minus_1,  type: "currency" },
                    { label: "D0",            value: node.d_zero,     type: "currency" },
                    { label: "Δ",             value: node.delta,      type: "currency" },
                    { label: "Δ %",           value: node.delta_pct,  type: "percentage" },
                    { label: "Rows classif.", value: String(node.rows_classified) },
                  ]}
                />

                {classeBreakdown && classeBreakdown.length > 0 && (
                  <div className="mt-6">
                    <DrillDownSheet.SectionLabel>
                      Composicao por classe
                    </DrillDownSheet.SectionLabel>
                    <SrMezSubBreakdown items={classeBreakdown} />
                  </div>
                )}

                {/* Slot ExplainerCard — Fase 1 backend ainda nao envia explainers.
                    Quando vier, renderizar aqui. */}
                <div className="mt-6">
                  <DrillDownSheet.SectionLabel>
                    Por que essa conta variou
                  </DrillDownSheet.SectionLabel>
                  <div className="rounded border border-dashed border-gray-300 bg-gray-50 px-3 py-4 text-xs text-gray-500 dark:border-gray-700 dark:bg-gray-900/40 dark:text-gray-400">
                    Explainers contextuais (PDD constituida, nova NCPX, subscricao/resgate, diferimento)
                    chegam na Fase 1.5 do backend. Por enquanto, consulte o silver canonico
                    via /admin/explorador para investigar a variacao.
                  </div>
                </div>
              </>
            ),
          },
          {
            value:   "rows",
            label:   `Rows silver${rowsQuery.data ? ` (${rowsQuery.data.rows.length})` : ""}`,
            content: (
              <RowsSilverTab
                node={node}
                loading={rowsQuery.isLoading}
                error={
                  rowsQuery.isError
                    ? (rowsQuery.error as Error | undefined)?.message ?? "Erro desconhecido"
                    : null
                }
                rows={rowsQuery.data?.rows ?? []}
                totalValor={rowsQuery.data?.total_valor ?? 0}
              />
            ),
          },
        ]}
        defaultValue="geral"
      />

      <DrillDownSheet.Footer>
        <div className="flex-1 text-xs text-gray-500 dark:text-gray-400">
          {node.cosif_source === "pendente"
            ? "Crie um override em /admin/controladoria/cosif para classificar."
            : null}
        </div>
      </DrillDownSheet.Footer>
    </DrillDownSheet>
  )
}
