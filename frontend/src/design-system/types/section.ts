// src/design-system/types/section.ts
//
// CONTRATO UNIVERSAL da esteira de crédito (Fase 1 — fundação).
// Ver docs/esteira-credito-interface-camadas.md.
//
// Princípio (A1): todo node — agente OU NÃO — expõe um `SectionDescriptor`
// (lista de blocos). UM renderizador consome isso e NÃO sabe se veio de um
// agente, de uma consulta, de um check ou de um documento. A consistência mora
// na CAMADA C (vocabulário de blocos, fechado): só existem estes tipos, cada um
// renderiza de um jeito só, em todo lugar. A derivação (como cada node monta
// seus blocos) é heterogênea e invisível.
//
// Esta camada é só TIPOS — sem runtime, sem componente. O `<SectionRenderer>` e
// os componentes de bloco entram na Etapa 2.

import type { ProvenanceRef } from "@/design-system/tokens/provenance"

// ════════════════════════════════════════════════════════════════════════════
// CAMADA C — Vocabulário de blocos (FECHADO: 6 display + 2 interativos + 1 recursivo)
// ════════════════════════════════════════════════════════════════════════════

/** Discriminante de bloco. Conjunto fechado — não inventar um nono. */
export type BlockType =
  // display
  | "ficha"
  | "tabela"
  | "grafico"
  | "serie_temporal"
  | "conclusao_agente"
  | "apontamentos"
  | "texto"
  // interativos
  | "conferencia"
  | "fonte_origem"
  // recursivo (Fase 2 — declarado e ocioso na Fase 1; abre a porta do sonho)
  | "sub_dossie"

type BlockBase = {
  /** Id estável do bloco dentro da seção (pra key de render e âncora de trilha). */
  id: string
  /** Proveniência do bloco como um todo. Campos/células podem ter a sua própria. */
  provenance?: ProvenanceRef
}

// ─── Display ──────────────────────────────────────────────────────────────

/** Um campo da Ficha (label + valor + proveniência opcional por campo). */
export type FichaCampo = {
  label: string
  valor: string
  /** Linha secundária (muted) — ex.: a leitura do agente sob um valor. */
  nota?: string
  /** Marcador curto inline (ex.: "leitura fraca", situação cadastral). */
  badge?: { texto: string; tom: "ok" | "atencao" | "critico" | "neutro" }
  provenance?: ProvenanceRef
}

/** Ficha de campos — key/value. Consulta cadastral, dados básicos, etc. */
export type FichaBlock = BlockBase & {
  type: "ficha"
  titulo?: string
  campos: FichaCampo[]
}

export type TabelaColuna = {
  key: string
  label: string
  align?: "left" | "right" | "center"
  /** Formato do valor (deixa o renderer escolher; não formata aqui). */
  formato?: "texto" | "numero" | "brl" | "pct" | "data"
}

export type TabelaCelula = {
  /** Valor cru; o renderer formata segundo `coluna.formato`. */
  valor: string | number | null
  provenance?: ProvenanceRef
}

/** Tabela — séries, breakdowns, listas estruturadas. */
export type TabelaBlock = BlockBase & {
  type: "tabela"
  titulo?: string
  colunas: TabelaColuna[]
  linhas: Record<string, TabelaCelula>[]
  /** Rodapé de reconciliação (§14.6): soma que bate o headline. */
  rodape?: Record<string, TabelaCelula>
}

/** Série de um gráfico (alinha com a anatomia do KpiChartCard). */
export type GraficoSerie = {
  nome: string
  pontos: { x: string; y: number }[]
}

/** Gráfico (KpiChartCard) — KPI headline + barras/linha. */
export type GraficoBlock = BlockBase & {
  type: "grafico"
  titulo?: string
  /** Headline KPI opcional (L1 eyebrow / L2 valor / L3 contexto). */
  kpi?: { eyebrow?: string; valor: string; delta?: string; contexto?: string }
  series: GraficoSerie[]
}

