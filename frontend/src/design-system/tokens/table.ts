// src/design-system/tokens/table.ts
//
// Vocabulario tipografico canonico para qualquer celula de DataTable.
// Use via cx() em cell renderers — NUNCA escreva text-xs/text-sm/text-[Npx]
// inline em cell. Excecao com `// MOTIVO:` no proprio cell.
//
// Decisoes (2026-04-30):
//   - Texto principal de celula: 12px (text-xs)
//   - Numero / label / total: TODOS 12px — nao subimos pra 13/14px
//   - Badges dentro de celulas: 11px
//   - Header: 10px uppercase eyebrow (preserva assinatura visual Strata)
//   - Cor primaria dark: gray-100 (nao gray-50, mais coerente com o app)

export const tableTokens = {
  // ── Texto de celula (use 1 destes em todo cell custom) ────────────────
  /** Texto principal sans, peso normal — 90% das celulas. */
  cellText: "text-xs text-gray-900 dark:text-gray-100",

  /** Identificador estrutural mono (ID, alias, CNPJ, codigo). */
  cellTextMono: "font-mono text-xs text-gray-900 dark:text-gray-100",

  /** Metadado (data relativa, contagem, descricao secundaria). */
  cellSecondary: "text-xs text-gray-500 dark:text-gray-400",

  /** Estado vazio dentro da celula ("—", placeholder de null). */
  cellMuted: "text-xs text-gray-400 dark:text-gray-600",

  /** Linha de subtotal/destaque dentro de celula textual. */
  cellStrong: "text-xs font-semibold text-gray-900 dark:text-gray-100",

  /** Numero (com tabular-nums). Mesma cor do cellText. */
  cellNumber: "tabular-nums text-xs text-gray-900 dark:text-gray-100",

  /** Numero secundario (zero, vazio, neutro). */
  cellNumberSecondary: "tabular-nums text-xs text-gray-500 dark:text-gray-400",

  /** Numero positivo (delta crescente, ganho). */
  cellNumberPositive: "tabular-nums text-xs text-emerald-600 dark:text-emerald-400",

  /** Numero negativo (delta decrescente, perda). */
  cellNumberNegative: "tabular-nums text-xs text-red-600 dark:text-red-400",

  // ── Badges dentro de celulas (combinar com cor de tone) ──────────────
  // whitespace-nowrap: badge NUNCA quebra linha — em row de density compact
  // a quebra sobrepoe o texto (bug visual). Coluna estreita = aumentar size.
  /** Badge basico — combine com `bg-X-50 text-X-700 dark:...` por tone. */
  badge:
    "inline-flex items-center gap-1 whitespace-nowrap rounded-sm px-1.5 py-0.5 text-[11px] font-medium",

  /** Badge com dot indicador a esquerda. Combine com tone. */
  badgeWithDot:
    "inline-flex items-center gap-1.5 whitespace-nowrap rounded-sm px-1.5 py-0.5 text-[11px] font-medium",

  // ── Badges semanticos de STATUS (CLAUDE.md §4/§6 — decisao 2026-07-06).
  // Codigo novo usa ESTES tokens; nao recriar a receita de cor inline.
  // Legado com receita inline converte quando a area for tocada.
  /** Status positivo — "Ativo", "Aceito", "Conciliado", "Member". */
  badgeSuccess:
    "inline-flex items-center gap-1 whitespace-nowrap rounded-sm px-1.5 py-0.5 text-[11px] font-medium bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",

  /** Status de atencao — "Pendente", "Aguardando", "Parcial". */
  badgeWarning:
    "inline-flex items-center gap-1 whitespace-nowrap rounded-sm px-1.5 py-0.5 text-[11px] font-medium bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",

  /** Status negativo — "Expirado", "Falhou", "Bloqueado". */
  badgeDanger:
    "inline-flex items-center gap-1 whitespace-nowrap rounded-sm px-1.5 py-0.5 text-[11px] font-medium bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",

  /** Status neutro — "Inativo", "Rascunho", "Arquivado". */
  badgeNeutral:
    "inline-flex items-center gap-1 whitespace-nowrap rounded-sm px-1.5 py-0.5 text-[11px] font-medium bg-gray-100 text-gray-600 dark:bg-gray-500/10 dark:text-gray-400",

  // ── Header (`<th>`) ──────────────────────────────────────────────────
  /** Estilo eyebrow do header — assinatura visual Strata.
   * Cor e aplicada pela DataTable canonica — nao redefinir aqui. */
  header: "text-[10px] font-semibold uppercase tracking-[0.05em]",

  // ── Layout do `<DataTableShell>` ──────────────────────────────────────
  /** Card que envolve filtros + DataTable. Padding 16px — superficie da
   *  familia de tabelas (handoff Tabela canonica v2: padding 12->16px). */
  cardWrapper: "flex flex-col gap-3 p-4",

  /** Faixa horizontal de filtros (search + segments + counter). */
  filterBar: "flex flex-wrap items-center gap-2",

  /** Counter "X de Y" alinhado a direita da filterBar. */
  countLabel:
    "ml-auto text-[11px] tabular-nums text-gray-500 dark:text-gray-400",
} as const
