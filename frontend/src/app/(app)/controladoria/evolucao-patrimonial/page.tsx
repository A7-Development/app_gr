// src/app/(app)/controladoria/evolucao-patrimonial/page.tsx
//
// Controladoria · Evolucao Patrimonial — serie temporal do PL do passivo do
// FIDC (todas as classes de cota: Senior / Mezanino / Subordinada).
//
// Pagina derivada do pattern `DashboardBiPadrao`, reusando o shell canonico do
// cota-sub (toolbar 52px com TabNavigation-less + FilterChips, scroll-shadow,
// ProvenanceFooter, AIPanel, header DashboardHeaderActions).
//
// Fonte: GET /controladoria/evolucao-patrimonial/serie (silver wh_mec +
// wh_rentabilidade). Filtros globais (Fundo · Periodo · Granularidade ·
// Classes) aplicam a 100% dos agregados (CLAUDE.md §7.2). A "lente de
// variacao" do card de Variacao e LOCAL (client-side sobre dados ja filtrados).

"use client"

import * as React from "react"
import {
  RiCalendarLine,
  RiCheckLine,
  RiFundsLine,
  RiStackLine,
} from "@remixicon/react"
import type { EChartsOption } from "echarts"
import { format, subMonths } from "date-fns"

import { cx } from "@/lib/utils"
import { Button } from "@/components/tremor/Button"

import { PageHeader } from "@/design-system/components/PageHeader"
import { DashboardHeaderActions } from "@/design-system/components/DashboardHeaderActions"
import { FilterChip } from "@/design-system/components/FilterBar"
import { EChartsCard } from "@/design-system/components/EChartsCard"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { Insight, InsightBar } from "@/design-system/components/Insight"
import { KpiCard, KpiStrip } from "@/design-system/components/KpiStrip"
import { SegmentSwitch } from "@/design-system/components/SegmentSwitch"
import {
  CompactSeriesTable,
  type CompactSeriesRow,
} from "@/design-system/components/CompactSeriesTable"
import { ProvenanceFooter } from "@/design-system/components/ProvenanceFooter"
import { AIPanel, useAIPanel } from "@/design-system/components/AIPanel"

import { useUAs } from "@/lib/hooks/cadastros"
import { useEvolucaoPatrimonial } from "@/lib/hooks/controladoria"
import type {
  EvolucaoClasse,
  EvolucaoGranularidade,
  EvolucaoPatrimonialResponse,
  EvolucaoSeriePonto,
} from "@/lib/api-client"
import { useScrollShadow } from "@/lib/hooks/use-scroll-shadow"

// ───────────────────────────────────────────────────────────────────────────
// Constantes
// ───────────────────────────────────────────────────────────────────────────

// Cor por classe (hex inline permitido em EChartsOption — §4 excecao canvas).
// Sub = slate (base/residual), Mez = sky, Sr = teal — paleta A7 de chart.
const CLASSE_COLOR: Record<EvolucaoClasse, string> = {
  sub: "#64748B",
  mez: "#0EA5E9",
  sr: "#14B8A6",
}
const CDI_COLOR = "#9CA3AF"
// Ordem de empilhamento: Sr na base, Sub no topo (residual mais visivel).
const CLASSE_STACK_ORDER: EvolucaoClasse[] = ["sr", "mez", "sub"]

type Preset = "3M" | "6M" | "12M" | "24M" | "Tudo"
const PRESETS: Preset[] = ["3M", "6M", "12M", "24M", "Tudo"]
const PRESET_MESES: Record<Exclude<Preset, "Tudo">, number> = {
  "3M": 3,
  "6M": 6,
  "12M": 12,
  "24M": 24,
}

type VarLente = "diaria" | "mensal" | "acumulada"

// ───────────────────────────────────────────────────────────────────────────
// Formatadores
// ───────────────────────────────────────────────────────────────────────────

