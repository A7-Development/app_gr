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
  | "transformar"
  | "decisao"
  | "notificar"

export const JOURNEY_LABEL: Record<JourneyCategory, string> = {
  inicio: "Inicio (gatilhos)",
  coletar: "Coletar do analista",
  enriquecer: "Enriquecer com dados externos",
  ia: "Processar com IA",
  transformar: "Transformar dados",
  decisao: "Decisoes e roteamento",
  notificar: "Saidas e notificacoes",
}

export const JOURNEY_HINT: Record<JourneyCategory, string> = {
  inicio: "Toda analise comeca aqui.",
  coletar: "Pedir dados/documentos para o analista preencher.",
  enriquecer: "Buscar dados externos (bureaus, integracoes).",
  ia: "Acionar agentes IA para analise automatizada.",
  transformar: "Combinar e reformatar dados sem IA — regra fixa.",
  decisao: "Sincronizar e ramificar o fluxo.",
  notificar: "Notificar pessoas e gerar saidas finais.",
}

// Defaults injetados em `initialConfig` por nodeType — quando o backend
// exige config minima pra `validate_config` passar, palette ja nasce com
// valor sensato pra que graph_validator consiga instanciar e expor o
// produces() das variaveis upstream desde o primeiro instante.
//
// human_input: form_id e obrigatorio. Default "form" funciona out-of-the-box
// e o usuario renomeia se quiser. Sem isso, validate_config falha, e o
// RefField downstream nao acha as variaveis dos `fields`.
//
// document_extractor: o node-type que LE o arquivo (run_document_extraction
// -> _load_document_content_block -> bloco multimodal). DocumentExtractorNode
// .validate_config exige `for_each: "uploaded_documents"` + `agent`. Sem este
// default o node nasce incompleto e falha na validacao/execucao (o Inspector
// so deixa trocar o agente, nao seta o for_each). Nao confundir com o
// specialist_agent homonimo, que roda o agente SEM anexar o documento.
const TYPE_INITIAL_CONFIG: Record<string, Record<string, unknown>> = {
  human_input: { form_id: "form" },
  document_extractor: { for_each: "uploaded_documents", agent: "document_extractor" },
}

// Mapa de categoria tecnica do backend → categoria-jornada visivel.
const TECH_TO_JOURNEY: Record<string, JourneyCategory> = {
  triggers: "inicio",
  humano: "coletar",
  coleta: "coletar",       // document_request
  integracao: "enriquecer", // bureau_query, http_request
  agentes: "ia",
  transformar: "transformar", // consolidator (deterministico, sem IA)
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
  /** Marca entries para aparecerem tambem no grupo virtual "Destaques" no
   *  topo da palette. Curado a mao (sem tracking) — flag em entries que
   *  o time decide promover (uso frequente, centrais ao caso de credito). */
  featured?: boolean
}

