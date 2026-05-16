"use client"

/**
 * DriversCard — rail direito do split. Lista 4 categorias de variacao
 * ordenadas por |delta|, com expand individual mostrando narrativa +
 * evidencias.
 *
 * Categorias canonicas (CLAUDE.md alinhada com AnaliseVariacaoCard.tsx):
 *   - fluxo_caixa (aporte/resgate)         — emerald
 *   - movimento_carteira (liq/aquisicao)   — blue
 *   - eventos_contabeis (PDD/diferimento)  — violet
 *   - marcacao_mercado                     — amber
 *
 * Hoje so PDD tem dado real. Demais entram com "Em construcao" — mantemos
 * a coluna na lista para consistencia com o BridgeCard.
 */

import * as React from "react"
import {
  RiArrowDownSLine,
  RiArrowUpSLine,
  RiBankCardLine,
  RiBriefcaseLine,
  RiFileList3Line,
  RiLineChartLine,
} from "@remixicon/react"
import type { ComponentType } from "react"

import { cx, focusRing } from "@/lib/utils"
import type {
  ApropriacaoExplanation,
  DiferimentoExplanation,
  EvidenciaCprLinha,
  PddEvidencia,
  PddExplanation,
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
  id:       Exclude<BridgeCategoryId, "outros">
  label:    string
  icon:     ComponentType<{ className?: string }>
  iconCls:  string
  bgCls:    string
  barHex:   string
}

