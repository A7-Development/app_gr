"use client"

/**
 * React Query hooks do modulo Controladoria.
 * Espelha endpoints em backend/app/modules/controladoria/api/.
 */

import * as React from "react"
import { differenceInCalendarDays, parseISO } from "date-fns"
import { useQuery } from "@tanstack/react-query"

import {
  controladoria,
  type CoverageDay,
  type DreBaseFilters,
  type DreDrillFornecedoresFilters,
  type DrePivotFilters,
} from "@/lib/api-client"
import {
  buildCoverageStripEntry,
  isCoverageStripEntryHealthy,
  type CoverageStripEntry,
} from "@/design-system/components"

import { useSourceCoverage } from "./integracoes"

const KEYS = {
  variacaoDiaria: (fundoId: string, data: string, dataAnterior?: string) =>
    ["controladoria", "cota-sub", "variacao-diaria", fundoId, data, dataAnterior ?? null] as const,
  balanco: (fundoId: string, data: string, dataAnterior?: string) =>
    ["controladoria", "cota-sub", "balanco", fundoId, data, dataAnterior ?? null] as const,
  balanceteDiario: (fundoId: string, data: string, dataAnterior?: string) =>
    ["controladoria", "cota-sub", "balancete-diario", fundoId, data, dataAnterior ?? null] as const,
  cosifRows: (fundoId: string, data: string, cosifCodigo: string) =>
    ["controladoria", "cota-sub", "cosif-rows", fundoId, data, cosifCodigo] as const,
  variacoesDia: (fundoId: string, data: string, dataAnterior?: string) =>
    ["controladoria", "cota-sub", "variacoes-dia", fundoId, data, dataAnterior ?? null] as const,
  datasDisponiveis: (fundoId: string) =>
    ["controladoria", "cota-sub", "datas-disponiveis", fundoId] as const,
  explicacaoVariacao: (fundoId: string, data: string, dataAnterior?: string, thresholdBrl?: number, topN?: number) =>
    ["controladoria", "cota-sub", "explicacao", fundoId, data, dataAnterior ?? null, thresholdBrl ?? null, topN ?? null] as const,

  dreCompetencias: (f: DreBaseFilters) =>
    ["controladoria", "dre", "competencias", f] as const,
  drePivot: (f: DrePivotFilters) =>
    ["controladoria", "dre", "pivot", f] as const,
  dreFornecedores: (f: DreDrillFornecedoresFilters) =>
    ["controladoria", "dre", "fornecedores", f] as const,
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

export function useVariacaoDiaria(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  dataAnterior?: string | null,
) {
  const enabled = !!fundoId && !!data
  return useQuery({
    queryKey: KEYS.variacaoDiaria(fundoId ?? "", data ?? "", dataAnterior ?? undefined),
    queryFn: () => controladoria.cotaSubVariacaoDiaria(
      fundoId!,
      data!,
      dataAnterior ?? undefined,
    ),
    enabled,
    staleTime: 5 * 60 * 1000,  // 5 min — dia anterior nao muda
  })
}

export function useBalanco(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  dataAnterior?: string | null,
) {
  const enabled = !!fundoId && !!data
  return useQuery({
    queryKey: KEYS.balanco(fundoId ?? "", data ?? "", dataAnterior ?? undefined),
    queryFn: () => controladoria.cotaSubBalanco(
      fundoId!,
      data!,
      dataAnterior ?? undefined,
    ),
    enabled,
    staleTime: 5 * 60 * 1000,
  })
}

export function useVariacoesDia(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  dataAnterior?: string | null,
) {
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

export function useBalanceteDiario(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  dataAnterior?: string | null,
) {
  const enabled = !!fundoId && !!data
  return useQuery({
    queryKey: KEYS.balanceteDiario(fundoId ?? "", data ?? "", dataAnterior ?? undefined),
    queryFn: () => controladoria.cotaSubBalanceteDiario(
      fundoId!,
      data!,
      dataAnterior ?? undefined,
    ),
    enabled,
    staleTime: 5 * 60 * 1000,
  })
}

export function useExplicacaoVariacao(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  opts?: {
    dataAnterior?: string | null
    thresholdBrl?: number
    topN?:         number
  },
) {
  // Explainers heuristicos da variacao do PL Sub (D-1 -> D0). Por ora so PDD.
  // Lazy: so dispara quando o usuario tem fundoId + data validos.
  const enabled = !!fundoId && !!data
  return useQuery({
    queryKey: KEYS.explicacaoVariacao(
      fundoId ?? "",
      data ?? "",
      opts?.dataAnterior ?? undefined,
      opts?.thresholdBrl,
      opts?.topN,
    ),
    queryFn: () => controladoria.cotaSubExplicacao(fundoId!, data!, {
      dataAnterior: opts?.dataAnterior ?? undefined,
      thresholdBrl: opts?.thresholdBrl,
      topN:         opts?.topN,
    }),
    enabled,
    staleTime: 5 * 60 * 1000,
  })
}

export function useCosifRows(
  fundoId: string | null | undefined,
  data: string | null | undefined,
  cosifCodigo: string | null | undefined,
) {
  // Drill-down do CosifDrillSheet — so dispara quando o user clica numa
  // conta com codigo. Bucket pendente (codigo=null) nao tem rows endpoint.
  const enabled = !!fundoId && !!data && !!cosifCodigo
  return useQuery({
    queryKey: KEYS.cosifRows(fundoId ?? "", data ?? "", cosifCodigo ?? ""),
    queryFn: () => controladoria.cotaSubBalanceteCosifRows(
      fundoId!,
      data!,
      cosifCodigo!,
    ),
    enabled,
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

/** Reports QiTech que alimentam a pagina Cota Sub. Ordem = display order. */
export const COTA_SUB_REPORTS: ReadonlyArray<{
  name:       string
  shortLabel: string
  fullLabel:  string
}> = [
  { name: "market.tesouraria",        shortLabel: "Tesouraria",  fullLabel: "Tesouraria"                },
  { name: "market.conta_corrente",    shortLabel: "Conta corr.", fullLabel: "Conta-corrente"            },
  { name: "market.rf",                shortLabel: "RF",          fullLabel: "Renda fixa"                },
  { name: "market.rf_compromissadas", shortLabel: "RF compr.",   fullLabel: "RF compromissadas"         },
  { name: "market.outros_fundos",     shortLabel: "Out. fundos", fullLabel: "Posicao em outros fundos"  },
  { name: "market.outros_ativos",     shortLabel: "Out. ativos", fullLabel: "Outros ativos"             },
  { name: "market.cpr",               shortLabel: "CPR",         fullLabel: "CPR (movimentacoes)"       },
  { name: "market.mec",               shortLabel: "MEC",         fullLabel: "MEC (evolucao cotas)"      },
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
        day:        byName.get(r.name),
      }),
    )
  }, [cov.data, data])

  const allReady = entries.every(isCoverageStripEntryHealthy)
  const blocking = entries.filter((e) => !isCoverageStripEntryHealthy(e))

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
