// src/design-system/patterns/ListagemCrudCards.tsx
//
// PATTERN — Listagem CRUD Cards
// Copy, paste, adapt. Not a black-box component.
//
// Composes:
//   PageHeader (title + info tooltip + subtitle eyebrow + "+ Novo X" action)
//   ↓
//   EmptyState | ErrorState | (Card[FilterSearch + SegmentSwitch + counter] + grid de EntityCard)
//   ↓
//   DrillDownSheet (criar)  — abre via ?action=new
//   DrillDownSheet (editar) — abre via ?selected=<id>     [opcional — so quando edit eh inline]
//   Dialog destrutivo (excluir) — confirmacao com state local
//
// Use for: gestao administrativa de cadastros onde cada entidade e melhor
// representada em CARD visualmente rico (icone + titulo + descricao + meta +
// badges + acoes) do que em linha de tabela. Casos tipicos:
//
//   - Workflows         (primeira instancia em prod: /credito/workflows)
//   - Agentes IA        (proximo candidato: /credito/agentes)
//   - Dashboards salvos (icone, autor, periodo, ultima edicao)
//   - Conexoes externas (logo do provedor, status, conta, ultimo sync)
//   - Templates de extracao (icone do tipo de doc, esquema)
//
// REGRA DE TAMANHO (decida QUAL pattern usar):
// ┌──────────────────────────┬──────────────────────────────────────────────┐
// │  Caracteristicas          │  Pattern                                     │
// ├──────────────────────────┼──────────────────────────────────────────────┤
// │ Cada entidade tem        │  ListagemCrudInline (DataTableShell)         │
// │ identidade tabular       │  ex.: usuarios, etiquetas, regras,           │
// │ (compara em linha)        │       fornecedores, credenciais             │
// │                          │                                              │
// │ Cada entidade tem        │  ESTE pattern (ListagemCrudCards)            │
// │ identidade visual        │  ex.: workflows, agentes, dashboards,        │
// │ (icone, descricao,       │       templates, conexoes                    │
// │  metadata heterogeneo)   │                                              │
// └──────────────────────────┴──────────────────────────────────────────────┘
//
// REGRA DE VOLUME:
// ┌──────────────────────┬────────────────────────────────────────────────┐
// │  Volume tipico       │  Comportamento                                 │
// ├──────────────────────┼────────────────────────────────────────────────┤
// │  < ~50 items         │  Grid client-side com FilterSearch + Segments  │
// │                      │  (3 paginas de scroll, suficiente).            │
// │                      │                                                │
// │  50-200 items        │  Adicione paginacao server-side (limit/offset) │
// │                      │  ou infinite scroll. Mantem grid.              │
// │                      │                                                │
// │  200+ items          │  Considere migrar pra ListagemCrudInline       │
// │                      │  (tabela e mais densa em volume).              │
// └──────────────────────┴────────────────────────────────────────────────┘
//
// HOW TO ADAPT:
//   1. Troque `EspacoRow` pelo seu tipo de dominio.
//   2. Troque `SAMPLE_DATA` por hook React Query real.
//   3. Troque os 3 hooks de mutacao (create/update/delete) pelos seus
//      `useMutation` reais.
//   4. Adapte `EntityCard` pro seu dominio:
//      - icone identitario (cor via token nomeado, NUNCA `bg-X-N` solto)
//      - titulo (line-clamp-1)
//      - descricao (line-clamp-2)
//      - metadata em linha (3-5 valores com separador `·`)
//      - badges secundarios (ex.: "Strata template", "Em breve")
//   5. Substitua `<MockCreateForm />` e `<MockEditForm />` pelos seus.
//   6. Se edit deve abrir DRAWER (form): mantenha `<DrillDownSheet open={selected}>`.
//      Se edit deve REDIRECIONAR para outra rota (ex.: editor visual): omita
//      o drawer de edit e ajuste `onCardClick` pra `router.push(...)`.
//
// URL state:
//   ?action=new            → drawer de criacao
//   ?selected=<id>         → drawer de edicao (so quando edit eh inline)
//   (delete usa state local — operacao efemera, nao precisa deep-link)

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"
import {
  RiAddLine,
  RiDeleteBinLine,
  RiFolderLine,
  RiMoreLine,
  RiPencilLine,
} from "@remixicon/react"

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
import { Divider } from "@/components/tremor/Divider"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/tremor/DropdownMenu"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import {
  DrillDownSheet,
  EmptyState,
  ErrorState,
  FilterSearch,
  PageHeader,
  SegmentSwitch,
} from "@/design-system/components"
import { cardTokens } from "@/design-system/tokens/card"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

