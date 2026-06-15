// Layout do organograma do grupo economico.
//
// Modo RAIAS POR SEGMENTO: cada segmento de atuacao (ver segment.ts) vira uma
// coluna; as empresas daquele segmento empilham verticalmente. Pessoas (PF)
// ficam na raia "Pessoas". A posicao inicial e so um ponto de partida — os nos
// sao ARRASTAVEIS (conectores seguem), entao o usuario reorganiza a mao.
//
// Filtro de papel: "all" | "socio" | "admin" — recorta as arestas pela
// qualificacao (SOCIO* x ADMINISTRADOR/DIRETOR/PRESIDENTE/CONSELHEIRO) e some
// com nos que ficam sem nenhum vinculo (exceto a raiz).

import type { Edge, Node } from "@xyflow/react"

import { ORG_NODE_H, ORG_NODE_W, type OrgNodeData } from "../_components/OrgNode"
import type { OrgEdgeRaw, OrgNodeRaw } from "../_data/quimassa"
import { SEGMENTS, SEGMENT_BY_KEY, classifySegment, type SegmentKey } from "./segment"

export type RoleFilter = "all" | "socio" | "admin"
export type LayoutMode = "hierarchy" | "lanes" | "radial"

const COL_W = ORG_NODE_W + 40 // espaco entre sub-colunas dentro da raia
const ROW_H = ORG_NODE_H + 24 // espaco vertical entre nos
const LANE_GAP = 72 // folga entre raias de segmento
const ROWS_PER_COL = 14 // raia quebra em sub-colunas a cada N nos (evita coluna gigante)
const HEADER_Y = -84 // titulo da raia acima da 1a linha

// Layout B (radial): aneis concentricos por nivel
const RADIAL_BASE_R = 460 // raio do 1o anel
const RADIAL_MIN_ARC = 300 // arco minimo por no (evita sobreposicao -> anel cresce se preciso)

const SEG_ORDER = new Map(SEGMENTS.map((s, i) => [s.key, i]))

export type SegHeaderData = { label: string; color: string; count: number }

export type BuiltGraph = {
  nodes: Node<OrgNodeData | SegHeaderData>[]
  edges: Edge[]
}

/** Qualificacao -> flags de papel. SOCIO-ADMINISTRADOR conta nos dois. */
export function classifyRole(label: string): { isSocio: boolean; isAdmin: boolean } {
  const up = (label || "").toUpperCase()
  const isSocio =
    up.includes("SOCIO") ||
    up.includes("COTAS EM TESOURARIA") ||
    up.includes("TITULAR")
  const isAdmin = /ADMINISTRADOR|DIRETOR|PRESIDENTE|CONSELHEIRO|PROCURADOR/.test(up)
  return { isSocio, isAdmin }
}

function edgePassesRole(label: string, filter: RoleFilter): boolean {
  if (filter === "all") return true
  const { isSocio, isAdmin } = classifyRole(label)
  return filter === "socio" ? isSocio : isAdmin
}

