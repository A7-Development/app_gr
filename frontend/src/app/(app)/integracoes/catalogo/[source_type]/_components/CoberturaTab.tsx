"use client"

//
// Aba "Cobertura" — heatmap historico por endpoint (Fase 1 freshness, 2026-05-12).
//
// Pergunta que responde: "tenho furos de data no meu sync?"
// Cruza raw tables (wh_qitech_raw_*) com calendario ANBIMA (wh_dim_dia_util)
// pra distinguir furo real de feriado/fim-de-semana.
//

import * as React from "react"

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

import { useSourceCoverage } from "@/lib/hooks/integracoes"
import type { SourceTypeId } from "@/lib/api-client"

const RANGE_OPTIONS = [
  { value: "30", label: "Últimos 30 dias" },
  { value: "60", label: "Últimos 60 dias" },
  { value: "90", label: "Últimos 90 dias" },
  { value: "180", label: "Últimos 180 dias" },
] as const

export function CoberturaTab({
  sourceType,
  uaId,
}: {
  sourceType: SourceTypeId
  uaId: string | null
}) {
  const [rangeDays, setRangeDays] = React.useState<number>(90)
  const { data, isLoading, isError, refetch } = useSourceCoverage(
    sourceType,
    rangeDays,
    uaId,
  )

  if (isError) {
    return (
      <ErrorState
        title="Erro ao carregar cobertura"
        description="Não foi possível consultar o histórico de coleta. Tente novamente."
        action={
          <button
            type="button"
            className="text-sm text-blue-600 hover:underline"
            onClick={() => refetch()}
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

      {isLoading && (
        <div className="h-64 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
      )}

      {!isLoading && data && data.endpoints.length === 0 && (
        <EmptyState
          icon={RiInboxLine}
          title="Sem endpoints no catálogo"
          description="Esta fonte não participa do agendamento por endpoint."
        />
      )}

      {!isLoading && data && data.endpoints.length > 0 && (
        <CoverageHeatmap
          endpoints={data.endpoints}
          startDate={data.start_date}
          endDate={data.end_date}
        />
      )}
    </div>
  )
}
