"use client"

//
// ConcentracaoCard — modo ANALISE Top 1/5/10 (handoff "Tabela canonica" v2, §4b).
// "A tabela como grafico": uma DenseTable ranqueada por %PL serve as tres
// leituras de risco numa estrutura so, vestindo a anatomia de card de grafico:
//
//   eyebrow "Concentracao de cedentes — em R$"
//   trio de KPIs (Top 1 / Top 5 / Top 10 = %PL ACM nos ranks 1/5/10),
//     padrao KpiBand (colunas com divisoria parcial, valor neutro 22px)
//   contexto "PL R$ X · Carteira DD/MM"
//   DenseTable: linhas-marco (1,5,10) com TRILHO azul + # e %PL ACM em
//     negrito gray-900; demais com %PL ACM muted (gray-400) -> "escada".
//   rodape "10 maiores" + "Outros (N)" reconcilia a carteira (§14.6).
//
// NOTA (delta): o handoff cita "Top 10 com delta tintado". O snapshot `tabela`
// nao traz base de comparacao (vs D-1 / vs limite), entao o delta foi OMITIDO
// em vez de fabricado (§14 auditabilidade). Ligar ao historico e follow-up.
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
  loading,
}: {
  titulo: string
  posicao: string
  tabela: ConcentracaoTabela | undefined
  plTotal: number | undefined
  loading: boolean
}) {
  // "Cedentes" -> "Cedente" (label da coluna de nome).
  const singular = titulo.endsWith("s") ? titulo.slice(0, -1) : titulo

  const { rows, top1, top5, top10 } = React.useMemo(() => {
    const itens = tabela?.itens ?? []
    let acc = 0
    const rows: DenseRow[] = itens.map((i) => {
      acc += i.pct_pl
      return {
        rank: i.rank,
        nome: i.nome,
        financeiro: Math.round(i.financeiro),
        pct_pl: i.pct_pl,
        acm: acc,
      }
    })
    const acmAt = (r: number) =>
      (rows.find((x) => x.rank === r)?.acm as number | undefined) ?? undefined
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
        widthClass: "w-9",
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
        // Coluna larga (resto do espaco em table-fixed) que TRUNCA — nome longo
        // de cedente nao quebra a linha; nome completo no title (hover).
        key: "nome",
        label: singular,
        format: "texto",
        render: (row) => (
          <span className={cx("block truncate", tableTokens.cellText)} title={String(row.nome ?? "")}>
            {row.nome}
          </span>
        ),
      },
      { key: "financeiro", label: "Valor pres.", format: "numero", widthClass: "w-[92px]" },
      { key: "pct_pl", label: "% PL", format: "pct", widthClass: "w-[60px]" },
      {
        key: "acm",
        label: "% PL ACM",
        format: "pct",
        widthClass: "w-[72px]",
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

  const footer: DenseRow | undefined = tabela && {
    nome: "10 maiores",
    financeiro: Math.round(tabela.total_financeiro),
    pct_pl: tabela.total_pct_pl,
  }
  const footerSecondary: DenseRow | undefined = tabela && {
    nome: `Outros (${tabela.outros_qtd})`,
    financeiro: Math.round(tabela.outros_financeiro),
    pct_pl: tabela.outros_pct_pl,
  }

  const kpis = [
    { label: "Top 1", value: pct1(top1) },
    { label: "Top 5", value: pct1(top5) },
    { label: "Top 10", value: pct1(top10) },
  ]

  return (
    <Card className="p-0">
      {/* Cabecalho: eyebrow + trio de KPIs (Top 1/5/10) + contexto.
          SEM border-b (a tabela flui direto sob o contexto — handoff §4b). */}
      <div className="px-4 pb-1 pt-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
          Concentração de {titulo.toLowerCase()} — em R$
        </p>

        {/* Trio de KPIs — anatomia KpiBand (colunas + divisoria parcial; valor neutro). */}
        <div className="mt-2 flex">
          {kpis.map((k, idx) => (
            <div
              key={k.label}
              className={cx("relative flex-1", idx > 0 && "pl-5")}
            >
              {idx > 0 && (
                <span
                  aria-hidden
                  className="absolute bottom-1 left-0 top-1 w-px bg-gray-100 dark:bg-gray-800"
                />
              )}
              <p className="text-[10px] font-medium uppercase tracking-[0.05em] text-gray-500 dark:text-gray-400">
                {k.label} · acum.
              </p>
              <span className="mt-0.5 block text-[22px] font-semibold leading-tight tracking-tight tabular-nums text-gray-900 dark:text-gray-50">
                {k.value}
              </span>
            </div>
          ))}
        </div>

        <p className="mt-2 text-[13px] text-gray-500 dark:text-gray-400">
          {plTotal != null && plTotal > 0 ? `PL ${fmtMi(plTotal)} · ` : ""}
          Carteira {posicao}
        </p>
      </div>

      {loading ? (
        <div className="space-y-1.5 px-3 pb-3">
          {Array.from({ length: 10 }).map((_, i) => (
            <div
              key={i}
              className="h-5 animate-pulse rounded bg-gray-100 dark:bg-gray-800"
            />
          ))}
        </div>
      ) : (
        <div className="px-3 pb-3">
          <DenseTable
            bordered={false}
            tableLayout="fixed"
            columns={columns}
            rows={rows}
            footer={footer}
            footerSecondary={footerSecondary}
            rowClassName={rowClassName}
          />
        </div>
      )}
    </Card>
  )
}
