"use client"

// Preview page — demo isolada do <DataTableShell> + tableTokens.
//
// Tabela mockada de Cedentes (FIDC). Usa o wrapper canonico proposto:
//   - Card flex flex-col gap-3 p-3
//   - FilterSearch + SegmentSwitch + Counter (X de Y)
//   - DataTable density=compact
//   - Cells via tableTokens (12px, gray-900/100, badges 11px, mono em CNPJ)
//
// Quando aprovado, este pattern vira o padrao de toda listagem CRUD/admin.

import * as React from "react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import {
  RiAddLine,
  RiBuildingLine,
  RiCheckLine,
  RiDeleteBinLine,
  RiMoreLine,
} from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/tremor/DropdownMenu"
import { DataTableShell, PageHeader } from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

// ───────────────────────────────────────────────────────────────────────────
// Tipo + mock
// ───────────────────────────────────────────────────────────────────────────

type CedenteRow = {
  id: string
  razao_social: string
  cnpj: string
  setor: "industrial" | "varejo" | "servicos" | "agro"
  status: "ativo" | "suspenso" | "em_analise"
  volume_mensal: number
  ultima_cessao: string // ISO yyyy-MM-dd
}

const SAMPLE: CedenteRow[] = [
  { id: "ced-001", razao_social: "Metalúrgica São Paulo Ltda", cnpj: "11222333000181", setor: "industrial", status: "ativo",     volume_mensal: 1_850_400, ultima_cessao: "2026-04-28" },
  { id: "ced-002", razao_social: "Distribuidora Norte S.A.",   cnpj: "22333444000172", setor: "varejo",     status: "ativo",     volume_mensal:   923_000, ultima_cessao: "2026-04-26" },
  { id: "ced-003", razao_social: "Tech Soluções ME",           cnpj: "33444555000163", setor: "servicos",   status: "em_analise",volume_mensal:   450_000, ultima_cessao: "2026-04-15" },
  { id: "ced-004", razao_social: "Agro Grãos do Sul S.A.",     cnpj: "44555666000154", setor: "agro",       status: "ativo",     volume_mensal: 12_300_000, ultima_cessao: "2026-04-29" },
  { id: "ced-005", razao_social: "Confecções RJ Ltda",         cnpj: "55666777000145", setor: "industrial", status: "suspenso",  volume_mensal:   143_200, ultima_cessao: "2026-03-12" },
  { id: "ced-006", razao_social: "Logística Express ME",       cnpj: "66777888000136", setor: "servicos",   status: "ativo",     volume_mensal:   678_000, ultima_cessao: "2026-04-22" },
  { id: "ced-007", razao_social: "Móveis Rápidos Ltda",        cnpj: "77888999000127", setor: "industrial", status: "ativo",     volume_mensal:   345_000, ultima_cessao: "2026-04-25" },
  { id: "ced-008", razao_social: "Padaria Industrial ME",      cnpj: "88999000000118", setor: "varejo",     status: "em_analise",volume_mensal:   298_000, ultima_cessao: "2026-04-10" },
  { id: "ced-009", razao_social: "Farmacêutica Sul Ltda",      cnpj: "99000111000109", setor: "industrial", status: "ativo",     volume_mensal: 2_150_000, ultima_cessao: "2026-04-30" },
  { id: "ced-010", razao_social: "Construtora ABC Ltda",       cnpj: "10111222000190", setor: "servicos",   status: "suspenso",  volume_mensal:   789_000, ultima_cessao: "2026-02-15" },
]

// ───────────────────────────────────────────────────────────────────────────
// Formatters
// ───────────────────────────────────────────────────────────────────────────

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  maximumFractionDigits: 0,
})