// ───────────────────────────────────────────────────────────────────────────
// TIPOS DE DOMINIO — troque pelo seu
// ───────────────────────────────────────────────────────────────────────────

export type EspacoRow = {
  id: string
  nome: string
  descricao: string | null
  kind: "projeto" | "time" | "pessoal"
  member_count: number
  status: "ativo" | "arquivado"
  updated_at: string
}

const SAMPLE_DATA: EspacoRow[] = [
  { id: "e-001", nome: "Onda 1 - MVP A7",      descricao: "Workspace do squad de credito para o MVP da A7 Securitizadora.", kind: "projeto", member_count: 8, status: "ativo",     updated_at: "2026-04-30T14:22:00Z" },
  { id: "e-002", nome: "Time de Risco",        descricao: "Espaco compartilhado pelo time de risco e PDD.",                  kind: "time",     member_count: 5, status: "ativo",     updated_at: "2026-04-29T10:05:00Z" },
  { id: "e-003", nome: "Estudos pessoais",     descricao: null,                                                              kind: "pessoal",  member_count: 1, status: "ativo",     updated_at: "2026-04-25T18:40:00Z" },
  { id: "e-004", nome: "Projeto antigo",       descricao: "Workspace arquivado pos-Onda 0.",                                 kind: "projeto", member_count: 3, status: "arquivado", updated_at: "2026-02-15T09:00:00Z" },
  { id: "e-005", nome: "Comite de credito",    descricao: "Espaco do comite mensal de aprovacao.",                           kind: "time",     member_count: 4, status: "ativo",     updated_at: "2026-04-28T15:30:00Z" },
  { id: "e-006", nome: "Sandbox bureaus",      descricao: "Testes de adapter Serasa/BigData/InfoSimples.",                   kind: "projeto", member_count: 2, status: "ativo",     updated_at: "2026-04-22T11:15:00Z" },
]

const KIND_LABEL: Record<EspacoRow["kind"], string> = {
  projeto: "Projeto",
  time: "Time",
  pessoal: "Pessoal",
}

// ───────────────────────────────────────────────────────────────────────────
// IDENTIDADE VISUAL POR KIND
// IMPORTANTE: em codigo real estas classes devem vir de tokens nomeados em
// `design-system/tokens/<nome>.ts` (vide `nodeCategoryTokens` em
// /credito/workflows). NUNCA `bg-X-N` solto fora de token.
// Para o pattern (template), aceitamos inline com nota.
// ───────────────────────────────────────────────────────────────────────────

const KIND_AVATAR: Record<EspacoRow["kind"], { bg: string; fg: string }> = {
  projeto: { bg: "bg-blue-50 dark:bg-blue-500/10",     fg: "text-blue-600 dark:text-blue-400" },
  time:    { bg: "bg-emerald-50 dark:bg-emerald-500/10", fg: "text-emerald-600 dark:text-emerald-400" },
  pessoal: { bg: "bg-violet-50 dark:bg-violet-500/10", fg: "text-violet-600 dark:text-violet-400" },
}

// ───────────────────────────────────────────────────────────────────────────
// ENTITY CARD — anatomia canonica do pattern
// Exporte SEU EntityCard customizado em _components/<X>Card.tsx no caller.
// ───────────────────────────────────────────────────────────────────────────

