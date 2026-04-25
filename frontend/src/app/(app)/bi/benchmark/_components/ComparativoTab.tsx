"use client"

import {
  RiAlertLine,
  RiCheckLine,
  RiCloseLine,
  RiLoader4Line,
  RiScales3Line,
} from "@remixicon/react"
import { useQuery } from "@tanstack/react-query"
import * as React from "react"

import { cx } from "@/lib/utils"
import { EmptyState } from "@/design-system/components/EmptyState"
import { Badge } from "@/components/tremor/Badge"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRoot,
  TableRow,
} from "@/components/tremor/Table"
import { BarChart } from "@/components/charts/BarChart"
import { BarList } from "@/components/charts/BarList"
import { DonutChart } from "@/components/charts/DonutChart"
import { LineChart } from "@/components/charts/LineChart"
import {
  biBenchmark,
  type ComparativoResponse,
  type ComposicaoFundo,
  type FundoHeader,
  type RankingLinha,
} from "@/lib/api-client"

import { FUNDO_COR_CLASSES, FUNDO_CORES } from "../_fixtures/indicadores"
import { useSelectedFundos } from "../_hooks/useBenchmarkUrl"
import {
  formatCNPJ,
  labelCompetencia,
  moeda,
  moedaCompacta,
  numero,
  percent1,
} from "./formatters"
import { ChartCard } from "./ChartCard"

const MESES_COMPARATIVO = 24

// Subset dos indicadores do ranking que sao renderizados como BarChart horizontal
// no "Confronto visual". Todas as outras linhas continuam no ranking.
const INDICADORES_CONFRONTO = [
  "pl",
  "pct_inad_total",
  "pct_saudavel",
  "pct_dc_pl",
  "dc_total",
  "top1_cedente",
] as const

// Agrupamento visual do ranking (ordem preservada).
const GRUPOS: Array<{ titulo: string; keys: string[] }> = [
  { titulo: "Escala", keys: ["pl", "pl_medio", "dc_total", "pct_dc_pl"] },
  { titulo: "Qualidade de credito", keys: ["pct_inad_total", "pct_inad_longo", "pct_saudavel"] },
  { titulo: "Concentracao de cedentes", keys: ["qt_cedentes", "top1_cedente", "top3_cedente"] },
]

export function ComparativoTab() {
  const { selected, remove, clear } = useSelectedFundos()

  const query = useQuery({
    queryKey: ["bi", "benchmark", "comparativo", selected, MESES_COMPARATIVO],
    queryFn: () =>
      biBenchmark.comparativo({ cnpjs: selected, meses: MESES_COMPARATIVO }),
    enabled: selected.length >= 2,
    staleTime: 60_000,
  })

  if (selected.length < 2) {
    return (
      <EmptyState
        icon={RiScales3Line}
        title="Selecione pelo menos 2 fundos"
        description="Use a aba Lista de fundos para marcar ate 5 fundos e comparar os principais indicadores lado a lado."
      />
    )
  }

  if (query.isLoading) {
    return (
      <div className="flex items-center justify-center gap-2 py-16 text-sm text-gray-500 dark:text-gray-400">
        <RiLoader4Line className="size-4 animate-spin" aria-hidden="true" />
        Carregando comparativo...
      </div>
    )
  }

  if (query.isError || !query.data) {
    return (
      <EmptyState
        icon={RiAlertLine}
        title="Nao foi possivel carregar o comparativo"
        description="Verifique a conexao ou tente novamente em instantes."
      />
    )
  }

  const data = query.data.data

  return (
    <div className="flex flex-col gap-6">
      <ComparativoHeader data={data} onRemove={remove} onClear={clear} />
      <RankingTable data={data} />
      <ConfrontoVisual data={data} />
      <EvolucaoComparada data={data} />
      <PerfisLadoALado data={data} />
    </div>
  )
}

