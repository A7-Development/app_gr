// src/app/(app)/credito/workflows/[id]/editor/_lib/etapas.ts
//
// Catalogo de ETAPAS da palette do editor — organizado por JORNADA do
// dominio, NAO por categoria tecnica do backend.
//
// O backend retorna `NodeTypeMeta[]` em /credito/node-types com categorias
// tecnicas (`triggers`, `humano`, `coleta`, `agentes`, `logica`,
// `integracao`, `output`). Este arquivo MAPEIA cada NodeTypeMeta pra uma
// das 6 categorias-jornada visiveis ao usuario.
//
// Para etapas "Analise IA", ainda expandimos cada agente do catalog em uma
// linha propria da palette (ex.: "Analise financeira" arrastavel direto,
// nao precisa arrastar specialist_agent generico e configurar `agent`).

import type { NodeTypeMeta } from "@/lib/credito-client"

import { AGENT_FRIENDLY_LABEL, ETAPA_LABEL } from "./glossary"

export type JourneyCategory =
  | "inicio"
  | "coletar"
  | "enriquecer"
  | "ia"
  | "decisao"
  | "notificar"

export const JOURNEY_LABEL: Record<JourneyCategory, string> = {
  inicio: "Inicio",
  coletar: "Coletar do analista",
  enriquecer: "Enriquecer com dados externos",
  ia: "Processar com IA",
  decisao: "Decisoes & Fluxo",
  notificar: "Notificar / Entregar",
}

export const JOURNEY_HINT: Record<JourneyCategory, string> = {
  inicio: "Toda analise comeca aqui.",
  coletar: "Pedir dados/documentos para o analista preencher.",
  enriquecer: "Buscar dados externos (bureaus, integracoes).",
  ia: "Acionar agentes IA para analise automatizada.",
  decisao: "Sincronizar e ramificar o fluxo.",
  notificar: "Notificar pessoas e gerar saidas finais.",
}

// Mapa de categoria tecnica do backend → categoria-jornada visivel.
const TECH_TO_JOURNEY: Record<string, JourneyCategory> = {
  triggers: "inicio",
  humano: "coletar",
  coleta: "coletar",       // document_request
  integracao: "enriquecer", // bureau_query, http_request
  agentes: "ia",
  logica: "decisao",        // conditional_branch, parallel
  output: "notificar",      // output_generator, notification
}

// Para tipos do backend que precisam ser AGRUPADOS na mesma jornada mas
// vem com categoria tecnica diferente (ex.: human_review e logica de
// "humano" mas e mais "decisao manual" — vai pra decisao na jornada).
const TYPE_OVERRIDE: Record<string, JourneyCategory> = {
  human_review: "decisao", // pausa pra revisao manual e parte do fluxo, nao coleta
}

export function categoryToJourney(meta: NodeTypeMeta): JourneyCategory {
  if (TYPE_OVERRIDE[meta.type]) return TYPE_OVERRIDE[meta.type]
  return TECH_TO_JOURNEY[meta.category] ?? "decisao"
}

// ─── PaletteEntry ────────────────────────────────────────────────────────
//
// Cada item arrastavel da palette. A maioria dos entries vira de
// NodeTypeMeta, mas etapas "specialist_agent" sao expandidas em multiplos
// entries (1 por agente do catalog).

export type PaletteEntry = {
  /** Identificador unico do entry. Para nos genericos = nodeType. Para
   * agentes especialistas = `specialist_agent:<agent_name>`. */
  paletteId: string
  /** Tipo de no que sera criado no graph. */
  nodeType: string
  /** Config inicial — para specialist_agent inclui `agent`. */
  initialConfig: Record<string, unknown>
  /** Nome amigavel exibido. */
  label: string
  /** Descricao curta (tooltip). */
  description: string
  /** Icone Remix (component name). */
  icon: string
  /** Disponivel para arrastar (false = "em breve"). */
  available: boolean
  /** Categoria-jornada na palette. */
  journey: JourneyCategory
}

// Catalogo de specialist agents que viram entries proprios na palette.
// (Nao confundir com backend/app/shared/agents/catalog.py — aqui so
// listamos quais agentes APARECEM como entry na palette.)
export const SPECIALIST_AGENT_PALETTE: Array<{
  agent: string
  description: string
  icon?: string
}> = [
  { agent: "document_extractor",       description: "IA extrai dados estruturados de PDFs e imagens (multimodal)." },
  { agent: "social_contract_analyst",  description: "IA avalia QSA, poderes, restricoes do contrato social." },
  { agent: "financial_analyst",        description: "IA avalia DRE/Balanco/Faturamento — indicadores e tendencias." },
  { agent: "indebtedness_analyst",     description: "IA estima capacidade de pagamento via SCR + dividas." },
  { agent: "legal_analyst",            description: "IA classifica risco de processos judiciais e protestos." },
  { agent: "partner_analyst",          description: "IA cruza socios com bureaus e processos." },
  { agent: "commercial_visit_analyst", description: "IA confronta visita comercial com declaracoes da empresa." },
  { agent: "cross_reference_analyst",  description: "IA detecta inconsistencias entre todas as analises." },
  { agent: "opinion_writer",           description: "IA escreve parecer consolidado com recomendacao final." },
  { agent: "pleito_extractor",         description: "IA extrai produto/volume/taxa/prazo de email/texto livre." },
]

