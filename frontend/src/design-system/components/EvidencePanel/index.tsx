// src/design-system/components/EvidencePanel/index.tsx
//
// Right rail persistente do Wizard V2. ~320px, sticky a partir do top do
// workspace. Compoe 4 secoes colapsaveis:
//
//   📎 Documentos       — FileList + FileUploadZone compact
//   📝 Notas            — StepNoteList + StepNoteEditor mode="create"
//   🔗 Links            — LinkList + LinkInput
//   ⚠️ Inconsistencias  — InconsistencyList (hidden quando vazia)
//
// Filtro global: "Esta etapa | Todo o dossie". Caller passa os items ja
// filtrados/ordenados — o EvidencePanel so escolhe qual sub-componente
// renderizar.
//
// Em md (telas medias) o panel some — o caller normalmente abre como Sheet
// via atalho Cmd+E (nao escopo deste componente).

"use client"

import * as React from "react"
import {
  RiArrowDownSLine,
  RiAttachment2,
  RiErrorWarningLine,
  RiLink,
  RiStickyNoteLine,
  type RemixiconComponentType,
} from "@remixicon/react"

import { Card } from "@/components/tremor/Card"
import { cardTokens } from "@/design-system/tokens/card"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

import { FileList, type FileListItem } from "../FileList"
import { FileUploadZone } from "../FileUploadZone"
import {
  InconsistencyList,
  type InconsistencyItem,
} from "../InconsistencyList"
import { LinkInput, LinkList, type LinkListItem } from "../LinkInput"
import {
  StepNoteEditor,
  StepNoteList,
  type StepNoteListItem,
} from "../StepNoteEditor"

export type EvidenceFilterScope = "step" | "dossier"

export type EvidencePanelProps = {
  /** Filtro de escopo (controlled). */
  scope: EvidenceFilterScope
  onScopeChange: (s: EvidenceFilterScope) => void

  /** Step atualmente em foco. Quando scope === "step", o caller filtra os
   *  attachments/notes/links para retornar so os deste step. Quando
   *  scope === "dossier", todos. */
  currentNodeId: string | null

  // ── Documentos ────────────────────────────────────────────────────────────
  attachments: FileListItem[]
  onUploadAttachment: (file: File) => Promise<void>
  onDeleteAttachment?: (id: string) => void
  /** Quando o requester nao e o uploader nem admin, filtra delete. */
  canDeleteAttachment?: (item: FileListItem) => boolean

  // ── Notas ─────────────────────────────────────────────────────────────────
  notes: StepNoteListItem[]
  /** Cria nota — caller vincula ao currentNodeId quando scope === "step". */
  onCreateNote: (body_md: string, pinned: boolean) => Promise<void>
  onEditNote?: (note: StepNoteListItem) => void
  onDeleteNote?: (id: string) => void
  currentUserId?: string | null

  // ── Links ─────────────────────────────────────────────────────────────────
  links: LinkListItem[]
  onCreateLink: (vals: {
    url: string
    title?: string
    description?: string
  }) => Promise<void>
  onDeleteLink?: (id: string) => void
  canDeleteLink?: (item: LinkListItem) => boolean

  // ── Inconsistencias ───────────────────────────────────────────────────────
  inconsistencies?: InconsistencyItem[]
  onInconsistencyStepClick?: (nodeId: string) => void

  className?: string
}

