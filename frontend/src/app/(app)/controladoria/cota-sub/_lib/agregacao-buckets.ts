/**
 * Agregacao das linhas do balancete em 6 buckets do waterfall hero.
 *
 * Equacao da pagina:  Δ Cota Sub = Δ Ativo − Δ Passivo Contabil − Δ Equity (Mez+Sr)
 *
 * Cada linha do payload do `/balanco` (BalanceRow) e mapeada para um bucket
 * pelo id retornado do backend (services/balanco.py). O sinal da contribuicao
 * na Cota Sub depende do lado do balancete:
 *   • Ativo            → contribuicao = +Δlinha (cresceu Ativo = +Cota Sub)
 *   • Passivo Contabil → contribuicao = -Δlinha (cresceu Passivo = -Cota Sub)
 *   • Equity (Mez+Sr)  → contribuicao = -Δlinha (cresceu Equity = -Cota Sub)
 *
 * Funcao pura — sem dependencia de React/Tanstack. Testavel isolada.
 */

import type { BalanceRow } from "@/lib/api-client"

// ─── Tipos ───────────────────────────────────────────────────────────────────

export type BucketId =
  | "caixa"
  | "posicao"
  | "dc"
  | "outros_ativos"
  | "despesas"
  | "outras_cotas"

export type BucketDef = {
  id:    BucketId
  label: string
  /** "Lado" do balancete — define o sinal aplicado ao Δ na Cota Sub. */
  lado:  "ativo" | "passivo"
}

export type BucketAgregado = BucketDef & {
  d1:                   number
  d0:                   number
  delta:                number  // Δ bruto da soma das linhas (D0 − D-1)
  contribuicao_cota_sub: number  // Δ aplicando o sinal do lado
  /** IDs das linhas do balancete que compoem este bucket. */
  source_row_ids: string[]
  /** Linhas reais agregadas — uteis para drill-down futuro (PR2). */
  source_rows: BalanceRow[]
}

export type BucketsAgregados = {
  buckets:        BucketAgregado[]
  cota_sub_d1:    number
  cota_sub_d0:    number
  delta_cota_sub: number
  delta_ativo:    number
  delta_passivo:  number  // soma de Passivo Contabil + Equity (lado contrario do Ativo)
}

// ─── Definicao dos buckets (ordem visual do waterfall) ───────────────────────

const BUCKETS: BucketDef[] = [
  { id: "caixa",         label: "Caixa",                lado: "ativo" },
  { id: "posicao",       label: "Posicao Ativos",       lado: "ativo" },
  { id: "dc",            label: "Direitos Crediticios", lado: "ativo" },
  { id: "outros_ativos", label: "Outros Ativos",        lado: "ativo" },
  { id: "despesas",      label: "Despesas (CPR)",       lado: "passivo" },
  { id: "outras_cotas",  label: "Outras Cotas (Mez+Sr)", lado: "passivo" },
]

/** Mapeamento id-da-linha → bucket. Vem do schema do backend
 * (services/balanco.py — funcao compute_balanco). */
const ROW_TO_BUCKET: Record<string, BucketId> = {
  // Ativo · Caixa
  bancos_privados: "caixa",
  // Ativo · Posicao
  compromissada: "posicao",
  tp:            "posicao",
  dce:           "posicao",
  fdi:           "posicao",
  // Ativo · Direitos Crediticios
  dc: "dc",
  // Ativo · Outros (residuais + CPR ativo)
  pdd:          "outros_ativos",
  liquidacoes:  "outros_ativos",
  desp_antecip: "outros_ativos",
  oa_residual:  "outros_ativos",
  // Passivo Contabil · CPR despesas apropriadas
  iof:       "despesas",
  prov_pgto: "despesas",
  val_adm:   "despesas",
  // Equity · Outras classes de cota
  mez: "outras_cotas",
  sr:  "outras_cotas",
}

// ─── Agregacao ───────────────────────────────────────────────────────────────