//
// Header com chips removiveis dos fundos selecionados.
//
function ComparativoHeader({
  data,
  onRemove,
  onClear,
}: {
  data: ComparativoResponse
  onRemove: (cnpj: string) => void
  onClear: () => void
}) {
  return (
    <div className="sticky top-0 z-10 flex flex-wrap items-center gap-2 border-b border-gray-200 bg-white/95 py-3 backdrop-blur dark:border-gray-800 dark:bg-gray-950/95">
      <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
        Comparando {data.fundos.length} fundos
        {data.competencia && ` (${labelCompetencia(data.competencia)})`}:
      </span>
      {data.fundos.map((f) => {
        const cor = FUNDO_CORES[f.cor_index] ?? "slate"
        const classes = FUNDO_COR_CLASSES[cor]
        const label = f.denom_social ?? formatCNPJ(f.cnpj)
        return (
          <span
            key={f.cnpj}
            className={cx(
              "inline-flex items-center gap-1.5 rounded border py-1 pl-2 pr-1 text-xs font-medium text-gray-900 dark:text-gray-50",
              classes.border,
              classes.bg,
            )}
          >
            <span className={cx("inline-block size-2.5 rounded-full", classes.dot)} />
            <span className="max-w-[240px] truncate">{label}</span>
            <button
              type="button"
              onClick={() => onRemove(f.cnpj)}
              className="rounded p-0.5 text-gray-500 transition hover:bg-gray-200 dark:text-gray-400 dark:hover:bg-gray-800"
              aria-label={`Remover ${label}`}
            >
              <RiCloseLine className="size-3.5" aria-hidden="true" />
            </button>
          </span>
        )
      })}
      <button
        type="button"
        onClick={onClear}
        className="ml-auto inline-flex items-center gap-1 rounded px-2 py-1 text-xs font-medium text-gray-500 transition hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-50"
      >
        <RiCloseLine className="size-3.5" aria-hidden="true" />
        Limpar selecao
      </button>
    </div>
  )
}

function formatValor(v: number | null, unidade: string): string {
  if (v == null) return "—"
  if (unidade === "BRL") return moedaCompacta.format(v)
  if (unidade === "%") return percent1(v)
  if (unidade === "dias") return `${numero.format(Math.round(v))} d`
  return numero.format(Math.round(v))
}

function melhorCnpj(linha: RankingLinha): string | null {
  const validos = linha.valores.filter((v) => v.valor != null) as Array<{
    cnpj: string
    valor: number
  }>
  if (validos.length === 0) return null
  const comparator = linha.direction === "desc" ? (a: number, b: number) => a > b : (a: number, b: number) => a < b
  let melhor = validos[0]
  for (const v of validos.slice(1)) {
    if (comparator(v.valor, melhor.valor)) melhor = v
  }
  return melhor.cnpj
}

//
// §1 — Ranking sintetico
//
function RankingTable({ data }: { data: ComparativoResponse }) {
  const porKey = React.useMemo(() => {
    const map: Record<string, RankingLinha> = {}
    for (const linha of data.ranking) map[linha.key] = linha
    return map
  }, [data.ranking])

  return (
    <ChartCard
      title="Ranking sintetico"
      info="Cada linha destaca o melhor fundo no indicador. ↑ = maior e melhor, ↓ = menor e melhor."
    >
      <TableRoot>
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell className="w-[240px]">Indicador</TableHeaderCell>
              {data.fundos.map((f) => (
                <TableHeaderCell key={f.cnpj} className="text-right">
                  <FundoHeaderCell fundo={f} />
                </TableHeaderCell>
              ))}
              <TableHeaderCell className="text-right text-gray-500">
                Mediana mercado
              </TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {GRUPOS.flatMap((g) => {
              const linhas = g.keys
                .map((k) => porKey[k])
                .filter((l): l is RankingLinha => Boolean(l))
              if (linhas.length === 0) return []
              return [
                <TableRow key={`group-${g.titulo}`}>
                  <TableCell
                    colSpan={data.fundos.length + 2}
                    className="bg-gray-50 py-2 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:bg-gray-900 dark:text-gray-400"
                  >
                    {g.titulo}
                  </TableCell>
                </TableRow>,
                ...linhas.map((linha) => {
                  const melhor = melhorCnpj(linha)
                  return (
                    <TableRow key={linha.key}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-medium text-gray-900 dark:text-gray-50">
                            {linha.label}
                          </span>
                          <span className="text-[11px] text-gray-400">
                            {linha.direction === "desc" ? "↑ melhor" : "↓ melhor"}
                          </span>
                        </div>
                      </TableCell>
                      {data.fundos.map((f) => {
                        const v = linha.valores.find((x) => x.cnpj === f.cnpj)
                        const isMelhor = melhor === f.cnpj
                        return (
                          <TableCell
                            key={f.cnpj}
                            className={cx(
                              "text-right tabular-nums text-xs",
                              isMelhor &&
                                "bg-blue-50 font-semibold text-blue-900 dark:bg-blue-500/10 dark:text-blue-200",
                            )}
                          >
                            <span className="inline-flex items-center justify-end gap-1">
                              {isMelhor && (
                                <RiCheckLine
                                  className="size-3 text-blue-600 dark:text-blue-400"
                                  aria-hidden="true"
                                />
                              )}
                              {formatValor(v?.valor ?? null, linha.unidade)}
                            </span>
                          </TableCell>
                        )
                      })}
                      <TableCell className="text-right tabular-nums text-xs text-gray-500">
                        {formatValor(linha.mediana_mercado, linha.unidade)}
                      </TableCell>
                    </TableRow>
                  )
                }),
              ]
            })}
          </TableBody>
        </Table>
      </TableRoot>
    </ChartCard>
  )
}

