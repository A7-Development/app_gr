"use client"

import * as React from "react"

import { Badge, type BadgeProps } from "@/components/tremor/Badge"
import { Tooltip } from "@/components/tremor/Tooltip"
import { StrataIcon } from "@/design-system/components/StrataIcon"
import { cx } from "@/lib/utils"

/**
 * StrataConclusaoBadge — badge para conclusoes DERIVADAS pelo Strata.
 *
 * Convencao (decisao 2026-06-10): toda conclusao que o sistema deriva por
 * conta propria (nao vem do ERP nem de bureau) leva a marquinha Strata +
 * sufixo "· Strata", com a proveniencia completa (fator + regra versionada
 * + trust) no tooltip — §14.3 explicabilidade. O sistema e canonico sobre
 * os sistemas de origem; a marquinha diz "essa leitura e nossa".
 *
 * Primeiro uso: "Possível Liminar" (regra serasa_liminar_v1).
 * Reutilizavel para futuras conclusoes derivadas (score hibrido, flags de
 * risco, anomalias).
 */
type StrataConclusaoBadgeProps = {
  /** Texto curto da conclusao (ex.: "Possível Liminar"). */
  label: string
  /** Proveniencia: fator que disparou + regra versionada + trust + data. */
  tooltip: React.ReactNode
  variant?: BadgeProps["variant"]
  className?: string
}

export function StrataConclusaoBadge({
  label,
  tooltip,
  variant = "warning",
  className,
}: StrataConclusaoBadgeProps) {
  return (
    <Tooltip content={tooltip} className="max-w-xs">
      <span className={cx("inline-flex cursor-help", className)}>
        <Badge variant={variant} className="gap-1">
          <StrataIcon height={10} />
          {label}
          <span className="opacity-60">· Strata</span>
        </Badge>
      </span>
    </Tooltip>
  )
}
