// src/design-system/patterns/WizardMultiStep.tsx
//
// PATTERN — Wizard Multi-Step (Hibrido enterprise)
// Copy, paste, adapt. Not a black-box component.
//
// Layout (3 colunas + sticky top):
//
//   ┌──────────────────────────────────────────────────────────────────────┐
//   │ <WizardTopRail> sticky                                               │
//   │ back · titulo · subtitle | linear progress | ações + SaveIndicator   │
//   ├──────────────┬───────────────────────────────────┬───────────────────┤
//   │ Side micro   │  Workspace central                │  Evidence panel   │
//   │ (colaps.)    │  (waiting/running/completed/      │  (right rail)     │
//   │              │   failed/blocked views)           │                   │
//   └──────────────┴───────────────────────────────────┴───────────────────┘
//
// HOW TO ADAPT:
//   1. Copie este arquivo para `src/app/(app)/<dominio>/<rota>/page.tsx` —
//      ou importe direto se a estrutura do dominio cabe sem ajustes.
//   2. Substitua os tipos do mock por tipos reais do dominio (NodeRunSummary,
//      WorkflowRunSummary, etc).
//   3. Conecte os hooks de domínio (useDossierState, useStepDraft,
//      useDossierEvidence) no caller — este pattern recebe DADOS, nao queries.
//   4. URL state: `?step=<nodeId>&panel=<docs|notes|links|inconsistencies>`.
//      currentNodeId vem da URL (useSearchParams), onStepSelect atualiza URL.
//   5. AgentLiveStatus: passe via `renderRunning` callback do
//      WizardWorkspace — ele recebe o step running e devolve o JSX.
//   6. AgentOutputRenderer: idem via `renderCompleted` — escolhe sub-view por
//      agentName extraido do step.input ou step.id.
//   7. Form do waiting_input: passe via `renderWaitingInput` — o form e
//      especifico do dominio (DynamicForm + react-hook-form).
//
// Use for: workflow execution multi-step com agentes IA + humano-in-the-loop
// + persistencia rica (anexos/notas/links). Ex.: dossie de credito, analise
// de risco, onboarding multi-etapa.
//
// NAO use para: forms simples sem etapas (use create-form-page skill),
// dashboards (use DashboardBiPadrao/DashboardOperacional).

"use client"

import * as React from "react"

import {
  AgentLiveStatus,
  AgentOutputRenderer,
  EvidencePanel,
  WizardSideMicro,
  WizardTopRail,
  WizardWorkspace,
  type EvidenceFilterScope,
  type FileListItem,
  type InconsistencyItem,
  type LinkListItem,
  type SaveIndicatorState,
  type StepNoteListItem,
  type WizardSideMicroStep,
  type WizardStepLite,
  type WizardWorkspaceStep,
} from "@/design-system/components"

// ─── Types do pattern ──────────────────────────────────────────────────────

export type WizardMultiStepProps = {
  // Identidade do dossie/run
  dossierTitle: string
  dossierSubtitle?: string

  // Steps + foco
  /** Lista canonica de steps. Cada item alimenta side micro + top rail dots. */
  steps: WizardMultiStepStep[]
  /** Step focado — vem da URL (?step=<id>) ou inferido do estado. */
  currentNodeId: string | null
  onStepSelect: (nodeId: string) => void
  /** Click no dot do progress bar — opcional (default: igual onStepSelect). */
  onProgressDotClick?: (nodeId: string) => void

  // Meta + auto-save
  meta: {
    completedSteps: number
    totalSteps: number
    totalCostBrl?: number
    durationMinutes?: number | null
  }
  saveState: SaveIndicatorState
  lastSavedAt?: string | null
  saveErrorMessage?: string | null
  onSaveRetry?: () => void

  // Top rail extras
  onBack?: () => void
  topActions?: React.ReactNode

  // Render hooks pra workspace
  /** Form do waiting_input. Caller passa <DynamicForm /> tipicamente. */
  renderWaitingInput?: (step: WizardMultiStepStep) => React.ReactNode
  /** Live status de agente. Caller passa <AgentLiveStatus /> com tools_log. */
  renderRunning?: (step: WizardMultiStepStep) => React.ReactNode
  /** Output estruturado. Caller passa <AgentOutputRenderer /> com agentName. */
  renderCompleted?: (step: WizardMultiStepStep) => React.ReactNode
  onRetryStep?: (stepId: string) => void

  // Evidence panel
  evidence: {
    scope: EvidenceFilterScope
    onScopeChange: (s: EvidenceFilterScope) => void
    attachments: FileListItem[]
    onUploadAttachment: (file: File) => Promise<void>
    onDeleteAttachment?: (id: string) => void
    notes: StepNoteListItem[]
    onCreateNote: (body: string, pinned: boolean) => Promise<void>
    onEditNote?: (note: StepNoteListItem) => void
    onDeleteNote?: (id: string) => void
    links: LinkListItem[]
    onCreateLink: (vals: {
      url: string
      title?: string
      description?: string
    }) => Promise<void>
    onDeleteLink?: (id: string) => void
    inconsistencies?: InconsistencyItem[]
    currentUserId?: string | null
  }

  className?: string
}

