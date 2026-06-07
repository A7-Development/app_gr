// src/app/(app)/bi/operacoes5/cedente/[id]/page.tsx
//
// BI · Operações · Drill por dimensão — ROTA do cedente.
//
// Nivel Cedente da espinha (docs/navegacao-aprofundamento.md): o cedente vira
// um LOCAL DE TRABALHO (rota dedicada, back button, breadcrumb derivado). Aqui:
//
//   - lista de OPERACOES do cedente (DataTable)
//   - clique numa operacao -> DRAWER (?selected via nuqs, history=push)
//   - dentro do drawer: DOCUMENTOS (titulos) INLINE
//
// Filtros globais (periodo/UA/produto) chegam pela query string preservada na
// navegacao (useBiFilters le da URL). cedente_id vem do segmento de rota.
// Regime caixa (wh_operacao + wh_titulo). Reconcilia on-screen (§14.6).

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { useRouter } from "next/navigation"
import { useQueryState } from "nuqs"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import { RiArrowLeftLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import { DataTable } from "@/design-system/components/DataTable"
import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"
import { cardTokens } from "@/design-system/tokens/card"
import { fmt, fmtCNPJ, fmtDate } from "@/design-system/tokens/typography"

import { ProvenanceFooter } from "@/components/bi/ProvenanceFooter"
import { useBiFilters } from "@/lib/hooks/useBiFilters"
import { biMetadata, biOperacoes5 } from "@/lib/api-client"
import type {
  Operacoes5DocumentoItem,
  Operacoes5OperacaoItem,
} from "@/lib/api-client"

const fmtPct2 = (v: number) => `${v.toFixed(2).replace(".", ",")}%`
const fmtDias = (v: number) => `${fmt.decimal1.format(v)}d`

// wh_titulo.situacao -> rotulo curto (codigos Bitfin). Fallback: "Cód N".
const SITUACAO_LABEL: Record<number, string> = {
  0: "Aberto",
  1: "Liquidado",
  2: "Vencido",
  3: "Protestado",
  4: "Negativado",
}
const situacaoLabel = (s: number) => SITUACAO_LABEL[s] ?? `Cód ${s}`

export default function CedenteOperacoesPage({
  params,
}: {
  params: { id: string }
}) {
  const cedenteId = Number(params.id)
  const router = useRouter()

  const dataMinimaQuery = useQuery({
    queryKey: ["bi", "metadata", "data-minima"],
    queryFn: () => biMetadata.dataMinima(),
    staleTime: 6 * 60 * 60 * 1000,
  })
  const dataMinima = dataMinimaQuery.data?.data_minima ?? undefined

  // Filtros globais preservados na URL + cedente_id do segmento de rota.
  const { filtersWithFocus } = useBiFilters(dataMinima)
  const filters = React.useMemo(
    () => ({ ...filtersWithFocus, cedenteId }),
    [filtersWithFocus, cedenteId],
  )

  const q = useQuery({
    queryKey: ["bi", "operacoes5", "operacoes", filters],
    queryFn: () => biOperacoes5.operacoes(filters),
    enabled: Number.isFinite(cedenteId),
  })
  const bundle = q.data?.data

  // Drawer da operacao — estado na URL (?selected), abrir = push (voltar fecha).
  const [selected, setSelected] = useQueryState("selected", { history: "push" })
  const opId = selected ? Number(selected) : null
  const selectedOp = React.useMemo(
    () => bundle?.operacoes.find((o) => o.operacao_id === opId) ?? null,
    [bundle, opId],
  )

  const docsQ = useQuery({
    queryKey: ["bi", "operacoes5", "documentos", opId],
    queryFn: () => biOperacoes5.documentos(opId as number),
    enabled: opId != null,
  })
  const docs = docsQ.data?.data

  const columns = React.useMemo(() => buildOperacaoColumns(), [])
  const docColumns = React.useMemo(() => buildDocumentoColumns(), [])

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col overflow-hidden">
      {/* Header do cedente */}
      <div className="shrink-0 border-b border-gray-200 bg-white px-6 pt-3.5 pb-3 dark:border-gray-800 dark:bg-gray-950">
        <button
          type="button"
          onClick={() => router.back()}
          className="mb-1 inline-flex items-center gap-1 text-[12px] text-gray-500 transition-colors hover:text-blue-600 dark:text-gray-400 dark:hover:text-blue-400"
        >
          <RiArrowLeftLine className="size-3.5" aria-hidden />
          Voltar para cedentes
        </button>
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div className="min-w-0">
            <p className="text-[11px] uppercase tracking-wider text-gray-500 dark:text-gray-400">
              BI · Operações · Cedente
            </p>
            <h1 className="truncate text-xl font-semibold text-gray-900 dark:text-gray-50">
              {bundle?.cedente_nome ?? (q.isLoading ? "Carregando…" : "(n/d)")}
            </h1>
            {bundle?.cedente_documento && (
              <p className="text-[12px] tabular-nums text-gray-500 dark:text-gray-400">
                {fmtCNPJ(bundle.cedente_documento)}
              </p>
            )}
          </div>
          {bundle && (
            <div className="flex gap-6">
              <HeaderKpi label="VOP" value={fmt.currencyCompact.format(bundle.vop_total)} />
              <HeaderKpi
                label="Receita"
                value={fmt.currencyCompact.format(bundle.receita_total)}
              />
              <HeaderKpi label="Operações" value={fmt.number.format(bundle.total)} />
            </div>
          )}
        </div>
      </div>

      {/* Lista de operacoes */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {q.isLoading && (
          <div className="h-96 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
        )}
        {q.isError && (
          <Card className={cx(cardTokens.body, "py-12 text-center")}>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Não foi possível carregar as operações do cedente.
            </p>
            <Button variant="ghost" className="mt-2" onClick={() => q.refetch()}>
              Tentar novamente
            </Button>
          </Card>
        )}
        {bundle && (
          <Card className={cx(cardTokens.body, "p-0")}>
            <div className="px-4 py-3">
              <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
                Operações
              </h2>
              <p className="text-[11px] text-gray-500 dark:text-gray-400">
                {fmt.number.format(bundle.total)} operações · clique para ver os documentos
              </p>
            </div>
            <DataTable<Operacoes5OperacaoItem>
              data={bundle.operacoes}
              columns={columns}
              density="compact"
              onRowClick={(row) => setSelected(String(row.operacao_id))}
              renderFooter={(rows) => {
                const vop = rows.reduce(
                  (s, r) => s + (r as Operacoes5OperacaoItem).vop,
                  0,
                )
                const receita = rows.reduce(
                  (s, r) => s + (r as Operacoes5OperacaoItem).receita,
                  0,
                )
                return (
                  <tr>
                    <td className="px-3 py-2 text-xs text-gray-500 dark:text-gray-400">
                      {fmt.number.format(rows.length)} operações
                    </td>
                    <td className="px-3 py-2" />
                    <td className="px-3 py-2" />
                    <td className="px-3 py-2 text-right text-xs font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                      {fmt.currencyWhole.format(vop)}
                    </td>
                    <td className="px-3 py-2" />
                    <td className="px-3 py-2" />
                    <td className="px-3 py-2 text-right text-xs font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                      {fmt.currencyWhole.format(receita)}
                    </td>
                  </tr>
                )
              }}
              className="h-full"
            />
          </Card>
        )}
      </div>

      <ProvenanceFooter provenance={q.data?.provenance} />

      {/* Drawer da operacao — documentos inline */}
      <DrillDownSheet
        open={opId != null}
        onClose={() => setSelected(null)}
        size="xl"
        title={selectedOp ? `Operação ${selectedOp.operacao_id}` : "Operação"}
      >
        {selectedOp && (
          <>
            <DrillDownSheet.Header
              breadcrumb={[
                bundle?.cedente_nome ?? "Cedente",
                `Operação ${selectedOp.operacao_id}`,
              ]}
            />
            <DrillDownSheet.Hero
              id={`Operação #${selectedOp.operacao_id}`}
              title={`${selectedOp.produto} · ${
                selectedOp.data_de_efetivacao
                  ? fmtDate(selectedOp.data_de_efetivacao)
                  : "—"
              }`}
              value={selectedOp.vop}
            />
            <DrillDownSheet.Body>
              <DrillDownSheet.SectionLabel>
                Dados da operação
              </DrillDownSheet.SectionLabel>
              <DrillDownSheet.PropertyList
                items={[
                  { label: "Produto", value: selectedOp.produto },
                  { label: "Modalidade", value: selectedOp.modalidade },
                  { label: "VOP", value: selectedOp.vop, type: "currency" },
                  { label: "Líquido", value: selectedOp.total_liquido, type: "currency" },
                  { label: "Taxa", value: fmtPct2(selectedOp.taxa_juros) },
                  { label: "Prazo médio", value: fmtDias(selectedOp.prazo_medio) },
                  { label: "Receita", value: selectedOp.receita, type: "currency" },
                  {
                    label: "Títulos",
                    value: selectedOp.quantidade_de_titulos,
                    type: "number",
                  },
                ]}
              />

              <div className="mt-6">
                <DrillDownSheet.SectionLabel>
                  Documentos{docs ? ` (${fmt.number.format(docs.total)})` : ""}
                </DrillDownSheet.SectionLabel>
                {docsQ.isLoading && <DrillDownSheet.Skeleton lines={6} />}
                {docsQ.isError && (
                  <p className="py-4 text-sm text-gray-500 dark:text-gray-400">
                    Não foi possível carregar os documentos.
                  </p>
                )}
                {docs && (
                  <DataTable<Operacoes5DocumentoItem>
                    data={docs.documentos}
                    columns={docColumns}
                    density="ultra"
                    renderFooter={(rows) => {
                      const valor = rows.reduce(
                        (s, r) => s + (r as Operacoes5DocumentoItem).valor,
                        0,
                      )
                      return (
                        <tr>
                          <td className="px-3 py-2 text-xs text-gray-500 dark:text-gray-400">
                            {fmt.number.format(rows.length)} documentos
                          </td>
                          <td className="px-3 py-2" />
                          <td className="px-3 py-2 text-right text-xs font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                            {fmt.currencyWhole.format(valor)}
                          </td>
                          <td className="px-3 py-2" />
                          <td className="px-3 py-2" />
                        </tr>
                      )
                    }}
                  />
                )}
              </div>
            </DrillDownSheet.Body>
          </>
        )}
      </DrillDownSheet>
    </div>
  )
}

// ─── Colunas: operacoes ────────────────────────────────────────────────────

const opcol = createColumnHelper<Operacoes5OperacaoItem>()

function buildOperacaoColumns(): ColumnDef<Operacoes5OperacaoItem, unknown>[] {
  return [
    opcol.accessor("operacao_id", {
      header: "Operação",
      size: 110,
      cell: (info) => (
        <span className="tabular-nums text-sm text-gray-900 dark:text-gray-50">
          #{info.getValue<number>()}
        </span>
      ),
    }) as ColumnDef<Operacoes5OperacaoItem, unknown>,
    opcol.accessor("data_de_efetivacao", {
      header: "Data",
      size: 100,
      cell: (info) => {
        const v = info.getValue<string | null>()
        return (
          <span className="tabular-nums text-sm text-gray-700 dark:text-gray-300">
            {v ? fmtDate(v) : "—"}
          </span>
        )
      },
    }) as ColumnDef<Operacoes5OperacaoItem, unknown>,
    opcol.accessor("produto", {
      header: "Produto",
      size: 90,
      cell: (info) => (
        <span className="text-sm text-gray-700 dark:text-gray-300">
          {info.getValue<string>()}
        </span>
      ),
    }) as ColumnDef<Operacoes5OperacaoItem, unknown>,
    opcol.accessor("vop", {
      header: "VOP",
      size: 130,
      cell: (info) => (
        <div className="text-right tabular-nums text-sm text-gray-900 dark:text-gray-50">
          {fmt.currencyWhole.format(info.getValue<number>())}
        </div>
      ),
    }) as ColumnDef<Operacoes5OperacaoItem, unknown>,
    opcol.accessor("taxa_juros", {
      header: "Taxa",
      size: 80,
      cell: (info) => (
        <div className="text-right tabular-nums text-sm text-gray-700 dark:text-gray-300">
          {fmtPct2(info.getValue<number>())}
        </div>
      ),
    }) as ColumnDef<Operacoes5OperacaoItem, unknown>,
    opcol.accessor("prazo_medio", {
      header: "Prazo",
      size: 80,
      cell: (info) => (
        <div className="text-right tabular-nums text-sm text-gray-700 dark:text-gray-300">
          {fmtDias(info.getValue<number>())}
        </div>
      ),
    }) as ColumnDef<Operacoes5OperacaoItem, unknown>,
    opcol.accessor("receita", {
      header: "Receita",
      size: 120,
      cell: (info) => (
        <div className="text-right tabular-nums text-sm text-gray-900 dark:text-gray-50">
          {fmt.currencyWhole.format(info.getValue<number>())}
        </div>
      ),
    }) as ColumnDef<Operacoes5OperacaoItem, unknown>,
  ]
}

// ─── Colunas: documentos (inline no drawer) ────────────────────────────────

const doccol = createColumnHelper<Operacoes5DocumentoItem>()

function buildDocumentoColumns(): ColumnDef<Operacoes5DocumentoItem, unknown>[] {
  return [
    doccol.accessor("numero", {
      header: "Documento",
      size: 160,
      cell: (info) => {
        const r = info.row.original
        return (
          <span className="text-sm text-gray-900 dark:text-gray-50">
            <span className="mr-1 text-[11px] font-medium uppercase text-gray-400 dark:text-gray-500">
              {r.sigla}
            </span>
            {r.numero}
          </span>
        )
      },
    }) as ColumnDef<Operacoes5DocumentoItem, unknown>,
    doccol.accessor("data_de_vencimento_efetiva", {
      header: "Vencimento",
      size: 110,
      cell: (info) => {
        const v = info.getValue<string | null>()
        return (
          <span className="tabular-nums text-sm text-gray-700 dark:text-gray-300">
            {v ? fmtDate(v) : "—"}
          </span>
        )
      },
    }) as ColumnDef<Operacoes5DocumentoItem, unknown>,
    doccol.accessor("valor", {
      header: "Valor",
      size: 120,
      cell: (info) => (
        <div className="text-right tabular-nums text-sm text-gray-900 dark:text-gray-50">
          {fmt.currencyWhole.format(info.getValue<number>())}
        </div>
      ),
    }) as ColumnDef<Operacoes5DocumentoItem, unknown>,
    doccol.accessor("saldo_devedor", {
      header: "Saldo",
      size: 120,
      cell: (info) => (
        <div className="text-right tabular-nums text-sm text-gray-700 dark:text-gray-300">
          {fmt.currencyWhole.format(info.getValue<number>())}
        </div>
      ),
    }) as ColumnDef<Operacoes5DocumentoItem, unknown>,
    doccol.accessor("situacao", {
      header: "Situação",
      size: 100,
      cell: (info) => (
        <span className="text-[12px] text-gray-500 dark:text-gray-400">
          {situacaoLabel(info.getValue<number>())}
        </span>
      ),
    }) as ColumnDef<Operacoes5DocumentoItem, unknown>,
  ]
}

// ─── Header KPI ────────────────────────────────────────────────────────────

function HeaderKpi({ label, value }: { label: string; value: string }) {
  return (
    <div className="text-right">
      <p className="text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400">
        {label}
      </p>
      <p className="text-base font-semibold tabular-nums text-gray-900 dark:text-gray-50">
        {value}
      </p>
    </div>
  )
}
