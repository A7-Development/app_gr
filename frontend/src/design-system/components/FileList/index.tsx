// src/design-system/components/FileList/index.tsx
//
// Renderiza lista de attachments do dossie (resultados de upload). Cada item
// mostra: icone do mime + filename + size + uploaded_at relativo + autor +
// acoes (download, remover).
//
// Suporta `groupBy="step"` agrupando por node_id com header pequeno.

"use client"

import * as React from "react"
import {
  RiDeleteBinLine,
  RiDownloadLine,
  RiFile3Line,
  RiFileImageLine,
  RiFilePdf2Line,
  RiFileTextLine,
  type RemixiconComponentType,
} from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

export type FileListItem = {
  id: string
  filename: string
  mime_type: string
  size_bytes: number
  uploaded_at: string
  uploaded_by_label?: string | null
  /** node_id ao qual o anexo esta vinculado (null = anexo do dossie). */
  node_id?: string | null
  /** Label legivel do node (ex.: "Coleta de DRE"). */
  node_label?: string | null
  /** URL absoluta de download. */
  download_url?: string | null
}

export type FileListProps = {
  files: FileListItem[]
  onDelete?: (id: string) => void
  /** Quando "step", agrupa items por node_id. */
  groupBy?: "none" | "step"
  /** Mensagem custom no estado vazio. */
  emptyMessage?: string
  /** Quando o requester nao e o uploader nem admin, omitir botao de delete. */
  canDelete?: (item: FileListItem) => boolean
  className?: string
}

export function FileList({
  files,
  onDelete,
  groupBy = "none",
  emptyMessage = "Nenhum documento anexado",
  canDelete,
  className,
}: FileListProps) {
  if (files.length === 0) {
    return (
      <p className={cx(tableTokens.cellSecondary, "py-3 text-center", className)}>
        {emptyMessage}
      </p>
    )
  }

  if (groupBy === "step") {
    const groups = groupByNode(files)
    return (
      <div className={cx("space-y-3", className)}>
        {groups.map(({ key, label, items }) => (
          <div key={key}>
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-500">
              {label}
            </p>
            <ul className="space-y-1">
              {items.map((file) => (
                <Row
                  key={file.id}
                  file={file}
                  onDelete={onDelete}
                  canDelete={canDelete?.(file) ?? Boolean(onDelete)}
                />
              ))}
            </ul>
          </div>
        ))}
      </div>
    )
  }

  return (
    <ul className={cx("space-y-1", className)}>
      {files.map((file) => (
        <Row
          key={file.id}
          file={file}
          onDelete={onDelete}
          canDelete={canDelete?.(file) ?? Boolean(onDelete)}
        />
      ))}
    </ul>
  )
}

// ─── Row ────────────────────────────────────────────────────────────────────

function Row({
  file,
  onDelete,
  canDelete,
}: {
  file: FileListItem
  onDelete?: (id: string) => void
  canDelete: boolean
}) {
  const Icon = iconForMime(file.mime_type)
  return (
    <li className="flex items-center gap-2 rounded border border-gray-100 bg-white px-2.5 py-1.5 dark:border-gray-900 dark:bg-gray-950">
      <Icon
        className="size-4 shrink-0 text-gray-400 dark:text-gray-500"
        aria-hidden
      />
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-medium text-gray-900 dark:text-gray-100">
          {file.filename}
        </p>
        <p className={tableTokens.cellSecondary}>
          {formatBytes(file.size_bytes)}
          {" · "}
          {formatRelativeShort(file.uploaded_at)}
          {file.uploaded_by_label && <> · {file.uploaded_by_label}</>}
        </p>
      </div>
      {file.download_url && (
        <a
          href={file.download_url}
          download={file.filename}
          target="_blank"
          rel="noopener noreferrer"
          className={cx(
            "inline-flex size-7 shrink-0 items-center justify-center rounded",
            "text-gray-400 hover:bg-gray-100 hover:text-gray-700",
            "dark:text-gray-500 dark:hover:bg-gray-800 dark:hover:text-gray-300",
          )}
          aria-label={`Baixar ${file.filename}`}
        >
          <RiDownloadLine className="size-3.5" aria-hidden />
        </a>
      )}
      {canDelete && onDelete && (
        <Button
          variant="ghost"
          className="size-7 shrink-0 p-0"
          onClick={() => onDelete(file.id)}
          aria-label={`Remover ${file.filename}`}
        >
          <RiDeleteBinLine className="size-3.5" aria-hidden />
        </Button>
      )}
    </li>
  )
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function iconForMime(mime: string): RemixiconComponentType {
  if (mime === "application/pdf") return RiFilePdf2Line
  if (mime.startsWith("image/")) return RiFileImageLine
  if (
    mime === "text/plain" ||
    mime === "text/csv" ||
    mime === "application/json"
  )
    return RiFileTextLine
  return RiFile3Line
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

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

function groupByNode(
  files: FileListItem[],
): Array<{ key: string; label: string; items: FileListItem[] }> {
  const map = new Map<string, FileListItem[]>()
  for (const f of files) {
    const k = f.node_id ?? "__dossier__"
    if (!map.has(k)) map.set(k, [])
    map.get(k)!.push(f)
  }
  const out: Array<{ key: string; label: string; items: FileListItem[] }> = []
  // Anexos do dossie (sem step) primeiro.
  const dossierItems = map.get("__dossier__")
  if (dossierItems) {
    out.push({ key: "__dossier__", label: "Dossie", items: dossierItems })
  }
  Array.from(map.entries()).forEach(([key, items]) => {
    if (key === "__dossier__") return
    const label = items[0].node_label ?? key
    out.push({ key, label, items })
  })
  return out
}
