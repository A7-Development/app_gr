// src/design-system/components/WizardSideMicro/index.tsx
//
// Sidebar esquerda colapsavel do Wizard V2. Lista vertical detalhada das
// etapas do fluxo, com bullet de estado, label, meta (duracao + custo).
//
// Toggle persistido em localStorage (`wizardSideOpen`):
//   - aberta (default): w-72, mostra label + meta
//   - fechada:          w-12, mostra so o bullet (tooltip no hover)
//
// Click num item dispara onSelect(nodeId) — caller normalmente atualiza a
// URL (?step=<nodeId>), e o currentNodeId vem da URL no proximo render.

"use client"

import * as React from "react"
import {
  RiAlertLine,
  RiArrowLeftSLine,
  RiArrowRightSLine,
  RiCheckLine,
  RiErrorWarningLine,
  RiLoader4Line,
  RiPlayCircleLine,
  RiSkipForwardLine,
  type RemixiconComponentType,
} from "@remixicon/react"
import * as TooltipPrimitive from "@radix-ui/react-tooltip"

import { Card } from "@/components/tremor/Card"
import { cardTokens } from "@/design-system/tokens/card"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

export type WizardSideMicroStepState =
  | "pending"
  | "running"
  | "waiting_input"
  | "completed"
  | "failed"
  | "skipped"
  | "blocked"

export type WizardSideMicroStep = {
  id: string
  label: string
  state: WizardSideMicroStepState
  /** Tipo do node (ex.: "human_input", "specialist_agent") — usado pra tooltip. */
  nodeType?: string
  /** Duracao em ms quando completed/failed. */
  durationMs?: number | null
  /** Custo em BRL acumulado neste step. */
  costBrl?: number
  /** Mensagem de erro quando state === "failed". */
  errorDetail?: string | null
}

export type WizardSideMicroProps = {
  steps: WizardSideMicroStep[]
  currentNodeId: string | null
  onSelect: (nodeId: string) => void
  /** Chave do localStorage do toggle. Permite N wizards na pagina sem
   *  conflito de estado (default: "wizardSideOpen"). */
  storageKey?: string
  className?: string
}

const STATE_META: Record<
  WizardSideMicroStepState,
  {
    label: string
    icon: RemixiconComponentType
    bullet: string
    tone: string
  }
> = {
  pending: {
    label: "Pendente",
    icon: RiPlayCircleLine,
    bullet:
      "border-gray-300 bg-white text-gray-400 dark:border-gray-700 dark:bg-gray-950",
    tone: "text-gray-500 dark:text-gray-400",
  },
  running: {
    label: "Em execucao",
    icon: RiLoader4Line,
    bullet:
      "border-blue-500 bg-blue-50 text-blue-600 dark:border-blue-500 dark:bg-blue-500/10 dark:text-blue-300",
    tone: "text-blue-700 dark:text-blue-300",
  },
  waiting_input: {
    label: "Aguardando voce",
    icon: RiAlertLine,
    bullet:
      "border-amber-500 bg-amber-50 text-amber-700 dark:border-amber-500 dark:bg-amber-500/10 dark:text-amber-300",
    tone: "text-amber-700 dark:text-amber-300",
  },
  completed: {
    label: "Concluido",
    icon: RiCheckLine,
    bullet:
      "border-emerald-500 bg-emerald-500 text-white dark:border-emerald-500 dark:bg-emerald-500",
    tone: "text-emerald-700 dark:text-emerald-400",
  },
  failed: {
    label: "Falhou",
    icon: RiErrorWarningLine,
    bullet:
      "border-red-500 bg-red-500 text-white dark:border-red-500 dark:bg-red-500",
    tone: "text-red-700 dark:text-red-400",
  },
  skipped: {
    label: "Pulada",
    icon: RiSkipForwardLine,
    bullet:
      "border-gray-300 bg-gray-100 text-gray-400 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-600",
    tone: "text-gray-500 dark:text-gray-500",
  },
  blocked: {
    label: "Bloqueada",
    icon: RiPlayCircleLine,
    bullet:
      "border-slate-400 bg-slate-100 text-slate-500 dark:border-slate-500 dark:bg-slate-800 dark:text-slate-400",
    tone: "text-gray-500 dark:text-gray-400",
  },
}

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

/**
 * Sidebar vertical do wizard. Estado aberto/fechado persistido em
 * localStorage. Renderiza no SSR como aberta (default) — hidrata pro
 * estado salvo no useEffect.
 */