function fmtCnpj(s: string): string {
  const d = s.replace(/\D/g, "").padStart(14, "0")
  return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`
}

function fmtDateRelative(iso: string): string {
  const diff = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
  if (diff === 0) return "hoje"
  if (diff === 1) return "ontem"
  if (diff < 30) return `há ${diff} dias`
  if (diff < 365) return `há ${Math.floor(diff / 30)} meses`
  return `há ${Math.floor(diff / 365)} anos`
}

// ───────────────────────────────────────────────────────────────────────────
// Cells custom — usam EXCLUSIVAMENTE tableTokens
// ───────────────────────────────────────────────────────────────────────────

const SETOR_LABEL: Record<CedenteRow["setor"], string> = {
  industrial: "Industrial",
  varejo: "Varejo",
  servicos: "Serviços",
  agro: "Agro",
}

const SETOR_TONES: Record<
  CedenteRow["setor"],
  { bg: string; fg: string; dot: string }
> = {
  industrial: { bg: "bg-blue-50 dark:bg-blue-500/10",       fg: "text-blue-700 dark:text-blue-300",       dot: "bg-blue-500" },
  varejo:     { bg: "bg-emerald-50 dark:bg-emerald-500/10", fg: "text-emerald-700 dark:text-emerald-300", dot: "bg-emerald-500" },
  servicos:   { bg: "bg-violet-50 dark:bg-violet-500/10",   fg: "text-violet-700 dark:text-violet-300",   dot: "bg-violet-500" },
  agro:       { bg: "bg-amber-50 dark:bg-amber-500/10",     fg: "text-amber-700 dark:text-amber-300",     dot: "bg-amber-500" },
}

function SetorBadge({ setor }: { setor: CedenteRow["setor"] }) {
  const tone = SETOR_TONES[setor]
  return (
    <span className={cx(tableTokens.badgeWithDot, tone.bg, tone.fg)}>
      <span aria-hidden className={cx("size-1.5 rounded-full", tone.dot)} />
      {SETOR_LABEL[setor]}
    </span>
  )
}

function StatusBadge({ status }: { status: CedenteRow["status"] }) {
  if (status === "ativo") {
    return (
      <span className={cx(tableTokens.badge, "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300")}>
        <RiCheckLine className="size-3" aria-hidden />
        Ativo
      </span>
    )
  }
  if (status === "em_analise") {
    return (
      <span className={cx(tableTokens.badge, "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300")}>
        Em análise
      </span>
    )
  }
  return (
    <span className={cx(tableTokens.badge, "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400")}>
      Suspenso
    </span>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

const col = createColumnHelper<CedenteRow>()

type Segment = "todos" | "ativos" | "suspensos" | "em_analise"

export default function DataTableShellDemoPage() {
  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState<Segment>("todos")

  const columns = React.useMemo<ColumnDef<CedenteRow, unknown>[]>(
    () => [
      col.accessor("razao_social", {
        header: "Razão social",
        size: 280,
        cell: (info) => (
          <span className={tableTokens.cellText}>{info.getValue()}</span>
        ),
      }) as ColumnDef<CedenteRow, unknown>,

      col.accessor("cnpj", {
        header: "CNPJ",
        size: 160,
        cell: (info) => (
          <span className={tableTokens.cellTextMono}>
            {fmtCnpj(info.getValue())}
          </span>
        ),
      }) as ColumnDef<CedenteRow, unknown>,

      col.accessor("setor", {
        header: "Setor",
        size: 130,
        cell: (info) => <SetorBadge setor={info.getValue()} />,
      }) as ColumnDef<CedenteRow, unknown>,

      col.accessor("status", {
        header: "Status",
        size: 120,
        cell: (info) => <StatusBadge status={info.getValue()} />,
      }) as ColumnDef<CedenteRow, unknown>,

      col.accessor("volume_mensal", {
        header: "Volume mensal",
        meta: { align: "right" },
        size: 150,
        cell: (info) => (
          <span className={cx(tableTokens.cellNumber, "block text-right")}>
            {fmtBRL.format(info.getValue())}
          </span>
        ),
      }) as ColumnDef<CedenteRow, unknown>,

      col.accessor("ultima_cessao", {
        header: "Última cessão",
        size: 130,
        cell: (info) => (
          <span className={tableTokens.cellSecondary}>
            {fmtDateRelative(info.getValue())}
          </span>
        ),
      }) as ColumnDef<CedenteRow, unknown>,

      col.display({
        id: "actions",
        header: "",
        size: 56,
        cell: ({ row }) => (
          <div className="flex justify-end">
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  variant="ghost"
                  className="size-7 p-0"
                  aria-label={`Ações de ${row.original.razao_social}`}
                  onClick={(e) => e.stopPropagation()}
                >
                  <RiMoreLine className="size-4" aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" sideOffset={4}>
                <DropdownMenuItem onSelect={() => console.log("Editar", row.original.id)}>
                  Editar
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  onSelect={() => console.log("Excluir", row.original.id)}
                  className="text-red-600 focus:text-red-700 dark:text-red-400 dark:focus:text-red-300"
                >
                  <RiDeleteBinLine className="mr-2 size-4" aria-hidden />
                  Excluir
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        ),
      }) as ColumnDef<CedenteRow, unknown>,
    ],
    [],
  )

  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Demo · DataTableShell"
        info="Wrapper canonico de tabelas (Card + filtros + DataTable). Usa tableTokens em todas as cells. Use esta pagina para validar visualmente o padrao antes de propagar."
        subtitle="Preview · validação do padrão"
        actions={
          <Button
            variant="primary"
            onClick={() => console.log("Novo")}
          >
            <RiAddLine className="mr-1 size-4" aria-hidden />
            Novo cedente
          </Button>
        }
      />

      <DataTableShell<CedenteRow>
        data={SAMPLE}
        columns={columns}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: "Buscar por razão social ou CNPJ...",
        }}
        segments={{
          value: segment,
          onChange: (v) => setSegment(v as Segment),
          options: [
            { value: "todos",      label: "Todos",      filter: () => true },
            { value: "ativos",     label: "Ativos",     filter: (r) => r.status === "ativo" },
            { value: "suspensos",  label: "Suspensos",  filter: (r) => r.status === "suspenso" },
            { value: "em_analise", label: "Em análise", filter: (r) => r.status === "em_analise" },
          ],
        }}
        itemNoun={{ singular: "cedente", plural: "cedentes" }}
        emptyState={{
          icon: RiBuildingLine,
          title: "Nenhum cedente cadastrado",
          description: "Cadastre o primeiro cedente para começar a operar.",
          action: (
            <Button variant="primary">
              <RiAddLine className="mr-1 size-4" aria-hidden />
              Cadastrar cedente
            </Button>
          ),
        }}
        onRowClick={(row) => console.log("Row click:", row.id)}
      />
    </div>
  )
}
