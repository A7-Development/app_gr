// Formatadores compartilhados das abas do /bi/panorama.

const _MES_ABREV = [
  "jan", "fev", "mar", "abr", "mai", "jun",
  "jul", "ago", "set", "out", "nov", "dez",
]

export const fmtInt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 })

const _fmtBRLCompact = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
})
export function fmtBRLCompact(v: number): string {
  return _fmtBRLCompact.format(v)
}

export function fmtPct(v: number, digits = 2): string {
  return `${v.toFixed(digits).replace(".", ",")}%`
}

export function fmtDias(v: number): string {
  return `${fmtInt.format(Math.round(v))} d`
}

export function signedInt(v: number): string {
  const sign = v > 0 ? "+" : v < 0 ? "−" : ""
  return `${sign}${fmtInt.format(Math.abs(v))}`
}

/** 'YYYY-MM' -> 'abr/26' (eixo de chart). */
export function competenciaShort(yyyymm: string): string {
  const [y, m] = yyyymm.split("-").map(Number)
  if (!y || !m) return yyyymm
  return `${_MES_ABREV[m - 1]}/${String(y).slice(2)}`
}

/** 'YYYY-MM' -> 'abr/2026' (header). */
export function competenciaLong(yyyymm: string): string {
  const [y, m] = yyyymm.split("-").map(Number)
  if (!y || !m) return yyyymm
  return `${_MES_ABREV[m - 1]}/${y}`
}

/** Formata um valor de metrica conforme a unidade ('BRL'|'%'|'dias'). */
export function fmtMetrica(valor: number, unidade: string): string {
  switch (unidade) {
    case "BRL":
      return fmtBRLCompact(valor)
    case "%":
      return fmtPct(valor)
    case "dias":
      return fmtDias(valor)
    default:
      return String(valor)
  }
}
