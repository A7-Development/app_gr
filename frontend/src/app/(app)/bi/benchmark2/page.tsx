"use client"

// /bi/benchmark2 — Listagem dos FIDCs CVM + entry point pra Ficha Lamina.
//
// Estrutura (CLAUDE.md sec 11.6 hierarquia 3 niveis):
//   L3 = TabNavigation com 4 abas. Aba "Fundos" tem a tabela <DataTableShell>
//   com a lista completa de fundos CVM (PL + cotistas via cvm_remote.*).
//   Clicar numa linha navega pra /bi/benchmark2/[cnpj] (Ficha Lamina).
//
// Padroes aplicados:
//   - PageHeader com info + actions canonicos.
//   - KpiStrip 4 KPIs derivados da lista de fundos.
//   - <DataTableShell> + tableTokens.* nas cells (decisao 2026-04-30).

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { Button } from "@/components/tremor/Button"
import {
  TabNavigation,
  TabNavigationLink,
} from "@/components/tremor/TabNavigation"
import {
  DataTableShell,
  KpiCard,
  KpiStrip,
  PageHeader,
} from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type { Benchmark2FundoRow } from "@/lib/api-client"
import { cx } from "@/lib/utils"

import { useBenchmark2Fundos } from "./_components/useBenchmark2"

// ───────────────────────────────────────────────────────────────────────────
// Tabs L3
// ───────────────────────────────────────────────────────────────────────────

const TABS = [
  { key: "fundos",        label: "Fundos" },
  { key: "concentracao",  label: "Concentracao" },
  { key: "distribuicao",  label: "Distribuicao" },
  { key: "cotistas",      label: "Cotistas" },
] as const

type TabKey = (typeof TABS)[number]["key"]

function useActiveTab(): TabKey {
  const sp = useSearchParams()
  const t = sp.get("tab")
  if (t && TABS.some((x) => x.key === t)) return t as TabKey
  return "fundos"
}

// ───────────────────────────────────────────────────────────────────────────
// Formatters
// ───────────────────────────────────────────────────────────────────────────

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
})
const fmtBRLCompact = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  notation: "compact",
  maximumFractionDigits: 1,
})
const fmtInt = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 })

function fmtCompetencia(yyyymm: string): string {
  if (!yyyymm) return "—"
  const [y, m] = yyyymm.split("-")
  if (!y || !m) return yyyymm
  return new Date(Number(y), Number(m) - 1, 1).toLocaleString("pt-BR", {
    month: "short",
    year: "numeric",
  })
}

// ───────────────────────────────────────────────────────────────────────────
// Cells custom (badges) — usam tableTokens
// ───────────────────────────────────────────────────────────────────────────

