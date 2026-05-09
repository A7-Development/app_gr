// src/design-system/patterns/ListagemCrudInline.tsx
//
// PATTERN — Listagem CRUD Inline
// Copy, paste, adapt. Not a black-box component.
//
// Composes:
//   PageHeader (com botao "+ Novo X")
//   ↓
//   EmptyState | ErrorState | Card > [FilterSearch + Segments + Contador] > DataTable
//   ↓
//   DrillDownSheet (criar) — abre via ?action=new
//   DrillDownSheet (editar) — abre via ?selected=<id>
//   Dialog destrutivo (excluir) — confirmacao com state local
//
// Use for: gestao administrativa de cadastros pequenos a medios (~5-200 rows)
// onde criar/editar/deletar acontecem inline (sem trocar de rota). Ex.:
// credenciais de provedor, usuarios do tenant, etiquetas, templates, regras
// de classificacao.
//
// REGRA DE TAMANHO (decida QUAL versao do pattern usar):
// ┌─────────────────────┬───────────────────────────────────────────────────┐
// │  Volume tipico      │  Filtros / Performance                            │
// ├─────────────────────┼───────────────────────────────────────────────────┤
// │  < 200 rows         │  ESTE pattern: <FilterSearch> + segments locais.  │
// │                     │  Tudo client-side, virtualize=false. Suficiente   │
// │                     │  pra cadastros admin tipicos.                     │
// │                     │                                                   │
// │  200-2000 rows      │  Copy-paste-edit + adicione <FilterChip> por      │
// │                     │  coluna (multi-select via Popover). Mantem        │
// │                     │  client-side. virtualize=true (DataTable auto).   │
// │                     │                                                   │
// │  2000+ rows         │  Migre para `ListagemComDrilldown` + busca/       │
// │                     │  filtros server-side (debounced). React Query     │
// │                     │  com query key incluindo filtros. Paginacao real. │
// └─────────────────────┴───────────────────────────────────────────────────┘
//
// NAO use para:
// - Listagem de DADOS de dominio (cessoes, eventos) — use `ListagemComDrilldown`.
// - CRUD com formulario complexo / multi-step — use rota dedicada
//   (skill `create-form-page`, ex.: `/<dominio>/novo`).
//
// HOW TO ADAPT:
//   1. Troque `FornecedorRow` pelo seu tipo de dominio.
//   2. Troque `SAMPLE_DATA` por um hook React Query real (`useFornecedores()` etc).
//   3. Troque os 3 hooks de mutacao (create/update/delete) pelos seus
//      `useMutation` reais.
//   4. Adapte as colunas — cells canonicas (CurrencyCell, DateCell, StatusCell,
//      IdCell, RelationshipCell) ou custom inline para badges de dominio.
//   5. Substitua `<MockCreateForm />` e `<MockEditForm />` pelos seus forms
//      reais (siga skill `create-form-page` mas SEM o wrapper de pagina —
//      forms ficam em `_components/<X>Form.tsx` e o caller passa `submitting`
//      + handlers).
//
// URL state:
//   ?action=new            → drawer de criacao
//   ?selected=<id>         → drawer de edicao
//   (delete usa state local — operacao efemera, nao precisa deep-link)

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"
import {
  RiAddLine,
  RiBuildingLine,
  RiCheckLine,
  RiDeleteBinLine,
  RiMoreLine,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

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
  DataTable,
  DateCell,
  DrillDownSheet,
  EmptyState,
  ErrorState,
  FilterSearch,
  PageHeader,
  SegmentSwitch,
} from "@/design-system/components"
import { cx } from "@/lib/utils"

// ───────────────────────────────────────────────────────────────────────────
// TIPOS DE DOMINIO — troque pelo seu
// ───────────────────────────────────────────────────────────────────────────

export type FornecedorRow = {
  id: string
  nome: string
  categoria: "produto" | "servico" | "matriz"
  ativo: boolean
  created_at: string
}

const SAMPLE_DATA: FornecedorRow[] = [
  { id: "f-001", nome: "Metalúrgica São Paulo Ltda", categoria: "produto", ativo: true,  created_at: "2026-01-12T10:30:00Z" },
  { id: "f-002", nome: "Tech Soluções ME",            categoria: "servico", ativo: true,  created_at: "2026-02-04T08:15:00Z" },
  { id: "f-003", nome: "Distribuidora Norte S.A.",    categoria: "matriz",  ativo: false, created_at: "2026-02-22T14:50:00Z" },
  { id: "f-004", nome: "Logística Express ME",        categoria: "servico", ativo: true,  created_at: "2026-03-08T11:00:00Z" },
  { id: "f-005", nome: "Confecções RJ Ltda",          categoria: "produto", ativo: true,  created_at: "2026-04-01T09:45:00Z" },
]

