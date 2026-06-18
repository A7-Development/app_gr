// src/app/(foco)/credito/dossies/[id]/page.tsx
//
// MODO FOCO da análise de crédito (handoff Conceito D, 2026-06-10).
// Substitui o Wizard V2 (WizardMultiStep) pelo chassi de ESTAÇÕES:
//
//   rail 56px (layout do route group) · sidebar de etapas 292px ·
//   workbench da estação ativa (header + sub-passos + zonas em cards
//   sobre gray-50 + barra de fechamento)
//
// Estações são derivadas CLIENT-SIDE do grafo + node_runs (projeção):
//   - nodes "só trilha" (trigger, notification, output, http) não viram estação
//   - document_extractor funde na estação do document_request
//   - human_review com config.review_of funde como GATE na estação do agente
//   - human_review final funde na estação do opinion_writer ("Parecer")
// Quando o backend ganhar a flag "§ gera seção" no graph (workstream F1+),
// esta projeção passa a ler a declaração do node.
//
// URL: `?step=<nodeId>` continua sendo a fonte da verdade (aceita o id de
// qualquer membro — resolve para a estação dona).

"use client"

import * as React from "react"
import { useParams, useRouter, useSearchParams } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  RiArchiveDrawerLine,
  RiArrowRightLine,
  RiCheckLine,
  RiErrorWarningLine,
  RiFileUploadLine,
  RiLoopLeftLine,
  RiRestartLine,
  RiSparkling2Line,
  RiUserFollowLine,
} from "@remixicon/react"
import { toast } from "sonner"

import { Button } from "@/components/tremor/Button"
import { Textarea } from "@/components/tremor/Textarea"
import { DynamicForm } from "@/design-system/components/DynamicForm"
import { type WizardMultiStepStep } from "@/design-system/patterns/WizardMultiStep"
import { DescriptorParityPanel } from "./_components/DescriptorParityPanel"
import { DocumentSourceZone, FichaConferenceZone } from "./_components/DocumentZones"
import {
  JucespDocSelector,
  type JucespDocOption,
} from "./_components/JucespDocSelector"
import {
  buildCoverage,
  DossierCoverageStrip,
} from "./_components/DossierCoverageStrip"
import { DossierReadingView } from "./_components/DossierReadingView"
import {
  FaturamentoStation,
  type FaturamentoPhase,
} from "./_components/FaturamentoStation"
import { RevenueAnalysisView } from "./_components/RevenueAnalysisView"
import { SocialContractAnalysisView } from "./_components/SocialContractAnalysisView"
import { SocialContractConferenceView } from "./_components/SocialContractConferenceView"
import { TrailSheet, type TrailEvent } from "./_components/TrailSheet"
import { CadastralAnalysisView } from "./_components/CadastralAnalysisView"
import { CadastralCard } from "./_components/CadastralCard"
import {
  AgentesAoVivoPanel,
  AgentLiveStatus,
  AgentOutputRenderer,
  ClosureBar,
  DeterministicCheckView,
  OpinionView,
  StationHeader,
  StationStateChip,
  StationsSidebar,
  type ClosureBarState,
  type GlassAlsoRunning,
  type GlassStep,
  type IndebtednessAnalysis,
  type OpinionDraft,
  type StationItem,
  type StationState,
  type StationSubstep,
} from "@/design-system/components"
import { provenanceTokens, type ProvenanceOrigin } from "@/design-system/tokens/provenance"
import {
  credito,
  type CadastralAnalysis,
  type EdgeSpec,
  type FormField,
  type CreditDocumentRead,
  type NodeRunSummary,
  type NodeSpec,
  type OpinionInput,
  type RedFlagItem,
  type RevenueAnalysis,
  type SocialContractAnalysis,
} from "@/lib/credito-client"
import { useDossierState, useStepDraft } from "@/lib/hooks/credito"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

// ─── Estação (projeção client-side) ────────────────────────────────────────

type Estacao = {
  /** Id do node âncora (alvo do ?step= e do submit principal). */
  id: string
  label: string
  members: WizardMultiStepStep[]
  /** Gate humano da estação (human_review), quando existe. */
  gate: WizardMultiStepStep | null
  state: StationState
}

/** Nodes que não viram estação — são bastidor ("só trilha"). */
const TRILHA_TYPES = new Set([
  "trigger",
  "notification",
  "output_generator",
  "http_request",
  "conditional_branch",
])

const RERUNNABLE = new Set([
  "deterministic_check",
  "specialist_agent",
  "document_extractor",
  "bureau_query",
  "cadastral_enrichment",
  "http_request",
])

function agentOf(step: WizardMultiStepStep): string | null {
  return (
    (step.input as { agent?: string } | undefined)?.agent ??
    (step.config as { agent?: string } | undefined)?.agent ??
    null
  )
}

// Afinidade agente → fonte de dados da seção. Funde o specialist_agent na
// estação que contém a fonte (D1: documento + conferência + leitura = UMA
// estação). Interim client-side até o backend declarar "§ gera seção" no graph.
const AGENT_STATION_AFFINITY: Record<string, string> = {
  revenue_analyst: "document_request",
  cadastral_analyst: "cadastral_enrichment",
  social_contract_analyst: "document_request",
}

const AGENT_STATION_LABEL: Record<string, string> = {
  revenue_analyst: "Faturamento",
  cadastral_analyst: "Cadastral",
  social_contract_analyst: "Contrato social",
}

// O aspecto (e o rótulo) de uma estação vêm do DOCUMENTO que ela coleta, não do
// nome do agente — a conferência + o gráfico são do documento. Um analista que
// segue o documento herda o aspecto dele, qualquer que seja o agente fiado
// (revenue_analyst, financial_analyst, …). Decoupling da Fatia 2(a).
const DOC_TYPE_STATION_LABEL: Record<string, string> = {
  revenue_report: "Faturamento",
  social_contract: "Contrato social",
}

function reviewOf(step: WizardMultiStepStep): string | null {
  return (step.config as { review_of?: string } | undefined)?.review_of ?? null
}

// Tipos de documento exigidos por um nó document_request (config no grafo, ou
// output em runtime). Sinal do ASPECTO da estação — robusto ao nome do agente.
function requiredDocTypes(step: WizardMultiStepStep): string[] {
  const cfg = (step.config as { required?: string[] } | undefined)?.required
  const out = (step.output as { required?: string[] } | undefined)?.required
  return cfg ?? out ?? []
}

// Receita de busca oficial → tipo de documento que ela produz. Sinal do ASPECTO
// (Fatia 2c): uma busca oficial e o pedido manual do MESMO documento são duas
// formas de obter a mesma fonte → uma estação só. Espelha RECIPES do backend.
const OFFICIAL_FETCH_DOC_TYPE: Record<string, string> = {
  social_contract_jucesp: "social_contract",
}

// Caixa de vidro: tipo do nó → assinatura de proveniência do passo (chip).
const GLASS_SOURCE_BY_NODE: Record<string, ProvenanceOrigin> = {
  document_request: "documento",
  document_extractor: "documento",
  official_document_fetch: "documento",
  bureau_query: "fonte",
  cadastral_enrichment: "fonte",
  specialist_agent: "agente",
}

function officialFetchDocType(step: WizardMultiStepStep): string | null {
  const recipe = (step.config as { document?: string } | undefined)?.document
  const fromOutput = (step.output as { doc_type?: string } | undefined)?.doc_type
  return (recipe ? OFFICIAL_FETCH_DOC_TYPE[recipe] : undefined) ?? fromOutput ?? null
}

function buildEstacoes(steps: WizardMultiStepStep[]): Estacao[] {
  const estacoes: Estacao[] = []

  const anchorFor = (step: WizardMultiStepStep): Estacao | null => {
    // Cruzamentos determinísticos pertencem à seção que acabou de coletar o
    // dado — fundem na estação anterior (não viram estação própria).
    if (step.nodeType === "deterministic_check") {
      return estacoes[estacoes.length - 1] ?? null
    }
    // Pedido manual que é FALLBACK de uma busca oficial do MESMO documento
    // (official_document_fetch) funde na estação dela — uma estação por aspecto
    // (busca automática + fallback manual + análise = "Contrato social"). Mata a
    // duplicação estação-fonte × estação-pedido (Fatia 2c). Só a última estação.
    if (step.nodeType === "document_request") {
      const reqTypes = requiredDocTypes(step)
      const last = estacoes[estacoes.length - 1]
      if (last) {
        const fetchTypes = last.members
          .filter((m) => m.nodeType === "official_document_fetch")
          .map((m) => officialFetchDocType(m))
          .filter((t): t is string => Boolean(t))
        if (fetchTypes.some((t) => reqTypes.includes(t))) return last
      }
      return null
    }
    // document_extractor funde na estação do document_request anterior.
    if (step.nodeType === "document_extractor") {
      for (let i = estacoes.length - 1; i >= 0; i--) {
        if (estacoes[i].members.some((m) => m.nodeType === "document_request")) {
          return estacoes[i]
        }
      }
      return null
    }
    if (step.nodeType === "specialist_agent") {
      const agent = agentOf(step)
      // opinion_writer é o sintetizador → estação "Parecer" própria, nunca funde
      // numa fonte.
      if (agent === "opinion_writer") return null
      const affinity = agent ? AGENT_STATION_AFFINITY[agent] : undefined
      if (affinity) {
        for (let i = estacoes.length - 1; i >= 0; i--) {
          if (estacoes[i].members.some((m) => m.nodeType === affinity)) {
            return estacoes[i]
          }
        }
      }
      // Fallback decoupled (Fatia 2a): um analista que CONTINUA um pipeline de
      // documento funde na estação dele, independente do nome do agente. Só a
      // última estação e só se ela coleta documento e ainda não tem analista —
      // evita capturar analista de bureau (que segue bureau_query, não doc).
      const last = estacoes[estacoes.length - 1]
      if (
        last &&
        last.members.some((m) => m.nodeType === "document_request") &&
        !last.members.some((m) => m.nodeType === "specialist_agent")
      ) {
        return last
      }
      return null
    }
    if (step.nodeType === "human_review") {
      const target = reviewOf(step)
      if (target) {
        // Gate de UMA análise → estação do agente revisado.
        for (const e of estacoes) {
          if (e.members.some((m) => agentOf(m) === target || m.id === target)) return e
        }
        return null
      }
      // Checkpoint final → estação do opinion_writer ("Parecer").
      for (const e of estacoes) {
        if (e.members.some((m) => agentOf(m) === "opinion_writer")) return e
      }
      return null
    }
    return null
  }

  for (const step of steps) {
    if (TRILHA_TYPES.has(step.nodeType ?? "")) continue

    const host = anchorFor(step)
    if (host) {
      host.members.push(step)
      if (step.nodeType === "human_review") host.gate = step
      // Agente fundido batiza a estação ("Faturamento", "Cadastral").
      const agent = agentOf(step)
      if (step.nodeType === "specialist_agent" && agent && AGENT_STATION_LABEL[agent]) {
        host.label = AGENT_STATION_LABEL[agent]
      }
      continue
    }

    estacoes.push({
      id: step.id,
      label:
        agentOf(step) === "opinion_writer" || step.nodeType === "human_review"
          ? "Parecer"
          : step.label,
      members: [step],
      gate: step.nodeType === "human_review" ? step : null,
      state: "bloqueada",
    })
  }

  // Rótulo da estação pelo ASPECTO do documento que ela coleta (decoupled do
  // nome do agente). Override do label-por-agente quando o document_request
  // declara um tipo conhecido — fonte única do "Faturamento"/"Contrato social".
  for (const e of estacoes) {
    const docReq = e.members.find((m) => m.nodeType === "document_request")
    if (!docReq) continue
    const aspect = requiredDocTypes(docReq)
      .map((t) => DOC_TYPE_STATION_LABEL[t])
      .find(Boolean)
    if (aspect) e.label = aspect
  }

  for (const e of estacoes) e.state = estacaoState(e)
  return estacoes
}

