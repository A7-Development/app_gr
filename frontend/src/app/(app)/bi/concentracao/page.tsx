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
import { toast } from "sonner"

import { PageHeader } from "@/design-system/components/PageHeader"
import { DashboardHeaderActions } from "@/design-system/components/DashboardHeaderActions"
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

export default function ConcentracaoPage() {
  const q = useQuery({
    queryKey: ["bi", "concentracao"],
    queryFn: () => biConcentracao.get(),
  })

  const data = q.data?.data
  const loading = q.isLoading
  const posicao = fmtData(data?.data_posicao)

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

        {/* Conteúdo */}
        <div className="flex-1 overflow-auto">
          <div className="flex flex-col gap-6 px-6 pt-4 pb-8">
            {/* Tabelas — Cedentes | Sacados */}
            <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
              <ConcentracaoCard
                titulo="Cedentes"
                eyebrow="Cedentes"
                posicao={posicao}
                tabela={data?.cedentes}
                loading={loading}
              />
              <ConcentracaoCard
                titulo="Sacados"
                eyebrow="Sacados"
                posicao={posicao}
                tabela={data?.sacados}
                loading={loading}
              />
            </div>

            {/* Histórico — Cedentes | Sacados */}
            <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
              <HistoricoCard
                titulo="Histórico de concentração — cedentes"
                labelMaior="Maior cedente"
                pontos={data?.historico_cedentes ?? []}
                kpiTop10={data?.cedentes.total_pct_pl ?? 0}
                kpiMaior={data?.cedentes.itens[0]?.pct_pl ?? 0}
                loading={loading}
              />
              <HistoricoCard
                titulo="Histórico de concentração — sacados"
                labelMaior="Maior sacado"
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
