"use client"

//
// Preview publico dos primitivos do BI Framework (CLAUDE.md §19).
// Fora do shell (app), sem AuthGuard -- serve para validacao visual
// dos componentes criados a partir do handoff A7 Credit Design System.
//
// Rota: /preview/bi-framework
//

import * as React from "react"
import {
  RiAlertLine,
  RiArrowUpCircleLine,
  RiCalendarLine,
  RiDownloadLine,
  RiFundsLine,
  RiLockUnlockLine,
  RiShareLine,
  RiSparklingFill,
} from "@remixicon/react"

import { AIButton } from "@/design-system/components/AIButton"
import { AIDrawer } from "@/design-system/components/AIDrawer"
import { FilterBar, MoreFiltersButton } from "@/design-system/components/FilterBar"
import { FilterChip } from "@/design-system/components/FilterBar"
import { Insight, InsightBar } from "@/design-system/components/Insight"
import { KpiCard, KpiStrip } from "@/design-system/components/KpiStrip"
import { PageHeader } from "@/design-system/components/PageHeader"
import { VizCard } from "@/design-system/components/VizCard"
import { Button } from "@/components/tremor/Button"
import {
  TabNavigation,
  TabNavigationLink,
} from "@/components/tremor/TabNavigation"
import { BarChart } from "@/components/charts/BarChart"
import { AreaChart } from "@/components/charts/AreaChart"

const MOCK_EVOLUCAO = [
  { periodo: "nov/25", pl: 420, fundos: 2720 },
  { periodo: "dez/25", pl: 432, fundos: 2742 },
  { periodo: "jan/26", pl: 446, fundos: 2788 },
  { periodo: "fev/26", pl: 461, fundos: 2830 },
  { periodo: "mar/26", pl: 475, fundos: 2858 },
  { periodo: "abr/26", pl: 490, fundos: 2872 },
]

const MOCK_COMP = [
  { categoria: "Multiclasse", valor: 1245 },
  { categoria: "Direitos Credit.", valor: 982 },
  { categoria: "Infraestrutura", valor: 410 },
  { categoria: "Imobiliario", valor: 235 },
]

const SOURCE = "cvm_remote (Informes Mensais)"
const UPDATED_AT = "2026-04-15T02:15:00Z"

