// _lib/cosif.ts
//
// Tipos UI + helpers para a arvore COSIF da Cota Sub.
//
// Backend devolve `nodes: CosifNode[]` plano, com `parent_codigo` apontando
// para o pai. Aqui montamos a arvore (CosifNodeUI com `subRows`) e fornecemos
// helpers de descoberta/expansao para a Z3 BalanceteDiarioTable e a Z2
// ReconciliacaoWaterfallCard.

import type {
  ClasseBreakdown,
  CosifNode,
  CosifRowDiff,
  CosifRowStatus,
  CosifSource,
} from "@/lib/api-client"

/**
 * No da arvore COSIF para consumo do TanStack Table (com `subRows`).
 * Identico ao `CosifNode` do api-client + `subRows`.
 *
 * Tres tipos de no sintetico:
 *
 *  - `_isClasseRow=true` — quebra Sr/Mez/Sub de uma conta analitica que
 *    carrega classe (ex.: 6.1.1.70.30.001 Cotas Emitidas). Vem do
 *    `classe_breakdown_por_cosif` da BalanceteResponse.
 *
 *  - `_isPaperRow=true` — papel individual (silver row) sustentando o saldo
 *    de uma conta analitica. Vem do `rows_por_cosif` da BalanceteResponse.
 *    Carrega quantidade, indexador, status (novo|removido|alterado|inalterado).
 *
 *  - bucket pendente (`codigo=null`, sem flag) — agregador virtual de rows
 *    sem classificacao COSIF.
 */
export type CosifNodeUI = CosifNode & {
  subRows?: CosifNodeUI[]
  _isClasseRow?: boolean
  _classeLabel?: string
  _isPaperRow?: boolean
  /** Codigo do papel no silver (ex.: "739704"). Pode ser null. */
  _paperCodigo?: string | null
  /** Descricao do papel (ex.: "BB MAXIMA FIA"). Sempre presente. */
  _paperNome?: string
  _paperQtdD0?: number | null
  _paperQtdD1?: number | null
  _paperIndexador?: string | null
  _paperStatus?: CosifRowStatus
  _paperSilverOrigin?: string
  /** Emitente (renda fixa) ou gestor (cota fundo). null nos demais silvers. */
  _paperContraparte?: string | null
}

const _CLASSE_LABEL: Record<string, string> = {
  senior:      "Senior",
  mezanino:    "Mezanino",
  subordinado: "Subordinada",
  compensacao: "Compensacao",
  aporte:      "Aporte",
}

function classeLabel(classe: string): string {
  return _CLASSE_LABEL[classe] ?? (classe.charAt(0).toUpperCase() + classe.slice(1))
}

/**
 * Grupos COSIF "principais" (sempre renderizados em modo padrao).
 * 1 = Ativo / 4 = Passivo / 6 = PL.
 * 8 = Despesas (so aparece em fundos com lancamentos contabeis diarios; em
 *               muitos fundos esta agregado em PL via 6.x — ainda assim
 *               mostramos quando vier do backend).
 */
export const GRUPOS_PRINCIPAIS: ReadonlySet<number> = new Set([1, 4, 6, 8])

/**
 * Grupos COSIF de "compensacao" (controles de custodia).
 * 3 = Ativo de Compensacao / 9 = Passivo de Compensacao.
 * Por default escondidos — toggle "auditoria avancada" liga.
 */
export const GRUPOS_COMPENSACAO: ReadonlySet<number> = new Set([3, 9])

/** Bucket pseudo-grupo para nos `pendente` (sem cosif_codigo). */
export const GRUPO_PENDENTE = 0

/**
 * Reconstroi a arvore a partir do array plano de `nodes`.
 *
 * - Liga child→parent via `parent_codigo`.
 * - Filtra grupos de compensacao (3/9) quando `incluirCompensacao=false`.
 * - Mantem nos `pendente` (codigo=null) sempre — sao bucket separado.
 * - Ordem: por |delta| desc dentro de cada nivel, mas nos com nivel mais
 *   baixo primeiro (quando empate na ordem do array original).
 * - Sintetiza um no virtual "PENDENTE" no topo quando ha rows sem cosif.
 */
