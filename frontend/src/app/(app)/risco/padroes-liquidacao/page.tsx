// src/app/(app)/risco/padroes-liquidacao/page.tsx
//
// Risco · Liquidações · Padrões de liquidação — painel 100% DETERMINÍSTICO
// (decisão Ricardo 2026-07-09). Diferente de /risco/cedentes (score do modelo),
// aqui só há fatos: ocorrências já materializadas em deteccao_score.features +
// as conclusões determinísticas (regra_dura). O score do modelo é ignorado.
//
// Indicadores (travados 2026-07-09), todos INTRÍNSECOS ao cedente:
//   Conta do cedente (o maior red flag, peso máximo) · Praça do cedente
//   (condicionada) · Fora da praça do sacado · Fora do padrão do sacado ·
//   Agência multi-sacado (condicionada). + Canal por segmento oficial Bacen
//   (banco digital / cooperativa / IP / SCD / financeira). Alerta = regra dura.
//
// Temporalidade: janela sobre data_evento (filtra 100%) + Δ vs janela anterior
// + recência. Detalhe por cedente (rede/anel + liquidações) = 2º momento.
//

"use client"

import * as React from "react"
import { RiPulseLine } from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { DataTableShell, KpiBand, PageHeader, SegmentSwitch } from "@/design-system/components"
import type { KpiBandItem } from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type { CedentePerfilRow, JanelaLiquidacao } from "@/lib/api-client"
import { usePadroesLiquidacao } from "@/lib/hooks/risco"
import { cx } from "@/lib/utils"

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

// Red flags intrínsecos ao cedente (heatmap). Conta do cedente é a coluna-líder
// (peso máximo) e vem separada; estes são os demais.
const SINAIS: { key: string; head: string; info: string }[] = [
  { key: "praca_cedente", head: "Praça Ced.", info: "Praça do cedente — pago na cidade do cedente E fora da cidade do sacado (se mesma praça, não conta)." },
  { key: "fora_praca", head: "Fora praça", info: "Fora da praça do sacado — pago em cidade diferente da do sacado." },
  { key: "fora_padrao", head: "Fora padrão Sac.", info: "Fora do padrão do sacado — sacado pagou fora do banco/agência habitual dele." },
  { key: "multi_sacado", head: "Agência Multi-Sac.", info: "Agência multi-sacado — muitos sacados na mesma agência, de cidades divergentes (concentração local não conta)." },
]

// Canal por segmento oficial Bacen (descritor — para onde foi o pagamento).
const SEGMENTOS: { key: string; head: string; info: string }[] = [
  { key: "banco_digital", head: "Banco Dig.", info: "Banco digital (banco sem rede física, ≤1 agência)." },
  { key: "cooperativa", head: "Coop.", info: "Cooperativa de crédito." },
  { key: "ip", head: "IP", info: "Instituição de pagamento (conta eletrônica)." },
  { key: "scd", head: "SCD", info: "Sociedade de crédito direto." },
  { key: "financeira", head: "Financ.", info: "Financeira (SCFI)." },
]

// Cabeçalho que quebra em 2 linhas (colunas estreitas uniformes) + tooltip.
function Hd({ label, info }: { label: string; info?: string }) {
  return (
    <span className="block whitespace-normal leading-[1.15]" title={info}>
      {label}
    </span>
  )
}

const COL_SINAL = 66 // largura uniforme das colunas de contagem

// Heatmap de red flag: 0 = vazio; senão intensidade pela razão count/n_liq.
// MOTIVO: chip de heatmap é viz aprovada (matriz determinística) — a cor
// carrega a intensidade; tableTokens não tem variante de heat.
function HeatCell({ count, total }: { count: number; total: number }) {
  if (!count) return <span className={tableTokens.cellMuted}>—</span>
  const ratio = total > 0 ? count / total : 0
  const tom =
    ratio < 0.25
      ? "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400"
      : ratio < 0.6
        ? "bg-orange-100 text-orange-800 dark:bg-orange-500/15 dark:text-orange-300"
        : "bg-red-100 text-red-800 dark:bg-red-500/20 dark:text-red-300"
  return (
    <span
      className={cx(tableTokens.cellNumber, "inline-block min-w-[26px] rounded px-1.5 text-center", tom)}
      title={`${count} de ${total} liquidações (${Math.round(ratio * 100)}%)`}
    >
      {count}
    </span>
  )
}

// Segmento = descritor, não red flag: contagem neutra (sem heat).
function SegCell({ count, total }: { count: number; total: number }) {
  if (!count) return <span className={tableTokens.cellMuted}>—</span>
  return (
    <span className={tableTokens.cellNumberSecondary} title={`${count} de ${total} liquidações`}>
      {count}
    </span>
  )
}

function AlertaCell({ row }: { row: CedentePerfilRow }) {
  if (!row.n_alerta) return <span className={tableTokens.cellMuted}>—</span>
  const partes: string[] = []
  if (row.n_alerta_conta) partes.push(`${row.n_alerta_conta} conta+cidade`)
  if (row.n_alerta_multicedente) partes.push(`${row.n_alerta_multicedente} agência multi-cedente`)
  return (
    <span
      className={cx(tableTokens.badge, tableTokens.badgeDanger)}
      title={`Regra dura acionada: ${partes.join(" · ") || row.n_alerta}`}
    >
      ⚠ {row.n_alerta}
    </span>
  )
}

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
      className={cx(
        tableTokens.cellNumber,
        piorou ? "text-red-600 dark:text-red-400" : "text-emerald-600 dark:text-emerald-400",
      )}
      title={`Variação de alertas vs janela anterior: ${piorou ? "+" : ""}${delta}`}
    >
      {piorou ? "▲" : "▼"} {Math.abs(delta)}
    </span>
  )
}

