// src/design-system/components/ContextPanel/index.tsx
//
// Painel de contexto da Bancada Viva (handoff workflow JUCESP, 2026-06-18).
// A barra direita deixou de ser uma "Agentes ao vivo" ociosa e virou um painel
// de abas, sempre útil — o conteúdo cresce com o processo:
//
//   1. Atividade   — a caixa de vidro ao vivo (<AgentesAoVivoBody>): passos do
//                    agente + stream; dot pulsante quando trabalha, empty quando
//                    ocioso.
//   2. Apontamentos — radar de risco agregado de TODAS as estações, ordenado por
//                     severidade. Fonte real: red_flags dos agentes + flags dos
//                     deterministic_check.
//   3. Documentos  — cofre de evidências: ficha, PDF, extração, dossiê. Fonte
//                    real: credit_dossier_document + outputs.
//   4. Auditoria   — trilha de eventos (quem fez o quê, quando). Fonte real:
//                    decision_log + node runs.
//
// Presentational: a página deriva os dados de cada aba e alimenta por props.

"use client"

import * as React from "react"
import {
  RiAlertFill,
  RiArticleLine,
  RiBankLine,
  RiDownload2Line,
  RiErrorWarningFill,
  RiErrorWarningLine,
  RiExternalLinkLine,
  RiEyeLine,
  RiFilePdf2Line,
  RiFolder3Line,
  RiHistoryLine,
  RiInformationFill,
  RiPulseLine,
  RiTableLine,
  type RemixiconComponentType,
} from "@remixicon/react"

import {
  AgentesAoVivoBody,
  type GlassAlsoRunning,
  type GlassStep,
} from "@/design-system/components/AgentesAoVivoPanel"
import { DevZoneLabel } from "@/design-system/components/DevZoneLabel"
import { cx } from "@/lib/utils"

// ─── Tipos de dado das abas ──────────────────────────────────────────────────

export type ContextApontamentoSev = "critico" | "atencao" | "info"

export type ContextApontamento = {
  id: string
  titulo: string
  detail?: string
  /** Origem do apontamento (ex.: "check_socios", "Conferência", "Contrato social"). */
  station?: string
  sev: ContextApontamentoSev
  onEvidence?: () => void
}

export type ContextDocTone = "fonte" | "documento" | "dados" | "saida"

export type ContextDoc = {
  id: string
  name: string
  /** Categoria curta ("Consulta" / "Documento" / "Dados" / "Saída"). */
  kind: string
  meta?: string
  tone: ContextDocTone
  action?: "view" | "external" | "download"
  onOpen?: () => void
}

export type ContextAuditActor = "voce" | "agente" | "sistema"

export type ContextAuditEvent = {
  id: string
  titulo: string
  actor: string
  when: string
  actorKind: ContextAuditActor
}

export type ContextTabKey = "atividade" | "apontamentos" | "documentos" | "auditoria"

export type ContextPanelProps = {
  // Aba Atividade (caixa de vidro)
  activeStationLabel: string
  activeStationStatus?: string
  confidence?: "alta" | "media" | "baixa" | null
  steps: GlassStep[]
  alsoRunning?: GlassAlsoRunning[]
  /** Há agente trabalhando agora? → dot pulsante na aba Atividade. */
  agentBusy?: boolean
  // Demais abas
  apontamentos: ContextApontamento[]
  documentos: ContextDoc[]
  auditoria: ContextAuditEvent[]
  /** Rótulo de andaime (toggle "Zonas") — nomeia esta área na tela. */
  devLabel?: string
  className?: string
}

const EYEBROW =
  "text-[13px] font-semibold text-gray-900 dark:text-gray-50"
const SUB = "mt-0.5 text-[11px] leading-snug text-gray-400 dark:text-gray-500"

// ─── Tokens por severidade (apontamentos) ────────────────────────────────────

const SEV_TOKEN: Record<
  ContextApontamentoSev,
  { color: string; icon: RemixiconComponentType; rank: number }
> = {
  critico: { color: "#DC2626", icon: RiErrorWarningFill, rank: 0 },
  atencao: { color: "#D97706", icon: RiAlertFill, rank: 1 },
  info: { color: "#3B82F6", icon: RiInformationFill, rank: 2 },
}

// ─── Tokens por tom de documento (cofre) ─────────────────────────────────────

const DOC_TONE: Record<
  ContextDocTone,
  { color: string; bg: string; icon: RemixiconComponentType }
> = {
  fonte: { color: "#0891B2", bg: "rgba(8,145,178,0.10)", icon: RiBankLine },
  documento: { color: "#DC2626", bg: "rgba(220,38,38,0.10)", icon: RiFilePdf2Line },
  dados: { color: "#6366F1", bg: "rgba(99,102,241,0.10)", icon: RiTableLine },
  saida: { color: "#374151", bg: "rgba(55,65,81,0.10)", icon: RiArticleLine },
}

