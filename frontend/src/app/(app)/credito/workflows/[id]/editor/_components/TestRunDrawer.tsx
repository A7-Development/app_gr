// src/app/(app)/credito/workflows/[id]/editor/_components/TestRunDrawer.tsx
//
// Drawer "Testar" — roda o workflow em modo SANDBOX (dry-run) sem
// chamar Serasa real, sem chamar Anthropic, sem persistir nada. Cada
// nó produz output mock baseado em produces() (Fase 2/3a).
//
// O analista digita um trigger_data JSON (ex.: {cnpj, target_name}),
// clica Rodar, e vê step-a-step:
// - ordem de execução topológica
// - status (concluído / falhou / pulado / em-breve)
// - duração sintética por tipo
// - output JSON expandível
//
// Útil pra validar wiring antes de criar dossiê real e queimar
// requisição paga de bureau.

"use client"

import * as React from "react"
import { useMutation } from "@tanstack/react-query"
import {
  RiCheckLine,
  RiCloseLine,
  RiErrorWarningLine,
  RiFlashlightLine,
  RiLoader4Line,
  RiPauseCircleLine,
  RiPlayCircleLine,
  RiSkipForwardLine,
} from "@remixicon/react"
import { toast } from "sonner"

import { Button } from "@/components/tremor/Button"
import {
  Sheet,
  SheetBody,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/design-system/primitives"
import { tableTokens } from "@/design-system/tokens/table"
import {
  credito,
  type DryRunResult,
  type DryRunStep,
} from "@/lib/credito-client"
import { cx } from "@/lib/utils"

const DEFAULT_TRIGGER_JSON = JSON.stringify(
  { cnpj: "46.802.619/0001-10", target_name: "EXEMPLO LTDA" },
  null,
  2,
)

export function TestRunDrawer({
  open,
  onOpenChange,
  workflowId,
  workflowName,
  hasUnsavedChanges,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  workflowId: string
  workflowName: string
  /** Se true, mostra warning de que dry-run usa a versão SALVA (last commit),
   *  não as mudanças no canvas. */
  hasUnsavedChanges: boolean
}) {
  const [triggerJson, setTriggerJson] = React.useState<string>(DEFAULT_TRIGGER_JSON)
  const [parseError, setParseError] = React.useState<string | null>(null)
  const [expandedSteps, setExpandedSteps] = React.useState<Set<string>>(new Set())

  const runMutation = useMutation<DryRunResult>({
    mutationFn: async () => {
      let parsed: Record<string, unknown> = {}
      try {
        parsed = JSON.parse(triggerJson || "{}") as Record<string, unknown>
      } catch (e) {
        throw new Error(`JSON inválido: ${(e as Error).message}`)
      }
      return credito.workflows.dryRun(workflowId, parsed)
    },
    onError: (e) => toast.error((e as Error).message),
    onSuccess: (data) => {
      if (data.final_status === "completed") {
        toast.success(`Dry-run concluiu: ${data.steps.length} etapas executadas.`)
      } else {
        toast.error(`Dry-run falhou em alguma etapa.`)
      }
    },
  })

  function validateJson(value: string) {
    setTriggerJson(value)
    if (!value.trim()) {
      setParseError(null)
      return
    }
    try {
      JSON.parse(value)
      setParseError(null)
    } catch (e) {
      setParseError((e as Error).message)
    }
  }

  function toggleStep(nodeId: string) {
    setExpandedSteps((prev) => {
      const next = new Set(prev)
      if (next.has(nodeId)) next.delete(nodeId)
      else next.add(nodeId)
      return next
    })
  }

  const result = runMutation.data
  const totalDuration = React.useMemo(
    () => (result?.steps ?? []).reduce((sum, s) => sum + (s.duration_ms ?? 0), 0),
    [result],
  )

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent className="sm:max-w-xl">
        <SheetHeader>
          <SheetTitle className="flex items-center gap-2">
            <RiFlashlightLine className="size-5 text-amber-500" aria-hidden />
            Testar fluxo
          </SheetTitle>
          <SheetDescription>
            Roda <span className="font-mono">{workflowName}</span> em modo
            sandbox. Não chama Serasa, não chama Anthropic, não persiste. Útil
            pra validar wiring antes de criar dossiê real.
          </SheetDescription>
        </SheetHeader>
        <SheetBody>
          {hasUnsavedChanges && (
            <div className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-200">
              Você tem mudanças não salvas. O dry-run usa a versão{" "}
              <strong>salva</strong> do fluxo. Salve antes de testar pra ver as
              mudanças refletidas.
            </div>
          )}

          <label className="mb-1 block text-xs font-medium text-gray-700 dark:text-gray-300">
            Trigger data (JSON)
          </label>
          <p className="mb-2 text-[11px] text-gray-500 dark:text-gray-400">
            O que o engine receberia em <span className="font-mono">create_dossier</span>.
            Tipicamente <span className="font-mono">cnpj</span> e{" "}
            <span className="font-mono">target_name</span>.
          </p>
          <textarea
            value={triggerJson}
            onChange={(e) => validateJson(e.target.value)}
            spellCheck={false}
            rows={6}
            className={cx(
              "w-full rounded-md border bg-white px-3 py-2 font-mono text-xs text-gray-900 focus:outline-none focus:ring-2 focus:ring-blue-500 dark:bg-gray-950 dark:text-gray-100",
              parseError
                ? "border-red-400 dark:border-red-500/50"
                : "border-gray-200 dark:border-gray-800",
            )}
          />
          {parseError && (
            <p className="mt-1 text-[11px] text-red-600 dark:text-red-400">
              {parseError}
            </p>
          )}

          <div className="mt-3 flex items-center justify-between">
            <p className={tableTokens.cellSecondary}>
              {result
                ? `Última execução: ${result.steps.length} etapas, ${formatDuration(totalDuration)}`
                : "Sem execuções ainda."}
            </p>
            <Button
              type="button"
              onClick={() => runMutation.mutate()}
              isLoading={runMutation.isPending}
              disabled={parseError !== null}
            >
              <RiPlayCircleLine className="size-4" aria-hidden />
              Rodar dry-run
            </Button>
          </div>

          <div className="mt-5">
            {runMutation.isPending && (
              <div className="flex items-center justify-center gap-2 py-8 text-sm text-gray-600 dark:text-gray-400">
                <RiLoader4Line className="size-4 animate-spin" aria-hidden />
                Executando…
              </div>
            )}

            {result && (
              <ol className="space-y-1.5">
                {result.steps.map((step, idx) => (
                  <StepRow
                    key={`${step.node_id}-${idx}`}
                    step={step}
                    expanded={expandedSteps.has(step.node_id)}
                    onToggle={() => toggleStep(step.node_id)}
                    index={idx + 1}
                  />
                ))}
              </ol>
            )}
          </div>
        </SheetBody>
      </SheetContent>
    </Sheet>
  )
}

