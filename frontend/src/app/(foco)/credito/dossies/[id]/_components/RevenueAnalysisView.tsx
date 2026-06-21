// RevenueAnalysisView — análise de faturamento no cockpit.
//
// Duas camadas, fiéis à tese (§14): em cima, os NÚMEROS determinísticos
// (fonte: endpoint /faturamento/analytics — os mesmos fatos que o agente leu);
// embaixo, o JULGAMENTO do agente (revenue_analyst).
//
// Fase 1 / Etapa 2: a camada de julgamento agora renderiza via <SectionRenderer>
// (vocabulário de blocos), não mais JSX bespoke. A camada determinística segue
// como está — é o produtor "consulta/silver" que vira Ficha/Tabela via Contrato
// de Dados na Etapa 4. Ver docs/esteira-credito-interface-camadas.md.

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"

import { SectionRenderer } from "@/design-system/components/SectionRenderer"
import {
  DenseTable,
  type DenseColumn,
  type DenseRow,
} from "@/design-system/components/DenseTable"
import { tableTokens } from "@/design-system/tokens/table"
import {
  credito,
  type FaturamentoAnalytics,
  type RevenueAnalysis,
} from "@/lib/credito-client"
import { cx } from "@/lib/utils"
import { revenueToSection } from "../_lib/section-mappers"

type FaturamentoAnalyticsOk = Extract<FaturamentoAnalytics, { encontrado: true }>

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })

function fmtBRL(n: number | null | undefined): string {
  return typeof n === "number" && Number.isFinite(n) ? brl.format(n) : "—"
}

function fmtMonth(s: string): string {
  const m = /^(\d{4})-(\d{2})$/.exec(s)
  if (!m) return s
  const months = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
  const idx = Number(m[2]) - 1
  return months[idx] ? `${months[idx]}/${m[1].slice(2)}` : s
}

// Série mensal de receita (DenseTable). Os meses são LINHAS, então DenseTable
// simples (não .Series). O marcador de outlier é preservado como sufixo textual
// "· outlier" no rótulo do mês (DenseTable só renderiza valores textuais/numéricos).
const SERIE_COLUMNS: DenseColumn[] = [
  { key: "mes", label: "Mês", format: "texto" },
  { key: "receita", label: "Receita", format: "brl" },
]

export function RevenueAnalysisView({
  dossierId,
  output,
}: {
  dossierId: string
  output: RevenueAnalysis
}) {
  const { data } = useQuery({
    queryKey: ["credito", "faturamento-analytics", dossierId],
    queryFn: () => credito.dossies.faturamentoAnalytics(dossierId),
  })

  return (
    <div className="space-y-4">
      {/* Camada 1 — números determinísticos (fonte auditável) */}
      {data && data.encontrado && <DeterministicPanel data={data} />}

      {/* Camada 2 — julgamento do agente (via vocabulário de blocos) */}
      <SectionRenderer section={revenueToSection(output)} mode="work" />
    </div>
  )
}

// ─── Painel determinístico (números da fonte auditável) ──────────────────────

function DeterministicPanel({ data }: { data: FaturamentoAnalyticsOk }) {
  const { analytics, atestacao } = data
  const ag = analytics.agregados
  const serie = analytics.serie

  return (
    <div className="space-y-2 rounded-md border border-gray-200 bg-gray-50/50 p-3 dark:border-gray-800 dark:bg-gray-950/40">
      <SectionTitle>Números (fonte determinística)</SectionTitle>
      <div className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-4">
        <Metric label="Total" value={fmtBRL(ag.total)} />
        <Metric label="Média mensal" value={fmtBRL(ag.media)} />
        <Metric
          label="Tendência"
          value={`${analytics.tendencia.direcao ?? "—"} (${analytics.tendencia.variacao_periodo_pct ?? 0}%)`}
        />
        <Metric
          label="Meses"
          value={`${ag.n_meses ?? serie.length}${
            analytics.qualidade.soma_confere === false ? " · soma ≠" : ""
          }`}
        />
      </div>

      {serie.length > 0 && (
        <DenseTable
          columns={SERIE_COLUMNS}
          rows={serie.map<DenseRow>((r) => {
            const isOut = analytics.outliers.some((o) => o.mes === r.mes)
            return {
              mes: `${fmtMonth(r.mes)}${isOut ? " · outlier" : ""}`,
              receita: r.receita_bruta,
            }
          })}
        />
      )}

      {/* Sinais de atestação (determinísticos) */}
      <div className="flex flex-wrap gap-1.5">
        <FactBadge ok={atestacao.assinado === true} label={atestacao.assinado ? "Assinado" : "Sem assinatura"} />
        {atestacao.idade_meses != null && (
          <FactBadge
            ok={atestacao.recente !== false}
            label={`${atestacao.idade_meses} mês(es)${atestacao.recente === false ? " · antigo" : ""}`}
          />
        )}
        {atestacao.emitente_confere != null && (
          <FactBadge
            ok={atestacao.emitente_confere === true}
            label={atestacao.emitente_confere ? "Emitente confere" : "Emitente difere"}
          />
        )}
        {atestacao.tem_ressalva && <FactBadge ok={false} label="Com ressalva" />}
      </div>
    </div>
  )
}

// ─── Primitivos locais ───────────────────────────────────────────────────────

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <p className="text-sm font-medium text-gray-900 dark:text-gray-50">{children}</p>
  )
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {label}
      </span>
      <span className="text-xs font-medium capitalize tabular-nums text-gray-900 dark:text-gray-100">
        {value}
      </span>
    </div>
  )
}

function FactBadge({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span
      className={cx(
        tableTokens.badge,
        ok
          ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
          : "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
      )}
    >
      {label}
    </span>
  )
}
