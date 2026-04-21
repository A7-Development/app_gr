"use client"

import { useQuery } from "@tanstack/react-query"

import { AreaChart } from "@/components/charts/AreaChart"
import { BarChart } from "@/components/charts/BarChart"
import { BarList } from "@/components/charts/BarList"
import { KpiHero, KpiSecondary } from "@/components/bi/KpiGrid"
import { biBenchmark } from "@/lib/api-client"

import { labelCompetencia, moedaCompacta, numero, percent1 } from "./formatters"
import { ChartCard } from "./ChartCard"

//
// MercadoTab — visao macro do setor FIDC com dados reais CVM (postgres_fdw).
// Consome /bi/benchmark/resumo + /pdd + /evolucao. Storytelling top-down:
// KPIs do mercado -> distribuicao -> evolucao. Loading = placeholders vazios.
//

const MESES_EVOLUCAO = 24

export function MercadoTab() {
  const resumo = useQuery({
    queryKey: ["bi", "benchmark", "resumo"],
    queryFn: () => biBenchmark.resumo(),
    staleTime: 60_000,
  })
  const pdd = useQuery({
    queryKey: ["bi", "benchmark", "pdd"],
    queryFn: () => biBenchmark.pdd(),
    staleTime: 60_000,
  })
  const evolucao = useQuery({
    queryKey: ["bi", "benchmark", "evolucao", MESES_EVOLUCAO],
    queryFn: () => biBenchmark.evolucao({ meses: MESES_EVOLUCAO }),
    staleTime: 60_000,
  })

  const totalFundosKpi = resumo.data?.data.total_fundos
  const plTotalKpi = resumo.data?.data.pl_total
  const pddMediana = resumo.data?.data.pdd_mediana
  const inadMediana = resumo.data?.data.inadimplencia_mediana
  const cobMediana = resumo.data?.data.cobertura_mediana

  const plChart = (evolucao.data?.data.pl_total ?? []).map((p) => ({
    periodo: labelCompetencia(p.periodo),
    "PL total do mercado": p.valor,
  }))
  const fundosChart = (evolucao.data?.data.num_fundos ?? []).map((p) => ({
    periodo: labelCompetencia(p.periodo),
    "Fundos reportando": p.valor,
  }))
  const plMedianoChart = (evolucao.data?.data.pl_mediano ?? []).map((p) => ({
    periodo: labelCompetencia(p.periodo),
    "PL mediano": p.valor,
  }))
  const plMedianoAtual = evolucao.data?.data.pl_mediano.at(-1)?.valor ?? 0

  const hist = (pdd.data?.data.histograma ?? []).map((c) => ({
    bucket: c.categoria,
    "Qtd. fundos": c.valor,
  }))
  const top = (pdd.data?.data.top_fundos ?? []).map((c) => ({
    name: c.categoria,
    value: c.valor,
  }))

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4">
        <KpiHero
          kpis={[
            {
              label: totalFundosKpi?.label ?? "Fundos reportando",
              valor: totalFundosKpi?.valor ?? 0,
              unidade: totalFundosKpi?.unidade ?? "un",
              detalhe: totalFundosKpi?.detalhe ?? null,
            },
            {
              label: plTotalKpi?.label ?? "PL total do mercado",
              valor: plTotalKpi?.valor ?? 0,
              unidade: plTotalKpi?.unidade ?? "BRL",
              detalhe: plTotalKpi?.detalhe ?? null,
            },
            {
              label: "PL mediano",
              valor: plMedianoAtual,
              unidade: "BRL",
              detalhe: "defensivo contra outliers",
            },
          ]}
        />
        <KpiSecondary
          kpis={[
            {
              label: inadMediana?.label ?? "Inadimplencia mediana",
              valor: inadMediana?.valor ?? 0,
              unidade: inadMediana?.unidade ?? "%",
              detalhe: inadMediana?.detalhe ?? null,
            },
            {
              label: cobMediana?.label ?? "Cobertura PDD mediana",
              valor: cobMediana?.valor ?? 0,
              unidade: cobMediana?.unidade ?? "%",
              detalhe: cobMediana?.detalhe ?? null,
            },
            {
              label: pddMediana?.label ?? "PDD mediana",
              valor: pddMediana?.valor ?? 0,
              unidade: pddMediana?.unidade ?? "%",
              detalhe: pddMediana?.detalhe ?? null,
            },
          ]}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <ChartCard title="PL total do mercado (24m)" className="lg:col-span-2">
          <AreaChart
            data={plChart}
            index="periodo"
            categories={["PL total do mercado"]}
            valueFormatter={(v) => moedaCompacta.format(v)}
            className="h-72"
            showLegend={false}
          />
        </ChartCard>
        <ChartCard title="Fundos reportando">
          <BarChart
            data={fundosChart}
            index="periodo"
            categories={["Fundos reportando"]}
            valueFormatter={(v) => numero.format(v)}
            className="h-72"
            showLegend={false}
          />
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard title="Distribuicao de %PDD no mercado">
          <BarChart
            data={hist}
            index="bucket"
            categories={["Qtd. fundos"]}
            valueFormatter={(v) => numero.format(v)}
            className="h-72"
            showLegend={false}
          />
        </ChartCard>
        <ChartCard title="Top 10 fundos por %PDD">
          <BarList data={top} valueFormatter={(v) => percent1(v)} />
        </ChartCard>
      </div>

      <ChartCard title="PL mediano do mercado (24m)">
        <AreaChart
          data={plMedianoChart}
          index="periodo"
          categories={["PL mediano"]}
          valueFormatter={(v) => moedaCompacta.format(v)}
          className="h-72"
          showLegend={false}
        />
      </ChartCard>
    </div>
  )
}
