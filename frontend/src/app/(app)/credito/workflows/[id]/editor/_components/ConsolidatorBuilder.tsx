// src/app/(app)/credito/workflows/[id]/editor/_components/ConsolidatorBuilder.tsx
//
// Builder VISUAL para `config.output_fields` da etapa "Consolidador"
// (consolidator). Substitui o textarea de JSON.
//
// Cada output field tem:
//   - name (texto livre, suporta ponto pra objeto aninhado)
//   - type (VarType: string/number/boolean/list/object/cnpj/cpf/date)
//   - op (whitelist: pegar_valor, min, max, sum, avg, concat, coalesce, len)
//   - args (lista de {kind: "ref"|"literal", ...})
//
// O usuario nunca toca em JSON nem digita `{{node.X.output.Y}}`.
//   - kind=ref: dropdown com campos disponiveis upstream (mesmo que ConditionBuilder)
//   - kind=literal: input simples (text/number/boolean), so escalares na Fase 1
//
// Espelha o ConsolidatorNode em `backend/app/shared/workflow/nodes/consolidator.py`.

"use client"

import * as React from "react"
import { type Edge, type Node } from "@xyflow/react"
import {
  RiAddLine,
  RiArrowDownSLine,
  RiArrowUpSLine,
  RiCloseLine,
  RiDeleteBinLine,
  RiInformationLine,
} from "@remixicon/react"

import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import { Button } from "@/components/tremor/Button"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

import { type AvailableSource, getAvailableSources } from "../_lib/refs"

// ─── Types (espelham backend) ───────────────────────────────────────────

type ConsolidatorOp =
  | "pegar_valor"
  | "min"
  | "max"
  | "sum"
  | "avg"
  | "concat"
  | "coalesce"
  | "len"

type VarTypeOption =
  | "string"
  | "number"
  | "boolean"
  | "list"
  | "object"
  | "date"
  | "cnpj"
  | "cpf"

type ConsolidatorArg =
  | { kind: "ref"; path: string }
  | { kind: "literal"; value: number | string | boolean }

export type ConsolidatorOutputField = {
  name: string
  type: VarTypeOption
  op: ConsolidatorOp
  args: ConsolidatorArg[]
}

// ─── Op metadata ────────────────────────────────────────────────────────

type OpMeta = {
  label: string
  hint: string
  /** "1" = exato 1; "variadic" = 1+ args (botoes add/remove). */
  arity: "1" | "variadic"
  /** Tipo de saida forcado pela op (null = depende do arg). */
  forcedOutputType: VarTypeOption | null
}

const OPS: Record<ConsolidatorOp, OpMeta> = {
  pegar_valor: {
    label: "Pegar valor",
    hint: "Copia 1 valor de outra etapa (ou um valor fixo) para este campo.",
    arity: "1",
    forcedOutputType: null,
  },
  min: {
    label: "Minimo",
    hint: "Menor valor entre os argumentos. Ignora valores vazios.",
    arity: "variadic",
    forcedOutputType: "number",
  },
  max: {
    label: "Maximo",
    hint: "Maior valor entre os argumentos. Ignora valores vazios.",
    arity: "variadic",
    forcedOutputType: "number",
  },
  sum: {
    label: "Somar",
    hint: "Soma dos argumentos. Ignora valores vazios; tudo vazio = 0.",
    arity: "variadic",
    forcedOutputType: "number",
  },
  avg: {
    label: "Media",
    hint: "Media dos argumentos numericos. Ignora valores vazios.",
    arity: "variadic",
    forcedOutputType: "number",
  },
  concat: {
    label: "Concatenar listas",
    hint: "Junta varias listas em uma. Valores vazios sao ignorados.",
    arity: "variadic",
    forcedOutputType: "list",
  },
  coalesce: {
    label: "Primeiro nao-vazio",
    hint: "Devolve o primeiro argumento que nao for vazio.",
    arity: "variadic",
    forcedOutputType: null,
  },
  len: {
    label: "Tamanho da lista",
    hint: "Conta quantos itens a lista tem. Vazio = 0.",
    arity: "1",
    forcedOutputType: "number",
  },
}

const TYPE_OPTIONS: Array<{ value: VarTypeOption; label: string }> = [
  { value: "string",  label: "Texto" },
  { value: "number",  label: "Numero" },
  { value: "boolean", label: "Sim/Nao" },
  { value: "list",    label: "Lista" },
  { value: "object",  label: "Objeto" },
  { value: "date",    label: "Data" },
  { value: "cnpj",    label: "CNPJ" },
  { value: "cpf",     label: "CPF" },
]

// ─── Component ──────────────────────────────────────────────────────────

export type ConsolidatorBuilderProps = {
  value: ConsolidatorOutputField[]
  onChange: (next: ConsolidatorOutputField[]) => void
  /** Etapa-alvo (usado para calcular variaveis upstream disponiveis). */
  targetNodeId: string
  nodes: Node[]
  edges: Edge[]
}

