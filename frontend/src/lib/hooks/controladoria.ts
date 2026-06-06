"use client"

/**
 * React Query hooks do modulo Controladoria.
 * Espelha endpoints em backend/app/modules/controladoria/api/.
 */

import * as React from "react"
import { differenceInCalendarDays, parseISO } from "date-fns"
import { useMutation, useQuery } from "@tanstack/react-query"

import {
  buildCotaSubAgenteVariacaoStreamRequest,
  coerceAgenteVariacaoRun,
  controladoria,
  type AgenteVariacaoRunResponse,
  type AgenteVariacaoRunResponseDTO,
  type CoverageDay,
  type EvolucaoClasse,
  type EvolucaoGranularidade,
  type DreBaseFilters,
  type DreBreakdownFilters,
  type DreDrillFornecedoresFilters,
  type DrePivotFilters,
  type DreRoaFilters,
} from "@/lib/api-client"
import {
  buildCoverageStripEntry,
  isCoverageStripEntryHealthy,
  type AgentToolLogEntry,
  type CoverageStripEntry,
} from "@/design-system/components"

import { useSourceCoverage } from "./integracoes"

const KEYS = {
  balancoEstrutural: (fundoId: string, data: string, dataAnterior?: string) =>
    ["controladoria", "cota-sub", "balanco-estrutural", fundoId, data, dataAnterior ?? null] as const,
  variacaoHeadline: (fundoId: string, data: string, dataAnterior?: string) =>
    ["controladoria", "cota-sub", "variacao-headline", fundoId, data, dataAnterior ?? null] as const,
  variacoesDia: (fundoId: string, data: string, dataAnterior?: string) =>
    ["controladoria", "cota-sub", "variacoes-dia", fundoId, data, dataAnterior ?? null] as const,
  datasDisponiveis: (fundoId: string) =>
    ["controladoria", "cota-sub", "datas-disponiveis", fundoId] as const,

  evolucaoPatrimonial: (
    fundoId: string,
    granularidade: string,
    periodoInicio?: string,
    periodoFim?: string,
    classes?: string[],
  ) =>
    [
      "controladoria",
      "evolucao-patrimonial",
      "serie",
      fundoId,
      granularidade,
      periodoInicio ?? null,
      periodoFim ?? null,
      (classes ?? []).join(",") || null,
    ] as const,
  // F2 drills (2026-05-23)
  drillDc: (fundoId: string, data: string, dataAnterior?: string) =>
    ["controladoria", "cota-sub", "drill", "dc", fundoId, data, dataAnterior ?? null] as const,
  drillPdd: (fundoId: string, data: string, dataAnterior?: string, thresholdBrl?: number, topN?: number) =>
    ["controladoria", "cota-sub", "drill", "pdd", fundoId, data, dataAnterior ?? null, thresholdBrl ?? null, topN ?? null] as const,
  drillCpr: (fundoId: string, data: string, dataAnterior?: string, side?: "receber" | "pagar") =>
    ["controladoria", "cota-sub", "drill", "cpr", fundoId, data, dataAnterior ?? null, side ?? null] as const,
  drillOrigem: (fundoId: string, data: string, linha: string) =>
    ["controladoria", "cota-sub", "drill", "origem", fundoId, data, linha] as const,

  dreCompetencias: (f: DreBaseFilters) =>
    ["controladoria", "dre", "competencias", f] as const,
  drePivot: (f: DrePivotFilters) =>
    ["controladoria", "dre", "pivot", f] as const,
  dreFornecedores: (f: DreDrillFornecedoresFilters) =>
    ["controladoria", "dre", "fornecedores", f] as const,
  dreBreakdown: (f: DreBreakdownFilters) =>
    ["controladoria", "dre", "breakdown", f] as const,
  dreRoa: (f: DreRoaFilters) =>
    ["controladoria", "dre", "roa", f] as const,
}

