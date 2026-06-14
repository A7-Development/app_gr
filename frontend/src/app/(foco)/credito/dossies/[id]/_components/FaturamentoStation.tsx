// FaturamentoStation — zonas da Estação Faturamento (handoff Conceito D,
// frame D1 — a tela-herói). Substitui o DocumentWorkspace genérico quando a
// estação fundida contém document_request + revenue_analyst:
//
//   Zona 1  Documento-fonte (thumbnail 44×56 + chip extração + ações)
//   Zona 2  Conferência da extração (IA propôs × No dossiê × Estado | painel
//           de origem 380px com o PRÓPRIO documento ao lado — o par
//           leitura ↔ proposta nunca se separa)
//   Zona 3  KpiChartCard (barra selecionada ↔ linha da tabela)
//   Zona 4  Leitura do agente (AgentConclusion indigo dashed; Homologar /
//           Editar observação / Recusar e reprocessar)
//
// A extração dispara SOZINHA ao receber o documento (upload → extract).
// Edição da coluna "No dossiê" persiste via PATCH /extraction com debounce —
// a coluna "IA propôs" (_ai_original) nunca é editada.

"use client"

import * as React from "react"
import { useMutation, useQueryClient } from "@tanstack/react-query"
import {
  RiCheckLine,
  RiCloseCircleLine,
  RiCursorLine,
  RiEditLine,
  RiInformationLine,
  RiQuillPenLine,
  RiSlideshow3Line,
} from "@remixicon/react"
import { toast } from "sonner"

import { Button } from "@/components/tremor/Button"
import { Textarea } from "@/components/tremor/Textarea"
import {
  AgentConclusion,
  AgentLiveStatus,
  AgentOutputRenderer,
  KpiChartCard,
  type KpiChartDatum,
} from "@/design-system/components"
import { credito, type CreditDocumentRead, type RevenueAnalysis } from "@/lib/credito-client"
import {
  DocumentSourceZone,
  OriginPanel,
  aiOriginalOf,
  extractedFieldsOf,
  getMonthly,
  type Fields,
  type MonthRow,
} from "./DocumentZones"
import { cx } from "@/lib/utils"

// ─── Tipos ──────────────────────────────────────────────────────────────────

export type FaturamentoPhase =
  | "documento" // document_request aguardando — analista envia/confere
  | "fila" // documento fechado, agente ainda não rodou
  | "rodando" // agente em execução
  | "homologar" // conclusão pronta, gate aguardando
  | "fechada" // estação fechada

export type FaturamentoStationProps = {
  dossierId: string
  docs: CreditDocumentRead[]
  requiredDocTypes: string[]
  phase: FaturamentoPhase
  /** Output do analista fundido (quando já concluiu). Pode ser revenue_analyst
   *  (schema rico) OU outro analista fiado ao documento (render genérico). */
  agentOutput: Record<string, unknown> | null
  /** Nome do agente fundido — decide o renderer da leitura (revenue vs genérico). */
  agentName?: string | null
  /** Live status do agente (fase rodando). */
  agentLabel?: string
  runStartedAt?: string | null
  toolsLog?: Array<{
    iso_at: string
    kind: "tool_use" | "tool_result"
    tool_name?: string
    duration_ms?: number
  }>
  tokensInput?: number
  tokensOutput?: number
  costBrl?: number
  onApproveGate: (notes: string) => void
  approving: boolean
  onRerunAgent?: () => void
  rerunning?: boolean
}

// ─── Componente principal ───────────────────────────────────────────────────