/** Um ponto da série periódica (mês/competência + valor). */
export type SerieTemporalPonto = { periodo: string; valor: number }

/**
 * Série temporal/periódica — conceito recorrente de FIDC (faturamento mensal,
 * PL mês a mês, rentabilidade…). Renderiza KPI headline + gráfico de barras +
 * tabela compacta dos períodos. É a forma CANÔNICA de exibir uma série; o que
 * varia é só o `formato` dos valores. (A conferência editável da série é
 * interativa e vive na camada de trabalho, não como bloco.)
 */
export type SerieTemporalBlock = BlockBase & {
  type: "serie_temporal"
  titulo?: string
  kpi?: { eyebrow?: string; valor: string; delta?: string; contexto?: string }
  pontos: SerieTemporalPonto[]
  /** Formato dos valores na tabela (default "brl"). */
  formato?: "brl" | "numero" | "pct"
}

/** Conclusão de agente — o julgamento (resumo + recomendação + estado de homologação). */
export type ConclusaoAgenteBlock = BlockBase & {
  type: "conclusao_agente"
  /** Nome do agente (revenue_analyst, cadastral_analyst, opinion_writer, …). */
  agente: string
  resumo: string
  /** Quando o agente recomenda (opinion_writer). */
  recomendacao?: { veredito: "aprovar" | "negar" | "condicional"; condicoes?: string[] }
  /** Conclusão homologada vira contínua (assinatura E3); pendente fica pontilhada. */
  homologado: boolean
}

/** Um apontamento (red flag / ponto de atenção). */
export type Apontamento = {
  severidade: "critico" | "atencao" | "info"
  titulo: string
  descricao?: string
  /** Evidência citável (provém o flag). */
  evidencia?: string
  provenance?: ProvenanceRef
}

/** Lista de apontamentos — red flags, pontos de atenção, achados. */
export type ApontamentosBlock = BlockBase & {
  type: "apontamentos"
  titulo?: string
  itens: Apontamento[]
}

/** Texto livre — narrativa em markdown (render via react-markdown + remark-gfm). */
export type TextoBlock = BlockBase & {
  type: "texto"
  titulo?: string
  markdown: string
}

// ─── Interativos ────────────────────────────────────────────────────────────

/** Uma linha da conferência (IA propôs × no dossiê). */
export type ConferenciaLinha = {
  campo: string
  valorIa: string
  valorDossie: string
  /** ok = bate · ajustado = analista corrigiu (diff + pena) · pendente = falta conferir. */
  estado: "ok" | "ajustado" | "pendente"
  /** Citação pro trecho de origem do valor proposto. */
  locator?: ProvenanceRef["locator"]
}

/** Conferência editável — IA propôs × no dossiê, com edição inline + autosave. */
export type ConferenciaBlock = BlockBase & {
  type: "conferencia"
  titulo?: string
  linhas: ConferenciaLinha[]
}

/** Fonte+Origem — visualizador do documento (PDF/iframe) focado num localizador. */
export type FonteOrigemBlock = BlockBase & {
  type: "fonte_origem"
  docId: string
  /** Abre já posicionado no trecho citado, quando houver. */
  locator?: ProvenanceRef["locator"]
}

// ─── Recursivo (Fase 2 — sonho; declarado e ocioso na Fase 1) ─────────────────

/**
 * Sub-dossiê — uma `SectionDescriptor` aninhada. Torna o dossiê FRACTAL: um CNPJ
 * do grupo descoberto vira uma seção que, ao expandir, é um mini-dossiê com a
 * mesma anatomia. NINGUÉM emite isto na Fase 1 — existe só pra travar o contrato
 * e não virar muro depois. Ver §4 do doc.
 */
export type SubDossieBlock = BlockBase & {
  type: "sub_dossie"
  titulo: string
  descriptor: SectionDescriptor
}

/** O vocabulário fechado. */
export type Block =
  | FichaBlock
  | TabelaBlock
  | GraficoBlock
  | SerieTemporalBlock
  | ConclusaoAgenteBlock
  | ApontamentosBlock
  | TextoBlock
  | ConferenciaBlock
  | FonteOrigemBlock
  | SubDossieBlock