export function useDatasDisponiveis(
  fundoId: string | null | undefined,
) {
  // Datas em que a QiTech publicou snapshot da UA. Usado pelo Calendar para
  // impedir selecao de dias sem dados (fim de semana, feriado, falha ETL).
  // staleTime longo porque ETL nao roda toda hora.
  const enabled = !!fundoId
  return useQuery({
    queryKey: KEYS.datasDisponiveis(fundoId ?? ""),
    queryFn: () => controladoria.cotaSubDatasDisponiveis(fundoId!),
    enabled,
    staleTime: 60 * 60 * 1000,  // 1 hora
  })
}

export function useEvolucaoPatrimonial(
  fundoId: string | null | undefined,
  opts?: {
    periodoInicio?: string | null
    periodoFim?:    string | null
    granularidade?: EvolucaoGranularidade
    classes?:       EvolucaoClasse[]
  },
) {
  // Serie temporal do PL do passivo (todas as classes). Default mensal /
  // 12M corridos / todas as classes resolvido no backend.
  const granularidade = opts?.granularidade ?? "mensal"
  const enabled = !!fundoId
  return useQuery({
    queryKey: KEYS.evolucaoPatrimonial(
      fundoId ?? "",
      granularidade,
      opts?.periodoInicio ?? undefined,
      opts?.periodoFim ?? undefined,
      opts?.classes,
    ),
    queryFn: () =>
      controladoria.evolucaoPatrimonialSerie({
        fundoId: fundoId!,
        periodoInicio: opts?.periodoInicio ?? undefined,
        periodoFim:    opts?.periodoFim ?? undefined,
        granularidade,
        classes:       opts?.classes,
      }),
    enabled,
    staleTime: 5 * 60 * 1000,
  })
}

export function useBalancoEstrutural(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  dataAnterior?: string | null,
) {
  // Balance hero ESTRUTURAL (redesign 2026-05-27). Coerente por natureza +
  // sinal: PDD contra-ativo, CPR dividido, Cotas Prioritarias, reconciliacao
  // MEC a parte. Endpoint aditivo — nao quebra a tool do agente.
  const enabled = !!fundoId && !!data
  return useQuery({
    queryKey: KEYS.balancoEstrutural(fundoId ?? "", data ?? "", dataAnterior ?? undefined),
    queryFn: () => controladoria.cotaSubBalancoEstrutural(
      fundoId!,
      data!,
      dataAnterior ?? undefined,
    ),
    enabled,
    staleTime: 5 * 60 * 1000,
  })
}

export function useVariacaoHeadline(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  dataAnterior?: string | null,
) {
  // O read de 10s (Fase 1, 2026-05-31): veredito + drivers giro-limpos + flags.
  // Estruturado, deterministico, monta das tools. Substitui o MOCK_INSIGHTS + o
  // botao morto do monolito.
  const enabled = !!fundoId && !!data
  return useQuery({
    queryKey: KEYS.variacaoHeadline(fundoId ?? "", data ?? "", dataAnterior ?? undefined),
    queryFn: () => controladoria.cotaSubVariacaoHeadline(
      fundoId!,
      data!,
      dataAnterior ?? undefined,
    ),
    enabled,
    staleTime: 5 * 60 * 1000,
  })
}

export function useVariacaoResumo(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  dataAnterior?: string | null,
) {
  // A aba "Resumo do dia" (redesign 2026-06-01): waterfall por grupo de balanco
  // (giro-limpo) + ancoras MEC + reconciliacao + atencoes. Substitui o headline.
  const enabled = !!fundoId && !!data
  return useQuery({
    queryKey: ["controladoria", "cota-sub", "variacao-resumo", fundoId ?? "", data ?? "", dataAnterior ?? null] as const,
    queryFn: () => controladoria.cotaSubVariacaoResumo(fundoId!, data!, dataAnterior ?? undefined),
    enabled,
    staleTime: 5 * 60 * 1000,
  })
}