// Catalogo de CONSULTAS DE BUREAU que aparecem na palette.
//
// Hoje so `serasa_pj` esta wired no backend (ver _WIRED_ADAPTERS em
// `backend/app/shared/workflow/nodes/bureau_query.py`). Os 4 produtos
// nomeados (Dados Basicos RFB, Processos Detalhado, etc.) sao
// placeholders pra fontes futuras — quando uma API for ligada, basta
// flippar `available: true` e ajustar o `config` pro adapter correto.
//
// `data_product` e uma chave estavel pra roteamento futuro — quando o
// backend ganhar logica "se data_product=X usar adapter Y", a UI nao
// precisa mudar.
export const DATA_PRODUCT_PALETTE: Array<{
  /** Chave estavel do entry — diferencia paletteId. */
  key: string
  label: string
  description: string
  available: boolean
  /** Config aplicada ao criar a etapa. */
  config: Record<string, unknown>
}> = [
  {
    key: "serasa_pj",
    label: "Consultar Serasa PJ",
    description: "Business Information Report — score, restricoes, protestos, socios, participacoes.",
    available: true,
    config: {
      adapter: "serasa_pj",
      entity_ref: "{{trigger.cnpj}}",
      environment: "production",
    },
  },
  {
    key: "dados_basicos_rfb",
    label: "Dados Basicos RFB",
    description: "Cadastro da empresa: CNAE, situacao, enderecos, socios, capital social.",
    available: false,
    config: {
      data_product: "dados_basicos_rfb",
      entity_ref: "{{trigger.cnpj}}",
      environment: "production",
    },
  },
  {
    key: "processos_detalhado",
    label: "Processos Detalhado",
    description: "Processos judiciais detalhados — partes, valores, foro, classificacao.",
    available: false,
    config: {
      data_product: "processos_detalhado",
      entity_ref: "{{trigger.cnpj}}",
      environment: "production",
    },
  },
  {
    key: "protestos_detalhado",
    label: "Protestos Detalhado",
    description: "Protestos formais com valor, cartorio, data e situacao atual.",
    available: false,
    config: {
      data_product: "protestos_detalhado",
      entity_ref: "{{trigger.cnpj}}",
      environment: "production",
    },
  },
  {
    key: "relacionamento_pj",
    label: "Relacionamento PJ",
    description: "Empresas relacionadas via socios em comum, predecessoras, referencias.",
    available: false,
    config: {
      data_product: "relacionamento_pj",
      entity_ref: "{{trigger.cnpj}}",
      environment: "production",
    },
  },
]

// ─── Build palette entries ───────────────────────────────────────────────
//
// Pega o `nodeTypes[]` que vem do backend e gera a lista de entries para
// a palette, ja agrupada por categoria-jornada.

export function buildPaletteEntries(nodeTypes: NodeTypeMeta[]): PaletteEntry[] {
  const entries: PaletteEntry[] = []

  for (const meta of nodeTypes) {
    if (meta.type === "specialist_agent") {
      // Expandir um entry por agente do catalogo.
      for (const ag of SPECIALIST_AGENT_PALETTE) {
        entries.push({
          paletteId: `specialist_agent:${ag.agent}`,
          nodeType: "specialist_agent",
          initialConfig: { agent: ag.agent },
          label: AGENT_FRIENDLY_LABEL[ag.agent] ?? ag.agent,
          description: ag.description,
          icon: meta.icon,
          available: meta.available,
          journey: "ia",
        })
      }
      continue
    }

    if (meta.type === "bureau_query") {
      // Expandir cada consulta como entry proprio. Serasa PJ e o unico
      // wired hoje; os outros 4 produtos sao placeholders "em breve".
      for (const p of DATA_PRODUCT_PALETTE) {
        entries.push({
          paletteId: `bureau_query:${p.key}`,
          nodeType: "bureau_query",
          initialConfig: { ...p.config },
          label: p.label,
          description: p.description,
          icon: meta.icon,
          available: meta.available && p.available,
          journey: "enriquecer",
        })
      }
      continue
    }

    entries.push({
      paletteId: meta.type,
      nodeType: meta.type,
      initialConfig: {},
      label: ETAPA_LABEL[meta.type] ?? meta.label,
      description: meta.description,
      icon: meta.icon,
      available: meta.available,
      journey: categoryToJourney(meta),
    })
  }

  return entries
}

export function groupByJourney(
  entries: PaletteEntry[],
): Record<JourneyCategory, PaletteEntry[]> {
  const out: Record<JourneyCategory, PaletteEntry[]> = {
    inicio: [],
    coletar: [],
    enriquecer: [],
    ia: [],
    decisao: [],
    notificar: [],
  }
  for (const e of entries) out[e.journey].push(e)
  return out
}

export const JOURNEY_ORDER: JourneyCategory[] = [
  "inicio",
  "coletar",
  "enriquecer",
  "ia",
  "decisao",
  "notificar",
]
