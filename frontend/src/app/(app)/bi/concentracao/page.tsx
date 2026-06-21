"use client"

//
// BI · Concentração — Top-10 cedentes e sacados por valor presente (carteira
// QiTech) sobre o PL total do fundo (MEC), + histórico diário. Só Realinvest.
//
// Padrão canônico DashboardBiPadrao (shell): PageHeader + DashboardHeaderActions
// + AIPanel in-layout + ProvenanceFooter. Sem KpiStrip — os KPIs de
// concentração vivem na 2a linha do título dos charts (EChartsCard headerKpi).
//

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { parseAsString, useQueryState } from "nuqs"
import { toast } from "sonner"
import {
  RiBuilding2Line,
  RiCalendarLine,
  RiCheckLine,
  RiHistoryLine,
} from "@remixicon/react"

import { PageHeader } from "@/design-system/components/PageHeader"
import { DashboardHeaderActions } from "@/design-system/components/DashboardHeaderActions"
import { FilterChip } from "@/design-system/components/FilterBar"
import {
  AIPanel,
  useAIPanel,
  type AIInsight,
} from "@/design-system/components/AIPanel"
import { AIQuotaIndicator } from "@/design-system/components/AIQuotaIndicator"
import { useAIChat, useAIInsights, useAIQuota } from "@/lib/hooks/ai"
import { biConcentracao } from "@/lib/api-client"
import { cx } from "@/lib/utils"

import { ConcentracaoCard } from "./_components/ConcentracaoCard"
import { HistoricoCard } from "./_components/HistoricoCard"

const JANELA_OPTS = [
  { value: "6m", label: "6 meses" },
  { value: "12m", label: "12 meses" },
  { value: "24m", label: "24 meses" },
  { value: "tudo", label: "Tudo" },
] as const

const JANELA_LABEL: Record<string, string> = Object.fromEntries(
  JANELA_OPTS.map((o) => [o.value, o.label]),
)

// Lista de opcoes (single-select) dentro de um FilterChip — padrao das paginas
// BI (panorama/operacoes). `nullLabel` opcional renderiza a opcao "limpar".
function OptList({
  options,
  selected,
  onSelect,
  nullLabel,
}: {
  options: ReadonlyArray<{ value: string; label: string }>
  selected: string | null
  onSelect: (value: string | null) => void
  nullLabel?: string
}) {
  const item = (value: string | null, label: string) => (
    <button
      key={value ?? "__null__"}
      type="button"
      onClick={() => onSelect(value)}
      className={cx(
        "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
        selected === value
          ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
          : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
      )}
    >
      <span className="flex-1 text-left">{label}</span>
      {selected === value && (
        <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />
      )}
    </button>
  )
  return (
    <div className="max-h-72 overflow-y-auto py-1">
      {nullLabel !== undefined && item(null, nullLabel)}
      {options.map((o) => item(o.value, o.label))}
    </div>
  )
}

function fmtMi(v: number): string {
  return `R$ ${(v / 1e6).toLocaleString("pt-BR", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} mi`
}

// Data curta DD/MM/YY (toolbar/PL de referência).
function fmtDataYY(iso: string | undefined): string {
  if (!iso) return "—"
  return new Date(iso).toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
    timeZone: "UTC",
  })
}

function fmtData(iso: string | undefined, long = false): string {
  if (!iso) return "—"
  const d = new Date(iso)
  return d.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: long ? "numeric" : undefined,
    timeZone: "UTC",
  })
}

/** Variacao (pp) do Top 10 vs ponto anterior do historico (ultimo - penultimo). */
function deltaTop10Pp(pontos: { top10_pct: number }[] | undefined): number | undefined {
  if (!pontos || pontos.length < 2) return undefined
  return pontos[pontos.length - 1].top10_pct - pontos[pontos.length - 2].top10_pct
}

