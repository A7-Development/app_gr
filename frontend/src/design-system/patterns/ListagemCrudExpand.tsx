// src/design-system/patterns/ListagemCrudExpand.tsx
//
// PATTERN — Listagem CRUD Expansivel (hierarquica)
// Copy, paste, adapt. Not a black-box component.
//
// Variante hierarquica de `ListagemCrudInline`. Mesmo DNA leve/compacto, mas
// com sub-rows expansiveis via chevron `>`. Use quando os registros tem
// estrutura pai-filho (plano de contas, categorias com sub-categorias,
// hierarquia organizacional, etc).
//
// Composes:
//   PageHeader (com botao "+ Novo X")
//   ↓
//   EmptyState | ErrorState | Card > [FilterSearch + Segments + Contador] > DataTable (expand)
//   ↓
//   DrillDownSheet (criar root | criar sub) — abre via ?action=new&parent=<id?>
//   DrillDownSheet (editar) — abre via ?selected=<id>
//   Dialog destrutivo (excluir) — bloqueia se nó tem filhos
//
// Defaults adotados (todos sao escolhas opinativas — adapte se precisar):
//   • Filtragem: PAI PERSISTE se algum descendente match. Auto-expand quando
//     ha busca ativa (UX: nao perde contexto, ve onde o resultado esta).
//   • Criar sub-item: opcao "+ Adicionar sub-item" no DropdownMenu de cada
//     row (alem do "+ Novo X" do PageHeader que cria item raiz).
//   • Excluir pai com filhos: BLOQUEIA com mensagem clara ("remova primeiro
//     os N sub-itens"). Mais seguro que cascade silencioso.
//   • Counts no SegmentSwitch: CONTA FOLHAS (X ativos = X folhas ativas;
//     nos pai sao agrupadores, nao itens contaveis).
//   • Default expand: COLAPSADO (menos poluido na primeira renderizacao).
//   • Chevron: `>` (texto mono, rotaciona 90° quando expandido). Padrao da
//     DataTable canonica.
//
// REGRA DE TAMANHO: igual a `ListagemCrudInline`. Para arvores grandes
// (>2000 nos no total), considere lazy-load de subRows por demanda.
//
// HOW TO ADAPT:
//   1. Troque `ContaRow` pelo seu tipo de dominio. Mantenha o campo
//      `subRows?: Hierarchical<...>[]` para o getSubRows funcionar.
//   2. Troque SAMPLE_DATA por um hook React Query que devolve a arvore
//      ja montada (preferivel) OU uma lista flat com `parent_id` e
//      monte a arvore client-side.
//   3. Substitua os 3 hooks de mutacao (create/update/delete).
//   4. Para criacao de sub-item, o handler recebe o `parent_id` no payload.
//
// URL state:
//   ?action=new                → drawer de criacao raiz
//   ?action=new&parent=<id>    → drawer de criacao de sub-item
//   ?selected=<id>             → drawer de edicao

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"
import {
  RiAddLine,
  RiDeleteBinLine,
  RiFolderOpenLine,
  RiMoreLine,
  RiNodeTree,
} from "@remixicon/react"
import { type ColumnDef, type ExpandedState, createColumnHelper } from "@tanstack/react-table"

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
// TIPOS DE DOMINIO — troque pelo seu (tipo recursivo via subRows)
// ───────────────────────────────────────────────────────────────────────────

/** Genérico: aninha qualquer tipo via campo `subRows`. */
export type Hierarchical<T> = T & { subRows?: Hierarchical<T>[] }

export type ContaRow = Hierarchical<{
  id: string
  codigo: string                  // ex.: "1.1.2.80.00.001"
  nome: string                    // ex.: "BANCOS CONTA MOVIMENTO"
  ativo: boolean
  created_at: string
}>

