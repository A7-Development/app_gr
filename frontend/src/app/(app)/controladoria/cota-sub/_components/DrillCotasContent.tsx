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
 */

import { RiGroupLine, RiHandCoinLine, RiInboxLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { useDrillCotas } from "@/lib/hooks/controladoria"
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
  toneClass,
} from "./drillKit"

const CLASSIF: Record<string, string> = {
  aporte: "Aporte", resgate: "Resgate", apenas_valorizacao: "Só carrego",
}
const TIPO: Record<string, string> = {
  nova: "Nova", aumento: "Aumentou", reducao: "Reduziu", quitada: "Quitada",
}
const ORDEM: Record<string, number> = { senior: 0, mezanino: 1, sub_jr: 2 }

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
  const classes = [...d.classes].sort((a, b) => (ORDEM[a.classe] ?? 9) - (ORDEM[b.classe] ?? 9))

  return (
    <div className="flex flex-col gap-5">
      {/* ── 1. Classes: capital vs carrego ── */}
      <section>
        <DrillSectionTitle
          icon={RiGroupLine}
          label="Cotas — capital vs carrego"
          help="ΔPL de cada classe separado em aporte/resgate (capital) vs remuneração da cota (carrego)."
        />
        <div className={cx("mt-2", drillTableWrap)}>
          <table className="w-full whitespace-nowrap text-[12px] tabular-nums">
            <thead className={drillThead}>
              <tr>
                <th className="px-3 py-1.5 text-left font-medium">Classe</th>
                <th className="px-3 py-1.5 text-right font-medium">Capital</th>
                <th className="px-3 py-1.5 text-right font-medium">Carrego</th>
                <th className="px-3 py-1.5 text-right font-medium">Impacto Sub</th>
                <th className="px-3 py-1.5 text-left font-medium">Tipo</th>
              </tr>
            </thead>
            <tbody>
              {classes.map((c) => (
                <tr key={c.classe} className={drillRowBorder}>
                  <td className="px-3 py-1.5 text-left text-gray-900 dark:text-gray-100">{c.label}</td>
                  <td className="px-3 py-1.5 text-right text-gray-600 dark:text-gray-300">
                    {Math.abs(c.efeito_capital) < 1 ? "—" : fmtBRLSigned(c.efeito_capital)}
                  </td>
                  <td className="px-3 py-1.5 text-right text-gray-600 dark:text-gray-300">{fmtBRLSigned(c.efeito_valorizacao)}</td>
                  <td className={cx("px-3 py-1.5 text-right font-semibold", toneClass(c.impacto_pl_sub))}>{fmtBRLSigned(c.impacto_pl_sub)}</td>
                  <td className="px-3 py-1.5 text-left text-gray-500 dark:text-gray-400">{CLASSIF[c.classificacao] ?? c.classificacao}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-[11px] text-gray-500 dark:text-gray-400">
          Carrego que a Sub paga às prioritárias:{" "}
          <strong className="text-gray-900 dark:text-gray-100">{fmtBRL.format(d.custo_prioritarias_valorizacao)}</strong>
          {Math.abs(d.capital_liquido_prioritarias) >= 1 && (
            <> · Capital líquido (diluiu/concentrou a Sub):{" "}
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
        {d.obrigacoes.length === 0 ? (
          <EmptyState
            className="mt-2"
            icon={RiInboxLine}
            title="Sem obrigações em aberto"
            description="Nenhuma Cota a Resgatar, Aporte ou Resgate no dia."
          />
        ) : (
          <div className={cx("mt-2", drillTableWrap)}>
            <table className="w-full whitespace-nowrap text-[12px] tabular-nums">
              <thead className={drillThead}>
                <tr>
                  <th className="px-3 py-1.5 text-left font-medium">Obrigação</th>
                  <th className="px-3 py-1.5 text-right font-medium">Saldo D-1</th>
                  <th className="px-3 py-1.5 text-right font-medium">Saldo D0</th>
                  <th className="px-3 py-1.5 text-right font-medium">Δ</th>
                  <th className="px-3 py-1.5 text-left font-medium">Tipo</th>
                </tr>
              </thead>
              <tbody>
                {d.obrigacoes.map((o, i) => (
                  <tr key={`${o.descricao}-${i}`} className={drillRowBorder}>
                    <td className="px-3 py-1.5 text-left text-gray-900 dark:text-gray-100">{o.descricao}</td>
                    <td className="px-3 py-1.5 text-right text-gray-500 dark:text-gray-400">{fmtBRL.format(o.saldo_d1)}</td>
                    <td className="px-3 py-1.5 text-right text-gray-600 dark:text-gray-300">{fmtBRL.format(o.saldo_d0)}</td>
                    <td className={cx("px-3 py-1.5 text-right", toneClass(o.delta))}>{fmtBRLSigned(o.delta)}</td>
                    <td className="px-3 py-1.5 text-left text-gray-500 dark:text-gray-400">{TIPO[o.tipo] ?? o.tipo}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