function FundoHeaderCell({ fundo }: { fundo: FundoHeader }) {
  const cor = FUNDO_CORES[fundo.cor_index] ?? "slate"
  return (
    <span className="inline-flex items-center gap-1.5">
      <span
        className={cx(
          "inline-block size-2 rounded-full",
          FUNDO_COR_CLASSES[cor].dot,
        )}
      />
      <span className="max-w-[140px] truncate">
        {fundo.denom_social ?? formatCNPJ(fundo.cnpj)}
      </span>
    </span>
  )
}

//
// §2 — Confronto visual: BarCharts horizontais por indicador-chave.
//
function ConfrontoVisual({ data }: { data: ComparativoResponse }) {
  const porKey = React.useMemo(() => {
    const map: Record<string, RankingLinha> = {}
    for (const linha of data.ranking) map[linha.key] = linha
    return map
  }, [data.ranking])

  const linhas = INDICADORES_CONFRONTO.map((k) => porKey[k]).filter(
    (l): l is RankingLinha => Boolean(l),
  )

  if (linhas.length === 0) return null

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {linhas.map((linha) => {
        const chartData = data.fundos.map((f) => {
          const v = linha.valores.find((x) => x.cnpj === f.cnpj)
          return {
            fundo: abreviaNome(f.denom_social ?? formatCNPJ(f.cnpj)),
            [linha.label]: v?.valor ?? 0,
          }
        })
        return (
          <ChartCard key={linha.key} title={linha.label}>
            <BarChart
              data={chartData}
              index="fundo"
              categories={[linha.label]}
              valueFormatter={(v) => formatValor(v, linha.unidade)}
              className="h-48"
              showLegend={false}
              layout="horizontal"
            />
            <div className="text-[11px] text-gray-500 dark:text-gray-400">
              Mediana mercado:{" "}
              <span className="font-medium">
                {formatValor(linha.mediana_mercado, linha.unidade)}
              </span>
            </div>
          </ChartCard>
        )
      })}
    </div>
  )
}

function abreviaNome(nome: string): string {
  const partes = nome.replace(/ FIDC$/i, "").split(" ")
  if (partes.length <= 2) return partes.join(" ")
  return partes.slice(0, 2).join(" ") + "..."
}

