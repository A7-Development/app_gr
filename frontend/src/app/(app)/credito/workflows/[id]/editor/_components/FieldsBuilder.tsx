// src/app/(app)/credito/workflows/[id]/editor/_components/FieldsBuilder.tsx
//
// Builder VISUAL para `config.fields` da etapa "Pedir dados ao analista"
// (human_input). Substitui o textarea de JSON.
//
// Cada field tem: key, label, type, required, hint.
// Reordenavel (move up/down). Pre-sets prontos pra inserir batches comuns.
//
// O usuario nunca toca em JSON — adiciona/remove/edita campos via form.

"use client"

import * as React from "react"
import {
  RiAddLine,
  RiArrowDownSLine,
  RiArrowUpSLine,
  RiDeleteBinLine,
} from "@remixicon/react"

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
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

// ─── Tipos ──────────────────────────────────────────────────────────────

export type FieldDef = {
  key: string
  label: string
  type:
    | "string"
    | "textarea"
    | "number"
    | "boolean"
    | "date"
    | "cnpj"
    | "cpf"
    | "email"
    | "select"
    | "json"
  required?: boolean
  hint?: string
  /** Para type=select. */
  options?: Array<{ value: string; label: string }>
}

const TYPE_OPTIONS: Array<{ value: FieldDef["type"]; label: string; example: string }> = [
  { value: "string",   label: "Texto curto",     example: "Razao social, nome" },
  { value: "textarea", label: "Texto longo",     example: "Notas, observacoes" },
  { value: "number",   label: "Numero",          example: "Volume R$, prazo dias" },
  { value: "cnpj",     label: "CNPJ (mascarado)",example: "00.000.000/0000-00" },
  { value: "cpf",      label: "CPF (mascarado)", example: "000.000.000-00" },
  { value: "email",    label: "E-mail",          example: "alguem@empresa.com" },
  { value: "date",     label: "Data",            example: "2026-04-30" },
  { value: "boolean",  label: "Sim ou nao",      example: "Empresa ativa?" },
  { value: "select",   label: "Lista de opcoes", example: "Produto: A/B/C" },
  { value: "json",     label: "JSON livre",      example: "Avancado" },
]

const TYPE_LABEL: Record<FieldDef["type"], string> = Object.fromEntries(
  TYPE_OPTIONS.map((t) => [t.value, t.label]),
) as Record<FieldDef["type"], string>

// ─── Pre-sets ───────────────────────────────────────────────────────────

const PRESETS: Array<{ name: string; description: string; fields: FieldDef[] }> = [
  {
    name: "Dados basicos da empresa",
    description: "CNPJ, razao social, atividade, endereco.",
    fields: [
      { key: "cnpj",           label: "CNPJ",           type: "cnpj",     required: true },
      { key: "razao_social",   label: "Razao social",   type: "string",   required: true },
      { key: "nome_fantasia",  label: "Nome fantasia",  type: "string" },
      { key: "atividade",      label: "Atividade",      type: "textarea", hint: "O que a empresa faz" },
      { key: "endereco",       label: "Endereco",       type: "string" },
      { key: "data_fundacao",  label: "Data de fundacao",type: "date" },
    ],
  },
  {
    name: "Pleito comercial",
    description: "Produto, volume, taxa, prazo.",
    fields: [
      { key: "produto",        label: "Produto",         type: "select",
        options: [
          { value: "antecipacao_recebiveis", label: "Antecipacao de recebiveis" },
          { value: "capital_giro",           label: "Capital de giro" },
          { value: "fianca",                 label: "Fianca" },
        ],
        required: true },
      { key: "volume_brl",     label: "Volume (R$)",     type: "number", required: true },
      { key: "taxa_estimada",  label: "Taxa estimada (% am)", type: "number" },
      { key: "prazo_dias",     label: "Prazo (dias)",    type: "number" },
      { key: "observacoes",    label: "Observacoes",     type: "textarea" },
    ],
  },
  {
    name: "Contatos",
    description: "Responsavel, email, telefone.",
    fields: [
      { key: "responsavel_nome",      label: "Nome do responsavel",      type: "string", required: true },
      { key: "responsavel_email",     label: "E-mail do responsavel",    type: "email" },
      { key: "responsavel_telefone",  label: "Telefone",                 type: "string" },
    ],
  },
]

// ─── Component ──────────────────────────────────────────────────────────

export type FieldsBuilderProps = {
  value: FieldDef[]
  onChange: (next: FieldDef[]) => void
}