export function useVariacaoDiariaSerie(
  fundoId: string | null | undefined,
  competencia: string | null | undefined, // "YYYY-MM"
) {
  // Serie diaria da variacao da Cota Sub na competencia — o MASTER do
  // master-detail da aba "Resumo do dia". 1 request por competencia; trocar de
  // dia so re-chaveia o useVariacaoResumo (cacheado por dia). Ver dependencia
  // de backend documentada em api-client (endpoint /variacao-diaria).
  const enabled = !!fundoId && !!competencia
  return useQuery({
    queryKey: ["controladoria", "cota-sub", "variacao-diaria", fundoId ?? "", competencia ?? ""] as const,
    queryFn: () => controladoria.cotaSubVariacaoDiaria(fundoId!, competencia!),
    enabled,
    staleTime: 5 * 60 * 1000,
  })
}

export function useVariacaoDetalhamento(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  dataAnterior?: string | null,
) {
  // O painel dos 60% — uma area por card com o resumo da sua tool, clicavel.
  const enabled = !!fundoId && !!data
  return useQuery({
    queryKey: ["controladoria", "cota-sub", "variacao-detalhamento", fundoId ?? "", data ?? "", dataAnterior ?? null] as const,
    queryFn: () => controladoria.cotaSubVariacaoDetalhamento(fundoId!, data!, dataAnterior ?? undefined),
    enabled,
    staleTime: 5 * 60 * 1000,
  })
}

export function useDrillContasAPagar(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  dataAnterior?: string | null,
) {
  // Drill da linha Contas a Pagar — Auditor de Contas a Pagar (provisoes +
  // pagamentos + impacto nao provisionado).
  const enabled = !!fundoId && !!data
  return useQuery({
    queryKey: ["controladoria", "cota-sub", "drill-contas-a-pagar", fundoId ?? "", data ?? "", dataAnterior ?? null] as const,
    queryFn: () => controladoria.cotaSubDrillContasAPagar(fundoId!, data!, dataAnterior ?? undefined),
    enabled,
    staleTime: 5 * 60 * 1000,
  })
}

export function useDrillCotas(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  dataAnterior?: string | null,
  enabledExtra = true,
) {
  // Drill das linhas de Cota/Passivo (Sr/Mez/Obrigacoes) — Auditor de Cotas.
  const enabled = !!fundoId && !!data && enabledExtra
  return useQuery({
    queryKey: ["controladoria", "cota-sub", "drill-cotas", fundoId ?? "", data ?? "", dataAnterior ?? null] as const,
    queryFn: () => controladoria.cotaSubDrillCotas(fundoId!, data!, dataAnterior ?? undefined),
    enabled,
    staleTime: 5 * 60 * 1000,
  })
}

export function useDrillAplicacoes(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  dataAnterior?: string | null,
  enabledExtra = true,
) {
  // Drill do grupo Aplicacoes — rendimento DI (valorizacao = a barra) vs capital
  // (aplicacao/resgate, neutro) por fundo DI + linhas menores.
  const enabled = !!fundoId && !!data && enabledExtra
  return useQuery({
    queryKey: ["controladoria", "cota-sub", "drill-aplicacoes", fundoId ?? "", data ?? "", dataAnterior ?? null] as const,
    queryFn: () => controladoria.cotaSubDrillAplicacoes(fundoId!, data!, dataAnterior ?? undefined),
    enabled,
    staleTime: 5 * 60 * 1000,
  })
}

export function useVariacoesDia(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  dataAnterior?: string | null,
) {
  // Consumido pela pagina Pagamento Diario (conciliacao pagamento->provisao).
  const enabled = !!fundoId && !!data
  return useQuery({
    queryKey: KEYS.variacoesDia(fundoId ?? "", data ?? "", dataAnterior ?? undefined),
    queryFn: () => controladoria.cotaSubVariacoesDia(
      fundoId!,
      data!,
      dataAnterior ?? undefined,
    ),
    enabled,
    staleTime: 5 * 60 * 1000,
  })
}

// ── Drills DC / PDD / CPR (F2 do redesign, 2026-05-23) ────────────────────

