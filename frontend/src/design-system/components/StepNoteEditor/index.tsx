// src/design-system/components/StepNoteEditor/index.tsx
//
// Editor + lista de notas markdown que o analista escreve por step do dossie.
//
// StepNoteEditor:
//   - 3 modos: "create" (campo vazio), "edit" (pre-populado), "read" (so markdown)
//   - Toggle write/preview no canto direito quando em create/edit
//   - Markdown renderizado via react-markdown + remark-gfm (mesmo da AIPanel)
//   - Body limit 1..10000 chars
//
// StepNoteList:
//   - Pinned notes flutuam pro topo
//   - Cada item: avatar de autor + relative timestamp + ações (edit/delete)
//   - Body markdown renderizado
//
// Ambos sao uncontrolled em relacao ao backend — caller passa onSave/onDelete
// callbacks (TanStack Query mutations) e o componente gerencia o input state.

"use client"

import * as React from "react"
import {
  RiDeleteBinLine,
  RiEdit2Line,
  RiEyeLine,
  RiPencilLine,
  RiPushpin2Fill,
  RiPushpin2Line,
} from "@remixicon/react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { Button } from "@/components/tremor/Button"
import { Textarea } from "@/components/tremor/Textarea"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

// ─── StepNoteEditor ─────────────────────────────────────────────────────────

export type StepNoteEditorMode = "create" | "edit" | "read"

export type StepNoteEditorProps = {
  mode: StepNoteEditorMode
  /** Conteudo inicial. Em mode="read", e o conteudo a renderizar.
   *  Em mode="edit", e o seed do textarea. */
  initialValue?: string
  initialPinned?: boolean
  /** Disparado em "create" e "edit" ao clicar Salvar. */
  onSave?: (body: string, pinned: boolean) => Promise<void> | void
  /** Disparado em "edit" ao cancelar (volta ao texto original ou descarta). */
  onCancel?: () => void
  /** Placeholder textarea (default: "Adicione uma nota..."). */
  placeholder?: string
  /** Quando true, chama onSave com debounce de 500ms a cada keystroke (auto-save). */
  autoSave?: boolean
  className?: string
}

