"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import {
  RiArrowDownSLine,
  RiArrowUpSLine,
  RiBarChart2Line,
  RiBuilding2Line,
  RiLineChartLine,
  RiSubtractLine,
} from "@remixicon/react"

import { LineChart } from "@/components/charts/LineChart"
import { SparkAreaChart } from "@/components/charts/SparkChart"
import { ChartSkeleton } from "@/components/app/ChartSkeleton"
import { cx, focusRing } from "@/lib/utils"
import { biMetadata } from "@/lib/api-client"
import type {
  CategoryValueDelta,
  Point,
  PointDim,
  SeriesEVolume,
} from "@/lib/api-client"

//
// Formatters
//

const moedaCompacta = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
})

const numero = new Intl.NumberFormat("pt-BR")

const pct1 = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(1)}%`

/**
 * Formata valor em milhoes com 1 casa decimal, sem prefixo "R$" nem sufixo
 * "mi". Usado em data labels onde o contexto (eixo Y, legenda, titulo do
 * chart) ja comunica que estamos falando de volume em R$ milhoes.
 * Ex.: 24_033_219 -> "24,0"
 */
const milhoes1 = (v: number) =>
  (v / 1_000_000).toLocaleString("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })

//
// Helpers
//

function labelForPeriodo(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number)
  if (d === 1) {
    return new Date(y, m - 1, 1).toLocaleString("pt-BR", {
      month: "short",
      year: "2-digit",
    })
  }
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}`
}

type PivotedRow = {
  periodo: string
  _iso: string
  [categoria: string]: number | string
}

function pivotPointsDim(
  points: PointDim[],
  /**
   * Opcional: traduz a `categoria` recebida do backend (tipicamente uma
   * sigla curta como "FAT") para um nome amigavel antes de pivotar.
   * Usado para que a legenda/chart renderize "Faturização" em vez de "FAT".
   */
  relabel?: (categoria: string) => string,
): { rows: PivotedRow[]; categories: string[] } {
  const byPeriodo = new Map<string, PivotedRow>()
  const catSet = new Set<string>()

  for (const p of points) {
    const key = p.periodo
    const cat = relabel ? relabel(p.categoria) : p.categoria
    if (!byPeriodo.has(key)) {
      byPeriodo.set(key, {
        periodo: labelForPeriodo(p.periodo),
        _iso: p.periodo,
      })
    }
    const row = byPeriodo.get(key)!
    row[cat] = ((row[cat] as number) ?? 0) + p.valor
    catSet.add(cat)
  }

  const rows = Array.from(byPeriodo.values()).sort((a, b) =>
    a._iso < b._iso ? -1 : 1,
  )
  const categories = Array.from(catSet)
  for (const row of rows) {
    for (const c of categories) {
      if (row[c] === undefined) row[c] = 0
    }
  }
  return { rows, categories }
}

/**
 * Busca o mapa {sigla -> nome completo} via API (fonte canonica =
 * wh_dim_produto populada pelo adapter Bitfin). Cache longo (1h) —
 * taxonomia muda raramente.
 *
 * Quando a query ainda nao carregou OU falhou, retorna o identity
 * (nome == sigla) para que a UI funcione em modo degradado sem quebrar.
 */
