"use client"

import { RiAlertLine, RiInformationLine, RiSearchLine } from "@remixicon/react"
import { useQuery } from "@tanstack/react-query"
import * as React from "react"

import {
  CompactSeriesTable,
  type CompactSeriesRow,
} from "@/components/app/CompactSeriesTable"
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
import { ProvenanceFooter } from "@/components/bi/ProvenanceFooter"
import {
  biBenchmark,
  type FichaFundo,
  type FundoAtrasoBuckets,
  type FundoCarteiraPonto,
} from "@/lib/api-client"
import { cx } from "@/lib/utils"

import { useBiFilters } from "@/lib/hooks/useBiFilters"

import { useFundoCnpj } from "../_hooks/useBenchmarkUrl"
import {
  formatCNPJ,
  labelCompetencia,
  milharesBRL,
  numero,
  percent1,
} from "./formatters"
import { ChartCard } from "./ChartCard"
import { FavoritoStar } from "./FavoritoStar"

//
// Helpers de mapping — converte posicional (array paralelo a `periodos`) para
// keyed (Record<competencia, number>) exigido pelo CompactSeriesTable.
//
function toValuesByComp<T extends { competencia: string }>(
  items: T[],
  pick: (item: T) => number | null | undefined,
): Record<string, number | null> {
  const out: Record<string, number | null> = {}
  for (const item of items) {
    const v = pick(item)
    out[item.competencia] = v == null ? null : v
  }
  return out
}

//
// FichaFundoTab — aba "Ficha do fundo" (L3 Benchmark).
// Layout compacto em 2 colunas inspirado em /bi/operacoes, com tabelas
// wide (meses nas colunas) no estilo da lamina Austin. Charts virao depois.
//
// Deep-link: /bi/benchmark?tab=ficha&cnpj=<digits>
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

  return <FichaContent cnpj={cnpj} />
}