export function WizardSideMicro({
  steps,
  currentNodeId,
  onSelect,
  storageKey = "wizardSideOpen",
  className,
}: WizardSideMicroProps) {
  const [open, setOpen] = React.useState<boolean>(true)
  const [hydrated, setHydrated] = React.useState<boolean>(false)

  React.useEffect(() => {
    if (typeof window === "undefined") return
    const raw = window.localStorage.getItem(storageKey)
    if (raw === "false") setOpen(false)
    if (raw === "true") setOpen(true)
    setHydrated(true)
  }, [storageKey])

  const toggle = React.useCallback(() => {
    setOpen((prev) => {
      const next = !prev
      if (typeof window !== "undefined") {
        window.localStorage.setItem(storageKey, String(next))
      }
      return next
    })
  }, [storageKey])

  if (!open) {
    return (
      <CollapsedRail
        steps={steps}
        currentNodeId={currentNodeId}
        onSelect={onSelect}
        onToggle={toggle}
        className={className}
      />
    )
  }

  return (
    <Card className={cx("flex w-72 shrink-0 flex-col", className)}>
      <div className={cx(cardTokens.header, "flex items-center justify-between")}>
        <div>
          <p className={cardTokens.headerTitle}>Etapas</p>
          <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
            {steps.length} {steps.length === 1 ? "etapa" : "etapas"} no total
          </p>
        </div>
        {/* MOTIVO: <button> cru — toggle compacto sem texto. Button do Tremor
            traz padding que conflita com o size-7 visual canonico. */}
        <button
          type="button"
          onClick={toggle}
          className={cx(
            "inline-flex size-7 shrink-0 items-center justify-center rounded",
            "text-gray-400 hover:bg-gray-100 hover:text-gray-600",
            "dark:text-gray-500 dark:hover:bg-gray-800 dark:hover:text-gray-300",
          )}
          aria-label={hydrated ? "Recolher lista" : "Lista de etapas"}
        >
          <RiArrowLeftSLine className="size-4" aria-hidden />
        </button>
      </div>
      <ol className="relative px-4 py-4">
        {steps.map((step, idx) => {
          const meta = STATE_META[step.state]
          const Icon = meta.icon
          const isLast = idx === steps.length - 1
          const isCurrent = step.id === currentNodeId
          const subtitle = formatStepMeta(step, meta.label)
          return (
            <li
              key={step.id}
              className={cx("relative flex gap-3 pb-5", isLast && "pb-0")}
            >
              {!isLast && (
                <span
                  aria-hidden
                  className="absolute left-[14px] top-7 h-[calc(100%-12px)] w-px bg-gray-200 dark:bg-gray-800"
                />
              )}
              {/* MOTIVO: <button> cru — item de lista clicavel inteiro.
                  Button do Tremor nao da pra customizar layout interno (bullet
                  + label + meta) sem subir varios niveis de wrapper. */}
              <button
                type="button"
                onClick={() => onSelect(step.id)}
                className={cx(
                  "relative z-10 flex w-full items-start gap-3 rounded text-left",
                  "px-1.5 py-1 transition-colors",
                  isCurrent
                    ? "bg-blue-50 ring-1 ring-blue-500 dark:bg-blue-500/10"
                    : "hover:bg-gray-50 dark:hover:bg-gray-900",
                )}
                aria-current={isCurrent ? "step" : undefined}
              >
                <div
                  className={cx(
                    "flex size-7 shrink-0 items-center justify-center rounded-full border text-xs font-semibold",
                    meta.bullet,
                  )}
                  aria-hidden
                >
                  {step.state === "completed" ||
                  step.state === "failed" ||
                  step.state === "waiting_input" ? (
                    <Icon className="size-3.5" />
                  ) : step.state === "running" ? (
                    <Icon className="size-3.5 animate-spin" />
                  ) : (
                    idx + 1
                  )}
                </div>
                <div className="min-w-0 flex-1 pt-0.5">
                  <p
                    className={cx(
                      "text-sm font-medium",
                      isCurrent
                        ? "text-gray-900 dark:text-gray-50"
                        : "text-gray-700 dark:text-gray-300",
                    )}
                  >
                    {step.label}
                  </p>
                  <p className={cx("mt-0.5 text-xs", meta.tone)}>{subtitle}</p>
                  {step.errorDetail && step.state === "failed" && (
                    <p className="mt-1 text-xs text-red-600 dark:text-red-400">
                      {step.errorDetail}
                    </p>
                  )}
                </div>
              </button>
            </li>
          )
        })}
      </ol>
    </Card>
  )
}

