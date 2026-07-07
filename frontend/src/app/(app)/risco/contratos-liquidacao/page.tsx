// src/app/(app)/risco/contratos-liquidacao/page.tsx
//
// Risco · Contratos de liquidação — primeira tela do módulo Risco.
//
// Curadoria do "contrato de liquidação por produto" (programa antifraude de
// auto-liquidação): para cada produto o curador DECLARA fluxo esperado /
// boleto / baixa manual; a tela mostra o comportamento OBSERVADO no warehouse
// e destaca divergências (item de curadoria ou sinal). Editar cria uma NOVA
// versão (append-only) — o motor de sinais lê sempre a versão ativa.
//
// Pattern: ListagemCrudInline (mesma anatomia de /integracoes/coletores),
// sem "+ Novo": o universo de produtos vem do ERP (wh_dim_produto); produto
// sem contrato aparece como "Em aberto".
// Estado da URL (deep-linkável): ?selected=<sigla> → drawer de curadoria.
//

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { RiScales3Line } from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import { format, parseISO } from "date-fns"
import { toast } from "sonner"

import { Divider } from "@/components/tremor/Divider"
import { DataTableShell, DrillDownSheet, PageHeader } from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type { ContratoLiquidacaoRow } from "@/lib/api-client"
import {
  useContratosLiquidacao,
  useDefinirContratoLiquidacao,
  useVersoesContratoLiquidacao,
} from "@/lib/hooks/risco"
import {
  BAIXA_MANUAL_LABELS,
  BOLETO_LABELS,
  DIVERGENCIA_LABELS,
  FLUXO_LABELS,
  fromContrato,
  toUpdatePayload,
  type ContratoLiquidacaoFormValues,
} from "@/lib/schemas/contrato-liquidacao-schema"
import { cx } from "@/lib/utils"

import { ContratoForm } from "./_components/ContratoForm"

// Janela do perfil observado. O corpus de boletos (CNAB) começa em dez/2025 —
// janela longa demais deprimiria o % bancarizado com títulos antigos sem CNAB.
const JANELA_DIAS = 180

// ───────────────────────────────────────────────────────────────────────────
// Cells
// ───────────────────────────────────────────────────────────────────────────

function DeclaradoCell({ value }: { value: string | null }) {
  if (value === null) {
    return <span className={cx(tableTokens.badge, tableTokens.badgeNeutral)}>Em aberto</span>
  }
  return <span className={tableTokens.cellText}>{value}</span>
}

function ObservadoCell({ row }: { row: ContratoLiquidacaoRow }) {
  const obs = row.observado
  if (obs.qtd_titulos === 0) {
    return (
      <span className={tableTokens.cellMuted}>sem títulos em {obs.janela_dias}d</span>
    )
  }
  const tooltip =
    `${obs.qtd_titulos.toLocaleString("pt-BR")} títulos nos últimos ${obs.janela_dias} dias · ` +
    `${obs.qtd_bancarizados.toLocaleString("pt-BR")} com boleto · ` +
    `${obs.qtd_baixa_manual_bancarizados.toLocaleString("pt-BR")} baixados à mão`
  return (
    <span className={tableTokens.cellSecondary} title={tooltip}>
      <span className={tableTokens.cellNumber}>
        {obs.pct_bancarizado?.toLocaleString("pt-BR") ?? "0"}%
      </span>{" "}
      boleto
      {obs.pct_baixa_manual_bancarizados !== null && (
        <>
          {" · "}
          <span className={tableTokens.cellNumber}>
            {obs.pct_baixa_manual_bancarizados.toLocaleString("pt-BR")}%
          </span>{" "}
          baixa manual
        </>
      )}
    </span>
  )
}

function DivergenciasCell({ row }: { row: ContratoLiquidacaoRow }) {
  if (row.divergencias.length === 0) {
    return <span className={tableTokens.cellMuted}>—</span>
  }
  return (
    <div className="flex flex-wrap gap-1">
      {row.divergencias.map((d) => (
        <span key={d} className={cx(tableTokens.badge, tableTokens.badgeWarning)}>
          {DIVERGENCIA_LABELS[d] ?? d}
        </span>
      ))}
    </div>
  )
}