// ─── Per-step row ────────────────────────────────────────────────────────

const STATUS_META: Record<
  DryRunStep["status"],
  { label: string; tone: string; iconClass: string; Icon: typeof RiCheckLine }
> = {
  completed: {
    label: "Concluído",
    tone: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
    iconClass: "text-emerald-500",
    Icon: RiCheckLine,
  },
  failed: {
    label: "Falhou",
    tone: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
    iconClass: "text-red-500",
    Icon: RiErrorWarningLine,
  },
  skipped: {
    label: "Pulado",
    tone: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
    iconClass: "text-gray-400",
    Icon: RiSkipForwardLine,
  },
  unavailable: {
    label: "Em breve",
    tone: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
    iconClass: "text-amber-500",
    Icon: RiPauseCircleLine,
  },
}

function StepRow({
  step,
  expanded,
  onToggle,
  index,
}: {
  step: DryRunStep
  expanded: boolean
  onToggle: () => void
  index: number
}) {
  const meta = STATUS_META[step.status]
  const Icon = meta.Icon
  const hasOutput = step.output && Object.keys(step.output).length > 0
  return (
    <li className="rounded-md border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center gap-3 px-3 py-2 text-left hover:bg-gray-50 dark:hover:bg-gray-900"
      >
        <span className="text-[10px] font-mono text-gray-400 dark:text-gray-600">
          {String(index).padStart(2, "0")}
        </span>
        <Icon className={cx("size-4 shrink-0", meta.iconClass)} aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-gray-900 dark:text-gray-100">
            {step.label}
          </p>
          <p className={cx(tableTokens.cellSecondary, "mt-0.5 font-mono text-[10px]")}>
            {step.node_id} · {step.node_type}
          </p>
        </div>
        <span className={cx(tableTokens.badge, meta.tone, "shrink-0")}>
          {meta.label}
        </span>
        <span className={cx(tableTokens.cellSecondary, "shrink-0 tabular-nums")}>
          {formatDuration(step.duration_ms)}
        </span>
        {hasOutput && (
          <RiCloseLine
            className={cx(
              "size-4 shrink-0 text-gray-400 transition-transform",
              expanded ? "rotate-0" : "rotate-45",
            )}
            aria-hidden
          />
        )}
      </button>
      {step.error && (
        <div className="border-t border-red-100 bg-red-50/50 px-3 py-1.5 text-xs text-red-700 dark:border-red-500/20 dark:bg-red-500/5 dark:text-red-300">
          {step.error}
        </div>
      )}
      {expanded && hasOutput && (
        <div className="border-t border-gray-100 px-3 py-2 dark:border-gray-900">
          <p className="mb-1 text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
            Output mock
          </p>
          <pre className="overflow-x-auto rounded bg-gray-50 p-2 font-mono text-[10px] text-gray-700 dark:bg-gray-900 dark:text-gray-300">
            {JSON.stringify(step.output, null, 2)}
          </pre>
        </div>
      )}
    </li>
  )
}

function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}
