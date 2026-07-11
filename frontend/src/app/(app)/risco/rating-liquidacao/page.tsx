// src/app/(app)/risco/rating-liquidacao/page.tsx
//
// Risco · Liquidações · Rating de liquidação — nota determinística de
// INTEGRIDADE de liquidação por cedente (score 0-100 + grade A-E/NC),
// com drill para os pares cedente×sacado (onde o "título frio" mora).
//
// Princípios (framework 2026-07-11):
//   - score só sobre eventos com alegação de pagamento do sacado;
//     recompra/perda ficam na COBERTURA (integridade ≠ crédito);
//   - sinal crítico (PRC-01/CNV-90) trava a nota (grade E);
//   - grade boa exige base (n + cobertura) — senão NC, nunca um A imerecido;
//   - letra é apresentação: o primitivo é o score numérico (componível no
//     futuro rating do cedente).
// MOTIVO: deriva de ListagemComDrilldown; sem FilterBar — a janela é
// parâmetro versionado da fórmula (não filtro de usuário).

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { RiShieldStarLine } from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import {
  DataTableShell,
  DrillDownSheet,
  KpiBand,
  PageHeader,
} from "@/design-system/components"
import type { KpiBandItem } from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type { RatingLiquidacaoRow } from "@/lib/api-client"
import { useRatingLiquidacao, useRatingLiquidacaoPares } from "@/lib/hooks/risco"
import { cx } from "@/lib/utils"

const brl = (v: number) =>
  v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 })

// Grade badge: A/B saudáveis, C atenção, D/E problema, NC = sem base.
const GRADE_BADGE: Record<string, string> = {
  A: tableTokens.badgeSuccess,
  B: tableTokens.badgeSuccess,
  C: tableTokens.badgeWarning,
  D: tableTokens.badgeDanger,
  E: tableTokens.badgeDanger,
  NC: tableTokens.badgeNeutral,
}

function GradeBadge({ grade, critico }: { grade: string; critico: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={cx(tableTokens.badge, GRADE_BADGE[grade] ?? tableTokens.badgeNeutral)}>
        {grade === "NC" ? "NC" : grade}
      </span>
      {critico && (
        <span
          className={cx(tableTokens.badge, tableTokens.badgeDanger)}
          title="Sinal crítico (PRC-01/CNV-90) trava a nota"
        >
          crítico
        </span>
      )}
    </span>
  )
}

function ScoreCell({ score }: { score: number | null }) {
  if (score === null) return <span className={tableTokens.cellMuted}>—</span>
  return <span className={tableTokens.cellNumber}>{score.toFixed(0)}</span>
}

function CoberturaCell({ v }: { v: number }) {
  const pct = Math.round(v * 100)
  return (
    <span
      className={cx(tableTokens.cellNumber, pct < 50 && "text-amber-600 dark:text-amber-400")}
      title="% do valor de desfechos que passou pelo trilho bancário (atestável)"
    >
      {pct}%
    </span>
  )
}

function SinaisCell({ sinais }: { sinais?: Record<string, number> }) {
  const entries = Object.entries(sinais ?? {}).sort((a, b) => b[1] - a[1])
  if (entries.length === 0) return <span className={tableTokens.cellMuted}>—</span>
  return (
    <span className="inline-flex flex-wrap gap-1">
      {entries.slice(0, 4).map(([codigo, n]) => (
        <span
          key={codigo}
          className={cx(
            tableTokens.badge,
            codigo === "PRC-01" || codigo === "CNV-90"
              ? tableTokens.badgeDanger
              : tableTokens.badgeNeutral,
          )}
          title={`${codigo}: ${n} eventos`}
        >
          {codigo}·{n}
        </span>
      ))}
      {entries.length > 4 && (
        <span className={tableTokens.cellMuted}>+{entries.length - 4}</span>
      )}
    </span>
  )
}

const col = createColumnHelper<RatingLiquidacaoRow>()

