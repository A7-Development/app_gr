"use client"

/**
 * DrillAplicacoesContent — drill do grupo Aplicacoes do waterfall.
 *
 * Abre os 3 sub-grupos em tabelas canonicas <DataTable> (density ultra),
 * TODAS no mesmo shape e colunas (Fundo/Título | Detalhe | VLR D-1 | VLR D0 |
 * Delta), com total no rodape de cada uma:
 *   1. Fundos DI        (posicao por fundo; detalhe = natureza do movimento)
 *   2. Op. Estruturadas (notas comerciais por papel; detalhe = emitente · venc)
 *   3. Títulos Públicos (TPF por papel; detalhe = vencimento)
 *
 * Per-instrumento vem do /drill/aplicacoes (classificacao TPF/NC = a mesma do
 * balanco, via _driver_for_nome_papel) — reconcilia §14.6.
 */

import { RiBankLine, RiInboxLine, RiLineChartLine, RiStockLine, type RemixiconComponentType } from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import { useDrillAplicacoes } from "@/lib/hooks/controladoria"
import type { AplicacaoInstrumento } from "@/lib/api-client"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { Button } from "@/components/tremor/Button"
import { DrillSectionTitle, fmtBRL, fmtBRLSigned, toneClass } from "./drillKit"

type Props = { fundoId: string; data: string; dataAnterior?: string | null }

// Props compartilhadas das 3 DataTables — ultra, sem toolbar, container bordado
// (mesmo padrao do DrillDcContent).
const DT_PROPS = {
  density:           "ultra",
  virtualize:        false,
  showColumnManager: false,
  showDensityToggle: false,
  showExport:        false,
  className:         "rounded border border-gray-200 dark:border-gray-800",
} as const

// Linha de total no rodape — borda superior destacada.
const FOOT_ROW = "border-t-2 border-t-gray-300 dark:border-t-gray-700"

// ── Colunas canonicas (unico set, reusado nas 3 tabelas) ─────────────────────
// So o header da 1a coluna varia (Fundo / Título); tamanhos + alinhamento +
// tokens sao identicos -> as 3 tabelas ficam absolutamente alinhadas.
const col = createColumnHelper<AplicacaoInstrumento>()

function makeColumns(primeiraColuna: string): ColumnDef<AplicacaoInstrumento, unknown>[] {
  return [
    col.accessor("titulo", {
      id: "titulo", header: primeiraColuna, size: 160,
      cell: (i) => {
        const v = i.getValue<string>()
        return <span className={cx("block truncate", tableTokens.cellText)} title={v}>{v}</span>
      },
    }),
    col.accessor("detalhe", {
      id: "detalhe", header: "Detalhe", size: 190,
      cell: (i) => {
        const v = i.getValue<string>()
        return <span className={cx("block truncate", tableTokens.cellSecondary)} title={v}>{v}</span>
      },
    }),
    col.accessor("valor_d1", {
      id: "valor_d1", header: "VLR D-1", size: 120, meta: { align: "right" },
      cell: (i) => <div className={cx("text-right", tableTokens.cellNumberSecondary)}>{fmtBRL.format(i.getValue<number>())}</div>,
    }),
    col.accessor("valor_d0", {
      id: "valor_d0", header: "VLR D0", size: 120, meta: { align: "right" },
      cell: (i) => <div className={cx("text-right", tableTokens.cellNumber)}>{fmtBRL.format(i.getValue<number>())}</div>,
    }),
    col.accessor("delta", {
      id: "delta", header: "Delta", size: 120, meta: { align: "right" },
      cell: (i) => {
        const v = i.getValue<number>()
        return <div className={cx("text-right text-xs font-semibold tabular-nums", toneClass(v))}>{fmtBRLSigned(v)}</div>
      },
    }),
  ] as ColumnDef<AplicacaoInstrumento, unknown>[]
}

const COLS_FUNDO = makeColumns("Fundo")
const COLS_TITULO = makeColumns("Título")