function estacaoState(e: Estacao): StationState {
  const members = e.members
  if (members.some((m) => m.state === "failed")) return "falhou"
  const waiting = members.find((m) => m.state === "waiting_input")
  if (waiting) {
    if (waiting.nodeType === "human_review") return "homologar"
    if (waiting.nodeType === "document_request") return "aguardando_documento"
    return "sua_vez"
  }
  if (members.some((m) => m.state === "running")) return "rodando"
  if (members.every((m) => m.state === "completed" || m.state === "skipped")) return "fechada"
  // Parcialmente completa SEM membro ativo = em espera de etapas anteriores
  // (ex.: fontes ok, conclusão espera outra estação) — não é "rodando".
  return "bloqueada"
}

// BÚSSOLA, NÃO CADEADO (decisão 2026-06-13, §1.1 — substitui a "condução
// sequencial estrita" de 2026-06-12). Esta função devolve apenas a SUGESTÃO de
// próxima estação (a primeira em ordem que ainda não fechou); o analista
// continua livre pra navegar pra qualquer estação via `onSelect` (que seta
// ?step= sem gating). É a versão local de `pickRecommendedNext`
// (@/design-system/types/section) — quando o cockpit migrar pra
// StationDescriptor com `dependsOn` declarado no grafo (Etapa 4), adota-se o
// helper canônico (prontidão por dependência em vez de ordem linear).
function pickFocusEstacao(estacoes: Estacao[]): Estacao | null {
  return (
    estacoes.find(
      (e) => e.state !== "fechada" && e.state !== "fechada_com_ressalva",
    ) ??
    [...estacoes].reverse().find((e) => e.state === "fechada") ??
    estacoes[0] ??
    null
  )
}

const STATION_SUBLABEL: Record<StationState, string> = {
  fechada: "fechada",
  fechada_com_ressalva: "fechada com ressalva",
  sua_vez: "esperando por você",
  homologar: "conclusão pronta",
  rodando: "agente trabalhando…",
  aguardando_documento: "aguardando documento",
  em_espera: "em espera",
  bloqueada: "abre quando as anteriores fecharem",
  falhou: "precisa de atenção",
}

// Fases canônicas da estação (handoff): Documento → Conferência → Leitura →
// Homologação. Derivadas dos MEMBROS do nó (sem hardcode por estação); a estação
// PULA a fase que não tem. Estado de cada fase vem dos membros relevantes.
function buildFases(e: Estacao): StationSubstep[] | undefined {
  const closed = e.state === "fechada" || e.state === "fechada_com_ressalva"
  if (e.members.length <= 1 && !closed) return undefined

  const docM = e.members.find((m) =>
    ["document_request", "document_extractor", "official_document_fetch"].includes(
      m.nodeType,
    ),
  )
  const agentM = e.members.find((m) => m.nodeType === "specialist_agent")
  const gateM = e.members.find((m) => m.nodeType === "human_review")

  const st = (m: WizardMultiStepStep | undefined): StationSubstep["state"] => {
    if (!m) return "future"
    if (m.state === "completed" || m.state === "skipped") return "done"
    if (m.state === "running" || m.state === "waiting_input" || m.state === "failed")
      return "active"
    return "future"
  }

  const fases: StationSubstep[] = []
  if (docM) {
    fases.push({ kind: "documento", label: "Documento", state: st(docM) })
    // Conferência existe quando há documento; done quando o doc foi confirmado.
    fases.push({
      kind: "conferencia",
      label: "Conferência",
      state: st(docM) === "done" ? "done" : "future",
    })
  }
  if (agentM) fases.push({ kind: "leitura", label: "Leitura", state: st(agentM) })
  fases.push({
    kind: "homologacao",
    label: "Homologação",
    state: closed ? "done" : st(gateM),
  })

  // Estação aberta sem nenhuma fase ativa → a 1ª futura vira a presente.
  if (!closed && !fases.some((f) => f.state === "active")) {
    const next = fases.find((f) => f.state === "future")
    if (next) next.state = "active"
  }
  return fases
}

function formatBRLCompact(raw: string | null): string | null {
  if (!raw) return null
  const v = Number(raw)
  if (!Number.isFinite(v) || v === 0) return null
  const fmt = (n: number) =>
    n.toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 1 })
  if (Math.abs(v) >= 1_000_000_000) return `R$ ${fmt(v / 1_000_000_000)} bi`
  if (Math.abs(v) >= 1_000_000) return `R$ ${fmt(v / 1_000_000)} mi`
  if (Math.abs(v) >= 1_000) return `R$ ${fmt(v / 1_000)} mil`
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
}

// ─── Zona (card branco sobre gray-50) ───────────────────────────────────────

function Zone({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <section
      className={cx(
        "rounded border border-gray-200 bg-white p-5 shadow-xs dark:border-gray-800 dark:bg-gray-950",
        className,
      )}
    >
      {children}
    </section>
  )
}

/** Zona adormecida (D2): descreve o que fará quando acordar. */
function DormantZone({ label }: { label: string }) {
  return (
    <div
      className="flex items-center gap-2.5 rounded px-5 py-3.5 opacity-75"
      style={{ border: "1.5px dashed #E5E7EB" }}
    >
      <RiFileUploadLine className="size-4 shrink-0 text-gray-400" aria-hidden />
      <p className="text-[12.5px] text-gray-500 dark:text-gray-400">
        <strong className="font-semibold text-gray-700 dark:text-gray-300">{label}</strong>{" "}
        — acorda assim que as etapas anteriores fecharem.
      </p>
    </div>
  )
}

// ─── Page ───────────────────────────────────────────────────────────────────

