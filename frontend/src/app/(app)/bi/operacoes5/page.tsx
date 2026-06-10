// src/app/(app)/bi/operacoes5/page.tsx
//
// BI · Operações · Drill por dimensão — pagina /bi/operacoes5.
//
// Reconstrucao de /bi/operacoes4 reorientada para a ESPINHA DE DRILL pelas
// dimensoes UA -> Produto -> Cedente -> (Sacado, Fase 2) -> Operacao ->
// Documento, aplicando o padrao de navegacao (docs/navegacao-aprofundamento.md):
//
//   - UA / Produto = filtros globais (FilterBar, este nivel)
//   - Cedente      = ROTA dedicada (/bi/operacoes5/cedente/[id])
//   - Operacao     = DRAWER (?selected, na rota do cedente)
//   - Documento    = INLINE (dentro do drawer)
//
// Esta pagina e o nivel de overview: KPIs do recorte + ranking de cedentes
// clicavel (o ponto de entrada da espinha). Regime CAIXA (wh_operacao),
// mesma matematica de operacoes4. Reconcilia on-screen (§14.6): o rodape da
// tabela soma o VOP total retornado.

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { useRouter, useSearchParams } from "next/navigation"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import {
  RiArrowRightSLine,
  RiCalendarLine,
  RiCheckLine,
  RiRefreshLine,
} from "@remixicon/react"
import { toast } from "sonner"

import { cx } from "@/lib/utils"
import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import { Checkbox } from "@/components/tremor/Checkbox"

import { PageHeader } from "@/design-system/components/PageHeader"
import { FilterChip, MoreFiltersButton } from "@/design-system/components/FilterBar"
import { DataTable } from "@/design-system/components/DataTable"
import { cardTokens } from "@/design-system/tokens/card"
import { tableTokens } from "@/design-system/tokens/table"
import { fmt, fmtCNPJ } from "@/design-system/tokens/typography"

import { ProvenanceFooter } from "@/components/bi/ProvenanceFooter"
import { useScrollShadow } from "@/lib/hooks/use-scroll-shadow"
import { useBiFilters, type PresetKey } from "@/lib/hooks/useBiFilters"
import { biMetadata, biOperacoes5 } from "@/lib/api-client"
import type { Operacoes5CedenteItem } from "@/lib/api-client"
import { EntidadeLink } from "@/design-system/components/EntidadeLink"

const PRESET_OPTIONS: ReadonlyArray<{ key: PresetKey; label: string }> = [
  { key: "ytd", label: "Ano até hoje" },
  { key: "3m", label: "Últimos 3 meses" },
  { key: "6m", label: "Últimos 6 meses" },
  { key: "12m", label: "Últimos 12 meses" },
  { key: "24m", label: "Últimos 24 meses" },
  { key: "36m", label: "Últimos 36 meses" },
  { key: "all", label: "Todo histórico" },
]
const PRESET_LABEL_MAP: Record<PresetKey, string> = Object.fromEntries(
  PRESET_OPTIONS.map((o) => [o.key, o.label]),
) as Record<PresetKey, string>

const fmtPct2 = (v: number) => `${v.toFixed(2).replace(".", ",")}%`
// Prazo e sempre em dias — exibe so o numero (sem sufixo "d").
const fmtDias = (v: number) => fmt.decimal1.format(v)

