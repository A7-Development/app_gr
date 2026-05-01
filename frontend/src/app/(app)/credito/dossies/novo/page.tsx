// src/app/(app)/credito/dossies/novo/page.tsx
//
// Wizard MINIMO de criacao de dossiê.
//
// Filosofia (Bloco F.4): o que o analista digita aqui e SO o necessario
// para criar o dossie e disparar o workflow run. Tudo o resto (cadastro
// completo da empresa, sócios, pleito, etc) sai pelos human_input nodes
// do workflow ATIVO.
//
// Campos:
//   - target_cnpj  (com mascara)
//   - target_name  (razao social)
//   - notes (opcional, livre)
//   - workflow: pre-selecionado com o ATIVO do tenant; "Trocar" para
//     mudar manualmente. 99% dos analistas nao precisa abrir.

"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { useMutation, useQuery } from "@tanstack/react-query"
import {
  RiArrowLeftLine,
  RiCheckLine,
  RiFlowChart,
  RiShieldStarLine,
} from "@remixicon/react"
import { toast } from "sonner"

import { Badge } from "@/components/tremor/Badge"
import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
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
import { PageHeader } from "@/design-system/components"
import { cardTokens } from "@/design-system/tokens/card"
import { cx } from "@/lib/utils"
import {
  credito,
  type DossierCreatePayload,
  type WorkflowDefinitionRead,
} from "@/lib/credito-client"

// CNPJ mask helper (mesma logica do DynamicForm).
function maskCnpj(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 14)
  if (digits.length <= 2) return digits
  if (digits.length <= 5) return `${digits.slice(0, 2)}.${digits.slice(2)}`
  if (digits.length <= 8)
    return `${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5)}`
  if (digits.length <= 12)
    return `${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5, 8)}/${digits.slice(8)}`
  return `${digits.slice(0, 2)}.${digits.slice(2, 5)}.${digits.slice(5, 8)}/${digits.slice(8, 12)}-${digits.slice(12, 14)}`
}

const DEFAULT_WORKFLOW_NAME = "credit.a7_standard"

