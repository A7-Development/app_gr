"use client"

//
// PromptInstructionsField — Fatia A do cockpit de agente.
//
// Mostra (e permite editar) o system_text do prompt selecionado SEM sair da
// tela do agente. O prompt e um cadastro COMPARTILHADO (varios agentes podem
// apontar pro mesmo `name`), entao:
//   - exibimos quantos agentes usam o prompt (usage_count, vindo do backend);
//   - editar cria NOVA versao (ai_prompt e imutavel) e a ativa — afetando
//     todos os agentes que usam o nome. Quando usage_count > 1, exigimos uma
//     confirmacao explicita antes de salvar.
//
// O texto editado vive em /admin/ia/prompts (fonte de verdade). Aqui e so um
// atalho de leitura/curadoria embutido no editor do agente.
//

import * as React from "react"
import Link from "next/link"
import { useWatch } from "react-hook-form"
import {
  RiAlertLine,
  RiArrowRightUpLine,
  RiCheckLine,
  RiFileTextLine,
  RiLoader4Line,
  RiPencilLine,
} from "@remixicon/react"

import { Badge } from "@/components/tremor/Badge"
import { Button } from "@/components/tremor/Button"
import { Label } from "@/components/tremor/Label"
import { Textarea } from "@/components/tremor/Textarea"
import {
  useActivatePromptVersion,
  usePromptDetail,
  useUpdatePrompt,
} from "@/lib/hooks/admin-ai"
import type { AIPromptVersionInfo } from "@/lib/api-client"
import { cx } from "@/lib/utils"

type PromptInstructionsFieldProps = {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  control: any
  prompts: AIPromptVersionInfo[]
}

