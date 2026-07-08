"use client"

/**
 * DrillContasAPagarContent — drill COMPLETO da linha Contas a Pagar.
 *
 * Substitui o drill antigo (so provisao/CPR<0). Usa a tool do Auditor de Contas
 * a Pagar, que tem a HISTORIA INTEIRA:
 *   0. IMPACTO no PL Sub — a despesa paga ALEM da provisao (o R$15k do 28/05).
 *   1. Provisoes (CPR<0) — apropriacao (accrual) vs baixa (paga/estornada).
 *   2. Pagamentos do caixa — por codigo do extrato, com flag de provisionado.
 *   3. Fora de escopo — capital de cotista que nao e despesa (sinalizado).
 *
 * 2026-05-29: a tabela "Pagamentos do caixa" migrou do `<table>` artesanal para
 * a DataTable canonica `density="ultra"` (h-7/28px) — regra dura de consistencia
 * dos drills da Cota Sub. Sem corte (lista TODOS os pagamentos do dia).
 */

import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import { RiAlertLine, RiBankCardLine, RiErrorWarningLine, RiFileList3Line } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { useDrillContasAPagar } from "@/lib/hooks/controladoria"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { Button } from "@/components/tremor/Button"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"
import {
  DrillSectionTitle,
  fmtBRL,
} from "./drillKit"
import { DrillImpactoTable, makeImpactoColumns } from "./DrillImpactoTable"

const TIPO: Record<string, string> = {
  apropriacao: "Apropriou", nova_provisao: "Nova", baixa: "Baixou", quitada: "Quitada",
  estavel: "Estável",
}

// Mesma estrutura da tabela "Aplicações · impacto na cota".
const PROVISOES_COLS = makeImpactoColumns({ nome: "Rubrica", d1: "D-1", d0: "D0", impacto: "Δ" })
const CANAL: Record<string, string> = {
  codigo_proprio: "Débito direto", tarifa_ted: "Tarifa de TED", ted_fornecedor: "TED a fornecedor",
}

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

// Linha de pagamento de caixa (linha-a-linha do extrato classificada por canal).
type PagamentoRow = {
  label:         string
  contrapartida: string | null
  canal:         string
  valor:         number
  provisionado:  boolean
  historico:     string
}

const pagCol = createColumnHelper<PagamentoRow>()

const PAGAMENTOS_COLUMNS: ColumnDef<PagamentoRow, unknown>[] = [
  pagCol.accessor("label", {
    id: "label", header: "Despesa / fornecedor", size: 220,
    cell: (info) => (
      <span className={cx("block max-w-[200px] truncate", tableTokens.cellText)} title={info.row.original.contrapartida ?? info.getValue<string>()}>
        {info.getValue<string>()}
      </span>
    ),
  }) as ColumnDef<PagamentoRow, unknown>,
  pagCol.accessor("canal", {
    id: "canal", header: "Canal", size: 150,
    cell: (info) => (
      <span className={cx("block truncate", tableTokens.cellSecondary)}>{CANAL[info.getValue<string>()] ?? info.getValue<string>()}</span>
    ),
  }) as ColumnDef<PagamentoRow, unknown>,
  pagCol.accessor("valor", {
    id: "valor", header: "Valor", size: 120, meta: { align: "right" },
    cell: (info) => <div className={cx("text-right", tableTokens.cellNumber)}>{fmtBRL.format(info.getValue<number>())}</div>,
  }) as ColumnDef<PagamentoRow, unknown>,
  pagCol.accessor("provisionado", {
    id: "provisionado", header: "Provisionado?", size: 120, meta: { align: "center" },
    cell: (info) => (
      <div className="text-center">
        {info.getValue<boolean>() ? (
          <span className={tableTokens.badgeSuccess}>sim</span>
        ) : (
          <span className={tableTokens.badgeWarning}>
            <RiErrorWarningLine className="size-3.5" aria-hidden /> não
          </span>
        )}
      </div>
    ),
  }) as ColumnDef<PagamentoRow, unknown>,
]

type Props = { fundoId: string; data: string; dataAnterior?: string | null }

