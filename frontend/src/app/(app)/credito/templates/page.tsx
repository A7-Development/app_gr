// src/app/(app)/credito/templates/page.tsx
//
// Templates de extracao de documentos — por tenant.
//
// Cada tenant define os SEUS templates (ex.: "Relatorio Onboard A7"). Quando
// um documento e uploadado e o usuario seleciona um template, o
// document_extractor agent recebe `instructions` + `fields_schema` do
// template para guiar a extracao.
//
// Templates com tenant_id NULL = starter pack Strata, clonavel.

"use client"

import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  RiAddLine,
  RiDeleteBinLine,
  RiFileCopyLine,
  RiFileTextLine,
  RiPencilLine,
  RiShieldStarLine,
} from "@remixicon/react"
import { toast } from "sonner"

import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/tremor/Dialog"
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
import { filterControlClass, PageHeader } from "@/design-system/components"
import { cardTokens } from "@/design-system/tokens/card"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"
import {
  credito,
  DOCUMENT_TYPE_LABEL,
  type DocumentTemplateRead,
  type DocumentTemplateUpsertPayload,
  type DocumentType,
} from "@/lib/credito-client"

const ALL_DOC_TYPES: DocumentType[] = [
  "dre",
  "balance_sheet",
  "revenue_report",
  "indebtedness",
  "scr",
  "income_tax_pf",
  "cnh",
  "rg",
  "social_contract",
  "commercial_visit",
  "photo",
  "abc_curve",
  "other",
]

type DialogState =
  | { kind: "closed" }
  | { kind: "create" }
  | { kind: "edit"; tpl: DocumentTemplateRead }

