"use client"

//
// Integracoes · Operacao · Historico — decision_log cross-source unificado.
//
// PR 4 (2026-05-21): visao consolidada das execucoes de TODOS os adapters de
// integracao registrados em RULE_NAME_BY_SOURCE. Substitui o uso "abro a aba
// Historico de N fontes pra cruzar" por uma pagina unica filtravel.
//
// Hierarquia (CLAUDE.md 11.6):
//   L1 Integracoes > L2 Operacao > Historico
//
// Filtros (todos via URL — deep-link-aveis):
//   ?source=<id>      (multi via repeat)
//   ?status=ok|error
//   ?since=YYYY-MM-DD
//   ?until=YYYY-MM-DD
//   ?triggered_by=<prefixo>
//   ?limit=<int>
//
// Row expansivel inline (em vez de DrillDownSheet) — o conteudo de cada run
// e essencialmente JSON output + explanation, cabe melhor inline e e o
// mesmo padrao do HistoricoTab por fonte. Manter coerencia visual.
//

import * as React from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { format } from "date-fns"
import { ptBR } from "date-fns/locale"
import {
  RiArrowDownSLine,
  RiArrowRightSLine,
  RiCheckLine,
  RiExternalLinkLine,
  RiFilterLine,
  RiHistoryLine,
  RiStackLine,
} from "@remixicon/react"

import { PageHeader } from "@/design-system/components/PageHeader"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import {
  FilterBar,
  FilterChip,
  FilterSearch,
  RemovableChip,
} from "@/design-system/components/FilterBar"
import { JsonPreview } from "@/design-system/components/JsonPreview"
import { SegmentSwitch } from "@/design-system/components/SegmentSwitch"
import { Badge } from "@/components/tremor/Badge"
import { Button } from "@/components/tremor/Button"
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
import { cx, focusRing } from "@/lib/utils"
import {
  useCrossSourceRuns,
  useSources,
} from "@/lib/hooks/integracoes"
import type {
  CrossSourceRunEntry,
  CrossSourceRunsFilters,
  SourceListItem,
  SourceTypeId,
} from "@/lib/api-client"

const PAGE_INFO =
  "Historico unificado de execucoes (decision_log) de todos os adapters de integracao. Filtre por fonte, periodo ou status para investigar incidentes ou auditar uma janela."

// Presets de periodo. `null` = sem filtro (todo o intervalo retornado em ate
// `limit` registros). YYYY-MM-DD inclusivo nos dois lados (backend).
type PeriodKey = "7d" | "30d" | "90d" | "all"
const PERIODS: { value: PeriodKey; label: string }[] = [
  { value: "7d", label: "7 dias" },
  { value: "30d", label: "30 dias" },
  { value: "90d", label: "90 dias" },
  { value: "all", label: "Tudo" },
]

function periodToSince(period: PeriodKey): string | null {
  if (period === "all") return null
  const days = period === "7d" ? 7 : period === "30d" ? 30 : 90
  const d = new Date()
  d.setDate(d.getDate() - days)
  return d.toISOString().slice(0, 10)
}

// Status do SegmentSwitch
type StatusKey = "all" | "ok" | "error"
const STATUS_SEGMENTS: { value: StatusKey; label: string }[] = [
  { value: "all", label: "Todos" },
  { value: "ok", label: "OK" },
  { value: "error", label: "Erro" },
]

