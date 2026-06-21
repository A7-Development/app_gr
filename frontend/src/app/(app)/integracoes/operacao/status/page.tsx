"use client"

//
// Integracoes · Operacao · Status — agregado cross-source.
//
// Tabela com todas as fontes configuradas. Cada fonte expande mostrando os
// endpoints (cadencia individual, ultima sync, botao "Sync agora"). O detalhe
// completo continua em /fontes/[source_type].
//
// Modo master-detail canonico: <ExpandableTable> (handoff "Tabela canonica").
// A linha do source e o ponto de entrada; expandir abre o painel de endpoints
// daquela fonte (so fontes com catalogo expandem — ver SOURCES_WITH_ENDPOINT_
// CATALOG + canExpand). Substitui o <TableRoot> cru com expand inline (era
// Tremor Table cru em pagina, proibido — CLAUDE.md §6).
//
// Hierarquia (CLAUDE.md 11.6):
//   L1 Integracoes > L2 Operacao > Status
//
// Filtros (PR 2 — 2026-05-21): Todas / Configuradas / Habilitadas viraram
// SegmentSwitch numa FilterBar canonica. Antes eram TabNavigation, mas filtros
// de listagem fingindo ser tabs e anti-pattern: tab L3 e "perspectiva diferente
// do mesmo dado", filtro e "subset filtrado". URL param `?tab=` preservado por
// retrocompat.
//
// Granularidade fina (CLAUDE.md §13 — refactor 2026-05-05): a linha do source
// e o ponto de entrada; a expansion mostra os endpoints daquela fonte com
// suas cadencias proprias. Mantemos por-source para nao explodir em 100+
// linhas flat (1 tenant pode ter 12 endpoints da QiTech + 1 do Bitfin).
//

import Link from "next/link"
import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { toast } from "sonner"
import {
  RiArrowRightLine,
  RiLoader4Line,
  RiPlayLine,
  RiRefreshLine,
  RiStackLine,
} from "@remixicon/react"

import { PageHeader } from "@/design-system/components/PageHeader"
import {
  AdapterStatusBadge,
  statusFrom,
} from "@/design-system/components/AdapterStatusBadge"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import {
  ExpandableTable,
  type ExpandableColumn,
} from "@/design-system/components/ExpandableTable"
import { FilterBar } from "@/design-system/components/FilterBar"
import { LastSyncCell } from "@/design-system/components/LastSyncCell"
import { SegmentSwitch } from "@/design-system/components/SegmentSwitch"
import { Badge } from "@/components/tremor/Badge"
import { Button } from "@/components/tremor/Button"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"
import { integracoes } from "@/lib/api-client"
import {
  useSources,
  useSourceEndpoints,
  useSyncEndpoint,
} from "@/lib/hooks/integracoes"
import type {
  EndpointDetail,
  Environment,
  ScheduleKind,
  SourceListItem,
  SourceTypeId,
} from "@/lib/api-client"

const PAGE_INFO =
  "Visao consolidada de sincronizacoes por fonte. Expanda uma fonte para ver os endpoints e suas cadencias."

// Segments do SegmentSwitch (PR 2). Param de URL mantido como `?tab=` por
// retrocompat de bookmarks/links externos — internamente e segment, nao tab.
const SEGMENTS = [
  { value: "todas", label: "Todas" },
  { value: "configuradas", label: "Configuradas" },
  { value: "habilitadas", label: "Habilitadas" },
] as const
type SegmentKey = (typeof SEGMENTS)[number]["value"]

// Sources sem catalogo de endpoints — bureaus, parsers de documento, etc.
// Manter sincronizado com `_CATALOG_BY_SOURCE` em backend public.py.
const SOURCES_WITH_ENDPOINT_CATALOG = new Set<SourceTypeId>([
  "admin:qitech",
  "erp:bitfin",
])

function filterBySegment(rows: SourceListItem[], seg: SegmentKey): SourceListItem[] {
  if (seg === "configuradas") return rows.filter((r) => r.configured)
  if (seg === "habilitadas") return rows.filter((r) => r.configured && r.enabled)
  return rows
}

function rowKey(row: SourceListItem): string {
  return `${row.source_type}-${row.unidade_administrativa_id ?? "noua"}`
}

