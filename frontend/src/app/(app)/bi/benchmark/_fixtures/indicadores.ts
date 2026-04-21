import type { IndicadorDefinicao, IndicadorKey } from "./types"

//
// Catalogo canonico de indicadores usados no ranking do comparativo.
// Ordem = ordem visual nas tabelas.
//
export const INDICADORES: IndicadorDefinicao[] = [
  { key: "pl", label: "PL", unidade: "BRL", grupo: "escala", direcao: "higher_is_better" },
  { key: "pl_medio_3m", label: "PL medio 3m", unidade: "BRL", grupo: "escala", direcao: "higher_is_better" },
  { key: "pct_dc_pl", label: "% DC / PL", unidade: "%", grupo: "escala", direcao: "higher_is_better" },
  { key: "nro_cotistas", label: "Cotistas", unidade: "un", grupo: "escala", direcao: "higher_is_better" },
  { key: "colchao_subordinacao_pct", label: "Colchao de subordinacao", unidade: "%", grupo: "estrutura", direcao: "higher_is_better" },
  { key: "top1_cedente_pct", label: "Top-1 cedente", unidade: "%", grupo: "estrutura", direcao: "lower_is_better" },
  { key: "duration_dias", label: "Duration carteira", unidade: "dias", grupo: "estrutura", direcao: "lower_is_better" },
  { key: "pct_inad_total", label: "% Inadimplencia total", unidade: "%", grupo: "qualidade", direcao: "lower_is_better" },
  { key: "pct_inad_90d", label: "% Inadimplencia >90d", unidade: "%", grupo: "qualidade", direcao: "lower_is_better" },
  { key: "pct_inad_360d", label: "% Inadimplencia >360d", unidade: "%", grupo: "qualidade", direcao: "lower_is_better" },
  { key: "pct_cobertura_pdd", label: "% Cobertura PDD", unidade: "%", grupo: "qualidade", direcao: "higher_is_better" },
  { key: "pct_aa_scr", label: "% AA (SCR)", unidade: "%", grupo: "qualidade", direcao: "higher_is_better" },
  { key: "pct_d_mais_scr", label: "% D+ (SCR)", unidade: "%", grupo: "qualidade", direcao: "lower_is_better" },
  { key: "taxa_dc_com", label: "Taxa DC com risco", unidade: "%", grupo: "taxas", direcao: "higher_is_better" },
  { key: "taxa_dc_sem", label: "Taxa DC sem risco", unidade: "%", grupo: "taxas", direcao: "higher_is_better" },
]

export const INDICADOR_POR_KEY: Record<IndicadorKey, IndicadorDefinicao> =
  INDICADORES.reduce(
    (acc, ind) => {
      acc[ind.key] = ind
      return acc
    },
    {} as Record<IndicadorKey, IndicadorDefinicao>,
  )

/** Mediana de mercado (mockado) para destacar referencia no ranking. */
export const MEDIANA_MERCADO: Record<IndicadorKey, number> = {
  pl: 180_000_000,
  pl_medio_3m: 172_000_000,
  pct_dc_pl: 92,
  nro_cotistas: 18,
  colchao_subordinacao_pct: 21.5,
  top1_cedente_pct: 14.2,
  duration_dias: 118,
  pct_inad_total: 6.4,
  pct_inad_90d: 3.8,
  pct_inad_360d: 1.2,
  pct_cobertura_pdd: 82,
  pct_aa_scr: 68,
  pct_d_mais_scr: 5.6,
  taxa_dc_com: 2.35,
  taxa_dc_sem: 1.18,
}

//
// Cores canonicas A7 para slots 1..5 do comparativo (CLAUDE.md §4).
// Ordem: slate, sky, teal, emerald, amber.
//
export const FUNDO_CORES = ["slate", "sky", "teal", "emerald", "amber"] as const
export type FundoCor = (typeof FUNDO_CORES)[number]

//
// Classes Tailwind materializadas por cor. Necessario porque o JIT nao
// resolve classes dinamicas (ex.: `bg-${cor}-500`). As classes abaixo sao
// as mesmas usadas pelos charts Tremor via `chartColors` — mantem consistencia
// com as series do ComparativoTab.
//
export const FUNDO_COR_CLASSES: Record<
  FundoCor,
  { dot: string; text: string; border: string; bg: string }
> = {
  slate: {
    dot: "bg-slate-500",
    text: "text-slate-600 dark:text-slate-400",
    border: "border-slate-300 dark:border-slate-700",
    bg: "bg-slate-50 dark:bg-slate-500/10",
  },
  sky: {
    dot: "bg-sky-500",
    text: "text-sky-600 dark:text-sky-400",
    border: "border-sky-300 dark:border-sky-700",
    bg: "bg-sky-50 dark:bg-sky-500/10",
  },
  teal: {
    dot: "bg-teal-500",
    text: "text-teal-600 dark:text-teal-400",
    border: "border-teal-300 dark:border-teal-700",
    bg: "bg-teal-50 dark:bg-teal-500/10",
  },
  emerald: {
    dot: "bg-emerald-500",
    text: "text-emerald-600 dark:text-emerald-400",
    border: "border-emerald-300 dark:border-emerald-700",
    bg: "bg-emerald-50 dark:bg-emerald-500/10",
  },
  amber: {
    dot: "bg-amber-500",
    text: "text-amber-600 dark:text-amber-400",
    border: "border-amber-300 dark:border-amber-700",
    bg: "bg-amber-50 dark:bg-amber-500/10",
  },
}
