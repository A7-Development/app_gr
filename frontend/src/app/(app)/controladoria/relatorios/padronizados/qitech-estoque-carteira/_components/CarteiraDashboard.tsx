// _components/CarteiraDashboard.tsx
//
// Dashboard rico da carteira FIDC (KPIs + charts + tabela + drilldown).
// E o "destino" dentro da rota — exibido quando ha `?data=YYYY-MM-DD` na URL.
// A landing (sem `?data=`) e a SnapshotsLanding.
//
// `dataReferencia` chega como prop (do searchParam da page.tsx). Mudancas no
// filter chip de data fazem router.push(`?data=YYYY-MM-DD`) — URL e a fonte
// unica da verdade.

"use client"

import * as React from "react"
import { usePathname, useRouter } from "next/navigation"
import { useMutation, useQuery } from "@tanstack/react-query"
import {
  RiArrowLeftLine,
  RiCalendarLine,
  RiDownloadLine,
  RiFileChart2Line,
} from "@remixicon/react"
import { toast } from "sonner"
import type { EChartsOption } from "echarts"

import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import { Input } from "@/components/tremor/Input"
import {
  TabNavigation,
  TabNavigationLink,
} from "@/components/tremor/TabNavigation"
import {
  DataTableShell,
  EmptyState,
  ErrorState,
  EChartsCard,
  PageHeader,
} from "@/design-system/components"
import { cardTokens } from "@/design-system/tokens/card"
import {
  FilterChip,
  FilterSearch,
} from "@/design-system/components/FilterBar"
import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"
import {
  ProvenanceFooter,
  type ProvenanceSource,
} from "@/design-system/components/ProvenanceFooter"
import { useScrollShadow } from "@/lib/hooks/use-scroll-shadow"
import { useUAs } from "@/lib/hooks/cadastros"
import { cx } from "@/lib/utils"

import {
  relatorios,
  type CarteiraBreakdownItem,
  type CarteiraKpis,
} from "../../../_lib/api"
import {
  columns as carteiraColumns,
  itemNoun as carteiraItemNoun,
  type EstoqueRecebivelRow,
} from "@/lib/reports/qitech-estoque-carteira"
import { brl, brlMi, formatDateBR, mapProvenance, pct } from "./format"

const SLUG = "qitech-estoque-carteira"
const TABS = [{ key: "carteira", label: "Carteira" }] as const
type TabKey = (typeof TABS)[number]["key"]

// Paleta sequencial para faixa PDD (Bacen Resol. 2682 A→H, baixo→alto risco).
const FAIXA_COLORS = [
  "#10B981", // A
  "#34D399", // B
  "#FBBF24", // C
  "#F59E0B", // D
  "#F97316", // E
  "#EF4444", // F
  "#DC2626", // G
  "#991B1B", // H
]

// ─────────────────────────────────────────────────────────────────────────────
// Chart builders
// ─────────────────────────────────────────────────────────────────────────────

type BreakdownItem = {
  chave: string
  label: string
  valor_nominal: string | number
  // So vem populado em `por_faixa_pdd` (decomposicao real de valor_pdd_total).
  valor_pdd?: string | number | null
  qtd_titulos: number
  pct_do_total: number
}

