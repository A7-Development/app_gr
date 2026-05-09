// src/design-system/components/WizardTopRail/index.tsx
//
// Top sticky compacto do Wizard V2 (CLAUDE.md plan §3.1):
//   - Linha 1: back + titulo + subtitle | ações (SaveIndicator + custom actions)
//   - Linha 2: barra linear de progresso (dots conectados) + meta line (X de Y +
//              custo + duracao)
//
// Esqueleto do "topo macro" do wizard hibrido. Side micro fica colapsavel
// (componente separado), workspace e right rail preenchem o resto.

"use client"

import * as React from "react"
import { RiArrowLeftLine } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

import { SaveIndicator, type SaveIndicatorState } from "../SaveIndicator"

export type WizardStepLite = {
  id: string
  /** Estado canonico que dirige o visual do dot. */
  state: "pending" | "running" | "waiting_input" | "completed" | "failed" | "skipped" | "blocked"
}

export type WizardTopRailMeta = {
  completedSteps: number
  totalSteps: number
  /** Custo acumulado em BRL (ex.: 0.82). */
  totalCostBrl?: number
  /** Duracao decorrida desde o inicio do run. Se passado, formato "12min" / "2h". */
  durationMinutes?: number | null
}

export type WizardTopRailProps = {
  dossierTitle: string
  dossierSubtitle?: string
  steps: WizardStepLite[]
  currentNodeId: string | null
  meta: WizardTopRailMeta
  saveState: SaveIndicatorState
  lastSavedAt?: string | null
  saveErrorMessage?: string | null
  /** Callback opcional de retry quando saveState === "error". */
  onSaveRetry?: () => void
  /** Slot de acoes adicionais (ex.: Exportar PDF, Cmd+I IA, Mais...). */
  actions?: React.ReactNode
  onBack?: () => void
  /** Click no dot do progress bar — navega pro step. Opcional. */
  onStepClick?: (nodeId: string) => void
  className?: string
}

/**
 * Top sticky do wizard. Largura plena; conteudo internamente alinhado
 * (sem max-w). Sticky em `top-0`.
 *
 * Cores por estado de step (consistente com STEP_STATE_META do wizard atual):
 *   pending       -> gray-300 (bg-white)
 *   running       -> blue-500 (animate-pulse)
 *   waiting_input -> amber-500
 *   completed     -> emerald-500
 *   failed        -> red-500
 *   skipped       -> gray-200
 *   blocked       -> slate-400
 */
