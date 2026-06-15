"use client"

// FinancialTable — par canonico de tabelas financeiras IBCS-style.
//
// Dois componentes irmaos sobre um nucleo compartilhado, construidos a partir
// dos primitivos `Table` do Tremor (CLAUDE.md §1/§3, linhagem DenseTable.Series):
//
//   - <PeriodComparisonTable>  — IBCS T01/T02: dimensoes nas linhas, cenarios
//     (PY/PL/AC/FC) nas colunas, blocos de periodo (mes | YTD), colunas de
//     variancia (AC-PY, (AC-PY)%) em texto ou barra inline.
//   - <DecompositionTable>     — IBCS T03/T04: esquema de calculo nas linhas
//     (+/−/=), subtotais com regua pesada, reconciliacao automatica (§14.6),
//     colapso de cauda em "Outros (N)" sem nunca cortar linhas.
//
// Gramatica IBCS encodada (templates T01–T04, ibcs.com):
//   1. Unidade declarada UMA vez no titulo ("em R$ mil"), nunca por celula.
//   2. Cenario tem identidade visual fixa: barra sob o header — AC solida
//      escura, PY solida cinza, PL/BU vazada, FC hachurada.
//   3. Variancia nomeada pela formula ("AC-PY"), nao "Δ" generico.
//   4. Cor e exclusiva da variancia (valores ficam neutros) — mesma convencao
//      do KpiBand (emerald positivo / red negativo).
//   5. Polaridade de impacto: linha de custo com Δ+ pinta vermelho (linhas
//      com op "-" sao custo por default).
//   6. Anotacoes numeradas ① ligando linha a comentario no rodape.

import * as React from "react"

import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRoot,
  TableRow,
} from "@/components/tremor/Table"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

// ─────────────────────────────────────────────────────────────────────────────
// Vocabulario compartilhado
// ─────────────────────────────────────────────────────────────────────────────

/** Cenarios IBCS. PL e BU sao sinonimos visuais (barra vazada). */
export type Scenario = "AC" | "PY" | "PL" | "BU" | "FC"

export type Polarity = "revenue" | "cost"

export type RowEmphasis = "subtotal" | "total"

export type FinancialTableTitle = {
  /** Entidade dona do numero (ex.: "REALINVEST FIDC"). */
  entity?: string
  /** Metrica apresentada (ex.: "Volume operado"). */
  measure: string
  /** Unidade declarada UMA vez (IBCS) — ex.: "R$ mil". */
  unit?: string
  /** Declaracao de cenarios/periodo (ex.: "2026 PY, AC"). */
  note?: string
}

export type FinancialTableAnnotation = {
  ref: number
  text: React.ReactNode
}

export type VarianceMode = "none" | "abs" | "pct" | "abs+pct"
export type VarianceStyle = "text" | "bars"

const SCENARIO_TOOLTIP: Record<Scenario, string> = {
  AC: "Realizado (actual)",
  PY: "Período anterior (previous year)",
  PL: "Planejado (plan)",
  BU: "Orçado (budget)",
  FC: "Projetado (forecast)",
}

/** Prioridade de quem e o cenario "comparado" nas variancias derivadas. */
const MINUEND_RANK: Scenario[] = ["AC", "FC", "PL", "BU"]

function deriveVariancePairs(
  scenarios: Scenario[],
): Array<[Scenario, Scenario]> {
  if (scenarios.length < 2) return []
  const minuend =
    MINUEND_RANK.find((s) => scenarios.includes(s)) ??
    scenarios[scenarios.length - 1]
  return scenarios
    .filter((s) => s !== minuend)
    .map((ref) => [minuend, ref] as [Scenario, Scenario])
}

// ─────────────────────────────────────────────────────────────────────────────
// Formatacao
// ─────────────────────────────────────────────────────────────────────────────

