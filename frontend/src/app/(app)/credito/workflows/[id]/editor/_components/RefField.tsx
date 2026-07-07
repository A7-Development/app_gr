// src/app/(app)/credito/workflows/[id]/editor/_components/RefField.tsx
//
// "Reference Field" — campo do editor de workflow que aceita (a) variavel
// upstream OU (b) valor literal. Visual no padrao Tremor Select fechado:
// trigger de largura completa, click em qualquer lugar abre dropdown com
// lista de variaveis disponiveis + opcao "Digitar valor manual".
//
// Estados:
//
// 1. Vazio
//    [ Selecione uma variavel ou digite um valor             ▾ ]
//
// 2. Variavel escolhida (template `{{node.X.output.field}}` puro)
//    [ 🔵 cnpj · Cadastro empresa                            ▾ ]
//
// 3. Literal (qualquer outro texto)
//    [ 12.345.678/0001-90                  ] [ ← Voltar pro dropdown ]
//
// O componente detecta o modo automaticamente via regex em `value`. Caller
// nao precisa diferenciar — passa `value` (string) e `onChange(next)`.
//
// Default vazio (PR A — opcao B): bureau queries da palette ja nao vem
// pre-preenchidas, forca escolha consciente do user.
//
// Filtro por tipo: quando `filterType` e dado, so aparecem variaveis daquele
// tipo. Tipos wildcard (string/object/list) sempre passam.

"use client"

import * as React from "react"
import {
  RiArrowLeftLine,
  RiExpandUpDownLine,
  RiInformationLine,
  RiKeyboardLine,
  RiNodeTree,
} from "@remixicon/react"
import type { Edge, Node } from "@xyflow/react"

import { Button } from "@/components/tremor/Button"
import { Divider } from "@/components/tremor/Divider"
import { Input } from "@/components/tremor/Input"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/tremor/Popover"
import { varTypeMeta } from "@/design-system/tokens/var-type"
import { cx } from "@/lib/utils"

import type { StrataNodeData } from "./StrataNode"

// Match string que e EXATAMENTE um template `{{...}}` puro (sem mistura).
// Espelha `_extract_single_template` em backend/.../bureau_query.py.
const PURE_TEMPLATE_RE = /^\s*\{\{\s*(.+?)\s*\}\}\s*$/

// Sentinela usada pra entrar em modo literal sem injetar valor de
// verdade. Trim no Input transforma de volta em "" se nada for digitado.
const LITERAL_INIT = " "

type ParsedRef =
  | { kind: "trigger"; field: string; sourceLabel: string; varType: string | undefined }
  | {
      kind: "node"
      nodeId: string
      field: string
      sourceLabel: string
      varType: string | undefined
    }
  | { kind: "unknown"; raw: string }

type UpstreamVar = {
  expr: string         // "node.X.output.cnpj" ou "trigger.cnpj"
  template: string     // "{{node.X.output.cnpj}}"
  name: string         // "cnpj"
  varType: string      // "cnpj"
  sourceLabel: string  // "Cadastro empresa" / "Inicio do workflow"
  sourceType: string   // "trigger" | "human_input" | ...
}

export function RefField({
  selectedNodeId,
  nodes,
  edges,
  producedByNode,
  filterType,
  value,
  onChange,
  placeholder,
  expectedTypeLabel,
}: {
  selectedNodeId: string
  nodes: Node[]
  edges: Edge[]
  producedByNode: Record<string, Record<string, string>>
  filterType?: string
  value: string
  onChange: (next: string) => void
  placeholder?: string
  /** "CNPJ", "CPF", etc — usado em hints e filtro do popover. */
  expectedTypeLabel?: string
}) {
  const trimmed = value.trim()
  const templateMatch = trimmed.match(PURE_TEMPLATE_RE)
  const isVar = templateMatch !== null
  const isLiteral = trimmed !== "" && !isVar

  const upstream = useUpstreamVars(
    selectedNodeId,
    nodes,
    edges,
    producedByNode,
    filterType,
  )

  if (isLiteral) {
    return (
      <LiteralRow
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        onBackToDropdown={() => onChange("")}
        canBack={upstream.length > 0}
      />
    )
  }

  const parsed: ParsedRef | null = templateMatch
    ? parseExpression(templateMatch[1], nodes, producedByNode)
    : null

  return (
    <DropdownTrigger
      parsed={parsed}
      placeholder={
        placeholder ?? "Selecione uma variavel ou digite um valor"
      }
      upstream={upstream}
      expectedTypeLabel={expectedTypeLabel}
      onPickVar={onChange}
      onPickLiteral={() => onChange(LITERAL_INIT)}
    />
  )
}

