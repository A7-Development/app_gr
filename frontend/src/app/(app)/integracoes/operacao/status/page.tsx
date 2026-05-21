"use client"

//
// Integracoes · Operacao · Status — agregado cross-source.
//
// Tabela com todas as fontes configuradas. Cada fonte expande mostrando os
// endpoints (cadencia individual, ultima sync, botao "Sync agora"). O detalhe
// completo continua em /fontes/[source_type].
//
// Hierarquia (CLAUDE.md 11.6):
//   L1 Integracoes > L2 Operacao > Status
//
// Filtros (PR 2 — 2026-05-21): Todas / Configuradas / Habilitadas viraram
// SegmentSwitch numa FilterBar canonica (CLAUDE.md §7.1 — Card branco em faixa
// cinza-50). Antes eram TabNavigation, mas filtros de listagem fingindo ser
// tabs e anti-pattern: tab L3 e "perspectiva diferente do mesmo dado", filtro
// e "subset filtrado". URL param `?tab=` preservado por retrocompat.
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
  RiArrowDownSLine,
  RiArrowRightLine,
  RiArrowRightSLine,
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRoot,
  TableRow,
} from "@/components/tremor/Table"
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

export default function SyncPage() {
  const sp = useSearchParams()
  const router = useRouter()
  const environment: Environment =
    sp.get("environment") === "sandbox" ? "sandbox" : "production"
  const activeSegment: SegmentKey =
    (SEGMENTS.find((s) => s.value === sp.get("tab"))?.value ?? "todas") as SegmentKey

  const { data, isLoading, isError, refetch } = useSources(environment)
  const [expanded, setExpanded] = React.useState<Set<string>>(new Set())

  function toggleExpanded(sourceType: string) {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(sourceType)) next.delete(sourceType)
      else next.add(sourceType)
      return next
    })
  }

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
              <TableRoot>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableHeaderCell className="w-10" />
                      <TableHeaderCell>Fonte</TableHeaderCell>
                      <TableHeaderCell>Categoria</TableHeaderCell>
                      <TableHeaderCell>Status</TableHeaderCell>
                      <TableHeaderCell>Endpoints</TableHeaderCell>
                      <TableHeaderCell>Ultimo sync</TableHeaderCell>
                      <TableHeaderCell className="w-48 text-right">
                        Acoes
                      </TableHeaderCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {isLoading &&
                      Array.from({ length: 3 }).map((_, i) => (
                        <TableRow key={`skeleton-${i}`}>
                          <TableCell colSpan={7}>
                            <div className="h-6 w-full animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
                          </TableCell>
                        </TableRow>
                      ))}
                    {!isLoading &&
                      filtered.map((row) => (
                        <React.Fragment key={`${row.source_type}-${row.unidade_administrativa_id ?? "noua"}`}>
                          <SyncRow
                            row={row}
                            environment={environment}
                            expanded={expanded.has(row.source_type)}
                            canExpand={SOURCES_WITH_ENDPOINT_CATALOG.has(
                              row.source_type,
                            )}
                            onToggleExpand={() =>
                              toggleExpanded(row.source_type)
                            }
                            onRefresh={() => refetch()}
                          />
                          {expanded.has(row.source_type) &&
                            SOURCES_WITH_ENDPOINT_CATALOG.has(
                              row.source_type,
                            ) && (
                              <EndpointsExpansion
                                sourceType={row.source_type}
                                environment={environment}
                                uaId={row.unidade_administrativa_id}
                              />
                            )}
                        </React.Fragment>
                      ))}
                  </TableBody>
                </Table>
              </TableRoot>
            </div>
          )}
        </>
      )}
    </div>
  )
}