// Rodape: soma das 3 colunas numericas (reconcilia a tabela com seu sub-grupo).
function renderFooter(itens: AplicacaoInstrumento[]) {
  const s1 = itens.reduce((a, x) => a + x.valor_d1, 0)
  const s0 = itens.reduce((a, x) => a + x.valor_d0, 0)
  const sd = itens.reduce((a, x) => a + x.delta, 0)
  return (
    <tr className={FOOT_ROW}>
      <td colSpan={2} className="px-3"><span className={tableTokens.cellStrong}>Total ({itens.length})</span></td>
      <td className="px-3"><div className={cx("text-right tabular-nums", tableTokens.cellNumberSecondary)}>{fmtBRL.format(s1)}</div></td>
      <td className="px-3"><div className={cx("text-right tabular-nums", tableTokens.cellStrong)}>{fmtBRL.format(s0)}</div></td>
      <td className="px-3"><div className={cx("text-right text-xs font-semibold tabular-nums", toneClass(sd))}>{fmtBRLSigned(sd)}</div></td>
    </tr>
  )
}

function TabelaSubgrupo({
  icon, label, help, columns, itens, emptyTitle,
}: {
  icon: RemixiconComponentType
  label: string
  help: string
  columns: ColumnDef<AplicacaoInstrumento, unknown>[]
  itens: AplicacaoInstrumento[]
  emptyTitle: string
}) {
  return (
    <section>
      <DrillSectionTitle icon={icon} label={label} help={help} />
      {itens.length === 0 ? (
        <EmptyState className="mt-2" icon={RiInboxLine} title={emptyTitle} description="Nenhuma posição no dia." />
      ) : (
        <div className="mt-2">
          <DataTable<AplicacaoInstrumento> {...DT_PROPS} columns={columns} data={itens} renderFooter={renderFooter} />
        </div>
      )}
    </section>
  )
}

export function DrillAplicacoesContent({ fundoId, data, dataAnterior }: Props) {
  const q = useDrillAplicacoes(fundoId, data, dataAnterior)

  if (q.isError) {
    return (
      <ErrorState
        title="Falha ao carregar drill de Aplicações"
        description={(q.error as Error)?.message ?? "Erro desconhecido"}
        action={<Button variant="secondary" onClick={() => q.refetch()}>Tentar de novo</Button>}
      />
    )
  }
  if (q.isLoading || !q.data) {
    return (
      <div className="flex animate-pulse flex-col gap-2">
        {[0, 1, 2].map((i) => <div key={i} className="h-8 rounded bg-gray-100 dark:bg-gray-900" />)}
      </div>
    )
  }
  const d = q.data

  // Fundos DI -> shape canonico. Detalhe = natureza do movimento do dia.
  const fundosItens: AplicacaoInstrumento[] = d.fundos_di.map((f) => ({
    titulo:   f.fundo_nome,
    detalhe:  f.tipo === "so_valorizacao" ? "rendimento" : f.tipo === "aplicacao" ? "aplicação" : "resgate",
    valor_d1: f.valor_d1,
    valor_d0: f.valor_d0,
    delta:    f.delta_valor,
  }))

  return (
    <div className="flex flex-col gap-5">
      <TabelaSubgrupo
        icon={RiBankLine}
        label="Fundos DI"
        help="Caixa ocioso estacionado em fundos DI. ΔSaldo = rendimento do dia + aplicação/resgate de capital."
        columns={COLS_FUNDO}
        itens={fundosItens}
        emptyTitle="Sem fundos DI"
      />
      <TabelaSubgrupo
        icon={RiLineChartLine}
        label="Op. Estruturadas"
        help="Notas comerciais (carrego do dia + entradas/baixas). Posição a mercado por papel."
        columns={COLS_TITULO}
        itens={d.op_estruturadas_itens}
        emptyTitle="Sem notas comerciais"
      />
      <TabelaSubgrupo
        icon={RiStockLine}
        label="Títulos Públicos"
        help="Tesouro (NTN/LTN/LFT) a mercado. Marcação do dia por papel."
        columns={COLS_TITULO}
        itens={d.titulos_publicos_itens}
        emptyTitle="Sem títulos públicos"
      />
    </div>
  )
}