export function agregarBuckets(rows: BalanceRow[]): BucketsAgregados {
  const flat = flattenLinhas(rows)
  const indexed = new Map<string, BalanceRow>()
  for (const r of flat) indexed.set(r.id, r)

  const buckets: BucketAgregado[] = BUCKETS.map((def) => {
    const sourceIds = Object.entries(ROW_TO_BUCKET)
      .filter(([, b]) => b === def.id)
      .map(([id]) => id)

    const sourceRows = sourceIds
      .map((id) => indexed.get(id))
      .filter((r): r is BalanceRow => r !== undefined)

    const d1 = sumNullable(sourceRows.map((r) => r.d1))
    const d0 = sumNullable(sourceRows.map((r) => r.d0))
    const delta = d0 - d1
    const sinal = def.lado === "ativo" ? 1 : -1

    return {
      ...def,
      d1,
      d0,
      delta,
      contribuicao_cota_sub: sinal * delta,
      source_row_ids: sourceRows.map((r) => r.id),
      source_rows: sourceRows,
    }
  })

  const cotaSubRow = indexed.get("total")
  const cota_sub_d1 = cotaSubRow?.d1 ?? 0
  const cota_sub_d0 = cotaSubRow?.d0 ?? 0
  const delta_cota_sub = cota_sub_d0 - cota_sub_d1

  const delta_ativo = buckets
    .filter((b) => b.lado === "ativo")
    .reduce((acc, b) => acc + b.delta, 0)

  const delta_passivo = buckets
    .filter((b) => b.lado === "passivo")
    .reduce((acc, b) => acc + b.delta, 0)

  return {
    buckets,
    cota_sub_d1,
    cota_sub_d0,
    delta_cota_sub,
    delta_ativo,
    delta_passivo,
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Decomposicao granular — 1 linha por entrada do balancete (sem agregar)
//
// Diferente de `agregarBuckets`, que junta as 15 linhas em 6 buckets tematicos
// (legivel para insights/KPIs), esta funcao mantem a granularidade original
// para alimentar o waterfall detalhado (Ativo | Passivo | Δ).
// ─────────────────────────────────────────────────────────────────────────────

export type LinhaContribuicao = {
  id:                    string
  label:                 string
  lado:                  "ativo" | "passivo"
  delta:                 number
  contribuicao_cota_sub: number  // sinal aplicado conforme o lado
}

export type DecomposicaoLinhas = {
  ativo:          LinhaContribuicao[]
  passivo:        LinhaContribuicao[]  // inclui Equity (Mez+Sr) — todos contribuem negativamente
  cota_sub_d1:    number
  cota_sub_d0:    number
  delta_cota_sub: number
}

/** IDs do backend que pertencem ao lado Ativo do balancete (services/balanco.py).
 * Ordem segue a ordem natural retornada pelo backend (top → bottom no balancete). */
const IDS_ATIVO: readonly string[] = [
  "bancos_privados",   // Caixa
  "compromissada",     // LETRAS DO TESOURO NACIONAL (compromissadas)
  "tp",                // NOTAS DO TESOURO NACIONAL
  "dce",               // NOTA COMERCIAL
  "fdi",               // COTAS DE FUNDOS MUTUOS
  "dc",                // Direitos Creditorios
  "pdd",               // (-) PDD
  "liquidacoes",       // Devedores - Conta Liquidacao Pendente
  "desp_antecip",      // Despesas Antecipadas
  "oa_residual",       // Outros Ativos
]

/** IDs do lado Passivo Contabil + Equity. Mez+Sr juntam aqui pois subtraem
 * da Cota Sub identicamente ao Passivo Contabil (perspectiva do cotista
 * subordinado: tudo que tira do PL Total reduz a fatia residual). */
const IDS_PASSIVO: readonly string[] = [
  "iof",         // IOF A RECOLHER
  "prov_pgto",   // PROVISAO PARA PAGAMENTOS A EFETUAR
  "val_adm",     // VALORES A PAGAR A SOCIEDADE ADMINISTRADORA
  "mez",         // Cota Mezanino (equity)
  "sr",          // Cota Senior (equity)
]

export function decomposicaoLinhas(rows: BalanceRow[]): DecomposicaoLinhas {
  const flat = flattenLinhas(rows)
  const indexed = new Map<string, BalanceRow>()
  for (const r of flat) indexed.set(r.id, r)

  function lookup(ids: readonly string[], lado: "ativo" | "passivo"): LinhaContribuicao[] {
    const sinal = lado === "ativo" ? 1 : -1
    return ids
      .map((id) => indexed.get(id))
      .filter((r): r is BalanceRow => r !== undefined)
      .map((r) => ({
        id:                    r.id,
        label:                 r.label,
        lado,
        delta:                 r.delta ?? 0,
        contribuicao_cota_sub: sinal * (r.delta ?? 0),
      }))
  }

  const ativo   = lookup(IDS_ATIVO, "ativo")
  const passivo = lookup(IDS_PASSIVO, "passivo")

  const cotaSubRow   = indexed.get("total")
  const cota_sub_d1  = cotaSubRow?.d1 ?? 0
  const cota_sub_d0  = cotaSubRow?.d0 ?? 0
  const delta_cota_sub = cota_sub_d0 - cota_sub_d1

  return { ativo, passivo, cota_sub_d1, cota_sub_d0, delta_cota_sub }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Achata recursivamente a arvore de BalanceRow em uma lista de linhas
 * (incluindo subRows — necessario para encontrar bancos_privados, mez, etc.
 * que vem como filhos dos no-raiz "ativo" / "passivo-contabil" / "equity"). */
function flattenLinhas(rows: BalanceRow[]): BalanceRow[] {
  const out: BalanceRow[] = []
  function walk(r: BalanceRow) {
    out.push(r)
    if (r.subRows) for (const sub of r.subRows) walk(sub)
  }
  for (const r of rows) walk(r)
  return out
}

function sumNullable(values: (number | null)[]): number {
  return values.reduce<number>((acc, v) => acc + (v ?? 0), 0)
}
