// src/design-system/components/StationsSidebar/index.tsx
//
// Trilha do modo foco — tratamento A2 "Espinha conectada" (handoff redesenho
// Construtor de Dossiê, 2026-06-18). Timeline vertical: cada estação e um no
// na linha; o gradiente da linha marca percorrido (verde) -> presente (indigo)
// -> futuro (cinza). A trilha CONDUZ ("bussola, nao cadeado"): toda estacao
// pronta e navegavel.
//
// Anatomia: header (← fila · eyebrow · cedente · meta · progresso 4px) ·
// espinha de estacoes (no + linha por estado) · rodape ("Ver dossie · X%" +
// linha da trilha). Mesma interface/props da versao anterior (lista plana).

"use client"

import Link from "next/link"
import {
  RiArrowRightCircleFill,
  RiArticleLine,
  RiCheckboxCircleFill,
  RiCheckLine,
  RiCircleLine,
  RiErrorWarningFill,
  RiFileUploadLine,
  RiHistoryLine,
  RiLockLine,
  RiSparkling2Fill,
  RiTimeLine,
} from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { AgentPulseDot } from "@/design-system/components/AgentLiveChip"
import { provenanceTokens } from "@/design-system/tokens/provenance"
import type { StationState } from "@/design-system/types/section"
import { cx } from "@/lib/utils"

// Vocabulário canônico de estados mora em types/section (dono do contrato, Fase 1).
export type { StationState }

/** Fase interna da estação (handoff playbook JUCESP: as fases vivem no card
 *  da estação ativa na trilha, não como trilho horizontal no header). */
export type StationPhase = {
  label: string
  state: "done" | "active" | "future"
}

export type StationItem = {
  id: string
  label: string
  sublabel?: string
  state: StationState
  /** Fases da estação — renderizadas só quando ela é a ativa (card destacado). */
  phases?: StationPhase[]
  /** Marcador não-interativo da trilha (Abertura/Encerramento) — só visual,
   *  não dispara `onSelect` nem vira foco. */
  decorative?: boolean
}

export type StationsSidebarProps = {
  /** Link "← Fila de análises" no topo. */
  backHref: string
  backLabel?: string
  eyebrow?: string
  /** Nome do cedente / alvo da análise. */
  title: string
  /** Meta 11.5px (ex.: "DC-2026-0148 · R$ 2,5 mi pleiteado"). */
  meta?: string
  /** Progresso 0–100 + rótulo ("2 de 5"). */
  progressPct: number
  progressLabel: string
  stations: StationItem[]
  activeId: string | null
  onSelect: (id: string) => void
  /** Rodapé: "Ver dossiê · 48% montado". */
  dossierLabel: string
  onOpenDossier?: () => void
  dossierActive?: boolean
  /** Linha da trilha ("Trilha: 23 eventos · último há 4 min"). */
  trailLabel?: string
  className?: string
}

// ─── Cores da espinha (proveniência/estado) ──────────────────────────────────
const C_DONE = "#059669" // verde — percorrido
const C_PRESENT = provenanceTokens.agente.color // indigo #6366F1 — presente
const C_FUTURE = "#E5E7EB" // gray-200 — futuro
const C_RING_ACTIVE = "#C7D2FE" // indigo-200 — borda do card ativo
const C_AMBER = "#F59E0B"

const _DONE = new Set<StationState>(["fechada", "fechada_com_ressalva"])
const _PRESENT = new Set<StationState>(["homologar", "sua_vez", "rodando"])

/** Cor do SEGMENTO de linha que SAI deste nó (para o nó de baixo). */
function segColor(state: StationState): string {
  if (_DONE.has(state)) return C_DONE
  if (_PRESENT.has(state)) return C_PRESENT
  return C_FUTURE
}