const DOC_ACTION_ICON: Record<NonNullable<ContextDoc["action"]>, RemixiconComponentType> = {
  view: RiEyeLine,
  external: RiExternalLinkLine,
  download: RiDownload2Line,
}

const AUDIT_DOT: Record<ContextAuditActor, string> = {
  voce: "#1F2937",
  agente: "#6366F1",
  sistema: "#0891B2",
}

// ════════════════════════════════════════════════════════════════════════════
// Abas
// ════════════════════════════════════════════════════════════════════════════

function ApontamentosTab({
  items,
}: {
  items: ContextApontamento[]
}) {
  const sorted = [...items].sort((a, b) => SEV_TOKEN[a.sev].rank - SEV_TOKEN[b.sev].rank)
  return (
    <div className="flex-1 overflow-y-auto px-4 py-4">
      <p className={EYEBROW}>Radar de risco</p>
      <p className={SUB}>apontamentos de todas as estações</p>

      {sorted.length === 0 ? (
        <p className="mt-6 text-center text-[12px] text-gray-400 dark:text-gray-500">
          Nenhum apontamento ainda. Achados dos agentes e dos checks aparecem aqui.
        </p>
      ) : (
        <div className="mt-3 space-y-2.5">
          {sorted.map((a) => {
            const t = SEV_TOKEN[a.sev]
            const Icon = t.icon
            return (
              <div
                key={a.id}
                className="rounded-md bg-gray-50/70 py-2.5 pl-3 pr-3 dark:bg-gray-900/40"
                style={{ borderLeft: `3px solid ${t.color}` }}
              >
                <div className="flex items-start gap-2">
                  <Icon
                    className="mt-px size-4 shrink-0"
                    style={{ color: t.color }}
                    aria-hidden
                  />
                  <div className="min-w-0 flex-1">
                    <p className="text-[13px] font-semibold text-gray-900 dark:text-gray-50">
                      {a.titulo}
                    </p>
                    {a.detail && (
                      <p className="mt-0.5 text-[12px] leading-relaxed text-gray-600 dark:text-gray-400">
                        {a.detail}
                      </p>
                    )}
                    <div className="mt-1.5 flex items-center justify-between gap-2">
                      {a.station && (
                        <span className="truncate font-mono text-[10.5px] text-gray-400 dark:text-gray-500">
                          {a.station}
                        </span>
                      )}
                      {a.onEvidence && (
                        <button
                          type="button"
                          onClick={a.onEvidence}
                          className="shrink-0 text-[11px] font-medium text-blue-600 hover:underline dark:text-blue-400"
                        >
                          ver evidência →
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

function DocumentosTab({ items }: { items: ContextDoc[] }) {
  return (
    <div className="flex-1 overflow-y-auto px-4 py-4">
      <p className={EYEBROW}>Cofre de evidências</p>
      <p className={SUB}>artefatos e fontes do dossiê</p>

      {items.length === 0 ? (
        <p className="mt-6 text-center text-[12px] text-gray-400 dark:text-gray-500">
          Nenhum documento ainda. Fichas, PDFs e extrações aparecem aqui.
        </p>
      ) : (
        <div className="mt-3 space-y-2">
          {items.map((d) => {
            const tone = DOC_TONE[d.tone]
            const Icon = tone.icon
            const ActionIcon = d.action ? DOC_ACTION_ICON[d.action] : null
            return (
              <button
                key={d.id}
                type="button"
                onClick={d.onOpen}
                disabled={!d.onOpen}
                className={cx(
                  "flex w-full items-center gap-3 rounded-md border border-gray-200 bg-white px-3 py-2.5 text-left dark:border-gray-800 dark:bg-gray-950",
                  d.onOpen
                    ? "transition-colors duration-100 hover:border-gray-300 dark:hover:border-gray-700"
                    : "cursor-default",
                )}
              >
                <span
                  className="flex size-8 shrink-0 items-center justify-center rounded"
                  style={{ background: tone.bg }}
                >
                  <Icon className="size-4" style={{ color: tone.color }} aria-hidden />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[12.5px] font-semibold text-gray-900 dark:text-gray-50">
                    {d.name}
                  </span>
                  <span className="block truncate text-[11px] text-gray-400 dark:text-gray-500">
                    {d.kind}
                    {d.meta ? ` · ${d.meta}` : ""}
                  </span>
                </span>
                {ActionIcon && (
                  <ActionIcon
                    className="size-4 shrink-0 text-gray-400 dark:text-gray-500"
                    aria-hidden
                  />
                )}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

function AuditoriaTab({ events }: { events: ContextAuditEvent[] }) {
  return (
    <div className="flex-1 overflow-y-auto px-4 py-4">
      <p className={EYEBROW}>Trilha de auditoria</p>
      <p className={SUB}>
        {events.length} evento{events.length === 1 ? "" : "s"} · quem fez o quê
      </p>

      {events.length === 0 ? (
        <p className="mt-6 text-center text-[12px] text-gray-400 dark:text-gray-500">
          Nenhum evento ainda.
        </p>
      ) : (
        <ol className="mt-3 space-y-3">
          {events.map((e) => (
            <li key={e.id} className="flex items-start gap-2.5">
              <span
                className="mt-1 flex size-3.5 shrink-0 items-center justify-center rounded-full"
                style={{ background: AUDIT_DOT[e.actorKind] }}
                aria-hidden
              >
                <span className="size-1.5 rounded-full bg-white" />
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-[12.5px] font-medium text-gray-900 dark:text-gray-100">
                  {e.titulo}
                </p>
                <p className="mt-0.5 text-[11px] text-gray-400 dark:text-gray-500">
                  {e.actor} · {e.when}
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// ContextPanel
// ════════════════════════════════════════════════════════════════════════════

type TabMeta = {
  key: ContextTabKey
  label: string
  icon: RemixiconComponentType
  /** Número (badge âmbar) ou "pulse" (dot indigo pulsante) ou 0 (sem badge). */
  badge: number | "pulse"
}

export function ContextPanel({
  activeStationLabel,
  activeStationStatus,
  confidence,
  steps,
  alsoRunning = [],
  agentBusy = false,
  apontamentos,
  documentos,
  auditoria,
  devLabel,
  className,
}: ContextPanelProps) {
  const [tab, setTab] = React.useState<ContextTabKey>("atividade")

  const tabs: TabMeta[] = [
    { key: "atividade", label: "Atividade", icon: RiPulseLine, badge: agentBusy ? "pulse" : 0 },
    {
      key: "apontamentos",
      label: "Apontam.",
      icon: RiErrorWarningLine,
      badge: apontamentos.length,
    },
    { key: "documentos", label: "Docs", icon: RiFolder3Line, badge: documentos.length },
    { key: "auditoria", label: "Auditoria", icon: RiHistoryLine, badge: 0 },
  ]

  return (
    <aside
      aria-label="Painel de contexto"
      className={cx(
        "relative flex h-full w-[308px] shrink-0 flex-col border-l border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
        className,
      )}
    >
      {devLabel && <DevZoneLabel corner="bl">{devLabel}</DevZoneLabel>}
      {/* Barra de abas */}
      <div
        role="tablist"
        className="flex shrink-0 border-b border-gray-200 dark:border-gray-800"
      >
        {tabs.map((t) => {
          const active = tab === t.key
          const Icon = t.icon
          const showBadge = t.badge === "pulse" || (typeof t.badge === "number" && t.badge > 0)
          return (
            <button
              key={t.key}
              type="button"
              role="tab"
              aria-selected={active}
              onClick={() => setTab(t.key)}
              className={cx(
                "relative flex flex-1 flex-col items-center gap-1 px-1 pb-2 pt-2.5 text-[10.5px] font-medium transition-colors duration-100",
                active
                  ? "text-blue-600 dark:text-blue-400"
                  : "text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300",
              )}
            >
              <span className="relative">
                <Icon className="size-[18px]" aria-hidden />
                {showBadge &&
                  (t.badge === "pulse" ? (
                    <span
                      className="absolute -right-1.5 -top-1 size-[7px] rounded-full bg-indigo-500 motion-safe:animate-pulse"
                      aria-hidden
                    />
                  ) : (
                    <span
                      className="absolute -right-2.5 -top-1.5 inline-flex h-[14px] min-w-[14px] items-center justify-center rounded-full bg-amber-500 px-[3px] text-[9px] font-bold leading-none text-white"
                      aria-hidden
                    >
                      {t.badge}
                    </span>
                  ))}
              </span>
              <span className={cx(active && "font-semibold")}>{t.label}</span>
              {active && (
                <span
                  className="absolute inset-x-2 bottom-0 h-0.5 rounded-t-sm bg-blue-500"
                  aria-hidden
                />
              )}
            </button>
          )
        })}
      </div>

      {/* Conteúdo da aba ativa */}
      {tab === "atividade" && (
        <AgentesAoVivoBody
          activeStationLabel={activeStationLabel}
          activeStationStatus={activeStationStatus}
          confidence={confidence}
          steps={steps}
          alsoRunning={alsoRunning}
        />
      )}
      {tab === "apontamentos" && <ApontamentosTab items={apontamentos} />}
      {tab === "documentos" && <DocumentosTab items={documentos} />}
      {tab === "auditoria" && <AuditoriaTab events={auditoria} />}
    </aside>
  )
}
