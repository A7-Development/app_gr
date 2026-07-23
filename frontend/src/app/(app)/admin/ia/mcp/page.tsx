// src/app/(app)/admin/ia/mcp/page.tsx
//
// Admin · IA · Servidores MCP (Fase 3 — copiloto-mcp, CLAUDE.md §19).
//
// Catalogo DB-first versionado de servidores MCP — provedores de capacidade
// pros agentes (irmao de Tools/Agentes). Permite:
//  - Cadastrar novo servidor (vira v1 e e ativado)
//  - Editar servidor (sempre cria nova versao — base e imutavel)
//  - Ativar uma versao (rollback de 1 click)
//  - Arquivar versao (soft-delete)
//  - Testar conexao (initialize + tools/list no servidor remoto)
//
// A lista do backend retorna TODAS as versoes; aqui colapsamos por familia
// (name) mostrando a versao ativa — as demais versoes aparecem no drawer.
//
// Pattern: ListagemCrudInline (CLAUDE.md §7) — clone de
// /admin/ia/personas/page.tsx.

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"
import {
  RiAddLine,
  RiArchive2Line,
  RiCheckLine,
  RiEdit2Line,
  RiHistoryLine,
  RiMoreLine,
  RiPlugLine,
  RiWifiLine,
} from "@remixicon/react"
import { formatDistanceToNow, parseISO } from "date-fns"
import { ptBR } from "date-fns/locale"
import { type ColumnDef } from "@tanstack/react-table"

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
  DrillDownSheet,
  PageHeader,
} from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type { AIMcpServerDetail } from "@/lib/api-client"
import {
  useActivateMcpServer,
  useArchiveMcpServer,
  useCreateMcpServer,
  useMcpServers,
  useTestMcpServer,
  useUpdateMcpServer,
} from "@/lib/hooks/admin-ai"
import {
  buildCreatePayload,
  buildUpdatePayload,
  type McpServerCreateValues,
  type McpServerUpdateValues,
} from "@/lib/schemas/ai-mcp-server-schema"
import { cx } from "@/lib/utils"

import { McpServerCreateForm, McpServerEditForm } from "./_components/McpServerForm"

// ───────────────────────────────────────────────────────────────────────────
// Helpers
// ───────────────────────────────────────────────────────────────────────────

/**
 * Colapsa a lista completa (todas as versoes) por familia (name): mostra a
 * versao ativa; sem ativa, a versao mais recente nao-arquivada; sem nenhuma,
 * a mais recente (arquivada).
 */
function collapseByFamily(all: AIMcpServerDetail[]): AIMcpServerDetail[] {
  const byName = new Map<string, AIMcpServerDetail[]>()
  for (const s of all) {
    const list = byName.get(s.name) ?? []
    list.push(s)
    byName.set(s.name, list)
  }
  const out: AIMcpServerDetail[] = []
  for (const versions of Array.from(byName.values())) {
    const sorted = [...versions].sort((a, b) => b.version - a.version)
    const active = sorted.find((v) => v.is_active)
    const latestLive = sorted.find((v) => v.archived_at === null)
    out.push(active ?? latestLive ?? sorted[0])
  }
  return out.sort((a, b) => a.name.localeCompare(b.name))
}

function formatChars(n: number): string {
  if (n >= 1000 && n % 1000 === 0) return `${n / 1000}k`
  return n.toLocaleString("pt-BR")
}

function StatusBadge({ active, archived }: { active: boolean; archived: boolean }) {
  if (archived) {
    return <span className={tableTokens.badgeNeutral}>Arquivado</span>
  }
  if (active) {
    return <span className={tableTokens.badgeSuccess}>Ativo</span>
  }
  return <span className={tableTokens.badgeNeutral}>Inativo</span>
}

// ───────────────────────────────────────────────────────────────────────────
// Header sticky do sheet — fixa contexto enquanto usuario rola form
// ───────────────────────────────────────────────────────────────────────────