function EspacoCard({
  item,
  onOpen,
  onEdit,
  onDelete,
}: {
  item: EspacoRow
  onOpen: () => void
  onEdit: () => void
  onDelete: () => void
}) {
  const avatar = KIND_AVATAR[item.kind]
  return (
    <Card
      onClick={onOpen}
      className={cx(
        "cursor-pointer transition-all hover:border-blue-500 hover:shadow-sm",
        "dark:hover:border-blue-500",
      )}
    >
      <div className={cx(cardTokens.body, "space-y-3")}>
        {/* Linha 1: avatar + badges + dropdown */}
        <div className="flex items-start justify-between gap-3">
          <div
            className={cx(
              "flex size-10 shrink-0 items-center justify-center rounded-md",
              avatar.bg,
              avatar.fg,
            )}
          >
            <RiFolderLine className="size-5" aria-hidden />
          </div>
          <div className="flex flex-1 flex-wrap items-center justify-end gap-2">
            <span className={cx(tableTokens.badge, "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300")}>
              {KIND_LABEL[item.kind]}
            </span>
            {item.status === "arquivado" && (
              <span className={cx(tableTokens.badge, "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400")}>
                Arquivado
              </span>
            )}
          </div>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button
                variant="ghost"
                className="size-7 shrink-0 p-0"
                aria-label={`Acoes de ${item.nome}`}
                onClick={(e) => e.stopPropagation()}
              >
                <RiMoreLine className="size-4" aria-hidden />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" sideOffset={4}>
              <DropdownMenuItem onSelect={onEdit}>
                <RiPencilLine className="mr-2 size-4" aria-hidden />
                Editar
              </DropdownMenuItem>
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onSelect={onDelete}
                className="text-red-600 focus:text-red-700 dark:text-red-400 dark:focus:text-red-300"
              >
                <RiDeleteBinLine className="mr-2 size-4" aria-hidden />
                Excluir
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        {/* Linha 2: titulo + descricao */}
        <div>
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-100 line-clamp-1">
            {item.nome}
          </h3>
          <p className={cx(tableTokens.cellSecondary, "mt-1 line-clamp-2")}>
            {item.descricao ?? "Sem descricao"}
          </p>
        </div>

        {/* Linha 3: metadados — separador `·` entre valores */}
        <div className={cx(tableTokens.cellSecondary, "flex items-center gap-3")}>
          <span>
            {item.member_count} {item.member_count === 1 ? "membro" : "membros"}
          </span>
          <span aria-hidden>·</span>
          <span title={item.updated_at}>
            atualizado {formatRelative(item.updated_at)}
          </span>
        </div>
      </div>
    </Card>
  )
}

function formatRelative(iso: string): string {
  // Helper de exemplo. Em codigo real, use date-fns formatDistanceToNow.
  const diff = Date.now() - new Date(iso).getTime()
  const days = Math.floor(diff / (1000 * 60 * 60 * 24))
  if (days === 0) return "hoje"
  if (days === 1) return "ontem"
  if (days < 30) return `${days}d atras`
  return `${Math.floor(days / 30)}m atras`
}

// ───────────────────────────────────────────────────────────────────────────
// FORMS MOCK — substitua por _components/<X>Form.tsx reais
// (siga padrao react-hook-form + zod, ver `ProviderForm` em
//  /admin/ia/providers/_components/)
// ───────────────────────────────────────────────────────────────────────────

function MockCreateForm({
  submitting,
  onSubmit,
  onCancel,
}: {
  submitting: boolean
  onSubmit: (values: { nome: string; descricao: string }) => void
  onCancel: () => void
}) {
  const [nome, setNome] = React.useState("")
  const [descricao, setDescricao] = React.useState("")
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (nome.trim()) onSubmit({ nome: nome.trim(), descricao: descricao.trim() })
      }}
      className="flex flex-col gap-6"
      noValidate
    >
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
          Novo espaco
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Substitua este form pelo seu (react-hook-form + zod, primitivos Tremor).
        </p>
      </div>
      <Divider />
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="nome">
            Nome <span className="ml-1 text-red-600 dark:text-red-500" aria-hidden>*</span>
          </Label>
          <Input
            id="nome"
            placeholder="Ex.: Onda 2 - Cessoes"
            value={nome}
            onChange={(e) => setNome(e.target.value)}
            autoFocus
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="descricao">Descricao (opcional)</Label>
          <Input
            id="descricao"
            placeholder="O que vai acontecer neste espaco"
            value={descricao}
            onChange={(e) => setDescricao(e.target.value)}
          />
        </div>
      </div>
      <Divider />
      <div className="flex items-center justify-end gap-2">
        <Button type="button" variant="secondary" onClick={onCancel} disabled={submitting}>
          Cancelar
        </Button>
        <Button type="submit" variant="primary" disabled={submitting || !nome.trim()}>
          Cadastrar
        </Button>
      </div>
    </form>
  )
}

