"use client"

/**
 * DrillDcContent — conteudo do drill da categoria DC (Direitos Creditorios).
 *
 * Renderiza dentro do CategoriaDrillSheet 3 secoes:
 *   1. Apropriacao derivada (formula explicita ΔEstoque + Liquidacoes − Aquisicoes)
 *   2. Liquidacoes por tipo_movimento (agregado)
 *   3. Aquisicoes do dia (lista — top N visiveis)
 */

import * as React from "react"
import {
  RiCalculatorLine,
  RiArrowRightDownLine,
  RiArrowRightUpLine,
  RiPlayLine,
  RiInboxLine,
  type RemixiconComponentType,
} from "@remixicon/react"

import { cx } from "@/lib/utils"
import { useDrillDc } from "@/lib/hooks/controladoria"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { Button } from "@/components/tremor/Button"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style:                 "currency",
  currency:              "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const fmtBRLSigned = (v: number): string => {
  if (Math.abs(v) < 0.005) return "R$ 0,00"
  const sign = v > 0 ? "+" : "−"
  return `${sign}${fmtBRL.format(Math.abs(v))}`
}

const fmtPct = (v: number, base: number): string => {
  if (Math.abs(base) < 0.005) return "—"
  return `${((v / base) * 100).toFixed(2).replace(".", ",")}%`
}

export type DrillDcContentProps = {
  fundoId:        string
  data:           string
  dataAnterior?:  string
}