function useProdutosNomeMap(): (sigla: string) => string {
  const q = useQuery({
    queryKey: ["bi", "metadata", "produtos"],
    queryFn: () => biMetadata.produtos(),
    staleTime: 60 * 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
  const map = React.useMemo(() => {
    const m = new Map<string, string>()
    for (const p of q.data ?? []) m.set(p.sigla, p.nome)
    return m
  }, [q.data])
  return React.useCallback(
    (sigla: string) => map.get(sigla) ?? sigla,
    [map],
  )
}

//
// DeltaMini
//

function DeltaMini({ value }: { value: number | null }) {
  if (value === null || Number.isNaN(value)) {
    return (
      <span className="inline-flex items-center gap-0.5 text-[10px] font-medium text-gray-400 tabular-nums">
        <RiSubtractLine className="size-3" aria-hidden="true" />—
      </span>
    )
  }
  const isPositive = value > 0
  const isNegative = value < 0
  return (
    <span
      className={cx(
        "inline-flex items-center gap-0.5 text-[10px] font-medium tabular-nums",
        isPositive && "text-emerald-600 dark:text-emerald-500",
        isNegative && "text-rose-600 dark:text-rose-500",
        !isPositive && !isNegative && "text-gray-500",
      )}
    >
      {isPositive && <RiArrowUpSLine className="size-3" aria-hidden="true" />}
      {isNegative && <RiArrowDownSLine className="size-3" aria-hidden="true" />}
      {pct1(value)}
    </span>
  )
}

//
// Tabs internos (3: Produto | Empresa | MoM)
//

type TabId = "produto" | "ua" | "mom"

const TABS: { id: TabId; label: string; icon: typeof RiBarChart2Line }[] = [
  { id: "produto", label: "Produto", icon: RiBarChart2Line },
  { id: "ua", label: "Empresa", icon: RiBuilding2Line },
  { id: "mom", label: "MoM", icon: RiLineChartLine },
]

function IndicadoresTabs({
  active,
  onChange,
}: {
  active: TabId
  onChange: (id: TabId) => void
}) {
  return (
    <div
      role="tablist"
      className="inline-flex w-full rounded border border-gray-200 bg-gray-50 p-0.5 dark:border-gray-800 dark:bg-gray-900"
    >
      {TABS.map((t) => {
        const isActive = active === t.id
        const Icon = t.icon
        return (
          <button
            key={t.id}
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(t.id)}
            className={cx(
              "flex flex-1 items-center justify-center gap-1 rounded px-2 py-1 text-xs font-medium transition",
              // Tab ativa em NEUTRO (cinza) — azul fica reservado para
              // estado de filtro/foco aplicado. Tabs sao navegacao pura,
              // nao deveriam competir visualmente com chips de filtro.
              // CLAUDE.md §4: blue = atencao/selecao; slate/gray = neutros.
              isActive
                ? "bg-white text-gray-900 shadow-xs ring-1 ring-gray-200 dark:bg-gray-800 dark:text-gray-50 dark:ring-gray-700"
                : "text-gray-600 hover:text-gray-900 dark:text-gray-400 hover:dark:text-gray-50",
              focusRing,
            )}
          >
            <Icon className="size-3.5 shrink-0" aria-hidden="true" />
            <span>{t.label}</span>
          </button>
        )
      })}
    </div>
  )
}

//
// ─── Tab: Produto — tabela analitica com sparkline inline ─────────
//
// Cada linha: # | Nome | % | Volume | Taxa a.m. | Prazo (d) | Tendencia 90d
// A coluna Tendencia combina sparkline semanal (13 pts) com seta/% de
// variacao vs 90d anteriores — inspirado em dashboards financeiros
// (Bloomberg Terminal, Stripe Dashboard) que priorizam densidade de
// informacao acionavel sobre espacamento.
//

// Unidade intencionalmente omitida dos valores — o rotulo da coluna
// ("TAXA", "PRAZO") ja identifica a metrica. Evita repetir "% a.m." e
// "d" em cada linha, reduzindo ruido visual.
const taxaFmt = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `${v.toFixed(2)}%`

const prazoFmt = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `${v.toFixed(0)}`

/**
 * Coluna Tendencia 90d — sparkline (forma) + seta/% (direcao). Serve pro
 * analista ler em 1 segundo se o produto esta em alta/baixa e comparar
 * trajetorias entre linhas.
 */
function TendenciaCell({
  pontos,
  deltaPct,
}: {
  pontos: Point[] | undefined
  deltaPct: number | null | undefined
}) {
  const sparkData = React.useMemo(
    () =>
      (pontos ?? []).map((p) => ({
        periodo: typeof p.periodo === "string" ? p.periodo : String(p.periodo),
        valor: p.valor,
      })),
    [pontos],
  )

  if (sparkData.length < 2) {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] text-gray-400 tabular-nums">
        <RiSubtractLine className="size-3" aria-hidden="true" />—
      </span>
    )
  }

  const isPos = (deltaPct ?? 0) > 0.05
  const isNeg = (deltaPct ?? 0) < -0.05

  return (
    <span className="inline-flex items-center gap-1.5">
      <SparkAreaChart
        data={sparkData}
        index="periodo"
        categories={["valor"]}
        colors={[
          isPos ? "emerald" : isNeg ? "rose" : "slate",
        ]}
        className="h-5 w-16 shrink-0"
      />
      {deltaPct === null || deltaPct === undefined ? (
        <span className="text-[10px] text-gray-400">—</span>
      ) : (
        <span
          className={cx(
            "inline-flex items-center gap-0.5 text-[10px] font-medium tabular-nums w-14 justify-end",
            isPos && "text-emerald-600 dark:text-emerald-500",
            isNeg && "text-rose-600 dark:text-rose-500",
            !isPos && !isNeg && "text-gray-500",
          )}
        >
          {isPos && <RiArrowUpSLine className="size-3" aria-hidden="true" />}
          {isNeg && <RiArrowDownSLine className="size-3" aria-hidden="true" />}
          {(deltaPct >= 0 ? "+" : "") + deltaPct.toFixed(1) + "%"}
        </span>
      )}
    </span>
  )
}