export function DrillContasAPagarContent({ fundoId, data, dataAnterior }: Props) {
  const q = useDrillContasAPagar(fundoId, data, dataAnterior)

  if (q.isError) {
    return (
      <ErrorState
        title="Falha ao carregar Contas a Pagar"
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
  const temImpacto = d.impacto_resultado_nao_provisionado >= 1
  const pagamentos: PagamentoRow[] = d.pagamentos.map((p) => ({
    label:         p.label,
    contrapartida: p.contrapartida ?? null,
    canal:         p.canal,
    valor:         p.valor,
    provisionado:  p.provisionado,
    historico:     p.historico,
  }))

  return (
    <div className="flex flex-col gap-5">
      {/* ── 0. Impacto no PL Sub (o que faltava) ── */}
      {temImpacto && (
        <div className="rounded-lg border border-amber-200 bg-amber-50/60 p-3 dark:border-amber-900/50 dark:bg-amber-950/20">
          <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.04em] text-amber-800 dark:text-amber-300">
            <RiAlertLine className="size-4" aria-hidden />
            Impacto no PL Sub — despesa paga além da provisão
          </div>
          <div className="mt-1 text-lg font-semibold tabular-nums text-amber-900 dark:text-amber-200">
            −{fmtBRL.format(d.impacto_resultado_nao_provisionado)}
          </div>
          <p className="mt-1 text-[12px] text-amber-800/90 dark:text-amber-300/80">
            Pagou <strong>{fmtBRL.format(d.total_pago)}</strong> de despesa, mas só
            {" "}<strong>{fmtBRL.format(d.total_baixa)}</strong> tinha provisão pra baixar.
            O excesso (+ tarifas) saiu de caixa sem um passivo pra liberar, então
            bateu direto no resultado da cota Sub neste dia.
          </p>
        </div>
      )}

      {/* ── 1. Provisoes (CPR<0) ── */}
      <section>
        <DrillSectionTitle
          icon={RiFileList3Line}
          label="Provisões de despesa"
          counter={`apropriou ${fmtBRL.format(d.total_apropriacao)} · baixou ${fmtBRL.format(d.total_baixa)}`}
          help="Accrual de taxa (apropriacao) vs provisao que saiu (baixa/quitada). CPR<0."
        />
        <div className="mt-2">
          <DrillImpactoTable
            columns={PROVISOES_COLS}
            itens={d.provisoes.map((p) => ({
              nome:     p.descricao,
              detalhe:  TIPO[p.tipo] ?? p.tipo,
              valor_d1: Math.abs(p.saldo_d1),
              valor_d0: Math.abs(p.saldo_d0),
              impacto:  p.delta,
            }))}
          />
        </div>
      </section>

      {/* ── 2. Pagamentos do caixa (o que o drill antigo nao mostrava) ── */}
      <section>
        <DrillSectionTitle
          icon={RiBankCardLine}
          label="Pagamentos do caixa"
          counter={`Σ pago ${fmtBRL.format(d.total_pago)}`}
          help="Debitos de despesa do extrato classificados por codigo. provisionado=False -> saiu sem provisao."
          tone={d.total_nao_provisionado >= 1 ? "alert" : "neutral"}
        />
        {pagamentos.length === 0 ? (
          <p className="mt-2 text-[12px] text-gray-500 dark:text-gray-400">Nenhum pagamento de despesa no caixa do dia.</p>
        ) : (
          <div className="mt-2">
            <DataTable<PagamentoRow>
              {...DT_PROPS}
              data={pagamentos}
              columns={PAGAMENTOS_COLUMNS}
              rowClassName={(r) => cx(!r.provisionado && "bg-amber-50/40 dark:bg-amber-950/10")}
              renderFooter={() => (
                <tr className={FOOT_ROW}>
                  <td colSpan={2} className="px-3"><span className={tableTokens.cellStrong}>Σ pago · {pagamentos.length} pagamento(s)</span></td>
                  <td className="px-3"><div className={cx("text-right", tableTokens.cellStrong)}>{fmtBRL.format(d.total_pago)}</div></td>
                  <td className="px-3" />
                </tr>
              )}
            />
          </div>
        )}
      </section>

      {/* ── 3. Fora de escopo (capital de cotista, sinalizado) ── */}
      {d.fora_escopo.length > 0 && (
        <section>
          <DrillSectionTitle
            icon={RiAlertLine}
            label="Fora do escopo de despesa"
            help="Itens CPR<0 que NAO sao despesa (capital de cotista) — pertencem a outro auditor."
            tone="alert"
          />
          <div className="mt-2 flex flex-col gap-1">
            {d.fora_escopo.map((f, i) => (
              <div key={i} className="flex items-center justify-between rounded border border-amber-200 px-3 py-1.5 text-[12px] dark:border-amber-900/40">
                <span className="text-gray-700 dark:text-gray-300">{f.descricao} <span className="text-gray-400">({f.natureza} → {f.dono})</span></span>
                <span className="tabular-nums text-gray-900 dark:text-gray-100">{fmtBRL.format(Math.abs(f.saldo_d0))}</span>
              </div>
            ))}
          </div>
        </section>
      )}

      {d.provisoes.length === 0 && d.pagamentos.length === 0 && !temImpacto && (
        <EmptyState icon={RiFileList3Line} title="Sem movimento em Contas a Pagar" description="Nenhuma provisão ou pagamento de despesa no dia." />
      )}
    </div>
  )
}
