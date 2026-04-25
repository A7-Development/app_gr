"use client"

import { useSearchParams, usePathname } from "next/navigation"
import { useQuery } from "@tanstack/react-query"
import Link from "next/link"
import * as React from "react"

import { RiLinkM } from "@remixicon/react"

import { PageHeader } from "@/design-system/components/PageHeader"
import { Button } from "@/components/tremor/Button"
import {
  TabNavigation,
  TabNavigationLink,
} from "@/components/tremor/TabNavigation"
import { AreaChart } from "@/components/charts/AreaChart"
import { BarChart } from "@/components/charts/BarChart"
import { BarList } from "@/components/charts/BarList"
import { DonutChart } from "@/components/charts/DonutChart"

import { biOperacoes, type BIFilters, type BIResponse } from "@/lib/api-client"
import { useBiFilters } from "@/lib/hooks/useBiFilters"
import { BiFiltersBar } from "@/components/bi/BiFiltersBar"
import { ProvenanceFooter } from "@/components/bi/ProvenanceFooter"
// L3 Volume — reformulacao com layout storytelling (KPIs inline + chart
// principal + painel lateral de indicadores).
import { VolumeKpisInline } from "@/components/bi/VolumeKpisInline"
import { VolumeEvolucaoChart } from "@/components/bi/VolumeEvolucaoChart"
import { VolumeIndicadoresPanel } from "@/components/bi/VolumeIndicadoresPanel"

const moedaCompacta = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 2,
})
const moeda = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
})
const percent1 = (v: number) => `${v.toFixed(1)}%`
const diasFmt = (v: number) => `${v.toFixed(1)} d`

const TABS = [
  { key: "volume", label: "Volume" },
  { key: "taxa", label: "Taxa" },
  { key: "prazo", label: "Prazo" },
  { key: "ticket", label: "Ticket" },
  { key: "receita", label: "Receita contratada" },
  { key: "dia-util", label: "Dia util" },
] as const

type TabKey = (typeof TABS)[number]["key"]

function useActiveTab(): TabKey {
  const sp = useSearchParams()
  const t = sp.get("tab")
  if (t && TABS.some((x) => x.key === t)) return t as TabKey
  return "volume"
}

function labelForPeriodo(iso: string): string {
  const [y, m, d] = iso.split("-").map(Number)
  // Para serie mensal o backend retorna 'YYYY-MM-01' — exibe 'mmm/yy'.
  if (d === 1) {
    return new Date(y, m - 1, 1).toLocaleString("pt-BR", {
      month: "short",
      year: "2-digit",
    })
  }
  return `${String(d).padStart(2, "0")}/${String(m).padStart(2, "0")}`
}

//
// Pagina BI · Operacoes — convergencia visual ao Tremor Template Planner.
//
// Diagramacao (Tremor-style, ver quotes/layout.tsx do template oficial):
//  - Conteudo FLUI direto sobre o fundo da pagina (sem Card/border/shadow
//    envolvendo). O body/header ja fornece bg-white — nao precisamos de
//    uma moldura adicional.
//  - Titulo em text-lg, descricao via InfoTooltip (sem border-b).
//  - 3 KPIs hero (volume bruto, ticket medio, receita contratada) em inline
//    dl + 3 KPIs secundarios (taxa, prazo, total operacoes) em linha menor.
//  - BiFiltersBar inline dentro de cada TabContent, acima dos charts.
//  - ProvenanceFooter ao fim (requisito compliance CLAUDE.md 14.6).
//

const PAGE_INFO =
  "Volume, taxa, prazo, ticket, receita contratada e distribuicao por dia util das operacoes efetivadas no periodo."

export default function OperacoesPage() {
  const pathname = usePathname()
  const sp = useSearchParams()
  const { filtersWithFocus } = useBiFilters()
  const activeTab = useActiveTab()

  const buildTabHref = (tab: TabKey) => {
    const next = new URLSearchParams(sp.toString())
    next.set("tab", tab)
    return `${pathname}?${next.toString()}`
  }

  //
  // Resumo — mantida pelo ProvenanceFooter (que precisa do metadata de
  // proveniencia agregado). Os KPIs em si foram removidos da UI; quando
  // voltarem, reutilizamos esta mesma query.
  // Usa `filtersWithFocus` porque qualquer agregado exibido na pagina
  // respeita o cross-filter de mes selecionado.
  //
  const resumoQuery = useQuery({
    queryKey: ["bi", "operacoes", "resumo", filtersWithFocus],
    queryFn: () => biOperacoes.resumo(filtersWithFocus),
  })

  const handleCopyLink = React.useCallback(() => {
    // Best-effort: navegador sem Clipboard API so nao copia; nao e erro critico.
    void navigator.clipboard?.writeText(window.location.href)
  }, [])

  return (
    <div className="flex flex-col gap-6 px-12 py-6">
      <PageHeader
        title="BI · Operacoes"
        info={PAGE_INFO}
        actions={
          <Button variant="secondary" onClick={handleCopyLink}>
            <RiLinkM aria-hidden="true" className="size-4 shrink-0" />
            Copiar link
          </Button>
        }
      />

      {/* L3 tabs — CLAUDE.md 11.6: L3 sempre TabNavigation, nunca sub-sub-item de sidebar. */}
      <TabNavigation>
        {TABS.map((t) => (
          <TabNavigationLink
            key={t.key}
            asChild
            active={activeTab === t.key}
          >
            <Link href={buildTabHref(t.key)}>{t.label}</Link>
          </TabNavigationLink>
        ))}
      </TabNavigation>

      <TabContent tab={activeTab} />

      <ProvenanceFooter provenance={resumoQuery.data?.provenance} />
    </div>
  )
}

