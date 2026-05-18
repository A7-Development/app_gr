"use client"

/**
 * AnaliseVariacaoCard — narrativa das variacoes do dia.
 *
 * Abriga os explainers heuristicos das variacoes patrimoniais. Cinco
 * categorias canonicas (split de "eventos_contabeis" em 2 buckets em
 * 2026-05-17 — PDD merece visualizacao propria):
 *
 *   1. PDD — provisao de credito (rose, alerta de risco)
 *      Fonte: diff wh_estoque_recebivel.valor_pdd
 *      Status: **entregue 2026-05-13 (categoria 3.2)**
 *
 *   2. Ajustes contabeis — diferimento + apropriacao de despesas (violet)
 *      Fontes: CPR `Diferimento de despesa%` + `Apropriacao%`
 *      Status: em construcao
 *
 *   3. Fluxo de caixa do cotista — aporte/resgate (emerald)
 *      Fonte: CPR `Aporte` + cruzamento com MEC (Δquantidade por classe)
 *      Status: em construcao
 *
 *   4. Movimento de carteira — liquidacao / aquisicao de papeis (blue)
 *      Fontes: diff wh_estoque_recebivel D-1 vs D0 + CPR `LIQUIDADOS TOTAL - PROV`
 *      Status: em construcao
 *
 *   5. Marcacao a mercado — papel com qtde delta=0 e valor delta != 0 (amber)
 *      Fonte: cruzamento direto wh_posicao_renda_fixa D-1 vs D0
 *      Status: em construcao
 *
 * Plano completo: backend/docs/cota-sub-explainers-heuristicos.md.
 * Endpoint: GET /controladoria/cota-sub/explicacao
 */

import {
  RiBankCardLine,
  RiBriefcaseLine,
  RiFileList3Line,
  RiLineChartLine,
  RiShieldCheckLine,
  RiStackLine,
} from "@remixicon/react"
import type { ComponentType } from "react"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import { useExplicacaoVariacao } from "@/lib/hooks/controladoria"
import type { BalanceteResponse, PddExplanation } from "@/lib/api-client"

import { PddEvidenciaTable } from "./PddEvidenciaTable"

// ─── Formatadores ────────────────────────────────────────────────────────────

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style:                  "currency",
  currency:               "BRL",
  minimumFractionDigits:  2,
  maximumFractionDigits:  2,
})

// ─── Categorias (5, fixas) ───────────────────────────────────────────────────

type Categoria = {
  id:          "pdd" | "ajustes_contabeis" | "fluxo_caixa" | "movimento_carteira" | "marcacao_mercado" | "remuneracao_sr_mez"
  icon:        ComponentType<{ className?: string }>
  iconCls:     string
  dotCls:      string
  titulo:      string
  descricao:   string
}

const CATEGORIAS: readonly Categoria[] = [
  {
    id:        "pdd",
    icon:      RiShieldCheckLine,
    iconCls:   "text-rose-600 dark:text-rose-400",
    dotCls:    "bg-rose-500",
    titulo:    "PDD (provisao de credito)",
    descricao: "Constituicao ou reversao de provisao por mudanca de faixa de credito.",
  },
  {
    id:        "ajustes_contabeis",
    icon:      RiFileList3Line,
    iconCls:   "text-violet-600 dark:text-violet-400",
    dotCls:    "bg-violet-500",
    titulo:    "Ajustes contabeis",
    descricao: "Diferimento e apropriacao de despesas — natureza temporal.",
  },
  {
    id:        "fluxo_caixa",
    icon:      RiBankCardLine,
    iconCls:   "text-emerald-600 dark:text-emerald-400",
    dotCls:    "bg-emerald-500",
    titulo:    "Aporte e resgate de cotistas",
    descricao: "Aporte ou resgate em Sub, Mez ou Sr. Sub absorve direto; Mez/Sr afetam via equity.",
  },
  {
    id:        "movimento_carteira",
    icon:      RiBriefcaseLine,
    iconCls:   "text-blue-600 dark:text-blue-400",
    dotCls:    "bg-blue-500",
    titulo:    "Movimento de carteira",
    descricao: "Giro da carteira de DC. Bucket informacional — movimento patrimonial neutro no Sub.",
  },
  {
    id:        "marcacao_mercado",
    icon:      RiLineChartLine,
    iconCls:   "text-amber-600 dark:text-amber-400",
    dotCls:    "bg-amber-500",
    titulo:    "Marcacao a mercado",
    descricao: "Papeis de renda fixa com qtd estavel - PU mexeu pela curva do dia. Sub absorve direto.",
  },
  {
    id:        "remuneracao_sr_mez",
    icon:      RiStackLine,
    iconCls:   "text-rose-600 dark:text-rose-400",
    dotCls:    "bg-rose-500",
    titulo:    "Remuneracao Sr/Mez",
    descricao: "Custo de subordinacao. Cotas Sr e Mez valorizam pela curva, Sub absorve com sinal invertido.",
  },
]

