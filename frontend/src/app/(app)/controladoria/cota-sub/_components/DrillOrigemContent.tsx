"use client"

/**
 * DrillOrigemContent — drill "ver origem" das 9 linhas SEM drill rico
 * (RF/Op.Estruturadas/Fundos DI/Compromissada/Outros Ativos/Tesouraria/
 * Conta Corrente/Cota Senior/Cota Mezanino).
 *
 * Lista as linhas-fonte (snapshot D0) que compoem o valor da linha do balanco
 * e prova o fechamento: Σ(linhas) == valor_balanco. O selo verde/vermelho e a
 * conferenciabilidade (§14) — cada numero rastreavel ate o dado-fonte.
 *
 * 2026-05-29: tabela migrada do `<table>` artesanal para a DataTable canonica
 * `density="ultra"` (h-7/28px) — regra dura de consistencia dos drills da
 * Cota Sub. Total via `renderFooter`; nenhum corte (mostra TODAS as linhas).
 */

import * as React from "react"
import { RiInboxLine, RiStackLine } from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import { useDrillOrigem } from "@/lib/hooks/controladoria"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { Button } from "@/components/tremor/Button"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"
import {
  DrillClosureBadge,
  DrillSectionTitle,
  fmtBRL,
  fmtBRLSigned,
} from "./drillKit"

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

// Linha de total no rodape (renderFooter) — borda superior destacada.
const FOOT_ROW = "border-t-2 border-t-gray-300 dark:border-t-gray-700"

type LinhaFonteRow = {
  identificador: string
  descricao:     string
  detalhe:       string | null
  valor:         number
}

export type DrillOrigemContentProps = {
  fundoId: string
  data:    string
  linha:   string
}

export function DrillOrigemContent({ fundoId, data, linha }: DrillOrigemContentProps) {
  const q = useDrillOrigem(fundoId, data, linha)

  const columns: ColumnDef<LinhaFonteRow, unknown>[] = React.useMemo(() => {
    const hasDetalhe = q.data?.linhas.some((l) => !!l.detalhe) ?? false
    const col = createColumnHelper<LinhaFonteRow>()
    const cols: ColumnDef<LinhaFonteRow, unknown>[] = [
      col.accessor("identificador", {
        id: "identificador", header: "Identificador", size: 160,
        cell: (info) => (
          <span className={cx("block max-w-[140px] truncate font-mono", tableTokens.cellTextMono)} title={info.getValue<string>()}>
            {info.getValue<string>()}
          </span>
        ),
      }) as ColumnDef<LinhaFonteRow, unknown>,
      col.accessor("descricao", {
        id: "descricao", header: "Descrição", size: 280,
        cell: (info) => (
          <span className={cx("block max-w-[260px] truncate", tableTokens.cellText)} title={info.getValue<string>()}>
            {info.getValue<string>()}
          </span>
        ),
      }) as ColumnDef<LinhaFonteRow, unknown>,
    ]
    if (hasDetalhe) {
      cols.push(
        col.accessor("detalhe", {
          id: "detalhe", header: "Detalhe", size: 160,
          cell: (info) => (
            <span className={cx("block truncate font-mono", tableTokens.cellSecondary)}>
              {info.getValue<string | null>() ?? "—"}
            </span>
          ),
        }) as ColumnDef<LinhaFonteRow, unknown>,
      )
    }
    cols.push(
      col.accessor("valor", {
        id: "valor", header: "Valor", size: 140, meta: { align: "right" },
        cell: (info) => (
          <div className={cx("text-right", tableTokens.cellNumber)}>{fmtBRL.format(info.getValue<number>())}</div>
        ),
      }) as ColumnDef<LinhaFonteRow, unknown>,
    )
    return cols
  }, [q.data])

  if (q.isError) {
    return (
      <ErrorState
        title="Falha ao carregar origem"
        description={(q.error as Error)?.message ?? "Erro desconhecido"}
        action={<Button onClick={() => q.refetch()}>Tentar novamente</Button>}
      />
    )
  }

  if (q.isLoading || !q.data) {
    return (
      <div className="flex h-40 items-center justify-center text-[12px] text-gray-500 dark:text-gray-400">
        Carregando origem…
      </div>
    )
  }

  const d = q.data
  const hasDetalhe = d.linhas.some((l) => !!l.detalhe)
  const rows: LinhaFonteRow[] = d.linhas.map((ln) => ({
    identificador: ln.identificador,
    descricao:     ln.descricao,
    detalhe:       ln.detalhe ?? null,
    valor:         ln.valor,
  }))

  return (
    <div className="flex flex-col gap-4">
      {/* ── Selo de fechamento ── */}
      <DrillClosureBadge
        fecha={d.fecha}
        sub={!d.fecha ? `balanço ${fmtBRL.format(d.valor_balanco)} · soma ${fmtBRL.format(d.soma)}` : undefined}
      >
        {d.fecha
          ? `Fecha · ${d.linhas.length} linha(s)-fonte somam ${fmtBRL.format(d.valor_balanco)}`
          : `Diverge ${fmtBRLSigned(d.diferenca)} · soma das linhas ≠ valor do balanço`}
      </DrillClosureBadge>

      {/* ── Linhas-fonte ── */}
      <section>
        <DrillSectionTitle
          icon={RiStackLine}
          label="Linhas-fonte"
          counter={<span className="font-mono">{d.fonte}</span>}
        />

        {d.linhas.length === 0 ? (
          <EmptyState
            icon={RiInboxLine}
            title="Sem linhas-fonte nesta data"
            description="A linha está zerada em D0 — nenhum registro na tabela de origem."
            className="mt-2"
          />
        ) : (
          <div className="mt-2">
            <DataTable<LinhaFonteRow>
              {...DT_PROPS}
              data={rows}
              columns={columns}
              renderFooter={() => (
                <tr className={FOOT_ROW}>
                  <td colSpan={hasDetalhe ? 3 : 2} className="px-3"><span className={tableTokens.cellStrong}>Total</span></td>
                  <td className="px-3"><div className={cx("text-right", tableTokens.cellStrong)}>{fmtBRL.format(d.soma)}</div></td>
                </tr>
              )}
            />
          </div>
        )}
      </section>
    </div>
  )
}
