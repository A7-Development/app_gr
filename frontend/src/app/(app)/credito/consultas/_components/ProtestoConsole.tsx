// src/app/(app)/credito/consultas/_components/ProtestoConsole.tsx
//
// Console reutilizável de consulta de protesto (por CNPJ/CPF), parametrizado
// pela `fonte`. Duas instâncias: "Protestos" (cenprot_sp, robusta, com
// cancelamento/quitação, sem credor) e "Protestos · Credor (SP)" (ieptb_credor,
// com credor via login gov.br — gated). Dispara POST /credito/consultas/protesto
// (isLoading + progresso ao vivo, §7.3) e renderiza a tabela reconciliando o
// total (§14.6), avisando quando a fonte só devolveu a 1ª página.

"use client"

import * as React from "react"
import type { ColumnDef } from "@tanstack/react-table"
import { useMutation } from "@tanstack/react-query"
import { RiAlarmWarningLine, RiSearchLine, RiShieldCheckLine } from "@remixicon/react"
import { toast } from "sonner"

import { Badge } from "@/components/tremor/Badge"
import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import { DataTable, PageHeader } from "@/design-system/components"
import { cardTokens } from "@/design-system/tokens/card"
import { tableTokens } from "@/design-system/tokens/table"
import {
  credito,
  type ProtestoFonte,
  type ProtestoTituloView,
  type ProtestoView,
} from "@/lib/credito-client"
import { cx } from "@/lib/utils"

const BRL = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })

function fmtBRL(v: number | null): string {
  return v === null || Number.isNaN(v) ? "—" : BRL.format(v)
}

function fmtData(s: string | null): string {
  if (!s) return "—"
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s)
  return m ? `${m[3]}/${m[2]}/${m[1]}` : s
}

function SituacaoBadge({ t }: { t: ProtestoTituloView }) {
  if ((t.valor_quitacao ?? 0) > 0)
    return <Badge variant="success">Quitado</Badge>
  if ((t.valor_cancelamento ?? 0) > 0)
    return <Badge variant="neutral">Cancelado</Badge>
  return <Badge variant="warning">Aberto</Badge>
}

const COL_CARTORIO: ColumnDef<ProtestoTituloView, unknown> = {
  id: "cartorio",
  header: "Cartório",
  cell: ({ row }) => (
    <span className={cx(tableTokens.cellText, "truncate")}>
      {row.original.cartorio ?? "—"}
    </span>
  ),
}
const COL_PRACA: ColumnDef<ProtestoTituloView, unknown> = {
  id: "praca",
  header: "Cidade/UF",
  cell: ({ row }) => {
    const { cidade, uf } = row.original
    return (
      <span className={tableTokens.cellSecondary}>
        {[cidade, uf].filter(Boolean).join(" / ") || "—"}
      </span>
    )
  },
}
const COL_VALOR: ColumnDef<ProtestoTituloView, unknown> = {
  id: "valor",
  header: "Valor",
  cell: ({ row }) => (
    <span className={cx(tableTokens.cellNumber, "block text-right")}>
      {fmtBRL(row.original.valor)}
    </span>
  ),
}

const COLS_CENPROT: ColumnDef<ProtestoTituloView, unknown>[] = [
  COL_CARTORIO,
  COL_PRACA,
  COL_VALOR,
  {
    id: "cancelamento",
    header: "Cancelamento",
    cell: ({ row }) => (
      <span className={cx(tableTokens.cellNumberSecondary, "block text-right")}>
        {fmtBRL(row.original.valor_cancelamento)}
      </span>
    ),
  },
  {
    id: "quitacao",
    header: "Quitação",
    cell: ({ row }) => (
      <span className={cx(tableTokens.cellNumberSecondary, "block text-right")}>
        {fmtBRL(row.original.valor_quitacao)}
      </span>
    ),
  },
  {
    id: "situacao",
    header: "Situação",
    cell: ({ row }) => <SituacaoBadge t={row.original} />,
  },
]

const COLS_CREDOR: ColumnDef<ProtestoTituloView, unknown>[] = [
  COL_CARTORIO,
  COL_PRACA,
  {
    id: "data",
    header: "Data",
    cell: ({ row }) => (
      <span className={tableTokens.cellNumberSecondary}>
        {fmtData(row.original.data_protesto)}
      </span>
    ),
  },
  COL_VALOR,
  {
    id: "credor",
    header: "Credor (cedente)",
    cell: ({ row }) => {
      const c = row.original.credor
      return c ? (
        <span className={cx(tableTokens.cellText, "font-medium")}>{c}</span>
      ) : (
        <span className={tableTokens.cellMuted}>não identificado</span>
      )
    },
  },
]

export type ProtestoConsoleProps = {
  fonte: ProtestoFonte
  title: string
  subtitle: string
  info: string
  /** Aviso fixo sob o input (ex.: gated "acesso gov.br em configuração"). */
  hint?: string
}

