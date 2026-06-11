// SocialContractAnalysisView — análise societária em duas camadas (espelha
// RevenueAnalysisView):
//
//   Camada 1 — FATOS determinísticos (GET /societario): ficha do contrato
//   homologado, quadro societário (CPF redactado), estrutura (soma das
//   participações, controlador, idade) e CRUZAMENTOS com o cadastro oficial.
//   Mesmo payload que a read-tool entregou ao agente — a tela mostra o que
//   ele julgou (§14).
//
//   Camada 2 — JULGAMENTO do agente (output do social_contract_analyst):
//   poderes de assinatura, alterações de QSA, objeto x operação, restrições
//   e checklist. Zero JSON cru.

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { RiCheckLine, RiCloseLine, RiErrorWarningLine } from "@remixicon/react"

import { tableTokens } from "@/design-system/tokens/table"
import {
  credito,
  type SocialContractAnalysis,
  type SocietarioPayload,
} from "@/lib/credito-client"
import { cx } from "@/lib/utils"

const SEV_TONE: Record<string, string> = {
  critical: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
  important: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
  informational: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
  alert: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
  ok: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <p className={cx(tableTokens.header, "mb-1")}>{children}</p>
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className={cx(tableTokens.header, "mb-0.5")}>{label}</p>
      <div className="text-sm text-gray-900 dark:text-gray-100">{children}</div>
    </div>
  )
}

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })

function fmtBRL(v: unknown): string {
  const n = Number(v)
  return Number.isFinite(n) ? brl.format(n) : "—"
}

// ─── Camada 1 — fatos determinísticos ───────────────────────────────────────

