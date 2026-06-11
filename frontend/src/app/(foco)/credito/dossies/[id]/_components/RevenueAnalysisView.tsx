// RevenueAnalysisView — mostra a análise de faturamento no cockpit.
//
// Duas camadas, fiéis à tese (§14): em cima, os NÚMEROS determinísticos
// (fonte: endpoint /faturamento/analytics — os mesmos fatos que o agente leu);
// embaixo, o JULGAMENTO do agente (revenue_analyst). O analista vê o número
// auditável e a leitura lado a lado.

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import {
  RiAlertLine,
  RiCheckLine,
  RiInformationLine,
} from "@remixicon/react"

import { tableTokens } from "@/design-system/tokens/table"
import {
  credito,
  type FaturamentoAnalytics,
  type RevenueAnalysis,
} from "@/lib/credito-client"
import { cx } from "@/lib/utils"

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

const SEV_TONE: Record<string, string> = {
  alta: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
  media: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
  baixa: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
}
const NIVEL_TONE: Record<string, string> = {
  alto: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
  medio: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
  baixo: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
}

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

      {/* Camada 2 — julgamento do agente */}
      <div className="space-y-3">
        <SectionTitle>Leitura do analista IA</SectionTitle>
        <p className="text-sm text-gray-900 dark:text-gray-100">{output.resumo_executivo}</p>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Tendência">
            <span className="font-medium capitalize">{output.tendencia.direcao}</span>
            <span className={cx(tableTokens.cellSecondary, "ml-1")}>
              · {output.tendencia.intensidade}
            </span>
            <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>{output.tendencia.leitura}</p>
          </Field>
          <Field label="Sazonalidade">
            <span className="font-medium">
              {output.sazonalidade.detectada ? "Detectada" : "Sem padrão claro"}
            </span>
            {!output.sazonalidade.confiavel && (
              <span className={cx(tableTokens.badge, SEV_TONE.baixa, "ml-1.5")}>
                leitura fraca
              </span>
            )}
            {output.sazonalidade.padrao && (
              <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
                {output.sazonalidade.padrao}
              </p>
            )}
          </Field>
        </div>

        {output.pontos_de_atencao.length > 0 && (
          <div>
            <p className={cx(tableTokens.header, "mb-1")}>Pontos de atenção</p>
            <ul className="space-y-1.5">
              {output.pontos_de_atencao.map((p, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 rounded-md border border-gray-100 bg-gray-50/50 p-2 dark:border-gray-900 dark:bg-gray-950/40"
                >
                  <span className={cx(tableTokens.badge, SEV_TONE[p.severidade] ?? SEV_TONE.baixa)}>
                    {p.severidade}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-xs text-gray-900 dark:text-gray-100">
                      {p.mes ? `${fmtMonth(p.mes)} · ` : ""}
                      <span className="capitalize">{p.tipo}</span>
                      <span
                        className={cx(
                          "ml-1.5",
                          p.esperado_ou_anomalo === "anomalo"
                            ? "text-red-600 dark:text-red-400"
                            : "text-gray-500 dark:text-gray-400",
                        )}
                      >
                        ({p.esperado_ou_anomalo})
                      </span>
                    </p>
                    <p className={tableTokens.cellSecondary}>{p.observacao}</p>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Qualidade do dado">
            <span className="inline-flex items-center gap-1">
              {output.qualidade_do_dado.soma_confere ? (
                <RiCheckLine className="size-3.5 text-emerald-600 dark:text-emerald-400" aria-hidden />
              ) : (
                <RiAlertLine className="size-3.5 text-amber-600 dark:text-amber-400" aria-hidden />
              )}
              <span className="text-xs">
                {output.qualidade_do_dado.n_meses} mês(es)
                {output.qualidade_do_dado.meses_faltantes.length > 0 &&
                  ` · faltam ${output.qualidade_do_dado.meses_faltantes.length}`}
              </span>
            </span>
            <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
              {output.qualidade_do_dado.observacao}
            </p>
          </Field>
          <Field label="Credibilidade do documento">
            <span className={cx(tableTokens.badge, NIVEL_TONE[output.credibilidade_documento.nivel] ?? NIVEL_TONE.medio)}>
              {output.credibilidade_documento.nivel}
            </span>
            <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
              {output.credibilidade_documento.leitura}
            </p>
            {output.credibilidade_documento.ressalvas.length > 0 && (
              <ul className="mt-1 space-y-0.5">
                {output.credibilidade_documento.ressalvas.map((r, i) => (
                  <li key={i} className="flex items-start gap-1 text-[11px] text-amber-700 dark:text-amber-300">
                    <RiInformationLine className="mt-0.5 size-3 shrink-0" aria-hidden />
                    {r}
                  </li>
                ))}
              </ul>
            )}
          </Field>
        </div>

        <div className="rounded-md bg-blue-50/60 p-2.5 dark:bg-blue-500/10">
          <p className={cx(tableTokens.header, "mb-0.5 text-blue-700 dark:text-blue-300")}>
            Leitura para crédito
          </p>
          <p className="text-sm text-gray-900 dark:text-gray-100">
            {output.leitura_para_credito}
          </p>
        </div>
      </div>
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
        <div className="overflow-hidden rounded-md border border-gray-200 dark:border-gray-800">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/60 dark:border-gray-900 dark:bg-gray-900/40">
                <th className={cx(tableTokens.header, "px-3 py-1 text-left")}>Mês</th>
                <th className={cx(tableTokens.header, "px-3 py-1 text-right")}>Receita</th>
              </tr>
            </thead>
            <tbody>
              {serie.map((r) => {
                const isOut = analytics.outliers.some((o) => o.mes === r.mes)
                return (
                  <tr key={r.mes} className="border-b border-gray-50 last:border-0 dark:border-gray-900/60">
                    <td className="px-3 py-0.5">
                      <span className={tableTokens.cellText}>{fmtMonth(r.mes)}</span>
                      {isOut && (
                        <span className={cx(tableTokens.badge, SEV_TONE.media, "ml-1.5")}>outlier</span>
                      )}
                    </td>
                    <td className="px-3 py-0.5 text-right">
                      <span className={tableTokens.cellNumber}>{fmtBRL(r.receita_bruta)}</span>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
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

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className={tableTokens.header}>{label}</span>
      <div className="text-sm text-gray-900 dark:text-gray-100">{children}</div>
    </div>
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
