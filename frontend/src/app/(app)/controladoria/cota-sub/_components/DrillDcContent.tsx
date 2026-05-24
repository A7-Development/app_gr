"use client"

/**
 * DrillDcContent — conteudo do drill da categoria DC (Direitos Creditorios).
 *
 * F3 redesign 2026-05-24: substitui o bloco "Apropriacao derivada" pela
 * **decomposicao em 5 buckets** calculada do granular `wh_estoque_recebivel`
 * (ver backend Fase 2). Identidade contabil fecha por construcao -- mutacao
 * silenciosa (ex-F5) vira RESULTADO NATURAL da decomposicao.
 *
 * Estrutura:
 *   1. Composicao do estoque (5 buckets + Estoque D-1 + Estoque D0 + Residuo)
 *   2. Mutacao silenciosa (papeis com mudanca de parametro, se houver)
 *   3. Migracao WOP (papeis que viraram WOP, se houver)
 *   4. Liquidacoes por tipo (agregado)
 *   5. Aquisicoes do dia (lista — top N visiveis)
 */

import * as React from "react"
import {
  RiCalculatorLine,
  RiArrowRightDownLine,
  RiArrowRightUpLine,
  RiPlayLine,
  RiInboxLine,
  RiAlertLine,
  RiArchive2Line,
  type RemixiconComponentType,
} from "@remixicon/react"

import { cx } from "@/lib/utils"
import { useDrillDc } from "@/lib/hooks/controladoria"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { Button } from "@/components/tremor/Button"
import type { DrillDcDecomposicao, DrillDcMutacaoPapel, DrillDcMigracaoWopPapel } from "@/lib/api-client"

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

const fmtTaxa = (v: number): string => {
  // taxa_recebivel vem decimal (0,4692739943 = 0,47% ao mes)
  return `${(v * 100).toFixed(4).replace(".", ",")}%`
}

