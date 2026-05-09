// src/design-system/components/SaveIndicator/index.tsx
//
// Chip compacto que comunica o estado do auto-save granular do wizard.
// Quatro estados (alimentados pelo hook useStepDraft):
//   - "idle"    -> nada (nao ha rascunho pendente nem salvo)
//   - "saving"  -> spinner + "Salvando..."
//   - "saved"   -> check + "Salvo ha Xs" (atualiza relativo a cada 30s)
//   - "unsaved" -> alerta + "Nao salvo" (usuario digitou, debounce ainda nao
//                  rodou ou backend ainda nao respondeu)
//   - "error"   -> erro + botao "Tentar novamente"
//
// Posicao canonica: slot direito do <WizardTopRail>. Pode tambem ser embutido
// em formularios standalone que precisem dar feedback de auto-save.

"use client"

import * as React from "react"
import {
  RiAlertLine,
  RiCheckLine,
  RiErrorWarningLine,
  RiLoader4Line,
  RiRefreshLine,
} from "@remixicon/react"

import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

export type SaveIndicatorState =
  | "idle"
  | "saving"
  | "saved"
  | "unsaved"
  | "error"

export type SaveIndicatorProps = {
  state: SaveIndicatorState
  /** ISO timestamp do ultimo save bem-sucedido. Usado para o texto relativo
   *  "Salvo ha Xs". Ignorado nos demais estados. */
  lastSavedAt?: string | null
  /** Mensagem de erro a exibir em hover/tooltip quando state="error". */
  errorMessage?: string | null
  /** Callback de retry. Se omitido, o botao de retry nao aparece. */
  onRetry?: () => void
  className?: string
}

/**
 * Chip pequeno que se atualiza a cada 30s para o texto relativo "Salvo ha Xs".
 *
 * Uso tipico:
 *
 *     const { state, lastSavedAt, errorMessage, flushNow } = useStepDraft(...)
 *     <SaveIndicator
 *       state={state}
 *       lastSavedAt={lastSavedAt}
 *       errorMessage={errorMessage}
 *       onRetry={flushNow}
 *     />
 */
export function SaveIndicator({
  state,
  lastSavedAt,
  errorMessage,
  onRetry,
  className,
}: SaveIndicatorProps) {
  // Re-render leve a cada 30s para atualizar o texto relativo.
  const [, forceTick] = React.useState(0)
  React.useEffect(() => {
    if (state !== "saved") return
    const id = setInterval(() => forceTick((t) => t + 1), 30_000)
    return () => clearInterval(id)
  }, [state])

  if (state === "idle") return null

  if (state === "saving") {
    return (
      <span
        className={cx(
          tableTokens.badge,
          "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
          className,
        )}
        aria-live="polite"
      >
        <RiLoader4Line className="mr-1 inline size-3 animate-spin" aria-hidden />
        Salvando...
      </span>
    )
  }

  if (state === "saved") {
    const relative = formatRelativeShort(lastSavedAt)
    return (
      <span
        className={cx(
          tableTokens.badge,
          "bg-gray-50 text-gray-500 dark:bg-gray-900 dark:text-gray-500",
          className,
        )}
        title={lastSavedAt ?? undefined}
      >
        <RiCheckLine className="mr-1 inline size-3" aria-hidden />
        Salvo {relative}
      </span>
    )
  }

  if (state === "unsaved") {
    return (
      <span
        className={cx(
          tableTokens.badge,
          "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
          className,
        )}
        aria-live="polite"
        title="Voce digitou — aguardando o save automatico"
      >
        <RiAlertLine className="mr-1 inline size-3" aria-hidden />
        Nao salvo
      </span>
    )
  }

  // state === "error"
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5",
        className,
      )}
      role="alert"
    >
      <span
        className={cx(
          tableTokens.badge,
          "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
        )}
        title={errorMessage ?? "Falha ao salvar"}
      >
        <RiErrorWarningLine className="mr-1 inline size-3" aria-hidden />
        Erro ao salvar
      </span>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className={cx(
            "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium",
            "text-red-700 hover:bg-red-50",
            "dark:text-red-300 dark:hover:bg-red-500/10",
          )}
          aria-label="Tentar salvar novamente"
        >
          <RiRefreshLine className="size-3" aria-hidden />
          Tentar de novo
        </button>
      )}
    </span>
  )
}

// ─── Helpers ────────────────────────────────────────────────────────────────

/** "ha 3s", "ha 12min", "ha 2h", "agora" — sempre curto, pt-BR. */
function formatRelativeShort(isoTs: string | null | undefined): string {
  if (!isoTs) return "agora"
  const ts = Date.parse(isoTs)
  if (Number.isNaN(ts)) return "agora"
  const diffSec = Math.max(0, Math.floor((Date.now() - ts) / 1000))
  if (diffSec < 5) return "agora"
  if (diffSec < 60) return `ha ${diffSec}s`
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `ha ${diffMin}min`
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return `ha ${diffH}h`
  const diffD = Math.floor(diffH / 24)
  return `ha ${diffD}d`
}