/** O nó (círculo 18px) — dupla codificação cor + ícone por estado. */
function StationNode({ state }: { state: StationState }) {
  const base =
    "relative z-10 flex size-[18px] shrink-0 items-center justify-center rounded-full"
  switch (state) {
    case "fechada":
      return (
        <span className={base} style={{ background: C_DONE }}>
          <RiCheckLine className="size-3 text-white" aria-hidden />
        </span>
      )
    case "fechada_com_ressalva":
      return (
        <span
          className={base}
          style={{ background: C_DONE, boxShadow: `0 0 0 1.5px ${C_AMBER}` }}
        >
          <RiCheckLine className="size-3 text-white" aria-hidden />
        </span>
      )
    case "homologar":
    case "sua_vez":
      return (
        <span
          className={cx(base, "bg-white dark:bg-gray-950")}
          style={{ boxShadow: `0 0 0 2px ${C_PRESENT}` }}
        >
          <RiSparkling2Fill
            className="size-[11px]"
            style={{ color: C_PRESENT }}
            aria-hidden
          />
        </span>
      )
    case "rodando":
      return (
        <span
          className={cx(base, "bg-white dark:bg-gray-950")}
          style={{ boxShadow: `0 0 0 2px ${C_PRESENT}` }}
        >
          <AgentPulseDot size={7} />
        </span>
      )
    case "aguardando_documento":
      return (
        <span
          className={cx(
            base,
            "border-[1.5px] border-dashed border-gray-300 bg-white dark:border-gray-600 dark:bg-gray-950",
          )}
        >
          <RiFileUploadLine className="size-[10px] text-gray-400" aria-hidden />
        </span>
      )
    case "em_espera":
      return (
        <span
          className={cx(
            base,
            "border-[1.5px] border-gray-300 bg-white dark:border-gray-600 dark:bg-gray-950",
          )}
        >
          <RiTimeLine className="size-[10px] text-gray-400" aria-hidden />
        </span>
      )
    case "falhou":
      return (
        <span
          className={cx(base, "bg-white dark:bg-gray-950")}
          style={{ boxShadow: `0 0 0 2px ${C_AMBER}` }}
        >
          <RiErrorWarningFill
            className="size-[12px]"
            style={{ color: C_AMBER }}
            aria-hidden
          />
        </span>
      )
    case "bloqueada":
      return (
        <span
          className={cx(
            base,
            "border border-gray-200 bg-gray-100 dark:border-gray-700 dark:bg-gray-900",
          )}
        >
          <RiLockLine className="size-[10px] text-gray-400 dark:text-gray-600" aria-hidden />
        </span>
      )
  }
}

function StationBadge({ state }: { state: StationState }) {
  if (state === "sua_vez") {
    return (
      <span
        className="inline-flex h-[18px] shrink-0 items-center rounded-full px-2 text-[10px] font-semibold leading-none"
        style={{ background: "rgba(59,130,246,0.1)", color: "#2563EB" }}
      >
        sua vez
      </span>
    )
  }
  if (state === "homologar") {
    return (
      <span
        className="inline-flex h-[18px] shrink-0 items-center rounded-full px-2 text-[10px] font-semibold leading-none"
        style={{
          background: provenanceTokens.agente.chipBg,
          color: provenanceTokens.agente.chipText,
        }}
      >
        homologar
      </span>
    )
  }
  return null
}

/** Uma fase dentro do card da estação ativa (done ✓ / active → / future ○). */
function PhaseRow({ phase }: { phase: StationPhase }) {
  const done = phase.state === "done"
  const active = phase.state === "active"
  const Icon = done ? RiCheckboxCircleFill : active ? RiArrowRightCircleFill : RiCircleLine
  const iconColor = done ? C_DONE : active ? "#3B82F6" : "#D1D5DB"
  const textColor = done ? "#6B7280" : active ? "#111827" : "#9CA3AF"
  return (
    <span className="flex items-center gap-1.5">
      <Icon className="size-[15px] shrink-0" style={{ color: iconColor }} aria-hidden />
      <span
        className="truncate text-[12px]"
        style={{ color: textColor, fontWeight: active ? 600 : 400 }}
      >
        {phase.label}
      </span>
    </span>
  )
}

