"use client"

/**
 * BalanceTable — Balanço Sub Jr (D-1 vs D0)
 *
 * Tabela única estruturada com 5 tipos de linha (section / line / sub /
 * subtotal / total) representando o balanço do FIDC pela ótica do cotista
 * subordinado:
 *
 *   ATIVO
 *     Tesouraria, Compromissada, Títulos Públicos, Fundos DI, DC, DC estruturada,
 *     Outros Ativos, (−) PDD
 *     Subtotal Ativo
 *   PASSIVO
 *     Contas a Pagar, Cota Mezanino, Cota Senior
 *     Subtotal Passivo
 *   = COTA SUBORDINADA (residual)
 *
 * Cada linha pode ter subitens (`type='sub'`) renderizados indented logo abaixo.
 * Não há expand/collapse na v1 — tudo aberto.
 *
 * Stack: DataTable canônica + rowClassName por tipo. Sem componente novo no DS.
 *
 * Backend: endpoint `GET /controladoria/cota-sub/balanco?fundo_id={id}&data={D0}`
 * monta os BalanceRow[] lendo APENAS de silver canônico (CLAUDE.md §13.2.1):
 *   • Tesouraria        ← wh_saldo_tesouraria + wh_saldo_conta_corrente (≠ CONCILI)
 *   • Compromissada     ← wh_posicao_compromissada
 *   • Títulos Públicos  ← wh_posicao_renda_fixa (NTN-*, LFT, LTN)
 *   • Fundos DI         ← wh_posicao_cota_fundo (código ∉ REAL*)
 *   • DC                ← wh_posicao_cota_fundo (código ∈ REAL*)
 *   • DC estruturada    ← wh_posicao_renda_fixa (NCPX, VCNC)
 *   • Outros Ativos     ← wh_cpr_movimento (valor>0) + wh_saldo_conta_corrente (CONCILI)
 *   • PDD               ← wh_posicao_outros_ativos (código=PDD)
 *   • Contas a Pagar    ← wh_cpr_movimento (valor<0)
 *   • Cota Mez/Sr       ← wh_posicao_renda_fixa (papel=MEZAN/SRP)
 */

import * as React from "react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"

// ─────────────────────────────────────────────────────────────────────────────
// Types — re-exportados do api-client (fonte unica)
// ─────────────────────────────────────────────────────────────────────────────

export type { BalanceRow, BalanceRowType } from "@/lib/api-client"
import type { BalanceRow, BalanceRowType } from "@/lib/api-client"

// ─────────────────────────────────────────────────────────────────────────────
// Formatters
// ─────────────────────────────────────────────────────────────────────────────

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

function formatValue(v: number | null): string {
  if (v == null) return ""
  if (v === 0) return "—"
  if (v < 0) return `(${fmtBRL.format(Math.abs(v))})`
  return fmtBRL.format(v)
}

function formatDelta(v: number | null): string {
  if (v == null) return ""
  if (v === 0) return "—"
  const sign = v > 0 ? "+" : ""
  return sign + fmtBRL.format(v)
}

/** ISO yyyy-MM-dd → "DD/MM/YY" (ex.: "2026-04-24" → "24/04/26"). */
function fmtDateShort(iso?: string): string {
  if (!iso) return ""
  const [y, m, d] = iso.split("-")
  if (!y || !m || !d) return iso
  return `${d}/${m}/${y.slice(2)}`
}

// ─────────────────────────────────────────────────────────────────────────────
// Title Case pt-BR
//
// Labels do plano COSIF chegam em ALL CAPS do backend (ex.: "BANCOS PRIVADOS"),
// enquanto sub-itens custom vem em case mais natural ("Direitos Creditorios").
// Pra padronizar a leitura sem alterar o dado de origem, normalizamos no
// render: se a string esta toda maiuscula, converte para Title Case respeitando
// stopwords pt-BR e siglas separadas por barra (S/A, RJ/SP).
// ─────────────────────────────────────────────────────────────────────────────

const PT_STOPWORDS = new Set([
  "de", "da", "do", "das", "dos", "e", "a", "o", "as", "os",
  "em", "no", "na", "nos", "nas", "para", "pelo", "pela", "com",
])

