"use client"

//
// ConcentracaoCard — card de ranking Top-10 (cedentes ou sacados).
// Lâmina de leitura -> DenseTable canônica (modo padrão): coluna de posição
// (#), nome, valor presente, % PL + rodapé "10 maiores" (subtotal) e
// "Outros (N)" (cauda) que reconciliam a carteira (§14.6).
//

import * as React from "react"

import { Card } from "@/components/tremor/Card"
import {
  DenseTable,
  type DenseColumn,
  type DenseRow,
} from "@/design-system/components/DenseTable"
import { cardTokens } from "@/design-system/tokens/card"
import { cx } from "@/lib/utils"
import type { ConcentracaoTabela } from "@/lib/api-client"

export function ConcentracaoCard({
  titulo,
  eyebrow,
  posicao,
  tabela,
  loading,
}: {
  titulo: string
  eyebrow: string
  posicao: string
  tabela: ConcentracaoTabela | undefined
  loading: boolean
}) {
  const columns = React.useMemo<DenseColumn[]>(
    () => [
      { key: "rank", label: "#", format: "numero" },
      { key: "nome", label: eyebrow, format: "texto" },
      { key: "financeiro", label: "Valor Presente", format: "numero" },
      { key: "pct_pl", label: "% PL", format: "pct" },
    ],
    [eyebrow],
  )

  const rows = React.useMemo<DenseRow[]>(
    () =>
      (tabela?.itens ?? []).map((i) => ({
        rank: i.rank,
        nome: i.nome,
        financeiro: Math.round(i.financeiro),
        pct_pl: i.pct_pl,
      })),
    [tabela],
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

  return (
    <Card className="p-0">
      <div className={cx(cardTokens.header, "flex items-baseline gap-2")}>
        <h3 className="text-[15px] font-semibold text-gray-900 dark:text-gray-50">
          {titulo}
        </h3>
        <span className="text-[12px] text-gray-500 dark:text-gray-400">
          10 maiores · {posicao}
        </span>
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
            columns={columns}
            rows={rows}
            footer={footer}
            footerSecondary={footerSecondary}
          />
        </div>
      )}
    </Card>
  )
}