export default function NovoDossiePage() {
  const router = useRouter()

  // Fetch active workflow as default. Falls back to listing if no active.
  const { data: activeWorkflow, isLoading: loadingActive } = useQuery({
    queryKey: ["credito", "workflow-active", DEFAULT_WORKFLOW_NAME],
    queryFn: () => credito.workflows.getActive(DEFAULT_WORKFLOW_NAME),
    retry: false,
  })

  const { data: allWorkflows } = useQuery({
    queryKey: ["credito", "workflows"],
    queryFn: () => credito.workflows.list(),
  })

  const [cnpj, setCnpj] = React.useState("")
  const [name, setName] = React.useState("")
  const [notes, setNotes] = React.useState("")
  const [workflowId, setWorkflowId] = React.useState<string>("")
  const [showWorkflowPicker, setShowWorkflowPicker] = React.useState(false)

  // Auto-select active workflow when it loads.
  React.useEffect(() => {
    if (!workflowId && activeWorkflow) {
      setWorkflowId(activeWorkflow.id)
    } else if (
      !workflowId &&
      !loadingActive &&
      allWorkflows &&
      allWorkflows.length > 0
    ) {
      // Fallback: first available.
      setWorkflowId(allWorkflows[0].id)
    }
  }, [activeWorkflow, allWorkflows, loadingActive, workflowId])

  const createMutation = useMutation({
    mutationFn: (payload: DossierCreatePayload) => credito.dossies.create(payload),
    onSuccess: (created) => {
      toast.success("Dossie criado. Workflow iniciado.")
      router.push(`/credito/dossies/${created.id}`)
    },
    onError: (err) => {
      toast.error(`Erro ao criar dossie: ${(err as Error).message}`)
    },
  })

  const canSubmit =
    cnpj.replace(/\D/g, "").length === 14 &&
    name.trim().length > 0 &&
    workflowId.length > 0

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    createMutation.mutate({
      target_cnpj: cnpj,
      target_name: name.trim(),
      workflow_definition_id: workflowId,
      notes: notes.trim() || null,
    })
  }

  const selectedWorkflow: WorkflowDefinitionRead | undefined =
    allWorkflows?.find((w) => w.id === workflowId) ?? activeWorkflow ?? undefined

  return (
    <div className="flex flex-col gap-6 px-12 py-6 pb-28">
      <PageHeader
        title="Novo dossie de credito"
        subtitle="Identifique a empresa-alvo. O workflow vai cuidar do resto."
        actions={
          <Button variant="ghost" onClick={() => router.back()}>
            <RiArrowLeftLine className="size-4" aria-hidden />
            Voltar
          </Button>
        }
      />

      <form onSubmit={handleSubmit} className="flex flex-col gap-6">
        {/* Step 1: Empresa */}
        <Card>
          <div className={cx(cardTokens.bodyComfortable, "space-y-4")}>
            <div>
              <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                Empresa-alvo
              </h3>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                Apenas o suficiente para criar o dossie. Cadastro completo
                vem no primeiro passo do workflow.
              </p>
            </div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <div>
                <Label htmlFor="cnpj">CNPJ</Label>
                <Input
                  id="cnpj"
                  placeholder="00.000.000/0000-00"
                  value={cnpj}
                  onChange={(e) => setCnpj(maskCnpj(e.target.value))}
                  maxLength={18}
                  required
                />
              </div>
              <div>
                <Label htmlFor="name">Razao social</Label>
                <Input
                  id="name"
                  placeholder="Nome da empresa"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </div>
            </div>
            <div>
              <Label htmlFor="notes">Notas iniciais (opcional)</Label>
              <Textarea
                id="notes"
                rows={2}
                placeholder="Anotacoes do analista, contexto inicial recebido do comercial..."
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </div>
          </div>
        </Card>

        {/* Step 2: Workflow (collapsible) */}
        <Card>
          <div className={cx(cardTokens.bodyComfortable, "space-y-3")}>
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0 flex-1">
                <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                  Workflow
                </h3>
                {selectedWorkflow ? (
                  <div className="mt-1 flex items-center gap-2">
                    <RiFlowChart
                      className="size-4 text-gray-500 dark:text-gray-400"
                      aria-hidden
                    />
                    <span className="text-sm text-gray-900 dark:text-gray-100">
                      {selectedWorkflow.name}
                    </span>
                    <span className="text-xs text-gray-500 dark:text-gray-400">
                      v{selectedWorkflow.version}
                    </span>
                    {selectedWorkflow.id === activeWorkflow?.id && (
                      <Badge variant="success">
                        <RiShieldStarLine className="size-3" aria-hidden />
                        ATIVO
                      </Badge>
                    )}
                  </div>
                ) : (
                  <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                    Carregando...
                  </p>
                )}
              </div>
              <Button
                type="button"
                variant="ghost"
                onClick={() => setShowWorkflowPicker(!showWorkflowPicker)}
              >
                {showWorkflowPicker ? "Ocultar" : "Trocar"}
              </Button>
            </div>

            {showWorkflowPicker && (
              <div>
                <Label htmlFor="wf">Selecione o workflow</Label>
                <Select value={workflowId} onValueChange={setWorkflowId}>
                  <SelectTrigger id="wf" className="w-full">
                    <SelectValue placeholder="Selecione" />
                  </SelectTrigger>
                  <SelectContent>
                    {allWorkflows?.map((wf) => (
                      <SelectItem key={wf.id} value={wf.id}>
                        {wf.name} v{wf.version}
                        {wf.id === activeWorkflow?.id ? " (ativo)" : ""}
                        {wf.tenant_id === null ? " — Strata" : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>
        </Card>

        {/* Submit */}
        <div className="flex items-center justify-end gap-3">
          <Button type="button" variant="secondary" onClick={() => router.back()}>
            Cancelar
          </Button>
          <Button
            type="submit"
            disabled={!canSubmit || createMutation.isPending}
            isLoading={createMutation.isPending}
          >
            <RiCheckLine className="size-4" aria-hidden />
            Criar dossie e iniciar workflow
          </Button>
        </div>
      </form>
    </div>
  )
}
