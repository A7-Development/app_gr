"use client"

/**
 * React Query hooks do modulo credito (Wizard V2).
 *
 * - useDossierState: query + polling 3s do estado completo do dossie/run.
 * - useStepDraft: auto-save debounced 500ms para form values de um node WAITING_INPUT.
 * - useDossierAttachments / useDossierNotes / useDossierLinks: CRUD com
 *   invalidacao cruzada — listagens filtraveis por node_id.
 */

import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  credito,
  type AttachmentRead,
  type DossierStateResponse,
  type LinkCreatePayload,
  type LinkRead,
  type NoteCreatePayload,
  type NoteRead,
  type NoteUpdatePayload,
} from "@/lib/credito-client"

// ─── Keys ────────────────────────────────────────────────────────────────

const KEYS = {
  state: (id: string) => ["credito", "dossie-state", id] as const,
  attachments: (id: string, nodeId?: string | null) =>
    ["credito", "attachments", id, nodeId ?? null] as const,
  notes: (id: string, nodeId?: string | null) =>
    ["credito", "notes", id, nodeId ?? null] as const,
  links: (id: string, nodeId?: string | null) =>
    ["credito", "links", id, nodeId ?? null] as const,
}

// ─── Dossier list mutations ──────────────────────────────────────────────

export function useDeleteDossier() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (dossierId: string) => credito.dossies.remove(dossierId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["credito", "dossies"] })
    },
  })
}

// ─── State (polling) ─────────────────────────────────────────────────────

/**
 * Query do estado do dossie + workflow_run + node_runs.
 *
 * Polling 3s enquanto run esta RUNNING ou PAUSED — para quando completa,
 * falha ou e cancelado.
 */
export function useDossierState(dossierId: string | null | undefined) {
  return useQuery<DossierStateResponse>({
    queryKey: KEYS.state(dossierId ?? ""),
    queryFn: () => credito.dossies.getState(dossierId as string),
    enabled: Boolean(dossierId),
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data?.run) return false
      const status = (data.run as { status?: string }).status
      if (status && ["completed", "failed", "cancelled"].includes(status)) {
        return false
      }
      return 3000
    },
  })
}

// ─── Step draft auto-save ────────────────────────────────────────────────

export type SaveState = "idle" | "saving" | "saved" | "unsaved" | "error"

/**
 * Auto-save debounced 500ms para form values de um node WAITING_INPUT.
 *
 * Chame `save(values)` em cada onBlur de campo do form; o hook rebufferiza
 * e PATCHa o backend uma unica vez por janela. `state` alimenta o
 * <SaveIndicator />.
 */
export function useStepDraft(
  dossierId: string | null | undefined,
  nodeId: string | null | undefined,
  debounceMs = 500,
) {
  const [state, setState] = React.useState<SaveState>("idle")
  const [lastSavedAt, setLastSavedAt] = React.useState<string | null>(null)
  const [errorMessage, setErrorMessage] = React.useState<string | null>(null)

  const pendingValues = React.useRef<Record<string, unknown> | null>(null)
  const timer = React.useRef<ReturnType<typeof setTimeout> | null>(null)

  const flush = React.useCallback(async () => {
    const values = pendingValues.current
    if (!values || !dossierId || !nodeId) return
    pendingValues.current = null
    setState("saving")
    setErrorMessage(null)
    try {
      const res = await credito.dossies.saveNodeDraft(
        dossierId,
        nodeId,
        values,
      )
      setLastSavedAt(res.saved_at)
      setState("saved")
    } catch (err) {
      setState("error")
      setErrorMessage(err instanceof Error ? err.message : String(err))
    }
  }, [dossierId, nodeId])

  const save = React.useCallback(
    (values: Record<string, unknown>) => {
      if (!dossierId || !nodeId) return
      pendingValues.current = { ...(pendingValues.current ?? {}), ...values }
      setState("unsaved")
      if (timer.current) clearTimeout(timer.current)
      timer.current = setTimeout(() => {
        void flush()
      }, debounceMs)
    },
    [dossierId, nodeId, debounceMs, flush],
  )

  /** Forca o save imediato (ignora debounce) — util antes de submit. */
  const flushNow = React.useCallback(async () => {
    if (timer.current) {
      clearTimeout(timer.current)
      timer.current = null
    }
    await flush()
  }, [flush])

  // Cleanup pendente ao desmontar.
  React.useEffect(() => {
    return () => {
      if (timer.current) clearTimeout(timer.current)
    }
  }, [])

  return {
    state,
    lastSavedAt,
    errorMessage,
    save,
    flushNow,
  }
}

// ─── Evidence: attachments ───────────────────────────────────────────────

export function useDossierAttachments(
  dossierId: string | null | undefined,
  nodeId?: string | null,
) {
  return useQuery<AttachmentRead[]>({
    queryKey: KEYS.attachments(dossierId ?? "", nodeId),
    queryFn: () => credito.attachments.list(dossierId as string, nodeId),
    enabled: Boolean(dossierId),
  })
}

export function useUploadAttachment(dossierId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: {
      file: File
      node_id?: string | null
      description?: string | null
    }) =>
      credito.attachments.upload(dossierId, vars.file, {
        node_id: vars.node_id ?? null,
        description: vars.description ?? null,
      }),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ["credito", "attachments", dossierId],
      })
    },
  })
}

export function useDeleteAttachment(dossierId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (attachmentId: string) =>
      credito.attachments.remove(dossierId, attachmentId),
    onSuccess: () => {
      qc.invalidateQueries({
        queryKey: ["credito", "attachments", dossierId],
      })
    },
  })
}

// ─── Evidence: notes ─────────────────────────────────────────────────────

export function useDossierNotes(
  dossierId: string | null | undefined,
  nodeId?: string | null,
) {
  return useQuery<NoteRead[]>({
    queryKey: KEYS.notes(dossierId ?? "", nodeId),
    queryFn: () => credito.notes.list(dossierId as string, nodeId),
    enabled: Boolean(dossierId),
  })
}

export function useCreateNote(dossierId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: NoteCreatePayload) =>
      credito.notes.create(dossierId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["credito", "notes", dossierId] })
    },
  })
}

export function useUpdateNote(dossierId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (vars: { noteId: string; payload: NoteUpdatePayload }) =>
      credito.notes.update(dossierId, vars.noteId, vars.payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["credito", "notes", dossierId] })
    },
  })
}

export function useDeleteNote(dossierId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (noteId: string) => credito.notes.remove(dossierId, noteId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["credito", "notes", dossierId] })
    },
  })
}

// ─── Evidence: links ─────────────────────────────────────────────────────

export function useDossierLinks(
  dossierId: string | null | undefined,
  nodeId?: string | null,
) {
  return useQuery<LinkRead[]>({
    queryKey: KEYS.links(dossierId ?? "", nodeId),
    queryFn: () => credito.links.list(dossierId as string, nodeId),
    enabled: Boolean(dossierId),
  })
}

export function useCreateLink(dossierId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (payload: LinkCreatePayload) =>
      credito.links.create(dossierId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["credito", "links", dossierId] })
    },
  })
}

export function useDeleteLink(dossierId: string) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (linkId: string) => credito.links.remove(dossierId, linkId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["credito", "links", dossierId] })
    },
  })
}