export default function Operacoes5Page() {
  const router = useRouter()
  const sp = useSearchParams()

  const dataMinimaQuery = useQuery({
    queryKey: ["bi", "metadata", "data-minima"],
    queryFn: () => biMetadata.dataMinima(),
    staleTime: 6 * 60 * 60 * 1000,
  })
  const dataMinima = dataMinimaQuery.data?.data_minima ?? undefined

  const { filtersWithFocus, preset, setFilter, resetFilters } =
    useBiFilters(dataMinima)

  const uasQuery = useQuery({
    queryKey: ["bi", "metadata", "uas"],
    queryFn: () => biMetadata.uas(),
    staleTime: 60 * 60 * 1000,
  })
  const produtosQuery = useQuery({
    queryKey: ["bi", "metadata", "produtos"],
    queryFn: () => biMetadata.produtos(),
    staleTime: 60 * 60 * 1000,
  })
  const uaOptions = React.useMemo(
    () => (uasQuery.data ?? []).map((u) => ({ value: String(u.id), label: u.nome })),
    [uasQuery.data],
  )
  const produtoOptions = React.useMemo(
    () =>
      (produtosQuery.data ?? []).map((p) => ({
        value: p.sigla,
        label: `${p.nome} (${p.sigla})`,
      })),
    [produtosQuery.data],
  )

  // Ranking de cedentes — nivel de overview + ponto de entrada da espinha.
  const q = useQuery({
    queryKey: ["bi", "operacoes5", "cedentes", filtersWithFocus],
    queryFn: () => biOperacoes5.cedentes(filtersWithFocus),
  })
  const bundle = q.data?.data

  const kpis = React.useMemo(() => {
    if (!bundle) return null
    const nOp = bundle.cedentes.reduce((s, c) => s + c.n_op, 0)
    const yieldPct =
      bundle.vop_total > 0 ? (bundle.receita_total / bundle.vop_total) * 100 : null
    return {
      vop: bundle.vop_total,
      receita: bundle.receita_total,
      cedentes: bundle.total,
      nOp,
      yieldPct,
    }
  }, [bundle])

  const [scrollRef, scrolled] = useScrollShadow<HTMLDivElement>()

  // Navega para a ROTA do cedente preservando os filtros globais (URL e a
  // fonte da verdade — useBiFilters le da query). Cedente sem id (n/d) nao
  // navega: nao ha rota possivel sem chave.
  const goCedente = React.useCallback(
    (cedenteId: number | null) => {
      if (cedenteId == null) {
        toast.info("Cedente sem identificador — sem detalhe disponível.")
        return
      }
      const qs = sp.toString()
      router.push(`/bi/operacoes5/cedente/${cedenteId}${qs ? `?${qs}` : ""}`)
    },
    [router, sp],
  )

  const columns = React.useMemo(() => buildCedenteColumns(), [])

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col overflow-hidden">
      {/* Title row */}
      <div className="shrink-0 bg-white px-6 pt-3.5 pb-3 dark:bg-gray-950">
        <PageHeader
          title="BI · Operações · Drill por dimensão"
          info="Espinha de aprofundamento UA → Produto → Cedente → Operação → Documento. Clique num cedente para abrir sua tela (operações → documentos). Regime caixa (wh_operacao); o rodapé da tabela reconcilia com o VOP total do recorte."
          subtitle="BI · Operações · Cedentes"
        />
      </div>

      {/* Toolbar de filtros */}
      <div
        className={cx(
          "shrink-0 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
          scrolled && "scroll-shadow",
        )}
      >
        <div className="flex h-[52px] items-center gap-2 px-6">
          <FilterChip
            label="Período"
            value={preset ? PRESET_LABEL_MAP[preset] : "Personalizado"}
            active={preset !== null && preset !== "12m"}
            icon={RiCalendarLine}
          >
            <div className="py-1">
              {PRESET_OPTIONS.map((opt) => (
                <button
                  key={opt.key}
                  type="button"
                  onClick={() => setFilter({ preset: opt.key })}
                  className={cx(
                    "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                    preset === opt.key
                      ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                      : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
                  )}
                >
                  <span className="flex-1 text-left">{opt.label}</span>
                  {preset === opt.key && (
                    <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />
                  )}
                </button>
              ))}
            </div>
          </FilterChip>

          <FilterChip
            label="Produto"
            value={multiLabel(filtersWithFocus.produtoSigla, produtoOptions)}
            active={(filtersWithFocus.produtoSigla?.length ?? 0) > 0}
          >
            <MultiCheckList
              options={produtoOptions}
              selected={filtersWithFocus.produtoSigla ?? []}
              onChange={(next) =>
                setFilter({ produtoSigla: next.length > 0 ? next : undefined })
              }
            />
          </FilterChip>

          <FilterChip
            label="UA"
            value={multiLabel((filtersWithFocus.uaId ?? []).map(String), uaOptions)}
            active={(filtersWithFocus.uaId?.length ?? 0) > 0}
          >
            <MultiCheckList
              options={uaOptions}
              selected={(filtersWithFocus.uaId ?? []).map(String)}
              onChange={(next) =>
                setFilter({
                  uaId:
                    next.length > 0
                      ? next.map((x) => Number(x)).filter(Number.isFinite)
                      : undefined,
                })
              }
            />
          </FilterChip>

          <MoreFiltersButton />

          <Button
            variant="ghost"
            onClick={resetFilters}
            disabled={!hasFiltrosAtivos(preset, filtersWithFocus)}
            className="ml-1"
          >
            <RiRefreshLine className="size-3.5 shrink-0" aria-hidden="true" />
            Resetar
          </Button>

          <span className="ml-auto shrink-0 text-[11px] text-gray-500 dark:text-gray-400">
            {q.isFetching ? "Atualizando…" : "Atualizado"}
          </span>
        </div>
      </div>

      {/* Conteudo */}
      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4">
        <div className="flex flex-col gap-4">
          {q.isLoading && <PaginaSkeleton />}
          {q.isError && (
            <Card className={cx(cardTokens.body, "py-12 text-center")}>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Não foi possível carregar o ranking de cedentes.
              </p>
              <Button variant="ghost" className="mt-2" onClick={() => q.refetch()}>
                Tentar novamente
              </Button>
            </Card>
          )}

          {bundle && kpis && (
            <>
              {/* KPIs do recorte */}
              <section className="grid grid-cols-2 gap-4 xl:grid-cols-4">
                <KpiTile label="VOP no período" value={fmt.currencyCompact.format(kpis.vop)} />
                <KpiTile
                  label="Receita (regime caixa)"
                  value={fmt.currencyCompact.format(kpis.receita)}
                  hint={kpis.yieldPct != null ? `yield ${fmtPct2(kpis.yieldPct)}` : undefined}
                />
                <KpiTile label="Cedentes" value={fmt.number.format(kpis.cedentes)} />
                <KpiTile label="Operações" value={fmt.number.format(kpis.nOp)} />
              </section>

              {/* Ranking de cedentes — clicavel (entra na rota do cedente) */}
              <Card className={cx(cardTokens.body, "p-0")}>
                <div className="flex items-center justify-between px-4 py-3">
                  <div>
                    <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
                      Cedentes
                    </h2>
                    <p className="text-[11px] text-gray-500 dark:text-gray-400">
                      {fmt.number.format(bundle.total)} cedentes · clique para abrir
                    </p>
                  </div>
                </div>
                <DataTable<Operacoes5CedenteItem>
                  data={bundle.cedentes}
                  columns={columns}
                  density="compact"
                  onRowClick={(row) => goCedente(row.cedente_id)}
                  renderFooter={(rows) => {
                    const vop = rows.reduce(
                      (s, r) => s + (r as Operacoes5CedenteItem).vop,
                      0,
                    )
                    const receita = rows.reduce(
                      (s, r) => s + (r as Operacoes5CedenteItem).receita,
                      0,
                    )
                    return (
                      <tr>
                        <td className="px-3 py-2 text-xs text-gray-500 dark:text-gray-400">
                          {fmt.number.format(rows.length)} cedente
                          {rows.length === 1 ? "" : "s"}
                        </td>
                        <td className="px-3 py-2" />
                        <td className="px-3 py-2 text-right text-xs font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                          {fmt.currencyWhole.format(vop)}
                        </td>
                        {/* share · deságio · taxa_final · prazo */}
                        <td className="px-3 py-2" />
                        <td className="px-3 py-2" />
                        <td className="px-3 py-2" />
                        <td className="px-3 py-2" />
                        <td className="px-3 py-2 text-right text-xs font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                          {fmt.currencyWhole.format(receita)}
                        </td>
                      </tr>
                    )
                  }}
                  className="h-full"
                />
              </Card>
            </>
          )}
        </div>
      </div>

      <ProvenanceFooter provenance={q.data?.provenance} />
    </div>
  )
}

