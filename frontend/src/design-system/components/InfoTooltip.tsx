"use client"

import * as React from "react"
import { RiInformationLine } from "@remixicon/react"

import { Tooltip } from "@/components/tremor/Tooltip"
import { cx } from "@/lib/utils"

type InfoTooltipProps = {
  /** Texto exibido no tooltip. */
  content: string
  /** Lado preferencial do tooltip. */
  side?: "top" | "bottom" | "left" | "right"
  /** Classe extra do icone (ex.: para ajustar tamanho). */
  className?: string
  /** Label acessivel. Default: "Mais informacoes". */
  ariaLabel?: string
}

/**
 * Icone "(i)" que revela um tooltip com texto explicativo.
 * Uso tipico: ao lado de titulos, labels ou metricas que precisam
 * de uma descricao extra sem ocupar espaco vertical.
 */
export function InfoTooltip({
  content,
  side = "top",
  className,
  ariaLabel = "Mais informacoes",
}: InfoTooltipProps) {
  return (
    <Tooltip content={content} side={side} asChild>
      <button
        type="button"
        aria-label={ariaLabel}
        className={cx(
          "inline-flex shrink-0 items-center justify-center rounded-full text-gray-400 transition-colors hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300",
          "focus:outline-hidden focus-visible:ring-2 focus-visible:ring-blue-500",
        )}
      >
        <RiInformationLine
          aria-hidden="true"
          className={cx("size-4", className)}
        />
      </button>
    </Tooltip>
  )
}
