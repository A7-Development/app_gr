// RawDataFields — renderer GENÉRICO de um objeto JSON (qualquer dataset).
//
// Princípio (governança 2026-06-06): o dev NÃO escolhe quais campos mostrar.
// Este componente exibe TODOS os campos de um payload (primitivos, objetos
// aninhados, arrays) de forma segura — nunca renderiza objeto/array como filho
// React (evita o crash #31). Rótulos sao a chave "prettificada" (neutro); a
// curadoria de rótulo/ordem/visibilidade vem depois, via catálogo do usuário.

"use client"

import * as React from "react"

import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

const _MAX_DEPTH = 6

/** "TaxIdStatus" -> "Tax Id Status"; "founding_date" -> "Founding Date". Neutro. */
function prettyKey(key: string): string {
  const spaced = key
    .replace(/_/g, " ")
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/([A-Z]+)([A-Z][a-z])/g, "$1 $2")
    .trim()
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

function isEmpty(v: unknown): boolean {
  return (
    v === null ||
    v === undefined ||
    (typeof v === "string" && v.trim() === "") ||
    (Array.isArray(v) && v.length === 0) ||
    (typeof v === "object" && !Array.isArray(v) && Object.keys(v as object).length === 0)
  )
}

function scalarText(v: unknown): string {
  if (typeof v === "boolean") return v ? "Sim" : "Não"
  return String(v)
}

function isScalar(v: unknown): boolean {
  return v === null || ["string", "number", "boolean"].includes(typeof v)
}

export function RawDataFields({
  data,
  depth = 0,
}: {
  data: Record<string, unknown>
  depth?: number
}) {
  const entries = Object.entries(data)
  if (entries.length === 0) {
    return <p className={tableTokens.cellSecondary}>—</p>
  }
  return (
    <dl className="space-y-1.5">
      {entries.map(([key, value]) => (
        <FieldRow key={key} label={prettyKey(key)} value={value} depth={depth} />
      ))}
    </dl>
  )
}

function FieldRow({
  label,
  value,
  depth,
}: {
  label: string
  value: unknown
  depth: number
}) {
  // Vazio.
  if (isEmpty(value)) {
    return <ScalarRow label={label} text="—" />
  }
  // Escalar.
  if (isScalar(value)) {
    return <ScalarRow label={label} text={scalarText(value)} />
  }
  // Profundidade máxima — fallback seguro (nunca objeto cru como filho).
  if (depth >= _MAX_DEPTH) {
    return <ScalarRow label={label} text={JSON.stringify(value)} />
  }
  // Array.
  if (Array.isArray(value)) {
    const allScalar = value.every(isScalar)
    if (allScalar) {
      return <ScalarRow label={label} text={value.map(scalarText).join(", ")} />
    }
    return (
      <Section label={`${label} (${value.length})`}>
        <div className="space-y-1.5">
          {value.map((item, i) => (
            <div
              key={i}
              className="rounded-md border border-gray-100 bg-gray-50/40 p-2 dark:border-gray-900 dark:bg-gray-950/30"
            >
              {isScalar(item) ? (
                <span className={tableTokens.cellText}>{scalarText(item)}</span>
              ) : (
                <RawDataFields
                  data={item as Record<string, unknown>}
                  depth={depth + 1}
                />
              )}
            </div>
          ))}
        </div>
      </Section>
    )
  }
  // Objeto aninhado.
  return (
    <Section label={label}>
      <div className="border-l border-gray-200 pl-2.5 dark:border-gray-800">
        <RawDataFields data={value as Record<string, unknown>} depth={depth + 1} />
      </div>
    </Section>
  )
}

function ScalarRow({ label, text }: { label: string; text: string }) {
  return (
    <div className="flex flex-col gap-0.5 sm:flex-row sm:items-baseline sm:gap-2">
      <dt className={cx(tableTokens.header, "sm:w-56 sm:shrink-0")}>{label}</dt>
      <dd className="text-sm text-gray-900 dark:text-gray-100">{text}</dd>
    </div>
  )
}

function Section({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="flex flex-col gap-1">
      <dt className={cx(tableTokens.header, "text-gray-600 dark:text-gray-300")}>
        {label}
      </dt>
      <dd>{children}</dd>
    </div>
  )
}
