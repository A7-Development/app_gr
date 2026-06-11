// DocumentZones — zonas D1 COMPARTILHADAS das estações de documento
// (handoff Conceito D, frame D1, generalizado a partir do FaturamentoStation):
//
//   <DocumentSourceZone>   documento-fonte: thumbnail 44×56 + chips de estado,
//                          extração AUTOMÁTICA no upload, ações Abrir no
//                          leitor / Substituir / Reprocessar
//   <FichaConferenceZone>  conferência de FICHA (contrato de bloco "Ficha de
//                          campos"): Campo | IA propôs (nunca editável) |
//                          No dossiê (edição inline, autosave) | Estado —
//                          com o PRÓPRIO documento ao lado (par leitura ↔
//                          proposta nunca se separa)
//   <OriginPanel>          o PDF/imagem real no painel de origem
//
// Usadas pela estação Faturamento (que adiciona tabela mensal + chart) e por
// QUALQUER estação de documento (contrato social, SCR, ...) — fim do
// DocumentWorkspace legado nas estações.

"use client"

import * as React from "react"
import { useMutation } from "@tanstack/react-query"
import {
  RiAddLine,
  RiBankLine,
  RiCheckLine,
  RiEditLine,
  RiEyeLine,
  RiFileTextLine,
  RiLoader4Line,
  RiQuillPenLine,
  RiRestartLine,
  RiUpload2Line,
  RiUploadCloud2Line,
} from "@remixicon/react"
import { toast } from "sonner"

import { Button } from "@/components/tremor/Button"
import { provenanceTokens } from "@/design-system/tokens/provenance"
import { credito, type CreditDocumentRead } from "@/lib/credito-client"
import { cx } from "@/lib/utils"

// ─── Tipos e helpers compartilhados ─────────────────────────────────────────

export type Fields = Record<string, unknown>
export type MonthRow = { month: string; value: number }

export const DOC_LABEL: Record<string, string> = {
  dre: "DRE",
  balance_sheet: "Balanço",
  revenue_report: "Faturamento",
  social_contract: "Contrato Social",
  scr: "SCR",
  indebtedness: "Endividamento",
  abc_curve: "Curva ABC",
  income_tax_pf: "IR Sócio",
  cnh: "CNH",
  rg: "RG",
}

export const FIELD_LABELS: Record<string, string> = {
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

export function extractedFieldsOf(doc: CreditDocumentRead): Fields | null {
  const ext = (doc.ai_extraction ?? null) as Fields | null
  if (!ext) return null
  return (ext.extracted_fields ?? null) as Fields | null
}

export function aiOriginalOf(doc: CreditDocumentRead): Fields | null {
  const ext = (doc.ai_extraction ?? null) as Fields | null
  if (!ext) return null
  return (ext._ai_original ?? extractedFieldsOf(doc)) as Fields | null
}

export function getMonthly(fields: Fields | null): MonthRow[] | null {
  if (!fields) return null
  const m = fields.monthly
  if (!Array.isArray(m) || m.length === 0) return null
  return m.map((row) => {
    const r = (row ?? {}) as Record<string, unknown>
    return { month: String(r.month ?? ""), value: Number(r.value ?? 0) }
  })
}

export function fmtDateTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString("pt-BR", {
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

export function humanizeKey(key: string): string {
  return FIELD_LABELS[key] ?? key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())
}

function displayValue(key: string, v: unknown): string {
  if (v === null || v === undefined || v === "") return "—"
  if (typeof v === "number") {
    if (key === "capital_social" || key === "revenue") {
      return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })
    }
    return v.toLocaleString("pt-BR")
  }
  return String(v)
}

// ─── Zona · Documento-fonte ─────────────────────────────────────────────────