function buildFaixaPddOption(items: BreakdownItem[]): EChartsOption {
  const ordered = [...items].sort((a, b) => a.chave.localeCompare(b.chave))
  const labels = ordered.map((i) => i.chave)
  // Y axis = valor_pdd (decomposicao real da provisao por faixa Bacen 2682).
  // Soma das barras casa com `kpis.valor_pdd_total` no header do card.
  // Decisao 2026-05-10 (Opcao A): mostrar PDD em vez de valor_nominal porque
  // o titulo do card e "PDD por faixa".
  const values = ordered.map((i) => Number(i.valor_pdd ?? 0))
  return {
    grid: { top: 8, right: 12, bottom: 28, left: 40 },
    xAxis: { type: "category", data: labels, axisTick: { show: false } },
    yAxis: { type: "value", axisLabel: { formatter: (v: number) => brlMi(v) } },
    tooltip: {
      trigger: "axis",
      formatter: (params: unknown) => {
        const arr = params as Array<{ name: string; value: number }>
        const p = arr[0]
        const item = ordered.find((i) => i.chave === p.name)
        if (!item) return ""
        const pddValue = Number(item.valor_pdd ?? 0)
        const nominalValue = Number(item.valor_nominal)
        const pddRatePct =
          nominalValue > 0 ? (pddValue / nominalValue) * 100 : 0
        return [
          `<b>Faixa ${p.name}</b>`,
          `PDD: ${brl(pddValue)}`,
          `Nominal: ${brl(nominalValue)} (${item.qtd_titulos} titulos)`,
          `PDD/Nominal: ${pct(pddRatePct, 2)}`,
        ].join("<br/>")
      },
    },
    series: [
      {
        type: "bar",
        barMaxWidth: 36,
        // Rotulo de dados no topo de cada barra — valor BRL compacto. Decisao
        // 2026-05-10: card tem espaco pequeno, formato "R$ X mi/k" cabe sem
        // sobrepor; ajuda a leitura sem precisar hover.
        label: {
          show: true,
          position: "top",
          formatter: (params: unknown) =>
            brlMi((params as { value: number }).value),
          fontSize: 10,
          color: "#6B7280", // gray-500 — mesmo tom dos eyebrows do card
        },
        data: values.map((v, i) => ({
          value: v,
          itemStyle: {
            color: FAIXA_COLORS[i % FAIXA_COLORS.length],
            borderRadius: [3, 3, 0, 0],
          },
        })),
      },
    ],
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// CarteiraDashboard
// ─────────────────────────────────────────────────────────────────────────────

type CarteiraDashboardProps = {
  /** YYYY-MM-DD vindo do searchParam da page.tsx. */
  dataReferencia: string
}

export function CarteiraDashboard({ dataReferencia }: CarteiraDashboardProps) {
  const router = useRouter()
  const pathname = usePathname()

  // Filtro de fundo continua local — multi-fundo e edge case e nao precisa de
  // deep-link no MVP. Quando justificar, promover pra ?fundo_id=.
  const [fundoId, setFundoId] = React.useState<string | null>(null)
  const [search, setSearch] = React.useState("")
  const [activeTab, setActiveTab] = React.useState<TabKey>("carteira")
  const [selected, setSelected] = React.useState<EstoqueRecebivelRow | null>(null)

  const uasQuery = useUAs({ tipo: "fidc", ativa: true })
  const fundos = uasQuery.data ?? []
  const fundoSelecionado = fundos.find((f) => f.id === fundoId) ?? null

  const bundleQuery = useQuery({
    queryKey: [
      "controladoria",
      "qitech-estoque-carteira",
      "bundle",
      fundoId,
      dataReferencia,
    ] as const,
    queryFn: () =>
      relatorios.qitechEstoqueCarteiraBundle({
        fundo_id: fundoId ?? undefined,
        data_referencia: dataReferencia,
      }),
    staleTime: 30_000,
  })

  const exportMut = useMutation({
    mutationFn: () =>
      relatorios.qitechEstoqueCarteiraExportXlsx({
        fundo_id: fundoId ?? undefined,
        data_referencia: dataReferencia,
      }),
    onError: (err) => {
      const msg = err instanceof Error ? err.message : String(err)
      toast.error(`Falha ao exportar: ${msg}`)
    },
  })

  const rowsQuery = useQuery({
    queryKey: [
      "controladoria",
      "relatorios",
      "rows",
      SLUG,
      fundoId,
      dataReferencia,
    ] as const,
    queryFn: () =>
      relatorios.rows(SLUG, {
        fundo_id: fundoId ?? undefined,
        periodo_inicio: dataReferencia,
        periodo_fim: dataReferencia,
        page_size: 10_000,
      }),
  })

  const goToLanding = React.useCallback(() => {
    // Remove o ?data= e volta pra landing (lista de snapshots).
    router.push(pathname)
  }, [router, pathname])

  const updateDataParam = React.useCallback(
    (newDate: string | null) => {
      if (newDate) {
        router.push(`${pathname}?data=${newDate}`)
      } else {
        router.push(pathname)
      }
    },
    [router, pathname],
  )

  const provenance = mapProvenance(bundleQuery.data?.provenance)
  const provenanceSources: ProvenanceSource[] = bundleQuery.data?.provenance
    ? [
        {
          label: "QiTech · Estoque",
          updated: bundleQuery.data.provenance.last_ingested_at
            ? formatDateBR(bundleQuery.data.provenance.last_ingested_at)
            : "—",
          sla: "Webhook assincrono",
          stale: false,
        },
      ]
    : []

  const [scrollRef, scrolled] = useScrollShadow<HTMLDivElement>()

  const bundle = bundleQuery.data
  const isLoading = bundleQuery.isLoading
  const isError = bundleQuery.isError
  const isEmpty = !!bundle?.is_empty
  const kpis = bundle?.kpis

  return (
    <div className="flex h-[calc(100vh-3rem)] overflow-hidden">
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Title row */}
        <div className="shrink-0 bg-white px-6 pt-3.5 pb-3 dark:bg-gray-950">
          <PageHeader
            title="Carteira de recebiveis"
            info="Snapshot diario dos recebiveis em carteira do FIDC. Disparado via callback (eventType=fidcEstoque)."
            subtitle={`Snapshot · ${formatDateBR(dataReferencia)}`}
            actions={
              <div className="flex items-center gap-2">
                <Button variant="ghost" onClick={goToLanding}>
                  <RiArrowLeftLine className="mr-1 size-4" aria-hidden />
                  Voltar a lista de snapshots
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => exportMut.mutate()}
                  disabled={exportMut.isPending || !kpis}
                >
                  <RiDownloadLine className="mr-1 size-4" aria-hidden />
                  {exportMut.isPending ? "Exportando..." : "Exportar Excel"}
                </Button>
              </div>
            }
          />
        </div>

        {/* Toolbar (tabs + filtros) */}
        <div
          className={cx(
            "shrink-0 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
            scrolled && "scroll-shadow",
          )}
        >
          <div className="flex h-[52px] items-center gap-2 px-6">
            <TabNavigation className="border-0">
              {TABS.map((t, i) => (
                <TabNavigationLink
                  key={t.key}
                  href="#"
                  active={activeTab === t.key}
                  onClick={(e) => {
                    e.preventDefault()
                    setActiveTab(t.key)
                  }}
                  title={`Cmd/Ctrl + ${i + 1}`}
                >
                  {t.label}
                </TabNavigationLink>
              ))}
            </TabNavigation>

            <div aria-hidden="true" className="mx-1 h-5 w-px bg-gray-200 dark:bg-gray-800" />

            <FilterSearch
              placeholder="Buscar por sacado, cedente, documento..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onClear={() => setSearch("")}
            />

            <FilterChip
              label="Data ref."
              value={formatDateBR(dataReferencia)}
              active
              icon={RiCalendarLine}
            >
              <div className="flex flex-col gap-2 p-2">
                <Input
                  type="date"
                  value={dataReferencia}
                  onChange={(e) => updateDataParam(e.currentTarget.value || null)}
                />
                <Button
                  variant="ghost"
                  className="text-xs"
                  onClick={() => updateDataParam(null)}
                >
                  Voltar a lista
                </Button>
              </div>
            </FilterChip>

            <FilterChip
              label="Fundo"
              value={fundoSelecionado?.nome ?? "Todos"}
              active={fundoId !== null}
            >
              <div className="max-h-64 overflow-y-auto py-1">
                <button
                  type="button"
                  onClick={() => setFundoId(null)}
                  className={cx(
                    "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                    fundoId === null
                      ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                      : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                  )}
                >
                  Todos
                </button>
                {fundos.map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => setFundoId(f.id)}
                    className={cx(
                      "flex w-full flex-col items-start gap-0.5 rounded px-3 py-1.5 text-sm transition-colors",
                      fundoId === f.id
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="font-medium">{f.nome}</span>
                    {f.cnpj && (
                      <span className="text-[11px] text-gray-500 tabular-nums">
                        {f.cnpj}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            </FilterChip>
          </div>
        </div>

        {/* Conteudo scrollavel */}
        <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto px-6 pt-4 pb-6">
          {isError && !isLoading ? (
            <ErrorState
              title="Nao foi possivel carregar a carteira"
              description={
                bundleQuery.error instanceof Error
                  ? bundleQuery.error.message
                  : "Erro desconhecido. Tente novamente em alguns instantes."
              }
              action={
                <Button variant="secondary" onClick={() => bundleQuery.refetch()}>
                  Tentar novamente
                </Button>
              }
            />
          ) : isEmpty && !isLoading ? (
            <EmptyState
              icon={RiFileChart2Line}
              title="Sem carteira para esses filtros"
              description={
                fundoId
                  ? "Esse fundo nao tem snapshot da carteira na data selecionada. Volte a lista de snapshots pra ver datas disponiveis ou solicite uma nova."
                  : "Nao ha snapshot da carteira na data selecionada. Volte a lista de snapshots pra ver datas disponiveis ou solicite uma nova."
              }
              action={
                <Button variant="secondary" onClick={goToLanding}>
                  Ver lista de snapshots
                </Button>
              }
            />
          ) : (
            <div className="flex flex-col gap-4">
              {/* Grid 2x3 — mesmo formato da aba Mes Corrente do /bi/operacoes2.
                  KPI principal de cada card mora no header (sem KpiStrip de
                  topo). 7 dimensoes consolidadas em 6 cards: situacao +
                  coobrigacao compartilham o card "Composicao". */}
              <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
                <ValoresCard kpis={kpis} loading={isLoading} />
                <PddPorFaixaCard
                  items={bundle?.por_faixa_pdd ?? []}
                  pddTotal={kpis?.valor_pdd_total ?? 0}
                  pddMedioPct={kpis?.pdd_medio_pct ?? 0}
                  loading={isLoading}
                />
                <PorProdutoCard
                  items={bundle?.por_produto ?? []}
                  loading={isLoading}
                />
                <ConcentracaoCard
                  title="Top cedentes"
                  items={bundle?.top_cedentes ?? []}
                  top1Pct={kpis?.concentracao_top1_cedentes_pct ?? 0}
                  top5Pct={kpis?.concentracao_top5_cedentes_pct ?? 0}
                />
                <ConcentracaoCard
                  title="Top sacados"
                  items={bundle?.top_sacados ?? []}
                  top1Pct={kpis?.concentracao_top1_sacados_pct ?? 0}
                  top5Pct={kpis?.concentracao_top5_sacados_pct ?? 0}
                />
                <ComposicaoCard
                  situacao={bundle?.por_situacao ?? []}
                  coobrigacao={bundle?.por_coobrigacao ?? []}
                  pctVencido={kpis?.pct_vencido ?? 0}
                />
              </div>

              {/* Tabela */}
              <DataTableShell
                data={(rowsQuery.data?.rows ?? []) as EstoqueRecebivelRow[]}
                columns={carteiraColumns}
                loading={rowsQuery.isLoading}
                error={(rowsQuery.error ?? null) as Error | null}
                onRetry={() => rowsQuery.refetch()}
                onRowClick={(row) => setSelected(row)}
                search={{
                  value: search,
                  onChange: setSearch,
                  placeholder: `Buscar em ${carteiraItemNoun.plural}...`,
                }}
                itemNoun={carteiraItemNoun}
                provenance={provenance}
                emptyState={{
                  icon: RiFileChart2Line,
                  title: "Sem recebiveis",
                  description: "Nao ha registros para os filtros atuais.",
                }}
              />
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="shrink-0 border-t border-gray-200 px-6 py-2 bg-white dark:border-gray-800 dark:bg-gray-950">
          <ProvenanceFooter sources={provenanceSources} />
        </div>
      </div>

      {/* Drill-down */}
      <DrillDownSheet
        open={selected !== null}
        onClose={() => setSelected(null)}
        size="md"
        title="Recebivel"
      >
        {selected && <RecebivelDrill row={selected} />}
      </DrillDownSheet>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Cards do grid 2x3 — KPI no header (sem KpiStrip de topo).
// Cada card carrega o numero que ele decompõe (pattern bi/operacoes2).
// ─────────────────────────────────────────────────────────────────────────────

function CardHeader({
  eyebrow,
  kpiValue,
  kpiSub,
}: {
  eyebrow: string
  kpiValue: string
  kpiSub?: string
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
        {eyebrow}
      </p>
      <p className="flex items-baseline gap-2 tabular-nums">
        <span className="text-[20px] font-semibold leading-none tracking-tight text-gray-900 dark:text-gray-50">
          {kpiValue}
        </span>
        {kpiSub && (
          <span className="text-[11px] text-gray-500 dark:text-gray-400">
            {kpiSub}
          </span>
        )}
      </p>
    </div>
  )
}

// — Card 1: Valores (Aquisicao / Presente / Nominal) ─────────────────────────

function ValoresCard({
  kpis,
  loading,
}: {
  kpis: CarteiraKpis | undefined
  loading: boolean
}) {
  const presente = kpis?.valor_presente_total ?? 0
  const aquisicao = kpis?.valor_aquisicao_total ?? 0
  const nominal = kpis?.valor_nominal_total ?? 0
  // Desagio = (nominal - presente) / nominal. Quanto a carteira foi descontada.
  const desagioPct =
    Number(nominal) > 0
      ? ((Number(nominal) - Number(presente)) / Number(nominal)) * 100
      : 0

  return (
    <Card className={cardTokens.body}>
      <div className="flex h-full flex-col gap-3">
        <CardHeader
          eyebrow="Valores da carteira"
          kpiValue={brl(presente)}
          kpiSub="presente"
        />
        {loading ? (
          <CardSkeleton lines={2} />
        ) : (
          <div className="flex flex-col gap-2 pt-1">
            <ValueRow label="Aquisicao" value={brl(aquisicao)} />
            <ValueRow label="Nominal" value={brl(nominal)} />
            <ValueRow
              label="Desagio"
              value={pct(desagioPct, 2)}
              hint="(nominal - presente) / nominal"
            />
          </div>
        )}
      </div>
    </Card>
  )
}

function ValueRow({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint?: string
}) {
  return (
    <div className="flex items-baseline justify-between gap-2 border-t border-gray-100 pt-2 dark:border-gray-900">
      <div className="flex flex-col">
        <span className="text-xs text-gray-500 dark:text-gray-400">{label}</span>
        {hint && (
          <span className="text-[10px] text-gray-400 dark:text-gray-500">
            {hint}
          </span>
        )}
      </div>
      <span className="text-sm font-medium tabular-nums text-gray-900 dark:text-gray-50">
        {value}
      </span>
    </div>
  )
}

// — Card 2: PDD por faixa (Bacen, valor_pdd > 0) ─────────────────────────────

function PddPorFaixaCard({
  items,
  pddTotal,
  pddMedioPct,
  loading,
}: {
  items: CarteiraBreakdownItem[]
  pddTotal: string | number
  pddMedioPct: number
  loading: boolean
}) {
  return (
    <Card className={cardTokens.body}>
      <div className="flex h-full flex-col gap-3">
        <CardHeader
          eyebrow="PDD por faixa"
          kpiValue={brl(pddTotal)}
          kpiSub={`${pct(pddMedioPct, 2)} do nominal`}
        />
        <div className="-mx-1 -mb-1 mt-1 flex-1">
          <EChartsCard
            option={buildFaixaPddOption(items)}
            height={170}
            loading={loading}
            embedded
            caption="Faixas com PDD > 0 (Bacen 2682)"
          />
        </div>
      </div>
    </Card>
  )
}

// — Card 3: Por produto (tipo_recebivel) ─────────────────────────────────────

function PorProdutoCard({
  items,
  loading,
}: {
  items: CarteiraBreakdownItem[]
  loading: boolean
}) {
  const top = items[0]
  return (
    <Card className={cardTokens.body}>
      <div className="flex h-full flex-col gap-3">
        <CardHeader
          eyebrow="Distribuicao por produto"
          kpiValue={top?.label ?? "—"}
          kpiSub={top ? pct(top.pct_do_total, 1) : undefined}
        />
        <div className="flex flex-col gap-1.5 pt-1">
          {loading && items.length === 0 && <CardSkeleton lines={3} />}
          {!loading && items.length === 0 && (
            <p className="text-xs text-gray-400 dark:text-gray-600">
              Sem dados.
            </p>
          )}
          {items.map((item, idx) => (
            <ConcentracaoRow
              key={item.chave}
              rank={idx + 1}
              label={item.label}
              valorNominal={item.valor_nominal}
              pctOfTotal={item.pct_do_total}
              barRatio={
                (top?.pct_do_total ?? 0) > 0
                  ? item.pct_do_total / (top?.pct_do_total ?? 1)
                  : 0
              }
            />
          ))}
        </div>
      </div>
    </Card>
  )
}

// — Cards 4/5: Concentracao (Top cedentes / Top sacados) ─────────────────────

function ConcentracaoCard({
  title,
  items,
  top1Pct,
  top5Pct,
}: {
  title: string
  items: CarteiraBreakdownItem[]
  top1Pct: number
  top5Pct: number
}) {
  // Pega so os 5 maiores nomeados (ignora bucket "Outros") para a lista.
  const lista = items.filter((i) => i.chave !== "__outros__").slice(0, 5)
  const maxPct = lista[0]?.pct_do_total ?? 0
  return (
    <Card className={cardTokens.body}>
      <div className="flex h-full flex-col gap-3">
        <CardHeader
          eyebrow={title}
          kpiValue={pct(top5Pct, 1)}
          kpiSub={`Top 5 · Top 1: ${pct(top1Pct, 1)}`}
        />
        <div className="flex flex-col gap-1.5 pt-1">
          {lista.length === 0 && (
            <p className="text-xs text-gray-400 dark:text-gray-600">
              Sem dados.
            </p>
          )}
          {lista.map((item, idx) => (
            <ConcentracaoRow
              key={item.chave}
              rank={idx + 1}
              label={item.label}
              valorNominal={item.valor_nominal}
              pctOfTotal={item.pct_do_total}
              barRatio={maxPct > 0 ? item.pct_do_total / maxPct : 0}
            />
          ))}
        </div>
      </div>
    </Card>
  )
}

function ConcentracaoRow({
  rank,
  label,
  valorNominal,
  pctOfTotal,
  barRatio,
}: {
  rank: number
  label: string
  valorNominal: string | number
  pctOfTotal: number
  barRatio: number
}) {
  // Bar width via inline style — chart-like vizualization, sem token Tailwind
  // que cubra escala continua de 0-100%. Mesma excecao do `style={{}}` que
  // CLAUDE.md §5 permite em casos onde Tailwind nao alcanca.
  const widthPct = Math.max(2, Math.min(100, barRatio * 100))
  return (
    <div className="flex flex-col gap-0.5">
      <div className="flex items-baseline gap-2">
        {/* Nome — trunca em 1 linha, expande pra ocupar espaco. Valor e % nao
            quebram. Layout: [N. Nome trunca…] [R$ X mi] [Y.Y%] */}
        <span className="line-clamp-1 flex-1 text-xs text-gray-700 dark:text-gray-300">
          <span className="mr-1 text-gray-400 dark:text-gray-600">{rank}.</span>
          {label}
        </span>
        <span className="shrink-0 text-xs tabular-nums text-gray-600 dark:text-gray-400">
          {brlMi(valorNominal)}
        </span>
        <span className="shrink-0 text-xs font-medium tabular-nums text-gray-900 dark:text-gray-50">
          {pct(pctOfTotal, 1)}
        </span>
      </div>
      <div className="h-1 rounded-full bg-gray-100 dark:bg-gray-900">
        <div
          className="h-1 rounded-full bg-blue-500"
          style={{ width: `${widthPct}%` }}
        />
      </div>
    </div>
  )
}

// — Card 6: Composicao (Situacao + Coobrigacao) ──────────────────────────────

function ComposicaoCard({
  situacao,
  coobrigacao,
  pctVencido,
}: {
  situacao: CarteiraBreakdownItem[]
  coobrigacao: CarteiraBreakdownItem[]
  pctVencido: number
}) {
  return (
    <Card className={cardTokens.body}>
      <div className="flex h-full flex-col gap-3">
        <CardHeader
          eyebrow="Composicao da carteira"
          kpiValue={pct(pctVencido, 2)}
          kpiSub="vencido"
        />
        <div className="flex flex-col gap-3 pt-1">
          <CompositionSection title="Situacao" items={situacao} />
          <CompositionSection title="Coobrigacao" items={coobrigacao} />
        </div>
      </div>
    </Card>
  )
}

function CompositionSection({
  title,
  items,
}: {
  title: string
  items: CarteiraBreakdownItem[]
}) {
  if (items.length === 0) {
    return (
      <div className="flex flex-col gap-1">
        <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
          {title}
        </p>
        <p className="text-xs text-gray-400 dark:text-gray-600">Sem dados.</p>
      </div>
    )
  }
  return (
    <div className="flex flex-col gap-1">
      <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
        {title}
      </p>
      <div className="flex h-2 overflow-hidden rounded-full bg-gray-100 dark:bg-gray-900">
        {items.map((item, idx) => {
          const widthPct = Math.max(0, Math.min(100, item.pct_do_total))
          if (widthPct === 0) return null
          // Cor sequencial a partir da paleta de chart tokens — primeira eh
          // azul (blue-500 do produto), demais variam.
          const color = COMPOSITION_COLORS[idx % COMPOSITION_COLORS.length]
          return (
            <div
              key={item.chave}
              className={color}
              style={{ width: `${widthPct}%` }}
              title={`${item.label}: ${pct(item.pct_do_total, 1)}`}
            />
          )
        })}
      </div>
      <div className="flex flex-wrap gap-x-3 gap-y-0.5">
        {items.map((item, idx) => {
          const color = COMPOSITION_COLORS[idx % COMPOSITION_COLORS.length]
          return (
            <div key={item.chave} className="flex items-center gap-1">
              <span className={cx("size-2 shrink-0 rounded-sm", color)} />
              <span className="text-[11px] text-gray-600 dark:text-gray-400">
                {item.label} · {pct(item.pct_do_total, 1)}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// Paleta canonica do Tremor pra stacked bars de composicao. Mantemos no
// vocabulario do produto (blue de selecao + gray de cauda).
const COMPOSITION_COLORS = [
  "bg-blue-500",
  "bg-blue-400",
  "bg-gray-400",
  "bg-gray-300",
  "bg-gray-200",
]

function CardSkeleton({ lines }: { lines: number }) {
  return (
    <div className="flex flex-col gap-2 pt-2">
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="h-4 animate-pulse rounded bg-gray-100 dark:bg-gray-900"
        />
      ))}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Drill-down content
// ─────────────────────────────────────────────────────────────────────────────

function RecebivelDrill({ row }: { row: EstoqueRecebivelRow }) {
  const valorPresenteN = Number(row.valor_presente)
  return (
    <>
      <DrillDownSheet.Header
        breadcrumb={["Carteira", row.numero_documento]}
      />
      <DrillDownSheet.Hero
        id={row.numero_documento || row.seu_numero}
        title={`${row.cedente_nome} → ${row.sacado_nome}`}
        value={Number.isNaN(valorPresenteN) ? undefined : valorPresenteN}
      />
      <DrillDownSheet.Body>
        <DrillDownSheet.SectionLabel>Cessao</DrillDownSheet.SectionLabel>
        <DrillDownSheet.PropertyList
          items={[
            { label: "Cedente", value: row.cedente_nome },
            { label: "CNPJ cedente", value: row.cedente_doc },
            { label: "Originador", value: row.originador_nome },
            { label: "Tipo", value: row.tipo_recebivel },
            { label: "Coobrigacao", value: row.coobrigacao ? "Sim" : "Nao" },
            { label: "Data aquisicao", value: formatDateBR(row.data_aquisicao) },
            {
              label: "Taxa cessao",
              value: `${(Number(row.taxa_cessao) * 100).toFixed(4)}%`,
            },
          ]}
        />
        <DrillDownSheet.SectionLabel>Sacado</DrillDownSheet.SectionLabel>
        <DrillDownSheet.PropertyList
          items={[
            { label: "Sacado", value: row.sacado_nome },
            { label: "CNPJ sacado", value: row.sacado_doc },
          ]}
        />
        <DrillDownSheet.SectionLabel>Vencimento</DrillDownSheet.SectionLabel>
        <DrillDownSheet.PropertyList
          items={[
            {
              label: "Vencimento original",
              value: formatDateBR(row.data_vencimento_original),
            },
            {
              label: "Vencimento ajustado",
              value: formatDateBR(row.data_vencimento_ajustada),
            },
            { label: "Prazo (dias)", value: String(row.prazo) },
          ]}
        />
        <DrillDownSheet.SectionLabel>Valores</DrillDownSheet.SectionLabel>
        <DrillDownSheet.PropertyList
          items={[
            { label: "Valor presente", value: brl(row.valor_presente) },
            { label: "Valor nominal", value: brl(row.valor_nominal) },
            { label: "Valor aquisicao", value: brl(row.valor_aquisicao) },
            { label: "PDD", value: brl(row.valor_pdd) },
            {
              label: "Taxa recebivel",
              value: `${(Number(row.taxa_recebivel) * 100).toFixed(4)}%`,
            },
            { label: "Faixa PDD", value: row.faixa_pdd },
            { label: "Situacao", value: row.situacao_recebivel },
          ]}
        />
      </DrillDownSheet.Body>
    </>
  )
}