export function FaturamentoStation(props: FaturamentoStationProps) {
  const { dossierId, phase } = props
  // Só os documentos DESTA estação — docs de outras (contrato social etc.)
  // não vazam pra cá.
  const docs = React.useMemo(() => {
    if (!props.requiredDocTypes.length) return props.docs
    const allowed = new Set(props.requiredDocTypes.map((t) => t.toLowerCase()))
    return props.docs.filter((d) => allowed.has(d.doc_type.toLowerCase()))
  }, [props.docs, props.requiredDocTypes])
  const qc = useQueryClient()
  const queryKey = ["credito", "documents", dossierId]
  const invalidate = React.useCallback(
    () => qc.invalidateQueries({ queryKey }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [qc, dossierId],
  )

  // Documento primário da conferência: o que tem série mensal extraída.
  const primaryDoc = React.useMemo(() => {
    const processed = docs.filter(
      (d) => d.extraction_status === "success" || d.extraction_status === "validated",
    )
    return (
      processed.find((d) => getMonthly(extractedFieldsOf(d)) !== null) ??
      processed[0] ??
      docs[0] ??
      null
    )
  }, [docs])

  // ── Draft da conferência (coluna "No dossiê") ────────────────────────────
  const serverFields = primaryDoc ? extractedFieldsOf(primaryDoc) : null
  const [draft, setDraft] = React.useState<Fields | null>(null)
  const [draftDocId, setDraftDocId] = React.useState<string | null>(null)
  const dirtyRef = React.useRef(false)

  // Sincroniza o draft com o servidor quando o doc muda ou não há edição local.
  React.useEffect(() => {
    if (!primaryDoc) return
    if (draftDocId !== primaryDoc.id || (!dirtyRef.current && serverFields)) {
      setDraft(serverFields ? structuredClone(serverFields) : null)
      setDraftDocId(primaryDoc.id)
      dirtyRef.current = false
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [primaryDoc?.id, JSON.stringify(serverFields)])

  const patchMut = useMutation({
    mutationFn: (fields: Fields) =>
      credito.documents.updateExtraction(dossierId, primaryDoc!.id, {
        extracted_fields: fields,
      }),
    onSuccess: () => {
      dirtyRef.current = false
      invalidate()
    },
    onError: (e) => toast.error(`Erro ao salvar o ajuste: ${(e as Error).message}`),
  })

  // Persistência com debounce (rascunho contínuo — salvar ≠ fechar).
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

  const monthly = draft ? getMonthly(draft) : null
  const aiOriginal = primaryDoc ? aiOriginalOf(primaryDoc) : null
  const aiMonthly = aiOriginal ? getMonthly(aiOriginal) : null

  const editable = phase === "documento" || phase === "homologar"

  const setMonthValue = (index: number, value: number) => {
    if (!draft || !monthly) return
    const rows = monthly.map((r, i) => (i === index ? { ...r, value } : r))
    const next: Fields = { ...draft, monthly: rows }
    if ("revenue" in next) next.revenue = round2(sumRows(rows))
    setDraft(next)
    scheduleSave(next)
  }

  // ── Seleção (linha da tabela ↔ barra do chart ↔ painel de origem) ────────
  const [selected, setSelected] = React.useState<number | null>(null)
  const [confirmed, setConfirmed] = React.useState<Set<string>>(new Set())

  // Estados por linha (ok / ajustado / pendente).
  const rowStates: RowState[] = React.useMemo(() => {
    if (!monthly) return []
    const values = monthly.map((r) => r.value)
    const avg = values.length ? values.reduce((a, b) => a + b, 0) / values.length : 0
    return monthly.map((r, i) => {
      const ai = aiMonthly?.[i]
      if (ai && Math.abs(ai.value - r.value) > 0.004) return "ajustado"
      const suspicious = r.value <= 0 || (avg > 0 && (r.value > avg * 2.5 || r.value < avg * 0.4))
      if (suspicious && !confirmed.has(r.month) && editable) return "pendente"
      return "ok"
    })
  }, [monthly, aiMonthly, confirmed, editable])

  const counts = {
    ok: rowStates.filter((s) => s === "ok").length,
    ajustado: rowStates.filter((s) => s === "ajustado").length,
    pendente: rowStates.filter((s) => s === "pendente").length,
  }

  return (
    <>
      <DocumentSourceZone
        dossierId={dossierId}
        docs={docs}
        requiredDocTypes={props.requiredDocTypes}
        canUpload={phase === "documento"}
        onChanged={invalidate}
      />

      {monthly && monthly.length > 0 && primaryDoc && (
        <>
          <ConferenceZone
            dossierId={dossierId}
            doc={primaryDoc}
            rows={monthly}
            aiRows={aiMonthly}
            rowStates={rowStates}
            counts={counts}
            selected={selected}
            onSelect={setSelected}
            editable={editable}
            onChangeValue={setMonthValue}
            onConfirm={(month) =>
              setConfirmed((prev) => new Set(prev).add(month))
            }
            saving={patchMut.isPending}
          />
          <FaturamentoChart rows={monthly} selected={selected} onSelect={setSelected} />
        </>
      )}

      <AgentReadingZone {...props} />
    </>
  )
}

type RowState = "ok" | "ajustado" | "pendente"

// ─── Zona 2 · Conferência da extração ───────────────────────────────────────

function ConferenceZone({
  dossierId,
  doc,
  rows,
  aiRows,
  rowStates,
  counts,
  selected,
  onSelect,
  editable,
  onChangeValue,
  onConfirm,
  saving,
}: {
  dossierId: string
  doc: CreditDocumentRead
  rows: MonthRow[]
  aiRows: MonthRow[] | null
  rowStates: RowState[]
  counts: { ok: number; ajustado: number; pendente: number }
  selected: number | null
  onSelect: (i: number) => void
  editable: boolean
  onChangeValue: (i: number, value: number) => void
  onConfirm: (month: string) => void
  saving: boolean
}) {
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
          <span className="text-gray-300 dark:text-gray-700"> · </span>
          <strong className="font-semibold text-amber-600">
            {counts.pendente} pendente{counts.pendente === 1 ? "" : "s"}
          </strong>
        </span>
        {saving && (
          <span className="text-[11px] text-gray-400">salvando…</span>
        )}
        <Button variant="secondary" className="ml-auto h-[30px]" disabled title="Em breve">
          <RiSlideshow3Line className="mr-1.5 size-4" aria-hidden />
          Conferência guiada
        </Button>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px]">
        {/* Tabela */}
        <div className="border-gray-100 px-5 py-3.5 lg:border-r dark:border-gray-900">
          <div className="grid grid-cols-[64px_1fr_1fr_96px] gap-3 border-b border-gray-200 pb-[7px] dark:border-gray-800">
            {["Mês", "IA propôs", "No dossiê", "Estado"].map((h, i) => (
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

          {rows.map((r, i) => {
            const st = rowStates[i]
            const ai = aiRows?.[i]
            const isSelected = selected === i
            return (
              <ConferenceRow
                key={`${r.month}-${i}`}
                row={r}
                ai={ai ?? null}
                state={st}
                selected={isSelected}
                editable={editable}
                onSelect={() => onSelect(i)}
                onChangeValue={(v) => onChangeValue(i, v)}
                onConfirm={() => onConfirm(r.month)}
              />
            )
          })}

          <p className="pt-2.5 text-[11px] italic text-gray-400 dark:text-gray-500">
            a coluna &quot;IA propôs&quot; nunca é editada — ajustes preservam o valor
            original na trilha
          </p>
        </div>

        {/* Painel de origem */}
        <OriginPanel
          dossierId={dossierId}
          doc={doc}
          selectedLabel={selected != null && rows[selected] ? fmtMonth(rows[selected].month) : null}
        />
      </div>
    </section>
  )
}

function ConferenceRow({
  row,
  ai,
  state,
  selected,
  editable,
  onSelect,
  onChangeValue,
  onConfirm,
}: {
  row: MonthRow
  ai: MonthRow | null
  state: RowState
  selected: boolean
  editable: boolean
  onSelect: () => void
  onChangeValue: (v: number) => void
  onConfirm: () => void
}) {
  const [editing, setEditing] = React.useState(false)
  const [text, setText] = React.useState("")

  const beginEdit = () => {
    if (!editable) return
    setText(String(row.value).replace(".", ","))
    setEditing(true)
  }
  const commit = () => {
    setEditing(false)
    const v = Number(text.replace(/\./g, "").replace(",", "."))
    if (Number.isFinite(v) && Math.abs(v - row.value) > 0.004) onChangeValue(v)
  }

  const fullBleed = state !== "ok"
  return (
    <div
      onClick={onSelect}
      className={cx(
        "grid cursor-pointer grid-cols-[64px_1fr_1fr_96px] items-center gap-3 border-b border-gray-100 py-[6.5px] text-[12.5px] dark:border-gray-900",
        fullBleed && "-mx-5 bg-gray-50 px-5 dark:bg-gray-925",
        selected && !fullBleed && "-mx-5 bg-blue-500/5 px-5",
      )}
      style={state === "pendente" ? { boxShadow: "inset 2px 0 0 #D97706" } : undefined}
    >
      <span className="text-gray-500 dark:text-gray-400">{fmtMonth(row.month)}</span>

      {/* IA propôs — nunca editável */}
      <span className="font-medium text-gray-900 tabular-nums dark:text-gray-100">
        {ai ? (
          state === "ajustado" ? (
            <span className="text-gray-400 line-through dark:text-gray-600">
              {fmtBRL(ai.value)}
            </span>
          ) : (
            <>
              {fmtBRL(ai.value)}
              {state === "pendente" && (
                <span
                  className="ml-1.5 inline-flex h-4 items-center rounded-full px-[5px] text-[9.5px] font-medium leading-none"
                  style={{ background: "#FEFCE8", color: "#713F12" }}
                  title="Confiança baixa nesta leitura — confira no documento ao lado."
                >
                  confira
                </span>
              )}
            </>
          )
        ) : (
          <span className="text-gray-400">—</span>
        )}
      </span>

      {/* No dossiê — editável */}
      <span className="font-semibold text-gray-900 tabular-nums dark:text-gray-50">
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
            className="w-full max-w-[140px] rounded border border-blue-500 bg-white px-2 py-[3px] text-[12.5px] font-semibold tabular-nums outline-none dark:bg-gray-950"
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
            className={cx(
              "inline-flex items-center gap-1.5 rounded px-1 -mx-1 text-left",
              editable && "hover:bg-gray-100 dark:hover:bg-gray-900",
            )}
            disabled={!editable}
          >
            {fmtBRL(row.value)}
            {state === "ajustado" && (
              <RiQuillPenLine className="size-3 text-gray-800 dark:text-gray-200" aria-hidden />
            )}
          </button>
        )}
      </span>

      {/* Estado */}
      <span className="flex items-center justify-end gap-1 text-right text-[11px] font-medium">
        {state === "ok" && (
          <span className="inline-flex items-center gap-1" style={{ color: "#059669" }}>
            <RiCheckLine className="size-3" aria-hidden />
            ok
          </span>
        )}
        {state === "ajustado" && (
          <span className="inline-flex items-center gap-1 text-gray-700 dark:text-gray-300">
            <RiEditLine className="size-3" aria-hidden />
            ajustado
          </span>
        )}
        {state === "pendente" && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation()
              onConfirm()
            }}
            className="inline-flex items-center gap-1 text-amber-600 hover:text-amber-700"
            title="Confirmar este valor como está"
          >
            <RiCursorLine className="size-3" aria-hidden />
            confira →
          </button>
        )}
      </span>
    </div>
  )
}