//
// Renderers por L3
//

function TabContent({ tab }: { tab: TabKey }) {
  switch (tab) {
    case "volume":
      return <VolumeTab />
    case "taxa":
      return <TaxaTab />
    case "prazo":
      return <PrazoTab />
    case "ticket":
      return <TicketTab />
    case "receita":
      return <ReceitaTab />
    case "dia-util":
      return <DiaUtilTab />
  }
}

//
// useBiQuery — assinatura nova aceita filtros explicitos.
// Motivacao: com cross-filter, cada chart pode precisar de um subset
// diferente dos filtros globais. Ex.: chart-SOURCE usa `filters` raw,
// widgets-DESTINO usam `filtersWithFocus`. O hook nao decide mais — quem
// chama passa os filtros e o fetcher que os consome.
//
function useBiQuery<T>(
  tab: TabKey,
  filters: BIFilters,
  fetcher: (f: BIFilters) => Promise<BIResponse<T>>,
  extraKey?: string,
) {
  return useQuery({
    queryKey: extraKey
      ? ["bi", "operacoes", tab, extraKey, filters]
      : ["bi", "operacoes", tab, filters],
    queryFn: () => fetcher(filters),
  })
}

//
// Wrapper generico da aba — sempre renderiza <BiFiltersBar variant="inline" />
// no topo e o conteudo da aba embaixo, com gap consistente.
//
function TabShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-4">
      <BiFiltersBar variant="inline" />
      {children}
    </div>
  )
}

//
// ChartCard — mantido como wrapper leve para cada chart dentro da aba.
// Diferente do Card Tremor externo: este apenas agrupa titulo + chart
// com border sutil para separacao visual dentro da superficie unica.
//
function ChartCard({
  title,
  children,
  className = "",
}: {
  title: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <div
      className={`flex flex-col gap-3 rounded border border-gray-200 p-4 dark:border-gray-800 ${className}`}
    >
      <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
        {title}
      </h3>
      {children}
    </div>
  )
}

