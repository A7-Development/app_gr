// src/design-system/components/WizardWorkspace/index.tsx
//
// Container central do Wizard V2. Comuta entre 5 views baseado no
// `step.state` da etapa em foco:
//
//   "waiting_input" -> WaitingInputView (form embutido + actions sticky)
//   "running"       -> AgentRunningView (corpo do AgentLiveStatus)
//   "completed"     -> AgentCompletedView (renderer estruturado do output)
//   "failed"        -> FailedView (caixa vermelha + Reprocessar)
//   "pending"|"blocked"|"skipped" -> BlockedView (msg neutra)
//
// Sub-views sao named exports do mesmo arquivo — caller pode usar
// <WizardWorkspace step=...> que faz o switch, OU compor view por view
// se precisar de layout especial.

"use client"

import * as React from "react"
import {
  RiCheckLine,
  RiErrorWarningLine,
  RiLoader4Line,
  RiPlayCircleLine,
  RiRefreshLine,
} from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import { cardTokens } from "@/design-system/tokens/card"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

// ─── Types ─────────────────────────────────────────────────────────────────

export type WizardWorkspaceStepState =
  | "pending"
  | "running"
  | "waiting_input"
  | "completed"
  | "failed"
  | "skipped"
  | "blocked"

export type WizardWorkspaceStep = {
  id: string
  label: string
  state: WizardWorkspaceStepState
  nodeType: string
  durationMs?: number | null
  errorDetail?: string | null
  /** Output do node quando state === "completed". */
  output?: Record<string, unknown>
  /** Input data persistido pelo engine (input_data do node_run). Caller
   *  pode usar pra extrair `agent` name, `tools_log`, etc. */
  input?: Record<string, unknown>
  /** Input descriptor quando state === "waiting_input"
   *  (vem do engine — { form_id, title, description, fields, submit_label }). */
  formDescriptor?: Record<string, unknown>
}

export type WizardWorkspaceProps = {
  step: WizardWorkspaceStep | null
  /** Conteudo do form (renderizado pelo caller — passa <DynamicForm /> tipicamente). */
  renderWaitingInput?: (step: WizardWorkspaceStep) => React.ReactNode
  /** Conteudo do "agente em execucao". Caller passa <AgentLiveStatus /> com
   *  os dados especificos do node_run em curso. Se omitido, fallback simples. */
  renderRunning?: (step: WizardWorkspaceStep) => React.ReactNode
  /** Renderer estruturado do output. Caller passa <AgentOutputRenderer /> com
   *  os dados especificos. Se omitido, fallback JSON. */
  renderCompleted?: (step: WizardWorkspaceStep) => React.ReactNode
  /** Callback de "Reprocessar etapa" no FailedView. */
  onRetryStep?: (stepId: string) => void
  className?: string
}

// ─── Top-level switch ──────────────────────────────────────────────────────

export function WizardWorkspace({
  step,
  renderWaitingInput,
  renderRunning,
  renderCompleted,
  onRetryStep,
  className,
}: WizardWorkspaceProps) {
  if (!step) {
    return (
      <Card className={cx("flex flex-1 items-center justify-center", className)}>
        <p className={cx(tableTokens.cellSecondary, "py-12")}>
          Aguardando o fluxo iniciar...
        </p>
      </Card>
    )
  }

  switch (step.state) {
    case "waiting_input":
      return (
        <WaitingInputView
          step={step}
          renderForm={renderWaitingInput}
          className={className}
        />
      )
    case "running":
      return (
        <AgentRunningView
          step={step}
          renderLive={renderRunning}
          className={className}
        />
      )
    case "completed":
      return (
        <AgentCompletedView
          step={step}
          renderOutput={renderCompleted}
          className={className}
        />
      )
    case "failed":
      return (
        <FailedView
          step={step}
          onRetry={onRetryStep ? () => onRetryStep(step.id) : undefined}
          className={className}
        />
      )
    case "pending":
    case "blocked":
    case "skipped":
    default:
      return <BlockedView step={step} className={className} />
  }
}