// ─── Colunas do ranking de cedentes ────────────────────────────────────────

const col = createColumnHelper<Operacoes5CedenteItem>()

function buildCedenteColumns(): ColumnDef<Operacoes5CedenteItem, unknown>[] {
  return [
    col.accessor("cedente_nome", {
      header: "Cedente",
      size: 280,
      cell: (info) => {
        const r = info.row.original
        return (
          <div className="flex items-center gap-2">
            <RiArrowRightSLine
              className="size-4 shrink-0 text-gray-400 dark:text-gray-600"
              aria-hidden
            />
            <div className="min-w-0">
              {/* Nome abre o peek da entidade (?entidade=); o resto da linha
                  continua navegando pra rota do cedente (espinha do drill). */}
              <EntidadeLink
                documento={r.cedente_documento}
                className={cx("block truncate", tableTokens.cellText)}
              >
                {r.cedente_nome}
              </EntidadeLink>
              {r.cedente_documento && (
                <p className={cx("truncate tabular-nums", tableTokens.cellSecondary)}>
                  {fmtCNPJ(r.cedente_documento)}
                </p>
              )}
            </div>
          </div>
        )
      },
    }) as ColumnDef<Operacoes5CedenteItem, unknown>,
    col.accessor("n_op", {
      header: "Operações",
      size: 90,
      cell: (info) => (
        <span className={tableTokens.cellNumber}>
          {fmt.number.format(info.getValue<number>())}
        </span>
      ),
    }) as ColumnDef<Operacoes5CedenteItem, unknown>,
    col.accessor("vop", {
      header: "VOP",
      size: 130,
      cell: (info) => (
        <div className={cx("text-right", tableTokens.cellNumber)}>
          {fmt.currencyWhole.format(info.getValue<number>())}
        </div>
      ),
    }) as ColumnDef<Operacoes5CedenteItem, unknown>,
    col.accessor("share_pct", {
      header: "Share",
      size: 80,
      cell: (info) => (
        <div className={cx("text-right", tableTokens.cellNumberSecondary)}>
          {fmtPct2(info.getValue<number>())}
        </div>
      ),
    }) as ColumnDef<Operacoes5CedenteItem, unknown>,
    col.accessor("taxa_media", {
      header: "Deságio méd.",
      size: 90,
      cell: (info) => {
        const v = info.getValue<number | null>()
        return (
          <div className={cx("text-right", tableTokens.cellNumberSecondary)}>
            {v != null ? fmtPct2(v) : "—"}
          </div>
        )
      },
    }) as ColumnDef<Operacoes5CedenteItem, unknown>,
    col.accessor("taxa_final", {
      header: "Taxa final",
      size: 90,
      cell: (info) => {
        const v = info.getValue<number | null>()
        return (
          <div className={cx("text-right font-medium", tableTokens.cellNumber)}>
            {v != null ? fmtPct2(v) : "—"}
          </div>
        )
      },
    }) as ColumnDef<Operacoes5CedenteItem, unknown>,
    col.accessor("prazo_medio", {
      header: "Prazo méd.",
      size: 90,
      cell: (info) => {
        const v = info.getValue<number | null>()
        return (
          <div className={cx("text-right", tableTokens.cellNumber)}>
            {v != null ? fmtDias(v) : "—"}
          </div>
        )
      },
    }) as ColumnDef<Operacoes5CedenteItem, unknown>,
    col.accessor("receita", {
      header: "Receita",
      size: 120,
      cell: (info) => (
        <div className={cx("text-right", tableTokens.cellNumber)}>
          {fmt.currencyWhole.format(info.getValue<number>())}
        </div>
      ),
    }) as ColumnDef<Operacoes5CedenteItem, unknown>,
  ]
}