export default function DossierFocusPage() {
  const params = useParams<{ id: string }>()
  const router = useRouter()
  const sp = useSearchParams()
  const dossierId = params.id

  const stepFromUrl = sp.get("step")
  const viewDossie = sp.get("view") === "dossie"
  // QA do wiring (Etapa 4): ?descriptor=1 mostra o painel de paridade
  // server (/descriptor) × client (buildEstacoes). Não altera o rendering.
  const descriptorDebug = sp.get("descriptor") === "1"
  const queryClient = useQueryClient()
  const [trailOpen, setTrailOpen] = React.useState(false)
  // Gate JUCESP (opção B): node cuja escolha o analista acabou de confirmar →
  // a fase de download está rodando (muda o texto do feedback ao vivo).
  const [downloadingNode, setDownloadingNode] = React.useState<string | null>(null)

  // Fase 1 / Etapa 1.4 (flag): com ?descriptor=1, o §miolo do dossiê (A4) vem do
  // /descriptor (server) via SectionRenderer read-mode. Sem flag, A4 hand-built.
  const descriptorQ = useQuery({
    queryKey: ["credito", "descriptor", dossierId],
    queryFn: () => credito.dossies.descriptor(dossierId),
    enabled: descriptorDebug,
  })

  const { data: state, isLoading } = useDossierState(dossierId)
  const { data: workflow } = useQuery({
    queryKey: ["credito", "workflow-def", state?.dossier?.workflow_definition_id],
    queryFn: () => credito.workflows.get(state!.dossier.workflow_definition_id),
    enabled: Boolean(state?.dossier?.workflow_definition_id),
  })

  const steps: WizardMultiStepStep[] = React.useMemo(() => {
    if (!state) return []
    if (workflow?.graph) {
      return buildSteps(workflow.graph, state.node_runs, state.pending_node)
    }
    return state.node_runs.map((nr) => stepFromNodeRun(nr, state.pending_node))
  }, [state, workflow])

  const estacoes = React.useMemo(() => buildEstacoes(steps), [steps])

  // Nodes cujo SUCESSOR direto é uma busca JUCESP (official_document_fetch):
  // ao submeter esses passos, o resume roda a consulta JUCESP — SÍNCRONA e
  // demorada (1-2 min). Mostramos feedback honesto em vez do "Salvar" mudo
  // girando (DC-2026-0044). [1b: tornar o resume assíncrono é o fix de raiz.]
  const jucespTriggerNodes = React.useMemo(() => {
    const set = new Set<string>()
    const g = workflow?.graph as
      | {
          nodes?: Array<{ id: string; type: string }>
          edges?: Array<{ source: string; target: string }>
        }
      | undefined
    if (!g?.nodes || !g?.edges) return set
    const typeById = new Map(g.nodes.map((n) => [n.id, n.type]))
    for (const e of g.edges) {
      if (typeById.get(e.target) === "official_document_fetch") set.add(e.source)
    }
    return set
  }, [workflow])

  const focused = React.useMemo(() => {
    if (stepFromUrl) {
      const direct = estacoes.find(
        (e) => e.id === stepFromUrl || e.members.some((m) => m.id === stepFromUrl),
      )
      if (direct) return direct
    }
    return pickFocusEstacao(estacoes)
  }, [estacoes, stepFromUrl])

  const onSelect = React.useCallback(
    (id: string) => {
      const next = new URLSearchParams(sp.toString())
      next.set("step", id)
      next.delete("view") // selecionar estação sai do modo dossiê
      router.replace(`?${next.toString()}`)
    },
    [router, sp],
  )

  const onOpenDossier = React.useCallback(() => {
    const next = new URLSearchParams(sp.toString())
    next.set("view", "dossie")
    router.replace(`?${next.toString()}`)
  }, [router, sp])

  // ── Mutations ───────────────────────────────────────────────────────────
  const submitMutation = useMutation({
    mutationFn: (vars: { nodeId: string; values: Record<string, unknown> }) =>
      credito.dossies.submitNodeInput(dossierId, vars.nodeId, vars.values),
    onSuccess: () => {
      toast.success("Etapa fechada. A análise prossegue.")
      queryClient.invalidateQueries({ queryKey: ["credito", "dossie-state", dossierId] })
    },
    onError: (e) => toast.error(`Erro ao salvar: ${(e as Error).message}`),
  })

  const finalizeMutation = useMutation({
    mutationFn: (vars: { nodeId: string; opinion: OpinionInput }) =>
      credito.dossies.finalize(dossierId, { node_id: vars.nodeId, opinion: vars.opinion }),
    onSuccess: () => {
      toast.success("Parecer gerado. Análise finalizada.")
      queryClient.invalidateQueries({ queryKey: ["credito", "dossie-state", dossierId] })
    },
    onError: (e) => toast.error(`Erro ao finalizar: ${(e as Error).message}`),
  })

  const rerunMutation = useMutation({
    mutationFn: (nodeId: string) => credito.dossies.rerunNode(dossierId, nodeId),
    onSuccess: () => {
      toast.success("Reprocessando a partir desta etapa…")
      queryClient.invalidateQueries({ queryKey: ["credito", "dossie-state", dossierId] })
    },
    onError: (e) => toast.error(`Erro ao reprocessar: ${(e as Error).message}`),
  })

  // ── Rascunho contínuo (salvar ≠ fechar) ─────────────────────────────────
  const waitingMember = focused?.members.find((m) => m.state === "waiting_input") ?? null
  const draft = useStepDraft(dossierId, waitingMember?.id ?? null)

  // ── Estação Faturamento (D1) — documentos no nível da página ────────────
  // Dirigido pelo DOCUMENTO (revenue_report), não pelo nome do agente: a
  // conferência + o gráfico são do documento. Vale para qualquer analista
  // fundido (revenue_analyst, financial_analyst, …). Decoupling da Fatia 2(a).
  const isFaturamento = Boolean(
    focused &&
      focused.members.some(
        (m) =>
          m.nodeType === "document_request" &&
          requiredDocTypes(m).includes("revenue_report"),
      ),
  )
  const docsQuery = useQuery({
    queryKey: ["credito", "documents", dossierId],
    queryFn: () => credito.documents.list(dossierId),
    // Polla enquanto o run está ativo: nodes como official_document_fetch
    // anexam documentos SERVER-SIDE no resume (sem mutation no front). Sem
    // isto, a lista de docs ficava stale e a conferência não aparecia — a
    // estação mostrava "Documento não localizado" mesmo com found=true
    // (DC-2026-0044). Espelha o polling do useDossierState.
    refetchInterval: () => {
      const status = state?.run?.status
      if (status && ["completed", "failed", "cancelled"].includes(status)) {
        return false
      }
      return 3000
    },
  })
  const docs = React.useMemo(() => docsQuery.data ?? [], [docsQuery.data])

  // "Enviar para análise": homologa as extrações pendentes (PATCH) e fecha o
  // document_request — a orquestração aciona o agente em seguida. Restrito
  // aos tipos da PRÓPRIA estação: homologar um doc de outra estação aqui
  // validaria extração que o analista ainda não conferiu.
  const sendToAnalysisMutation = useMutation({
    mutationFn: async (vars: { nodeId: string; docTypes: string[] }) => {
      const allowed = new Set(vars.docTypes.map((t) => t.toLowerCase()))
      for (const d of docs) {
        if (allowed.size > 0 && !allowed.has(d.doc_type.toLowerCase())) continue
        if (d.extraction_status === "success") {
          const fields =
            ((d.ai_extraction as Record<string, unknown> | null)?.extracted_fields as
              | Record<string, unknown>
              | undefined) ?? {}
          await credito.documents.updateExtraction(dossierId, d.id, {
            extracted_fields: fields,
          })
        }
      }
      return credito.dossies.submitNodeInput(dossierId, vars.nodeId, {})
    },
    onSuccess: () => {
      toast.success("Valores gravados no dossiê — análise acionada.")
      queryClient.invalidateQueries({ queryKey: ["credito", "documents", dossierId] })
      queryClient.invalidateQueries({ queryKey: ["credito", "dossie-state", dossierId] })
    },
    onError: (e) => toast.error(`Erro ao enviar: ${(e as Error).message}`),
  })

  // ── Parecer final (estado içado pra barra de fechamento) ────────────────
  const finalGate =
    focused?.gate && !reviewOf(focused.gate) && focused.gate.state === "waiting_input"
      ? focused.gate
      : null
  const [reviewSummary, setReviewSummary] = React.useState<string | null>(null)
  const [reviewReco, setReviewReco] =
    React.useState<OpinionInput["recommendation"]>("conditional")
  React.useEffect(() => {
    if (finalGate && reviewSummary === null && state) {
      setReviewSummary(buildDraftSummary(state.red_flags ?? []))
    }
  }, [finalGate, reviewSummary, state])

  // ── Estação Faturamento (D1): fase + prontidão dos documentos ───────────
  const fatuDocStep = isFaturamento
    ? (focused!.members.find((m) => m.nodeType === "document_request") ?? null)
    : null
  // Qualquer analista fundido na estação (decoupled do nome) — a leitura é
  // renderizada conforme o schema do agente (revenue rico, demais genérico).
  const fatuAgentStep = isFaturamento
    ? (focused!.members.find((m) => m.nodeType === "specialist_agent") ?? null)
    : null
  const fatuGateStep =
    isFaturamento &&
    focused?.gate &&
    reviewOf(focused.gate) === agentOf(fatuAgentStep ?? ({} as WizardMultiStepStep))
      ? focused.gate
      : null

  const fatuPhase: FaturamentoPhase | null = !isFaturamento
    ? null
    : focused!.state === "fechada" || focused!.state === "fechada_com_ressalva"
      ? "fechada"
      : fatuDocStep?.state === "waiting_input"
        ? "documento"
        : fatuAgentStep?.state === "running"
          ? "rodando"
          : fatuGateStep?.state === "waiting_input"
            ? "homologar"
            : "fila"

  const fatuRequired = React.useMemo(() => {
    const out = (fatuDocStep?.output ?? {}) as { required?: string[] }
    return Array.isArray(out.required) ? out.required : []
  }, [fatuDocStep])

  const fatuReadiness = React.useMemo(() => {
    // Só os docs DESTA estação contam pra prontidão (um contrato social com
    // erro de extração não trava o fechamento do faturamento).
    const stationDocs = fatuRequired.length
      ? docs.filter((d) =>
          fatuRequired.some((t) => t.toLowerCase() === d.doc_type.toLowerCase()),
        )
      : docs
    const uploaded = new Set(stationDocs.map((d) => d.doc_type.toLowerCase()))
    const missing = fatuRequired.filter((t) => !uploaded.has(t.toLowerCase()))
    const processing = stationDocs.some(
      (d) => d.extraction_status === "pending" || d.extraction_status === "processing",
    )
    const hasError = stationDocs.some((d) => d.extraction_status === "error")
    const processedOk = stationDocs.some(
      (d) => d.extraction_status === "success" || d.extraction_status === "validated",
    )
    const ready =
      stationDocs.length > 0 &&
      missing.length === 0 &&
      !processing &&
      !hasError &&
      processedOk
    const pendingText = missing.length
      ? `falta: enviar ${missing.join(", ")}`
      : hasError
        ? "falta: tratar a falha da extração"
        : processing
          ? "falta: aguardar a extração do documento"
          : !processedOk
            ? "falta: enviar e processar o documento"
            : undefined
    return { ready, pendingText, processedOk }
  }, [docs, fatuRequired])

  // ── Trilha de auditoria (projeção client-side dos eventos) ──────────────
  const trailEvents: TrailEvent[] = React.useMemo(() => {
    if (!state) return []
    const stationOf = (nodeId: string): Estacao | undefined =>
      estacoes.find((e) => e.members.some((m) => m.id === nodeId))
    const events: TrailEvent[] = []

    if (state.run?.started_at) {
      events.push({
        id: "run-start",
        origin: "analista",
        phrase: (
          <>
            <strong className="font-semibold text-gray-900 dark:text-gray-50">
              Analista
            </strong>{" "}
            abriu a análise
          </>
        ),
        meta: fmtTime(state.run.started_at),
        at: state.run.started_at,
      })
    }

    for (const nr of state.node_runs) {
      if (!nr.completed_at && !nr.started_at) continue
      const step = steps.find((s) => s.id === nr.node_id)
      const est = stationOf(nr.node_id)
      const secao = est ? `§${estacoes.indexOf(est) + 1} ${est.label}` : null
      const at = nr.completed_at ?? nr.started_at!
      const label = step?.label ?? nr.node_id
      const base = { at, stationId: est?.id, id: `nr-${nr.id}` }
      const metaParts = [secao, fmtTime(at)].filter(Boolean)

      if (nr.node_type === "bureau_query" || nr.node_type === "cadastral_enrichment") {
        if (nr.status !== "completed") continue
        if (nr.duration_ms != null) {
          metaParts.push(`resposta em ${(nr.duration_ms / 1000).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}s`)
        }
        events.push({
          ...base,
          origin: "fonte",
          phrase: <>{label} — consulta concluída</>,
          meta: metaParts.join(" · "),
        })
      } else if (nr.node_type === "specialist_agent") {
        if (nr.status === "failed") {
          events.push({
            ...base,
            origin: "agente",
            phrase: (
              <>
                <strong className="font-semibold text-gray-900 dark:text-gray-50">
                  Agente
                </strong>{" "}
                não concluiu — {label}
              </>
            ),
            meta: metaParts.join(" · "),
          })
          continue
        }
        if (nr.status !== "completed") continue
        const cost = Number(nr.cost_brl) || 0
        if (cost > 0) metaParts.push(`R$ ${cost.toLocaleString("pt-BR", { minimumFractionDigits: 2 })}`)
        events.push({
          ...base,
          origin: "agente",
          phrase: (
            <>
              <strong className="font-semibold text-gray-900 dark:text-gray-50">
                Agente
              </strong>{" "}
              concluiu a análise — {label}
            </>
          ),
          meta: metaParts.join(" · "),
        })
      } else if (nr.node_type === "human_review" && nr.status === "completed") {
        events.push({
          ...base,
          origin: "analista",
          phrase: (
            <>
              <strong className="font-semibold text-gray-900 dark:text-gray-50">
                Analista
              </strong>{" "}
              homologou — {label}
            </>
          ),
          meta: metaParts.join(" · "),
        })
      } else if (nr.node_type === "human_input" && nr.status === "completed") {
        events.push({
          ...base,
          origin: "analista",
          phrase: (
            <>
              <strong className="font-semibold text-gray-900 dark:text-gray-50">
                Analista
              </strong>{" "}
              preencheu — {label}
            </>
          ),
          meta: metaParts.join(" · "),
        })
      } else if (nr.node_type === "document_request" && nr.status === "completed") {
        events.push({
          ...base,
          origin: "documento",
          phrase: <>Documentos enviados para análise — {label}</>,
          meta: metaParts.join(" · "),
        })
      }
    }

    for (const d of docs) {
      events.push({
        id: `doc-${d.id}`,
        origin: "documento",
        phrase: <>Documento recebido — {d.original_filename}</>,
        meta: fmtTime(d.uploaded_at),
        at: d.uploaded_at,
      })
      if ((d.ai_extraction as Record<string, unknown> | null)?._analyst_edited === true) {
        events.push({
          id: `doc-adj-${d.id}`,
          origin: "analista",
          phrase: (
            <>
              <strong className="font-semibold text-gray-900 dark:text-gray-50">
                Analista
              </strong>{" "}
              ajustou valores extraídos — {d.original_filename}
            </>
          ),
          meta: `${fmtTime(d.uploaded_at)} · valor original da IA preservado`,
          at: d.uploaded_at,
        })
      }
    }

    return events
  }, [state, steps, estacoes, docs])

  // ── Dados do dossiê de leitura (D4) ──────────────────────────────────────
  const revenueOutput = extractAgentOutput<RevenueAnalysis>(steps, "revenue_analyst")
  const opinionOutput = extractAgentOutput<OpinionDraft>(steps, "opinion_writer")
  const hasCadastral = steps.some(
    (s) => s.nodeType === "cadastral_enrichment" && s.state === "completed",
  )
  const completedAgents = steps.filter(
    (s) => s.nodeType === "specialist_agent" && s.state === "completed",
  )
  const adjustments = docs
    .filter((d) => (d.ai_extraction as Record<string, unknown> | null)?._analyst_edited === true)
    .map((d) => `Valores de ${d.original_filename} ajustados pelo analista · original preservado`)

  // ── Loading ─────────────────────────────────────────────────────────────
  if (isLoading || !state) {
    return (
      <div className="flex h-screen flex-1 items-center justify-center bg-gray-50 dark:bg-gray-925">
        <p className={tableTokens.cellSecondary}>Carregando a análise…</p>
      </div>
    )
  }

  const { dossier } = state
  const titleLabel =
    dossier.target_name ??
    (dossier.target_cnpj ? `CNPJ ${dossier.target_cnpj}` : "Análise sem identidade")

  const amount = formatBRLCompact(dossier.requested_amount)
  const sidebarMeta = [
    dossier.code,
    dossier.target_cnpj ? `CNPJ ${dossier.target_cnpj}` : null,
    amount ? `${amount} pleiteado` : null,
  ]
    .filter(Boolean)
    .join(" · ")

  const fechadas = estacoes.filter(
    (e) => e.state === "fechada" || e.state === "fechada_com_ressalva",
  ).length
  const progressPct = estacoes.length
    ? Math.round((fechadas / estacoes.length) * 100)
    : 0

  const sidebarItems: StationItem[] = estacoes.map((e, i) => ({
    id: e.id,
    label: `${i + 1} · ${e.label}`,
    sublabel: STATION_SUBLABEL[e.state],
    state: e.state,
  }))

  const focusedIndex = focused ? estacoes.indexOf(focused) : -1

  // ── Caixa de vidro (Agentes ao vivo) — dados da estação ativa + globais ────
  const glassSteps: GlassStep[] = (focused?.members ?? [])
    .filter((m) => m.nodeType !== "human_input")
    .map((m) => ({
      id: m.id,
      status:
        m.state === "completed" || m.state === "skipped"
          ? "ok"
          : m.state === "running"
            ? "rodando"
            : m.state === "failed"
              ? "erro"
              : "atencao",
      label: m.label,
      source: GLASS_SOURCE_BY_NODE[m.nodeType],
    }))
  const glassActiveStatus = !focused
    ? ""
    : focused.state === "fechada" || focused.state === "fechada_com_ressalva"
      ? "concluído"
      : focused.state === "rodando"
        ? "em curso"
        : focused.state === "sua_vez" || focused.state === "homologar"
          ? "aguardando você"
          : focused.state === "aguardando_documento"
            ? "aguardando documento"
            : "em espera"
  const runningEstacoes = estacoes.filter((e) => e.state === "rodando")
  const glassAlsoRunning: GlassAlsoRunning[] = runningEstacoes
    .filter((e) => e.id !== focused?.id)
    .map((e) => {
      const agentM = e.members.find((m) => m.nodeType === "specialist_agent")
      const log = (
        agentM?.input as { tools_log?: Array<{ tool_name?: string }> } | undefined
      )?.tools_log
      const last = log?.[log.length - 1]
      return {
        id: e.id,
        label: e.label,
        hint: "2º plano",
        onOpen: () => onSelect(e.id),
        stream: last?.tool_name
          ? [{ origin: "agente" as const, text: last.tool_name, typing: true }]
          : undefined,
      }
    })

  // ── Header da estação ───────────────────────────────────────────────────
  const chip = focused ? stationChip(focused.state) : null

  const ranAlone = focused
    ? focused.members
        .filter(
          (m) =>
            (m.state === "completed" || m.state === "skipped") &&
            m.nodeType !== "human_review" &&
            m.nodeType !== "human_input",
        )
        .map((m) => m.label)
    : []
  const needsYou = focused ? needsYouLabel(focused) : null
  const subtitle =
    focused &&
    [
      ranAlone.length ? `Rodou sozinho: ${ranAlone.join(" → ")}.` : null,
      needsYou ? `Falta você: ${needsYou}.` : null,
      focused.state === "rodando" ? "Nada trava: esta tela atualiza sozinha." : null,
      focused.state === "bloqueada"
        ? "Esta estação abre quando as anteriores fecharem."
        : null,
    ]
      .filter(Boolean)
      .join(" ")

  // Trilho de fases — derivado dos blocos, igual em toda estação (handoff F1.2).
  const substeps: StationSubstep[] | undefined = focused
    ? buildFases(focused)
    : undefined

  // ── Barra de fechamento ─────────────────────────────────────────────────
  const fatuClosure: React.ComponentProps<typeof ClosureBar> | null =
    isFaturamento && fatuPhase && focused
      ? fatuPhase === "documento"
        ? fatuReadiness.ready
          ? {
              state: "armed",
              statusText:
                "Valores conferidos — enviar grava a seção no dossiê e aciona o agente de faturamento.",
              primaryLabel: "Enviar para análise",
              primaryIcon: RiArrowRightLine,
              onPrimary: () =>
                fatuDocStep &&
                sendToAnalysisMutation.mutate({
                  nodeId: fatuDocStep.id,
                  docTypes: fatuRequired,
                }),
              primaryLoading: sendToAnalysisMutation.isPending,
              statusIcon: RiArchiveDrawerLine,
            }
          : {
              state: "pending",
              statusText:
                "Rascunho automático ativo — nada se perde se você sair.",
              pendingText: fatuReadiness.pendingText,
              primaryLabel: "Enviar para análise",
              onPrimary: () => {},
            }
        : fatuPhase === "rodando" || fatuPhase === "fila"
          ? {
              state: "pending",
              statusText: "Agente trabalhando — esta tela atualiza sozinha.",
              pendingText: "falta: aguardar o agente concluir",
              primaryLabel: "Fechar estação",
              onPrimary: () => {},
            }
          : fatuPhase === "homologar"
            ? {
                state: "pending",
                statusText:
                  "Homologar a leitura fecha a estação e grava a seção §Faturamento no dossiê.",
                pendingText: "falta: decidir sobre a leitura da IA",
                primaryLabel: "Fechar estação",
                onPrimary: () => {},
              }
            : null // fechada → fluxo genérico abaixo
      : null

  const closure =
    fatuClosure ??
    (focused
      ? buildClosure({
        estacao: focused,
        estacoes,
        finalGate,
        reviewSummary,
        draftSavedAt: draft.lastSavedAt,
        submitting: submitMutation.isPending || sendToAnalysisMutation.isPending,
        finalizing: finalizeMutation.isPending,
        docs,
        onSubmitEmpty: (nodeId) => submitMutation.mutate({ nodeId, values: {} }),
        onSendToAnalysis: (nodeId, docTypes) =>
          sendToAnalysisMutation.mutate({ nodeId, docTypes }),
        onFinalize: () => {
          if (!finalGate || !reviewSummary?.trim()) return
          finalizeMutation.mutate({
            nodeId: finalGate.id,
            opinion: {
              executive_summary: reviewSummary,
              recommendation: reviewReco,
              concerns: (state.red_flags ?? []).map((f) => f.title),
            },
          })
        },
          onGoTo: (id) => onSelect(id),
          onBackToQueue: () => router.push("/credito/dossies"),
        })
      : null)

  // ── Renderers de zona ───────────────────────────────────────────────────
  const renderAnalysisView = (s: WizardMultiStepStep): React.ReactNode => {
    const agent = agentOf(s)
    if (agent === "revenue_analyst" && s.output) {
      return (
        <RevenueAnalysisView
          dossierId={dossierId}
          output={s.output as unknown as RevenueAnalysis}
        />
      )
    }
    if (agent === "cadastral_analyst" && s.output) {
      return (
        <CadastralAnalysisView
          dossierId={dossierId}
          output={s.output as unknown as CadastralAnalysis}
        />
      )
    }
    if (agent === "social_contract_analyst" && s.output) {
      return (
        <SocialContractAnalysisView
          dossierId={dossierId}
          output={s.output as unknown as SocialContractAnalysis}
        />
      )
    }
    return <AgentOutputRenderer agentName={agent} output={s.output} />
  }

  const renderCompletedBody = (m: WizardMultiStepStep): React.ReactNode => {
    if (m.nodeType === "deterministic_check") {
      const out = (m.output ?? {}) as {
        passed?: boolean
        result?: boolean
        summary?: string
        check?: string
        flag_ids?: string[]
      }
      const ids = new Set(out.flag_ids ?? [])
      const flags = (state.red_flags ?? [])
        .filter((f) => ids.has(f.id))
        .map((f) => ({
          id: f.id,
          severity: f.severity,
          title: f.title,
          description: f.description,
          evidence: f.evidence,
          provenance: f.provenance,
        }))
      return (
        <DeterministicCheckView
          passed={Boolean(out.passed ?? out.result)}
          summary={out.summary}
          checkLabel={out.check}
          flags={flags}
        />
      )
    }
    if (m.nodeType === "cadastral_enrichment") {
      return <CadastralCard dossierId={dossierId} />
    }
    const agent = agentOf(m)
    if (agent === "opinion_writer") {
      const opinion = m.output as unknown as OpinionDraft | null
      const indebtedness = extractAgentOutput<IndebtednessAnalysis>(
        steps,
        "indebtedness_analyst",
      )
      if (opinion && Object.keys(opinion).length > 0) {
        return <OpinionView output={opinion} indebtedness={indebtedness} />
      }
      return null
    }
    if (m.nodeType === "human_review" || m.nodeType === "human_input") {
      // Gates fechados não têm corpo próprio — o resultado vive na seção.
      return null
    }
    return renderAnalysisView(m)
  }

  const renderMemberZone = (m: WizardMultiStepStep): React.ReactNode => {
    // Extração coberta pelo card de documento (DocumentWorkspace).
    if (m.nodeType === "document_extractor") return null

    // Busca em fonte oficial (JUCESP): o node roda sozinho e fecha, mas a
    // CONFERÊNCIA da extração (citações, trechos, PDF) continua sendo da
    // estação — sem isto, fluxos sem "Pedir documentos" perdiam a ficha
    // rica (regressão apontada pelo Ricardo no DC-2026-0039).
    if (m.nodeType === "official_document_fetch") {
      if (m.state === "pending") return <DormantZone key={m.id} label={m.label} />

      // GATE DE SELEÇÃO (opção B): node pausado expondo a lista de documentos
      // arquivados — o analista escolhe qual usar (a máquina sugere).
      const fetchOut = m.output as
        | { phase?: string; options?: JucespDocOption[]; nire?: string }
        | null
      if (m.state === "waiting_input" && fetchOut?.phase === "select") {
        return (
          <JucespDocSelector
            key={m.id}
            dossierId={dossierId}
            nodeId={m.id}
            options={fetchOut.options ?? []}
            onChoose={() => setDownloadingNode(m.id)}
          />
        )
      }

      // FEEDBACK AO VIVO (frente B do DC-2026-0040): sem isto a tela fica muda
      // enquanto o motor trabalha. No gate (opção B) a mensagem muda por fase:
      // consultar a lista (segundos) vs baixar+ler o doc escolhido (~1 min).
      if (m.state === "running") {
        const selectMode =
          (m.config as { mode?: string } | undefined)?.mode === "select"
        const downloading = downloadingNode === m.id
        const title = !selectMode
          ? "Buscando o contrato social na fonte oficial…"
          : downloading
            ? "Baixando o documento escolhido e lendo com IA…"
            : "Consultando os arquivamentos na JUCESP…"
        const detail = !selectMode
          ? "JUCESP: login gov.br → ficha da empresa → documento mais recente → download → leitura com IA. Costuma levar ~2 minutos."
          : downloading
            ? "Download da cópia digitalizada na JUCESP + extração multimodal. Costuma levar ~1 minuto."
            : "JUCESP: ficha da empresa → lista de documentos societários arquivados. Uns segundos."
        return (
          <section
            key={m.id}
            className="flex items-start gap-3 rounded border border-blue-200 bg-blue-50/60 px-5 py-4 dark:border-blue-500/30 dark:bg-blue-500/10"
          >
            <span className="mt-1 size-2 shrink-0 rounded-full bg-blue-500 motion-safe:animate-pulse" />
            <div>
              <p className="text-sm font-medium text-blue-900 dark:text-blue-200">
                {title}
              </p>
              <p className="mt-0.5 text-xs text-blue-800/80 dark:text-blue-300/80">
                {detail}
              </p>
            </div>
          </section>
        )
      }
      const primaryDoc =
        docs.find(
          (d) =>
            d.doc_type.toLowerCase() === "social_contract" &&
            (d.extraction_status === "success" ||
              d.extraction_status === "validated"),
        ) ?? null
      if (!primaryDoc) {
        // DESFECHO VISÍVEL (frente A): found=false não pode ficar mudo — o
        // motivo (612 etc.) vinha só no texto do agente, estações depois.
        const out = (m.output ?? {}) as {
          found?: boolean
          message?: string
          transient?: boolean
        }
        // CONTRADIÇÃO a evitar: o node achou + anexou o doc (found=true,
        // aguardando homologação), mas a lista de docs ainda não trouxe a
        // extração (a query de docs atualiza no polling). NUNCA mostrar
        // "Documento não localizado / não é de SP" aqui — é mentira. Mostra
        // "preparando" até o primaryDoc chegar e a conferência renderizar.
        // DC-2026-0044.
        if (out.found) {
          return (
            <section
              key={m.id}
              className="flex items-start gap-3 rounded border border-blue-200 bg-blue-50/60 px-5 py-4 dark:border-blue-500/30 dark:bg-blue-500/10"
            >
              <span className="mt-1 size-2 shrink-0 rounded-full bg-blue-500 motion-safe:animate-pulse" />
              <div>
                <p className="text-sm font-medium text-blue-900 dark:text-blue-200">
                  Preparando a conferência da extração…
                </p>
                <p className="mt-0.5 text-xs text-blue-800/80 dark:text-blue-300/80">
                  Documento localizado e lido na JUCESP. Carregando a ficha para
                  homologação — alguns segundos.
                </p>
              </div>
            </section>
          )
        }
        // Indisponibilidade TRANSITÓRIA da JUCESP (609 etc.): não é "não existe"
        // nem "não é de SP" — é portal instável. Mensagem honesta + caminho de
        // retry (o "Buscar na JUCESP"/upload da estação manual logo abaixo).
        // DC-2026-0044.
        if (out.transient) {
          return (
            <section
              key={m.id}
              className="flex items-start gap-3 rounded border border-amber-200 bg-amber-50/70 px-5 py-4 dark:border-amber-500/30 dark:bg-amber-500/10"
            >
              <RiErrorWarningLine
                className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400"
                aria-hidden
              />
              <div>
                <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">
                  A consulta à JUCESP não completou agora
                </p>
                <p className="mt-0.5 text-xs leading-relaxed text-amber-800 dark:text-amber-300">
                  {out.message ||
                    "A JUCESP (portal gov.br) está instável ou lenta neste momento."}
                </p>
                <p className="mt-1.5 text-xs leading-relaxed text-amber-800/80 dark:text-amber-300/80">
                  Isso <strong>não</strong> quer dizer que a empresa não existe ou
                  não é de SP. Clique em <strong>&quot;Buscar na JUCESP&quot;</strong>{" "}
                  novamente em instantes, ou anexe o contrato social manualmente
                  abaixo.
                </p>
              </div>
            </section>
          )
        }
        return (
          <section
            key={m.id}
            className="flex items-start gap-3 rounded border border-amber-200 bg-amber-50/70 px-5 py-4 dark:border-amber-500/30 dark:bg-amber-500/10"
          >
            <RiErrorWarningLine
              className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-400"
              aria-hidden
            />
            <div>
              <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">
                Documento não localizado na fonte oficial
              </p>
              <p className="mt-0.5 text-xs leading-relaxed text-amber-800 dark:text-amber-300">
                {out.message ||
                  "A consulta à JUCESP não retornou resultados para esta empresa."}
              </p>
              <p className="mt-1.5 text-xs leading-relaxed text-amber-800/80 dark:text-amber-300/80">
                A JUCESP cobre empresas registradas em <strong>São Paulo</strong>.
                Se a empresa for de outro estado (ou o registro não estiver
                digitalizado), solicite o contrato social ao cliente — adicione a
                etapa &quot;Pedir documentos&quot; ao playbook para habilitar o
                upload manual nesta estação.
              </p>
            </div>
          </section>
        )
      }
      // Estação fundida (Fatia 2c): se um pedido manual irmão (document_request)
      // do mesmo documento está na estação, a CONFERÊNCIA renderiza por ele
      // (que tem upload/JUCESP + ficha). Aqui fica só a confirmação compacta de
      // que a busca automática trouxe o doc — sem duplicar a conferência.
      const fetchType = officialFetchDocType(m)
      // Só DELEGA a conferência ao irmão `document_request` quando ele está ATIVO
      // (rodou / aguarda upload). No fluxo de busca bem-sucedida (found==true), o
      // irmão fica `pending` (gated pela aresta found==false) e renderiza apenas um
      // DormantZone — delegar pra ele deixava o aviso "conferência logo abaixo"
      // apontando pra um placeholder vazio, sem a conferência nem o botão de
      // homologar (DC-2026-0044). Quando o irmão está pending, renderiza a
      // conferência AQUI mesmo.
      const siblingRequest =
        fetchType &&
        focused?.members.some(
          (s) =>
            s.nodeType === "document_request" &&
            s.state !== "pending" &&
            requiredDocTypes(s).includes(fetchType),
        )
      if (siblingRequest) {
        return (
          <section
            key={m.id}
            className="flex items-start gap-3 rounded border border-emerald-200 bg-emerald-50/60 px-5 py-3 dark:border-emerald-500/30 dark:bg-emerald-500/10"
          >
            <RiCheckLine
              className="mt-0.5 size-4 shrink-0 text-emerald-600 dark:text-emerald-400"
              aria-hidden
            />
            <p className="text-xs leading-relaxed text-emerald-900 dark:text-emerald-200">
              <strong className="font-semibold">Localizado na fonte oficial (JUCESP)</strong>{" "}
              — a conferência da extração está logo abaixo. Você pode substituir
              por um upload manual se preferir.
            </p>
          </section>
        )
      }
      return (
        <SocialContractConferenceView
          key={m.id}
          dossierId={dossierId}
          doc={primaryDoc}
          analysis={extractAgentOutput<SocialContractAnalysis>(
            steps,
            "social_contract_analyst",
          )}
        />
      )
    }

    // Busca em fonte oficial (JUCESP): o node roda sozinho e fecha, mas a
    // CONFERÊNCIA da extração (citações, trechos, PDF) continua sendo da
    // estação — sem isto, fluxos sem "Pedir documentos" perdiam a ficha
    // rica (regressão apontada pelo Ricardo no DC-2026-0039).
    if (m.nodeType === "official_document_fetch") {
      if (m.state === "pending") return <DormantZone key={m.id} label={m.label} />
      const primaryDoc =
        docs.find(
          (d) =>
            d.doc_type.toLowerCase() === "social_contract" &&
            (d.extraction_status === "success" ||
              d.extraction_status === "validated"),
        ) ?? null
      if (!primaryDoc) return null
      return (
        <SocialContractConferenceView
          key={m.id}
          dossierId={dossierId}
          doc={primaryDoc}
          analysis={extractAgentOutput<SocialContractAnalysis>(
            steps,
            "social_contract_analyst",
          )}
        />
      )
    }

    if (m.nodeType === "document_request") {
      const out = (m.output ?? {}) as { required?: string[]; optional?: string[] }
      if (m.state === "pending") return <DormantZone key={m.id} label={m.label} />
      const required = Array.isArray(out.required) ? out.required : []
      const optional = Array.isArray(out.optional) ? out.optional : []
      const stationTypes = [...required, ...optional].map((t) => t.toLowerCase())
      // Docs de OUTRAS estações não vazam pra cá (e vice-versa).
      const stationDocs = stationTypes.length
        ? docs.filter((d) => stationTypes.includes(d.doc_type.toLowerCase()))
        : docs
      const primaryDoc =
        stationDocs.find(
          (d) =>
            d.extraction_status === "success" || d.extraction_status === "validated",
        ) ?? null
      const stationOpen =
        focused?.state !== "fechada" && focused?.state !== "fechada_com_ressalva"
      // Zonas D1 compartilhadas (documento-fonte + conferência de ficha) —
      // mesmo padrão da estação Faturamento, sem o DocumentWorkspace legado.
      return (
        <React.Fragment key={m.id}>
          <DocumentSourceZone
            dossierId={dossierId}
            docs={stationDocs}
            requiredDocTypes={required}
            canUpload={m.state === "waiting_input"}
            juntaFetch={required.some(
              (t) => t.toLowerCase() === "social_contract",
            )}
            onChanged={() =>
              queryClient.invalidateQueries({
                queryKey: ["credito", "documents", dossierId],
              })
            }
          />
          {primaryDoc &&
            (primaryDoc.doc_type.toLowerCase() === "social_contract" ? (
              // Conferência GUIADA do contrato social (extração tipada tem
              // seções/tabelas/citações — a comparação plana fica pequena).
              <SocialContractConferenceView
                dossierId={dossierId}
                doc={primaryDoc}
                analysis={extractAgentOutput<SocialContractAnalysis>(
                  steps,
                  "social_contract_analyst",
                )}
              />
            ) : (
              <FichaConferenceZone
                dossierId={dossierId}
                doc={primaryDoc}
                editable={Boolean(stationOpen)}
              />
            ))}
        </React.Fragment>
      )
    }

    if (m.state === "pending" || m.state === "skipped") {
      return <DormantZone key={m.id} label={m.label} />
    }

    if (m.state === "running") {
      const inputData = (m.input ?? {}) as {
        agent?: string
        tools_log?: Array<{
          iso_at: string
          kind: "tool_use" | "tool_result"
          tool_name?: string
          duration_ms?: number
        }>
      }
      const nr = state.node_runs.find((x) => x.node_id === m.id)
      return (
        <Zone key={m.id}>
          <AgentLiveStatus
            agentLabel={inputData.agent}
            startedAt={state.run?.started_at ?? null}
            toolsLog={inputData.tools_log}
            tokensInput={nr?.tokens_input}
            tokensOutput={nr?.tokens_output}
            costBrl={Number(nr?.cost_brl ?? 0)}
          />
        </Zone>
      )
    }

    if (m.state === "failed") {
      return (
        <Zone key={m.id}>
          <FailedZone
            step={m}
            onRerun={() => rerunMutation.mutate(m.id)}
            rerunning={rerunMutation.isPending}
          />
        </Zone>
      )
    }

    if (m.state === "waiting_input") {
      if (m.nodeType === "human_review") {
        const target = reviewOf(m)
        if (target) {
          const agentStep = focused?.members.find((s) => agentOf(s) === target)
          const agentElsewhere = !agentStep
            ? steps.find((s) => s.state === "completed" && agentOf(s) === target)
            : undefined
          const rerunTarget = agentStep ?? agentElsewhere
          return (
            <Zone key={m.id}>
              <GateZone
                config={(m.config ?? {}) as { title?: string; description?: string }}
                externalAnalysis={
                  agentElsewhere ? renderAnalysisView(agentElsewhere) : null
                }
                approving={submitMutation.isPending}
                onApprove={(notes) =>
                  submitMutation.mutate({
                    nodeId: m.id,
                    values: { approved: true, notes },
                  })
                }
                onReprocess={
                  rerunTarget
                    ? () => {
                        if (window.confirm("Reprocessar a análise da IA?")) {
                          rerunMutation.mutate(rerunTarget.id)
                        }
                      }
                    : undefined
                }
                reprocessing={rerunMutation.isPending}
              />
            </Zone>
          )
        }
        // Checkpoint FINAL — parecer (a primária mora na barra de fechamento).
        return (
          <Zone key={m.id}>
            {/* Raio-X: o analista decide VENDO o que foi coberto. */}
            <div className="mb-4">
              <DossierCoverageStrip
                items={buildCoverage({
                  steps,
                  docs,
                  redFlags: state.red_flags ?? [],
                  opinion: opinionOutput,
                  hasCadastral,
                })}
              />
            </div>
            <CheckpointReview
              flags={state.red_flags ?? []}
              summary={reviewSummary ?? ""}
              onSummaryChange={setReviewSummary}
              recommendation={reviewReco}
              onRecommendationChange={setReviewReco}
            />
          </Zone>
        )
      }
      // Form padrão (human_input / coleta estruturada).
      const descriptor = (m.formDescriptor ?? {}) as {
        fields?: FormField[]
        submit_label?: string
      }
      const fields = descriptor.fields ?? []
      if (fields.length === 0) return null // primária vive na barra de fechamento
      const triggerData = (state.run?.trigger_data ?? {}) as Record<string, unknown>
      const initialValues: Record<string, unknown> = {}
      for (const f of fields) {
        if (triggerData[f.key] !== undefined) initialValues[f.key] = triggerData[f.key]
      }
      const consultingJucesp =
        submitMutation.isPending && jucespTriggerNodes.has(m.id)
      return (
        <Zone key={m.id}>
          {consultingJucesp && (
            <section className="mb-3 flex items-start gap-3 rounded border border-blue-200 bg-blue-50/60 px-5 py-4 dark:border-blue-500/30 dark:bg-blue-500/10">
              <span className="mt-1 size-2 shrink-0 rounded-full bg-blue-500 motion-safe:animate-pulse" />
              <div>
                <p className="text-sm font-medium text-blue-900 dark:text-blue-200">
                  Consultando a JUCESP…
                </p>
                <p className="mt-0.5 text-xs text-blue-800/80 dark:text-blue-300/80">
                  Login gov.br → ficha da empresa → documentos arquivados. Costuma
                  levar 1–2 minutos — pode deixar a tela aberta.
                </p>
              </div>
            </section>
          )}
          <DynamicForm
            fields={fields}
            initialValues={initialValues}
            onSubmit={async (values) => {
              await draft.flushNow()
              submitMutation.mutate({ nodeId: m.id, values })
            }}
            submitting={submitMutation.isPending}
            submitLabel={descriptor.submit_label ?? "Salvar e prosseguir"}
          />
        </Zone>
      )
    }

    // completed
    const body = renderCompletedBody(m)
    if (body === null) return null
    return (
      <Zone key={m.id}>
        {RERUNNABLE.has(m.nodeType ?? "") && (
          <div className="mb-3 flex justify-end">
            <Button
              variant="ghost"
              className="h-7 text-xs"
              onClick={() => {
                if (
                  window.confirm(
                    "Reprocessar esta etapa e as seguintes? As análises serão refeitas.",
                  )
                ) {
                  rerunMutation.mutate(m.id)
                }
              }}
              isLoading={rerunMutation.isPending}
            >
              <RiLoopLeftLine className="mr-1 size-3.5" aria-hidden />
              Reprocessar
            </Button>
          </div>
        )}
        {body}
      </Zone>
    )
  }

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <div className="flex min-w-0 flex-1">
      <StationsSidebar
        backHref="/credito/dossies"
        title={titleLabel}
        meta={sidebarMeta || undefined}
        progressPct={progressPct}
        progressLabel={`${fechadas} de ${estacoes.length}`}
        stations={sidebarItems}
        activeId={focused?.id ?? null}
        onSelect={onSelect}
        dossierLabel={`Ver dossiê · ${progressPct}% montado`}
        onOpenDossier={onOpenDossier}
        dossierActive={viewDossie}
        trailLabel={`Trilha: ${trailEvents.length} eventos`}
      />

      <TrailSheet
        open={trailOpen}
        onClose={() => setTrailOpen(false)}
        events={trailEvents}
        onGoToStation={onSelect}
      />

      {viewDossie ? (
        <DossierReadingView
          coverage={buildCoverage({
            steps,
            docs,
            redFlags: state.red_flags ?? [],
            opinion: opinionOutput,
            hasCadastral,
          })}
          dossier={dossier}
          docs={docs}
          redFlags={state.red_flags ?? []}
          revenueOutput={revenueOutput}
          opinionOutput={opinionOutput}
          hasCadastral={hasCadastral}
          agentSteps={completedAgents}
          adjustments={adjustments}
          progressPct={progressPct}
          trailCount={trailEvents.length}
          onOpenTrail={() => setTrailOpen(true)}
          onGoToStation={onSelect}
          descriptorStations={descriptorDebug ? descriptorQ.data?.stations : undefined}
        />
      ) : (
      <div className="flex h-screen min-w-0 flex-1 flex-col">
        {focused ? (
          <>
            <StationHeader
              title={`Estação ${focusedIndex + 1} · ${focused.label}`}
              chip={chip}
              subtitle={subtitle || undefined}
              substeps={substeps}
              onOpenTrail={() => setTrailOpen(true)}
            />
            {/* block + space-y (não flex): zona com overflow-hidden teria
                min-height 0 como flex item e seria esmagada pelo scroll. */}
            <div className="flex-1 space-y-5 overflow-y-auto bg-gray-50 px-8 pb-6 pt-6 dark:bg-gray-925">
              {descriptorDebug && (
                <DescriptorParityPanel
                  dossierId={dossierId}
                  clientStations={estacoes.map((e) => ({
                    id: e.id,
                    label: e.label,
                    state: e.state,
                  }))}
                />
              )}
              {isFaturamento && fatuPhase ? (
                <FaturamentoStation
                  dossierId={dossierId}
                  docs={docs}
                  requiredDocTypes={fatuRequired}
                  phase={fatuPhase}
                  agentOutput={
                    fatuAgentStep?.state === "completed" && fatuAgentStep.output
                      ? (fatuAgentStep.output as Record<string, unknown>)
                      : null
                  }
                  agentName={agentOf(fatuAgentStep ?? ({} as WizardMultiStepStep))}
                  agentLabel={
                    (fatuAgentStep?.input as { agent?: string } | undefined)?.agent
                  }
                  runStartedAt={state.run?.started_at ?? null}
                  toolsLog={
                    (
                      fatuAgentStep?.input as {
                        tools_log?: Array<{
                          iso_at: string
                          kind: "tool_use" | "tool_result"
                          tool_name?: string
                          duration_ms?: number
                        }>
                      } | undefined
                    )?.tools_log
                  }
                  tokensInput={
                    state.node_runs.find((x) => x.node_id === fatuAgentStep?.id)
                      ?.tokens_input
                  }
                  tokensOutput={
                    state.node_runs.find((x) => x.node_id === fatuAgentStep?.id)
                      ?.tokens_output
                  }
                  costBrl={Number(
                    state.node_runs.find((x) => x.node_id === fatuAgentStep?.id)
                      ?.cost_brl ?? 0,
                  )}
                  onApproveGate={(notes) =>
                    fatuGateStep &&
                    submitMutation.mutate({
                      nodeId: fatuGateStep.id,
                      values: { approved: true, notes },
                    })
                  }
                  approving={submitMutation.isPending}
                  onRerunAgent={
                    fatuAgentStep
                      ? () => rerunMutation.mutate(fatuAgentStep.id)
                      : undefined
                  }
                  rerunning={rerunMutation.isPending}
                />
              ) : (
                focused.members.map(renderMemberZone)
              )}
            </div>
            {closure && <ClosureBar {...closure} />}
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center bg-gray-50 dark:bg-gray-925">
            <p className={tableTokens.cellSecondary}>
              Este fluxo ainda não tem estações executadas.
            </p>
          </div>
        )}
      </div>
      )}

      {!viewDossie && focused && (
        <AgentesAoVivoPanel
          activeStationLabel={focused.label}
          activeStationStatus={glassActiveStatus}
          steps={glassSteps}
          alsoRunning={glassAlsoRunning}
          activeCount={runningEstacoes.length}
        />
      )}
    </div>
  )
}