function DeterministicPanel({ data }: { data: SocietarioPayload }) {
  const c = data.contrato
  const e = data.estrutura
  return (
    <div className="space-y-3 rounded-md bg-gray-50/70 p-3 dark:bg-gray-900/40">
      <div className="flex flex-wrap items-center gap-2">
        <p className="text-xs font-semibold text-gray-700 dark:text-gray-300">
          Ficha do contrato (fonte determinística)
        </p>
        {data.homologado ? (
          <span className={cx(tableTokens.badge, SEV_TONE.ok)}>homologada</span>
        ) : (
          <span className={cx(tableTokens.badge, SEV_TONE.alert)}>
            aguardando homologação
          </span>
        )}
        {data.fonte?.ajustado_pelo_analista && (
          <span className={cx(tableTokens.badge, SEV_TONE.informational)}>
            ajustada pelo analista
          </span>
        )}
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
        <Aggregate label="Capital social" value={fmtBRL(c?.capital_social)} />
        <Aggregate label="Constituição" value={c?.data_constituicao ?? "—"} />
        <Aggregate
          label="Idade da empresa"
          value={
            e?.idade_empresa_anos != null ? `${e.idade_empresa_anos} anos` : "—"
          }
        />
        <Aggregate label="Sócios" value={String(e?.n_socios ?? "—")} />
      </div>

      {/* Quadro societário */}
      {c?.socios && c.socios.length > 0 && (
        <div className="overflow-hidden rounded-md border border-gray-200 dark:border-gray-800">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50/60 dark:border-gray-900 dark:bg-gray-900/40">
                <th className={cx(tableTokens.header, "px-3 py-1.5 text-left")}>Sócio</th>
                <th className={cx(tableTokens.header, "px-3 py-1.5 text-left")}>CPF</th>
                <th className={cx(tableTokens.header, "px-3 py-1.5 text-right")}>
                  Participação
                </th>
              </tr>
            </thead>
            <tbody>
              {c.socios.map((s, i) => (
                <tr
                  key={i}
                  className="border-b border-gray-50 last:border-0 dark:border-gray-900/60"
                >
                  <td className={cx(tableTokens.cellText, "px-3 py-1")}>{s.nome}</td>
                  <td className={cx(tableTokens.cellTextMono, "px-3 py-1")}>
                    {s.cpf_ultimos4 ? `***.***.***-${s.cpf_ultimos4.slice(-2)}` : "—"}
                  </td>
                  <td className={cx(tableTokens.cellNumber, "px-3 py-1 text-right")}>
                    {s.participacao_pct != null ? `${s.participacao_pct}%` : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {e && (
        <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs">
          <span
            className={cx(
              "flex items-center gap-1",
              e.soma_confere === false
                ? "text-amber-700 dark:text-amber-300"
                : "text-gray-600 dark:text-gray-400",
            )}
          >
            {e.soma_confere === false ? (
              <RiErrorWarningLine className="size-3.5" aria-hidden />
            ) : (
              <RiCheckLine className="size-3.5 text-emerald-600" aria-hidden />
            )}
            participações somam {e.soma_participacoes_pct ?? "—"}%
          </span>
          {e.controlador && (
            <span className="text-gray-600 dark:text-gray-400">
              controle: <strong className="font-medium">{e.controlador.nome}</strong> (
              {e.controlador.participacao_pct}%
              {e.controlador.controle_majoritario ? " · majoritário" : ""})
            </span>
          )}
        </div>
      )}

      {/* Cruzamentos com o cadastro oficial */}
      {data.cruzamentos && data.cruzamentos.length > 0 && (
        <div className="space-y-1 border-t border-gray-200/60 pt-2 dark:border-gray-800/60">
          <p className={cx(tableTokens.header)}>Cruzamentos com o registro oficial</p>
          {data.cruzamentos.map((cz, i) => (
            <div key={i} className="flex items-start gap-1.5 text-xs">
              {cz.confere === true ? (
                <RiCheckLine
                  className="mt-0.5 size-3.5 shrink-0 text-emerald-600"
                  aria-hidden
                />
              ) : cz.confere === false ? (
                <RiCloseLine className="mt-0.5 size-3.5 shrink-0 text-amber-600" aria-hidden />
              ) : (
                <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-gray-300 dark:bg-gray-700" />
              )}
              <span
                className={cx(
                  cz.confere === false
                    ? "text-amber-700 dark:text-amber-300"
                    : "text-gray-600 dark:text-gray-400",
                )}
              >
                {cz.detalhe}
                {cz.confere === false && (
                  <span className={cx(tableTokens.cellTextMono, "ml-1")}>
                    (contrato: {String(cz.contrato ?? "—")} · oficial:{" "}
                    {String(cz.oficial ?? "—")})
                  </span>
                )}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function Aggregate({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {label}
      </span>
      <span className="text-xs font-medium tabular-nums text-gray-900 dark:text-gray-100">
        {value}
      </span>
    </div>
  )
}

// ─── View completa ──────────────────────────────────────────────────────────

export function SocialContractAnalysisView({
  dossierId,
  output,
}: {
  dossierId: string
  output: SocialContractAnalysis
}) {
  const { data } = useQuery({
    queryKey: ["credito", "societario", dossierId],
    queryFn: () => credito.dossies.societario(dossierId),
  })

  const signing = Object.entries(output.signing_powers ?? {})

  return (
    <div className="space-y-4">
      {/* Camada 1 — fatos */}
      {data && data.encontrado && <DeterministicPanel data={data} />}

      {/* Camada 2 — julgamento */}
      <div className="space-y-3">
        <SectionTitle>Leitura do analista IA</SectionTitle>
        <p className="text-sm text-gray-900 dark:text-gray-100">{output.summary}</p>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Alterações recentes de QSA (24m)">
            <span className="font-medium">
              {output.qsa_changes_recent ? "Sim — atenção" : "Não identificadas"}
            </span>
            {output.qsa_changes_detail && (
              <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
                {output.qsa_changes_detail}
              </p>
            )}
          </Field>
          <Field label="Objeto social x operação">
            <span className="font-medium">
              {output.object_compatible_with_operation ? "Compatível" : "Incompatível"}
            </span>
            <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
              {output.object_compatibility_rationale}
            </p>
          </Field>
        </div>

        {signing.length > 0 && (
          <div>
            <SectionTitle>Poderes de assinatura</SectionTitle>
            <ul className="space-y-1">
              {signing.map(([nome, forma]) => (
                <li key={nome} className="flex items-baseline gap-2 text-sm">
                  <span className="font-medium text-gray-900 dark:text-gray-100">{nome}</span>
                  <span className={tableTokens.cellSecondary}>{forma}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {output.statutory_restrictions.length > 0 && (
          <div>
            <SectionTitle>Restrições estatutárias</SectionTitle>
            <ul className="list-inside list-disc space-y-0.5 text-sm text-gray-700 dark:text-gray-300">
              {output.statutory_restrictions.map((r, i) => (
                <li key={i}>{r}</li>
              ))}
            </ul>
          </div>
        )}

        {output.checklist_results.length > 0 && (
          <div>
            <SectionTitle>Checklist</SectionTitle>
            <ul className="space-y-1.5">
              {output.checklist_results.map((c, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 rounded-md border border-gray-100 bg-gray-50/50 p-2 dark:border-gray-900 dark:bg-gray-950/40"
                >
                  <span className={cx(tableTokens.badge, SEV_TONE[c.status] ?? SEV_TONE.informational)}>
                    {c.code}
                  </span>
                  <span className="min-w-0 text-xs text-gray-700 dark:text-gray-300">
                    <strong className="font-medium">{c.description}</strong>
                    {" — "}
                    {c.rationale}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}
