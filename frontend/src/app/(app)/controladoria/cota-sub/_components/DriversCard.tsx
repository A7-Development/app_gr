"use client"

/**
 * DriversCard — rail direito do split. Lista 7 categorias de variacao
 * ordenadas por |delta|, com expand individual mostrando narrativa +
 * evidencias.
 *
 * Categorias canonicas (alinhada com AnaliseVariacaoCard.tsx):
 *   - pdd (provisao de credito)            — rose   (alerta de risco)
 *   - ajustes_contabeis (dif/aprop)        — violet
 *   - fluxo_caixa (aporte/resgate)         — emerald
 *   - movimento_carteira (liq/aquisicao)   — blue   (INFORMACIONAL, delta=0)
 *   - marcacao_mercado                     — amber
 *   - remuneracao_sr_mez                   — rose   (custo de subordinacao)
 *   - outros (nao explicado)               — slate  (gap residual, transparente)
 *
 * Movimento de carteira e bucket INFORMACIONAL: papel liquidado/adquirido
 * tem impacto patrimonial neutro no Sub (caixa +X, DC -X = net 0).
 * Diferencas residuais caem em PDD ou Apropriacao.
 *
 * Marcacao a mercado: papeis de renda fixa com qtd estavel + valor variando
 * — Sub absorve direto (papel sobe → Ativo cresce → Sub cresce).
 *
 * Remuneracao Sr/Mez: cotas Senior/Mez valorizam diariamente pela curva
 * contratada; Sub absorve com sinal invertido (PL_Sub = Ativo - Passivo -
 * Equity_Sr - Equity_Mez). Sub paga subordinacao.
 *
 * Outros (Nao explicado): gap residual entre ΔPL real (MEC) e Σ explainers.
 * Sub-causas conhecidas (2026-05-17): (a) apropriacao de juros DC (carrego
 * diario dos recebiveis), (b) variacao nao-MtM de RF (liquidacao/baixa que
 * mexe qtd), (c) CPRs nao-cobertos pelos regex atuais. Bucket TRANSPARENTE:
 * mostra honestamente o que o sistema ainda nao classificou + CTA pra
 * investigar no balancete.
 */

import * as React from "react"
import {
  RiArrowDownSLine,
  RiArrowRightSLine,
  RiArrowUpSLine,
  RiBankCardLine,
  RiBriefcaseLine,
  RiFileList3Line,
  RiLineChartLine,
  RiQuestionLine,
  RiShieldCheckLine,
  RiStackLine,
} from "@remixicon/react"
import type { ComponentType } from "react"

import { cx, focusRing } from "@/lib/utils"
import type {
  ApropriacaoDcEvidencia,
  ApropriacaoExplanation,
  CosifOrigem,
  DiferimentoExplanation,
  DriverResultOut,
  EventoOperacionalEvidencia,
  EvidenciaCprLinha,
  FluxoCaixaEvidencia,
  FluxoCaixaExplanation,
  MovimentoCarteiraEvidencia,
  MovimentoCarteiraExplanation,
  MtmEvidencia,
  MtmExplanation,
  OutrosExplanation,
  PddEvidencia,
  PddExplanation,
  RemuneracaoSrMezEvidencia,
  RemuneracaoSrMezExplanation,
  SaldoTesourariaEvidencia,
} from "@/lib/api-client"

import type { BridgeCategoryId } from "./BridgeCard"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL",
  minimumFractionDigits: 2, maximumFractionDigits: 2,
})

const fmtBRLk = (v: number) => {
  const abs = Math.abs(v)
  const sign = v < 0 ? "−" : ""
  if (abs >= 1_000_000) return `${sign}R$ ${(abs / 1_000_000).toFixed(2).replace(".", ",")}M`
  if (abs >= 1_000)     return `${sign}R$ ${(abs / 1_000).toFixed(1).replace(".", ",")}k`
  return `${sign}R$ ${abs.toFixed(0)}`
}

const fmtPp = (deltaBrl: number, base: number): string => {
  if (!base) return "—"
  const pp = (deltaBrl / base) * 100
  const sign = pp > 0 ? "+" : pp < 0 ? "−" : ""
  return `${sign}${Math.abs(pp).toFixed(2).replace(".", ",")}pp`
}

type CategoryMeta = {
  id:       BridgeCategoryId
  label:    string
  icon:     ComponentType<{ className?: string }>
  iconCls:  string
  bgCls:    string
  barHex:   string
}

const CATEGORY_META: readonly CategoryMeta[] = [
  // Drivers canonicos do metodo gestor (Fase 4c, 2026-05-19). Ordem da lista
  // segue a planilha REALINVEST: ativos da carteira primeiro, depois passivos
  // (Sr/Mez), depois residuais. DriversCard re-ordena por |delta| desc em
  // runtime, mas a ordem aqui controla o waterfall e o estado "empty".
  {
    id:      "pdd",
    label:   "PDD (provisão de crédito)",
    icon:    RiShieldCheckLine,
    iconCls: "text-rose-600 dark:text-rose-400",
    bgCls:   "bg-rose-50 dark:bg-rose-500/10",
    barHex:  "#F43F5E",
  },
  {
    id:      "apropriacao_dc",
    label:   "Apropriação de DC",
    icon:    RiBriefcaseLine,
    iconCls: "text-blue-600 dark:text-blue-400",
    bgCls:   "bg-blue-50 dark:bg-blue-500/10",
    barHex:  "#3B82F6",
  },
  {
    id:      "apropriacao_despesas",
    label:   "Apropriação de despesas",
    icon:    RiFileList3Line,
    iconCls: "text-violet-600 dark:text-violet-400",
    bgCls:   "bg-violet-50 dark:bg-violet-500/10",
    barHex:  "#8B5CF6",
  },
  {
    id:      "fundos_di",
    label:   "Fundos DI",
    icon:    RiBankCardLine,
    iconCls: "text-cyan-600 dark:text-cyan-400",
    bgCls:   "bg-cyan-50 dark:bg-cyan-500/10",
    barHex:  "#06B6D4",
  },
  {
    id:      "compromissada",
    label:   "Compromissada",
    icon:    RiStackLine,
    iconCls: "text-indigo-600 dark:text-indigo-400",
    bgCls:   "bg-indigo-50 dark:bg-indigo-500/10",
    barHex:  "#6366F1",
  },
  {
    id:      "titulos_publicos",
    label:   "Títulos Públicos",
    icon:    RiLineChartLine,
    iconCls: "text-amber-600 dark:text-amber-400",
    bgCls:   "bg-amber-50 dark:bg-amber-500/10",
    barHex:  "#F59E0B",
  },
  // Senior + Mezanino sao colapsados em UM driver na UI ("Remuneracao Sr/Mez"),
  // mantendo as duas classes detalhadas no expand. Backend continua expondo
  // 2 drivers granulares (controladoria.cota_sub.driver.senior e .mezanino);
  // o merge acontece no EventosDiaTab antes de chegar aqui. Reduz a contagem
  // de drivers visiveis (de 11 pra 10) sem perder granularidade auditavel.
  {
    id:      "remuneracao_sr_mez",
    label:   "Remuneração Sr/Mez",
    icon:    RiStackLine,
    iconCls: "text-rose-600 dark:text-rose-400",
    bgCls:   "bg-rose-50 dark:bg-rose-500/10",
    barHex:  "#F43F5E",
  },
  {
    id:      "tesouraria",
    label:   "Tesouraria",
    icon:    RiBankCardLine,
    iconCls: "text-teal-600 dark:text-teal-400",
    bgCls:   "bg-teal-50 dark:bg-teal-500/10",
    barHex:  "#14B8A6",
  },
  {
    id:      "op_estruturadas",
    label:   "Op Estruturadas",
    icon:    RiFileList3Line,
    iconCls: "text-orange-600 dark:text-orange-400",
    bgCls:   "bg-orange-50 dark:bg-orange-500/10",
    barHex:  "#F97316",
  },
  {
    id:      "outros_ativos",
    label:   "Outros Ativos",
    icon:    RiQuestionLine,
    iconCls: "text-slate-600 dark:text-slate-400",
    bgCls:   "bg-slate-100 dark:bg-slate-500/10",
    barHex:  "#64748B",
  },
]

