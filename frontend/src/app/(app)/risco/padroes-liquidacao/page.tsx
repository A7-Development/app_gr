// src/app/(app)/risco/padroes-liquidacao/page.tsx
//
// Risco · Liquidações · Padrões de liquidação — painel 100% DETERMINÍSTICO.
// Só fatos (deteccao_score.features) + conclusões determinísticas (regra_dura);
// o score do modelo é ignorado (vive em /risco/cedentes).
//
// Explicação por CAMADAS de zoom (decisão Ricardo 2026-07-10):
//   - linha  -> reason chips + severidade (escanear/comparar N cedentes)
//   - drawer -> narrativa determinística de UM cedente (sem rolagem) + botão
//               pro detalhe extremo das liquidações (janela dedicada futura)
// Reason codes = modelo de adverse-action do crédito: vocabulário fechado,
// padronizado, comparável — nunca prosa por linha.
//

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { RiPulseLine } from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { DataTableShell, DrillDownSheet, KpiBand, PageHeader, SegmentSwitch } from "@/design-system/components"
import type { KpiBandItem } from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type { CedentePerfilRow, JanelaLiquidacao } from "@/lib/api-client"
import { usePadroesLiquidacao } from "@/lib/hooks/risco"
import { cx } from "@/lib/utils"
import { CedenteDrawerBody } from "./_components/CedenteDrawer"
import { ReasonChips, SeverityCell } from "./_components/chips"

const brl = (v: number) =>
  v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 })

const JANELAS: { value: JanelaLiquidacao; label: string }[] = [
  { value: "7d", label: "7d" },
  { value: "15d", label: "15d" },
  { value: "30d", label: "30d" },
  { value: "90d", label: "90d" },
  { value: "12m", label: "12m" },
  { value: "tudo", label: "Tudo" },
]

function RecenciaCell({ iso }: { iso: string | null }) {
  if (!iso) return <span className={tableTokens.cellMuted}>—</span>
  const dias = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
  const label = dias <= 0 ? "hoje" : `há ${dias}d`
  return (
    <span
      className={cx(tableTokens.cellSecondary, dias > 90 && "text-amber-600 dark:text-amber-400")}
      title={new Date(iso).toLocaleString("pt-BR")}
    >
      {label}
    </span>
  )
}

function DeltaCell({ delta, novo }: { delta: number | null; novo: boolean }) {
  if (novo) return <span className={cx(tableTokens.badge, tableTokens.badgeWarning)} title="Sem alerta na janela anterior">novo</span>
  if (delta === null || delta === 0) return <span className={tableTokens.cellMuted}>—</span>
  const piorou = delta > 0
  return (
    <span
      className={cx(tableTokens.cellNumber, piorou ? "text-red-600 dark:text-red-400" : "text-emerald-600 dark:text-emerald-400")}
      title={`Variação de alertas vs janela anterior: ${piorou ? "+" : ""}${delta}`}
    >
      {piorou ? "▲" : "▼"} {Math.abs(delta)}
    </span>
  )
}

const col = createColumnHelper<CedentePerfilRow>()