// ─── Props ───────────────────────────────────────────────────────────────────

export type AnaliseVariacaoCardProps = {
  balancete?: BalanceteResponse
  title?:     string
}

// ─── Componente ──────────────────────────────────────────────────────────────

export function AnaliseVariacaoCard({
  balancete,
  title = "Analise da variacao do dia",
}: AnaliseVariacaoCardProps) {
  const fundoId = balancete?.fundo_id ?? null
  const dataD0  = balancete?.data_d_zero ?? null
  const dataD1  = balancete?.data_d_minus_1 ?? null

  const explicacao = useExplicacaoVariacao(
    fundoId,
    dataD0,
    { dataAnterior: dataD1 },
  )

  const pdd: PddExplanation | undefined = explicacao.data?.explanations.find(
    (e) => e.categoria === "pdd",
  )

  return (
    <Card className="flex h-full flex-col gap-3 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm text-gray-900 dark:text-gray-50">{title}</h3>
        {explicacao.isLoading && (
          <span className="text-[11px] text-gray-400">carregando…</span>
        )}
        {explicacao.isError && (
          <span className="text-[11px] text-red-500">erro ao carregar</span>
        )}
      </div>

      <ul className="flex flex-1 flex-col divide-y divide-gray-100 dark:divide-gray-800">
        {CATEGORIAS.map((c) => {
          const Icon = c.icon
          const isPdd = c.id === "pdd"
          const hasPdd = isPdd && pdd && pdd.evidencias_total > 0
          return (
            <li
              key={c.id}
              className="flex flex-col py-3 first:pt-0 last:pb-0"
            >
              <div className="flex items-start gap-3">
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
                    {hasPdd && (
                      <span
                        className={cx(
                          "ml-auto rounded px-1.5 py-0.5 text-[11px] font-medium tabular-nums",
                          pdd!.delta_brl < 0
                            ? "bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300"
                            : "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300",
                        )}
                      >
                        {pdd!.delta_brl > 0 ? "+" : ""}
                        {fmtBRL.format(pdd!.delta_brl)}
                      </span>
                    )}
                  </div>
                  <p className="text-[12px] text-gray-500 dark:text-gray-400">
                    {hasPdd ? pdd!.narrative : c.descricao}
                  </p>
                  {!hasPdd && (
                    <p
                      className={cx(
                        "mt-1 text-[11px] italic",
                        "text-gray-400 dark:text-gray-600",
                      )}
                    >
                      » Em construcao
                    </p>
                  )}
                </div>
              </div>
              {hasPdd && (
                <div className="mt-2">
                  <PddEvidenciaTable
                    evidencias={pdd!.evidencias}
                    evidenciasTotal={pdd!.evidencias_total}
                    evidenciasMostradas={pdd!.evidencias_mostradas}
                    outrosDeltaBrl={pdd!.outros_delta_brl}
                  />
                </div>
              )}
            </li>
          )
        })}
      </ul>
    </Card>
  )
}