// Catalogo de specialist agents que viram entries proprios na palette.
// (Nao confundir com backend/app/shared/agents/catalog.py — aqui so
// listamos quais agentes APARECEM como entry na palette.)
//
// `icon` substitui o RiRobot2Line generico do tipo specialist_agent. Cada
// agente ganha icone proprio sinalizando seu dominio — variedade visual
// comunica a riqueza do catalogo.
export const SPECIALIST_AGENT_PALETTE: Array<{
  agent: string
  description: string
  icon?: string
}> = [
  // NOTA: `document_extractor` NAO entra aqui. A extracao multimodal que LE o
  // arquivo e o node-type `document_extractor` (grupo Coletar / "Extrair
  // Documentos"), nao um specialist_agent. Um specialist_agent com
  // agent=document_extractor rodaria run_specialist_agent, que nao anexa o
  // documento — extracao vazia. Ver TYPE_INITIAL_CONFIG acima.
  { agent: "social_contract_analyst",  description: "IA avalia QSA, poderes, restricoes do contrato social.",         icon: "RiFileList3Line" },
  { agent: "financial_analyst",        description: "IA avalia DRE/Balanco/Faturamento — indicadores e tendencias.",  icon: "RiBarChart2Line" },
  { agent: "indebtedness_analyst",     description: "IA estima capacidade de pagamento via SCR + dividas.",           icon: "RiBankLine" },
  { agent: "legal_analyst",            description: "IA classifica risco de processos judiciais e protestos.",        icon: "RiScales3Line" },
  { agent: "partner_analyst",          description: "IA cruza socios com bureaus e processos.",                       icon: "RiTeamLine" },
  { agent: "commercial_visit_analyst", description: "IA confronta visita comercial com declaracoes da empresa.",      icon: "RiMapPin2Line" },
  { agent: "cross_reference_analyst",  description: "IA detecta inconsistencias entre todas as analises.",            icon: "RiNodeTree" },
  { agent: "opinion_writer",           description: "IA escreve parecer consolidado com recomendacao final.",         icon: "RiQuillPenLine" },
  { agent: "pleito_extractor",         description: "IA extrai produto/volume/taxa/prazo de email/texto livre.",      icon: "RiPriceTag3Line" },
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
      entity_ref: "",
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
      entity_ref: "",
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
      entity_ref: "",
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
      entity_ref: "",
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
      entity_ref: "",
      environment: "production",
    },
  },
]

// ─── Build palette entries ───────────────────────────────────────────────
//
// Pega o `nodeTypes[]` que vem do backend e gera a lista de entries para
// a palette, ja agrupada por categoria-jornada.

// Set de paletteIds curados como "Destaques" — aparecem no topo da palette
// num grupo virtual quando o filtro esta vazio. Lista hand-curated; sem
// tracking de uso. Promover/despromover edita esta linha.
const FEATURED_PALETTE_IDS = new Set<string>([
  "bureau_query:serasa_pj",
  "document_extractor",
  "specialist_agent:financial_analyst",
  "specialist_agent:opinion_writer",
  "conditional_branch",
])


export function buildPaletteEntries(nodeTypes: NodeTypeMeta[]): PaletteEntry[] {
  const entries: PaletteEntry[] = []

  for (const meta of nodeTypes) {
    if (meta.type === "specialist_agent") {
      // Expandir um entry por agente do catalogo.
      for (const ag of SPECIALIST_AGENT_PALETTE) {
        const paletteId = `specialist_agent:${ag.agent}`
        entries.push({
          paletteId,
          nodeType: "specialist_agent",
          initialConfig: { agent: ag.agent },
          label: AGENT_FRIENDLY_LABEL[ag.agent] ?? ag.agent,
          description: ag.description,
          icon: ag.icon ?? meta.icon,
          available: meta.available,
          journey: "ia",
          featured: FEATURED_PALETTE_IDS.has(paletteId),
        })
      }
      continue
    }

    if (meta.type === "bureau_query") {
      // Expandir cada consulta como entry proprio. Serasa PJ e o unico
      // wired hoje; os outros 4 produtos sao placeholders "em breve".
      for (const p of DATA_PRODUCT_PALETTE) {
        const paletteId = `bureau_query:${p.key}`
        entries.push({
          paletteId,
          nodeType: "bureau_query",
          initialConfig: { ...p.config },
          label: p.label,
          description: p.description,
          icon: meta.icon,
          available: meta.available && p.available,
          journey: "enriquecer",
          featured: FEATURED_PALETTE_IDS.has(paletteId),
        })
      }
      continue
    }

    entries.push({
      paletteId: meta.type,
      nodeType: meta.type,
      initialConfig: { ...(TYPE_INITIAL_CONFIG[meta.type] ?? {}) },
      label: ETAPA_LABEL[meta.type] ?? meta.label,
      description: meta.description,
      icon: meta.icon,
      available: meta.available,
      journey: categoryToJourney(meta),
      featured: FEATURED_PALETTE_IDS.has(meta.type),
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
    transformar: [],
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
  "transformar",
  "decisao",
  "notificar",
]
