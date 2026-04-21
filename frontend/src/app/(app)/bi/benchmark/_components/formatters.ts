//
// Formatters compartilhados pelos components da feature Benchmark.
//

export const moeda = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
})

export const moedaCompacta = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 2,
})

export const numero = new Intl.NumberFormat("pt-BR")
export const decimal1 = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
})

export const percent1 = (v: number | null | undefined): string =>
  v == null ? "—" : `${decimal1.format(v)}%`

export const dias = (v: number | null | undefined): string =>
  v == null ? "—" : `${numero.format(Math.round(v))} d`

export function labelCompetencia(iso: string): string {
  // Aceita 'YYYY-MM' ou 'YYYY-MM-DD'.
  const [y, m] = iso.split("-").map(Number)
  return new Date(y, m - 1, 1).toLocaleString("pt-BR", {
    month: "short",
    year: "2-digit",
  })
}

export function formatCNPJ(v: string): string {
  const s = v.replace(/\D/g, "").padStart(14, "0")
  return `${s.slice(0, 2)}.${s.slice(2, 5)}.${s.slice(5, 8)}/${s.slice(
    8,
    12,
  )}-${s.slice(12, 14)}`
}
