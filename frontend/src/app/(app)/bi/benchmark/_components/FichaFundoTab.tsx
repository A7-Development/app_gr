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

import { useFundoCnpj } from "../_hooks/useBenchmarkUrl"
import {
  formatCNPJ,
  labelCompetencia,
  moedaCompacta,
  numero,
  percent1,
} from "./formatters"
import { ChartCard } from "./ChartCard"

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
  const query = useQuery({
    queryKey: ["bi", "benchmark", "fundo", cnpj],
    queryFn: () => biBenchmark.fundo(cnpj, 24),
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
      <KpisHeroCard ficha={ficha} />

      {/* Bloco 1 — Subclasses + Cotistas lado a lado */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <SubclassesCard ficha={ficha} />
        <CotistasSerieCard ficha={ficha} />
      </div>

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

      {/* Bloco 5 — Rent acumulada + Desempenho vs meta */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <RentAcumuladaTable ficha={ficha} />
        <DesempenhoVsMetaTable ficha={ficha} />
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
  ficha.desempenho_vs_meta.forEach((p) =>
    Object.keys(p.por_subclasse).forEach((k) => set.add(k)),
  )
  return Array.from(set).sort()
}

function lastN<T extends { competencia: string }>(items: T[], n: number): T[] {
  return items.slice(-n)
}

// ===========================================================================
// §1 — Identidade
// ===========================================================================

function IdentidadeHeader({ ficha }: { ficha: FichaFundo }) {
  const id = ficha.identificacao
  const condomLabel = id.condom ? id.condom.toLowerCase() : "n/d"

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-50">
          {id.denom_social ?? "Fundo sem denominacao"}
        </h2>
        {id.tp_fundo_classe && (
          <Badge variant="default">{id.tp_fundo_classe}</Badge>
        )}
        {id.classe && <Badge variant="neutral">{id.classe}</Badge>}
        <Badge variant="neutral">Condominio: {condomLabel}</Badge>
        <Badge variant="neutral">
          Resgate:{" "}
          {id.prazo_pagto_resgate != null ? `${id.prazo_pagto_resgate} d` : "n/a"}
        </Badge>
        <Badge variant="neutral">
          Conversao:{" "}
          {id.prazo_conversao_cota != null ? `${id.prazo_conversao_cota} d` : "n/a"}
        </Badge>
      </div>
      <dl className="flex flex-wrap gap-x-6 gap-y-1 text-xs text-gray-500 dark:text-gray-400">
        <div>
          <dt className="inline font-medium">Administrador: </dt>
          <dd className="inline">{id.admin ?? "n/d"}</dd>
        </div>
        <div>
          <dt className="inline font-medium">CNPJ admin: </dt>
          <dd className="inline font-mono">
            {id.cnpj_admin ? formatCNPJ(id.cnpj_admin) : "n/d"}
          </dd>
        </div>
        <div>
          <dt className="inline font-medium">CNPJ fundo: </dt>
          <dd className="inline font-mono">{formatCNPJ(id.cnpj)}</dd>
        </div>
        <div>
          <dt className="inline font-medium">Competencia: </dt>
          <dd className="inline">{labelCompetencia(id.competencia_atual)}</dd>
        </div>
        <div>
          <dt className="inline font-medium">Primeiro registro: </dt>
          <dd className="inline">{labelCompetencia(id.competencia_primeira)}</dd>
        </div>
      </dl>
    </div>
  )
}

// ===========================================================================
// §2 — KPIs hero
// ===========================================================================

function KpisHeroCard({ ficha }: { ficha: FichaFundo }) {
  const plAtual = ficha.pl_serie.at(-1)?.pl ?? 0
  const nroCotistas = ficha.subclasses.reduce((s, x) => s + x.nr_cotst, 0)
  const subSub = ficha.subclasses
    .filter((s) => /sub/i.test(s.classe_serie))
    .reduce((s, x) => s + x.pct_pl, 0)
  const subName =
    ficha.subclasses.find((s) => /sub/i.test(s.classe_serie))?.classe_serie ?? null
  let rent12m: number | null = null
  if (subName) {
    const last12 = ficha.rent_serie.slice(-12)
    if (last12.length > 0) {
      rent12m =
        last12.reduce(
          (acc, p) => acc * (1 + (p.por_subclasse[subName] ?? 0) / 100),
          1,
        ) * 100 -
        100
    }
  }

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <KpiTile
        label="Patrimonio liquido"
        valor={moedaCompacta.format(plAtual)}
        detalhe={labelCompetencia(ficha.identificacao.competencia_atual)}
      />
      <KpiTile
        label="Numero de cotistas"
        valor={numero.format(nroCotistas)}
        detalhe="soma das subclasses"
      />
      <KpiTile
        label="% Subordinacao"
        valor={percent1(subSub)}
        detalhe="% PL em subordinadas"
      />
      <KpiTile
        label="Rent. sub. acum. 12m"
        valor={rent12m != null ? percent1(rent12m) : "n/d"}
        detalhe="realizada (CDI pend.)"
      />
    </div>
  )
}

function KpiTile({
  label,
  valor,
  detalhe,
}: {
  label: string
  valor: string
  detalhe?: string
}) {
  return (
    <div className="flex flex-col gap-0.5 rounded border border-gray-200 p-3 dark:border-gray-800">
      <span className="text-xs font-medium text-gray-500 dark:text-gray-400">
        {label}
      </span>
      <span className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
        {valor}
      </span>
      {detalhe && (
        <span className="text-[11px] text-gray-500 dark:text-gray-400">
          {detalhe}
        </span>
      )}
    </div>
  )
}

// ===========================================================================
// §3 — Subclasses (tabela snapshot)
// ===========================================================================

function SubclassesCard({ ficha }: { ficha: FichaFundo }) {
  if (ficha.subclasses.length === 0) {
    return (
      <ChartCard title="Subclasses (snapshot)">
        {emptyNote("Nao ha subclasses reportadas pela CVM.")}
      </ChartCard>
    )
  }
  return (
    <ChartCard
      title="Subclasses (snapshot)"
      info="Cada serie/subclasse ativa com quantidade de cotas, valor da cota, PL e numero de cotistas (tab_x_1 + tab_x_2)."
    >
      <TableRoot className="text-xs">
        <Table className="text-xs">
          <TableHead>
            <TableRow>
              <TableHeaderCell>Subclasse</TableHeaderCell>
              <TableHeaderCell className="text-right">Qt cotas</TableHeaderCell>
              <TableHeaderCell className="text-right">Vl cota</TableHeaderCell>
              <TableHeaderCell className="text-right">PL</TableHeaderCell>
              <TableHeaderCell className="text-right">% PL</TableHeaderCell>
              <TableHeaderCell className="text-right">Cotist.</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {ficha.subclasses.map((s) => (
              <TableRow key={`${s.classe_serie}|${s.id_subclasse ?? ""}`}>
                <TableCell className="font-medium">{s.classe_serie}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {numero.format(s.qt_cota)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {moedaCompacta.format(s.vl_cota)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {moedaCompacta.format(s.pl)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {percent1(s.pct_pl)}
                </TableCell>
                <TableCell className="text-right tabular-nums">
                  {numero.format(s.nr_cotst)}
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
// §4 — Cotistas por serie (tabela wide)
// ===========================================================================

function CotistasSerieCard({ ficha }: { ficha: FichaFundo }) {
  const last12 = lastN(ficha.cotistas_serie, 12)
  const subs = collectSubclasses(ficha)
  if (last12.length === 0 || subs.length === 0) {
    return (
      <ChartCard title="Cotistas por serie (12m)">
        {emptyNote("Nao ha serie de cotistas publicada pela CVM.")}
      </ChartCard>
    )
  }
  const periodos = last12.map((p) => p.competencia)
  const rows: CompactSeriesRow[] = subs.map((s) => ({
    label: s,
    format: "num",
    values: toValuesByComp(last12, (p) => p.por_serie[s] ?? null),
  }))
  rows.push({
    label: "Total",
    emphasis: "total",
    format: "num",
    values: toValuesByComp(last12, (p) =>
      Object.values(p.por_serie).reduce((a, b) => a + b, 0),
    ),
  })
  return (
    <ChartCard
      title="Cotistas por serie (12m)"
      info="Evolucao do numero de cotistas por serie/subclasse (tab_x_1)."
    >
      <CompactSeriesTable
        label="Subclasse"
        periods={periodos}
        rows={rows}
        bordered={false}
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
  const last12 = lastN(ficha.carteira_serie, 12)
  if (last12.length === 0) {
    return (
      <ChartCard title="Ativo (Tabela I) — R$">
        {emptyNote("Nao ha composicao do ativo publicada pela CVM.")}
      </ChartCard>
    )
  }
  const periodos = last12.map((p) => p.competencia)
  const rows = buildCarteiraRows(last12, "brlK")
  return (
    <ChartCard
      title="Ativo (Tabela I) — R$ mil — 12 meses"
      info="Composicao do ativo do fundo conforme Tabela I do Informe Mensal FIDC (CVM). Valores em milhares de reais, sem casas decimais (formato 000.000). Linhas zeradas no periodo sao ocultadas. PDD e informativa (ja contida em I.2.a)."
    >
      <CompactSeriesTable
        label="Linha"
        periods={periodos}
        rows={rows}
        bordered={false}
      />
    </ChartCard>
  )
}

// ===========================================================================
// §5b — Ativo (Tabela I) em % PL
// ===========================================================================

function CarteiraPctPlTable({ ficha }: { ficha: FichaFundo }) {
  const last12 = lastN(ficha.carteira_serie, 12)
  if (last12.length === 0) return null
  const plByComp = new Map(ficha.pl_serie.map((p) => [p.competencia, p.pl]))
  const periodos = last12.map((p) => p.competencia)
  const rows = buildCarteiraRows(last12, "pct", plByComp)
  return (
    <ChartCard
      title="Ativo (Tabela I) — % do PL — 12 meses"
      info="Mesmas linhas da Tabela I, normalizadas pelo PL mensal (tab_iv_a_vl_pl)."
    >
      <CompactSeriesTable
        label="Linha"
        periods={periodos}
        rows={rows}
        bordered={false}
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
  const last12 = lastN(ficha.atraso_serie, 12)
  if (last12.length === 0) {
    return (
      <ChartCard title="Atraso por bucket (% PL)" className={className}>
        {emptyNote("Nao ha buckets de atraso publicados (tab_v).")}
      </ChartCard>
    )
  }
  const periodos = last12.map((p) => p.competencia)
  const rows: CompactSeriesRow[] = ATRASO_BUCKETS.map((b) => ({
    label: b.label,
    format: "pct",
    values: toValuesByComp(last12, (p) => {
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
    values: toValuesByComp(last12, (p) => p.pct_pl_total * 100),
  })
  return (
    <ChartCard
      title="Atraso por bucket (% do PL) — 12 meses"
      info="CVM nao separa bucket 0-15d da lamina Austin. Granularidade nativa aqui e 0-30d/30-60d/..."
      className={className}
    >
      <CompactSeriesTable
        label="Bucket"
        periods={periodos}
        rows={rows}
        bordered={false}
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
  const last12 = lastN(ficha.prazo_medio_serie, 12)
  if (last12.length === 0) {
    return (
      <ChartCard title="Prazo medio ponderado (dias)" className={className}>
        {emptyNote("Nao ha prazo medio reportado pela CVM.")}
      </ChartCard>
    )
  }
  return (
    <ChartCard
      title="Prazo medio ponderado (dias)"
      info="Media ponderada pelos pontos medios dos buckets a vencer (tab_v_a1..a10). Austin publica em dias uteis; aqui usamos calendario."
      className={className}
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
            {last12.map((p) => (
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
  const last = lastN(ficha.pl_subclasses_serie, 12)
  const subs = collectSubclasses(ficha)
  if (last.length === 0 || subs.length === 0) {
    return (
      <ChartCard title="PL por subclasse (12m)">
        {emptyNote("Nao ha serie de PL por subclasse publicada (tab_x_2).")}
      </ChartCard>
    )
  }
  const periodos = last.map((p) => p.competencia)
  const rows: CompactSeriesRow[] = subs.map((s) => ({
    label: s,
    format: "brl",
    values: toValuesByComp(last, (p) => p.por_subclasse[s] ?? null),
  }))
  rows.push({
    label: "Total PL",
    emphasis: "total",
    format: "brl",
    values: toValuesByComp(last, (p) =>
      Object.values(p.por_subclasse).reduce((a, b) => a + b, 0),
    ),
  })
  return (
    <ChartCard
      title="PL por subclasse (12m)"
      info="Qt cotas x Vl cota por serie (tab_x_2)."
    >
      <CompactSeriesTable
        label="Subclasse"
        periods={periodos}
        rows={rows}
        bordered={false}
      />
    </ChartCard>
  )
}

// ===========================================================================
// §9 — Rentabilidade mensal (tabela wide)
// ===========================================================================

function RentMensalTable({ ficha }: { ficha: FichaFundo }) {
  const last = lastN(ficha.rent_serie, 12)
  const subs = collectSubclasses(ficha)
  if (last.length === 0 || subs.length === 0) {
    return (
      <ChartCard title="Rentabilidade mensal (% a.m.) — 12m">
        {emptyNote("Nao ha rentabilidade mensal publicada (tab_x_3).")}
      </ChartCard>
    )
  }
  const periodos = last.map((p) => p.competencia)
  const rows: CompactSeriesRow[] = subs.map((s) => ({
    label: s,
    format: "pct",
    values: toValuesByComp(last, (p) => p.por_subclasse[s] ?? null),
  }))
  return (
    <ChartCard
      title="Rentabilidade mensal (% a.m.) — 12m"
      info="% ao mes realizado por subclasse (tab_x_3). %CDI nao computado no MVP."
    >
      <CompactSeriesTable
        label="Subclasse"
        periods={periodos}
        rows={rows}
        bordered={false}
      />
    </ChartCard>
  )
}

// ===========================================================================
// §10 — Rentabilidade acumulada
// ===========================================================================

function RentAcumuladaTable({ ficha }: { ficha: FichaFundo }) {
  const last = lastN(ficha.rent_acumulada, 12)
  const subs = collectSubclasses(ficha)
  if (last.length === 0 || subs.length === 0) {
    return (
      <ChartCard title="Rent. acumulada (%)">
        {emptyNote("Sem rentabilidade acumulada disponivel.")}
      </ChartCard>
    )
  }
  const periodos = last.map((p) => p.competencia)
  const rows: CompactSeriesRow[] = subs.map((s) => ({
    label: s,
    format: "pct",
    values: toValuesByComp(last, (p) => p.por_subclasse[s] ?? null),
  }))
  if (last.some((p) => p.cdi_acum != null)) {
    rows.push({
      label: "CDI",
      emphasis: "emphasis",
      format: "pct",
      values: toValuesByComp(last, (p) => p.cdi_acum),
    })
  }
  return (
    <ChartCard
      title="Rentabilidade acumulada (%) — 12m"
      info="Produtorio de (1 + rent_mes). CDI pendente de ingestao Bacen SGS 12."
    >
      <CompactSeriesTable
        label="Subclasse"
        periods={periodos}
        rows={rows}
        bordered={false}
      />
    </ChartCard>
  )
}

// ===========================================================================
// §11 — Desempenho vs meta
// ===========================================================================

function DesempenhoVsMetaTable({ ficha }: { ficha: FichaFundo }) {
  const last = lastN(ficha.desempenho_vs_meta, 12)
  const subs = collectSubclasses(ficha)
  if (last.length === 0) {
    return (
      <ChartCard title="Desempenho realizado (%)">
        {emptyNote("Nao ha desempenho realizado publicado (tab_x_6).")}
      </ChartCard>
    )
  }
  const periodos = last.map((p) => p.competencia)
  const rows: CompactSeriesRow[] = subs.map((s) => ({
    label: s,
    format: "pct",
    values: toValuesByComp(last, (p) => p.por_subclasse[s]?.realizado ?? null),
  }))
  if (rows.length === 0) {
    return (
      <ChartCard title="Desempenho realizado (%)">
        {emptyNote("Nao ha desempenho realizado publicado (tab_x_6).")}
      </ChartCard>
    )
  }
  return (
    <ChartCard
      title="Desempenho realizado (%) — 12m"
      info="Realizado por subclasse (tab_x_6)."
    >
      <CompactSeriesTable
        label="Subclasse"
        periods={periodos}
        rows={rows}
        bordered={false}
      />
    </ChartCard>
  )
}

// ===========================================================================
// §12 — Fluxo de cotas (captacao / resgate / amortizacao) — wide
// Duas tabelas separadas: (a) Captacao e (b) Resgate + Amortizacao + outros.
// ===========================================================================

function isCaptacao(tpOper: string): boolean {
  return /captac/i.test(tpOper)
}

function FluxoCotasTable({ ficha }: { ficha: FichaFundo }) {
  if (ficha.fluxo_cotas.length === 0) {
    return (
      <ChartCard title="Fluxo de cotas — 12m">
        {emptyNote("Nao ha captacao/resgate/amortizacao publicado (tab_x_4).")}
      </ChartCard>
    )
  }

  const compsSet = new Set<string>()
  for (const f of ficha.fluxo_cotas) compsSet.add(f.competencia)
  const periodos = Array.from(compsSet).sort().slice(-12)

  return (
    <>
      <FluxoCotasBloco
        title="Captacao de cotas por subclasse — 12m"
        info="Entrada de recursos via emissao de cotas (tab_x_4, tp_oper = captacao). Valores em R$."
        items={ficha.fluxo_cotas.filter((f) => isCaptacao(f.tp_oper))}
        periodos={periodos}
        emptyLabel="Nao ha captacao publicada no periodo."
      />
      <FluxoCotasBloco
        title="Resgate e amortizacao por subclasse — 12m"
        info="Saidas: resgate, amortizacao e demais operacoes nao classificadas como captacao (tab_x_4). Valores em R$."
        items={ficha.fluxo_cotas.filter((f) => !isCaptacao(f.tp_oper))}
        periodos={periodos}
        emptyLabel="Nao ha resgate/amortizacao publicado no periodo."
      />
    </>
  )
}

function FluxoCotasBloco({
  title,
  info,
  items,
  periodos,
  emptyLabel,
}: {
  title: string
  info: string
  items: FichaFundo["fluxo_cotas"]
  periodos: string[]
  emptyLabel: string
}) {
  if (items.length === 0) {
    return <ChartCard title={title}>{emptyNote(emptyLabel)}</ChartCard>
  }
  // Pivot: linha por tp_oper × classe_serie, colunas = competencias.
  const byKey = new Map<string, Map<string, number>>()
  for (const f of items) {
    const key = `${f.tp_oper} · ${f.classe_serie}`
    if (!byKey.has(key)) byKey.set(key, new Map())
    const m = byKey.get(key)!
    m.set(f.competencia, (m.get(f.competencia) ?? 0) + f.vl_total)
  }
  const rows: CompactSeriesRow[] = Array.from(byKey.entries())
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([label, m]) => {
      const values: Record<string, number | null> = {}
      for (const c of periodos) values[c] = m.get(c) ?? 0
      return { label, format: "brl" as const, values }
    })
  return (
    <ChartCard title={title} info={info}>
      <CompactSeriesTable
        label="Operacao · subclasse"
        periods={periodos}
        rows={rows}
        bordered={false}
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
  const last12 = lastN(ficha.liquidez_serie, 12)
  if (last12.length === 0) {
    return (
      <ChartCard title="Liquidez escalonada (R$) — 12m">
        {emptyNote("Nao ha faixas de liquidez publicadas (tab_x_5).")}
      </ChartCard>
    )
  }
  const periodos = last12.map((p) => p.competencia)
  const rows: CompactSeriesRow[] = LIQUIDEZ_KEYS.map((k) => ({
    label: k.label,
    format: "brl",
    values: toValuesByComp(
      last12,
      (p) => (p.faixas[k.key as keyof typeof p.faixas] as number) ?? 0,
    ),
  }))
  rows.push({
    label: "Total liquidez",
    emphasis: "total",
    format: "brl",
    values: toValuesByComp(last12, (p) =>
      LIQUIDEZ_KEYS.reduce(
        (acc, k) => acc + (p.faixas[k.key as keyof typeof p.faixas] ?? 0),
        0,
      ),
    ),
  })
  return (
    <ChartCard
      title="Liquidez escalonada (R$) — 12m"
      info="Caixa + recebiveis esperados por faixa de prazo (tab_x_5)."
    >
      <CompactSeriesTable
        label="Faixa"
        periods={periodos}
        rows={rows}
        bordered={false}
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
      <ChartCard title="Cedentes — snapshot">
        {emptyNote("CVM nao publicou cedentes para este fundo (tab_i2a12).")}
      </ChartCard>
    )
  }
  return (
    <ChartCard
      title="Top cedentes — snapshot"
      info="CVM so publica os 9 maiores cedentes. Sacados nao sao publicados."
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
      <ChartCard title="Setores — snapshot">
        {emptyNote("CVM nao publicou composicao setorial (tab_ii).")}
      </ChartCard>
    )
  }
  return (
    <ChartCard
      title="Composicao setorial — snapshot"
      info="Substitui parcialmente a 'natureza DC' da Austin (CVM so agrega por setor)."
    >
      <TableRoot className="text-xs">
        <Table className="text-xs">
          <TableHead>
            <TableRow>
              <TableHeaderCell>Setor</TableHeaderCell>
              <TableHeaderCell className="text-right">Valor</TableHeaderCell>
              <TableHeaderCell className="text-right">%</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {ficha.setores.map((s) => (
              <TableRow key={s.setor}>
                <TableCell>{s.setor}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {moedaCompacta.format(s.valor)}
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
      <ChartCard title="SCR A..H — snapshot">
        {emptyNote("Nao ha rating SCR publicado (tab_x).")}
      </ChartCard>
    )
  }
  return (
    <ChartCard
      title="SCR A..H — snapshot"
      info="Rating regulatorio dos devedores reportado a CVM (tab_x)."
    >
      <TableRoot className="text-xs">
        <Table className="text-xs">
          <TableHead>
            <TableRow>
              <TableHeaderCell>Rating</TableHeaderCell>
              <TableHeaderCell className="text-right">Valor</TableHeaderCell>
              <TableHeaderCell className="text-right">%</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {ficha.scr_distribuicao.map((r) => (
              <TableRow key={r.rating}>
                <TableCell className="font-medium">{r.rating}</TableCell>
                <TableCell className="text-right tabular-nums">
                  {moedaCompacta.format(r.valor)}
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
            Valor garantido
          </span>
          <span className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
            {moedaCompacta.format(g.vl_garantia)}
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