const SAMPLE_DATA: ContaRow[] = [
  {
    id: "c-1",
    codigo: "1.1",
    nome: "DISPONIBILIDADES",
    ativo: true,
    created_at: "2026-01-10T10:00:00Z",
    subRows: [
      {
        id: "c-1.1",
        codigo: "1.1.2",
        nome: "DEPÓSITOS BANCÁRIOS",
        ativo: true,
        created_at: "2026-01-10T10:00:00Z",
        subRows: [
          {
            id: "c-1.1.1",
            codigo: "1.1.2.80.00.002",
            nome: "BANCO BRADESCO S/A",
            ativo: true,
            created_at: "2026-01-12T08:30:00Z",
          },
          {
            id: "c-1.1.2",
            codigo: "1.1.2.80.00.007",
            nome: "SINGULARE CORRETORA",
            ativo: true,
            created_at: "2026-01-15T09:45:00Z",
          },
          {
            id: "c-1.1.3",
            codigo: "1.1.2.80.00.001",
            nome: "BANCOS CONTA MOVIMENTO",
            ativo: false,
            created_at: "2026-02-08T14:20:00Z",
          },
        ],
      },
    ],
  },
  {
    id: "c-2",
    codigo: "1.2",
    nome: "APLICAÇÕES INTERFINANCEIRAS DE LIQUIDEZ",
    ativo: true,
    created_at: "2026-01-20T11:15:00Z",
    subRows: [
      {
        id: "c-2.1",
        codigo: "1.2.1.10.05",
        nome: "LETRAS DO TESOURO NACIONAL",
        ativo: true,
        created_at: "2026-01-20T11:15:00Z",
      },
    ],
  },
  {
    id: "c-3",
    codigo: "1.3",
    nome: "TÍTULOS E VALORES MOBILIÁRIOS",
    ativo: true,
    created_at: "2026-02-01T15:00:00Z",
    subRows: [
      {
        id: "c-3.1",
        codigo: "1.3.1.10.07",
        nome: "NOTAS DO TESOURO NACIONAL",
        ativo: true,
        created_at: "2026-02-01T15:00:00Z",
      },
      {
        id: "c-3.2",
        codigo: "1.3.1.10.16.001",
        nome: "NOTA COMERCIAL",
        ativo: true,
        created_at: "2026-02-04T10:30:00Z",
      },
      {
        id: "c-3.3",
        codigo: "1.3.1.15.30",
        nome: "COTAS DE FUNDOS MÚTUOS",
        ativo: false,
        created_at: "2026-02-12T13:45:00Z",
      },
    ],
  },
]

// ───────────────────────────────────────────────────────────────────────────
// CELLS CUSTOM
// ───────────────────────────────────────────────────────────────────────────

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
      {ativo ? "Ativo" : "Suspenso"}
    </span>
  )
}

