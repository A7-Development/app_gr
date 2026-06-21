"use client"

//
// Tab "Historico" — lista runs recentes do adapter (decision_log).
// Modo master-detail canonico: <ExpandableTable> (handoff "Tabela canonica").
// Cada linha expande mostrando explanation + JSON do output.
//

import * as React from "react"
import { format } from "date-fns"
import { ptBR } from "date-fns/locale"
import { RiHistoryLine } from "@remixicon/react"

import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { ExpandableTable, type ExpandableColumn } from "@/design-system/components/ExpandableTable"
import { JsonPreview } from "@/design-system/components/JsonPreview"
import { Badge } from "@/components/tremor/Badge"
import { Button } from "@/components/tremor/Button"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"
import { useSourceRuns } from "@/lib/hooks/integracoes"
import type { RunEntry, SourceTypeId } from "@/lib/api-client"

function runDetail(run: RunEntry) {
  return (
    <div className="flex flex-col gap-3">
      {run.explanation && (
        <div className="flex flex-col gap-1">
          <span className={tableTokens.header}>Explicação</span>
          <p className="text-sm text-gray-700 dark:text-gray-300">{run.explanation}</p>
        </div>
      )}
      <div className="flex flex-col gap-1">
        <span className={tableTokens.header}>Output</span>
        <JsonPreview value={run.output ?? {}} maxHeight={400} />
      </div>
    </div>
  )
}

const columns: ExpandableColumn<RunEntry>[] = [
  {
    id: "quando",
    header: "Quando",
    cell: (run) => (
      <span className={tableTokens.cellText}>
        {format(new Date(run.occurred_at), "dd/MM/yyyy HH:mm:ss", { locale: ptBR })}
      </span>
    ),
  },
  {
    id: "triggered_by",
    header: "Disparado por",
    cell: (run) => <span className={tableTokens.cellTextMono}>{run.triggered_by}</span>,
  },
  {
    id: "adapter",
    header: "Adapter",
    cell: (run) => (
      <div className="flex flex-col">
        <span className={tableTokens.cellText}>{run.rule_or_model ?? "—"}</span>
        {run.rule_or_model_version && (
          <span className={tableTokens.cellSecondary}>{run.rule_or_model_version}</span>
        )}
      </div>
    ),
  },
  {
    id: "resumo",
    header: "Resumo",
    cell: (run) => {
      const output = run.output ?? {}
      const errors = (output.errors ?? []) as unknown[]
      const elapsed = output.elapsed_seconds as number | undefined
      const hasErrors = errors.length > 0
      return (
        <div className="flex items-center gap-2">
          <Badge variant={hasErrors ? "warning" : "success"}>
            {hasErrors ? `${errors.length} erro(s)` : "OK"}
          </Badge>
          {elapsed !== undefined && (
            <span className={tableTokens.cellSecondary}>{elapsed.toFixed(1)}s</span>
          )}
        </div>
      )
    },
  },
]

export function HistoricoTab({ sourceType }: { sourceType: SourceTypeId }) {
  const { data, isLoading, isError, refetch } = useSourceRuns(sourceType, 50)

  if (isError) {
    return (
      <ErrorState
        title="Nao foi possivel carregar o historico"
        description="Tente novamente em instantes ou verifique a API."
        action={
          <Button variant="secondary" onClick={() => refetch()}>
            Tentar novamente
          </Button>
        }
      />
    )
  }

  if (!isLoading && data && data.length === 0) {
    return (
      <EmptyState
        icon={RiHistoryLine}
        title="Nenhuma execucao registrada"
        description="Quando o adapter rodar (manual ou via scheduler), as execucoes aparecerao aqui."
      />
    )
  }

  return (
    <div className={cx("rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950")}>
      <ExpandableTable<RunEntry>
        data={data ?? []}
        columns={columns}
        renderRowDetail={runDetail}
        getRowId={(run) => run.id}
        loading={isLoading}
        skeletonRows={4}
        emptyText="Nenhuma execução registrada."
      />
    </div>
  )
}