function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })
  } catch {
    return iso
  }
}

// ─── Chip do header por estado ──────────────────────────────────────────────

function stationChip(state: StationState): React.ReactNode {
  switch (state) {
    case "sua_vez":
      return (
        <StationStateChip variant="blue" icon={RiUserFollowLine}>
          Sua vez
        </StationStateChip>
      )
    case "homologar":
      return (
        <StationStateChip variant="indigo" icon={RiSparkling2Line}>
          Aguardando homologação
        </StationStateChip>
      )
    case "rodando":
      return (
        <StationStateChip variant="indigo" icon={RiSparkling2Line}>
          Agente em execução
        </StationStateChip>
      )
    case "aguardando_documento":
      return (
        <StationStateChip variant="neutral" icon={RiFileUploadLine}>
          Aguardando documento
        </StationStateChip>
      )
    case "fechada":
    case "fechada_com_ressalva":
      return <StationStateChip variant="green">Fechada</StationStateChip>
    case "falhou":
      return (
        <StationStateChip variant="neutral" icon={RiErrorWarningLine}>
          Precisa de atenção
        </StationStateChip>
      )
    default:
      return <StationStateChip variant="neutral">Bloqueada</StationStateChip>
  }
}

function needsYouLabel(e: Estacao): string | null {
  const waiting = e.members.find((m) => m.state === "waiting_input")
  if (!waiting) return null
  if (waiting.nodeType === "human_review") {
    return reviewOf(waiting)
      ? "homologar a conclusão do agente"
      : "decidir e finalizar o parecer"
  }
  if (waiting.nodeType === "document_request") {
    return "enviar e conferir o documento, depois fechar"
  }
  return "preencher os dados e salvar"
}

