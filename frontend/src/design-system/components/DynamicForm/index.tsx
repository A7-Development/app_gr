// src/design-system/components/DynamicForm/index.tsx
//
// DynamicForm — renderiza um form a partir de uma lista de FormField
// (descritor vindo do backend, ex.: `human_input` node config).
//
// Suporta types: string | cnpj | cpf | email | textarea | select | number |
// date | json | boolean.
//
// CNPJ/CPF aplicam mascara progressiva (livre na entrada, formatada no display
// quando o valor preenche). Validacao basica (dig digitos suficientes) — a
// validacao definitiva e do backend.
//
// Uso:
//
//   <DynamicForm
//     fields={pendingNode.output_data.fields}
//     onSubmit={(values) => submit(values)}
//     submitting={mutation.isPending}
//     submitLabel="Salvar e prosseguir"
//   />

"use client"

import * as React from "react"

import { Button } from "@/components/tremor/Button"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import { Textarea } from "@/components/tremor/Textarea"
import { type FormField } from "@/lib/credito-client"
import { cx } from "@/lib/utils"

type Props = {
  fields: FormField[]
  initialValues?: Record<string, unknown>
  onSubmit: (values: Record<string, unknown>) => void
  onCancel?: () => void
  submitting?: boolean
  submitLabel?: string
  cancelLabel?: string
}

export function DynamicForm({
  fields,
  initialValues,
  onSubmit,
  onCancel,
  submitting = false,
  submitLabel = "Salvar",
  cancelLabel = "Cancelar",
}: Props) {
  const [values, setValues] = React.useState<Record<string, unknown>>(
    () => initialValues ?? {},
  )
  const [errors, setErrors] = React.useState<Record<string, string>>({})

  function setField(key: string, value: unknown) {
    setValues((prev) => ({ ...prev, [key]: value }))
    if (errors[key]) {
      setErrors((prev) => {
        const next = { ...prev }
        delete next[key]
        return next
      })
    }
  }

  function validate(): boolean {
    const errs: Record<string, string> = {}
    for (const f of fields) {
      const v = values[f.key]
      if (f.required && (v === undefined || v === null || v === "")) {
        errs[f.key] = "Obrigatorio"
        continue
      }
      if (v === undefined || v === null || v === "") continue

      if (f.type === "cnpj" && !isValidCnpjLike(String(v))) {
        errs[f.key] = "CNPJ invalido (precisa 14 digitos)"
      } else if (f.type === "cpf" && !isValidCpfLike(String(v))) {
        errs[f.key] = "CPF invalido (precisa 11 digitos)"
      } else if (f.type === "email" && !isValidEmail(String(v))) {
        errs[f.key] = "E-mail invalido"
      } else if (f.type === "json") {
        // Already validated as JSON in onChange
      }
    }
    setErrors(errs)
    return Object.keys(errs).length === 0
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!validate()) return
    onSubmit(values)
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {fields.map((f) => (
        <FieldRenderer
          key={f.key}
          field={f}
          value={values[f.key]}
          error={errors[f.key]}
          onChange={(v) => setField(f.key, v)}
        />
      ))}

      <div className="flex items-center justify-end gap-2 border-t border-gray-200 pt-4 dark:border-gray-800">
        {onCancel && (
          <Button type="button" variant="secondary" onClick={onCancel} disabled={submitting}>
            {cancelLabel}
          </Button>
        )}
        <Button type="submit" disabled={submitting} isLoading={submitting}>
          {submitLabel}
        </Button>
      </div>
    </form>
  )
}

