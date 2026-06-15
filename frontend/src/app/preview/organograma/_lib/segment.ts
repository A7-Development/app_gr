// Classificacao de SEGMENTO de atuacao das empresas do grupo.
//
// IMPORTANTE: heuristica por razao social — o dataset `economic_group_relationships`
// NAO traz CNAE por entidade. Para segmento real, seria preciso 1 `basic_data`
// por empresa (com CNAE). Aqui inferimos pela palavra-chave do nome; pessoas
// (PF) vao para a raia "Pessoas".

export type SegmentKey =
  | "holding"
  | "imobiliario"
  | "engenharia"
  | "mineracao"
  | "alimentos"
  | "servicos"
  | "advocacia"
  | "outros"
  | "pessoas"

export type SegmentMeta = { key: SegmentKey; label: string; color: string }

// Ordem = ordem das raias (colunas) da esquerda p/ direita.
export const SEGMENTS: SegmentMeta[] = [
  { key: "holding", label: "Participações / Holding", color: "#6366f1" },
  { key: "imobiliario", label: "Imobiliário / Incorporação", color: "#0ea5e9" },
  { key: "engenharia", label: "Engenharia / Construção", color: "#14b8a6" },
  { key: "mineracao", label: "Mineração", color: "#f59e0b" },
  { key: "alimentos", label: "Alimentos", color: "#f43f5e" },
  { key: "servicos", label: "Serviços / Consultoria", color: "#8b5cf6" },
  { key: "advocacia", label: "Advocacia", color: "#a855f7" },
  { key: "outros", label: "Outros (PJ)", color: "#64748b" },
  { key: "pessoas", label: "Pessoas (PF)", color: "#9ca3af" },
]

export const SEGMENT_BY_KEY: Record<SegmentKey, SegmentMeta> = Object.fromEntries(
  SEGMENTS.map((s) => [s.key, s]),
) as Record<SegmentKey, SegmentMeta>

export function classifySegment(name: string, kind: "PJ" | "PF"): SegmentKey {
  if (kind === "PF") return "pessoas"
  const n = name.toUpperCase()
  // ordem: atividade concreta antes de "holding" (fallback de participacoes puras)
  if (/IMOB|IMOVEIS|EMPREEND|INCORPORA|REAL ESTATE/.test(n)) return "imobiliario"
  if (/ENGENHARIA|CONSTRU|\bOBRAS\b|INFRAESTRUTURA|RODOVIAR/.test(n)) return "engenharia"
  if (/MINERAC|MINERA\b/.test(n)) return "mineracao"
  if (/ALIMENT/.test(n)) return "alimentos"
  if (/ADVOGAD|ADVOCACIA/.test(n)) return "advocacia"
  if (/CONSULT|GESTAO|ASSESSORIA|SERVICOS|ADMINISTRACAO DE/.test(n)) return "servicos"
  if (/PARTICIPAC|HOLDING|INVESTIMENT/.test(n)) return "holding"
  return "outros"
}
