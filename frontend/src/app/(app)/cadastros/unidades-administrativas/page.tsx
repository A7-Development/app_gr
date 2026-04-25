"use client"

//
// Cadastros · Unidades Administrativas — listagem + criacao/edicao via Dialog.
//
// Hierarquia (CLAUDE.md 11.6):
//   L1 (dropdown): Cadastros
//     L2 (sidebar): Unidades administrativas → /cadastros/unidades-administrativas
//       L3 (TabNavigation): n/a — lista unica + dialog inline
//
// UA primaria do tenant. Cada UA pode (mas nao precisa) ter integracao
// QiTech / Bitfin / outra admin. Pode ser FIDC, securitizadora, factoring,
// gestora, consultoria.
//

import * as React from "react"
import { useState } from "react"
import {
  RiAddLine,
  RiBuildingLine,
  RiDeleteBinLine,
  RiEditLine,
} from "@remixicon/react"

import { EmptyState } from "@/components/app/EmptyState"
import { ErrorState } from "@/components/app/ErrorState"
import { PageHeader } from "@/components/app/PageHeader"
import { Badge } from "@/components/tremor/Badge"
import { Button } from "@/components/tremor/Button"
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
import { Switch } from "@/components/tremor/Switch"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRoot,
  TableRow,
} from "@/components/tremor/Table"
import {
  useCreateUA,
  useDeleteUA,
  useUAs,
  useUpdateUA,
} from "@/lib/hooks/cadastros"
import type {
  TipoUA,
  UnidadeAdministrativa,
} from "@/lib/api-client"

const PAGE_INFO =
  "Unidades administrativas (UAs) sao as entidades operacionais do tenant: FIDCs, securitizadoras, factorings, gestoras, consultorias. Cada UA pode ter ou nao integracao com fontes externas (QiTech, Bitfin, outras)."

const TIPO_LABELS: Record<TipoUA, string> = {
  fidc: "FIDC",
  consultoria: "Consultoria",
  securitizadora: "Securitizadora",
  factoring: "Factoring",
  gestora: "Gestora",
}

const TIPOS: TipoUA[] = [
  "fidc",
  "consultoria",
  "securitizadora",
  "factoring",
  "gestora",
]

function formatCnpj(cnpj: string | null): string {
  if (!cnpj) return "—"
  if (cnpj.length !== 14) return cnpj
  return `${cnpj.slice(0, 2)}.${cnpj.slice(2, 5)}.${cnpj.slice(5, 8)}/${cnpj.slice(8, 12)}-${cnpj.slice(12)}`
}

type FormState = {
  nome: string
  cnpj: string
  tipo: TipoUA
  ativa: boolean
}

const EMPTY_FORM: FormState = {
  nome: "",
  cnpj: "",
  tipo: "fidc",
  ativa: true,
}