/** True se a string esta toda em maiusculas e merece Title Case.
 * Heuristica para tokens unicos (sem espaco):
 *   - Siglas curtas (<= 4 chars) ou sem vogais => preserva (NTN, LFT, S/A,
 *     NTN-B, PDD, VCNC, NCPX).
 *   - Palavras longas (>= 5 chars) com vogais => normaliza (ATIVO, PASSIVO,
 *     TOTAL, DIVERSOS, TESOURARIA). */
function shouldNormalize(s: string): boolean {
  if (!s) return false
  if (!/[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ]/.test(s)) return false
  if (s !== s.toUpperCase()) return false
  // Frase com espaco -> sempre normaliza ("FUNDOS DI" -> "Fundos DI").
  if (/\s/.test(s)) return true
  // Token unico: heuristica sigla vs palavra.
  if (s.length < 5) return false
  if (!/[AEIOUÁÀÂÃÉÊÍÓÔÕÚ]/.test(s)) return false
  return true
}

/** Title Case pt-BR. Aplicado APENAS quando `shouldNormalize` aprova
 * (string toda all-caps + tem espacos). Stopwords (de/da/do/...) ficam
 * minusculas; tokens de 1-2 chars sao mantidos uppercase (preserva SI/SP/A/O
 * de codigos de fundo + siglas em meio a frase como "REF SI"). */
function titleCasePtBR(input: string): string {
  if (!shouldNormalize(input)) return input
  const tokens = input.split(/(\s+|-|\/)/)
  return tokens
    .map((token, idx) => {
      if (/^(\s+|-|\/)$/.test(token)) return token
      const lower = token.toLocaleLowerCase("pt-BR")
      // Stopword vale APENAS quando o token anterior eh espaco (palavra real
      // dentro da frase). Nao normaliza apos `-` ou `/` — preserva siglas como
      // "S/A", "RJ/SP", "M-A".
      const prev = tokens[idx - 1]
      const afterSpace = idx > 0 && prev !== undefined && /^\s+$/.test(prev)
      if (afterSpace && PT_STOPWORDS.has(lower)) return lower
      // Token 1-2 chars (e nao stopword) e provavel sigla — mantem uppercase
      // (ex.: "REF SI", "S/A", "S/N").
      if (token.length <= 2 && /^[A-ZÁÀÂÃÉÊÍÓÔÕÚÇ]+$/.test(token)) return token
      return lower.charAt(0).toLocaleUpperCase("pt-BR") + lower.slice(1)
    })
    .join("")
}

// ─────────────────────────────────────────────────────────────────────────────
// Lado do balancete — mapeado pelo id top-level e propagado aos subRows
//
// Determina o sinal da contribuicao na Cota Subordinada:
//   • Ativo            → contribuicao = +Δ (cresceu Ativo = +Cota Sub)
//   • Passivo Contabil → contribuicao = -Δ (cresceu Passivo = -Cota Sub)
//   • Equity (Mez+Sr)  → contribuicao = -Δ
// Linhas neutras (pl-total, total) nao tem contribuicao individual.
// ─────────────────────────────────────────────────────────────────────────────

type LadoBalancete = "ativo" | "passivo" | "neutro"

function buildLadoMap(rows: BalanceRow[]): Map<string, LadoBalancete> {
  const map = new Map<string, LadoBalancete>()
  function walk(r: BalanceRow, lado: LadoBalancete) {
    map.set(r.id, lado)
    if (r.subRows) for (const sub of r.subRows) walk(sub, lado)
  }
  for (const r of rows) {
    if (r.id === "ativo") walk(r, "ativo")
    else if (r.id === "passivo-contabil" || r.id === "equity") walk(r, "passivo")
    else walk(r, "neutro")
  }
  return map
}

// ─────────────────────────────────────────────────────────────────────────────
// Column factory — dinâmica nos cabeçalhos D-1 / D0 (mostra a data real)
// ─────────────────────────────────────────────────────────────────────────────

const col = createColumnHelper<BalanceRow>()

type BuildColumnsOpts = {
  dataAnterior?:     string
  data?:             string
  showContribuicao?: boolean
  ladoMap?:          Map<string, LadoBalancete>
}

