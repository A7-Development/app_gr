// src/app/(app)/credito/workflows/[id]/editor/_components/ConditionBuilder.tsx
//
// Construtor visual de CONDICAO — substitui o textarea com sintaxe
// `{{node.X.output.field}} == "value"`.
//
// UI:
//   [Se] [Campo ↓] [Operador ↓] [Valor: input/dropdown]
//
// O usuario nunca digita template syntax. Os dropdowns sao derivados de
// `getAvailableSources()` que computa que campos estao disponiveis a
// partir das etapas upstream.
//
// Funciona em 2 contextos:
//   - Edge condition (EdgeConditionPopover): contexto = etapa do source.
//   - conditional_branch.config.expression: contexto = a propria etapa.
// Em ambos os casos o caller passa `targetNodeId` (a etapa a partir da qual
// upstream e calculado).

"use client"

import * as React from "react"
import { type Edge, type Node } from "@xyflow/react"
import { RiInformationLine } from "@remixicon/react"

import { Input } from "@/components/tremor/Input"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

import {
  type AvailableField,
  type AvailableSource,
  type Condition,
  type ConditionOperator,
  type FieldRef,
  conditionToString,
  getAvailableSources,
  parseCondition,
} from "../_lib/refs"

// ─── Operators per type ─────────────────────────────────────────────────

const OPERATOR_LABEL: Record<ConditionOperator, string> = {
  "==": "e igual a",
  "!=": "e diferente de",
  ">":  "e maior que",
  ">=": "e maior ou igual a",
  "<":  "e menor que",
  "<=": "e menor ou igual a",
}

const OPERATORS_BY_TYPE: Record<string, ConditionOperator[]> = {
  string:  ["==", "!="],
  number:  ["==", "!=", ">", ">=", "<", "<="],
  boolean: ["=="],
  date:    ["==", "!=", ">", ">=", "<", "<="],
  list:    ["=="],
  unknown: ["==", "!=", ">", ">=", "<", "<="],
}

// ─── Component ──────────────────────────────────────────────────────────

export type ConditionBuilderProps = {
  /** Valor atual no formato template syntax. null = sem condicao. */
  value: string | null
  onChange: (next: string | null) => void
  /** Etapa-alvo (cujo upstream e considerado). */
  targetNodeId: string
  /** Todas as etapas do graph (pra computar upstream + labels). */
  nodes: Node[]
  /** Todas as conexoes do graph. */
  edges: Edge[]
  /** Mensagem auxiliar (ex.: "Vazio = sempre passa"). */
  hint?: string
}

