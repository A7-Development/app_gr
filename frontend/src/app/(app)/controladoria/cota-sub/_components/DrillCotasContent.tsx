"use client"

/**
 * DrillCotasContent — conteudo do drill das linhas de Cota/Passivo de cotista
 * (Senior, Mezanino, Obrigacoes com Cotistas). Detalhe do Auditor de Cotas.
 *
 * 2 secoes:
 *   1. Classes (Sr/Mez/Sub) — ΔPL separado em CAPITAL (aporte/resgate) vs
 *      VALORIZACAO (carrego que a Sub paga).
 *   2. Obrigacoes com Cotistas — Cotas a Resgatar / Aporte / Resgate (CPR).
 *
 * Reusa a mesma tool do agente `controladoria.auditor_cotas`
 * (compute_movimento_cotas) via /drill/cotas.
 *
 * 2026-05-29: a tabela "Obrigações com cotistas" migrou do `<table>` artesanal
 * para a DataTable canonica `density="ultra"` (h-7/28px) — regra dura de
 * consistencia dos drills da Cota Sub. Sem corte (lista TODAS as obrigacoes).
 */

import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import { RiGroupLine, RiHandCoinLine, RiInboxLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { useDrillCotas } from "@/lib/hooks/controladoria"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { Button } from "@/components/tremor/Button"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"
import {
  DrillSectionTitle,
  fmtBRL,
  fmtBRLSigned,
  toneClass,
} from "./drillKit"
import { DrillImpactoTable, makeImpactoColumns } from "./DrillImpactoTable"

const CLASSIF: Record<string, string> = {
  aporte: "Aporte", resgate: "Resgate", apenas_valorizacao: "Só carrego",
}
const TIPO: Record<string, string> = {
  nova: "Nova", aumento: "Aumentou", reducao: "Reduziu", quitada: "Quitada",
}
const ORDEM: Record<string, number> = { senior: 0, mezanino: 1, sub_jr: 2 }

// Mesma estrutura da tabela "Aplicações · impacto na cota".
const COTAS_COLS = makeImpactoColumns({
  nome: "Classe", d1: "Patrim. D-1", d0: "Patrim. D0", impacto: "Impacto Sub",
})

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

// Linha de obrigacao com cotista (Cotas a Resgatar / Aporte / Resgate no CPR).
type ObrigacaoRow = {
  descricao: string
  saldo_d1:  number
  saldo_d0:  number
  delta:     number
  tipo:      string
}

const obrCol = createColumnHelper<ObrigacaoRow>()

const OBRIGACOES_COLUMNS: ColumnDef<ObrigacaoRow, unknown>[] = [
  obrCol.accessor("descricao", {
    id: "descricao", header: "Obrigação", size: 220,
    cell: (info) => (
      <span className={cx("block truncate", tableTokens.cellText)} title={info.getValue<string>()}>{info.getValue<string>()}</span>
    ),
  }) as ColumnDef<ObrigacaoRow, unknown>,
  obrCol.accessor("saldo_d1", {
    id: "saldo_d1", header: "Saldo D-1", size: 120, meta: { align: "right" },
    cell: (info) => <div className={cx("text-right", tableTokens.cellNumberSecondary)}>{fmtBRL.format(info.getValue<number>())}</div>,
  }) as ColumnDef<ObrigacaoRow, unknown>,
  obrCol.accessor("saldo_d0", {
    id: "saldo_d0", header: "Saldo D0", size: 120, meta: { align: "right" },
    cell: (info) => <div className={cx("text-right", tableTokens.cellNumber)}>{fmtBRL.format(info.getValue<number>())}</div>,
  }) as ColumnDef<ObrigacaoRow, unknown>,
  obrCol.accessor("delta", {
    id: "delta", header: "Δ", size: 110, meta: { align: "right" },
    cell: (info) => <div className={cx("text-right text-xs font-semibold tabular-nums", toneClass(info.getValue<number>()))}>{fmtBRLSigned(info.getValue<number>())}</div>,
  }) as ColumnDef<ObrigacaoRow, unknown>,
  obrCol.accessor("tipo", {
    id: "tipo", header: "Tipo", size: 110,
    cell: (info) => <span className={cx("block truncate", tableTokens.cellSecondary)}>{TIPO[info.getValue<string>()] ?? info.getValue<string>()}</span>,
  }) as ColumnDef<ObrigacaoRow, unknown>,
]

type Props = { fundoId: string; data: string; dataAnterior?: string | null }

export function DrillCotasContent({ fundoId, data, dataAnterior }: Props) {
  const q = useDrillCotas(fundoId, data, dataAnterior)

  if (q.isError) {
    return (
      <ErrorState
        title="Falha ao carregar drill de Cotas"
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
  // Esta tabela explica as PRIORITARIAS (passivo que compoe a Sub). A propria
  // Sub Jr e o residual que a pagina calcula — mostra-la aqui como "carrego
  // positivo" nao faz sentido (seria circular). Filtra fora.
  const classes = [...d.classes]
    .filter((c) => c.classe !== "sub_jr")
    .sort((a, b) => (ORDEM[a.classe] ?? 9) - (ORDEM[b.classe] ?? 9))

  const obrigacoes: ObrigacaoRow[] = d.obrigacoes.map((o) => ({
    descricao: o.descricao,
    saldo_d1:  o.saldo_d1,
    saldo_d0:  o.saldo_d0,
    delta:     o.delta,
    tipo:      o.tipo,
  }))

  return (
    <div className="flex flex-col gap-5">
      {/* ── 1. Classes: capital vs carrego ── */}
      <section>
        <DrillSectionTitle
          icon={RiGroupLine}
          label="Cotas — capital vs carrego"
          help="ΔPL de cada classe separado em aporte/resgate (capital) vs remuneração da cota (carrego)."
        />
        <div className="mt-2">
          <DrillImpactoTable
            columns={COTAS_COLS}
            itens={classes.map((c) => {
              const classif = CLASSIF[c.classificacao] ?? c.classificacao
              return {
                nome:     c.label,
                // capital e neutro no PL Sub — fica no detalhe (carrego = Impacto).
                detalhe:  Math.abs(c.efeito_capital) >= 1
                  ? `${classif} · capital ${fmtBRLSigned(c.efeito_capital)}`
                  : classif,
                valor_d1: c.patrimonio_d1,
                valor_d0: c.patrimonio_d0,
                impacto:  c.impacto_pl_sub,
              }
            })}
          />
        </div>
        <p className="mt-2 text-[11px] text-gray-500 dark:text-gray-400">
          Carrego que a Sub paga às prioritárias:{" "}
          <strong className="text-gray-900 dark:text-gray-100">{fmtBRL.format(d.custo_prioritarias_valorizacao)}</strong>
          {Math.abs(d.capital_liquido_prioritarias) >= 1 && (
            <> · Capital líquido das prioritárias (aporte/resgate — neutro no PL Sub):{" "}
              <strong className="text-gray-900 dark:text-gray-100">{fmtBRLSigned(d.capital_liquido_prioritarias)}</strong>
            </>
          )}
        </p>
      </section>

      {/* ── 2. Obrigacoes com cotistas ── */}
      <section>
        <DrillSectionTitle
          icon={RiHandCoinLine}
          label="Obrigações com cotistas"
          counter={`saldo ${fmtBRL.format(d.obrigacoes_saldo_d0)}`}
          help="Cotas a Resgatar, Aporte e Resgate — capital de cotista no CPR (não é despesa)."
        />
        {obrigacoes.length === 0 ? (
          <EmptyState
            className="mt-2"
            icon={RiInboxLine}
            title="Sem obrigações em aberto"
            description="Nenhuma Cota a Resgatar, Aporte ou Resgate no dia."
          />
        ) : (
          <div className="mt-2">
            <DataTable<ObrigacaoRow>
              {...DT_PROPS}
              data={obrigacoes}
              columns={OBRIGACOES_COLUMNS}
              renderFooter={() => {
                const s1 = obrigacoes.reduce((a, x) => a + x.saldo_d1, 0)
                const sd = obrigacoes.reduce((a, x) => a + x.delta, 0)
                return (
                  <tr className={FOOT_ROW}>
                    <td className="px-3"><span className={tableTokens.cellStrong}>Total · {obrigacoes.length} obrigação(ões)</span></td>
                    <td className="px-3"><div className={cx("text-right", tableTokens.cellNumberSecondary)}>{fmtBRL.format(s1)}</div></td>
                    <td className="px-3"><div className={cx("text-right", tableTokens.cellStrong)}>{fmtBRL.format(d.obrigacoes_saldo_d0)}</div></td>
                    <td className="px-3"><div className={cx("text-right text-xs font-semibold tabular-nums", toneClass(sd))}>{fmtBRLSigned(sd)}</div></td>
                    <td className="px-3" />
                  </tr>
                )
              }}
            />
          </div>
        )}
      </section>
    </div>
  )
}