export default function TemplatesPage() {
  const queryClient = useQueryClient()
  const [filterDocType, setFilterDocType] = React.useState<DocumentType | "all">("all")
  const [dialog, setDialog] = React.useState<DialogState>({ kind: "closed" })

  const { data: templates, isLoading } = useQuery({
    queryKey: ["credito", "templates", filterDocType],
    queryFn: () =>
      credito.templates.list(
        filterDocType === "all" ? undefined : { doc_type: filterDocType },
      ),
  })

  const createMutation = useMutation({
    mutationFn: credito.templates.create,
    onSuccess: () => {
      toast.success("Template criado.")
      queryClient.invalidateQueries({ queryKey: ["credito", "templates"] })
      setDialog({ kind: "closed" })
    },
    onError: (e) => toast.error(`Erro: ${(e as Error).message}`),
  })

  const updateMutation = useMutation({
    mutationFn: (vars: { id: string; payload: DocumentTemplateUpsertPayload }) =>
      credito.templates.update(vars.id, vars.payload),
    onSuccess: () => {
      toast.success("Template atualizado.")
      queryClient.invalidateQueries({ queryKey: ["credito", "templates"] })
      setDialog({ kind: "closed" })
    },
    onError: (e) => toast.error(`Erro: ${(e as Error).message}`),
  })

  const deleteMutation = useMutation({
    mutationFn: credito.templates.remove,
    onSuccess: () => {
      toast.success("Template removido.")
      queryClient.invalidateQueries({ queryKey: ["credito", "templates"] })
    },
    onError: (e) => toast.error(`Erro: ${(e as Error).message}`),
  })

  const cloneMutation = useMutation({
    mutationFn: credito.templates.clone,
    onSuccess: () => {
      toast.success("Template clonado para o tenant. Agora editavel.")
      queryClient.invalidateQueries({ queryKey: ["credito", "templates"] })
    },
    onError: (e) => toast.error(`Erro: ${(e as Error).message}`),
  })

  return (
    <div className="px-6 py-6">
      <PageHeader
        title="Templates de extracao"
        subtitle="Templates que guiam o agente IA na extracao de cada tipo de documento. Cada tenant define os seus."
        actions={
          <Button onClick={() => setDialog({ kind: "create" })}>
            <RiAddLine className="size-4" aria-hidden />
            Novo template
          </Button>
        }
      />

      {/* Filtro por tipo */}
      <div className="mt-4 flex items-center gap-3">
        <Label htmlFor="doc-type-filter" className="text-xs">
          Tipo:
        </Label>
        <Select
          value={filterDocType}
          onValueChange={(v) => setFilterDocType(v as DocumentType | "all")}
        >
          <SelectTrigger id="doc-type-filter" className={cx(filterControlClass, "w-72")}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Todos</SelectItem>
            {ALL_DOC_TYPES.map((dt) => (
              <SelectItem key={dt} value={dt}>
                {DOCUMENT_TYPE_LABEL[dt]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {isLoading ? (
        <p className={cx(tableTokens.cellSecondary, "mt-6")}>Carregando...</p>
      ) : !templates || templates.length === 0 ? (
        <Card className="mt-6">
          <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
            <RiFileTextLine
              className="size-10 text-gray-300 dark:text-gray-700"
              aria-hidden
            />
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
              Nenhum template
            </p>
            <p className={cx(tableTokens.cellSecondary, "max-w-md")}>
              Sem templates, a IA extrai os documentos em modo livre. Adicione
              templates para guiar a extracao com campos esperados e instrucoes
              especificas do seu processo.
            </p>
            <Button onClick={() => setDialog({ kind: "create" })}>
              <RiAddLine className="size-4" aria-hidden />
              Criar primeiro template
            </Button>
          </div>
        </Card>
      ) : (
        <div className="mt-6 grid grid-cols-1 gap-4 md:grid-cols-2">
          {templates.map((tpl) => (
            <TemplateCard
              key={tpl.id}
              template={tpl}
              onEdit={() => setDialog({ kind: "edit", tpl })}
              onClone={() => cloneMutation.mutate(tpl.id)}
              onDelete={() => {
                if (confirm(`Remover template "${tpl.name}"?`))
                  deleteMutation.mutate(tpl.id)
              }}
            />
          ))}
        </div>
      )}

      <TemplateDialog
        state={dialog}
        onClose={() => setDialog({ kind: "closed" })}
        onSubmit={(payload) => {
          if (dialog.kind === "create") createMutation.mutate(payload)
          if (dialog.kind === "edit")
            updateMutation.mutate({ id: dialog.tpl.id, payload })
        }}
        submitting={createMutation.isPending || updateMutation.isPending}
      />
    </div>
  )
}

function TemplateCard({
  template,
  onEdit,
  onDelete,
  onClone,
}: {
  template: DocumentTemplateRead
  onEdit: () => void
  onDelete: () => void
  onClone: () => void
}) {
  const isStarter = template.tenant_id === null
  return (
    <Card>
      <div className={cardTokens.body}>
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                {template.name}
              </h3>
              {isStarter && (
                <span
                  className={cx(
                    tableTokens.badge,
                    "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
                  )}
                >
                  <RiShieldStarLine className="mr-1 inline size-3" aria-hidden />
                  Starter
                </span>
              )}
              {!template.active && (
                <span className={cx(tableTokens.badge, "bg-gray-100 text-gray-500")}>
                  Inativo
                </span>
              )}
            </div>
            <p className={cx(tableTokens.cellSecondary, "mt-1")}>
              {DOCUMENT_TYPE_LABEL[template.doc_type]}
            </p>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {isStarter ? (
              <Button variant="ghost" onClick={onClone}>
                <RiFileCopyLine className="size-4" aria-hidden />
              </Button>
            ) : (
              <>
                <Button variant="ghost" onClick={onEdit}>
                  <RiPencilLine className="size-4" aria-hidden />
                </Button>
                <Button variant="ghost" onClick={onDelete}>
                  <RiDeleteBinLine className="size-4" aria-hidden />
                </Button>
              </>
            )}
          </div>
        </div>

        {template.description && (
          <p className={cx(tableTokens.cellSecondary, "mt-3")}>
            {template.description}
          </p>
        )}

        {template.instructions && (
          <div className="mt-3 rounded-md bg-gray-50 p-3 dark:bg-gray-900">
            <p className={cx(tableTokens.header, "mb-1")}>Instrucoes</p>
            <p className={cx(tableTokens.cellSecondary, "whitespace-pre-wrap")}>
              {template.instructions}
            </p>
          </div>
        )}

        {template.fields_schema && Object.keys(template.fields_schema).length > 0 && (
          <details className="mt-3 text-xs">
            <summary className="cursor-pointer text-gray-700 hover:text-gray-900 dark:text-gray-300 dark:hover:text-gray-100">
              Schema de campos
            </summary>
            <pre className="mt-2 overflow-x-auto rounded bg-gray-50 p-3 font-mono text-[11px] text-gray-700 dark:bg-gray-900 dark:text-gray-300">
              {JSON.stringify(template.fields_schema, null, 2)}
            </pre>
          </details>
        )}
      </div>
    </Card>
  )
}

function TemplateDialog({
  state,
  onClose,
  onSubmit,
  submitting,
}: {
  state: DialogState
  onClose: () => void
  onSubmit: (payload: DocumentTemplateUpsertPayload) => void
  submitting: boolean
}) {
  const isOpen = state.kind !== "closed"
  const editing = state.kind === "edit" ? state.tpl : null

  const [docType, setDocType] = React.useState<DocumentType>("commercial_visit")
  const [name, setName] = React.useState("")
  const [description, setDescription] = React.useState("")
  const [instructions, setInstructions] = React.useState("")
  const [fieldsJson, setFieldsJson] = React.useState("{}")
  const [active, setActive] = React.useState(true)
  const [jsonError, setJsonError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (editing) {
      setDocType(editing.doc_type)
      setName(editing.name)
      setDescription(editing.description ?? "")
      setInstructions(editing.instructions ?? "")
      setFieldsJson(JSON.stringify(editing.fields_schema ?? {}, null, 2))
      setActive(editing.active)
    } else if (state.kind === "create") {
      setDocType("commercial_visit")
      setName("")
      setDescription("")
      setInstructions("")
      setFieldsJson("{}")
      setActive(true)
    }
    setJsonError(null)
  }, [state, editing])

  function submit(e: React.FormEvent) {
    e.preventDefault()
    let fields_schema: Record<string, unknown> = {}
    try {
      fields_schema = fieldsJson.trim() ? JSON.parse(fieldsJson) : {}
    } catch {
      setJsonError("JSON invalido nos campos.")
      return
    }
    onSubmit({
      doc_type: docType,
      name,
      description: description.trim() || null,
      instructions: instructions.trim() || null,
      fields_schema,
      active,
    })
  }

  return (
    <Dialog open={isOpen} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl">
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>
              {editing ? `Editar ${editing.name}` : "Novo template de extracao"}
            </DialogTitle>
            <DialogDescription>
              O agente IA usa estas instrucoes + schema para guiar a extracao
              quando este template for selecionado no upload.
            </DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <Label htmlFor="docType">Tipo de documento</Label>
              <Select value={docType} onValueChange={(v) => setDocType(v as DocumentType)}>
                <SelectTrigger id="docType" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ALL_DOC_TYPES.map((dt) => (
                    <SelectItem key={dt} value={dt}>
                      {DOCUMENT_TYPE_LABEL[dt]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="name">Nome do template</Label>
              <Input
                id="name"
                placeholder="ex: Relatorio Onboard A7"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
              />
            </div>
          </div>

          <div>
            <Label htmlFor="description">Descricao (opcional)</Label>
            <Input
              id="description"
              placeholder="Quando usar este template"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>

          <div>
            <Label htmlFor="instructions">Instrucoes para o agente</Label>
            <Textarea
              id="instructions"
              rows={5}
              placeholder="ex: 'Este e o template Onboard da A7. Extraia: data da visita, responsavel, historico da empresa, descricao das instalacoes, quantidade de funcionarios, observacoes da composicao de custos.'"
              value={instructions}
              onChange={(e) => setInstructions(e.target.value)}
            />
          </div>

          <div>
            <Label htmlFor="fields_schema">
              Schema de campos esperados (JSON, opcional)
            </Label>
            <Textarea
              id="fields_schema"
              rows={6}
              placeholder='{"campos": [{"nome": "data_visita", "tipo": "date"}, ...]}'
              value={fieldsJson}
              onChange={(e) => setFieldsJson(e.target.value)}
              className="font-mono text-xs"
            />
            {jsonError && (
              <p className="mt-1 text-xs text-red-600 dark:text-red-400">{jsonError}</p>
            )}
          </div>

          <div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={active}
                onChange={(e) => setActive(e.target.checked)}
                className="rounded"
              />
              Template ativo
            </label>
          </div>

          <DialogFooter>
            <Button type="button" variant="secondary" onClick={onClose}>
              Cancelar
            </Button>
            <Button type="submit" isLoading={submitting} disabled={submitting}>
              {editing ? "Salvar" : "Criar"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
