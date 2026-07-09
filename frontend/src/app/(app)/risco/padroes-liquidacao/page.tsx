// src/app/(app)/risco/padroes-liquidacao/page.tsx
//
// Risco · Liquidações · Padrões de liquidação — painel 100% DETERMINÍSTICO
// (decisão Ricardo 2026-07-09). Diferente de /risco/cedentes (que usa o SCORE
// do modelo), aqui só há FATOS: as ocorrências já materializadas em
// deteccao_score.features + as conclusões determinísticas (regra_dura). O
// score do modelo é deliberadamente ignorado.
//
// Duas camadas por cedente, escopadas por uma JANELA sobre data_evento:
//   - Fatos   → matriz de contagem de ocorrência por sinal (heatmap) + mix de
//               canal.
//   - Alertas → regra_dura acionada (cedente em alerta sobe ao topo).
// Temporalidade: a janela filtra 100% dos agregados; cada célula/kpi traz o Δ
// vs a janela anterior; a recência evita alerta velho parecendo atual.
//
// Detalhe por cedente (buckets temporais + liquidações por canal) = 2º momento
// (drawer), conforme combinado.
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

// Sinais de ocorrência — ordem canônica da matriz. `key` casa com o dict
// `sinais` do backend; `head` é o cabeçalho curto; `info` o tooltip.
const SINAIS: { key: string; head: string; info: string }[] = [
  { key: "match_conta", head: "Conta", info: "Recebido na agência/conta do próprio cedente." },
  { key: "match_cidade", head: "Cidade", info: "Cidade do pagamento = cidade do cedente." },
  { key: "fora_praca", head: "Fora praça", info: "Pago fora da praça (cidade) do sacado." },
  { key: "ag_compartilhada", head: "Ag. comp.", info: "Agência compartilhada por vários sacados." },
  { key: "anel_cedentes", head: "Anel", info: "Agência compartilhada entre cedentes diferentes." },
  { key: "contrato_aberto", head: "Contr. aberto", info: "Liquidado com o contrato ainda aberto." },
  { key: "boleto_nao_esperado", head: "Boleto ines.", info: "Boleto não esperado, mas houve trilho bancário." },
  { key: "baixa_manual_anomala", head: "Baixa anôm.", info: "Baixa manual anômala para o produto." },
  { key: "quebra_fingerprint", head: "Fingerpr.", info: "Quebra do padrão histórico de pagamento do sacado." },
  { key: "pago_exato_vencimento", head: "Venc. exato", info: "Pago exatamente no dia do vencimento." },
]

// Mix de canal (mini-barra) — cores categóricas (viz aprovada). Ordem = norma
// primeiro (banco na praça), depois os canais de atenção.
const CANAL: { key: string; label: string; cor: string }[] = [
  { key: "banco_praca", label: "Banco na praça", cor: "bg-gray-400 dark:bg-gray-500" },
  { key: "cooperativa", label: "Cooperativa", cor: "bg-sky-500" },
  { key: "ip", label: "Inst. pagamento", cor: "bg-violet-500" },
  { key: "sem_praca", label: "Sem praça (inc. SCD/fin.)", cor: "bg-amber-500" },
  { key: "nao_resolvido", label: "Não resolvido", cor: "bg-red-500" },
  { key: "baixa_manual", label: "Baixa manual", cor: "bg-orange-500" },
]

// Heatmap de ocorrência: 0 = vazio; senão intensidade pela razão count/n_liq.
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

function AlertaCell({ row }: { row: CedentePerfilRow }) {
  if (!row.n_alerta) return <span className={tableTokens.cellMuted}>—</span>
  const partes: string[] = []
  if (row.n_alerta_conta) partes.push(`${row.n_alerta_conta} conta/cidade`)
  if (row.n_alerta_anel) partes.push(`${row.n_alerta_anel} anel de agência`)
  return (
    <span
      className={cx(tableTokens.badge, tableTokens.badgeDanger)}
      title={`Regra dura acionada: ${partes.join(" · ") || row.n_alerta}`}
    >
      ⚠ {row.n_alerta}
    </span>
  )
}

function CanalMixBar({ row }: { row: CedentePerfilRow }) {
  const total = row.n_liq || 1
  const tooltip = CANAL.map((c) => `${c.label}: ${row.canal[c.key] ?? 0}`).join(" · ")
  return (
    <div className="flex h-3 w-[120px] overflow-hidden rounded-sm" title={tooltip}>
      {CANAL.map((c) => {
        const n = row.canal[c.key] ?? 0
        if (!n) return null
        return <div key={c.key} className={c.cor} style={{ width: `${(100 * n) / total}%` }} />
      })}
    </div>
  )
}