// ─── Zona 3 · Gráfico ───────────────────────────────────────────────────────

function FaturamentoChart({
  rows,
  selected,
  onSelect,
}: {
  rows: MonthRow[]
  selected: number | null
  onSelect: (i: number) => void
}) {
  const sum = sumRows(rows)
  const avg = rows.length ? sum / rows.length : 0

  // Delta: 2ª metade vs 1ª metade da série (tendência simples).
  let delta: string | undefined
  let deltaTone: "pos" | "neg" = "pos"
  if (rows.length >= 6) {
    const half = Math.floor(rows.length / 2)
    const a = rows.slice(0, half).reduce((s, r) => s + r.value, 0) / half
    const b = rows.slice(-half).reduce((s, r) => s + r.value, 0) / half
    if (a > 0) {
      const pct = (b / a - 1) * 100
      deltaTone = pct >= 0 ? "pos" : "neg"
      delta = `${pct >= 0 ? "↑" : "↓"} ${Math.abs(pct).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`
    }
  }

  const maxVal = Math.max(...rows.map((r) => r.value), 0)
  const data: KpiChartDatum[] = rows.map((r, i) => ({
    label: fmtMonth(r.month),
    value: r.value,
    valueLabel: compactNumber(r.value),
    selected: selected === i,
  }))

  return (
    <KpiChartCard
      eyebrow={`Faturamento mensal · últimos ${rows.length} meses`}
      value={fmtBRLCompact(avg)}
      delta={delta}
      deltaTone={deltaTone}
      deltaSuffix={delta ? "2ª metade vs 1ª" : undefined}
      context={`média mensal · total ${fmtBRLCompact(sum)} · fonte: documento conferido`}
      data={data}
      yMax={maxVal * 1.15 || 1}
      height={280}
      onBarClick={onSelect}
    />
  )
}

