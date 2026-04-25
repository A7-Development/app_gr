"use client"

import { useQuery } from "@tanstack/react-query"

import {
  RiAlertLine,
  RiArrowUpCircleLine,
  RiSparklingFill,
} from "@remixicon/react"

import { AreaChart } from "@/components/charts/AreaChart"
import { BarChart } from "@/components/charts/BarChart"
import { BarList } from "@/components/charts/BarList"
import { DonutChart } from "@/components/charts/DonutChart"
import { Insight, InsightBar } from "@/components/app/Insight"
import { KPICard, KPIStrip } from "@/components/app/KPICard"
import { biBenchmark } from "@/lib/api-client"

import { labelCompetencia, moedaCompacta, numero } from "./formatters"
import { ChartCard } from "./ChartCard"
import { useBenchmarkFilters } from "../_hooks/useBenchmarkFilters"

//
// MercadoTab — visao macro do setor FIDC com dados CVM publicos.
//
// Charts:
//  1. PL total do mercado (area) + Fundos reportando (bar) — evolucao
//  2. PL mediano do mercado (area) — evolucao
//  3. Top 10 Administradoras por quantidade (barlist) e por PL (barlist)
//  4. Aberto vs Fechado — snapshot (donut) + evolucao mensal (stacked %)
//
// Filtros: BenchmarkFiltersBar (PeriodoPresets + MonthRangePicker +
// tipo_fundo FilterPill + incluir_exclusivos Switch).
//

/** Converte 'YYYY-MM' em label extenso 'abril/2026' (para headline do donut). */
function fmtYmLong(ym: string): string {
  const [y, m] = ym.split("-").map(Number)
  return new Date(y, m - 1, 1).toLocaleString("pt-BR", {
    month: "long",
    year: "numeric",
  })
}