function TabProduto({
  items,
  total,
  nomeCompletoDe,
  focusSigla,
  onItemClick,
}: {
  items: CategoryValueDelta[]
  total: number
  nomeCompletoDe: (sigla: string) => string
  focusSigla?: string
  onItemClick?: (sigla: string) => void
}) {
  const hasFocus = Boolean(focusSigla)

  if (items.length === 0) {
    return <EmptyState message="Sem dados no período." />
  }

  return (
    // HTML table resolve alinhamento por coluna automaticamente — cada
    // <td> compartilha largura com o <th> da mesma coluna via layout
    // nativo (impossivel com grids independentes por linha).
    <table className="w-full border-collapse">
      <thead>
        <tr className="border-b border-gray-200 dark:border-gray-800">
          <th className="w-6 px-1 py-1 text-right text-[10px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            #
          </th>
          <th className="px-1 py-1 text-left text-[10px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Produto
          </th>
          <th className="px-1 py-1 text-right text-[10px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            %
          </th>
          <th className="px-1 py-1 text-right text-[10px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Volume
          </th>
          <th className="px-1 py-1 text-right text-[10px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Taxa
          </th>
          <th className="px-1 py-1 text-right text-[10px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Prazo
          </th>
          <th className="px-1 py-1 text-right text-[10px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Tend. 90d
          </th>
        </tr>
      </thead>
      <tbody>
        {items.map((item, idx) => {
          const pct = total > 0 ? (item.valor / total) * 100 : 0
          const sigla = item.categoria_id ?? item.categoria
          const nome = nomeCompletoDe(sigla)
          const isFocused = sigla === focusSigla
          const muted = hasFocus && !isFocused

          return (
            <tr
              key={sigla}
              aria-pressed={isFocused}
              tabIndex={onItemClick ? 0 : undefined}
              role={onItemClick ? "button" : undefined}
              onClick={
                onItemClick ? () => onItemClick(sigla) : undefined
              }
              onKeyDown={
                onItemClick
                  ? (e) => {
                      if (e.key === "Enter" || e.key === " ") {
                        e.preventDefault()
                        onItemClick(sigla)
                      }
                    }
                  : undefined
              }
              className={cx(
                "transition",
                onItemClick &&
                  "cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-900",
                isFocused && "bg-blue-50 dark:bg-blue-500/10",
                muted && "opacity-40",
              )}
            >
              <td className="px-1 py-1.5 text-right text-[11px] tabular-nums text-gray-400">
                {idx + 1}.
              </td>
              <td className="truncate px-1 py-1.5 text-left text-xs text-gray-900 dark:text-gray-50">
                {nome}
              </td>
              <td className="px-1 py-1.5 text-right text-[11px] font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                {pct.toFixed(1)}%
              </td>
              <td className="px-1 py-1.5 text-right text-[11px] tabular-nums text-gray-500">
                {moedaCompacta.format(item.valor)}
              </td>
              <td className="px-1 py-1.5 text-right text-[11px] tabular-nums text-gray-700 dark:text-gray-300">
                {taxaFmt(item.taxa_media_pct)}
              </td>
              <td className="px-1 py-1.5 text-right text-[11px] tabular-nums text-gray-700 dark:text-gray-300">
                {prazoFmt(item.prazo_medio_dias)}
              </td>
              <td className="px-1 py-1.5 text-right align-middle">
                <TendenciaCell
                  pontos={item.tendencia_90d}
                  deltaPct={item.tendencia_90d_delta_pct ?? null}
                />
              </td>
            </tr>
          )
        })}
      </tbody>
    </table>
  )
}

//
// ─── Tab: UA/Empresa ──────────
//

function TabUa({ points }: { points: PointDim[] }) {
  const { rows, categories } = React.useMemo(() => pivotPointsDim(points), [
    points,
  ])

  if (rows.length === 0) {
    return <EmptyState message="Sem dados por UA no período." />
  }

  return (
    <div className="flex flex-col gap-2">
      <LineChart
        data={rows}
        index="periodo"
        categories={categories}
        valueFormatter={(v) => moedaCompacta.format(v)}
        className="h-64"
        showLegend
        yAxisWidth={76}
        // Chart do painel lateral tem pouca altura — tooltip flutuante
        // sobrepoe a propria linha. Desligado para leitura limpa de
        // trajetoria; legenda + eixo Y ja dao referencia numerica.
        showTooltip={false}
        // Rotulos de dados em milhoes (1 casa decimal), sem prefixo "R$"
        // nem sufixo "mi" — eixo Y ja contextualiza a unidade.
        showLabels
        labelFormatter={milhoes1}
      />
      <p className="text-[11px] text-gray-500 dark:text-gray-400">
        Uma linha por unidade administrativa. Identifica qual empresa puxa
        ou freia o volume agregado.
      </p>
    </div>
  )
}

//
// ─── Tab: MoM ──────────
//