// ════════════════════════════════════════════════════════════════════════════
// CAMADA B — SectionDescriptor (o que cada node expõe)
// ════════════════════════════════════════════════════════════════════════════

export type SectionDescriptor = {
  id: string
  /** Estação a que esta seção pertence (declarado no grafo — Etapa 4). */
  stationId: string
  titulo: string
  blocks: Block[]
  provenance?: ProvenanceRef
  /**
   * § gera seção: entra na projeção compilada (dossiê)? `false` = só aparece no
   * workbench / na trilha, não vira seção do documento final.
   */
  generatesDossierSection: boolean
}

// ════════════════════════════════════════════════════════════════════════════
// Estação + modelo de prontidão (bússola, não cadeado — §1.1)
// ════════════════════════════════════════════════════════════════════════════

/**
 * Estado visual da estação. Vocabulário canônico (movido do StationsSidebar pra
 * cá — types/ é o dono do contrato; o componente re-exporta). `bloqueada` já
 * codifica "deps não satisfeitas"; os demais = pronta/ativa.
 */
export type StationState =
  | "fechada"
  | "fechada_com_ressalva"
  | "sua_vez"
  | "homologar"
  | "rodando"
  | "aguardando_documento"
  | "em_espera"
  | "bloqueada"
  | "falhou"

/** Estados em que a estação JÁ fechou (não conta como pendência). */
export const CLOSED_STATION_STATES: ReadonlySet<StationState> = new Set<StationState>([
  "fechada",
  "fechada_com_ressalva",
])

export type StationDescriptor = {
  id: string
  label: string
  sublabel?: string
  state: StationState
  /**
   * Prontidão POR DEPENDÊNCIA, não sequência (§1.1): ids das estações que
   * precisam fechar antes desta poder abrir. Vazio = sem pré-requisito.
   */
  dependsOn: string[]
  /** Preenchido quando `state="bloqueada"`: "esperando Cadastral". */
  blockedReason?: string
  /** A bússola: estação sugerida como próxima. NÃO é cadeado — as prontas são todas navegáveis. */
  isRecommendedNext?: boolean
  /** Ids dos nodes fundidos nesta estação (âncora + fundidos). */
  memberNodeIds?: string[]
  sections: SectionDescriptor[]
}

/** O dossiê inteiro projetado do run do playbook. */
export type DossierDescriptor = {
  /** Código humano (DC-AAAA-NNNN). */
  code: string
  stations: StationDescriptor[]
}

/** Modo do renderizador único: workbench (editável) vs dossiê (leitura). */
export type RenderMode = "work" | "read"

// ─── Helpers de prontidão (a bússola, pura/testável) ─────────────────────────

/** Uma estação está pronta quando não fechou e todas as deps já fecharam. */
export function isStationReady(
  station: StationDescriptor,
  byId: ReadonlyMap<string, StationDescriptor>,
): boolean {
  if (CLOSED_STATION_STATES.has(station.state)) return false
  return station.dependsOn.every((depId) => {
    const dep = byId.get(depId)
    return dep != null && CLOSED_STATION_STATES.has(dep.state)
  })
}

/**
 * A bússola: sugere a próxima estação sem prender o analista. Default = a
 * primeira (na ordem dada) que esteja PRONTA; se nenhuma, a última fechada;
 * senão a primeira. Substitui o `pickFocusEstacao` cadeado (§1.1).
 */
export function pickRecommendedNext(
  stations: StationDescriptor[],
): StationDescriptor | null {
  const byId = new Map(stations.map((s) => [s.id, s]))
  const ready = stations.find((s) => isStationReady(s, byId))
  if (ready) return ready
  const lastClosed = [...stations]
    .reverse()
    .find((s) => CLOSED_STATION_STATES.has(s.state))
  return lastClosed ?? stations[0] ?? null
}