function ParesDrawerBody({ cedente }: { cedente: RatingLiquidacaoRow }) {
  const pares = useRatingLiquidacaoPares(cedente.cedente_documento)
  const rows = pares.data?.rows ?? []
  return (
    <div className="space-y-4">
      <p className={tableTokens.cellSecondary}>
        Pares cedente×sacado — o sinal agrega pelo lado do <strong>cedente</strong> (quem
        controla o fluxo de liquidação); o sacado nunca é penalizado globalmente por
        conduta do cedente.
      </p>
      {pares.isPending ? (
        <p className={tableTokens.cellMuted}>Carregando pares…</p>
      ) : (
        <div className="overflow-x-auto">
          {/* MOTIVO: drill dentro de drawer — tabela leve (poucas colunas,
              density ultra) em vez de DataTable completa (§ drills). */}
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200 text-left dark:border-gray-800">
                <th className={tableTokens.header}>Sacado</th>
                <th className={tableTokens.header}>Rating</th>
                <th className={cx(tableTokens.header, "text-right")}>Score</th>
                <th className={cx(tableTokens.header, "text-right")}>Ev.</th>
                <th className={cx(tableTokens.header, "text-right")}>Cobert.</th>
                <th className={tableTokens.header}>Sinais</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr
                  key={p.sacado_documento ?? ""}
                  className="h-8 border-b border-gray-100 dark:border-gray-800/60"
                >
                  <td
                    className={cx(tableTokens.cellText, "max-w-[180px] truncate")}
                    title={p.sacado_nome ?? undefined}
                  >
                    {p.sacado_nome ?? p.sacado_documento}
                  </td>
                  <td>
                    <GradeBadge grade={p.grade} critico={p.tem_critico} />
                  </td>
                  <td className="text-right">
                    <ScoreCell score={p.score} />
                  </td>
                  <td className={cx(tableTokens.cellNumberSecondary, "text-right")}>
                    {p.n_eventos_score}
                  </td>
                  <td className="text-right">
                    <CoberturaCell v={p.cobertura} />
                  </td>
                  <td>
                    <SinaisCell sinais={p.componentes?.sinais} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export default function RatingLiquidacaoPage() {
  const router = useRouter()
  const sp = useSearchParams()
  const selectedDoc = sp.get("selected")

  const [search, setSearch] = React.useState("")
  const query = useRatingLiquidacao()
  const rows = React.useMemo(() => query.data?.rows ?? [], [query.data])

  const selected = React.useMemo(
    () => (selectedDoc ? (rows.find((r) => r.cedente_documento === selectedDoc) ?? null) : null),
    [rows, selectedDoc],
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
    const criticos = rows.filter((r) => r.tem_critico)
    const de = rows.filter((r) => r.grade === "D" || r.grade === "E")
    const nc = rows.filter((r) => r.grade === "NC")
    return [
      {
        eyebrow: "CEDENTES AVALIADOS",
        value: rows.length.toLocaleString("pt-BR"),
        sub: "rollup por cedente · janela 12m",
      },
      {
        eyebrow: "COM SINAL CRÍTICO",
        value: criticos.length.toLocaleString("pt-BR"),
        sub: "PRC-01 / CNV-90 travam a nota",
      },
      { eyebrow: "GRADE D/E", value: de.length.toLocaleString("pt-BR"), sub: "integridade ruim" },
      {
        eyebrow: "SEM CLASSIFICAÇÃO",
        value: nc.length.toLocaleString("pt-BR"),
        sub: "base insuficiente p/ grade boa",
      },
      {
        eyebrow: "VALOR SOB CRÍTICO",
        value: brl(criticos.reduce((a, r) => a + r.valor_desfechos, 0)),
        sub: "desfechos 12m dos cedentes críticos",
      },
    ]
  }, [rows])

  const columns = React.useMemo<ColumnDef<RatingLiquidacaoRow, unknown>[]>(
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
      }) as ColumnDef<RatingLiquidacaoRow, unknown>,
      col.display({
        id: "rating",
        header: () => (
          <span title="Grade do score (letra é apresentação; o primitivo é o score 0-100). NC = base insuficiente para grade boa.">
            Rating
          </span>
        ),
        size: 120,
        cell: ({ row }) => <GradeBadge grade={row.original.grade} critico={row.original.tem_critico} />,
      }) as ColumnDef<RatingLiquidacaoRow, unknown>,
      col.accessor("score", {
        header: () => <span title="Score 0-100 (maior = melhor); crítico trava em ≤20">Score</span>,
        size: 70,
        meta: { align: "right" },
        cell: (info) => <ScoreCell score={info.getValue() as number | null} />,
      }) as ColumnDef<RatingLiquidacaoRow, unknown>,
      col.accessor("n_eventos_score", {
        header: () => <span title="Eventos com alegação de pagamento do sacado (base do score)">Ev.</span>,
        size: 64,
        meta: { align: "right" },
        cell: (info) => (
          <span className={tableTokens.cellNumberSecondary}>
            {(info.getValue() as number).toLocaleString("pt-BR")}
          </span>
        ),
      }) as ColumnDef<RatingLiquidacaoRow, unknown>,
      col.accessor("cobertura", {
        header: () => (
          <span title="% do valor de desfechos que passou pelo trilho bancário — recompra/perda reduzem a cobertura, não o score (integridade ≠ crédito)">
            Cobert.
          </span>
        ),
        size: 76,
        meta: { align: "right" },
        cell: (info) => <CoberturaCell v={info.getValue() as number} />,
      }) as ColumnDef<RatingLiquidacaoRow, unknown>,
      col.accessor("valor_desfechos", {
        header: () => <span title="Valor total de desfechos na janela">R$ 12m</span>,
        size: 104,
        meta: { align: "right" },
        cell: (info) => (
          <span className={tableTokens.cellNumberSecondary}>{brl(info.getValue() as number)}</span>
        ),
      }) as ColumnDef<RatingLiquidacaoRow, unknown>,
      col.display({
        id: "sinais",
        header: () => (
          <span title="Sinais do catálogo que acenderam (código · nº de eventos)">Sinais</span>
        ),
        size: 220,
        cell: ({ row }) => <SinaisCell sinais={row.original.componentes?.sinais} />,
      }) as ColumnDef<RatingLiquidacaoRow, unknown>,
    ],
    [],
  )

  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Rating de liquidação"
        subtitle="Risco · Liquidações"
        info="Nota determinística de INTEGRIDADE de liquidação: o dinheiro vem de quem dizem? Score 0-100 sobre eventos com alegação de pagamento do sacado; sinal crítico (PRC-01/CNV-90) trava a nota; grade boa exige base mínima (senão NC). Recompra/perda não entram no score — entram na cobertura (dimensão de crédito, futuro sub-rating). Fórmula, deduções e cortes são parâmetros versionados. Clique num cedente para os pares cedente×sacado."
      />

      <KpiBand items={kpiItems} loading={query.isLoading && !query.data} />

      <DataTableShell<RatingLiquidacaoRow>
        data={rows}
        columns={columns}
        loading={query.isLoading && !query.data}
        error={query.error}
        onRetry={() => query.refetch()}
        tableLayout="fixed"
        minWidth={860}
        onRowClick={(r) => setSelected(r.cedente_documento)}
        search={{ value: search, onChange: setSearch, placeholder: "Buscar cedente..." }}
        segments={{
          value: "todos",
          onChange: () => undefined,
          options: [{ value: "todos", label: "Todos", filter: () => true }],
        }}
        itemNoun={{ singular: "cedente", plural: "cedentes" }}
        emptyState={{
          icon: RiShieldStarLine,
          title: "Nenhum rating calculado",
          description:
            "O rating é recalculado automaticamente após o scoring (a cada 6h). Se acabou de subir, aguarde o próximo ciclo.",
        }}
      />

      <DrillDownSheet
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={selected ? (selected.cedente_nome ?? selected.cedente_documento) : ""}
        size="md"
      >
        {selected && <ParesDrawerBody cedente={selected} />}
      </DrillDownSheet>
    </div>
  )
}