function TabMom({
  items,
  nomeCompletoDe,
}: {
  items: CategoryValueDelta[]
  nomeCompletoDe: (sigla: string) => string
}) {
  if (items.length === 0) {
    return <EmptyState message="Sem dados para calcular MoM." />
  }
  const sorted = [...items].sort((a, b) => {
    const aDelta = a.delta_pct ?? 0
    const bDelta = b.delta_pct ?? 0
    return Math.abs(bDelta) - Math.abs(aDelta)
  })

  return (
    <ul className="flex flex-col gap-1">
      {sorted.map((item) => {
        const sigla = item.categoria_id ?? item.categoria
        return (
          <li
            key={sigla}
            className="flex items-center justify-between gap-2 rounded px-2 py-1.5"
          >
            <span className="truncate text-sm text-gray-900 dark:text-gray-50">
              {nomeCompletoDe(sigla)}
            </span>
            <div className="flex shrink-0 items-center gap-3 text-xs tabular-nums">
              <span className="text-gray-500">
                {moedaCompacta.format(item.valor)}
              </span>
              <DeltaMini value={item.delta_pct} />
            </div>
          </li>
        )
      })}
    </ul>
  )
}

function EmptyState({ message }: { message: string }) {
  return (
    <p className="py-8 text-center text-sm text-gray-500 dark:text-gray-400">
      {message}
    </p>
  )
}

//
// ─── VolumeIndicadoresPanel ──────────
//

type Props = {
  /**
   * Fonte primaria para agregacoes (listas/rankings) — tab Produto.lista,
   * tab MoM. Espera-se `filtersWithFocusMes` aplicado (source de produto,
   * destino de mes).
   */
  data: SeriesEVolume | undefined
  /**
   * Fonte dos charts temporais (mini-charts mensais dentro das tabs
   * Produto.evolucao e Empresa). Espera-se `filtersWithFocusProduto`
   * aplicado — esses charts sao source de mes e nao devem colapsar
   * quando o usuario clica numa barra mensal do chart principal.
   *
   * Se `undefined`, cai em `data` como fallback (comportamento legado).
   */
  chartData?: SeriesEVolume | undefined
  loading?: boolean
  /** Sigla do produto em foco (cross-filter). Destaca na lista e muta os
   *  demais. Passar `undefined` para nenhum foco. */
  focusSigla?: string
  onProdutoClick?: (sigla: string) => void
  className?: string
}

export function VolumeIndicadoresPanel({
  data,
  chartData,
  loading,
  focusSigla,
  onProdutoClick,
  className,
}: Props) {
  // Fonte efetiva para charts temporais: prefere chartData; fallback = data
  const chartSrc = chartData ?? data
  const [tab, setTab] = React.useState<TabId>("produto")
  const nomeCompletoDe = useProdutosNomeMap()

  const produtoTotal = React.useMemo(
    () => (data?.por_produto ?? []).reduce((acc, p) => acc + p.valor, 0),
    [data?.por_produto],
  )

  // Informativo no header: quantos produtos tem dados no periodo.
  const produtosCount = data?.por_produto?.length ?? 0

  return (
    <div
      className={cx(
        "flex flex-col gap-3 rounded border border-gray-200 p-5 dark:border-gray-800",
        className,
      )}
    >
      <div className="flex items-baseline justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
            Indicadores
          </h3>
          <p className="text-[11px] text-gray-500 dark:text-gray-400">
            {tab === "produto" &&
              `Top produtos (${numero.format(produtosCount)}) e evolução mensal`}
            {tab === "ua" && "Evolução mensal por unidade administrativa"}
            {tab === "mom" && "Variação mês a mês por produto"}
          </p>
        </div>
      </div>

      <IndicadoresTabs active={tab} onChange={setTab} />

      {loading ? (
        <ChartSkeleton variant="table" className="h-64" />
      ) : (
        <div className="min-h-64">
          {tab === "produto" && (
            // TabProduto agora e tabela analitica com sparkline inline
            // (tendencia 90d embutida em cada linha) — nao usa mais
            // `chartSrc` porque nao ha mini-chart comparativo.
            <TabProduto
              items={data?.por_produto ?? []}
              total={produtoTotal}
              nomeCompletoDe={nomeCompletoDe}
              focusSigla={focusSigla}
              onItemClick={onProdutoClick}
            />
          )}
          {tab === "ua" && (
            // Chart temporal de evolucao por UA — mesmo principio do
            // evolucao_por_produto: precisa da fonte source-de-mes para
            // exibir toda a linha temporal independente de focusMes.
            <TabUa points={chartSrc?.evolucao_por_ua ?? []} />
          )}
          {tab === "mom" && (
            <TabMom
              items={data?.por_produto ?? []}
              nomeCompletoDe={nomeCompletoDe}
            />
          )}
        </div>
      )}
    </div>
  )
}