//
// §3 — Evolucao comparada (Select de indicador + LineChart).
//
function EvolucaoComparada({ data }: { data: ComparativoResponse }) {
  const rankingPorKey = React.useMemo(() => {
    const map: Record<string, RankingLinha> = {}
    for (const linha of data.ranking) map[linha.key] = linha
    return map
  }, [data.ranking])

  const opcoes = Object.keys(data.series)
    .map((k) => rankingPorKey[k])
    .filter((l): l is RankingLinha => Boolean(l))

  const [indKey, setIndKey] = React.useState<string>(opcoes[0]?.key ?? "")

  if (opcoes.length === 0) {
    return null
  }

  const linha = rankingPorKey[indKey] ?? opcoes[0]
  const pontos = data.series[linha.key] ?? []

  if (pontos.length < 3) {
    return (
      <ChartCard title="Evolucao comparada">
        <EmptyState
          icon={RiAlertLine}
          title="Historico insuficiente"
          description="Evolucao comparada exige pelo menos 3 competencias. Dados atuais cobrem um periodo menor."
        />
      </ChartCard>
    )
  }

  const chartData = pontos.map((pt) => {
    const row: Record<string, string | number> = {
      periodo: labelCompetencia(pt.competencia),
    }
    for (const f of data.fundos) {
      const v = pt.valores.find((x) => x.cnpj === f.cnpj)
      const nome = f.denom_social ?? formatCNPJ(f.cnpj)
      row[nome] = v?.valor ?? 0
    }
    row["Mediana mercado"] = pt.mediana ?? 0
    return row
  })

  const categorias = [
    ...data.fundos.map((f) => f.denom_social ?? formatCNPJ(f.cnpj)),
    "Mediana mercado",
  ]
  const cores = [
    ...data.fundos.map((f) => FUNDO_CORES[f.cor_index] ?? "slate"),
    "gray" as const,
  ]

  return (
    <ChartCard
      title="Evolucao comparada"
      actions={
        <Select value={linha.key} onValueChange={setIndKey}>
          <SelectTrigger className="w-[260px]">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {opcoes.map((o) => (
              <SelectItem key={o.key} value={o.key}>
                {o.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      }
    >
      <LineChart
        data={chartData}
        index="periodo"
        categories={categorias}
        colors={cores}
        valueFormatter={(v) => formatValor(v, linha.unidade)}
        className="h-72"
        showLegend
      />
    </ChartCard>
  )
}

//
// §4 — Perfis lado a lado: composicao por fundo (ativo, setores top, SCR).
//
function PerfisLadoALado({ data }: { data: ComparativoResponse }) {
  const cols =
    data.fundos.length >= 5
      ? "lg:grid-cols-5"
      : data.fundos.length === 4
        ? "lg:grid-cols-4"
        : data.fundos.length === 3
          ? "lg:grid-cols-3"
          : "lg:grid-cols-2"

  const composicaoPorCnpj = React.useMemo(() => {
    const map: Record<string, ComposicaoFundo> = {}
    for (const c of data.composicoes) map[c.cnpj] = c
    return map
  }, [data.composicoes])

  return (
    <ChartCard title="Perfis lado a lado">
      <div className={cx("grid grid-cols-1 gap-4 md:grid-cols-2", cols)}>
        {data.fundos.map((f) => {
          const cor = FUNDO_CORES[f.cor_index] ?? "slate"
          const classes = FUNDO_COR_CLASSES[cor]
          const comp = composicaoPorCnpj[f.cnpj]
          const ativoData = (comp?.ativo ?? []).map((a) => ({
            categoria: a.categoria,
            valor: a.valor,
          }))
          const setoresTop = (comp?.setores_top ?? []).slice(0, 5).map((s) => ({
            name: s.categoria,
            value: s.percentual ?? s.valor,
          }))
          const scrTop = (comp?.scr_devedor ?? []).slice(0, 5).map((s) => ({
            name: s.categoria,
            value: s.percentual ?? s.valor,
          }))
          const nome = f.denom_social ?? formatCNPJ(f.cnpj)
          return (
            <div
              key={f.cnpj}
              className={cx(
                "flex flex-col gap-3 rounded border p-3",
                classes.border,
              )}
            >
              <div className="flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <span
                    className={cx(
                      "inline-block size-2.5 rounded-full",
                      classes.dot,
                    )}
                  />
                  <span className="text-sm font-semibold text-gray-900 dark:text-gray-50">
                    {nome}
                  </span>
                </div>
                <span className="font-mono text-[11px] text-gray-500 dark:text-gray-400">
                  {formatCNPJ(f.cnpj)}
                </span>
                {f.classe_anbima && (
                  <Badge variant="neutral">{f.classe_anbima}</Badge>
                )}
              </div>

              <div className="flex flex-col gap-1">
                <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                  Ativo total
                </span>
                <span className="text-base font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                  {comp?.ativo_total != null
                    ? moeda.format(comp.ativo_total)
                    : "—"}
                </span>
              </div>

              {ativoData.length > 0 && (
                <div>
                  <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                    Composicao do ativo
                  </span>
                  <DonutChart
                    data={ativoData}
                    category="categoria"
                    value="valor"
                    valueFormatter={(v) => moedaCompacta.format(v)}
                    className="h-32"
                  />
                </div>
              )}

              {setoresTop.length > 0 && (
                <div>
                  <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                    Top setores
                  </span>
                  <BarList
                    data={setoresTop}
                    valueFormatter={(v) => percent1(v)}
                    sortOrder="descending"
                  />
                </div>
              )}

              {scrTop.length > 0 && (
                <div>
                  <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
                    SCR devedor (top)
                  </span>
                  <BarList
                    data={scrTop}
                    valueFormatter={(v) => percent1(v)}
                    sortOrder="none"
                  />
                </div>
              )}
            </div>
          )
        })}
      </div>
    </ChartCard>
  )
}
