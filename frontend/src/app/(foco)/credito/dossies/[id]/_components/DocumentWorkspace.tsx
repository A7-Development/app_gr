// DocumentWorkspace — painel do step `document_request` no cockpit.
//
// Ciclo dirigido pelo analista (IA propoe, humano homologa — esteira §14):
// sobe arquivo + escolhe o TIPO -> "Processar" (IA le via Vision) -> revisa a
// extracao formatada -> ajusta se precisar -> Aprovar -> Continuar. Depois de
// aprovado da pra Reavaliar. Reusa FileUploadZone; fala com credito.documents.*.

"use client"

import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  RiAddLine,
  RiAlertLine,
  RiArrowGoBackLine,
  RiCheckboxCircleFill,
  RiCheckLine,
  RiCloseLine,
  RiDeleteBin6Line,
  RiExternalLinkLine,
  RiFileTextLine,
  RiLoader4Line,
  RiPencilLine,
  RiSparkling2Line,
} from "@remixicon/react"
import { toast } from "sonner"

import { Button } from "@/components/tremor/Button"
import { Input } from "@/components/tremor/Input"
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
  docTypes,
  onContinue,
  continuing = false,
}: {
  dossierId: string
  requiredDocTypes?: string[]
  /** Restringe a estação a estes tipos: filtra a lista de documentos E as
   *  opções de upload. Sem isso, docs de OUTRAS estações vazariam pra cá. */
  docTypes?: string[]
  onContinue?: () => void
  continuing?: boolean
}) {
  const qc = useQueryClient()
  const allowed = React.useMemo(
    () =>
      docTypes && docTypes.length > 0
        ? new Set(docTypes.map((t) => t.toLowerCase()))
        : null,
    [docTypes],
  )
  const typeOptions = allowed
    ? DOC_TYPES.filter((t) => allowed.has(t.value))
    : DOC_TYPES
  const [docType, setDocType] = React.useState<string>(
    () => typeOptions[0]?.value ?? "dre",
  )
  const queryKey = ["credito", "documents", dossierId]

  const { data: allDocs = [] } = useQuery({
    queryKey,
    queryFn: () => credito.documents.list(dossierId),
  })
  const docs = React.useMemo(
    () =>
      allowed ? allDocs.filter((d) => allowed.has(d.doc_type.toLowerCase())) : allDocs,
    [allDocs, allowed],
  )

  const invalidate = () => qc.invalidateQueries({ queryKey })

  const uploadMut = useMutation({
    mutationFn: (file: File) => credito.documents.upload(dossierId, file, docType),
    onSuccess: () => {
      toast.success("Documento anexado.")
      invalidate()
    },
    onError: (e) => toast.error(`Erro no upload: ${(e as Error).message}`),
  })

  const uploadedTypes = new Set(docs.map((d) => d.doc_type.toLowerCase()))
  const missing = requiredDocTypes.filter((t) => !uploadedTypes.has(t.toLowerCase()))

  return (
    <div className="space-y-5">
      <div>
        <p className="text-sm font-medium text-gray-900 dark:text-gray-50">
          Documentos
        </p>
        <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
          Suba o arquivo, escolha o tipo e clique em <b>Processar</b> — a IA lê e
          extrai os dados. Você confere, ajusta se precisar e aprova.
        </p>
      </div>

      {requiredDocTypes.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className={tableTokens.cellSecondary}>Obrigatórios:</span>
          {requiredDocTypes.map((t) => {
            const ok = uploadedTypes.has(t.toLowerCase())
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

      {/* Upload: tipo + zona (chips só quando há mais de um tipo possível) */}
      <div className="space-y-2 rounded-md border border-gray-200 bg-gray-50/50 p-3 dark:border-gray-800 dark:bg-gray-950/40">
        {typeOptions.length > 1 && (
          <p className="text-xs font-medium text-gray-700 dark:text-gray-300">
            Tipo do documento
          </p>
        )}
        <div className={cx("flex flex-wrap gap-1.5", typeOptions.length <= 1 && "hidden")}>
          {typeOptions.map((opt) => (
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

      {/* Lista de cards */}
      {docs.length === 0 ? (
        <p className={tableTokens.cellSecondary}>Nenhum documento ainda.</p>
      ) : (
        <ul className="space-y-3">
          {docs.map((doc) => (
            <li key={doc.id}>
              <DocCard dossierId={dossierId} doc={doc} onChanged={invalidate} />
            </li>
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

// ─── Card de documento ───────────────────────────────────────────────────────

type Fields = Record<string, unknown>

const STATUS_META: Record<string, { label: string; tone: string }> = {
  pending: {
    label: "Aguardando",
    tone: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
  },
  processing: {
    label: "Processando",
    tone: "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300",
  },
  success: {
    label: "Extraído",
    tone: "bg-sky-50 text-sky-700 dark:bg-sky-500/10 dark:text-sky-300",
  },
  validated: {
    label: "Validado",
    tone: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
  },
  error: {
    label: "Erro",
    tone: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
  },
}

function DocCard({
  dossierId,
  doc,
  onChanged,
}: {
  dossierId: string
  doc: CreditDocumentRead
  onChanged: () => void
}) {
  const status = doc.extraction_status
  const meta = STATUS_META[status] ?? STATUS_META.pending
  const processed = status === "success" || status === "validated"

  const extraction = (doc.ai_extraction ?? {}) as Fields
  const currentFields = (extraction.extracted_fields ?? null) as Fields | null
  const aiOriginal = (extraction._ai_original ?? null) as Fields | null
  const analystEdited = extraction._analyst_edited === true

  // Edicao local (draft) — IA propoe, analista homologa.
  const [editing, setEditing] = React.useState(false)
  const [draft, setDraft] = React.useState<Fields>({})
  const dirty =
    editing && JSON.stringify(draft) !== JSON.stringify(currentFields ?? {})

  const beginEdit = () => {
    setDraft(structuredClone(currentFields ?? {}))
    setEditing(true)
  }
  const cancelEdit = () => {
    if (dirty && !window.confirm("Descartar os ajustes não salvos?")) return
    setEditing(false)
  }

  // ── Mutations ────────────────────────────────────────────────────────────
  const extractMut = useMutation({
    mutationFn: () => credito.documents.extract(dossierId, doc.id),
    onSuccess: () => {
      toast.success("Documento processado pela IA.")
      setEditing(false)
      onChanged()
    },
    onError: (e) => toast.error(`Erro ao processar: ${(e as Error).message}`),
  })
  const approveMut = useMutation({
    mutationFn: (fields: Fields) =>
      credito.documents.updateExtraction(dossierId, doc.id, {
        extracted_fields: fields,
      }),
    onSuccess: () => {
      toast.success("Extração aprovada.")
      setEditing(false)
      onChanged()
    },
    onError: (e) => toast.error(`Erro ao aprovar: ${(e as Error).message}`),
  })
  const deleteMut = useMutation({
    mutationFn: () => credito.documents.remove(dossierId, doc.id),
    onSuccess: () => {
      toast.success("Documento removido.")
      onChanged()
    },
    onError: (e) => toast.error(`Erro ao remover: ${(e as Error).message}`),
  })
  const [openingFile, setOpeningFile] = React.useState(false)
  const openFile = async () => {
    setOpeningFile(true)
    try {
      const url = await credito.documents.fileObjectUrl(dossierId, doc.id)
      window.open(url, "_blank", "noopener,noreferrer")
      // Revoga depois de um tempo — a aba ja carregou o blob.
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (e) {
      toast.error(`Não foi possível abrir o documento: ${(e as Error).message}`)
    } finally {
      setOpeningFile(false)
    }
  }

  const reprocess = () => {
    if (
      (status === "validated" || analystEdited) &&
      !window.confirm(
        "Reprocessar descarta a extração atual (incluindo seus ajustes) e lê o documento de novo pela IA. Continuar?",
      )
    ) {
      return
    }
    extractMut.mutate()
  }

  const viewFields = editing ? draft : currentFields ?? {}

  return (
    <div className="rounded-lg border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
      {/* Header */}
      <div className="flex items-start gap-2.5 border-b border-gray-100 p-3 dark:border-gray-900">
        <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md bg-gray-100 dark:bg-gray-900">
          <RiFileTextLine className="size-4 text-gray-500" aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="truncate text-sm font-medium text-gray-900 dark:text-gray-100">
              {doc.original_filename}
            </p>
            <span className={cx(tableTokens.badge, meta.tone)}>
              {status === "processing" && (
                <RiLoader4Line
                  className="mr-1 inline size-3 animate-spin"
                  aria-hidden
                />
              )}
              {meta.label}
            </span>
            {analystEdited && (
              <span
                className={cx(
                  tableTokens.badge,
                  "bg-violet-50 text-violet-700 dark:bg-violet-500/10 dark:text-violet-300",
                )}
                title="Os valores foram ajustados pelo analista; o original da IA está preservado."
              >
                editado
              </span>
            )}
          </div>
          <p className={cx(tableTokens.cellSecondary, "mt-0.5 truncate")}>
            {DOC_LABEL[doc.doc_type.toLowerCase()] ?? doc.doc_type}
            {doc.ai_model_used && <> · {doc.ai_model_used}</>}
            {doc.ai_prompt_version && <> · {doc.ai_prompt_version}</>}
            {doc.uploaded_at && <> · {fmtDateTime(doc.uploaded_at)}</>}
          </p>
        </div>
        {processed && doc.extraction_confidence != null && (
          <ConfidenceBadge value={Number(doc.extraction_confidence)} />
        )}
      </div>

      {/* Corpo */}
      <div className="p-3">
        {status === "pending" && (
          <p className={tableTokens.cellSecondary}>
            Documento anexado. Clique em <b>Processar</b> para a IA extrair os
            dados.
          </p>
        )}
        {status === "processing" && (
          <p className={cx(tableTokens.cellSecondary, "flex items-center gap-1.5")}>
            <RiLoader4Line className="size-3.5 animate-spin" aria-hidden /> A IA
            está lendo o documento…
          </p>
        )}
        {status === "error" && (
          <p className="text-xs text-red-600 dark:text-red-400">
            {doc.extraction_error ?? "Falha na extração."}
          </p>
        )}

        {processed && currentFields && (
          <ExtractionReview
            fields={viewFields}
            aiOriginal={aiOriginal}
            editing={editing}
            onChange={setDraft}
          />
        )}
      </div>

      {/* Barra de ações */}
      <div className="flex flex-wrap items-center gap-2 border-t border-gray-100 p-3 dark:border-gray-900">
        <Button
          variant="ghost"
          onClick={openFile}
          isLoading={openingFile}
          className="text-gray-600 dark:text-gray-400"
        >
          <RiExternalLinkLine className="size-4" aria-hidden />
          Ver documento
        </Button>

        <div className="ml-auto flex flex-wrap items-center gap-2">
          {editing ? (
            <>
              {aiOriginal && (
                <Button
                  variant="ghost"
                  onClick={() => setDraft(structuredClone(aiOriginal))}
                  title="Descarta seus ajustes e volta aos valores que a IA extraiu."
                >
                  <RiArrowGoBackLine className="size-4" aria-hidden />
                  Valores da IA
                </Button>
              )}
              <Button variant="ghost" onClick={cancelEdit}>
                <RiCloseLine className="size-4" aria-hidden />
                Cancelar
              </Button>
              <Button
                onClick={() => approveMut.mutate(draft)}
                isLoading={approveMut.isPending}
              >
                <RiCheckLine className="size-4" aria-hidden />
                Salvar e aprovar
              </Button>
            </>
          ) : (
            <>
              <Button
                variant="ghost"
                onClick={() => deleteMut.mutate()}
                isLoading={deleteMut.isPending}
                className="text-red-600 dark:text-red-400"
                title="Remove este documento (depois você pode subir outro)."
              >
                <RiDeleteBin6Line className="size-4" aria-hidden />
                Excluir
              </Button>
              <Button
                variant="secondary"
                onClick={reprocess}
                isLoading={extractMut.isPending}
              >
                <RiSparkling2Line className="size-4" aria-hidden />
                {processed ? "Reprocessar IA" : "Processar"}
              </Button>
              {processed && (
                <Button variant="secondary" onClick={beginEdit}>
                  <RiPencilLine className="size-4" aria-hidden />
                  {status === "validated" ? "Reavaliar" : "Ajustar"}
                </Button>
              )}
              {status === "success" && (
                <Button
                  onClick={() => approveMut.mutate(currentFields ?? {})}
                  isLoading={approveMut.isPending}
                >
                  <RiCheckboxCircleFill className="size-4" aria-hidden />
                  Aprovar
                </Button>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ─── Revisão da extração (formatada + editável) ───────────────────────────────

function ExtractionReview({
  fields,
  aiOriginal,
  editing,
  onChange,
}: {
  fields: Fields
  aiOriginal: Fields | null
  editing: boolean
  onChange: (next: Fields) => void
}) {
  const monthly = getMonthly(fields)
  // Chaves escalares (tudo que nao e `monthly`, lista, objeto nem `_…`).
  const scalarKeys = Object.keys(fields).filter(
    (k) =>
      k !== "monthly" &&
      !k.startsWith("_") &&
      (fields[k] === null || typeof fields[k] !== "object"),
  )
  // Listas de objetos (ex.: socios do contrato social) — viram mini-tabela,
  // nunca "[object Object]".
  const listKeys = Object.keys(fields).filter(
    (k) =>
      k !== "monthly" &&
      !k.startsWith("_") &&
      Array.isArray(fields[k]) &&
      (fields[k] as unknown[]).length > 0,
  )

  const setField = (key: string, value: unknown) =>
    onChange({ ...fields, [key]: value })

  const setMonthly = (rows: MonthRow[]) => {
    const next: Fields = { ...fields, monthly: rows }
    // Mantem o total coerente com a soma dos meses quando ha campo de receita.
    if ("revenue" in fields) next.revenue = round2(sumRows(rows))
    onChange(next)
  }

  return (
    <div className="space-y-3">
      {/* Resumo escalar */}
      {scalarKeys.length > 0 && (
        <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
          {scalarKeys.map((k) => (
            <ScalarField
              key={k}
              fieldKey={k}
              value={fields[k]}
              aiValue={aiOriginal ? aiOriginal[k] : undefined}
              editing={editing && k !== "revenue"} // revenue e derivado da soma
              onChange={(v) => setField(k, v)}
            />
          ))}
        </dl>
      )}

      {/* Listas de objetos (socios etc.) */}
      {listKeys.map((k) => (
        <GenericListTable key={k} fieldKey={k} rows={fields[k] as unknown[]} />
      ))}

      {/* Tabela mensal */}
      {monthly && (
        <MonthlyTable rows={monthly} editing={editing} onChange={setMonthly} />
      )}

      {/* Checks de sanidade + agregados */}
      {monthly && monthly.length > 0 && (
        <SanityAndAggregates fields={fields} rows={monthly} />
      )}
    </div>
  )
}

function ScalarField({
  fieldKey,
  value,
  aiValue,
  editing,
  onChange,
}: {
  fieldKey: string
  value: unknown
  aiValue: unknown
  editing: boolean
  onChange: (v: unknown) => void
}) {
  const label = FIELD_LABELS[fieldKey] ?? humanize(fieldKey)
  const edited =
    aiValue !== undefined && JSON.stringify(aiValue) !== JSON.stringify(value)

  return (
    <div className="flex flex-col gap-0.5">
      <dt
        className={cx(
          tableTokens.cellSecondary,
          "flex items-center gap-1 text-[11px] uppercase tracking-wide",
        )}
      >
        {label}
        {edited && (
          <span
            className="text-violet-500"
            title={`Ajustado pelo analista. IA: ${displayScalar(fieldKey, aiValue)}`}
          >
            ●
          </span>
        )}
      </dt>
      {editing ? (
        <Input
          value={String(value ?? "")}
          onChange={(e) => onChange(e.target.value)}
          className="h-8"
        />
      ) : (
        <dd className="text-sm font-medium tabular-nums text-gray-900 dark:text-gray-100">
          {displayScalar(fieldKey, value)}
        </dd>
      )}
    </div>
  )
}

/** Lista de objetos extraída (ex.: `socios`) como mini-tabela legível. */
function GenericListTable({ fieldKey, rows }: { fieldKey: string; rows: unknown[] }) {
  const objects = rows.filter(
    (r): r is Record<string, unknown> => typeof r === "object" && r !== null,
  )
  if (objects.length === 0) {
    // Lista de primitivos — vira linha única legível.
    return (
      <div>
        <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
          {FIELD_LABELS[fieldKey] ?? humanize(fieldKey)}
        </p>
        <p className={tableTokens.cellText}>{rows.map(String).join(" · ")}</p>
      </div>
    )
  }
  const columns = Array.from(
    objects.reduce<Set<string>>((acc, o) => {
      Object.keys(o).forEach((k) => acc.add(k))
      return acc
    }, new Set()),
  )
  return (
    <div>
      <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {FIELD_LABELS[fieldKey] ?? humanize(fieldKey)}
      </p>
      <div className="overflow-hidden rounded-md border border-gray-200 dark:border-gray-800">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50/60 dark:border-gray-900 dark:bg-gray-900/40">
              {columns.map((c) => (
                <th key={c} className={cx(tableTokens.header, "px-3 py-1.5 text-left")}>
                  {FIELD_LABELS[c] ?? humanize(c)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {objects.map((row, i) => (
              <tr
                key={i}
                className="border-b border-gray-50 last:border-0 dark:border-gray-900/60"
              >
                {columns.map((c) => (
                  <td key={c} className={cx(tableTokens.cellText, "px-3 py-1")}>
                    {displayScalar(c, row[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

type MonthRow = { month: string; value: number }

function MonthlyTable({
  rows,
  editing,
  onChange,
}: {
  rows: MonthRow[]
  editing: boolean
  onChange: (rows: MonthRow[]) => void
}) {
  const setRow = (i: number, patch: Partial<MonthRow>) =>
    onChange(rows.map((r, idx) => (idx === i ? { ...r, ...patch } : r)))
  const removeRow = (i: number) => onChange(rows.filter((_, idx) => idx !== i))
  const addRow = () => onChange([...rows, { month: "", value: 0 }])

  return (
    <div>
      <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
        Receita mensal
      </p>
      <div className="overflow-hidden rounded-md border border-gray-200 dark:border-gray-800">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50/60 dark:border-gray-900 dark:bg-gray-900/40">
              <th className={cx(tableTokens.header, "px-3 py-1.5 text-left")}>
                Mês
              </th>
              <th className={cx(tableTokens.header, "px-3 py-1.5 text-right")}>
                Receita bruta (R$)
              </th>
              {editing && <th className="w-8" />}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr
                key={i}
                className="border-b border-gray-50 last:border-0 dark:border-gray-900/60"
              >
                <td className="px-3 py-1">
                  {editing ? (
                    <Input
                      value={r.month}
                      onChange={(e) => setRow(i, { month: e.target.value })}
                      placeholder="2025-01"
                      className="h-7"
                    />
                  ) : (
                    <span className={tableTokens.cellText}>
                      {fmtMonth(r.month)}
                    </span>
                  )}
                </td>
                <td className="px-3 py-1 text-right">
                  {editing ? (
                    <Input
                      type="number"
                      step="0.01"
                      value={String(r.value)}
                      onChange={(e) =>
                        setRow(i, { value: Number(e.target.value) || 0 })
                      }
                      className="h-7 text-right"
                    />
                  ) : (
                    <span className={cx(tableTokens.cellNumber)}>
                      {fmtBRL(r.value)}
                    </span>
                  )}
                </td>
                {editing && (
                  <td className="px-1 text-center">
                    <button
                      type="button"
                      onClick={() => removeRow(i)}
                      className="text-gray-400 hover:text-red-600"
                      title="Remover mês"
                    >
                      <RiCloseLine className="size-4" aria-hidden />
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {editing && (
        <button
          type="button"
          onClick={addRow}
          className="mt-1.5 inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400"
        >
          <RiAddLine className="size-3.5" aria-hidden />
          Adicionar mês
        </button>
      )}
    </div>
  )
}

function SanityAndAggregates({
  fields,
  rows,
}: {
  fields: Fields
  rows: MonthRow[]
}) {
  const sum = sumRows(rows)
  const declared =
    typeof fields.revenue === "number" ? (fields.revenue as number) : null
  const sumMatches = declared == null || Math.abs(sum - declared) < 0.01
  const avg = rows.length ? sum / rows.length : 0
  const values = rows.map((r) => r.value)
  const max = rows[values.indexOf(Math.max(...values))]
  const min = rows[values.indexOf(Math.min(...values))]
  const hasZeroOrNeg = rows.filter((r) => r.value <= 0)
  // Outlier simples: > 2,5x a média ou < 0,4x.
  const outliers = rows.filter(
    (r) => avg > 0 && (r.value > avg * 2.5 || r.value < avg * 0.4),
  )

  return (
    <div className="space-y-2 rounded-md bg-gray-50/70 p-2.5 dark:bg-gray-900/40">
      {/* Agregados */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-1 sm:grid-cols-4">
        <Aggregate label="Total (12m)" value={fmtBRL(sum)} />
        <Aggregate label="Média mensal" value={fmtBRL(avg)} />
        {max && <Aggregate label="Maior mês" value={`${fmtMonth(max.month)} · ${fmtBRL(max.value)}`} />}
        {min && <Aggregate label="Menor mês" value={`${fmtMonth(min.month)} · ${fmtBRL(min.value)}`} />}
      </div>

      {/* Checks */}
      <div className="space-y-1 border-t border-gray-200/60 pt-2 dark:border-gray-800/60">
        <Check
          ok={sumMatches}
          okText={`Soma dos meses confere com o total declarado (${fmtBRL(sum)}).`}
          warnText={`Soma dos meses (${fmtBRL(sum)}) ≠ total declarado (${declared != null ? fmtBRL(declared) : "—"}).`}
        />
        {hasZeroOrNeg.length > 0 && (
          <Check
            ok={false}
            warnText={`${hasZeroOrNeg.length} mês(es) com valor zero ou negativo: ${hasZeroOrNeg.map((r) => fmtMonth(r.month)).join(", ")}.`}
          />
        )}
        {outliers.length > 0 && (
          <Check
            ok={false}
            warnText={`Possível outlier (muito acima/abaixo da média): ${outliers.map((r) => fmtMonth(r.month)).join(", ")}. Confira.`}
          />
        )}
        {rows.length !== 12 && (
          <Check
            ok={false}
            warnText={`${rows.length} mês(es) — esperado 12 para um exercício anual.`}
          />
        )}
      </div>
    </div>
  )
}

function Aggregate({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {label}
      </span>
      <span className="text-xs font-medium tabular-nums text-gray-900 dark:text-gray-100">
        {value}
      </span>
    </div>
  )
}

function Check({
  ok,
  okText,
  warnText,
}: {
  ok: boolean
  okText?: string
  warnText?: string
}) {
  return (
    <div className="flex items-start gap-1.5 text-xs">
      {ok ? (
        <RiCheckLine
          className="mt-0.5 size-3.5 shrink-0 text-emerald-600 dark:text-emerald-400"
          aria-hidden
        />
      ) : (
        <RiAlertLine
          className="mt-0.5 size-3.5 shrink-0 text-amber-600 dark:text-amber-400"
          aria-hidden
        />
      )}
      <span
        className={cx(
          ok
            ? "text-gray-600 dark:text-gray-400"
            : "text-amber-700 dark:text-amber-300",
        )}
      >
        {ok ? okText : warnText}
      </span>
    </div>
  )
}

function ConfidenceBadge({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const tone =
    value >= 0.9
      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
      : value >= 0.7
        ? "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300"
        : "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300"
  return (
    <span
      className={cx(tableTokens.badge, tone, "shrink-0 tabular-nums")}
      title="Nível de confiança que a IA atribuiu à extração."
    >
      confiança {pct}%
    </span>
  )
}

// ─── Helpers de formato / parse ────────────────────────────────────────────────

const FIELD_LABELS: Record<string, string> = {
  cnpj: "CNPJ",
  cpf: "CPF",
  revenue: "Receita total (12m)",
  period_start: "Início do período",
  period_end: "Fim do período",
  razao_social: "Razão social",
  company: "Empresa",
  socios: "Sócios",
  nome: "Nome",
  participacao_pct: "Participação (%)",
  capital_social: "Capital social",
  data_constituicao: "Data de constituição",
  objeto_social: "Objeto social",
  endereco: "Endereço",
}

const brl = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
})

function fmtBRL(n: number): string {
  if (!Number.isFinite(n)) return "—"
  return brl.format(n)
}

function round2(n: number): number {
  return Math.round(n * 100) / 100
}

function fmtMonth(s: string): string {
  // "2025-01" -> "jan/25"
  const m = /^(\d{4})-(\d{2})$/.exec(s)
  if (!m) return s
  const months = [
    "jan",
    "fev",
    "mar",
    "abr",
    "mai",
    "jun",
    "jul",
    "ago",
    "set",
    "out",
    "nov",
    "dez",
  ]
  const idx = Number(m[2]) - 1
  return months[idx] ? `${months[idx]}/${m[1].slice(2)}` : s
}

function fmtDate(s: string): string {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s)
  if (!m) return s
  return `${m[3]}/${m[2]}/${m[1]}`
}

function fmtDateTime(iso: string): string {
  try {
    const d = new Date(iso)
    return d.toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    })
  } catch {
    return iso
  }
}

function displayScalar(key: string, v: unknown): string {
  if (v === null || v === undefined || v === "") return "—"
  if (key === "revenue" && typeof v === "number") return fmtBRL(v)
  if ((key === "period_start" || key === "period_end") && typeof v === "string")
    return fmtDate(v)
  if (typeof v === "number") return v.toLocaleString("pt-BR")
  return String(v)
}

function humanize(key: string): string {
  return key
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase())
}

function getMonthly(fields: Fields): MonthRow[] | null {
  const m = fields.monthly
  if (!Array.isArray(m)) return null
  return m.map((row) => {
    const r = (row ?? {}) as Record<string, unknown>
    return {
      month: String(r.month ?? ""),
      value: Number(r.value ?? 0),
    }
  })
}

function sumRows(rows: MonthRow[]): number {
  return round2(rows.reduce((acc, r) => acc + (Number(r.value) || 0), 0))
}