export function DrillDcContent({ fundoId, data, dataAnterior }: DrillDcContentProps) {
  const q = useDrillDc(fundoId, data, dataAnterior)
  const [aquisicoesExpanded, setAquisicoesExpanded] = React.useState(false)
  const AQUISICOES_PREVIEW = 8

  if (q.isError) {
    return (
      <ErrorState
        title="Falha ao carregar drill DC"
        description={(q.error as Error)?.message ?? "Erro desconhecido"}
        action={<Button onClick={() => q.refetch()}>Tentar novamente</Button>}
      />
    )
  }

  if (q.isLoading || !q.data) {
    return (
      <div className="flex h-40 items-center justify-center text-[12px] text-gray-500 dark:text-gray-400">
        Carregando drill DC…
      </div>
    )
  }

  const d = q.data
  const a = d.apropriacao
  const aquisicoesVisiveis = aquisicoesExpanded ? d.aquisicoes : d.aquisicoes.slice(0, AQUISICOES_PREVIEW)
  const totalAquisicoes = d.aquisicoes.length

  return (
    <div className="flex flex-col gap-5">
      {/* ── Apropriacao derivada ── */}
      <section>
        <SectionTitle icon={RiCalculatorLine} label="Apropriação derivada" />
        <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
          Apropriação = Δ Estoque + Liquidações − Aquisições. Em dia típico positivo
          (juros + valorização). Negativo sinaliza mutação silenciosa em titulo
          (taxa ou nominal).
        </p>
        <div className="mt-3 overflow-hidden rounded border border-gray-200 dark:border-gray-800">
          <FormulaRow
            label="Estoque consolidado"
            d1={a.estoque_d1}
            d0={a.estoque_d0}
            delta={a.delta_estoque}
            isFirst
          />
          <FormulaRow
            label="+ Liquidações (saída do estoque)"
            singleValue={a.liquidacoes_total}
            indent
          />
          <FormulaRow
            label="− Aquisições (entrada no estoque)"
            singleValue={-a.aquisicoes_total}
            indent
          />
          <FormulaRow
            label="= Apropriação"
            singleValue={a.apropriacao}
            highlight
          />
        </div>
      </section>

      {/* ── Liquidações por tipo ── */}
      <section>
        <SectionTitle
          icon={RiArrowRightUpLine}
          label="Liquidações por tipo"
          counter={`${d.liquidacoes_qtd} título(s) · ${fmtBRL.format(d.liquidacoes_total)}`}
        />
        {d.liquidacoes_por_tipo.length === 0 ? (
          <EmptyState
            icon={RiInboxLine}
            title="Sem liquidações no dia"
            description="Nenhum recebível foi liquidado entre D-1 e D0."
            className="mt-2"
          />
        ) : (
          <div className="mt-2 overflow-hidden rounded border border-gray-200 dark:border-gray-800">
            <table className="w-full text-[12px] tabular-nums">
              <thead className="bg-gray-50 text-[10px] font-medium uppercase tracking-[0.04em] text-gray-500 dark:bg-gray-900/30 dark:text-gray-400">
                <tr>
                  <th className="px-3 py-1.5 text-left">Tipo</th>
                  <th className="px-3 py-1.5 text-right">Qtd</th>
                  <th className="px-3 py-1.5 text-right">Σ valor pago</th>
                  <th className="px-3 py-1.5 text-right">Σ aquisição</th>
                  <th className="px-3 py-1.5 text-right">Ganho líquido</th>
                  <th className="px-3 py-1.5 text-right">%</th>
                </tr>
              </thead>
              <tbody>
                {d.liquidacoes_por_tipo.map((t) => (
                  <tr key={t.tipo_movimento} className="border-t border-gray-100 dark:border-gray-900">
                    <td className="px-3 py-1.5 text-gray-700 dark:text-gray-200">{t.tipo_movimento}</td>
                    <td className="px-3 py-1.5 text-right text-gray-600 dark:text-gray-400">{t.qtd_papeis}</td>
                    <td className="px-3 py-1.5 text-right text-gray-900 dark:text-gray-50">{fmtBRL.format(t.sum_valor_pago)}</td>
                    <td className="px-3 py-1.5 text-right text-gray-500 dark:text-gray-400">{fmtBRL.format(t.sum_valor_aquisicao)}</td>
                    <td className={cx(
                      "px-3 py-1.5 text-right font-medium",
                      t.ganho_liquido > 0
                        ? "text-emerald-700 dark:text-emerald-400"
                        : t.ganho_liquido < 0
                        ? "text-red-700 dark:text-red-400"
                        : "text-gray-400 dark:text-gray-600",
                    )}>{fmtBRLSigned(t.ganho_liquido)}</td>
                    <td className="px-3 py-1.5 text-right text-[10px] text-gray-400 dark:text-gray-600">
                      {fmtPct(t.sum_valor_pago, d.liquidacoes_total)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── Aquisições do dia ── */}
      <section>
        <SectionTitle
          icon={RiArrowRightDownLine}
          label="Aquisições do dia"
          counter={`${totalAquisicoes} título(s) · ${fmtBRL.format(d.aquisicoes_total)}`}
        />
        {totalAquisicoes === 0 ? (
          <EmptyState
            icon={RiInboxLine}
            title="Sem aquisições no dia"
            description="Nenhum recebível novo entrou na carteira em D0."
            className="mt-2"
          />
        ) : (
          <>
            <div className="mt-2 overflow-hidden rounded border border-gray-200 dark:border-gray-800">
              <table className="w-full text-[12px] tabular-nums">
                <thead className="bg-gray-50 text-[10px] font-medium uppercase tracking-[0.04em] text-gray-500 dark:bg-gray-900/30 dark:text-gray-400">
                  <tr>
                    <th className="px-3 py-1.5 text-left">Cedente</th>
                    <th className="px-3 py-1.5 text-left">Sacado</th>
                    <th className="px-3 py-1.5 text-left">Título</th>
                    <th className="px-3 py-1.5 text-right">Valor compra</th>
                    <th className="px-3 py-1.5 text-right">Valor venc.</th>
                    <th className="px-3 py-1.5 text-right">Prazo</th>
                  </tr>
                </thead>
                <tbody>
                  {aquisicoesVisiveis.map((aq) => (
                    <tr key={`${aq.cedente_doc}-${aq.seu_numero}-${aq.numero_documento}`} className="border-t border-gray-100 dark:border-gray-900">
                      <td className="px-3 py-1.5 text-gray-700 dark:text-gray-200" title={aq.cedente_doc}>
                        <span className="truncate block max-w-[160px]">{aq.cedente_nome}</span>
                      </td>
                      <td className="px-3 py-1.5 text-gray-700 dark:text-gray-200" title={aq.sacado_doc}>
                        <span className="truncate block max-w-[160px]">{aq.sacado_nome}</span>
                      </td>
                      <td className="px-3 py-1.5 font-mono text-[11px] text-gray-500 dark:text-gray-400" title={aq.numero_documento}>
                        {aq.seu_numero}
                      </td>
                      <td className="px-3 py-1.5 text-right text-gray-900 dark:text-gray-50">{fmtBRL.format(aq.valor_compra)}</td>
                      <td className="px-3 py-1.5 text-right text-gray-500 dark:text-gray-400">{fmtBRL.format(aq.valor_vencimento)}</td>
                      <td className="px-3 py-1.5 text-right text-[11px] text-gray-400 dark:text-gray-600">{aq.prazo_recebivel}d</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {totalAquisicoes > AQUISICOES_PREVIEW && (
              <button
                type="button"
                onClick={() => setAquisicoesExpanded((v) => !v)}
                className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-blue-700 hover:text-blue-800 dark:text-blue-300 dark:hover:text-blue-200"
              >
                <RiPlayLine className={cx("size-3 transition-transform", aquisicoesExpanded && "rotate-90")} aria-hidden="true" />
                {aquisicoesExpanded
                  ? `Mostrar apenas as ${AQUISICOES_PREVIEW} primeiras`
                  : `Mostrar todas as ${totalAquisicoes} aquisições`}
              </button>
            )}
          </>
        )}
      </section>
    </div>
  )
}

function SectionTitle({
  icon: Icon, label, counter,
}: {
  icon: RemixiconComponentType
  label: string
  counter?: string
}) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <h4 className="flex items-center gap-1.5 text-[12px] font-semibold uppercase tracking-[0.04em] text-gray-700 dark:text-gray-300">
        <Icon className="size-3.5 text-gray-400 dark:text-gray-500" aria-hidden />
        {label}
      </h4>
      {counter && (
        <span className="text-[11px] text-gray-500 dark:text-gray-400 tabular-nums">{counter}</span>
      )}
    </div>
  )
}

function FormulaRow({
  label, d1, d0, delta, singleValue, indent, highlight, isFirst,
}: {
  label:        string
  d1?:          number
  d0?:          number
  delta?:       number
  singleValue?: number
  indent?:      boolean
  highlight?:   boolean
  isFirst?:     boolean
}) {
  return (
    <div className={cx(
      "grid grid-cols-[1fr_120px_120px_120px] items-center gap-2 px-3 py-1.5 text-[12px] tabular-nums",
      !isFirst && "border-t border-gray-100 dark:border-gray-900",
      highlight && "border-t-gray-300 bg-blue-50/40 dark:border-t-gray-700 dark:bg-blue-950/10",
      indent && "pl-6",
    )}>
      <span className={cx(
        "truncate",
        highlight
          ? "font-semibold text-gray-900 dark:text-gray-50"
          : "text-gray-700 dark:text-gray-200",
      )}>{label}</span>
      {d1 !== undefined ? (
        <span className="text-right text-gray-500 dark:text-gray-400">{fmtBRL.format(d1)}</span>
      ) : <span />}
      {d0 !== undefined ? (
        <span className={cx(
          "text-right",
          highlight ? "font-bold text-gray-900 dark:text-gray-50" : "text-gray-900 dark:text-gray-50",
        )}>{fmtBRL.format(d0)}</span>
      ) : <span />}
      {(delta !== undefined || singleValue !== undefined) ? (
        <span className={cx(
          "text-right",
          highlight && "font-bold text-blue-700 dark:text-blue-300",
          !highlight && (delta ?? singleValue ?? 0) > 0 && "text-emerald-700 dark:text-emerald-400",
          !highlight && (delta ?? singleValue ?? 0) < 0 && "text-red-700 dark:text-red-400",
          !highlight && (delta ?? singleValue ?? 0) === 0 && "text-gray-400 dark:text-gray-600",
        )}>
          {fmtBRLSigned(delta ?? singleValue ?? 0)}
        </span>
      ) : <span />}
    </div>
  )
}
