// src/app/(app)/risco/cedentes/page.tsx
//
// Risco · Risco de cedentes — o PRODUTO do programa de detecção (decisão
// Ricardo 2026-07-08): a unidade de decisão do FIDC é o CEDENTE, e cada
// modelo do catálogo de detecção é UM INDICADOR que contribui com um
// subscore. Esta página lê a série `cedente_risco_snapshot` (consolidada
// após cada scoring) e mostra o risco COMPOSTO + a decomposição por
// indicador + tendência — o instrumento do comitê antes de renovar limite.
//
// Multivariável por desenho: novos indicadores (lastro, Benford, grafo...)
// entram como novas linhas do snapshot — esta tela itera sobre
// `indicadores[]` e não precisa mudar.
//
// Pattern: ListagemComDrilldown via DataTableShell (client-side: ~350
// cedentes) + DrillDownSheet com a composição explicável (§14.3).
//

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import {
  RiArrowDownLine,
  RiArrowUpLine,
  RiShieldCheckLine,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import { format, parseISO } from "date-fns"

import { Button } from "@/components/tremor/Button"
import { Divider } from "@/components/tremor/Divider"
import { DataTableShell, DrillDownSheet, PageHeader } from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type { CedenteRiscoRow } from "@/lib/api-client"
import { useCedentesRisco } from "@/lib/hooks/risco"
import { cx } from "@/lib/utils"

// Nome humano de cada indicador do catálogo (novos entram aqui).
const INDICADOR_LABELS: Record<string, string> = {
  liquidacao_boleto: "Liquidação de boleto",
  lastro_inconsistente: "Lastro documental",
}

const brl = (v: number) =>
  v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 })

function RiscoBadge({ valor }: { valor: number }) {
  const classe =
    valor >= 70
      ? tableTokens.badgeDanger
      : valor >= 40
        ? tableTokens.badgeWarning
        : tableTokens.badgeNeutral
  return <span className={cx(tableTokens.badge, classe)}>{Math.round(valor)}</span>
}

function TendenciaCell({ delta }: { delta: number | null }) {
  if (delta === null || Math.abs(delta) < 0.5) {
    return <span className={tableTokens.cellMuted}>estável</span>
  }
  const piorou = delta > 0
  return (
    <span
      className={cx(
        tableTokens.cellNumber,
        piorou ? "text-red-600 dark:text-red-400" : "text-emerald-600 dark:text-emerald-400",
      )}
      title={`Variação de ${delta > 0 ? "+" : ""}${delta.toFixed(1)} pontos na janela`}
    >
      {piorou ? (
        <RiArrowUpLine className="inline size-3.5" aria-hidden />
      ) : (
        <RiArrowDownLine className="inline size-3.5" aria-hidden />
      )}
      {Math.abs(delta).toFixed(0)}
    </span>
  )
}

const col = createColumnHelper<CedenteRiscoRow>()

