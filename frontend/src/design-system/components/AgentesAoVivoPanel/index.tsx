// src/design-system/components/AgentesAoVivoPanel/index.tsx
//
// "Caixa de vidro" — painel direito persistente do construtor de dossiê
// (handoff redesenho, tratamento B2: passos estruturados + confiança + rastro).
// Mostra TODOS os agentes do dossiê, não só os da estação aberta:
//   1. ESTA ESTAÇÃO  — passos do agente da estação ativa (status + fonte + detalhe).
//   2. TAMBÉM EM ANDAMENTO — agentes rodando em 2º plano, com stream ao vivo.
// Presentational: a página alimenta os dados (node_runs / tools_log / estados).

"use client"

import {
  RiCheckboxCircleFill,
  RiErrorWarningFill,
  RiLoader4Line,
  RiShieldCheckLine,
} from "@remixicon/react"

import { AgentPulseDot } from "@/design-system/components/AgentLiveChip"
import { ProvenanceChip } from "@/design-system/components/Provenance"
import {
  agentContainerTokens,
  provenanceTokens,
  type ProvenanceOrigin,
} from "@/design-system/tokens/provenance"
import { cx } from "@/lib/utils"

export type GlassStepStatus = "ok" | "atencao" | "erro" | "rodando"

export type GlassStep = {
  id: string
  status: GlassStepStatus
  /** O que o agente fez (ex.: "Leu o relatório", "Consultou Serasa"). */
  label: string
  /** Assinatura da fonte do passo → chip de proveniência (doc/fonte/…). */
  source?: ProvenanceOrigin
  sourceLabel?: string
  /** Linha secundária (ex.: "14 págs · soma confere"). */
  detail?: string
  /** Abre a evidência do passo (drill até a fonte). */
  onEvidence?: () => void
}

export type GlassStreamLine = {
  origin?: ProvenanceOrigin
  text: string
  /** Última linha digitando ao vivo (caret). */
  typing?: boolean
}

export type GlassAlsoRunning = {
  id: string
  label: string
  /** "2º plano · ~40s". */
  hint?: string
  stream?: GlassStreamLine[]
  onOpen?: () => void
}

export type AgentesAoVivoPanelProps = {
  activeStationLabel: string
  /** "concluído" · "em curso" · "aguardando". */
  activeStationStatus?: string
  confidence?: "alta" | "media" | "baixa" | null
  steps: GlassStep[]
  alsoRunning?: GlassAlsoRunning[]
  /** Contagem de agentes ativos no dossiê (chip do header). */
  activeCount?: number
  className?: string
}

const EYEBROW =
  "text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-500"

function StepIcon({ status }: { status: GlassStepStatus }) {
  switch (status) {
    case "ok":
      return (
        <RiCheckboxCircleFill
          className="mt-px size-4 shrink-0"
          style={{ color: provenanceTokens.documento.color }}
          aria-hidden
        />
      )
    case "atencao":
      return (
        <RiErrorWarningFill
          className="mt-px size-4 shrink-0 text-amber-500"
          aria-hidden
        />
      )
    case "erro":
      return (
        <RiErrorWarningFill className="mt-px size-4 shrink-0 text-red-500" aria-hidden />
      )
    case "rodando":
      return (
        <RiLoader4Line
          className="mt-px size-4 shrink-0 animate-spin"
          style={{ color: provenanceTokens.agente.color }}
          aria-hidden
        />
      )
  }
}

function ConfidenceChip({ level }: { level: "alta" | "media" | "baixa" }) {
  const tone =
    level === "alta"
      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
      : level === "baixa"
        ? "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300"
        : "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300"
  const label = level === "alta" ? "alta" : level === "baixa" ? "baixa" : "média"
  return (
    <span
      className={cx(
        "inline-flex h-[18px] items-center gap-1 rounded-full px-[7px] text-[10px] font-semibold leading-none",
        tone,
      )}
    >
      <RiShieldCheckLine className="size-3 shrink-0" aria-hidden />
      Confiança {label}
    </span>
  )
}