function CosifMono({ value }: { value: string }) {
  return (
    <span className="font-mono text-[11px] text-gray-500 dark:text-gray-400">
      {value}
    </span>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// HELPERS — operacoes recursivas sobre arvore
// ───────────────────────────────────────────────────────────────────────────

/** Retorna apenas as folhas (nos sem subRows ou com subRows vazio). */
function flattenLeaves<T extends { subRows?: T[] }>(rows: T[]): T[] {
  const out: T[] = []
  const walk = (nodes: T[]) => {
    for (const n of nodes) {
      if (!n.subRows || n.subRows.length === 0) {
        out.push(n)
      } else {
        walk(n.subRows)
      }
    }
  }
  walk(rows)
  return out
}

/** Conta total de descendentes (filhos + netos + ...). */
function countDescendants<T extends { subRows?: T[] }>(node: T): number {
  if (!node.subRows || node.subRows.length === 0) return 0
  let total = node.subRows.length
  for (const child of node.subRows) total += countDescendants(child)
  return total
}

/** Filtra arvore mantendo um no se ele OU algum descendente match.
    Retorna nova arvore — nos pais com matches descendentes ficam visiveis. */
function filterTree<T extends { subRows?: T[] }>(
  rows: T[],
  predicate: (node: T) => boolean,
): T[] {
  const out: T[] = []
  for (const n of rows) {
    const filteredChildren = n.subRows ? filterTree(n.subRows, predicate) : undefined
    const selfMatch = predicate(n)
    if (selfMatch || (filteredChildren && filteredChildren.length > 0)) {
      out.push({ ...n, subRows: filteredChildren && filteredChildren.length > 0 ? filteredChildren : undefined })
    }
  }
  return out
}

/** Devolve set com TODOS os ids da arvore — usado pra expandir tudo quando
    ha busca ativa (mostra os caminhos que matcharam). */
function allIds<T extends { id: string; subRows?: T[] }>(rows: T[]): Record<string, true> {
  const out: Record<string, true> = {}
  const walk = (nodes: T[]) => {
    for (const n of nodes) {
      out[n.id] = true
      if (n.subRows) walk(n.subRows)
    }
  }
  walk(rows)
  return out
}

/** Acha um no por id na arvore. */
function findNode<T extends { id: string; subRows?: T[] }>(
  rows: T[],
  id: string,
): T | null {
  for (const n of rows) {
    if (n.id === id) return n
    if (n.subRows) {
      const found = findNode(n.subRows, id)
      if (found) return found
    }
  }
  return null
}

/** Aplica uma transformacao em UM no (por id), mantendo a arvore imutavel. */
function mapNode<T extends { id: string; subRows?: T[] }>(
  rows: T[],
  id: string,
  fn: (node: T) => T,
): T[] {
  return rows.map((n) => {
    if (n.id === id) return fn(n)
    if (n.subRows) {
      const newChildren = mapNode(n.subRows, id, fn)
      if (newChildren !== n.subRows) return { ...n, subRows: newChildren }
    }
    return n
  })
}

/** Remove um no da arvore por id. Retorna nova arvore. */
function removeNode<T extends { id: string; subRows?: T[] }>(
  rows: T[],
  id: string,
): T[] {
  return rows
    .filter((n) => n.id !== id)
    .map((n) => {
      if (n.subRows) {
        const newChildren = removeNode(n.subRows, id)
        if (newChildren !== n.subRows) return { ...n, subRows: newChildren }
      }
      return n
    })
}

// ───────────────────────────────────────────────────────────────────────────
// FORMS MOCK — troque pelos seus reais (react-hook-form + zod)
// ───────────────────────────────────────────────────────────────────────────

function MockCreateForm({
  parentNome,
  submitting,
  onSubmit,
  onCancel,
}: {
  parentNome:  string | null    // null = item raiz; string = sub-item de X
  submitting:  boolean
  onSubmit:    (values: { codigo: string; nome: string }) => void
  onCancel:    () => void
}) {
  const [codigo, setCodigo] = React.useState("")
  const [nome, setNome] = React.useState("")
  const valid = codigo.trim().length > 0 && nome.trim().length > 0
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (valid) onSubmit({ codigo: codigo.trim(), nome: nome.trim() })
      }}
      className="flex flex-col gap-6"
      noValidate
    >
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
          {parentNome ? `Novo sub-item em "${parentNome}"` : "Nova conta raiz"}
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Substitua este form pelo seu (react-hook-form + zod, primitivos
          Tremor).
        </p>
      </div>
      <Divider />
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="codigo">
            Código COSIF
            <span className="ml-1 text-red-600 dark:text-red-500" aria-hidden>*</span>
          </Label>
          <Input
            id="codigo"
            placeholder="Ex.: 1.1.2.80.00.003"
            value={codigo}
            onChange={(e) => setCodigo(e.target.value)}
            autoFocus
          />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="nome">
            Nome
            <span className="ml-1 text-red-600 dark:text-red-500" aria-hidden>*</span>
          </Label>
          <Input
            id="nome"
            placeholder="Ex.: BANCO ITAÚ S.A."
            value={nome}
            onChange={(e) => setNome(e.target.value)}
          />
        </div>
      </div>
      <Divider />
      <div className="flex items-center justify-end gap-2">
        <Button type="button" variant="secondary" onClick={onCancel} disabled={submitting}>
          Cancelar
        </Button>
        <Button type="submit" variant="primary" disabled={submitting || !valid}>
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
  initial:    ContaRow
  submitting: boolean
  onSubmit:   (values: { codigo: string; nome: string }) => void
  onCancel:   () => void
}) {
  const [codigo, setCodigo] = React.useState(initial.codigo)
  const [nome, setNome]     = React.useState(initial.nome)
  React.useEffect(() => {
    setCodigo(initial.codigo)
    setNome(initial.nome)
  }, [initial])
  const isDirty =
    codigo.trim() !== initial.codigo || nome.trim() !== initial.nome
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        if (isDirty) onSubmit({ codigo: codigo.trim(), nome: nome.trim() })
      }}
      className="flex flex-col gap-6"
      noValidate
    >
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
          Editar · {initial.nome}
        </h2>
      </div>
      <Divider />
      <div className="flex flex-col gap-3">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="edit-codigo">Código</Label>
          <Input id="edit-codigo" value={codigo} onChange={(e) => setCodigo(e.target.value)} />
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="edit-nome">Nome</Label>
          <Input id="edit-nome" value={nome} onChange={(e) => setNome(e.target.value)} />
        </div>
      </div>
      <Divider />
      <div className="flex items-center justify-end gap-2">
        <Button type="button" variant="secondary" onClick={onCancel} disabled={submitting}>
          Cancelar
        </Button>
        <Button type="submit" variant="primary" disabled={submitting || !isDirty}>
          Salvar alterações
        </Button>
      </div>
    </form>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// PATTERN