export function StepNoteEditor({
  mode,
  initialValue = "",
  initialPinned = false,
  onSave,
  onCancel,
  placeholder = "Adicione uma nota...",
  autoSave = false,
  className,
}: StepNoteEditorProps) {
  const [body, setBody] = React.useState(initialValue)
  const [pinned, setPinned] = React.useState(initialPinned)
  const [view, setView] = React.useState<"write" | "preview">("write")
  const [submitting, setSubmitting] = React.useState(false)

  if (mode === "read") {
    return (
      <div className={cx(MARKDOWN_CLASS, className)}>
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{initialValue}</ReactMarkdown>
      </div>
    )
  }

  const valid = body.trim().length > 0 && body.length <= 10000
  const charCount = body.length

  const handleSave = async () => {
    if (!onSave || !valid) return
    setSubmitting(true)
    try {
      await onSave(body.trim(), pinned)
      if (mode === "create") {
        setBody("")
        setPinned(false)
        setView("write")
      }
    } finally {
      setSubmitting(false)
    }
  }

  // Auto-save (opcional). Debounce 500ms.
  React.useEffect(() => {
    if (!autoSave || !onSave || mode === "create") return
    if (body.trim() === initialValue.trim()) return
    const id = setTimeout(() => {
      if (body.trim().length > 0 && body.length <= 10000) {
        void onSave(body.trim(), pinned)
      }
    }, 500)
    return () => clearTimeout(id)
  }, [body, pinned, autoSave, onSave, mode, initialValue])

  return (
    <div className={cx("space-y-2", className)}>
      <div className="flex items-center justify-between gap-2">
        <SegmentedToggle view={view} onChange={setView} />
        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            className="size-7 p-0"
            onClick={() => setPinned((p) => !p)}
            aria-label={pinned ? "Desfixar nota" : "Fixar nota"}
            title={pinned ? "Nota fixada" : "Fixar"}
          >
            {pinned ? (
              <RiPushpin2Fill
                className="size-3.5 text-amber-500"
                aria-hidden
              />
            ) : (
              <RiPushpin2Line
                className="size-3.5 text-gray-400 dark:text-gray-500"
                aria-hidden
              />
            )}
          </Button>
        </div>
      </div>

      {view === "write" ? (
        <Textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          placeholder={placeholder}
          rows={4}
          maxLength={10000}
          className="resize-y"
        />
      ) : (
        <div
          className={cx(
            "min-h-[80px] rounded border bg-white p-3",
            "border-gray-200 dark:border-gray-800 dark:bg-gray-950",
            MARKDOWN_CLASS,
          )}
        >
          {body.trim() ? (
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{body}</ReactMarkdown>
          ) : (
            <p className={tableTokens.cellSecondary}>(sem conteudo)</p>
          )}
        </div>
      )}

      <div className="flex items-center justify-between gap-2">
        <p className={tableTokens.cellSecondary}>
          Markdown · {charCount}/10000
        </p>
        <div className="flex items-center gap-2">
          {mode === "edit" && onCancel && (
            <Button variant="ghost" onClick={onCancel} disabled={submitting}>
              Cancelar
            </Button>
          )}
          {!autoSave && (
            <Button
              onClick={handleSave}
              disabled={!valid || submitting}
              isLoading={submitting}
            >
              {mode === "create" ? "Adicionar nota" : "Salvar"}
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── SegmentedToggle (interno, write/preview) ──────────────────────────────

function SegmentedToggle({
  view,
  onChange,
}: {
  view: "write" | "preview"
  onChange: (v: "write" | "preview") => void
}) {
  return (
    <div className="inline-flex items-center rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
      {(["write", "preview"] as const).map((v) => (
        // MOTIVO: <button> cru — toggle compacto sem texto longo. Button
        // do Tremor traz padding default que quebra o visual de tab pequena.
        <button
          key={v}
          type="button"
          onClick={() => onChange(v)}
          className={cx(
            "inline-flex h-7 items-center gap-1 px-2 text-xs",
            view === v
              ? "bg-gray-100 text-gray-900 dark:bg-gray-800 dark:text-gray-50"
              : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-300",
          )}
          aria-pressed={view === v}
        >
          {v === "write" ? (
            <RiPencilLine className="size-3" aria-hidden />
          ) : (
            <RiEyeLine className="size-3" aria-hidden />
          )}
          {v === "write" ? "Editar" : "Preview"}
        </button>
      ))}
    </div>
  )
}

// ─── StepNoteList ──────────────────────────────────────────────────────────

export type StepNoteListItem = {
  id: string
  body_md: string
  pinned: boolean
  created_at: string
  updated_at: string
  author_id: string | null
  /** Label legivel do autor (vem do caller — backend nao expoe nome
   *  por user_id automaticamente; geralmente "Voce" ou nome do team). */
  author_label?: string | null
}

export type StepNoteListProps = {
  notes: StepNoteListItem[]
  /** ID do usuario logado — gating de edit/delete. */
  currentUserId?: string | null
  onEdit?: (note: StepNoteListItem) => void
  onDelete?: (id: string) => void
  /** Mensagem custom no estado vazio. */
  emptyMessage?: string
  className?: string
}

export function StepNoteList({
  notes,
  currentUserId,
  onEdit,
  onDelete,
  emptyMessage = "Nenhuma nota nesta etapa",
  className,
}: StepNoteListProps) {
  if (notes.length === 0) {
    return (
      <p className={cx(tableTokens.cellSecondary, "py-3 text-center", className)}>
        {emptyMessage}
      </p>
    )
  }

  // Pinned primeiro, depois cronologico desc.
  const sorted = [...notes].sort((a, b) => {
    if (a.pinned !== b.pinned) return a.pinned ? -1 : 1
    return Date.parse(b.created_at) - Date.parse(a.created_at)
  })

  return (
    <ul className={cx("space-y-2", className)}>
      {sorted.map((note) => {
        const isAuthor = note.author_id === currentUserId
        return (
          <li
            key={note.id}
            className="rounded border border-gray-100 bg-white p-3 dark:border-gray-900 dark:bg-gray-950"
          >
            <header className="mb-2 flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                {note.pinned && (
                  <RiPushpin2Fill
                    className="size-3.5 text-amber-500"
                    aria-hidden
                  />
                )}
                <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
                  {note.author_label ?? "—"}
                </span>
                <span className={tableTokens.cellSecondary}>
                  · {formatRelativeShort(note.updated_at ?? note.created_at)}
                </span>
              </div>
              {isAuthor && (
                <div className="flex items-center gap-1">
                  {onEdit && (
                    <Button
                      variant="ghost"
                      className="size-7 p-0"
                      onClick={() => onEdit(note)}
                      aria-label="Editar nota"
                    >
                      <RiEdit2Line className="size-3.5" aria-hidden />
                    </Button>
                  )}
                  {onDelete && (
                    <Button
                      variant="ghost"
                      className="size-7 p-0"
                      onClick={() => onDelete(note.id)}
                      aria-label="Remover nota"
                    >
                      <RiDeleteBinLine className="size-3.5" aria-hidden />
                    </Button>
                  )}
                </div>
              )}
            </header>
            <div className={MARKDOWN_CLASS}>
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {note.body_md}
              </ReactMarkdown>
            </div>
          </li>
        )
      })}
    </ul>
  )
}

// ─── Markdown styling (compartilhado com AIPanel idealmente, mas inline aqui) ─

/** Tailwind reset minimo pra elementos markdown (p, strong, em, ul, ol, code). */
const MARKDOWN_CLASS = cx(
  "prose-sm max-w-none text-sm text-gray-800 dark:text-gray-200",
  "[&_p]:m-0 [&_p+p]:mt-2",
  "[&_ul]:my-2 [&_ul]:pl-5 [&_ul]:list-disc",
  "[&_ol]:my-2 [&_ol]:pl-5 [&_ol]:list-decimal",
  "[&_li]:my-0.5",
  "[&_strong]:font-semibold [&_strong]:text-gray-900 dark:[&_strong]:text-gray-50",
  "[&_em]:italic",
  "[&_code]:rounded [&_code]:bg-gray-100 [&_code]:px-1 [&_code]:py-0.5",
  "[&_code]:font-mono [&_code]:text-xs",
  "dark:[&_code]:bg-gray-800",
  "[&_a]:text-blue-600 [&_a]:underline hover:[&_a]:text-blue-700",
  "dark:[&_a]:text-blue-400 dark:hover:[&_a]:text-blue-300",
)

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatRelativeShort(iso: string): string {
  const ts = Date.parse(iso)
  if (Number.isNaN(ts)) return "—"
  const diffSec = Math.max(0, Math.floor((Date.now() - ts) / 1000))
  if (diffSec < 60) return "agora"
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `ha ${diffMin}min`
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return `ha ${diffH}h`
  const diffD = Math.floor(diffH / 24)
  if (diffD < 30) return `ha ${diffD}d`
  return new Date(ts).toLocaleDateString("pt-BR")
}
