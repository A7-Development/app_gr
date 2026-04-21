"use client"

import * as React from "react"
import { cx } from "@/lib/utils"

type LogoVariant = "icon" | "full"

type LogoProps = {
  /**
   * - "icon" (padrao): apenas o simbolo (`public/Logo-only.png`).
   *   Usado na sidebar e em slots pequenos.
   * - "full": simbolo + wordmark (`public/logo-a7-credit.png`).
   *   Usado em telas de login, splash e afins.
   */
  variant?: LogoVariant
  className?: string
}

const SOURCES: Record<LogoVariant, string> = {
  icon: "/Logo-only.png",
  full: "/logo-a7-credit.png",
}

/**
 * Logo da marca A7 Credit.
 *
 * Renderiza uma das variantes do logo (icone ou wordmark completa).
 * Se o arquivo PNG nao estiver presente em `public/`, exibe fallback
 * text-based com as iniciais "A7".
 */
export function Logo({ variant = "icon", className }: LogoProps) {
  const [imgFailed, setImgFailed] = React.useState(false)
  const src = SOURCES[variant]
  const isIcon = variant === "icon"

  return (
    <span
      className={cx(
        "relative flex shrink-0 items-center justify-center overflow-hidden",
        isIcon
          ? "size-9 rounded bg-white ring-1 ring-gray-200 dark:bg-gray-900 dark:ring-gray-800"
          : "h-14 w-auto",
        className,
      )}
      aria-label="A7 Credit"
    >
      {imgFailed ? (
        <span
          aria-hidden="true"
          className={cx(
            "font-bold text-gray-900 dark:text-gray-50",
            isIcon ? "text-xs" : "text-lg",
          )}
        >
          A7 Credit
        </span>
      ) : (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={src}
          alt=""
          className={cx(
            "size-full object-contain",
            isIcon && "p-1",
          )}
          onError={() => setImgFailed(true)}
        />
      )}
    </span>
  )
}
