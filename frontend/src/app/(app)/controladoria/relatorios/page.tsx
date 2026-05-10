// src/app/(app)/controladoria/relatorios/page.tsx
//
// Catalogo unico de relatorios das administradoras (QiTech, ...).
// Pattern tabular canonico: <DataTableShell> (mesma familia de
// /admin/ia/providers, /credito/agentes). Density compact por padrao.
//
// L1 Controladoria > L2 Relatorios > L3 [Padronizados | Espelho da Administradora]
//
// Decisao 2026-05-09: ambas as tabs leem o MESMO catalogo (Opcao A —
// lente operacional). Diferenca entre tabs e visual:
//   - Padronizados: foco em entidade canonica.
//   - Espelho: foco na administradora (frescor + reprocessar + logs vem na Phase 4).
//
// Plano: ~/.claude/plans/shimmering-snuggling-snail.md.

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { useQuery } from "@tanstack/react-query"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import { RiArrowRightSLine, RiFileChart2Line } from "@remixicon/react"

import {
  TabNavigation,
  TabNavigationLink,
} from "@/components/tremor/TabNavigation"
import {
  DataTableShell,
  PageHeader,
} from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import {
  REPORT_CATEGORY_AVATAR_COLORS,
  REPORT_CATEGORY_LABEL,
  type ReportCategoryId,
} from "@/design-system/tokens/report-category"
import { cx } from "@/lib/utils"

import { relatorios, type ReportCard, type ReportRefreshKind } from "./_lib/api"

type TabKey = "padronizados" | "espelho"

const TABS: { key: TabKey; label: string }[] = [
  { key: "padronizados", label: "Padronizados" },
  { key: "espelho", label: "Espelho da Administradora" },
]

const REFRESH_KIND_LABEL: Record<ReportRefreshKind, string> = {
  daily: "Diario",
  interval: "Intervalo",
  on_demand_async: "Sob demanda",
}

const ADMIN_LABEL: Record<string, string> = {
  "admin:qitech": "QiTech",
}

const col = createColumnHelper<ReportCard>()