export function useDrillDc(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  dataAnterior?: string | null,
  enabled: boolean = true,
) {
  const ready = !!fundoId && !!data && enabled
  return useQuery({
    queryKey: KEYS.drillDc(fundoId ?? "", data ?? "", dataAnterior ?? undefined),
    queryFn: () => controladoria.cotaSubDrillDc(fundoId!, data!, dataAnterior ?? undefined),
    enabled: ready,
    staleTime: 5 * 60 * 1000,
  })
}

export function useDrillPdd(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  opts?: {
    dataAnterior?: string | null
    thresholdBrl?: number
    topN?:         number
    enabled?:      boolean
  },
) {
  const ready = !!fundoId && !!data && (opts?.enabled ?? true)
  return useQuery({
    queryKey: KEYS.drillPdd(
      fundoId ?? "",
      data ?? "",
      opts?.dataAnterior ?? undefined,
      opts?.thresholdBrl,
      opts?.topN,
    ),
    queryFn: () => controladoria.cotaSubDrillPdd(fundoId!, data!, {
      dataAnterior: opts?.dataAnterior ?? undefined,
      thresholdBrl: opts?.thresholdBrl,
      topN:         opts?.topN,
    }),
    enabled: ready,
    staleTime: 5 * 60 * 1000,
  })
}

export function useDrillCpr(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  dataAnterior?: string | null,
  side?: "receber" | "pagar",
  enabled: boolean = true,
) {
  const ready = !!fundoId && !!data && enabled
  return useQuery({
    queryKey: KEYS.drillCpr(fundoId ?? "", data ?? "", dataAnterior ?? undefined, side),
    queryFn: () => controladoria.cotaSubDrillCpr(fundoId!, data!, dataAnterior ?? undefined, side),
    enabled: ready,
    staleTime: 5 * 60 * 1000,
  })
}

export function useDrillOrigem(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  linha: string | null | undefined,
  enabled: boolean = true,
) {
  const ready = !!fundoId && !!data && !!linha && enabled
  return useQuery({
    queryKey: KEYS.drillOrigem(fundoId ?? "", data ?? "", linha ?? ""),
    queryFn: () => controladoria.cotaSubDrillOrigem(fundoId!, data!, linha!),
    enabled: ready,
    staleTime: 5 * 60 * 1000,
  })
}

// ── Readiness QiTech (gate da pagina Cota Sub) ────────────────────────────
//
// A pagina Cota Sub depende de 8 reports QiTech para uma data especifica.
// Esse hook consulta /integracoes/sources/admin:qitech/coverage e devolve
// `{ entries, allReady, blocking }` — o consumer renderiza o strip de
// saude e aplica o gate suave (so renderiza analise quando allReady).
//
// staleTime espelha o do `useSourceCoverage` (5min) — coverage nao muda em
// segundos. Quando o user dispara backfill, invalidar manualmente via
// `useCreateBackfill` ja faz o refetch.

/** Reports QiTech que alimentam a pagina Cota Sub. Ordem = display order.
 *
 * `advisory: true` marca reports que NAO bloqueiam o render quando ausentes.
 * O strip mostra o estado de saude para o user, mas `allReady` e `blocking`
 * ignoram esses entries. Uso atual: `market.fidc_estoque` e assincrono
 * (job + callback) e frequentemente atrasa em relacao aos market.* sincronos;
 * quando ausente, os drivers consolidados (PDD, DC) ainda renderizam com
 * valor correto vindo do MEC/posicoes — apenas as evidencias granulares
 * papel-a-papel ficam vazias. Bloquear a pagina toda seria forte demais.
 */