function RecenciaCell({ iso }: { iso: string | null }) {
  if (!iso) return <span className={tableTokens.cellMuted}>—</span>
  const dias = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000)
  const label = dias <= 0 ? "hoje" : `há ${dias}d`
  // Recência velha (>90d) = alerta possivelmente parado — sinaliza em âmbar.
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
  const [segment, setSegment] = React.useState<"todos" | "alerta" | "anel">("todos")

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
      { eyebrow: "BANCO NA PRAÇA", value: `${kpis.pct_banco_praca}%`, sub: "das liquidações" },
      { eyebrow: "FORA DA PRAÇA DO SACADO", value: `${kpis.pct_fora_praca}%`, sub: "das liquidações" },
      { eyebrow: "BAIXA MANUAL", value: `${kpis.pct_baixa_manual}%`, sub: "das liquidações" },
    ]
  }, [kpis])

  const columns = React.useMemo<ColumnDef<CedentePerfilRow, unknown>[]>(
    () => [
      col.accessor("cedente_nome", {
        header: "Cedente",
        size: 220,
        cell: (info) => {
          const nome = (info.getValue() as string | null) ?? info.row.original.cedente_documento
          return (
            <span className={cx(tableTokens.cellStrong, "block max-w-[210px] truncate")} title={nome}>
              {nome}
            </span>
          )
        },
      }) as ColumnDef<CedentePerfilRow, unknown>,
      col.display({
        id: "alerta",
        header: () => <span title="Liquidações que acionaram uma regra determinística (regra dura).">⚠ Alerta</span>,
        size: 80,
        cell: ({ row }) => <AlertaCell row={row.original} />,
      }) as ColumnDef<CedentePerfilRow, unknown>,
      col.accessor("n_liq", {
        header: "N liq.",
        size: 64,
        meta: { align: "right" },
        cell: (info) => <span className={tableTokens.cellNumber}>{(info.getValue() as number).toLocaleString("pt-BR")}</span>,
      }) as ColumnDef<CedentePerfilRow, unknown>,
      col.accessor("valor", {
        header: "R$ liquidado",
        size: 116,
        meta: { align: "right" },
        cell: (info) => <span className={tableTokens.cellNumberSecondary}>{brl(info.getValue() as number)}</span>,
      }) as ColumnDef<CedentePerfilRow, unknown>,
      ...SINAIS.map(
        (s) =>
          col.display({
            id: s.key,
            header: () => <span title={s.info}>{s.head}</span>,
            size: 78,
            meta: { align: "center" },
            cell: ({ row }) => (
              <HeatCell count={row.original.sinais[s.key] ?? 0} total={row.original.n_liq} />
            ),
          }) as ColumnDef<CedentePerfilRow, unknown>,
      ),
      col.display({
        id: "canal",
        header: () => <span title="Mix de canal de liquidação. SCD/financeira ainda contam em 'sem praça'.">Canal</span>,
        size: 130,
        cell: ({ row }) => <CanalMixBar row={row.original} />,
      }) as ColumnDef<CedentePerfilRow, unknown>,
      col.accessor("ultima_liq", {
        header: "Última liq.",
        size: 90,
        cell: (info) => <RecenciaCell iso={info.getValue() as string | null} />,
      }) as ColumnDef<CedentePerfilRow, unknown>,
      col.display({
        id: "delta",
        header: () => <span title="Variação de alertas vs a janela anterior de mesmo tamanho.">Δ alerta</span>,
        size: 78,
        cell: ({ row }) => <DeltaCell delta={row.original.delta_alerta} novo={row.original.cedente_novo} />,
      }) as ColumnDef<CedentePerfilRow, unknown>,
    ],
    [],
  )

  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Padrões de liquidação"
        info="Perfil 100% determinístico das liquidações: só fatos (ocorrências de sinal já materializadas) e conclusões determinísticas (regra dura). O score do modelo é ignorado aqui — ele vive em 'Risco de cedentes'. A janela filtra todos os agregados; cada célula é a contagem na janela (heatmap por intensidade); Δ compara com a janela anterior; a recência evita alerta velho parecendo atual."
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
        search={{ value: search, onChange: setSearch, placeholder: "Buscar cedente..." }}
        segments={{
          value: segment,
          onChange: (v) => setSegment(v as typeof segment),
          options: [
            { value: "todos", label: "Todos", filter: () => true },
            { value: "alerta", label: "Em alerta", filter: (c) => c.n_alerta > 0 },
            {
              value: "anel",
              label: "Anel de agência",
              filter: (c) => (c.sinais.anel_cedentes ?? 0) > 0 || c.n_alerta_anel > 0,
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
