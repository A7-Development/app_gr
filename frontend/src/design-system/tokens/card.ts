// src/design-system/tokens/card.ts
//
// Vocabulario canonico para Card headers e bodies.
//
// Antes deste token, cada caller chutava `px-N py-N` no header de Card,
// resultando em variacoes (`px-3.5 py-3`, `px-4 py-2.5`, `px-5 py-4`).
// Agora: SEMPRE use `cardTokens.*` em vez de chutar.
//
// Decisoes (2026-05-01):
//   - Default: padding compacto (`px-4 py-2.5`) — alinha com DashboardBiPadrao
//   - Comfortable: padding mais generoso (`px-5 py-4`) — para cards extensos
//     com muito conteudo no header (titulo + subtitulo longo + actions)
//   - Border SEMPRE `border-gray-200 dark:border-gray-800` — NAO `gray-100`
//   - Body default: `p-4` — combina com header compacto

export const cardTokens = {
  // ── Header (com border-b interna) ─────────────────────────────────────
  /** Header padrao — combine com body=`body`. Padding compacto, alinha com DashboardBiPadrao. */
  header:
    "border-b border-gray-200 px-4 py-2.5 dark:border-gray-800",

  /** Header mais alto — para cards com titulo + subtitle + actions horizontais. */
  headerComfortable:
    "border-b border-gray-200 px-5 py-3.5 dark:border-gray-800",

  /** Header bem compacto — para AIPanel-style sidebars/drawers. */
  headerCompact:
    "border-b border-gray-200 px-3.5 py-3 dark:border-gray-800",

  // ── Body (sem border, padding interno) ────────────────────────────────
  /** Body padrao — combina com header padrao. */
  body: "p-4",

  /** Body mais arejado — para cards com formularios ou prosa longa. */
  bodyComfortable: "p-6",

  /** Body sem padding (caller controla, util quando interior tem propria estrutura). */
  bodyFlush: "",

  // ── Footer (espelha header em algumas variantes) ─────────────────────
  /** Footer com border-top, padding alinhado com header padrao. */
  footer: "border-t border-gray-200 px-4 py-2.5 dark:border-gray-800",

  // ── List items (em Card que age como lista vertical) ─────────────────
  /** Item de lista vertical dentro de Card — combine com `divide-y divide-gray-100`. */
  listItem: "flex items-start gap-3 px-4 py-2.5",

  /** Item de lista mais alto, util quando tem actions a direita. */
  listItemComfortable: "flex items-start gap-3 px-5 py-3",

  // ── Tipografia do header ──────────────────────────────────────────────
  /** Titulo principal de header de Card. Use em `<p>` ou `<h3>`. */
  headerTitle: "text-sm font-semibold text-gray-900 dark:text-gray-100",

  /** Subtitle/lede abaixo do titulo. Combine com `mt-0.5`. */
  headerSubtitle: "text-xs text-gray-500 dark:text-gray-400",
} as const