function FieldRenderer({
  field,
  value,
  error,
  onChange,
}: {
  field: FormField
  value: unknown
  error?: string
  onChange: (v: unknown) => void
}) {
  const id = `field-${field.key}`
  const labelEl = (
    <Label htmlFor={id} className="text-xs">
      {field.label}
      {field.required && <span className="ml-0.5 text-red-600">*</span>}
    </Label>
  )

  let input: React.ReactNode

  switch (field.type) {
    case "textarea":
      input = (
        <Textarea
          id={id}
          rows={3}
          placeholder={field.placeholder}
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
        />
      )
      break

    case "select":
      input = (
        <Select
          value={(value as string) ?? ""}
          onValueChange={(v) => onChange(v)}
        >
          <SelectTrigger id={id} className="w-full">
            <SelectValue placeholder={field.placeholder ?? "Selecione"} />
          </SelectTrigger>
          <SelectContent>
            {(field.options ?? []).map((opt) => (
              <SelectItem key={opt} value={opt}>
                {opt}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      )
      break

    case "number":
      input = (
        <Input
          id={id}
          type="number"
          placeholder={field.placeholder}
          value={(value as number | string | undefined) ?? ""}
          onChange={(e) =>
            onChange(e.target.value === "" ? undefined : Number(e.target.value))
          }
        />
      )
      break

    case "date":
      input = (
        <Input
          id={id}
          type="date"
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value || undefined)}
        />
      )
      break

    case "boolean":
      return (
        <div>
          <label className="flex items-center gap-2 text-sm">
            <input
              id={id}
              type="checkbox"
              checked={Boolean(value)}
              onChange={(e) => onChange(e.target.checked)}
              className="rounded"
            />
            {field.label}
            {field.required && <span className="ml-0.5 text-red-600">*</span>}
          </label>
        </div>
      )

    case "cnpj":
      input = (
        <Input
          id={id}
          placeholder={field.placeholder ?? "00.000.000/0000-00"}
          value={(value as string) ?? ""}
          onChange={(e) => onChange(maskCnpj(e.target.value))}
          maxLength={18}
        />
      )
      break

    case "cpf":
      input = (
        <Input
          id={id}
          placeholder={field.placeholder ?? "000.000.000-00"}
          value={(value as string) ?? ""}
          onChange={(e) => onChange(maskCpf(e.target.value))}
          maxLength={14}
        />
      )
      break

    case "email":
      input = (
        <Input
          id={id}
          type="email"
          placeholder={field.placeholder}
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
        />
      )
      break

    case "json": {
      const text = stringifyJsonForInput(value)
      input = (
        <Textarea
          id={id}
          rows={5}
          placeholder={field.placeholder ?? "[]"}
          value={text}
          onChange={(e) => {
            const v = e.target.value
            if (v.trim() === "") {
              onChange(undefined)
              return
            }
            try {
              onChange(JSON.parse(v))
            } catch {
              // Keep raw text — user is mid-typing.
              onChange(v)
            }
          }}
          className="font-mono text-xs"
        />
      )
      break
    }

    default:
      input = (
        <Input
          id={id}
          placeholder={field.placeholder}
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
        />
      )
  }

  // Note: when type === "boolean", the function returned early above with a
  // self-contained <label>. Reaching here, the regular labelEl always applies.
  return (
    <div>
      {labelEl}
      {input}
      {error && (
        <p className={cx("mt-1 text-xs text-red-600 dark:text-red-400")}>{error}</p>
      )}
    </div>
  )
}

// ─── Helpers ───────────────────────────────────────────────────────────

function maskCnpj(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 14)
  const parts: string[] = []
  if (digits.length > 0) parts.push(digits.slice(0, 2))
  if (digits.length >= 3) parts[0] += `.${digits.slice(2, 5)}`
  if (digits.length >= 6) parts[0] += `.${digits.slice(5, 8)}`
  if (digits.length >= 9) parts[0] += `/${digits.slice(8, 12)}`
  if (digits.length >= 13) parts[0] += `-${digits.slice(12, 14)}`
  return parts[0] ?? digits
}

function maskCpf(raw: string): string {
  const digits = raw.replace(/\D/g, "").slice(0, 11)
  const parts: string[] = []
  if (digits.length > 0) parts.push(digits.slice(0, 3))
  if (digits.length >= 4) parts[0] += `.${digits.slice(3, 6)}`
  if (digits.length >= 7) parts[0] += `.${digits.slice(6, 9)}`
  if (digits.length >= 10) parts[0] += `-${digits.slice(9, 11)}`
  return parts[0] ?? digits
}

function isValidCnpjLike(value: string): boolean {
  return value.replace(/\D/g, "").length === 14
}

function isValidCpfLike(value: string): boolean {
  return value.replace(/\D/g, "").length === 11
}

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)
}

function stringifyJsonForInput(value: unknown): string {
  if (value === undefined || value === null) return ""
  if (typeof value === "string") return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}