// ─── Collapsed rail (faixa estreita) ────────────────────────────────────────

function CollapsedRail({
  steps,
  currentNodeId,
  onSelect,
  onToggle,
  className,
}: {
  steps: WizardSideMicroStep[]
  currentNodeId: string | null
  onSelect: (nodeId: string) => void
  onToggle: () => void
  className?: string
}) {
  return (
    <Card className={cx("flex w-12 shrink-0 flex-col items-center", className)}>
      {/* MOTIVO: <button> cru — toggle minimo sem texto. */}
      <button
        type="button"
        onClick={onToggle}
        className={cx(
          "inline-flex size-7 items-center justify-center rounded",
          "text-gray-400 hover:bg-gray-100 hover:text-gray-600",
          "dark:text-gray-500 dark:hover:bg-gray-800 dark:hover:text-gray-300",
          "mt-3",
        )}
        aria-label="Expandir lista de etapas"
      >
        <RiArrowRightSLine className="size-4" aria-hidden />
      </button>
      <TooltipPrimitive.Provider delayDuration={300}>
        <ol className="flex flex-col items-center gap-3 px-2 py-3">
          {steps.map((step, idx) => {
            const meta = STATE_META[step.state]
            const Icon = meta.icon
            const isCurrent = step.id === currentNodeId
            return (
              <li key={step.id}>
                <TooltipPrimitive.Root>
                  <TooltipPrimitive.Trigger asChild>
                    {/* MOTIVO: <button> cru — bullet de step. */}
                    <button
                      type="button"
                      onClick={() => onSelect(step.id)}
                      className={cx(
                        "flex size-7 items-center justify-center rounded-full border text-xs font-semibold transition-all",
                        meta.bullet,
                        isCurrent &&
                          "ring-2 ring-blue-500 ring-offset-1 ring-offset-white dark:ring-offset-gray-950",
                      )}
                      aria-label={`Etapa ${idx + 1}: ${step.label}`}
                      aria-current={isCurrent ? "step" : undefined}
                    >
                      {step.state === "completed" ||
                      step.state === "failed" ||
                      step.state === "waiting_input" ? (
                        <Icon className="size-3.5" />
                      ) : step.state === "running" ? (
                        <Icon className="size-3.5 animate-spin" />
                      ) : (
                        idx + 1
                      )}
                    </button>
                  </TooltipPrimitive.Trigger>
                  <TooltipPrimitive.Portal>
                    <TooltipPrimitive.Content
                      side="right"
                      sideOffset={8}
                      className={cx(
                        "z-50 max-w-xs rounded border px-2.5 py-1.5 text-xs shadow-lg",
                        "border-gray-200 bg-white text-gray-900",
                        "dark:border-gray-800 dark:bg-[#090E1A] dark:text-gray-50",
                      )}
                    >
                      <p className="font-medium">{step.label}</p>
                      <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
                        {meta.label}
                        {step.nodeType && NODE_TYPE_LABEL[step.nodeType] && (
                          <> · {NODE_TYPE_LABEL[step.nodeType]}</>
                        )}
                      </p>
                      <TooltipPrimitive.Arrow className="fill-gray-200 dark:fill-gray-800" />
                    </TooltipPrimitive.Content>
                  </TooltipPrimitive.Portal>
                </TooltipPrimitive.Root>
              </li>
            )
          })}
        </ol>
      </TooltipPrimitive.Provider>
    </Card>
  )
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatStepMeta(step: WizardSideMicroStep, stateLabel: string): string {
  const parts: string[] = [stateLabel]
  if (step.state === "completed" || step.state === "failed") {
    if (step.durationMs != null) {
      parts.push(`${(step.durationMs / 1000).toFixed(1)}s`)
    }
    if (step.costBrl != null && step.costBrl > 0) {
      parts.push(`R$ ${step.costBrl.toFixed(4)}`)
    }
  }
  if (step.nodeType && NODE_TYPE_LABEL[step.nodeType]) {
    parts.push(NODE_TYPE_LABEL[step.nodeType])
  }
  return parts.join(" · ")
}