// ─── Trigger estilo Select fechado ────────────────────────────────────────

const triggerClasses = cx(
  "group flex w-full select-none items-center justify-between gap-2 truncate rounded border px-3 py-2 text-sm shadow-xs outline-hidden transition",
  "border-gray-300 dark:border-gray-800",
  "bg-white text-gray-900 dark:bg-gray-950 dark:text-gray-50",
  "hover:bg-gray-50 dark:hover:bg-gray-950/50",
  "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-500",
)

function DropdownTrigger({
  parsed,
  placeholder,
  upstream,
  expectedTypeLabel,
  onPickVar,
  onPickLiteral,
}: {
  parsed: ParsedRef | null
  placeholder: string
  upstream: UpstreamVar[]
  expectedTypeLabel?: string
  onPickVar: (template: string) => void
  onPickLiteral: () => void
}) {
  const [open, setOpen] = React.useState(false)

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button type="button" className={triggerClasses}>
          <SelectedDisplay parsed={parsed} placeholder={placeholder} />
          <RiExpandUpDownLine
            className="size-4 shrink-0 text-gray-400 dark:text-gray-600"
            aria-hidden
          />
        </button>
      </PopoverTrigger>
      <PopoverContent
        className="w-[var(--radix-popover-trigger-width)] p-0"
        align="start"
        sideOffset={4}
      >
        <DropdownList
          upstream={upstream}
          expectedTypeLabel={expectedTypeLabel}
          onPickVar={(t) => {
            onPickVar(t)
            setOpen(false)
          }}
          onPickLiteral={() => {
            onPickLiteral()
            setOpen(false)
          }}
          selectedExpr={parsed && parsed.kind !== "unknown" ? exprFromParsed(parsed) : null}
        />
      </PopoverContent>
    </Popover>
  )
}

function SelectedDisplay({
  parsed,
  placeholder,
}: {
  parsed: ParsedRef | null
  placeholder: string
}) {
  if (!parsed) {
    return (
      <span className="truncate text-gray-500 dark:text-gray-500">
        {placeholder}
      </span>
    )
  }
  if (parsed.kind === "unknown") {
    return (
      <span className="flex items-center gap-1.5 truncate text-amber-700 dark:text-amber-300">
        <RiInformationLine className="size-3.5 shrink-0" aria-hidden />
        <span className="truncate font-mono text-xs">{parsed.raw}</span>
        <span className="text-xs">(variavel nao encontrada)</span>
      </span>
    )
  }
  const meta = varTypeMeta(parsed.varType)
  return (
    <span className="flex items-center gap-2 truncate">
      <span
        aria-hidden
        className={cx("size-2 shrink-0 rounded-full", meta.dotClass)}
      />
      <span className="font-mono text-xs text-gray-900 dark:text-gray-100">
        {parsed.field}
      </span>
      <span
        className={cx(
          "rounded px-1 py-0.5 text-[10px] font-medium",
          meta.chipClass,
        )}
      >
        {meta.label}
      </span>
      <span className="ml-1 truncate text-xs text-gray-500 dark:text-gray-400">
        · {parsed.sourceLabel}
      </span>
    </span>
  )
}

// ─── Conteudo do popover ──────────────────────────────────────────────────