// ─── KPI tile ──────────────────────────────────────────────────────────────

function KpiTile({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint?: string
}) {
  return (
    <Card className={cx(cardTokens.body, "p-4")}>
      <p className="text-[11px] uppercase tracking-wider text-gray-500 dark:text-gray-400">
        {label}
      </p>
      <p className="mt-1 text-xl font-semibold tabular-nums text-gray-900 dark:text-gray-50">
        {value}
      </p>
      {hint && (
        <p className="mt-0.5 text-[11px] text-gray-500 dark:text-gray-400">{hint}</p>
      )}
    </Card>
  )
}

// ─── Skeleton ──────────────────────────────────────────────────────────────

function PaginaSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <div
            key={i}
            className="h-20 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900"
          />
        ))}
      </div>
      <div className="h-96 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
    </div>
  )
}

// ─── Helpers de filtro (clones de operacoes4) ──────────────────────────────

type MultiOption = { value: string; label: string }

function multiLabel(
  selected: string[] | undefined,
  options: MultiOption[],
  placeholder = "Todos",
): string {
  if (!selected || selected.length === 0) return placeholder
  if (selected.length === 1) {
    const opt = options.find((o) => o.value === selected[0])
    return opt?.label ?? selected[0]
  }
  if (options.length > 0 && selected.length === options.length) return "Todos"
  return `${selected.length} selecionados`
}

function hasFiltrosAtivos(
  preset: PresetKey | null,
  filtros: { produtoSigla?: string[]; uaId?: number[] },
): boolean {
  if (preset !== null && preset !== "12m") return true
  if (filtros.produtoSigla && filtros.produtoSigla.length > 0) return true
  if (filtros.uaId && filtros.uaId.length > 0) return true
  return false
}

function MultiCheckList({
  options,
  selected,
  onChange,
}: {
  options: MultiOption[]
  selected: string[]
  onChange: (next: string[]) => void
}) {
  const set = React.useMemo(() => new Set(selected), [selected])
  const toggle = React.useCallback(
    (value: string, checked: boolean) => {
      const next = new Set(set)
      if (checked) next.add(value)
      else next.delete(value)
      onChange(Array.from(next))
    },
    [set, onChange],
  )
  return (
    <div className="max-h-72 overflow-y-auto py-1">
      {options.length === 0 && (
        <p className="px-3 py-2 text-xs text-gray-400 dark:text-gray-600">
          Nenhuma opção disponível.
        </p>
      )}
      {options.map((opt) => {
        const isChecked = set.has(opt.value)
        return (
          <label
            key={opt.value}
            className="flex cursor-pointer items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors hover:bg-gray-100 dark:hover:bg-gray-800"
          >
            <Checkbox
              checked={isChecked}
              onCheckedChange={(c) => toggle(opt.value, c === true)}
            />
            <span className="flex-1 text-gray-700 dark:text-gray-300">
              {opt.label}
            </span>
          </label>
        )
      })}
    </div>
  )
}
