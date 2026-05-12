"use client"

/**
 * AnaliseVariacaoCard — narrativa das variacoes do dia.
 *
 * Shell que vai abrigar os explainers heuristicos das variacoes patrimoniais.
 * Quatro categorias canonicas (mapeadas com Ricardo em 2026-05-12):
 *
 *   1. Fluxo de caixa do cotista — aporte/resgate da Cota Sub
 *      Fontes: wh_mec_evolucao_cotas + wh_cpr_movimento (linha de resgate +
 *      IRRF a pagar quando ha saque)
 *
 *   2. Movimento de carteira — liquidacao / aquisicao de papeis
 *      Fontes: Singulare /fidc-custodia/report/liquidados-baixados +
 *      /aquisicao-consolidada (adapter novo pendente)
 *
 *   3. Eventos contabeis — PDD, diferimento, apropriacao de despesas
 *      Fontes: wh_qitech_estoque (valor_pdd + faixa_pdd) e
 *      wh_cpr_movimento (descricao com "Diferimento")
 *
 *   4. Marcacao a mercado — papel com qtde delta=0 e valor delta != 0
 *      Fontes: cruzamento direto wh_posicao_renda_fixa D-1 vs D0
 *
 * Hoje: shell vazio listando as categorias com status "em construcao".
 * Plano: cada heuristico vira uma funcao pura
 * `(balancete, balancete_anterior) -> Explanation | null` em
 * `_lib/explainers/<categoria>.ts`, chamadas em ordem e listadas aqui
 * com narrative + evidencias.
 */

import {
  RiBankCardLine,
  RiBriefcaseLine,
  RiFileList3Line,
  RiLineChartLine,
} from "@remixicon/react"
import type { ComponentType } from "react"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import type { BalanceteResponse } from "@/lib/api-client"

type Categoria = {
  id:          string
  icon:        ComponentType<{ className?: string }>
  iconCls:     string
  dotCls:      string
  titulo:      string
  descricao:   string
}

const CATEGORIAS: readonly Categoria[] = [
  {
    id:        "fluxo_caixa",
    icon:      RiBankCardLine,
    iconCls:   "text-emerald-600 dark:text-emerald-400",
    dotCls:    "bg-emerald-500",
    titulo:    "Fluxo de caixa do cotista",
    descricao: "Aporte ou resgate da Cota Subordinada no dia.",
  },
  {
    id:        "movimento_carteira",
    icon:      RiBriefcaseLine,
    iconCls:   "text-blue-600 dark:text-blue-400",
    dotCls:    "bg-blue-500",
    titulo:    "Movimento de carteira",
    descricao: "Liquidacao e aquisicao de papeis no dia.",
  },
  {
    id:        "eventos_contabeis",
    icon:      RiFileList3Line,
    iconCls:   "text-violet-600 dark:text-violet-400",
    dotCls:    "bg-violet-500",
    titulo:    "Eventos contabeis",
    descricao: "Constituicao de PDD, diferimento e apropriacao de despesas.",
  },
  {
    id:        "marcacao_mercado",
    icon:      RiLineChartLine,
    iconCls:   "text-amber-600 dark:text-amber-400",
    dotCls:    "bg-amber-500",
    titulo:    "Marcacao a mercado",
    descricao: "Variacao tecnica de papeis sem movimento de quantidade.",
  },
]

export type AnaliseVariacaoCardProps = {
  /** Balancete do dia — passado pra plugar os explainers depois. Ainda nao
   *  consumido (shell). */
  balancete?: BalanceteResponse
  /** Override do titulo do card. */
  title?: string
}

export function AnaliseVariacaoCard({
  // balancete  — sera usado quando os explainers heuristicos forem ligados
  title = "Analise da variacao do dia",
}: AnaliseVariacaoCardProps) {
  return (
    <Card className="flex h-full flex-col gap-3 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm text-gray-900 dark:text-gray-50">{title}</h3>
        <span
          className={cx(
            "rounded-full border px-1.5 text-[11px]",
            "border-gray-200 bg-gray-50 text-gray-500",
            "dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400",
          )}
        >
          shell · em construcao
        </span>
      </div>

      <ul className="flex flex-1 flex-col divide-y divide-gray-100 dark:divide-gray-800">
        {CATEGORIAS.map((c) => {
          const Icon = c.icon
          return (
            <li
              key={c.id}
              className="flex items-start gap-3 py-3 first:pt-0 last:pb-0"
            >
              <span
                className={cx(
                  "mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded",
                  "bg-gray-50 dark:bg-gray-900/60",
                )}
              >
                <Icon className={cx("h-4 w-4", c.iconCls)} aria-hidden="true" />
              </span>
              <div className="flex min-w-0 flex-1 flex-col gap-0.5">
                <div className="flex items-center gap-2">
                  <span
                    className={cx(
                      "inline-block h-1.5 w-1.5 shrink-0 rounded-full",
                      c.dotCls,
                    )}
                    aria-hidden="true"
                  />
                  <span className="text-[13px] font-medium text-gray-900 dark:text-gray-50">
                    {c.titulo}
                  </span>
                </div>
                <p className="text-[12px] text-gray-500 dark:text-gray-400">
                  {c.descricao}
                </p>
                <p
                  className={cx(
                    "mt-1 text-[11px] italic",
                    "text-gray-400 dark:text-gray-600",
                  )}
                >
                  » Em construcao
                </p>
              </div>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}
