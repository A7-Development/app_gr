// DocumentWorkspace — painel do step `document_request` no cockpit.
//
// Ciclo dirigido pelo analista: sobe arquivo + escolhe o TIPO -> "Processar"
// (IA extrai via Vision) -> ve o resultado -> valida/reprocessa/exclui ->
// Continuar. Reusa FileUploadZone; fala com credito.documents.*.

"use client"

import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  RiCheckboxCircleFill,
  RiFileTextLine,
  RiLoader4Line,
  RiSparkling2Line,
} from "@remixicon/react"
import { toast } from "sonner"

import { Button } from "@/components/tremor/Button"
import { FileUploadZone } from "@/design-system/components/FileUploadZone"
import { tableTokens } from "@/design-system/tokens/table"
import { credito, type CreditDocumentRead } from "@/lib/credito-client"
import { cx } from "@/lib/utils"

const DOC_TYPES: Array<{ value: string; label: string }> = [
  { value: "dre", label: "DRE" },
  { value: "balance_sheet", label: "Balanço" },
  { value: "revenue_report", label: "Faturamento" },
  { value: "social_contract", label: "Contrato Social" },
  { value: "scr", label: "SCR" },
  { value: "indebtedness", label: "Endividamento" },
  { value: "abc_curve", label: "Curva ABC" },
  { value: "income_tax_pf", label: "IR Sócio" },
  { value: "cnh", label: "CNH" },
  { value: "rg", label: "RG" },
]
const DOC_LABEL: Record<string, string> = Object.fromEntries(
  DOC_TYPES.map((d) => [d.value, d.label]),
)

export function DocumentWorkspace({
  dossierId,
  requiredDocTypes = [],
  onContinue,
  continuing = false,
}: {
  dossierId: string
  requiredDocTypes?: string[]
  onContinue?: () => void
  continuing?: boolean
}) {
  const qc = useQueryClient()
  const [docType, setDocType] = React.useState<string>("dre")
  const queryKey = ["credito", "documents", dossierId]

  const { data: docs = [] } = useQuery({
    queryKey,
    queryFn: () => credito.documents.list(dossierId),
  })

  const invalidate = () => qc.invalidateQueries({ queryKey })

  const uploadMut = useMutation({
    mutationFn: (file: File) => credito.documents.upload(dossierId, file, docType),
    onSuccess: () => {
      toast.success("Documento anexado.")
      invalidate()
    },
    onError: (e) => toast.error(`Erro no upload: ${(e as Error).message}`),
  })
  const extractMut = useMutation({
    mutationFn: (docId: string) => credito.documents.extract(dossierId, docId),
    onSuccess: () => {
      toast.success("Documento processado pela IA.")
      invalidate()
    },
    onError: (e) => toast.error(`Erro ao processar: ${(e as Error).message}`),
  })
  const deleteMut = useMutation({
    mutationFn: (docId: string) => credito.documents.remove(dossierId, docId),
    onSuccess: () => {
      toast.success("Documento removido.")
      invalidate()
    },
    onError: (e) => toast.error(`Erro ao remover: ${(e as Error).message}`),
  })
  const validateMut = useMutation({
    mutationFn: (doc: CreditDocumentRead) => {
      const fields =
        ((doc.ai_extraction ?? {}) as Record<string, unknown>).extracted_fields ??
        {}
      return credito.documents.updateExtraction(dossierId, doc.id, {
        extracted_fields: fields as Record<string, unknown>,
      })
    },
    onSuccess: () => {
      toast.success("Extração validada.")
      invalidate()
    },
    onError: (e) => toast.error(`Erro ao validar: ${(e as Error).message}`),
  })

  const uploadedTypes = new Set(docs.map((d) => d.doc_type))
  const missing = requiredDocTypes.filter((t) => !uploadedTypes.has(t))

  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-medium text-gray-900 dark:text-gray-50">
          Documentos
        </p>
        <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
          Suba o arquivo, escolha o tipo e clique em <b>Processar</b> — a IA lê e
          extrai os dados. Você confere e valida.
        </p>
      </div>

      {requiredDocTypes.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={tableTokens.cellSecondary}>Obrigatórios:</span>
          {requiredDocTypes.map((t) => {
            const ok = uploadedTypes.has(t)
            return (
              <span
                key={t}
                className={cx(
                  tableTokens.badge,
                  ok
                    ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
                    : "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
                )}
              >
                {ok ? "✓ " : "⚠ "}
                {DOC_LABEL[t] ?? t}
              </span>
            )
          })}
        </div>
      )}

      {/* Upload: tipo + zona */}
      <div className="space-y-2 rounded-md border border-gray-200 bg-gray-50/50 p-3 dark:border-gray-800 dark:bg-gray-950/40">
        <p className="text-xs font-medium text-gray-700 dark:text-gray-300">
          Tipo do documento
        </p>
        <div className="flex flex-wrap gap-1.5">
          {DOC_TYPES.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => setDocType(opt.value)}
              className={cx(
                "rounded-md border px-2.5 py-1 text-xs font-medium",
                docType === opt.value
                  ? "border-blue-500 bg-blue-50 text-blue-700 dark:border-blue-500/40 dark:bg-blue-500/10 dark:text-blue-300"
                  : "border-gray-200 bg-white text-gray-600 hover:border-gray-300 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-400",
              )}
            >
              {opt.label}
            </button>
          ))}
        </div>
        <FileUploadZone
          accept={["application/pdf", "image/png", "image/jpeg"]}
          multiple={false}
          compact
          label={`Soltar/escolher arquivo — tipo: ${DOC_LABEL[docType]}`}
          onUpload={(file) => uploadMut.mutateAsync(file).then(() => undefined)}
        />
      </div>

      {/* Lista */}
      {docs.length === 0 ? (
        <p className={tableTokens.cellSecondary}>Nenhum documento ainda.</p>
      ) : (
        <ul className="space-y-2">
          {docs.map((doc) => (
            <DocRow
              key={doc.id}
              doc={doc}
              onExtract={() => extractMut.mutate(doc.id)}
              extracting={extractMut.isPending && extractMut.variables === doc.id}
              onValidate={() => validateMut.mutate(doc)}
              validating={validateMut.isPending}
              onDelete={() => {
                if (window.confirm("Remover este documento?")) {
                  deleteMut.mutate(doc.id)
                }
              }}
            />
          ))}
        </ul>
      )}

      {onContinue && (
        <div className="flex justify-end">
          <Button
            onClick={onContinue}
            isLoading={continuing}
            disabled={missing.length > 0}
            title={
              missing.length > 0
                ? `Faltam: ${missing.map((t) => DOC_LABEL[t] ?? t).join(", ")}`
                : undefined
            }
          >
            Continuar
          </Button>
        </div>
      )}
    </div>
  )
}

