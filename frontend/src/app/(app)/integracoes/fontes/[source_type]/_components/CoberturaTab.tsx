"use client"

//
// Aba "Cobertura" — heatmap historico por endpoint (Fase 1 freshness, 2026-05-12).
//
// Pergunta que responde: "tenho furos de data no meu sync?"
// Acao: bulk backfill com 1 click — Sub-fase 2A (2026-05-12).
//

import * as React from "react"
import { toast } from "sonner"

import { CoverageHeatmap } from "@/design-system/components/CoverageHeatmap"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import { RiInboxLine } from "@remixicon/react"

import {
  useActiveBackfills,
  useCreateBackfill,
  useSourceCoverage,
} from "@/lib/hooks/integracoes"
import type {
  BackfillJob,
  EndpointCoverage,
  Environment,
  SourceTypeId,
} from "@/lib/api-client"

import { BulkBackfillSheet } from "./BulkBackfillSheet"

const RANGE_OPTIONS = [
  { value: "30", label: "Últimos 30 dias" },
  { value: "60", label: "Últimos 60 dias" },
  { value: "90", label: "Últimos 90 dias" },
  { value: "180", label: "Últimos 180 dias" },
  { value: "365", label: "Último ano" },
  { value: "0", label: "Todo o período" },
] as const

export function CoberturaTab({
  sourceType,
  uaId,
  environment = "production",
}: {
  sourceType: SourceTypeId
  uaId: string | null
  environment?: Environment
}) {
  const [rangeDays, setRangeDays] = React.useState<number>(180)
  const [bulkEndpoint, setBulkEndpoint] = React.useState<EndpointCoverage | null>(
    null,
  )
  const [bulkOpen, setBulkOpen] = React.useState(false)

  const coverageQ = useSourceCoverage(sourceType, rangeDays, uaId)
  const activeJobsQ = useActiveBackfills(sourceType)
  const createBackfillMut = useCreateBackfill(sourceType)

  // Polling dos jobs ativos: cada job rebusca a cada 2s ate terminar.
  // useActiveBackfills (5s staleTime) cuida da lista; pra o heatmap so
  // precisamos do snapshot atualizado por endpoint.
  React.useEffect(() => {
    if (!activeJobsQ.data?.length) return
    const interval = setInterval(() => activeJobsQ.refetch(), 2000)
    return () => clearInterval(interval)
  }, [activeJobsQ])

  const activeJobByEndpoint = React.useMemo(() => {
    const map: Record<string, BackfillJob> = {}
    for (const j of activeJobsQ.data ?? []) {
      // Mantem o mais recente por endpoint
      if (
        !map[j.endpoint_name] ||
        new Date(j.created_at) > new Date(map[j.endpoint_name].created_at)
      ) {
        map[j.endpoint_name] = j
      }
    }
    return map
  }, [activeJobsQ.data])

  const handleBackfill = React.useCallback(
    async (endpointName: string, dates: string[]) => {
      try {
        const job = await createBackfillMut.mutateAsync({
          endpointName,
          payload: {
            dates,
            environment,
            unidade_administrativa_id: uaId,
          },
        })
        toast.success(
          `Backfill iniciado: ${dates.length} data${dates.length > 1 ? "s" : ""} de "${endpointName}". Worker vai processar em segundos.`,
        )
        return job
      } catch (err) {
        toast.error(
          `Falha ao iniciar backfill: ${err instanceof Error ? err.message : String(err)}`,
        )
        return null
      }
    },
    [createBackfillMut, environment, uaId],
  )

  if (coverageQ.isError) {
    return (
      <ErrorState
        title="Erro ao carregar cobertura"
        description="Não foi possível consultar o histórico de coleta. Tente novamente."
        action={
          <button
            type="button"
            className="text-sm text-blue-600 hover:underline"
            onClick={() => coverageQ.refetch()}
          >
            Tentar novamente
          </button>
        }
      />
    )
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-gray-600 dark:text-gray-400">
          Cobertura histórica por endpoint — cruza dados coletados com o
          calendário ANBIMA pra revelar furos reais.
        </p>
        <Select
          value={String(rangeDays)}
          onValueChange={(v) => setRangeDays(Number(v))}
        >
          <SelectTrigger className="w-48">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {RANGE_OPTIONS.map((r) => (
              <SelectItem key={r.value} value={r.value}>
                {r.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {coverageQ.isLoading && (
        <div className="h-64 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
      )}

      {!coverageQ.isLoading && coverageQ.data && coverageQ.data.endpoints.length === 0 && (
        <EmptyState
          icon={RiInboxLine}
          title="Sem endpoints no catálogo"
          description="Esta fonte não participa do agendamento por endpoint."
        />
      )}

      {!coverageQ.isLoading && coverageQ.data && coverageQ.data.endpoints.length > 0 && (
        <CoverageHeatmap
          endpoints={coverageQ.data.endpoints}
          startDate={coverageQ.data.start_date}
          endDate={coverageQ.data.end_date}
          onBackfill={handleBackfill}
          onBulkSync={(ep) => {
            setBulkEndpoint(ep)
            setBulkOpen(true)
          }}
          activeJobByEndpoint={activeJobByEndpoint}
        />
      )}

      <BulkBackfillSheet
        open={bulkOpen}
        onOpenChange={setBulkOpen}
        endpoint={bulkEndpoint}
        onSubmit={handleBackfill}
        isSubmitting={createBackfillMut.isPending}
      />
    </div>
  )
}
