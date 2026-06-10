"use client"

/**
 * ConciliacaoBoletoTable — tabela titulo-a-titulo da conciliacao de boletos.
 *
 * Recebe as `linhas` ja filtradas pelos chips globais (status/banco/produto/
 * cedente) e renderiza na `DataTable` CANONICA de listagem (density ULTRA +
 * toolbar completa: column manager, density toggle, export CSV; virtualiza >100
 * linhas). A busca por palavra mora na MESMA linha da toolbar (Exportar/colunas/
 * densidade), via slot `toolbarStart` da DataTable — alimenta o globalFilter do
 * TanStack. Colunas unificadas com "—" onde nao se aplica (ex.: "So em banco"
 * nao tem valor BITFIN). Cells via `tableTokens` (regra dura §6).
 */

import * as React from "react"
import { RiAuctionLine } from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import { DataTable } from "@/design-system/components/DataTable"
import { FilterSearch } from "@/design-system/components/FilterBar"
import { tableTokens } from "@/design-system/tokens/table"
import type {
  LinhaConciliacaoBoleto,
  StatusConciliacaoBoleto,
} from "@/lib/api-client"
import {
  STATUS_BADGE_LABEL,
  STATUS_META,
  agingTone,
  diasAguardando,
  protestoLabel,
  situacaoTituloCabeBaixa,
  situacaoTituloLabel,
} from "./status"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