export default function UnidadesAdministrativasPage() {
  const { data, isLoading, isError, refetch } = useUAs()
  const createMutation = useCreateUA()
  const deleteMutation = useDeleteUA()

  const [editing, setEditing] = useState<UnidadeAdministrativa | null>(null)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [form, setForm] = useState<FormState>(EMPTY_FORM)
  const [submitError, setSubmitError] = useState<string | null>(null)

  const updateMutation = useUpdateUA(editing?.id ?? "")

  function openCreate() {
    setEditing(null)
    setForm(EMPTY_FORM)
    setSubmitError(null)
    setDialogOpen(true)
  }

  function openEdit(ua: UnidadeAdministrativa) {
    setEditing(ua)
    setForm({
      nome: ua.nome,
      cnpj: ua.cnpj ?? "",
      tipo: ua.tipo,
      ativa: ua.ativa,
    })
    setSubmitError(null)
    setDialogOpen(true)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitError(null)
    const payload = {
      nome: form.nome.trim(),
      cnpj: form.cnpj.trim() || null,
      tipo: form.tipo,
      ativa: form.ativa,
    }
    try {
      if (editing) {
        await updateMutation.mutateAsync(payload)
      } else {
        await createMutation.mutateAsync(payload)
      }
      setDialogOpen(false)
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Falha ao salvar unidade administrativa."
      setSubmitError(msg)
    }
  }

  async function handleDelete(ua: UnidadeAdministrativa) {
    const ok = confirm(
      `Excluir a UA "${ua.nome}"? Esta operacao nao pode ser desfeita.`,
    )
    if (!ok) return
    try {
      await deleteMutation.mutateAsync(ua.id)
    } catch (err) {
      const msg =
        err instanceof Error ? err.message : "Falha ao excluir unidade administrativa."
      alert(msg)
    }
  }

  return (
    <div className="flex flex-col gap-6 px-12 py-6 pb-28">
      <PageHeader
        title="Cadastros · Unidades administrativas"
        info={PAGE_INFO}
        actions={
          <Button onClick={openCreate}>
            <RiAddLine className="mr-2 size-4" aria-hidden />
            Nova UA
          </Button>
        }
      />

      {isError && (
        <ErrorState
          title="Nao foi possivel carregar as UAs"
          description="Verifique se a API esta no ar e se seu usuario tem permissao admin no modulo Cadastros."
          action={
            <Button variant="secondary" onClick={() => refetch()}>
              Tentar novamente
            </Button>
          }
        />
      )}

      {!isError && !isLoading && data && data.length === 0 && (
        <EmptyState
          icon={RiBuildingLine}
          title="Nenhuma UA cadastrada"
          description="Cadastre a primeira unidade administrativa do tenant para comecar a usar integracoes e BI."
          action={
            <Button onClick={openCreate}>
              <RiAddLine className="mr-2 size-4" aria-hidden />
              Cadastrar primeira UA
            </Button>
          }
        />
      )}

      {!isError && (isLoading || (data && data.length > 0)) && (
        <div className="rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
          <TableRoot>
            <Table>
              <TableHead>
                <TableRow>
                  <TableHeaderCell>Nome</TableHeaderCell>
                  <TableHeaderCell>Tipo</TableHeaderCell>
                  <TableHeaderCell>CNPJ</TableHeaderCell>
                  <TableHeaderCell>Status</TableHeaderCell>
                  <TableHeaderCell className="w-32 text-right">
                    <span className="sr-only">Acoes</span>
                  </TableHeaderCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {isLoading &&
                  Array.from({ length: 3 }).map((_, i) => (
                    <TableRow key={`sk-${i}`}>
                      <TableCell colSpan={5}>
                        <div className="h-6 w-full animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
                      </TableCell>
                    </TableRow>
                  ))}
                {!isLoading &&
                  data?.map((ua) => (
                    <TableRow key={ua.id}>
                      <TableCell className="font-medium text-gray-900 dark:text-gray-50">
                        {ua.nome}
                      </TableCell>
                      <TableCell>{TIPO_LABELS[ua.tipo]}</TableCell>
                      <TableCell className="font-mono text-xs">
                        {formatCnpj(ua.cnpj)}
                      </TableCell>
                      <TableCell>
                        {ua.ativa ? (
                          <Badge variant="success">Ativa</Badge>
                        ) : (
                          <Badge variant="neutral">Inativa</Badge>
                        )}
                      </TableCell>
                      <TableCell className="text-right">
                        <div className="flex justify-end gap-1">
                          <Button
                            variant="ghost"
                            onClick={() => openEdit(ua)}
                            aria-label={`Editar ${ua.nome}`}
                          >
                            <RiEditLine className="size-4" aria-hidden />
                          </Button>
                          <Button
                            variant="ghost"
                            onClick={() => handleDelete(ua)}
                            aria-label={`Excluir ${ua.nome}`}
                          >
                            <RiDeleteBinLine className="size-4" aria-hidden />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
              </TableBody>
            </Table>
          </TableRoot>
        </div>
      )}

      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent>
          <form onSubmit={handleSubmit} className="flex flex-col gap-5">
            <DialogHeader>
              <DialogTitle>
                {editing ? "Editar UA" : "Nova UA"}
              </DialogTitle>
              <DialogDescription>
                {editing
                  ? "Atualize os dados da unidade administrativa. Campos vazios sao opcionais."
                  : "Cadastre uma nova unidade administrativa do tenant."}
              </DialogDescription>
            </DialogHeader>

            <div className="flex flex-col gap-4">
              <div className="flex flex-col gap-2">
                <Label htmlFor="nome">Nome</Label>
                <Input
                  id="nome"
                  required
                  maxLength={200}
                  value={form.nome}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, nome: e.target.value }))
                  }
                  placeholder="Ex.: REALINVEST FIDC"
                />
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="tipo">Tipo</Label>
                <Select
                  value={form.tipo}
                  onValueChange={(v) =>
                    setForm((f) => ({ ...f, tipo: v as TipoUA }))
                  }
                >
                  <SelectTrigger id="tipo">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {TIPOS.map((t) => (
                      <SelectItem key={t} value={t}>
                        {TIPO_LABELS[t]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="flex flex-col gap-2">
                <Label htmlFor="cnpj">
                  CNPJ <span className="text-xs text-gray-500">(opcional)</span>
                </Label>
                <Input
                  id="cnpj"
                  value={form.cnpj}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, cnpj: e.target.value }))
                  }
                  placeholder="00.000.000/0000-00 ou 14 digitos"
                  inputMode="numeric"
                />
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Pode ficar vazio para UAs sem CNPJ proprio (em formacao,
                  internas).
                </p>
              </div>

              <div className="flex items-center gap-3">
                <Switch
                  id="ativa"
                  checked={form.ativa}
                  onCheckedChange={(c) =>
                    setForm((f) => ({ ...f, ativa: c }))
                  }
                />
                <Label htmlFor="ativa">UA ativa</Label>
              </div>

              {submitError && (
                <p className="rounded border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
                  {submitError}
                </p>
              )}
            </div>

            <DialogFooter>
              <Button
                type="button"
                variant="secondary"
                onClick={() => setDialogOpen(false)}
              >
                Cancelar
              </Button>
              <Button
                type="submit"
                isLoading={
                  createMutation.isPending || updateMutation.isPending
                }
              >
                {editing ? "Salvar alteracoes" : "Cadastrar"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