// ─── Zona 4 · Leitura do agente ─────────────────────────────────────────────

function AgentReadingZone(props: FaturamentoStationProps) {
  const { phase, agentOutput } = props
  const [editingNotes, setEditingNotes] = React.useState(false)
  const [notes, setNotes] = React.useState("")

  if (phase === "documento" || phase === "fila") {
    return (
      <div
        className="flex items-center gap-2.5 rounded px-5 py-3.5 opacity-75"
        style={{ border: "1.5px dashed #E5E7EB" }}
      >
        <RiInformationLine className="size-4 shrink-0 text-gray-400" aria-hidden />
        <p className="text-[12.5px] text-gray-500 dark:text-gray-400">
          <strong className="font-semibold text-gray-700 dark:text-gray-300">
            Leitura do agente de faturamento
          </strong>{" "}
          —{" "}
          {phase === "documento"
            ? "acorda quando os documentos conferidos forem enviados para análise."
            : "na fila — roda assim que a orquestração chegar aqui."}
        </p>
      </div>
    )
  }

  if (phase === "rodando") {
    return (
      <section className="rounded border border-gray-200 bg-white p-5 shadow-xs dark:border-gray-800 dark:bg-gray-950">
        <AgentLiveStatus
          agentLabel={props.agentLabel ?? "revenue_analyst"}
          startedAt={props.runStartedAt ?? null}
          toolsLog={props.toolsLog}
          tokensInput={props.tokensInput}
          tokensOutput={props.tokensOutput}
          costBrl={props.costBrl ?? 0}
        />
      </section>
    )
  }

  if (!agentOutput) return null

  const homologado = phase === "fechada"

  // Decoupling (Fatia 2a): a conferência + o gráfico acima vêm do DOCUMENTO e
  // aparecem para qualquer analista. A LEITURA, porém, depende do schema do
  // agente — só o revenue_analyst tem a leitura rica abaixo; outros analistas
  // fiados ao documento (ex.: financial_analyst) renderizam pelo renderer
  // genérico, na mesma moldura índigo (proveniência = agente).
  const isRevenueShape =
    "resumo_executivo" in agentOutput && "tendencia" in agentOutput
  if (!isRevenueShape) {
    return (
      <AgentConclusion
        homologado={homologado}
        eyebrow={`Leitura do agente${props.agentName ? ` · ${props.agentName}` : ""}`}
        meta={
          homologado
            ? "homologada — registrada na trilha"
            : "gerada após a extração"
        }
        tag="julgamento"
      >
        <AgentOutputRenderer agentName={props.agentName} output={agentOutput} />
      </AgentConclusion>
    )
  }

  const rev = agentOutput as unknown as RevenueAnalysis

  return (
    <AgentConclusion
      homologado={homologado}
      eyebrow="Leitura do agente de faturamento"
      meta={
        homologado
          ? "homologada — registrada na trilha"
          : "gerada após a extração · será revisada se você ajustar valores"
      }
      tag="julgamento · editável"
      footnote={
        homologado ? undefined : (
          <>
            <RiInformationLine className="mt-px size-3.5 shrink-0" aria-hidden />
            <span>
              Homologar registra: conclusão da IA + sua observação + data/hora — tudo entra
              na trilha.
            </span>
          </>
        )
      }
      actions={
        homologado ? undefined : (
          <>
            <Button
              className="h-8"
              onClick={() => props.onApproveGate(notes)}
              isLoading={props.approving}
            >
              <RiCheckLine className="mr-1.5 size-4" aria-hidden />
              Homologar leitura
            </Button>
            <Button
              variant="secondary"
              className="h-8"
              onClick={() => setEditingNotes((v) => !v)}
            >
              <RiEditLine className="mr-1.5 size-4" aria-hidden />
              {editingNotes ? "Fechar observação" : "Editar"}
            </Button>
            {props.onRerunAgent && (
              <Button
                variant="ghost"
                className="h-8"
                isLoading={props.rerunning}
                onClick={() => {
                  if (
                    window.confirm(
                      "Recusar e reprocessar refaz a leitura do agente. A versão atual fica preservada na trilha. Continuar?",
                    )
                  ) {
                    props.onRerunAgent?.()
                  }
                }}
              >
                <RiCloseCircleLine className="mr-1.5 size-4" aria-hidden />
                Recusar e reprocessar
              </Button>
            )}
            <span className="ml-auto hidden text-[11.5px] text-gray-400 lg:block">
              sua observação entra no registro da homologação
            </span>
          </>
        )
      }
    >
      <div className="space-y-3">
        <p>{rev.resumo_executivo}</p>

        <div className="flex flex-wrap gap-x-6 gap-y-1.5 text-[12px]">
          <span>
            <span className="text-gray-400">tendência: </span>
            <strong className="font-semibold text-gray-800 dark:text-gray-200">
              {rev.tendencia.direcao} · {rev.tendencia.intensidade}
            </strong>
          </span>
          <span>
            <span className="text-gray-400">credibilidade do documento: </span>
            <strong className="font-semibold text-gray-800 dark:text-gray-200">
              {rev.credibilidade_documento.nivel}
            </strong>
          </span>
          <span>
            <span className="text-gray-400">qualidade do dado: </span>
            <strong className="font-semibold text-gray-800 dark:text-gray-200">
              {rev.qualidade_do_dado.n_meses} meses
              {rev.qualidade_do_dado.soma_confere ? " · soma confere" : " · soma diverge"}
            </strong>
          </span>
        </div>

        {rev.pontos_de_atencao.length > 0 && (
          <ul className="space-y-1 text-[12.5px]">
            {rev.pontos_de_atencao.map((p, i) => (
              <li key={i} className="flex items-start gap-1.5">
                <span
                  className={cx(
                    "mt-1.5 size-1.5 shrink-0 rounded-full",
                    p.severidade === "alta"
                      ? "bg-amber-500"
                      : p.severidade === "media" || p.severidade === "média"
                        ? "bg-amber-400"
                        : "bg-gray-300 dark:bg-gray-700",
                  )}
                  aria-hidden
                />
                <span>
                  {p.mes && <strong className="font-semibold">{fmtMonth(p.mes)}: </strong>}
                  {p.observacao}
                </span>
              </li>
            ))}
          </ul>
        )}

        <p>
          <span className="text-gray-400">Leitura para crédito: </span>
          <strong className="font-semibold text-gray-900 dark:text-gray-50">
            {rev.leitura_para_credito}
          </strong>
        </p>

        {editingNotes && (
          <div onClick={(e) => e.stopPropagation()}>
            <p className="mb-1.5 text-xs font-medium text-gray-700 dark:text-gray-300">
              Observação do analista (entra na homologação)
            </p>
            <Textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder="Ajustes, ressalvas ou concordância com a leitura…"
            />
          </div>
        )}
      </div>
    </AgentConclusion>
  )
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function sumRows(rows: MonthRow[]): number {
  return round2(rows.reduce((acc, r) => acc + (Number(r.value) || 0), 0))
}

function round2(n: number): number {
  return Math.round(n * 100) / 100
}

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })

function fmtBRL(n: number): string {
  if (!Number.isFinite(n)) return "—"
  return brl.format(n)
}

function fmtBRLCompact(v: number): string {
  const fmt = (n: number) =>
    n.toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: 2 })
  if (Math.abs(v) >= 1_000_000_000) return `R$ ${fmt(v / 1_000_000_000)} bi`
  if (Math.abs(v) >= 1_000_000) return `R$ ${fmt(v / 1_000_000)} mi`
  if (Math.abs(v) >= 1_000) return `R$ ${fmt(v / 1_000)} mil`
  return brl.format(v)
}

function compactNumber(v: number): string {
  if (Math.abs(v) >= 1_000_000)
    return (v / 1_000_000).toLocaleString("pt-BR", { maximumFractionDigits: 2 })
  if (Math.abs(v) >= 1_000)
    return `${(v / 1_000).toLocaleString("pt-BR", { maximumFractionDigits: 0 })}k`
  return v.toLocaleString("pt-BR", { maximumFractionDigits: 0 })
}

function fmtMonth(s: string): string {
  const m = /^(\d{4})-(\d{2})$/.exec(s)
  if (!m) return s
  const months = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
  const idx = Number(m[2]) - 1
  return months[idx] ? `${months[idx]}/${m[1].slice(2)}` : s
}