function DropdownList({
  upstream,
  expectedTypeLabel,
  selectedExpr,
  onPickVar,
  onPickLiteral,
}: {
  upstream: UpstreamVar[]
  expectedTypeLabel?: string
  selectedExpr: string | null
  onPickVar: (template: string) => void
  onPickLiteral: () => void
}) {
  const [query, setQuery] = React.useState("")

  const filtered = React.useMemo(() => {
    if (!query.trim()) return upstream
    const q = query.toLowerCase()
    return upstream.filter(
      (v) =>
        v.name.toLowerCase().includes(q) ||
        v.sourceLabel.toLowerCase().includes(q),
    )
  }, [upstream, query])

  return (
    <div className="flex flex-col">
      {upstream.length > 5 && (
        <div className="border-b border-gray-100 p-2 dark:border-gray-900">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filtrar variaveis..."
            className="text-xs"
            autoFocus
          />
          {expectedTypeLabel && (
            <p className="mt-1 flex items-center gap-1 text-[10px] text-gray-500 dark:text-gray-400">
              <RiInformationLine className="size-3" aria-hidden />
              Mostrando apenas tipo{" "}
              <span className="font-mono font-medium">
                {expectedTypeLabel}
              </span>
            </p>
          )}
        </div>
      )}

      <div className="max-h-72 overflow-y-auto py-1">
        {upstream.length === 0 && (
          <div className="px-3 py-4 text-center text-xs text-gray-500 dark:text-gray-400">
            Nenhuma variavel disponivel —{" "}
            {expectedTypeLabel ? (
              <>
                nenhuma etapa anterior produz{" "}
                <span className="font-mono">{expectedTypeLabel}</span>.
              </>
            ) : (
              "esta etapa esta na raiz do workflow."
            )}
          </div>
        )}
        {upstream.length > 0 && filtered.length === 0 && (
          <div className="px-3 py-4 text-center text-xs text-gray-500 dark:text-gray-400">
            Nenhuma variavel bate com o filtro.
          </div>
        )}
        {filtered.map((v) => {
          const meta = varTypeMeta(v.varType)
          const isSelected = v.expr === selectedExpr
          return (
            <button
              key={v.expr}
              type="button"
              onClick={() => onPickVar(v.template)}
              className={cx(
                "flex w-full items-center gap-2 px-3 py-1.5 text-left text-xs",
                isSelected
                  ? "bg-blue-50 dark:bg-blue-500/10"
                  : "hover:bg-gray-50 dark:hover:bg-gray-900",
              )}
            >
              <span
                aria-hidden
                className={cx("size-2 shrink-0 rounded-full", meta.dotClass)}
              />
              <span className="font-mono text-gray-900 dark:text-gray-100">
                {v.name}
              </span>
              <span
                className={cx(
                  "rounded px-1 py-0.5 text-[10px] font-medium",
                  meta.chipClass,
                )}
              >
                {meta.label}
              </span>
              <span className="ml-auto truncate text-[10px] text-gray-500 dark:text-gray-400">
                {v.sourceLabel}
              </span>
            </button>
          )
        })}
      </div>

      <Divider className="my-0" />

      <button
        type="button"
        onClick={onPickLiteral}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs text-gray-700 hover:bg-gray-50 dark:text-gray-300 dark:hover:bg-gray-900"
      >
        <RiKeyboardLine
          className="size-4 shrink-0 text-gray-500 dark:text-gray-400"
          aria-hidden
        />
        <span>Digitar valor manual</span>
      </button>
    </div>
  )
}

// ─── Modo literal ──────────────────────────────────────────────────────────