const CATEGORIA_LABEL: Record<FornecedorRow["categoria"], string> = {
  produto: "Produto",
  servico: "Servico",
  matriz: "Matriz",
}

// ───────────────────────────────────────────────────────────────────────────
// CELLS CUSTOM (declaradas no topo do arquivo, especificas desta tabela)
// Para celulas reutilizadas em outras tabelas, prefira as canonicas do DS:
//   CurrencyCell, PercentageCell, DateCell, StatusCell, IdCell,
//   CpfCnpjCell, RelationshipCell, SparklineCell, ProgressCell.
// ───────────────────────────────────────────────────────────────────────────

const CATEGORIA_TONES: Record<
  FornecedorRow["categoria"],
  { bg: string; fg: string; dot: string }
> = {
  produto: {
    bg: "bg-blue-50 dark:bg-blue-500/10",
    fg: "text-blue-700 dark:text-blue-300",
    dot: "bg-blue-500",
  },
  servico: {
    bg: "bg-emerald-50 dark:bg-emerald-500/10",
    fg: "text-emerald-700 dark:text-emerald-300",
    dot: "bg-emerald-500",
  },
  matriz: {
    bg: "bg-violet-50 dark:bg-violet-500/10",
    fg: "text-violet-700 dark:text-violet-300",
    dot: "bg-violet-500",
  },
}

function CategoriaBadge({ value }: { value: FornecedorRow["categoria"] }) {
  const tone = CATEGORIA_TONES[value]
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-sm px-1.5 py-0.5 text-[11px] font-medium",
        tone.bg,
        tone.fg,
      )}
    >
      <span aria-hidden className={cx("size-1.5 rounded-full", tone.dot)} />
      {CATEGORIA_LABEL[value]}
    </span>
  )
}

function AtivoBadge({ ativo }: { ativo: boolean }) {
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[11px] font-medium",
        ativo
          ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
          : "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400",
      )}
    >
      {ativo && <RiCheckLine className="size-3" aria-hidden />}
      {ativo ? "Ativo" : "Suspenso"}
    </span>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// FORMS MOCK — troque por seus _components/<X>Form.tsx reais
// (siga padrao react-hook-form + zod conforme CLAUDE.md §6 +
//  src/app/(app)/integracoes/catalogo/[source_type]/_components/CredenciaisTab.tsx)
// ───────────────────────────────────────────────────────────────────────────

function MockCreateForm({
  submitting,
  onSubmit,
  onCancel,
}: {
  submitting: boolean
  onSubmit: (values: { nome: string }) => void
  onCancel: () => void
}) {
  const [nome, setNome] = React.useState("")
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (nome.trim()) onSubmit({ nome: nome.trim() })
      }}
      className="flex flex-col gap-6"
      noValidate
    >
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
          Novo fornecedor
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Substitua este form pelo seu (react-hook-form + zod, primitivos
          Tremor, SecretInput para campos sensiveis).
        </p>
      </div>
      <Divider />
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="nome">
          Nome
          <span className="ml-1 text-red-600 dark:text-red-500" aria-hidden>
            *
          </span>
        </Label>
        <Input
          id="nome"
          placeholder="Ex.: Acme Distribuidora Ltda"
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          autoFocus
        />
      </div>
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
          disabled={submitting || !nome.trim()}
        >
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
  initial: FornecedorRow
  submitting: boolean
  onSubmit: (values: { nome: string }) => void
  onCancel: () => void
}) {
  const [nome, setNome] = React.useState(initial.nome)
  React.useEffect(() => setNome(initial.nome), [initial])
  const isDirty = nome.trim() !== initial.nome
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (nome.trim()) onSubmit({ nome: nome.trim() })
      }}
      className="flex flex-col gap-6"
      noValidate
    >
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
          Editar · {initial.nome}
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Use defaults vindos de `initial`. Em forms reais, useEffect +
          reset(defaults) quando trocar de registro selecionado.
        </p>
      </div>
      <Divider />
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="edit-nome">Nome</Label>
        <Input
          id="edit-nome"
          value={nome}
          onChange={(e) => setNome(e.target.value)}
        />
      </div>
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
          disabled={submitting || !isDirty}
        >
          Salvar alteracoes
        </Button>
      </div>
    </form>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// PATTERN
// ───────────────────────────────────────────────────────────────────────────