export const COTA_SUB_REPORTS: ReadonlyArray<{
  name:       string
  shortLabel: string
  fullLabel:  string
  advisory?:  boolean
}> = [
  { name: "market.tesouraria",        shortLabel: "Tesouraria",  fullLabel: "Tesouraria"                },
  { name: "market.conta_corrente",    shortLabel: "Conta corr.", fullLabel: "Conta-corrente"            },
  { name: "market.rf",                shortLabel: "RF",          fullLabel: "Renda fixa"                },
  // RF compromissadas e legitimamente vazio na maioria dos dias (so existe
  // operacao quando o fundo paquera caixa via compromissada overnight/curto).
  // Marcado advisory: nao bloqueia gate. Quando ha operacao, silver popula
  // e o driver Compromissada da Cota Sub mostra o valor. Quando nao ha, fica
  // R$ 0 — que e a verdade.
  {
    name:       "market.rf_compromissadas",
    shortLabel: "RF compr.",
    fullLabel:  "RF compromissadas",
    advisory:   true,
  },
  { name: "market.outros_fundos",     shortLabel: "Out. fundos", fullLabel: "Posicao em outros fundos"  },
  // Outros ativos tambem fica frequentemente vazio (endpoint cobre instrumentos
  // pouco comuns). Mesma logica do rf_compromissadas: ausencia = zero real
  // pra cota-sub.
  {
    name:       "market.outros_ativos",
    shortLabel: "Out. ativos",
    fullLabel:  "Outros ativos",
    advisory:   true,
  },
  { name: "market.cpr",               shortLabel: "CPR",         fullLabel: "CPR (movimentacoes)"       },
  { name: "market.mec",               shortLabel: "MEC",         fullLabel: "MEC (evolucao cotas)"      },
  {
    name:       "market.fidc_estoque",
    shortLabel: "Carteira",
    fullLabel:  "Estoque do FIDC (carteira granular)",
    advisory:   true,
  },
] as const

export type CotaSubReadiness = {
  /** 1 entry por report, na ordem canonica de `COTA_SUB_REPORTS`. */
  entries:   CoverageStripEntry[]
  /** Todos os entries em `ready`/`may_change`. */
  allReady:  boolean
  /** Entries que bloqueiam (in_progress/blocked/na). */
  blocking:  CoverageStripEntry[]
  /** Estado bruto da query (loading/error/refetching). */
  isLoading: boolean
  isError:   boolean
  refetch:   () => void
}

/**
 * Calcula `range_days` minimo para incluir `dataIso` no payload do /coverage.
 * `range_days` no backend representa "ultimos N dias contando hoje" — entao
 * precisamos cobrir do `dataIso` ate hoje. Cap em 365d (1 ano) para nao puxar
 * payload absurdo se o user picar data antiga.
 */
function _rangeDaysFor(dataIso: string | null | undefined): number {
  if (!dataIso) return 7
  try {
    const diff = differenceInCalendarDays(new Date(), parseISO(dataIso))
    return Math.min(Math.max(7, diff + 3), 365)
  } catch {
    return 7
  }
}

export function useCotaSubReadiness(
  fundoId: string | null | undefined,
  data:    string | null | undefined,
): CotaSubReadiness {
  const cov = useSourceCoverage(
    fundoId ? "admin:qitech" : null,
    _rangeDaysFor(data),
    fundoId,
  )

  const entries = React.useMemo<CoverageStripEntry[]>(() => {
    const byName = new Map<string, CoverageDay | undefined>()
    if (cov.data && data) {
      for (const ep of cov.data.endpoints) {
        const day = ep.days.find((d) => d.data === data)
        byName.set(ep.name, day)
      }
    }
    return COTA_SUB_REPORTS.map((r) =>
      buildCoverageStripEntry({
        name:       r.name,
        shortLabel: r.shortLabel,
        fullLabel:  r.fullLabel,
        advisory:   r.advisory,
        day:        byName.get(r.name),
      }),
    )
  }, [cov.data, data])

  // Advisory reports (ex.: market.fidc_estoque) aparecem no strip mas nao
  // bloqueiam o render — quando ausentes, drivers consolidados continuam
  // corretos; apenas evidencias granulares ficam vazias.
  const advisoryNames = React.useMemo(
    () => new Set(COTA_SUB_REPORTS.filter((r) => r.advisory).map((r) => r.name)),
    [],
  )
  const allReady = entries.every(
    (e) => advisoryNames.has(e.name) || isCoverageStripEntryHealthy(e),
  )
  const blocking = entries.filter(
    (e) => !advisoryNames.has(e.name) && !isCoverageStripEntryHealthy(e),
  )

  return {
    entries,
    allReady,
    blocking,
    isLoading: cov.isLoading,
    isError:   cov.isError,
    refetch:   cov.refetch,
  }
}