export function buildCosifTree(
  nodes: readonly CosifNode[],
  opts: {
    incluirCompensacao?:      boolean
    classeBreakdownPorCosif?: Record<string, readonly ClasseBreakdown[]>
    rowsPorCosif?:            Record<string, readonly CosifRowDiff[]>
  } = {},
): CosifNodeUI[] {
  const incluirCompensacao = opts.incluirCompensacao ?? false
  const breakdowns = opts.classeBreakdownPorCosif ?? {}
  const rowsPorCosif = opts.rowsPorCosif ?? {}

  // Filtra: pendentes vao pro bucket virtual; demais respeitam o toggle de
  // compensacao.
  const pendentes: CosifNode[] = []
  const classificados: CosifNode[] = []
  for (const n of nodes) {
    if (n.codigo === null) {
      pendentes.push(n)
      continue
    }
    if (!incluirCompensacao && GRUPOS_COMPENSACAO.has(n.grupo)) continue
    classificados.push(n)
  }

  // Index por codigo + cria UI shells vazias.
  const byCodigo = new Map<string, CosifNodeUI>()
  for (const n of classificados) {
    byCodigo.set(n.codigo!, { ...n, subRows: [] })
  }

  // Liga child→parent. Quando o parent_codigo do backend nao existe na
  // arvore (poda por grupo, ou parent fora do catalogo), o no vira raiz.
  const roots: CosifNodeUI[] = []
  for (const ui of Array.from(byCodigo.values())) {
    const parent = ui.parent_codigo ? byCodigo.get(ui.parent_codigo) : undefined
    if (parent) {
      parent.subRows!.push(ui)
    } else {
      roots.push(ui)
    }
  }

  // Bucket virtual para pendentes.
  if (pendentes.length > 0) {
    const totalD0 = pendentes.reduce((s, p) => s + p.d_zero, 0)
    const totalD1 = pendentes.reduce((s, p) => s + p.d_minus_1, 0)
    const totalDelta = totalD0 - totalD1
    const totalDeltaPct = totalD1 !== 0 ? (totalDelta / Math.abs(totalD1)) * 100 : 0
    const pendentesUI: CosifNodeUI[] = pendentes.map((p) => ({ ...p, subRows: undefined }))
    const bucket: CosifNodeUI = {
      codigo:          null,
      nome:            "Pendente — sem classificacao COSIF",
      natureza:        "?",
      nivel:           0,
      grupo:           GRUPO_PENDENTE,
      parent_codigo:   null,
      d_minus_1:       totalD1,
      d_zero:          totalD0,
      delta:           totalDelta,
      delta_pct:       totalDeltaPct,
      rows_classified: pendentes.reduce((s, p) => s + (p.rows_classified || 0), 0),
      cosif_source:    "pendente",
      subRows:         pendentesUI,
    }
    roots.push(bucket)
  }

  // Injeta breakdown por classe (Sr/Mez/Sub) como subRows sinteticas das
  // contas analiticas que carregam classe. Pivot-hide-aggregate da
  // BalanceteDiarioTable esconde o saldo agregado quando expandido —
  // visualmente fica como "drill direto na tabela".
  for (const ui of Array.from(byCodigo.values())) {
    if (!ui.codigo) continue
    const breakdown = breakdowns[ui.codigo]
    if (!breakdown || breakdown.length === 0) continue
    // Skip se a quebra so tem 1 classe (igualaria o agregado, ruido visual).
    if (breakdown.length < 2) continue
    const classeRows: CosifNodeUI[] = breakdown.map((b) => {
      const d_minus_1 = b.d_minus_1
      const d_zero    = b.d_zero
      const delta     = b.delta
      const delta_pct = d_minus_1 !== 0 ? (delta / Math.abs(d_minus_1)) * 100 : 0
      return {
        codigo:          null,
        nome:            classeLabel(b.classe),
        natureza:        ui.natureza,
        nivel:           ui.nivel + 1,
        grupo:           ui.grupo,
        parent_codigo:   ui.codigo,
        d_minus_1,
        d_zero,
        delta,
        delta_pct,
        rows_classified: 0,
        cosif_source:    ui.cosif_source,
        _isClasseRow:    true,
        _classeLabel:    classeLabel(b.classe),
      }
    })
    // Ordem: |d_zero| desc (Senior > Mezanino > Subordinada tipicamente).
    classeRows.sort((a, b) => Math.abs(b.d_zero) - Math.abs(a.d_zero))
    ui.subRows = [...(ui.subRows ?? []), ...classeRows]
  }

  // Injeta papeis (silver rows) como subRows sinteticas das contas analiticas.
  // Vem do `rows_por_cosif` da BalanceteResponse — diff D-1 vs D0 papel-a-papel.
  // Backend ja so popula `rows_por_cosif` para folhas analiticas (cosif_codigo
  // exato do silver classificado) — agrupamento de sinteticas e por
  // _propagate_to_parents, nao gera entrada em rows_por_cosif.
  for (const ui of Array.from(byCodigo.values())) {
    if (!ui.codigo) continue
    const papers = rowsPorCosif[ui.codigo]
    if (!papers || papers.length === 0) continue
    const paperRows: CosifNodeUI[] = papers.map((p) => {
      const delta_pct = p.valor_d_minus_1 !== 0
        ? (p.delta / Math.abs(p.valor_d_minus_1)) * 100
        : 0
      return {
        codigo:             null,  // sintetico, sem codigo COSIF
        nome:               p.nome,
        natureza:           ui.natureza,
        nivel:              ui.nivel + 1,
        grupo:              ui.grupo,
        parent_codigo:      ui.codigo,
        d_minus_1:          p.valor_d_minus_1,
        d_zero:             p.valor_d_zero,
        delta:              p.delta,
        delta_pct,
        rows_classified:    1,
        cosif_source:       p.cosif_source,
        _isPaperRow:        true,
        _paperCodigo:       p.codigo,
        _paperNome:         p.nome,
        _paperQtdD0:        p.quantidade_d_zero,
        _paperQtdD1:        p.quantidade_d_minus_1,
        _paperIndexador:    p.indexador,
        _paperStatus:       p.status,
        _paperSilverOrigin: p.silver_origin,
        _paperContraparte:  p.contraparte,
      }
    })
    ui.subRows = [...(ui.subRows ?? []), ...paperRows]
  }

  // Sort recursivo: roots por grupo (1, 4, 6, 8, depois compensacao 3/9,
  // pendente 0 por ultimo), demais niveis por |delta| desc.
  roots.sort(_sortRoots)
  for (const root of roots) {
    sortByAbsDeltaDesc(root.subRows)
  }

  return roots
}

