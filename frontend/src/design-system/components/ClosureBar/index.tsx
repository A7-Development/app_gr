// src/design-system/components/ClosureBar/index.tsx
//
// Barra de fechamento da estação (handoff Conceito D, frame D1b).
// Sticky no rodapé do workbench, sombra para cima. Salvar ≠ fechar:
// o rascunho é contínuo e automático; esta barra só trata o FECHAMENTO.
//
// 3 estados:
//   pending  — pendências SUAS: primária disabled + texto âmbar "falta: …"
//   armed    — tudo resolvido: card ganha borda azul; a primária diz o
//              destino calculado ("Fechar e seguir → Estação 3 · …")
//   external — pendência externa (cedente, fonte fora do ar):
//              "Fechar com ressalva" (primary) + "Deixar em espera" (ghost)

"use client"

import * as React from "react"
import {
  RiCheckboxCircleFill,
  RiCheckDoubleLine,
  RiErrorWarningLine,
  RiSaveLine,
  RiTimeLine,
  type RemixiconComponentType,
} from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { cx } from "@/lib/utils"

export type ClosureBarState = "pending" | "armed" | "external"

export type ClosureBarProps = {
  state: ClosureBarState
  /** Texto à esquerda (ex.: "Rascunho salvo automaticamente às 09:04 — nada se perde se você sair."). */
  statusText: React.ReactNode
  /** Pendências (estado pending): "falta: confirmar Nov/25 · decidir sobre a leitura". */
  pendingText?: React.ReactNode
  /** Rótulo da primária. Default por estado. */
  primaryLabel?: React.ReactNode
  primaryIcon?: RemixiconComponentType
  onPrimary?: () => void
  primaryLoading?: boolean
  /** Força disabled mesmo em armed (ex.: validação local pendente). */
  primaryDisabled?: boolean
  /** Slot à direita, antes da primária (menu ···, ghost de espera). */
  secondary?: React.ReactNode
  /** Ícone/linha à esquerda muda por contexto (ex.: ri-archive-drawer-line no D3). */
  statusIcon?: RemixiconComponentType
  className?: string
}

export function ClosureBar({
  state,
  statusText,
  pendingText,
  primaryLabel,
  primaryIcon,
  onPrimary,
  primaryLoading,
  primaryDisabled,
  secondary,
  statusIcon,
  className,
}: ClosureBarProps) {
  const StatusIcon =
    statusIcon ??
    (state === "armed"
      ? RiCheckboxCircleFill
      : state === "external"
        ? RiTimeLine
        : RiSaveLine)

  const PrimaryIcon = primaryIcon ?? RiCheckDoubleLine

  const defaultLabel =
    state === "external" ? "Fechar com ressalva" : "Fechar estação"

  return (
    <div
      className={cx(
        "sticky bottom-0 z-10 flex flex-wrap items-center gap-x-4 gap-y-2 border-t bg-white px-8 py-3.5 dark:bg-gray-950",
        state === "armed"
          ? "border-blue-500"
          : "border-gray-200 dark:border-gray-800",
        className,
      )}
      style={{ boxShadow: "0 -2px 4px rgba(0,0,0,0.04)" }}
    >
      <span
        className={cx(
          "flex min-w-0 items-center gap-2 text-[13px]",
          state === "armed"
            ? "text-gray-700 dark:text-gray-300"
            : state === "external"
              ? "text-gray-500 dark:text-gray-400"
              : "text-gray-500 dark:text-gray-400",
        )}
      >
        <StatusIcon
          className={cx(
            "size-4 shrink-0",
            state === "armed"
              ? "text-emerald-600"
              : state === "external"
                ? "text-amber-600"
                : "text-gray-400",
          )}
          aria-hidden
        />
        <span className="min-w-0">{statusText}</span>
      </span>

      <div className="ml-auto flex shrink-0 items-center gap-2.5">
        {state === "pending" && pendingText && (
          <span className="flex items-center gap-1.5 text-xs text-amber-600 dark:text-amber-500">
            <RiErrorWarningLine className="size-3.5 shrink-0" aria-hidden />
            {pendingText}
          </span>
        )}
        {secondary}
        {onPrimary && (
          <Button
            onClick={onPrimary}
            disabled={state === "pending" || primaryDisabled}
            isLoading={primaryLoading}
            className="h-9"
          >
            <PrimaryIcon className="mr-1.5 size-4" aria-hidden />
            {primaryLabel ?? defaultLabel}
          </Button>
        )}
      </div>
    </div>
  )
}