function LiteralRow({
  value,
  onChange,
  placeholder,
  onBackToDropdown,
  canBack,
}: {
  value: string
  onChange: (next: string) => void
  placeholder?: string
  onBackToDropdown: () => void
  canBack: boolean
}) {
  return (
    <div className="flex items-stretch gap-2">
      <Input
        value={value === LITERAL_INIT ? "" : value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="font-mono text-xs"
        autoFocus={value === LITERAL_INIT}
      />
      <Button
        type="button"
        variant="ghost"
        onClick={onBackToDropdown}
        className="h-8 shrink-0"
        disabled={!canBack}
        title={
          canBack
            ? "Voltar pra escolher variavel upstream"
            : "Nao ha variaveis upstream pra escolher"
        }
      >
        <RiArrowLeftLine className="mr-1.5 size-3.5" aria-hidden />
        <RiNodeTree className="size-3.5" aria-hidden />
      </Button>
    </div>
  )
}

// ─── Helpers ───────────────────────────────────────────────────────────────

function useUpstreamVars(
  selectedNodeId: string,
  nodes: Node[],
  edges: Edge[],
  producedByNode: Record<string, Record<string, string>>,
  filterType?: string,
): UpstreamVar[] {
  return React.useMemo(() => {
    const all = collectUpstream(selectedNodeId, nodes, edges, producedByNode)
    if (!filterType) return all
    const wildcards = new Set(["string", "object", "list"])
    if (wildcards.has(filterType)) return all
    return all.filter(
      (v) => v.varType === filterType || wildcards.has(v.varType),
    )
  }, [selectedNodeId, nodes, edges, producedByNode, filterType])
}

/** BFS reverso a partir do node selecionado, coletando outputs upstream. */
function collectUpstream(
  selectedNodeId: string,
  nodes: Node[],
  edges: Edge[],
  producedByNode: Record<string, Record<string, string>>,
): UpstreamVar[] {
  const incoming = new Map<string, string[]>()
  for (const n of nodes) incoming.set(n.id, [])
  for (const e of edges) {
    const list = incoming.get(e.target)
    if (list && !list.includes(e.source)) list.push(e.source)
  }
  const ancestorIds = new Set<string>()
  const queue = [...(incoming.get(selectedNodeId) ?? [])]
  while (queue.length > 0) {
    const id = queue.shift()!
    if (ancestorIds.has(id)) continue
    ancestorIds.add(id)
    for (const next of incoming.get(id) ?? []) {
      if (!ancestorIds.has(next)) queue.push(next)
    }
  }
  const result: UpstreamVar[] = []
  const nodeById = new Map(nodes.map((n) => [n.id, n]))
  for (const ancestorId of Array.from(ancestorIds)) {
    const ancestorNode = nodeById.get(ancestorId)
    if (!ancestorNode) continue
    const ancestorData = ancestorNode.data as unknown as StrataNodeData
    const ancestorVars = producedByNode[ancestorId] ?? {}
    const sourceLabel = ancestorData.label || ancestorData.nodeType
    for (const [name, varType] of Object.entries(ancestorVars)) {
      const isTrigger = ancestorData.nodeType === "trigger"
      const expr = isTrigger
        ? `trigger.${name}`
        : `node.${ancestorId}.output.${name}`
      result.push({
        expr,
        template: `{{${expr}}}`,
        name,
        varType,
        sourceLabel,
        sourceType: ancestorData.nodeType,
      })
    }
  }
  // Trigger primeiro (origem do fluxo), depois etapas em ordem de label.
  result.sort((a, b) => {
    if (a.sourceType === "trigger" && b.sourceType !== "trigger") return -1
    if (a.sourceType !== "trigger" && b.sourceType === "trigger") return 1
    const cmp = a.sourceLabel.localeCompare(b.sourceLabel)
    if (cmp !== 0) return cmp
    return a.name.localeCompare(b.name)
  })
  return result
}

/** Parse `node.<id>.output.<field>` ou `trigger.<field>` pra metadados. */
function parseExpression(
  expr: string,
  nodes: Node[],
  producedByNode: Record<string, Record<string, string>>,
): ParsedRef {
  const trimmed = expr.trim()
  if (trimmed.startsWith("trigger.")) {
    const field = trimmed.slice("trigger.".length)
    if (!field) return { kind: "unknown", raw: `{{${expr}}}` }
    const triggerNode = nodes.find(
      (n) => (n.data as unknown as StrataNodeData).nodeType === "trigger",
    )
    const triggerVars = triggerNode
      ? producedByNode[triggerNode.id] ?? {}
      : {}
    return {
      kind: "trigger",
      field,
      sourceLabel: "Inicio do workflow",
      varType: triggerVars[field],
    }
  }
  const nodeMatch = trimmed.match(/^node\.([^.]+)\.output\.(.+)$/)
  if (nodeMatch) {
    const [, nodeId, field] = nodeMatch
    const sourceNode = nodes.find((n) => n.id === nodeId)
    if (!sourceNode) return { kind: "unknown", raw: `{{${expr}}}` }
    const data = sourceNode.data as unknown as StrataNodeData
    const sourceVars = producedByNode[nodeId] ?? {}
    return {
      kind: "node",
      nodeId,
      field,
      sourceLabel: data.label || data.nodeType || nodeId,
      varType: sourceVars[field],
    }
  }
  return { kind: "unknown", raw: `{{${expr}}}` }
}

function exprFromParsed(parsed: ParsedRef): string | null {
  if (parsed.kind === "trigger") return `trigger.${parsed.field}`
  if (parsed.kind === "node") return `node.${parsed.nodeId}.output.${parsed.field}`
  return null
}