function buildColumns(
  opts: BuildColumnsOpts,
): ColumnDef<BalanceRow, unknown>[] {
  const { dataAnterior, data, showContribuicao = false, ladoMap } = opts
  const headerD1 = dataAnterior ? fmtDateShort(dataAnterior) : "D-1"
  const headerD0 = data         ? fmtDateShort(data)         : "D0"

  const baseColumns: ColumnDef<BalanceRow, unknown>[] = [
  // Coluna COSIF foi removida (decisao 2026-04-30): a hierarquia visual passou
  // a ser dada por padding-left automatico da DataTable em `expandedColumnId`.
  // O codigo COSIF (quando existe) e exibido como prefixo monoespaçado dentro
  // da propria coluna "Linha", colado ao label.

  col.accessor("label", {
    id:     "label",
    header: "Linha",
    size:   560,
    cell:   (info) => {
      const row = info.row.original
      const rawLabel = info.getValue<string>()

      // Normalizacao Title Case pt-BR aplicada a TODOS os tipos (incluindo
      // section: "ATIVO" -> "Ativo"). Bypass anterior do section foi removido —
      // section ja e destacada por bg + border + font-semibold no row styling,
      // nao precisa de uppercase forcado pra se diferenciar.
      const label = titleCasePtBR(rawLabel)

      // nowrap + truncate + tooltip nativo (title) — texto nunca quebra em 2
      // linhas. Tooltip mostra o label ORIGINAL pra preservar a forma COSIF.
      const baseTrunc = "block max-w-full truncate whitespace-nowrap"

      // Tipografia via tableTokens (12px) — uniforme em todos os niveis.
      // Hierarquia visual vem de: padding-left automatico (DataTable) +
      // peso (subtotal/total = semibold) + background (section = bg-gray-50).
      if (row.type === "section" || row.type === "subtotal" || row.type === "total") {
        return (
          <span title={rawLabel} className={cx(baseTrunc, tableTokens.cellStrong)}>
            {label}
          </span>
        )
      }
      // line (depth 0) ou sub (depth > 0). Codigos COSIF foram removidos da UI
      // por decisao 2026-04-30 (campo ainda vem do backend; ocultado aqui).
      return (
        <span title={rawLabel} className={cx(baseTrunc, tableTokens.cellText)}>
          {label}
        </span>
      )
    },
  }) as ColumnDef<BalanceRow, unknown>,

  col.accessor("descricao", {
    header: "Descrição",
    size:   200,
    cell:   (info) => {
      const row = info.row.original
      if (row.type !== "line" || !row.descricao) return null
      return <span className={tableTokens.cellSecondary}>{row.descricao}</span>
    },
  }) as ColumnDef<BalanceRow, unknown>,

  col.accessor("source", {
    id:     "source",
    header: "Fonte",
    size:   200,
    cell:   (info) => {
      const row = info.row.original
      if (row.type !== "line" || !row.source) return null
      return (
        <span
          className={cx(
            "block max-w-full truncate font-mono",
            tableTokens.cellSecondary,
          )}
          title={row.source}
        >
          {row.source}
        </span>
      )
    },
  }) as ColumnDef<BalanceRow, unknown>,

  col.accessor("d1", {
    header: headerD1,
    meta:   { align: "right" },
    size:   140,
    cell:   (info) => {
      const row = info.row.original
      if (row.type === "section") return null
      const v = info.getValue<number | null>()
      const isStrong = row.type === "subtotal" || row.type === "total"
      return (
        <div
          style={{ textAlign: "right" }}
          className={cx(
            v != null && v < 0
              ? tableTokens.cellNumberSecondary
              : tableTokens.cellNumber,
            isStrong && "font-semibold",
          )}
        >
          {formatValue(v)}
        </div>
      )
    },
  }) as ColumnDef<BalanceRow, unknown>,

  col.accessor("d0", {
    header: headerD0,
    meta:   { align: "right" },
    size:   140,
    cell:   (info) => {
      const row = info.row.original
      if (row.type === "section") return null
      const v = info.getValue<number | null>()
      const isStrong = row.type === "subtotal" || row.type === "total"
      return (
        <div
          style={{ textAlign: "right" }}
          className={cx(
            v != null && v < 0
              ? tableTokens.cellNumberSecondary
              : tableTokens.cellNumber,
            isStrong && "font-semibold",
          )}
        >
          {formatValue(v)}
        </div>
      )
    },
  }) as ColumnDef<BalanceRow, unknown>,

  col.accessor("delta", {
    header: "Δ",
    meta:   { align: "right" },
    size:   showContribuicao ? 160 : 140,
    cell:   (info) => {
      const row = info.row.original
      if (row.type === "section") return null
      const v = info.getValue<number | null>()
      const isPos = v != null && v > 0
      const isNeg = v != null && v < 0
      const isStrong = row.type === "subtotal" || row.type === "total"
      // No modo "Eventos do dia" (showContribuicao=true), Δ vira coluna de
      // destaque visual: font-medium em todas as linhas (em vez de so subtotal/
      // total). Mantem cor verde/vermelho que ja existia.
      const emphasizeAll = showContribuicao
      return (
        <div
          style={{ textAlign: "right" }}
          className={cx(
            isPos
              ? tableTokens.cellNumberPositive
              : isNeg
                ? tableTokens.cellNumberNegative
                : tableTokens.cellMuted + " tabular-nums",
            (isStrong || emphasizeAll) && "font-semibold",
          )}
        >
          {formatDelta(v)}
        </div>
      )
    },
  }) as ColumnDef<BalanceRow, unknown>,
  ]

  if (!showContribuicao || !ladoMap) return baseColumns

  // ─── Modo "Eventos do dia": adiciona coluna Contribuicao + reordena ───────
  //
  // Ordem visual canonica neste modo: Linha · Δ · Contribuicao · D-1 · D0
  // (Δ e Contribuicao ficam no centro destacados; D-1/D0 viram referencia
  // contabil compacta a direita.)

  const contribuicaoCol = col.accessor(
    (row) => row.delta,
    {
      id:     "contribuicao",
      header: "Contribuicao",
      meta:   { align: "right" },
      size:   160,
      cell:   (info) => {
        const row = info.row.original
        if (row.type === "section") return null
        const lado = ladoMap.get(row.id) ?? "neutro"
        if (lado === "neutro") return null
        const delta = info.getValue<number | null>()
        if (delta == null) return null
        const sinal = lado === "ativo" ? 1 : -1
        const v = sinal * delta
        const isPos = v > 0
        const isNeg = v < 0
        const isStrong = row.type === "subtotal" || row.type === "total"
        return (
          <div
            style={{ textAlign: "right" }}
            className={cx(
              isPos
                ? tableTokens.cellNumberPositive
                : isNeg
                  ? tableTokens.cellNumberNegative
                  : tableTokens.cellMuted + " tabular-nums",
              "font-semibold",
              isStrong && "font-bold",
            )}
            title={
              lado === "ativo"
                ? "Linha do Ativo: contribuicao = +Δ"
                : "Linha do Passivo/Equity: contribuicao = -Δ"
            }
          >
            {formatDelta(v)}
          </div>
        )
      },
    },
  ) as ColumnDef<BalanceRow, unknown>

  // Reordena: Linha · Descricao · Δ · Contribuicao · D-1 · D0 · (Fonte hidden)
  // baseColumns ordem original: [label, descricao, source, d1, d0, delta]
  const labelCol     = baseColumns[0]
  const descricaoCol = baseColumns[1]
  const sourceCol    = baseColumns[2]
  const d1Col        = baseColumns[3]
  const d0Col        = baseColumns[4]
  const deltaCol     = baseColumns[5]
  return [labelCol, descricaoCol, sourceCol, deltaCol, contribuicaoCol, d1Col, d0Col]
}

