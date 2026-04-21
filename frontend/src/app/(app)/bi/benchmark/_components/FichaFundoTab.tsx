"use client"

import { RiAlertLine, RiSearchLine } from "@remixicon/react"
import * as React from "react"

import { EmptyState } from "@/components/app/EmptyState"
import { Badge } from "@/components/tremor/Badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRoot,
  TableRow,
} from "@/components/tremor/Table"
import { AreaChart } from "@/components/charts/AreaChart"
import { BarChart } from "@/components/charts/BarChart"
import { BarList } from "@/components/charts/BarList"
import { DonutChart } from "@/components/charts/DonutChart"
import { LineChart } from "@/components/charts/LineChart"
import { ProgressCircle } from "@/components/charts/ProgressCircle"
import { KpiHero, KpiSecondary } from "@/components/bi/KpiGrid"

import { ficha as getFicha } from "../_fixtures/fundos"
import type { Ficha } from "../_fixtures/types"
import { useFundoCnpj } from "../_hooks/useBenchmarkUrl"
import {
  formatCNPJ,
  labelCompetencia,
  moeda,
  moedaCompacta,
  numero,
  percent1,
} from "./formatters"
import { ChartCard } from "./ChartCard"

//
// FichaFundoTab — orquestrador das secoes da ficha unitaria.
// Se nao ha `cnpj` na URL, mostra EmptyState pedindo selecao pelo combobox.
//
export function FichaFundoTab() {
  const { cnpj } = useFundoCnpj()

  if (!cnpj) {
    return (
      <EmptyState
        icon={RiSearchLine}
        title="Selecione um fundo"
        description="Use o seletor acima ou clique em 'Ver ficha' na aba Lista de fundos para abrir a ficha unitaria."
      />
    )
  }

  const ficha = getFicha(cnpj)
  if (!ficha) {
    return (
      <EmptyState
        icon={RiAlertLine}
        title="Fundo nao encontrado"
        description={`Nenhuma ficha disponivel para o CNPJ ${formatCNPJ(cnpj)} na competencia atual.`}
      />
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <IdentidadeHeader ficha={ficha} />
      <PlSubclassesCard ficha={ficha} />
      <QualidadeCreditoCard ficha={ficha} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <AtivoCard ficha={ficha} className="lg:col-span-2" />
        <SegmentoCard ficha={ficha} className="lg:col-span-3" />
      </div>
      <CedentesCard ficha={ficha} />
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <PassivoCard ficha={ficha} />
        <TaxasCard ficha={ficha} />
      </div>
      <CotistasCard ficha={ficha} />
      <RegularidadeGarantiasCard ficha={ficha} />
      <RentabilidadeCard />
    </div>
  )
}

//
// §1 — Identidade & Escala
//
function IdentidadeHeader({ ficha }: { ficha: Ficha }) {
  const { identidade, escala } = ficha
  const colchaoVariant: "success" | "warning" | "error" =
    escala.colchao_subordinacao_pct >= 20
      ? "success"
      : escala.colchao_subordinacao_pct >= 12
        ? "warning"
        : "error"

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-50">
            {identidade.denominacao_social}
          </h2>
          <Badge variant="default">{identidade.classe_anbima}</Badge>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="neutral">
            Condominio: {identidade.condominio === "aberto" ? "aberto" : "fechado"}
          </Badge>
          {identidade.exclusivo && <Badge variant="neutral">Exclusivo</Badge>}
          {identidade.monoclasse && <Badge variant="neutral">Monoclasse</Badge>}
          <Badge variant="neutral">
            Prazo resgate:{" "}
            {identidade.prazo_min_resgate_dias
              ? `${identidade.prazo_min_resgate_dias} d`
              : "n/a"}
          </Badge>
          <Badge variant="neutral">
            Conversao:{" "}
            {identidade.prazo_conversao_dias
              ? `${identidade.prazo_conversao_dias} d`
              : "n/a"}
          </Badge>
        </div>
        <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
          <div>
            <dt className="inline font-medium">Admin: </dt>
            <dd className="inline">{identidade.administrador}</dd>
          </div>
          <div>
            <dt className="inline font-medium">CNPJ fundo: </dt>
            <dd className="inline font-mono">
              {formatCNPJ(identidade.cnpj_fundo)}
            </dd>
          </div>
          <div>
            <dt className="inline font-medium">CNPJ classe: </dt>
            <dd className="inline font-mono">
              {formatCNPJ(identidade.cnpj_classe)}
            </dd>
          </div>
          <div>
            <dt className="inline font-medium">Competencia: </dt>
            <dd className="inline">{labelCompetencia(identidade.competencia)}</dd>
          </div>
        </dl>
      </div>

      <KpiHero
        kpis={[
          {
            label: "Patrimonio liquido",
            valor: escala.pl,
            unidade: "BRL",
            detalhe: `PL medio 3m ${moedaCompacta.format(escala.pl_medio_3m)}`,
          },
        ]}
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <ColchaoTile
          valor={escala.colchao_subordinacao_pct}
          variant={colchaoVariant}
        />
        <KpiSecondary
          kpis={[
            {
              label: "Duration carteira",
              valor: escala.duration_dias,
              unidade: "dias",
              detalhe: "media ponderada",
            },
          ]}
        />
        <KpiSecondary
          kpis={[
            {
              label: "Numero de cotistas",
              valor: escala.nro_cotistas,
              unidade: "un",
              detalhe: "total (todas subclasses)",
            },
          ]}
        />
        <KpiSecondary
          kpis={[
            {
              label: "% DC / PL",
              valor: escala.pct_dc_pl,
              unidade: "%",
              detalhe: "alocacao do PL em DC",
            },
          ]}
        />
      </div>
    </div>
  )
}