export function AgentesAoVivoPanel({
  activeStationLabel,
  activeStationStatus,
  confidence,
  steps,
  alsoRunning = [],
  activeCount = 0,
  className,
}: AgentesAoVivoPanelProps) {
  return (
    <aside
      aria-label="Agentes ao vivo"
      className={cx(
        "flex h-screen w-[308px] shrink-0 flex-col border-l border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
        className,
      )}
    >
      {/* Header */}
      <div className="shrink-0 border-b border-gray-200 px-4 pb-3 pt-3.5 dark:border-gray-800">
        <div className="flex items-center gap-2">
          <AgentPulseDot size={8} />
          <span className="text-sm font-semibold text-gray-900 dark:text-gray-50">
            Agentes ao vivo
          </span>
          {activeCount > 0 && (
            <span
              className="ml-auto inline-flex h-[18px] items-center rounded-full px-2 text-[10px] font-semibold leading-none"
              style={{
                background: provenanceTokens.agente.chipBg,
                color: provenanceTokens.agente.chipText,
              }}
            >
              {activeCount} ativo{activeCount > 1 ? "s" : ""}
            </span>
          )}
        </div>
        <p className="mt-1 text-[11px] leading-snug text-gray-400 dark:text-gray-500">
          Caixa de vidro · todos os agentes do dossiê, não só desta etapa
        </p>
      </div>

      {/* Corpo */}
      <div className="flex-1 space-y-5 overflow-y-auto px-4 py-4">
        {/* Esta estação */}
        <section>
          <p className={EYEBROW}>Esta estação</p>
          <div className="mt-1.5 flex items-center justify-between gap-2">
            <span className="truncate text-[13px] text-gray-700 dark:text-gray-300">
              {activeStationLabel}
              {activeStationStatus ? ` · ${activeStationStatus}` : ""}
            </span>
            {confidence && <ConfidenceChip level={confidence} />}
          </div>

          {steps.length > 0 ? (
            <ol className="mt-2.5 space-y-2.5">
              {steps.map((s) => (
                <li key={s.id} className="flex items-start gap-2">
                  <StepIcon status={s.status} />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-1.5">
                      <span className="text-[13px] text-gray-900 dark:text-gray-100">
                        {s.label}
                      </span>
                      {s.source && (
                        <ProvenanceChip origin={s.source}>
                          {s.sourceLabel ?? s.source}
                        </ProvenanceChip>
                      )}
                    </div>
                    {s.detail && (
                      <p className="mt-0.5 text-[11px] text-gray-400 dark:text-gray-500">
                        {s.detail}
                        {s.onEvidence && (
                          <>
                            {" · "}
                            <button
                              type="button"
                              onClick={s.onEvidence}
                              className="font-medium text-blue-600 hover:underline dark:text-blue-400"
                            >
                              ver evidência
                            </button>
                          </>
                        )}
                      </p>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          ) : (
            <p className="mt-2 text-[11px] text-gray-400 dark:text-gray-500">
              Sem passos registrados ainda.
            </p>
          )}
        </section>

        {/* Também em andamento */}
        {alsoRunning.length > 0 && (
          <section>
            <p className={EYEBROW}>Também em andamento</p>
            <div className="mt-2 space-y-3">
              {alsoRunning.map((a) => (
                <div key={a.id}>
                  <button
                    type="button"
                    onClick={a.onOpen}
                    disabled={!a.onOpen}
                    className="flex w-full items-center gap-2 text-left disabled:cursor-default"
                  >
                    <AgentPulseDot size={7} />
                    <span className="truncate text-[13px] font-medium text-gray-800 dark:text-gray-200">
                      {a.label}
                    </span>
                    {a.hint && (
                      <span className="ml-auto shrink-0 text-[11px] text-gray-400 dark:text-gray-500">
                        {a.hint}
                      </span>
                    )}
                  </button>
                  {a.stream && a.stream.length > 0 && (
                    <div
                      className="mt-1.5 space-y-0.5 rounded border-l-2 px-2.5 py-1.5 font-mono text-[11px] leading-relaxed"
                      style={{
                        background: agentContainerTokens.bg,
                        borderColor: agentContainerTokens.divider,
                      }}
                    >
                      {a.stream.map((line, i) => (
                        <p
                          key={i}
                          className="text-gray-600 dark:text-gray-300"
                          style={
                            line.origin
                              ? { color: provenanceTokens[line.origin].chipText }
                              : undefined
                          }
                        >
                          {line.origin && (
                            <span
                              className="mr-1 font-semibold"
                              style={{ color: provenanceTokens[line.origin].color }}
                            >
                              {provenanceTokens[line.origin].supPrefix}
                            </span>
                          )}
                          <span className="text-gray-700 dark:text-gray-300">
                            {line.text}
                          </span>
                          {line.typing && (
                            <span
                              className="ml-px inline-block h-3 w-1.5 translate-y-px bg-current motion-safe:animate-pulse"
                              aria-hidden
                            />
                          )}
                        </p>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </section>
        )}
      </div>

      {/* Rodapé */}
      <div className="mt-auto shrink-0 border-t border-gray-200 px-4 py-2.5 dark:border-gray-800">
        <p className="text-[11px] text-gray-400 dark:text-gray-500">
          Clique num passo para abrir a evidência
        </p>
      </div>
    </aside>
  )
}