export function ProtestoConsole({ fonte, title, subtitle, info, hint }: ProtestoConsoleProps) {
  const [documento, setDocumento] = React.useState("")
  const [result, setResult] = React.useState<ProtestoView | null>(null)
  const isCredor = fonte === "ieptb_credor"

  const consulta = useMutation({
    mutationFn: (doc: string) => credito.consultas.protesto({ documento: doc, fonte }),
    onSuccess: (view) => {
      setResult(view)
      if (!view.encontrado)
        toast.error(view.message ?? view.mensagem ?? "Consulta não completou.")
    },
    onError: (err) => toast.error(`Erro na consulta: ${(err as Error).message}`),
  })

  const digits = documento.replace(/\D/g, "")
  const canSubmit = (digits.length === 11 || digits.length === 14) && !consulta.isPending

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!canSubmit) return
    setResult(null)
    consulta.mutate(documento)
  }

  return (
    <div className="flex flex-col gap-6 px-12 py-6 pb-28">
      <PageHeader title={title} subtitle={subtitle} info={info} />

      <Card>
        <form onSubmit={handleSubmit} className={cardTokens.bodyComfortable}>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="doc">CNPJ ou CPF</Label>
            <div className="flex flex-wrap items-center gap-3">
              <Input
                id="doc"
                value={documento}
                onChange={(e) => setDocumento(e.target.value)}
                placeholder="00.000.000/0001-00 ou 000.000.000-00"
                className="max-w-xs"
                disabled={consulta.isPending}
              />
              <Button type="submit" disabled={!canSubmit} isLoading={consulta.isPending}>
                <RiSearchLine className="size-4" aria-hidden />
                Consultar
              </Button>
            </div>
          </div>

          {hint && !consulta.isPending && (
            <p className="mt-3 text-sm text-amber-700 dark:text-amber-400">{hint}</p>
          )}

          {consulta.isPending && (
            <p className="mt-3 flex items-center gap-2 text-sm text-blue-700 dark:text-blue-300">
              <span className="size-1.5 animate-pulse rounded-full bg-blue-500" aria-hidden />
              {isCredor
                ? "Consultando o IEPTB/CENPROT (gov.br) — nacional + detalhe dos cartórios de SP. Pode levar até ~1 min."
                : "Consultando o CENPROT-SP (protestosp.com.br). Pode levar alguns segundos."}
            </p>
          )}
        </form>
      </Card>

      {result !== null && !consulta.isPending && (
        <Resultado view={result} isCredor={isCredor} />
      )}
    </div>
  )
}

function Resultado({ view, isCredor }: { view: ProtestoView; isCredor: boolean }) {
  if (!view.encontrado) {
    return (
      <Card>
        <div className={cx(cardTokens.bodyComfortable, "flex items-start gap-3")}>
          <RiAlarmWarningLine className="size-5 shrink-0 text-amber-500" aria-hidden />
          <div>
            <p className="text-sm font-medium text-gray-900 dark:text-gray-100">
              {view.transitorio ? "Fonte instável" : "Consulta sem resultado"}
            </p>
            <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
              {view.message ?? view.mensagem ?? "Tente novamente."}
            </p>
          </div>
        </div>
      </Card>
    )
  }

  const constam = view.constam_protestos
  const temDetalhe = view.titulos.length > 0
  const columns = isCredor ? COLS_CREDOR : COLS_CENPROT

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <div className={cx(cardTokens.bodyComfortable, "flex flex-wrap items-center gap-x-8 gap-y-3")}>
          {constam ? (
            <Badge variant="error">
              <RiAlarmWarningLine className="-ml-0.5 size-3.5" aria-hidden />
              Constam protestos
            </Badge>
          ) : (
            <Badge variant="success">
              <RiShieldCheckLine className="-ml-0.5 size-3.5" aria-hidden />
              Nada consta
            </Badge>
          )}
          <Stat label="Títulos" value={String(view.qtd_total)} />
          <Stat label="Valor total" value={fmtBRL(view.valor_total)} />
          {isCredor && (
            <Stat label="Com credor" value={`${view.titulos_com_credor} de ${view.titulos.length}`} />
          )}
        </div>
      </Card>

      {/* Aviso de lista parcial (§14.6) */}
      {constam && !view.completo && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-2.5 text-sm text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300">
          A fonte retornou apenas a 1ª página do site — a lista abaixo pode ser
          parcial em relação ao total de {view.qtd_total} título(s).
        </div>
      )}

      {constam && temDetalhe && (
        <Card>
          <div className={cardTokens.body}>
            <DataTable<ProtestoTituloView>
              data={view.titulos}
              columns={columns}
              density="compact"
              renderFooter={(rows) => {
                const soma = rows.reduce((acc, r) => acc + (r.valor ?? 0), 0)
                return (
                  <div className="flex items-center justify-between px-3 py-2">
                    <span className={tableTokens.cellSecondary}>
                      {rows.length} {rows.length === 1 ? "título" : "títulos"}
                    </span>
                    <span className={cx(tableTokens.cellNumber, "font-semibold")}>
                      {fmtBRL(soma)}
                    </span>
                  </div>
                )
              }}
            />
          </div>
        </Card>
      )}

      {constam && !temDetalhe && (
        <Card>
          <p className={cx(cardTokens.bodyComfortable, "text-sm text-gray-500 dark:text-gray-400")}>
            Constam {view.qtd_total} protesto(s) ({fmtBRL(view.valor_total)}), mas a
            fonte não detalhou por título.
          </p>
        </Card>
      )}

      <p className="px-1 text-xs text-gray-400 dark:text-gray-500">
        Fonte: Infosimples · consultado em{" "}
        {new Date(view.consultado_em).toLocaleString("pt-BR")}. {view.nota}
      </p>
    </div>
  )
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[11px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {label}
      </span>
      <span className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
        {value}
      </span>
    </div>
  )
}
