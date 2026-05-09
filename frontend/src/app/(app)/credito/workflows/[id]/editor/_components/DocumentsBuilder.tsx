// src/app/(app)/credito/workflows/[id]/editor/_components/DocumentsBuilder.tsx
//
// Builder VISUAL para `config.required` e `config.optional` da etapa
// "Pedir documentos" (document_request). Substitui os arrays JSON em
// textarea por checkboxes.
//
// Cada doc_type vira uma linha clicavel com 3 estados:
//   ☐ Nao pedir
//   ⊙ Opcional
//   ☑ Obrigatorio
// Pre-set "A7 padrao" marca os 4 obrigatorios mais comuns.

"use client"

import * as React from "react"
import {
  RiCheckLine,
  RiCircleLine,
  RiCloseLine,
} from "@remixicon/react"

import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

// ─── Catalogo de doc_types ──────────────────────────────────────────────
//
// Espelha `DocumentType` em `lib/credito-client.ts`. Quando um novo tipo
// for adicionado no backend, adicione aqui.

const DOC_CATALOG: Array<{ value: string; label: string; hint: string }> = [
  { value: "dre",                label: "DRE",                hint: "Demonstracao de resultado dos ultimos 24 meses" },
  { value: "balance_sheet",      label: "Balanco patrimonial",hint: "Balanco dos ultimos 24 meses" },
  { value: "revenue_report",     label: "Faturamento",        hint: "Relatorio de faturamento mensal" },
  { value: "indebtedness",       label: "Endividamento",      hint: "Relacao de dividas e bancos" },
  { value: "scr",                label: "SCR Bacen",          hint: "Extrato do Sistema de Informacoes de Credito" },
  { value: "social_contract",    label: "Contrato social",    hint: "Inclui alteracoes contratuais" },
  { value: "income_tax_pf",      label: "IRPF dos socios",    hint: "Imposto de renda pessoa fisica" },
  { value: "rg",                 label: "RG / CNH dos socios",hint: "Documento de identidade" },
  { value: "cnh",                label: "CNH dos socios",     hint: "Carteira de habilitacao" },
  { value: "commercial_visit",   label: "Visita comercial",   hint: "Relatorio de visita Onboard" },
  { value: "photo",              label: "Fotos",              hint: "Fotos das instalacoes" },
  { value: "abc_curve",          label: "Curva ABC",          hint: "Concentracao de clientes/fornecedores" },
  { value: "other",              label: "Outros",             hint: "Documentos diversos" },
]

const DEFAULT_PRESET_REQUIRED = ["dre", "balance_sheet", "revenue_report", "social_contract"]

// ─── Component ──────────────────────────────────────────────────────────

type DocStatus = "off" | "optional" | "required"

export type DocumentsBuilderProps = {
  required: string[]
  optional: string[]
  onChange: (next: { required: string[]; optional: string[] }) => void
}

