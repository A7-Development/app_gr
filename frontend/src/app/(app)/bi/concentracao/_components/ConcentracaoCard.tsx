"use client"

//
// ConcentracaoCard — modo ANALISE Top 1/5/10 (handoff "Tabela canonica" §4b).
// Casado 1:1 com o specimen .dc.html: card padding 16px / gap 12px; eyebrow
// 11px gray-500; trio de KPIs 20px/700 com divisoria inteira gray-200 e label
// 10px gray-400; contexto 12px; tabela table-fixed, linha 28px (ultra), header
// 28px; coluna Cedente trunca (Title Case, siglas preservadas); rodape so
// "Outros (N)" com %PL ACM acumulado (reconcilia §14.6 junto das 10 linhas).
//
// NOTA: delta "↑ x pp" do Top 10 OMITIDO por decisao do Ricardo (snapshot sem
// base de comparacao). O specimen mostra o delta; aqui fica sem.
//

import * as React from "react"

import { Card } from "@/components/tremor/Card"
import {
  DenseTable,
  type DenseColumn,
  type DenseRow,
} from "@/design-system/components/DenseTable"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"
import type { ConcentracaoTabela } from "@/lib/api-client"

/** Ranks que marcam as faixas Top 1 / 5 / 10. */
const MARKERS = new Set([1, 5, 10])

/** Conectores que ficam minusculos no meio da razao social. */
const CONNECTORS = new Set(["de", "do", "da", "dos", "das", "e"])

/** Palavras curtas em CAIXA ALTA que NAO sao sigla (a heuristica <=3 letras
 *  preservaria como sigla por engano). Forma correta -> aqui. */
const FORCE_WORD: Record<string, string> = { SAO: "São" }

/**
 * Normaliza razao social de CAIXA ALTA (dado cru) para Title Case legivel
 * (handoff: nome em caixa normal). Preserva SIGLAS curtas (<=3 letras todas
 * maiusculas: MFL, BLB, SA, ME, EPP) e deixa conectores minusculos.
 */
function formatRazaoSocial(raw: string): string {
  const words = raw.trim().split(/\s+/)
  return words
    .map((w, i) => {
      const lower = w.toLowerCase()
      if (FORCE_WORD[w]) return FORCE_WORD[w]
      if (i > 0 && CONNECTORS.has(lower)) return lower
      if (w.length <= 3 && /^[A-ZÀ-Ý]+$/.test(w)) return w // sigla -> preserva
      return lower.charAt(0).toUpperCase() + lower.slice(1)
    })
    .join(" ")
}

function pct1(v: number | null | undefined): string {
  if (v == null) return "—"
  return `${v.toLocaleString("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })}%`
}

/** "27900000" -> "R$ 27,9 mi" (compacto pt-BR). */
function fmtMi(v: number): string {
  const f = (n: number) =>
    n.toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 1 })
  if (Math.abs(v) >= 1_000_000_000) return `R$ ${f(v / 1_000_000_000)} bi`
  if (Math.abs(v) >= 1_000_000) return `R$ ${f(v / 1_000_000)} mi`
  if (Math.abs(v) >= 1_000) return `R$ ${f(v / 1_000)} mil`
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
}