// ── DRE — Demonstrativo do Resultado do Exercicio ──────────────────────────
// Le silver wh_dre_mensal. fundoId aqui e INT (Bitfin), NAO UUID.

export function useDreCompetencias(filters: DreBaseFilters = {}) {
  return useQuery({
    queryKey: KEYS.dreCompetencias(filters),
    queryFn:  () => controladoria.dreCompetenciasDisponiveis(filters),
    staleTime: 30 * 60 * 1000,  // ETL Bitfin nao roda toda hora
  })
}

export function useDrePivot(filters: DrePivotFilters | null | undefined) {
  return useQuery({
    queryKey: KEYS.drePivot(filters ?? ({} as DrePivotFilters)),
    queryFn:  () => controladoria.drePivot(filters!),
    enabled:  !!filters?.competenciaDe && !!filters?.competenciaAte,
    staleTime: 5 * 60 * 1000,
  })
}

export function useDreFornecedores(
  filters: DreDrillFornecedoresFilters | null | undefined,
) {
  return useQuery({
    queryKey: KEYS.dreFornecedores(filters ?? ({} as DreDrillFornecedoresFilters)),
    queryFn:  () => controladoria.dreDrillFornecedores(filters!),
    enabled:
      !!filters?.grupoDre && !!filters?.competenciaDe && !!filters?.competenciaAte,
    staleTime: 5 * 60 * 1000,
  })
}

export function useDreBreakdown(filters: DreBreakdownFilters | null | undefined) {
  return useQuery({
    queryKey: KEYS.dreBreakdown(filters ?? ({} as DreBreakdownFilters)),
    queryFn:  () => controladoria.dreBreakdown(filters!),
    enabled:  !!filters?.competencia && !!filters?.dim,
    staleTime: 5 * 60 * 1000,
  })
}

export function useDreRoa(filters: DreRoaFilters | null | undefined) {
  return useQuery({
    queryKey: KEYS.dreRoa(filters ?? ({} as DreRoaFilters)),
    queryFn:  () => controladoria.dreRoa(filters!),
    enabled:  !!filters?.competenciaDe && !!filters?.competenciaAte,
    staleTime: 5 * 60 * 1000,
  })
}

// ─── Agente IA · analista de variacao da Cota Sub Jr ─────────────────
//
// useMutation porque invoca LLM (side effect — grava em agent_analysis_run).
// Cache no backend (1 chamada com mesmos params reaproveita resposta
// previa), entao React Query nao precisa cachear de novo.

export function useAgenteAnalistaVariacao() {
  return useMutation({
    mutationFn: ({ fundoId, data }: { fundoId: string; data: string }) =>
      controladoria.cotaSubAgenteAnalistaVariacaoRun(fundoId, data),
  })
}

// ─── Agente IA · streaming SSE (ao vivo) ─────────────────────────────
//
// Versao streaming do agente: em vez de bloquear ~90s e devolver o JSON
// pronto, mostra o trabalho do agente ao vivo (tool_use / tool_result /
// reasoning) via SSE. Le o ReadableStream no mesmo molde do useAIChat.

export type AgenteVariacaoStreamStatus = "idle" | "streaming" | "done" | "error"

export type AgenteVariacaoStreamState = {
  status:    AgenteVariacaoStreamStatus
  toolsLog:  AgentToolLogEntry[]
  result:    AgenteVariacaoRunResponse | null
  error:     string | null
  startedAt: string | null
}

const _INITIAL_STREAM_STATE: AgenteVariacaoStreamState = {
  status:    "idle",
  toolsLog:  [],
  result:    null,
  error:     null,
  startedAt: null,
}

