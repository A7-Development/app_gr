"use client"

//
// Tab "Historico" — lista runs recentes do adapter (decision_log).
//
// Expande detalhe inline ao clicar; mostra JSON do output e explanation.
//

import * as React from "react"
import { format } from "date-fns"
import { ptBR } from "date-fns/locale"
import {
  RiArrowDownSLine,
  RiArrowRightSLine,
  RiHistoryLine,
} from "@remixicon/react"

import { EmptyState } from "@/components/app/EmptyState"
import { ErrorState } from "@/components/app/ErrorState"
import { JsonPreview } from "@/components/app/JsonPreview"
import { Badge } from "@/components/tremor/Badge"
import { Button } from "@/components/tremor/Button"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRoot,
  TableRow,
} from "@/components/tremor/Table"
import { useSourceRuns } from "@/lib/hooks/integracoes"
import type { RunEntry, SourceTypeId } from "@/lib/api-client"

export function HistoricoTab({ sourceType }: { sourceType: SourceTypeId }) {
  const { data, isLoading, isError, refetch } = useSourceRuns(sourceType, 50)
  const [openId, setOpenId] = React.useState<string | null>(null)

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
    <div className="rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
      <TableRoot>
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell className="w-8" />
              <TableHeaderCell>Quando</TableHeaderCell>
              <TableHeaderCell>Disparado por</TableHeaderCell>
              <TableHeaderCell>Adapter</TableHeaderCell>
              <TableHeaderCell>Resumo</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading &&
              Array.from({ length: 4 }).map((_, i) => (
                <TableRow key={`skeleton-${i}`}>
                  <TableCell colSpan={5}>
                    <div className="h-6 w-full animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
                  </TableCell>
                </TableRow>
              ))}
            {!isLoading &&
              data?.map((run) => (
                <RunRow
                  key={run.id}
                  run={run}
                  expanded={openId === run.id}
                  onToggle={() =>
                    setOpenId((cur) => (cur === run.id ? null : run.id))
                  }
                />
              ))}
          </TableBody>
        </Table>
      </TableRoot>
    </div>
  )
}

function RunRow({
  run,
  expanded,
  onToggle,
}: {
  run: RunEntry
  expanded: boolean
  onToggle: () => void
}) {
  const output = run.output ?? {}
  const errors = (output.errors ?? []) as unknown[]
  const elapsed = output.elapsed_seconds as number | undefined
  const hasErrors = errors.length > 0

  return (
    <>
      <TableRow
        className="cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-900"
        onClick={onToggle}
      >
        <TableCell>
          {expanded ? (
            <RiArrowDownSLine
              className="size-4 text-gray-500"
              aria-hidden
            />
          ) : (
            <RiArrowRightSLine
              className="size-4 text-gray-500"
              aria-hidden
            />
          )}
        </TableCell>
        <TableCell>
          <span className="text-gray-900 dark:text-gray-50">
            {format(new Date(run.occurred_at), "dd/MM/yyyy HH:mm:ss", {
              locale: ptBR,
            })}
          </span>
        </TableCell>
        <TableCell className="font-mono text-xs">{run.triggered_by}</TableCell>
        <TableCell>
          <div className="flex flex-col">
            <span className="text-gray-900 dark:text-gray-50">
              {run.rule_or_model ?? "—"}
            </span>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {run.rule_or_model_version ?? ""}
            </span>
          </div>
        </TableCell>
        <TableCell>
          <div className="flex items-center gap-2">
            <Badge variant={hasErrors ? "warning" : "success"}>
              {hasErrors ? `${errors.length} erro(s)` : "OK"}
            </Badge>
            {elapsed !== undefined && (
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {elapsed.toFixed(1)}s
              </span>
            )}
          </div>
        </TableCell>
      </TableRow>
      {expanded && (
        <TableRow>
          <TableCell colSpan={5} className="bg-gray-50 dark:bg-gray-900/50">
            <div className="flex flex-col gap-3 py-2">
              {run.explanation && (
                <div className="flex flex-col gap-1">
                  <span className="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">
                    Explicacao
                  </span>
                  <p className="text-sm text-gray-700 dark:text-gray-300">
                    {run.explanation}
                  </p>
                </div>
              )}
              <div className="flex flex-col gap-1">
                <span className="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">
                  Output
                </span>
                <JsonPreview value={run.output ?? {}} maxHeight={400} />
              </div>
            </div>
          </TableCell>
        </TableRow>
      )}
    </>
  )
}