function fmtDateBR(iso: string | null): string {
  if (!iso) return "—"
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[3]}/${m[2]}/${m[1].slice(2)}` : iso
}

// ── Cells (via tableTokens) ─────────────────────────────────────────────────

function NumCell({ value }: { value: number | null }) {
  if (value === null) return <div className={cx("text-right", tableTokens.cellNumberSecondary)}>—</div>
  return <div className={cx("text-right", tableTokens.cellNumber)}>{fmtBRL.format(value)}</div>
}

function DateCell({ value }: { value: string | null }) {
  return <div className={cx("text-right", tableTokens.cellNumberSecondary)}>{fmtDateBR(value)}</div>
}

/** Diferenca contextual: valor (toned) quando ha; senao dias; senao "—". */
function DiffCell({ row }: { row: LinhaConciliacaoBoleto }) {
  if (row.diferenca_valor !== null && Math.abs(row.diferenca_valor) >= 0.005) {
    const positive = row.diferenca_valor > 0
    return (
      <div
        className={cx(
          "text-right text-xs font-semibold tabular-nums",
          positive ? "text-red-600 dark:text-red-400" : "text-amber-600 dark:text-amber-400",
        )}
      >
        {positive ? "+" : ""}
        {fmtBRL.format(row.diferenca_valor)}
      </div>
    )
  }
  if (row.diferenca_dias !== null && row.diferenca_dias !== 0) {
    return (
      <div className="text-right text-xs font-semibold tabular-nums text-amber-600 dark:text-amber-400">
        {row.diferenca_dias > 0 ? "+" : ""}
        {row.diferenca_dias}d
      </div>
    )
  }
  return <div className={cx("text-right", tableTokens.cellNumberSecondary)}>—</div>
}

const col = createColumnHelper<LinhaConciliacaoBoleto>()

// Factory: a coluna Produto precisa do mapa sigla->nome (vem do biMetadata da
// pagina), por isso as colunas sao construidas com o resolver injetado.
function makeColumns(
  produtoNome: (sigla: string | null) => string,
): ColumnDef<LinhaConciliacaoBoleto, unknown>[] {
  return [
  // Status CONSOLIDADO: badge + anotacoes compactas na mesma celula (decisao
  // 2026-06-10, Ricardo: todas as colunas visiveis sem scroll horizontal).
  // - enviado_nao_confirmado: aging "Nd" colorido (>=3 amber, >=10 red=stuck)
  // - so_em_banco: situacao do titulo no sistema (Liquidado/Recomprado = baixa)
  // - protesto: icone martelo (red=instruido/cartorio) com tooltip tipo+data
  // O CSV exporta cada informacao como coluna propria (detalhe completo la).
  col.accessor("status", {
    id: "status", header: "Status", size: 168,
    cell: (info) => {
      const row = info.row.original
      const s = info.getValue<StatusConciliacaoBoleto>()
      const dias = s === "enviado_nao_confirmado" ? diasAguardando(row.enviado_em) : null
      const cabeBaixa = situacaoTituloCabeBaixa(row.situacao_titulo)
      return (
        <span className="flex items-center gap-1.5">
          <span className={cx("shrink-0", tableTokens.badge, STATUS_META[s].tone)}>
            {STATUS_BADGE_LABEL[s]}
          </span>
          {dias !== null && (
            <span
              className={cx("shrink-0 text-[11px] font-medium tabular-nums", agingTone(dias))}
              title={`Remessa de registro enviada em ${fmtDateBR(row.enviado_em)} — sem confirmação de entrada do banco há ${dias} dias`}
            >
              {dias}d
            </span>
          )}
          {s === "so_em_banco" && (
            <span
              className={cx(
                "truncate text-[11px]",
                cabeBaixa || row.situacao_titulo === null
                  ? "font-medium text-amber-700 dark:text-amber-400"
                  : "text-gray-500 dark:text-gray-400",
              )}
              title={
                cabeBaixa
                  ? "Título encerrado no sistema com boleto ativo no banco — cabe pedido de baixa"
                  : row.situacao_titulo === null
                    ? "Número de documento sem título correspondente no warehouse"
                    : undefined
              }
            >
              {situacaoTituloLabel(row.situacao_titulo)}
            </span>
          )}
          {row.protesto_tipo && (
            <span
              className="shrink-0"
              title={`Protesto: ${protestoLabel(row.protesto_tipo)} em ${fmtDateBR(row.protesto_em)}`}
            >
              <RiAuctionLine
                className={cx(
                  "size-3",
                  row.protesto_tipo === "protesto_instruido" || row.protesto_tipo === "encaminhado_cartorio"
                    ? "text-red-500"
                    : "text-gray-400 dark:text-gray-500",
                )}
                aria-hidden="true"
              />
            </span>
          )}
        </span>
      )
    },
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  col.accessor("data_operacao", {
    id: "data_operacao", header: "Data operação", size: 104,
    cell: (info) => (
      <span className={cx("tabular-nums", tableTokens.cellSecondary)}>
        {fmtDateBR(info.getValue<string | null>())}
      </span>
    ),
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  col.accessor("numero", {
    id: "numero", header: "Nº documento", size: 120,
    cell: (info) => (
      <span className={cx("block truncate font-mono", tableTokens.cellTextMono)}>
        {info.getValue<string>()}
      </span>
    ),
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  col.accessor("nosso_numero", {
    id: "nosso_numero", header: "Nº no banco", size: 110,
    cell: (info) => {
      const v = info.getValue<string | null>()
      return (
        <span className={cx("block truncate font-mono", tableTokens.cellTextMono)}>
          {v ?? "—"}
        </span>
      )
    },
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  col.accessor("produto", {
    id: "produto", header: "Produto", size: 140,
    // Nome completo do produto (ex.: "Comissária"), nao a sigla. Resolver vem
    // do biMetadata da pagina; fallback pra sigla se o catalogo nao tiver.
    cell: (info) => {
      const nome = produtoNome(info.getValue<string | null>())
      return (
        <span className={cx("block truncate", tableTokens.cellSecondary)} title={nome}>
          {nome}
        </span>
      )
    },
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  col.accessor("banco", {
    id: "banco", header: "Banco", size: 100,
    cell: (info) => {
      const b = info.getValue<string>()
      return <span className={cx("capitalize", tableTokens.cellSecondary)}>{b ?? "—"}</span>
    },
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  col.accessor("cedente_nome", {
    id: "cedente", header: "Cedente", size: 180,
    // MOTIVO: largura fixa + truncate (sem quebra). Nome do cedente pode ser
    // longo; max-w constante mantem a coluna estavel, tooltip mostra o full.
    cell: (info) => {
      const v = info.getValue<string | null>()
      return (
        <span
          className={cx("block max-w-[180px] truncate", tableTokens.cellText)}
          title={v ?? undefined}
        >
          {v ?? "—"}
        </span>
      )
    },
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  // Vencimento/Valor CONSOLIDADOS: BITFIN e banco coincidem em ~99% das linhas
  // (a conciliacao garante). Mostra um so; quando divergem, amber + tooltip com
  // os dois lados (e a coluna Diferença quantifica). CSV exporta os 2 lados.
  col.accessor("venc_bitfin", {
    id: "vencimento", header: "Vencimento", size: 100, meta: { align: "right" },
    cell: (info) => {
      const row = info.row.original
      const diverge =
        row.venc_bitfin !== null && row.venc_banco !== null && row.venc_bitfin !== row.venc_banco
      if (!diverge) return <DateCell value={row.venc_bitfin ?? row.venc_banco} />
      return (
        <div
          className="text-right text-xs font-medium tabular-nums text-amber-600 dark:text-amber-400"
          title={`BITFIN ${fmtDateBR(row.venc_bitfin)} · banco ${fmtDateBR(row.venc_banco)}`}
        >
          {fmtDateBR(row.venc_bitfin)}
        </div>
      )
    },
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  col.accessor("valor_bitfin", {
    id: "valor", header: "Valor", size: 120, meta: { align: "right" },
    cell: (info) => {
      const row = info.row.original
      const diverge =
        row.valor_bitfin !== null && row.valor_banco !== null &&
        Math.abs(row.valor_bitfin - row.valor_banco) >= 0.005
      if (!diverge) return <NumCell value={row.valor_bitfin ?? row.valor_banco} />
      return (
        <div
          className="text-right text-xs font-medium tabular-nums text-amber-600 dark:text-amber-400"
          title={`BITFIN ${fmtBRL.format(row.valor_bitfin ?? 0)} · banco ${fmtBRL.format(row.valor_banco ?? 0)}`}
        >
          {fmtBRL.format(row.valor_bitfin ?? 0)}
        </div>
      )
    },
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  col.display({
    id: "diferenca", header: "Diferença", size: 120, meta: { align: "right" },
    cell: (info) => <DiffCell row={info.row.original} />,
  }) as ColumnDef<LinhaConciliacaoBoleto, unknown>,
  ]
}

function exportarCsv(
  rows: LinhaConciliacaoBoleto[],
  produtoNome: (sigla: string | null) => string,
) {
  const head = [
    "Status", "Titulo no sistema", "Enviado em", "Aguardando (dias)", "Protesto", "Protesto em",
    "Data operacao", "Nro documento", "Nro no banco", "Produto", "Banco", "Cedente",
    "Venc BITFIN", "Venc banco", "Valor BITFIN", "Valor banco", "Dif valor", "Dif dias",
  ]
  const esc = (v: string | number | null | undefined) => {
    const s = v === null || v === undefined ? "" : String(v)
    return /[";\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  // Valor monetario no padrao pt-BR (virgula decimal, sem separador de milhar)
  // para o Excel BR somar. O separador de campo do CSV e ';', entao a virgula
  // decimal nao conflita.
  const csvNum = (v: number | null | undefined) =>
    v === null || v === undefined ? "" : Number(v).toFixed(2).replace(".", ",")
  const corpo = rows.map((r) =>
    [
      STATUS_META[r.status]?.label ?? r.status,  // label longo no CSV
      r.status === "so_em_banco" ? situacaoTituloLabel(r.situacao_titulo) : "",
      r.enviado_em ?? "",
      r.status === "enviado_nao_confirmado" ? diasAguardando(r.enviado_em) ?? "" : "",
      r.protesto_tipo ? protestoLabel(r.protesto_tipo) : "",
      r.protesto_em ?? "",
      r.data_operacao ?? "",
      r.numero, r.nosso_numero ?? "", produtoNome(r.produto), r.banco ?? "", r.cedente_nome ?? "",
      r.venc_bitfin ?? "", r.venc_banco ?? "",
      csvNum(r.valor_bitfin), csvNum(r.valor_banco),
      csvNum(r.diferenca_valor), r.diferenca_dias ?? "",
    ].map(esc).join(";"),
  )
  const csv = [head.join(";"), ...corpo].join("\n")
  const blob = new Blob(["﻿" + csv], { type: "text/csv;charset=utf-8" })
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download = "conciliacao-boletos.csv"
  a.click()
  URL.revokeObjectURL(url)
}

export function ConciliacaoBoletoTable({
  linhas,
  produtoNome,
}: {
  linhas: LinhaConciliacaoBoleto[]
  /** Resolver sigla->nome completo do produto (do biMetadata da pagina). */
  produtoNome: (sigla: string | null) => string
}) {
  // Busca por palavra mora na toolbar (via toolbarStart), alimentando o
  // globalFilter do TanStack — separada dos chips globais da pagina.
  const [busca, setBusca] = React.useState("")

  const columns = React.useMemo(() => makeColumns(produtoNome), [produtoNome])

  return (
    <div className="flex flex-col overflow-hidden rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
      <DataTable
        data={linhas}
        columns={columns}
        density="ultra"
        showColumnManager
        showDensityToggle
        showExport
        globalFilter={busca}
        onExport={(_format, rows) => exportarCsv(rows, produtoNome)}
        toolbarStart={
          <FilterSearch
            placeholder="Buscar número, produto, cedente…"
            value={busca}
            onChange={(e) => setBusca(e.target.value)}
            onClear={() => setBusca("")}
          />
        }
      />
    </div>
  )
}