//
// Volume — reformulada Onda 1: KPIs de contexto + chart principal
// configuravel + decomposicao com deltas.
//
// Cross-filter: chart principal (modo Total + Barra) e SOURCE. Clique numa
// barra foca o mes nos widgets-destino (KPIs, decomposicao, outras tabs).
// O proprio chart source NAO se auto-filtra — continua mostrando o range
// macro, Tremor destaca a barra ativa e as demais ficam em opacity reduzida.
//
function VolumeTab() {
  const {
    filtersWithFocus,
    filtersWithFocusMes,
    filtersWithFocusProduto,
    focusProduto,
    setFilter,
  } = useBiFilters()

  // 3 queries especializadas conforme o papel de cada componente no
  // cross-filter. Sem focus ativo, as chaves dedupam para 1 request.
  //
  //  - `chartQuery`: destino de focusProduto, SOURCE de focusMes.
  //    O chart principal nao deve se auto-filtrar por mes (se o usuario
  //    clicou num mes, mostra todas as barras mantendo a ativa em destaque),
  //    mas deve responder ao produto em foco.
  const chartQuery = useBiQuery(
    "volume",
    filtersWithFocusProduto,
    biOperacoes.volume,
    "chart",
  )

  //  - `listaQuery`: destino de focusMes, SOURCE de focusProduto.
  //    A lista de produto e o chart lateral de evolucao precisam mostrar
  //    TODOS os produtos (para o muted/destaque funcionar), mas devem
  //    refletir o mes em foco quando o usuario clica numa barra.
  const listaQuery = useBiQuery(
    "volume",
    filtersWithFocusMes,
    biOperacoes.volume,
    "lista",
  )

  //  - `kpisQuery`: destino total (ambos os focos aplicados).
  //    KPIs do topo e tabs Empresa/MoM sao destinos puros — nenhuma
  //    dimensao se auto-preserva aqui.
  const kpisQuery = useBiQuery(
    "volume",
    filtersWithFocus,
    biOperacoes.volume,
    "kpis",
  )

  return (
    <TabShell>
      <div className="flex flex-col gap-4">
        {/* §1 — KPIs INLINE: barra horizontal compacta (storytelling-ready).
            Altura ~60px (vs 150px do formato em card). Inclui mini donut
            "Volume / UA" clicavel que aplica filtro de UA globalmente. */}
        <VolumeKpisInline
          resumo={kpisQuery.data?.data.resumo}
          porUa={kpisQuery.data?.data.por_ua}
          volumeTotal={kpisQuery.data?.data.resumo.volume_total}
          loading={kpisQuery.isLoading}
          onUaClick={(uaId) => {
            if (!uaId) {
              setFilter({ uaId: undefined })
              return
            }
            const n = Number(uaId)
            if (Number.isFinite(n)) setFilter({ uaId: [n] })
          }}
        />

        {/* §2 — Grid 60/40: chart principal (source) + painel lateral (destinos)

            Inspirado no padrao premium de BI (Seer/Eleken/Looker): chart fica
            protagonista sem ocupar a tela toda; indicadores contextuais ficam
            ao lado, permitindo comparar evolucao x decomposicao no mesmo
            campo de visao. */}
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
          {/*
            Chart de Evolucao: SOURCE de focusMes, DESTINO de focusProduto.
            Usa `chartQuery` (filtersWithFocusProduto) para que clicar em
            "Faturização" na lista ao lado filtre este chart, mas sem que
            uma barra clicada aqui se auto-filtre.
          */}
          <VolumeEvolucaoChart
            data={chartQuery.data?.data}
            loading={chartQuery.isLoading}
            onBarClick={(iso) => {
              if (!iso) {
                setFilter({ focusMes: undefined })
                return
              }
              setFilter({ focusMes: iso.slice(0, 7) })
            }}
            className="lg:col-span-3"
          />

          {/*
            Painel lateral — duas fontes de dados por dimensao:

              - `data` = listaQuery (filtersWithFocusMes):
                alimenta as LISTAS/agregacoes (TabProduto.lista, TabMom).
                Source de produto + destino de mes.

              - `chartData` = chartQuery (filtersWithFocusProduto):
                alimenta os CHARTS TEMPORAIS (evolucao_por_produto do
                TabProduto, evolucao_por_ua do TabEmpresa). Esses charts
                compartilham a natureza "source de mes" com o chart
                principal — se filtrassem por focusMes colapsariam em
                1 unico ponto temporal.
          */}
          <VolumeIndicadoresPanel
            data={listaQuery.data?.data}
            chartData={chartQuery.data?.data}
            loading={listaQuery.isLoading || chartQuery.isLoading}
            focusSigla={focusProduto}
            onProdutoClick={(sigla) =>
              // Toggle: clicar na sigla ja focada desmarca; caso contrario foca.
              setFilter({
                focusProduto:
                  focusProduto === sigla ? undefined : sigla,
              })
            }
            className="lg:col-span-2"
          />
        </div>
      </div>
    </TabShell>
  )
}

//
// Taxa
//
function TaxaTab() {
  const { filtersWithFocus } = useBiFilters()
  const q = useBiQuery("taxa", filtersWithFocus, biOperacoes.taxa)
  const data = q.data?.data
  const evo = (data?.evolucao ?? []).map((p) => ({
    periodo: labelForPeriodo(p.periodo),
    "Taxa media": p.valor,
  }))
  const prod = (data?.por_produto ?? []).map((c) => ({
    name: c.categoria,
    value: c.valor,
  }))
  const mod = (data?.por_modalidade ?? []).map((c) => ({
    name: c.categoria,
    value: c.valor,
  }))
  return (
    <TabShell>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard
          title="Taxa de juros media ponderada por volume (% a.m.)"
          className="lg:col-span-2"
        >
          <AreaChart
            data={evo}
            index="periodo"
            categories={["Taxa media"]}
            valueFormatter={percent1}
            className="h-72"
            showLegend={false}
          />
        </ChartCard>
        <ChartCard title="Por produto">
          <BarList data={prod} valueFormatter={percent1} />
        </ChartCard>
        <ChartCard title="Por modalidade">
          <BarList data={mod} valueFormatter={percent1} />
        </ChartCard>
      </div>
    </TabShell>
  )
}