export default function ConcentracaoPage() {
  // Filtros globais (§7.2) — deep-linkaveis via URL (nuqs).
  const [uaParam, setUaParam] = useQueryState("ua")
  const [dataParam, setDataParam] = useQueryState("data")
  const [janela, setJanela] = useQueryState(
    "janela",
    parseAsString.withDefault("12m"),
  )

  const q = useQuery({
    queryKey: ["bi", "concentracao", uaParam, dataParam, janela],
    queryFn: () => biConcentracao.get(uaParam, dataParam, janela),
  })

  const data = q.data?.data
  const prov = q.data?.provenance
  const loading = q.isLoading
  const posicao = fmtData(data?.data_posicao)
  const suportado = data?.suportado ?? true

  // Opcoes do chip UA (todas as UAs do tenant).
  const uaOpts = React.useMemo(
    () => (data?.uas ?? []).map((u) => ({ value: u.id, label: u.nome })),
    [data?.uas],
  )

  // Toolbar shadow ao rolar.
  const scrollRef = React.useRef<HTMLDivElement>(null)
  const [scrolled, setScrolled] = React.useState(false)
  React.useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    const onScroll = () => setScrolled(el.scrollTop > 0)
    el.addEventListener("scroll", onScroll, { passive: true })
    return () => el.removeEventListener("scroll", onScroll)
  }, [])

  // Opcoes do chip Posicao (datas disponiveis, mais recentes primeiro).
  const dateOpts = React.useMemo(
    () =>
      (data?.datas_disponiveis ?? []).map((iso) => ({
        value: iso.slice(0, 10),
        label: fmtData(iso, true),
      })),
    [data?.datas_disponiveis],
  )
  const posicaoChipValue = dataParam
    ? fmtData(dataParam, true)
    : `Última (${fmtData(data?.data_posicao, true)})`

  // ── IA (shell canônico) ──────────────────────────────────────────────
  const quotaQ = useAIQuota()
  const [conversationId, setConversationId] = React.useState<string | null>(null)
  const insightsQ = useAIInsights({ page: "/bi/concentracao", period: "snapshot" })
  const { send } = useAIChat({
    conversationId,
    onConversationCreated: setConversationId,
  })
  const insights: AIInsight[] = React.useMemo(
    () => (insightsQ.data?.insights ?? []).map((i) => ({ text: i.text })),
    [insightsQ.data],
  )
  const ai = useAIPanel()
  const aiContext = React.useMemo(
    () => ({
      page: "BI · Concentração",
      period: data?.data_posicao ?? "snapshot",
      filters: "Realinvest",
    }),
    [data?.data_posicao],
  )

  const handleExport = React.useCallback(() => {
    if (!data) return
    const lines = ["tipo;rank;nome;documento;financeiro;pct_pl"]
    const push = (tipo: string, t: typeof data.cedentes) =>
      t.itens.forEach((i) =>
        lines.push(
          `${tipo};${i.rank};"${i.nome}";${i.documento};${i.financeiro};${i.pct_pl}`,
        ),
      )
    push("cedente", data.cedentes)
    push("sacado", data.sacados)
    const blob = new Blob([lines.join("\n")], { type: "text/csv;charset=utf-8" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `concentracao_${data.data_posicao}.csv`
    a.click()
    URL.revokeObjectURL(url)
    toast.success("Exportado.")
  }, [data])

  return (
    <div className="flex h-[calc(100vh-3rem)] overflow-hidden">
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Title row */}
        <div className="shrink-0 bg-white px-6 pt-3.5 pb-3 dark:bg-gray-950">
          <PageHeader
            title="Concentração"
            subtitle="BI · Risco"
            info="Top-10 cedentes e sacados por valor presente da carteira FIDC (QiTech) sobre o PL total do fundo (MEC, soma das classes). Posição diária. Apenas Realinvest."
            actions={
              <div className="flex items-center gap-2">
                <AIQuotaIndicator quota={quotaQ.data} loading={quotaQ.isLoading} />
                <DashboardHeaderActions
                  ai={{ open: ai.open, onToggle: ai.toggle }}
                  onExport={handleExport}
                />
              </div>
            }
          />
        </div>

        {/* Toolbar de filtros (Z3) — Posição + Histórico (§7.1/§7.2) */}
        <div
          className={cx(
            "shrink-0 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
            scrolled && "scroll-shadow",
          )}
        >
          <div className="flex h-[52px] items-center gap-2 px-6">
            <FilterChip
              label="UA"
              value={data?.ua?.nome ?? "—"}
              active={uaParam !== null}
              icon={RiBuilding2Line}
            >
              <OptList
                options={uaOpts}
                selected={uaParam ?? data?.ua?.id ?? null}
                onSelect={(v) => setUaParam(v)}
              />
            </FilterChip>
            <FilterChip
              label="Posição"
              value={posicaoChipValue}
              active={dataParam !== null}
              icon={RiCalendarLine}
            >
              <OptList
                options={dateOpts}
                selected={dataParam}
                onSelect={(v) => setDataParam(v)}
                nullLabel="Última disponível"
              />
            </FilterChip>
            <FilterChip
              label="Histórico"
              value={JANELA_LABEL[janela] ?? "12 meses"}
              active={janela !== "12m"}
              icon={RiHistoryLine}
            >
              <OptList
                options={JANELA_OPTS}
                selected={janela}
                onSelect={(v) => setJanela(v ?? "12m")}
              />
            </FilterChip>
            <div className="ml-auto flex shrink-0 items-center gap-3">
              {suportado && (data?.pl_total ?? 0) > 0 && (
                <span className="text-[11px] text-gray-500 dark:text-gray-400">
                  PL de referência ·{" "}
                  <span className="font-medium tabular-nums text-gray-700 dark:text-gray-300">
                    {fmtMi(data!.pl_total)}
                  </span>
                  {data?.pl_data && (
                    <span className="tabular-nums">
                      {" · "}
                      {fmtDataYY(data.pl_data)}
                    </span>
                  )}
                  {" · "}
                  {data?.pl_origem ?? "MEC"}
                </span>
              )}
              <span className="text-[11px] text-gray-400 dark:text-gray-500">
                {q.isFetching ? "Atualizando…" : "Atualizado"}
              </span>
            </div>
          </div>
        </div>

        {/* Conteúdo */}
        <div ref={scrollRef} className="flex-1 overflow-auto">
          <div className="flex flex-col gap-6 px-6 pt-4 pb-8">
            {data && !suportado && (
              <div className="rounded-md border border-amber-200 bg-amber-50 p-3 text-[13px] text-amber-900 dark:border-amber-900/50 dark:bg-amber-500/10 dark:text-amber-200">
                Concentração ainda não disponível para{" "}
                <b>{data.ua?.nome ?? "esta UA"}</b> — a lógica de cálculo desta
                UA está em construção. Por enquanto, apenas Realinvest.
              </div>
            )}
            {/* Cedentes — tabela ranking (40%) + histórico (60%) na mesma linha.
                items-stretch: o gráfico estica até a altura da tabela (simetria). */}
            <div className="grid grid-cols-1 items-stretch gap-6 xl:grid-cols-[2fr_3fr]">
              <ConcentracaoCard
                titulo="Cedentes"
                posicao={posicao}
                tabela={data?.cedentes}
                plTotal={data?.pl_total}
                top10DeltaPp={deltaTop10Pp(data?.historico_cedentes)}
                provenance={prov}
                loading={loading}
              />
              <HistoricoCard
                titulo="Histórico de concentração — cedentes"
                pontos={data?.historico_cedentes ?? []}
                kpiTop10={data?.cedentes.total_pct_pl ?? 0}
                kpiMaior={data?.cedentes.itens[0]?.pct_pl ?? 0}
                loading={loading}
              />
            </div>

            {/* Sacados — tabela ranking (40%) + histórico (60%) na mesma linha */}
            <div className="grid grid-cols-1 items-stretch gap-6 xl:grid-cols-[2fr_3fr]">
              <ConcentracaoCard
                titulo="Sacados"
                posicao={posicao}
                tabela={data?.sacados}
                plTotal={data?.pl_total}
                top10DeltaPp={deltaTop10Pp(data?.historico_sacados)}
                provenance={prov}
                loading={loading}
              />
              <HistoricoCard
                titulo="Histórico de concentração — sacados"
                pontos={data?.historico_sacados ?? []}
                kpiTop10={data?.sacados.total_pct_pl ?? 0}
                kpiMaior={data?.sacados.itens[0]?.pct_pl ?? 0}
                loading={loading}
              />
            </div>
          </div>
        </div>

        {/* Proveniência — linha de marca A7 (lâmina de consultoria). */}
        <div
          className={cx(
            "flex shrink-0 items-center border-t px-6 py-1.5",
            "border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900/40",
          )}
        >
          <span className="text-[11px] text-gray-500 dark:text-gray-400">
            Dados fornecidos pela administradora e modelados pela consultoria A7
            Credit. Posição {fmtData(data?.data_posicao, true)}.
          </span>
        </div>
      </div>

      <AIPanel
        open={ai.open}
        onClose={() => ai.setOpen(false)}
        context={aiContext}
        insights={insights}
        sendMessage={send}
      />
    </div>
  )
}