export function DocumentSourceZone({
  dossierId,
  docs,
  requiredDocTypes,
  canUpload,
  onChanged,
  juntaFetch = false,
}: {
  dossierId: string
  docs: CreditDocumentRead[]
  requiredDocTypes: string[]
  canUpload: boolean
  onChanged: () => void
  /** Habilita "Buscar na JUCESP" (estações de contrato social): baixa o
   *  documento societário mais recente DIRETO da Junta + QSA oficial. */
  juntaFetch?: boolean
}) {
  const juntaMut = useMutation({
    mutationFn: () => credito.documents.fetchFromJunta(dossierId),
    onSuccess: (doc) => {
      toast.success(
        `Documento da JUCESP anexado (${doc.original_filename}) — extração concluída.`,
      )
      onChanged()
    },
    onError: (e) =>
      toast.error(`Busca na JUCESP falhou: ${(e as Error).message}`),
  })
  const [showUpload, setShowUpload] = React.useState(docs.length === 0)
  const fileInputRef = React.useRef<HTMLInputElement>(null)
  const replaceRef = React.useRef<{ docId: string; docType: string } | null>(null)

  const defaultType = requiredDocTypes[0] ?? "revenue_report"

  const extractMut = useMutation({
    mutationFn: (documentId: string) => credito.documents.extract(dossierId, documentId),
    onSuccess: () => {
      toast.success("Extração concluída.")
      onChanged()
    },
    onError: (e) => toast.error(`Erro na extração: ${(e as Error).message}`),
  })

  const uploadMut = useMutation({
    mutationFn: async (vars: { file: File; docType: string; replaceDocId?: string }) => {
      const doc = await credito.documents.upload(dossierId, vars.file, vars.docType)
      if (vars.replaceDocId) {
        await credito.documents.remove(dossierId, vars.replaceDocId)
      }
      return doc
    },
    onSuccess: (doc) => {
      toast.success("Documento recebido — a extração disparou sozinha.")
      onChanged()
      setShowUpload(false)
      // A extração dispara sozinha ao receber (handoff D2).
      extractMut.mutate(doc.id)
    },
    onError: (e) => toast.error(`Erro no upload: ${(e as Error).message}`),
  })

  const onPickFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    e.target.value = ""
    if (!file) return
    const replace = replaceRef.current
    replaceRef.current = null
    uploadMut.mutate({
      file,
      docType: replace?.docType ?? defaultType,
      replaceDocId: replace?.docId,
    })
  }

  return (
    <section className="rounded border border-gray-200 bg-white shadow-xs dark:border-gray-800 dark:bg-gray-950">
      <header className="flex items-center justify-between border-b border-gray-100 px-5 py-3 dark:border-gray-900">
        <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
          Documento-fonte
        </span>
        <span className="flex items-center gap-3">
          {juntaFetch && canUpload && (
            <button
              type="button"
              onClick={() => {
                if (
                  window.confirm(
                    "Buscar na JUCESP consulta a ficha oficial (QSA + arquivamentos) e baixa o documento societário mais recente arquivado. Leva ~1-2 min e tem custo por consulta. Continuar?",
                  )
                ) {
                  juntaMut.mutate()
                }
              }}
              disabled={juntaMut.isPending}
              className="inline-flex items-center gap-1 text-xs font-medium disabled:opacity-60"
              style={{ color: provenanceTokens.fonte.chipText }}
              title="Baixa o contrato/alteração mais recente direto da Junta Comercial de SP"
            >
              {juntaMut.isPending ? (
                <RiLoader4Line className="size-3.5 animate-spin" aria-hidden />
              ) : (
                <RiBankLine className="size-3.5" aria-hidden />
              )}
              {juntaMut.isPending ? "Buscando na JUCESP…" : "Buscar na JUCESP"}
            </button>
          )}
          {canUpload && (
            <button
              type="button"
              onClick={() => {
                replaceRef.current = null
                setShowUpload((v) => !v)
              }}
              className="inline-flex items-center gap-1 text-xs font-medium text-blue-600 hover:text-blue-700 dark:text-blue-400"
            >
              <RiAddLine className="size-3.5" aria-hidden />
              Adicionar documento
            </button>
          )}
        </span>
      </header>

      <input
        ref={fileInputRef}
        type="file"
        accept="application/pdf,image/png,image/jpeg"
        className="hidden"
        onChange={onPickFile}
      />

      <div className="flex flex-col gap-4 px-5 py-4">
        {docs.map((doc) => (
          <DocRow
            key={doc.id}
            dossierId={dossierId}
            doc={doc}
            canUpload={canUpload}
            onReplace={() => {
              replaceRef.current = { docId: doc.id, docType: doc.doc_type }
              fileInputRef.current?.click()
            }}
            onReprocess={() => {
              if (
                doc.extraction_status === "validated" &&
                !window.confirm(
                  "Reprocessar descarta a extração atual (incluindo ajustes) e lê o documento de novo. Continuar?",
                )
              ) {
                return
              }
              extractMut.mutate(doc.id)
            }}
            reprocessing={extractMut.isPending}
          />
        ))}

        {docs.length === 0 || (showUpload && canUpload) ? (
          <button
            type="button"
            onClick={() => {
              replaceRef.current = null
              fileInputRef.current?.click()
            }}
            disabled={uploadMut.isPending}
            className="flex flex-col items-center gap-2 rounded bg-gray-50 px-6 py-11 text-center transition-colors duration-100 hover:bg-gray-100 dark:bg-gray-925 dark:hover:bg-gray-900"
            style={{ border: "1.5px dashed #D1D5DB" }}
          >
            {uploadMut.isPending ? (
              <RiLoader4Line className="size-7 animate-spin text-gray-400" aria-hidden />
            ) : (
              <RiUploadCloud2Line className="size-7 text-gray-400" aria-hidden />
            )}
            <span className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Arraste o documento aqui ou{" "}
              <span className="font-semibold text-blue-600 dark:text-blue-400">
                procure no computador
              </span>
            </span>
            <span className="text-xs text-gray-400">
              PDF ou imagem · a extração dispara sozinha ao receber
              {requiredDocTypes.length > 0 && (
                <> · esperado: {requiredDocTypes.map((t) => DOC_LABEL[t] ?? t).join(", ")}</>
              )}
            </span>
          </button>
        ) : null}
      </div>
    </section>
  )
}