/** Step canonico do pattern — combina shapes esperados por SideMicro/Workspace.
 *  Caller adapta NodeRunSummary -> WizardMultiStepStep no seletor da page. */
export type WizardMultiStepStep = WizardSideMicroStep & WizardWorkspaceStep

// ─── Pattern ────────────────────────────────────────────────────────────────

export function WizardMultiStep({
  dossierTitle,
  dossierSubtitle,
  steps,
  currentNodeId,
  onStepSelect,
  onProgressDotClick,
  meta,
  saveState,
  lastSavedAt,
  saveErrorMessage,
  onSaveRetry,
  onBack,
  topActions,
  renderWaitingInput,
  renderRunning,
  renderCompleted,
  onRetryStep,
  evidence,
  className,
}: WizardMultiStepProps) {
  const focusedStep = React.useMemo(
    () => steps.find((s) => s.id === currentNodeId) ?? null,
    [steps, currentNodeId],
  )

  // Steps lite pro top rail (so id + state).
  const stepsLite: WizardStepLite[] = React.useMemo(
    () => steps.map((s) => ({ id: s.id, state: s.state })),
    [steps],
  )

  return (
    <div className={className}>
      <WizardTopRail
        dossierTitle={dossierTitle}
        dossierSubtitle={dossierSubtitle}
        steps={stepsLite}
        currentNodeId={currentNodeId}
        meta={meta}
        saveState={saveState}
        lastSavedAt={lastSavedAt}
        saveErrorMessage={saveErrorMessage}
        onSaveRetry={onSaveRetry}
        actions={topActions}
        onBack={onBack}
        onStepClick={onProgressDotClick ?? onStepSelect}
      />

      {/* Linha 3-col: side micro | workspace | evidence panel.
          gap: 4 — equilibra densidade enterprise sem apertar. */}
      <div className="mt-4 flex gap-4">
        <WizardSideMicro
          steps={steps}
          currentNodeId={currentNodeId}
          onSelect={onStepSelect}
        />

        <div className="min-w-0 flex-1">
          <WizardWorkspace
            step={focusedStep}
            renderWaitingInput={renderWaitingInput}
            renderRunning={renderRunning}
            renderCompleted={renderCompleted}
            onRetryStep={onRetryStep}
          />
        </div>

        <EvidencePanel
          scope={evidence.scope}
          onScopeChange={evidence.onScopeChange}
          currentNodeId={currentNodeId}
          attachments={evidence.attachments}
          onUploadAttachment={evidence.onUploadAttachment}
          onDeleteAttachment={evidence.onDeleteAttachment}
          notes={evidence.notes}
          onCreateNote={evidence.onCreateNote}
          onEditNote={evidence.onEditNote}
          onDeleteNote={evidence.onDeleteNote}
          currentUserId={evidence.currentUserId}
          links={evidence.links}
          onCreateLink={evidence.onCreateLink}
          onDeleteLink={evidence.onDeleteLink}
          inconsistencies={evidence.inconsistencies}
          onInconsistencyStepClick={onStepSelect}
        />
      </div>
    </div>
  )
}

// ─── Re-exports pra facilitar import na page ───────────────────────────────
//
// O caller importa AgentLiveStatus + AgentOutputRenderer pra passar em
// renderRunning/renderCompleted. Re-expor aqui evita import direto do barrel
// dentro da page que copia este pattern.

export { AgentLiveStatus, AgentOutputRenderer }
