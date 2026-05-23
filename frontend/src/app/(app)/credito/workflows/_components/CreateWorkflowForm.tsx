// src/app/(app)/credito/workflows/_components/CreateWorkflowForm.tsx
//
// Form de criacao de playbook — usado dentro do <DrillDownSheet> da
// listagem `/credito/workflows`.
//
// Dois modos:
//   (a) "empty" — playbook minimo (so trigger + output, sem edge); usuario
//       monta o resto arrastando da palette no editor.
//   (b) "clone" — copia o graph (nodes + edges) de um playbook existente
//       (template Strata ou outro do tenant). Usuario ajusta no editor.
//
// O caller (page.tsx) e responsavel por `handleSubmit` (mutation) e
// `onCancel` (fechar drawer).

"use client"

import * as React from "react"

import { Button } from "@/components/tremor/Button"
import { Divider } from "@/components/tremor/Divider"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import { Textarea } from "@/components/tremor/Textarea"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"
import type {
  WorkflowCreatePayload,
  WorkflowDefinitionRead,
} from "@/lib/credito-client"

// Empty graph: trigger + output, sem edge — usuario conecta no editor.
const EMPTY_GRAPH = {
  nodes: [
    {
      id: "trigger",
      type: "trigger",
      label: "Inicio",
      config: { kind: "manual" },
      position: { x: 80, y: 60 },
    },
    {
      id: "output",
      type: "output_generator",
      label: "Output",
      config: { format: "pdf" },
      position: { x: 80, y: 240 },
    },
  ],
  edges: [],
}

export type CreateWorkflowFormProps = {
  /** Lista de workflows disponiveis para clonagem (templates Strata + tenant). */
  templates: WorkflowDefinitionRead[]
  /** Callback chamado com o payload pronto pra criar. */
  onSubmit: (payload: WorkflowCreatePayload) => void
  onCancel: () => void
  /** True enquanto a mutation esta em execucao. */
  submitting: boolean
}

export function CreateWorkflowForm({
  templates,
  onSubmit,
  onCancel,
  submitting,
}: CreateWorkflowFormProps) {
  const [mode, setMode] = React.useState<"empty" | "clone">("clone")
  const [name, setName] = React.useState("")
  const [description, setDescription] = React.useState("")
  const [cloneFromId, setCloneFromId] = React.useState<string>("")

  // Pre-select primeiro template Strata se existir; senao, primeiro disponivel.
  React.useEffect(() => {
    const starter = templates.find((t) => t.tenant_id === null)
    setCloneFromId(starter?.id ?? templates[0]?.id ?? "")
    setMode(starter ? "clone" : "empty")
  }, [templates])

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return
    if (mode === "clone") {
      if (!cloneFromId) return
      onSubmit({
        name: name.trim(),
        description: description.trim() || null,
        clone_from: cloneFromId,
      })
    } else {
      onSubmit({
        name: name.trim(),
        description: description.trim() || null,
        category: "credit",
        graph: EMPTY_GRAPH,
      })
    }
  }

  const canSubmit =
    name.trim().length > 0 && (mode === "empty" || (mode === "clone" && Boolean(cloneFromId)))

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-6" noValidate>
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
          Novo workflow
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Comece do zero ou clone um template existente. Voce vai poder editar
          o graph no editor visual em seguida.
        </p>
      </div>

      <Divider />

      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="wf-name">
            Nome <span className="ml-1 text-red-600 dark:text-red-500" aria-hidden>*</span>
          </Label>
          <Input
            id="wf-name"
            placeholder="credit.meu_processo"
            value={name}
            onChange={(e) => setName(e.target.value)}
            autoFocus
            required
          />
          <p className={cx(tableTokens.cellSecondary, "mt-1")}>
            Convencao: <code>credit.&lt;slug&gt;</code> (ex: credit.express, credit.high_risk)
          </p>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="wf-desc">Descricao</Label>
          <Textarea
            id="wf-desc"
            rows={2}
            placeholder="Para que serve este playbook"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
      </div>

      <Divider />

      <fieldset className="flex flex-col gap-2">
        <legend className="text-xs font-medium text-gray-700 dark:text-gray-300">
          Como comecar
        </legend>

        <label className="flex cursor-pointer items-start gap-2 rounded-md border border-gray-200 p-3 dark:border-gray-800">
          <input
            type="radio"
            name="mode"
            value="clone"
            checked={mode === "clone"}
            onChange={() => setMode("clone")}
            className="mt-0.5"
          />
          <div className="flex-1">
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
              Clonar de um template
            </p>
            <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
              Copia o graph (nos + edges) de um playbook existente. Voce
              ajusta no editor.
            </p>
            {mode === "clone" && (
              <div className="mt-2">
                <Select value={cloneFromId} onValueChange={setCloneFromId}>
                  <SelectTrigger className="w-full">
                    <SelectValue placeholder="Selecione o template" />
                  </SelectTrigger>
                  <SelectContent>
                    {templates.map((t) => (
                      <SelectItem key={t.id} value={t.id}>
                        {t.name} v{t.version}
                        {t.tenant_id === null ? " (Strata template)" : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
        </label>

        <label className="flex cursor-pointer items-start gap-2 rounded-md border border-gray-200 p-3 dark:border-gray-800">
          <input
            type="radio"
            name="mode"
            value="empty"
            checked={mode === "empty"}
            onChange={() => setMode("empty")}
            className="mt-0.5"
          />
          <div className="flex-1">
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
              Comecar do zero
            </p>
            <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
              Workflow minimo (Trigger + Output, sem edges) — voce monta o
              resto arrastando da palette no editor.
            </p>
          </div>
        </label>
      </fieldset>

      <Divider />

      <div className="flex items-center justify-end gap-2">
        <Button
          type="button"
          variant="secondary"
          onClick={onCancel}
          disabled={submitting}
        >
          Cancelar
        </Button>
        <Button
          type="submit"
          variant="primary"
          isLoading={submitting}
          disabled={!canSubmit || submitting}
        >
          Criar e abrir editor
        </Button>
      </div>
    </form>
  )
}