export default function RelatoriosPage() {
  const router = useRouter()
  const sp = useSearchParams()
  const tabParam = sp.get("tab")
  const tab: TabKey =
    tabParam === "espelho" || tabParam === "padronizados"
      ? tabParam
      : "padronizados"

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["controladoria", "relatorios", "catalog"],
    queryFn: () => relatorios.catalog(),
  })

  const reports = data?.reports ?? []

  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState<"todos" | ReportCategoryId>(
    "todos",
  )

  const setTab = React.useCallback(
    (next: TabKey) => {
      const params = new URLSearchParams(sp.toString())
      params.set("tab", next)
      router.replace(`?${params.toString()}`, { scroll: false })
    },
    [router, sp],
  )

  const onRowClick = React.useCallback(
    (row: ReportCard) => {
      const adminSegment =
        tab === "espelho"
          ? `espelho/${row.administradora.split(":")[1] ?? "qitech"}`
          : "padronizados"
      router.push(`/controladoria/relatorios/${adminSegment}/${row.slug}`)
    },
    [router, tab],
  )

  const columns = React.useMemo<ColumnDef<ReportCard, unknown>[]>(
    () => [
      col.accessor("category", {
        header: "Categoria",
        size: 140,
        cell: (info) => {
          const cat = info.getValue() as ReportCategoryId
          return (
            <span className="inline-flex items-center gap-2">
              <span
                className={cx(
                  "flex size-6 shrink-0 items-center justify-center rounded",
                  REPORT_CATEGORY_AVATAR_COLORS[cat],
                )}
                aria-hidden
              >
                <RiFileChart2Line className="size-3.5" />
              </span>
              <span className={tableTokens.cellText}>
                {REPORT_CATEGORY_LABEL[cat]}
              </span>
            </span>
          )
        },
      }) as ColumnDef<ReportCard, unknown>,
      col.accessor("name", {
        header: "Relatorio",
        size: 420,
        cell: (info) => (
          <span
            className={cx(tableTokens.cellStrong, "line-clamp-1")}
            title={info.row.original.description}
          >
            {info.getValue()}
          </span>
        ),
      }) as ColumnDef<ReportCard, unknown>,
      // "Administradora" so faz sentido em Espelho. Em Padronizados a fonte
      // e abstraida (multi-admin canonicalization e followup — quando 2a admin
      // entrar, Padronizados ganha coluna "Cobertura" agregando admins).
      ...(tab === "espelho"
        ? [
            col.accessor("administradora", {
              header: "Administradora",
              size: 130,
              cell: (info) => (
                <span className={tableTokens.cellText}>
                  {ADMIN_LABEL[info.getValue()] ?? info.getValue()}
                </span>
              ),
            }) as ColumnDef<ReportCard, unknown>,
          ]
        : []),
      col.accessor("refresh_kind", {
        header: "Atualizacao",
        size: 130,
        cell: (info) => {
          const v = info.getValue() as ReportRefreshKind
          return (
            <span
              className={cx(
                tableTokens.badge,
                "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
              )}
            >
              {REFRESH_KIND_LABEL[v]}
            </span>
          )
        },
      }) as ColumnDef<ReportCard, unknown>,
      col.display({
        id: "open",
        header: "",
        size: 40,
        cell: () => (
          <RiArrowRightSLine
            className="size-4 text-gray-400 dark:text-gray-500"
            aria-hidden
          />
        ),
      }) as ColumnDef<ReportCard, unknown>,
    ],
    [tab],
  )

  const segmentOptions: {
    value: "todos" | ReportCategoryId
    label: string
    filter: (r: ReportCard) => boolean
  }[] = [
    { value: "todos",         label: "Todos",          filter: () => true },
    { value: "cota",          label: REPORT_CATEGORY_LABEL.cota,          filter: (r) => r.category === "cota" },
    { value: "posicao",       label: REPORT_CATEGORY_LABEL.posicao,       filter: (r) => r.category === "posicao" },
    { value: "estoque",       label: REPORT_CATEGORY_LABEL.estoque,       filter: (r) => r.category === "estoque" },
    { value: "movimentacoes", label: REPORT_CATEGORY_LABEL.movimentacoes, filter: (r) => r.category === "movimentacoes" },
    { value: "custodia",      label: REPORT_CATEGORY_LABEL.custodia,      filter: (r) => r.category === "custodia" },
    { value: "recebimentos",  label: REPORT_CATEGORY_LABEL.recebimentos,  filter: (r) => r.category === "recebimentos" },
    { value: "outros",        label: REPORT_CATEGORY_LABEL.outros,        filter: (r) => r.category === "outros" },
  ]

  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Relatorios"
        info="Catalogo de relatorios das administradoras (QiTech, ...). Padronizados = formato A7 comparavel; Espelho = lente operacional fiel ao adapter."
        subtitle="Controladoria · Catalogo"
      />

      <TabNavigation>
        {TABS.map((t) => (
          <TabNavigationLink key={t.key} asChild active={tab === t.key}>
            <button
              onClick={() => setTab(t.key)}
              className="cursor-pointer"
              aria-current={tab === t.key ? "page" : undefined}
            >
              {t.label}
            </button>
          </TabNavigationLink>
        ))}
      </TabNavigation>

      <DataTableShell<ReportCard>
        data={reports}
        columns={columns}
        loading={isLoading}
        error={error as Error | null}
        onRetry={() => refetch()}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: "Buscar por nome ou descricao...",
        }}
        segments={{
          value: segment,
          onChange: (v) => setSegment(v as typeof segment),
          options: segmentOptions,
        }}
        itemNoun={{ singular: "relatorio", plural: "relatorios" }}
        onRowClick={onRowClick}
        emptyState={{
          icon: RiFileChart2Line,
          title: "Nenhum relatorio disponivel",
          description:
            "Conecte uma administradora (QiTech, ...) em Integracoes para que seus relatorios apareçam aqui.",
        }}
      />
    </div>
  )
}