/** Sub-passos canônicos da Estação Faturamento (D1). */
// ─── Barra de fechamento (estado calculado) ─────────────────────────────────

type ClosureConfig = {
  estacao: Estacao
  estacoes: Estacao[]
  finalGate: WizardMultiStepStep | null
  reviewSummary: string | null
  draftSavedAt: string | null
  submitting: boolean
  finalizing: boolean
  docs: CreditDocumentRead[]
  onSubmitEmpty: (nodeId: string) => void
  onSendToAnalysis: (nodeId: string, docTypes: string[]) => void
  onFinalize: () => void
  onGoTo: (id: string) => void
  onBackToQueue: () => void
}

function buildClosure(
  cfg: ClosureConfig,
): React.ComponentProps<typeof ClosureBar> | null {
  const { estacao, estacoes, finalGate } = cfg
  const draftText = cfg.draftSavedAt
    ? `Rascunho salvo automaticamente às ${new Date(cfg.draftSavedAt).toLocaleTimeString(
        "pt-BR",
        { hour: "2-digit", minute: "2-digit" },
      )} — nada se perde se você sair.`
    : "Rascunho automático ativo — nada se perde se você sair."

  // Parecer final: a primária da barra finaliza a análise.
  if (finalGate) {
    const ready = Boolean(cfg.reviewSummary?.trim())
    return {
      state: (ready ? "armed" : "pending") as ClosureBarState,
      statusText: ready
        ? "Decisão e parecer prontos — finalizar grava o parecer e conclui a análise."
        : draftText,
      pendingText: ready ? undefined : "falta: escrever o parecer",
      primaryLabel: "Finalizar análise",
      onPrimary: cfg.onFinalize,
      primaryLoading: cfg.finalizing,
      primaryDisabled: !ready,
    }
  }

  const waiting = estacao.members.find((m) => m.state === "waiting_input")

  if (waiting?.nodeType === "document_request") {
    // Prontidão real dos docs DESTA estação (mesma régua da Faturamento).
    const out = (waiting.output ?? {}) as { required?: string[] }
    const required = Array.isArray(out.required) ? out.required : []
    const stationDocs = required.length
      ? cfg.docs.filter((d) =>
          required.some((t) => t.toLowerCase() === d.doc_type.toLowerCase()),
        )
      : cfg.docs
    const uploaded = new Set(stationDocs.map((d) => d.doc_type.toLowerCase()))
    const missing = required.filter((t) => !uploaded.has(t.toLowerCase()))
    const processing = stationDocs.some(
      (d) => d.extraction_status === "pending" || d.extraction_status === "processing",
    )
    const hasError = stationDocs.some((d) => d.extraction_status === "error")
    const processedOk = stationDocs.some(
      (d) => d.extraction_status === "success" || d.extraction_status === "validated",
    )
    const ready =
      stationDocs.length > 0 &&
      missing.length === 0 &&
      !processing &&
      !hasError &&
      processedOk
    if (ready) {
      return {
        state: "armed",
        statusText:
          "Valores conferidos — enviar grava a seção no dossiê e aciona os cruzamentos e a análise.",
        primaryLabel: "Enviar para análise",
        primaryIcon: RiArrowRightLine,
        onPrimary: () => cfg.onSendToAnalysis(waiting.id, required),
        primaryLoading: cfg.submitting,
        statusIcon: RiArchiveDrawerLine,
      }
    }
    return {
      state: "pending",
      statusText: draftText,
      pendingText: missing.length
        ? `falta: enviar ${missing.map((t) => t.toLowerCase()).join(", ")}`
        : hasError
          ? "falta: tratar a falha da extração"
          : processing
            ? "falta: aguardar a extração do documento"
            : "falta: enviar e processar o documento",
      primaryLabel: "Enviar para análise",
      onPrimary: () => {},
    }
  }

  if (waiting?.nodeType === "human_review") {
    return {
      state: "pending",
      statusText: draftText,
      pendingText: "falta: homologar a conclusão do agente",
      primaryLabel: "Fechar estação",
      onPrimary: () => {},
    }
  }

  // Gate de seleção JUCESP (opção B): o próprio <JucespDocSelector> tem os botões
  // ("usar este" / "anexar manual"). A barra só orienta — sem primária aqui pra
  // não criar uma segunda ação que enviaria o node vazio (= cair no manual).
  if (
    waiting?.nodeType === "official_document_fetch" &&
    (waiting.output as { phase?: string } | null)?.phase === "select"
  ) {
    return {
      state: "pending",
      statusText:
        "Escolha o documento na lista acima — a busca dispara assim que você confirmar.",
      pendingText: "falta: escolher o documento (ou anexar manual)",
    }
  }

  // Gate de HOMOLOGAÇÃO da busca oficial (waiting_input SEM phase=select): o doc
  // já foi baixado e extraído; a homologação é o PATCH da conferência (botão na
  // própria <SocialContractConferenceView>), NÃO um submit vazio do node. Sem
  // este branch a barra caía no genérico abaixo e oferecia "Fechar estação" →
  // onSubmitEmpty, reenviando o node vazio (só a idempotência do node evitava
  // cair no fluxo manual). DC-2026-0044.
  if (waiting?.nodeType === "official_document_fetch") {
    return {
      state: "pending",
      statusText:
        "Documento localizado e lido. Homologue a conferência abaixo para seguir pra análise.",
      pendingText: "falta: homologar a conferência da extração",
    }
  }

  if (waiting) {
    // Form com submit próprio (DynamicForm) — sem segunda primária na barra.
    const descriptor = (waiting.formDescriptor ?? {}) as { fields?: FormField[] }
    if ((descriptor.fields ?? []).length === 0) {
      return {
        state: "armed",
        statusText: "Nada a preencher aqui — fechar segue a análise.",
        primaryLabel: "Fechar estação",
        onPrimary: () => cfg.onSubmitEmpty(waiting.id),
        primaryLoading: cfg.submitting,
      }
    }
    return {
      state: "pending",
      statusText: draftText,
      pendingText: "falta: preencher os dados e salvar",
    }
  }

  if (estacao.state === "rodando") {
    return {
      state: "pending",
      statusText: "Agente trabalhando — esta tela atualiza sozinha.",
      pendingText: "falta: aguardar o agente concluir",
      primaryLabel: "Fechar estação",
      onPrimary: () => {},
    }
  }

  if (estacao.state === "falhou") {
    return {
      state: "pending",
      statusText: "Trabalho parcial preservado — nada foi descartado.",
      pendingText: "falta: tratar a falha da etapa",
      primaryLabel: "Fechar estação",
      onPrimary: () => {},
    }
  }

  if (estacao.state === "fechada" || estacao.state === "fechada_com_ressalva") {
    const idx = estacoes.indexOf(estacao)
    // Sequencial: a próxima é a PRIMEIRA não-fechada em ordem (mesmo rodando).
    const next = estacoes.find(
      (e, i) =>
        i > idx && e.state !== "fechada" && e.state !== "fechada_com_ressalva",
    ) ??
    estacoes.find(
      (e, i) =>
        i < idx && e.state !== "fechada" && e.state !== "fechada_com_ressalva",
    )
    if (next) {
      return {
        state: "armed",
        statusText: "Seção gravada no dossiê — esta estação está fechada.",
        primaryLabel: `Ir para → Estação ${estacoes.indexOf(next) + 1} · ${next.label}`,
        primaryIcon: RiArrowRightLine,
        onPrimary: () => cfg.onGoTo(next.id),
        statusIcon: RiArchiveDrawerLine,
      }
    }
    return {
      state: "armed",
      statusText:
        "Seção gravada no dossiê — nenhuma pendência aberta nas demais estações.",
      primaryLabel: "Voltar à fila",
      primaryIcon: RiArrowRightLine,
      onPrimary: cfg.onBackToQueue,
      statusIcon: RiArchiveDrawerLine,
    }
  }

  return null
}