function MockEditForm({
  initial,
  submitting,
  onSubmit,
  onCancel,
}: {
  initial: EspacoRow
  submitting: boolean
  onSubmit: (values: { nome: string; descricao: string }) => void
  onCancel: () => void
}) {
  const [nome, setNome] = React.useState(initial.nome)
  const [descricao, setDescricao] = React.useState(initial.descricao ?? "")
  React.useEffect(() => {
    setNome(initial.nome)
    setDescricao(initial.descricao ?? "")
  }, [initial])
  const isDirty = nome.trim() !== initial.nome || descricao.trim() !== (initial.descricao ?? "")
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (nome.trim()) onSubmit({ nome: nome.trim(), descricao: descricao.trim() })
      }}
      className="flex flex-col gap-6"
      noValidate
    >
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
          Editar · {initial.nome}
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Use defaults vindos de `initial`. Em forms reais, useEffect + reset(defaults).
        </p>
      </div>
      <Divider />
      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="edit-nome">Nome</Label>
          <Input id="edit-nome" value={nome} onChange={(e) => setNome(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="edit-descricao">Descricao</Label>
          <Input
            id="edit-descricao"
            value={descricao}
            onChange={(e) => setDescricao(e.target.value)}
          />
        </div>
      </div>
      <Divider />
      <div className="flex items-center justify-end gap-2">
        <Button type="button" variant="secondary" onClick={onCancel} disabled={submitting}>
          Cancelar
        </Button>
        <Button type="submit" variant="primary" disabled={submitting || !isDirty}>
          Salvar alteracoes
        </Button>
      </div>
    </form>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// PATTERN
// ───────────────────────────────────────────────────────────────────────────

type Segment = "todos" | "ativos" | "arquivados" | "projetos" | "times"

export function ListagemCrudCards() {
  const router = useRouter()
  const sp = useSearchParams()
  const action = sp.get("action") // "new" | null
  const selectedId = sp.get("selected")

  // ── Estado da listagem (mock) ───────────────────────────────────────────
  // SUBSTITUA por React Query: const { data, isLoading, error, refetch } = useEspacos()
  const [data, setData] = React.useState<EspacoRow[]>(SAMPLE_DATA)
  const isLoading = false
  const error = null as Error | null

  // ── Filtros locais (search + segment) ───────────────────────────────────
  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState<Segment>("todos")

  // Counts por segment (alimentam badges no SegmentSwitch).
  const counts = React.useMemo(
    () => ({
      todos: data.length,
      ativos: data.filter((r) => r.status === "ativo").length,
      arquivados: data.filter((r) => r.status === "arquivado").length,
      projetos: data.filter((r) => r.kind === "projeto").length,
      times: data.filter((r) => r.kind === "time").length,
    }),
    [data],
  )

  // Pre-filtro por segment.
  const segmentFiltered = React.useMemo(() => {
    switch (segment) {
      case "ativos":
        return data.filter((r) => r.status === "ativo")
      case "arquivados":
        return data.filter((r) => r.status === "arquivado")
      case "projetos":
        return data.filter((r) => r.kind === "projeto")
      case "times":
        return data.filter((r) => r.kind === "time")
      default:
        return data
    }
  }, [data, segment])

  // Search global (case-insensitive em nome + descricao).
  const visible = React.useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return segmentFiltered
    return segmentFiltered.filter(
      (r) =>
        r.nome.toLowerCase().includes(term) ||
        (r.descricao ?? "").toLowerCase().includes(term),
    )
  }, [segmentFiltered, search])

  const selected = React.useMemo(
    () => (selectedId ? data.find((p) => p.id === selectedId) ?? null : null),
    [data, selectedId],
  )

  // Confirmacao destrutiva: state local, sem deep-link.
  const [pendingDelete, setPendingDelete] = React.useState<EspacoRow | null>(null)

  // Estados de submit (mocks). SUBSTITUA por useMutation().isPending.
  const [creating, setCreating] = React.useState(false)
  const [editing, setEditing] = React.useState(false)
  const [deleting, setDeleting] = React.useState(false)

  // ── Navegacao via URL (deep-linkavel) ───────────────────────────────────
  const setQuery = React.useCallback(
    (next: { action?: string | null; selected?: string | null }) => {
      const params = new URLSearchParams(sp.toString())
      if (next.action !== undefined) {
        if (next.action) params.set("action", next.action)
        else params.delete("action")
      }
      if (next.selected !== undefined) {
        if (next.selected) params.set("selected", next.selected)
        else params.delete("selected")
      }
      const qs = params.toString()
      router.push(qs ? `?${qs}` : "?")
    },
    [router, sp],
  )

  const openNew = React.useCallback(
    () => setQuery({ action: "new", selected: null }),
    [setQuery],
  )
  const openEdit = React.useCallback(
    (p: EspacoRow) => setQuery({ action: null, selected: p.id }),
    [setQuery],
  )
  const closeSheet = React.useCallback(
    () => setQuery({ action: null, selected: null }),
    [setQuery],
  )

  // openOpen = navegar para o recurso (no mock, abre o drawer de edit; em
  // codigo real, geralmente router.push(`/recurso/${id}`)).
  const openItem = openEdit

  // ── Handlers de submit ──────────────────────────────────────────────────
  const handleCreate = React.useCallback(
    async (values: { nome: string; descricao: string }) => {
      setCreating(true)
      try {
        await new Promise((r) => setTimeout(r, 400))
        const novo: EspacoRow = {
          id: `e-${String(data.length + 1).padStart(3, "0")}`,
          nome: values.nome,
          descricao: values.descricao || null,
          kind: "projeto",
          member_count: 1,
          status: "ativo",
          updated_at: new Date().toISOString(),
        }
        setData((prev) => [novo, ...prev])
        toast.success(`'${values.nome}' cadastrado.`)
        closeSheet()
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Falha ao cadastrar.")
      } finally {
        setCreating(false)
      }
    },
    [data.length, closeSheet],
  )

  const handleEdit = React.useCallback(
    async (values: { nome: string; descricao: string }) => {
      if (!selected) return
      setEditing(true)
      try {
        await new Promise((r) => setTimeout(r, 400))
        setData((prev) =>
          prev.map((p) =>
            p.id === selected.id
              ? { ...p, nome: values.nome, descricao: values.descricao || null }
              : p,
          ),
        )
        toast.success(`'${values.nome}' atualizado.`)
        closeSheet()
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Falha ao atualizar.")
      } finally {
        setEditing(false)
      }
    },
    [selected, closeSheet],
  )

  const handleDelete = React.useCallback(async () => {
    if (!pendingDelete) return
    setDeleting(true)
    try {
      await new Promise((r) => setTimeout(r, 400))
      setData((prev) => prev.filter((p) => p.id !== pendingDelete.id))
      toast.success(`'${pendingDelete.nome}' excluido.`)
      setPendingDelete(null)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao excluir.")
    } finally {
      setDeleting(false)
    }
  }, [pendingDelete])

  const isEmpty = !isLoading && !error && data.length === 0
  const noResults = !isEmpty && visible.length === 0

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Espacos de trabalho"
        info="Espacos compartilhados onde times organizam projetos, dashboards e dossies."
        subtitle="Cadastros · Configuracao"
        actions={
          <Button variant="primary" onClick={openNew} disabled={isLoading}>
            <RiAddLine className="mr-1 size-4" aria-hidden />
            Novo espaco
          </Button>
        }
      />

      {error ? (
        <ErrorState
          title="Falha ao carregar registros"
          description={
            error instanceof Error
              ? error.message
              : "Verifique sua conexao e tente novamente."
          }
          action={
            <Button
              variant="secondary"
              onClick={() => {
                /* refetch */
              }}
            >
              Tentar novamente
            </Button>
          }
        />
      ) : isEmpty ? (
        <EmptyState
          icon={RiFolderLine}
          title="Nenhum espaco cadastrado"
          description="Crie o primeiro espaco para comecar a organizar projetos e times."
          action={
            <Button variant="primary" onClick={openNew}>
              <RiAddLine className="mr-1 size-4" aria-hidden />
              Cadastrar espaco
            </Button>
          }
        />
      ) : (
        <>
          {/* Faixa de filtros — mesma anatomia do DataTableShell */}
          <Card className="flex flex-wrap items-center gap-2 p-3">
            <FilterSearch
              value={search}
              onChange={(e) => setSearch(e.currentTarget.value)}
              onClear={() => setSearch("")}
              placeholder="Buscar por nome ou descricao..."
            />
            <SegmentSwitch
              options={[
                { value: "todos",      label: "Todos",      count: counts.todos },
                { value: "ativos",     label: "Ativos",     count: counts.ativos },
                { value: "projetos",   label: "Projetos",   count: counts.projetos },
                { value: "times",      label: "Times",      count: counts.times },
                { value: "arquivados", label: "Arquivados", count: counts.arquivados },
              ]}
              value={segment}
              onChange={setSegment}
            />
            <span
              className="ml-auto text-[11px] tabular-nums text-gray-500 dark:text-gray-400"
              aria-live="polite"
            >
              {visible.length === counts.todos
                ? `${visible.length} ${visible.length === 1 ? "espaco" : "espacos"}`
                : `${visible.length} de ${counts.todos}`}
            </span>
          </Card>

          {noResults ? (
            <div className="flex flex-col items-center justify-center gap-2 rounded border border-dashed border-gray-200 bg-white py-12 text-center dark:border-gray-800 dark:bg-gray-950">
              <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
                Nenhum resultado para esses filtros
              </p>
              <Button
                variant="ghost"
                onClick={() => {
                  setSearch("")
                  setSegment("todos")
                }}
              >
                Limpar filtros
              </Button>
            </div>
          ) : (
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3">
              {visible.map((item) => (
                <EspacoCard
                  key={item.id}
                  item={item}
                  onOpen={() => openItem(item)}
                  onEdit={() => openEdit(item)}
                  onDelete={() => setPendingDelete(item)}
                />
              ))}
            </div>
          )}
        </>
      )}

      {/* Drawer: Novo */}
      <DrillDownSheet
        open={action === "new"}
        onClose={closeSheet}
        title="Novo espaco"
        size="md"
      >
        <div className="p-6">
          <MockCreateForm
            submitting={creating}
            onSubmit={handleCreate}
            onCancel={closeSheet}
          />
        </div>
      </DrillDownSheet>

      {/* Drawer: Editar — OPCIONAL.
          Se o "edit" for um redirect a outra rota (ex.: editor visual),
          REMOVA este drawer e ajuste `openItem` pra `router.push(...)`. */}
      <DrillDownSheet
        open={selected !== null}
        onClose={closeSheet}
        title={selected ? `Editar · ${selected.nome}` : ""}
        size="md"
      >
        {selected && (
          <div className="p-6">
            <MockEditForm
              initial={selected}
              submitting={editing}
              onSubmit={handleEdit}
              onCancel={closeSheet}
            />
          </div>
        )}
      </DrillDownSheet>

      {/* Confirmacao destrutiva (state local) */}
      <Dialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir espaco</DialogTitle>
            <DialogDescription>
              Esta acao remove permanentemente{" "}
              <span className="font-medium text-gray-900 dark:text-gray-50">
                {pendingDelete?.nome}
              </span>
              . Membros perderao acesso e dossies vinculados ficarao orfaos.
            </DialogDescription>
          </DialogHeader>
          <Divider />
          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => setPendingDelete(null)}
              disabled={deleting}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleDelete}
              disabled={deleting}
            >
              <RiDeleteBinLine className="mr-1.5 size-4" aria-hidden />
              Excluir espaco
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// Default export pra simplificar import em paginas de demo/preview.
export default ListagemCrudCards

// Re-export do tipo de dominio + util para callers que queiram o card avulso.
export { EspacoCard }