const _GRUPO_ORDER: Record<number, number> = {
  1: 0,  // Ativo
  4: 1,  // Passivo
  6: 2,  // PL
  8: 3,  // Despesa
  7: 4,  // Receita (raro)
  3: 5,  // Compensacao (Ativo)
  9: 6,  // Compensacao (Passivo)
  0: 99, // Pendente
}

function _sortRoots(a: CosifNodeUI, b: CosifNodeUI): number {
  const oa = _GRUPO_ORDER[a.grupo] ?? 50
  const ob = _GRUPO_ORDER[b.grupo] ?? 50
  if (oa !== ob) return oa - ob
  // Dentro do mesmo grupo: codigo asc (ordem natural COSIF)
  return (a.codigo ?? "").localeCompare(b.codigo ?? "")
}

function sortByAbsDeltaDesc(rows?: CosifNodeUI[]): void {
  if (!rows || rows.length === 0) return
  rows.sort((a, b) => Math.abs(b.delta) - Math.abs(a.delta))
  for (const r of rows) sortByAbsDeltaDesc(r.subRows)
}

/**
 * Conjunto de codigos para expandir por default — todos os nos de nivel
 * <= `ate` que tem subRows. Frontend passa esse Set para o `expanded` do
 * TanStack Table.
 */
export function defaultExpandedCodigos(
  tree: CosifNodeUI[],
  ate: number = 3,
): Set<string> {
  const out = new Set<string>()
  function walk(rows: CosifNodeUI[] | undefined): void {
    if (!rows) return
    for (const r of rows) {
      if (r.codigo && r.nivel <= ate && r.subRows && r.subRows.length > 0) {
        out.add(r.codigo)
      }
      walk(r.subRows)
    }
  }
  walk(tree)
  // Bucket pendente sempre expandido (ja que e raro e proeminente quando aparece)
  for (const r of tree) {
    if (r.codigo === null) {
      // bucket pendente nao tem codigo pra expandir via TanStack — ignorado
    }
  }
  return out
}

/**
 * Encontra um no por codigo (DFS na arvore).
 */
export function findNodeByCodigo(
  tree: readonly CosifNodeUI[],
  codigo: string,
): CosifNodeUI | undefined {
  for (const n of tree) {
    if (n.codigo === codigo) return n
    if (n.subRows) {
      const found = findNodeByCodigo(n.subRows, codigo)
      if (found) return found
    }
  }
  return undefined
}

/**
 * Soma de saldo D0 dos nos do grupo informado (raiz da arvore).
 * Usado por KPIs derivados (Ativo total, Passivo total, etc).
 */
export function somaGrupo(
  tree: readonly CosifNodeUI[],
  grupo: number,
  field: "d_minus_1" | "d_zero" | "delta",
): number {
  return tree
    .filter((n) => n.grupo === grupo)
    .reduce((s, n) => s + (n[field] as number), 0)
}

/**
 * Mapping de cosif_source para badge color/label.
 */
export const SOURCE_BADGE: Record<string, { label: string; tone: "green" | "blue" | "amber" | "red" | "gray" }> = {
  override:  { label: "Override",  tone: "blue"  },
  rule:      { label: "Regra",     tone: "green" },
  mixed:     { label: "Misto",     tone: "amber" },
  pendente:  { label: "Pendente",  tone: "red"   },
}

export function sourceBadge(source: CosifSource): { label: string; tone: "green" | "blue" | "amber" | "red" | "gray" } {
  return SOURCE_BADGE[source] ?? { label: source || "—", tone: "gray" }
}