// ─────────────────────────────────────────────────────────────────────────────
// Sort por magnitude do Δ — preserva hierarquia (section/subtotal/total) e
// reordena APENAS as subRows dentro de cada secao.
// ─────────────────────────────────────────────────────────────────────────────

function sortRowsByDeltaMagnitude(rows: BalanceRow[]): BalanceRow[] {
  function sortRecursive(rs: BalanceRow[]): BalanceRow[] {
    return rs
      .map((r) => ({
        ...r,
        subRows: r.subRows ? sortRecursive(r.subRows) : undefined,
      }))
      .sort((a, b) => {
        // Mantem section/subtotal/total nas suas posicoes naturais. Sort vale
        // apenas para line/sub.
        const sortable = (t: BalanceRowType) => t === "line"
        if (!sortable(a.type) || !sortable(b.type)) return 0
        const da = Math.abs(a.delta ?? 0)
        const db = Math.abs(b.delta ?? 0)
        return db - da
      })
  }
  return sortRecursive(rows)
}

// ─────────────────────────────────────────────────────────────────────────────
// Row styling per type
// ─────────────────────────────────────────────────────────────────────────────

const ROW_BG: Record<BalanceRowType, string> = {
  // Section: !h-6 sobrescreve a altura padrao da DataTable (h-8 em compact)
  // pra ficar mais discreta — eh apenas um separador visual.
  // !border-l-0 anula o `border-l-2 border-l-transparent` da DataTable canonica
  // (que reserva 2px na esquerda mesmo invisivel e cria "step" visivel ao
  // combinar com border-y/border-t).
  // Section: border-y intencional (borda em cima E embaixo) — destaca o cabecalho
  // de bloco. border-y-gray-200 evita override da border-bottom-color default
  // gray-100 da DataTable (que aparecia como borda dupla quando combinada).
  section:  "!h-6 !border-l-0 bg-gray-50 dark:bg-gray-900/60 border-y border-y-gray-200 dark:border-y-gray-800",
  line:     "",
  // Subtotal: APENAS border-top. border-t-gray-300 (em vez do shorthand
  // border-gray-300) preserva a border-bottom-color default da DataTable —
  // o shorthand sobrescrevia os 4 lados e causava aparencia "boxed".
  subtotal: "!border-l-0 bg-gray-50 dark:bg-gray-900/40 border-t border-t-gray-300 dark:border-t-gray-700",
  // Total (PL Total / Cota Sub residual): mesmo padrao do subtotal. border-t
  // exclusivo via border-t-gray-200 — sem shorthand que vaze para o bottom.
  total:    "!border-l-0 border-t border-t-gray-200 dark:border-t-gray-800",
}