// ─── Gate de homologação (human_review com review_of) ───────────────────────

function GateZone({
  config,
  externalAnalysis,
  onApprove,
  approving,
  onReprocess,
  reprocessing,
}: {
  config: { title?: string; description?: string }
  /** Análise do agente quando ela NÃO é membro desta estação. */
  externalAnalysis?: React.ReactNode
  onApprove: (notes: string) => void
  approving: boolean
  onReprocess?: () => void
  reprocessing?: boolean
}) {
  const [notes, setNotes] = React.useState("")
  return (
    <div className="space-y-4">
      <div>
        <p className="flex items-center gap-2 text-sm font-medium text-gray-900 dark:text-gray-50">
          <RiSparkling2Line
            className="size-4"
            style={{ color: provenanceTokens.agente.color }}
            aria-hidden
          />
          {config.title ?? "Homologação da conclusão"}
        </p>
        <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
          {config.description ??
            "Homologar registra: conclusão da IA + sua observação + data/hora — tudo entra na trilha."}
        </p>
      </div>

      {externalAnalysis}

      <div>
        <p className="mb-1.5 text-xs font-medium text-gray-700 dark:text-gray-300">
          Observação do analista (opcional)
        </p>
        <Textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          placeholder="Ajustes, ressalvas ou concordância com a leitura do agente…"
        />
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2">
        {onReprocess && (
          <Button
            variant="secondary"
            className="h-8"
            onClick={onReprocess}
            isLoading={reprocessing}
          >
            <RiLoopLeftLine className="mr-1.5 size-4" aria-hidden />
            Reprocessar análise
          </Button>
        )}
        <Button className="h-8" onClick={() => onApprove(notes)} isLoading={approving}>
          <RiCheckLine className="mr-1.5 size-4" aria-hidden />
          Homologar e continuar
        </Button>
      </div>
    </div>
  )
}