export function ConsolidatorBuilder({
  value,
  onChange,
  targetNodeId,
  nodes,
  edges,
}: ConsolidatorBuilderProps) {
  const sources = React.useMemo(
    () => getAvailableSources(targetNodeId, nodes, edges),
    [targetNodeId, nodes, edges],
  )

  const fields = value ?? []

  function update(idx: number, next: ConsolidatorOutputField) {
    const arr = [...fields]
    arr[idx] = next
    onChange(arr)
  }

  function remove(idx: number) {
    onChange(fields.filter((_, i) => i !== idx))
  }

  function move(idx: number, dir: -1 | 1) {
    const arr = [...fields]
    const target = idx + dir
    if (target < 0 || target >= arr.length) return
    ;[arr[idx], arr[target]] = [arr[target], arr[idx]]
    onChange(arr)
  }

  function addBlank() {
    const next: ConsolidatorOutputField = {
      name: `campo_${fields.length + 1}`,
      type: "string",
      op: "pegar_valor",
      args: [{ kind: "literal", value: "" }],
    }
    onChange([...fields, next])
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className={tableTokens.header}>Saidas deste consolidador</p>
        <span className={tableTokens.cellSecondary}>
          {fields.length} {fields.length === 1 ? "campo" : "campos"}
        </span>
      </div>

      <div className="rounded-md border border-blue-200 bg-blue-50 p-2.5 text-xs dark:border-blue-500/30 dark:bg-blue-500/10">
        <p className="font-medium text-blue-900 dark:text-blue-200">
          <RiInformationLine className="-mt-0.5 mr-1 inline size-3.5" aria-hidden />
          Como funciona
        </p>
        <p className="mt-1 text-blue-800 dark:text-blue-300">
          Cada saida vem de UMA operacao sobre dados das etapas anteriores.
          Para objetos aninhados use ponto no nome
          (ex.: <code className="font-mono">cabecalho.cnpj</code>).
          Sem IA — regra fixa, resultado igual sempre.
        </p>
      </div>

      {fields.length === 0 ? (
        <div className="rounded-md border border-dashed border-gray-200 bg-gray-50 p-4 text-center dark:border-gray-800 dark:bg-gray-900">
          <p className={tableTokens.cellSecondary}>
            Sem campos ainda. Adicione o primeiro abaixo.
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {fields.map((f, i) => (
            <li
              key={i}
              className="rounded-md border border-gray-200 bg-white p-2.5 dark:border-gray-800 dark:bg-gray-950"
            >
              <FieldRow
                field={f}
                sources={sources}
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
        Adicionar campo de saida
      </Button>
    </div>
  )
}

// ─── FieldRow ───────────────────────────────────────────────────────────

function FieldRow({
  field,
  sources,
  onChange,
  onRemove,
  onMoveUp,
  onMoveDown,
}: {
  field: ConsolidatorOutputField
  sources: AvailableSource[]
  onChange: (next: ConsolidatorOutputField) => void
  onRemove: () => void
  onMoveUp?: () => void
  onMoveDown?: () => void
}) {
  const opMeta = OPS[field.op]

  function commitOp(nextOp: ConsolidatorOp) {
    const meta = OPS[nextOp]
    // Adjust args to match the new op's arity.
    let nextArgs = field.args
    if (meta.arity === "1") {
      nextArgs = [field.args[0] ?? { kind: "literal", value: "" }]
    } else if (field.args.length === 0) {
      nextArgs = [{ kind: "literal", value: "" }]
    }
    // Adjust output type if the new op forces it.
    const nextType =
      meta.forcedOutputType ?? field.type
    onChange({ ...field, op: nextOp, args: nextArgs, type: nextType })
  }

  function commitArg(idx: number, next: ConsolidatorArg) {
    const arr = [...field.args]
    arr[idx] = next
    onChange({ ...field, args: arr })
  }

  function addArg() {
    onChange({
      ...field,
      args: [...field.args, { kind: "literal", value: "" }],
    })
  }

  function removeArg(idx: number) {
    if (field.args.length <= 1) return
    onChange({
      ...field,
      args: field.args.filter((_, i) => i !== idx),
    })
  }

  return (
    <div className="space-y-2">
      {/* Linha 1: nome + tipo + acoes */}
      <div className="grid grid-cols-[1fr_auto_auto] items-end gap-2">
        <div>
          <Label htmlFor={`name-${field.name}`} className="text-[11px]">
            Nome do campo
          </Label>
          <Input
            id={`name-${field.name}`}
            value={field.name}
            placeholder="ex.: score_consolidado ou cabecalho.cnpj"
            onChange={(e) => onChange({ ...field, name: e.target.value })}
            className="text-xs"
          />
        </div>
        <div className="w-32">
          <Label htmlFor={`type-${field.name}`} className="text-[11px]">
            Tipo
          </Label>
          <Select
            value={field.type}
            onValueChange={(v) =>
              onChange({ ...field, type: v as VarTypeOption })
            }
            disabled={opMeta.forcedOutputType !== null}
          >
            <SelectTrigger id={`type-${field.name}`} className="text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {TYPE_OPTIONS.map((t) => (
                <SelectItem key={t.value} value={t.value}>
                  {t.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="flex items-center gap-0.5">
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

      {/* Linha 2: operacao */}
      <div>
        <Label className="text-[11px]">Como calcular</Label>
        <Select value={field.op} onValueChange={(v) => commitOp(v as ConsolidatorOp)}>
          <SelectTrigger className="text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(Object.keys(OPS) as ConsolidatorOp[]).map((op) => (
              <SelectItem key={op} value={op}>
                {OPS[op].label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="mt-1 text-[10px] text-gray-500 dark:text-gray-400">
          {opMeta.hint}
        </p>
      </div>

      {/* Linha 3: argumentos */}
      <div className="rounded-md border border-gray-100 bg-gray-50 p-2 dark:border-gray-900 dark:bg-gray-900/50">
        <p className="mb-1.5 text-[11px] font-medium text-gray-700 dark:text-gray-300">
          {opMeta.arity === "1" ? "Argumento" : "Argumentos"}
        </p>
        <ul className="space-y-1.5">
          {field.args.map((arg, i) => (
            <li key={i} className="flex items-center gap-1.5">
              <ArgInput
                arg={arg}
                sources={sources}
                onChange={(next) => commitArg(i, next)}
              />
              {opMeta.arity === "variadic" && field.args.length > 1 && (
                <button
                  type="button"
                  onClick={() => removeArg(i)}
                  className="rounded p-1 text-gray-400 hover:bg-gray-100 hover:text-red-600 dark:hover:bg-gray-800 dark:hover:text-red-400"
                  aria-label="Remover argumento"
                >
                  <RiCloseLine className="size-3.5" aria-hidden />
                </button>
              )}
            </li>
          ))}
        </ul>
        {opMeta.arity === "variadic" && (
          <button
            type="button"
            onClick={addArg}
            className="mt-2 text-[11px] font-medium text-blue-700 hover:text-blue-900 dark:text-blue-400 dark:hover:text-blue-300"
          >
            + adicionar argumento
          </button>
        )}
      </div>
    </div>
  )
}

// ─── ArgInput ───────────────────────────────────────────────────────────

function ArgInput({
  arg,
  sources,
  onChange,
}: {
  arg: ConsolidatorArg
  sources: AvailableSource[]
  onChange: (next: ConsolidatorArg) => void
}) {
  if (arg.kind === "ref") {
    return (
      <div className="flex flex-1 items-center gap-1">
        <RefSelect path={arg.path} sources={sources} onChange={(p) => onChange({ kind: "ref", path: p })} />
        <button
          type="button"
          onClick={() => onChange({ kind: "literal", value: "" })}
          className="text-[10px] text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
          title="Mudar para valor fixo"
        >
          fixo
        </button>
      </div>
    )
  }

  // literal
  return (
    <div className="flex flex-1 items-center gap-1">
      <Input
        value={String(arg.value)}
        placeholder="valor fixo"
        onChange={(e) => {
          const raw = e.target.value
          // Try numeric parse; fall back to string.
          if (raw === "") {
            onChange({ kind: "literal", value: "" })
            return
          }
          const num = Number(raw)
          if (!Number.isNaN(num) && raw.trim() !== "") {
            onChange({ kind: "literal", value: num })
          } else {
            onChange({ kind: "literal", value: raw })
          }
        }}
        className="text-xs"
      />
      <button
        type="button"
        onClick={() => {
          // Switch to ref mode — pick first available source/field.
          const firstSrc = sources[0]
          const firstField = firstSrc?.fields[0]
          if (firstSrc && firstField) {
            const path =
              firstSrc.sourceId === "trigger"
                ? `trigger.${firstField.key}`
                : `node.${firstSrc.sourceId}.output.${firstField.key}`
            onChange({ kind: "ref", path })
          }
        }}
        className="text-[10px] text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
        title="Mudar para campo de outra etapa"
        disabled={sources.every((s) => s.fields.length === 0)}
      >
        ref
      </button>
    </div>
  )
}

// ─── RefSelect ──────────────────────────────────────────────────────────

function RefSelect({
  path,
  sources,
  onChange,
}: {
  path: string
  sources: AvailableSource[]
  onChange: (path: string) => void
}) {
  return (
    <Select value={path} onValueChange={onChange}>
      <SelectTrigger className="text-xs">
        <SelectValue placeholder="Selecione um campo" />
      </SelectTrigger>
      <SelectContent className="max-h-80">
        {sources.length === 0 || sources.every((s) => s.fields.length === 0) ? (
          <SelectItem value="__none__" disabled>
            Sem campos disponiveis (conecte a etapa a outra primeiro)
          </SelectItem>
        ) : (
          sources.map((src) => (
            <React.Fragment key={src.sourceId}>
              <div className="px-2 py-1 text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                {src.sourceLabel}
              </div>
              {src.fields.map((f) => {
                const refPath =
                  src.sourceId === "trigger"
                    ? `trigger.${f.key}`
                    : `node.${src.sourceId}.output.${f.key}`
                return (
                  <SelectItem key={refPath} value={refPath}>
                    {f.label}{" "}
                    <span className="text-[10px] text-gray-400">({f.type})</span>
                  </SelectItem>
                )
              })}
            </React.Fragment>
          ))
        )}
      </SelectContent>
    </Select>
  )
}
