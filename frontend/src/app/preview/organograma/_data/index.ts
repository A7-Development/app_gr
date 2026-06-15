// Registry de empresas do prototipo de organograma. Cada entrada e um
// fixture estatico gerado de um retorno real do BDC `economic_group_relationships`.
// Selecao na pagina via ?empresa=<slug>.

import type { OrgEdgeRaw, OrgNodeRaw } from "./quimassa"
import { ORG_EDGES, ORG_NODES, ROOT_ID } from "./quimassa"
import { ORG_EDGES_E2, ORG_NODES_E2, ROOT_ID_E2 } from "./empresa2"

export type EmpresaDataset = {
  slug: string
  label: string
  doc: string
  rootId: string
  nodes: OrgNodeRaw[]
  edges: OrgEdgeRaw[]
}

export const EMPRESAS: EmpresaDataset[] = [
  {
    slug: "quimassa",
    label: "QUIMASSA",
    doc: "26.239.451/0001-70",
    rootId: ROOT_ID,
    nodes: ORG_NODES,
    edges: ORG_EDGES,
  },
  {
    slug: "pmz",
    label: "PMZ ALIMENTOS",
    doc: "66.129.842/0001-56",
    rootId: ROOT_ID_E2,
    nodes: ORG_NODES_E2,
    edges: ORG_EDGES_E2,
  },
]

export function getEmpresa(slug: string | null | undefined): EmpresaDataset {
  return EMPRESAS.find((e) => e.slug === slug) ?? EMPRESAS[0]
}