export default function HistoricoCrossSourcePage() {
  const sp = useSearchParams()
  const router = useRouter()

  // ─── Leitura dos filtros da URL ─────────────────────────────────────────
  const selectedSources = React.useMemo<SourceTypeId[]>(
    () => sp.getAll("source") as SourceTypeId[],
    [sp],
  )
  const period = (sp.get("period") as PeriodKey | null) ?? "30d"
  const status = (sp.get("status") as StatusKey | null) ?? "all"
  const triggeredBy = sp.get("triggered_by") ?? ""

  function setSearch(next: Record<string, string | string[] | null>) {
    const qs = new URLSearchParams(sp?.toString() ?? "")
    for (const [k, v] of Object.entries(next)) {
      qs.delete(k)
      if (v === null || v === "") continue
      if (Array.isArray(v)) v.forEach((x) => qs.append(k, x))
      else qs.set(k, v)
    }
    const s = qs.toString()
    router.replace(s ? `?${s}` : "?")
  }

  // ─── Query filters ──────────────────────────────────────────────────────
  const filters: CrossSourceRunsFilters = React.useMemo(() => {
    const since = periodToSince(period)
    return {
      source_type: selectedSources.length ? selectedSources : undefined,
      since: since ?? undefined,
      status: status === "all" ? undefined : status,
      triggered_by: triggeredBy.trim() || undefined,
      limit: 200,
    }
  }, [selectedSources, period, status, triggeredBy])

  const { data, isLoading, isError, refetch } = useCrossSourceRuns(filters)

  // ─── Catalogo de fontes (para opcoes do filtro) ─────────────────────────
  const { data: sourcesData } = useSources("production")
  const sourcesUnique = React.useMemo(() => {
    const seen = new Set<string>()
    const out: SourceListItem[] = []
    for (const s of sourcesData ?? []) {
      if (seen.has(s.source_type)) continue
      seen.add(s.source_type)
      out.push(s)
    }
    return out
  }, [sourcesData])

  const labelBySourceType = React.useMemo(() => {
    const m = new Map<SourceTypeId, string>()
    for (const s of sourcesUnique) m.set(s.source_type, s.label)
    return m
  }, [sourcesUnique])

  const sourceChipValue =
    selectedSources.length === 0
      ? "Todas"
      : selectedSources.length === 1
        ? labelBySourceType.get(selectedSources[0]) ?? selectedSources[0]
        : `${selectedSources.length} selecionadas`

  function toggleSource(st: SourceTypeId) {
    const cur = new Set(selectedSources)
    if (cur.has(st)) cur.delete(st)
    else cur.add(st)
    setSearch({ source: Array.from(cur) })
  }

  const hasAnyFilter =
    selectedSources.length > 0 ||
    status !== "all" ||
    period !== "30d" ||
    triggeredBy.length > 0

  function clearFilters() {
    setSearch({
      source: null,
      status: null,
      period: null,
      triggered_by: null,
    })
  }

  // ─── Render ─────────────────────────────────────────────────────────────
  return (
    <div className="flex flex-col gap-6 px-12 py-6 pb-28">
      <PageHeader
        title="Integracoes · Historico"
        info={PAGE_INFO}
        breadcrumbs={[
          { label: "Integracoes", href: "/integracoes/fontes" },
          { label: "Operacao" },
          { label: "Historico" },
        ]}
      />

      <FilterBar
        extraActions={
          hasAnyFilter ? (
            <Button variant="ghost" onClick={clearFilters}>
              Limpar filtros
            </Button>
          ) : undefined
        }
      >
        <SegmentSwitch<StatusKey>
          ariaLabel="Filtrar por status"
          value={status}
          options={STATUS_SEGMENTS}
          onChange={(v) => setSearch({ status: v === "all" ? null : v })}
        />

        <FilterChip
          label="Periodo"
          icon={RiHistoryLine}
          value={PERIODS.find((p) => p.value === period)?.label ?? "30 dias"}
          active={period !== "30d"}
        >
          <ul className="flex flex-col">
            {PERIODS.map((p) => {
              const active = period === p.value
              return (
                <li key={p.value}>
                  <button
                    type="button"
                    onClick={() =>
                      setSearch({ period: p.value === "30d" ? null : p.value })
                    }
                    className={cx(
                      "flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-sm",
                      "hover:bg-gray-100 dark:hover:bg-gray-800",
                      focusRing,
                    )}
                  >
                    <span className="text-gray-900 dark:text-gray-50">
                      {p.label}
                    </span>
                    {active && (
                      <RiCheckLine
                        className="size-3.5 text-blue-500"
                        aria-hidden
                      />
                    )}
                  </button>
                </li>
              )
            })}
          </ul>
        </FilterChip>

        <FilterChip
          label="Fonte"
          icon={RiStackLine}
          value={sourceChipValue}
          active={selectedSources.length > 0}
        >
          {sourcesUnique.length === 0 ? (
            <p className="px-2 py-1.5 text-xs text-gray-500 dark:text-gray-400">
              Carregando fontes…
            </p>
          ) : (
            <ul className="flex flex-col">
              {sourcesUnique.map((s) => {
                const active = selectedSources.includes(s.source_type)
                return (
                  <li key={s.source_type}>
                    <button
                      type="button"
                      onClick={() => toggleSource(s.source_type)}
                      className={cx(
                        "flex w-full items-center justify-between rounded px-2 py-1.5 text-left text-sm",
                        "hover:bg-gray-100 dark:hover:bg-gray-800",
                        focusRing,
                      )}
                    >
                      <div className="flex flex-col">
                        <span className="text-gray-900 dark:text-gray-50">
                          {s.label}
                        </span>
                        <span className="font-mono text-[11px] text-gray-500 dark:text-gray-400">
                          {s.source_type}
                        </span>
                      </div>
                      {active && (
                        <RiCheckLine
                          className="size-3.5 text-blue-500"
                          aria-hidden
                        />
                      )}
                    </button>
                  </li>
                )
              })}
            </ul>
          )}
        </FilterChip>

        <FilterSearch
          placeholder="Disparado por (ex.: user:, system:)"
          value={triggeredBy}
          onChange={(e) => setSearch({ triggered_by: e.target.value || null })}
          onClear={() => setSearch({ triggered_by: null })}
        />

        {/* Chips de filtros aplicados — visiveis pos-FilterChip pra reforcar
            "voce esta vendo um subset". Cada um remove o filtro especifico. */}
        {selectedSources.length > 0 &&
          selectedSources.map((st) => (
            <RemovableChip
              key={st}
              label="Fonte"
              value={labelBySourceType.get(st) ?? st}
              onRemove={() => toggleSource(st)}
            />
          ))}
      </FilterBar>

      {isError && (
        <ErrorState
          title="Nao foi possivel carregar o historico"
          description="Tente novamente em instantes ou ajuste os filtros."
          action={
            <Button variant="secondary" onClick={() => refetch()}>
              Tentar novamente
            </Button>
          }
        />
      )}

      {!isError && !isLoading && data && data.length === 0 && (
        <EmptyState
          icon={RiFilterLine}
          title="Nenhuma execucao no recorte atual"
          description={
            hasAnyFilter
              ? "Ajuste ou limpe os filtros para ver mais execucoes."
              : "Nao ha execucoes registradas — o decision_log esta vazio para este tenant."
          }
        />
      )}

      {!isError && (data === undefined || data.length > 0) && (
        <div className="rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
          <TableRoot>
            <Table>
              <TableHead>
                <TableRow>
                  <TableHeaderCell className="w-8" />
                  <TableHeaderCell>Quando</TableHeaderCell>
                  <TableHeaderCell>Fonte</TableHeaderCell>
                  <TableHeaderCell>Disparado por</TableHeaderCell>
                  <TableHeaderCell>Adapter</TableHeaderCell>
                  <TableHeaderCell>Resumo</TableHeaderCell>
                  <TableHeaderCell className="w-10" />
                </TableRow>
              </TableHead>
              <TableBody>
                {isLoading &&
                  Array.from({ length: 6 }).map((_, i) => (
                    <TableRow key={`skeleton-${i}`}>
                      <TableCell colSpan={7}>
                        <div className="h-6 w-full animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
                      </TableCell>
                    </TableRow>
                  ))}
                {!isLoading &&
                  data?.map((run) => (
                    <RunRow
                      key={run.id}
                      run={run}
                      sourceLabel={
                        labelBySourceType.get(run.source_type) ?? run.source_type
                      }
                    />
                  ))}
              </TableBody>
            </Table>
          </TableRoot>
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// RunRow — toggle inline. Mesmo padrao do HistoricoTab por fonte.
// ─────────────────────────────────────────────────────────────────────────────

function RunRow({
  run,
  sourceLabel,
}: {
  run: CrossSourceRunEntry
  sourceLabel: string
}) {
  const [expanded, setExpanded] = React.useState(false)
  const output = run.output ?? {}
  const errors = (output.errors ?? []) as unknown[]
  const elapsed = output.elapsed_seconds as number | undefined
  const hasErrors = errors.length > 0

  const detailHref = `/integracoes/fontes/${encodeURIComponent(
    run.source_type,
  )}?tab=diagnostico&view=historico`

  return (
    <>
      <TableRow
        className="cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-900"
        onClick={() => setExpanded((v) => !v)}
      >
        <TableCell>
          {expanded ? (
            <RiArrowDownSLine
              className="size-4 text-gray-500"
              aria-hidden
            />
          ) : (
            <RiArrowRightSLine
              className="size-4 text-gray-500"
              aria-hidden
            />
          )}
        </TableCell>
        <TableCell>
          <span className="text-gray-900 dark:text-gray-50">
            {format(new Date(run.occurred_at), "dd/MM/yyyy HH:mm:ss", {
              locale: ptBR,
            })}
          </span>
        </TableCell>
        <TableCell>
          <div className="flex flex-col">
            <span className={tableTokens.cellStrong}>{sourceLabel}</span>
            <span className={cx(tableTokens.cellTextMono, tableTokens.cellSecondary)}>
              {run.source_type}
            </span>
          </div>
        </TableCell>
        <TableCell className="font-mono text-xs">{run.triggered_by}</TableCell>
        <TableCell>
          <div className="flex flex-col">
            <span className="text-gray-900 dark:text-gray-50">
              {run.rule_or_model}
            </span>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              {run.rule_or_model_version ?? ""}
            </span>
          </div>
        </TableCell>
        <TableCell>
          <div className="flex items-center gap-2">
            <Badge variant={hasErrors ? "warning" : "success"}>
              {hasErrors ? `${errors.length} erro(s)` : "OK"}
            </Badge>
            {elapsed !== undefined && (
              <span className="text-xs text-gray-500 dark:text-gray-400">
                {elapsed.toFixed(1)}s
              </span>
            )}
          </div>
        </TableCell>
        <TableCell>
          <Link
            href={detailHref}
            onClick={(e) => e.stopPropagation()}
            className={cx(
              "inline-flex size-7 items-center justify-center rounded text-gray-400 hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-gray-800 dark:hover:text-gray-200",
              focusRing,
            )}
            aria-label={`Abrir historico da fonte ${sourceLabel}`}
            title="Abrir detalhe da fonte"
          >
            <RiExternalLinkLine className="size-3.5" aria-hidden />
          </Link>
        </TableCell>
      </TableRow>
      {expanded && (
        <TableRow>
          <TableCell colSpan={7} className="bg-gray-50 dark:bg-gray-900/50">
            <div className="flex flex-col gap-3 py-2">
              {run.explanation && (
                <div className="flex flex-col gap-1">
                  <span className="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">
                    Explicacao
                  </span>
                  <p className="text-sm text-gray-700 dark:text-gray-300">
                    {run.explanation}
                  </p>
                </div>
              )}
              <div className="flex flex-col gap-1">
                <span className="text-xs font-semibold uppercase text-gray-500 dark:text-gray-400">
                  Output
                </span>
                <JsonPreview value={run.output ?? {}} maxHeight={400} />
              </div>
            </div>
          </TableCell>
        </TableRow>
      )}
    </>
  )
}