export type DriverEvidence = {
  /** Identificador legivel (papel, lancamento, MOV-id). */
  titulo:   string
  /** Subtitle mono: COSIF · motivo / cedente / etc. */
  subtitle: string
  d1?:      number | null
  d0?:      number | null
  /** Delta ja com sinal coerente com o impacto no PL (positivo=verde, negativo=vermelho). */
  delta:    number
  /** Valor nominal do papel — referencia "quanto ainda ha para avancar". */
  valorNominal?: number
  /** Label customizada da linha d1 → d0 (default: "D-1 → D0"). Em PDD usamos "PDD". */
  flowLabel?: string
}

export type DriverCosifOrigem = {
  codigo:    string
  nome:      string
  d_minus_1: number
  d_zero:    number
  delta:     number
}

export type DriverInput = {
  id:          BridgeCategoryId
  /** Delta R$ na categoria. 0 quando placeholder ou empty. */
  delta:       number
  /** Sublabel curta da categoria no estado colapsado. */
  sublabel?:   string
  /** Narrativa que aparece quando expandido. Vazia => default da categoria. */
  narrative?:  string
  /** Evidencias detalhadas. */
  evidencias?: DriverEvidence[]
  /** Eventos operacionais SEM impacto no PL — renderizam em sub-secao
   * separada com style cinza. Hoje so o bucket `fluxo_caixa` produz isso
   * (aporte engaiolado / devolucao). Soma 0 no delta do bucket. */
  operationalEvents?: OperationalEvent[]
  /** Categoria ainda NAO implementada no backend. Mostra "Em construcao". */
  placeholder?: boolean
  /** Categoria implementada mas SEM evento no dia (delta=0, sem evidencias,
   * sem eventos operacionais). Mostra "Sem movimentacao no dia" — diferente
   * de placeholder porque a feature existe, so o dia foi trivial. */
  empty?:       boolean
  /** Sinaliza que o bucket eh "Nao explicado" (id="outros") — renderizado com
   * tom slate e ofertando o CTA "Investigar". O sinal nao vai pra cor (slate
   * sempre), o pp e o R$ vao com a cor semantica do impacto. */
  unexplained?: boolean
  /** Folhas COSIF que somam pro delta_brl do bucket. Refactor 2026-05-17:
   * fonte contabil da variacao, exibida no expand como "Origem contabil".
   * Permite auditar exatamente DE ONDE vem o impacto antes mesmo das
   * evidencias enriquecidas pelas heuristicas. */
  cosifOrigin?: DriverCosifOrigem[]
  /** Quando o granular nao pode ser computado por dado upstream ausente
   * (ex.: wh_estoque_recebivel vazio em D-1 ou D0), carrega explicacao
   * curta. Driver continua valido (vem do consolidado MEC); evidencias
   * ficam vazias. UI renderiza este texto no lugar da lista de papeis. */
  evidenciasIndisponiveisMotivo?: string
}

export type OperationalEvent = {
  /** Titulo curto (ex.: "Aporte recebido sem integralizacao"). */
  titulo:    string
  /** Subtitle mono com origem / detalhe extra. */
  subtitle?: string
  /** Valor absoluto envolvido (R$). Renderiza em cinza, sem sinal. */
  valor:     number
}

export type DriversCardProps = {
  drivers: DriverInput[]
  /** Base para conversao R$ -> pp (geralmente PL Cota Sub D-1). */
  base?:   number
  /** Callback do CTA "Investigar no balancete" — chamado dentro do expand
   * do bucket "Não explicado". Tipicamente alterna pro sub-tab "Detalhe". */
  onInvestigate?: () => void
}

export function DriversCard({ drivers, base, onInvestigate }: DriversCardProps) {
  const driverById = new Map(drivers.map((d) => [d.id, d]))
  // "outros" so aparece quando ha gap real (input presente). Os demais 6
  // sempre renderizam (mesmo sem input -> placeholder/empty).
  const allCategories = CATEGORY_META
    .filter((m) => m.id !== "outros" || driverById.has("outros"))
    .map((m) => {
      const d = driverById.get(m.id)
      return {
        meta:        m,
        input:       d,
        delta:       d?.delta ?? 0,
        placeholder: d?.placeholder ?? (!d && m.id !== "outros"),
        empty:       d?.empty ?? false,
        unexplained: d?.unexplained ?? false,
      }
    })

  // Ordem: drivers com impacto (delta != 0) primeiro por |delta| desc;
  // depois "sem movimentacao" (entregues mas sem evento); por ultimo
  // "em construcao" (placeholders). "Nao explicado" entra no ranking
  // junto com os outros — usuario ve por IMPACTO, sem esconder o gap.
  const rank = (d: { placeholder: boolean; empty: boolean; delta: number }): number => {
    if (d.placeholder) return 2
    if (d.empty || d.delta === 0) return 1
    return 0
  }
  const sorted = [...allCategories].sort((a, b) => {
    const rA = rank(a), rB = rank(b)
    if (rA !== rB) return rA - rB
    return Math.abs(b.delta) - Math.abs(a.delta)
  })

  const maxAbs = Math.max(...sorted.map((d) => Math.abs(d.delta)), 1)

  const firstWithImpact = sorted.findIndex(
    (d) => !d.placeholder && !d.empty && d.delta !== 0,
  )
  const [expandedId, setExpandedId] = React.useState<BridgeCategoryId | null>(
    firstWithImpact >= 0 ? sorted[firstWithImpact].meta.id : null,
  )

  return (
    <section
      className={cx(
        "flex h-full flex-col rounded border px-4 py-3",
        "border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
      )}
    >
      <div className="mb-1 flex flex-wrap items-baseline gap-2">
        <h3 className="text-[13.5px] font-semibold leading-tight tracking-[-0.01em] text-gray-900 dark:text-gray-50">
          Drivers do dia
        </h3>
        <span className="text-[11.5px] text-gray-500 dark:text-gray-400">
          ordenadas por impacto
        </span>
      </div>

      <ul className="flex flex-1 flex-col">
        {sorted.map((d, i) => (
          <DriverItem
            key={d.meta.id}
            meta={d.meta}
            input={d.input}
            delta={d.delta}
            placeholder={d.placeholder}
            empty={d.empty}
            unexplained={d.unexplained}
            base={base}
            maxAbs={maxAbs}
            firstInList={i === 0}
            expanded={expandedId === d.meta.id}
            onToggle={() =>
              setExpandedId((curr) => (curr === d.meta.id ? null : d.meta.id))
            }
            onInvestigate={onInvestigate}
          />
        ))}
      </ul>
    </section>
  )
}