export default function CedentesRiscoPage() {
  const router = useRouter()
  const sp = useSearchParams()
  const selectedDoc = sp.get("selected")

  const cedentesQuery = useCedentesRisco(30)
  const data = React.useMemo(() => cedentesQuery.data ?? [], [cedentesQuery.data])

  const selected = React.useMemo(
    () => (selectedDoc ? (data.find((c) => c.cedente_documento === selectedDoc) ?? null) : null),
    [data, selectedDoc],
  )

  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState<"todos" | "criticos" | "alto" | "piorando">(
    "todos",
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

  const columns = React.useMemo<ColumnDef<CedenteRiscoRow, unknown>[]>(
    () => [
      col.accessor("cedente_nome", {
        header: "Cedente",
        size: 240,
        cell: (info) => {
          const nome = (info.getValue() as string | null) ?? info.row.original.cedente_documento
          return (
            <span
              className={cx(tableTokens.cellStrong, "block max-w-[230px] truncate")}
              title={nome}
            >
              {nome}
            </span>
          )
        },
      }) as ColumnDef<CedenteRiscoRow, unknown>,
      col.accessor("risco", {
        header: "Risco",
        size: 72,
        cell: (info) => <RiscoBadge valor={info.getValue() as number} />,
      }) as ColumnDef<CedenteRiscoRow, unknown>,
      col.accessor("tendencia", {
        header: "Tendência 30d",
        size: 100,
        cell: (info) => <TendenciaCell delta={info.getValue() as number | null} />,
      }) as ColumnDef<CedenteRiscoRow, unknown>,
      col.accessor("carteira_atual", {
        header: () => (
          <span title="Posição em aberto do cedente no ERP (risco total: vencido + a vencer). É a exposição atual — não confundir com o volume liquidado suspeito.">
            Carteira atual
          </span>
        ),
        size: 120,
        cell: (info) => {
          const v = info.getValue() as number | null
          return v === null ? (
            <span className={tableTokens.cellMuted}>—</span>
          ) : (
            <span className={tableTokens.cellNumber}>{brl(v)}</span>
          )
        },
      }) as ColumnDef<CedenteRiscoRow, unknown>,
      col.accessor("valor_em_risco", {
        header: () => (
          <span title="Valor JÁ PAGO em liquidações que o modelo marcou como suspeitas (score ≥ 0,7 ou evento crítico). Retrospectivo — não é exposição em aberto.">
            R$ liq. suspeito
          </span>
        ),
        size: 120,
        cell: (info) => (
          <span
            className={cx(
              tableTokens.cellNumber,
              (info.getValue() as number) > 0 && "font-semibold",
            )}
          >
            {brl(info.getValue() as number)}
          </span>
        ),
      }) as ColumnDef<CedenteRiscoRow, unknown>,
      col.accessor("valor_avaliado", {
        header: "R$ avaliado",
        size: 120,
        cell: (info) => (
          <span className={tableTokens.cellNumberSecondary}>
            {brl(info.getValue() as number)}
          </span>
        ),
      }) as ColumnDef<CedenteRiscoRow, unknown>,
      col.accessor("n_criticos", {
        header: () => (
          <span title="Nº de liquidações que dispararam a regra determinística (padrão crítico): sacado de outra cidade pagando na agência do cedente.">
            Eventos críticos
          </span>
        ),
        size: 110,
        cell: (info) => {
          const n = info.getValue() as number
          return n > 0 ? (
            <span className={cx(tableTokens.badge, tableTokens.badgeDanger)}>{n}</span>
          ) : (
            <span className={tableTokens.cellMuted}>—</span>
          )
        },
      }) as ColumnDef<CedenteRiscoRow, unknown>,
      col.accessor("n_alto_risco", {
        header: "Eventos ≥70%",
        size: 100,
        cell: (info) => (
          <span className={tableTokens.cellNumber}>{info.getValue() as number}</span>
        ),
      }) as ColumnDef<CedenteRiscoRow, unknown>,
      col.display({
        id: "indicadores",
        header: "Indicadores",
        size: 170,
        cell: ({ row }) => (
          <div className="flex flex-wrap gap-1">
            {row.original.indicadores.map((i) => (
              <span
                key={i.indicador}
                className={cx(tableTokens.badge, tableTokens.badgeNeutral)}
                title={`${INDICADOR_LABELS[i.indicador] ?? i.indicador}: subscore ${i.subscore}`}
              >
                {(INDICADOR_LABELS[i.indicador] ?? i.indicador).toLowerCase()}{" "}
                {Math.round(i.subscore)}
              </span>
            ))}
          </div>
        ),
      }) as ColumnDef<CedenteRiscoRow, unknown>,
    ],
    [],
  )

  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Risco de cedentes"
        info="Risco composto por cedente, combinando os indicadores do programa de detecção (hoje: liquidação de boleto; novos indicadores entram na composição conforme forem criados). Score 0–100 ponderado por valor, com piso quando há evento crítico. 'R$ liq. suspeito' é retrospectivo (valor já pago em liquidações suspeitas); 'Carteira atual' é a exposição em aberto no ERP. Use antes de renovar ou ampliar limite — o drill mostra a decomposição e leva às liquidações que explicam o número."
        subtitle="Risco · Detecção de anomalias"
      />

      <DataTableShell<CedenteRiscoRow>
        data={data}
        columns={columns}
        loading={cedentesQuery.isLoading}
        error={cedentesQuery.error}
        onRetry={() => cedentesQuery.refetch()}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: "Buscar cedente...",
        }}
        segments={{
          value: segment,
          onChange: (v) => setSegment(v as typeof segment),
          options: [
            { value: "todos", label: "Todos", filter: () => true },
            {
              value: "criticos",
              label: "Com evento crítico",
              filter: (c) => c.n_criticos > 0,
            },
            { value: "alto", label: "Risco ≥ 40", filter: (c) => c.risco >= 40 },
            {
              value: "piorando",
              label: "Piorando",
              filter: (c) => (c.tendencia ?? 0) > 0.5,
            },
          ],
        }}
        itemNoun={{ singular: "cedente", plural: "cedentes" }}
        onRowClick={(c) => setSelected(c.cedente_documento)}
        emptyState={{
          icon: RiShieldCheckLine,
          title: "Sem consolidação de risco ainda",
          description:
            "O painel é alimentado após cada rodada de scoring (automática a cada 6h ou pelo botão \"Pontuar agora\" na curadoria de liquidações).",
        }}
      />

      <DrillDownSheet
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={selected ? (selected.cedente_nome ?? selected.cedente_documento) : ""}
        size="md"
      >
        {selected && (
          <div className="flex flex-col gap-5 p-6">
            <div className="flex items-center gap-3">
              <RiscoBadge valor={selected.risco} />
              <span className={tableTokens.cellSecondary}>
                Risco composto · consolidado em{" "}
                {format(parseISO(String(selected.data_ref)), "dd/MM/yyyy")}
              </span>
              <TendenciaCell delta={selected.tendencia} />
            </div>

            <div className="flex flex-col gap-1">
              <span className={tableTokens.header}>Carteira atual</span>
              <span className={tableTokens.cellSecondary}>
                {selected.carteira_atual === null
                  ? "Sem posição em aberto no ERP"
                  : `${brl(selected.carteira_atual)} em aberto (vencido + a vencer)`}
              </span>
            </div>

            <div className="flex flex-col gap-1">
              <span className={tableTokens.header}>Liquidações suspeitas (retrospectivo)</span>
              <span className={tableTokens.cellSecondary}>
                {brl(selected.valor_em_risco)} liquidado suspeito de{" "}
                {brl(selected.valor_avaliado)} avaliados ·{" "}
                {selected.n_eventos.toLocaleString("pt-BR")} liquidações ·{" "}
                {selected.n_criticos} eventos críticos · {selected.n_alto_risco} eventos ≥70%
              </span>
            </div>

            <Divider className="my-0" />

            <div className="flex flex-col gap-3">
              <span className={tableTokens.header}>Composição do risco</span>
              {selected.indicadores.map((i) => (
                <div key={i.indicador} className="flex flex-col gap-1">
                  <div className="flex items-baseline justify-between">
                    <span className={tableTokens.cellStrong}>
                      {INDICADOR_LABELS[i.indicador] ?? i.indicador}
                    </span>
                    <RiscoBadge valor={i.subscore} />
                  </div>
                  <span className={tableTokens.cellSecondary}>
                    {brl(i.valor_em_risco)} liquidado suspeito de {brl(i.valor_avaliado)} ·{" "}
                    {i.n_eventos ?? 0} eventos · {i.n_criticos ?? 0} críticos
                  </span>
                  {i.componentes?.piso_critico_aplicado === true && (
                    <span className={cx(tableTokens.badge, tableTokens.badgeWarning, "w-fit")}>
                      piso de padrão crítico aplicado (mín. 70)
                    </span>
                  )}
                </div>
              ))}
              <span className={tableTokens.cellMuted}>
                Score do indicador = % do valor avaliado em eventos de alto risco, com
                piso 70 quando há padrão crítico. A composição entre indicadores é
                versionada e evolui conforme novos indicadores entram.
              </span>
            </div>

            <Divider className="my-0" />

            <Button
              variant="secondary"
              onClick={() =>
                router.push(
                  `/risco/curadoria-liquidacoes?cedente=${encodeURIComponent(
                    selected.cedente_nome ?? selected.cedente_documento,
                  )}`,
                )
              }
            >
              Ver liquidações deste cedente
            </Button>
          </div>
        )}
      </DrillDownSheet>
    </div>
  )
}