export function StationsSidebar({
  backHref,
  backLabel = "Fila de análises",
  eyebrow = "Análise de crédito",
  title,
  meta,
  progressPct,
  progressLabel,
  stations,
  activeId,
  onSelect,
  dossierLabel,
  onOpenDossier,
  dossierActive,
  trailLabel,
  className,
}: StationsSidebarProps) {
  const n = stations.length
  return (
    <aside
      aria-label="Estações da análise"
      className={cx(
        "flex h-full w-[292px] shrink-0 flex-col border-r border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-925",
        "motion-safe:animate-slide-right-and-fade",
        className,
      )}
    >
      {/* Header */}
      <div className="shrink-0 border-b border-gray-200 px-[18px] pb-4 pt-[18px] dark:border-gray-800">
        <Link
          href={backHref}
          className="text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 transition-colors duration-100 hover:text-blue-600 dark:text-gray-500 dark:hover:text-blue-400"
        >
          ← {backLabel}
        </Link>
        <p className="mt-2.5 text-[11px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-500">
          {eyebrow}
        </p>
        <p className="mt-1 truncate text-sm font-semibold tracking-[-0.01em] text-gray-900 dark:text-gray-50">
          {title}
        </p>
        {meta && (
          <p className="mt-0.5 truncate text-[11.5px] text-gray-500 tabular-nums dark:text-gray-400">
            {meta}
          </p>
        )}
        <div className="mt-3 flex items-center gap-2.5">
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-gray-200 dark:bg-gray-800">
            <div
              className="h-full rounded-full bg-blue-500 transition-[width] duration-150"
              style={{ width: `${Math.max(0, Math.min(100, progressPct))}%` }}
            />
          </div>
          <span className="shrink-0 text-[11px] font-medium text-gray-500 tabular-nums dark:text-gray-400">
            {progressLabel}
          </span>
        </div>
      </div>

      {/* Espinha de estações (A2) */}
      <nav className="flex-1 overflow-y-auto px-[18px] py-4">
        <div className="flex flex-col">
          {stations.map((st, i) => {
            const isActive = !dossierActive && st.id === activeId
            const isBlocked = st.state === "bloqueada"
            const locked = isBlocked || Boolean(st.decorative)
            const topColor = i > 0 ? segColor(stations[i - 1].state) : undefined
            const botColor = i < n - 1 ? segColor(st.state) : undefined
            return (
              <button
                key={st.id}
                type="button"
                onClick={() => !locked && onSelect(st.id)}
                disabled={locked}
                className={cx(
                  "group relative flex gap-3 pb-4 text-left last:pb-0",
                  locked && "cursor-default",
                )}
              >
                {/* Rail: linha + nó */}
                <span className="relative flex w-[18px] shrink-0 justify-center">
                  {topColor && (
                    <span
                      className="absolute left-1/2 top-0 h-[13px] w-0.5 -translate-x-1/2"
                      style={{ background: topColor }}
                      aria-hidden
                    />
                  )}
                  {botColor && (
                    <span
                      className="absolute left-1/2 bottom-0 top-[13px] w-0.5 -translate-x-1/2"
                      style={{ background: botColor }}
                      aria-hidden
                    />
                  )}
                  <span className={cx("mt-1", isBlocked && "opacity-60")}>
                    <StationNode state={st.state} />
                  </span>
                </span>

                {/* Conteúdo */}
                <span className={cx("min-w-0 flex-1", isBlocked && "opacity-55")}>
                  {isActive ? (
                    <span
                      className="block rounded-md border bg-white px-3 py-2 shadow-xs dark:bg-gray-950"
                      style={{ borderColor: C_RING_ACTIVE }}
                    >
                      <span className="flex items-center gap-2">
                        <span className="truncate text-[13px] font-semibold text-gray-900 dark:text-gray-50">
                          {st.label}
                        </span>
                        <StationBadge state={st.state} />
                      </span>
                      {st.phases && st.phases.length > 0 ? (
                        <span className="mt-2 flex flex-col gap-1.5">
                          {st.phases.map((ph, pi) => (
                            <PhaseRow key={`${ph.label}-${pi}`} phase={ph} />
                          ))}
                        </span>
                      ) : (
                        <span
                          className="mt-1 block text-[11px] font-medium"
                          style={{ color: C_PRESENT }}
                        >
                          ▸ você está aqui
                          {st.sublabel ? ` · ${st.sublabel}` : ""}
                        </span>
                      )}
                    </span>
                  ) : (
                    <span className="block pt-px">
                      <span className="flex items-center gap-2">
                        <span
                          className={cx(
                            "truncate text-[13px]",
                            st.state === "bloqueada"
                              ? "text-gray-400 dark:text-gray-600"
                              : "text-gray-700 group-hover:text-gray-900 dark:text-gray-300 dark:group-hover:text-gray-100",
                          )}
                        >
                          {st.label}
                        </span>
                        <StationBadge state={st.state} />
                      </span>
                      {st.sublabel && (
                        <span className="mt-0.5 block truncate text-[11px] text-gray-400 dark:text-gray-500">
                          {st.sublabel}
                        </span>
                      )}
                    </span>
                  )}
                </span>
              </button>
            )
          })}
        </div>
      </nav>

      {/* Rodapé */}
      <div className="mt-auto shrink-0 border-t border-gray-200 px-[18px] py-3.5 dark:border-gray-800">
        <Button
          variant="secondary"
          className={cx(
            "h-[34px] w-full justify-center",
            dossierActive && "border-blue-500 text-blue-600 dark:text-blue-400",
          )}
          onClick={onOpenDossier}
          disabled={!onOpenDossier}
        >
          <RiArticleLine className="mr-1.5 size-4" aria-hidden />
          {dossierLabel}
        </Button>
        {trailLabel && (
          <p className="mt-2.5 flex items-center gap-1.5 text-[11px] leading-normal text-gray-400 dark:text-gray-500">
            <RiHistoryLine className="size-[13px] shrink-0" aria-hidden />
            {trailLabel}
          </p>
        )}
      </div>
    </aside>
  )
}
