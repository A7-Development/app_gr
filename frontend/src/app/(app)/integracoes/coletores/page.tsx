// src/app/(app)/integracoes/coletores/page.tsx
//
// Integracoes · Coletores (Strata Collector).
//
// Gestao das credenciais dos agentes de coleta instalados nos servidores dos
// clientes: criar (token exibido UMA vez), editar watch_config (pastas ->
// esteiras), rotacionar token e revogar. Backend protege com
// require_module(INTEGRACOES, ADMIN).
//
// Pattern: ListagemCrudInline (mesma anatomia de /admin/ia/providers).
// Estado da URL (deep-linkavel):
//   ?action=new            → drawer de criacao
//   ?selected=<uuid>       → drawer de edicao do coletor selecionado
//

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import {
  RiAddLine,
  RiForbidLine,
  RiKey2Line,
  RiMoreLine,
  RiUploadCloud2Line,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import { formatDistanceToNow, parseISO } from "date-fns"
import { ptBR } from "date-fns/locale"
import { toast } from "sonner"

import { Button } from "@/components/tremor/Button"
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
import {
  DataTableShell,
  DateCell,
  DrillDownSheet,
  PageHeader,
} from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type { ColetorRead } from "@/lib/api-client"
import {
  useColetores,
  useCreateColetor,
  useRevokeColetor,
  useRotateColetor,
  useUpdateColetor,
} from "@/lib/hooks/coletores"
import {
  COLETOR_FORM_DEFAULTS,
  fromColetor,
  toCreatePayload,
  toWatchConfig,
  type ColetorFormValues,
} from "@/lib/schemas/coletor-schema"
import { cx } from "@/lib/utils"

import { ColetorForm } from "./_components/ColetorForm"
import { TokenDialog } from "./_components/TokenDialog"

// ───────────────────────────────────────────────────────────────────────────
// Cells
// ───────────────────────────────────────────────────────────────────────────

function StatusBadge({ coletor }: { coletor: ColetorRead }) {
  const revoked = coletor.revoked_at !== null
  return (
    <span
      className={cx(
        tableTokens.badge,
        revoked ? tableTokens.badgeDanger : tableTokens.badgeSuccess,
      )}
    >
      {revoked ? "Revogado" : "Ativo"}
    </span>
  )
}

// Heartbeat: verde = visto ha pouco (agente saudavel), amber = atrasado,
// cinza = nunca conectou. Limiar generoso (15 min) sobre o intervalo default.
function HeartbeatCell({ value }: { value: string | null }) {
  if (!value) {
    return <span className={tableTokens.cellMuted}>nunca conectou</span>
  }
  const seen = parseISO(value)
  const ageMin = (Date.now() - seen.getTime()) / 60_000
  const dot =
    ageMin <= 15 ? "bg-emerald-500" : ageMin <= 24 * 60 ? "bg-amber-500" : "bg-gray-400"
  return (
    <span className={cx(tableTokens.cellSecondary, "inline-flex items-center gap-1.5")} title={value}>
      <span aria-hidden className={cx("size-1.5 shrink-0 rounded-full", dot)} />
      {formatDistanceToNow(seen, { addSuffix: true, locale: ptBR })}
    </span>
  )
}

function WatchesCell({ coletor }: { coletor: ColetorRead }) {
  const watches = coletor.watch_config?.watches ?? []
  if (watches.length === 0) {
    return <span className={tableTokens.cellMuted}>nenhuma pasta</span>
  }
  const labels = watches.map((w) => w.source_label).join(", ")
  return (
    <span className={tableTokens.cellText} title={labels}>
      {watches.length} pasta{watches.length > 1 ? "s" : ""}
      <span className={cx(tableTokens.cellSecondary, "ml-1.5")}>{labels}</span>
    </span>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

const col = createColumnHelper<ColetorRead>()

export default function ColetoresPage() {
  const router = useRouter()
  const sp = useSearchParams()
  const action = sp.get("action") // "new" | null
  const selectedId = sp.get("selected")

  const coletoresQuery = useColetores()
  const createMut = useCreateColetor()
  const updateMut = useUpdateColetor()
  const rotateMut = useRotateColetor()
  const revokeMut = useRevokeColetor()

  const data = coletoresQuery.data ?? []
  const selected = React.useMemo(
    () => (selectedId ? (data.find((c) => c.id === selectedId) ?? null) : null),
    [data, selectedId],
  )

  // Token exibido uma unica vez (create/rotate) — estado local, nunca na URL.
  const [revealedToken, setRevealedToken] = React.useState<{
    token: string
    name: string
  } | null>(null)
  // Confirmacoes destrutivas/sensiveis — estado local (operacao efemera).
  const [pendingRevoke, setPendingRevoke] = React.useState<ColetorRead | null>(null)
  const [pendingRotate, setPendingRotate] = React.useState<ColetorRead | null>(null)

  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState<"todos" | "ativos" | "revogados">(
    "todos",
  )

  // ── Navigation helpers ────────────────────────────────────────────────────
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
    (c: ColetorRead) => setQuery({ action: null, selected: c.id }),
    [setQuery],
  )
  const closeSheet = React.useCallback(
    () => setQuery({ action: null, selected: null }),
    [setQuery],
  )

  // ── Handlers ──────────────────────────────────────────────────────────────
  const handleCreate = React.useCallback(
    async (values: ColetorFormValues) => {
      try {
        const created = await createMut.mutateAsync(toCreatePayload(values))
        toast.success(`Coletor '${created.name}' criado.`)
        closeSheet()
        setRevealedToken({ token: created.token, name: created.name })
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Falha ao criar coletor.")
      }
    },
    [createMut, closeSheet],
  )

  const handleEdit = React.useCallback(
    async (values: ColetorFormValues) => {
      if (!selected) return
      try {
        await updateMut.mutateAsync({
          id: selected.id,
          payload: {
            name: values.name.trim(),
            watch_config: toWatchConfig(values),
          },
        })
        toast.success(`Coletor '${values.name}' atualizado.`)
        closeSheet()
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : "Falha ao atualizar coletor.",
        )
      }
    },
    [updateMut, selected, closeSheet],
  )

  const handleRotate = React.useCallback(async () => {
    if (!pendingRotate) return
    try {
      const rotated = await rotateMut.mutateAsync(pendingRotate.id)
      toast.success(`Novo token gerado para '${rotated.name}'.`)
      setPendingRotate(null)
      setRevealedToken({ token: rotated.token, name: rotated.name })
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao gerar token.")
    }
  }, [rotateMut, pendingRotate])

  const handleRevoke = React.useCallback(async () => {
    if (!pendingRevoke) return
    try {
      await revokeMut.mutateAsync(pendingRevoke.id)
      toast.success(`Coletor '${pendingRevoke.name}' revogado.`)
      setPendingRevoke(null)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao revogar coletor.")
    }
  }, [revokeMut, pendingRevoke])

  // ── Columns ───────────────────────────────────────────────────────────────
  const columns = React.useMemo<ColumnDef<ColetorRead, unknown>[]>(
    () => [
      col.accessor("name", {
        header: "Coletor",
        size: 200,
        cell: (info) => (
          <span className={tableTokens.cellStrong}>{info.getValue()}</span>
        ),
      }) as ColumnDef<ColetorRead, unknown>,
      col.display({
        id: "watches",
        header: "Pastas / esteiras",
        size: 260,
        cell: ({ row }) => <WatchesCell coletor={row.original} />,
      }) as ColumnDef<ColetorRead, unknown>,
      col.display({
        id: "status",
        header: "Status",
        size: 100,
        cell: ({ row }) => <StatusBadge coletor={row.original} />,
      }) as ColumnDef<ColetorRead, unknown>,
      col.accessor("last_seen_at", {
        header: "Ultimo contato",
        size: 150,
        cell: (info) => <HeartbeatCell value={info.getValue()} />,
      }) as ColumnDef<ColetorRead, unknown>,
      col.accessor("agent_version", {
        header: "Versao",
        size: 80,
        cell: (info) => {
          const v = info.getValue()
          return v ? (
            <span className={tableTokens.cellTextMono}>{v}</span>
          ) : (
            <span className={tableTokens.cellMuted}>—</span>
          )
        },
      }) as ColumnDef<ColetorRead, unknown>,
      col.accessor("arquivos_total", {
        header: "Arquivos",
        size: 90,
        cell: (info) => (
          <span className={tableTokens.cellNumber}>
            {info.getValue().toLocaleString("pt-BR")}
          </span>
        ),
      }) as ColumnDef<ColetorRead, unknown>,
      col.accessor("created_at", {
        header: "Criado em",
        size: 110,
        cell: (info) => <DateCell value={info.getValue()} />,
      }) as ColumnDef<ColetorRead, unknown>,
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
                  aria-label={`Acoes de ${row.original.name}`}
                  onClick={(e) => e.stopPropagation()}
                >
                  <RiMoreLine className="size-4" aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" sideOffset={4}>
                <DropdownMenuItem onSelect={() => openEdit(row.original)}>
                  Editar
                </DropdownMenuItem>
                <DropdownMenuItem onSelect={() => setPendingRotate(row.original)}>
                  <RiKey2Line className="mr-2 size-4" aria-hidden />
                  {row.original.revoked_at
                    ? "Reativar com token novo"
                    : "Gerar novo token"}
                </DropdownMenuItem>
                {row.original.revoked_at === null && (
                  <>
                    <DropdownMenuSeparator />
                    <DropdownMenuItem
                      onSelect={() => setPendingRevoke(row.original)}
                      className="text-red-600 focus:text-red-700 dark:text-red-400 dark:focus:text-red-300"
                    >
                      <RiForbidLine className="mr-2 size-4" aria-hidden />
                      Revogar acesso
                    </DropdownMenuItem>
                  </>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ),
      }) as ColumnDef<ColetorRead, unknown>,
    ],
    [openEdit],
  )

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Coletores"
        info="Agentes Strata Collector instalados nos servidores dos clientes. Cada coletor autentica com um token proprio e recebe daqui a lista de pastas a vigiar — mudar a configuracao nao exige tocar na maquina do cliente."
        subtitle="Integracoes · Arquivos"
        actions={
          <Button
            variant="primary"
            onClick={openNew}
            disabled={coletoresQuery.isLoading}
          >
            <RiAddLine className="mr-1 size-4" aria-hidden />
            Novo coletor
          </Button>
        }
      />

      <DataTableShell<ColetorRead>
        data={data}
        columns={columns}
        loading={coletoresQuery.isLoading}
        error={coletoresQuery.error}
        onRetry={() => coletoresQuery.refetch()}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: "Buscar por nome ou esteira...",
        }}
        segments={{
          value: segment,
          onChange: (v) => setSegment(v as typeof segment),
          options: [
            { value: "todos", label: "Todos", filter: () => true },
            { value: "ativos", label: "Ativos", filter: (c) => c.revoked_at === null },
            {
              value: "revogados",
              label: "Revogados",
              filter: (c) => c.revoked_at !== null,
            },
          ],
        }}
        itemNoun={{ singular: "coletor", plural: "coletores" }}
        onRowClick={openEdit}
        emptyState={{
          icon: RiUploadCloud2Line,
          title: "Nenhum coletor cadastrado",
          description:
            "Crie o primeiro coletor para gerar o token usado pelo instalador do Strata Collector no servidor do cliente.",
          action: (
            <Button variant="primary" onClick={openNew}>
              <RiAddLine className="mr-1 size-4" aria-hidden />
              Criar coletor
            </Button>
          ),
        }}
      />

      {/* Drawer: Novo */}
      <DrillDownSheet
        open={action === "new"}
        onClose={closeSheet}
        title="Novo coletor"
        size="md"
      >
        <div className="p-6">
          <ColetorForm
            initial={COLETOR_FORM_DEFAULTS}
            submitting={createMut.isPending}
            submitLabel="Criar e gerar token"
            onSubmit={handleCreate}
            onCancel={closeSheet}
          />
        </div>
      </DrillDownSheet>

      {/* Drawer: Editar */}
      <DrillDownSheet
        open={selected !== null}
        onClose={closeSheet}
        title={selected ? `Editar · ${selected.name}` : ""}
        size="md"
      >
        {selected && (
          <div className="p-6">
            <ColetorForm
              key={selected.id}
              initial={fromColetor(selected)}
              submitting={updateMut.isPending}
              submitLabel="Salvar alteracoes"
              onSubmit={handleEdit}
              onCancel={closeSheet}
            />
          </div>
        )}
      </DrillDownSheet>

      {/* Token exibido uma unica vez */}
      <TokenDialog
        token={revealedToken?.token ?? null}
        coletorName={revealedToken?.name ?? ""}
        onClose={() => setRevealedToken(null)}
      />

      {/* Confirmacao: gerar novo token */}
      <Dialog
        open={pendingRotate !== null}
        onOpenChange={(open) => !open && setPendingRotate(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {pendingRotate?.revoked_at
                ? "Reativar com token novo"
                : "Gerar novo token"}
            </DialogTitle>
            <DialogDescription>
              O token atual de{" "}
              <span className="font-medium text-gray-900 dark:text-gray-50">
                {pendingRotate?.name}
              </span>{" "}
              deixa de funcionar imediatamente — o agente instalado ficara
              offline ate o novo token ser configurado na maquina
              (reinstalacao ou edicao do config.json).
            </DialogDescription>
          </DialogHeader>
          <Divider />
          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => setPendingRotate(null)}
              disabled={rotateMut.isPending}
            >
              Cancelar
            </Button>
            <Button
              variant="primary"
              onClick={handleRotate}
              disabled={rotateMut.isPending}
              isLoading={rotateMut.isPending}
            >
              Gerar novo token
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Confirmacao: revogar */}
      <Dialog
        open={pendingRevoke !== null}
        onOpenChange={(open) => !open && setPendingRevoke(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Revogar acesso</DialogTitle>
            <DialogDescription>
              O coletor{" "}
              <span className="font-medium text-gray-900 dark:text-gray-50">
                {pendingRevoke?.name}
              </span>{" "}
              perde acesso imediatamente (recebe 401 no proximo contato). Os
              arquivos ja recebidos permanecem. Para reativar depois, use
              &quot;Reativar com token novo&quot;.
            </DialogDescription>
          </DialogHeader>
          <Divider />
          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => setPendingRevoke(null)}
              disabled={revokeMut.isPending}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleRevoke}
              disabled={revokeMut.isPending}
              isLoading={revokeMut.isPending}
            >
              <RiForbidLine className="mr-1.5 size-4" aria-hidden />
              Revogar acesso
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
