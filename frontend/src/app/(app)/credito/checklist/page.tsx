// src/app/(app)/credito/checklist/page.tsx
//
// Checklist do tenant — itens de analise que os agentes IA avaliam por secao.
//
// Cada tenant define os SEUS itens. Itens com tenant_id NULL sao "starter pack"
// Strata — visiveis a todos, mas precisam ser clonados para serem editaveis.
//
// O backend (`shared/agents/runtime.py::_render_checklist_block`) injeta esses
// itens no prompt do agente especialista quando ele roda a analise da secao.

"use client"

import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  RiAddLine,
  RiDeleteBinLine,
  RiFileCopyLine,
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
import { PageHeader } from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"
import {
  credito,
  SEVERITY_LABEL,
  SEVERITY_TONE,
  type CheckSeverity,
  type ChecklistItemRead,
  type ChecklistItemUpsertPayload,
} from "@/lib/credito-client"

// Sections come from app/shared/agents/catalog.py::SpecialistAgentSpec.section_id
const SECTIONS: Array<{ id: string; label: string }> = [
  { id: "plea", label: "Pleito" },
  { id: "documents", label: "Documentos" },
  { id: "social_contract", label: "Contrato social" },
  { id: "financial", label: "Financeiro" },
  { id: "indebtedness", label: "Endividamento" },
  { id: "legal", label: "Juridico" },
  { id: "partners", label: "Socios" },
  { id: "commercial_visit", label: "Visita" },
  { id: "cross_reference", label: "Cross-Reference" },
  { id: "opinion", label: "Parecer" },
]

const SEVERITIES: CheckSeverity[] = ["critical", "important", "informational"]

type DialogState =
  | { kind: "closed" }
  | { kind: "create" }
  | { kind: "edit"; item: ChecklistItemRead }