export function PromptInstructionsField({
  control,
  prompts,
}: PromptInstructionsFieldProps) {
  const promptName = (useWatch({ control, name: "prompt_name" }) ?? "") as string

  // Versao ATIVA do prompt selecionado (o runtime usa a ativa).
  const activeRow =
    prompts.find((p) => p.name === promptName && p.is_active) ??
    prompts.find((p) => p.name === promptName) ??
    null

  const usageCount = activeRow?.usage_count ?? 0
  const detailQuery = usePromptDetail(activeRow?.id ?? null)

  const [expanded, setExpanded] = React.useState(false)
  const [editing, setEditing] = React.useState(false)
  const [draft, setDraft] = React.useState("")
  const [confirmShared, setConfirmShared] = React.useState(false)

  const updateMut = useUpdatePrompt()
  const activateMut = useActivatePromptVersion()
  const saving = updateMut.isPending || activateMut.isPending

  const systemText = detailQuery.data?.system_text ?? ""

  // Sai do modo edicao se o prompt selecionado mudar.
  React.useEffect(() => {
    setEditing(false)
    setConfirmShared(false)
  }, [activeRow?.id])

  function startEdit() {
    setDraft(systemText)
    setConfirmShared(false)
    setEditing(true)
    setExpanded(true)
  }

  async function save() {
    if (!activeRow) return
    const created = await updateMut.mutateAsync({
      id: activeRow.id,
      payload: { system_text: draft },
    })
    // Promove a nova versao para ativa — senao o agente continua na antiga.
    await activateMut.mutateAsync({ name: activeRow.name, versionId: created.id })
    setEditing(false)
  }

  if (!promptName) {
    return (
      <div className="rounded-md border border-dashed border-gray-200 p-3 text-[12px] text-gray-500 dark:border-gray-800 dark:text-gray-400">
        Selecione um prompt acima para ver e editar as instrucoes aqui.
      </div>
    )
  }

  const dirty = editing && draft.trim() !== systemText.trim()
  const blockedByConfirm = usageCount > 1 && !confirmShared
  const isStale = !activeRow?.is_active

  return (
    <div className="flex flex-col gap-2 rounded-md border border-gray-200 p-3 dark:border-gray-800">
      {/* Cabecalho: titulo + uso + deep-link */}
      <div className="flex flex-wrap items-center gap-2">
        <Label className="flex items-center gap-1.5 text-[13px]">
          <RiFileTextLine className="size-3.5 text-gray-500" aria-hidden />
          Instrucoes (system prompt)
        </Label>
        {usageCount > 0 && (
          <Badge variant={usageCount > 1 ? "warning" : "neutral"}>
            usado por {usageCount} agente{usageCount > 1 ? "s" : ""}
          </Badge>
        )}
        {activeRow && (
          <span className="font-mono text-[11px] text-gray-500 dark:text-gray-400">
            {activeRow.name}@{activeRow.version}
          </span>
        )}
        <Link
          href="/admin/ia/prompts"
          className="ml-auto flex items-center gap-0.5 text-[11px] font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400"
        >
          abrir em /admin/ia/prompts
          <RiArrowRightUpLine className="size-3" aria-hidden />
        </Link>
      </div>

      {/* Loading do detalhe */}
      {detailQuery.isLoading ? (
        <div className="flex items-center gap-1.5 text-[12px] text-gray-500">
          <RiLoader4Line className="size-3.5 animate-spin" aria-hidden />
          Carregando instrucoes...
        </div>
      ) : !expanded ? (
        <button
          type="button"
          onClick={() => setExpanded(true)}
          className="self-start text-[12px] font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400"
        >
          Ver instrucoes
        </button>
      ) : editing ? (
        // ── Modo edicao ──────────────────────────────────────────────────
        <div className="flex flex-col gap-2">
          <Textarea
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={12}
            className="font-mono text-[12px]"
          />
          {usageCount > 1 && (
            <label
              className={cx(
                "flex items-start gap-2 rounded-md border p-2 text-[12px] cursor-pointer",
                "border-amber-200 bg-amber-50 text-amber-900",
                "dark:border-amber-900/50 dark:bg-amber-500/10 dark:text-amber-200",
              )}
            >
              <input
                type="checkbox"
                checked={confirmShared}
                onChange={(e) => setConfirmShared(e.target.checked)}
                className="mt-0.5 size-4 rounded border-amber-300"
              />
              <span className="flex items-start gap-1.5">
                <RiAlertLine className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                <span>
                  Este prompt e compartilhado por <b>{usageCount} agentes</b>.
                  Salvar cria uma nova versao e a ativa — <b>afeta todos eles</b>.
                  Marque para confirmar.
                </span>
              </span>
            </label>
          )}
          <div className="flex items-center justify-end gap-2">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setEditing(false)}
              disabled={saving}
            >
              Cancelar
            </Button>
            <Button
              type="button"
              onClick={save}
              disabled={saving || !dirty || blockedByConfirm}
            >
              {saving && (
                <RiLoader4Line className="mr-1.5 size-4 animate-spin" aria-hidden />
              )}
              Salvar nova versao + ativar
            </Button>
          </div>
        </div>
      ) : (
        // ── Modo leitura ─────────────────────────────────────────────────
        <div className="flex flex-col gap-2">
          {isStale && (
            <span className="flex items-center gap-1 text-[11px] text-amber-600 dark:text-amber-400">
              <RiAlertLine className="size-3" aria-hidden />
              Mostrando a versao mais recente — nenhuma versao deste prompt
              esta marcada como ativa.
            </span>
          )}
          <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded bg-gray-50 p-2.5 font-mono text-[12px] leading-relaxed text-gray-800 dark:bg-gray-900 dark:text-gray-200">
            {systemText || "(vazio)"}
          </pre>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              variant="secondary"
              onClick={startEdit}
              className="text-[12px]"
            >
              <RiPencilLine className="mr-1.5 size-3.5" aria-hidden />
              Editar instrucoes inline
            </Button>
            <button
              type="button"
              onClick={() => setExpanded(false)}
              className="text-[12px] text-gray-500 hover:text-gray-700 dark:hover:text-gray-300"
            >
              recolher
            </button>
            {(updateMut.isSuccess || activateMut.isSuccess) && (
              <span className="flex items-center gap-1 text-[11px] text-emerald-600 dark:text-emerald-400">
                <RiCheckLine className="size-3.5" aria-hidden />
                Nova versao ativada.
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
