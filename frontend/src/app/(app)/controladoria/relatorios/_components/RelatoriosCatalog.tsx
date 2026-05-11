// src/app/(app)/controladoria/relatorios/_components/RelatoriosCatalog.tsx
//
// Catalogo de relatorios — composicao compartilhada entre as duas L2:
//   - /controladoria/relatorios/padronizados
//   - /controladoria/relatorios/espelho
//
// Decisao 2026-05-09 preservada: ambos os segmentos leem o MESMO catalogo
// (Opcao A — lente operacional). Diferenca entre segmentos e visual:
//   - Padronizados: foco em entidade canonica (sem coluna Administradora).
//   - Espelho: foco na administradora (coluna extra + drill-down inclui admin).
//
// Refator 2026-05-10: tab L3 (TabNavigation) substituida por L2 na sidebar
// (caption 'Relatorios' + 2 itens). Plano: conversa em chat 2026-05-10.

"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { useQuery } from "@tanstack/react-query"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import { RiArrowRightSLine, RiFileChart2Line } from "@remixicon/react"

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

import { relatorios, type ReportCard, type ReportRefreshKind } from "../_lib/api"

export type RelatoriosSegment = "padronizados" | "espelho"

const REFRESH_KIND_LABEL: Record<ReportRefreshKind, string> = {
  daily: "Diario",
  interval: "Intervalo",
  on_demand_async: "Sob demanda",
}

const ADMIN_LABEL: Record<string, string> = {
  "admin:qitech": "QiTech",
}

// TEMPORARIO (2026-05-10) — coluna de diagnostico exibindo o endpoint real
// chamado no vendor para cada relatorio. Espelha:
//   - backend/app/modules/integracoes/adapters/admin/qitech/endpoints.py
//   - backend/.../qitech/reports.py::TIPOS_DE_MERCADO_CONHECIDOS
//   - backend/.../qitech/report_jobs.py (POST async do fidc-estoque)
// Quando o backend expor `endpoint_path` no ReportCard, remover este mapa.
const QITECH_ENDPOINT_ADDRESS: Record<string, string> = {
  "market.outros_fundos":      "GET /v2/netreport/report/market/outros-fundos/{data}",
  "market.conta_corrente":     "GET /v2/netreport/report/market/conta-corrente/{data}",
  "market.tesouraria":         "GET /v2/netreport/report/market/tesouraria/{data}",
  "market.outros_ativos":      "GET /v2/netreport/report/market/outros-ativos/{data}",
  "market.demonstrativo_caixa":"GET /v2/netreport/report/market/demonstrativo-caixa/{data}",
  "market.cpr":                "GET /v2/netreport/report/market/cpr/{data}",
  "market.mec":                "GET /v2/netreport/report/market/mec/{data}",
  "market.rentabilidade":      "GET /v2/netreport/report/market/rentabilidade/{data}",
  "market.rf":                 "GET /v2/netreport/report/market/rf/{data}",
  "market.rf_compromissadas":  "GET /v2/netreport/report/market/rf-compromissadas/{data}",
  "market.fidc_estoque":       "POST /v2/queue/scheduler/report/fidc-estoque",
  "bank_account.balance":      "GET /v2/conta-corrente/bank-account/balance/{agencia}/{conta}/{data}",
  "bank_account.statement":    "GET /v2/conta-corrente/bank-account/statement/{agencia}/{conta}/{inicio}/{fim}",
}

const SEGMENT_META: Record<
  RelatoriosSegment,
  { title: string; info: string; subtitle: string }
> = {
  padronizados: {
    title: "Relatorios Padronizados",
    info: "Formato A7 canonico — comparavel entre administradoras (QiTech, ...). Use quando voce quer a mesma metrica/visao independente de quem operou o fundo.",
    subtitle: "Controladoria · Relatorios",
  },
  espelho: {
    title: "Espelho da Administradora",
    info: "Lente operacional fiel ao formato da administradora (QiTech, ...). Use para reconciliacao, conferencia de extratos e auditoria.",
    subtitle: "Controladoria · Relatorios",
  },
}

const col = createColumnHelper<ReportCard>()

export function RelatoriosCatalog({ segment }: { segment: RelatoriosSegment }) {
  const router = useRouter()
  const meta = SEGMENT_META[segment]

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["controladoria", "relatorios", "catalog"],
    queryFn: () => relatorios.catalog(),
  })

  const reports = data?.reports ?? []

  const [search, setSearch] = React.useState("")
  const [segmentFilter, setSegmentFilter] = React.useState<
    "todos" | ReportCategoryId
  >("todos")

  const onRowClick = React.useCallback(
    (row: ReportCard) => {
      const adminSegment =
        segment === "espelho"
          ? `espelho/${row.administradora.split(":")[1] ?? "qitech"}`
          : "padronizados"
      router.push(`/controladoria/relatorios/${adminSegment}/${row.slug}`)
    },
    [router, segment],
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
      ...(segment === "espelho"
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
            // TEMPORARIO (2026-05-10) — coluna de diagnostico. Remover quando
            // o backend expuser `endpoint_path` direto no ReportCard.
            col.accessor("endpoint_name", {
              header: "Endpoint",
              size: 460,
              cell: (info) => {
                const name = info.getValue() as string
                const addr = QITECH_ENDPOINT_ADDRESS[name]
                return (
                  <span
                    className={cx(tableTokens.cellTextMono, "line-clamp-1")}
                    title={addr ?? name}
                  >
                    {addr ?? name}
                  </span>
                )
              },
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
    [segment],
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
        title={meta.title}
        info={meta.info}
        subtitle={meta.subtitle}
      />

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
          value: segmentFilter,
          onChange: (v) => setSegmentFilter(v as typeof segmentFilter),
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
