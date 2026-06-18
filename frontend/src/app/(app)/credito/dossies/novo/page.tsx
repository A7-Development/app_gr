// src/app/(app)/credito/dossies/novo/page.tsx
//
// "Iniciar análise" — entrada minimalista do módulo Crédito.
//
// Filosofia (Fase 1): NÃO há mais "empresa-alvo" cobrada upfront. O fluxo
// escolhido é quem decide o que coletar (CNPJ, CPF, nada). O que o analista
// digita aqui é só:
//   - Qual fluxo rodar (dropdown sempre visível)
//   - Apelido livre (opcional) — só pra reconhecer essa análise na listagem
//     antes do fluxo coletar a identidade real
//   - Notas iniciais (opcional)
//
// Identidade da entidade (CNPJ, CPF, razão social, nome) emerge depois,
// quando o fluxo executa um `human_input` que coleta esses campos. Backend
// popula `dossier.target_cnpj`/`target_name` via `absorb_identity_from_human_input`.

"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { useMutation, useQuery } from "@tanstack/react-query"
import {
  RiArrowLeftLine,
  RiFlowChart,
  RiPlayLine,
} from "@remixicon/react"
import { toast } from "sonner"

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

export default function NovoAnalisePage() {
  const router = useRouter()

  const { data: allWorkflows, isLoading: loadingWorkflows } = useQuery({
    queryKey: ["credito", "workflows"],
    queryFn: () => credito.workflows.list(),
  })

  // Filtra só workflows ACTIVE (rascunho não roda).
  const usableWorkflows = React.useMemo(
    () => (allWorkflows ?? []).filter((w) => w.status === "active"),
    [allWorkflows],
  )

  const [workflowId, setWorkflowId] = React.useState<string>("")
  const [apelido, setApelido] = React.useState("")
  const [notes, setNotes] = React.useState("")

  // Pré-seleciona o primeiro workflow ativo do tenant ao carregar.
  React.useEffect(() => {
    if (!workflowId && usableWorkflows.length > 0) {
      const tenantOwned = usableWorkflows.find((w) => w.tenant_id !== null)
      setWorkflowId((tenantOwned ?? usableWorkflows[0]).id)
    }
  }, [usableWorkflows, workflowId])

  const createMutation = useMutation({
    mutationFn: (payload: DossierCreatePayload) => credito.dossies.create(payload),
    onSuccess: (created) => {
      toast.success("Análise iniciada.")
      router.push(`/credito/dossies/${created.id}`)
    },
    onError: (err) => {
      toast.error(`Erro ao iniciar análise: ${(err as Error).message}`)
    },
  })

  const canSubmit = workflowId.length > 0 && !createMutation.isPending

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    createMutation.mutate({
      workflow_definition_id: workflowId,
      target_name: apelido.trim() || null,
      notes: notes.trim() || null,
    })
  }

  const selectedWorkflow: WorkflowDefinitionRead | undefined = usableWorkflows.find(
    (w) => w.id === workflowId,
  )
  const stepCount = selectedWorkflow?.graph?.nodes?.length ?? 0

  return (
    <div className="flex flex-col gap-6 px-12 py-6 pb-28">
      <PageHeader
        title="Iniciar análise"
        subtitle="Crédito · Dossiês"
        info="O fluxo selecionado decide o que coletar (CNPJ, CPF, documentos, etc) ao longo da execução. Você não precisa preencher nada antes."
        actions={
          <Button variant="ghost" onClick={() => router.back()}>
            <RiArrowLeftLine className="size-4" aria-hidden />
            Voltar
          </Button>
        }
      />

      <form onSubmit={handleSubmit} className="flex flex-col gap-6">
        {/* Step 1: Fluxo */}
        <Card>
          <div className={cx(cardTokens.bodyComfortable, "space-y-4")}>
            <div>
              <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                Fluxo
              </h3>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                Escolha o fluxo de análise que vai conduzir essa execução.
              </p>
            </div>

            {loadingWorkflows ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Carregando fluxos disponíveis…
              </p>
            ) : usableWorkflows.length === 0 ? (
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Nenhum fluxo ativo disponível. Crie e ative um em{" "}
                <button
                  type="button"
                  className="text-blue-600 underline hover:text-blue-700 dark:text-blue-400"
                  onClick={() => router.push("/credito/workflows")}
                >
                  Workflows
                </button>
                .
              </p>
            ) : (
              <div>
                <Label htmlFor="wf">Fluxo selecionado</Label>
                <Select value={workflowId} onValueChange={setWorkflowId}>
                  <SelectTrigger id="wf" className="w-full">
                    <SelectValue placeholder="Selecione um fluxo" />
                  </SelectTrigger>
                  <SelectContent>
                    {usableWorkflows.map((wf) => (
                      <SelectItem key={wf.id} value={wf.id}>
                        {wf.name} v{wf.version}
                        {wf.tenant_id === null ? " · Strata" : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {selectedWorkflow && stepCount > 0 && (
                  <p className="mt-2 flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
                    <RiFlowChart className="size-3.5" aria-hidden />
                    {stepCount} {stepCount === 1 ? "etapa" : "etapas"} no fluxo
                  </p>
                )}
              </div>
            )}
          </div>
        </Card>

        {/* Step 2: Identificação opcional */}
        <Card>
          <div className={cx(cardTokens.bodyComfortable, "space-y-4")}>
            <div>
              <h3 className="text-base font-semibold text-gray-900 dark:text-gray-100">
                Identificação <span className="font-normal text-gray-500 dark:text-gray-400">(opcional)</span>
              </h3>
              <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
                Apelido livre só pra reconhecer essa análise na listagem antes
                do fluxo coletar identidade real.
              </p>
            </div>
            <div>
              <Label htmlFor="apelido">Apelido</Label>
              <Input
                id="apelido"
                placeholder="ACME LTDA · Locação Sala 305 · Maio/26"
                value={apelido}
                onChange={(e) => setApelido(e.target.value)}
                maxLength={255}
              />
            </div>
            <div>
              <Label htmlFor="notes">Notas iniciais</Label>
              <Textarea
                id="notes"
                rows={2}
                placeholder="Contexto recebido do comercial, urgência, restrições conhecidas…"
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
              />
            </div>
          </div>
        </Card>

        {/* Submit */}
        <div className="flex items-center justify-end gap-3">
          <Button type="button" variant="secondary" onClick={() => router.back()}>
            Cancelar
          </Button>
          <Button
            type="submit"
            disabled={!canSubmit}
            isLoading={createMutation.isPending}
          >
            <RiPlayLine className="size-4" aria-hidden />
            Iniciar análise
          </Button>
        </div>
      </form>
    </div>
  )
}