const fmtDateBR = (iso: string | null): string => {
  if (!iso) return "—"
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[3]}/${m[2]}/${m[1].slice(2)}` : iso
}

// Limite acima do qual o Residuo da decomposicao vira alerta.
// < R$ 0,50 = arredondamento contabil aceitavel; > = sinal de pipeline.
const RESIDUO_OK_BRL = 0.5

export type DrillDcContentProps = {
  fundoId:        string
  data:           string
  dataAnterior?:  string
}

export function DrillDcContent({ fundoId, data, dataAnterior }: DrillDcContentProps) {
  const q = useDrillDc(fundoId, data, dataAnterior)
  const [aquisicoesExpanded, setAquisicoesExpanded] = React.useState(false)
  const [mutacaoExpanded, setMutacaoExpanded] = React.useState(false)
  const AQUISICOES_PREVIEW = 8
  const MUTACAO_PREVIEW = 5

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
  const dec = d.decomposicao
  const aquisicoesVisiveis = aquisicoesExpanded ? d.aquisicoes : d.aquisicoes.slice(0, AQUISICOES_PREVIEW)
  const totalAquisicoes = d.aquisicoes.length
  const mutacaoVisivel = mutacaoExpanded ? d.mutacao_papeis : d.mutacao_papeis.slice(0, MUTACAO_PREVIEW)

  return (
    <div className="flex flex-col gap-5">
      {/* ── 1. Decomposicao do estoque ── */}
      <section>
        <SectionTitle
          icon={RiCalculatorLine}
          label="Composição do estoque"
          help="Σ Valor Presente dos recebíveis em estoque (exclui WOP)"
        />
        <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
          ΔDC explicado linha-a-linha pelo granular. Identidade contábil fecha
          por construção — resíduo &gt; R$ 0,50 sinaliza desalinhamento de pipeline.
        </p>
        <div className="mt-3 overflow-hidden rounded border border-gray-200 dark:border-gray-800">
          <DecomposicaoRow label="Estoque (D-1)" value={dec.saldo_d1} isAnchor isFirst />
          <DecomposicaoRow
            label="+ Aquisições"
            counter={`${dec.aquisicoes_n} título${dec.aquisicoes_n === 1 ? "" : "s"} novo${dec.aquisicoes_n === 1 ? "" : "s"}`}
            value={dec.aquisicoes_total}
            sign="+"
          />
          <DecomposicaoRow
            label="− Liquidações"
            counter={`${dec.liquidacoes_n} título${dec.liquidacoes_n === 1 ? "" : "s"} baixado${dec.liquidacoes_n === 1 ? "" : "s"}`}
            value={-dec.liquidacoes_total}
            sign="−"
          />
          <DecomposicaoRow
            label="− Migração WOP"
            counter={`${dec.migracao_wop_n} título${dec.migracao_wop_n === 1 ? "" : "s"} ${dec.migracao_wop_n === 1 ? "migrou" : "migraram"}`}
            value={-dec.migracao_wop_total}
            sign="−"
            muted={dec.migracao_wop_n === 0}
          />
          <DecomposicaoRow
            label="+ Apropriação de juros"
            counter={`${dec.apropriacao_n} papéis na carteira`}
            value={dec.apropriacao_total}
            sign="+"
          />
          <DecomposicaoRow
            label="+ Mutação silenciosa"
            counter={`${dec.mutacao_n} papel${dec.mutacao_n === 1 ? "" : "is"} com mudança de parâmetro`}
            value={dec.mutacao_total}
            sign="+"
            muted={dec.mutacao_n === 0}
            highlightAlert={dec.mutacao_n > 0}
          />
          <DecomposicaoRow label="= Estoque (D0)" value={dec.saldo_d0} isAnchor highlight />
          <ResiduoRow value={dec.residuo} />
        </div>
      </section>

      {/* ── 2. Detalhe Mutacao silenciosa (so se houver) ── */}
      {d.mutacao_papeis.length > 0 && (
        <section>
          <SectionTitle
            icon={RiAlertLine}
            label="Papéis com mutação silenciosa"
            counter={`${d.mutacao_papeis.length} papel${d.mutacao_papeis.length === 1 ? "" : "is"}`}
            tone="alert"
          />
          <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
            Papéis presentes nos dois dias com mudança em valor nominal, taxa
            ou vencimento entre D-1 e D0 — sem evento de liquidação ou aquisição
            correspondente.
          </p>
          <div className="mt-2 overflow-hidden rounded border border-amber-200 dark:border-amber-900/40">
            <table className="w-full text-[12px] tabular-nums">
              <thead className="bg-amber-50 text-[10px] font-medium uppercase tracking-[0.04em] text-amber-800 dark:bg-amber-950/30 dark:text-amber-300">
                <tr>
                  <th className="px-3 py-1.5 text-left">Cedente → Sacado</th>
                  <th className="px-3 py-1.5 text-left">Título</th>
                  <th className="px-3 py-1.5 text-right">VP D-1</th>
                  <th className="px-3 py-1.5 text-right">VP D0</th>
                  <th className="px-3 py-1.5 text-right">Δ VP</th>
                  <th className="px-3 py-1.5 text-left">Mudou</th>
                </tr>
              </thead>
              <tbody>
                {mutacaoVisivel.map((p) => (
                  <MutacaoRow key={`${p.cedente_doc}-${p.seu_numero}-${p.numero_documento}`} p={p} />
                ))}
              </tbody>
            </table>
            {d.mutacao_papeis.length > MUTACAO_PREVIEW && (
              <div className="border-t border-amber-200 px-3 py-1.5 dark:border-amber-900/40">
                <button
                  type="button"
                  onClick={() => setMutacaoExpanded((v) => !v)}
                  className="inline-flex items-center gap-1 text-[11px] font-medium text-amber-800 hover:text-amber-900 dark:text-amber-300 dark:hover:text-amber-200"
                >
                  <RiPlayLine className={cx("size-3 transition-transform", mutacaoExpanded && "rotate-90")} aria-hidden="true" />
                  {mutacaoExpanded
                    ? `Mostrar apenas os ${MUTACAO_PREVIEW} primeiros`
                    : `Mostrar todos os ${d.mutacao_papeis.length} papéis`}
                </button>
              </div>
            )}
          </div>
        </section>
      )}

      {/* ── 3. Detalhe Migracao WOP (so se houver) ── */}
      {d.migracao_wop_papeis.length > 0 && (
        <section>
          <SectionTitle
            icon={RiArchive2Line}
            label="Papéis que migraram para WOP"
            counter={`${d.migracao_wop_papeis.length} papel${d.migracao_wop_papeis.length === 1 ? "" : "is"}`}
          />
          <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
            Saem da DC (VP zera no estoque ex-WOP) e simultaneamente saem da
            PDD — efeito líquido no PL Sub Jr é zero.
          </p>
          <div className="mt-2 overflow-hidden rounded border border-gray-200 dark:border-gray-800">
            <table className="w-full text-[12px] tabular-nums">
              <thead className="bg-gray-50 text-[10px] font-medium uppercase tracking-[0.04em] text-gray-500 dark:bg-gray-900/30 dark:text-gray-400">
                <tr>
                  <th className="px-3 py-1.5 text-left">Cedente → Sacado</th>
                  <th className="px-3 py-1.5 text-left">Título</th>
                  <th className="px-3 py-1.5 text-center">Faixa D-1</th>
                  <th className="px-3 py-1.5 text-right">VP D-1</th>
                  <th className="px-3 py-1.5 text-right">PDD D-1</th>
                </tr>
              </thead>
              <tbody>
                {d.migracao_wop_papeis.map((p) => (
                  <MigracaoWopRow key={`${p.cedente_doc}-${p.seu_numero}-${p.numero_documento}`} p={p} />
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* ── 4. Liquidações por tipo ── */}
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

      {/* ── 5. Aquisições do dia ── */}
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

// ─── Sub-componentes ────────────────────────────────────────────────────────

function SectionTitle({
  icon: Icon, label, counter, help, tone = "neutral",
}: {
  icon:    RemixiconComponentType
  label:   string
  counter?: string
  help?:    string
  tone?:    "neutral" | "alert"
}) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <h4 className={cx(
        "flex items-center gap-1.5 text-[12px] font-semibold uppercase tracking-[0.04em]",
        tone === "alert"
          ? "text-amber-800 dark:text-amber-300"
          : "text-gray-700 dark:text-gray-300",
      )}>
        <Icon
          className={cx(
            "size-3.5",
            tone === "alert"
              ? "text-amber-600 dark:text-amber-400"
              : "text-gray-400 dark:text-gray-500",
          )}
          aria-hidden
        />
        {label}
        {help && (
          <span
            className="cursor-help text-[10px] font-normal normal-case tracking-normal text-gray-400 dark:text-gray-600"
            title={help}
          >
            (?)
          </span>
        )}
      </h4>
      {counter && (
        <span className="text-[11px] text-gray-500 dark:text-gray-400 tabular-nums">{counter}</span>
      )}
    </div>
  )
}

function DecomposicaoRow({
  label, value, counter, sign, isAnchor, isFirst, highlight, muted, highlightAlert,
}: {
  label:           string
  value:           number
  counter?:        string
  sign?:           "+" | "−"
  isAnchor?:       boolean  // saldo D-1 ou D0 (sem +/-)
  isFirst?:        boolean
  highlight?:      boolean  // saldo D0
  muted?:          boolean  // bucket vazio
  highlightAlert?: boolean  // bucket Mutacao com valor != 0
}) {
  const isZero = Math.abs(value) < 0.005
  const isPositive = value > 0
  const isNegative = value < 0

  return (
    <div className={cx(
      "grid grid-cols-[1fr_auto_140px] items-center gap-2 px-3 py-1.5 text-[12px] tabular-nums",
      !isFirst && "border-t border-gray-100 dark:border-gray-900",
      highlight && "border-t-gray-300 bg-blue-50/40 dark:border-t-gray-700 dark:bg-blue-950/10",
      highlightAlert && "bg-amber-50/40 dark:bg-amber-950/10",
      muted && "opacity-50",
    )}>
      <span className={cx(
        "truncate",
        isAnchor
          ? "font-semibold text-gray-900 dark:text-gray-50"
          : "text-gray-700 dark:text-gray-200",
      )}>{label}</span>
      <span className="whitespace-nowrap text-[10px] text-gray-400 dark:text-gray-600">
        {counter ?? ""}
      </span>
      <span className={cx(
        "text-right",
        isAnchor && (highlight
          ? "font-bold text-gray-900 dark:text-gray-50"
          : "font-semibold text-gray-900 dark:text-gray-50"),
        !isAnchor && isZero && "text-gray-300 dark:text-gray-700",
        !isAnchor && isPositive && sign === "+" && "text-emerald-700 dark:text-emerald-400",
        !isAnchor && isNegative && sign === "−" && "text-red-700 dark:text-red-400",
        !isAnchor && isPositive && sign === "−" && "text-red-700 dark:text-red-400",
        !isAnchor && isNegative && sign === "+" && "text-red-700 dark:text-red-400",
        highlightAlert && "font-semibold",
      )}>
        {isAnchor ? fmtBRL.format(value) : fmtBRLSigned(value)}
      </span>
    </div>
  )
}

function ResiduoRow({ value }: { value: number }) {
  const abs = Math.abs(value)
  const isOk = abs < RESIDUO_OK_BRL
  return (
    <div className={cx(
      "grid grid-cols-[1fr_140px] items-center gap-2 border-t px-3 py-1.5 text-[11px] tabular-nums",
      isOk
        ? "border-gray-100 dark:border-gray-900"
        : "border-amber-200 bg-amber-50/40 dark:border-amber-900/40 dark:bg-amber-950/10",
    )}>
      <span className={cx(
        "uppercase tracking-[0.06em]",
        isOk
          ? "text-gray-400 dark:text-gray-600"
          : "font-semibold text-amber-800 dark:text-amber-300",
      )}>
        Resíduo {isOk ? "(arredondamento)" : "(desalinhamento de pipeline)"}
      </span>
      <span className={cx(
        "text-right",
        isOk
          ? "text-gray-500 dark:text-gray-400"
          : "font-semibold text-amber-800 dark:text-amber-300",
      )}>
        {fmtBRLSigned(value)}
      </span>
    </div>
  )
}

function MutacaoRow({ p }: { p: DrillDcMutacaoPapel }) {
  const mudancas: string[] = []
  if (p.mudou_vn) mudancas.push(`VN ${fmtBRL.format(p.vn_d1)} → ${fmtBRL.format(p.vn_d0)}`)
  if (p.mudou_taxa) mudancas.push(`Taxa ${fmtTaxa(p.taxa_d1)} → ${fmtTaxa(p.taxa_d0)}`)
  if (p.mudou_venc) mudancas.push(`Venc ${fmtDateBR(p.venc_d1)} → ${fmtDateBR(p.venc_d0)}`)
  const isNegative = p.delta_vp < 0

  return (
    <tr className="border-t border-amber-100 dark:border-amber-900/40">
      <td className="px-3 py-1.5 text-gray-700 dark:text-gray-200">
        <div className="flex flex-col">
          <span className="truncate text-[11px]" title={`${p.cedente_doc} → ${p.sacado_doc}`}>
            <span className="font-medium">{p.cedente_nome}</span>
            <span className="text-gray-400"> → </span>
            <span>{p.sacado_nome}</span>
          </span>
        </div>
      </td>
      <td className="px-3 py-1.5 font-mono text-[11px] text-gray-500 dark:text-gray-400" title={p.numero_documento}>
        {p.seu_numero}
      </td>
      <td className="px-3 py-1.5 text-right text-gray-500 dark:text-gray-400">{fmtBRL.format(p.vp_d1)}</td>
      <td className="px-3 py-1.5 text-right text-gray-900 dark:text-gray-50">{fmtBRL.format(p.vp_d0)}</td>
      <td className={cx(
        "px-3 py-1.5 text-right font-semibold",
        isNegative ? "text-red-700 dark:text-red-400" : "text-emerald-700 dark:text-emerald-400",
      )}>
        {fmtBRLSigned(p.delta_vp)}
      </td>
      <td className="px-3 py-1.5 text-[10px] text-gray-500 dark:text-gray-400">
        <div className="flex flex-col gap-0.5">
          {mudancas.map((m, i) => <span key={i}>{m}</span>)}
        </div>
      </td>
    </tr>
  )
}

function MigracaoWopRow({ p }: { p: DrillDcMigracaoWopPapel }) {
  return (
    <tr className="border-t border-gray-100 dark:border-gray-900">
      <td className="px-3 py-1.5 text-gray-700 dark:text-gray-200">
        <span className="truncate text-[11px]" title={`${p.cedente_doc} → ${p.sacado_doc}`}>
          <span className="font-medium">{p.cedente_nome}</span>
          <span className="text-gray-400"> → </span>
          <span>{p.sacado_nome}</span>
        </span>
      </td>
      <td className="px-3 py-1.5 font-mono text-[11px] text-gray-500 dark:text-gray-400" title={p.numero_documento}>
        {p.seu_numero}
      </td>
      <td className="px-3 py-1.5 text-center">
        <span className="inline-flex items-center rounded-sm bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium text-gray-700 dark:bg-gray-800 dark:text-gray-300">
          {p.faixa_pdd_d1}
        </span>
      </td>
      <td className="px-3 py-1.5 text-right text-gray-700 dark:text-gray-200">{fmtBRL.format(p.vp_d1)}</td>
      <td className="px-3 py-1.5 text-right text-gray-500 dark:text-gray-400">{fmtBRL.format(p.valor_pdd_d1)}</td>
    </tr>
  )
}