export function useAgenteVariacaoStream() {
  const [state, setState] = React.useState<AgenteVariacaoStreamState>(_INITIAL_STREAM_STATE)
  // AbortController da execucao em curso — cancela o stream anterior se o
  // user re-disparar (Retry / trocar dia) antes do termino.
  const abortRef = React.useRef<AbortController | null>(null)

  const reset = React.useCallback(() => {
    abortRef.current?.abort()
    abortRef.current = null
    setState(_INITIAL_STREAM_STATE)
  }, [])

  const run = React.useCallback(async (fundoId: string, data: string) => {
    abortRef.current?.abort()
    const ac = new AbortController()
    abortRef.current = ac

    setState({
      status:    "streaming",
      toolsLog:  [],
      result:    null,
      error:     null,
      startedAt: new Date().toISOString(),
    })

    const { url, init } = buildCotaSubAgenteVariacaoStreamRequest(fundoId, data)

    try {
      const res = await fetch(url, { ...init, signal: ac.signal })
      if (!res.ok || !res.body) {
        let detail = res.statusText
        try {
          const errJson = (await res.json()) as { detail?: string }
          if (errJson.detail) detail = errJson.detail
        } catch {
          // ignore
        }
        throw new Error(detail || `Falha HTTP ${res.status}`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder("utf-8")
      let buffer = ""

      const handleEvent = (event: string, dataStr: string) => {
        let payload: Record<string, unknown> = {}
        try {
          payload = JSON.parse(dataStr) as Record<string, unknown>
        } catch {
          return
        }
        if (event === "step") {
          setState((s) => ({
            ...s,
            toolsLog: [...s.toolsLog, payload as unknown as AgentToolLogEntry],
          }))
        } else if (event === "result") {
          const coerced = coerceAgenteVariacaoRun(
            payload as unknown as AgenteVariacaoRunResponseDTO,
          )
          setState((s) => ({ ...s, status: "done", result: coerced }))
        } else if (event === "error") {
          const detail = (payload.detail as string) ?? "Erro desconhecido"
          setState((s) => ({ ...s, status: "error", error: detail }))
        }
      }

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // SSE frames separados por linha em branco.
        let sep: number
        while ((sep = buffer.indexOf("\n\n")) !== -1) {
          const frame = buffer.slice(0, sep)
          buffer = buffer.slice(sep + 2)
          const lines = frame.split("\n")
          let event = "message"
          const dataLines: string[] = []
          for (const line of lines) {
            if (line.startsWith("event:")) event = line.slice(6).trim()
            else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim())
          }
          if (dataLines.length > 0) handleEvent(event, dataLines.join("\n"))
        }
      }

      // Stream encerrou sem result nem error (queda de conexao no meio).
      setState((s) =>
        s.status === "streaming"
          ? { ...s, status: "error", error: "Conexao encerrada antes do resultado." }
          : s,
      )
    } catch (err) {
      if ((err as Error)?.name === "AbortError") return // re-disparo: silencioso
      setState((s) => ({
        ...s,
        status: "error",
        error:  (err as Error)?.message ?? "Erro desconhecido",
      }))
    }
  }, [])

  return { state, run, reset }
}

// ── Conciliacao de boletos (Banco Cobrador) ──────────────────────────────────

export function useConciliacaoBancoCobrador() {
  // Estado-vs-estado: carteira BITFIN atual x cobranca vigente (sem data-base).
  return useQuery({
    queryKey: ["controladoria", "conciliacao", "banco-cobrador"] as const,
    queryFn: () => controladoria.conciliacaoBancoCobrador(),
  })
}

// Dispara a coleta/reprocessamento (por tenant). Servidor roda em background
// (~1 min) e retorna 202 "iniciado"; a pagina re-busca a conciliacao depois.
export function useConciliacaoBancoCobradorSync() {
  return useMutation({
    mutationFn: () => controladoria.conciliacaoBancoCobradorSync(),
  })
}