const col = createColumnHelper<CedentePerfilRow>()

export default function PadroesLiquidacaoPage() {
  const [janela, setJanela] = React.useState<JanelaLiquidacao>("30d")
  const [search, setSearch] = React.useState("")
  const [segment, setSegment] = React.useState<"todos" | "alerta" | "conta">("todos")

  const query = usePadroesLiquidacao(janela)
  const cedentes = React.useMemo(() => query.data?.cedentes ?? [], [query.data])
  const kpis = query.data?.kpis

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
            ? {
                value: `${deltaAlerta > 0 ? "+" : ""}${deltaAlerta}`,
                tone: deltaAlerta > 0 ? "negative" : "positive",
              }
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
      // Cedente — sem size: absorve a folga no layout fixo.
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
      // Conta do cedente — o MAIOR red flag (peso máximo), coluna-líder.
      col.display({
        id: "conta_cedente",
        header: () => (
          <Hd label="Contas Ced. ⭐" info="Conta do cedente — recebido em agência/conta cadastrada do próprio cedente (o maior red flag de auto-liquidação)." />
        ),
        size: COL_SINAL,
        meta: { align: "center" },
        cell: ({ row }) => (
          <HeatCell count={row.original.sinais.conta_cedente ?? 0} total={row.original.n_liq} />
        ),
      }) as ColumnDef<CedentePerfilRow, unknown>,
      col.display({
        id: "alerta",
        header: () => <Hd label="Alertas" info="Liquidações que acionaram uma regra determinística (regra dura)." />,
        size: 72,
        meta: { align: "center" },
        cell: ({ row }) => <AlertaCell row={row.original} />,
      }) as ColumnDef<CedentePerfilRow, unknown>,
      col.accessor("n_liq", {
        header: () => <Hd label="Nº Liq." info="Nº de liquidações na janela" />,
        size: 62,
        meta: { align: "right" },
        cell: (info) => <span className={tableTokens.cellNumber}>{(info.getValue() as number).toLocaleString("pt-BR")}</span>,
      }) as ColumnDef<CedentePerfilRow, unknown>,
      col.accessor("valor", {
        header: () => <Hd label="R$ Liq." info="Valor liquidado na janela" />,
        size: 96,
        meta: { align: "right" },
        cell: (info) => <span className={tableTokens.cellNumberSecondary}>{brl(info.getValue() as number)}</span>,
      }) as ColumnDef<CedentePerfilRow, unknown>,
      ...SINAIS.map(
        (s) =>
          col.display({
            id: s.key,
            header: () => <Hd label={s.head} info={s.info} />,
            size: COL_SINAL,
            meta: { align: "center" },
            cell: ({ row }) => (
              <HeatCell count={row.original.sinais[s.key] ?? 0} total={row.original.n_liq} />
            ),
          }) as ColumnDef<CedentePerfilRow, unknown>,
      ),
      ...SEGMENTOS.map(
        (s) =>
          col.display({
            id: `seg_${s.key}`,
            header: () => <Hd label={s.head} info={s.info} />,
            size: COL_SINAL,
            meta: { align: "center" },
            cell: ({ row }) => (
              <SegCell count={row.original.segmentos[s.key] ?? 0} total={row.original.n_liq} />
            ),
          }) as ColumnDef<CedentePerfilRow, unknown>,
      ),
      col.accessor("ultima_liq", {
        header: () => <Hd label="Últ. liq." info="Última liquidação (recência)" />,
        size: 72,
        meta: { align: "center" },
        cell: (info) => <RecenciaCell iso={info.getValue() as string | null} />,
      }) as ColumnDef<CedentePerfilRow, unknown>,
      col.display({
        id: "delta",
        header: () => <Hd label="Δ" info="Variação de alertas vs a janela anterior de mesmo tamanho." />,
        size: 48,
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
        info="Perfil 100% determinístico das liquidações: só fatos (ocorrências já materializadas) e conclusões determinísticas (regra dura). O score do modelo é ignorado — ele vive em 'Risco de cedentes'. Indicadores intrínsecos ao cedente: Conta do cedente (o maior red flag), Praça do cedente (só quando ≠ praça do sacado), Fora da praça do sacado, Fora do padrão do sacado, Agência multi-sacado (só com cidades divergentes) + canal por segmento Bacen. A janela filtra todos os agregados; Δ compara com a janela anterior; recência evita alerta velho."
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
          Janela sobre a data do evento · agregados reconciliam com os KPIs
        </span>
      </div>

      <KpiBand items={kpiItems} loading={query.isLoading && !query.data} />

      <DataTableShell<CedentePerfilRow>
        data={cedentes}
        columns={columns}
        loading={query.isLoading && !query.data}
        error={query.error}
        onRetry={() => query.refetch()}
        // Layout fixo: colunas de contagem com largura uniforme; Cedente
        // absorve a folga; scroll-x só abaixo de ~1140px.
        tableLayout="fixed"
        minWidth={1140}
        search={{ value: search, onChange: setSearch, placeholder: "Buscar cedente..." }}
        segments={{
          value: segment,
          onChange: (v) => setSegment(v as typeof segment),
          options: [
            { value: "todos", label: "Todos", filter: () => true },
            { value: "alerta", label: "Em alerta", filter: (c) => c.n_alerta > 0 },
            {
              value: "conta",
              label: "Conta do cedente",
              filter: (c) => (c.sinais.conta_cedente ?? 0) > 0,
            },
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
    </div>
  )
}