type Segment = "todos" | "ativos" | "suspensos"

const col = createColumnHelper<FornecedorRow>()

export function ListagemCrudInline() {
  const router = useRouter()
  const sp = useSearchParams()
  const action = sp.get("action") // "new" | null
  const selectedId = sp.get("selected")

  // ── Estado da listagem (mock) ───────────────────────────────────────────
  // SUBSTITUA por React Query: const { data, isLoading, error, refetch } = useFornecedores()
  const [data, setData] = React.useState<FornecedorRow[]>(SAMPLE_DATA)
  const isLoading = false
  const error = null as Error | null

  // ── Filtros locais (search global + segment) ────────────────────────────
  // Para volumes > 200 rows considere mover busca/filtros para server-side
  // (ver tabela "REGRA DE TAMANHO" no topo deste arquivo).
  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState<Segment>("todos")

  // Contagens por segment — alimentam o badge no SegmentSwitch.
  const counts = React.useMemo(
    () => ({
      todos: data.length,
      ativos: data.filter((r) => r.ativo).length,
      suspensos: data.filter((r) => !r.ativo).length,
    }),
    [data],
  )

  // Pre-filtro por segment (search continua via globalFilter do DataTable —
  // TanStack faz filtro fuzzy "includesString" em todas as colunas accessor).
  const segmentFiltered = React.useMemo(() => {
    if (segment === "ativos") return data.filter((r) => r.ativo)
    if (segment === "suspensos") return data.filter((r) => !r.ativo)
    return data
  }, [data, segment])

  // Para o contador "X de Y", calculamos quantos rows passariam tanto pelo
  // segment quanto pela busca (replica a logica `includesString` do TanStack).
  const visibleCount = React.useMemo(() => {
    const term = search.trim().toLowerCase()
    if (!term) return segmentFiltered.length
    return segmentFiltered.filter((r) =>
      Object.values(r).some(
        (v) => typeof v === "string" && v.toLowerCase().includes(term),
      ),
    ).length
  }, [segmentFiltered, search])

  const selected = React.useMemo(
    () => (selectedId ? data.find((p) => p.id === selectedId) ?? null : null),
    [data, selectedId],
  )

  // Confirmacao destrutiva: state local, sem deep-link.
  const [pendingDelete, setPendingDelete] = React.useState<FornecedorRow | null>(
    null,
  )

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
    (p: FornecedorRow) => setQuery({ action: null, selected: p.id }),
    [setQuery],
  )
  const closeSheet = React.useCallback(
    () => setQuery({ action: null, selected: null }),
    [setQuery],
  )

  // ── Handlers de submit ──────────────────────────────────────────────────
  const handleCreate = React.useCallback(
    async (values: { nome: string }) => {
      setCreating(true)
      try {
        // SUBSTITUA: await createMut.mutateAsync(values)
        await new Promise((r) => setTimeout(r, 400))
        const novo: FornecedorRow = {
          id: `f-${String(data.length + 1).padStart(3, "0")}`,
          nome: values.nome,
          categoria: "produto",
          ativo: true,
          created_at: new Date().toISOString(),
        }
        setData((prev) => [novo, ...prev])
        toast.success(`'${values.nome}' cadastrado.`)
        closeSheet()
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : "Falha ao cadastrar.",
        )
      } finally {
        setCreating(false)
      }
    },
    [data.length, closeSheet],
  )

  const handleEdit = React.useCallback(
    async (values: { nome: string }) => {
      if (!selected) return
      setEditing(true)
      try {
        // SUBSTITUA: await updateMut.mutateAsync({ id: selected.id, payload: values })
        await new Promise((r) => setTimeout(r, 400))
        setData((prev) =>
          prev.map((p) =>
            p.id === selected.id ? { ...p, nome: values.nome } : p,
          ),
        )
        toast.success(`'${values.nome}' atualizado.`)
        closeSheet()
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : "Falha ao atualizar.",
        )
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
      // SUBSTITUA: await deleteMut.mutateAsync(pendingDelete.id)
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

  // ── Colunas ─────────────────────────────────────────────────────────────
  const columns = React.useMemo<ColumnDef<FornecedorRow, unknown>[]>(
    () => [
      col.accessor("nome", {
        header: "Nome",
        size: 320,
        cell: (info) => (
          <span className="text-sm text-gray-900 dark:text-gray-100">
            {info.getValue()}
          </span>
        ),
      }) as ColumnDef<FornecedorRow, unknown>,
      col.accessor("categoria", {
        header: "Categoria",
        size: 130,
        cell: (info) => <CategoriaBadge value={info.getValue()} />,
      }) as ColumnDef<FornecedorRow, unknown>,
      col.accessor("ativo", {
        header: "Status",
        size: 110,
        cell: (info) => <AtivoBadge ativo={info.getValue()} />,
      }) as ColumnDef<FornecedorRow, unknown>,
      col.accessor("created_at", {
        header: "Cadastrado em",
        size: 130,
        cell: (info) => <DateCell value={info.getValue()} />,
      }) as ColumnDef<FornecedorRow, unknown>,
      col.display({
        id: "actions",
        header: "",
        size: 56,
        cell: ({ row }) => (
          <div className="flex justify-end">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  className="size-7 p-0"
                  aria-label={`Acoes de ${row.original.nome}`}
                  onClick={(e) => e.stopPropagation()}
                >
                  <RiMoreLine className="size-4" aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" sideOffset={4}>
                <DropdownMenuItem onSelect={() => openEdit(row.original)}>
                  Editar
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onSelect={() => setPendingDelete(row.original)}
                  className="text-red-600 focus:text-red-700 dark:text-red-400 dark:focus:text-red-300"
                >
                  <RiDeleteBinLine className="mr-2 size-4" aria-hidden />
                  Excluir
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ),
      }) as ColumnDef<FornecedorRow, unknown>,
    ],
    [openEdit],
  )

  const isEmpty = !isLoading && !error && data.length === 0

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Fornecedores"
        info="Cadastros administrativos compartilhados com todas as areas."
        subtitle="Cadastros · Gestao"
        actions={
          <Button
            variant="primary"
            onClick={openNew}
            disabled={isLoading}
          >
            <RiAddLine className="mr-1 size-4" aria-hidden />
            Novo fornecedor
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
            <Button variant="secondary" onClick={() => { /* refetch */ }}>
              Tentar novamente
            </Button>
          }
        />
      ) : isEmpty ? (
        <EmptyState
          icon={RiBuildingLine}
          title="Nenhum fornecedor cadastrado"
          description="Cadastre o primeiro para comecar."
          action={
            <Button variant="primary" onClick={openNew}>
              <RiAddLine className="mr-1 size-4" aria-hidden />
              Cadastrar fornecedor
            </Button>
          }
        />
      ) : (
        <Card className="flex flex-col gap-3 p-3">
          {/* Filtros — busca global + segments + contador */}
          <div className="flex flex-wrap items-center gap-2">
            <FilterSearch
              value={search}
              onChange={(e) => setSearch(e.currentTarget.value)}
              onClear={() => setSearch("")}
              placeholder="Buscar por nome..."
            />
            <SegmentSwitch
              options={[
                { value: "todos",     label: "Todos",     count: counts.todos },
                { value: "ativos",    label: "Ativos",    count: counts.ativos },
                { value: "suspensos", label: "Suspensos", count: counts.suspensos },
              ]}
              value={segment}
              onChange={setSegment}
            />
            <span
              className="ml-auto text-[11px] tabular-nums text-gray-500 dark:text-gray-400"
              aria-live="polite"
            >
              {visibleCount === counts.todos
                ? `${visibleCount} ${visibleCount === 1 ? "registro" : "registros"}`
                : `${visibleCount} de ${counts.todos}`}
            </span>
          </div>

          <DataTable
            data={segmentFiltered}
            columns={columns}
            loading={isLoading}
            density="compact"
            virtualize={false}
            showColumnManager={false}
            showDensityToggle={false}
            showExport={false}
            globalFilter={search}
            onRowClick={openEdit}
            renderEmpty={(hasFilters) =>
              hasFilters ? (
                <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
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
                <div className="py-12 text-center text-sm text-gray-500 dark:text-gray-400">
                  Sem registros neste segmento.
                </div>
              )
            }
          />
        </Card>
      )}

      {/* Drawer: Novo */}
      <DrillDownSheet
        open={action === "new"}
        onClose={closeSheet}
        title="Novo fornecedor"
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

      {/* Drawer: Editar */}
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

      {/* Confirmacao destrutiva */}
      <Dialog
        open={pendingDelete !== null}
        onOpenChange={(open) => !open && setPendingDelete(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Excluir fornecedor</DialogTitle>
            <DialogDescription>
              Esta acao remove permanentemente{" "}
              <span className="font-medium text-gray-900 dark:text-gray-50">
                {pendingDelete?.nome}
              </span>
              . Vinculos com pedidos historicos serao preservados, mas o
              registro nao podera mais ser usado em novos cadastros.
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
              Excluir fornecedor
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