function brl(v: number): string {
  return `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}
function brlCompact(v: number): string {
  const a = Math.abs(v)
  if (a >= 1e6)
    return `R$ ${(v / 1e6).toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })} mi`
  if (a >= 1e3)
    return `R$ ${(v / 1e3).toLocaleString("pt-BR", { maximumFractionDigits: 0 })} mil`
  return brl(v)
}
function pct(v: number | null | undefined, dec = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—"
  return `${v.toLocaleString("pt-BR", { minimumFractionDigits: dec, maximumFractionDigits: dec })}%`
}

function presetToInicio(preset: Preset): string {
  if (preset === "Tudo") return "2015-01-01"
  return format(subMonths(new Date(), PRESET_MESES[preset]), "yyyy-MM-dd")
}

function xLabel(iso: string, gran: EvolucaoGranularidade): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!m) return iso
  const [, yyyy, mm, dd] = m
  const MES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
  if (gran === "mensal") return `${MES[Number(mm) - 1]}/${yyyy.slice(2)}`
  return `${dd}/${mm}`
}

// Pivota a serie numa array por ponto pra uma classe + campo.
// `fillZero` usa 0 quando a classe nao existe no ponto (stack); senao null (gap).
function pivot(
  serie: EvolucaoSeriePonto[],
  classe: EvolucaoClasse,
  field: "patrimonio" | "valor_cota" | "captacao_liquida" | "variacao_diaria_pct" | "variacao_mensal_pct",
  fillZero: boolean,
): (number | null)[] {
  return serie.map((p) => {
    const c = p.classes.find((x) => x.classe === classe)
    if (!c) return fillZero ? 0 : null
    return c[field]
  })
}

// Indexa uma serie de cotas a base 100 (primeiro valor nao-nulo = 100).
function indexar100(valores: (number | null)[]): (number | null)[] {
  const base = valores.find((v) => v !== null && v !== 0) ?? null
  if (base === null) return valores.map(() => null)
  return valores.map((v) => (v === null ? null : (v / base) * 100))
}

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

export default function EvolucaoPatrimonialPage() {
  const fundosQuery = useUAs({ tipo: "fidc", ativa: true })
  const fundoOptions = React.useMemo(
    () => ["Todos", ...(fundosQuery.data?.map((ua) => ua.nome) ?? [])],
    [fundosQuery.data],
  )
  const [fundo, setFundo] = React.useState<string>("Todos")
  const fundoId = React.useMemo(() => {
    if (fundo === "Todos") return null
    return fundosQuery.data?.find((ua) => ua.nome === fundo)?.id ?? null
  }, [fundo, fundosQuery.data])
  const fundoSelecionado = fundoId !== null

  const [preset, setPreset] = React.useState<Preset>("12M")
  const [granularidade, setGranularidade] = React.useState<EvolucaoGranularidade>("mensal")
  // Filtro de classe: vazio = todas. Subset = manda no query.
  const [classesSel, setClassesSel] = React.useState<EvolucaoClasse[]>([])
  // Lente local do card de Variacao (client-side sobre dados ja filtrados).
  const [varLente, setVarLente] = React.useState<VarLente>("mensal")

  const periodoInicio = React.useMemo(() => presetToInicio(preset), [preset])
  const classesParam = classesSel.length > 0 ? classesSel : undefined

  const ai = useAIPanel()
  const [scrollRef, scrolled] = useScrollShadow<HTMLDivElement>()

  // Charts + KPIs na granularidade escolhida.
  const serieQuery = useEvolucaoPatrimonial(fundoId, {
    periodoInicio,
    granularidade,
    classes: classesParam,
  })
  // Tabela mes-a-mes sempre mensal (CompactSeriesTable e serie temporal FIDC).
  // React Query dedupa quando granularidade ja e "mensal".
  const mensalQuery = useEvolucaoPatrimonial(fundoId, {
    periodoInicio,
    granularidade: "mensal",
    classes: classesParam,
  })

  const data = serieQuery.data
  const classesDisp = data?.classes_disponiveis ?? []

  const handleShare = React.useCallback(() => {
    void navigator.clipboard?.writeText(window.location.href)
  }, [])

  const aiContext = React.useMemo(
    () => ({
      page: "Controladoria · Evolucao Patrimonial",
      period: `${preset} · ${granularidade === "mensal" ? "mensal" : "diaria"}`,
      filters: [
        fundo !== "Todos" && `Fundo: ${fundo}`,
        classesSel.length > 0 && `Classes: ${classesSel.join(", ")}`,
      ]
        .filter(Boolean)
        .join(", ") || "Nenhum",
    }),
    [preset, granularidade, fundo, classesSel],
  )

  const toggleClasse = React.useCallback((c: EvolucaoClasse) => {
    setClassesSel((curr) =>
      curr.includes(c) ? curr.filter((x) => x !== c) : [...curr, c],
    )
  }, [])

  return (
    <div className="flex h-[calc(100vh-3rem)] overflow-hidden">
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Title row */}
        <div className="shrink-0 bg-white px-6 pt-3.5 pb-3 dark:bg-gray-950">
          <PageHeader
            title="Evolucao Patrimonial"
            info="Evolucao do PL do passivo do FIDC (Senior / Mezanino / Subordinada) ao longo do tempo. Escolha o fundo, periodo, granularidade e classes na barra de filtros. Fonte: QiTech MEC + rentabilidade (silver)."
            subtitle="Controladoria · Patrimonio e Cotas"
            actions={
              <DashboardHeaderActions
                ai={{ open: ai.open, onToggle: ai.toggle }}
                onShare={handleShare}
              />
            }
          />
        </div>

        {/* Toolbar (52px) — filtros globais */}
        <div
          className={cx(
            "shrink-0 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
            scrolled && "scroll-shadow",
          )}
        >
          <div className="flex h-[52px] items-center gap-2 px-6">
            {/* Fundo */}
            <FilterChip label="Fundo" value={fundo} active={fundo !== "Todos"} icon={RiFundsLine}>
              <div className="py-1">
                {fundosQuery.isLoading && (
                  <div className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400">Carregando UAs...</div>
                )}
                {fundoOptions.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setFundo(opt)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      fundo === opt
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{opt}</span>
                    {fundo === opt && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                  </button>
                ))}
              </div>
            </FilterChip>

            {/* Periodo */}
            <FilterChip label="Periodo" value={preset} active={preset !== "12M"} icon={RiCalendarLine}>
              <div className="py-1">
                {PRESETS.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => setPreset(p)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      preset === p
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{p === "12M" ? "12M corridos" : p === "Tudo" ? "Tudo" : `Ultimos ${p}`}</span>
                    {preset === p && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                  </button>
                ))}
              </div>
            </FilterChip>

            {/* Classes (multiselect) */}
            <FilterChip
              label="Classes"
              value={classesSel.length === 0 ? "Todas" : classesSel.map((c) => c.toUpperCase()).join("+")}
              active={classesSel.length > 0}
              icon={RiStackLine}
            >
              <div className="py-1">
                {classesDisp.length === 0 && (
                  <div className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400">
                    {fundoSelecionado ? "Carregando classes..." : "Selecione um fundo"}
                  </div>
                )}
                {classesDisp.map((ci) => {
                  return (
                    <button
                      key={ci.classe}
                      type="button"
                      onClick={() => toggleClasse(ci.classe)}
                      className={cx(
                        "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                        "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
                      )}
                    >
                      <span
                        aria-hidden="true"
                        className="size-2.5 shrink-0 rounded-[2px]"
                        style={{ backgroundColor: CLASSE_COLOR[ci.classe] }}
                      />
                      <span className="flex-1 text-left">{ci.label}</span>
                      {classesSel.includes(ci.classe) && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                    </button>
                  )
                })}
                {classesSel.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setClassesSel([])}
                    className="mt-1 flex w-full items-center rounded px-3 py-1.5 text-sm text-blue-600 transition-colors hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-500/10"
                  >
                    Mostrar todas
                  </button>
                )}
              </div>
            </FilterChip>

            <div aria-hidden="true" className="mx-1 h-5 w-px bg-gray-200 dark:bg-gray-800" />

            {/* Granularidade */}
            <SegmentSwitch<EvolucaoGranularidade>
              options={[
                { value: "mensal", label: "Mensal" },
                { value: "diaria", label: "Diaria" },
              ]}
              value={granularidade}
              onChange={setGranularidade}
            />

            <div className="ml-auto flex items-center gap-2">
              <span className="shrink-0 text-[11px] text-gray-500 dark:text-gray-400">
                {serieQuery.isFetching ? "Atualizando…" : "Atualizado"}
              </span>
            </div>
          </div>
        </div>

        {/* Conteudo */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4">
          {!fundoSelecionado ? (
            <EmptyState
              icon={RiFundsLine}
              title="Selecione um fundo para comecar"
              description='A Evolucao Patrimonial analisa um FIDC por vez. Escolha o fundo no filtro "Fundo" acima para carregar a serie do PL do passivo por classe.'
              className="mt-4"
            />
          ) : serieQuery.isError ? (
            <ErrorState
              title="Falha ao carregar a serie"
              description={(serieQuery.error as Error)?.message ?? "Erro desconhecido."}
              action={
                <Button variant="secondary" onClick={() => serieQuery.refetch()}>
                  Tentar novamente
                </Button>
              }
              className="mt-4"
            />
          ) : data && data.serie.length === 0 ? (
            <EmptyState
              icon={RiFundsLine}
              title="Sem dados no periodo"
              description="Nao ha snapshots MEC para o fundo no periodo selecionado. Ajuste o periodo ou verifique a sincronizacao QiTech."
              className="mt-4"
            />
          ) : (
            <EvolucaoContent
              data={data}
              loading={serieQuery.isLoading}
              granularidade={granularidade}
              mensalData={mensalQuery.data}
              varLente={varLente}
              setVarLente={setVarLente}
            />
          )}
        </div>

        {data?.proveniencia && (
          <ProvenanceFooter
            sources={[
              {
                label: "QiTech · MEC + Rentabilidade",
                updated: data.proveniencia.atualizado_em ?? new Date().toISOString(),
                sla: "Diario (dia util)",
                stale: data.proveniencia.gaps_ignorados > 0,
              },
            ]}
          />
        )}
      </div>

      <AIPanel open={ai.open} onClose={() => ai.setOpen(false)} context={aiContext} insights={buildInsights(data)} />
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Conteudo (KPIs + charts + tabela) — separado pra so renderizar com dados.
// ───────────────────────────────────────────────────────────────────────────

function EvolucaoContent({
  data,
  loading,
  granularidade,
  mensalData,
  varLente,
  setVarLente,
}: {
  data: EvolucaoPatrimonialResponse | undefined
  loading: boolean
  granularidade: EvolucaoGranularidade
  mensalData: EvolucaoPatrimonialResponse | undefined
  varLente: VarLente
  setVarLente: (v: VarLente) => void
}) {
  const serie = React.useMemo(() => data?.serie ?? [], [data])
  const kpis = data?.kpis
  const xLabels = React.useMemo(
    () => serie.map((p) => xLabel(p.data, granularidade)),
    [serie, granularidade],
  )
  // Classes presentes na serie (respeita o filtro de classe da toolbar). Os
  // charts iteram estas — quando o usuario filtra, as demais somem da legenda.
  // (O multiselect da toolbar usa `classes_disponiveis` cru, sempre completo.)
  const classesDisp = React.useMemo(
    () =>
      (data?.classes_disponiveis ?? []).filter((ci) =>
        serie.some((p) => p.classes.some((x) => x.classe === ci.classe)),
      ),
    [data, serie],
  )

  // ── Evolucao do PL (stacked area) ──
  const plOption = React.useMemo<EChartsOption>(() => {
    const ativas = CLASSE_STACK_ORDER.filter((c) => classesDisp.some((ci) => ci.classe === c))
    return {
      grid: { top: 16, right: 16, bottom: 48, left: 60 },
      xAxis: { type: "category", data: xLabels, axisTick: { show: false } },
      yAxis: {
        type: "value",
        axisLabel: { formatter: (v: number) => `R$ ${(v / 1e6).toFixed(0)}M` },
      },
      series: ativas.map((c) => ({
        name: classesDisp.find((ci) => ci.classe === c)?.label ?? c,
        type: "line",
        stack: "pl",
        smooth: true,
        symbol: "none",
        areaStyle: { opacity: 0.65 },
        lineStyle: { width: 1, color: CLASSE_COLOR[c] },
        itemStyle: { color: CLASSE_COLOR[c] },
        data: pivot(serie, c, "patrimonio", true),
      })),
      legend: { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v) => (typeof v === "number" ? brlCompact(v) : String(v)),
      },
    }
  }, [serie, xLabels, classesDisp])

  // ── Composicao do passivo (100% stacked area) ──
  const compOption = React.useMemo<EChartsOption>(() => {
    const ativas = CLASSE_STACK_ORDER.filter((c) => classesDisp.some((ci) => ci.classe === c))
    return {
      grid: { top: 16, right: 12, bottom: 48, left: 40 },
      xAxis: { type: "category", data: xLabels, axisTick: { show: false } },
      yAxis: { type: "value", max: 100, axisLabel: { formatter: "{value}%" } },
      series: ativas.map((c) => {
        const pat = pivot(serie, c, "patrimonio", true) as number[]
        const share = pat.map((v, i) => (serie[i].pl_total ? (v / serie[i].pl_total) * 100 : 0))
        return {
          name: classesDisp.find((ci) => ci.classe === c)?.label ?? c,
          type: "line",
          stack: "comp",
          smooth: true,
          symbol: "none",
          areaStyle: { opacity: 0.7 },
          lineStyle: { width: 0, color: CLASSE_COLOR[c] },
          itemStyle: { color: CLASSE_COLOR[c] },
          data: share,
        }
      }),
      legend: { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v) => (typeof v === "number" ? `${v.toFixed(1)}%` : String(v)),
      },
    }
  }, [serie, xLabels, classesDisp])

  // ── Valor da cota indexado a 100 ──
  const cotaOption = React.useMemo<EChartsOption>(() => {
    return {
      grid: { top: 16, right: 12, bottom: 48, left: 48 },
      xAxis: { type: "category", data: xLabels, axisTick: { show: false } },
      yAxis: { type: "value", axisLabel: { formatter: "{value}" }, scale: true },
      series: classesDisp.map((ci) => ({
        name: ci.label,
        type: "line",
        smooth: true,
        symbol: "none",
        lineStyle: { width: 2, color: CLASSE_COLOR[ci.classe] },
        itemStyle: { color: CLASSE_COLOR[ci.classe] },
        data: indexar100(pivot(serie, ci.classe, "valor_cota", false)),
      })),
      legend: { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v) => (typeof v === "number" ? v.toFixed(1) : String(v)),
      },
    }
  }, [serie, xLabels, classesDisp])

  // ── Rentabilidade vs CDI (Sub indexada vs CDI acumulado) ──
  const cdiOption = React.useMemo<EChartsOption>(() => {
    const subCota = indexar100(pivot(serie, "sub", "valor_cota", false))
    // CDI acumulado: parte de 100, compoe cdi_retorno_pct ponto a ponto.
    let fator = 100
    const cdiAcc = serie.map((p) => {
      if (p.cdi_retorno_pct !== null && p.cdi_retorno_pct !== undefined) {
        fator *= 1 + p.cdi_retorno_pct / 100
      }
      return fator
    })
    return {
      grid: { top: 16, right: 12, bottom: 48, left: 48 },
      xAxis: { type: "category", data: xLabels, axisTick: { show: false } },
      yAxis: { type: "value", scale: true, axisLabel: { formatter: "{value}" } },
      series: [
        {
          name: "Cota Sub",
          type: "line",
          smooth: true,
          symbol: "none",
          lineStyle: { width: 2, color: CLASSE_COLOR.sub },
          itemStyle: { color: CLASSE_COLOR.sub },
          data: subCota,
        },
        {
          name: "CDI",
          type: "line",
          smooth: true,
          symbol: "none",
          lineStyle: { width: 1.5, color: CDI_COLOR, type: "dashed" },
          itemStyle: { color: CDI_COLOR },
          data: cdiAcc,
        },
      ],
      legend: { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
      tooltip: {
        trigger: "axis",
        valueFormatter: (v) => (typeof v === "number" ? v.toFixed(1) : String(v)),
      },
    }
  }, [serie, xLabels])

  // ── Variacao (lente diaria / mensal / acumulada) ──
  const varOption = React.useMemo<EChartsOption>(() => {
    if (varLente === "acumulada") {
      return {
        grid: { top: 16, right: 12, bottom: 48, left: 48 },
        xAxis: { type: "category", data: xLabels, axisTick: { show: false } },
        yAxis: { type: "value", axisLabel: { formatter: "{value}%" } },
        series: classesDisp.map((ci) => {
          const idx = indexar100(pivot(serie, ci.classe, "valor_cota", false))
          return {
            name: ci.label,
            type: "line",
            smooth: true,
            symbol: "none",
            lineStyle: { width: 2, color: CLASSE_COLOR[ci.classe] },
            itemStyle: { color: CLASSE_COLOR[ci.classe] },
            data: idx.map((v) => (v === null ? null : v - 100)),
          }
        }),
        legend: { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
        tooltip: { trigger: "axis", valueFormatter: (v) => (typeof v === "number" ? `${v.toFixed(2)}%` : String(v)) },
      }
    }
    const field = varLente === "diaria" ? "variacao_diaria_pct" : "variacao_mensal_pct"
    return {
      grid: { top: 16, right: 12, bottom: 48, left: 48 },
      xAxis: { type: "category", data: xLabels, axisTick: { show: false } },
      yAxis: { type: "value", axisLabel: { formatter: "{value}%" } },
      series: classesDisp.map((ci) => ({
        name: ci.label,
        type: "bar",
        itemStyle: { color: CLASSE_COLOR[ci.classe] },
        data: pivot(serie, ci.classe, field, false),
      })),
      legend: { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => (typeof v === "number" ? `${v.toFixed(2)}%` : String(v)) },
    }
  }, [serie, xLabels, classesDisp, varLente])

  // ── Captacao liquida (bars stacked por classe) ──
  const captOption = React.useMemo<EChartsOption>(() => {
    return {
      grid: { top: 16, right: 12, bottom: 48, left: 56 },
      xAxis: { type: "category", data: xLabels, axisTick: { show: false } },
      yAxis: { type: "value", axisLabel: { formatter: (v: number) => `${(v / 1e6).toFixed(1)}M` } },
      series: classesDisp.map((ci) => ({
        name: ci.label,
        type: "bar",
        stack: "capt",
        itemStyle: { color: CLASSE_COLOR[ci.classe] },
        data: pivot(serie, ci.classe, "captacao_liquida", true),
      })),
      legend: { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: (v) => (typeof v === "number" ? brlCompact(v) : String(v)) },
    }
  }, [serie, xLabels, classesDisp])

  // ── Tabela mes-a-mes ──
  const tabela = React.useMemo(() => buildTabela(mensalData), [mensalData])

  return (
    <div className="flex flex-col gap-3">
      <InsightBar>
        {buildInsightTexts(data).map((t, i) => (
          <Insight key={i} tone={t.tone} text={t.text} />
        ))}
      </InsightBar>

      {/* KPIs */}
      <KpiStrip cols={5}>
        <KpiCard
          label="PL total"
          value={kpis ? brlCompact(kpis.pl_total_atual) : "—"}
          delta={
            kpis?.pl_total_delta_pct != null
              ? { value: Number(kpis.pl_total_delta_pct.toFixed(1)), suffix: "%", good: kpis.pl_total_delta_pct >= 0 }
              : undefined
          }
          deltaSub="no periodo"
        />
        <KpiCard
          label="Subordinacao"
          value={pct(kpis?.subordinacao_pct, 1)}
          sub="PL Sub / PL total"
        />
        <KpiCard
          label="Rentab. Sub"
          value={pct(kpis?.rentab_sub_periodo_pct, 1)}
          sub="no periodo"
        />
        <KpiCard
          label="% do CDI (Sub)"
          value={pct(kpis?.pct_cdi_sub_ultimo, 0)}
          sub="ultimo ponto"
        />
        <KpiCard
          label="Captacao liquida"
          value={kpis ? brlCompact(kpis.captacao_liquida_periodo) : "—"}
          deltaSub="no periodo"
        />
      </KpiStrip>

      {/* Hero: Evolucao do PL (2/3) + Composicao (1/3) */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <EChartsCard
            title="Evolucao do PL"
            caption="Patrimonio liquido por classe (empilhado)"
            option={plOption}
            height={320}
            loading={loading}
            headerKpi={
              kpis
                ? {
                    value: brlCompact(kpis.pl_total_atual),
                    delta:
                      kpis.pl_total_delta_pct != null
                        ? { value: Number(kpis.pl_total_delta_pct.toFixed(1)), suffix: "%", good: kpis.pl_total_delta_pct >= 0 }
                        : undefined,
                    deltaSub: "no periodo",
                  }
                : undefined
            }
          />
        </div>
        <EChartsCard
          title="Composicao do passivo"
          caption="Participacao % por classe"
          option={compOption}
          height={320}
          loading={loading}
        />
      </div>

      {/* Cota indexada + Rentab vs CDI */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <EChartsCard
          title="Valor da cota (base 100)"
          caption="Performance relativa entre classes"
          option={cotaOption}
          height={260}
          loading={loading}
        />
        <EChartsCard
          title="Rentabilidade vs CDI"
          caption="Cota Sub vs CDI acumulado (base 100)"
          option={cdiOption}
          height={260}
          loading={loading}
        />
      </div>

      {/* Variacao (lente) + Captacao */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <div className="flex flex-col gap-2">
          <div className="flex items-center justify-end">
            <SegmentSwitch<VarLente>
              options={[
                { value: "diaria", label: "Diaria" },
                { value: "mensal", label: "Mensal" },
                { value: "acumulada", label: "Acumulada" },
              ]}
              value={varLente}
              onChange={setVarLente}
            />
          </div>
          <EChartsCard
            title="Variacao da cota"
            caption={
              varLente === "acumulada"
                ? "Retorno acumulado no periodo (%)"
                : varLente === "diaria"
                  ? "Variacao diaria (%)"
                  : "Variacao mensal (%)"
            }
            option={varOption}
            height={260}
            loading={loading}
          />
        </div>
        <EChartsCard
          title="Captacao liquida"
          caption="Entradas - saidas por classe (R$)"
          option={captOption}
          height={260}
          loading={loading}
        />
      </div>

      {/* Tabela mes-a-mes */}
      {tabela && (
        <CompactSeriesTable
          label="Serie mes-a-mes por classe"
          periods={tabela.periods}
          rows={tabela.rows}
          periodFormat="mmm/aa"
          footnote="PL, valor da cota, rentabilidade mensal e captacao liquida por classe. Fonte: QiTech MEC."
        />
      )}
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Helpers de conteudo
// ───────────────────────────────────────────────────────────────────────────

function buildInsightTexts(
  data: EvolucaoPatrimonialResponse | undefined,
): { text: string; tone: "violet" | "amber" | "blue" }[] {
  if (!data?.kpis) return []
  const k = data.kpis
  const out: { text: string; tone: "violet" | "amber" | "blue" }[] = []
  if (k.pl_total_delta_pct != null) {
    out.push({
      tone: "violet",
      text: `PL total em ${brlCompact(k.pl_total_atual)} (${k.pl_total_delta_pct >= 0 ? "+" : ""}${k.pl_total_delta_pct.toFixed(1)}% no periodo), com captacao liquida de ${brlCompact(k.captacao_liquida_periodo)}.`,
    })
  }
  if (k.subordinacao_pct != null) {
    out.push({
      tone: "blue",
      text: `Subordinacao em ${pct(k.subordinacao_pct, 1)} (PL Sub sobre PL total) — colchao que absorve as perdas das classes Senior/Mezanino.`,
    })
  }
  if (k.rentab_sub_periodo_pct != null && k.pct_cdi_sub_ultimo != null) {
    out.push({
      tone: "violet",
      text: `Cota Sub rendeu ${pct(k.rentab_sub_periodo_pct, 1)} no periodo, equivalente a ${pct(k.pct_cdi_sub_ultimo, 0)} do CDI.`,
    })
  }
  if (data.proveniencia.gaps_ignorados > 0) {
    out.push({
      tone: "amber",
      text: `${data.proveniencia.gaps_ignorados} snapshot(s) MEC incompleto(s) (classe zerada na publicacao QiTech) foram ignorados na serie.`,
    })
  }
  return out
}

// Insights pro AIPanel (so texto).
function buildInsights(data: EvolucaoPatrimonialResponse | undefined) {
  return buildInsightTexts(data).map((t) => ({ text: t.text }))
}

// Monta a tabela mes-a-mes (CompactSeriesTable) a partir da serie mensal.
function buildTabela(
  data: EvolucaoPatrimonialResponse | undefined,
): { periods: string[]; rows: CompactSeriesRow[] } | null {
  if (!data || data.serie.length === 0) return null
  const periods = data.serie.map((p) => p.data)
  const rows: CompactSeriesRow[] = []

  // PL total (linha de destaque).
  rows.push({
    label: "PL total",
    format: "brlK",
    emphasis: "total",
    values: Object.fromEntries(data.serie.map((p) => [p.data, p.pl_total])),
  })

  for (const ci of data.classes_disponiveis) {
    rows.push({ separator: true })
    rows.push({
      label: `${ci.label} · PL`,
      format: "brlK",
      values: Object.fromEntries(
        data.serie.map((p) => [p.data, p.classes.find((c) => c.classe === ci.classe)?.patrimonio ?? null]),
      ),
    })
    rows.push({
      label: `${ci.label} · Cota`,
      format: "cota",
      indent: 1,
      values: Object.fromEntries(
        data.serie.map((p) => [p.data, p.classes.find((c) => c.classe === ci.classe)?.valor_cota ?? null]),
      ),
    })
    rows.push({
      label: `${ci.label} · Var. mensal`,
      format: "pct",
      indent: 1,
      values: Object.fromEntries(
        data.serie.map((p) => [p.data, p.classes.find((c) => c.classe === ci.classe)?.variacao_mensal_pct ?? null]),
      ),
    })
    rows.push({
      label: `${ci.label} · Captacao liq.`,
      format: "brlK",
      indent: 1,
      values: Object.fromEntries(
        data.serie.map((p) => [p.data, p.classes.find((c) => c.classe === ci.classe)?.captacao_liquida ?? null]),
      ),
    })
  }

  return { periods, rows }
}