export function MercadoTab() {
  const { filters } = useBenchmarkFilters()

  const evolucao = useQuery({
    queryKey: ["bi", "benchmark", "evolucao", filters],
    queryFn: () => biBenchmark.evolucao(filters),
    staleTime: 60_000,
  })

  const admins = useQuery({
    queryKey: ["bi", "benchmark", "admins", filters],
    queryFn: () => biBenchmark.admins(filters),
    staleTime: 60_000,
  })

  const condom = useQuery({
    queryKey: ["bi", "benchmark", "condom", filters],
    queryFn: () => biBenchmark.condom(filters),
    staleTime: 60_000,
  })

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

  // Top 10 admins por quantidade e por PL — formato BarList.
  const adminsData = admins.data?.data
  const topQtdBars = (adminsData?.top_por_quantidade ?? []).map((a) => ({
    key: a.cnpj_admin ?? a.admin,
    name: a.admin,
    value: a.quantidade_fundos,
  }))
  const topPlBars = (adminsData?.top_por_pl ?? []).map((a) => ({
    key: a.cnpj_admin ?? a.admin,
    name: a.admin,
    value: a.pl_total,
  }))

  // Aberto vs Fechado — snapshot (donut) e serie mensal (stacked 100%).
  const condomData = condom.data?.data
  const donutData = condomData
    ? [
        { categoria: "Aberto", qtd: condomData.aberto_qtd },
        { categoria: "Fechado", qtd: condomData.fechado_qtd },
      ]
    : []
  const condomTotal = condomData
    ? condomData.aberto_qtd + condomData.fechado_qtd
    : 0
  const condomSerie = (condomData?.evolucao ?? []).map((p) => ({
    periodo: labelCompetencia(p.periodo),
    Aberto: p.aberto_qtd,
    Fechado: p.fechado_qtd,
  }))

  // ---------------------------------------------------------------------
  // Zona Z3 (BI Framework, CLAUDE.md §19) — KPI strip do mercado.
  // 6 cards, SEM sparkline, cada um com OriginDot.
  // ---------------------------------------------------------------------
  const plTotalSerie = evolucao.data?.data.pl_total ?? []
  const plTotalLast = plTotalSerie.at(-1)
  const plTotalPrev = plTotalSerie.at(-2)
  const plTotalDelta =
    plTotalLast && plTotalPrev && plTotalPrev.valor !== 0
      ? ((plTotalLast.valor - plTotalPrev.valor) / plTotalPrev.valor) * 100
      : undefined

  const plMedianoSerie = evolucao.data?.data.pl_mediano ?? []
  const plMedianoLast = plMedianoSerie.at(-1)

  const fundosSerie = evolucao.data?.data.num_fundos ?? []
  const fundosLast = fundosSerie.at(-1)
  const fundosPrev = fundosSerie.at(-2)
  const fundosDelta =
    fundosLast && fundosPrev ? fundosLast.valor - fundosPrev.valor : undefined

  const topAdmin = adminsData?.top_por_pl.at(0)
  const adminSource = "cvm_remote (Informes Mensais)"
  const kpiUpdatedISO = plTotalLast
    ? `${plTotalLast.periodo}-01T00:00:00Z`
    : null

  // ---------------------------------------------------------------------
  // Intensidade dos KPIs (barrinhas 3) — heuristicas baseadas na leitura
  // do mercado FIDC. Regras simples, conservadoras (Handoff v2 §Z3):
  //   pos (emerald) = leitura favoravel; neu (amber) = estavel/neutro;
  //   neg (red) = leitura desfavoravel; info (blue) = informativo.
  // ---------------------------------------------------------------------
  const plTotalIntensity =
    plTotalDelta === undefined
      ? undefined
      : ({
          tone: plTotalDelta >= 0 ? "pos" : "neg",
          level:
            Math.abs(plTotalDelta) >= 5
              ? "high"
              : Math.abs(plTotalDelta) >= 1
                ? "mid"
                : "low",
        } as const)

  const fundosIntensity =
    fundosDelta === undefined
      ? undefined
      : ({
          tone: fundosDelta >= 0 ? "pos" : "neg",
          level:
            Math.abs(fundosDelta) >= 30
              ? "high"
              : Math.abs(fundosDelta) >= 5
                ? "mid"
                : "low",
        } as const)

  return (
    <div className="flex flex-col gap-4">
      <h2 className="text-[17px] font-semibold leading-tight tracking-tight text-gray-900 dark:text-gray-50">
        Visão geral
      </h2>

      <KPIStrip>
        <KPICard
          label="PL total do mercado"
          value={
            plTotalLast ? moedaCompacta.format(plTotalLast.valor) : "--"
          }
          sub={plTotalLast ? labelCompetencia(plTotalLast.periodo) : undefined}
          delta={
            plTotalDelta !== undefined
              ? {
                  value: plTotalDelta,
                  suffix: "%",
                  direction: plTotalDelta >= 0 ? "up" : "down",
                }
              : undefined
          }
          intensity={plTotalIntensity}
          source={adminSource}
          updatedAtISO={kpiUpdatedISO}
        />
        <KPICard
          label="Fundos reportando"
          value={fundosLast ? numero.format(fundosLast.valor) : "--"}
          sub={fundosLast ? labelCompetencia(fundosLast.periodo) : undefined}
          delta={
            fundosDelta !== undefined
              ? {
                  value: fundosDelta,
                  direction: fundosDelta >= 0 ? "up" : "down",
                }
              : undefined
          }
          intensity={fundosIntensity}
          source={adminSource}
          updatedAtISO={kpiUpdatedISO}
        />
        <KPICard
          label="PL mediano"
          value={
            plMedianoLast ? moedaCompacta.format(plMedianoLast.valor) : "--"
          }
          sub="por fundo"
          intensity={{ tone: "info", level: "mid" }}
          source={adminSource}
          updatedAtISO={kpiUpdatedISO}
        />
        <KPICard
          label="Administradoras"
          value={
            adminsData ? numero.format(adminsData.total_admins) : "--"
          }
          sub="distintas no mercado"
          intensity={{ tone: "info", level: "high" }}
          source={adminSource}
          updatedAtISO={kpiUpdatedISO}
        />
        <KPICard
          label="% Aberto"
          value={
            condomData ? `${condomData.aberto_pct.toFixed(1)}%` : "--"
          }
          sub={`${numero.format(condomData?.aberto_qtd ?? 0)} fundos`}
          intensity={
            condomData
              ? {
                  tone: "neu",
                  level:
                    condomData.aberto_pct >= 60
                      ? "high"
                      : condomData.aberto_pct >= 30
                        ? "mid"
                        : "low",
                }
              : undefined
          }
          source={adminSource}
          updatedAtISO={kpiUpdatedISO}
        />
        <KPICard
          label="Maior administrador"
          value={topAdmin?.admin ?? "--"}
          sub={
            topAdmin ? moedaCompacta.format(topAdmin.pl_total) + " PL" : undefined
          }
          intensity={{ tone: "neu", level: "high" }}
          source={adminSource}
          updatedAtISO={kpiUpdatedISO}
        />
      </KPIStrip>

      <InsightBar>
        {plTotalDelta !== undefined && plTotalLast && (
          <Insight
            tone={plTotalDelta >= 0 ? "blue" : "amber"}
            icon={plTotalDelta >= 0 ? RiArrowUpCircleLine : RiAlertLine}
            text={
              plTotalDelta >= 0
                ? `PL total do mercado cresceu ${plTotalDelta.toFixed(1)}% na competencia ${labelCompetencia(plTotalLast.periodo)}.`
                : `PL total do mercado recuou ${Math.abs(plTotalDelta).toFixed(1)}% na competencia ${labelCompetencia(plTotalLast.periodo)}.`
            }
            cta={{ label: "Ver no grafico", href: "#pl-total" }}
          />
        )}
        {topAdmin && adminsData && (
          <Insight
            tone="violet"
            icon={RiSparklingFill}
            text={`${topAdmin.admin} concentra ${moedaCompacta.format(topAdmin.pl_total)} de PL \u2014 maior administrador do mercado FIDC na competencia.`}
          />
        )}
      </InsightBar>

      {/* Linha 1 — PL total (wide) + Fundos reportando */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <ChartCard title="PL total do mercado" className="lg:col-span-2">
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

      {/* Linha 2 — PL mediano */}
      <ChartCard title="PL mediano do mercado">
        <AreaChart
          data={plMedianoChart}
          index="periodo"
          categories={["PL mediano"]}
          valueFormatter={(v) => moedaCompacta.format(v)}
          className="h-72"
          showLegend={false}
        />
      </ChartCard>

      {/* Linha 3 — Top 10 admins (qtd + PL) */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard
          title="Top 10 administradoras por quantidade de fundos"
          info={
            adminsData?.competencia
              ? `Snapshot em ${fmtYmLong(adminsData.competencia)}. ${
                  adminsData.total_admins
                } administradoras distintas no mercado.`
              : undefined
          }
        >
          <BarList
            data={topQtdBars}
            valueFormatter={(v) => numero.format(v)}
            className="h-72 overflow-y-auto"
          />
        </ChartCard>
        <ChartCard
          title="Top 10 administradoras por PL sob administracao"
          info={
            adminsData?.competencia
              ? `Snapshot em ${fmtYmLong(adminsData.competencia)}.`
              : undefined
          }
        >
          <BarList
            data={topPlBars}
            valueFormatter={(v) => moedaCompacta.format(v)}
            className="h-72 overflow-y-auto"
          />
        </ChartCard>
      </div>

      {/* Linha 4 — Aberto vs Fechado: snapshot + evolucao */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <ChartCard
          title="Aberto vs Fechado — snapshot"
          info={
            condomData?.competencia
              ? `Distribuicao em ${fmtYmLong(
                  condomData.competencia,
                )}. Fundos com condominio fora de (ABERTO, FECHADO) sao ignorados.`
              : undefined
          }
        >
          <div className="flex flex-col items-center gap-2 py-4">
            <span className="text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
              {condomData?.competencia
                ? fmtYmLong(condomData.competencia)
                : "—"}
            </span>
            <DonutChart
              data={donutData}
              category="categoria"
              value="qtd"
              valueFormatter={(v) => numero.format(v)}
              showLabel
              label={numero.format(condomTotal)}
              colors={["emerald", "slate"]}
              className="h-52"
            />
            <div className="flex gap-4 text-xs text-gray-600 dark:text-gray-400">
              <span>
                <span className="font-semibold text-gray-900 dark:text-gray-50">
                  {condomData ? `${condomData.aberto_pct.toFixed(1)}%` : "—"}
                </span>{" "}
                Aberto
              </span>
              <span>
                <span className="font-semibold text-gray-900 dark:text-gray-50">
                  {condomData ? `${condomData.fechado_pct.toFixed(1)}%` : "—"}
                </span>{" "}
                Fechado
              </span>
            </div>
          </div>
        </ChartCard>
        <ChartCard
          title="Aberto vs Fechado — evolucao (%)"
          className="lg:col-span-2"
          info="Proporcao mensal entre fundos abertos e fechados no universo publicado pela CVM."
        >
          <BarChart
            data={condomSerie}
            index="periodo"
            categories={["Aberto", "Fechado"]}
            type="percent"
            colors={["emerald", "slate"]}
            valueFormatter={(v) => numero.format(v)}
            className="h-72"
          />
        </ChartCard>
      </div>
    </div>
  )
}
