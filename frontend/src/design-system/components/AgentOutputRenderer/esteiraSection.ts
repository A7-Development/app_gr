// src/design-system/components/AgentOutputRenderer/esteiraSection.ts
//
// MAPPER GENÉRICO por SHAPE (não por agente). Converte o output de QUALQUER
// specialist agent da esteira que siga a gramática canônica de julgamento
// (resumo_executivo + campos de leitura + pontos_de_atencao + leitura_para_credito)
// num SectionDescriptor de blocos -> renderiza no <SectionRenderer> único.
//
// Por que existe: agente novo que emite esse shape vira plug-and-play na tela
// (e, espelhado no backend, no PDF e no consolidador) SEM código por agente.
// É o fallback do AgentOutputRenderer no lugar do JSON cru. Agentes com schema
// rico e próprio (opinion_writer, indebtedness) seguem com view dedicada.

import type {
  Apontamento,
  Block,
  FichaCampo,
  SectionDescriptor,
} from "@/design-system/types/section"

type Dict = Record<string, unknown>

// Campos tratados à parte — não entram na Ficha genérica.
const RESERVED = new Set([
  "resumo_executivo",
  "pontos_de_atencao",
  "leitura_para_credito",
])

// Rótulos mais bonitos para agentes conhecidos (display only — não é lógica;
// agente desconhecido cai no humanize, então continua plug-and-play).
const AGENT_LABEL: Record<string, string> = {
  porte_analyst: "Porte",
  societario_analyst: "Societário",
  kyc_analyst: "KYC",
  cadastral_analyst: "Cadastral",
  revenue_analyst: "Faturamento",
}

/** snake_case -> "Título legível" (sem inventar acento). Tira sufixo `_leitura`. */
function humanize(key: string): string {
  const base = key.replace(/_leitura$/, "").replace(/_/g, " ").trim()
  return base.charAt(0).toUpperCase() + base.slice(1)
}

function agentLabel(agentName: string | null | undefined): string {
  if (!agentName) return "Análise"
  return AGENT_LABEL[agentName] ?? humanize(agentName.replace(/_analyst$/, ""))
}

/** "alta/media/baixa" OU "critico/atencao/info" -> severidade canônica. */
function toSeveridade(s: unknown): Apontamento["severidade"] {
  const v = String(s ?? "").toLowerCase()
  if (v === "critico" || v === "alta") return "critico"
  if (v === "atencao" || v === "media") return "atencao"
  return "info"
}

function scalarToStr(v: unknown): string {
  if (typeof v === "boolean") return v ? "Sim" : "Não"
  if (v === null || v === undefined) return "—"
  return String(v)
}

/** O output tem a gramática de julgamento da esteira? (decide genérico vs JSON cru) */
export function hasEsteiraShape(output: Dict | null | undefined): boolean {
  if (!output) return false
  return (
    typeof output.resumo_executivo === "string" ||
    typeof output.leitura_para_credito === "string"
  )
}

/**
 * output (shape de julgamento) -> SectionDescriptor. Genérico: itera os campos,
 * sem conhecer nomes de agente. Blocos na ordem: conclusão · ficha (leituras
 * escalares) · listas de string (bullets) · apontamentos · leitura para crédito.
 */
export function esteiraOutputToSection(
  agentName: string | null | undefined,
  output: Dict,
): SectionDescriptor {
  const label = agentLabel(agentName)
  const slug = (agentName ?? "agente").replace(/[^a-z0-9]+/gi, "-")
  const blocks: Block[] = []

  // 1) Conclusão (resumo_executivo).
  if (typeof output.resumo_executivo === "string" && output.resumo_executivo) {
    blocks.push({
      id: `${slug}-conclusao`,
      type: "conclusao_agente",
      agente: label,
      resumo: output.resumo_executivo,
      homologado: false,
    })
  }

  // 2) Ficha — todo campo ESCALAR (string/number/bool) que não é reservado.
  const campos: FichaCampo[] = []
  const listaStr: { key: string; itens: string[] }[] = []
  for (const [key, val] of Object.entries(output)) {
    if (RESERVED.has(key)) continue
    if (Array.isArray(val)) {
      // Lista de strings vira bullets (ex.: achados_alta_confianca).
      const itens = val.filter((x): x is string => typeof x === "string")
      if (itens.length > 0) listaStr.push({ key, itens })
      continue // listas de objetos (que não pontos_de_atencao) ficam de fora
    }
    if (val === null || val === undefined) continue
    if (typeof val === "object") continue
    campos.push({ label: humanize(key), valor: scalarToStr(val) })
  }
  if (campos.length > 0) {
    blocks.push({ id: `${slug}-ficha`, type: "ficha", campos })
  }

  // 3) Listas de string (achados etc.) — cada uma um bloco de texto com bullets.
  for (const { key, itens } of listaStr) {
    blocks.push({
      id: `${slug}-${key}`,
      type: "texto",
      titulo: humanize(key),
      markdown: itens.map((i) => `- ${i}`).join("\n"),
    })
  }

  // 4) Apontamentos (pontos_de_atencao: [{tipo?, severidade, observacao}]).
  const pontos = Array.isArray(output.pontos_de_atencao)
    ? (output.pontos_de_atencao as Dict[])
    : []
  if (pontos.length > 0) {
    blocks.push({
      id: `${slug}-pontos`,
      type: "apontamentos",
      itens: pontos.map((p) => ({
        severidade: toSeveridade(p.severidade),
        titulo: String(p.tipo ?? p.titulo ?? "Ponto de atenção"),
        descricao:
          typeof p.observacao === "string"
            ? p.observacao
            : typeof p.descricao === "string"
              ? p.descricao
              : undefined,
      })),
    })
  }

  // 5) Leitura para crédito (texto livre).
  if (
    typeof output.leitura_para_credito === "string" &&
    output.leitura_para_credito
  ) {
    blocks.push({
      id: `${slug}-leitura-credito`,
      type: "texto",
      titulo: "Leitura para crédito",
      markdown: output.leitura_para_credito,
    })
  }

  return {
    id: `section-${slug}`,
    stationId: slug,
    titulo: label,
    blocks,
    generatesDossierSection: true,
  }
}
