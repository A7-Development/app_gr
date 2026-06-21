// SocialContractAnalysisView — análise societária em duas camadas:
//
//   Camada 1 — FATOS determinísticos (GET /societario): ficha do contrato
//   homologado, quadro societário (CPF redactado), estrutura e CRUZAMENTOS com
//   o cadastro oficial. Mesmo payload que a read-tool entregou ao agente (§14).
//
//   Camada 2 — JULGAMENTO do agente (social_contract_analyst).
//
// Fase 1 / Etapa 2: a camada 2 renderiza via <SectionRenderer> (vocabulário de
// blocos). A camada 1 (produtor "consulta/silver") segue como está — vira
// Ficha/Tabela via Contrato de Dados na Etapa 4.

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import { RiCheckLine, RiCloseLine, RiErrorWarningLine } from "@remixicon/react"

import { SectionRenderer } from "@/design-system/components/SectionRenderer"
import {
  DenseTable,
  type DenseColumn,
  type DenseRow,
} from "@/design-system/components/DenseTable"
import { tableTokens } from "@/design-system/tokens/table"
import {
  credito,
  type SocialContractAnalysis,
  type SocietarioPayload,
} from "@/lib/credito-client"
import { cx } from "@/lib/utils"
import { socialContractToSection } from "../_lib/section-mappers"

const SEV_TONE: Record<string, string> = {
  alert: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
  ok: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
  informational: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
}

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })

function fmtBRL(v: unknown): string {
  const n = Number(v)
  return Number.isFinite(n) ? brl.format(n) : "—"
}

// Quadro societário (DenseTable). CPF permanece REDACTADO — só os 2 últimos
// dígitos, formato `***.***.***-NN`, nunca o valor cru. Participação mantém o
// formato original (número cru + "%"), por isso renderiza como texto.
const SOCIOS_COLUMNS: DenseColumn[] = [
  { key: "nome", label: "Sócio", format: "texto" },
  { key: "cpf", label: "CPF", format: "texto" },
  { key: "participacao", label: "Participação", format: "texto", align: "right" },
]

function sociosRows(
  socios: { nome: string; cpf_ultimos4: string | null; participacao_pct: number | null }[],
): DenseRow[] {
  return socios.map((s) => ({
    nome: s.nome,
    cpf: s.cpf_ultimos4 ? `***.***.***-${s.cpf_ultimos4.slice(-2)}` : "—",
    participacao: s.participacao_pct != null ? `${s.participacao_pct}%` : "—",
  }))
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
          value={e?.idade_empresa_anos != null ? `${e.idade_empresa_anos} anos` : "—"}
        />
        <Aggregate label="Sócios" value={String(e?.n_socios ?? "—")} />
      </div>

      {/* Quadro societário */}
      {c?.socios && c.socios.length > 0 && (
        <DenseTable columns={SOCIOS_COLUMNS} rows={sociosRows(c.socios)} />
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
                <RiCheckLine className="mt-0.5 size-3.5 shrink-0 text-emerald-600" aria-hidden />
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
                    (contrato: {String(cz.contrato ?? "—")} · oficial: {String(cz.oficial ?? "—")})
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

  return (
    <div className="space-y-4">
      {/* Camada 1 — fatos */}
      {data && data.encontrado && <DeterministicPanel data={data} />}

      {/* Camada 2 — julgamento (via vocabulário de blocos) */}
      <SectionRenderer section={socialContractToSection(output)} mode="work" />
    </div>
  )
}