function ColchaoTile({
  valor,
  variant,
}: {
  valor: number
  variant: "success" | "warning" | "error"
}) {
  const badgeVariant = variant
  const label =
    variant === "success" ? "Saudavel" : variant === "warning" ? "Moderado" : "Baixo"
  return (
    <div className="flex flex-col gap-1">
      <dt className="text-xs font-medium text-gray-500 dark:text-gray-400">
        Colchao de subordinacao
      </dt>
      <dd className="flex items-baseline gap-2">
        <span className="text-base font-semibold tabular-nums text-gray-900 dark:text-gray-50">
          {percent1(valor)}
        </span>
        <Badge variant={badgeVariant}>{label}</Badge>
      </dd>
      <span className="text-xs text-gray-500 dark:text-gray-400">
        % do PL em subordinada/mezanino
      </span>
    </div>
  )
}

//
// §2 — PL por Subclasse
//
function PlSubclassesCard({ ficha }: { ficha: Ficha }) {
  const donut = ficha.pl_subclasses.map((s) => ({
    subclasse: s.subclasse,
    pl: s.pl,
  }))
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
      <ChartCard
        title="Distribuicao por subclasse"
        className="lg:col-span-2"
      >
        <DonutChart
          data={donut}
          category="subclasse"
          value="pl"
          valueFormatter={(v) => moedaCompacta.format(v)}
          className="h-56"
        />
      </ChartCard>
      <ChartCard title="PL por subclasse" className="lg:col-span-3">
        <TableRoot>
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell>Subclasse</TableHeaderCell>
                <TableHeaderCell className="text-right">Cotas</TableHeaderCell>
                <TableHeaderCell className="text-right">Vl. cota</TableHeaderCell>
                <TableHeaderCell className="text-right">PL</TableHeaderCell>
                <TableHeaderCell className="text-right">% PL</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {ficha.pl_subclasses.map((s) => (
                <TableRow key={s.subclasse}>
                  <TableCell className="font-medium">{s.subclasse}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {numero.format(s.qtd_cotas)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {moeda.format(s.vl_cota)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {moedaCompacta.format(s.pl)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {percent1(s.pct_pl)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableRoot>
      </ChartCard>
    </div>
  )
}

//
// §3 — Rentabilidade por Classe (gated no MVP)
//
function RentabilidadeCard() {
  return (
    <EmptyState
      icon={RiAlertLine}
      title="Rentabilidade por classe — em extensao"
      description="Rentabilidade mensal por classe/subclasse (X.3-RENT_MES) sera disponibilizada apos extensao do ETL CVM. Previsto em v1.1."
    />
  )
}

//
// §4 — Qualidade de Credito
//
function QualidadeCreditoCard({ ficha }: { ficha: Ficha }) {
  const { qualidade } = ficha
  const evo = qualidade.evolucao.map((p) => ({
    periodo: labelCompetencia(p.periodo),
    "% Inad total": p.pct_inad_total,
    "% Inad >90d": p.pct_inad_90d,
    "% Inad >360d": p.pct_inad_360d,
    "% Cobertura PDD": p.pct_cobertura,
  }))

  const aVencer = qualidade.aging_a_vencer.map((f) => ({
    faixa: f.faixa,
    Valor: f.valor,
  }))
  const inad = qualidade.aging_inadimplente.map((f) => ({
    faixa: f.faixa,
    Valor: f.valor,
  }))
  const scr = qualidade.scr_devedores.map((s) => ({
    name: s.rating,
    value: s.pct_devedores,
  }))

  const pctAAA = qualidade.scr_devedores
    .filter((s) => s.rating === "AA" || s.rating === "A")
    .reduce((sum, s) => sum + s.pct_operacoes, 0)
  const pctBC = qualidade.scr_devedores
    .filter((s) => s.rating === "B" || s.rating === "C")
    .reduce((sum, s) => sum + s.pct_operacoes, 0)
  const pctDG = qualidade.scr_devedores
    .filter((s) => ["D", "E", "F", "G"].includes(s.rating))
    .reduce((sum, s) => sum + s.pct_operacoes, 0)
  const pctH = qualidade.scr_devedores
    .filter((s) => s.rating === "H")
    .reduce((sum, s) => sum + s.pct_operacoes, 0)

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-4">
        <QualidadeKpi
          label="% Inadimplencia total"
          valor={qualidade.pct_inad_total}
          percentil={qualidade.percentil_inad_total}
          inverso
        />
        <QualidadeKpi
          label="% Inadimplencia >90d"
          valor={qualidade.pct_inad_90d}
          percentil={Math.max(qualidade.percentil_inad_total - 5, 0)}
          inverso
        />
        <QualidadeKpi
          label="% Inadimplencia >360d"
          valor={qualidade.pct_inad_360d}
          percentil={Math.max(qualidade.percentil_inad_total - 10, 0)}
          inverso
        />
        <QualidadeKpi
          label="% Cobertura PDD"
          valor={qualidade.pct_cobertura_pdd}
          percentil={qualidade.percentil_cobertura}
        />
      </div>

      <ChartCard
        title="Evolucao de qualidade de credito (24m)"
        info="Tendencia de inadimplencia em multiplas marcas e cobertura por PDD."
      >
        <LineChart
          data={evo}
          index="periodo"
          categories={[
            "% Inad total",
            "% Inad >90d",
            "% Inad >360d",
            "% Cobertura PDD",
          ]}
          valueFormatter={percent1}
          className="h-72"
        />
      </ChartCard>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ChartCard title="Carteira a vencer — aging">
          <BarChart
            data={aVencer}
            index="faixa"
            categories={["Valor"]}
            valueFormatter={(v) => moedaCompacta.format(v)}
            className="h-64"
            showLegend={false}
          />
        </ChartCard>
        <ChartCard title="Carteira inadimplente — aging">
          <BarChart
            data={inad}
            index="faixa"
            categories={["Valor"]}
            valueFormatter={(v) => moedaCompacta.format(v)}
            className="h-64"
            showLegend={false}
          />
        </ChartCard>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <ChartCard title="SCR devedores (% por rating)" className="lg:col-span-3">
          <BarList
            data={scr}
            valueFormatter={(v) => percent1(v)}
            sortOrder="none"
          />
        </ChartCard>
        <div className="grid grid-cols-2 gap-4 lg:col-span-2">
          <ScrKpi label="% AA-A" valor={pctAAA} variant="success" />
          <ScrKpi label="% B-C" valor={pctBC} variant="default" />
          <ScrKpi label="% D-G" valor={pctDG} variant="warning" />
          <ScrKpi label="% H" valor={pctH} variant="error" />
        </div>
      </div>
    </div>
  )
}

function QualidadeKpi({
  label,
  valor,
  percentil,
  inverso = false,
}: {
  label: string
  valor: number
  percentil: number
  inverso?: boolean
}) {
  // Se o indicador e "lower is better" (inverso), percentil bom = alto no universo (abaixo da mediana).
  const variant: "success" | "warning" | "error" =
    percentil >= 70 ? "success" : percentil >= 40 ? "warning" : "error"
  const progressVariant =
    variant === "success" ? "success" : variant === "error" ? "error" : "warning"
  return (
    <div className="flex items-center gap-3 rounded border border-gray-200 p-4 dark:border-gray-800">
      <ProgressCircle
        value={percentil}
        radius={22}
        strokeWidth={4}
        variant={progressVariant}
      >
        <span className="text-[10px] font-semibold tabular-nums text-gray-900 dark:text-gray-50">
          P{percentil}
        </span>
      </ProgressCircle>
      <div className="flex flex-col gap-0.5">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
          {label}
        </span>
        <span className="text-base font-semibold tabular-nums text-gray-900 dark:text-gray-50">
          {percent1(valor)}
        </span>
        <span className="text-[11px] text-gray-500 dark:text-gray-400">
          vs classe ANBIMA{inverso ? " (menor e melhor)" : ""}
        </span>
      </div>
    </div>
  )
}

function ScrKpi({
  label,
  valor,
  variant,
}: {
  label: string
  valor: number
  variant: "success" | "default" | "warning" | "error"
}) {
  return (
    <div className="flex flex-col gap-1 rounded border border-gray-200 p-3 dark:border-gray-800">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
          {label}
        </span>
        <Badge variant={variant}>SCR</Badge>
      </div>
      <span className="text-base font-semibold tabular-nums text-gray-900 dark:text-gray-50">
        {percent1(valor)}
      </span>
    </div>
  )
}

//
// §5 — Ativo
//
function AtivoCard({
  ficha,
  className,
}: {
  ficha: Ficha
  className?: string
}) {
  const donut = ficha.ativo.map((a) => ({ categoria: a.categoria, valor: a.valor }))
  return (
    <ChartCard title="Composicao do ativo" className={className}>
      <DonutChart
        data={donut}
        category="categoria"
        value="valor"
        valueFormatter={(v) => moedaCompacta.format(v)}
        className="h-56"
      />
      <TableRoot className="mt-3">
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Categoria</TableHeaderCell>
              <TableHeaderCell className="text-right">Valor</TableHeaderCell>
              <TableHeaderCell className="text-right">% Ativo</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {ficha.ativo.map((a) => (
              <TableRow key={a.categoria}>
                <TableCell className="text-xs">{a.categoria}</TableCell>
                <TableCell className="text-right tabular-nums text-xs">
                  {moedaCompacta.format(a.valor)}
                </TableCell>
                <TableCell className="text-right tabular-nums text-xs">
                  {percent1(a.pct)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableRoot>
    </ChartCard>
  )
}

//
// §6 — Carteira por Segmento
//
function SegmentoCard({
  ficha,
  className,
}: {
  ficha: Ficha
  className?: string
}) {
  const bars = ficha.segmento.map((s) => ({ name: s.setor, value: s.valor }))
  const evolucao = ficha.evolucao_setores.map((p) => ({
    ...p,
    periodo: labelCompetencia(p.periodo as string),
  }))
  return (
    <div className={className + " flex flex-col gap-4"}>
      <ChartCard title="Carteira por segmento">
        <BarList data={bars} valueFormatter={(v) => moedaCompacta.format(v)} />
      </ChartCard>
      <ChartCard title="Evolucao setorial (24m, stacked)">
        <AreaChart
          data={evolucao}
          index="periodo"
          categories={["Comercial", "Industrial", "Servicos", "Factoring", "Agro", "Outros"]}
          valueFormatter={(v) => moedaCompacta.format(v)}
          type="stacked"
          className="h-64"
        />
      </ChartCard>
    </div>
  )
}

//
// §7 — Concentracao de Cedentes
//
function CedentesCard({ ficha }: { ficha: Ficha }) {
  const bars = ficha.cedentes.map((c) => ({
    name: c.denominacao ?? c.cnpj_mascarado,
    value: c.pct,
  }))
  const top1 = ficha.cedentes[0]?.pct ?? 0
  const top3 = ficha.cedentes.slice(0, 3).reduce((s, c) => s + c.pct, 0)
  const top9 = ficha.cedentes.slice(0, 9).reduce((s, c) => s + c.pct, 0)

  const alerta = top1 > 20
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
      <ChartCard
        title="Top cedentes (% da carteira)"
        className="lg:col-span-3"
      >
        <BarList
          data={bars}
          valueFormatter={(v) => percent1(v)}
          sortOrder="none"
        />
      </ChartCard>
      <div className="flex flex-col gap-3 lg:col-span-2">
        <CedenteKpi
          label="Top-1"
          valor={top1}
          alerta={alerta}
          detalhe="maior cedente"
        />
        <CedenteKpi
          label="Top-3 acumulado"
          valor={top3}
          detalhe="3 maiores cedentes"
        />
        <CedenteKpi
          label="Top-9 acumulado"
          valor={top9}
          detalhe="9 maiores cedentes"
        />
      </div>
    </div>
  )
}

function CedenteKpi({
  label,
  valor,
  alerta,
  detalhe,
}: {
  label: string
  valor: number
  alerta?: boolean
  detalhe: string
}) {
  return (
    <div className="flex items-center justify-between rounded border border-gray-200 p-4 dark:border-gray-800">
      <div className="flex flex-col gap-0.5">
        <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
          {label}
        </span>
        <span className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
          {percent1(valor)}
        </span>
        <span className="text-[11px] text-gray-500 dark:text-gray-400">
          {detalhe}
        </span>
      </div>
      {alerta && <Badge variant="warning">Concentrado</Badge>}
    </div>
  )
}

//
// §8 — Passivo
//
function PassivoCard({ ficha }: { ficha: Ficha }) {
  return (
    <ChartCard title="Passivo & alavancagem">
      <TableRoot>
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Linha</TableHeaderCell>
              <TableHeaderCell className="text-right">Valor</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            <TableRow>
              <TableCell>Curto prazo</TableCell>
              <TableCell className="text-right tabular-nums">
                {moeda.format(ficha.passivo.curto_prazo)}
              </TableCell>
            </TableRow>
            <TableRow>
              <TableCell>Longo prazo</TableCell>
              <TableCell className="text-right tabular-nums">
                {moeda.format(ficha.passivo.longo_prazo)}
              </TableCell>
            </TableRow>
            {ficha.passivo.derivativos.map((d) => (
              <TableRow key={d.tipo}>
                <TableCell className="text-xs text-gray-500">{d.tipo}</TableCell>
                <TableCell className="text-right tabular-nums text-xs">
                  {moeda.format(d.valor)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableRoot>
      <div className="mt-3 flex items-center justify-between rounded bg-gray-50 px-3 py-2 dark:bg-gray-900">
        <span className="text-xs font-medium text-gray-600 dark:text-gray-400">
          Alavancagem (Passivo / PL)
        </span>
        <span className="text-sm font-semibold tabular-nums text-gray-900 dark:text-gray-50">
          {percent1(ficha.passivo.alavancagem_pct)}
        </span>
      </div>
    </ChartCard>
  )
}

//
// §9 — Taxa de desconto na aquisicao
//
function TaxasCard({ ficha }: { ficha: Ficha }) {
  const evo = ficha.taxas.evolucao.map((p) => ({
    periodo: labelCompetencia(p.periodo),
    "DC com risco": p.taxa_dc_com,
    "DC sem risco": p.taxa_dc_sem,
  }))
  return (
    <ChartCard title="Taxas de desconto (media ponderada)">
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-1 rounded border border-gray-200 p-3 dark:border-gray-800">
          <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
            DC com risco cedente
          </span>
          <span className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
            {percent1(ficha.taxas.taxa_media_ponderada_dc_com_risco)} a.m.
          </span>
        </div>
        <div className="flex flex-col gap-1 rounded border border-gray-200 p-3 dark:border-gray-800">
          <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
            DC sem risco cedente
          </span>
          <span className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
            {percent1(ficha.taxas.taxa_media_ponderada_dc_sem_risco)} a.m.
          </span>
        </div>
      </div>
      <AreaChart
        data={evo}
        index="periodo"
        categories={["DC com risco", "DC sem risco"]}
        valueFormatter={percent1}
        className="mt-3 h-56"
      />
    </ChartCard>
  )
}

//
// §10 — Cotistas
//
function CotistasCard({ ficha }: { ficha: Ficha }) {
  const donut = ficha.cotistas.por_subclasse.map((s) => ({
    subclasse: s.subclasse,
    qtd: s.qtd,
  }))
  const bars = ficha.cotistas.por_tipo_investidor
    .map((t) => ({ name: t.tipo, value: t.senior + t.subord }))
    .filter((b) => b.value > 0)

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
      <ChartCard title="Cotistas por subclasse" className="lg:col-span-2">
        <DonutChart
          data={donut}
          category="subclasse"
          value="qtd"
          valueFormatter={(v) => numero.format(v)}
          className="h-56"
        />
        <div className="mt-2 text-center text-xs text-gray-500 dark:text-gray-400">
          Total: {numero.format(ficha.cotistas.total)} cotistas
        </div>
      </ChartCard>
      <ChartCard title="Cotistas por tipo de investidor" className="lg:col-span-3">
        <BarList data={bars} valueFormatter={(v) => numero.format(v)} />
      </ChartCard>
    </div>
  )
}

//
// §11 & §12 — Regularidade + Garantias (compactos, lado a lado)
//
function RegularidadeGarantiasCard({ ficha }: { ficha: Ficha }) {
  const hasDivida = ficha.regularidade_cedido_com_divida > 0
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <ChartCard title="Regularidade tributaria de cedentes">
        <div className="flex items-center justify-between rounded bg-gray-50 p-3 dark:bg-gray-900">
          <div className="flex flex-col gap-0.5">
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
              Volume cedido por cedentes com divida ativa
            </span>
            <span className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
              {moeda.format(ficha.regularidade_cedido_com_divida)}
            </span>
          </div>
          <Badge variant={hasDivida ? "warning" : "neutral"}>
            {hasDivida ? "Atencao" : "Zerado"}
          </Badge>
        </div>
      </ChartCard>
      <ChartCard title="Garantias vinculadas a DC">
        <div className="grid grid-cols-2 gap-3">
          <div className="flex flex-col gap-0.5 rounded bg-gray-50 p-3 dark:bg-gray-900">
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
              % DC com garantia
            </span>
            <span className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
              {percent1(ficha.garantias_pct_dc_com_garantia)}
            </span>
          </div>
          <div className="flex flex-col gap-0.5 rounded bg-gray-50 p-3 dark:bg-gray-900">
            <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
              Valor total garantias
            </span>
            <span className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
              {moedaCompacta.format(ficha.garantias_valor_total)}
            </span>
          </div>
        </div>
      </ChartCard>
    </div>
  )
}