export function WizardTopRail({
  dossierTitle,
  dossierSubtitle,
  steps,
  currentNodeId,
  meta,
  saveState,
  lastSavedAt,
  saveErrorMessage,
  onSaveRetry,
  actions,
  onBack,
  onStepClick,
  className,
}: WizardTopRailProps) {
  const metaLineParts: string[] = []
  metaLineParts.push(
    `${meta.completedSteps} de ${meta.totalSteps} ${meta.totalSteps === 1 ? "etapa" : "etapas"}`,
  )
  if (typeof meta.totalCostBrl === "number" && meta.totalCostBrl > 0) {
    metaLineParts.push(`R$ ${meta.totalCostBrl.toFixed(2)}`)
  }
  if (typeof meta.durationMinutes === "number") {
    metaLineParts.push(formatDuration(meta.durationMinutes))
  }

  return (
    <div
      className={cx(
        "sticky top-0 z-20 -mx-6 px-6 pt-3 pb-3",
        "bg-gray-50 dark:bg-gray-950",
        "border-b border-gray-200 dark:border-gray-900",
        className,
      )}
    >
      {/* Linha 1: back + titulo + acoes */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          {onBack && (
            <Button
              variant="ghost"
              className="size-7 shrink-0 p-0"
              onClick={onBack}
              aria-label="Voltar"
            >
              <RiArrowLeftLine className="size-4" aria-hidden />
            </Button>
          )}
          <div className="min-w-0">
            <h1 className="truncate text-base font-semibold text-gray-900 dark:text-gray-50">
              {dossierTitle}
            </h1>
            {dossierSubtitle && (
              <p className="truncate text-xs text-gray-500 dark:text-gray-400">
                {dossierSubtitle}
              </p>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          <SaveIndicator
            state={saveState}
            lastSavedAt={lastSavedAt}
            errorMessage={saveErrorMessage}
            onRetry={onSaveRetry}
          />
          {actions}
        </div>
      </div>

      {/* Linha 2: barra linear de progresso + meta */}
      <div className="mt-2 flex items-center gap-3">
        <ProgressDots
          steps={steps}
          currentNodeId={currentNodeId}
          onStepClick={onStepClick}
        />
        <span
          className={cx(tableTokens.cellSecondary, "shrink-0")}
          aria-live="polite"
        >
          {metaLineParts.join(" · ")}
        </span>
      </div>
    </div>
  )
}

// ─── Progress dots (uma das poucas coisas que esta camada inventa) ─────────

function ProgressDots({
  steps,
  currentNodeId,
  onStepClick,
}: {
  steps: WizardStepLite[]
  currentNodeId: string | null
  onStepClick?: (nodeId: string) => void
}) {
  if (steps.length === 0) {
    return <div className="h-1.5 flex-1" aria-hidden />
  }
  return (
    <ol
      className="flex flex-1 items-center gap-1"
      aria-label="Progresso do fluxo"
    >
      {steps.map((step, idx) => {
        const isCurrent = step.id === currentNodeId
        const dotClass = DOT_CLASS[step.state]
        const isClickable = Boolean(onStepClick)
        return (
          <li
            key={step.id}
            className={cx(
              "flex flex-1 items-center gap-1",
              idx === steps.length - 1 && "flex-initial",
            )}
          >
            {/* MOTIVO: <button> cru — Button do Tremor traz padding/border que
                quebram o visual de dot em size-2.5. Precedente: ColumnManager
                e ExportMenu em DataTable/index.tsx usam o mesmo padrao. */}
            <button
              type="button"
              onClick={isClickable ? () => onStepClick?.(step.id) : undefined}
              className={cx(
                "size-2.5 shrink-0 rounded-full border transition-all",
                dotClass,
                isCurrent && "ring-2 ring-blue-500 ring-offset-1 ring-offset-gray-50 dark:ring-offset-gray-950",
                isClickable
                  ? "cursor-pointer hover:scale-110"
                  : "cursor-default",
              )}
              aria-label={`Etapa ${idx + 1}`}
              aria-current={isCurrent ? "step" : undefined}
              tabIndex={isClickable ? 0 : -1}
              disabled={!isClickable}
            />
            {idx < steps.length - 1 && (
              <span
                aria-hidden
                className={cx(
                  "h-px flex-1",
                  step.state === "completed"
                    ? "bg-emerald-400 dark:bg-emerald-600"
                    : "bg-gray-200 dark:bg-gray-800",
                )}
              />
            )}
          </li>
        )
      })}
    </ol>
  )
}

const DOT_CLASS: Record<WizardStepLite["state"], string> = {
  pending:
    "border-gray-300 bg-white dark:border-gray-700 dark:bg-gray-950",
  running:
    "border-blue-500 bg-blue-500 animate-pulse",
  waiting_input:
    "border-amber-500 bg-amber-500",
  completed:
    "border-emerald-500 bg-emerald-500",
  failed:
    "border-red-500 bg-red-500",
  skipped:
    "border-gray-200 bg-gray-100 dark:border-gray-800 dark:bg-gray-900",
  blocked:
    "border-slate-400 bg-slate-300 dark:border-slate-500 dark:bg-slate-700",
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatDuration(minutes: number): string {
  if (minutes < 1) return "< 1min"
  if (minutes < 60) return `${Math.round(minutes)}min`
  const h = Math.floor(minutes / 60)
  const m = Math.round(minutes % 60)
  if (m === 0) return `${h}h`
  return `${h}h ${m}min`
}