export function ConditionBuilder({
  value,
  onChange,
  targetNodeId,
  nodes,
  edges,
  hint,
}: ConditionBuilderProps) {
  const sources = React.useMemo(
    () => getAvailableSources(targetNodeId, nodes, edges),
    [targetNodeId, nodes, edges],
  )

  // Parse value into structured Condition. If unparseable, fall back to
  // a default empty condition.
  const parsed = React.useMemo<Condition | null>(() => {
    if (!value) return null
    return parseCondition(value)
  }, [value])

  // Local editing state — managed when condition exists.
  const [draft, setDraft] = React.useState<Condition>(() =>
    parsed ?? defaultCondition(sources),
  )

  React.useEffect(() => {
    if (parsed) setDraft(parsed)
  }, [parsed])

  const noCondition = value === null || value.trim() === ""

  // Encontra o campo selecionado pra computar tipo + opcoes de operador.
  const leftField = React.useMemo(
    () => findField(sources, draft.left),
    [sources, draft.left],
  )
  const operators = OPERATORS_BY_TYPE[leftField?.type ?? "unknown"] ?? OPERATORS_BY_TYPE.unknown

  // Quando o tipo do campo muda, garante que o operador atual e valido.
  React.useEffect(() => {
    if (!operators.includes(draft.operator)) {
      setDraft((d) => ({ ...d, operator: operators[0] }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [leftField?.type])

  function commit(next: Condition) {
    setDraft(next)
    onChange(conditionToString(next))
  }

  // ── Render ──────────────────────────────────────────────────────────

  if (noCondition) {
    return (
      <div className="space-y-2">
        <div className="rounded-md border border-dashed border-gray-200 bg-gray-50 p-3 text-center dark:border-gray-800 dark:bg-gray-900">
          <p className="text-xs text-gray-700 dark:text-gray-300">
            Sem condicao — esta conexao sempre e seguida.
          </p>
          <button
            type="button"
            onClick={() =>
              onChange(conditionToString(defaultCondition(sources)))
            }
            className="mt-2 text-xs font-medium text-blue-700 hover:text-blue-900 dark:text-blue-400 dark:hover:text-blue-300"
            disabled={sources.length === 0}
          >
            + Adicionar condicao
          </button>
        </div>
        {hint && (
          <p className={cx(tableTokens.cellSecondary)}>{hint}</p>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <p className={cx(tableTokens.cellSecondary)}>Quando seguir por aqui:</p>
      <div className="grid grid-cols-[auto_1fr_auto_1fr] items-center gap-2">
        <span className="text-xs font-medium text-gray-700 dark:text-gray-300">
          Se
        </span>
        <FieldSelect
          sources={sources}
          value={draft.left}
          onChange={(left) => commit({ ...draft, left })}
        />
        <Select
          value={draft.operator}
          onValueChange={(op) =>
            commit({ ...draft, operator: op as ConditionOperator })
          }
        >
          <SelectTrigger className="text-xs">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {operators.map((op) => (
              <SelectItem key={op} value={op}>
                {OPERATOR_LABEL[op]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <ValueInput
          fieldType={leftField?.type ?? "unknown"}
          value={draft.right}
          onChange={(right) => commit({ ...draft, right })}
          sources={sources}
        />
      </div>
      <div className="flex items-center justify-between gap-2">
        {hint ? (
          <p className={cx(tableTokens.cellSecondary, "flex-1")}>{hint}</p>
        ) : (
          <span />
        )}
        <button
          type="button"
          onClick={() => onChange(null)}
          className="text-xs text-gray-500 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-400"
        >
          Remover condicao
        </button>
      </div>
      <details className="rounded-md border border-gray-200 dark:border-gray-800">
        <summary className="cursor-pointer px-3 py-1.5 text-[11px] text-gray-500 dark:text-gray-400">
          <RiInformationLine className="-mt-0.5 mr-1 inline size-3" aria-hidden />
          Ver expressao gerada (avancado)
        </summary>
        <code className="block border-t border-gray-200 bg-gray-50 px-3 py-2 font-mono text-[11px] text-gray-700 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-300">
          {value}
        </code>
      </details>
    </div>
  )
}

// ─── Sub-components ─────────────────────────────────────────────────────

function FieldSelect({
  sources,
  value,
  onChange,
}: {
  sources: AvailableSource[]
  value: FieldRef
  onChange: (next: FieldRef) => void
}) {
  const currentKey = refToSelectKey(value)
  return (
    <Select
      value={currentKey}
      onValueChange={(k) => {
        const ref = selectKeyToRef(k)
        if (ref) onChange(ref)
      }}
    >
      <SelectTrigger className="text-xs">
        <SelectValue placeholder="Selecione um campo" />
      </SelectTrigger>
      <SelectContent className="max-h-80">
        {sources.length === 0 ? (
          <SelectItem value="__none__" disabled>
            Sem campos disponiveis (conecte a etapa a outra com saida)
          </SelectItem>
        ) : (
          sources.map((src) => (
            <React.Fragment key={src.sourceId}>
              <div className="px-2 py-1 text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                {src.sourceLabel}
              </div>
              {src.fields.map((f) => (
                <SelectItem
                  key={`${src.sourceId}.${f.key}`}
                  value={refToSelectKey(
                    src.sourceId === "trigger"
                      ? { kind: "trigger", field: f.key }
                      : { kind: "node", nodeId: src.sourceId, field: f.key },
                  )}
                >
                  {f.label}{" "}
                  <span className="text-[10px] text-gray-400">
                    ({fieldTypeLabel(f.type)})
                  </span>
                </SelectItem>
              ))}
            </React.Fragment>
          ))
        )}
      </SelectContent>
    </Select>
  )
}

function ValueInput({
  fieldType,
  value,
  onChange,
  sources,
}: {
  fieldType: AvailableField["type"]
  value: FieldRef
  onChange: (next: FieldRef) => void
  sources: AvailableSource[]
}) {
  // Se valor e uma referencia a outra etapa, usar FieldSelect.
  // Default: literal — input simples.
  const isRef = value.kind !== "literal"

  if (isRef) {
    return (
      <div className="flex items-center gap-1">
        <FieldSelect sources={sources} value={value} onChange={onChange} />
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

  // Boolean: dropdown true/false.
  if (fieldType === "boolean") {
    return (
      <Select
        value={value.value || "true"}
        onValueChange={(v) => onChange({ kind: "literal", value: v })}
      >
        <SelectTrigger className="text-xs">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value="true">Verdadeiro</SelectItem>
          <SelectItem value="false">Falso</SelectItem>
        </SelectContent>
      </Select>
    )
  }

  // Number: input numerico.
  if (fieldType === "number") {
    return (
      <Input
        type="number"
        value={value.value}
        placeholder="0"
        onChange={(e) => onChange({ kind: "literal", value: e.target.value })}
        className="text-xs"
      />
    )
  }

  // String / unknown: input livre.
  return (
    <div className="flex items-center gap-1">
      <Input
        value={value.value}
        placeholder="valor"
        onChange={(e) => onChange({ kind: "literal", value: e.target.value })}
        className="text-xs"
      />
      <button
        type="button"
        onClick={() => {
          // Switch para modo referencia.
          const first = sources[0]
          const firstField = first?.fields[0]
          if (first && firstField) {
            onChange(
              first.sourceId === "trigger"
                ? { kind: "trigger", field: firstField.key }
                : { kind: "node", nodeId: first.sourceId, field: firstField.key },
            )
          }
        }}
        className="text-[10px] text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
        title="Comparar com campo de outra etapa"
      >
        ref
      </button>
    </div>
  )
}

// ─── Helpers ────────────────────────────────────────────────────────────

function defaultCondition(sources: AvailableSource[]): Condition {
  const first = sources[0]
  const firstField = first?.fields[0]
  const left: FieldRef = first && firstField
    ? first.sourceId === "trigger"
      ? { kind: "trigger", field: firstField.key }
      : { kind: "node", nodeId: first.sourceId, field: firstField.key }
    : { kind: "literal", value: "" }
  return {
    left,
    operator: "==",
    right: { kind: "literal", value: "" },
  }
}

function refToSelectKey(ref: FieldRef): string {
  if (ref.kind === "trigger") return `trigger.${ref.field}`
  if (ref.kind === "node") return `node.${ref.nodeId}.${ref.field}`
  return `literal:${ref.value}`
}

function selectKeyToRef(key: string): FieldRef | null {
  if (key.startsWith("trigger.")) {
    return { kind: "trigger", field: key.slice("trigger.".length) }
  }
  if (key.startsWith("node.")) {
    const rest = key.slice("node.".length)
    const lastDot = rest.lastIndexOf(".")
    if (lastDot < 0) return null
    return {
      kind: "node",
      nodeId: rest.slice(0, lastDot),
      field: rest.slice(lastDot + 1),
    }
  }
  return null
}

function findField(sources: AvailableSource[], ref: FieldRef): AvailableField | undefined {
  if (ref.kind === "literal") return undefined
  if (ref.kind === "trigger") {
    return sources.find((s) => s.sourceId === "trigger")?.fields.find((f) => f.key === ref.field)
  }
  return sources.find((s) => s.sourceId === ref.nodeId)?.fields.find((f) => f.key === ref.field)
}

function fieldTypeLabel(t: AvailableField["type"]): string {
  switch (t) {
    case "string": return "texto"
    case "number": return "numero"
    case "boolean": return "sim/nao"
    case "date":   return "data"
    case "list":   return "lista"
    default:       return "?"
  }
}