function DriverItem({
  meta,
  input,
  delta,
  placeholder,
  empty,
  unexplained,
  base,
  maxAbs,
  firstInList,
  expanded,
  onToggle,
  onInvestigate,
}: {
  meta:        CategoryMeta
  input?:      DriverInput
  delta:       number
  placeholder: boolean
  empty:       boolean
  unexplained: boolean
  base?:       number
  maxAbs:      number
  firstInList: boolean
  expanded:    boolean
  onToggle:    () => void
  onInvestigate?: () => void
}) {
  const Icon = meta.icon
  const barPct = (Math.abs(delta) / maxAbs) * 100

  // 3 estados visuais:
  //  - placeholder: categoria nao implementada — "Em construcao", cinza
  //  - empty: implementada mas sem evento no dia — "Sem movimentacao no dia",
  //    cinza mais claro, avatar/ícone com cor viva da categoria pra indicar
  //    que a feature existe (so o dia foi trivial)
  //  - normal: render com cor por sinal (+/-)
  const isNeutral = placeholder || empty || delta === 0

  const deltaCls = isNeutral
    ? "text-gray-400 dark:text-gray-600"
    : delta > 0
      ? "text-emerald-700 dark:text-emerald-400"
      : "text-rose-700 dark:text-rose-400"

  const sublabel = placeholder
    ? "Em construção"
    : empty
      ? "Sem movimentação no dia"
      : input?.sublabel ?? defaultSublabel(meta.id)

  return (
    <li
      className={cx(
        firstInList ? "" : "border-t border-gray-100 dark:border-gray-800",
      )}
    >
      <button
        type="button"
        onClick={onToggle}
        className={cx(
          "flex w-full items-start gap-2.5 py-3 text-left transition-colors",
          "hover:bg-gray-50/60 dark:hover:bg-gray-900/40",
          focusRing,
        )}
        aria-expanded={expanded}
      >
        <span
          className={cx(
            "mt-0.5 inline-flex size-7 shrink-0 items-center justify-center rounded",
            meta.bgCls,
          )}
        >
          <Icon className={cx("size-3.5", meta.iconCls)} aria-hidden="true" />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-baseline gap-2">
            <span className="text-[13px] font-semibold text-gray-900 dark:text-gray-50">
              {meta.label}
            </span>
            <span
              className={cx(
                "ml-auto text-[13px] font-semibold tabular-nums",
                deltaCls,
              )}
            >
              {isNeutral
                ? "—"
                : `${delta > 0 ? "+" : ""}${fmtBRL.format(delta)}`}
            </span>
          </div>
          <div className="mt-0.5 flex items-baseline gap-2">
            <span
              className={cx(
                "min-w-0 flex-1 truncate text-[11.5px]",
                isNeutral
                  ? "italic text-gray-400 dark:text-gray-600"
                  : "text-gray-500 dark:text-gray-400",
              )}
            >
              {sublabel}
            </span>
            <span className="shrink-0 text-[11px] tabular-nums text-gray-500 dark:text-gray-400">
              {isNeutral ? "—" : fmtPp(delta, base ?? 0)}
            </span>
          </div>
          {/* Mini bar */}
          <div className="mt-2 h-1 overflow-hidden rounded-sm bg-gray-100 dark:bg-gray-800">
            <div
              className="h-full"
              style={{
                width:      `${Math.max(barPct, isNeutral ? 0 : 2)}%`,
                background: isNeutral ? "#D1D5DB" : meta.barHex,
                opacity:    isNeutral ? 0.45 : 0.85,
              }}
            />
          </div>
        </div>
        <span className="mt-1 text-gray-400 dark:text-gray-600">
          {expanded ? (
            <RiArrowUpSLine className="size-4" aria-hidden="true" />
          ) : (
            <RiArrowDownSLine className="size-4" aria-hidden="true" />
          )}
        </span>
      </button>

      {expanded && (
        <div
          className={cx(
            "mb-3 rounded border-l-[3px] bg-gray-50 px-3 py-2.5 dark:bg-gray-900/60",
          )}
          style={{ borderLeftColor: isNeutral ? "#D1D5DB" : meta.barHex }}
        >
          <p className="text-[12px] leading-[1.5] text-gray-700 dark:text-gray-300">
            {input?.narrative ?? (placeholder
              ? "Detector heurístico desta categoria ainda não foi entregue. Aguarda o backend implementar o explainer dedicado em `cota_sub_explainers.py`."
              : empty
                ? `Nenhuma movimentação detectada no dia. Categoria monitora: ${defaultNarrative(meta.id).toLowerCase()}`
                : defaultNarrative(meta.id))}
          </p>

          {/* Origem contabil — lista as folhas COSIF que somam pro delta_brl
              do bucket. Refactor 2026-05-17: fonte de verdade. No bucket
              "Não explicado" isso e a UNICA evidencia disponivel (folhas
              sem mapping); nos demais e auditoria. */}
          {input?.cosifOrigin && input.cosifOrigin.length > 0 && (
            <div className="mt-2.5 rounded border border-gray-200 bg-white p-2.5 dark:border-gray-800 dark:bg-gray-950/60">
              <div className="mb-1.5 flex items-baseline justify-between gap-2">
                <span className="text-[10.5px] font-semibold uppercase tracking-[0.04em] text-gray-600 dark:text-gray-400">
                  {unexplained ? "Contas COSIF sem mapping" : "Origem contábil"}
                </span>
                <span className="text-[10.5px] tabular-nums text-gray-500 dark:text-gray-500">
                  {input.cosifOrigin.length} {input.cosifOrigin.length === 1 ? "conta" : "contas"}
                </span>
              </div>
              <ul className="flex flex-col gap-1.5">
                {input.cosifOrigin.map((c) => (
                  <li key={c.codigo + c.nome} className="flex items-baseline gap-2 text-[11.5px]">
                    <span className="font-mono text-[10.5px] text-gray-500 dark:text-gray-400 shrink-0">
                      {c.codigo}
                    </span>
                    <span className="min-w-0 flex-1 truncate text-gray-700 dark:text-gray-300">
                      {c.nome}
                    </span>
                    <span
                      className={cx(
                        "shrink-0 tabular-nums",
                        c.delta > 0
                          ? "text-emerald-700 dark:text-emerald-400"
                          : c.delta < 0
                            ? "text-rose-700 dark:text-rose-400"
                            : "text-gray-500 dark:text-gray-500",
                      )}
                    >
                      {c.delta > 0 ? "+" : c.delta < 0 ? "−" : ""}
                      {fmtBRL.format(Math.abs(c.delta))}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {unexplained && onInvestigate && (
            <button
              type="button"
              onClick={onInvestigate}
              className={cx(
                "mt-2.5 inline-flex items-center gap-1 text-[11.5px] font-medium",
                "text-blue-700 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300",
                focusRing,
              )}
            >
              Investigar no balancete
              <RiArrowRightSLine className="size-3.5" aria-hidden="true" />
            </button>
          )}

          {input?.evidencias && input.evidencias.length > 0 && (
            <ul className="mt-2.5 flex flex-col gap-2">
              {input.evidencias.map((e, i) => (
                <EvidenceItem key={i} ev={e} />
              ))}
            </ul>
          )}

          {input?.evidenciasIndisponiveisMotivo
            && (!input.evidencias || input.evidencias.length === 0) && (
            <div
              className={cx(
                "mt-2.5 rounded border border-dashed px-3 py-2.5",
                "border-amber-300 bg-amber-50/60 dark:border-amber-500/40 dark:bg-amber-500/5",
              )}
            >
              <div className="mb-1 flex items-baseline gap-1.5">
                <span className="text-[10.5px] font-semibold uppercase tracking-[0.04em] text-amber-700 dark:text-amber-400">
                  Evidências papel-a-papel indisponíveis
                </span>
              </div>
              <p className="text-[11.5px] leading-[1.5] text-amber-900 dark:text-amber-200">
                {input.evidenciasIndisponiveisMotivo}
              </p>
            </div>
          )}

          {input?.operationalEvents && input.operationalEvents.length > 0 && (
            <div className="mt-3 border-t border-gray-200 pt-2.5 dark:border-gray-800">
              <div className="mb-1.5 flex items-baseline gap-1.5">
                <span className="text-[10.5px] font-semibold uppercase tracking-[0.04em] text-gray-500 dark:text-gray-400">
                  Eventos operacionais
                </span>
                <span className="text-[10.5px] italic text-gray-400 dark:text-gray-600">
                  sem impacto no PL
                </span>
              </div>
              <ul className="flex flex-col gap-2">
                {input.operationalEvents.map((e, i) => (
                  <OperationalEventItem key={i} ev={e} />
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </li>
  )
}

function OperationalEventItem({ ev }: { ev: OperationalEvent }) {
  return (
    <li
      className={cx(
        "flex items-center gap-2.5 rounded border px-2.5 py-2",
        "border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950/60",
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="truncate text-[12px] font-medium text-gray-700 dark:text-gray-300">
          {ev.titulo}
        </div>
        {ev.subtitle && (
          <div className="truncate font-mono text-[10.5px] text-gray-500 dark:text-gray-500">
            {ev.subtitle}
          </div>
        )}
      </div>
      <div className="shrink-0 text-right">
        <div className="text-[12px] font-semibold tabular-nums text-gray-600 dark:text-gray-400">
          {fmtBRL.format(ev.valor)}
        </div>
        <div className="text-[10px] tabular-nums text-gray-400 dark:text-gray-600">
          neutro no PL
        </div>
      </div>
    </li>
  )
}

function EvidenceItem({ ev }: { ev: DriverEvidence }) {
  const flowLabel = ev.flowLabel ?? "D-1 → D0"
  return (
    <li
      className={cx(
        "flex items-center gap-2.5 rounded border bg-white px-2.5 py-2",
        "border-gray-200 dark:border-gray-800 dark:bg-gray-950/60",
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="truncate text-[12px] font-medium text-gray-900 dark:text-gray-50">
          {ev.titulo}
        </div>
        <div className="truncate font-mono text-[10.5px] text-gray-500 dark:text-gray-400">
          {ev.subtitle}
        </div>
        {ev.valorNominal != null && (
          <div className="mt-0.5 text-[10.5px] text-gray-500 dark:text-gray-400">
            <span className="text-gray-400 dark:text-gray-600">Valor nominal: </span>
            <span className="tabular-nums text-gray-700 dark:text-gray-300">
              {fmtBRL.format(ev.valorNominal)}
            </span>
          </div>
        )}
      </div>
      <div className="shrink-0 text-right">
        <div
          className={cx(
            "text-[12px] font-semibold tabular-nums",
            ev.delta > 0
              ? "text-emerald-700 dark:text-emerald-400"
              : ev.delta < 0
                ? "text-rose-700 dark:text-rose-400"
                : "text-gray-600 dark:text-gray-400",
          )}
        >
          {ev.delta > 0 ? "+" : ev.delta < 0 ? "−" : ""}
          {fmtBRL.format(Math.abs(ev.delta))}
        </div>
        {(ev.d1 != null || ev.d0 != null) && (
          <div className="text-[10px] tabular-nums text-gray-400 dark:text-gray-600">
            <span className="mr-1 text-gray-400 dark:text-gray-600">{flowLabel}:</span>
            {ev.d1 == null ? "—" : fmtBRLkSigned(ev.d1)} →{" "}
            {ev.d0 == null ? "—" : fmtBRLkSigned(ev.d0)}
          </div>
        )}
      </div>
    </li>
  )
}

function fmtBRLkSigned(v: number): string {
  if (v === 0) return "R$ 0"
  const abs = Math.abs(v)
  const sign = v < 0 ? "−" : ""
  if (abs >= 1_000_000) return `${sign}R$ ${(abs / 1_000_000).toFixed(2).replace(".", ",")}M`
  if (abs >= 1_000)     return `${sign}R$ ${(abs / 1_000).toFixed(1).replace(".", ",")}k`
  return `${sign}R$ ${abs.toFixed(0)}`
}

function defaultSublabel(id: CategoryMeta["id"]): string {
  switch (id) {
    // Drivers do metodo gestor (Fase 4c)
    case "pdd":                  return "Constituição ou reversão de provisão de crédito"
    case "apropriacao_dc":       return "Apropriação de juros do estoque DC (dEstoque − Aq + Liq)"
    case "apropriacao_despesas": return "Apropriação de despesas e taxas operacionais via CPR"
    case "fundos_di":            return "Rendimento de cotas de fundos externos (DI, Selic, CDI)"
    case "compromissada":        return "Rendimento de operações compromissadas"
    case "titulos_publicos":     return "Marcação a mercado de TPF (LTN, NTN, LFT)"
    case "senior":               return "Custo de subordinação da classe Senior"
    case "mezanino":             return "Custo de subordinação da classe Mezanino"
    case "tesouraria":           return "Rendimento de saldos em conta corrente e tesouraria"
    case "op_estruturadas":      return "Variação de operações estruturadas"
    case "outros_ativos":        return "Outros ativos não classificados em categorias específicas"
    // Legacy COSIF
    case "ajustes_contabeis":    return "Apropriação de diferimentos e despesas contábeis"
    case "fluxo_caixa":          return "Aporte ou resgate em qualquer classe de cota"
    case "movimento_carteira":   return "Giro da carteira de direitos creditórios"
    case "marcacao_mercado":     return "TPF + Notas comerciais + cotas de fundos RF"
    case "remuneracao_sr_mez":   return "Custo de subordinação das cotas Sr e Mez"
    case "outros":               return "Gap residual entre ΔPL real e Σ drivers conhecidos"
  }
}
function defaultNarrative(id: CategoryMeta["id"]): string {
  switch (id) {
    // Drivers do metodo gestor (Fase 4c)
    case "pdd":                  return "Mudança de faixa de provisão dos direitos creditórios — Sub absorve PDD, então constituição reduz o PL Sub e reversão aumenta."
    case "apropriacao_dc":       return "Apropriação dos juros embutidos no estoque DC: Apropriação = Estoque_D0 − (Estoque_D−1 + Aquisições − Liquidações). Carrego diário da curva contratada de cada recebível."
    case "apropriacao_despesas": return "Apropriação de despesas e taxas operacionais (Adm, Custódia, Gestão, Auditoria, IOF, Cobrança, Registradora, etc.) e diferimentos sendo amortizados. Sub absorve direto."
    case "fundos_di":            return "Rendimento diário de cotas de fundos externos (Itaú Soberano, BB Fix, etc.). Δposição menos movimento de caixa do dia (aplicação/resgate é neutro pro PL)."
    case "compromissada":        return "Rendimento de operações compromissadas (overnight ou prazo) — Δposição da carteira de compromissadas. Comum em FIDCs que parquerizam caixa entre giros."
    case "titulos_publicos":     return "Marcação a mercado de Títulos Públicos Federais (TPF: LTN, NTN-B, NTN-F, LFT). Variação do PU pela curva do dia. Não conta resgate/aquisição (esses são movimento de caixa)."
    case "senior":               return "Cotas Senior valorizam diariamente pela curva contratada (CDI + spread). Sub absorve com sinal invertido. Aporte/resgate na classe Sr é subtraído pra isolar APENAS a remuneração (curva)."
    case "mezanino":             return "Cotas Mezanino valorizam diariamente pela curva contratada. Análogo a Senior — Sub paga a remuneração da classe."
    case "tesouraria":           return "Rendimento de saldos em conta corrente e tesouraria (incluindo conta movimento, conciliação)."
    case "op_estruturadas":      return "Variação de operações estruturadas — derivativos, hedge, instrumentos sintéticos. Raro em REALINVEST."
    case "outros_ativos":        return "Ativos que não casaram com nenhuma das 10 categorias canônicas — em regime estável fica perto de zero. Quando aparece, indica papel novo no payload que precisa entrar no filtro."
    // Legacy COSIF
    case "ajustes_contabeis":    return "Apropriação de despesas diferidas e lançamentos de competência — natureza temporal, não muda risco de crédito."
    case "fluxo_caixa":          return "Aporte ou resgate em Subordinada, Mezanino ou Senior. Sub absorve direto (aporte Sub = +PL Sub); Mez/Sr afetam Sub via equity (aporte Mez = −PL Sub residual)."
    case "movimento_carteira":   return "Giro da carteira: papéis liquidados saem do DC; papéis adquiridos entram. Bucket informacional — movimento patrimonial neutro no PL Sub (caixa cresce/cai e DC cai/cresce no mesmo valor). Diferenças residuais aparecem em PDD ou Apropriação."
    case "marcacao_mercado":     return "Variações em títulos de Renda Fixa: TPF (LTN, NTN), Notas Comerciais e cotas de fundos de RF. Inclui marcação a mercado (PU pela curva do dia), apropriação de juros, ganhos/perdas de liquidação."
    case "remuneracao_sr_mez":   return "Cotas Senior e Mezanino valorizam diariamente pela curva contratada (CDI + spread). Sub absorve com sinal invertido: PL_Sub = Ativo − Passivo − Equity_Sr − Equity_Mez. Quanto mais Sr/Mez valorizam, mais Sub paga de subordinação."
    case "outros":               return "Diferença entre o ΔPL real (do MEC) e a soma dos drivers acima. Não é erro do balancete — o balancete fecha. É um pedaço da variação que os heurísticos atuais ainda não atribuem a uma causa nomeada."
  }
}

// ─── Helpers para o EventosDiaTab montar os drivers de PDD e Ajustes ─────────

/** Mapeia CosifOrigem[] (api) -> DriverCosifOrigem[] (driver input). */
function cosifOrigemToDriver(list: CosifOrigem[] | undefined): DriverCosifOrigem[] | undefined {
  return list && list.length > 0 ? list.map((c) => ({
    codigo:    c.codigo,
    nome:      c.nome,
    d_minus_1: c.d_minus_1,
    d_zero:    c.d_zero,
    delta:     c.delta,
  })) : undefined
}

export function buildDriverFromPdd(pdd: PddExplanation): DriverInput {
  return {
    id:          "pdd",
    delta:       pdd.delta_brl,
    sublabel:    pdd.evidencias_total === 1
      ? "1 papel com variação de provisão"
      : `${pdd.evidencias_total} papéis com variação de provisão`,
    evidencias:  pdd.evidencias.map(evidenciaFromPdd),
    cosifOrigin: cosifOrigemToDriver(pdd.cosif_origin),
  }
}

/**
 * Bucket `ajustes_contabeis`: Diferimento + Apropriacao apenas (PDD foi
 * promovido a bucket proprio em 2026-05-17). Soma deltas, agrega evidencias
 * por categoria com prefixo no subtitle, monta sublabel composta.
 */
export function buildDriverFromAjustesContabeis(args: {
  diferimento?:  DiferimentoExplanation | undefined
  apropriacao?:  ApropriacaoExplanation | undefined
}): DriverInput | undefined {
  const { diferimento, apropriacao } = args
  if (!diferimento && !apropriacao) return undefined

  const delta =
    (diferimento?.delta_brl ?? 0)
    + (apropriacao?.delta_brl ?? 0)

  const evidencias: DriverEvidence[] = [
    ...(diferimento?.evidencias.map(
      (e) => evidenciaFromCpr(e, "Diferimento"),
    ) ?? []),
    ...(apropriacao?.evidencias.map(
      (e) => evidenciaFromCpr(e, "Apropriação"),
    ) ?? []),
  ]

  // Sublabel: composicao curta, ex.: "5 apropriações · 3 diferimentos"
  const partes: string[] = []
  if (apropriacao) {
    partes.push(
      apropriacao.evidencias_total === 1
        ? "1 apropriação"
        : `${apropriacao.evidencias_total} apropriações`,
    )
  }
  if (diferimento) {
    partes.push(
      diferimento.evidencias_total === 1
        ? "1 diferimento"
        : `${diferimento.evidencias_total} diferimentos`,
    )
  }

  // cosif_origin: ambas explanations (diferimento+apropriacao) apontam pro
  // MESMO conjunto de COSIFs (bucket Ajustes contabeis no backend). Pega
  // de uma das duas (preferindo apropriacao por mais abrangente).
  const cosif = apropriacao?.cosif_origin ?? diferimento?.cosif_origin

  return {
    id:          "ajustes_contabeis",
    delta,
    sublabel:    partes.join(" · "),
    evidencias,
    cosifOrigin: cosifOrigemToDriver(cosif),
  }
}

function evidenciaFromPdd(e: PddEvidencia): DriverEvidence {
  const tipoLabel = e.tipo_recebivel ? `${e.tipo_recebivel} · ` : ""
  const faixaInfo = e.faixa_pdd_d1 && e.faixa_pdd_d0 && e.faixa_pdd_d1 !== e.faixa_pdd_d0
    ? `Faixa ${e.faixa_pdd_d1} → ${e.faixa_pdd_d0}`
    : e.faixa_pdd_d0 ?? "—"
  // Sinais coerentes com o impacto no PL:
  //   PDD cresce  -> delta_valor_pdd > 0  ->  PL Sub cai  -> exibir como NEGATIVO (vermelho)
  //   PDD reverte -> delta_valor_pdd < 0  ->  PL Sub sobe -> exibir como POSITIVO (verde)
  // Valores absolutos de PDD sao expressos como negativo (convencao contabil:
  // provisao = deducao do ativo).
  return {
    titulo:       `${e.cedente_nome || e.cedente_doc} — ${e.sacado_nome || e.sacado_doc}`,
    subtitle:     `PDD · ${tipoLabel}${e.numero_documento || "—"} · ${faixaInfo}`,
    d1:           -e.valor_pdd_d1,
    d0:           -e.valor_pdd_d0,
    delta:        -e.delta_valor_pdd,
    valorNominal: e.valor_nominal,
    flowLabel:    "PDD",
  }
}

function evidenciaFromCpr(
  e: EvidenciaCprLinha,
  categoria: "Diferimento" | "Apropriação",
): DriverEvidence {
  return {
    titulo:    e.historico_traduzido || e.descricao,
    subtitle:  `${categoria} · CPR · ${truncate(e.descricao, 64)}`,
    d1:        e.valor_d1,
    d0:        e.valor_d0,
    delta:     e.delta_valor,
    flowLabel: "CPR",
  }
}

function truncate(s: string, max: number): string {
  return s.length > max ? `${s.slice(0, max - 1)}…` : s
}

// ─── Builder do bucket fluxo_caixa (categoria 1.1 + 1.2) ────────────────────

const fmtBRLkShort = (v: number): string => {
  const abs = Math.abs(v)
  if (abs >= 1_000_000) return `R$ ${(abs / 1_000_000).toFixed(2).replace(".", ",")}M`
  if (abs >= 1_000)     return `R$ ${(abs / 1_000).toFixed(1).replace(".", ",")}k`
  return `R$ ${abs.toFixed(0)}`
}

/**
 * Bucket `fluxo_caixa`: aporte/resgate em qualquer classe (Sub, Mez, Sr).
 *
 * Evidencias regulares listam classe x tipo com delta = `impacto_pl_sub`
 * (ja com sinal coerente: + ganho Sub, - perda Sub). Eventos operacionais
 * (aporte engaiolado, devolucao) viram OperationalEvent[] na sub-secao
 * 'Eventos operacionais (sem impacto no PL)' do expand.
 */
export function buildDriverFromFluxoCaixa(
  fc: FluxoCaixaExplanation,
): DriverInput {
  const evidencias: DriverEvidence[] = fc.evidencias.map(evidenciaFromFluxoCaixa)
  const operationalEvents: OperationalEvent[] = fc.eventos_operacionais.map(
    operationalEventFromCpr,
  )

  // Sublabel: ex.: "2 movimentos · 1 aporte Sub · 1 resgate Mez"
  const partes: string[] = []
  if (fc.evidencias.length > 0) {
    const n = fc.evidencias.length
    partes.push(n === 1 ? "1 movimento" : `${n} movimentos`)
  }
  if (fc.eventos_operacionais.length > 0) {
    const n = fc.eventos_operacionais.length
    partes.push(n === 1 ? "1 evento operacional" : `${n} eventos operacionais`)
  }

  return {
    id:                "fluxo_caixa",
    delta:             fc.delta_brl,
    sublabel:          partes.join(" · ") || undefined,
    evidencias,
    operationalEvents,
    cosifOrigin:       cosifOrigemToDriver(fc.cosif_origin),
  }
}

function evidenciaFromFluxoCaixa(e: FluxoCaixaEvidencia): DriverEvidence {
  const acao = e.tipo === "aporte" ? "Aporte" : "Resgate"
  const titulo = `${acao} ${e.classe_label}`
  // Subtitle: valor MEC + delta de cotas
  const qtdLabel = `${e.delta_qtd >= 0 ? "+" : ""}${e.delta_qtd.toLocaleString("pt-BR", {
    minimumFractionDigits: 2, maximumFractionDigits: 6,
  })} cotas`
  const subtitle = `MEC · ${fmtBRLkShort(e.valor_brl)} · ${qtdLabel}`
  return {
    titulo,
    subtitle,
    delta:     e.impacto_pl_sub,
    flowLabel: "Impacto Sub",
  }
}

function operationalEventFromCpr(e: EventoOperacionalEvidencia): OperationalEvent {
  const titulo = e.tipo === "aporte_engaiolado"
    ? "Aporte recebido sem integralização"
    : "Devolução de aporte efetivada"
  return {
    titulo,
    subtitle: e.detalhe ?? e.descricao,
    valor:    e.valor_brl,
  }
}

// ─── Builder do bucket movimento_carteira (categoria 2.1 + 2.2) ─────────────

/**
 * Bucket `movimento_carteira`: giro da carteira de DC entre D-1 e D0.
 *
 * INFORMACIONAL — `delta=0` por construcao (movimento patrimonial neutro
 * no Sub: papel liquidado: caixa +X, DC -X = net 0). Diferencas residuais
 * (ganho/perda de liquidacao) caem em PDD ou Apropriacao. Aqui mostramos
 * APENAS atividade: papeis liquidados/adquiridos, volume girado.
 */
export function buildDriverFromMovimentoCarteira(
  mc: MovimentoCarteiraExplanation,
): DriverInput {
  const evidencias: DriverEvidence[] = mc.evidencias.map(evidenciaFromMovimentoCarteira)

  // Sublabel: ex.: "86 liq · 203 aquis"
  const partes: string[] = []
  if (mc.papeis_liquidados > 0) {
    partes.push(
      mc.papeis_liquidados === 1
        ? "1 liquidação"
        : `${mc.papeis_liquidados} liquidações`,
    )
  }
  if (mc.papeis_adquiridos > 0) {
    partes.push(
      mc.papeis_adquiridos === 1
        ? "1 aquisição"
        : `${mc.papeis_adquiridos} aquisições`,
    )
  }

  return {
    id:          "movimento_carteira",
    // Refactor 2026-05-17: delta_brl agora vem do COSIF (Σ folhas 1.1.2.* +
    // 1.6.1.30.* + transitos), nao mais 0 por construcao.
    delta:       mc.delta_brl,
    sublabel:    partes.join(" · ") || undefined,
    evidencias,
    cosifOrigin: cosifOrigemToDriver(mc.cosif_origin),
  }
}

function evidenciaFromMovimentoCarteira(e: MovimentoCarteiraEvidencia): DriverEvidence {
  const acao = e.tipo === "liquidado" ? "Liquidado" : "Adquirido"
  // Sinal: liquidado sai do estoque (-), adquirido entra (+) — pra controller
  // ler a direção sem confundir. Cor verde/vermelho do EvidenceItem segue o sinal.
  const deltaSign = e.tipo === "liquidado" ? -1 : 1
  return {
    titulo:       `${acao} · ${e.cedente_nome || e.cedente_doc} → ${e.sacado_nome || e.sacado_doc}`,
    subtitle:     `${e.tipo_recebivel} · ${e.numero_documento}`,
    delta:        deltaSign * e.valor_brl,
    valorNominal: e.valor_nominal,
    flowLabel:    "Valor presente",
  }
}

// ─── Builder do bucket mtm (categoria 4.1) ───────────────────────────────────

/**
 * Bucket `mtm`: marcacao a mercado de papeis de renda fixa.
 *
 * Detecta papeis com qtd estavel (Δqtd=0) cujo valor mexeu entre D-1 e D0.
 * Sub absorve direto: papel sobe → Ativo cresce → PL Sub cresce. delta_brl
 * = Σ Δvalor_bruto (sem inversao de sinal).
 */
export function buildDriverFromMtm(mtm: MtmExplanation): DriverInput {
  const evidencias: DriverEvidence[] = mtm.evidencias.map(evidenciaFromMtm)
  const n = mtm.evidencias_total
  const sublabel = n === 1
    ? "1 papel com variação de mercado"
    : `${n} papéis com variação de mercado`
  return {
    id:          "marcacao_mercado",
    delta:       mtm.delta_brl,
    sublabel,
    evidencias,
    cosifOrigin: cosifOrigemToDriver(mtm.cosif_origin),
  }
}

function evidenciaFromMtm(e: MtmEvidencia): DriverEvidence {
  // titulo: codigo + indexador (curto pra render)
  // subtitle: emitente + vencimento — context pro auditor
  const venc = e.data_vencimento ? ` · vence ${formatBrDate(e.data_vencimento)}` : ""
  return {
    titulo:    `${e.codigo} · ${e.indexador}`,
    subtitle:  `${e.emitente}${venc}`,
    d1:        e.valor_d1,
    d0:        e.valor_d0,
    delta:     e.delta_valor,
    flowLabel: "Valor bruto",
  }
}

function formatBrDate(iso: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!m) return iso
  return `${m[3]}/${m[2]}/${m[1]}`
}

// ─── Builder do bucket remuneracao_sr_mez (categoria 5.1) ───────────────────

/**
 * Bucket `remuneracao_sr_mez`: custo diario de subordinacao.
 *
 * Cotas Senior e Mezanino valorizam pela curva contratada; Sub absorve com
 * sinal invertido (PL_Sub = Ativo - Passivo - Equity_Sr - Equity_Mez).
 * delta_brl ja vem com sinal coerente (-(ΔPL_Sr + ΔPL_Mez)) — Sub paga.
 */
export function buildDriverFromRemuneracaoSrMez(
  rem: RemuneracaoSrMezExplanation,
): DriverInput {
  const evidencias: DriverEvidence[] = rem.evidencias.map(evidenciaFromRemuneracao)
  const partes = rem.evidencias.map((e) => e.classe_label)
  const sublabel = partes.length > 0
    ? `Remuneração ${partes.join(" + ")}`
    : undefined
  return {
    id:          "remuneracao_sr_mez",
    delta:       rem.delta_brl,
    sublabel,
    evidencias,
    cosifOrigin: cosifOrigemToDriver(rem.cosif_origin),
  }
}

// ─── Builder do bucket outros (refactor 2026-05-17) ──────────────────────────

/**
 * Bucket `outros` (Nao explicado): folhas COSIF que nao casaram com nenhum
 * mapping. Em regime estavel deve ser zero. Quando aparece, lista folhas
 * COSIF cruas pra o usuario revisar e o engenheiro adicionar em
 * `cosif_to_bucket.py`. Sem evidencias enriquecidas (por definicao).
 */
export function buildDriverFromOutros(outros: OutrosExplanation): DriverInput {
  return {
    id:           "outros",
    delta:        outros.delta_brl,
    sublabel:     outros.cosif_origin.length === 1
      ? "1 conta COSIF sem mapping"
      : `${outros.cosif_origin.length} contas COSIF sem mapping`,
    narrative:    outros.narrative,
    unexplained:  true,
    cosifOrigin:  cosifOrigemToDriver(outros.cosif_origin),
  }
}

function evidenciaFromSaldoTesouraria(e: SaldoTesourariaEvidencia): DriverEvidence {
  // Shape generico de "composicao de saldo" — usado por Tesouraria (1 conta),
  // Fundos DI (1 fundo externo), Compromissada (1 operacao). Subtitle deduz a
  // origem pela `fonte` da evidencia.
  const fonteLabel =
    e.fonte === "wh_saldo_conta_corrente"
      ? `Conta corrente${e.codigo ? ` · ${e.codigo}` : ""}`
      : e.fonte === "wh_posicao_cota_fundo"
        ? "Fundo externo"
        : e.fonte === "wh_posicao_compromissada"
          ? `Operação compromissada${e.codigo ? ` · ${e.codigo}` : ""}`
          : "Tesouraria QiTech"
  return {
    titulo:    e.descricao,
    subtitle:  fonteLabel,
    d1:        e.valor_d_prev,
    d0:        e.valor_d0,
    delta:     e.delta,
    flowLabel: "Saldo",
  }
}

function evidenciaFromApropriacaoDc(e: ApropriacaoDcEvidencia): DriverEvidence {
  // Estoques (a_vencer/vencidos): mostram d_prev → d_0 + delta.
  // Aquisicoes/Liquidacoes: mostram apenas o valor (sem d_prev/d_0).
  const isEstoque = e.bloco === "a_vencer" || e.bloco === "vencidos"
  const subtitle = isEstoque
    ? `${e.fonte} · ΔEstoque`
    : e.bloco === "aquisicoes"
      ? "Saída de caixa (entrada de DC) · com sinal negativo"
      : "Entrada de caixa (saída de DC) · com sinal positivo"
  return {
    titulo:    e.label,
    subtitle,
    d1:        isEstoque ? e.valor_d_prev : null,
    d0:        isEstoque ? e.valor_d0 : null,
    delta:     e.valor_brl,
    flowLabel: isEstoque ? "Estoque" : "Valor",
  }
}

function evidenciaFromRemuneracao(e: RemuneracaoSrMezEvidencia): DriverEvidence {
  // Subtitle: rendimento em pp + valor da cota antes/depois pra auditoria.
  const ppAbs = Math.abs(e.delta_pct * 100).toFixed(4).replace(".", ",")
  const sinal = e.delta_pl > 0 ? "+" : e.delta_pl < 0 ? "−" : ""
  const cotaD1 = e.valor_cota_d1.toFixed(8).replace(".", ",")
  const cotaD0 = e.valor_cota_d0.toFixed(8).replace(".", ",")
  return {
    titulo:    e.classe_label,
    subtitle:  `Rendimento ${sinal}${ppAbs}% · cota ${cotaD1} → ${cotaD0}`,
    d1:        e.pl_d1,
    d0:        e.pl_d0,
    delta:     e.impacto_pl_sub,
    flowLabel: "PL classe",
  }
}


// ─── Builder unificado pra drivers do metodo gestor (Fase 4c, 2026-05-19) ───
//
// Substitui os builders 1-por-bucket COSIF (buildDriverFromPdd,
// buildDriverFromMovimentoCarteira, etc.) por um unico que consome o
// DriverResultOut canonico de /variacao-diaria. Cada driver:
//   - mapeia metric_global_id -> BridgeCategoryId (parte final do dotted id)
//   - usa valor_brl como delta
//   - detecta qual campo de evidencia esta populado (5 tipos: PDD, MtM, CPR,
//     Remuneracao, MovimentoCarteira) e renderiza com o conversor
//     correspondente
//
// Drivers sem evidencia rica (Fundos DI, Compromissada, Tesouraria, etc.)
// mostram so o numero — formula descritiva ja vive em formula_description.

/** Extrai `<tail>` de `controladoria.cota_sub.driver.<tail>`. */
function categoryIdFromMetric(metricGlobalId: string): BridgeCategoryId {
  const parts = metricGlobalId.split(".")
  return (parts[parts.length - 1] || "outros_ativos") as BridgeCategoryId
}

export function buildDriverFromDriverResultOut(d: DriverResultOut): DriverInput {
  const id = categoryIdFromMetric(d.metric_global_id)

  // Detecta evidencias populadas + monta sublabel.
  // Apropriacao DC tem 2 campos populados (apropriacao_dc_evidencias E
  // movimento_carteira_evidencias). O 1o e composicao do calculo (Σ =
  // valor_brl); o 2o e atividade do dia (informacional). Renderizamos
  // o 1o como evidencias principais e o 2o como operationalEvents (sub-secao).
  let evidencias: DriverEvidence[] = []
  let operationalEvents: OperationalEvent[] = []
  let sublabel: string | undefined

  if (d.pdd_evidencias.length > 0) {
    evidencias = d.pdd_evidencias.map(evidenciaFromPdd)
    const n = d.pdd_evidencias.length
    sublabel = n === 1 ? "1 papel com variação de PDD" : `${n} papéis com variação de PDD`
  } else if (d.mtm_evidencias.length > 0) {
    evidencias = d.mtm_evidencias.map(evidenciaFromMtm)
    const n = d.mtm_evidencias.length
    sublabel = n === 1 ? "1 papel com variação de mercado" : `${n} papéis com variação de mercado`
  } else if (d.cpr_evidencias.length > 0) {
    evidencias = d.cpr_evidencias.map((e) => evidenciaFromCpr(e, "Apropriação"))
    const n = d.cpr_evidencias.length
    sublabel = n === 1 ? "1 apropriação" : `${n} apropriações`
  } else if (d.remuneracao_evidencias.length > 0) {
    evidencias = d.remuneracao_evidencias.map(evidenciaFromRemuneracao)
    sublabel = "Custo de subordinação"
  } else if (d.apropriacao_dc_evidencias.length > 0) {
    // Composicao do calculo (Σ = valor_brl). `movimento_carteira_evidencias`
    // continua disponivel no payload pra eventual uso futuro (drill-down,
    // export), mas NAO renderizamos como sub-secao — polui muito a analise
    // (até 20 papeis adquiridos/liquidados, decisao Ricardo 2026-05-19).
    evidencias = d.apropriacao_dc_evidencias.map(evidenciaFromApropriacaoDc)
    sublabel = "ΔEstoque − Aquisições + Liquidações"
  } else if (d.movimento_carteira_evidencias.length > 0) {
    // Fallback legado — driver Apropriacao DC sem apropriacao_dc_evidencias
    // (shouldn't happen apos refactor 2026-05-19).
    evidencias = d.movimento_carteira_evidencias.map(evidenciaFromMovimentoCarteira)
    const n = d.movimento_carteira_evidencias.length
    sublabel = n === 1 ? "1 papel movimentado" : `${n} papéis movimentados`
  } else if (d.saldo_tesouraria_evidencias.length > 0) {
    evidencias = d.saldo_tesouraria_evidencias.map(evidenciaFromSaldoTesouraria)
    const n = d.saldo_tesouraria_evidencias.length
    // Shape generico — sublabel adapta ao tipo predominante de fonte.
    const isFundos = d.saldo_tesouraria_evidencias.every(
      (ev) => ev.fonte === "wh_posicao_cota_fundo",
    )
    const isCompromissada = d.saldo_tesouraria_evidencias.every(
      (ev) => ev.fonte === "wh_posicao_compromissada",
    )
    if (isFundos) {
      sublabel = n === 1 ? "1 fundo" : `${n} fundos`
    } else if (isCompromissada) {
      sublabel = n === 1 ? "1 operação" : `${n} operações`
    } else {
      sublabel = n === 1 ? "1 conta" : `${n} contas`
    }
  }

  // Fallback de sublabel pra drivers sem evidencia rica: usar a formula
  // descritiva do catalog (ex.: "dPosicao − caixa do dia").
  if (!sublabel && d.formula_description) {
    sublabel = d.formula_description
  }

  return {
    id,
    delta: d.valor_brl,
    sublabel,
    evidencias,
    operationalEvents: operationalEvents.length > 0 ? operationalEvents : undefined,
    // Driver indeterminado por dado: marca como placeholder (ainda nao
    // computado por falta de fonte) — UI mostra "Em construcao".
    placeholder: d.indeterminado_por_dado,
    // Driver implementado mas dia trivial (sem evento) — UI mostra
    // "Sem movimentacao no dia". Se evidencias estao indisponiveis por
    // dado upstream ausente (evidencias_indisponiveis_motivo), NAO marca
    // como empty — driver tem valor_brl real, so o granular faltou.
    empty:
      !d.indeterminado_por_dado
      && d.valor_brl === 0
      && evidencias.length === 0
      && !d.evidencias_indisponiveis_motivo,
    evidenciasIndisponiveisMotivo: d.evidencias_indisponiveis_motivo ?? undefined,
  }
}
