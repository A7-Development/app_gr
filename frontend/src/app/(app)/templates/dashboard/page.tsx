"use client"

import * as React from "react"
import { ptBR } from "date-fns/locale"
import { RiArrowUpLine, RiArrowDownLine } from "@remixicon/react"

import { PageHeader } from "@/components/app/PageHeader"
import { Badge } from "@/components/tremor/Badge"
import { Card } from "@/components/tremor/Card"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import { DateRangePicker, type DateRange } from "@/components/tremor/DatePicker"
import { AreaChart } from "@/components/charts/AreaChart"
import { BarChart } from "@/components/charts/BarChart"
import { DonutChart } from "@/components/charts/DonutChart"
import { BarList } from "@/components/charts/BarList"
import {
  SparkAreaChart,
  SparkLineChart,
  SparkBarChart,
} from "@/components/charts/SparkChart"

//
// Formatadores pt-BR
//

const moedaBR = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
})

const moedaBRcompacta = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
})

const numeroBR = new Intl.NumberFormat("pt-BR")

const percentualBR = (value: number) =>
  value.toLocaleString("pt-BR", {
    style: "percent",
    maximumFractionDigits: 1,
  })

//
// Mock de dados
//

const kpiSparkReceita = [
  { mes: "Jan", valor: 820 },
  { mes: "Fev", valor: 900 },
  { mes: "Mar", valor: 870 },
  { mes: "Abr", valor: 1020 },
  { mes: "Mai", valor: 980 },
  { mes: "Jun", valor: 1080 },
]

const kpiSparkContratos = [
  { mes: "Jan", valor: 118 },
  { mes: "Fev", valor: 121 },
  { mes: "Mar", valor: 124 },
  { mes: "Abr", valor: 128 },
  { mes: "Mai", valor: 130 },
  { mes: "Jun", valor: 134 },
]

const kpiSparkInadimplencia = [
  { mes: "Jan", valor: 3.1 },
  { mes: "Fev", valor: 3.4 },
  { mes: "Mar", valor: 3.0 },
  { mes: "Abr", valor: 2.8 },
  { mes: "Mai", valor: 3.2 },
  { mes: "Jun", valor: 3.6 },
]

const receitaAno = [
  { mes: "Mai/25", Receita: 820000 },
  { mes: "Jun/25", Receita: 910000 },
  { mes: "Jul/25", Receita: 870000 },
  { mes: "Ago/25", Receita: 940000 },
  { mes: "Set/25", Receita: 980000 },
  { mes: "Out/25", Receita: 1020000 },
  { mes: "Nov/25", Receita: 1055000 },
  { mes: "Dez/25", Receita: 1120000 },
  { mes: "Jan/26", Receita: 980000 },
  { mes: "Fev/26", Receita: 1050000 },
  { mes: "Mar/26", Receita: 1090000 },
  { mes: "Abr/26", Receita: 1130000 },
]

const receitaPorCategoria = [
  { categoria: "Servicos", Valor: 620000 },
  { categoria: "Licencas", Valor: 310000 },
  { categoria: "Consultoria", Valor: 180000 },
  { categoria: "Suporte", Valor: 95000 },
]

const mixProdutos = [
  { name: "Plano Essencial", value: 540000 },
  { name: "Plano Avancado", value: 380000 },
  { name: "Plano Premium", value: 210000 },
  { name: "Adicionais", value: 120000 },
]

const topClientes = [
  { name: "Industria Alfa", value: 184000 },
  { name: "Comercial Beta", value: 142000 },
  { name: "Logistica Epsilon", value: 121000 },
  { name: "Construtora Zeta", value: 98000 },
  { name: "Transportes Gama", value: 76000 },
]

//
// KPI Card
//

type KpiProps = {
  label: string
  valor: string
  delta: string
  direction: "up" | "down"
  positive: boolean
  children: React.ReactNode
}

function KpiCard({ label, valor, delta, direction, positive, children }: KpiProps) {
  const Arrow = direction === "up" ? RiArrowUpLine : RiArrowDownLine
  return (
    <Card className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col gap-1">
          <span className="text-sm text-gray-500 dark:text-gray-400">
            {label}
          </span>
          <span className="text-2xl font-semibold text-gray-900 dark:text-gray-50">
            {valor}
          </span>
        </div>
        <Badge variant={positive ? "success" : "error"}>
          <Arrow className="size-3" aria-hidden />
          {delta}
        </Badge>
      </div>
      <div className="h-12">{children}</div>
    </Card>
  )
}

