// src/design-system/components/AgentLiveStatus/index.tsx
//
// "Agente trabalhando ao vivo". Compoe o corpo de <AgentRunningView /> do
// WizardWorkspace quando step.state === "running".
//
// Layout:
//   - Header: "Analise por agente IA em curso · 0:32" (timer ticando)
//   - Timeline pequena de tools (ultimas 10 entradas: tool_use, tool_result)
//   - Stats row: tokens (in/out/cache) + custo
//   - Botoes: Cancelar (opcional) — Reprocessar fica em FailedView
//
// Fallback (sem `toolsLog`): spinner grande + mensagem contextual. Esperado
// no MVP enquanto o runtime nao popula `node_run.input_data.tools_log[]`.

"use client"

import * as React from "react"
import {
  RiArrowLeftLine,
  RiArrowRightLine,
  RiChat3Line,
  RiCloseCircleLine,
  RiErrorWarningLine,
  RiLoader4Line,
} from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

export type AgentToolLogEntry = {
  /** ISO timestamp do evento. */
  iso_at: string
  /**
   * Tipo do step. `tool_use`/`tool_result` = coreografia de ferramentas;
   * `reasoning` = texto que o modelo narrou entre tool calls (o "raciocinio
   * em voz alta"); `observation` = marcador de inicio/fim; `scratchpad` =
   * resumo interno (nao renderizado); `error` = falha.
   */
  kind: "tool_use" | "tool_result" | "reasoning" | "observation" | "scratchpad" | "error"
  /** Nome da ferramenta chamada (ex.: "ref_calc", "dossier_read"). */
  tool_name?: string | null
  /** Duracao em ms (so em tool_result). */
  duration_ms?: number | null
  /** Mensagem opcional (ex.: input/output truncado pra display, ou narrativa). */
  message?: string | null
}

export type AgentLiveStatusProps = {
  /** Label legivel do agente (ex.: "financial_analyst"). Vai pro header. */
  agentLabel?: string
  /** ISO timestamp em que o run comecou. Usado pra ticker do timer. */
  startedAt: string | null
  /** Ultimas N entradas de tool_use/tool_result. Sem isso, vai pro fallback. */
  toolsLog?: AgentToolLogEntry[]
  /** Limite de entradas exibidas (default 10). */
  maxEntries?: number
  tokensInput?: number
  tokensOutput?: number
  tokensCache?: number
  /** Custo acumulado em BRL. */
  costBrl?: number
  /** Callback do botao Cancelar. Se omitido, botao nao aparece. */
  onCancel?: () => void
  /** Mensagem contextual no fallback (ex.: "Consultando bureau · Serasa..."). */
  fallbackMessage?: string
  className?: string
}

/**
 * Renderiza estado "ao vivo" de um agente IA executando. Atualiza o timer a
 * cada 1s. Quando `toolsLog` chega, troca o fallback pelo timeline real.
 */
export function AgentLiveStatus({
  agentLabel,
  startedAt,
  toolsLog,
  maxEntries = 10,
  tokensInput,
  tokensOutput,
  tokensCache,
  costBrl,
  onCancel,
  fallbackMessage,
  className,
}: AgentLiveStatusProps) {
  const elapsed = useTimerSince(startedAt)
  const headerText = formatHeader(agentLabel, elapsed)
  const hasLog = (toolsLog?.length ?? 0) > 0

  return (
    <div className={cx("space-y-4", className)}>
      <header className="flex items-baseline justify-between gap-3">
        <p className="text-sm font-medium text-blue-700 dark:text-blue-300">
          {headerText}
        </p>
        {onCancel && (
          <Button variant="secondary" onClick={onCancel}>
            <RiCloseCircleLine className="size-4" aria-hidden />
            Cancelar
          </Button>
        )}
      </header>

      {hasLog ? (
        <ToolsTimeline entries={toolsLog ?? []} maxEntries={maxEntries} />
      ) : (
        <div className="flex flex-col items-center gap-3 py-6 text-center">
          <RiLoader4Line
            className="size-8 animate-spin text-blue-500"
            aria-hidden
          />
          <p className="text-sm text-gray-700 dark:text-gray-300">
            {fallbackMessage ?? "Agente em execucao..."}
          </p>
          <p className={tableTokens.cellSecondary}>
            Esta tela atualiza sozinha quando a etapa concluir.
          </p>
        </div>
      )}

      <Stats
        tokensInput={tokensInput}
        tokensOutput={tokensOutput}
        tokensCache={tokensCache}
        costBrl={costBrl}
      />
    </div>
  )
}

// ─── Timeline ───────────────────────────────────────────────────────────────

function ToolsTimeline({
  entries,
  maxEntries,
}: {
  entries: AgentToolLogEntry[]
  maxEntries: number
}) {
  const recent = entries.slice(-maxEntries)
  return (
    <ol
      className="relative space-y-1.5 pl-1"
      aria-label="Atividade do agente em tempo real"
    >
      {recent.map((entry, idx) => (
        <TimelineRow key={`${entry.iso_at}-${idx}`} entry={entry} />
      ))}
    </ol>
  )
}

