// src/app/(app)/credito/workflows/[id]/editor/_components/AgentInputBindingsField.tsx
//
// Builder VISUAL para `config.input_bindings` de um specialist_agent
// (Phase B1 da migracao para contexto estruturado — backend Phase A entregue).
//
// Cada slot declarado no `agent.inputs` ganha uma linha:
//   nome [chip de tipo] descricao
//   ← [picker de variavel upstream]
//
// O usuario nao toca em JSON nem digita `{{node.X.output.Y}}`. O picker
// reusa `getAvailableSources` (mesmo dropdown filtrado upstream usado pelo
// ConditionBuilder e ConsolidatorBuilder).
//
// Quando o agente nao tem `inputs[]` (legacy path), este componente nao
// e renderizado pelo AgentInspector.

"use client"

import * as React from "react"
import { type Edge, type Node } from "@xyflow/react"
import { RiInformationLine } from "@remixicon/react"

import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import type { AgentInputMeta, AgentMeta } from "@/lib/credito-client"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

import { type AvailableSource, getAvailableSources } from "../_lib/refs"

// ─── pt-BR labels per VarType ───────────────────────────────────────────

const TYPE_LABEL: Record<string, string> = {
  string: "Texto",
  cpf: "CPF",
  cnpj: "CNPJ",
  email: "E-mail",
  phone: "Telefone",
  date: "Data",
  datetime: "Data/Hora",
  number: "Numero",
  money_brl: "Valor (R$)",
  score: "Score",
  boolean: "Sim/Nao",
  url: "URL",
  uuid: "ID",
  file: "Arquivo",
  object: "Objeto",
  list: "Lista",
}

function typeLabel(t: string): string {
  return TYPE_LABEL[t] ?? t
}

// ─── Component ──────────────────────────────────────────────────────────

export type AgentInputBindingsFieldProps = {
  agent: AgentMeta
  /** Map { slot_name: ref_path } onde ref_path eh "trigger.X" ou
   *  "node.X.output.Y" — formato esperado pelo backend resolver. */
  value: Record<string, string>
  onChange: (next: Record<string, string>) => void
  /** Etapa-alvo (a propria) — define o universo de variaveis upstream. */
  targetNodeId: string
  nodes: Node[]
  edges: Edge[]
}

export function AgentInputBindingsField({
  agent,
  value,
  onChange,
  targetNodeId,
  nodes,
  edges,
}: AgentInputBindingsFieldProps) {
  const sources = React.useMemo(
    () => getAvailableSources(targetNodeId, nodes, edges),
    [targetNodeId, nodes, edges],
  )
  const bindings = value ?? {}

  function commit(slotName: string, refPath: string | null) {
    const next = { ...bindings }
    if (refPath === null || refPath === "") {
      delete next[slotName]
    } else {
      next[slotName] = refPath
    }
    onChange(next)
  }

  if (!agent.inputs || agent.inputs.length === 0) {
    return null
  }

  const requiredCount = agent.inputs.filter((s) => !s.optional).length
  const boundCount = agent.inputs.filter((s) => bindings[s.name]).length
  const requiredUnbound = agent.inputs.filter(
    (s) => !s.optional && !bindings[s.name],
  ).length

  return (
    <div className="space-y-3 rounded-md border border-gray-200 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-900/50">
      <div>
        <p className={tableTokens.header}>
          Inputs do agente ({boundCount} de {agent.inputs.length} conectado
          {agent.inputs.length === 1 ? "" : "s"})
        </p>
        <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
          Liga cada dado que o agente precisa receber a uma etapa anterior do playbook.
        </p>
      </div>

      {requiredUnbound > 0 && (
        <div className="flex items-start gap-1.5 rounded-md border border-red-200 bg-red-50 p-2 text-[11px] text-red-900 dark:border-red-500/40 dark:bg-red-500/10 dark:text-red-200">
          <RiInformationLine
            className="mt-0.5 size-3.5 shrink-0 text-red-700 dark:text-red-400"
            aria-hidden
          />
          <span>
            {requiredUnbound === 1
              ? "1 input obrigatorio sem conexao."
              : `${requiredUnbound} inputs obrigatorios sem conexao.`}{" "}
            O agente vai receber valor vazio em runtime.
          </span>
        </div>
      )}

      <ul className="space-y-2">
        {agent.inputs.map((slot) => (
          <li
            key={slot.name}
            className="rounded-md border border-gray-200 bg-white p-2.5 dark:border-gray-800 dark:bg-gray-950"
          >
            <SlotRow
              slot={slot}
              value={bindings[slot.name] ?? null}
              onChange={(next) => commit(slot.name, next)}
              sources={sources}
              isRequiredAndUnbound={
                !slot.optional && !bindings[slot.name]
              }
            />
          </li>
        ))}
      </ul>

      <p className={cx(tableTokens.cellSecondary, "italic")}>
        {requiredCount} obrigatorio{requiredCount === 1 ? "" : "s"} ·{" "}
        {agent.inputs.length - requiredCount} opcional
        {agent.inputs.length - requiredCount === 1 ? "" : "is"}
      </p>
    </div>
  )
}

// ─── SlotRow ────────────────────────────────────────────────────────────

function SlotRow({
  slot,
  value,
  onChange,
  sources,
  isRequiredAndUnbound,
}: {
  slot: AgentInputMeta
  value: string | null
  onChange: (next: string | null) => void
  sources: AvailableSource[]
  isRequiredAndUnbound: boolean
}) {
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="font-mono text-xs font-semibold text-gray-900 dark:text-gray-100">
          {slot.name}
        </span>
        <span className="rounded bg-gray-100 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-gray-600 dark:bg-gray-800 dark:text-gray-300">
          {typeLabel(slot.type)}
        </span>
        {!slot.optional ? (
          <span
            className={cx(
              "rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider",
              isRequiredAndUnbound
                ? "bg-red-100 text-red-700 dark:bg-red-500/15 dark:text-red-300"
                : "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300",
            )}
          >
            obrigatorio
          </span>
        ) : (
          <span className="rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
            opcional
          </span>
        )}
      </div>

      {slot.description && (
        <p className="text-[11px] text-gray-500 dark:text-gray-400">
          {slot.description}
        </p>
      )}

      <div className="flex items-center gap-1.5">
        <RefSelect
          path={value ?? ""}
          sources={sources}
          onChange={(next) => onChange(next || null)}
        />
        {value && (
          <button
            type="button"
            onClick={() => onChange(null)}
            className="text-[10px] text-gray-500 hover:text-red-600 dark:text-gray-400 dark:hover:text-red-400"
            title="Remover conexao"
          >
            limpar
          </button>
        )}
      </div>
    </div>
  )
}

// ─── RefSelect ──────────────────────────────────────────────────────────
//
// Mesmo dropdown agrupado por etapa upstream usado no ConsolidatorBuilder.
// Mantido como copia local pra evitar circular import e porque o uso aqui
// nao precisa de literal mode (so refs).

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
        <SelectValue placeholder="Selecione uma variavel..." />
      </SelectTrigger>
      <SelectContent className="max-h-80">
        {sources.length === 0 || sources.every((s) => s.fields.length === 0) ? (
          <SelectItem value="__none__" disabled>
            Sem variaveis disponiveis (conecte a etapa a outra primeiro)
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