function HistoricoVersoes({ sigla }: { sigla: string }) {
  const q = useVersoesContratoLiquidacao(sigla)
  if (q.isLoading) {
    return <p className={tableTokens.cellMuted}>Carregando histórico…</p>
  }
  const versoes = q.data ?? []
  if (versoes.length === 0) {
    return (
      <p className={tableTokens.cellMuted}>
        Nenhuma versão ainda — o contrato está em aberto.
      </p>
    )
  }
  return (
    <ul className="flex flex-col gap-2">
      {versoes.map((v) => (
        <li key={v.version} className="flex flex-col gap-0.5">
          <span className={tableTokens.cellStrong}>
            v{v.version}
            <span className={cx(tableTokens.cellSecondary, "ml-2 font-normal")}>
              {format(parseISO(v.created_at), "dd/MM/yyyy HH:mm")}
            </span>
          </span>
          <span className={tableTokens.cellSecondary}>
            {FLUXO_LABELS[v.fluxo_esperado]} · Boleto {BOLETO_LABELS[v.boleto].toLowerCase()} ·
            Baixa manual {BAIXA_MANUAL_LABELS[v.baixa_manual].toLowerCase()}
          </span>
          {v.justificativa && (
            <span className={tableTokens.cellMuted}>{v.justificativa}</span>
          )}
        </li>
      ))}
    </ul>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

const col = createColumnHelper<ContratoLiquidacaoRow>()

export default function ContratosLiquidacaoPage() {
  const router = useRouter()
  const sp = useSearchParams()
  const selectedSigla = sp.get("selected")

  const contratosQuery = useContratosLiquidacao(JANELA_DIAS)
  const definirMut = useDefinirContratoLiquidacao()

  const data = contratosQuery.data ?? []
  const selected = React.useMemo(
    () =>
      selectedSigla
        ? (data.find((c) => c.produto_sigla === selectedSigla) ?? null)
        : null,
    [data, selectedSigla],
  )

  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState<
    "todos" | "definidos" | "em_aberto" | "divergentes"
  >("todos")

  const setSelected = React.useCallback(
    (sigla: string | null) => {
      const params = new URLSearchParams(sp.toString())
      if (sigla) params.set("selected", sigla)
      else params.delete("selected")
      const qs = params.toString()
      router.push(qs ? `?${qs}` : "?")
    },
    [router, sp],
  )

  const openEdit = React.useCallback(
    (c: ContratoLiquidacaoRow) => setSelected(c.produto_sigla),
    [setSelected],
  )
  const closeSheet = React.useCallback(() => setSelected(null), [setSelected])

  const handleSubmit = React.useCallback(
    async (values: ContratoLiquidacaoFormValues) => {
      if (!selected) return
      try {
        const updated = await definirMut.mutateAsync({
          sigla: selected.produto_sigla,
          payload: toUpdatePayload(values),
        })
        toast.success(
          `Contrato de ${updated.produto_nome} salvo (v${updated.version}).`,
        )
        closeSheet()
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : "Falha ao salvar o contrato.",
        )
      }
    },
    [definirMut, selected, closeSheet],
  )

  const columns = React.useMemo<ColumnDef<ContratoLiquidacaoRow, unknown>[]>(
    () => [
      col.accessor("produto_nome", {
        header: "Produto",
        size: 220,
        cell: (info) => (
          <span className={tableTokens.cellStrong}>
            {info.getValue()}
            <span className={cx(tableTokens.cellSecondary, "ml-1.5 font-normal")}>
              ({info.row.original.produto_sigla})
            </span>
          </span>
        ),
      }) as ColumnDef<ContratoLiquidacaoRow, unknown>,
      col.display({
        id: "fluxo",
        header: "Fluxo esperado",
        size: 150,
        cell: ({ row }) => (
          <DeclaradoCell
            value={
              row.original.fluxo_esperado
                ? FLUXO_LABELS[row.original.fluxo_esperado]
                : null
            }
          />
        ),
      }) as ColumnDef<ContratoLiquidacaoRow, unknown>,
      col.display({
        id: "boleto",
        header: "Boleto",
        size: 110,
        cell: ({ row }) => (
          <DeclaradoCell
            value={row.original.boleto ? BOLETO_LABELS[row.original.boleto] : null}
          />
        ),
      }) as ColumnDef<ContratoLiquidacaoRow, unknown>,
      col.display({
        id: "baixa_manual",
        header: "Baixa manual",
        size: 110,
        cell: ({ row }) => (
          <DeclaradoCell
            value={
              row.original.baixa_manual
                ? BAIXA_MANUAL_LABELS[row.original.baixa_manual]
                : null
            }
          />
        ),
      }) as ColumnDef<ContratoLiquidacaoRow, unknown>,
      col.display({
        id: "observado",
        header: `Observado (${JANELA_DIAS}d)`,
        size: 200,
        cell: ({ row }) => <ObservadoCell row={row.original} />,
      }) as ColumnDef<ContratoLiquidacaoRow, unknown>,
      col.display({
        id: "divergencias",
        header: "Divergência",
        size: 200,
        cell: ({ row }) => <DivergenciasCell row={row.original} />,
      }) as ColumnDef<ContratoLiquidacaoRow, unknown>,
      col.accessor("version", {
        header: "Versão",
        size: 90,
        cell: (info) => {
          const v = info.getValue()
          if (v === null) return <span className={tableTokens.cellMuted}>—</span>
          const quando = info.row.original.atualizado_em
          return (
            <span className={tableTokens.cellSecondary}>
              v{v}
              {quando && (
                <span className="ml-1.5">
                  {format(parseISO(quando), "dd/MM/yyyy")}
                </span>
              )}
            </span>
          )
        },
      }) as ColumnDef<ContratoLiquidacaoRow, unknown>,
    ],
    [],
  )

  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Contratos de liquidação"
        info="Para cada produto, o contrato declara como a liquidação deve acontecer (fluxo, boleto, baixa manual). O comportamento observado no warehouse é comparado à declaração: divergência é item de curadoria — e alimenta o motor de sinais antifraude. Editar cria uma nova versão; o histórico fica auditável."
        subtitle="Risco · Curadoria"
      />

      <DataTableShell<ContratoLiquidacaoRow>
        data={data}
        columns={columns}
        loading={contratosQuery.isLoading}
        error={contratosQuery.error}
        onRetry={() => contratosQuery.refetch()}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: "Buscar por produto ou sigla...",
        }}
        segments={{
          value: segment,
          onChange: (v) => setSegment(v as typeof segment),
          options: [
            { value: "todos", label: "Todos", filter: () => true },
            { value: "definidos", label: "Definidos", filter: (c) => !c.em_aberto },
            { value: "em_aberto", label: "Em aberto", filter: (c) => c.em_aberto },
            {
              value: "divergentes",
              label: "Com divergência",
              filter: (c) => c.divergencias.length > 0,
            },
          ],
        }}
        itemNoun={{ singular: "produto", plural: "produtos" }}
        onRowClick={openEdit}
        emptyState={{
          icon: RiScales3Line,
          title: "Nenhum produto na dimensão",
          description:
            "Os produtos chegam do ERP via sincronização (wh_dim_produto). Assim que existirem, cada um aparece aqui para curadoria do contrato de liquidação.",
        }}
      />

      {/* Drawer: curadoria do contrato */}
      <DrillDownSheet
        open={selected !== null}
        onClose={closeSheet}
        title={
          selected
            ? `${selected.produto_nome} (${selected.produto_sigla})`
            : ""
        }
        size="md"
      >
        {selected && (
          <div className="flex flex-col gap-5 p-6">
            <div className="flex flex-col gap-1">
              <span className={tableTokens.header}>Observado na janela</span>
              <ObservadoCell row={selected} />
              {selected.divergencias.length > 0 && <DivergenciasCell row={selected} />}
            </div>

            <Divider className="my-0" />

            <ContratoForm
              key={`${selected.produto_sigla}-v${selected.version ?? 0}`}
              initial={fromContrato(selected)}
              submitting={definirMut.isPending}
              submitLabel={
                selected.em_aberto ? "Definir contrato" : "Salvar como nova versão"
              }
              onSubmit={handleSubmit}
              onCancel={closeSheet}
            />

            <Divider className="my-0" />

            <div className="flex flex-col gap-2">
              <span className={tableTokens.header}>Histórico de versões</span>
              <HistoricoVersoes sigla={selected.produto_sigla} />
            </div>
          </div>
        )}
      </DrillDownSheet>
    </div>
  )
}
