// CadastralAnalysisView — análise cadastral (cadastral_analyst) no cockpit.
//
// Em cima, os dados coletados (CadastralCard, fonte oficial); embaixo, o
// julgamento do agente sobre a saúde cadastral.

"use client"

import { tableTokens } from "@/design-system/tokens/table"
import { type CadastralAnalysis } from "@/lib/credito-client"
import { cx } from "@/lib/utils"
import { CadastralCard } from "./CadastralCard"

const SEV_TONE: Record<string, string> = {
  alta: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
  media: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
  baixa: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
}
const SIT_TONE: Record<string, string> = {
  ativa: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
  irregular: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
  desconhecida: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
}

export function CadastralAnalysisView({
  dossierId,
  output,
}: {
  dossierId: string
  output: CadastralAnalysis
}) {
  return (
    <div className="space-y-4">
      {/* Dados coletados (fonte oficial) */}
      <CadastralCard dossierId={dossierId} />

      {/* Julgamento do agente */}
      <div className="space-y-3">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-gray-900 dark:text-gray-50">
            Leitura do analista IA
          </p>
          <span className={cx(tableTokens.badge, SIT_TONE[output.situacao_cadastral] ?? SIT_TONE.desconhecida)}>
            {output.situacao_cadastral}
          </span>
        </div>
        <p className="text-sm text-gray-900 dark:text-gray-100">{output.resumo_executivo}</p>

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label="Tempo de atividade" value={output.tempo_atividade_leitura} />
          <Field label="Aderência da atividade (CNAE)" value={output.aderencia_atividade} />
          <Field label="Capital vs porte" value={output.porte_capital_leitura} />
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
                  <p className="min-w-0 flex-1 text-xs text-gray-900 dark:text-gray-100">
                    <span className="capitalize text-gray-500 dark:text-gray-400">{p.tipo}: </span>
                    {p.observacao}
                  </p>
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="rounded-md bg-blue-50/60 p-2.5 dark:bg-blue-500/10">
          <p className={cx(tableTokens.header, "mb-0.5 text-blue-700 dark:text-blue-300")}>
            Leitura para crédito
          </p>
          <p className="text-sm text-gray-900 dark:text-gray-100">{output.leitura_para_credito}</p>
        </div>
      </div>
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className={tableTokens.header}>{label}</span>
      <span className="text-sm text-gray-900 dark:text-gray-100">{value}</span>
    </div>
  )
}