function SyncRow({
  row,
  environment,
  expanded,
  canExpand,
  onToggleExpand,
  onRefresh,
}: {
  row: SourceListItem
  environment: Environment
  expanded: boolean
  canExpand: boolean
  onToggleExpand: () => void
  onRefresh: () => void
}) {
  const [running, setRunning] = React.useState(false)

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
    <TableRow>
      <TableCell className="w-10">
        {canExpand ? (
          <Button
            type="button"
            variant="ghost"
            onClick={onToggleExpand}
            aria-label={expanded ? "Recolher endpoints" : "Expandir endpoints"}
            aria-expanded={expanded}
          >
            {expanded ? (
              <RiArrowDownSLine className="size-4" aria-hidden />
            ) : (
              <RiArrowRightSLine className="size-4" aria-hidden />
            )}
          </Button>
        ) : null}
      </TableCell>
      <TableCell className="font-medium text-gray-900 dark:text-gray-50">
        <div className="flex flex-col">
          <span>{row.label}</span>
          <span className="font-mono text-xs text-gray-500 dark:text-gray-400">
            {row.source_type}
          </span>
        </div>
      </TableCell>
      <TableCell className="capitalize">{row.category}</TableCell>
      <TableCell>
        <AdapterStatusBadge status={statusFrom(row.configured, row.enabled)} />
      </TableCell>
      <TableCell>
        {canExpand ? (
          <span className={tableTokens.cellSecondary}>
            Cadencia por endpoint
          </span>
        ) : (
          <span className={tableTokens.cellMuted}>Sob demanda</span>
        )}
      </TableCell>
      <TableCell>
        <LastSyncCell iso={row.last_sync_at} />
      </TableCell>
      <TableCell className="text-right">
        <div className="flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="secondary"
            disabled={!row.configured || running}
            onClick={handleSyncNow}
          >
            {running ? (
              <RiLoader4Line
                className="mr-1.5 size-4 animate-spin"
                aria-hidden
              />
            ) : (
              <RiRefreshLine className="mr-1.5 size-4" aria-hidden />
            )}
            Sync agora
          </Button>
          <Button variant="ghost" asChild>
            <Link href={detailHref} aria-label={`Abrir ${row.label}`}>
              <RiArrowRightLine className="size-4" aria-hidden />
            </Link>
          </Button>
        </div>
      </TableCell>
    </TableRow>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// EndpointsExpansion
// ─────────────────────────────────────────────────────────────────────────────

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

  if (isLoading) {
    return (
      <TableRow className="bg-gray-50 dark:bg-gray-900/40">
        <TableCell colSpan={7}>
          <div className="h-6 w-full animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
        </TableCell>
      </TableRow>
    )
  }

  if (isError) {
    return (
      <TableRow className="bg-gray-50 dark:bg-gray-900/40">
        <TableCell colSpan={7}>
          <span className={tableTokens.cellSecondary}>
            Falha ao carregar endpoints.
          </span>
        </TableCell>
      </TableRow>
    )
  }

  if (!data || data.length === 0) {
    return (
      <TableRow className="bg-gray-50 dark:bg-gray-900/40">
        <TableCell colSpan={7}>
          <span className={tableTokens.cellSecondary}>
            Sem endpoints no catalogo desta fonte.
          </span>
        </TableCell>
      </TableRow>
    )
  }

  return (
    <>
      {data.map((ep) => (
        <EndpointSubRow
          key={ep.name}
          endpoint={ep}
          sourceType={sourceType}
          environment={environment}
          uaId={uaId}
        />
      ))}
    </>
  )
}

function EndpointSubRow({
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

  const kind = endpoint.schedule_kind ?? endpoint.default_schedule_kind
  const value = endpoint.schedule_value ?? endpoint.default_schedule_value
  const enabled = endpoint.enabled ?? true

  return (
    <TableRow className="bg-gray-50 dark:bg-gray-900/40">
      <TableCell className="w-10" />
      <TableCell>
        <div className="flex flex-col gap-0.5 pl-4">
          <span className={tableTokens.cellStrong}>{endpoint.label}</span>
          <span className={cx(tableTokens.cellSecondary, "font-mono")}>
            {endpoint.name}
          </span>
        </div>
      </TableCell>
      <TableCell>
        <KindBadge kind={kind} />
      </TableCell>
      <TableCell>
        <EndpointStateBadge
          enabled={enabled}
          status={endpoint.last_sync_status}
        />
      </TableCell>
      <TableCell>
        <span className={tableTokens.cellNumber}>
          {formatScheduleSummary(kind, value)}
        </span>
      </TableCell>
      <TableCell>
        <LastSyncCell
          startedAt={endpoint.last_sync_started_at}
          finishedAt={endpoint.last_sync_finished_at}
          status={endpoint.last_sync_status}
          errorMessage={endpoint.last_sync_error}
        />
      </TableCell>
      <TableCell className="text-right">
        <Button
          type="button"
          variant="ghost"
          onClick={handleSyncNow}
          disabled={syncMut.isPending}
          title="Sincronizar agora"
          aria-label={`Sincronizar ${endpoint.label} agora`}
        >
          <RiPlayLine className="size-4" aria-hidden />
        </Button>
      </TableCell>
    </TableRow>
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
