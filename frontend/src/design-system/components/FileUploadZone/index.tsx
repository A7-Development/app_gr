// src/design-system/components/FileUploadZone/index.tsx
//
// Dropzone enterprise para upload de documentos do dossie.
//
// Features:
//   - Drag & drop + click-to-browse
//   - Fila de uploads com status individual (uploading | success | failed)
//   - Validacao client-side (size, mime type)
//   - Variant `compact` pra encaixar no fim de listas (Evidence panel)
//   - Retry de uploads que falharam

"use client"

import * as React from "react"
import {
  RiCheckLine,
  RiCloseLine,
  RiErrorWarningLine,
  RiLoader4Line,
  RiRefreshLine,
  RiUploadCloud2Line,
} from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

export type FileUploadStatus = "uploading" | "success" | "failed"

type QueueItem = {
  /** Local-only id (Date.now() + random suffix). */
  id: string
  file: File
  status: FileUploadStatus
  errorMessage?: string
}

export type FileUploadZoneProps = {
  /** Callback chamado quando o usuario solta um arquivo valido. Promise pra
   *  poder marcar success/failed. Throw -> failed. */
  onUpload: (file: File) => Promise<void>
  /** Lista de mime types aceitos (ex.: ["application/pdf", "image/png"]).
   *  Vazio aceita tudo. */
  accept?: string[]
  /** Tamanho maximo em bytes. Default: 25 MB. */
  maxBytes?: number
  multiple?: boolean
  /** Variante compacta (sem ilustracao, so dropzone curta + texto). */
  compact?: boolean
  /** Texto principal exibido no dropzone (default: "Arraste arquivos aqui ou clique para escolher"). */
  label?: string
  className?: string
}

const DEFAULT_MAX_BYTES = 25 * 1024 * 1024 // 25 MB

export function FileUploadZone({
  onUpload,
  accept,
  maxBytes = DEFAULT_MAX_BYTES,
  multiple = true,
  compact = false,
  label,
  className,
}: FileUploadZoneProps) {
  const inputRef = React.useRef<HTMLInputElement>(null)
  const [dragOver, setDragOver] = React.useState(false)
  const [queue, setQueue] = React.useState<QueueItem[]>([])

  const validate = React.useCallback(
    (file: File): string | null => {
      if (file.size > maxBytes) {
        return `Arquivo grande demais (${formatBytes(file.size)} — max ${formatBytes(maxBytes)})`
      }
      if (accept && accept.length > 0 && !accept.includes(file.type)) {
        return `Tipo de arquivo nao aceito (${file.type || "desconhecido"})`
      }
      return null
    },
    [accept, maxBytes],
  )

  const enqueue = React.useCallback(
    async (files: File[]) => {
      const newItems: QueueItem[] = []
      for (const file of files) {
        const err = validate(file)
        const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
        if (err) {
          newItems.push({
            id,
            file,
            status: "failed",
            errorMessage: err,
          })
        } else {
          newItems.push({ id, file, status: "uploading" })
        }
      }
      setQueue((prev) => [...prev, ...newItems])

      // Dispara uploads em paralelo dos que sao validos.
      for (const item of newItems) {
        if (item.status === "failed") continue
        try {
          await onUpload(item.file)
          setQueue((prev) =>
            prev.map((i) => (i.id === item.id ? { ...i, status: "success" } : i)),
          )
        } catch (e) {
          const msg = e instanceof Error ? e.message : String(e)
          setQueue((prev) =>
            prev.map((i) =>
              i.id === item.id
                ? { ...i, status: "failed", errorMessage: msg }
                : i,
            ),
          )
        }
      }
    },
    [onUpload, validate],
  )

  const handleFiles = React.useCallback(
    (list: FileList | null) => {
      if (!list || list.length === 0) return
      const files = multiple ? Array.from(list) : [list[0]]
      void enqueue(files)
    },
    [enqueue, multiple],
  )

  const handleDrop = React.useCallback(
    (e: React.DragEvent<HTMLDivElement>) => {
      e.preventDefault()
      e.stopPropagation()
      setDragOver(false)
      handleFiles(e.dataTransfer.files)
    },
    [handleFiles],
  )

  const handleRetry = React.useCallback(
    async (id: string) => {
      setQueue((prev) =>
        prev.map((i) => (i.id === id ? { ...i, status: "uploading" } : i)),
      )
      const item = queue.find((i) => i.id === id)
      if (!item) return
      try {
        await onUpload(item.file)
        setQueue((prev) =>
          prev.map((i) => (i.id === id ? { ...i, status: "success" } : i)),
        )
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e)
        setQueue((prev) =>
          prev.map((i) =>
            i.id === id ? { ...i, status: "failed", errorMessage: msg } : i,
          ),
        )
      }
    },
    [onUpload, queue],
  )

  const handleRemove = React.useCallback((id: string) => {
    setQueue((prev) => prev.filter((i) => i.id !== id))
  }, [])

  const dropzoneLabel =
    label ?? "Arraste arquivos aqui ou clique para escolher"

  return (
    <div className={cx("space-y-2", className)}>
      {/* MOTIVO: <button> cru — area de drop precisa ser <div> com click delegado.
          Mantemos como div + onClick + role pra acessibilidade. */}
      <div
        role="button"
        tabIndex={0}
        onClick={() => inputRef.current?.click()}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault()
            inputRef.current?.click()
          }
        }}
        onDragOver={(e) => {
          e.preventDefault()
          setDragOver(true)
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={cx(
          "flex cursor-pointer items-center justify-center rounded-md border-2 border-dashed transition-colors",
          compact ? "px-3 py-2 text-xs" : "px-4 py-6 text-sm",
          dragOver
            ? "border-blue-500 bg-blue-50 dark:bg-blue-500/10"
            : "border-gray-300 bg-white hover:bg-gray-50 dark:border-gray-700 dark:bg-gray-950 dark:hover:bg-gray-900",
        )}
        aria-label={dropzoneLabel}
      >
        <div className="flex items-center gap-2 text-gray-600 dark:text-gray-400">
          <RiUploadCloud2Line
            className={cx(compact ? "size-4" : "size-5")}
            aria-hidden
          />
          <span>{dropzoneLabel}</span>
        </div>
      </div>

      {/* MOTIVO: <input type="file"> cru — Tremor Input nao tem variante de
          file picker (sao mecanismos fundamentalmente diferentes). Mantemos
          escondido e disparamos via click no div acima. */}
      <input
        ref={inputRef}
        type="file"
        multiple={multiple}
        accept={accept?.join(",")}
        className="hidden"
        onChange={(e) => {
          handleFiles(e.target.files)
          e.target.value = "" // reset pra permitir re-selecionar mesmo arquivo
        }}
      />

      {/* Fila */}
      {queue.length > 0 && (
        <ul className="space-y-1">
          {queue.map((item) => (
            <QueueRow
              key={item.id}
              item={item}
              onRemove={() => handleRemove(item.id)}
              onRetry={() => void handleRetry(item.id)}
            />
          ))}
        </ul>
      )}
    </div>
  )
}

