"use client"

/**
 * BalancoPatrimonialHero — Balance hero da Cota Sub (redesign ESTRUTURAL 2026-05-27).
 *
 * Consome /controladoria/cota-sub/balanco-estrutural. Coerente por natureza + sinal:
 *   - ATIVO (lista plana): Direitos Creditórios, (−) PDD (contra-ativo),
 *     Títulos Públicos, ..., Contas a Receber.
 *   - PASSIVO (lista plana): Contas a Pagar, Cota Senior, Cota Mezanino.
 *   - PL Sub Jr = Σ Ativo − Σ Passivo (fecha por construção).
 *   - Reconciliação MEC (PL fonte + resíduo) num rodapé separado — não é
 *     linha do balanço.
 *
 * DataTable canônica com padrão DRE (hierarquia expansível, sempre expandida,
 * chevron escondido). Grupos top-level (Ativos/Passivos) via subRows. Click em
 * linha com `drillKey` (dc/pdd/cpr) dispara onDrillCategoria.
 */

import * as React from "react"
import {
  RiCheckLine,
  RiAlertLine,
  RiErrorWarningLine,
  RiArrowRightSLine,
  RiCalendarLine,
  RiSparklingFill,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import { DataTable } from "@/design-system/components/DataTable"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { Button } from "@/components/tremor/Button"
import { tableTokens } from "@/design-system/tokens/table"
import type {
  BalancoEstruturalResponse,
  BalancoLinhaEstrutural,
  CategoriaPatrimonialKey,
} from "@/lib/api-client"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style:                 "currency",
  currency:              "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const fmtBRLSigned = (v: number): string => {
  if (Math.abs(v) < 0.005) return "0,00"
  const sign = v > 0 ? "+" : "−"
  return `${sign}${fmtBRL.format(Math.abs(v))}`
}

