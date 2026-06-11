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

import type { DataProduct, NodeTypeMeta } from "@/lib/credito-client"

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

// ─── Tipo de PRIMITIVO ─────────────────────────────────────────────────────
//
// Eixo ORTOGONAL a jornada. Jornada = "onde no fluxo" (Inicio/Coletar/IA/...);
// tipo de primitivo = "que coisa e" (agente/check/externo/humano/logica/fluxo)
// — o vocabulario travado da esteira. A UI sinaliza o tipo por COR (barra) +
// chip muted, pra ficar claro o que e agente vs check vs consulta externa vs
// passo humano (ex.: "Ler documentos com IA" e agente, mesmo morando em
// Coletar). Derivado do nodeType (override) com fallback por categoria tecnica
// — assim cobre tambem os nos "em breve" (placeholders por categoria).

export type PrimitiveTypeKey =
  | "agente"
  | "check"
  | "externo"
  | "humano"
  | "logica"
  | "io"

export type PrimitiveTypeMeta = {
  key: PrimitiveTypeKey
  label: string
  /** Classe de COR da barra/realce do tipo (sinal pre-atentivo). */
  bar: string
}

export const PRIMITIVE_TYPES: Record<PrimitiveTypeKey, PrimitiveTypeMeta> = {
  agente: { key: "agente", label: "Agente", bar: "bg-violet-500" },
  check: { key: "check", label: "Check", bar: "bg-emerald-500" },
  externo: { key: "externo", label: "Externo", bar: "bg-amber-500" },
  humano: { key: "humano", label: "Humano", bar: "bg-slate-400" },
  logica: { key: "logica", label: "Logica", bar: "bg-sky-500" },
  io: { key: "io", label: "Fluxo", bar: "bg-zinc-400" },
}

// Override por nodeType (precede a categoria). Resolve casos onde a categoria
// tecnica nao separa o tipo — ex.: `coleta` tem document_request (humano) E
// document_extractor (agente de percepcao via Vision).
const PRIMITIVE_BY_NODE: Record<string, PrimitiveTypeKey> = {
  trigger: "io",
  human_input: "humano",
  human_review: "humano",
  document_request: "humano",
  document_extractor: "agente",
  bureau_query: "externo",
  cadastral_enrichment: "externo",
  official_document_fetch: "externo",
  specialist_agent: "agente",
  consolidator: "logica",
  deterministic_check: "check",
  conditional_branch: "logica",
  http_request: "externo",
  notification: "io",
  output_generator: "io",
}

// Fallback por categoria tecnica do backend (cobre placeholders "em breve").
const PRIMITIVE_BY_CATEGORY: Record<string, PrimitiveTypeKey> = {
  triggers: "io",
  humano: "humano",
  coleta: "humano",
  agentes: "agente",
  logica: "logica",
  transformar: "logica",
  integracao: "externo",
  output: "io",
}

export function primitiveTypeFor(
  nodeType: string,
  category?: string,
): PrimitiveTypeMeta {
  const key =
    PRIMITIVE_BY_NODE[nodeType] ??
    (category ? PRIMITIVE_BY_CATEGORY[category] : undefined) ??
    "io"
  return PRIMITIVE_TYPES[key]
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
  /** Tipo de primitivo (agente/check/externo/...) — eixo ortogonal a jornada,
   *  sinalizado por cor (barra) + chip muted na UI. */
  primitiveType: PrimitiveTypeKey
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

// Catalogo de RECEITAS do node `official_document_fetch` — o usuario escolhe
// o DOCUMENTO (nao os datasets crus); cada receita e uma cadeia curada de
// 1..N consultas do catalogo de dados executada pelo backend (decisao de
// produto 2026-06-11). Espelha `RECIPES` em
// backend/app/agentic/playbooks/nodes/official_document_fetch.py.
export const OFFICIAL_DOCUMENT_PALETTE: Array<{
  /** Chave estavel da receita (vai em `config.document`). */
  key: string
  label: string
  description: string
}> = [
  {
    key: "social_contract_jucesp",
    label: "Contrato Social · JUCESP",
    description:
      "Baixa o contrato/alteracao mais recente da Junta Comercial SP, anexa ao dossie e extrai com IA — sem clique do analista (~R$ 0,66 · 3 consultas).",
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


export function buildPaletteEntries(
  nodeTypes: NodeTypeMeta[],
  // Catalogo white-label de produtos de dado (GET /credito/data-products).
  // Expande `cadastral_enrichment` em um entry por dataset habilitado — o
  // vendor nunca aparece, so o public_code + label curado.
  dataProducts: DataProduct[] = [],
): PaletteEntry[] {
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
          primitiveType: primitiveTypeFor("specialist_agent").key,
          featured: FEATURED_PALETTE_IDS.has(paletteId),
        })
      }
      continue
    }

    if (meta.type === "cadastral_enrichment") {
      // Data-driven (white-label): um entry por dataset do catalogo
      // (/credito/data-products). Cada um instancia o node ja com o
      // public_code certo — o gerente nunca digita codigo nem ve vendor.
      // Fallback: catalogo vazio/nao-carregado => entry generico (gerente
      // preenche public_code no Inspector), pra paleta nunca ficar sem o node.
      if (dataProducts.length === 0) {
        entries.push({
          paletteId: meta.type,
          nodeType: meta.type,
          initialConfig: { ...(TYPE_INITIAL_CONFIG[meta.type] ?? {}) },
          label: ETAPA_LABEL[meta.type] ?? meta.label,
          description: meta.description,
          icon: meta.icon,
          available: meta.available,
          journey: "enriquecer",
          primitiveType: primitiveTypeFor(meta.type, meta.category).key,
          featured: FEATURED_PALETTE_IDS.has(meta.type),
        })
        continue
      }
      for (const dp of dataProducts) {
        const paletteId = `cadastral_enrichment:${dp.public_code}`
        entries.push({
          paletteId,
          nodeType: "cadastral_enrichment",
          initialConfig: { public_code: dp.public_code },
          label: dp.display_name,
          description: dp.description ?? meta.description,
          icon: meta.icon,
          available: meta.available,
          journey: "enriquecer",
          primitiveType: primitiveTypeFor("cadastral_enrichment").key,
          featured: FEATURED_PALETTE_IDS.has(paletteId),
        })
      }
      continue
    }

    if (meta.type === "official_document_fetch") {
      // Expandir um entry por RECEITA de documento oficial — o gerente
      // arrasta "Contrato Social · JUCESP" direto, ja configurado.
      for (const r of OFFICIAL_DOCUMENT_PALETTE) {
        const paletteId = `official_document_fetch:${r.key}`
        entries.push({
          paletteId,
          nodeType: "official_document_fetch",
          initialConfig: { document: r.key },
          label: r.label,
          description: r.description,
          icon: meta.icon,
          available: meta.available,
          journey: "enriquecer",
          primitiveType: primitiveTypeFor("official_document_fetch").key,
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
          primitiveType: primitiveTypeFor("bureau_query").key,
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
      primitiveType: primitiveTypeFor(meta.type, meta.category).key,
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
