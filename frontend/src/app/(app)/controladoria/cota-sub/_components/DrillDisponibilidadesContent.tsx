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
 */

import { RiArrowLeftRightLine, RiPulseLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import type { GiroCapitalItem } from "@/lib/api-client"
import {
  DrillSectionTitle,
  drillRowBorder,
  drillTableWrap,
  drillThead,
  fmtBRLSigned,
} from "./drillKit"

const TIPO_LABEL: Record<GiroCapitalItem["tipo"], string> = {
  giro_carteira:     "Giro de carteira",
  capital_cotista:   "Capital de cotista",
  capital_aplicacao: "Aplicação/resgate",
  floating:          "Floating",
  outros:            "Outros",
}

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
          <div className={cx("mt-2", drillTableWrap)}>
            <table className="w-full whitespace-nowrap text-[12px] tabular-nums">
              <thead className={drillThead}>
                <tr>
                  <th className="px-3 py-1.5 text-left font-medium">Movimento</th>
                  <th className="px-3 py-1.5 text-left font-medium">Tipo</th>
                  <th className="px-3 py-1.5 text-right font-medium">Valor</th>
                </tr>
              </thead>
              <tbody>
                {giroCapital.map((g, i) => (
                  <tr key={`${g.tipo}-${i}`} className={drillRowBorder}>
                    <td className="px-3 py-1.5 text-left text-gray-900 dark:text-gray-100">{g.label}</td>
                    <td className="px-3 py-1.5 text-left text-gray-500 dark:text-gray-400">{TIPO_LABEL[g.tipo] ?? g.tipo}</td>
                    <td className="px-3 py-1.5 text-right text-gray-500 dark:text-gray-400">{fmtBRLSigned(g.valor)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
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