// ─── WaitingInputView ──────────────────────────────────────────────────────

export function WaitingInputView({
  step,
  renderForm,
  className,
}: {
  step: WizardWorkspaceStep
  renderForm?: (step: WizardWorkspaceStep) => React.ReactNode
  className?: string
}) {
  const descriptor = (step.formDescriptor ?? {}) as {
    title?: string
    description?: string
  }
  const title = descriptor.title ?? step.label
  const description =
    descriptor.description ??
    "Preencha os campos abaixo para o fluxo prosseguir."

  return (
    <Card className={className}>
      <div className={cardTokens.header}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className={cardTokens.headerTitle}>{title}</p>
            <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>{description}</p>
          </div>
          <span
            className={cx(
              tableTokens.badge,
              "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
            )}
          >
            Aguardando voce
          </span>
        </div>
      </div>
      <div className={cardTokens.body}>
        {renderForm ? (
          renderForm(step)
        ) : (
          <p className={tableTokens.cellSecondary}>
            (caller deve passar `renderWaitingInput` com o DynamicForm)
          </p>
        )}
      </div>
    </Card>
  )
}

// ─── AgentRunningView ──────────────────────────────────────────────────────

export function AgentRunningView({
  step,
  renderLive,
  className,
}: {
  step: WizardWorkspaceStep
  renderLive?: (step: WizardWorkspaceStep) => React.ReactNode
  className?: string
}) {
  const message = runningMessage(step.nodeType, step.label)
  return (
    <Card className={className}>
      <div className={cardTokens.header}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className={cardTokens.headerTitle}>{step.label}</p>
            <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
              {NODE_TYPE_LABEL[step.nodeType] ?? step.nodeType}
            </p>
          </div>
          <span
            className={cx(
              tableTokens.badge,
              "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300",
            )}
          >
            Em execucao
          </span>
        </div>
      </div>
      <div className={cardTokens.body}>
        {renderLive ? (
          renderLive(step)
        ) : (
          <div className="flex flex-col items-center gap-3 py-8 text-center">
            <RiLoader4Line
              className="size-8 animate-spin text-blue-500"
              aria-hidden
            />
            <p className="text-sm text-gray-700 dark:text-gray-300">{message}</p>
            <p className={tableTokens.cellSecondary}>
              Esta tela atualiza sozinha quando a etapa concluir.
            </p>
          </div>
        )}
      </div>
    </Card>
  )
}

// ─── AgentCompletedView ────────────────────────────────────────────────────

export function AgentCompletedView({
  step,
  renderOutput,
  className,
}: {
  step: WizardWorkspaceStep
  renderOutput?: (step: WizardWorkspaceStep) => React.ReactNode
  className?: string
}) {
  const hasOutput = step.output && Object.keys(step.output).length > 0
  return (
    <Card className={className}>
      <div className={cardTokens.header}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className={cardTokens.headerTitle}>{step.label}</p>
            <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
              {NODE_TYPE_LABEL[step.nodeType] ?? step.nodeType}
              {step.durationMs != null && (
                <> · {(step.durationMs / 1000).toFixed(1)}s</>
              )}
            </p>
          </div>
          <span
            className={cx(
              tableTokens.badge,
              "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
            )}
          >
            <RiCheckLine className="mr-1 inline size-3" aria-hidden />
            Concluido
          </span>
        </div>
      </div>
      <div className={cardTokens.body}>
        {renderOutput ? (
          renderOutput(step)
        ) : hasOutput ? (
          <details className="group">
            <summary
              className={cx(
                "cursor-pointer text-xs font-medium",
                "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200",
              )}
            >
              Output bruto (JSON)
            </summary>
            <pre className="mt-2 overflow-x-auto rounded bg-gray-50 p-3 font-mono text-[11px] text-gray-700 dark:bg-gray-900 dark:text-gray-300">
              {JSON.stringify(step.output, null, 2)}
            </pre>
          </details>
        ) : (
          <p className={tableTokens.cellSecondary}>(sem output)</p>
        )}
      </div>
    </Card>
  )
}