const fmtDate = (iso: string): string => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[3]}/${m[2]}` : iso
}

// Tooltip amigavel por linha (descricao economica) — usado em title de linha.
const LINHA_TOOLTIP: Record<string, string> = {
  dc_bruto:             "Σ Valor Presente dos recebíveis em estoque (exclui WOP).",
  pdd:                  "Σ Provisão para Devedores Duvidosos (faixas A-H, exclui WOP). Contra-ativo: reduz o ativo.",
  cpr_receber:          "Contas a receber: liquidações em floating (recebível em trânsito retido pelo banco) + despesas diferidas. Σ valores positivos do CPR.",
  cpr_pagar:            "Contas a pagar: despesas, taxas e IOF a recolher. Σ valores negativos do CPR (mostrado em módulo).",
  tesouraria:           "Saldo em tesouraria da classe Sub (exclui Mez/Sr). Negativo = caixa a descoberto (reduz o ativo).",
  saldo_conta_corrente: "Saldo em conta corrente. Exclui linhas CONCILIA (contra-saldos que somam 0).",
  compromissada:        "Operações compromissadas (overnight).",
  titulos_publicos:     "Σ posição em títulos públicos (NTN-*, LFT, LTN).",
  op_estruturadas:      "Σ posição em operações estruturadas (NCPX, VCNC).",
  fundos_di:            "Σ cotas de fundos DI externos.",
  outros_ativos:        "Outros ativos não classificados (exclui PDD e TPF).",
  senior:               "Patrimônio da Cota Senior — cota prioritária (recebe antes da Sub).",
  mezanino:             "Patrimônio da Cota Mezanino — cota prioritária (recebe antes da Sub).",
}

const RESIDUO_AMBER_BRL = 1
const RESIDUO_RED_BRL = 1000

// ─────────────────────────────────────────────────────────────────────────────
// Tipos de linha
// ─────────────────────────────────────────────────────────────────────────────

type RowKind =
  | "grupo"      // Ativos / Passivos (top-level)
  | "line"       // linha de balanço (drilável se drillKey != null)
  | "subtotal"   // Σ Ativos / Σ Passivos
  | "pl-sub"     // PL Sub Jr (residual, destaque)
  | "pl-fonte"   // PL Sub Jr · fonte MEC (reconciliação)
  | "residuo"    // Resíduo identidade contábil (dia)

type Row = {
  id:        string
  kind:      RowKind
  label:     string
  d1:        number | null
  d0:        number | null
  delta:     number | null
  subRows?:  Row[]
  drillKey?: CategoriaPatrimonialKey | null
  contra?:   boolean
  tooltip?:  string
}

function lineTooltip(ln: BalancoLinhaEstrutural): string | undefined {
  const parts: string[] = []
  const friendly = LINHA_TOOLTIP[ln.key]
  if (friendly) parts.push(friendly)
  if (ln.source) parts.push(`Fonte: ${ln.source}`)
  return parts.length ? parts.join("\n\n") : undefined
}

function lineRow(ln: BalancoLinhaEstrutural): Row {
  const contra = ln.natureza === "contra_ativo"
  return {
    id:        `line-${ln.key}`,
    kind:      "line",
    label:     contra ? `(−) ${ln.label}` : ln.label,
    d1:        ln.d1,
    d0:        ln.d0,
    delta:     ln.delta,
    drillKey:  ln.drill_key,
    contra,
    tooltip:   lineTooltip(ln),
  }
}

function subtotalRow(id: string, label: string, d1: number, d0: number, delta: number): Row {
  return { id, kind: "subtotal", label, d1, d0, delta }
}

function buildTree(data: BalancoEstruturalResponse): Row[] {
  const ativoRows = data.ativos.map(lineRow)
  ativoRows.push(subtotalRow("sub-ativos", "Σ Ativos", data.total_ativo_d1, data.total_ativo_d0, data.total_ativo_delta))

  const passivoRows = data.passivos.map(lineRow)
  passivoRows.push(subtotalRow("sub-passivos", "Σ Passivos", data.total_passivo_d1, data.total_passivo_d0, data.total_passivo_delta))

  const r = data.reconciliacao
  return [
    { id: "g-ativos", kind: "grupo", label: "Ativos", d1: null, d0: null, delta: null, subRows: ativoRows },
    { id: "g-passivos", kind: "grupo", label: "Passivos", d1: null, d0: null, delta: null, subRows: passivoRows },
    {
      id: "pl-sub", kind: "pl-sub", label: "PL Sub Jr",
      d1: data.pl_sub_d1, d0: data.pl_sub_d0, delta: data.pl_sub_delta,
      tooltip: "Patrimônio Líquido da Cota Sub Jr = Σ Ativo − Σ Passivo. Fecha por construção.",
    },
    {
      id: "pl-fonte", kind: "pl-fonte", label: "PL Sub Jr · fonte MEC",
      d1: r.pl_fonte_d1, d0: r.pl_fonte_d0, delta: r.pl_fonte_delta,
      tooltip: "PL Sub Jr lido direto do MEC publicado pela QiTech. Check externo de reconciliação.",
    },
    {
      id: "residuo", kind: "residuo", label: "Resíduo de reconciliação (dia)",
      d1: null, d0: null, delta: r.residuo_delta,
    },
  ]
}

// ─────────────────────────────────────────────────────────────────────────────
// Colunas
// ─────────────────────────────────────────────────────────────────────────────

const col = createColumnHelper<Row>()

type BuildColsOpts = { data: string; dataAnterior: string }

function buildColumns(opts: BuildColsOpts): ColumnDef<Row, unknown>[] {
  return [
    col.accessor("label", {
      id:     "label",
      header: "Linha",
      size:   240,
      cell:   (info) => {
        const row = info.row.original
        const indent = info.row.depth * 16

        if (row.kind === "grupo") {
          return (
            <span className="block truncate text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-600 dark:text-gray-300">
              {row.label}
            </span>
          )
        }
        if (row.kind === "residuo") {
          return (
            <span
              className="block truncate text-[10px] uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600"
              title="Δ do dia = (ΔPL calculado) − (ΔPL fonte MEC). Erro real do dia, não snapshot acumulado."
            >
              {row.label}
            </span>
          )
        }
        if (row.kind === "subtotal") {
          return (
            <span style={{ paddingLeft: `${indent}px` }} className={cx("block truncate", tableTokens.cellStrong)}>
              {row.label}
            </span>
          )
        }
        if (row.kind === "pl-sub" || row.kind === "pl-fonte") {
          const isMain = row.kind === "pl-sub"
          return (
            <span
              title={row.tooltip}
              className={cx(
                "block truncate",
                isMain ? "font-semibold text-gray-900 dark:text-gray-50" : "font-medium text-gray-700 dark:text-gray-300",
                row.tooltip && "cursor-help",
              )}
            >
              {row.label}
            </span>
          )
        }
        // line
        return (
          <span
            style={{ paddingLeft: `${indent}px` }}
            className={cx("block truncate text-gray-900 dark:text-gray-50", row.tooltip && "cursor-help")}
            title={row.tooltip}
          >
            {row.label}
          </span>
        )
      },
    }) as ColumnDef<Row, unknown>,

    ...(["d1", "d0"] as const).map((field) =>
      col.accessor(field, {
        id:     field,
        header: () => (
          <div className="text-right text-[10px] font-medium uppercase tracking-[0.04em] text-gray-500 dark:text-gray-400">
            {field === "d1" ? "D-1" : "D0"}
            <div className="font-normal text-gray-400 normal-case">
              {fmtDate(field === "d1" ? opts.dataAnterior : opts.data)}
            </div>
          </div>
        ),
        meta:   { align: "right" },
        size:   130,
        cell:   (info) => {
          const row = info.row.original
          if (row.kind === "residuo") return null
          const v = info.getValue<number | null>()
          if (v == null) return null
          const isStrong = row.kind === "subtotal" || row.kind === "pl-sub"
          const isMuted = row.kind === "pl-fonte"
          return (
            <div
              style={{ textAlign: "right" }}
              className={cx(
                isMuted ? tableTokens.cellSecondary + " tabular-nums" : tableTokens.cellNumber,
                isStrong && "font-semibold",
              )}
            >
              {fmtBRL.format(v)}
            </div>
          )
        },
      }) as ColumnDef<Row, unknown>,
    ),

    col.accessor("delta", {
      id:     "delta",
      header: () => (
        <div className="text-right text-[10px] font-medium uppercase tracking-[0.04em] text-gray-500 dark:text-gray-400">Δ</div>
      ),
      meta:   { align: "right" },
      size:   120,
      cell:   (info) => {
        const row = info.row.original
        const v = info.getValue<number | null>()
        if (v == null) return null
        const isZero = Math.abs(v) < 0.005
        if (isZero) {
          return <div style={{ textAlign: "right" }} className="text-gray-300 dark:text-gray-700 tabular-nums">—</div>
        }
        if (row.kind === "residuo") {
          const abs = Math.abs(v)
          const tone = abs < RESIDUO_AMBER_BRL ? "ok" : abs < RESIDUO_RED_BRL ? "warn" : "error"
          return (
            <div
              style={{ textAlign: "right" }}
              className={cx(
                "tabular-nums",
                tone === "ok" && "text-gray-500 dark:text-gray-400",
                tone === "warn" && "font-medium text-amber-700 dark:text-amber-400",
                tone === "error" && "font-semibold text-red-700 dark:text-red-400",
              )}
            >
              {fmtBRLSigned(v)}
            </div>
          )
        }
        const isStrong = row.kind === "subtotal" || row.kind === "pl-sub"
        return (
          <div
            style={{ textAlign: "right" }}
            className={cx(
              v > 0 ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400",
              "tabular-nums",
              isStrong && "font-semibold",
            )}
          >
            {fmtBRLSigned(v)}
          </div>
        )
      },
    }) as ColumnDef<Row, unknown>,

    col.accessor((row) => row, {
      id:     "chevron",
      header: "",
      size:   24,
      cell:   (info) => {
        const row = info.row.original
        if (row.kind !== "line" || !row.drillKey) return null
        return (
          <div className="flex justify-end text-gray-300 dark:text-gray-700">
            <RiArrowRightSLine className="size-3.5" aria-hidden="true" />
          </div>
        )
      },
    }) as ColumnDef<Row, unknown>,
  ]
}

// ─────────────────────────────────────────────────────────────────────────────
// rowClassName por kind
// ─────────────────────────────────────────────────────────────────────────────

function rowClass(row: Row): string {
  if (row.kind === "grupo") {
    return cx("!border-l-0 bg-gray-50 dark:bg-gray-900/60", "border-y border-y-gray-200 dark:border-y-gray-800")
  }
  if (row.kind === "subtotal") {
    return "!border-l-0 bg-gray-50/40 dark:bg-gray-900/30 border-t border-t-gray-300 dark:border-t-gray-700"
  }
  if (row.kind === "pl-sub") {
    return "!border-l-0 bg-blue-50/40 dark:bg-blue-950/10 border-t-2 border-t-gray-300 dark:border-t-gray-700"
  }
  if (row.kind === "pl-fonte") {
    return "!border-l-0 border-t border-t-gray-100 dark:border-t-gray-900"
  }
  if (row.kind === "residuo") {
    return "!h-6 !border-l-0 border-t border-t-gray-200 dark:border-t-gray-800"
  }
  return "" // line
}

// ─────────────────────────────────────────────────────────────────────────────
// Componente
// ─────────────────────────────────────────────────────────────────────────────

export type BalancoPatrimonialHeroProps = {
  data?:         BalancoEstruturalResponse
  loading?:      boolean
  errorMessage?: string
  onRetry?:      () => void
  onDrillCategoria?: (key: CategoriaPatrimonialKey) => void
  /** Callback do botao "Explicar variacao". Quando undefined, botao some. */
  onExplicarVariacao?: () => void
  /** Loading state do agente — desabilita o botao + muda label. */
  explicarVariacaoLoading?: boolean
}

export function BalancoPatrimonialHero({
  data,
  loading       = false,
  errorMessage,
  onRetry,
  onDrillCategoria,
  onExplicarVariacao,
  explicarVariacaoLoading = false,
}: BalancoPatrimonialHeroProps) {
  const residuo = data ? data.reconciliacao.residuo_delta : 0
  const residuoAbs = Math.abs(residuo)
  const residuoStatus: "ok" | "warn" | "error" =
    residuoAbs < RESIDUO_AMBER_BRL ? "ok" : residuoAbs < RESIDUO_RED_BRL ? "warn" : "error"

  const tree = React.useMemo(() => (data ? buildTree(data) : []), [data])
  const columns = React.useMemo(
    () => buildColumns({ data: data?.data ?? "", dataAnterior: data?.data_anterior ?? "" }),
    [data?.data, data?.data_anterior],
  )
  const handleRowClick = React.useCallback((row: Row) => {
    if (row.kind === "line" && row.drillKey && onDrillCategoria) {
      onDrillCategoria(row.drillKey)
    }
  }, [onDrillCategoria])

  if (errorMessage && !loading) {
    return (
      <ErrorState
        title="Falha ao carregar o balanço"
        description={errorMessage}
        action={onRetry ? <Button onClick={onRetry}>Tentar novamente</Button> : undefined}
        className="mt-4"
      />
    )
  }

  if (loading && !data) {
    return (
      <Card className="flex h-[480px] items-center justify-center p-3">
        <span className="text-sm text-gray-500 dark:text-gray-400">Carregando balanço…</span>
      </Card>
    )
  }

  if (!data) {
    return (
      <EmptyState
        icon={RiCalendarLine}
        title="Sem dados para esta data"
        description="A QiTech não publicou snapshot deste fundo no dia selecionado."
        className="mt-4"
      />
    )
  }

  return (
    <Card className="flex flex-col p-0">
      <div className="flex flex-wrap items-start justify-between gap-2 px-3 pt-2.5 pb-2">
        <div className="flex flex-col">
          <h3 className="text-[13px] font-semibold text-gray-900 dark:text-gray-50">Balanço · ótica Sub Jr</h3>
          <p className="text-[11px] text-gray-500 dark:text-gray-400">{data.fundo_nome}</p>
        </div>
        <div className="flex items-center gap-2">
          {onExplicarVariacao && (
            <button
              type="button"
              onClick={onExplicarVariacao}
              disabled={explicarVariacaoLoading}
              className={cx(
                "inline-flex items-center gap-1 rounded border px-2 py-1 text-[11px] font-medium transition-colors",
                "border-violet-200 bg-violet-50 text-violet-700",
                "hover:border-violet-300 hover:bg-violet-100",
                "dark:border-violet-900/50 dark:bg-violet-500/10 dark:text-violet-300",
                "dark:hover:border-violet-800 dark:hover:bg-violet-500/20",
                "disabled:cursor-wait disabled:opacity-60",
              )}
              title="Invocar agente IA pra explicar a variacao do dia"
            >
              <RiSparklingFill className="size-3" aria-hidden="true" />
              {explicarVariacaoLoading ? "Analisando…" : "Explicar variação"}
            </button>
          )}
          <IdentidadeBadge status={residuoStatus} residuo={residuo} />
        </div>
      </div>

      <DataTable
        data={tree}
        columns={columns}
        density="compact"
        showColumnManager={false}
        showDensityToggle={false}
        showExport={false}
        virtualize={false}
        enableExpanding
        getSubRows={(row) => row.subRows}
        defaultExpanded={true}
        rowClassName={(row) => cx(
          rowClass(row),
          row.kind === "line" && row.drillKey && "cursor-pointer hover:bg-gray-50/80 dark:hover:bg-gray-900/40",
        )}
        onRowClick={handleRowClick}
      />
    </Card>
  )
}

// ─── IdentidadeBadge ─────────────────────────────────────────────────────────

function IdentidadeBadge({ status, residuo }: { status: "ok" | "warn" | "error"; residuo: number }) {
  if (status === "ok") {
    return (
      <span className="inline-flex items-center gap-1 rounded border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/40 dark:text-emerald-300">
        <RiCheckLine className="size-3" aria-hidden="true" />
        Fechamento ok
      </span>
    )
  }
  if (status === "warn") {
    return (
      <span
        className="inline-flex items-center gap-1 rounded border border-amber-200 bg-amber-50 px-1.5 py-0.5 text-[10px] font-medium text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300"
        title="Resíduo típico de arredondamento — investigar se persistir"
      >
        <RiAlertLine className="size-3" aria-hidden="true" />
        Resíduo {fmtBRLSigned(residuo)}
      </span>
    )
  }
  return (
    <span
      className="inline-flex items-center gap-1 rounded border border-red-200 bg-red-50 px-1.5 py-0.5 text-[10px] font-medium text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300"
      title="Desalinhamento entre PL deduzido e fonte — abrir investigação"
    >
      <RiErrorWarningLine className="size-3" aria-hidden="true" />
      Resíduo {fmtBRLSigned(residuo)}
    </span>
  )
}