// ─── Falha com dignidade (frame A4) ─────────────────────────────────────────

function FailedZone({
  step,
  onRerun,
  rerunning,
}: {
  step: WizardMultiStepStep
  onRerun: () => void
  rerunning: boolean
}) {
  const isAgent = step.nodeType === "specialist_agent"
  return (
    <div className="flex flex-col gap-2.5">
      <div className="flex items-center gap-2.5">
        <span className="relative flex size-8 shrink-0 items-center justify-center rounded-full bg-gray-100 dark:bg-gray-800">
          {isAgent ? (
            <RiSparkling2Line
              className="size-4"
              style={{ color: provenanceTokens.agente.color }}
              aria-hidden
            />
          ) : (
            <RiErrorWarningLine className="size-4 text-gray-500" aria-hidden />
          )}
          <span
            className="absolute -bottom-0.5 -right-0.5 flex size-3.5 items-center justify-center rounded-full border-[1.5px] border-white dark:border-gray-950"
            style={{ background: "#FEFCE8" }}
          >
            <RiErrorWarningLine
              className="size-2.5"
              style={{ color: "#713F12" }}
              aria-hidden
            />
          </span>
        </span>
        <div>
          <p className="text-[13px] font-semibold text-gray-900 dark:text-gray-50">
            {step.label} não concluiu
          </p>
          <p className="text-[11px] text-gray-400 dark:text-gray-500">
            tentativa registrada na trilha
          </p>
        </div>
      </div>
      <p className="text-[12.5px] leading-relaxed text-gray-500 dark:text-gray-400">
        O que já foi apurado foi preservado — nada se descarta. Você pode reprocessar a
        etapa que faltou.
        {step.errorDetail ? (
          <span className="mt-1 block text-[11.5px] text-gray-400">
            {step.errorDetail}
          </span>
        ) : null}
      </p>
      <div>
        <Button className="h-8" onClick={onRerun} isLoading={rerunning}>
          <RiRestartLine className="mr-1.5 size-4" aria-hidden />
          Reprocessar etapa
        </Button>
      </div>
    </div>
  )
}