export default function PadroesLiquidacaoPage() {
  const router = useRouter()
  const sp = useSearchParams()
  const selectedDoc = sp.get("selected")

  const [janela, setJanela] = React.useState<JanelaLiquidacao>("30d")
  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState<"todos" | "alerta" | "conta">("todos")

  const query = usePadroesLiquidacao(janela)
  const cedentes = React.useMemo(() => query.data?.cedentes ?? [], [query.data])
  const kpis = query.data?.kpis

  const selected = React.useMemo(
    () => (selectedDoc ? (cedentes.find((c) => c.cedente_documento === selectedDoc) ?? null) : null),
    [cedentes, selectedDoc],
  )

  const setSelected = React.useCallback(
    (doc: string | null) => {
      const params = new URLSearchParams(sp.toString())
      if (doc) params.set("selected", doc)
      else params.delete("selected")
      const qs = params.toString()
      router.push(qs ? `?${qs}` : "?")
    },
    [router, sp],
  )

  const kpiItems = React.useMemo<KpiBandItem[]>(() => {
    if (!kpis) return []
    const deltaAlerta =
      kpis.n_alerta_anterior !== null ? kpis.n_alerta_total - kpis.n_alerta_anterior : null
    return [
      {
        eyebrow: "LIQUIDADO · JANELA",
        value: brl(kpis.valor_total),
        sub: `${kpis.n_liq_total.toLocaleString("pt-BR")} liquidações · ${kpis.n_cedentes} cedentes`,
      },
      {
        eyebrow: "ALERTAS DETERMINÍSTICOS",
        value: kpis.n_alerta_total.toLocaleString("pt-BR"),
        delta:
          deltaAlerta !== null && deltaAlerta !== 0
            ? { value: `${deltaAlerta > 0 ? "+" : ""}${deltaAlerta}`, tone: deltaAlerta > 0 ? "negative" : "positive" }
            : undefined,
        sub: "regra dura na janela",
      },
      { eyebrow: "CONTA DO CEDENTE", value: `${kpis.pct_conta_cedente}%`, sub: "das liquidações" },
      { eyebrow: "FORA DA PRAÇA DO SACADO", value: `${kpis.pct_fora_praca}%`, sub: "das liquidações" },
      { eyebrow: "CANAL DE ATENÇÃO", value: `${kpis.pct_canal_atencao}%`, sub: "digital/coop/IP/SCD/fin." },
    ]
  }, [kpis])

  const columns = React.useMemo<ColumnDef<CedentePerfilRow, unknown>[]>(
    () => [
      col.accessor("cedente_nome", {
        header: "Cedente",
        cell: (info) => {
          const nome = (info.getValue() as string | null) ?? info.row.original.cedente_documento
          return (
            <span className={cx(tableTokens.cellStrong, "block truncate")} title={nome}>
              {nome}
            </span>
          )
        },
      }) as ColumnDef<CedentePerfilRow, unknown>,
      col.display({
        id: "alerta",
        header: () => <span title="Severidade determinística: crítico = regra dura; atenção = red flag forte.">Alerta</span>,
        size: 100,
        cell: ({ row }) => <SeverityCell row={row.original} />,
      }) as ColumnDef<CedentePerfilRow, unknown>,
      col.display({
        id: "porque",
        header: () => <span title="Reason codes: os drivers dominantes (vocabulário fechado, no máx. 3).">Por quê</span>,
        size: 236,
        cell: ({ row }) => <ReasonChips row={row.original} />,
      }) as ColumnDef<CedentePerfilRow, unknown>,
      col.accessor("n_liq", {
        header: () => <span title="Nº de liquidações na janela">Nº Liq.</span>,
        size: 74,
        meta: { align: "right" },
        cell: (info) => <span className={tableTokens.cellNumber}>{(info.getValue() as number).toLocaleString("pt-BR")}</span>,
      }) as ColumnDef<CedentePerfilRow, unknown>,
      col.accessor("valor", {
        header: () => <span title="Valor liquidado na janela">R$ Liq.</span>,
        size: 104,
        meta: { align: "right" },
        cell: (info) => <span className={tableTokens.cellNumberSecondary}>{brl(info.getValue() as number)}</span>,
      }) as ColumnDef<CedentePerfilRow, unknown>,
      col.accessor("ultima_liq", {
        header: () => <span title="Última liquidação (recência)">Últ. liq.</span>,
        size: 82,
        meta: { align: "center" },
        cell: (info) => <RecenciaCell iso={info.getValue() as string | null} />,
      }) as ColumnDef<CedentePerfilRow, unknown>,
      col.display({
        id: "delta",
        header: () => <span title="Variação de alertas vs a janela anterior.">Δ</span>,
        size: 60,
        meta: { align: "center" },
        cell: ({ row }) => <DeltaCell delta={row.original.delta_alerta} novo={row.original.cedente_novo} />,
      }) as ColumnDef<CedentePerfilRow, unknown>,
    ],
    [],
  )

  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Padrões de liquidação"
        info="Perfil 100% determinístico das liquidações: só fatos e conclusões determinísticas (regra dura); o score do modelo é ignorado (vive em 'Risco de cedentes'). Explicação em camadas: na linha, reason codes (os drivers dominantes, escaneáveis); ao clicar num cedente, a narrativa da história dele + os números. A janela filtra todos os agregados; Δ compara com a janela anterior."
        subtitle="Risco · Liquidações"
      />

      <div className="flex items-center justify-between gap-3">
        <SegmentSwitch<JanelaLiquidacao>
          options={JANELAS}
          value={janela}
          onChange={setJanela}
          ariaLabel="Janela temporal (sobre a data do evento de liquidação)"
        />
        <span className={tableTokens.cellMuted}>
          Janela sobre a data do evento · clique num cedente para a leitura completa
        </span>
      </div>

      <KpiBand items={kpiItems} loading={query.isLoading && !query.data} />

      <DataTableShell<CedentePerfilRow>
        data={cedentes}
        columns={columns}
        loading={query.isLoading && !query.data}
        error={query.error}
        onRetry={() => query.refetch()}
        tableLayout="fixed"
        minWidth={760}
        onRowClick={(c) => setSelected(c.cedente_documento)}
        search={{ value: search, onChange: setSearch, placeholder: "Buscar cedente..." }}
        segments={{
          value: segment,
          onChange: (v) => setSegment(v as typeof segment),
          options: [
            { value: "todos", label: "Todos", filter: () => true },
            { value: "alerta", label: "Em alerta", filter: (c) => c.n_alerta > 0 },
            { value: "conta", label: "Conta do cedente", filter: (c) => (c.sinais.conta_cedente ?? 0) > 0 },
          ],
        }}
        itemNoun={{ singular: "cedente", plural: "cedentes" }}
        emptyState={{
          icon: RiPulseLine,
          title: "Sem liquidações na janela",
          description:
            "Nenhuma liquidação pontuada no período. Amplie a janela ou rode o scoring (automático a cada 6h ou pelo botão \"Pontuar agora\" na curadoria de liquidações).",
        }}
      />

      <DrillDownSheet
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={selected ? (selected.cedente_nome ?? selected.cedente_documento) : ""}
        size="md"
      >
        {selected && (
          <CedenteDrawerBody
            row={selected}
            janelaLabel={janela}
            onVerLiquidacoes={() =>
              router.push(
                `/risco/curadoria-liquidacoes?cedente=${encodeURIComponent(
                  selected.cedente_nome ?? selected.cedente_documento,
                )}`,
              )
            }
          />
        )}
      </DrillDownSheet>
    </div>
  )
}