export function ConcentracaoCard({
  titulo,
  posicao,
  tabela,
  plTotal,
  top10DeltaPp,
  loading,
}: {
  titulo: string
  posicao: string
  tabela: ConcentracaoTabela | undefined
  plTotal: number | undefined
  /** Variacao em pontos percentuais do Top 10 vs ponto anterior do historico
   *  (derivado, real). Mostra "↑/↓ X,X pp" no KPI Top 10. undefined = sem delta. */
  top10DeltaPp?: number
  loading: boolean
}) {
  const singular = titulo.endsWith("s") ? titulo.slice(0, -1) : titulo

  const { rows, top1, top5, top10 } = React.useMemo(() => {
    const itens = tabela?.itens ?? []
    let acc = 0
    const rows: DenseRow[] = itens.map((i) => {
      acc += i.pct_pl
      return {
        rank: i.rank,
        nome: formatRazaoSocial(i.nome),
        financeiro: Math.round(i.financeiro),
        pct_pl: i.pct_pl,
        acm: acc,
      }
    })
    const acmAt = (r: number) => rows.find((x) => x.rank === r)?.acm as number | undefined
    return {
      rows,
      top1: acmAt(1),
      top5: acmAt(5),
      top10: acmAt(10) ?? tabela?.total_pct_pl,
    }
  }, [tabela])

  const columns = React.useMemo<DenseColumn[]>(
    () => [
      {
        key: "rank",
        label: "#",
        format: "numero",
        widthClass: "w-[30px]",
        render: (row) => {
          const mark = MARKERS.has(Number(row.rank))
          return (
            <span
              className={cx(
                "tabular-nums",
                mark ? tableTokens.cellStrong : tableTokens.cellNumberSecondary,
              )}
            >
              {row.rank}
            </span>
          )
        },
      },
      {
        // Resto do espaco (table-fixed) e TRUNCA — nome completo no title (hover).
        key: "nome",
        label: singular,
        format: "texto",
        render: (row) => (
          <span className={cx("block truncate", tableTokens.cellText)} title={String(row.nome ?? "")}>
            {row.nome}
          </span>
        ),
      },
      { key: "financeiro", label: "Valor pres.", format: "numero", widthClass: "w-[96px]" },
      {
        key: "acm",
        label: "% PL ACM",
        format: "pct",
        widthClass: "w-[82px]",
        render: (row) => {
          const mark = MARKERS.has(Number(row.rank))
          // Escada: marco = negrito gray-900; intermediaria = muted gray-400.
          return (
            <span
              className={cx(
                "tabular-nums",
                mark ? tableTokens.cellStrong : cx("text-xs", tableTokens.cellMuted),
              )}
            >
              {pct1(row.acm as number)}
            </span>
          )
        },
      },
    ],
    [singular],
  )

  // Trilho azul nas linhas-marco; transparente nas demais (sem deslocar celulas).
  const rowClassName = React.useCallback(
    (row: DenseRow) =>
      cx(
        "border-l-2",
        MARKERS.has(Number(row.rank)) ? "border-l-blue-500" : "border-l-transparent",
      ),
    [],
  )

  // Rodape: SO "Outros (N)" (sem "10 maiores"), com %PL ACM acumulado total —
  // as 10 linhas visiveis + Outros reconciliam a carteira (§14.6); o total das
  // 10 e o proprio KPI Top 10.
  const footerSecondary: DenseRow | undefined = tabela && {
    nome: `Outros (${tabela.outros_qtd})`,
    financeiro: Math.round(tabela.outros_financeiro),
    acm: tabela.total_pct_pl + tabela.outros_pct_pl,
  }

  // Delta do Top 10 (>= 0,05pp pra evitar ruido). ↑ verde / ↓ vermelho (handoff).
  const top10Delta =
    top10DeltaPp != null && Math.abs(top10DeltaPp) >= 0.05
      ? {
          up: top10DeltaPp >= 0,
          text: `${Math.abs(top10DeltaPp).toLocaleString("pt-BR", {
            minimumFractionDigits: 1,
            maximumFractionDigits: 1,
          })} pp`,
        }
      : undefined

  const kpis: Array<{ label: string; value: string; delta?: { up: boolean; text: string } }> = [
    { label: "Top 1", value: pct1(top1) },
    { label: "Top 5", value: pct1(top5) },
    { label: "Top 10", value: pct1(top10), delta: top10Delta },
  ]

  return (
    <Card className="flex flex-col gap-3 p-4">
      {/* Header 2 niveis (handoff Resumo·analise) */}
      <div>
        {/* Linha 1: eyebrow (esq) + PL/Carteira (dir), mesma baseline */}
        <div className="flex items-baseline justify-between gap-3">
          <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
            Concentração de {titulo.toLowerCase()} — em R$
          </p>
          <p className="shrink-0 whitespace-nowrap text-[12px] text-gray-500 dark:text-gray-400">
            {plTotal != null && plTotal > 0 && (
              <>
                PL{" "}
                <span className="font-semibold text-gray-900 dark:text-gray-100">
                  {fmtMi(plTotal)}
                </span>{" "}
                ·{" "}
              </>
            )}
            Carteira{" "}
            <span className="font-semibold text-gray-700 dark:text-gray-300">{posicao}</span>
          </p>
        </div>

        {/* Linha 2: trio de KPIs — divisoria inteira gray-200 */}
        <div className="mt-2.5 flex items-stretch">
          {kpis.map((k, idx) => (
            <div
              key={k.label}
              className={cx(
                "flex flex-col justify-start",
                idx === 0
                  ? "pr-[18px]"
                  : "border-l border-gray-200 px-[18px] dark:border-gray-800",
              )}
            >
              <p className="text-[10px] font-semibold uppercase tracking-[0.05em] text-gray-400 dark:text-gray-500">
                {k.label}
              </p>
              <span className="mt-[3px] flex items-baseline gap-1.5">
                <span className="text-[20px] font-bold leading-none tabular-nums text-gray-900 dark:text-gray-50">
                  {k.value}
                </span>
                {k.delta && (
                  <span
                    className={cx(
                      "text-[12px] font-semibold tabular-nums",
                      k.delta.up
                        ? "text-emerald-600 dark:text-emerald-400"
                        : "text-red-600 dark:text-red-400",
                    )}
                  >
                    {k.delta.up ? "↑" : "↓"} {k.delta.text}
                  </span>
                )}
              </span>
            </div>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="space-y-1.5">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="h-5 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
          ))}
        </div>
      ) : (
        <DenseTable
          bordered={false}
          tableLayout="fixed"
          density="ultra"
          columns={columns}
          rows={rows}
          footerSecondary={footerSecondary}
          rowClassName={rowClassName}
        />
      )}

      {/* Proveniencia — sangra ate as bordas (-mx-4), dot laranja (§14.5). */}
      <div className="-mx-4 -mb-4 flex items-center gap-1.5 border-t border-gray-100 px-4 py-2 dark:border-gray-900">
        <span className="size-[5px] shrink-0 rounded-full bg-[#F05A28]" aria-hidden />
        <span className="text-[10px] text-gray-400 dark:text-gray-500">
          Fonte: posição da carteira · {posicao}
        </span>
      </div>
    </Card>
  )
}