function fmtNum(v: number, decimals: number): string {
  return v.toLocaleString("pt-BR", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

function fmtSigned(v: number, decimals: number): string {
  return `${v > 0 ? "+" : ""}${fmtNum(v, decimals)}`
}

function fmtSignedPct(v: number, decimals: number): string {
  if (!Number.isFinite(v)) return "n/a"
  return `${v > 0 ? "+" : ""}${fmtNum(v, decimals)}%`
}

function isMissing(v: number | null | undefined): v is null | undefined {
  return v === null || v === undefined || Number.isNaN(v)
}

/** Impacto da variancia: bom (emerald) ou ruim (red), pela polaridade da linha. */
function impactClass(value: number, polarity: Polarity): string {
  const good = polarity === "cost" ? value <= 0 : value >= 0
  return good
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-red-600 dark:text-red-400"
}

function impactBarClass(value: number, polarity: Polarity): string {
  const good = polarity === "cost" ? value <= 0 : value >= 0
  return good ? "bg-emerald-500" : "bg-red-500"
}

// ─────────────────────────────────────────────────────────────────────────────
// Nucleo visual compartilhado (nao exportado)
// ─────────────────────────────────────────────────────────────────────────────

/** Barra de identidade do cenario sob o header (assinatura IBCS). */
function ScenarioBar({ scenario }: { scenario: Scenario }) {
  if (scenario === "AC") {
    return <div className="mt-1 h-[4px] w-full bg-gray-900 dark:bg-gray-100" />
  }
  if (scenario === "PY") {
    return <div className="mt-1 h-[4px] w-full bg-gray-400 dark:bg-gray-600" />
  }
  if (scenario === "FC") {
    return (
      <div
        className="mt-1 h-[5px] w-full border border-gray-700 text-gray-700 dark:border-gray-300 dark:text-gray-300"
        // MOTIVO: hachura diagonal (notacao IBCS de forecast) nao e
        // expressavel em utilities Tailwind.
        style={{
          backgroundImage:
            "repeating-linear-gradient(135deg, currentColor 0 1px, transparent 1px 4px)",
        }}
      />
    )
  }
  // PL | BU — barra vazada (outline)
  return (
    <div className="mt-1 h-[5px] w-full border border-gray-700 dark:border-gray-300" />
  )
}

function ScenarioHeaderCell({
  scenario,
  dense,
}: {
  scenario: Scenario
  dense: boolean
}) {
  return (
    <TableHeaderCell
      title={SCENARIO_TOOLTIP[scenario]}
      className={cx(
        "border-b-0 text-right align-bottom",
        dense ? "px-2 py-1" : "px-2 py-1.5",
        tableTokens.header,
        "text-gray-600 dark:text-gray-300",
      )}
    >
      <span className="inline-block min-w-[40px]">
        {scenario}
        <ScenarioBar scenario={scenario} />
      </span>
    </TableHeaderCell>
  )
}

function varianceLabel(pair: [Scenario, Scenario], kind: "abs" | "pct") {
  const base = `${pair[0]}-${pair[1]}`
  return kind === "pct" ? `(${base})%` : base
}

/**
 * Header de GRUPO de variancia (IBCS): "AC-PY" unico abarcando as subcolunas
 * nominal e percentual, com linha propria varrendo o grupo inteiro — na mesma
 * altura das barras de cenario (a fronteira header/corpo e UMA linha).
 */
function VarianceGroupHeaderCell({
  pair,
  span,
  dense,
}: {
  pair: [Scenario, Scenario]
  span: number
  dense: boolean
}) {
  return (
    <TableHeaderCell
      colSpan={span}
      className={cx(
        "border-b-0 text-center align-bottom",
        dense ? "px-2 py-1" : "px-2 py-1.5",
        tableTokens.header,
        "text-gray-600 dark:text-gray-300",
      )}
    >
      <span className="inline-block w-full min-w-[40px]">
        {varianceLabel(pair, "abs")}
        <div className="mt-1 h-[2px] w-full bg-gray-900 dark:bg-gray-100" />
      </span>
    </TableHeaderCell>
  )
}

/** Segmento da fronteira header/corpo na coluna de rotulos (mesma altura
 *  das barras de cenario — a 1a linha do corpo nao tem borda propria). */
function LabelBoundaryHeaderCell({ dense }: { dense: boolean }) {
  return (
    <TableHeaderCell
      className={cx(
        "w-full border-b-0 align-bottom",
        dense ? "px-2 py-1" : "px-2 py-1.5",
      )}
    >
      <div className="mt-1 h-[2px] w-full bg-gray-900 dark:bg-gray-100" />
    </TableHeaderCell>
  )
}

/** Barra de variancia inline com eixo central (IBCS T02/T04). */
function VarianceBar({
  value,
  max,
  polarity,
  label,
}: {
  value: number
  max: number
  polarity: Polarity
  label: string
}) {
  const half = max > 0 ? Math.min((Math.abs(value) / max) * 50, 50) : 0
  return (
    <span className="inline-flex items-center justify-end gap-1.5">
      <span
        className={cx(
          "tabular-nums text-xs",
          impactClass(value, polarity),
        )}
      >
        {label}
      </span>
      <span className="relative inline-block h-[12px] w-16 shrink-0">
        {/* eixo zero */}
        <span className="absolute inset-y-0 left-1/2 w-px bg-gray-300 dark:bg-gray-600" />
        <span
          className={cx(
            "absolute top-1/2 h-[8px] -translate-y-1/2",
            impactBarClass(value, polarity),
          )}
          style={
            value >= 0
              ? { left: "50%", width: `${half}%` }
              : { right: "50%", width: `${half}%` }
          }
        />
      </span>
    </span>
  )
}

/** Celula de variancia — texto ou barra. */
function VarianceCellContent({
  minuend,
  subtrahend,
  kind,
  style,
  polarity,
  max,
  decimals,
  pctDecimals,
}: {
  minuend: number | null | undefined
  subtrahend: number | null | undefined
  kind: "abs" | "pct"
  style: VarianceStyle
  polarity: Polarity
  max: number
  decimals: number
  pctDecimals: number
}) {
  if (isMissing(minuend) || isMissing(subtrahend)) {
    return <span className={tableTokens.cellMuted}>—</span>
  }
  const diff = minuend - subtrahend
  const value =
    kind === "abs" ? diff : subtrahend === 0 ? NaN : (diff / Math.abs(subtrahend)) * 100
  const label =
    kind === "abs" ? fmtSigned(diff, decimals) : fmtSignedPct(value, pctDecimals)

  if (!Number.isFinite(value)) {
    return <span className={tableTokens.cellMuted}>n/a</span>
  }
  if (style === "bars") {
    return (
      <VarianceBar value={value} max={max} polarity={polarity} label={label} />
    )
  }
  return (
    <span className={cx("tabular-nums text-xs", impactClass(value, polarity))}>
      {label}
    </span>
  )
}

/** Referencia de anotacao numerada ① (IBCS). */
function AnnotationRef({ n }: { n: number }) {
  return (
    <span
      aria-label={`nota ${n}`}
      className="ml-1 inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border border-blue-500 align-text-top text-[9px] font-medium leading-none text-blue-600 dark:border-blue-400 dark:text-blue-400"
    >
      {n}
    </span>
  )
}

function TitleBlock({ title }: { title: FinancialTableTitle }) {
  return (
    <div className="flex flex-col gap-0.5 px-3 pb-2 pt-2.5">
      {title.entity ? (
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {title.entity}
        </span>
      ) : null}
      <span className="text-sm font-semibold text-gray-900 dark:text-gray-50">
        {title.measure}
        {title.unit ? (
          <span className="font-normal text-gray-500 dark:text-gray-400">
            {" "}
            em {title.unit}
          </span>
        ) : null}
      </span>
      {title.note ? (
        <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
          {title.note}
        </span>
      ) : null}
    </div>
  )
}

function AnnotationsBlock({
  annotations,
}: {
  annotations: FinancialTableAnnotation[]
}) {
  return (
    <div className="flex flex-col gap-1.5 border-t border-gray-200 px-3 py-2 dark:border-gray-800">
      {annotations.map((a) => (
        <div key={a.ref} className="flex items-start gap-1.5">
          <span className="mt-px inline-flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full border border-blue-500 text-[9px] font-medium leading-none text-blue-600 dark:border-blue-400 dark:text-blue-400">
            {a.ref}
          </span>
          <span className="text-[11px] leading-snug text-gray-600 dark:text-gray-400">
            {a.text}
          </span>
        </div>
      ))}
    </div>
  )
}

function Wrapper({
  bordered,
  className,
  children,
}: {
  bordered: boolean
  className?: string
  children: React.ReactNode
}) {
  return (
    <div
      className={cx(
        "overflow-hidden",
        // mesma anatomia do Card canonico do Tremor (radius 4px + shadow-xs)
        bordered &&
          "rounded border border-gray-200 bg-white shadow-xs dark:border-gray-900 dark:bg-[#090E1A]",
        className,
      )}
    >
      {children}
    </div>
  )
}

const EMPHASIS_TEXT: Record<RowEmphasis, string> = {
  subtotal: "font-medium text-gray-900 dark:text-gray-100",
  total: "font-semibold text-gray-900 dark:text-gray-100",
}

/**
 * Reguas horizontais IBCS — aplicadas CELULA a celula, nunca na <tr>.
 * A tabela usa `border-separate` + `border-spacing-x`: borda de <tr> nao
 * pinta nesse modo, e e o spacing entre celulas que segmenta cada regua
 * em trechos por coluna com respiro branco (assinatura visual do padrao).
 */
type RowRule = "none" | "light" | "subtotal" | "strong"
const RULE_CLASS: Record<RowRule, string> = {
  none: "",
  // divisoria fina entre linhas comuns (gray-200: o gray-100 era claro demais)
  light: "border-t border-t-gray-200 dark:border-t-gray-800",
  subtotal: "border-t border-t-gray-400 dark:border-t-gray-600",
  // regua forte: acima da 1a linha do corpo e acima de toda linha "="/total
  strong: "border-t-2 border-t-gray-900 dark:border-t-gray-100",
}

/**
 * Em linhas "="/total, a regua de cada coluna de CENARIO repete a identidade
 * visual da barra do header (IBCS): AC preta solida, PY cinza, PL/BU dupla,
 * FC tracejada (aproximacao da hachura num traco de 2px). Rotulos e
 * variancias usam a regua forte comum.
 */
function scenarioRuleClass(s: Scenario): string {
  // mesma espessura da barra de cenario do header (4-5px)
  switch (s) {
    case "AC":
      return "border-t-4 border-t-gray-900 dark:border-t-gray-100"
    case "PY":
      return "border-t-4 border-t-gray-400 dark:border-t-gray-600"
    case "FC":
      return "border-t-4 border-dashed border-t-gray-700 dark:border-t-gray-300"
    default: // PL | BU
      return "border-t-[5px] border-double border-t-gray-900 dark:border-t-gray-100"
  }
}

/** Layout IBCS: reguas segmentadas por coluna via border-separate + spacing. */
const TABLE_LAYOUT =
  "border-separate border-spacing-x-1.5 border-spacing-y-0 border-b-0"

/** Celula vazia que abre o respiro maior entre rotulos e colunas numericas. */
function SpacerCell({ header = false }: { header?: boolean }) {
  return header ? (
    <th aria-hidden className="w-3 border-0 p-0" />
  ) : (
    <td aria-hidden className="w-3 border-0 p-0" />
  )
}

const CELL_PAD = "px-2 py-1"
const HEADER_PAD = "px-2 py-1.5"

// ─────────────────────────────────────────────────────────────────────────────
// PeriodComparisonTable (IBCS T01 / T02)
// ─────────────────────────────────────────────────────────────────────────────

export type PeriodBlock = {
  key: string
  label: string
}

export type ComparisonRow = {
  label: string
  /** Valores por bloco -> por cenario. Com `blocks` omitido, use a chave "default". */
  values: Record<string, Partial<Record<Scenario, number | null>>>
  emphasis?: RowEmphasis
  indent?: 0 | 1
  /** "cost" inverte a semantica de impacto da variancia (IBCS). Default "revenue". */
  polarity?: Polarity
  /** Referencia ① para `annotations`. */
  annotation?: number
}

export type PeriodComparisonTableProps = {
  title?: FinancialTableTitle
  /** Cenarios nas colunas, na ordem IBCS (ex.: ["PY", "PL", "AC"]). */
  scenarios: Scenario[]
  /** Blocos de periodo lado a lado (ex.: mes | YTD). Omitido = bloco unico. */
  blocks?: PeriodBlock[]
  rows: ComparisonRow[]
  /** Colunas de variancia derivadas (AC-PY, ...). Default "abs+pct". */
  variance?: VarianceMode
  /** Variancia como texto colorido ou barra inline (T02). Default "text". */
  varianceStyle?: VarianceStyle
  decimals?: number
  pctDecimals?: number
  annotations?: FinancialTableAnnotation[]
  bordered?: boolean
  className?: string
}

const DEFAULT_BLOCK: PeriodBlock = { key: "default", label: "" }

export function PeriodComparisonTable({
  title,
  scenarios,
  blocks,
  rows,
  variance = "abs+pct",
  varianceStyle = "text",
  decimals = 0,
  pctDecimals = 0,
  annotations,
  bordered = true,
  className,
}: PeriodComparisonTableProps) {
  const effectiveBlocks = React.useMemo(
    () => (blocks && blocks.length > 0 ? blocks : [DEFAULT_BLOCK]),
    [blocks],
  )
  const showBlockRow = Boolean(blocks && blocks.length > 0 && blocks.some((b) => b.label))
  const varCols = React.useMemo(() => {
    if (variance === "none") return []
    const pairs = deriveVariancePairs(scenarios)
    const kinds: Array<"abs" | "pct"> =
      variance === "abs" ? ["abs"] : variance === "pct" ? ["pct"] : ["abs", "pct"]
    return pairs.flatMap((p) => kinds.map((k) => ({ pair: p, kind: k })))
  }, [variance, scenarios])
  const variancePairs =
    variance === "none" ? [] : deriveVariancePairs(scenarios)
  const kindsPerPair = variance === "abs+pct" ? 2 : 1
  const colsPerBlock = scenarios.length + varCols.length

  // Max |valor| por coluna de variancia (p/ escala das barras), por bloco.
  const barMax = React.useMemo(() => {
    const m = new Map<string, number>()
    if (varianceStyle !== "bars") return m
    for (const block of effectiveBlocks) {
      for (const vc of varCols) {
        let max = 0
        for (const row of rows) {
          const v = row.values[block.key]
          const a = v?.[vc.pair[0]]
          const b = v?.[vc.pair[1]]
          if (isMissing(a) || isMissing(b)) continue
          const diff = a - b
          const val =
            vc.kind === "abs" ? diff : b === 0 ? NaN : (diff / Math.abs(b)) * 100
          if (Number.isFinite(val)) max = Math.max(max, Math.abs(val))
        }
        m.set(`${block.key}:${varianceLabel(vc.pair, vc.kind)}`, max)
      }
    }
    return m
  }, [effectiveBlocks, varCols, rows, varianceStyle])

  return (
    <Wrapper bordered={bordered} className={className}>
      {title ? <TitleBlock title={title} /> : null}
      <TableRoot>
        <Table className={TABLE_LAYOUT}>
          <TableHead>
            {showBlockRow ? (
              <TableRow>
                <TableHeaderCell className={cx("w-full border-b-0", HEADER_PAD)} />
                <SpacerCell header />
                {effectiveBlocks.map((b) => (
                  <TableHeaderCell
                    key={b.key}
                    colSpan={colsPerBlock}
                    className={cx(
                      // regua forte sob o rotulo do bloco (IBCS: sob o ano)
                      "border-b-2 border-b-gray-900 text-center dark:border-b-gray-100",
                      HEADER_PAD,
                      "text-xs font-semibold text-gray-900 dark:text-gray-100",
                    )}
                  >
                    {b.label}
                  </TableHeaderCell>
                ))}
              </TableRow>
            ) : null}
            {/* fronteira header/corpo = UMA linha: segmento nos rotulos +
                barras de cenario + linha dos grupos de variancia, todos na
                mesma altura (IBCS). A 1a linha do corpo nao tem borda. */}
            <TableRow>
              <LabelBoundaryHeaderCell dense={false} />
              <SpacerCell header />
              {effectiveBlocks.map((b) => (
                <React.Fragment key={b.key}>
                  {scenarios.map((s) => (
                    <ScenarioHeaderCell key={s} scenario={s} dense={false} />
                  ))}
                  {variancePairs.map((pair) => (
                    <VarianceGroupHeaderCell
                      key={varianceLabel(pair, "abs")}
                      pair={pair}
                      span={kindsPerPair}
                      dense={false}
                    />
                  ))}
                </React.Fragment>
              ))}
            </TableRow>
          </TableHead>
          <TableBody className="divide-y-0">
            {rows.map((row, idx) => {
              const empText = row.emphasis
                ? EMPHASIS_TEXT[row.emphasis]
                : undefined
              // 1a linha do corpo SEM borda: a fronteira com o header e a
              // linha unica formada pelos segmentos do proprio header.
              const rule: RowRule =
                row.emphasis === "total"
                  ? "strong"
                  : row.emphasis === "subtotal"
                    ? "subtotal"
                    : idx === 0
                      ? "none"
                      : "light"
              const labelRuleClass = RULE_CLASS[rule]
              const valueRuleClass = RULE_CLASS[rule]
              const polarity = row.polarity ?? "revenue"
              return (
                <TableRow key={`${row.label}-${idx}`}>
                  <TableCell
                    className={cx(
                      "w-full whitespace-nowrap",
                      CELL_PAD,
                      labelRuleClass,
                      tableTokens.cellText,
                      empText,
                      row.indent === 1 && "pl-5",
                    )}
                  >
                    {row.label}
                    {row.annotation !== undefined ? (
                      <AnnotationRef n={row.annotation} />
                    ) : null}
                  </TableCell>
                  <SpacerCell />
                  {effectiveBlocks.map((b) => {
                    const v = row.values[b.key]
                    return (
                      <React.Fragment key={b.key}>
                        {scenarios.map((s) => {
                          const raw = v?.[s]
                          return (
                            <TableCell
                              key={s}
                              className={cx(
                                "text-right whitespace-nowrap",
                                CELL_PAD,
                                valueRuleClass === RULE_CLASS.strong
                                  ? scenarioRuleClass(s)
                                  : valueRuleClass,
                              )}
                            >
                              {isMissing(raw) ? (
                                <span className={tableTokens.cellMuted}>—</span>
                              ) : (
                                <span
                                  className={cx(
                                    tableTokens.cellNumber,
                                    empText,
                                  )}
                                >
                                  {fmtNum(raw, decimals)}
                                </span>
                              )}
                            </TableCell>
                          )
                        })}
                        {varCols.map((vc) => (
                          <TableCell
                            key={varianceLabel(vc.pair, vc.kind)}
                            className={cx(
                              "text-right whitespace-nowrap",
                              CELL_PAD,
                              valueRuleClass,
                            )}
                          >
                            <VarianceCellContent
                              minuend={v?.[vc.pair[0]]}
                              subtrahend={v?.[vc.pair[1]]}
                              kind={vc.kind}
                              style={varianceStyle}
                              polarity={polarity}
                              max={
                                barMax.get(
                                  `${b.key}:${varianceLabel(vc.pair, vc.kind)}`,
                                ) ?? 0
                              }
                              decimals={decimals}
                              pctDecimals={pctDecimals}
                            />
                          </TableCell>
                        ))}
                      </React.Fragment>
                    )
                  })}
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </TableRoot>
      {annotations && annotations.length > 0 ? (
        <AnnotationsBlock annotations={annotations} />
      ) : null}
    </Wrapper>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// DecompositionTable (IBCS T03 / T04)
// ─────────────────────────────────────────────────────────────────────────────

export type DecompositionRow = {
  /** Esquema de calculo IBCS. "=" e subtotal/total (bold + regua). Default "+". */
  op?: "+" | "-" | "="
  label: string
  /** Numero simples (cenario unico) ou valores por cenario. */
  values: number | Partial<Record<Scenario, number | null>>
  /** Default: "cost" quando op === "-", senao "revenue". */
  polarity?: Polarity
  annotation?: number
  indent?: 0 | 1
}

export type DecompositionTableProps = {
  title?: FinancialTableTitle
  /** Default ["AC"] (coluna unica de realizado). */
  scenarios?: Scenario[]
  rows: DecompositionRow[]
  variance?: VarianceMode
  varianceStyle?: VarianceStyle
  /**
   * Colapsa caudas longas de itens consecutivos em "Outros (N) · valor"
   * com expand — NUNCA corta linhas (§14.6: a soma visivel = o total).
   */
  collapseAfter?: number
  /**
   * Valida cada linha "=" contra a soma corrente das linhas +/− anteriores
   * (no primeiro cenario). Divergencia exibe chip "resíduo" (§14.6). Default true.
   */
  reconcile?: boolean
  decimals?: number
  pctDecimals?: number
  annotations?: FinancialTableAnnotation[]
  bordered?: boolean
  className?: string
}

type NormalizedRow = Omit<DecompositionRow, "values" | "polarity"> & {
  values: Partial<Record<Scenario, number | null>>
  polarity: Polarity
}

type DisplayRow =
  | { kind: "row"; row: NormalizedRow }
  | {
      kind: "outros"
      label: string
      values: Partial<Record<Scenario, number | null>>
      polarity: Polarity
      count: number
      groupId: number
    }
  | { kind: "toggle"; groupId: number; expanded: boolean; count: number }

function normalizeRows(
  rows: DecompositionRow[],
  scenarios: Scenario[],
): NormalizedRow[] {
  const primary = scenarios[0]
  return rows.map((r) => ({
    ...r,
    values: typeof r.values === "number" ? { [primary]: r.values } : r.values,
    polarity: r.polarity ?? (r.op === "-" ? "cost" : "revenue"),
  }))
}

export function DecompositionTable({
  title,
  scenarios = ["AC"],
  rows,
  variance = "abs+pct",
  varianceStyle = "text",
  collapseAfter,
  reconcile = true,
  decimals = 0,
  pctDecimals = 0,
  annotations,
  bordered = true,
  className,
}: DecompositionTableProps) {
  const normalized = React.useMemo(
    () => normalizeRows(rows, scenarios),
    [rows, scenarios],
  )
  const primary = scenarios[0]
  const hasScheme = normalized.some((r) => r.op === "=")
  const varCols = React.useMemo(() => {
    if (variance === "none") return []
    const pairs = deriveVariancePairs(scenarios)
    const kinds: Array<"abs" | "pct"> =
      variance === "abs" ? ["abs"] : variance === "pct" ? ["pct"] : ["abs", "pct"]
    return pairs.flatMap((p) => kinds.map((k) => ({ pair: p, kind: k })))
  }, [variance, scenarios])
  const variancePairs =
    variance === "none" ? [] : deriveVariancePairs(scenarios)
  const kindsPerPair = variance === "abs+pct" ? 2 : 1

  const [expanded, setExpanded] = React.useState<Record<number, boolean>>({})

  // Reconciliacao §14.6: soma corrente das linhas +/− vs cada linha "=".
  const residuals = React.useMemo(() => {
    const map = new Map<number, number>()
    if (!reconcile || !hasScheme) return map
    let running = 0
    normalized.forEach((r, i) => {
      const v = r.values[primary]
      if (isMissing(v)) return
      if (r.op === "=") {
        const diff = running - v
        const tol = Math.max(0.02, Math.abs(v) * 1e-6)
        if (Math.abs(diff) > tol) map.set(i, diff)
        running = v // a partir do subtotal declarado, o calculo continua dele
      } else if (r.op === "-") {
        running -= v
      } else {
        running += v
      }
    })
    return map
  }, [normalized, primary, reconcile, hasScheme])

  // Colapso de cauda: grupos consecutivos de linhas nao-"=" maiores que
  // collapseAfter viram primeiras N + "Outros (M) · soma" + toggle.
  const displayRows = React.useMemo<Array<DisplayRow & { srcIndex?: number }>>(() => {
    if (!collapseAfter || collapseAfter < 1) {
      return normalized.map((row, i) => ({ kind: "row" as const, row, srcIndex: i }))
    }
    const out: Array<DisplayRow & { srcIndex?: number }> = []
    let group: Array<{ row: NormalizedRow; srcIndex: number }> = []
    let groupId = 0

    const flush = () => {
      if (group.length === 0) return
      const id = groupId++
      if (group.length <= collapseAfter + 1) {
        // +1: nao vale colapsar 1 linha so em "Outros (1)"
        group.forEach((g) =>
          out.push({ kind: "row", row: g.row, srcIndex: g.srcIndex }),
        )
      } else if (expanded[id]) {
        group.forEach((g) =>
          out.push({ kind: "row", row: g.row, srcIndex: g.srcIndex }),
        )
        out.push({
          kind: "toggle",
          groupId: id,
          expanded: true,
          count: group.length,
        })
      } else {
        const head = group.slice(0, collapseAfter)
        const tail = group.slice(collapseAfter)
        head.forEach((g) =>
          out.push({ kind: "row", row: g.row, srcIndex: g.srcIndex }),
        )
        const sums: Partial<Record<Scenario, number | null>> = {}
        for (const s of scenarios) {
          let acc = 0
          let any = false
          for (const g of tail) {
            const v = g.row.values[s]
            if (isMissing(v)) continue
            any = true
            acc += g.row.op === "-" ? -v : v
          }
          sums[s] = any ? acc : null
        }
        out.push({
          kind: "outros",
          label: `Outros (${tail.length})`,
          values: sums,
          polarity: tail[0]?.row.polarity ?? "revenue",
          count: tail.length,
          groupId: id,
        })
      }
      group = []
    }

    normalized.forEach((row, i) => {
      if (row.op === "=") {
        flush()
        out.push({ kind: "row", row, srcIndex: i })
      } else {
        group.push({ row, srcIndex: i })
      }
    })
    flush()
    return out
  }, [normalized, collapseAfter, expanded, scenarios])

  // Max p/ barras de variancia (sobre as linhas exibidas).
  const barMax = React.useMemo(() => {
    const m = new Map<string, number>()
    if (varianceStyle !== "bars") return m
    for (const vc of varCols) {
      let max = 0
      for (const d of displayRows) {
        const values =
          d.kind === "row" ? d.row.values : d.kind === "outros" ? d.values : null
        if (!values) continue
        const a = values[vc.pair[0]]
        const b = values[vc.pair[1]]
        if (isMissing(a) || isMissing(b)) continue
        const diff = a - b
        const val =
          vc.kind === "abs" ? diff : b === 0 ? NaN : (diff / Math.abs(b)) * 100
        if (Number.isFinite(val)) max = Math.max(max, Math.abs(val))
      }
      m.set(varianceLabel(vc.pair, vc.kind), max)
    }
    return m
  }, [displayRows, varCols, varianceStyle])

  // label + spacer + cenarios + variancias
  const totalCols = 2 + scenarios.length + varCols.length

  const renderValueCells = (
    values: Partial<Record<Scenario, number | null>>,
    polarity: Polarity,
    ruleClass: string,
    emphasisText?: string,
    srcIndex?: number,
  ) => (
    <>
      {scenarios.map((s, si) => {
        const raw = values[s]
        const residual =
          si === 0 && srcIndex !== undefined ? residuals.get(srcIndex) : undefined
        return (
          <TableCell
            key={s}
            className={cx(
              "text-right whitespace-nowrap",
              CELL_PAD,
              ruleClass === RULE_CLASS.strong ? scenarioRuleClass(s) : ruleClass,
            )}
          >
            {isMissing(raw) ? (
              <span className={tableTokens.cellMuted}>—</span>
            ) : (
              <span className="inline-flex items-center gap-1">
                {residual !== undefined ? (
                  <span
                    title={`Linhas exibidas somam ${fmtNum(raw + residual, decimals)} — resíduo de ${fmtSigned(residual, decimals)} vs o valor declarado (§14.6).`}
                    className={cx(
                      tableTokens.badge,
                      "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-400",
                    )}
                  >
                    resíduo {fmtSigned(residual, decimals)}
                  </span>
                ) : null}
                <span className={cx(tableTokens.cellNumber, emphasisText)}>
                  {fmtNum(raw, decimals)}
                </span>
              </span>
            )}
          </TableCell>
        )
      })}
      {varCols.map((vc) => (
        <TableCell
          key={varianceLabel(vc.pair, vc.kind)}
          className={cx("text-right whitespace-nowrap", CELL_PAD, ruleClass)}
        >
          <VarianceCellContent
            minuend={values[vc.pair[0]]}
            subtrahend={values[vc.pair[1]]}
            kind={vc.kind}
            style={varianceStyle}
            polarity={polarity}
            max={barMax.get(varianceLabel(vc.pair, vc.kind)) ?? 0}
            decimals={decimals}
            pctDecimals={pctDecimals}
          />
        </TableCell>
      ))}
    </>
  )

  return (
    <Wrapper bordered={bordered} className={className}>
      {title ? <TitleBlock title={title} /> : null}
      <TableRoot>
        <Table className={TABLE_LAYOUT}>
          {scenarios.length > 1 || varCols.length > 0 ? (
            <TableHead>
              {/* fronteira header/corpo = linha unica de segmentos do header
                  (rotulos + barras de cenario + grupos de variancia) */}
              <TableRow>
                <LabelBoundaryHeaderCell dense />
                <SpacerCell header />
                {scenarios.map((s) => (
                  <ScenarioHeaderCell key={s} scenario={s} dense />
                ))}
                {variancePairs.map((pair) => (
                  <VarianceGroupHeaderCell
                    key={varianceLabel(pair, "abs")}
                    pair={pair}
                    span={kindsPerPair}
                    dense
                  />
                ))}
              </TableRow>
            </TableHead>
          ) : null}
          <TableBody className="divide-y-0">
            {displayRows.map((d, idx) => {
              const hasHeader = scenarios.length > 1 || varCols.length > 0
              const isEqualsRow = d.kind === "row" && d.row.op === "="
              // Com header, a fronteira e a linha de segmentos do proprio
              // header — 1a linha do corpo sem borda. Sem header, a regua
              // forte abre a tabela.
              const rule: RowRule = isEqualsRow
                ? "strong"
                : idx === 0
                  ? hasHeader
                    ? "none"
                    : "strong"
                  : "light"
              const ruleClass = RULE_CLASS[rule]
              const valueRuleClass = ruleClass
              if (d.kind === "toggle") {
                return (
                  <tr key={`toggle-${d.groupId}`}>
                    <td
                      colSpan={totalCols}
                      className={cx(CELL_PAD, "text-left", ruleClass)}
                    >
                      <button
                        type="button"
                        onClick={() =>
                          setExpanded((e) => ({ ...e, [d.groupId]: false }))
                        }
                        className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
                      >
                        Recolher
                      </button>
                    </td>
                  </tr>
                )
              }
              if (d.kind === "outros") {
                return (
                  <TableRow key={`outros-${d.groupId}`}>
                    <TableCell
                      className={cx("w-full whitespace-nowrap", CELL_PAD, ruleClass)}
                    >
                      {hasScheme ? (
                        <span className="mr-1 inline-block w-2.5 text-gray-400 dark:text-gray-600">
                          +
                        </span>
                      ) : null}
                      <span className={tableTokens.cellSecondary}>{d.label}</span>
                      <button
                        type="button"
                        onClick={() =>
                          setExpanded((e) => ({ ...e, [d.groupId]: true }))
                        }
                        className="ml-2 text-xs font-medium text-blue-600 hover:underline dark:text-blue-400"
                      >
                        Mostrar todos
                      </button>
                    </TableCell>
                    <SpacerCell />
                    {renderValueCells(d.values, d.polarity, valueRuleClass)}
                  </TableRow>
                )
              }
              const { row } = d
              const isEquals = row.op === "="
              const empText = isEquals ? EMPHASIS_TEXT.total : undefined
              return (
                <TableRow key={`${row.label}-${idx}`}>
                  <TableCell
                    className={cx(
                      "w-full whitespace-nowrap",
                      CELL_PAD,
                      ruleClass,
                      tableTokens.cellText,
                      empText,
                      row.indent === 1 && "pl-5",
                    )}
                  >
                    {hasScheme ? (
                      <span
                        className={cx(
                          "mr-1 inline-block w-2.5",
                          isEquals
                            ? "text-gray-900 dark:text-gray-100"
                            : "text-gray-400 dark:text-gray-600",
                        )}
                      >
                        {row.op ?? "+"}
                      </span>
                    ) : null}
                    {row.label}
                    {row.annotation !== undefined ? (
                      <AnnotationRef n={row.annotation} />
                    ) : null}
                  </TableCell>
                  <SpacerCell />
                  {renderValueCells(
                    row.values,
                    row.polarity,
                    valueRuleClass,
                    empText,
                    d.srcIndex,
                  )}
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </TableRoot>
      {annotations && annotations.length > 0 ? (
        <AnnotationsBlock annotations={annotations} />
      ) : null}
    </Wrapper>
  )
}