function FichaContent({ cnpj }: { cnpj: string }) {
  const { filters } = useBiFilters()
  const periodoInicio = filters.periodoInicio
  const periodoFim = filters.periodoFim

  const query = useQuery({
    queryKey: ["bi", "benchmark", "fundo", cnpj, periodoInicio, periodoFim],
    queryFn: () =>
      biBenchmark.fundo(cnpj, {
        periodoInicio,
        periodoFim,
      }),
    staleTime: 5 * 60_000,
  })

  if (query.isPending) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-gray-500 dark:text-gray-400">
        Carregando ficha do fundo...
      </div>
    )
  }

  if (query.isError) {
    return (
      <EmptyState
        icon={RiAlertLine}
        title="Fundo nao encontrado"
        description={`Nenhuma ficha disponivel para o CNPJ ${formatCNPJ(cnpj)} na base CVM.`}
      />
    )
  }

  const ficha = query.data.data
  const provenance = query.data.provenance

  return (
    <div className="flex flex-col gap-4">
      <IdentidadeHeader ficha={ficha} />

      {/* Bloco 0 — Evolucao do PL (tab_iv) — primeira tabela */}
      <PlEvolucaoTable ficha={ficha} />

      {/* Bloco 0b — Recompras de DC (tab_vii.d) + %PL */}
      <RecompraTable ficha={ficha} />

      {/* Bloco 1 — Cotistas por serie — 2/3 da largura (tabela adaptativa) */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <CotistasSerieCard ficha={ficha} className="lg:col-span-2" />
      </div>

      {/* Bloco 1b — Cotistas por TIPO de investidor (tab_x_1_1) */}
      <CotistasPorTipoTable ficha={ficha} />

      {/* Bloco 2 — Ativo (Tabela I) em R$ + % do PL — TABELAS WIDE */}
      <div className="grid grid-cols-1 gap-4">
        <CarteiraReaisTable ficha={ficha} />
        <CarteiraPctPlTable ficha={ficha} />
      </div>

      {/* Bloco 3 — Atraso + Prazo medio */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-5">
        <AtrasoTable ficha={ficha} className="lg:col-span-3" />
        <PrazoMedioTable ficha={ficha} className="lg:col-span-2" />
      </div>

      {/* Bloco 4 — PL por subclasse + Rentabilidade mensal */}
      <div className="grid grid-cols-1 gap-4">
        <PlSubclassesTable ficha={ficha} />
        <RentMensalTable ficha={ficha} />
      </div>

      {/* Bloco 5 — Rent acumulada */}
      <div className="grid grid-cols-1 gap-4">
        <RentAcumuladaTable ficha={ficha} />
      </div>

      {/* Bloco 6 — Fluxo cotas + Liquidez */}
      <div className="grid grid-cols-1 gap-4">
        <FluxoCotasTable ficha={ficha} />
        <LiquidezTable ficha={ficha} />
      </div>

      {/* Bloco 7 — snapshots (cedentes + setores + SCR + garantias) 2x2 */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <CedentesSnapshot ficha={ficha} />
        <SetoresSnapshot ficha={ficha} />
        <ScrSnapshot ficha={ficha} />
        <GarantiasSnapshot ficha={ficha} />
      </div>

      <LimitacoesCard ficha={ficha} />
      <ProvenanceFooter provenance={provenance} />
    </div>
  )
}

// ===========================================================================
// Helpers de render / tipagem
// ===========================================================================

function emptyNote(texto: string) {
  return (
    <div className="flex items-center gap-2 rounded bg-gray-50 px-3 py-2 text-xs text-gray-500 dark:bg-gray-900 dark:text-gray-400">
      <RiInformationLine className="size-4" aria-hidden="true" />
      {texto}
    </div>
  )
}

function collectSubclasses(ficha: FichaFundo): string[] {
  const set = new Set<string>()
  ficha.subclasses.forEach((s) => set.add(s.classe_serie))
  ficha.rent_serie.forEach((p) =>
    Object.keys(p.por_subclasse).forEach((k) => set.add(k)),
  )
  ficha.pl_subclasses_serie.forEach((p) =>
    Object.keys(p.por_subclasse).forEach((k) => set.add(k)),
  )
  ficha.cotistas_serie.forEach((p) =>
    Object.keys(p.por_serie).forEach((k) => set.add(k)),
  )
  return Array.from(set).sort()
}

// ===========================================================================
// §1 — Identidade
// ===========================================================================

function IdentidadeHeader({ ficha }: { ficha: FichaFundo }) {
  const id = ficha.identificacao
  const condomRaw = id.condom?.toLowerCase() ?? null
  const condomVariant: "success" | "warning" | "neutral" =
    condomRaw === "aberto"
      ? "success"
      : condomRaw === "fechado"
        ? "warning"
        : "neutral"

  return (
    <div className="flex flex-col gap-2">
      {/* Linha 1 — Estrela de favorito + nome do fundo + badge de condominio */}
      <div className="flex flex-wrap items-center gap-2">
        <FavoritoStar cnpj={id.cnpj} />
        <h2 className="text-lg font-semibold leading-tight text-gray-900 dark:text-gray-50">
          {id.denom_social ?? "Fundo sem denominacao"}
        </h2>
        <Badge variant={condomVariant}>
          Condominio: {condomRaw ?? "n/d"}
        </Badge>
      </div>

      {/* Linha 2 — CNPJ fundo (abaixo do nome, bem proximo) */}
      <div className="-mt-1.5 font-mono text-xs text-gray-500 dark:text-gray-400">
        {formatCNPJ(id.cnpj)}
      </div>

      {/* Linha 3 — Administrador + CNPJ admin juntos */}
      <div className="text-xs text-gray-500 dark:text-gray-400">
        <span className="font-medium">Administrador: </span>
        <span>{id.admin ?? "n/d"}</span>
        <span className="mx-1.5 text-gray-400 dark:text-gray-600">·</span>
        <span className="font-mono">
          {id.cnpj_admin ? formatCNPJ(id.cnpj_admin) : "n/d"}
        </span>
      </div>
    </div>
  )
}

// ===========================================================================
// §1.5 — Evolucao do PL (tab_iv) — primeira tabela da ficha
// Tres linhas: PL (IV.a), PL medio 3m (IV.b), Delta m/m (%) derivado.
// ===========================================================================

function PlEvolucaoTable({ ficha }: { ficha: FichaFundo }) {
  const serie = ficha.pl_serie
  if (serie.length === 0) {
    return (
      <ChartCard title="Evolucao do PL — R$ mil" className="w-fit max-w-full">
        {emptyNote("Nao ha serie de PL publicada (tab_iv).")}
      </ChartCard>
    )
  }
  const periodos = serie.map((p) => p.competencia)
  const rows: CompactSeriesRow[] = [
    {
      label: "PL (IV.a)",
      emphasis: "emphasis",
      format: "brlK",
      values: toValuesByComp(serie, (p) => p.pl),
    },
    {
      label: "Δ m/m (%)",
      format: "pct",
      values: (() => {
        const out: Record<string, number | null> = {}
        for (let i = 0; i < serie.length; i++) {
          const cur = serie[i]
          const prev = i > 0 ? serie[i - 1] : null
          if (!prev || prev.pl <= 0) {
            out[cur.competencia] = null
          } else {
            out[cur.competencia] = ((cur.pl - prev.pl) / prev.pl) * 100
          }
        }
        return out
      })(),
    },
  ]
  return (
    <ChartCard
      title="Evolucao do PL — R$ mil"
      info="PL (tab_iv.a) + variacao mensal derivada. Valores em milhares de reais, sem casas decimais (formato 000.000). Fonte: Informe Mensal FIDC / CVM."
      className="w-fit max-w-full"
    >
      <CompactSeriesTable
        label="Indicador"
        periods={periodos}
        rows={rows}
        bordered={false}
        widthMode="adaptive"
      />
    </ChartCard>
  )
}

function RecompraTable({ ficha }: { ficha: FichaFundo }) {
  const serie = ficha.recompra_serie
  if (serie.length === 0) {
    return (
      <ChartCard title="Recompras de DC — R$ mil" className="w-fit max-w-full">
        {emptyNote("Nao ha recompras publicadas (tab_vii.d).")}
      </ChartCard>
    )
  }
  const periodos = serie.map((p) => p.competencia)
  const rows: CompactSeriesRow[] = [
    {
      label: "Valor de recompra (VII.d.2)",
      emphasis: "emphasis",
      format: "brlK",
      values: toValuesByComp(serie, (p) => p.vl_recompra),
    },
    {
      label: "% PL (VII.d.2 / IV.a)",
      format: "pct",
      values: toValuesByComp(serie, (p) => p.pct_pl),
    },
  ]
  return (
    <ChartCard
      title="Recompras de DC — R$ mil"
      info="Valor de recompra (tab_vii.d.2) e % do PL (tab_iv.a). Valores em milhares de reais, sem casas decimais (formato 000.000). Fonte: Informe Mensal FIDC / CVM."
      className="w-fit max-w-full"
    >
      <CompactSeriesTable
        label="Indicador"
        periods={periodos}
        rows={rows}
        bordered={false}
        widthMode="adaptive"
      />
    </ChartCard>
  )
}

// ===========================================================================
// §2 — Cotistas por serie (tabela wide)
// ===========================================================================

function CotistasSerieCard({
  ficha,
  className,
}: {
  ficha: FichaFundo
  className?: string
}) {
  const serie = ficha.cotistas_serie
  const subs = collectSubclasses(ficha)
  if (serie.length === 0 || subs.length === 0) {
    return (
      <ChartCard title="Cotistas por serie" className={className}>
        {emptyNote("Nao ha serie de cotistas publicada pela CVM.")}
      </ChartCard>
    )
  }
  const periodos = serie.map((p) => p.competencia)
  const rows: CompactSeriesRow[] = subs.map((s) => ({
    label: s,
    format: "num",
    values: toValuesByComp(serie, (p) => p.por_serie[s] ?? null),
  }))
  rows.push({
    label: "Total",
    emphasis: "total",
    format: "num",
    values: toValuesByComp(serie, (p) =>
      Object.values(p.por_serie).reduce((a, b) => a + b, 0),
    ),
  })
  return (
    <ChartCard
      title="Cotistas por serie"
      info="Evolucao do numero de cotistas por serie/subclasse (tab_x_1)."
      className={cx("w-fit max-w-full", className)}
    >
      <CompactSeriesTable
        label="Subclasse"
        periods={periodos}
        rows={rows}
        bordered={false}
        widthMode="adaptive"
      />
    </ChartCard>
  )
}

// ===========================================================================
// §2b — Cotistas por TIPO de investidor (tab_x_1_1)
// Quebra Senior vs Subordinada (NAO por serie). 16 tipos de investidor.
// ===========================================================================

const _COTST_TIPO_LABELS: { key: string; label: string }[] = [
  { key: "pf", label: "Pessoa fisica" },
  { key: "pj_nao_financ", label: "PJ nao-financeira" },
  { key: "pj_financ", label: "PJ financeira" },
  { key: "banco", label: "Banco comercial" },
  { key: "invnr", label: "Investidor nao-residente" },
  { key: "rpps", label: "RPPS" },
  { key: "eapc", label: "EAPC" },
  { key: "efpc", label: "EFPC" },
  { key: "fii", label: "FII" },
  { key: "cota_fidc", label: "FIC-FIDC" },
  { key: "outro_fi", label: "Outros FI" },
  { key: "clube", label: "Clube de investimento" },
  { key: "segur", label: "Seguradora" },
  { key: "corretora_distrib", label: "Corretora/distribuidora" },
  { key: "capitaliz", label: "Capitalizacao" },
  { key: "outro", label: "Outros" },
]

function CotistasPorTipoTable({ ficha }: { ficha: FichaFundo }) {
  const serie = ficha.cotistas_tipo_serie
  if (serie.length === 0) {
    return (
      <ChartCard title="Cotistas por tipo de investidor" className="w-fit max-w-full">
        {emptyNote("Nao ha serie de cotistas por tipo (tab_x_1_1).")}
      </ChartCard>
    )
  }
  const periodos = serie.map((p) => p.competencia)

  const hasAny = (bag: "senior" | "subord", key: string) =>
    serie.some((p) => (p[bag][key] ?? 0) > 0)

  const buildBloco = (bag: "senior" | "subord", header: string): CompactSeriesRow[] => {
    const tipos = _COTST_TIPO_LABELS.filter((t) => hasAny(bag, t.key))
    if (tipos.length === 0) return []
    const rows: CompactSeriesRow[] = [
      { label: header, emphasis: "header", values: {} },
    ]
    for (const t of tipos) {
      rows.push({
        label: t.label,
        format: "num",
        indent: 1,
        values: toValuesByComp(serie, (p) => p[bag][t.key] ?? 0),
      })
    }
    rows.push({
      label: "Total",
      emphasis: "subtotal",
      format: "num",
      values: toValuesByComp(serie, (p) =>
        Object.values(p[bag]).reduce((a, b) => a + b, 0),
      ),
    })
    return rows
  }

  const rows: CompactSeriesRow[] = [
    ...buildBloco("senior", "Senior"),
    ...(serie.some((p) => Object.values(p.senior).some((v) => v > 0)) &&
    serie.some((p) => Object.values(p.subord).some((v) => v > 0))
      ? ([{ separator: true }] as CompactSeriesRow[])
      : []),
    ...buildBloco("subord", "Subordinada"),
  ]

  if (rows.length === 0) {
    return (
      <ChartCard title="Cotistas por tipo de investidor" className="w-fit max-w-full">
        {emptyNote("Nao ha cotistas classificados por tipo nesse periodo.")}
      </ChartCard>
    )
  }

  return (
    <ChartCard
      title="Cotistas por tipo de investidor"
      info="Numero de cotistas por tipo (PF, PJ, banco, RPPS, etc.) quebrado em Senior vs Subordinada. Fonte: tab_x_1_1 (Informe Mensal FIDC / CVM). Linhas 100% zeradas no periodo ficam ocultas."
      className="w-fit max-w-full"
    >
      <CompactSeriesTable
        label="Tipo de investidor"
        periods={periodos}
        rows={rows}
        bordered={false}
        widthMode="adaptive"
      />
    </ChartCard>
  )
}

// ===========================================================================
// §5a — Ativo (Tabela I) em R$ — tabela wide
//
// Mapeamento 1:1 com a estrutura oficial do Informe Mensal FIDC da CVM
// (docs/cvm-fidc/dicionario.yaml, tab_i):
//   (I)   Ativo                         = disp + carteira_sub + deriv + outro_ativo
//   (I.1) Disponibilidades
//   (I.2) Carteira (subtotal)
//   (I.2.a..j) linhas detalhadas
//   (I.3) Derivativos
//   (I.4) Outros Ativos
//   (memo) PDD (aprox.)  -- informativo; ja esta deduzida em I.2.a
// ===========================================================================

type CarteiraRow =
  | { kind: "leaf"; key: keyof FundoCarteiraPonto; label: string; indent?: 0 | 1 | 2 }
  | { kind: "subtotal"; key: keyof FundoCarteiraPonto; label: string }
  | { kind: "total"; key: keyof FundoCarteiraPonto; label: string }
  | { kind: "memo"; key: keyof FundoCarteiraPonto; label: string }
  | { kind: "separator" }

const CARTEIRA_ROWS: CarteiraRow[] = [
  { kind: "leaf", key: "disp", label: "(I.1) Disponibilidades" },
  { kind: "separator" },
  { kind: "leaf", key: "dc_risco", label: "(I.2.a) Direitos Creditorios com risco", indent: 1 },
  { kind: "leaf", key: "dc_sem_risco", label: "(I.2.b) Direitos Creditorios sem risco", indent: 1 },
  { kind: "leaf", key: "vlmob", label: "(I.2.c) Valores Mobiliarios", indent: 1 },
  { kind: "leaf", key: "tit_pub", label: "(I.2.d) Titulos Publicos Federais", indent: 1 },
  { kind: "leaf", key: "cdb", label: "(I.2.e) CDB", indent: 1 },
  { kind: "leaf", key: "oper_comprom", label: "(I.2.f) Oper. Compromissadas", indent: 1 },
  { kind: "leaf", key: "outros_rf", label: "(I.2.g) Outros Renda Fixa", indent: 1 },
  { kind: "leaf", key: "cotas_fidc", label: "(I.2.h) Cotas de FIDC", indent: 1 },
  { kind: "leaf", key: "cotas_fidc_np", label: "(I.2.i) Cotas de FIDC-NP", indent: 1 },
  { kind: "leaf", key: "contrato_futuro", label: "(I.2.j) Warrants/Futuros", indent: 1 },
  { kind: "subtotal", key: "carteira_sub", label: "(I.2) Carteira" },
  { kind: "separator" },
  { kind: "leaf", key: "deriv", label: "(I.3) Posicoes em Derivativos" },
  { kind: "leaf", key: "outro_ativo", label: "(I.4) Outros Ativos" },
  { kind: "separator" },
  { kind: "total", key: "ativo_total", label: "(I) Ativo" },
  { kind: "memo", key: "pdd_aprox", label: "PDD (aprox., redutor ja contido em I.2.a)" },
]

// Linha e "zero em todo o periodo" quando todos os valores forem 0 ou null.
// PDD (memo) e o proprio Ativo total nunca sao ocultados.
function isAllZero(series: FundoCarteiraPonto[], key: keyof FundoCarteiraPonto): boolean {
  for (const p of series) {
    const v = p[key] as number | null | undefined
    if (v != null && v !== 0) return false
  }
  return true
}

function buildCarteiraRows(
  serie: FundoCarteiraPonto[],
  format: "brlK" | "pct",
  plByComp?: Map<string, number>,
): CompactSeriesRow[] {
  const out: CompactSeriesRow[] = []
  for (const r of CARTEIRA_ROWS) {
    if (r.kind === "separator") {
      // Evita 2 separadores consecutivos se a linha anterior foi ocultada.
      const last = out[out.length - 1]
      if (last && "separator" in last && last.separator) continue
      out.push({ separator: true })
      continue
    }
    // Oculta linhas zeradas em todo o periodo, exceto total e memo.
    if (
      (r.kind === "leaf" || r.kind === "subtotal") &&
      isAllZero(serie, r.key)
    ) {
      continue
    }
    const emphasis =
      r.kind === "total"
        ? "total"
        : r.kind === "subtotal"
          ? "subtotal"
          : r.kind === "memo"
            ? "emphasis"
            : undefined
    const indent = r.kind === "leaf" ? r.indent ?? 0 : 0
    const values = toValuesByComp(serie, (p) => {
      const v = (p[r.key] as number) ?? 0
      if (format === "brlK") return v
      const pl = plByComp?.get(p.competencia) ?? 0
      if (pl <= 0) return null
      return (v / pl) * 100
    })
    out.push({ label: r.label, format, indent, emphasis, values })
  }
  // Drop trailing separator, se sobrou.
  const last = out[out.length - 1]
  if (last && "separator" in last && last.separator) out.pop()
  return out
}

function CarteiraReaisTable({ ficha }: { ficha: FichaFundo }) {
  const serie = ficha.carteira_serie
  if (serie.length === 0) {
    return (
      <ChartCard title="Ativo (Tabela I) — R$ mil" className="w-fit max-w-full">
        {emptyNote("Nao ha composicao do ativo publicada pela CVM.")}
      </ChartCard>
    )
  }
  const periodos = serie.map((p) => p.competencia)
  const rows = buildCarteiraRows(serie, "brlK")
  return (
    <ChartCard
      title="Ativo (Tabela I) — R$ mil"
      info="Composicao do ativo do fundo conforme Tabela I do Informe Mensal FIDC (CVM). Valores em milhares de reais, sem casas decimais (formato 000.000). Linhas zeradas no periodo sao ocultadas. PDD e informativa (ja contida em I.2.a)."
      className="w-fit max-w-full"
    >
      <CompactSeriesTable
        label="Linha"
        periods={periodos}
        rows={rows}
        bordered={false}
        widthMode="adaptive"
      />
    </ChartCard>
  )
}

// ===========================================================================
// §5b — Ativo (Tabela I) em % PL
// ===========================================================================

function CarteiraPctPlTable({ ficha }: { ficha: FichaFundo }) {
  const serie = ficha.carteira_serie
  if (serie.length === 0) return null
  const plByComp = new Map(ficha.pl_serie.map((p) => [p.competencia, p.pl]))
  const periodos = serie.map((p) => p.competencia)
  const rows = buildCarteiraRows(serie, "pct", plByComp)
  return (
    <ChartCard
      title="Ativo (Tabela I) — % do PL"
      info="Mesmas linhas da Tabela I, normalizadas pelo PL mensal (tab_iv_a_vl_pl)."
      className="w-fit max-w-full"
    >
      <CompactSeriesTable
        label="Linha"
        periods={periodos}
        rows={rows}
        bordered={false}
        widthMode="adaptive"
      />
    </ChartCard>
  )
}

// ===========================================================================
// §6 — Atraso por bucket (tabela wide)
// ===========================================================================

const ATRASO_BUCKETS: { key: keyof FundoAtrasoBuckets; label: string }[] = [
  { key: "b0_30", label: "0-30d" },
  { key: "b30_60", label: "30-60d" },
  { key: "b60_90", label: "60-90d" },
  { key: "b90_120", label: "90-120d" },
  { key: "b120_150", label: "120-150d" },
  { key: "b150_180", label: "150-180d" },
  { key: "b180_360", label: "180-360d" },
  { key: "b360_720", label: "360-720d" },
  { key: "b720_1080", label: "720-1080d" },
  { key: "b1080_plus", label: ">1080d" },
]

function AtrasoTable({
  ficha,
  className,
}: {
  ficha: FichaFundo
  className?: string
}) {
  const serie = ficha.atraso_serie
  if (serie.length === 0) {
    return (
      <ChartCard
        title="Atraso por bucket (% PL)"
        className={cx("w-fit max-w-full", className)}
      >
        {emptyNote("Nao ha buckets de atraso publicados (tab_v).")}
      </ChartCard>
    )
  }
  const periodos = serie.map((p) => p.competencia)
  const rows: CompactSeriesRow[] = ATRASO_BUCKETS.map((b) => ({
    label: b.label,
    format: "pct",
    values: toValuesByComp(serie, (p) => {
      const pl = ficha.pl_serie.find((x) => x.competencia === p.competencia)?.pl
      const v = p.buckets[b.key] ?? 0
      if (!pl || pl <= 0) return null
      return (v / pl) * 100
    }),
  }))
  rows.push({
    label: "Total vencidos",
    emphasis: "total",
    format: "pct",
    values: toValuesByComp(serie, (p) => p.pct_pl_total * 100),
  })
  return (
    <ChartCard
      title="Atraso por bucket (% do PL)"
      info="CVM nao separa bucket 0-15d da lamina Austin. Granularidade nativa aqui e 0-30d/30-60d/..."
      className={cx("w-fit max-w-full", className)}
    >
      <CompactSeriesTable
        label="Bucket"
        periods={periodos}
        rows={rows}
        bordered={false}
        widthMode="adaptive"
      />
    </ChartCard>
  )
}

// ===========================================================================
// §7 — Prazo medio (tabela compacta 12m)
// ===========================================================================

function PrazoMedioTable({
  ficha,
  className,
}: {
  ficha: FichaFundo
  className?: string
}) {
  const serie = ficha.prazo_medio_serie
  if (serie.length === 0) {
    return (
      <ChartCard
        title="Prazo medio ponderado (dias)"
        className={cx("w-fit max-w-full", className)}
      >
        {emptyNote("Nao ha prazo medio reportado pela CVM.")}
      </ChartCard>
    )
  }
  return (
    <ChartCard
      title="Prazo medio ponderado (dias)"
      info="Media ponderada pelos pontos medios dos buckets a vencer (tab_v_a1..a10). Austin publica em dias uteis; aqui usamos calendario."
      className={cx("w-fit max-w-full", className)}
    >
      <TableRoot className="text-xs">
        <Table className="text-xs">
          <TableHead>
            <TableRow>
              <TableHeaderCell>Competencia</TableHeaderCell>
              <TableHeaderCell className="text-right">Dias (aprox.)</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {serie.map((p) => (
              <TableRow key={p.competencia}>
                <TableCell>{labelCompetencia(p.competencia)}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {numero.format(Math.round(p.dias_aprox))} d
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableRoot>
    </ChartCard>
  )
}

// ===========================================================================
// §8 — PL por subclasse (tabela wide 24m)
// ===========================================================================

function PlSubclassesTable({ ficha }: { ficha: FichaFundo }) {
  const serie = ficha.pl_subclasses_serie
  const subs = collectSubclasses(ficha)
  if (serie.length === 0 || subs.length === 0) {
    return (
      <ChartCard title="PL por subclasse — R$ mil" className="w-fit max-w-full">
        {emptyNote("Nao ha serie de PL por subclasse publicada (tab_x_2).")}
      </ChartCard>
    )
  }
  const periodos = serie.map((p) => p.competencia)
  const rows: CompactSeriesRow[] = subs.map((s) => ({
    label: s,
    format: "brlK",
    values: toValuesByComp(serie, (p) => p.por_subclasse[s] ?? null),
  }))
  rows.push({
    label: "Total PL",
    emphasis: "total",
    format: "brlK",
    values: toValuesByComp(serie, (p) =>
      Object.values(p.por_subclasse).reduce((a, b) => a + b, 0),
    ),
  })
  return (
    <ChartCard
      title="PL por subclasse — R$ mil"
      info="Qt cotas x Vl cota por serie (tab_x_2). Valores em milhares de reais, sem casas decimais (formato 000.000)."
      className="w-fit max-w-full"
    >
      <CompactSeriesTable
        label="Subclasse"
        periods={periodos}
        rows={rows}
        bordered={false}
        widthMode="adaptive"
      />
    </ChartCard>
  )
}

// ===========================================================================
// §9 — Rentabilidade mensal (tabela wide)
// ===========================================================================

function RentMensalTable({ ficha }: { ficha: FichaFundo }) {
  const serie = ficha.rent_serie
  const subs = collectSubclasses(ficha)
  if (serie.length === 0 || subs.length === 0) {
    return (
      <ChartCard
        title="Rentabilidade mensal (% a.m.)"
        className="w-fit max-w-full"
      >
        {emptyNote("Nao ha rentabilidade mensal publicada (tab_x_3).")}
      </ChartCard>
    )
  }
  const periodos = serie.map((p) => p.competencia)
  const rows: CompactSeriesRow[] = subs.map((s) => ({
    label: s,
    format: "pct",
    values: toValuesByComp(serie, (p) => p.por_subclasse[s] ?? null),
  }))
  return (
    <ChartCard
      title="Rentabilidade mensal (% a.m.)"
      info="% ao mes realizado por subclasse (tab_x_3). %CDI nao computado no MVP."
      className="w-fit max-w-full"
    >
      <CompactSeriesTable
        label="Subclasse"
        periods={periodos}
        rows={rows}
        bordered={false}
        widthMode="adaptive"
      />
    </ChartCard>
  )
}

// ===========================================================================
// §10 — Rentabilidade acumulada
// ===========================================================================

function RentAcumuladaTable({ ficha }: { ficha: FichaFundo }) {
  const serie = ficha.rent_acumulada
  const subs = collectSubclasses(ficha)
  if (serie.length === 0 || subs.length === 0) {
    return (
      <ChartCard title="Rent. acumulada (%)" className="w-fit max-w-full">
        {emptyNote("Sem rentabilidade acumulada disponivel.")}
      </ChartCard>
    )
  }
  const periodos = serie.map((p) => p.competencia)
  const rows: CompactSeriesRow[] = subs.map((s) => ({
    label: s,
    format: "pct",
    values: toValuesByComp(serie, (p) => p.por_subclasse[s] ?? null),
  }))
  if (serie.some((p) => p.cdi_acum != null)) {
    rows.push({
      label: "CDI",
      emphasis: "emphasis",
      format: "pct",
      values: toValuesByComp(serie, (p) => p.cdi_acum),
    })
  }
  return (
    <ChartCard
      title="Rentabilidade acumulada (%)"
      info="Produtorio de (1 + rent_mes). CDI pendente de ingestao Bacen SGS 12."
      className="w-fit max-w-full"
    >
      <CompactSeriesTable
        label="Subclasse"
        periods={periodos}
        rows={rows}
        bordered={false}
        widthMode="adaptive"
      />
    </ChartCard>
  )
}

// ===========================================================================
// §12 — Fluxo de cotas (captacao / resgate / amortizacao) — wide
// Tabela unica com dois grupos: (a) Captacao (positivo) e (b) Resgate/
// Amortizacao (negativo). Cada grupo tem subtotal e ha uma linha de
// resultado liquido ao final.
// ===========================================================================

function isCaptacao(tpOper: string): boolean {
  return /capta[cç]/i.test(tpOper)
}

function FluxoCotasTable({ ficha }: { ficha: FichaFundo }) {
  if (ficha.fluxo_cotas.length === 0) {
    return (
      <ChartCard title="Fluxo de cotas" className="w-fit max-w-full">
        {emptyNote("Nao ha captacao/resgate/amortizacao publicado (tab_x_4).")}
      </ChartCard>
    )
  }

  const compsSet = new Set<string>()
  for (const f of ficha.fluxo_cotas) compsSet.add(f.competencia)
  const periodos = Array.from(compsSet).sort()

  // Pivot por tp_oper · classe_serie para cada grupo.
  const pivot = (items: FichaFundo["fluxo_cotas"], signal: 1 | -1) => {
    const byKey = new Map<string, Map<string, number>>()
    for (const f of items) {
      const key = `${f.tp_oper} · ${f.classe_serie}`
      if (!byKey.has(key)) byKey.set(key, new Map())
      const m = byKey.get(key)!
      m.set(f.competencia, (m.get(f.competencia) ?? 0) + signal * f.vl_total)
    }
    return Array.from(byKey.entries()).sort(([a], [b]) => a.localeCompare(b))
  }

  const captItems = ficha.fluxo_cotas.filter((f) => isCaptacao(f.tp_oper))
  const saidaItems = ficha.fluxo_cotas.filter((f) => !isCaptacao(f.tp_oper))
  const captRows = pivot(captItems, 1)
  const saidaRows = pivot(saidaItems, -1)

  const sumByComp = (
    entries: [string, Map<string, number>][],
  ): Record<string, number | null> => {
    const out: Record<string, number | null> = {}
    for (const c of periodos) {
      let total = 0
      for (const [, m] of entries) total += m.get(c) ?? 0
      out[c] = total
    }
    return out
  }

  const subtotalCapt = sumByComp(captRows)
  const subtotalSaida = sumByComp(saidaRows)
  const liquido: Record<string, number | null> = {}
  for (const c of periodos) {
    liquido[c] = (subtotalCapt[c] ?? 0) + (subtotalSaida[c] ?? 0)
  }

  const rowsFromEntries = (
    entries: [string, Map<string, number>][],
  ): CompactSeriesRow[] =>
    entries.map(([label, m]) => {
      const values: Record<string, number | null> = {}
      for (const c of periodos) values[c] = m.get(c) ?? 0
      return {
        label,
        format: "brlK" as const,
        values,
        indent: 1,
      }
    })

  const rows: CompactSeriesRow[] = []

  // Grupo 1 — Captacao
  rows.push({ label: "Captacao", emphasis: "header", values: {} })
  if (captRows.length === 0) {
    rows.push({
      label: "Sem captacao publicada",
      format: "brlK",
      values: {},
      indent: 1,
    })
  } else {
    rows.push(...rowsFromEntries(captRows))
  }
  rows.push({
    label: "Subtotal captacao",
    emphasis: "subtotal",
    format: "brlK",
    values: subtotalCapt,
  })

  rows.push({ separator: true })

  // Grupo 2 — Amortizacao e Resgates (valores negativos)
  rows.push({
    label: "Amortizacao e resgates",
    emphasis: "header",
    values: {},
  })
  if (saidaRows.length === 0) {
    rows.push({
      label: "Sem resgate/amortizacao publicado",
      format: "brlK",
      values: {},
      indent: 1,
    })
  } else {
    rows.push(...rowsFromEntries(saidaRows))
  }
  rows.push({
    label: "Subtotal amortizacao e resgates",
    emphasis: "subtotal",
    format: "brlK",
    values: subtotalSaida,
  })

  rows.push({ separator: true })

  // Totalizador
  rows.push({
    label: "Resultado liquido",
    emphasis: "total",
    format: "brlK",
    values: liquido,
  })

  return (
    <ChartCard
      title="Fluxo de cotas por subclasse — R$ mil"
      info="Captacao (entrada, positivo) e amortizacao/resgate (saida, negativo) de cotas publicados em tab_x_4. Resultado liquido = captacao + saidas. Valores em milhares de reais, sem casas decimais (formato 000.000)."
      className="w-fit max-w-full"
    >
      <CompactSeriesTable
        label="Operacao · subclasse"
        periods={periodos}
        rows={rows}
        bordered={false}
        widthMode="adaptive"
      />
    </ChartCard>
  )
}

// ===========================================================================
// §13 — Liquidez escalonada (tabela wide)
// ===========================================================================

const LIQUIDEZ_KEYS = [
  { key: "d0", label: "0 dias" },
  { key: "d30", label: "30 dias" },
  { key: "d60", label: "60 dias" },
  { key: "d90", label: "90 dias" },
  { key: "d180", label: "180 dias" },
  { key: "d360", label: "360 dias" },
  { key: "mais_360", label: ">360 dias" },
] as const

function LiquidezTable({ ficha }: { ficha: FichaFundo }) {
  const serie = ficha.liquidez_serie
  if (serie.length === 0) {
    return (
      <ChartCard title="Liquidez escalonada — R$ mil" className="w-fit max-w-full">
        {emptyNote("Nao ha faixas de liquidez publicadas (tab_x_5).")}
      </ChartCard>
    )
  }
  const periodos = serie.map((p) => p.competencia)
  const rows: CompactSeriesRow[] = LIQUIDEZ_KEYS.map((k) => ({
    label: k.label,
    format: "brlK",
    values: toValuesByComp(
      serie,
      (p) => (p.faixas[k.key as keyof typeof p.faixas] as number) ?? 0,
    ),
  }))
  rows.push({
    label: "Total liquidez",
    emphasis: "total",
    format: "brlK",
    values: toValuesByComp(serie, (p) =>
      LIQUIDEZ_KEYS.reduce(
        (acc, k) => acc + (p.faixas[k.key as keyof typeof p.faixas] ?? 0),
        0,
      ),
    ),
  })
  return (
    <ChartCard
      title="Liquidez escalonada — R$ mil"
      info="Caixa + recebiveis esperados por faixa de prazo (tab_x_5). Valores em milhares de reais, sem casas decimais (formato 000.000)."
      className="w-fit max-w-full"
    >
      <CompactSeriesTable
        label="Faixa"
        periods={periodos}
        rows={rows}
        bordered={false}
        widthMode="adaptive"
      />
    </ChartCard>
  )
}

// ===========================================================================
// §14 — Cedentes (snapshot compacto)
// ===========================================================================

function CedentesSnapshot({ ficha }: { ficha: FichaFundo }) {
  if (ficha.cedentes.length === 0) {
    return (
      <ChartCard title="Cedentes — snapshot" className="w-fit max-w-full">
        {emptyNote("CVM nao publicou cedentes para este fundo (tab_i2a12).")}
      </ChartCard>
    )
  }
  return (
    <ChartCard
      title="Top cedentes — snapshot"
      info="CVM so publica os 9 maiores cedentes. Sacados nao sao publicados."
      className="w-fit max-w-full"
    >
      <TableRoot className="text-xs">
        <Table className="text-xs">
          <TableHead>
            <TableRow>
              <TableHeaderCell>#</TableHeaderCell>
              <TableHeaderCell>CPF/CNPJ</TableHeaderCell>
              <TableHeaderCell className="text-right">% carteira</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {ficha.cedentes.map((c) => (
              <TableRow key={c.rank}>
                <TableCell className="tabular-nums">{c.rank}</TableCell>
                <TableCell className="font-mono">
                  {c.cpf_cnpj ? formatCNPJ(c.cpf_cnpj) : "n/d"}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {percent1(c.pct)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableRoot>
    </ChartCard>
  )
}

// ===========================================================================
// §15 — Setores (snapshot compacto)
// ===========================================================================

function SetoresSnapshot({ ficha }: { ficha: FichaFundo }) {
  if (ficha.setores.length === 0) {
    return (
      <ChartCard title="Setores — snapshot" className="w-fit max-w-full">
        {emptyNote("CVM nao publicou composicao setorial (tab_ii).")}
      </ChartCard>
    )
  }
  return (
    <ChartCard
      title="Composicao setorial — snapshot"
      info="Substitui parcialmente a 'natureza DC' da Austin (CVM so agrega por setor)."
      className="w-fit max-w-full"
    >
      <TableRoot className="text-xs">
        <Table className="text-xs">
          <TableHead>
            <TableRow>
              <TableHeaderCell>Setor</TableHeaderCell>
              <TableHeaderCell className="text-right">Valor (R$ mil)</TableHeaderCell>
              <TableHeaderCell className="text-right">%</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {ficha.setores.map((s) => (
              <TableRow key={s.setor}>
                <TableCell>{s.setor}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {milharesBRL(s.valor)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {percent1(s.pct)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableRoot>
    </ChartCard>
  )
}

// ===========================================================================
// §16 — SCR (snapshot compacto)
// ===========================================================================

function ScrSnapshot({ ficha }: { ficha: FichaFundo }) {
  if (ficha.scr_distribuicao.length === 0) {
    return (
      <ChartCard title="SCR A..H — snapshot" className="w-fit max-w-full">
        {emptyNote("Nao ha rating SCR publicado (tab_x).")}
      </ChartCard>
    )
  }
  return (
    <ChartCard
      title="SCR A..H — snapshot"
      info="Rating regulatorio dos devedores reportado a CVM (tab_x)."
      className="w-fit max-w-full"
    >
      <TableRoot className="text-xs">
        <Table className="text-xs">
          <TableHead>
            <TableRow>
              <TableHeaderCell>Rating</TableHeaderCell>
              <TableHeaderCell className="text-right">Valor (R$ mil)</TableHeaderCell>
              <TableHeaderCell className="text-right">%</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {ficha.scr_distribuicao.map((r) => (
              <TableRow key={r.rating}>
                <TableCell className="font-medium">{r.rating}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {milharesBRL(r.valor)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {percent1(r.pct)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableRoot>
    </ChartCard>
  )
}

// ===========================================================================
// §17 — Garantias (snapshot compacto)
// ===========================================================================

function GarantiasSnapshot({ ficha }: { ficha: FichaFundo }) {
  const g = ficha.garantias
  if (!g) {
    return (
      <ChartCard title="Garantias — snapshot">
        {emptyNote("Nao ha garantias publicadas (tab_x_7).")}
      </ChartCard>
    )
  }
  return (
    <ChartCard title="Garantias vinculadas a DC — snapshot">
      <div className="grid grid-cols-2 gap-3">
        <div className="flex flex-col gap-0.5 rounded bg-gray-50 p-3 dark:bg-gray-900">
          <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
            Valor garantido (R$ mil)
          </span>
          <span className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
            {milharesBRL(g.vl_garantia)}
          </span>
        </div>
        <div className="flex flex-col gap-0.5 rounded bg-gray-50 p-3 dark:bg-gray-900">
          <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
            % DC com garantia
          </span>
          <span className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
            {percent1(g.pct_garantia)}
          </span>
        </div>
      </div>
    </ChartCard>
  )
}

// ===========================================================================
// §18 — Limitacoes
// ===========================================================================

function LimitacoesCard({ ficha }: { ficha: FichaFundo }) {
  if (ficha.limitacoes.length === 0) return null
  return (
    <ChartCard
      title="Limitacoes desta ficha"
      info="O que nao e reproduzivel a partir dos dados publicos da CVM."
    >
      <ul className="flex flex-col gap-1.5 text-xs text-gray-600 dark:text-gray-400">
        {ficha.limitacoes.map((l, i) => (
          <li key={i} className="flex items-start gap-2">
            <RiAlertLine
              className="mt-0.5 size-3.5 shrink-0 text-gray-400"
              aria-hidden="true"
            />
            <span>{l}</span>
          </li>
        ))}
      </ul>
    </ChartCard>
  )
}