// ───────────────────────────────────────────────────────────────────────────

type Segment = "todos" | "ativos" | "suspensos"

const col = createColumnHelper<ContaRow>()

export function ListagemCrudExpand() {
  const router = useRouter()
  const sp = useSearchParams()
  const action     = sp.get("action")     // "new" | null
  const parentId   = sp.get("parent")     // id do pai (sub-item) | null
  const selectedId = sp.get("selected")

  // ── Estado da listagem (mock) ───────────────────────────────────────────
  // SUBSTITUA por React Query: const { data, isLoading, error } = useContas()
  const [data, setData] = React.useState<ContaRow[]>(SAMPLE_DATA)
  const isLoading = false
  const error = null as Error | null

  // ── Filtros locais ──────────────────────────────────────────────────────
  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState<Segment>("todos")
  // Estado de expand (controlado p/ permitir auto-expand quando ha busca).
  const [expanded, setExpanded] = React.useState<ExpandedState>({})

  // ── Filtragem hierarquica ───────────────────────────────────────────────
  // Predicado combina segment + busca em codigo/nome. Pai persiste se algum
  // descendente match (ver `filterTree`).
  const filteredData = React.useMemo(() => {
    const term = search.trim().toLowerCase()
    return filterTree(data, (n) => {
      // Segment
      if (segment === "ativos" && !n.ativo) return false
      if (segment === "suspensos" && n.ativo) return false
      // Search
      if (!term) return true
      return (
        n.codigo.toLowerCase().includes(term) ||
        n.nome.toLowerCase().includes(term)
      )
    })
  }, [data, segment, search])

  // Quando ha busca ativa, auto-expandir tudo pra mostrar caminhos que
  // matcharam. Quando o usuario limpa, volta ao colapsado.
  React.useEffect(() => {
    if (search.trim().length > 0) {
      setExpanded(allIds(filteredData))
    } else {
      setExpanded({})
    }
  }, [search, filteredData])

  // Counts no SegmentSwitch — contam apenas FOLHAS (nos com sub_rows sao
  // agrupadores, nao itens contaveis no contexto de "ativos / suspensos").
  const counts = React.useMemo(() => {
    const leaves = flattenLeaves(data)
    return {
      todos:     leaves.length,
      ativos:    leaves.filter((r) => r.ativo).length,
      suspensos: leaves.filter((r) => !r.ativo).length,
    }
  }, [data])

  const visibleCount = React.useMemo(
    () => flattenLeaves(filteredData).length,
    [filteredData],
  )

  // ── Selecao e delete ────────────────────────────────────────────────────
  const selected = React.useMemo(
    () => (selectedId ? findNode(data, selectedId) : null),
    [data, selectedId],
  )
  const parentForCreate = React.useMemo(
    () => (parentId ? findNode(data, parentId) : null),
    [data, parentId],
  )

  const [pendingDelete, setPendingDelete] = React.useState<ContaRow | null>(null)
  const [creating,  setCreating]  = React.useState(false)
  const [editing,   setEditing]   = React.useState(false)
  const [deleting,  setDeleting]  = React.useState(false)

  // ── Navegacao via URL ───────────────────────────────────────────────────
  const setQuery = React.useCallback(
    (next: { action?: string | null; selected?: string | null; parent?: string | null }) => {
      const params = new URLSearchParams(sp.toString())
      if (next.action !== undefined) {
        if (next.action) params.set("action", next.action)
        else params.delete("action")
      }
      if (next.selected !== undefined) {
        if (next.selected) params.set("selected", next.selected)
        else params.delete("selected")
      }
      if (next.parent !== undefined) {
        if (next.parent) params.set("parent", next.parent)
        else params.delete("parent")
      }
      const qs = params.toString()
      router.push(qs ? `?${qs}` : "?")
    },
    [router, sp],
  )

  const openNewRoot = React.useCallback(
    () => setQuery({ action: "new", selected: null, parent: null }),
    [setQuery],
  )
  const openNewSub = React.useCallback(
    (parent: ContaRow) => setQuery({ action: "new", parent: parent.id, selected: null }),
    [setQuery],
  )
  const openEdit = React.useCallback(
    (n: ContaRow) => setQuery({ action: null, parent: null, selected: n.id }),
    [setQuery],
  )
  const closeSheet = React.useCallback(
    () => setQuery({ action: null, parent: null, selected: null }),
    [setQuery],
  )

  // ── Handlers de submit ──────────────────────────────────────────────────
  const handleCreate = React.useCallback(
    async (values: { codigo: string; nome: string }) => {
      setCreating(true)
      try {
        // SUBSTITUA: await createMut.mutateAsync({ ...values, parent_id: parentForCreate?.id })
        await new Promise((r) => setTimeout(r, 400))
        const novo: ContaRow = {
          id: `c-${Date.now()}`,
          codigo: values.codigo,
          nome:   values.nome,
          ativo:  true,
          created_at: new Date().toISOString(),
        }
        if (parentForCreate) {
          // Anexa como filho do parent
          setData((prev) =>
            mapNode(prev, parentForCreate.id, (p) => ({
              ...p,
              subRows: [...(p.subRows ?? []), novo],
            })),
          )
        } else {
          // Item raiz
          setData((prev) => [novo, ...prev])
        }
        toast.success(
          parentForCreate
            ? `'${values.nome}' adicionado em '${parentForCreate.nome}'.`
            : `'${values.nome}' cadastrado.`,
        )
        closeSheet()
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Falha ao cadastrar.")
      } finally {
        setCreating(false)
      }
    },
    [parentForCreate, closeSheet],
  )

  const handleEdit = React.useCallback(
    async (values: { codigo: string; nome: string }) => {
      if (!selected) return
      setEditing(true)
      try {
        // SUBSTITUA: await updateMut.mutateAsync({ id: selected.id, payload: values })
        await new Promise((r) => setTimeout(r, 400))
        setData((prev) => mapNode(prev, selected.id, (n) => ({ ...n, ...values })))
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
    // Defesa: nao deixa excluir pai com filhos.
    if (pendingDelete.subRows && pendingDelete.subRows.length > 0) {
      toast.error(
        `Não é possível excluir '${pendingDelete.nome}' porque ele tem ${countDescendants(pendingDelete)} sub-itens. Remova os sub-itens primeiro.`,
      )
      setPendingDelete(null)
      return
    }
    setDeleting(true)
    try {
      // SUBSTITUA: await deleteMut.mutateAsync(pendingDelete.id)
      await new Promise((r) => setTimeout(r, 400))
      setData((prev) => removeNode(prev, pendingDelete.id))
      toast.success(`'${pendingDelete.nome}' excluído.`)
      setPendingDelete(null)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao excluir.")
    } finally {
      setDeleting(false)
    }
  }, [pendingDelete])

  // ── Colunas ─────────────────────────────────────────────────────────────
  const columns = React.useMemo<ColumnDef<ContaRow, unknown>[]>(
    () => [
      // 1ª coluna — recebe o chevron via `expandedColumnId="codigo"`
      col.accessor("codigo", {
        id: "codigo",
        header: "Código",
        size: 220,
        cell: (info) => <CosifMono value={info.getValue()} />,
      }) as ColumnDef<ContaRow, unknown>,
      col.accessor("nome", {
        header: "Nome",
        size: 360,
        cell: (info) => {
          const isSubItem = info.row.depth > 0
          return (
            <span
              className={cx(
                "text-sm",
                isSubItem
                  ? "text-gray-500 dark:text-gray-400"
                  : "text-gray-900 dark:text-gray-100",
              )}
            >
              {info.getValue()}
            </span>
          )
        },
      }) as ColumnDef<ContaRow, unknown>,
      col.accessor("ativo", {
        header: "Status",
        size: 110,
        cell: (info) => <AtivoBadge ativo={info.getValue()} />,
      }) as ColumnDef<ContaRow, unknown>,
      col.accessor("created_at", {
        header: "Cadastrado em",
        size: 130,
        cell: (info) => <DateCell value={info.getValue()} />,
      }) as ColumnDef<ContaRow, unknown>,
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
                  aria-label={`Ações de ${row.original.nome}`}
                  onClick={(e) => e.stopPropagation()}
                >
                  <RiMoreLine className="size-4" aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" sideOffset={4}>
                <DropdownMenuItem onSelect={() => openEdit(row.original)}>
                  Editar
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => openNewSub(row.original)}>
                  <RiAddLine className="mr-2 size-4" aria-hidden />
                  Adicionar sub-item
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
      }) as ColumnDef<ContaRow, unknown>,
    ],
    [openEdit, openNewSub],
  )

  const isEmpty = !isLoading && !error && data.length === 0
  const hasBlockingChildren =
    pendingDelete?.subRows && pendingDelete.subRows.length > 0

  // ── Render ──────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Plano de Contas"
        info="Estrutura hierárquica de contas contábeis (COSIF). Sub-itens expansíveis."
        subtitle="Cadastros · Contábil"
        actions={
          <Button variant="primary" onClick={openNewRoot} disabled={isLoading}>
            <RiAddLine className="mr-1 size-4" aria-hidden />
            Nova conta raiz
          </Button>
        }
      />

      {error ? (
        <ErrorState
          title="Falha ao carregar registros"
          description={
            error instanceof Error
              ? error.message
              : "Verifique sua conexão e tente novamente."
          }
          action={
            <Button variant="secondary" onClick={() => { /* refetch */ }}>
              Tentar novamente
            </Button>
          }
        />
      ) : isEmpty ? (
        <EmptyState
          icon={RiNodeTree}
          title="Nenhuma conta cadastrada"
          description="Cadastre a primeira conta raiz para começar."
          action={
            <Button variant="primary" onClick={openNewRoot}>
              <RiAddLine className="mr-1 size-4" aria-hidden />
              Cadastrar conta
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
              placeholder="Buscar por código ou nome..."
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
                ? `${visibleCount} ${visibleCount === 1 ? "folha" : "folhas"}`
                : `${visibleCount} de ${counts.todos}`}
            </span>
          </div>

          <DataTable
            data={filteredData}
            columns={columns}
            loading={isLoading}
            density="compact"
            virtualize={false}
            showColumnManager={false}
            showDensityToggle={false}
            showExport={false}
            // — Hierarquia (DataTable canonica ja suporta)
            enableExpanding
            getSubRows={(row) => row.subRows}
            defaultExpanded={{}}
            expandedColumnId="codigo"
            // estado controlado externamente pra auto-expand quando ha busca
            // (via React.useEffect acima — DataTable continua o owner do
            //  toggle individual via onExpandedChange interno)
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

      {/* Drawer: Novo (raiz ou sub-item) */}
      <DrillDownSheet
        open={action === "new"}
        onClose={closeSheet}
        title={
          parentForCreate
            ? `Novo sub-item · ${parentForCreate.nome}`
            : "Nova conta raiz"
        }
        size="md"
      >
        <div className="p-6">
          <MockCreateForm
            parentNome={parentForCreate?.nome ?? null}
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
            <DialogTitle>
              {hasBlockingChildren ? "Não é possível excluir" : "Excluir conta"}
            </DialogTitle>
            <DialogDescription>
              {hasBlockingChildren ? (
                <>
                  <span className="font-medium text-gray-900 dark:text-gray-50">
                    {pendingDelete?.nome}
                  </span>{" "}
                  tem{" "}
                  <span className="font-medium text-gray-900 dark:text-gray-50">
                    {pendingDelete ? countDescendants(pendingDelete) : 0}{" "}
                    sub-itens
                  </span>
                  . Remova ou mova os sub-itens antes de excluir esta conta.
                </>
              ) : (
                <>
                  Esta ação remove permanentemente{" "}
                  <span className="font-medium text-gray-900 dark:text-gray-50">
                    {pendingDelete?.nome}
                  </span>
                  . Lançamentos históricos vinculados serão preservados, mas a
                  conta não poderá mais ser usada em novos registros.
                </>
              )}
            </DialogDescription>
          </DialogHeader>
          <Divider />
          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => setPendingDelete(null)}
              disabled={deleting}
            >
              {hasBlockingChildren ? "Entendi" : "Cancelar"}
            </Button>
            {!hasBlockingChildren && (
              <Button
                variant="destructive"
                onClick={handleDelete}
                disabled={deleting}
              >
                <RiDeleteBinLine className="mr-1.5 size-4" aria-hidden />
                Excluir conta
              </Button>
            )}
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Helper visual: folder icon — não usado direto, mas mantém import
         "vivo" caso futuras adicoes precisem (ex.: ícone no PageHeader subtitle).
         Manter ou remover ao adaptar. */}
      <span className="hidden">
        <RiFolderOpenLine />
      </span>
    </div>
  )
}