function SheetHeader({
  title,
  subtitle,
  mono = false,
}: {
  title: string
  subtitle?: string
  mono?: boolean
}) {
  return (
    <div
      className={cx(
        "sticky top-0 z-10 border-b px-6 py-4",
        "border-gray-200 bg-white",
        "dark:border-gray-800 dark:bg-[#090E1A]",
      )}
    >
      <h2
        className={cx(
          "text-base font-semibold text-gray-900 dark:text-gray-50",
          mono && "font-mono",
        )}
      >
        {title}
      </h2>
      {subtitle && (
        <p className="mt-0.5 text-[13px] text-gray-500 dark:text-gray-400">
          {subtitle}
        </p>
      )}
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

type DetailSheetState =
  | { kind: "closed" }
  | { kind: "view"; id: string }
  | { kind: "create" }

export default function McpServersAdminPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const selectedId = searchParams.get("selected")
  const action = searchParams.get("action")

  // URL-synced sheet state.
  const sheetState: DetailSheetState = React.useMemo(() => {
    if (action === "new") return { kind: "create" }
    if (selectedId) return { kind: "view", id: selectedId }
    return { kind: "closed" }
  }, [action, selectedId])

  const [editingId, setEditingId] = React.useState<string | null>(null)
  const [archivingId, setArchivingId] = React.useState<string | null>(null)
  const [testingId, setTestingId] = React.useState<string | null>(null)
  const [segment, setSegment] = React.useState<
    "todos" | "ativos" | "arquivados"
  >("todos")
  const [search, setSearch] = React.useState("")

  const serversQuery = useMcpServers()

  const createMut = useCreateMcpServer()
  const updateMut = useUpdateMcpServer()
  const activateMut = useActivateMcpServer()
  const archiveMut = useArchiveMcpServer()
  const testMut = useTestMcpServer()

  const allVersions = React.useMemo(
    () => serversQuery.data ?? [],
    [serversQuery.data],
  )
  // Tabela mostra 1 linha por familia (versao ativa).
  const collapsed = React.useMemo(
    () => collapseByFamily(allVersions),
    [allVersions],
  )

  // Servidor aberto no sheet (view/edit) — resolvido da lista completa,
  // que ja traz o shape Detail inteiro (sem fetch adicional).
  const openId = editingId ?? (sheetState.kind === "view" ? sheetState.id : null)
  const openServer = React.useMemo(
    () => allVersions.find((s) => s.id === openId) ?? null,
    [allVersions, openId],
  )
  // Versoes da familia do servidor aberto (texto "vN · ativa: vM" no drawer).
  const familyVersions = React.useMemo(() => {
    if (!openServer) return []
    return allVersions
      .filter((s) => s.name === openServer.name)
      .sort((a, b) => a.version - b.version)
  }, [allVersions, openServer])

  // ── URL helpers ───────────────────────────────────────────────────────
  const closeSheet = React.useCallback(() => {
    setEditingId(null)
    const params = new URLSearchParams(searchParams.toString())
    params.delete("selected")
    params.delete("action")
    router.replace(
      params.toString() ? `?${params.toString()}` : window.location.pathname,
      { scroll: false },
    )
  }, [router, searchParams])

  const openDetail = React.useCallback(
    (id: string) => {
      const params = new URLSearchParams(searchParams.toString())
      params.set("selected", id)
      params.delete("action")
      router.replace(`?${params.toString()}`, { scroll: false })
    },
    [router, searchParams],
  )

  const openCreate = React.useCallback(() => {
    const params = new URLSearchParams(searchParams.toString())
    params.set("action", "new")
    params.delete("selected")
    router.replace(`?${params.toString()}`, { scroll: false })
  }, [router, searchParams])

  // ── Handlers ──────────────────────────────────────────────────────────
  const handleCreate = async (values: McpServerCreateValues) => {
    try {
      const created = await createMut.mutateAsync(buildCreatePayload(values))
      toast.success(`Servidor ${created.name}@v${created.version} cadastrado e ativado.`)
      closeSheet()
      setTimeout(() => openDetail(created.id), 50)
    } catch (e) {
      toast.error(`Falha ao cadastrar: ${(e as Error).message}`)
    }
  }

  const handleEdit = async (values: McpServerUpdateValues) => {
    if (!editingId) return
    try {
      const updated = await updateMut.mutateAsync({
        id: editingId,
        payload: buildUpdatePayload(values),
      })
      toast.success(
        `Nova versao ${updated.name}@v${updated.version} criada (nao ativa).`,
      )
      setEditingId(null)
      openDetail(updated.id)
    } catch (e) {
      toast.error(`Falha ao salvar versao: ${(e as Error).message}`)
    }
  }

  const handleActivate = async (row: AIMcpServerDetail) => {
    try {
      await activateMut.mutateAsync({ name: row.name, version: row.version })
      toast.success(`${row.name}@v${row.version} ativado.`)
    } catch (e) {
      toast.error(`Falha ao ativar: ${(e as Error).message}`)
    }
  }

  const handleArchive = async () => {
    if (!archivingId) return
    try {
      const archived = await archiveMut.mutateAsync(archivingId)
      toast.success(`${archived.name}@v${archived.version} arquivado.`)
      setArchivingId(null)
    } catch (e) {
      toast.error(`Falha ao arquivar: ${(e as Error).message}`)
    }
  }

  // Testa a conexao com o servidor remoto (initialize + tools/list).
  // Feedback §7.3: toast de loading enquanto a sonda roda; desfecho explicito.
  const handleTest = async (row: AIMcpServerDetail) => {
    setTestingId(row.id)
    const loadingToast = toast.loading(`Testando conexao com ${row.name}...`)
    try {
      const res = await testMut.mutateAsync(row.id)
      toast.dismiss(loadingToast)
      if (res.ok) {
        toast.success(
          `Conexao OK — ${res.tool_count ?? 0} tools (${res.allowed_count ?? 0} na allowlist).`,
        )
      } else {
        toast.error(`Falha na conexao: ${res.error ?? "erro desconhecido"}`)
      }
    } catch (e) {
      toast.dismiss(loadingToast)
      toast.error(`Falha ao testar: ${(e as Error).message}`)
    } finally {
      setTestingId(null)
    }
  }

  // ── Columns ───────────────────────────────────────────────────────────
  const columns = React.useMemo<ColumnDef<AIMcpServerDetail>[]>(
    () => [
      {
        accessorKey: "name",
        header: "Nome",
        cell: ({ row }) => (
          <span className="flex items-center gap-2">
            <span className={cx(tableTokens.cellStrong, "font-mono")}>
              {row.original.name}
            </span>
            <Badge variant="neutral" className={tableTokens.badge}>
              v{row.original.version}
            </Badge>
          </span>
        ),
      },
      {
        accessorKey: "url",
        header: "URL",
        cell: ({ row }) => (
          <span className={cx(tableTokens.cellTextMono, "block max-w-[280px] truncate")}>
            {row.original.url}
          </span>
        ),
      },
      {
        accessorKey: "module",
        header: "Modulo",
        cell: ({ row }) =>
          row.original.module ? (
            <span className={tableTokens.cellText}>{row.original.module}</span>
          ) : (
            <span className={tableTokens.cellSecondary}>cross-modulo</span>
          ),
      },
      {
        accessorKey: "mode",
        header: "Modo",
        cell: ({ row }) => (
          <span className={tableTokens.cellSecondary}>{row.original.mode}</span>
        ),
      },
      {
        id: "caps",
        header: "Caps",
        cell: ({ row }) => (
          <span className={tableTokens.cellSecondary}>
            {row.original.max_calls_per_turn}/turno ·{" "}
            {formatChars(row.original.tool_result_max_chars)} chars
          </span>
        ),
      },
      {
        accessorKey: "is_active",
        header: "Status",
        cell: ({ row }) => (
          <StatusBadge
            active={row.original.is_active}
            archived={row.original.archived_at !== null}
          />
        ),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <div className="flex justify-end">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  className="size-7 p-0"
                  onClick={(e) => e.stopPropagation()}
                  aria-label="Mais acoes"
                >
                  <RiMoreLine className="size-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end">
                <DropdownMenuItem
                  disabled={testingId === row.original.id}
                  onClick={(e) => {
                    e.stopPropagation()
                    void handleTest(row.original)
                  }}
                >
                  <RiWifiLine className="mr-2 size-4" />
                  Testar conexao
                </DropdownMenuItem>
                <DropdownMenuItem
                  onClick={(e) => {
                    e.stopPropagation()
                    setEditingId(row.original.id)
                  }}
                >
                  <RiEdit2Line className="mr-2 size-4" />
                  Editar (cria nova versao)
                </DropdownMenuItem>
                {!row.original.is_active &&
                  row.original.archived_at === null && (
                    <DropdownMenuItem
                      onClick={(e) => {
                        e.stopPropagation()
                        void handleActivate(row.original)
                      }}
                    >
                      <RiCheckLine className="mr-2 size-4" />
                      Ativar
                    </DropdownMenuItem>
                  )}
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  disabled={row.original.archived_at !== null}
                  onClick={(e) => {
                    e.stopPropagation()
                    setArchivingId(row.original.id)
                  }}
                  className="text-red-600 dark:text-red-500"
                >
                  <RiArchive2Line className="mr-2 size-4" />
                  Arquivar
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ),
      },
    ],
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [testingId],
  )

  // ── Render ────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Servidores MCP"
        subtitle="Inteligencia Artificial · Administracao"
        info="Catalogo de servidores MCP — provedores de capacidade pros agentes (CLAUDE.md §19). Versionado: editar cria nova versao; ativar em 1 click sem deploy. O backend e o cliente MCP — nada e exposto publicamente."
        actions={
          <Button
            variant="primary"
            onClick={openCreate}
            disabled={serversQuery.isLoading}
          >
            <RiAddLine className="mr-1 size-4" aria-hidden />
            Novo servidor
          </Button>
        }
      />

      <DataTableShell<AIMcpServerDetail>
        data={collapsed}
        columns={columns}
        loading={serversQuery.isLoading}
        error={serversQuery.error}
        onRetry={() => serversQuery.refetch()}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: "Buscar por nome ou URL...",
        }}
        segments={{
          value: segment,
          onChange: (v) => setSegment(v as typeof segment),
          options: [
            { value: "todos", label: "Todos", filter: () => true },
            {
              value: "ativos",
              label: "Ativos",
              filter: (s) => s.is_active && s.archived_at === null,
            },
            {
              value: "arquivados",
              label: "Arquivados",
              filter: (s) => s.archived_at !== null,
            },
          ],
        }}
        itemNoun={{ singular: "servidor", plural: "servidores" }}
        onRowClick={(row) => openDetail(row.id)}
        emptyState={{
          icon: RiPlugLine,
          title: "Nenhum servidor MCP cadastrado",
          description:
            "Cadastre o primeiro servidor MCP para conceder tools externas aos agentes.",
          action: (
            <Button variant="primary" onClick={openCreate}>
              <RiAddLine className="mr-1 size-4" aria-hidden />
              Cadastrar servidor
            </Button>
          ),
        }}
      />

      {/* Detail / edit sheet */}
      <DrillDownSheet
        open={sheetState.kind === "view" || editingId !== null}
        onClose={closeSheet}
        title={
          editingId
            ? "Editar servidor MCP"
            : openServer
              ? openServer.name
              : "Servidor MCP"
        }
        size="lg"
      >
        <div className="flex flex-1 flex-col overflow-y-auto">
          <SheetHeader
            title={
              editingId
                ? "Editar servidor MCP"
                : openServer
                  ? openServer.name
                  : "Servidor MCP"
            }
            subtitle={
              editingId && openServer
                ? `${openServer.name} · cria nova versao (v${openServer.version + 1})`
                : openServer
                  ? `${openServer.name} · v${openServer.version}`
                  : "Detalhe do servidor"
            }
            mono={!editingId && !!openServer}
          />
          <div className="p-6">
            {serversQuery.isLoading ? (
              <div className="py-8 text-center text-[13px] text-gray-500">
                Carregando...
              </div>
            ) : openServer ? (
              editingId === openServer.id ? (
                <McpServerEditForm
                  server={openServer}
                  onSubmit={handleEdit}
                  onCancel={() => setEditingId(null)}
                  submitting={updateMut.isPending}
                />
              ) : (
                <McpServerDetailView
                  server={openServer}
                  familyVersions={familyVersions}
                  onEdit={() => setEditingId(openServer.id)}
                  onActivate={() => handleActivate(openServer)}
                  onArchive={() => setArchivingId(openServer.id)}
                  onTest={() => handleTest(openServer)}
                  activating={activateMut.isPending}
                  testing={testingId === openServer.id}
                />
              )
            ) : null}
          </div>
        </div>
      </DrillDownSheet>

      {/* Create sheet */}
      <DrillDownSheet
        open={sheetState.kind === "create"}
        onClose={closeSheet}
        title="Novo servidor MCP"
        size="lg"
      >
        <div className="flex flex-1 flex-col overflow-y-auto">
          <SheetHeader
            title="Novo servidor MCP"
            subtitle="Cadastra um servidor MCP no catalogo. Vira v1 e e ativado automaticamente."
          />
          <div className="p-6">
            <McpServerCreateForm
              onSubmit={handleCreate}
              onCancel={closeSheet}
              submitting={createMut.isPending}
            />
          </div>
        </div>
      </DrillDownSheet>

      {/* Archive confirmation */}
      <Dialog
        open={archivingId !== null}
        onOpenChange={(open) => !open && setArchivingId(null)}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Arquivar servidor MCP</DialogTitle>
            <DialogDescription>
              A versao sera marcada como arquivada e nao podera mais ser
              ativada. Agentes que referenciam este servidor deixam de receber
              as tools dele.
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              variant="secondary"
              onClick={() => setArchivingId(null)}
              disabled={archiveMut.isPending}
            >
              Cancelar
            </Button>
            <Button
              variant="destructive"
              onClick={handleArchive}
              disabled={archiveMut.isPending}
            >
              Arquivar
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Detail view
// ───────────────────────────────────────────────────────────────────────────