export default function DashboardTemplatePage() {
  const [periodo, setPeriodo] = React.useState<DateRange | undefined>(undefined)
  const [unidade, setUnidade] = React.useState("todas")

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Visao geral"
        subtitle="Abril 2026"
      />

      {/* Filtros globais */}
      <div className="flex flex-col gap-3 rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-950 sm:flex-row sm:items-center">
        <div className="w-full sm:w-72">
          <DateRangePicker
            value={periodo}
            onChange={setPeriodo}
            locale={ptBR}
            placeholder="Periodo de analise"
            translations={{
              cancel: "Cancelar",
              apply: "Aplicar",
              start: "Inicio",
              end: "Fim",
              range: "Periodo",
            }}
          />
        </div>
        <div className="w-full sm:ml-auto sm:w-64">
          <Select value={unidade} onValueChange={setUnidade}>
            <SelectTrigger>
              <SelectValue placeholder="Unidade de negocio" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="todas">Todas as unidades</SelectItem>
              <SelectItem value="servicos">Servicos</SelectItem>
              <SelectItem value="licencas">Licencas</SelectItem>
              <SelectItem value="consultoria">Consultoria</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      {/* KPIs */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-4">
        <KpiCard
          label="Receita"
          valor={moedaBR.format(1130000)}
          delta="+8,4%"
          direction="up"
          positive
        >
          <SparkAreaChart
            data={kpiSparkReceita}
            index="mes"
            categories={["valor"]}
            colors={["emerald"]}
            className="h-12 w-full"
          />
        </KpiCard>

        <KpiCard
          label="Contratos ativos"
          valor={numeroBR.format(134)}
          delta="+3,1%"
          direction="up"
          positive
        >
          <SparkLineChart
            data={kpiSparkContratos}
            index="mes"
            categories={["valor"]}
            colors={["blue"]}
            className="h-12 w-full"
          />
        </KpiCard>

        <KpiCard
          label="Inadimplencia"
          valor={percentualBR(0.036)}
          delta="+0,4 p.p."
          direction="up"
          positive={false}
        >
          <SparkBarChart
            data={kpiSparkInadimplencia}
            index="mes"
            categories={["valor"]}
            colors={["pink"]}
            className="h-12 w-full"
          />
        </KpiCard>

        <KpiCard
          label="Ticket medio"
          valor={moedaBR.format(8430)}
          delta="-1,2%"
          direction="down"
          positive={false}
        >
          <SparkAreaChart
            data={kpiSparkReceita}
            index="mes"
            categories={["valor"]}
            colors={["violet"]}
            className="h-12 w-full"
          />
        </KpiCard>
      </div>

      {/* Charts 2x2 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Card className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
              Receita ao longo do ano
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Evolucao mensal de maio/25 a abril/26.
            </p>
          </div>
          <AreaChart
            data={receitaAno}
            index="mes"
            categories={["Receita"]}
            colors={["blue"]}
            valueFormatter={(value) => moedaBRcompacta.format(value)}
            showLegend={false}
            className="h-72"
          />
        </Card>

        <Card className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
              Receita por categoria
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Distribuicao nos ultimos 30 dias.
            </p>
          </div>
          <BarChart
            data={receitaPorCategoria}
            index="categoria"
            categories={["Valor"]}
            colors={["emerald"]}
            valueFormatter={(value) => moedaBRcompacta.format(value)}
            showLegend={false}
            className="h-72"
          />
        </Card>

        <Card className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
              Mix de produtos
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Participacao de cada linha na receita total.
            </p>
          </div>
          <DonutChart
            data={mixProdutos}
            category="name"
            value="value"
            colors={["blue", "emerald", "violet", "amber"]}
            valueFormatter={(value) => moedaBRcompacta.format(value)}
            className="h-72"
          />
        </Card>

        <Card className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
              Top 5 clientes
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Maior volume faturado no mes.
            </p>
          </div>
          <BarList
            data={topClientes}
            valueFormatter={(value) => moedaBR.format(value)}
          />
        </Card>
      </div>
    </div>
  )
}
