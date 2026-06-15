// JucespDocSelector — gate de seleção do contrato social na JUCESP (opção B).
//
// Renderizado quando o node official_document_fetch (mode="select") está
// WAITING_INPUT com output.phase === "select": a máquina SUGERE o documento
// mais provável (badge "sugerido") e o analista CONFIRMA qual usar — em crédito
// regulado a escolha da fonte tem que ser confirmável (§14). "Usar este" dispara
// o download + extração direto (sem modal — a lista já é a confirmação); "anexar
// manual" cai no document_request.

"use client"

import * as React from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  RiCheckLine,
  RiDownloadLine,
  RiFileTextLine,
  RiInformationLine,
  RiUploadLine,
} from "@remixicon/react"
import { toast } from "sonner"

import { Button } from "@/components/tremor/Button"
import { tableTokens } from "@/design-system/tokens/table"
import { credito } from "@/lib/credito-client"
import { cx } from "@/lib/utils"

export type JucespDocOption = {
  registro: string
  protocolo: string | null
  descricao: string
  data: string | null
  disponivel: boolean
  suggested: boolean
}

export function JucespDocSelector({
  dossierId,
  nodeId,
  options,
  onChoose,
}: {
  dossierId: string
  nodeId: string
  options: JucespDocOption[]
  /** Chamado ao clicar "Usar este" — a página marca o node como "baixando". */
  onChoose: () => void
}) {
  const qc = useQueryClient()
  const defaultReg =
    options.find((o) => o.suggested)?.registro ??
    options.find((o) => o.disponivel)?.registro ??
    options[0]?.registro ??
    null
  const [selected, setSelected] = React.useState<string | null>(defaultReg)

  const submit = useMutation({
    mutationFn: (values: Record<string, unknown>) =>
      credito.dossies.submitNodeInput(dossierId, nodeId, values),
    onSuccess: () =>
      qc.invalidateQueries({ queryKey: ["credito", "dossie-state", dossierId] }),
    onError: (e) => toast.error(`Erro ao enviar a escolha: ${(e as Error).message}`),
  })

  const chosen = options.find((o) => o.registro === selected) ?? null

  const useChosen = () => {
    if (!chosen) return
    onChoose()
    submit.mutate({
      action: "use",
      registro: chosen.registro,
      protocolo: chosen.protocolo,
      descricao: chosen.descricao,
    })
  }

  return (
    <section className="overflow-hidden rounded border border-gray-200 bg-white shadow-xs dark:border-gray-800 dark:bg-gray-950">
      <header className="border-b border-gray-100 px-5 py-3.5 dark:border-gray-900">
        <div className="flex items-center gap-1.5">
          <RiFileTextLine className="size-3.5 text-gray-400" aria-hidden />
          <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
            Contrato social · JUCESP
          </span>
        </div>
        <p className="mt-1.5 text-[13px] leading-relaxed text-gray-700 dark:text-gray-300">
          Localizamos <strong className="font-semibold">{options.length}</strong>{" "}
          documento{options.length === 1 ? "" : "s"} arquivado{options.length === 1 ? "" : "s"}.
          A máquina sugere o mais provável — confirme qual usar para a análise.
        </p>
      </header>

      <div role="radiogroup" className="divide-y divide-gray-100 dark:divide-gray-900">
        {options.map((o) => {
          const isSel = o.registro === selected
          const disabled = !o.disponivel || submit.isPending
          return (
            <button
              key={o.registro}
              type="button"
              role="radio"
              aria-checked={isSel}
              disabled={disabled}
              onClick={() => setSelected(o.registro)}
              className={cx(
                "flex w-full items-center gap-3 px-5 py-2.5 text-left transition-colors",
                isSel && "bg-blue-500/5",
                o.disponivel
                  ? "hover:bg-gray-50 dark:hover:bg-gray-900"
                  : "cursor-not-allowed opacity-50",
              )}
            >
              <span
                className={cx(
                  "flex size-4 shrink-0 items-center justify-center rounded-full border",
                  isSel
                    ? "border-blue-500 bg-blue-500"
                    : "border-gray-300 dark:border-gray-700",
                )}
                aria-hidden
              >
                {isSel && <RiCheckLine className="size-3 text-white" />}
              </span>
              <span className="min-w-0 flex-1">
                <span className="flex items-center gap-2">
                  <span className={cx(tableTokens.cellText, "truncate")}>
                    {o.descricao}
                  </span>
                  {o.suggested && (
                    <span className="inline-flex shrink-0 items-center rounded-full bg-blue-50 px-1.5 text-[10px] font-medium text-blue-700 dark:bg-blue-500/10 dark:text-blue-300">
                      sugerido
                    </span>
                  )}
                  {!o.disponivel && (
                    <span className="shrink-0 text-[10px] text-gray-400">
                      indisponível
                    </span>
                  )}
                </span>
                <span className={cx(tableTokens.cellSecondary, "mt-0.5 block")}>
                  registro {o.registro}
                  {o.data ? ` · ${o.data}` : ""}
                </span>
              </span>
            </button>
          )
        })}
      </div>

      <footer className="flex flex-wrap items-center gap-2 border-t border-gray-100 px-5 py-3 dark:border-gray-900">
        <Button
          className="h-8"
          onClick={useChosen}
          isLoading={submit.isPending}
          disabled={!chosen}
        >
          <RiDownloadLine className="mr-1.5 size-4" aria-hidden />
          Usar este documento
        </Button>
        <Button
          variant="secondary"
          className="h-8"
          onClick={() => submit.mutate({ action: "manual" })}
          disabled={submit.isPending}
        >
          <RiUploadLine className="mr-1.5 size-4" aria-hidden />
          Nenhum — anexar manualmente
        </Button>
        <span className="ml-auto hidden items-center gap-1 text-[11.5px] text-gray-400 sm:inline-flex">
          <RiInformationLine className="size-3.5" aria-hidden />
          baixa direto da fonte oficial e lê com IA
        </span>
      </footer>
    </section>
  )
}