export function buildGraph(
  rawNodes: OrgNodeRaw[],
  rawEdges: OrgEdgeRaw[],
  opts: {
    rootId: string
    showInactive: boolean
    roleFilter: RoleFilter
    maxLevel: number
    mode: LayoutMode
  },
): BuiltGraph {
  const { rootId, showInactive, roleFilter, maxLevel, mode } = opts

  // 1. arestas: filtra por status + papel + profundidade (ambas as pontas <= maxLevel)
  const levelOf = new Map(rawNodes.map((n) => [n.id, n.level]))
  const kindOf = new Map(rawNodes.map((n) => [n.id, n.kind]))
  const withinLevel = (id: string) => (levelOf.get(id) ?? 99) <= maxLevel
  const keptEdges = rawEdges.filter(
    (e) =>
      (showInactive || e.active) &&
      edgePassesRole(e.label, roleFilter) &&
      withinLevel(e.source) &&
      withinLevel(e.target),
  )

  // 2. nos visiveis = raiz + tudo que sobrou conectado (dentro do nivel)
  const connected = new Set<string>([rootId])
  for (const e of keptEdges) {
    connected.add(e.source)
    connected.add(e.target)
  }
  const visible = rawNodes.filter((n) => connected.has(n.id) && n.level <= maxLevel)
  const visibleIds = new Set(visible.map((n) => n.id))
  const edges = keptEdges.filter((e) => visibleIds.has(e.source) && visibleIds.has(e.target))

  // Orientacao de PROPRIEDADE (dono -> participada), p/ a hierarquia societaria:
  //   - PF e sempre dono -> fica ACIMA da PJ;
  //   - entre PJs (ou PFs), a entidade mais distante da raiz (descoberta como
  //     sócia) fica acima da mais próxima.
  // owner = quem fica em cima; owned = quem fica embaixo.
  const ownerOwned = (a: string, b: string): [owner: string, owned: string] => {
    const ka = kindOf.get(a)
    const kb = kindOf.get(b)
    if (ka === "PF" && kb === "PJ") return [a, b]
    if (ka === "PJ" && kb === "PF") return [b, a]
    const la = levelOf.get(a) ?? 0
    const lb = levelOf.get(b) ?? 0
    return la >= lb ? [a, b] : [b, a]
  }

  // 3. segmento de cada no (cor + agrupamento)
  const segOf = new Map<string, SegmentKey>()
  for (const n of visible) {
    segOf.set(n.id, classifySegment(n.name, n.kind))
  }
  const colorOf = (id: string) => SEGMENT_BY_KEY[segOf.get(id) ?? "outros"].color
  const orgData = (n: OrgNodeRaw): OrgNodeData => ({
    name: n.name,
    doc: n.doc,
    kind: n.kind,
    active: n.active,
    isRoot: n.id === rootId,
    segmentColor: colorOf(n.id),
  })

  // 4. posiciona conforme o modo
  const nodes: Node<OrgNodeData | SegHeaderData>[] = []

  if (mode === "lanes") {
    // RAIAS POR SEGMENTO — cada raia quebra em sub-colunas (grid).
    const bySeg = new Map<SegmentKey, OrgNodeRaw[]>()
    for (const n of visible) {
      const seg = segOf.get(n.id)!
      const arr = bySeg.get(seg) ?? []
      arr.push(n)
      bySeg.set(seg, arr)
    }
    const segsPresent = SEGMENTS.filter((s) => bySeg.has(s.key))
    let cursorX = 0
    segsPresent.forEach((seg) => {
      const arr = bySeg
        .get(seg.key)!
        .slice()
        .sort((a, b) => a.level - b.level || a.name.localeCompare(b.name))
      const subCols = Math.max(1, Math.ceil(arr.length / ROWS_PER_COL))
      nodes.push({
        id: `__seg_${seg.key}`,
        type: "segHeader",
        position: { x: cursorX, y: HEADER_Y },
        draggable: false,
        selectable: false,
        data: { label: seg.label, color: seg.color, count: arr.length },
      })
      arr.forEach((n, i) => {
        nodes.push({
          id: n.id,
          type: "org",
          position: {
            x: cursorX + Math.floor(i / ROWS_PER_COL) * COL_W,
            y: (i % ROWS_PER_COL) * ROW_H,
          },
          data: orgData(n),
        })
      })
      cursorX += subCols * COL_W + LANE_GAP
    })
  } else if (mode === "radial") {
    // REDE / RADIAL (Layout B) — raiz no centro, aneis por nivel; dentro do
    // anel os nos sao ordenados por segmento (vira "fatia" angular) + nome.
    const byLevel = new Map<number, OrgNodeRaw[]>()
    for (const n of visible) {
      const arr = byLevel.get(n.level) ?? []
      arr.push(n)
      byLevel.set(n.level, arr)
    }
    for (const [lvl, arr] of Array.from(byLevel.entries())) {
      if (lvl === 0) {
        const r = arr[0]
        nodes.push({ id: r.id, type: "org", position: { x: 0, y: 0 }, data: orgData(r) })
        continue
      }
      arr.sort(
        (a, b) =>
          (SEG_ORDER.get(segOf.get(a.id)!) ?? 99) - (SEG_ORDER.get(segOf.get(b.id)!) ?? 99) ||
          a.name.localeCompare(b.name),
      )
      // raio cresce se o anel tiver muitos nos (evita sobreposicao)
      const radius = Math.max(
        lvl * RADIAL_BASE_R,
        (arr.length * RADIAL_MIN_ARC) / (2 * Math.PI),
      )
      arr.forEach((n, i) => {
        const ang = (i / arr.length) * 2 * Math.PI - Math.PI / 2
        nodes.push({
          id: n.id,
          type: "org",
          position: {
            x: Math.cos(ang) * radius - ORG_NODE_W / 2,
            y: Math.sin(ang) * radius - ORG_NODE_H / 2,
          },
          data: orgData(n),
        })
      })
    }
  } else {
    // HIERARQUIA SOCIETARIA — dono em cima, participada embaixo. A "camada"
    // (linha) de cada no = maior cadeia de propriedade acima dele (longest
    // path), entao sócios/holdings ficam acima das empresas que controlam.
    const ownersOf = new Map<string, string[]>() // owned -> [owners]
    for (const e of edges) {
      const [owner, owned] = ownerOwned(e.source, e.target)
      if (owner === owned) continue
      const arr = ownersOf.get(owned) ?? []
      arr.push(owner)
      ownersOf.set(owned, arr)
    }
    const memo = new Map<string, number>()
    const layerOf = (id: string, stack: Set<string>): number => {
      const cached = memo.get(id)
      if (cached != null) return cached
      if (stack.has(id)) return 0 // guarda de ciclo (participacao cruzada)
      const owners = ownersOf.get(id) ?? []
      if (owners.length === 0) {
        memo.set(id, 0)
        return 0
      }
      stack.add(id)
      const L = 1 + Math.max(...owners.map((o) => layerOf(o, stack)))
      stack.delete(id)
      memo.set(id, L)
      return L
    }

    const byLayer = new Map<number, OrgNodeRaw[]>()
    for (const n of visible) {
      const L = layerOf(n.id, new Set())
      const arr = byLayer.get(L) ?? []
      arr.push(n)
      byLayer.set(L, arr)
    }
    const layers = Array.from(byLayer.keys()).sort((a, b) => a - b)
    const HCOL = ORG_NODE_W + 56
    const HROW = ORG_NODE_H + 96
    for (const L of layers) {
      const arr = byLayer
        .get(L)!
        .slice()
        .sort(
          (a, b) =>
            (SEG_ORDER.get(segOf.get(a.id)!) ?? 99) - (SEG_ORDER.get(segOf.get(b.id)!) ?? 99) ||
            a.name.localeCompare(b.name),
        )
      const rowWidth = arr.length * HCOL
      arr.forEach((n, i) => {
        nodes.push({
          id: n.id,
          type: "org",
          position: { x: i * HCOL - rowWidth / 2, y: L * HROW },
          data: orgData(n),
        })
      })
    }
  }

  // 5. arestas soltas (bezier), cor por papel
  const rfEdges: Edge[] = edges.map((e, i) => {
    const { isSocio, isAdmin } = classifyRole(e.label)
    const stroke = !e.active
      ? "#d1d5db"
      : isSocio && isAdmin
        ? "#6366f1"
        : isSocio
          ? "#3b82f6"
          : isAdmin
            ? "#94a3b8"
            : "#9ca3af"
    // Na hierarquia, a aresta vai do DONO (em cima) p/ a PARTICIPADA (embaixo),
    // ligando o handle inferior do dono ao superior da participada.
    const [source, target] =
      mode === "hierarchy" ? ownerOwned(e.source, e.target) : [e.source, e.target]
    return {
      id: `e${i}`,
      source,
      target,
      label: e.label,
      // hierarquia = smoothstep (ortogonal, lê melhor como organograma);
      // demais modos = bezier "solto" que segue o no arrastado.
      type: mode === "hierarchy" ? "smoothstep" : "default",
      labelStyle: { fontSize: 10, fill: "#6b7280" },
      labelBgStyle: { fill: "#ffffff", fillOpacity: 0.85 },
      style: {
        stroke,
        strokeWidth: 1.2,
        strokeDasharray: e.active ? undefined : "4 3",
      },
    }
  })

  return { nodes, edges: rfEdges }
}

// re-export p/ legenda na pagina
export { SEGMENTS, SEGMENT_BY_KEY }