// ─────────────────────────────────────────────────────────────────────────────
// Component
// ─────────────────────────────────────────────────────────────────────────────

export type BalanceTableProps = {
  rows:          BalanceRow[]
  data?:         string  // ISO D0
  dataAnterior?: string  // ISO D-1
  emptyMessage?: string
  /** Adiciona coluna "Contribuicao na Cota Sub" e reordena visual:
   * Linha · Δ · Contribuicao · D-1 · D0. Default false (modo balancete classico). */
  showContribuicao?: boolean
  /** Reordena as line/sub rows dentro de cada secao por |Δ| desc. Mantem
   * section/subtotal/total em ordem natural. Default false. */
  sortByDelta?: boolean
  /** Override do titulo do card. Default "Balancete Diario". */
  title?: string
}

export function BalanceTable({
  rows,
  data,
  dataAnterior,
  emptyMessage,
  showContribuicao = false,
  sortByDelta      = false,
  title            = "Balancete Diário",
}: BalanceTableProps) {
  const ladoMap = React.useMemo(
    () => (showContribuicao ? buildLadoMap(rows) : undefined),
    [rows, showContribuicao],
  )

  const sortedRows = React.useMemo(
    () => (sortByDelta ? sortRowsByDeltaMagnitude(rows) : rows),
    [rows, sortByDelta],
  )

  const columns = React.useMemo(
    () => buildColumns({ dataAnterior, data, showContribuicao, ladoMap }),
    [dataAnterior, data, showContribuicao, ladoMap],
  )

  return (
    // Card Tremor com p-3 + gap-3 — mesmo padrão da ListagemCrudInline.
    // Tabela "flutua" dentro do card (não cola na borda); header inline
    // separado da tabela pelo gap, sem precisar de border-b.
    <Card className="flex flex-col gap-3 p-3">
      <div className="flex flex-wrap items-center gap-2">
        <h3 className="text-sm text-gray-900 dark:text-gray-50">
          {title}
        </h3>
      </div>
      <DataTable
        data={sortedRows}
        columns={columns}
        density="compact"
        showColumnManager={false}
        showDensityToggle={false}
        showExport={false}
        virtualize={false}
        enableExpanding
        getSubRows={(row) => row.subRows}
        defaultExpanded={{}}
        expandedColumnId="label"
        // "source" eh metadado tecnico (tabela silver origem) — escondido
        // permanentemente da UI. Continua no payload pra debug via DevTools.
        initialColumnVisibility={{ source: false }}
        rowClassName={(row) => ROW_BG[row.type]}
        renderEmpty={() => (
          <div className="flex flex-col items-center justify-center gap-1 py-12 text-center">
            <p className="text-sm text-gray-600 dark:text-gray-400">
              Sem dados para a data selecionada
            </p>
            {emptyMessage && (
              <p className="text-xs text-gray-400 dark:text-gray-600">
                {emptyMessage}
              </p>
            )}
          </div>
        )}
      />
    </Card>
  )
}