export function FieldsBuilder({ value, onChange }: FieldsBuilderProps) {
  const fields = value ?? []

  function update(index: number, next: FieldDef) {
    const arr = [...fields]
    arr[index] = next
    onChange(arr)
  }

  function remove(index: number) {
    const arr = fields.filter((_, i) => i !== index)
    onChange(arr)
  }

  function move(index: number, dir: -1 | 1) {
    const arr = [...fields]
    const target = index + dir
    if (target < 0 || target >= arr.length) return
    ;[arr[index], arr[target]] = [arr[target], arr[index]]
    onChange(arr)
  }

  function addBlank() {
    const next: FieldDef = {
      key: `campo_${fields.length + 1}`,
      label: `Campo ${fields.length + 1}`,
      type: "string",
    }
    onChange([...fields, next])
  }

  function applyPreset(preset: (typeof PRESETS)[number]) {
    // Adiciona campos do preset evitando colisao de `key`.
    const existingKeys = new Set(fields.map((f) => f.key))
    const toAdd = preset.fields.filter((f) => !existingKeys.has(f.key))
    onChange([...fields, ...toAdd])
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className={tableTokens.header}>Campos do formulario</p>
        <span className={tableTokens.cellSecondary}>
          {fields.length} {fields.length === 1 ? "campo" : "campos"}
        </span>
      </div>

      {/* Pre-sets */}
      <div className="rounded-md border border-blue-200 bg-blue-50 p-2.5 text-xs dark:border-blue-500/30 dark:bg-blue-500/10">
        <p className="font-medium text-blue-900 dark:text-blue-200">
          Adicionar conjunto pronto
        </p>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          {PRESETS.map((p) => (
            <button
              key={p.name}
              type="button"
              onClick={() => applyPreset(p)}
              className="rounded-md border border-blue-300 bg-white px-2 py-1 text-[11px] font-medium text-blue-800 transition hover:border-blue-500 hover:bg-blue-100 dark:border-blue-500/40 dark:bg-blue-500/10 dark:text-blue-200 dark:hover:bg-blue-500/20"
              title={p.description}
            >
              + {p.name}
            </button>
          ))}
        </div>
      </div>

      {/* Lista de campos */}
      {fields.length === 0 ? (
        <div className="rounded-md border border-dashed border-gray-200 bg-gray-50 p-4 text-center dark:border-gray-800 dark:bg-gray-900">
          <p className={tableTokens.cellSecondary}>
            Sem campos ainda. Use um conjunto pronto acima ou adicione manualmente.
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {fields.map((f, i) => (
            <li
              key={`${f.key}-${i}`}
              className="rounded-md border border-gray-200 bg-white p-2.5 dark:border-gray-800 dark:bg-gray-950"
            >
              <FieldRow
                field={f}
                onChange={(next) => update(i, next)}
                onRemove={() => remove(i)}
                onMoveUp={i > 0 ? () => move(i, -1) : undefined}
                onMoveDown={i < fields.length - 1 ? () => move(i, 1) : undefined}
              />
            </li>
          ))}
        </ul>
      )}

      <Button type="button" variant="secondary" onClick={addBlank} className="w-full">
        <RiAddLine className="size-4" aria-hidden />
        Adicionar campo
      </Button>
    </div>
  )
}

// ─── Single field editor ────────────────────────────────────────────────