export default function ChecklistPage() {
  const queryClient = useQueryClient()
  const [section, setSection] = React.useState<string>(SECTIONS[0].id)
  const [dialog, setDialog] = React.useState<DialogState>({ kind: "closed" })

  const { data: items, isLoading } = useQuery({
    queryKey: ["credito", "checklist", section],
    queryFn: () => credito.checklist.list({ section }),
  })

  const createMutation = useMutation({
    mutationFn: credito.checklist.create,
    onSuccess: () => {
      toast.success("Item criado.")
      queryClient.invalidateQueries({ queryKey: ["credito", "checklist"] })
      setDialog({ kind: "closed" })
    },
    onError: (e) => toast.error(`Erro: ${(e as Error).message}`),
  })

  const updateMutation = useMutation({
    mutationFn: (vars: { id: string; payload: ChecklistItemUpsertPayload }) =>
      credito.checklist.update(vars.id, vars.payload),
    onSuccess: () => {
      toast.success("Item atualizado.")
      queryClient.invalidateQueries({ queryKey: ["credito", "checklist"] })
      setDialog({ kind: "closed" })
    },
    onError: (e) => toast.error(`Erro: ${(e as Error).message}`),
  })

  const deleteMutation = useMutation({
    mutationFn: credito.checklist.remove,
    onSuccess: () => {
      toast.success("Item removido.")
      queryClient.invalidateQueries({ queryKey: ["credito", "checklist"] })
    },
    onError: (e) => toast.error(`Erro: ${(e as Error).message}`),
  })

  const cloneMutation = useMutation({
    mutationFn: credito.checklist.clone,
    onSuccess: () => {
      toast.success("Item clonado para o tenant. Agora editavel.")
      queryClient.invalidateQueries({ queryKey: ["credito", "checklist"] })
    },
    onError: (e) => toast.error(`Erro: ${(e as Error).message}`),
  })

  return (
    <div className="px-6 py-6">
      <PageHeader
        title="Checklist de analise"
        subtitle="Itens que os agentes IA avaliam em cada secao do dossie. Cada tenant define os seus."
        actions={
          <Button onClick={() => setDialog({ kind: "create" })}>
            <RiAddLine className="size-4" aria-hidden />
            Novo item
          </Button>
        }
      />

      {/* Tabs por secao */}
      <div className="mt-6 flex flex-wrap gap-1 border-b border-gray-200 dark:border-gray-800">
        {SECTIONS.map((s) => (
          <button
            key={s.id}
            type="button"
            onClick={() => setSection(s.id)}
            className={cx(
              "border-b-2 px-3 py-2 text-xs font-medium transition-colors",
              section === s.id
                ? "border-blue-500 text-blue-700 dark:text-blue-400"
                : "border-transparent text-gray-600 hover:text-gray-900 dark:text-gray-400 dark:hover:text-gray-100",
            )}
          >
            {s.label}
          </button>
        ))}
      </div>

      <Card className="mt-4">
        {isLoading ? (
          <p className={cx(tableTokens.cellSecondary, "p-6")}>Carregando...</p>
        ) : !items || items.length === 0 ? (
          <div className="flex flex-col items-center gap-3 px-6 py-12 text-center">
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
              Nenhum item nesta secao
            </p>
            <p className={cx(tableTokens.cellSecondary, "max-w-md")}>
              Adicione itens que os agentes IA devem avaliar quando rodarem a
              analise desta secao. Sem itens, o agente faz analise livre.
            </p>
            <Button onClick={() => setDialog({ kind: "create" })}>
              <RiAddLine className="size-4" aria-hidden />
              Adicionar primeiro item
            </Button>
          </div>
        ) : (
          <div className="divide-y divide-gray-100 dark:divide-gray-900">
            {items.map((it) => (
              <ChecklistRow
                key={it.id}
                item={it}
                onEdit={() => setDialog({ kind: "edit", item: it })}
                onDelete={() => deleteMutation.mutate(it.id)}
                onClone={() => cloneMutation.mutate(it.id)}
              />
            ))}
          </div>
        )}
      </Card>

      <ChecklistDialog
        state={dialog}
        defaultSection={section}
        onClose={() => setDialog({ kind: "closed" })}
        onSubmit={(payload) => {
          if (dialog.kind === "create") createMutation.mutate(payload)
          if (dialog.kind === "edit")
            updateMutation.mutate({ id: dialog.item.id, payload })
        }}
        submitting={createMutation.isPending || updateMutation.isPending}
      />
    </div>
  )
}