// ─── Checkpoint final (parecer) — controlado, primária na barra ─────────────

function buildDraftSummary(flags: RedFlagItem[]): string {
  if (flags.length === 0) {
    return (
      "Análise concluída sem inconsistências determinísticas. " +
      "Revise e finalize o parecer."
    )
  }
  const crit = flags.filter((f) => f.severity === "critical").length
  const imp = flags.filter((f) => f.severity === "important").length
  const parts: string[] = []
  if (crit) parts.push(`${crit} crítica(s)`)
  if (imp) parts.push(`${imp} importante(s)`)
  const top = flags
    .slice(0, 3)
    .map((f) => f.title)
    .join("; ")
  return (
    `Análise identificou ${flags.length} inconsistência(s)` +
    `${parts.length ? ` (${parts.join(", ")})` : ""}. Principais: ${top}. ` +
    "Revise e ajuste o parecer."
  )
}

const RECO_OPTIONS: Array<{ value: OpinionInput["recommendation"]; label: string }> = [
  { value: "approve", label: "Aprovar" },
  { value: "conditional", label: "Aprovação condicional" },
  { value: "deny", label: "Negar" },
]

function flagSeverityBadge(severity: RedFlagItem["severity"]): {
  label: string
  tone: string
} {
  if (severity === "critical") {
    return {
      label: "Crítico",
      tone: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
    }
  }
  if (severity === "important") {
    return {
      label: "Importante",
      tone: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
    }
  }
  return {
    label: "Informativo",
    tone: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
  }
}

function CheckpointReview({
  flags,
  summary,
  onSummaryChange,
  recommendation,
  onRecommendationChange,
}: {
  flags: RedFlagItem[]
  summary: string
  onSummaryChange: (v: string) => void
  recommendation: OpinionInput["recommendation"]
  onRecommendationChange: (v: OpinionInput["recommendation"]) => void
}) {
  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-medium text-gray-900 dark:text-gray-50">
          Decisão e parecer
        </p>
        <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
          Revise os apontamentos, escolha a decisão e ajuste o texto — o rascunho partiu
          da análise. Finalizar fica na barra abaixo.
        </p>
      </div>

      {flags.length > 0 ? (
        <ul className="space-y-2">
          {flags.map((f) => {
            const sev = flagSeverityBadge(f.severity)
            return (
              <li
                key={f.id}
                className="rounded-md border border-gray-100 bg-gray-50/50 p-2.5 dark:border-gray-900 dark:bg-gray-950/50"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {f.title}
                  </span>
                  <span className={cx(tableTokens.badge, sev.tone)}>{sev.label}</span>
                </div>
                <p className="mt-0.5 text-xs text-gray-700 dark:text-gray-300">
                  {f.description}
                </p>
              </li>
            )
          })}
        </ul>
      ) : (
        <p className={tableTokens.cellSecondary}>
          Nenhuma inconsistência determinística encontrada.
        </p>
      )}

      <div>
        <p className="mb-1.5 text-xs font-medium text-gray-700 dark:text-gray-300">
          Decisão
        </p>
        {/* Controle segmentado do D5: selecionado = fundo azul primary. */}
        <div className="inline-flex overflow-hidden rounded border border-gray-200 shadow-xs dark:border-gray-800">
          {RECO_OPTIONS.map((opt, i) => {
            const selected = recommendation === opt.value
            return (
              <button
                key={opt.value}
                type="button"
                onClick={() => onRecommendationChange(opt.value)}
                className={cx(
                  "flex items-center gap-1.5 px-[18px] py-2 text-[13px] transition-colors duration-100",
                  selected
                    ? "bg-blue-500 font-semibold text-white"
                    : "bg-white font-medium text-gray-500 hover:bg-gray-50 dark:bg-gray-950 dark:text-gray-400 dark:hover:bg-gray-900",
                  i > 0 && !selected && "border-l border-gray-200 dark:border-gray-800",
                )}
              >
                {selected && <RiCheckLine className="size-3.5" aria-hidden />}
                {opt.label}
              </button>
            )
          })}
        </div>
      </div>

      <div>
        <p className="mb-1.5 text-xs font-medium text-gray-700 dark:text-gray-300">
          Parecer (rascunho editável)
        </p>
        <Textarea
          value={summary}
          onChange={(e) => onSummaryChange(e.target.value)}
          rows={6}
        />
      </div>
    </div>
  )
}

// ─── Helpers (grafo → steps) ────────────────────────────────────────────────

const NODE_TYPE_LABEL: Record<string, string> = {
  trigger: "Início",
  human_input: "Coleta de dados",
  bureau_query: "Consulta a bureau",
  specialist_agent: "Análise por agente IA",
  document_request: "Documentos",
  document_extractor: "Extração de documento",
  conditional_branch: "Decisão condicional",
  human_review: "Revisão humana",
  http_request: "Requisição HTTP",
  output_generator: "Saída final",
  notification: "Notificação",
}

function topologicalOrder(nodes: NodeSpec[], edges: EdgeSpec[]): string[] {
  const inDegree = new Map<string, number>()
  const adjacency = new Map<string, string[]>()
  for (const n of nodes) {
    inDegree.set(n.id, 0)
    adjacency.set(n.id, [])
  }
  for (const e of edges) {
    if (!inDegree.has(e.source) || !inDegree.has(e.target)) continue
    inDegree.set(e.target, (inDegree.get(e.target) ?? 0) + 1)
    adjacency.get(e.source)!.push(e.target)
  }
  const queue: string[] = []
  inDegree.forEach((deg, id) => {
    if (deg === 0) queue.push(id)
  })
  queue.sort()
  const result: string[] = []
  while (queue.length > 0) {
    const id = queue.shift()!
    result.push(id)
    for (const next of adjacency.get(id) ?? []) {
      inDegree.set(next, inDegree.get(next)! - 1)
      if (inDegree.get(next) === 0) {
        queue.push(next)
        queue.sort()
      }
    }
  }
  for (const n of nodes) {
    if (!result.includes(n.id)) result.push(n.id)
  }
  return result
}

function stepFromNodeRun(
  nr: NodeRunSummary,
  pendingNode: NodeRunSummary | null,
): WizardMultiStepStep {
  const state = stepStateFromRun(nr, pendingNode)
  return {
    id: nr.node_id,
    label: NODE_TYPE_LABEL[nr.node_type] ?? nr.node_id,
    state,
    nodeType: nr.node_type,
    durationMs: nr.duration_ms,
    errorDetail: nr.error_detail,
    output: nr.output_data,
    input: nr.input_data,
    costBrl: Number(nr.cost_brl) || 0,
    formDescriptor:
      state === "waiting_input" ? (nr.output_data as Record<string, unknown>) : undefined,
  }
}

function buildSteps(
  graph: { nodes: NodeSpec[]; edges: EdgeSpec[] },
  nodeRuns: NodeRunSummary[],
  pendingNode: NodeRunSummary | null,
): WizardMultiStepStep[] {
  const order = topologicalOrder(graph.nodes, graph.edges)
  const nodeRunByNodeId = new Map<string, NodeRunSummary>()
  for (const nr of nodeRuns) nodeRunByNodeId.set(nr.node_id, nr)

  return order.map((nodeId) => {
    const spec = graph.nodes.find((n) => n.id === nodeId)
    const label = spec?.label ?? (spec ? NODE_TYPE_LABEL[spec.type] ?? spec.type : nodeId)
    const nodeType = spec?.type ?? "unknown"
    const run = nodeRunByNodeId.get(nodeId)

    if (!run) {
      return {
        id: nodeId,
        label,
        state: "pending" as const,
        nodeType,
        config: spec?.config,
      }
    }
    const stepState = stepStateFromRun(run, pendingNode)
    return {
      id: nodeId,
      label,
      state: stepState,
      nodeType,
      config: spec?.config,
      durationMs: run.duration_ms,
      errorDetail: run.error_detail,
      output: run.output_data,
      input: run.input_data,
      costBrl: Number(run.cost_brl) || 0,
      formDescriptor:
        stepState === "waiting_input"
          ? (run.output_data as Record<string, unknown>)
          : undefined,
    }
  })
}

function stepStateFromRun(
  run: NodeRunSummary,
  pendingNode: NodeRunSummary | null,
): WizardMultiStepStep["state"] {
  if (pendingNode && pendingNode.id === run.id) return "waiting_input"
  switch (run.status) {
    case "waiting_input":
      return "waiting_input"
    case "running":
      return "running"
    case "completed":
      return "completed"
    case "failed":
      return "failed"
    case "skipped":
      return "skipped"
    default:
      return "pending"
  }
}

function extractAgentOutput<T>(steps: WizardMultiStepStep[], agentName: string): T | null {
  const match = steps.find(
    (s) =>
      s.state === "completed" &&
      s.nodeType === "specialist_agent" &&
      (agentOf(s) === agentName ||
        s.id === agentName ||
        s.id === agentName.replace(/_analyst$/, "") ||
        s.id === agentName.replace(/_writer$/, "")),
  )
  if (!match || !match.output || Object.keys(match.output).length === 0) return null
  return match.output as T
}