export function EvidencePanel({
  scope,
  onScopeChange,
  currentNodeId,
  attachments,
  onUploadAttachment,
  onDeleteAttachment,
  canDeleteAttachment,
  notes,
  onCreateNote,
  onEditNote,
  onDeleteNote,
  currentUserId,
  links,
  onCreateLink,
  onDeleteLink,
  canDeleteLink,
  inconsistencies,
  onInconsistencyStepClick,
  className,
}: EvidencePanelProps) {
  const inconsistenciesVisible = (inconsistencies?.length ?? 0) > 0
  const stepDisabled = scope === "step" && !currentNodeId

  return (
    <Card
      className={cx(
        "hidden w-80 shrink-0 flex-col lg:flex",
        className,
      )}
    >
      {/* Header com toggle de escopo */}
      <div className={cardTokens.header}>
        <p className={cardTokens.headerTitle}>Evidencias</p>
        <div className="mt-2 inline-flex rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
          {/* MOTIVO: <button> cru — toggle compacto inline. Button do Tremor
              traria padding default que quebra o visual de segmented. */}
          {(["step", "dossier"] as const).map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => onScopeChange(s)}
              disabled={s === "step" && !currentNodeId}
              className={cx(
                "px-2.5 py-1 text-xs",
                scope === s
                  ? "bg-gray-100 font-medium text-gray-900 dark:bg-gray-800 dark:text-gray-50"
                  : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300",
                s === "step" && !currentNodeId && "opacity-50",
              )}
              aria-pressed={scope === s}
            >
              {s === "step" ? "Esta etapa" : "Todo o dossie"}
            </button>
          ))}
        </div>
        {stepDisabled && (
          <p className={cx(tableTokens.cellSecondary, "mt-1.5")}>
            Selecione uma etapa para filtrar.
          </p>
        )}
      </div>

      <div className="flex-1 overflow-y-auto">
        <Section
          icon={RiAttachment2}
          title="Documentos"
          count={attachments.length}
          defaultOpen
        >
          <FileList
            files={attachments}
            onDelete={onDeleteAttachment}
            canDelete={canDeleteAttachment}
            emptyMessage="Nenhum documento ainda"
          />
          <div className="mt-3">
            <FileUploadZone
              compact
              onUpload={onUploadAttachment}
              label="Anexar documento"
            />
          </div>
        </Section>

        <Section
          icon={RiStickyNoteLine}
          title="Notas"
          count={notes.length}
          defaultOpen
        >
          <StepNoteList
            notes={notes}
            currentUserId={currentUserId}
            onEdit={onEditNote}
            onDelete={onDeleteNote}
            emptyMessage="Nenhuma nota ainda"
          />
          {scope === "step" && currentNodeId && (
            <div className="mt-3 border-t border-gray-100 pt-3 dark:border-gray-900">
              <StepNoteEditor
                mode="create"
                onSave={(body, pinned) => onCreateNote(body, pinned)}
                placeholder="Adicione uma nota desta etapa..."
              />
            </div>
          )}
        </Section>

        <Section
          icon={RiLink}
          title="Links"
          count={links.length}
          defaultOpen={false}
        >
          <LinkList
            links={links}
            onDelete={onDeleteLink}
            canDelete={canDeleteLink}
            emptyMessage="Nenhum link ainda"
          />
          <div className="mt-3 border-t border-gray-100 pt-3 dark:border-gray-900">
            <LinkInput onSubmit={onCreateLink} />
          </div>
        </Section>

        {inconsistenciesVisible && (
          <Section
            icon={RiErrorWarningLine}
            title="Inconsistencias"
            count={inconsistencies?.length ?? 0}
            defaultOpen
            iconClassName="text-red-500"
          >
            <InconsistencyList
              items={inconsistencies ?? []}
              onStepClick={onInconsistencyStepClick}
            />
          </Section>
        )}
      </div>
    </Card>
  )
}

// ─── Section (collapsable) ─────────────────────────────────────────────────

function Section({
  icon: Icon,
  title,
  count,
  defaultOpen = false,
  iconClassName,
  children,
}: {
  icon: RemixiconComponentType
  title: string
  count: number
  defaultOpen?: boolean
  iconClassName?: string
  children: React.ReactNode
}) {
  const [open, setOpen] = React.useState(defaultOpen)
  return (
    <section className="border-b border-gray-100 dark:border-gray-900">
      {/* MOTIVO: <button> cru — header de section e clicavel inteiro,
          Button do Tremor com layout full-width nao cabe. */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={cx(
          "flex w-full items-center justify-between gap-2 px-4 py-2.5",
          "text-sm font-medium text-gray-700 dark:text-gray-300",
          "hover:bg-gray-50 dark:hover:bg-gray-900",
        )}
        aria-expanded={open}
      >
        <span className="flex items-center gap-2">
          <Icon
            className={cx(
              "size-4",
              iconClassName ?? "text-gray-400 dark:text-gray-500",
            )}
            aria-hidden
          />
          {title}
          <span className={cx(tableTokens.cellSecondary, "tabular-nums")}>
            ({count})
          </span>
        </span>
        <RiArrowDownSLine
          className={cx(
            "size-4 text-gray-400 transition-transform dark:text-gray-500",
            open && "rotate-180",
          )}
          aria-hidden
        />
      </button>
      {open && <div className="px-4 pb-4">{children}</div>}
    </section>
  )
}