//
// Prazo
//
function PrazoTab() {
  const { filtersWithFocus } = useBiFilters()
  const q = useBiQuery("prazo", filtersWithFocus, biOperacoes.prazo)
  const data = q.data?.data
  const evo = (data?.evolucao ?? []).map((p) => ({
    periodo: labelForPeriodo(p.periodo),
    "Prazo medio": p.valor,
  }))
  const prod = (data?.por_produto ?? []).map((c) => ({
    name: c.categoria,
    value: c.valor,
  }))
  return (
    <TabShell>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard
          title="Prazo medio real ponderado por volume (dias)"
          className="lg:col-span-2"
        >
          <AreaChart
            data={evo}
            index="periodo"
            categories={["Prazo medio"]}
            valueFormatter={diasFmt}
            className="h-72"
            showLegend={false}
          />
        </ChartCard>
        <ChartCard title="Por produto" className="lg:col-span-2">
          <BarList data={prod} valueFormatter={diasFmt} />
        </ChartCard>
      </div>
    </TabShell>
  )
}

//
// Ticket
//
function TicketTab() {
  const { filtersWithFocus } = useBiFilters()
  const q = useBiQuery("ticket", filtersWithFocus, biOperacoes.ticket)
  const data = q.data?.data
  const evo = (data?.evolucao ?? []).map((p) => ({
    periodo: labelForPeriodo(p.periodo),
    "Ticket medio": p.valor,
  }))
  const prod = (data?.por_produto ?? []).map((c) => ({
    name: c.categoria,
    value: c.valor,
  }))
  const top = (data?.por_cedente_top ?? []).map((c) => ({
    name: c.categoria,
    value: c.valor,
  }))
  return (
    <TabShell>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard title="Ticket medio por operacao" className="lg:col-span-2">
          <AreaChart
            data={evo}
            index="periodo"
            categories={["Ticket medio"]}
            valueFormatter={(v) => moeda.format(v)}
            className="h-72"
            showLegend={false}
          />
        </ChartCard>
        <ChartCard title="Por produto">
          <BarList data={prod} valueFormatter={(v) => moeda.format(v)} />
        </ChartCard>
        <ChartCard title="Top 10 contas por ticket medio (>= 3 op.)">
          <BarList data={top} valueFormatter={(v) => moeda.format(v)} />
        </ChartCard>
      </div>
    </TabShell>
  )
}

//
// Receita
//
function ReceitaTab() {
  const { filtersWithFocus } = useBiFilters()
  const q = useBiQuery("receita", filtersWithFocus, biOperacoes.receita)
  const data = q.data?.data
  const evo = (data?.evolucao ?? []).map((p) => ({
    periodo: labelForPeriodo(p.periodo),
    "Receita contratada": p.valor,
  }))
  const comp = (data?.por_componente ?? []).map((c) => ({
    name: c.categoria,
    amount: c.valor,
  }))
  const prod = (data?.por_produto ?? []).map((c) => ({
    name: c.categoria,
    value: c.valor,
  }))
  return (
    <TabShell>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <ChartCard title="Receita contratada mensal" className="lg:col-span-2">
          <AreaChart
            data={evo}
            index="periodo"
            categories={["Receita contratada"]}
            valueFormatter={(v) => moedaCompacta.format(v)}
            className="h-72"
            showLegend={false}
          />
        </ChartCard>
        <ChartCard title="Composicao por componente">
          <DonutChart
            data={comp}
            category="name"
            value="amount"
            valueFormatter={(v) => moeda.format(v)}
            className="h-56"
          />
        </ChartCard>
        <ChartCard title="Por produto" className="lg:col-span-3">
          <BarList data={prod} valueFormatter={(v) => moedaCompacta.format(v)} />
        </ChartCard>
      </div>
    </TabShell>
  )
}

//
// Dia util
//
function DiaUtilTab() {
  const { filtersWithFocus } = useBiFilters()
  const q = useBiQuery("dia-util", filtersWithFocus, biOperacoes.diaUtil)
  const data = q.data?.data

  // Converte periodo sintetico 2000-01-DD em rotulo de dia do mes
  const porDia = (data?.por_dia_util ?? []).map((p) => {
    const [, , d] = p.periodo.split("-").map(Number)
    return { dia: `Dia ${d}`, "Volume bruto": p.valor }
  })
  const porSemana = (data?.por_dia_semana ?? []).map((c) => ({
    name: c.categoria,
    value: c.valor,
  }))

  return (
    <TabShell>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard
          title="Volume por dia do mes (agregado no periodo)"
          className="lg:col-span-2"
        >
          <BarChart
            data={porDia}
            index="dia"
            categories={["Volume bruto"]}
            valueFormatter={(v) => moedaCompacta.format(v)}
            className="h-72"
            showLegend={false}
          />
        </ChartCard>
        <ChartCard title="Por dia da semana" className="lg:col-span-2">
          <BarList
            data={porSemana}
            valueFormatter={(v) => moedaCompacta.format(v)}
          />
        </ChartCard>
      </div>
    </TabShell>
  )
}
