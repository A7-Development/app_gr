// AnalysisCheckpoint — checkpoint humano de UMA análise (faturamento/cadastral).
//
// Mostra o trabalho do agente (view passada como children) + campo de
// observação do analista + ações: Reprocessar (re-roda o agente) e Aprovar
// (homologa e segue). Edição estruturada campo-a-campo da análise é
// fast-follow; aqui o analista homologa e registra ajustes como nota (vai
// no output do checkpoint para auditoria + contexto do parecer).

"use client"

import * as React from "react"
import { RiCheckLine, RiLoopLeftLine } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { Textarea } from "@/components/tremor/Textarea"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

export function AnalysisCheckpoint({
  title,
  description,
  children,
  onApprove,
  approving,
  onReprocess,
  reprocessing,
}: {
  title: string
  description?: string
  children: React.ReactNode
  onApprove: (notes: string) => void
  approving: boolean
  onReprocess?: () => void
  reprocessing?: boolean
}) {
  const [notes, setNotes] = React.useState("")

  return (
    <div className="space-y-4">
      <div>
        <p className="text-sm font-medium text-gray-900 dark:text-gray-50">{title}</p>
        {description && (
          <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>{description}</p>
        )}
      </div>

      {children}

      <div>
        <p className="mb-1.5 text-xs font-medium text-gray-700 dark:text-gray-300">
          Observação do analista (opcional)
        </p>
        <Textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={3}
          placeholder="Ajustes, ressalvas ou concordância com a leitura do agente…"
        />
      </div>

      <div className="flex flex-wrap items-center justify-end gap-2">
        {onReprocess && (
          <Button
            variant="secondary"
            onClick={onReprocess}
            isLoading={reprocessing}
          >
            <RiLoopLeftLine className="size-4" aria-hidden />
            Reprocessar análise
          </Button>
        )}
        <Button onClick={() => onApprove(notes)} isLoading={approving}>
          <RiCheckLine className="size-4" aria-hidden />
          Aprovar e continuar
        </Button>
      </div>
    </div>
  )
}