// ─── Linha de documento ──────────────────────────────────────────────────────

const STATUS_META: Record<
  string,
  { label: string; tone: string }
> = {
  pending: { label: "Aguardando", tone: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300" },
  processing: { label: "Processando", tone: "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300" },
  success: { label: "Extraído", tone: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300" },
  validated: { label: "Validado", tone: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300" },
  error: { label: "Erro", tone: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300" },
}

function DocRow({
  doc,
  onExtract,
  extracting,
  onValidate,
  validating,
  onDelete,
}: {
  doc: CreditDocumentRead
  onExtract: () => void
  extracting: boolean
  onValidate: () => void
  validating: boolean
  onDelete: () => void
}) {
  const status = doc.extraction_status
  const meta = STATUS_META[status] ?? STATUS_META.pending
  const processed = status === "success" || status === "validated"
  const fields =
    ((doc.ai_extraction ?? {}) as Record<string, unknown>).extracted_fields ?? null

  return (
    <li className="rounded-md border border-gray-200 bg-white p-3 dark:border-gray-800 dark:bg-gray-950">
      <div className="flex items-center gap-2">
        <RiFileTextLine className="size-4 shrink-0 text-gray-500" aria-hidden />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium text-gray-900 dark:text-gray-100">
            {doc.original_filename}
          </p>
          <p className={tableTokens.cellSecondary}>
            {DOC_LABEL[doc.doc_type] ?? doc.doc_type}
            {doc.extraction_confidence != null && (
              <> · confiança {Math.round(Number(doc.extraction_confidence) * 100)}%</>
            )}
          </p>
        </div>
        <span className={cx(tableTokens.badge, meta.tone)}>
          {status === "processing" && (
            <RiLoader4Line className="mr-1 inline size-3 animate-spin" aria-hidden />
          )}
          {meta.label}
        </span>
      </div>

      {status === "error" && doc.extraction_error && (
        <p className="mt-1.5 text-xs text-red-600 dark:text-red-400">
          {doc.extraction_error}
        </p>
      )}

      {processed && fields && typeof fields === "object" && (
        <ExtractedFields fields={fields as Record<string, unknown>} />
      )}

      <div className="mt-2 flex flex-wrap items-center justify-end gap-2">
        <Button variant="secondary" onClick={onExtract} isLoading={extracting}>
          <RiSparkling2Line className="size-4" aria-hidden />
          {processed ? "Reprocessar" : "Processar"}
        </Button>
        {status === "success" && (
          <Button variant="ghost" onClick={onValidate} isLoading={validating}>
            <RiCheckboxCircleFill className="size-4" aria-hidden />
            Validar
          </Button>
        )}
        <Button variant="ghost" onClick={onDelete}>
          Excluir
        </Button>
      </div>
    </li>
  )
}

function ExtractedFields({ fields }: { fields: Record<string, unknown> }) {
  const entries = Object.entries(fields).filter(([k]) => !k.startsWith("_"))
  if (entries.length === 0) return null
  return (
    <div className="mt-2 rounded border border-gray-100 bg-gray-50/60 p-2.5 dark:border-gray-900 dark:bg-gray-950/50">
      <p className="mb-1.5 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
        Dados extraídos pela IA
      </p>
      <dl className="grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">
        {entries.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-2">
            <dt className={tableTokens.cellSecondary}>{k}</dt>
            <dd className="text-right text-xs font-medium tabular-nums text-gray-900 dark:text-gray-100">
              {formatVal(v)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function formatVal(v: unknown): string {
  if (v === null || v === undefined) return "—"
  if (typeof v === "number" || typeof v === "string") return String(v)
  if (Array.isArray(v)) return `${v.length} item(s)`
  if (typeof v === "object") return JSON.stringify(v)
  return String(v)
}
