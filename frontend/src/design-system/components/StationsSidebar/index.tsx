// src/design-system/components/StationsSidebar/index.tsx
//
// Sidebar de etapas do modo foco (292px, handoff Conceito D).
// Gerada da mesma definição do fluxo: estação = node com gate humano ou
// que gera seção do dossiê. Mostra estados AO VIVO — o analista é puxado
// pelas pendências, não percorre 1→N.
//
// Anatomia: header (← fila, eyebrow, cedente, meta, progresso 4px) ·
// lista de estações (6 estados visuais) · rodapé ("Ver dossiê · X% montado"
// + linha da trilha).

"use client"

import * as React from "react"
import Link from "next/link"
import {
  RiArticleLine,
  RiCheckboxCircleFill,
  RiErrorWarningLine,
  RiFileUploadLine,
  RiHistoryLine,
  RiLockLine,
  RiSparkling2Line,
  RiTimeLine,
  RiUserFollowLine,
} from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { AgentPulseDot } from "@/design-system/components/AgentLiveChip"
import { provenanceTokens } from "@/design-system/tokens/provenance"
import { cx } from "@/lib/utils"

export type StationState =
  | "fechada"
  | "fechada_com_ressalva"
  | "sua_vez"
  | "homologar"
  | "rodando"
  | "aguardando_documento"
  | "em_espera"
  | "bloqueada"
  | "falhou"

export type StationItem = {
  id: string
  label: string
  sublabel?: string
  state: StationState
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

function StationIcon({ state }: { state: StationState }) {
  switch (state) {
    case "fechada":
      return <RiCheckboxCircleFill className="size-4 shrink-0" style={{ color: "#059669" }} aria-hidden />
    case "fechada_com_ressalva":
      return <RiCheckboxCircleFill className="size-4 shrink-0 text-amber-600" aria-hidden />
    case "sua_vez":
      return <RiUserFollowLine className="size-4 shrink-0 text-blue-600" aria-hidden />
    case "homologar":
      return (
        <RiSparkling2Line
          className="size-4 shrink-0"
          style={{ color: provenanceTokens.agente.color }}
          aria-hidden
        />
      )
    case "rodando":
      return (
        <span className="flex size-4 shrink-0 items-center justify-center">
          <AgentPulseDot size={8} />
        </span>
      )
    case "aguardando_documento":
      return <RiFileUploadLine className="size-4 shrink-0 text-gray-500 dark:text-gray-400" aria-hidden />
    case "em_espera":
      return <RiTimeLine className="size-4 shrink-0 text-amber-600" aria-hidden />
    case "falhou":
      return <RiErrorWarningLine className="size-4 shrink-0 text-amber-600" aria-hidden />
    case "bloqueada":
      return <RiLockLine className="size-4 shrink-0 text-gray-400 dark:text-gray-600" aria-hidden />
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
  return (
    <aside
      aria-label="Estações da análise"
      className={cx(
        "flex h-screen w-[292px] shrink-0 flex-col border-r border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-925",
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

      {/* Lista de estações */}
      <nav className="flex-1 overflow-y-auto px-2.5 py-3.5">
        <p className="px-2 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600">
          Estações
        </p>
        <div className="flex flex-col gap-[3px]">
          {stations.map((st) => {
            const isActive = !dossierActive && st.id === activeId
            const isBlocked = st.state === "bloqueada"
            return (
              <button
                key={st.id}
                type="button"
                onClick={() => !isBlocked && onSelect(st.id)}
                disabled={isBlocked}
                className={cx(
                  "relative flex items-start gap-2.5 rounded-md px-2 py-[9px] text-left transition-colors duration-100",
                  isActive
                    ? "border border-gray-200 bg-white shadow-xs dark:border-gray-800 dark:bg-gray-950"
                    : "border border-transparent",
                  !isActive && !isBlocked && "hover:bg-gray-100 dark:hover:bg-gray-900",
                  isBlocked && "cursor-default opacity-55",
                )}
              >
                {isActive && (
                  <span
                    className="absolute -left-2.5 top-1/2 h-5 w-0.5 -translate-y-1/2 rounded-full bg-blue-500"
                    aria-hidden
                  />
                )}
                <span className="mt-px">
                  <StationIcon state={st.state} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-center gap-2">
                    <span
                      className={cx(
                        "truncate text-[13px] text-gray-700 dark:text-gray-300",
                        isActive && "font-semibold text-gray-900 dark:text-gray-50",
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
