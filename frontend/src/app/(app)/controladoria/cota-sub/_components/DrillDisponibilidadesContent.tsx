"use client"

/**
 * DrillDisponibilidadesContent — drill do grupo Disponibilidades (caixa).
 *
 * A barra do waterfall e o RENDIMENTO LIQUIDO de caixa (pequeno = o unico
 * componente que afeta a cota). O caixa real mexe muito por GIRO/CAPITAL
 * (compra de carteira, aplicacao DI, aporte, floating, quitacao de despesa) —
 * tudo NEUTRO. Este drill mostra os dois lados.
 *
 * Sem endpoint proprio: os fluxos neutros ja vem em response.giro_capital
 * (do /variacao/resumo), passados por prop — sao o espelho do caixa.
 *
 * Tabela no mesmo estilo canonico das de Aplicacoes (DataTable ultra, bordada,
 * total no rodape). Colunas proprias (Movimento | Tipo | Valor) — esses
 * movimentos sao neutros, nao tem D-1/D0 nem impacto por linha (§14).
 */

import { RiArrowLeftRightLine, RiPulseLine } from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import type { GiroCapitalItem } from "@/lib/api-client"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"
import { DrillSectionTitle, fmtBRLSigned } from "./drillKit"

const TIPO_LABEL: Record<GiroCapitalItem["tipo"], string> = {
  giro_carteira:     "Giro de carteira",
  capital_cotista:   "Capital de cotista",
  capital_aplicacao: "Aplicação/resgate",
  floating:          "Floating",
  outros:            "Outros",
}

// Mesmo estilo canonico das tabelas de Aplicacoes — ultra, sem toolbar, bordada.
const DT_PROPS = {
  density:           "ultra",
  virtualize:        false,
  showColumnManager: false,
  showDensityToggle: false,
  showExport:        false,
  className:         "rounded border border-gray-200 dark:border-gray-800",
} as const

const FOOT_ROW = "border-t-2 border-t-gray-300 dark:border-t-gray-700"

const col = createColumnHelper<GiroCapitalItem>()
const COLS: ColumnDef<GiroCapitalItem, unknown>[] = [
  col.accessor("label", {
    id: "label", header: "Movimento", size: 220,
    cell: (i) => {
      const v = i.getValue<string>()
      return <span className={cx("block truncate", tableTokens.cellText)} title={i.row.original.nota || v}>{v}</span>
    },
  }),
  col.accessor("tipo", {
    id: "tipo", header: "Tipo", size: 160,
    cell: (i) => (
      <span className={cx("block truncate", tableTokens.cellSecondary)}>
        {TIPO_LABEL[i.getValue<GiroCapitalItem["tipo"]>()] ?? i.getValue<string>()}
      </span>
    ),
  }),
  col.accessor("valor", {
    id: "valor", header: "Valor", size: 140, meta: { align: "right" },
    cell: (i) => <div className={cx("text-right tabular-nums", tableTokens.cellNumberSecondary)}>{fmtBRLSigned(i.getValue<number>())}</div>,
  }),
] as ColumnDef<GiroCapitalItem, unknown>[]

type Props = { rendimento: number; giroCapital: GiroCapitalItem[] }

export function DrillDisponibilidadesContent({ rendimento, giroCapital }: Props) {
  const totalNeutro = giroCapital.reduce((s, g) => s + Math.abs(g.valor), 0)

  return (
    <div className="flex flex-col gap-5">
      {/* Rendimento = o que afeta a cota */}
      <div className="flex items-start gap-2 rounded border border-blue-200 bg-blue-50/50 px-3 py-2 dark:border-blue-900/60 dark:bg-blue-950/20">
        <RiPulseLine className="mt-0.5 size-4 shrink-0 text-blue-600 dark:text-blue-400" aria-hidden />
        <div className="flex flex-col">
          <span className="text-[12px] font-medium text-blue-800 dark:text-blue-300">
            Rendimento líquido de caixa: {fmtBRLSigned(rendimento)}
          </span>
          <span className="text-[11px] text-gray-600 dark:text-gray-400">
            É o único componente do caixa que afeta a cota. Tesouraria e conta corrente rendem pouco;
            todo o resto é movimentação neutra (entra e sai espelhado em outra linha).
          </span>
        </div>
      </div>

      {/* Movimentacoes neutras (o espelho do caixa) */}
      <section>
        <DrillSectionTitle
          icon={RiArrowLeftRightLine}
          label="Movimentações neutras de caixa"
          counter={totalNeutro >= 1 ? `movimentou ${fmtBRLSigned(totalNeutro)}` : undefined}
          help="O caixa entra/sai por compra de carteira, aplicação, aporte e floating — tudo espelhado em outra linha do balanço (impacto 0 na cota)."
        />
        {giroCapital.length === 0 ? (
          <p className="mt-2 text-[12px] text-gray-500 dark:text-gray-400">
            Sem movimentação neutra relevante no dia — o caixa praticamente só rendeu.
          </p>
        ) : (
          <div className="mt-2">
            <DataTable<GiroCapitalItem>
              {...DT_PROPS}
              columns={COLS}
              data={giroCapital}
              renderFooter={() => (
                <tr className={FOOT_ROW}>
                  <td colSpan={2} className="px-3"><span className={tableTokens.cellStrong}>Total ({giroCapital.length})</span></td>
                  <td className="px-3"><div className={cx("text-right tabular-nums", tableTokens.cellNumberSecondary)}>{fmtBRLSigned(totalNeutro)}</div></td>
                </tr>
              )}
            />
          </div>
        )}
        <p className="mt-2 text-[11px] text-gray-500 dark:text-gray-400">
          Esses valores não entram no waterfall — são transferências (caixa ↔ carteira / cotista / despesa).
          Só o rendimento acima afeta a cota.
        </p>
      </section>
    </div>
  )
}
