// src/design-system/tokens/typography.ts
// Typography scale + utility helpers.
// Font loading is handled by Next.js layout.tsx via the `geist` npm package.

export const tabular = 'tabular-nums font-[feature-settings:"lnum","tnum"]' as const

export const monoId = "font-mono text-xs tabular-nums tracking-[0.02em]" as const

export const caption = "text-[11px] font-medium uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400" as const

export const kpiHero = "font-semibold tabular-nums tracking-tight leading-none" as const

export const fmt = {
  /** R$ 1.234.567,89 */
  currency: new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 2,
  }),
  /** R$ 1.234.567 (sem centavos) */
  currencyWhole: new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 0,
  }),
  /** R$ 1,23M / R$ 456K */
  currencyCompact: new Intl.NumberFormat("pt-BR", {
    style: "currency",
    currency: "BRL",
    notation: "compact",
    maximumFractionDigits: 2,
  }),
  /** 12,34% */
  percent: new Intl.NumberFormat("pt-BR", {
    style: "percent",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }),
  /** 1.234 */
  number: new Intl.NumberFormat("pt-BR"),
  /** 38,5 dias */
  decimal1: new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1 }),
}

/**
 * Format a date string (ISO or yyyy-mm-dd) as dd/mm/aa for table cells.
 */
export function fmtDate(isoDate: string): string {
  const [y, m, d] = isoDate.split("T")[0].split("-")
  return `${d}/${m}/${y.slice(2)}`
}

/** Format CPF: 123.456.789-00 */
export function fmtCPF(cpf: string): string {
  const d = cpf.replace(/\D/g, "")
  return d.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4")
}

/** Format CNPJ: 12.345.678/0001-99 */
export function fmtCNPJ(cnpj: string): string {
  const d = cnpj.replace(/\D/g, "")
  return d.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, "$1.$2.$3/$4-$5")
}