// ─── FailedView ────────────────────────────────────────────────────────────

export function FailedView({
  step,
  onRetry,
  className,
}: {
  step: WizardWorkspaceStep
  onRetry?: () => void
  className?: string
}) {
  return (
    <Card className={className}>
      <div className={cardTokens.header}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className={cardTokens.headerTitle}>{step.label}</p>
            <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
              {NODE_TYPE_LABEL[step.nodeType] ?? step.nodeType}
            </p>
          </div>
          <span
            className={cx(
              tableTokens.badge,
              "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
            )}
          >
            <RiErrorWarningLine className="mr-1 inline size-3" aria-hidden />
            Falhou
          </span>
        </div>
      </div>
      <div className={cardTokens.body}>
        <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-900 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-200">
          <p className="font-medium">Erro nesta etapa</p>
          <p className="mt-1 font-mono text-xs">
            {step.errorDetail ?? "(sem detalhe)"}
          </p>
        </div>
        {onRetry && (
          <div className="mt-4 flex justify-end">
            <Button variant="secondary" onClick={onRetry}>
              <RiRefreshLine className="size-4" aria-hidden />
              Reprocessar etapa
            </Button>
          </div>
        )}
      </div>
    </Card>
  )
}

// ─── BlockedView ───────────────────────────────────────────────────────────

export function BlockedView({
  step,
  className,
}: {
  step: WizardWorkspaceStep
  className?: string
}) {
  const stateLabel =
    step.state === "skipped"
      ? "Pulada"
      : step.state === "blocked"
        ? "Bloqueada"
        : "Pendente"
  const description =
    step.state === "skipped"
      ? "Esta etapa foi pulada por uma decisao condicional do fluxo."
      : step.state === "blocked"
        ? "Esta etapa aguarda uma dependencia. Outra etapa precisa concluir antes."
        : "Esta etapa ainda nao foi alcancada pelo fluxo."

  return (
    <Card className={className}>
      <div className={cardTokens.header}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <p className={cardTokens.headerTitle}>{step.label}</p>
            <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
              {NODE_TYPE_LABEL[step.nodeType] ?? step.nodeType}
            </p>
          </div>
          <span
            className={cx(
              tableTokens.badge,
              "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
            )}
          >
            <RiPlayCircleLine className="mr-1 inline size-3" aria-hidden />
            {stateLabel}
          </span>
        </div>
      </div>
      <div className={cardTokens.body}>
        <p className={tableTokens.cellSecondary}>{description}</p>
      </div>
    </Card>
  )
}

// ─── Helpers compartilhados ────────────────────────────────────────────────

const NODE_TYPE_LABEL: Record<string, string> = {
  trigger: "Inicio",
  human_input: "Coleta humana",
  bureau_query: "Consulta a bureau",
  specialist_agent: "Analise por agente IA",
  document_request: "Solicitacao de documento",
  document_extractor: "Extracao de documento",
  conditional_branch: "Decisao condicional",
  human_review: "Revisao humana",
  http_request: "Requisicao HTTP",
  output_generator: "Saida final",
  notification: "Notificacao",
}

function runningMessage(type: string, label: string): string {
  switch (type) {
    case "bureau_query":
      return `Consultando bureau · ${label}...`
    case "specialist_agent":
      return `Agente analisando · ${label}...`
    case "document_extractor":
      return "Extraindo dados do documento..."
    case "http_request":
      return "Chamando servico externo..."
    case "output_generator":
      return "Gerando saida final..."
    default:
      return `Executando · ${label}...`
  }
}