export default function SyncPage() {
  const sp = useSearchParams()
  const router = useRouter()
  const environment: Environment =
    sp.get("environment") === "sandbox" ? "sandbox" : "production"
  const activeSegment: SegmentKey =
    (SEGMENTS.find((s) => s.value === sp.get("tab"))?.value ?? "todas") as SegmentKey

  const { data, isLoading, isError, refetch } = useSources(environment)

  function setSearch(next: Record<string, string | null>) {
    const qs = new URLSearchParams(sp?.toString() ?? "")
    for (const [k, v] of Object.entries(next)) {
      if (v === null) qs.delete(k)
      else qs.set(k, v)
    }
    const s = qs.toString()
    router.replace(s ? `/integracoes/operacao/status?${s}` : "/integracoes/operacao/status")
  }

  // Contagens por segment — exibidas como `count` em cada pill (UX: o usuario
  // ve quantas fontes caem em cada filtro sem precisar clicar).
  const counts = React.useMemo(() => {
    const rows = data ?? []
    return {
      todas: rows.length,
      configuradas: rows.filter((r) => r.configured).length,
      habilitadas: rows.filter((r) => r.configured && r.enabled).length,
    }
  }, [data])

  const filtered = data ? filterBySegment(data, activeSegment) : []

  // Colunas da tabela canonica. O chevron de expansao e renderizado pelo
  // proprio ExpandableTable (coluna implicita) — aqui ficam apenas as colunas
  // de conteudo. A coluna "acoes" carrega seu estado proprio via <ActionsCell>.
  const columns: ExpandableColumn<SourceListItem>[] = React.useMemo(
    () => [
      {
        id: "fonte",
        header: "Fonte",
        cell: (row) => (
          <div className="flex flex-col">
            <span className={tableTokens.cellStrong}>{row.label}</span>
            <span className={cx(tableTokens.cellSecondary, "font-mono")}>
              {row.source_type}
            </span>
          </div>
        ),
      },
      {
        id: "categoria",
        header: "Categoria",
        cell: (row) => (
          <span className={cx(tableTokens.cellText, "capitalize")}>
            {row.category}
          </span>
        ),
      },
      {
        id: "status",
        header: "Status",
        cell: (row) => (
          <AdapterStatusBadge status={statusFrom(row.configured, row.enabled)} />
        ),
      },
      {
        id: "endpoints",
        header: "Endpoints",
        cell: (row) =>
          SOURCES_WITH_ENDPOINT_CATALOG.has(row.source_type) ? (
            <span className={tableTokens.cellSecondary}>
              Cadencia por endpoint
            </span>
          ) : (
            <span className={tableTokens.cellMuted}>Sob demanda</span>
          ),
      },
      {
        id: "ultimo_sync",
        header: "Ultimo sync",
        cell: (row) => <LastSyncCell iso={row.last_sync_at} />,
      },
      {
        id: "acoes",
        header: "Acoes",
        align: "right",
        widthClass: "w-48",
        cell: (row) => (
          <ActionsCell
            row={row}
            environment={environment}
            onRefresh={() => refetch()}
          />
        ),
      },
    ],
    [environment, refetch],
  )

  return (
    <div className="flex flex-col gap-6 px-12 py-6 pb-28">
      <PageHeader
        title="Integracoes · Status"
        info={PAGE_INFO}
        breadcrumbs={[
          { label: "Integracoes", href: "/integracoes/fontes" },
          { label: "Operacao" },
          { label: "Status" },
        ]}
        actions={
          <div className="flex items-center gap-2">
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Ambiente
            </span>
            <Select
              value={environment}
              onValueChange={(v) =>
                setSearch({
                  environment: v === "production" ? null : v,
                })
              }
            >
              <SelectTrigger className="w-36">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="production">Producao</SelectItem>
                <SelectItem value="sandbox">Sandbox</SelectItem>
              </SelectContent>
            </Select>
          </div>
        }
      />

      {isError && (
        <ErrorState
          title="Nao foi possivel carregar as fontes"
          action={
            <Button variant="secondary" onClick={() => refetch()}>
              Tentar novamente
            </Button>
          }
        />
      )}

      {!isError && (
        <>
          <FilterBar>
            <SegmentSwitch<SegmentKey>
              ariaLabel="Filtrar fontes por configuracao"
              value={activeSegment}
              options={SEGMENTS.map((s) => ({
                value: s.value,
                label: s.label,
                count: counts[s.value],
              }))}
              onChange={(next) =>
                setSearch({ tab: next === "todas" ? null : next })
              }
            />
          </FilterBar>

          {!isLoading && filtered.length === 0 && (
            <EmptyState
              icon={RiStackLine}
              title="Nenhuma fonte nesta visao"
              description={
                activeSegment === "habilitadas"
                  ? "Nenhuma fonte habilitada no momento. Habilite em Fontes."
                  : activeSegment === "configuradas"
                    ? "Nenhuma fonte configurada ainda."
                    : "O catalogo de fontes esta vazio."
              }
            />
          )}

          {(isLoading || filtered.length > 0) && (
            <div className="rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
              <ExpandableTable<SourceListItem>
                data={filtered}
                columns={columns}
                getRowId={rowKey}
                canExpand={(row) =>
                  SOURCES_WITH_ENDPOINT_CATALOG.has(row.source_type)
                }
                renderRowDetail={(row) => (
                  <EndpointsExpansion
                    sourceType={row.source_type}
                    environment={environment}
                    uaId={row.unidade_administrativa_id}
                  />
                )}
                loading={isLoading}
                skeletonRows={3}
                emptyText="Nenhuma fonte nesta visao."
              />
            </div>
          )}
        </>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// ActionsCell — celula de acoes da linha de source. Carrega o estado proprio
// do "Sync agora" (spinner `running`). stopPropagation nos controles para nao
// disparar o expand da linha.
// ─────────────────────────────────────────────────────────────────────────────

function ActionsCell({
  row,
  environment,
  onRefresh,
}: {
  row: SourceListItem
  environment: Environment
  onRefresh: () => void
}) {
  const [running, setRunning] = React.useState(false)
  const canExpand = SOURCES_WITH_ENDPOINT_CATALOG.has(row.source_type)

  async function handleSyncNow() {
    setRunning(true)
    try {
      await integracoes.sync(
        row.source_type,
        environment,
        row.unidade_administrativa_id,
      )
      toast.success(`Sync de ${row.label} concluido.`)
      onRefresh()
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Falha ao executar sync.",
      )
    } finally {
      setRunning(false)
    }
  }

  const detailHref = `/integracoes/fontes/${encodeURIComponent(
    row.source_type,
  )}?environment=${environment}&tab=${canExpand ? "endpoints" : "historico"}${
    row.unidade_administrativa_id
      ? `&ua=${row.unidade_administrativa_id}`
      : ""
  }`

  return (
    <div className="flex items-center justify-end gap-2">
      <Button
        type="button"
        variant="secondary"
        disabled={!row.configured || running}
        onClick={(e) => {
          e.stopPropagation()
          void handleSyncNow()
        }}
      >
        {running ? (
          <RiLoader4Line className="mr-1.5 size-4 animate-spin" aria-hidden />
        ) : (
          <RiRefreshLine className="mr-1.5 size-4" aria-hidden />
        )}
        Sync agora
      </Button>
      <Button variant="ghost" asChild>
        <Link
          href={detailHref}
          aria-label={`Abrir ${row.label}`}
          onClick={(e) => e.stopPropagation()}
        >
          <RiArrowRightLine className="size-4" aria-hidden />
        </Link>
      </Button>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// EndpointsExpansion — painel de detalhe (renderRowDetail) de uma fonte.
// Lista os endpoints do catalogo, cada um com cadencia + estado + ultimo sync
// + botao "Sincronizar agora". Renderizado dentro do painel expandido — usa
// um ExpandableTable aninhado (canExpand=false) so pelo chrome canonico de
// tabela; os endpoints nao tem sub-detalhe proprio.
// ─────────────────────────────────────────────────────────────────────────────

const ENDPOINT_COLUMNS: ExpandableColumn<EndpointDetail>[] = [
  {
    id: "endpoint",
    header: "Endpoint",
    cell: (ep) => (
      <div className="flex flex-col gap-0.5">
        <span className={tableTokens.cellStrong}>{ep.label}</span>
        <span className={cx(tableTokens.cellSecondary, "font-mono")}>
          {ep.name}
        </span>
      </div>
    ),
  },
  {
    id: "cadencia",
    header: "Cadencia",
    cell: (ep) => <KindBadge kind={ep.schedule_kind ?? ep.default_schedule_kind} />,
  },
  {
    id: "estado",
    header: "Estado",
    cell: (ep) => (
      <EndpointStateBadge
        enabled={ep.enabled ?? true}
        status={ep.last_sync_status}
      />
    ),
  },
  {
    id: "agenda",
    header: "Agenda",
    cell: (ep) => (
      <span className={tableTokens.cellNumber}>
        {formatScheduleSummary(
          ep.schedule_kind ?? ep.default_schedule_kind,
          ep.schedule_value ?? ep.default_schedule_value,
        )}
      </span>
    ),
  },
  {
    id: "ultimo_sync",
    header: "Ultimo sync",
    cell: (ep) => (
      <LastSyncCell
        startedAt={ep.last_sync_started_at}
        finishedAt={ep.last_sync_finished_at}
        status={ep.last_sync_status}
        errorMessage={ep.last_sync_error}
      />
    ),
  },
]

function EndpointsExpansion({
  sourceType,
  environment,
  uaId,
}: {
  sourceType: SourceTypeId
  environment: Environment
  uaId: string | null
}) {
  const { data, isLoading, isError } = useSourceEndpoints(
    sourceType,
    environment,
    uaId,
  )

  if (isError) {
    return (
      <span className={tableTokens.cellSecondary}>
        Falha ao carregar endpoints.
      </span>
    )
  }

  if (!isLoading && (!data || data.length === 0)) {
    return (
      <span className={tableTokens.cellSecondary}>
        Sem endpoints no catalogo desta fonte.
      </span>
    )
  }

  const columns: ExpandableColumn<EndpointDetail>[] = [
    ...ENDPOINT_COLUMNS,
    {
      id: "acoes",
      header: "Acoes",
      align: "right",
      widthClass: "w-16",
      cell: (ep) => (
        <EndpointSyncButton
          endpoint={ep}
          sourceType={sourceType}
          environment={environment}
          uaId={uaId}
        />
      ),
    },
  ]

  return (
    <ExpandableTable<EndpointDetail>
      data={data ?? []}
      columns={columns}
      getRowId={(ep) => ep.name}
      canExpand={() => false}
      renderRowDetail={() => null}
      loading={isLoading}
      skeletonRows={2}
      emptyText="Sem endpoints no catalogo desta fonte."
    />
  )
}

function EndpointSyncButton({
  endpoint,
  sourceType,
  environment,
  uaId,
}: {
  endpoint: EndpointDetail
  sourceType: SourceTypeId
  environment: Environment
  uaId: string | null
}) {
  const syncMut = useSyncEndpoint(sourceType)

  const handleSyncNow = async () => {
    try {
      const result = await syncMut.mutateAsync({
        endpointName: endpoint.name,
        environment,
        uaId,
      })
      if (result.ok) {
        toast.success(`Sync de "${endpoint.label}" concluido.`)
      } else {
        toast.error(
          `Sync de "${endpoint.label}" falhou: ${result.errors.join("; ") || "erro desconhecido"}`,
        )
      }
    } catch (err) {
      toast.error(
        err instanceof Error ? err.message : "Falha ao disparar sync.",
      )
    }
  }

  return (
    <Button
      type="button"
      variant="ghost"
      onClick={(e) => {
        e.stopPropagation()
        void handleSyncNow()
      }}
      disabled={syncMut.isPending}
      title="Sincronizar agora"
      aria-label={`Sincronizar ${endpoint.label} agora`}
    >
      {syncMut.isPending ? (
        <RiLoader4Line className="size-4 animate-spin" aria-hidden />
      ) : (
        <RiPlayLine className="size-4" aria-hidden />
      )}
    </Button>
  )
}

function formatScheduleSummary(
  kind: ScheduleKind,
  value: string | null,
): string {
  if (kind === "interval") return value ? `A cada ${value} min` : "—"
  if (kind === "daily_at") return value ? `Diario as ${value}` : "—"
  return "Sob demanda"
}

function KindBadge({ kind }: { kind: ScheduleKind }) {
  if (kind === "interval") return <Badge variant="default">Intervalo</Badge>
  if (kind === "daily_at") return <Badge variant="success">Diario</Badge>
  return <Badge variant="neutral">Sob demanda</Badge>
}

function EndpointStateBadge({
  enabled,
  status,
}: {
  enabled: boolean
  status: EndpointDetail["last_sync_status"]
}) {
  if (!enabled) return <Badge variant="neutral">Desligado</Badge>
  if (status === "em_progresso")
    return <Badge variant="warning">Em curso</Badge>
  if (status === "erro") return <Badge variant="error">Erro</Badge>
  if (status === "ok") return <Badge variant="success">OK</Badge>
  return <Badge variant="neutral">Aguardando</Badge>
}