function DocRow({
  dossierId,
  doc,
  canUpload,
  onReplace,
  onReprocess,
  reprocessing,
}: {
  dossierId: string
  doc: CreditDocumentRead
  canUpload: boolean
  onReplace: () => void
  onReprocess: () => void
  reprocessing: boolean
}) {
  const verde = provenanceTokens.documento
  const status = doc.extraction_status
  const processed = status === "success" || status === "validated"
  const edited = (doc.ai_extraction as Fields | null)?._analyst_edited === true
  const fields = extractedFieldsOf(doc)
  const monthlyCount = getMonthly(fields)?.length ?? 0
  const fieldCount = fields
    ? Object.keys(fields).filter((k) => !k.startsWith("_")).length
    : 0
  const ext = (doc.original_filename.split(".").pop() ?? "PDF").toUpperCase().slice(0, 4)

  const [opening, setOpening] = React.useState(false)
  const openFile = async () => {
    setOpening(true)
    try {
      const url = await credito.documents.fileObjectUrl(dossierId, doc.id)
      window.open(url, "_blank", "noopener,noreferrer")
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
    } catch (e) {
      toast.error(`Não foi possível abrir o documento: ${(e as Error).message}`)
    } finally {
      setOpening(false)
    }
  }

  return (
    <div className="grid grid-cols-[1fr_auto] items-start gap-5">
      <div className="flex min-w-0 gap-3.5">
        {/* Thumbnail 44×56 */}
        <span className="relative mt-0.5 flex h-14 w-11 shrink-0 items-center justify-center rounded-[3px] border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900">
          <RiFileTextLine className="size-5" style={{ color: verde.color }} aria-hidden />
          <span className="absolute -bottom-1.5 left-1/2 flex h-3.5 -translate-x-1/2 items-center rounded-[3px] bg-gray-800 px-[5px] text-[9px] font-semibold leading-none text-white">
            {ext}
          </span>
        </span>

        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-2">
            <span className="truncate text-[13.5px] font-semibold text-gray-900 dark:text-gray-50">
              {doc.original_filename}
            </span>
            {edited && (
              <span className="inline-flex h-[17px] items-center rounded-full bg-gray-100 px-[7px] text-[10px] font-semibold leading-none text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                ajustado
              </span>
            )}
            {processed ? (
              <span
                className="inline-flex h-[17px] items-center gap-1 rounded-full px-[7px] text-[10.5px] font-medium leading-none"
                style={{ background: verde.chipBg, color: verde.chipText }}
              >
                <RiCheckLine className="size-[11px]" aria-hidden />
                extração concluída
              </span>
            ) : status === "processing" ? (
              <span
                className="inline-flex h-[17px] items-center gap-1 rounded-full px-[7px] text-[10.5px] font-medium leading-none"
                style={{
                  background: provenanceTokens.agente.chipBg,
                  color: provenanceTokens.agente.chipText,
                }}
              >
                <RiLoader4Line className="size-[11px] animate-spin" aria-hidden />
                extraindo…
              </span>
            ) : status === "error" ? (
              <span
                className="inline-flex h-[17px] items-center rounded-full px-[7px] text-[10.5px] font-medium leading-none"
                style={{ background: "#FEFCE8", color: "#713F12" }}
              >
                extração falhou
              </span>
            ) : (
              <span className="inline-flex h-[17px] items-center gap-1 rounded-full bg-gray-100 px-[7px] text-[10.5px] font-medium leading-none text-gray-600 dark:bg-gray-800 dark:text-gray-400">
                <RiLoader4Line className="size-[11px] animate-spin" aria-hidden />
                extração na fila…
              </span>
            )}
          </p>
          <p className="mt-1 text-xs text-gray-500 tabular-nums dark:text-gray-400">
            {DOC_LABEL[doc.doc_type.toLowerCase()] ?? doc.doc_type}
            {doc.uploaded_at && <> · recebido em {fmtDateTime(doc.uploaded_at)}</>}
            {monthlyCount > 0 ? (
              <> · {monthlyCount} valores extraídos</>
            ) : fieldCount > 0 ? (
              <> · {fieldCount} campos extraídos</>
            ) : null}
            {doc.extraction_confidence != null && processed && (
              <> · confiança {Math.round(Number(doc.extraction_confidence) * 100)}%</>
            )}
          </p>
          {status === "error" && doc.extraction_error && (
            <p className="mt-1 text-[11.5px] text-gray-400">{doc.extraction_error}</p>
          )}
          {doc.ai_model_used && processed && (
            <p className="mt-1 text-[11.5px] text-gray-400 dark:text-gray-500">
              lida por {doc.ai_model_used}
              {doc.ai_prompt_version && <> · {doc.ai_prompt_version}</>} — registrado na
              trilha
            </p>
          )}
        </div>
      </div>

      <div className="flex shrink-0 flex-wrap items-center gap-2">
        <Button variant="secondary" className="h-8" onClick={openFile} isLoading={opening}>
          <RiEyeLine className="mr-1.5 size-4" aria-hidden />
          Abrir no leitor
        </Button>
        {canUpload && (
          <Button variant="ghost" className="h-8" onClick={onReplace}>
            <RiUpload2Line className="mr-1.5 size-4" aria-hidden />
            Substituir
          </Button>
        )}
        <Button variant="ghost" className="h-8" onClick={onReprocess} isLoading={reprocessing}>
          <RiRestartLine className="mr-1.5 size-4" aria-hidden />
          {processed ? "Reprocessar" : "Processar"}
        </Button>
      </div>
    </div>
  )
}