export default function BIFrameworkPreviewPage() {
  const [agrupar, setAgrupar] = React.useState("categoria")
  const [recorte, setRecorte] = React.useState("top10")
  const [tipo, setTipo] = React.useState("barras")
  const [aiOpen, setAiOpen] = React.useState(false)
  const overrideActive = recorte !== "tudo" || tipo !== "barras"

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <div className="flex flex-col gap-4 px-12 py-4">
        {/* Z1 - Filter Bar sticky (chips canonicos v2) */}
        <FilterBar extraActions={<MoreFiltersButton count={0} />}>
          <FilterChip
            icon={RiCalendarLine}
            label="Periodo"
            value="12M"
            active
          />
          <FilterChip
            icon={RiFundsLine}
            label="Tipo de fundo"
            value="Todos"
          />
          <FilterChip
            icon={RiLockUnlockLine}
            label="Exclusivos"
            value="Excluidos"
          />
        </FilterBar>
        {/* Z2 - Page Header + AIButton */}
        <PageHeader
          title="BI · Benchmark (Preview)"
          info="Preview dos primitivos do BI Framework (handoff A7 Credit)."
          actions={
            <>
              <Button variant="secondary" className="gap-1.5">
                <RiShareLine className="size-4" aria-hidden="true" />
                Compartilhar
              </Button>
              <Button variant="secondary" className="gap-1.5">
                <RiDownloadLine className="size-4" aria-hidden="true" />
                Exportar
              </Button>
              <AIButton onClick={() => setAiOpen(true)} />
            </>
          }
        />

        {/* Z3 - KPI Strip (6 cards, com intensity v2, OriginDot) */}
        <KpiStrip>
          <KpiCard
            label="PL total do mercado"
            value="R$ 490 bi"
            sub="abr/26"
            delta={{ value: 3.2, suffix: "%", direction: "up" }}
            intensity={{ tone: "pos", level: "mid" }}
            source={SOURCE}
            updatedAtISO={UPDATED_AT}
          />
          <KpiCard
            label="Fundos reportando"
            value="2.872"
            sub="abr/26"
            delta={{ value: 14, direction: "up" }}
            intensity={{ tone: "pos", level: "mid" }}
            source={SOURCE}
            updatedAtISO={UPDATED_AT}
          />
          <KpiCard
            label="PL mediano"
            value="R$ 82 mi"
            sub="por fundo"
            intensity={{ tone: "info", level: "mid" }}
            source={SOURCE}
            updatedAtISO={UPDATED_AT}
          />
          <KpiCard
            label="Administradoras"
            value="184"
            sub="distintas"
            intensity={{ tone: "info", level: "high" }}
            source={SOURCE}
            updatedAtISO={UPDATED_AT}
          />
          <KpiCard
            label="% Aberto"
            value="62,4%"
            sub="1.792 fundos"
            delta={{ value: 0.4, suffix: "pp", direction: "up" }}
            intensity={{ tone: "neu", level: "high" }}
            source={SOURCE}
            updatedAtISO={UPDATED_AT}
          />
          <KpiCard
            label="Maior administrador"
            value="BRL Trust"
            sub="R$ 48 bi PL"
            intensity={{ tone: "neg", level: "low" }}
            source={SOURCE}
            updatedAtISO={UPDATED_AT}
          />
        </KpiStrip>

        {/* Z4 - Insights IA (tons variados v2) */}
        <InsightBar>
          <Insight
            tone="blue"
            icon={RiArrowUpCircleLine}
            text="PL total do mercado cresceu 3,2% em abr/26 -- maior salto mensal do ano."
            cta={{ label: "Ver no grafico", href: "#pl" }}
            onDismiss={() => {}}
          />
          <Insight
            tone="amber"
            icon={RiAlertLine}
            text="Concentracao top-3 admins subiu 1,1pp na competencia. Limite interno: 50%."
            cta={{ label: "Detalhar", href: "#concentracao" }}
            onDismiss={() => {}}
          />
          <Insight
            tone="violet"
            icon={RiSparklingFill}
            text="Tipo 'Multiclasse' representa 45% do PL total -- maior categoria do mercado."
            cta={{ label: "Ver detalhes", href: "#categoria" }}
            onDismiss={() => {}}
          />
        </InsightBar>

        {/* Z5 - L3 Tabs */}
        <TabNavigation>
          <TabNavigationLink active>Mercado</TabNavigationLink>
          <TabNavigationLink>Lista de fundos</TabNavigationLink>
          <TabNavigationLink>Ficha do fundo</TabNavigationLink>
          <TabNavigationLink>Comparativo</TabNavigationLink>
        </TabNavigation>

        {/* Z6 - Grid de visualizacoes (hero 3:2) */}
        <div className="grid grid-cols-1 gap-3 lg:grid-cols-5">
          <VizCard
            title="Evolucao do PL total"
            subtitle="Ultimos 6 meses"
            className="lg:col-span-3"
            source={SOURCE}
            updatedAtISO={UPDATED_AT}
            agrupar={{
              value: agrupar,
              onChange: setAgrupar,
              options: [
                { value: "categoria", label: "Categoria" },
                { value: "admin", label: "Administrador" },
                { value: "regiao", label: "Regiao" },
              ],
            }}
            recorte={{
              value: recorte,
              onChange: setRecorte,
              options: [
                { value: "tudo", label: "Toda a carteira" },
                { value: "top10", label: "Top 10" },
                { value: "top20", label: "Top 20" },
              ],
            }}
            tipo={{
              value: tipo,
              onChange: setTipo,
              options: [
                { value: "barras", label: "Barras" },
                { value: "linhas", label: "Linhas" },
                { value: "tabela", label: "Tabela" },
              ],
            }}
            override={
              overrideActive
                ? {
                    label: `${recorte === "top10" ? "Top 10" : recorte === "top20" ? "Top 20" : "Tudo"}${tipo !== "barras" ? ` / ${tipo}` : ""}`,
                    onReset: () => {
                      setRecorte("tudo")
                      setTipo("barras")
                    },
                  }
                : undefined
            }
          >
            <AreaChart
              data={MOCK_EVOLUCAO}
              index="periodo"
              categories={["pl"]}
              showLegend={false}
              className="h-56"
            />
          </VizCard>

          <VizCard
            title="Leitura do periodo"
            subtitle="Ultimos 6 meses · abr/26"
            className="lg:col-span-2"
          >
            <div className="flex flex-col gap-3">
              <div>
                <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500">
                  Crescimento acumulado
                </p>
                <p className="text-2xl font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                  +16,7%
                  <span className="ml-2 text-sm text-emerald-600">
                    ↑
                  </span>
                </p>
                <p className="text-xs text-gray-500">nov/25 → abr/26</p>
              </div>
              <div className="border-t border-gray-200 pt-3 dark:border-gray-800">
                <p className="text-[11px] font-medium uppercase tracking-wider text-gray-500">
                  Pico do periodo
                </p>
                <p className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                  R$ 490 bi · abr/26
                </p>
              </div>
              <p className="text-[11px] leading-relaxed text-gray-500">
                Serie reflete universo CVM sem ajuste por tipo de fundo. Aberto
                concentra 62,4% do PL.
              </p>
            </div>
          </VizCard>
        </div>

        <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
          <VizCard
            title="Composicao por categoria"
            subtitle="Snapshot abr/26"
            source={SOURCE}
            updatedAtISO={UPDATED_AT}
          >
            <BarChart
              data={MOCK_COMP}
              index="categoria"
              categories={["valor"]}
              showLegend={false}
              className="h-48"
            />
          </VizCard>
          <VizCard
            title="Fundos reportando"
            subtitle="Serie mensal"
            source={SOURCE}
            updatedAtISO={UPDATED_AT}
          >
            <BarChart
              data={MOCK_EVOLUCAO}
              index="periodo"
              categories={["fundos"]}
              showLegend={false}
              className="h-48"
            />
          </VizCard>
        </div>

        {/* Z7 - Provenance Footer */}
        <div className="mt-4 grid grid-cols-1 gap-3 border-t border-gray-200 pt-3 text-xs dark:border-gray-800 sm:grid-cols-3">
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider text-gray-500">
              Fonte
            </p>
            <p className="text-gray-900 dark:text-gray-50">
              DW · cvm_remote.tab_i
            </p>
          </div>
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider text-gray-500">
              Atualizado
            </p>
            <p className="font-mono text-gray-900 dark:text-gray-50">
              ha 2 h (15/04/2026 02:15)
            </p>
          </div>
          <div>
            <p className="text-[10px] font-medium uppercase tracking-wider text-gray-500">
              SLA
            </p>
            <p className="text-gray-900 dark:text-gray-50">
              2h — dentro do acordo
            </p>
          </div>
        </div>
      </div>

      <AIDrawer
        open={aiOpen}
        onOpenChange={setAiOpen}
        context={{
          page: "Benchmark (Preview)",
          tab: "Mercado",
          filters: ["Período: 12M", "Exclusivos: Excluídos"],
        }}
      />
    </div>
  )
}