function FieldRow({
  field,
  onChange,
  onRemove,
  onMoveUp,
  onMoveDown,
}: {
  field: FieldDef
  onChange: (next: FieldDef) => void
  onRemove: () => void
  onMoveUp?: () => void
  onMoveDown?: () => void
}) {
  const [showAdvanced, setShowAdvanced] = React.useState(false)

  return (
    <div className="space-y-2">
      <div className="grid grid-cols-2 gap-2">
        <div>
          <Label htmlFor={`label-${field.key}`} className="text-[11px]">
            Nome visivel
          </Label>
          <Input
            id={`label-${field.key}`}
            value={field.label}
            onChange={(e) => onChange({ ...field, label: e.target.value })}
            placeholder="Ex.: Razao social"
            className="text-xs"
          />
        </div>
        <div>
          <Label htmlFor={`type-${field.key}`} className="text-[11px]">
            Tipo
          </Label>
          <Select
            value={field.type}
            onValueChange={(v) => onChange({ ...field, type: v as FieldDef["type"] })}
          >
            <SelectTrigger id={`type-${field.key}`} className="text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TYPE_OPTIONS.map((t) => (
                <SelectItem key={t.value} value={t.value}>
                  <span className="text-xs">{t.label}</span>{" "}
                  <span className="text-[10px] text-gray-500">({t.example})</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="flex items-center justify-between gap-2">
        <label className="flex items-center gap-1.5 text-xs text-gray-700 dark:text-gray-300">
          <input
            type="checkbox"
            checked={Boolean(field.required)}
            onChange={(e) => onChange({ ...field, required: e.target.checked })}
            className="rounded"
          />
          Obrigatorio
        </label>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setShowAdvanced((v) => !v)}
            className="text-[11px] text-blue-700 hover:text-blue-900 dark:text-blue-400 dark:hover:text-blue-300"
          >
            {showAdvanced ? "Ocultar" : "Mais opcoes"}
          </button>
          {onMoveUp && (
            <button
              type="button"
              onClick={onMoveUp}
              className="rounded p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800"
              aria-label="Mover pra cima"
            >
              <RiArrowUpSLine className="size-3.5" aria-hidden />
            </button>
          )}
          {onMoveDown && (
            <button
              type="button"
              onClick={onMoveDown}
              className="rounded p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800"
              aria-label="Mover pra baixo"
            >
              <RiArrowDownSLine className="size-3.5" aria-hidden />
            </button>
          )}
          <button
            type="button"
            onClick={onRemove}
            className="rounded p-1 text-gray-500 hover:bg-red-50 hover:text-red-600 dark:text-gray-400 dark:hover:bg-red-500/10 dark:hover:text-red-400"
            aria-label="Remover campo"
          >
            <RiDeleteBinLine className="size-3.5" aria-hidden />
          </button>
        </div>
      </div>

      {showAdvanced && (
        <div className="space-y-2 border-t border-gray-100 pt-2 dark:border-gray-900">
          <div>
            <Label htmlFor={`key-${field.key}`} className="text-[11px]">
              Identificador interno (chave)
            </Label>
            <Input
              id={`key-${field.key}`}
              value={field.key}
              onChange={(e) =>
                onChange({
                  ...field,
                  key: e.target.value.replace(/[^a-zA-Z0-9_]/g, "_"),
                })
              }
              placeholder="razao_social"
              className="font-mono text-xs"
            />
            <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
              Use minusculas e _ — sera o nome do campo nos dados (ex.: <code>razao_social</code>).
            </p>
          </div>
          <div>
            <Label htmlFor={`hint-${field.key}`} className="text-[11px]">
              Dica para o analista
            </Label>
            <Input
              id={`hint-${field.key}`}
              value={field.hint ?? ""}
              onChange={(e) => onChange({ ...field, hint: e.target.value || undefined })}
              placeholder="Texto de apoio mostrado abaixo do campo."
              className="text-xs"
            />
          </div>
          {field.type === "select" && (
            <SelectOptionsEditor
              value={field.options ?? []}
              onChange={(opts) => onChange({ ...field, options: opts })}
            />
          )}
        </div>
      )}
    </div>
  )
}

// ─── Editor de opcoes (para type=select) ────────────────────────────────

function SelectOptionsEditor({
  value,
  onChange,
}: {
  value: Array<{ value: string; label: string }>
  onChange: (next: Array<{ value: string; label: string }>) => void
}) {
  function update(i: number, next: { value: string; label: string }) {
    const arr = [...value]
    arr[i] = next
    onChange(arr)
  }
  function remove(i: number) {
    onChange(value.filter((_, j) => j !== i))
  }
  function add() {
    onChange([...value, { value: `opcao_${value.length + 1}`, label: `Opcao ${value.length + 1}` }])
  }

  return (
    <div className="space-y-1.5">
      <Label className="text-[11px]">Opcoes da lista</Label>
      {value.length === 0 ? (
        <p className={tableTokens.cellSecondary}>
          Nenhuma opcao ainda — adicione abaixo.
        </p>
      ) : (
        <ul className="space-y-1">
          {value.map((opt, i) => (
            <li key={i} className="flex items-center gap-1">
              <Input
                value={opt.label}
                onChange={(e) => update(i, { ...opt, label: e.target.value })}
                placeholder="Visivel"
                className="text-xs"
              />
              <Input
                value={opt.value}
                onChange={(e) =>
                  update(i, { ...opt, value: e.target.value.replace(/[^a-zA-Z0-9_]/g, "_") })
                }
                placeholder="valor"
                className="font-mono text-xs"
              />
              <button
                type="button"
                onClick={() => remove(i)}
                className="rounded p-1 text-gray-500 hover:bg-red-50 hover:text-red-600 dark:text-gray-400 dark:hover:bg-red-500/10 dark:hover:text-red-400"
                aria-label="Remover opcao"
              >
                <RiDeleteBinLine className="size-3.5" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      )}
      <Button type="button" variant="secondary" onClick={add} className="w-full">
        <RiAddLine className="size-3.5" aria-hidden />
        Adicionar opcao
      </Button>
    </div>
  )
}

export { TYPE_LABEL as FIELD_TYPE_LABEL }
