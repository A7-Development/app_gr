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
 */

import { RiAlertLine, RiBankCardLine, RiErrorWarningLine, RiFileList3Line } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { useDrillContasAPagar } from "@/lib/hooks/controladoria"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { Button } from "@/components/tremor/Button"
import {
  DrillSectionTitle,
  drillRowBorder,
  drillTableWrap,
  drillThead,
  fmtBRL,
  fmtBRLSigned,
} from "./drillKit"

const TIPO: Record<string, string> = {
  apropriacao: "Apropriou", nova_provisao: "Nova", baixa: "Baixou", quitada: "Quitada",
  estavel: "Estável",
}
const CANAL: Record<string, string> = {
  codigo_proprio: "Débito direto", tarifa_ted: "Tarifa de TED", ted_fornecedor: "TED a fornecedor",
}

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
        <div className={cx("mt-2", drillTableWrap)}>
          <table className="w-full whitespace-nowrap text-[12px] tabular-nums">
            <thead className={drillThead}>
              <tr>
                <th className="px-3 py-1.5 text-left font-medium">Rubrica</th>
                <th className="px-3 py-1.5 text-right font-medium">D-1</th>
                <th className="px-3 py-1.5 text-right font-medium">D0</th>
                <th className="px-3 py-1.5 text-right font-medium">Δ</th>
                <th className="px-3 py-1.5 text-left font-medium">Tipo</th>
              </tr>
            </thead>
            <tbody>
              {d.provisoes.map((p, i) => (
                <tr key={`${p.descricao}-${i}`} className={drillRowBorder}>
                  <td className="max-w-[220px] truncate px-3 py-1.5 text-left text-gray-900 dark:text-gray-100" title={p.descricao}>{p.descricao}</td>
                  <td className="px-3 py-1.5 text-right text-gray-500 dark:text-gray-400">{fmtBRL.format(Math.abs(p.saldo_d1))}</td>
                  <td className="px-3 py-1.5 text-right text-gray-600 dark:text-gray-300">{fmtBRL.format(Math.abs(p.saldo_d0))}</td>
                  <td className={cx("px-3 py-1.5 text-right", p.delta > 0 ? "text-emerald-600 dark:text-emerald-400" : "text-gray-600 dark:text-gray-300")}>{fmtBRLSigned(p.delta)}</td>
                  <td className="px-3 py-1.5 text-left text-gray-500 dark:text-gray-400">{TIPO[p.tipo] ?? p.tipo}</td>
                </tr>
              ))}
            </tbody>
          </table>
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
        {d.pagamentos.length === 0 ? (
          <p className="mt-2 text-[12px] text-gray-500 dark:text-gray-400">Nenhum pagamento de despesa no caixa do dia.</p>
        ) : (
          <div className={cx("mt-2", drillTableWrap)}>
            <table className="w-full whitespace-nowrap text-[12px] tabular-nums">
              <thead className={drillThead}>
                <tr>
                  <th className="px-3 py-1.5 text-left font-medium">Despesa / fornecedor</th>
                  <th className="px-3 py-1.5 text-left font-medium">Canal</th>
                  <th className="px-3 py-1.5 text-right font-medium">Valor</th>
                  <th className="px-3 py-1.5 text-center font-medium">Provisionado?</th>
                </tr>
              </thead>
              <tbody>
                {d.pagamentos.map((p, i) => (
                  <tr key={`${p.historico}-${i}`} className={cx(drillRowBorder, !p.provisionado && "bg-amber-50/40 dark:bg-amber-950/10")}>
                    <td className="max-w-[200px] truncate px-3 py-1.5 text-left text-gray-900 dark:text-gray-100" title={p.contrapartida ?? p.label}>{p.label}</td>
                    <td className="px-3 py-1.5 text-left text-gray-500 dark:text-gray-400">{CANAL[p.canal] ?? p.canal}</td>
                    <td className="px-3 py-1.5 text-right text-gray-900 dark:text-gray-100">{fmtBRL.format(p.valor)}</td>
                    <td className="px-3 py-1.5 text-center">
                      {p.provisionado ? (
                        <span className="text-[11px] text-emerald-600 dark:text-emerald-400">sim</span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[11px] font-medium text-amber-700 dark:text-amber-400">
                          <RiErrorWarningLine className="size-3.5" aria-hidden /> não
                        </span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
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