function DetailSection({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <section>
      <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {label}
      </div>
      {children}
    </section>
  )
}

type DetailViewProps = {
  server: AIMcpServerDetail
  familyVersions: AIMcpServerDetail[]
  onEdit: () => void
  onActivate: () => void
  onArchive: () => void
  onTest: () => void
  activating: boolean
  testing: boolean
}

function McpServerDetailView({
  server,
  familyVersions,
  onEdit,
  onActivate,
  onArchive,
  onTest,
  activating,
  testing,
}: DetailViewProps) {
  const isArchived = server.archived_at !== null
  const activeVersion = familyVersions.find((v) => v.is_active)
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className={cx("font-mono text-[13px]", tableTokens.cellStrong)}>
          {server.name}
        </span>
        <Badge variant="neutral" className={tableTokens.badge}>
          v{server.version}
        </Badge>
        <StatusBadge active={server.is_active} archived={isArchived} />
        <span className="ml-auto text-[12px] text-gray-500 dark:text-gray-400">
          <RiHistoryLine className="-mt-0.5 mr-1 inline size-3.5" />
          {formatDistanceToNow(parseISO(server.created_at), {
            addSuffix: true,
            locale: ptBR,
          })}
        </span>
      </div>

      <DetailSection label="URL">
        <div className={cx(tableTokens.cellTextMono, "break-all")}>
          {server.url}
        </div>
      </DetailSection>

      <div className="grid grid-cols-2 gap-4">
        <DetailSection label="Transporte">
          <div className={tableTokens.cellText}>{server.transport}</div>
        </DetailSection>
        <DetailSection label="Modulo">
          <div className={tableTokens.cellText}>
            {server.module ?? "cross-modulo"}
          </div>
        </DetailSection>
        <DetailSection label="Modo">
          <div className={tableTokens.cellText}>{server.mode}</div>
        </DetailSection>
        <DetailSection label="Custo (hint)">
          <div className={tableTokens.cellText}>{server.cost_hint}</div>
        </DetailSection>
        <DetailSection label="Caps">
          <div className={tableTokens.cellText}>
            {server.max_calls_per_turn}/turno ·{" "}
            {formatChars(server.tool_result_max_chars)} chars
          </div>
        </DetailSection>
        <DetailSection label="Credencial">
          <div
            className={cx(
              server.credential_id
                ? tableTokens.cellTextMono
                : tableTokens.cellMuted,
              "break-all",
            )}
          >
            {server.credential_id ?? "—"}
          </div>
        </DetailSection>
      </div>

      <DetailSection label="Allowlist de tools">
        {server.allowed_tools && server.allowed_tools.length > 0 ? (
          <div className="flex flex-wrap gap-1">
            {server.allowed_tools.map((t) => (
              <span
                key={t}
                className={cx(
                  tableTokens.badge,
                  "bg-gray-100 font-mono text-gray-700 dark:bg-gray-800 dark:text-gray-300",
                )}
              >
                {t}
              </span>
            ))}
          </div>
        ) : (
          <div className={tableTokens.cellSecondary}>
            Sem allowlist — todas as tools expostas pelo servidor.
          </div>
        )}
      </DetailSection>

      {server.auth_header_map && (
        <DetailSection label="Mapeamento de headers de auth">
          <pre
            className={cx(
              "max-h-[160px] overflow-auto rounded-md border p-3 font-mono text-[12px] leading-relaxed",
              "border-gray-200 bg-gray-50 text-gray-900",
              "dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100",
            )}
          >
            {JSON.stringify(server.auth_header_map, null, 2)}
          </pre>
        </DetailSection>
      )}

      {server.description && (
        <DetailSection label="Descricao">
          <div className={tableTokens.cellSecondary}>{server.description}</div>
        </DetailSection>
      )}

      <DetailSection label="Versoes da familia">
        <div className={tableTokens.cellSecondary}>
          {familyVersions.map((v) => `v${v.version}`).join(" · ")}
          {activeVersion
            ? ` — v${activeVersion.version} ativa`
            : " — nenhuma ativa"}
        </div>
      </DetailSection>

      <Divider />

      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button variant="secondary" onClick={onTest} disabled={testing}>
          {testing ? (
            <RiWifiLine className="mr-1.5 size-4 animate-pulse" />
          ) : (
            <RiWifiLine className="mr-1.5 size-4" />
          )}
          {testing ? "Testando..." : "Testar conexao"}
        </Button>
        {!isArchived && (
          <>
            <Button
              variant="secondary"
              onClick={onArchive}
            >
              <RiArchive2Line className="mr-1.5 size-4" />
              Arquivar
            </Button>
            {!server.is_active && (
              <Button
                variant="secondary"
                onClick={onActivate}
                disabled={activating}
              >
                <RiCheckLine className="mr-1.5 size-4" />
                Ativar esta versao
              </Button>
            )}
            <Button onClick={onEdit}>
              <RiEdit2Line className="mr-1.5 size-4" />
              Editar (nova versao)
            </Button>
          </>
        )}
      </div>
    </div>
  )
}
