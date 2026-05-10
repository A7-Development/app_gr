// src/design-system/tokens/report-category.ts
//
// Cores nomeadas para o avatar de cada `ReportCategory` no catalogo
// de relatorios (`/controladoria/relatorios`). Espelha o enum
// `ReportCategory` em backend/app/modules/integracoes/report_catalog.py.
//
// Cada categoria tem cor de IDENTIDADE — nao iterativa, nao de status.
// Difere de chart series (que segue `chartColors` em chartUtils) e de
// avatar de modulo (que vive em modules.ts::MODULE_AVATAR_COLORS).
//
// Manter sincronizado com `ReportCategory` no backend. Adicionar
// categoria nova exige adicionar entrada aqui.

export type ReportCategoryId =
  | "cota"
  | "posicao"
  | "estoque"
  | "eventos"
  | "recebimentos"
  | "custodia"
  | "movimentacoes"
  | "outros"

// Avatar (bg + texto) para o icone da categoria. Tons sobrios — cor remete
// a familia semantica, nao a alarme.
export const REPORT_CATEGORY_AVATAR_COLORS: Record<ReportCategoryId, string> = {
  cota: "bg-indigo-50 text-indigo-600 dark:bg-indigo-500/10 dark:text-indigo-400",
  posicao: "bg-blue-50 text-blue-600 dark:bg-blue-500/10 dark:text-blue-400",
  estoque: "bg-emerald-50 text-emerald-600 dark:bg-emerald-500/10 dark:text-emerald-400",
  eventos: "bg-violet-50 text-violet-600 dark:bg-violet-500/10 dark:text-violet-400",
  recebimentos: "bg-teal-50 text-teal-600 dark:bg-teal-500/10 dark:text-teal-400",
  custodia: "bg-amber-50 text-amber-600 dark:bg-amber-500/10 dark:text-amber-400",
  movimentacoes: "bg-sky-50 text-sky-600 dark:bg-sky-500/10 dark:text-sky-400",
  outros: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
}

export const REPORT_CATEGORY_LABEL: Record<ReportCategoryId, string> = {
  cota: "Cota",
  posicao: "Posição",
  estoque: "Estoque",
  eventos: "Eventos",
  recebimentos: "Recebimentos",
  custodia: "Custódia",
  movimentacoes: "Movimentações",
  outros: "Outros",
}