export function DocumentsBuilder({
  required,
  optional,
  onChange,
}: DocumentsBuilderProps) {
  const requiredSet = React.useMemo(() => new Set(required), [required])
  const optionalSet = React.useMemo(() => new Set(optional), [optional])

  function statusOf(docValue: string): DocStatus {
    if (requiredSet.has(docValue)) return "required"
    if (optionalSet.has(docValue)) return "optional"
    return "off"
  }

  function setStatus(docValue: string, status: DocStatus) {
    const nextRequired = required.filter((v) => v !== docValue)
    const nextOptional = optional.filter((v) => v !== docValue)
    if (status === "required") nextRequired.push(docValue)
    if (status === "optional") nextOptional.push(docValue)
    onChange({ required: nextRequired, optional: nextOptional })
  }

  function applyA7Preset() {
    const nextRequired = Array.from(new Set([...required, ...DEFAULT_PRESET_REQUIRED]))
    const nextOptional = optional.filter((v) => !nextRequired.includes(v))
    onChange({ required: nextRequired, optional: nextOptional })
  }

  function clearAll() {
    onChange({ required: [], optional: [] })
  }

  const totalSelected = requiredSet.size + optionalSet.size

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className={tableTokens.header}>Documentos a solicitar</p>
        <span className={tableTokens.cellSecondary}>
          {totalSelected} de {DOC_CATALOG.length}
        </span>
      </div>

      <div className="rounded-md border border-blue-200 bg-blue-50 p-2.5 text-xs dark:border-blue-500/30 dark:bg-blue-500/10">
        <p className="font-medium text-blue-900 dark:text-blue-200">
          Conjuntos rapidos
        </p>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={applyA7Preset}
            className="rounded-md border border-blue-300 bg-white px-2 py-1 text-[11px] font-medium text-blue-800 transition hover:border-blue-500 hover:bg-blue-100 dark:border-blue-500/40 dark:bg-blue-500/10 dark:text-blue-200 dark:hover:bg-blue-500/20"
            title="DRE + Balanco + Faturamento + Contrato Social como obrigatorios"
          >
            + A7 padrao
          </button>
          {totalSelected > 0 && (
            <button
              type="button"
              onClick={clearAll}
              className="rounded-md border border-gray-300 bg-white px-2 py-1 text-[11px] font-medium text-gray-700 transition hover:border-gray-500 dark:border-gray-700 dark:bg-gray-900 dark:text-gray-300"
            >
              Limpar todos
            </button>
          )}
        </div>
      </div>

      <ul className="space-y-1">
        {DOC_CATALOG.map((doc) => (
          <DocRow
            key={doc.value}
            label={doc.label}
            hint={doc.hint}
            status={statusOf(doc.value)}
            onChange={(s) => setStatus(doc.value, s)}
          />
        ))}
      </ul>

      <p className={tableTokens.cellSecondary}>
        <span className="font-medium">Obrigatorio</span> bloqueia o avanco do fluxo.{" "}
        <span className="font-medium">Opcional</span> pode ser pulado.
      </p>
    </div>
  )
}

// ─── Single doc row ─────────────────────────────────────────────────────

function DocRow({
  label,
  hint,
  status,
  onChange,
}: {
  label: string
  hint: string
  status: DocStatus
  onChange: (next: DocStatus) => void
}) {
  return (
    <li
      className={cx(
        "flex items-center justify-between gap-2 rounded-md border px-2.5 py-1.5 transition",
        status === "required"
          ? "border-blue-300 bg-blue-50/40 dark:border-blue-500/30 dark:bg-blue-500/5"
          : status === "optional"
            ? "border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950"
            : "border-gray-100 bg-gray-50 dark:border-gray-900 dark:bg-gray-900",
      )}
    >
      <div className="min-w-0 flex-1">
        <p
          className={cx(
            "text-xs font-medium",
            status === "off"
              ? "text-gray-500 dark:text-gray-500"
              : "text-gray-900 dark:text-gray-100",
          )}
        >
          {label}
        </p>
        <p className={cx(tableTokens.cellSecondary, "line-clamp-1")}>{hint}</p>
      </div>
      <div className="flex shrink-0 items-center gap-0.5 rounded-md border border-gray-200 bg-white p-0.5 dark:border-gray-800 dark:bg-gray-950">
        <StatusButton
          active={status === "off"}
          onClick={() => onChange("off")}
          ariaLabel="Nao pedir"
          tone="off"
        >
          <RiCloseLine className="size-3" aria-hidden />
        </StatusButton>
        <StatusButton
          active={status === "optional"}
          onClick={() => onChange("optional")}
          ariaLabel="Opcional"
          tone="optional"
        >
          <RiCircleLine className="size-3" aria-hidden />
        </StatusButton>
        <StatusButton
          active={status === "required"}
          onClick={() => onChange("required")}
          ariaLabel="Obrigatorio"
          tone="required"
        >
          <RiCheckLine className="size-3" aria-hidden />
        </StatusButton>
      </div>
    </li>
  )
}

function StatusButton({
  active,
  tone,
  ariaLabel,
  onClick,
  children,
}: {
  active: boolean
  tone: "off" | "optional" | "required"
  ariaLabel: string
  onClick: () => void
  children: React.ReactNode
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={ariaLabel}
      title={ariaLabel}
      className={cx(
        "flex size-6 items-center justify-center rounded transition",
        active
          ? tone === "required"
            ? "bg-blue-600 text-white shadow-sm"
            : tone === "optional"
              ? "bg-gray-700 text-white shadow-sm dark:bg-gray-200 dark:text-gray-900"
              : "bg-gray-200 text-gray-700 dark:bg-gray-800 dark:text-gray-300"
          : "text-gray-400 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-500 dark:hover:bg-gray-800 dark:hover:text-gray-200",
      )}
    >
      {children}
    </button>
  )
}

export { DOC_CATALOG }