function CondomBadge({ value }: { value: Benchmark2FundoRow["condom"] }) {
  if (!value) return <span className={tableTokens.cellMuted}>—</span>
  if (value === "aberto") {
    return (
      <span
        className={cx(
          tableTokens.badge,
          "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300",
        )}
      >
        Aberto
      </span>
    )
  }
  return (
    <span
      className={cx(
        tableTokens.badge,
        "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
      )}
    >
      Fechado
    </span>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

const PAGE_INFO =
  "Lista completa de FIDCs registrados na CVM (dados publicos via postgres_fdw, schema cvm_remote). Usa o pattern <DataTableShell> + tableTokens — referencia para futuras listagens."

const col = createColumnHelper<Benchmark2FundoRow>()

export default function Benchmark2Page() {
  const activeTab = useActiveTab()
  const sp = useSearchParams()
  const router = useRouter()

  const fundosQuery = useBenchmark2Fundos()
  const data = fundosQuery.data?.fundos ?? []
  const competencia = fundosQuery.data?.competencia ?? ""

  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState<"todos" | "abertos" | "fechados">(
    "todos",
  )

  // ── KPIs derivados ──────────────────────────────────────────────────────
  const kpis = React.useMemo(() => {
    const totalFundos = data.length
    const plTotal = data.reduce((s, r) => s + (r.pl_ult_mes ?? 0), 0)
    const cotistasTotal = data.reduce((s, r) => s + (r.cotistas ?? 0), 0)
    const ticketMedio = totalFundos > 0 ? plTotal / totalFundos : 0
    return { totalFundos, plTotal, cotistasTotal, ticketMedio }
  }, [data])

  // ── Columns ─────────────────────────────────────────────────────────────
  const columns = React.useMemo<ColumnDef<Benchmark2FundoRow, unknown>[]>(
    () => [
      col.accessor("fundo", {
        header: "Fundo",
        size: 380,
        cell: (info) => (
          <span
            className={cx(tableTokens.cellText, "block max-w-full truncate")}
            title={info.getValue()}
          >
            {info.getValue()}
          </span>
        ),
      }) as ColumnDef<Benchmark2FundoRow, unknown>,

      col.accessor("cnpj", {
        header: "CNPJ",
        size: 160,
        cell: (info) => (
          <span className={tableTokens.cellTextMono}>{info.getValue()}</span>
        ),
      }) as ColumnDef<Benchmark2FundoRow, unknown>,

      col.accessor("condom", {
        header: "Condominio",
        size: 110,
        cell: (info) => <CondomBadge value={info.getValue()} />,
      }) as ColumnDef<Benchmark2FundoRow, unknown>,

      col.accessor("cotistas", {
        header: "Cotistas",
        meta: { align: "right" },
        size: 100,
        cell: (info) => {
          const v = info.getValue()
          if (v == null) return <span className={tableTokens.cellMuted}>—</span>
          return (
            <span className={cx(tableTokens.cellNumber, "block text-right")}>
              {fmtInt.format(v)}
            </span>
          )
        },
      }) as ColumnDef<Benchmark2FundoRow, unknown>,

      col.accessor("pl_medio_3m", {
        header: "PL medio 3M",
        meta: { align: "right" },
        size: 160,
        cell: (info) => {
          const v = info.getValue()
          if (v == null) return <span className={tableTokens.cellMuted}>—</span>
          return (
            <span className={cx(tableTokens.cellNumber, "block text-right")}>
              {fmtBRL.format(v)}
            </span>
          )
        },
      }) as ColumnDef<Benchmark2FundoRow, unknown>,

      col.accessor("pl_ult_mes", {
        header: `PL ${competencia ? fmtCompetencia(competencia) : "ult."}`,
        meta: { align: "right" },
        size: 170,
        cell: (info) => {
          const v = info.getValue()
          if (v == null) return <span className={tableTokens.cellMuted}>—</span>
          return (
            <span className={cx(tableTokens.cellNumber, "block text-right font-medium")}>
              {fmtBRL.format(v)}
            </span>
          )
        },
      }) as ColumnDef<Benchmark2FundoRow, unknown>,
    ],
    [competencia],
  )

  // ── Tab href builder (preserva outros params) ───────────────────────────
  const buildTabHref = (tab: TabKey) => {
    const next = new URLSearchParams(sp.toString())
    next.set("tab", tab)
    return `?${next.toString()}`
  }

  return (
    <div className="flex flex-col gap-4 px-6 pt-5 pb-6">
      {/* Z1 — PageHeader */}
      <PageHeader
        title="Benchmark2"
        info={PAGE_INFO}
        subtitle={
          competencia
            ? `Competencia ${fmtCompetencia(competencia)} · Fonte: CVM (publico)`
            : "Fonte: CVM (publico)"
        }
        actions={
          <Button variant="secondary" disabled>
            Exportar
          </Button>
        }
      />

      {/* Z2 — TabNavigation L3 */}
      <TabNavigation>
        {TABS.map((t) => (
          <TabNavigationLink
            key={t.key}
            href={buildTabHref(t.key)}
            active={activeTab === t.key}
          >
            {t.label}
          </TabNavigationLink>
        ))}
      </TabNavigation>

      {/* Z4 — KPIs (sempre visiveis em todas as abas) */}
      <KpiStrip cols={4}>
        <KpiCard
          label="Fundos"
          value={fmtInt.format(kpis.totalFundos)}
          sub="FIDCs"
          source="CVM (publico)"
          updatedAtISO={competencia ? `${competencia}-01` : undefined}
        />
        <KpiCard
          label="PL total mercado"
          value={fmtBRLCompact.format(kpis.plTotal)}
          source="CVM (publico)"
          updatedAtISO={competencia ? `${competencia}-01` : undefined}
        />
        <KpiCard
          label="Cotistas"
          value={fmtInt.format(kpis.cotistasTotal)}
          source="CVM (publico)"
          updatedAtISO={competencia ? `${competencia}-01` : undefined}
        />
        <KpiCard
          label="Ticket medio (PL/fundo)"
          value={fmtBRLCompact.format(kpis.ticketMedio)}
          source="CVM (publico)"
          updatedAtISO={competencia ? `${competencia}-01` : undefined}
        />
      </KpiStrip>

      {/* Z5 — conteudo da aba */}
      {activeTab === "fundos" && (
        <DataTableShell<Benchmark2FundoRow>
          data={data}
          columns={columns}
          loading={fundosQuery.isLoading}
          error={fundosQuery.error as Error | null}
          onRetry={() => fundosQuery.refetch()}
          search={{
            value: search,
            onChange: setSearch,
            placeholder: "Buscar por nome do fundo ou CNPJ...",
          }}
          segments={{
            value: segment,
            onChange: (v) => setSegment(v as typeof segment),
            options: [
              { value: "todos",    label: "Todos",    filter: () => true },
              { value: "abertos",  label: "Abertos",  filter: (r) => r.condom === "aberto" },
              { value: "fechados", label: "Fechados", filter: (r) => r.condom === "fechado" },
            ],
          }}
          itemNoun={{ singular: "fundo", plural: "fundos" }}
          onRowClick={(row) => {
            const digits = row.cnpj.replace(/\D/g, "")
            router.push(`/bi/benchmark2/${digits}`)
          }}
        />
      )}
      {activeTab !== "fundos" && (
        <PlaceholderTab label={TABS.find((t) => t.key === activeTab)?.label ?? ""} />
      )}
    </div>
  )
}

function PlaceholderTab({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 rounded border border-dashed border-gray-200 py-16 text-center dark:border-gray-800">
      <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
        {label}
      </p>
      <p className="text-xs text-gray-500 dark:text-gray-400">
        Aba placeholder — adicione conteudo aqui quando for o caso.
      </p>
    </div>
  )
}