// ─── Painel "Origem do valor selecionado" ───────────────────────────────────

export function OriginPanel({
  dossierId,
  doc,
  selectedLabel,
}: {
  dossierId: string
  doc: CreditDocumentRead
  selectedLabel?: string | null
}) {
  const [url, setUrl] = React.useState<string | null>(null)
  const [failed, setFailed] = React.useState(false)

  React.useEffect(() => {
    let revoked = false
    let objectUrl: string | null = null
    credito.documents
      .fileObjectUrl(dossierId, doc.id)
      .then((u) => {
        if (revoked) {
          URL.revokeObjectURL(u)
          return
        }
        objectUrl = u
        setUrl(u)
      })
      .catch(() => setFailed(true))
    return () => {
      revoked = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [dossierId, doc.id])

  const isPdf = (doc.mime_type ?? "").includes("pdf")

  return (
    <div className="flex flex-col bg-gray-100 px-4 py-3.5 dark:bg-gray-900">
      <p className="text-[11px] font-medium text-gray-500 dark:text-gray-400">
        Origem do valor selecionado
        {selectedLabel && <> · {selectedLabel}</>}
      </p>
      <div className="mt-2.5 min-h-[260px] flex-1 overflow-hidden rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
        {url ? (
          isPdf ? (
            // O documento REAL ao lado da proposta — o par leitura ↔ proposta
            // nunca se separa. (Highlight por trecho exige bounding boxes da
            // extração — workstream de backend.)
            <iframe
              src={url}
              title={doc.original_filename}
              className="h-full min-h-[260px] w-full"
            />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={url} alt={doc.original_filename} className="h-full w-full object-contain" />
          )
        ) : (
          <div className="flex h-full min-h-[260px] items-center justify-center text-[12px] text-gray-400">
            {failed ? "Não foi possível carregar o documento." : "Carregando o documento…"}
          </div>
        )}
      </div>
      <p className="mt-2 text-[11px] text-gray-400 dark:text-gray-500">
        O documento acompanha a conferência — o par leitura ↔ proposta nunca se separa.
      </p>
    </div>
  )
}

// ─── Zona · Conferência de FICHA (campo a campo) ────────────────────────────

type FichaRowState = "ok" | "ajustado"

export function FichaConferenceZone({
  dossierId,
  doc,
  editable,
}: {
  dossierId: string
  doc: CreditDocumentRead
  editable: boolean
}) {
  const serverFields = extractedFieldsOf(doc)
  const aiOriginal = aiOriginalOf(doc)

  // Draft local com autosave (rascunho contínuo — salvar ≠ fechar).
  const [draft, setDraft] = React.useState<Fields | null>(null)
  const [draftDocId, setDraftDocId] = React.useState<string | null>(null)
  const dirtyRef = React.useRef(false)

  React.useEffect(() => {
    if (draftDocId !== doc.id || (!dirtyRef.current && serverFields)) {
      setDraft(serverFields ? structuredClone(serverFields) : null)
      setDraftDocId(doc.id)
      dirtyRef.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc.id, JSON.stringify(serverFields)])

  const patchMut = useMutation({
    mutationFn: (fields: Fields) =>
      credito.documents.updateExtraction(dossierId, doc.id, {
        extracted_fields: fields,
      }),
    onSuccess: () => {
      dirtyRef.current = false
    },
    onError: (e) => toast.error(`Erro ao salvar o ajuste: ${(e as Error).message}`),
  })

  const patchTimer = React.useRef<number | null>(null)
  const scheduleSave = React.useCallback(
    (fields: Fields) => {
      dirtyRef.current = true
      if (patchTimer.current) window.clearTimeout(patchTimer.current)
      patchTimer.current = window.setTimeout(() => patchMut.mutate(fields), 800)
    },
    [patchMut],
  )
  React.useEffect(
    () => () => {
      if (patchTimer.current) window.clearTimeout(patchTimer.current)
    },
    [],
  )

  const fields = draft ?? serverFields ?? {}

  const isScalar = (v: unknown) => v === null || typeof v !== "object"
  const scalarKeys = Array.from(
    new Set([
      ...Object.keys(fields).filter((k) => !k.startsWith("_") && k !== "monthly"),
      ...Object.keys(aiOriginal ?? {}).filter((k) => !k.startsWith("_") && k !== "monthly"),
    ]),
  ).filter((k) => isScalar(fields[k]) && isScalar((aiOriginal ?? {})[k]))

  const listKeys = Object.keys(fields).filter(
    (k) =>
      !k.startsWith("_") &&
      k !== "monthly" &&
      Array.isArray(fields[k]) &&
      (fields[k] as unknown[]).length > 0,
  )

  const rowState = (k: string): FichaRowState => {
    const ai = (aiOriginal ?? {})[k]
    if (ai !== undefined && JSON.stringify(ai) !== JSON.stringify(fields[k])) {
      return "ajustado"
    }
    return "ok"
  }

  const counts = {
    ok: scalarKeys.filter((k) => rowState(k) === "ok").length,
    ajustado: scalarKeys.filter((k) => rowState(k) === "ajustado").length,
  }

  const [selected, setSelected] = React.useState<string | null>(null)

  const setField = (k: string, raw: string) => {
    if (!draft) return
    const original = (aiOriginal ?? {})[k]
    let value: unknown = raw
    if (typeof original === "number") {
      const n = Number(raw.replace(/\./g, "").replace(",", "."))
      value = Number.isFinite(n) ? n : raw
    }
    if (raw.trim() === "") value = null
    const next = { ...draft, [k]: value }
    setDraft(next)
    scheduleSave(next)
  }

  if (scalarKeys.length === 0 && listKeys.length === 0) return null

  return (
    <section className="overflow-hidden rounded border border-gray-200 bg-white shadow-xs dark:border-gray-800 dark:bg-gray-950">
      <header className="flex flex-wrap items-center gap-3 border-b border-gray-100 px-5 py-3 dark:border-gray-900">
        <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
          Conferência da extração
        </span>
        <span className="text-xs tabular-nums">
          <strong className="font-semibold" style={{ color: "#059669" }}>
            {counts.ok} ok
          </strong>
          <span className="text-gray-300 dark:text-gray-700"> · </span>
          <strong className="font-semibold text-gray-700 dark:text-gray-300">
            {counts.ajustado} ajustado{counts.ajustado === 1 ? "" : "s"}
          </strong>
        </span>
        {patchMut.isPending && <span className="text-[11px] text-gray-400">salvando…</span>}
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px]">
        <div className="border-gray-100 px-5 py-3.5 lg:border-r dark:border-gray-900">
          <div className="grid grid-cols-[160px_1fr_1fr_88px] gap-3 border-b border-gray-200 pb-[7px] dark:border-gray-800">
            {["Campo", "IA propôs", "No dossiê", "Estado"].map((h, i) => (
              <span
                key={h}
                className={cx(
                  "text-[10px] font-semibold uppercase tracking-[0.05em] text-gray-400 dark:text-gray-500",
                  i === 3 && "text-right",
                )}
              >
                {h}
              </span>
            ))}
          </div>

          {scalarKeys.map((k) => (
            <FichaRow
              key={k}
              fieldKey={k}
              value={fields[k]}
              aiValue={(aiOriginal ?? {})[k]}
              state={rowState(k)}
              selected={selected === k}
              editable={editable}
              onSelect={() => setSelected(k)}
              onCommit={(raw) => setField(k, raw)}
            />
          ))}

          {/* Listas (sócios etc.) — leitura; edição de listas na conferência
              guiada (próxima fatia). */}
          {listKeys.map((k) => (
            <FichaListBlock key={k} fieldKey={k} rows={fields[k] as unknown[]} />
          ))}

          <p className="pt-2.5 text-[11px] italic text-gray-400 dark:text-gray-500">
            a coluna &quot;IA propôs&quot; nunca é editada — ajustes preservam o valor
            original na trilha
          </p>
        </div>

        <OriginPanel
          dossierId={dossierId}
          doc={doc}
          selectedLabel={selected ? humanizeKey(selected) : null}
        />
      </div>
    </section>
  )
}

function FichaRow({
  fieldKey,
  value,
  aiValue,
  state,
  selected,
  editable,
  onSelect,
  onCommit,
}: {
  fieldKey: string
  value: unknown
  aiValue: unknown
  state: FichaRowState
  selected: boolean
  editable: boolean
  onSelect: () => void
  onCommit: (raw: string) => void
}) {
  const [editing, setEditing] = React.useState(false)
  const [text, setText] = React.useState("")

  const beginEdit = () => {
    if (!editable) return
    setText(value === null || value === undefined ? "" : String(value))
    setEditing(true)
  }
  const commit = () => {
    setEditing(false)
    onCommit(text)
  }

  return (
    <div
      onClick={onSelect}
      className={cx(
        "grid cursor-pointer grid-cols-[160px_1fr_1fr_88px] items-center gap-3 border-b border-gray-100 py-[6.5px] text-[12.5px] dark:border-gray-900",
        state === "ajustado" && "-mx-5 bg-gray-50 px-5 dark:bg-gray-925",
        selected && state === "ok" && "-mx-5 bg-blue-500/5 px-5",
      )}
    >
      <span className="truncate text-gray-500 dark:text-gray-400">
        {humanizeKey(fieldKey)}
      </span>

      <span className="min-w-0 truncate font-medium text-gray-900 tabular-nums dark:text-gray-100">
        {state === "ajustado" ? (
          <span className="text-gray-400 line-through dark:text-gray-600">
            {displayValue(fieldKey, aiValue)}
          </span>
        ) : (
          displayValue(fieldKey, aiValue)
        )}
      </span>

      <span className="min-w-0 font-semibold text-gray-900 tabular-nums dark:text-gray-50">
        {editing ? (
          <input
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            onBlur={commit}
            onKeyDown={(e) => {
              if (e.key === "Enter") commit()
              if (e.key === "Escape") setEditing(false)
            }}
            onClick={(e) => e.stopPropagation()}
            className="w-full rounded border border-blue-500 bg-white px-2 py-[3px] text-[12.5px] font-semibold tabular-nums outline-none dark:bg-gray-950"
            style={{ boxShadow: "0 0 0 2px rgba(59,130,246,0.3)" }}
          />
        ) : (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onSelect()
              beginEdit()
            }}
            disabled={!editable}
            className={cx(
              "-mx-1 inline-flex max-w-full items-center gap-1.5 truncate rounded px-1 text-left",
              editable && "hover:bg-gray-100 dark:hover:bg-gray-900",
            )}
          >
            <span className="truncate">{displayValue(fieldKey, value)}</span>
            {state === "ajustado" && (
              <RiQuillPenLine
                className="size-3 shrink-0 text-gray-800 dark:text-gray-200"
                aria-hidden
              />
            )}
          </button>
        )}
      </span>

      <span className="flex items-center justify-end gap-1 text-right text-[11px] font-medium">
        {state === "ok" ? (
          <span className="inline-flex items-center gap-1" style={{ color: "#059669" }}>
            <RiCheckLine className="size-3" aria-hidden />
            ok
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-gray-700 dark:text-gray-300">
            <RiEditLine className="size-3" aria-hidden />
            ajustado
          </span>
        )}
      </span>
    </div>
  )
}

function FichaListBlock({ fieldKey, rows }: { fieldKey: string; rows: unknown[] }) {
  const objects = rows.filter(
    (r): r is Record<string, unknown> => typeof r === "object" && r !== null,
  )
  if (objects.length === 0) return null
  const columns = Array.from(
    objects.reduce<Set<string>>((acc, o) => {
      Object.keys(o).forEach((k) => acc.add(k))
      return acc
    }, new Set()),
  )
  return (
    <div className="py-3">
      <p className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.05em] text-gray-400 dark:text-gray-500">
        {humanizeKey(fieldKey)} · {objects.length}
      </p>
      <div className="overflow-hidden rounded-md border border-gray-200 dark:border-gray-800">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50/60 dark:border-gray-900 dark:bg-gray-900/40">
              {columns.map((c) => (
                <th
                  key={c}
                  className="px-3 py-1.5 text-left text-[10px] font-semibold uppercase tracking-[0.05em] text-gray-400 dark:text-gray-500"
                >
                  {humanizeKey(c)}
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
                  <td
                    key={c}
                    className="px-3 py-1 text-[12.5px] text-gray-700 tabular-nums dark:text-gray-300"
                  >
                    {displayValue(c, row[c])}
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