const CATEGORY_META: readonly CategoryMeta[] = [
  {
    id:      "fluxo_caixa",
    label:   "Fluxo de caixa do cotista",
    icon:    RiBankCardLine,
    iconCls: "text-emerald-600 dark:text-emerald-400",
    bgCls:   "bg-emerald-50 dark:bg-emerald-500/10",
    barHex:  "#10B981",
  },
  {
    id:      "movimento_carteira",
    label:   "Movimento de carteira",
    icon:    RiBriefcaseLine,
    iconCls: "text-blue-600 dark:text-blue-400",
    bgCls:   "bg-blue-50 dark:bg-blue-500/10",
    barHex:  "#3B82F6",
  },
  {
    id:      "eventos_contabeis",
    label:   "Eventos contábeis",
    icon:    RiFileList3Line,
    iconCls: "text-violet-600 dark:text-violet-400",
    bgCls:   "bg-violet-50 dark:bg-violet-500/10",
    barHex:  "#8B5CF6",
  },
  {
    id:      "marcacao_mercado",
    label:   "Marcação a mercado",
    icon:    RiLineChartLine,
    iconCls: "text-amber-600 dark:text-amber-400",
    bgCls:   "bg-amber-50 dark:bg-amber-500/10",
    barHex:  "#F59E0B",
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

export type DriverInput = {
  id:          Exclude<BridgeCategoryId, "outros">
  /** Delta R$ na categoria. 0 quando placeholder. */
  delta:       number
  /** Sublabel curta da categoria no estado colapsado. */
  sublabel?:   string
  /** Narrativa que aparece quando expandido. Vazia => default da categoria. */
  narrative?:  string
  /** Evidencias detalhadas (so PDD hoje). */
  evidencias?: DriverEvidence[]
  /** Quando true, categoria fica "Em construcao". */
  placeholder?: boolean
}

export type DriversCardProps = {
  drivers: DriverInput[]
  /** Base para conversao R$ -> pp (geralmente PL Cota Sub D-1). */
  base?:   number
}

export function DriversCard({ drivers, base }: DriversCardProps) {
  const driverById = new Map(drivers.map((d) => [d.id, d]))
  const allFour = CATEGORY_META.map((m) => {
    const d = driverById.get(m.id)
    return {
      meta:        m,
      input:       d,
      delta:       d?.delta ?? 0,
      placeholder: d?.placeholder ?? !d,
    }
  })

  const sorted = [...allFour].sort((a, b) => {
    // Placeholders sempre vao para o fim, demais por |delta| desc.
    if (a.placeholder && !b.placeholder) return 1
    if (!a.placeholder && b.placeholder) return -1
    return Math.abs(b.delta) - Math.abs(a.delta)
  })

  const maxAbs = Math.max(...sorted.map((d) => Math.abs(d.delta)), 1)

  const firstNonPlaceholder = sorted.findIndex((d) => !d.placeholder)
  const [expandedId, setExpandedId] = React.useState<BridgeCategoryId | null>(
    firstNonPlaceholder >= 0 ? sorted[firstNonPlaceholder].meta.id : null,
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
          4 categorias · ordenadas por impacto
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
            base={base}
            maxAbs={maxAbs}
            firstInList={i === 0}
            expanded={expandedId === d.meta.id}
            onToggle={() =>
              setExpandedId((curr) => (curr === d.meta.id ? null : d.meta.id))
            }
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
  base,
  maxAbs,
  firstInList,
  expanded,
  onToggle,
}: {
  meta:        CategoryMeta
  input?:      DriverInput
  delta:       number
  placeholder: boolean
  base?:       number
  maxAbs:      number
  firstInList: boolean
  expanded:    boolean
  onToggle:    () => void
}) {
  const Icon = meta.icon
  const barPct = (Math.abs(delta) / maxAbs) * 100
  const deltaCls = placeholder
    ? "text-gray-400 dark:text-gray-600"
    : delta >= 0
      ? "text-emerald-700 dark:text-emerald-400"
      : "text-rose-700 dark:text-rose-400"

  const sublabel = placeholder
    ? "Em construção"
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
              {placeholder
                ? "—"
                : `${delta > 0 ? "+" : ""}${fmtBRL.format(delta)}`}
            </span>
          </div>
          <div className="mt-0.5 flex items-baseline gap-2">
            <span
              className={cx(
                "min-w-0 flex-1 truncate text-[11.5px]",
                placeholder
                  ? "italic text-gray-400 dark:text-gray-600"
                  : "text-gray-500 dark:text-gray-400",
              )}
            >
              {sublabel}
            </span>
            <span className="shrink-0 text-[11px] tabular-nums text-gray-500 dark:text-gray-400">
              {placeholder ? "—" : fmtPp(delta, base ?? 0)}
            </span>
          </div>
          {/* Mini bar */}
          <div className="mt-2 h-1 overflow-hidden rounded-sm bg-gray-100 dark:bg-gray-800">
            <div
              className="h-full"
              style={{
                width:      `${Math.max(barPct, placeholder ? 0 : 2)}%`,
                background: placeholder ? "#D1D5DB" : meta.barHex,
                opacity:    placeholder ? 0.45 : 0.85,
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
          style={{ borderLeftColor: placeholder ? "#D1D5DB" : meta.barHex }}
        >
          <p className="text-[12px] leading-[1.5] text-gray-700 dark:text-gray-300">
            {input?.narrative ?? (placeholder
              ? "Detector heurístico desta categoria ainda não foi entregue. Aguarda o backend implementar o explainer dedicado em `cota_sub_explainers.py`."
              : defaultNarrative(meta.id))}
          </p>

          {input?.evidencias && input.evidencias.length > 0 && (
            <ul className="mt-2.5 flex flex-col gap-2">
              {input.evidencias.map((e, i) => (
                <EvidenceItem key={i} ev={e} />
              ))}
            </ul>
          )}
        </div>
      )}
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
    case "fluxo_caixa":        return "Aporte ou resgate na classe Subordinada"
    case "movimento_carteira": return "Liquidação e aquisição de papéis"
    case "eventos_contabeis":  return "PDD, diferimento e apropriações"
    case "marcacao_mercado":   return "Variação técnica sem movimento de quantidade"
  }
}
function defaultNarrative(id: CategoryMeta["id"]): string {
  switch (id) {
    case "fluxo_caixa":        return "Aporte ou resgate na classe Subordinada — altera diretamente o PL Sub."
    case "movimento_carteira": return "Diferença entre liquidações e aquisições do dia — reflete o resultado financeiro do giro de carteira."
    case "eventos_contabeis":  return "Constituição ou reversão de PDD, apropriação de diferimentos e despesas contábeis."
    case "marcacao_mercado":   return "Variação técnica de papéis com quantidade inalterada — geralmente movimento de curva."
  }
}

// ─── Helpers para o EventosDiaTab montar o input do bucket eventos_contabeis ─

export function buildDriverFromPdd(pdd: PddExplanation): DriverInput {
  return {
    id:         "eventos_contabeis",
    delta:      pdd.delta_brl,
    sublabel:   pdd.evidencias_total === 1
      ? "1 papel impactado por PDD"
      : `${pdd.evidencias_total} papéis impactados por PDD`,
    // narrative omitida: o resumo do backend ("PDD aumentou em N papeis,
    // impacto liquido de R$ X") repete o header do card. Cai no default
    // da categoria, que e mais generico ("Constituicao ou reversao de PDD...").
    evidencias: pdd.evidencias.map(evidenciaFromPdd),
  }
}

/**
 * Empilha PDD + Diferimento + Apropriacao no bucket unico `eventos_contabeis`.
 * Soma deltas, agrega evidencias por categoria com prefixo no subtitle, monta
 * sublabel composta. Quando so PDD existe, fallback pra buildDriverFromPdd
 * (preserva texto historico).
 */
export function buildDriverFromEventosContabeis(args: {
  pdd?:          PddExplanation | undefined
  diferimento?:  DiferimentoExplanation | undefined
  apropriacao?:  ApropriacaoExplanation | undefined
}): DriverInput | undefined {
  const { pdd, diferimento, apropriacao } = args
  const presentes = [pdd, diferimento, apropriacao].filter(Boolean)
  if (presentes.length === 0) return undefined
  if (presentes.length === 1 && pdd) return buildDriverFromPdd(pdd)

  const delta =
    (pdd?.delta_brl ?? 0)
    + (diferimento?.delta_brl ?? 0)
    + (apropriacao?.delta_brl ?? 0)

  const evidencias: DriverEvidence[] = [
    ...(pdd?.evidencias.map(evidenciaFromPdd) ?? []),
    ...(diferimento?.evidencias.map(
      (e) => evidenciaFromCpr(e, "Diferimento"),
    ) ?? []),
    ...(apropriacao?.evidencias.map(
      (e) => evidenciaFromCpr(e, "Apropriação"),
    ) ?? []),
  ]

  // Sublabel: composicao curta, ex.: "13 papéis PDD · 5 apropriações · 3 diferimentos"
  const partes: string[] = []
  if (pdd) {
    partes.push(
      pdd.evidencias_total === 1
        ? "1 papel PDD"
        : `${pdd.evidencias_total} papéis PDD`,
    )
  }
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

  return {
    id:         "eventos_contabeis",
    delta,
    sublabel:   partes.join(" · "),
    evidencias,
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