// ─── Queue row ──────────────────────────────────────────────────────────────

function QueueRow({
  item,
  onRemove,
  onRetry,
}: {
  item: QueueItem
  onRemove: () => void
  onRetry: () => void
}) {
  return (
    <li
      className={cx(
        "flex items-center gap-2 rounded border px-2.5 py-1.5",
        item.status === "failed"
          ? "border-red-200 bg-red-50/50 dark:border-red-500/30 dark:bg-red-500/5"
          : "border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
      )}
    >
      <StatusIcon status={item.status} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-xs font-medium text-gray-900 dark:text-gray-100">
          {item.file.name}
        </p>
        <p className={tableTokens.cellSecondary}>
          {formatBytes(item.file.size)}
          {item.errorMessage && <> · {item.errorMessage}</>}
        </p>
      </div>
      {item.status === "failed" && (
        <Button variant="ghost" className="size-7 shrink-0 p-0" onClick={onRetry}>
          <RiRefreshLine className="size-3.5" aria-hidden />
        </Button>
      )}
      {item.status !== "uploading" && (
        <Button variant="ghost" className="size-7 shrink-0 p-0" onClick={onRemove}>
          <RiCloseLine className="size-3.5" aria-hidden />
        </Button>
      )}
    </li>
  )
}

function StatusIcon({ status }: { status: FileUploadStatus }) {
  if (status === "uploading") {
    return (
      <RiLoader4Line
        className="size-4 shrink-0 animate-spin text-blue-500"
        aria-hidden
      />
    )
  }
  if (status === "success") {
    return (
      <RiCheckLine
        className="size-4 shrink-0 text-emerald-500"
        aria-hidden
      />
    )
  }
  return (
    <RiErrorWarningLine
      className="size-4 shrink-0 text-red-500"
      aria-hidden
    />
  )
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(1)} MB`
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`
}