function ChecklistRow({
  item,
  onEdit,
  onDelete,
  onClone,
}: {
  item: ChecklistItemRead
  onEdit: () => void
  onDelete: () => void
  onClone: () => void
}) {
  const isStarter = item.tenant_id === null
  return (
    <div className="flex items-start justify-between gap-3 p-4">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <code className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[11px] text-gray-700 dark:bg-gray-900 dark:text-gray-300">
            {item.code}
          </code>
          <span className={cx(tableTokens.badge, SEVERITY_TONE[item.severity])}>
            {SEVERITY_LABEL[item.severity]}
          </span>
          {isStarter && (
            <span
              className={cx(
                tableTokens.badge,
                "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
              )}
            >
              <RiShieldStarLine className="mr-1 inline size-3" aria-hidden />
              Starter Strata
            </span>
          )}
          {!item.active && (
            <span className={cx(tableTokens.badge, "bg-gray-100 text-gray-500")}>
              Inativo
            </span>
          )}
        </div>
        <p className="mt-1.5 text-sm text-gray-900 dark:text-gray-100">
          {item.description}
        </p>
        {item.guidance && (
          <p className={cx(tableTokens.cellSecondary, "mt-1")}>
            <span className="font-medium">Orientacao:</span> {item.guidance}
          </p>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-1">
        {isStarter ? (
          <Button variant="ghost" onClick={onClone} title="Clonar para editar">
            <RiFileCopyLine className="size-4" aria-hidden />
            Clonar
          </Button>
        ) : (
          <>
            <Button variant="ghost" onClick={onEdit}>
              <RiPencilLine className="size-4" aria-hidden />
              Editar
            </Button>
            <Button
              variant="ghost"
              onClick={() => {
                if (confirm(`Remover item ${item.code}?`)) onDelete()
              }}
            >
              <RiDeleteBinLine className="size-4" aria-hidden />
            </Button>
          </>
        )}
      </div>
    </div>
  )
}

function ChecklistDialog({
  state,
  defaultSection,
  onClose,
  onSubmit,
  submitting,
}: {
  state: DialogState
  defaultSection: string
  onClose: () => void
  onSubmit: (payload: ChecklistItemUpsertPayload) => void
  submitting: boolean
}) {
  const isOpen = state.kind !== "closed"
  const editing = state.kind === "edit" ? state.item : null

  const [code, setCode] = React.useState("")
  const [description, setDescription] = React.useState("")
  const [guidance, setGuidance] = React.useState("")
  const [section, setSection] = React.useState(defaultSection)
  const [severity, setSeverity] = React.useState<CheckSeverity>("important")
  const [active, setActive] = React.useState(true)

  React.useEffect(() => {
    if (editing) {
      setCode(editing.code)
      setDescription(editing.description)
      setGuidance(editing.guidance ?? "")
      setSection(editing.section)
      setSeverity(editing.severity)
      setActive(editing.active)
    } else if (state.kind === "create") {
      setCode("")
      setDescription("")
      setGuidance("")
      setSection(defaultSection)
      setSeverity("important")
      setActive(true)
    }
  }, [state, editing, defaultSection])

  function submit(e: React.FormEvent) {
    e.preventDefault()
    onSubmit({
      section,
      code,
      description,
      guidance: guidance.trim() || null,
      severity,
      active,
      auto_evaluable: true,
      order_index: 0,
    })
  }

  return (
    <Dialog open={isOpen} onOpenChange={(o) => !o && onClose()}>
      <DialogContent>
        <form onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>
              {editing ? `Editar ${editing.code}` : "Novo item de checklist"}
            </DialogTitle>
            <DialogDescription>
              Os agentes IA receberao este item dinamicamente quando rodarem
              a analise da secao.
            </DialogDescription>
          </DialogHeader>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <Label htmlFor="section">Secao</Label>
              <Select value={section} onValueChange={setSection}>
                <SelectTrigger id="section" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SECTIONS.map((s) => (
                    <SelectItem key={s.id} value={s.id}>
                      {s.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div>
              <Label htmlFor="code">Codigo</Label>
              <Input
                id="code"
                placeholder="ex: SOC.001"
                value={code}
                onChange={(e) => setCode(e.target.value.toUpperCase())}
                required
              />
            </div>
          </div>

          <div>
            <Label htmlFor="description">Descricao do item</Label>
            <Textarea
              id="description"
              rows={2}
              placeholder="O que deve ser verificado neste item?"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              required
            />
          </div>

          <div>
            <Label htmlFor="guidance">Orientacao (opcional)</Label>
            <Textarea
              id="guidance"
              rows={3}
              placeholder="Instrucao para o agente sobre como avaliar (ex.: 'verificar atas dos ultimos 24 meses para identificar mudancas de QSA')"
              value={guidance}
              onChange={(e) => setGuidance(e.target.value)}
            />
          </div>

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div>
              <Label htmlFor="severity">Severidade</Label>
              <Select
                value={severity}
                onValueChange={(v) => setSeverity(v as CheckSeverity)}
              >
                <SelectTrigger id="severity" className="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SEVERITIES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {SEVERITY_LABEL[s]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex items-end">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={active}
                  onChange={(e) => setActive(e.target.checked)}
                  className="rounded"
                />
                Ativo
              </label>
            </div>
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