/** Renderiza UMA entrada do trace, com tratamento por `kind`. */
function TimelineRow({ entry }: { entry: AgentToolLogEntry }) {
  // Scratchpad = resumo interno do agente (JSON truncado) — poluiria a
  // timeline. Nao renderiza.
  if (entry.kind === "scratchpad") return null

  // Reasoning = o "falando com ele mesmo". Texto que o modelo escreveu antes
  // de chamar a tool. Renderiza como pensamento (italico, quebra linha).
  if (entry.kind === "reasoning") {
    return (
      <li className="flex items-start gap-2">
        <RiChat3Line
          className="mt-0.5 size-3.5 shrink-0 text-violet-500 dark:text-violet-400"
          aria-hidden
        />
        <span className="text-xs italic leading-relaxed text-gray-700 dark:text-gray-300">
          {entry.message}
        </span>
      </li>
    )
  }

  if (entry.kind === "error") {
    return (
      <li className="flex items-start gap-2">
        <RiErrorWarningLine
          className="mt-0.5 size-3 shrink-0 text-red-500"
          aria-hidden
        />
        <span className="font-mono text-xs text-red-600 dark:text-red-400">
          {entry.message ?? "erro"}
        </span>
      </li>
    )
  }

  // Observation = marcador de inicio/fim de agente. Faint, nao compete com
  // tool calls e reasoning.
  if (entry.kind === "observation") {
    return (
      <li className="flex items-start gap-2">
        <span
          className="mt-1 size-1.5 shrink-0 rounded-full bg-gray-300 dark:bg-gray-700"
          aria-hidden
        />
        <span className="text-[11px] text-gray-400 dark:text-gray-600">
          {entry.message}
        </span>
      </li>
    )
  }

  // tool_use / tool_result
  const isUse = entry.kind === "tool_use"
  const Icon = isUse ? RiArrowRightLine : RiArrowLeftLine
  const tone = isUse
    ? "text-blue-600 dark:text-blue-400"
    : "text-gray-500 dark:text-gray-400"
  const label = isUse
    ? entry.tool_name ?? "tool"
    : `${entry.tool_name ?? "tool"}${
        entry.duration_ms != null
          ? ` · ${(entry.duration_ms / 1000).toFixed(1)}s`
          : ""
      }`
  return (
    <li className="flex items-start gap-2">
      <Icon className={cx("mt-0.5 size-3 shrink-0", tone)} aria-hidden />
      <span className={cx("font-mono text-xs", tone)}>{label}</span>
    </li>
  )
}

// ─── Stats row ──────────────────────────────────────────────────────────────

function Stats({
  tokensInput,
  tokensOutput,
  tokensCache,
  costBrl,
}: {
  tokensInput?: number
  tokensOutput?: number
  tokensCache?: number
  costBrl?: number
}) {
  const hasTokens =
    typeof tokensInput === "number" ||
    typeof tokensOutput === "number" ||
    typeof tokensCache === "number"
  const hasCost = typeof costBrl === "number" && costBrl > 0

  if (!hasTokens && !hasCost) return null

  return (
    <div
      className={cx(
        tableTokens.cellSecondary,
        "flex flex-wrap items-center gap-x-3 gap-y-1 border-t pt-3",
        "border-gray-200 dark:border-gray-800",
      )}
    >
      {hasTokens && (
        <span>
          tokens:{" "}
          <span className="tabular-nums text-gray-700 dark:text-gray-300">
            {formatTokenCount(tokensInput)}
          </span>{" "}
          in /{" "}
          <span className="tabular-nums text-gray-700 dark:text-gray-300">
            {formatTokenCount(tokensOutput)}
          </span>{" "}
          out
          {typeof tokensCache === "number" && tokensCache > 0 && (
            <>
              {" "}/ <span className="tabular-nums text-gray-700 dark:text-gray-300">
                {formatTokenCount(tokensCache)}
              </span>{" "}
              cache
            </>
          )}
        </span>
      )}
      {hasCost && (
        <>
          <span aria-hidden>·</span>
          <span>
            custo:{" "}
            <span className="tabular-nums text-gray-700 dark:text-gray-300">
              R$ {costBrl?.toFixed(4)}
            </span>
          </span>
        </>
      )}
    </div>
  )
}

// ─── Helpers ────────────────────────────────────────────────────────────────

/** Hook: seg/min decorridos desde startedAt. Atualiza a cada 1s. */
function useTimerSince(startedAt: string | null | undefined) {
  const [now, setNow] = React.useState<number>(() => Date.now())
  React.useEffect(() => {
    if (!startedAt) return
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [startedAt])
  if (!startedAt) return "0:00"
  const ts = Date.parse(startedAt)
  if (Number.isNaN(ts)) return "0:00"
  const diffSec = Math.max(0, Math.floor((now - ts) / 1000))
  const min = Math.floor(diffSec / 60)
  const sec = diffSec % 60
  return `${min}:${String(sec).padStart(2, "0")}`
}

function formatHeader(agentLabel: string | undefined, elapsed: string): string {
  const head = agentLabel
    ? `Agente ${agentLabel} em execucao`
    : "Analise por agente IA em curso"
  return `${head} · ${elapsed}`
}

function formatTokenCount(n: number | undefined): string {
  if (typeof n !== "number") return "—"
  if (n < 1000) return String(n)
  return n.toLocaleString("pt-BR")
}
