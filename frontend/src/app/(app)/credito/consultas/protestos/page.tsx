// src/app/(app)/credito/consultas/protestos/page.tsx
//
// Crédito › Consultas › Protestos — console de consulta avulsa (por CNPJ/CPF).
//
// Dispara POST /credito/consultas/protesto (CENPROT/IEPTB via Infosimples):
// consulta nacional (existência + agregados + títulos) + detalhe dos cartórios
// de SP (onde aparece o CREDOR — cedente/apresentante). Por força do Provimento
// CNJ 225/2026, a consulta nacional NÃO identifica o credor; fora de SP ele não
// vem. A tabela reconcilia com o headline (§14.6): o rodapé soma os títulos.

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

const COLUMNS: ColumnDef<ProtestoTituloView, unknown>[] = [
  {
    id: "cartorio",
    header: "Cartório",
    cell: ({ row }) => (
      <span className={cx(tableTokens.cellText, "truncate")}>
        {row.original.cartorio ?? "—"}
      </span>
    ),
  },
  {
    id: "praca",
    header: "Cidade/UF",
    cell: ({ row }) => {
      const { cidade, uf } = row.original
      const txt = [cidade, uf].filter(Boolean).join(" / ") || "—"
      return <span className={tableTokens.cellSecondary}>{txt}</span>
    },
  },
  {
    id: "data",
    header: "Data",
    cell: ({ row }) => (
      <span className={tableTokens.cellNumberSecondary}>
        {fmtData(row.original.data_protesto)}
      </span>
    ),
  },
  {
    id: "valor",
    header: "Valor",
    meta: { align: "right" },
    cell: ({ row }) => (
      <span className={cx(tableTokens.cellNumber, "text-right")}>
        {fmtBRL(row.original.valor)}
      </span>
    ),
  },
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

export default function ConsultaProtestosPage() {
  const [documento, setDocumento] = React.useState("")
  const [result, setResult] = React.useState<ProtestoView | null>(null)

  const consulta = useMutation({
    mutationFn: (doc: string) => credito.consultas.protesto({ documento: doc }),
    onSuccess: (view) => {
      setResult(view)
      if (!view.encontrado) {
        toast.error(view.message ?? view.mensagem ?? "Consulta não completou.")
      }
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
      <PageHeader
        title="Protestos"
        subtitle="Crédito · Consultas"
        info="Consulta protestos de um CNPJ/CPF no CENPROT/IEPTB. A consulta nacional traz existência, quantidade e valor; o credor (cedente/apresentante) só aparece no detalhe de cartórios de SP — por força do Provimento CNJ 225/2026, a base pública nacional não identifica o credor."
      />

      {/* Consulta */}
      <Card>
        <form onSubmit={handleSubmit} className={cx(cardTokens.bodyComfortable)}>
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

          {consulta.isPending && (
            <p className="mt-3 flex items-center gap-2 text-sm text-blue-700 dark:text-blue-300">
              <span className="size-1.5 animate-pulse rounded-full bg-blue-500" aria-hidden />
              Consultando o CENPROT/IEPTB (nacional + detalhe dos cartórios de SP).
              Pode levar até ~1 min.
            </p>
          )}
        </form>
      </Card>

      {/* Resultado */}
      {result !== null && !consulta.isPending && (
        <ResultadoConsulta view={result} />
      )}
    </div>
  )
}

function ResultadoConsulta({ view }: { view: ProtestoView }) {
  if (!view.encontrado) {
    return (
      <Card>
        <div className={cx(cardTokens.bodyComfortable, "flex items-start gap-3")}>
          <RiAlarmWarningLine
            className="size-5 shrink-0 text-amber-500"
            aria-hidden
          />
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

  return (
    <div className="flex flex-col gap-4">
      {/* Headline */}
      <Card>
        <div className={cx(cardTokens.bodyComfortable, "flex flex-wrap items-center gap-x-8 gap-y-3")}>
          <div className="flex items-center gap-2">
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
          </div>
          <Stat label="Títulos" value={String(view.qtd_total)} />
          <Stat label="Valor total" value={fmtBRL(view.valor_total)} />
          <Stat label="Com credor" value={`${view.titulos_com_credor} de ${view.titulos.length}`} />
          <Stat label="Cartórios SP detalhados" value={String(view.cartorios_sp_detalhados)} />
        </div>
      </Card>

      {/* Tabela de títulos (reconcilia com o headline — §14.6) */}
      {constam && temDetalhe && (
        <Card>
          <div className={cardTokens.body}>
            <DataTable<ProtestoTituloView>
              data={view.titulos}
              columns={COLUMNS}
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

      {/* Constam protestos mas sem detalhe por título (só agregado nacional) */}
      {constam && !temDetalhe && (
        <Card>
          <p className={cx(cardTokens.bodyComfortable, "text-sm text-gray-500 dark:text-gray-400")}>
            A fonte retornou apenas o agregado nacional ({view.qtd_total} título(s),
            {" "}
            {fmtBRL(view.valor_total)}) — sem detalhe por título. O detalhe com
            cartório, data e credor só está disponível para cartórios de SP.
          </p>
        </Card>
      )}

      {/* Proveniência */}
      <p className="px-1 text-xs text-gray-400 dark:text-gray-500">
        Fonte: CENPROT/IEPTB via Infosimples · consultado em{" "}
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
