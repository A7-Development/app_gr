// src/app/(app)/credito/workflows/[id]/editor/_components/NodeInspector.tsx
//
// Inspector lateral do editor — quando o usuario seleciona uma etapa no
// canvas, mostra forms DEDICADOS por tipo (sem JSON cru).
//
// Despacho por nodeType:
//   - human_input          → FieldsBuilder
//   - document_request     → DocumentsBuilder
//   - specialist_agent     → AgentInspector (nome + criterios + avancado)
//   - conditional_branch   → ConditionBuilder (config.expression)
//   - bureau_query         → BureauInspector (adapter dropdown)
//   - http_request         → HttpInspector (url + method + body — Fase 2)
//   - default              → ConfigForm generico (nao-JSON quando possivel)
//
// O JSON cru ainda existe num <details> "Avancado" como escape hatch — mas
// nao e o caminho default.

"use client"

import * as React from "react"
import { type Edge, type Node } from "@xyflow/react"
import { RiExternalLinkLine, RiInformationLine } from "@remixicon/react"

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
import {
  type AgentMeta,
  type NodeConfigField,
  type NodeTypeMeta,
} from "@/lib/credito-client"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

import {
  AGENT_FRIENDLY_LABEL,
  AGENT_SECTION_ID,
  ETAPA_LABEL,
  getEtapaLabel,
} from "../_lib/glossary"
import { DATA_PRODUCT_PALETTE, OFFICIAL_DOCUMENT_PALETTE } from "../_lib/etapas"

import { AgentInputBindingsField } from "./AgentInputBindingsField"
import { ContractBlock } from "./NodeContract"
import { ConditionBuilder } from "./ConditionBuilder"
import {
  ConsolidatorBuilder,
  type ConsolidatorOutputField,
} from "./ConsolidatorBuilder"
import { DocumentsBuilder } from "./DocumentsBuilder"
import { FieldsBuilder, type FieldDef } from "./FieldsBuilder"
import type { StrataNodeData } from "./StrataNode"
import { RefField } from "./RefField"

// ─── Props ──────────────────────────────────────────────────────────────

type Props = {
  selectedNode: Node | null
  nodes: Node[]
  edges: Edge[]
  nodeTypes: NodeTypeMeta[]
  /** Catalogo per-agent vindo de GET /credito/agent-catalog.
   *  Quando o node selecionado e specialist_agent e o agente declara
   *  inputs[], o inspector renderiza AgentInputBindingsField para o user
   *  ligar cada slot a uma variavel upstream. */
  agentCatalog: AgentMeta[]
  /** Map { nodeId: { varName: vartype } } vindo do /workflows/_validate.
   *  Usado pelo VariablePicker pra listar variáveis upstream tipadas
   *  ao usuário no entity_ref do bureau, expression do branch, etc. */
  producedByNode: Record<string, Record<string, string>>
  onUpdateConfig: (nodeId: string, config: Record<string, unknown>) => void
  onUpdateLabel: (nodeId: string, label: string) => void
  /** Atualiza a semantica de fan-in do node ("all" = espera todas;
   *  "any" = qualquer parent dispara). Field so aparece quando o node
   *  tem 2+ incoming edges. */
  onUpdateJoinMode: (nodeId: string, joinMode: "any" | "all") => void
}

// ─── Main ───────────────────────────────────────────────────────────────

export function NodeInspector({
  selectedNode,
  nodes,
  edges,
  nodeTypes,
  agentCatalog,
  producedByNode,
  onUpdateConfig,
  onUpdateLabel,
  onUpdateJoinMode,
}: Props) {
  if (!selectedNode) return <EmptyInspector />

  const data = selectedNode.data as unknown as StrataNodeData
  const meta = nodeTypes.find((nt) => nt.type === data.nodeType)
  const etapaLabel = getEtapaLabel(data.nodeType, data.config ?? {})

  // Fan-in: se o node selecionado tem 2+ incoming edges, mostra o campo
  // de semantica de junção (all/any). Com 0 ou 1 parent o campo nao
  // se aplica.
  const incomingEdges = edges.filter((e) => e.target === selectedNode.id)
  const showJoinMode = incomingEdges.length >= 2
  const parentNodeTypes = incomingEdges.map((e) => {
    const parent = nodes.find((n) => n.id === e.source)
    return (parent?.data as StrataNodeData | undefined)?.nodeType
  })
  // Hint contextual: se algum parent vem de uma decisao (conditional_branch
  // ou human_review), o caso e quase sempre "convergencia de decisao", onde
  // o usuario provavelmente quer "Qualquer". Mostra nota soft, sem auto-flip.
  const hasDecisionParent = parentNodeTypes.some(
    (t) => t === "conditional_branch" || t === "human_review",
  )

  return (
    <div className="space-y-4">
      <div>
        <p className={cx(tableTokens.header, "mb-1")}>Etapa selecionada</p>
        <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
          {etapaLabel}
        </p>
        {meta?.description && (
          <p className={cx(tableTokens.cellSecondary, "mt-1")}>
            {meta.description}
          </p>
        )}
      </div>

      {/* Contrato da etapa — RECEBE → FAZ → PUBLICA (F1, mesma fonte do
          hover no canvas). PUBLICA vem do produced_by_node da validação. */}
      <ContractBlock
        nodeType={data.nodeType}
        config={data.config ?? {}}
        agentCatalog={agentCatalog}
        producedVars={producedByNode[selectedNode.id]}
        graphNodes={nodes.map((n) => n.data as Record<string, unknown>)}
      />

      <div>
        <Label htmlFor="node-label" className="text-xs">
          Nome da etapa
        </Label>
        <Input
          id="node-label"
          value={data.label}
          onChange={(e) => onUpdateLabel(selectedNode.id, e.target.value)}
          placeholder={etapaLabel}
        />
      </div>

      {showJoinMode && (
        <JoinModeField
          value={data.joinMode ?? "all"}
          onChange={(next) => onUpdateJoinMode(selectedNode.id, next)}
          incomingCount={incomingEdges.length}
          hasDecisionParent={hasDecisionParent}
        />
      )}

      {/* Despacho por tipo de etapa */}
      <NodeConfigDispatcher
        node={selectedNode}
        nodes={nodes}
        edges={edges}
        meta={meta}
        agentCatalog={agentCatalog}
        producedByNode={producedByNode}
        onUpdateConfig={(cfg) => onUpdateConfig(selectedNode.id, cfg)}
      />
    </div>
  )
}

// ─── JoinMode field ─────────────────────────────────────────────────────
//
// Aparece SO quando o node selecionado tem 2+ incoming edges.
// Default no schema backend e "all" (espera todas). Para o caso "decisao
// convergindo num passo terminal" (ex.: aprovado/rejeitado -> notificar)
// o usuario muda para "any" (qualquer uma).

function JoinModeField({
  value,
  onChange,
  incomingCount,
  hasDecisionParent,
}: {
  value: "any" | "all"
  onChange: (next: "any" | "all") => void
  incomingCount: number
  hasDecisionParent: boolean
}) {
  return (
    <div className="space-y-2 rounded-md border border-gray-200 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-900/50">
      <div>
        <p className={tableTokens.header}>
          Quando rodar esta etapa ({incomingCount} entradas)
        </p>
        <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
          A etapa tem mais de uma anterior. Quando ela deve executar?
        </p>
      </div>
      <div className="space-y-1.5">
        <label className="flex cursor-pointer items-start gap-2 rounded-md border border-transparent p-2 hover:bg-white dark:hover:bg-gray-950">
          <input
            type="radio"
            name="join-mode"
            value="all"
            checked={value === "all"}
            onChange={() => onChange("all")}
            className="mt-0.5"
          />
          <span className="flex-1">
            <span className="text-xs font-medium text-gray-900 dark:text-gray-100">
              Esperar todas as etapas anteriores
            </span>
            <span className="mt-0.5 block text-[11px] text-gray-500 dark:text-gray-400">
              So executa quando TODAS terminarem com sucesso. Se alguma for
              pulada por uma decisao, esta tambem e pulada.
            </span>
          </span>
        </label>
        <label className="flex cursor-pointer items-start gap-2 rounded-md border border-transparent p-2 hover:bg-white dark:hover:bg-gray-950">
          <input
            type="radio"
            name="join-mode"
            value="any"
            checked={value === "any"}
            onChange={() => onChange("any")}
            className="mt-0.5"
          />
          <span className="flex-1">
            <span className="text-xs font-medium text-gray-900 dark:text-gray-100">
              Qualquer uma das etapas anteriores
            </span>
            <span className="mt-0.5 block text-[11px] text-gray-500 dark:text-gray-400">
              Executa assim que UMA terminar. Caso classico: convergencia
              depois de uma decisao (aprovado/rejeitado -&gt; notificar).
            </span>
          </span>
        </label>
      </div>
      {hasDecisionParent && value === "all" && (
        <div className="flex items-start gap-1.5 rounded-md border border-blue-200 bg-blue-50 p-2 text-[11px] text-blue-900 dark:border-blue-500/30 dark:bg-blue-500/10 dark:text-blue-200">
          <RiInformationLine
            className="mt-0.5 size-3.5 shrink-0 text-blue-700 dark:text-blue-400"
            aria-hidden
          />
          <span>
            Detectamos uma decisao entre as etapas anteriores. Voce
            provavelmente quer{" "}
            <strong>&quot;Qualquer uma&quot;</strong> — caso contrario esta
            etapa sera pulada sempre que uma das ramificacoes for tomada.
          </span>
        </div>
      )}
    </div>
  )
}

// ─── Empty / no-selection state ─────────────────────────────────────────

function EmptyInspector() {
  return (
    <div className="space-y-3">
      <p className={tableTokens.header}>Inspector</p>
      <div className="rounded-md border border-dashed border-gray-200 bg-gray-50 p-4 text-center dark:border-gray-800 dark:bg-gray-900">
        <p className={tableTokens.cellSecondary}>
          Selecione uma etapa no canvas para ver e editar.
        </p>
      </div>
    </div>
  )
}

// ─── human_review (declaração de review_of — Fase 1 / Etapa 1.3) ──────────

/** Declara QUAL análise este checkpoint homologa. Define em que estação ele se
 *  funde (sem isto, a heurística trata como checkpoint final → pode gerar o
 *  "double-Parecer"). Vazio = checkpoint final (revisa o parecer). */
function HumanReviewInspector({
  config,
  nodes,
  onUpdateConfig,
}: {
  config: Record<string, unknown>
  nodes: Node[]
  onUpdateConfig: (cfg: Record<string, unknown>) => void
}) {
  const reviewOf = (config.review_of as string | undefined) ?? ""
  const agents = Array.from(
    new Set(
      nodes
        .map((n) => n.data as unknown as StrataNodeData)
        .filter((d) => d.nodeType === "specialist_agent")
        .map((d) => (d.config?.agent as string | undefined))
        .filter((a): a is string => Boolean(a)),
    ),
  )

  const FINAL = "__final__"
  return (
    <div className="space-y-2">
      <Label className="text-xs">Revisa qual análise?</Label>
      <Select
        value={reviewOf || FINAL}
        onValueChange={(v) =>
          onUpdateConfig({ ...config, review_of: v === FINAL ? undefined : v })
        }
      >
        <SelectTrigger>
          <SelectValue placeholder="Selecione" />
        </SelectTrigger>
        <SelectContent>
          <SelectItem value={FINAL}>Parecer final (revisa o parecer)</SelectItem>
          {agents.map((a) => (
            <SelectItem key={a} value={a}>
              {AGENT_FRIENDLY_LABEL[a] ?? a}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <p className="text-[11px] leading-snug text-gray-500 dark:text-gray-400">
        Define em que estação o checkpoint se funde. Sem declaração, vira um
        &ldquo;Parecer&rdquo; solto (double-Parecer).
      </p>
    </div>
  )
}

// ─── Dispatcher ─────────────────────────────────────────────────────────

function NodeConfigDispatcher({
  node,
  nodes,
  edges,
  meta,
  agentCatalog,
  producedByNode,
  onUpdateConfig,
}: {
  node: Node
  nodes: Node[]
  edges: Edge[]
  meta: NodeTypeMeta | undefined
  agentCatalog: AgentMeta[]
  producedByNode: Record<string, Record<string, string>>
  onUpdateConfig: (cfg: Record<string, unknown>) => void
}) {
  const data = node.data as unknown as StrataNodeData
  const config = data.config ?? {}

  switch (data.nodeType) {
    case "human_input":
      return (
        <HumanInputInspector
          config={config}
          onUpdateConfig={onUpdateConfig}
          schema={meta?.config_schema ?? []}
        />
      )

    case "document_request":
      return (
        <DocumentRequestInspector config={config} onUpdateConfig={onUpdateConfig} />
      )

    case "specialist_agent":
    case "document_extractor":
      return (
        <AgentInspector
          nodeId={node.id}
          data={data}
          nodes={nodes}
          edges={edges}
          agentCatalog={agentCatalog}
          onUpdateConfig={onUpdateConfig}
        />
      )

    case "conditional_branch":
      return (
        <ConditionalBranchInspector
          nodeId={node.id}
          config={config}
          nodes={nodes}
          edges={edges}
          onUpdateConfig={onUpdateConfig}
        />
      )

    case "bureau_query":
      return (
        <BureauInspector
          nodeId={node.id}
          config={config}
          nodes={nodes}
          edges={edges}
          producedByNode={producedByNode}
          onUpdateConfig={onUpdateConfig}
        />
      )

    case "official_document_fetch":
      return (
        <OfficialDocumentInspector
          config={config}
          onUpdateConfig={onUpdateConfig}
        />
      )

    case "consolidator":
      return (
        <ConsolidatorInspector
          nodeId={node.id}
          config={config}
          nodes={nodes}
          edges={edges}
          onUpdateConfig={onUpdateConfig}
        />
      )

    case "human_review":
      return (
        <HumanReviewInspector config={config} nodes={nodes} onUpdateConfig={onUpdateConfig} />
      )

    default:
      // Fallback: ConfigForm generico (substitui JSON quando possivel).
      return (
        <ConfigForm
          configSchema={meta?.config_schema ?? []}
          config={config}
          onChange={onUpdateConfig}
        />
      )
  }
}

// ═══════════════════════════════════════════════════════════════════════
// Inspectors especificos por tipo de etapa
// ═══════════════════════════════════════════════════════════════════════

// ─── human_input ────────────────────────────────────────────────────────

function HumanInputInspector({
  config,
  onUpdateConfig,
  schema,
}: {
  config: Record<string, unknown>
  onUpdateConfig: (cfg: Record<string, unknown>) => void
  schema: NodeConfigField[]
}) {
  const fields = (config.fields as FieldDef[] | undefined) ?? []

  // Outros campos do schema (ex.: title, description) viram inputs simples.
  const otherFields = schema.filter((s) => s.key !== "fields")

  return (
    <div className="space-y-4">
      {otherFields.map((f) => (
        <SimpleConfigField
          key={f.key}
          field={f}
          value={config[f.key]}
          onChange={(v) => onUpdateConfig({ ...config, [f.key]: v })}
        />
      ))}
      <FieldsBuilder
        value={fields}
        onChange={(next) => onUpdateConfig({ ...config, fields: next })}
      />
      <AdvancedJsonToggle config={config} onUpdateConfig={onUpdateConfig} />
    </div>
  )
}

// ─── document_request ───────────────────────────────────────────────────

function DocumentRequestInspector({
  config,
  onUpdateConfig,
}: {
  config: Record<string, unknown>
  onUpdateConfig: (cfg: Record<string, unknown>) => void
}) {
  const required = Array.isArray(config.required)
    ? (config.required as string[])
    : []
  const optional = Array.isArray(config.optional)
    ? (config.optional as string[])
    : []

  return (
    <div className="space-y-4">
      <DocumentsBuilder
        required={required}
        optional={optional}
        onChange={(next) =>
          onUpdateConfig({
            ...config,
            required: next.required,
            optional: next.optional,
          })
        }
      />
      <AdvancedJsonToggle config={config} onUpdateConfig={onUpdateConfig} />
    </div>
  )
}

// ─── specialist_agent / document_extractor ──────────────────────────────

function AgentInspector({
  nodeId,
  data,
  nodes,
  edges,
  agentCatalog,
  onUpdateConfig,
}: {
  nodeId: string
  data: StrataNodeData
  nodes: Node[]
  edges: Edge[]
  agentCatalog: AgentMeta[]
  onUpdateConfig: (cfg: Record<string, unknown>) => void
}) {
  const config = data.config ?? {}
  const agent = config.agent as string | undefined
  const sectionId = agent ? AGENT_SECTION_ID[agent] : undefined
  const friendlyLabel = agent ? AGENT_FRIENDLY_LABEL[agent] : undefined
  // Quando o agente declara inputs[] no catalog (Phase A), renderiza
  // AgentInputBindingsField. Senao (legacy) mantem so o link de criterios.
  const agentMeta = agent ? agentCatalog.find((a) => a.name === agent) : undefined
  const inputBindings =
    (config.input_bindings as Record<string, string> | undefined) ?? {}

  return (
    <div className="space-y-4">
      <div>
        <p className={tableTokens.header}>Agente IA</p>
        <p className="mt-1 text-sm font-medium text-gray-900 dark:text-gray-100">
          {friendlyLabel ?? agent ?? "(nao configurado)"}
        </p>
        {agent && (
          <code className="mt-0.5 inline-block rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[11px] text-gray-700 dark:bg-gray-900 dark:text-gray-300">
            {agent}
          </code>
        )}
      </div>

      {agentMeta && agentMeta.inputs.length > 0 && (
        <AgentInputBindingsField
          agent={agentMeta}
          value={inputBindings}
          onChange={(next) =>
            onUpdateConfig({ ...config, input_bindings: next })
          }
          targetNodeId={nodeId}
          nodes={nodes}
          edges={edges}
        />
      )}

      {agent && sectionId && data.nodeType === "specialist_agent" && (
        <CriteriosLink sectionId={sectionId} agentLabel={friendlyLabel ?? agent} />
      )}

      {data.nodeType === "document_extractor" && (
        <div className="rounded-md border border-blue-200 bg-blue-50 p-3 text-xs dark:border-blue-500/30 dark:bg-blue-500/10">
          <div className="flex items-start gap-2">
            <RiInformationLine
              className="mt-0.5 size-4 shrink-0 text-blue-700 dark:text-blue-400"
              aria-hidden
            />
            <div className="text-blue-900 dark:text-blue-200">
              <p className="font-medium">Templates de extracao</p>
              <p className="mt-1">
                A IA escolhe o template correto pra cada documento uploadado.
                Gerencie os templates em{" "}
                <a
                  href="/credito/templates"
                  target="_blank"
                  className="underline hover:text-blue-700 dark:hover:text-blue-300"
                >
                  Templates de extracao
                  <RiExternalLinkLine className="-mt-0.5 ml-0.5 inline size-3" aria-hidden />
                </a>
                .
              </p>
            </div>
          </div>
        </div>
      )}

      <AdvancedConfigSection
        title="Mais opcoes"
        config={config}
        onUpdateConfig={onUpdateConfig}
        excludeKeys={["agent"]}
      />
    </div>
  )
}

function CriteriosLink({
  sectionId,
  agentLabel,
}: {
  sectionId: string
  agentLabel: string
}) {
  return (
    <div className="rounded-md border border-blue-200 bg-blue-50 p-3 text-xs dark:border-blue-500/30 dark:bg-blue-500/10">
      <div className="flex items-start gap-2">
        <RiInformationLine
          className="mt-0.5 size-4 shrink-0 text-blue-700 dark:text-blue-400"
          aria-hidden
        />
        <div className="text-blue-900 dark:text-blue-200">
          <p className="font-medium">Criterios desta analise</p>
          <p className="mt-1">
            A IA recebe automaticamente os criterios que o tenant cadastrou para
            esta secao. Edite em{" "}
            <a
              href={`/credito/checklist?section=${sectionId}`}
              target="_blank"
              className="underline hover:text-blue-700 dark:hover:text-blue-300"
            >
              Criterios de {agentLabel}
              <RiExternalLinkLine className="-mt-0.5 ml-0.5 inline size-3" aria-hidden />
            </a>
            .
          </p>
        </div>
      </div>
    </div>
  )
}

// ─── conditional_branch ─────────────────────────────────────────────────

function ConditionalBranchInspector({
  nodeId,
  config,
  nodes,
  edges,
  onUpdateConfig,
}: {
  nodeId: string
  config: Record<string, unknown>
  nodes: Node[]
  edges: Edge[]
  onUpdateConfig: (cfg: Record<string, unknown>) => void
}) {
  const expression = (config.expression as string | undefined) ?? null

  return (
    <div className="space-y-4">
      <div>
        <p className={tableTokens.header}>Decisao</p>
        <p className={cx(tableTokens.cellSecondary, "mt-1")}>
          Define uma condicao que avalia o caminho a seguir no playbook.
        </p>
      </div>
      <ConditionBuilder
        value={expression}
        onChange={(next) => onUpdateConfig({ ...config, expression: next })}
        targetNodeId={nodeId}
        nodes={nodes}
        edges={edges}
        hint="Etapas conectadas apos esta vao receber o resultado da decisao."
      />
      <AdvancedJsonToggle config={config} onUpdateConfig={onUpdateConfig} />
    </div>
  )
}

// ─── consolidator ───────────────────────────────────────────────────────

function ConsolidatorInspector({
  nodeId,
  config,
  nodes,
  edges,
  onUpdateConfig,
}: {
  nodeId: string
  config: Record<string, unknown>
  nodes: Node[]
  edges: Edge[]
  onUpdateConfig: (cfg: Record<string, unknown>) => void
}) {
  const outputFields =
    (config.output_fields as ConsolidatorOutputField[] | undefined) ?? []

  return (
    <div className="space-y-4">
      <div>
        <p className={tableTokens.header}>Consolidador</p>
        <p className={cx(tableTokens.cellSecondary, "mt-1")}>
          Combina dados das etapas anteriores em saidas estruturadas. Sem IA —
          regra fixa.
        </p>
      </div>
      <ConsolidatorBuilder
        value={outputFields}
        onChange={(next) =>
          onUpdateConfig({ ...config, output_fields: next })
        }
        targetNodeId={nodeId}
        nodes={nodes}
        edges={edges}
      />
      <AdvancedJsonToggle config={config} onUpdateConfig={onUpdateConfig} />
    </div>
  )
}

// ─── official_document_fetch ────────────────────────────────────────────
//
// O usuario escolhe o DOCUMENTO (receita curada), nao datasets crus. Lista
// vem do `OFFICIAL_DOCUMENT_PALETTE` em `_lib/etapas.ts` — fonte unica de
// verdade pra palette + inspector (espelha RECIPES no backend).

function OfficialDocumentInspector({
  config,
  onUpdateConfig,
}: {
  config: Record<string, unknown>
  onUpdateConfig: (cfg: Record<string, unknown>) => void
}) {
  const selectedKey = (config.document as string | undefined) ?? ""
  const selectedEntry = OFFICIAL_DOCUMENT_PALETTE.find((r) => r.key === selectedKey)

  return (
    <div className="space-y-4">
      <div>
        <Label htmlFor="official-document" className="text-xs">
          Documento <span className="ml-0.5 text-red-600">*</span>
        </Label>
        <Select
          value={selectedKey}
          onValueChange={(key) => onUpdateConfig({ ...config, document: key })}
        >
          <SelectTrigger id="official-document">
            <SelectValue placeholder="Selecione o documento" />
          </SelectTrigger>
          <SelectContent>
            {OFFICIAL_DOCUMENT_PALETTE.map((r) => (
              <SelectItem key={r.key} value={r.key}>
                {r.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {selectedEntry && (
          <p className={cx(tableTokens.cellSecondary, "mt-1")}>
            {selectedEntry.description}
          </p>
        )}
      </div>

      <div className="rounded-md border border-blue-200 bg-blue-50 p-3 text-xs dark:border-blue-500/30 dark:bg-blue-500/10">
        <div className="flex items-start gap-2">
          <RiInformationLine
            className="mt-0.5 size-3.5 shrink-0 text-blue-600 dark:text-blue-400"
            aria-hidden
          />
          <p className="text-blue-800 dark:text-blue-200">
            O documento baixado entra no dossie no mesmo fluxo de conferencia
            do upload manual (extracao multimodal + revisao do analista). Se a
            empresa nao for localizada na fonte, a etapa conclui com{" "}
            <code>found=false</code> — sem travar o fluxo.
          </p>
        </div>
      </div>
    </div>
  )
}

// ─── bureau_query ───────────────────────────────────────────────────────
//
// Lista de consultas vem do `DATA_PRODUCT_PALETTE` em `_lib/etapas.ts` —
// fonte unica de verdade pra palette + inspector.
//
// Hoje so Serasa PJ esta wired; os 4 produtos nomeados (Dados Basicos RFB,
// Processos Detalhado, Protestos Detalhado, Relacionamento PJ) sao
// placeholders pra fontes futuras.

const ENVIRONMENT_OPTIONS = [
  { value: "production", label: "Producao (consulta real, gera custo)" },
  { value: "sandbox",    label: "Sandbox (mock, sem custo)" },
]

/** Determina qual entry da palette bate com o config atual. */
function inferSelectedKey(config: Record<string, unknown>): string {
  const dataProduct = config.data_product as string | undefined
  if (dataProduct) {
    const match = DATA_PRODUCT_PALETTE.find((p) => p.config.data_product === dataProduct)
    if (match) return match.key
  }
  const adapter = config.adapter as string | undefined
  if (adapter) {
    const match = DATA_PRODUCT_PALETTE.find(
      (p) => p.config.adapter === adapter && !p.config.data_product,
    )
    if (match) return match.key
  }
  return ""
}

function BureauInspector({
  nodeId,
  config,
  nodes,
  edges,
  producedByNode,
  onUpdateConfig,
}: {
  nodeId: string
  config: Record<string, unknown>
  nodes: Node[]
  edges: Edge[]
  producedByNode: Record<string, Record<string, string>>
  onUpdateConfig: (cfg: Record<string, unknown>) => void
}) {
  const entityRef = (config.entity_ref as string | undefined) ?? ""
  const environment = (config.environment as string | undefined) ?? "production"

  // Tipo esperado depende do adapter selecionado: serasa_pj/bigdata/infosimples → CNPJ;
  // serasa_pf → CPF. Mapa espelha _ADAPTER_INPUT_TYPE em backend.
  const adapter = config.adapter as string | undefined
  const expectedType =
    adapter === "serasa_pf"
      ? "cpf"
      : adapter && ["serasa_pj", "bigdatacorp", "infosimples"].includes(adapter)
        ? "cnpj"
        : undefined

  const selectedKey = inferSelectedKey(config)
  const selectedEntry = DATA_PRODUCT_PALETTE.find((p) => p.key === selectedKey)

  function pickEntry(key: string) {
    const entry = DATA_PRODUCT_PALETTE.find((p) => p.key === key)
    if (!entry) return
    // Aplica o config do entry mas preserva entity_ref/environment se ja
    // estavam customizados pelo usuario.
    onUpdateConfig({
      ...entry.config,
      entity_ref: entityRef || entry.config.entity_ref,
      environment: environment || entry.config.environment,
    })
  }

  return (
    <div className="space-y-4">
      <div>
        <Label htmlFor="data-product" className="text-xs">
          Consulta <span className="ml-0.5 text-red-600">*</span>
        </Label>
        <Select value={selectedKey} onValueChange={pickEntry}>
          <SelectTrigger id="data-product">
            <SelectValue placeholder="Selecione a consulta" />
          </SelectTrigger>
          <SelectContent>
            {DATA_PRODUCT_PALETTE.map((p) => (
              <SelectItem key={p.key} value={p.key} disabled={!p.available}>
                {p.label}
                {!p.available && (
                  <span className="ml-1 text-[10px] text-gray-500">(em breve)</span>
                )}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {selectedEntry && (
          <p className={cx(tableTokens.cellSecondary, "mt-1")}>
            {selectedEntry.description}
          </p>
        )}
      </div>

      <div>
        <Label htmlFor="bureau-entity" className="text-xs">
          {expectedType === "cpf" ? "CPF" : "CNPJ"} a consultar{" "}
          <span className="ml-0.5 text-red-600">*</span>
        </Label>
        <RefField
          selectedNodeId={nodeId}
          nodes={nodes}
          edges={edges}
          producedByNode={producedByNode}
          filterType={expectedType}
          value={entityRef}
          onChange={(next) => onUpdateConfig({ ...config, entity_ref: next })}
          placeholder={
            expectedType === "cpf" ? "000.000.000-00" : "00.000.000/0000-00"
          }
          expectedTypeLabel={expectedType === "cpf" ? "CPF" : "CNPJ"}
        />
        <p className={cx(tableTokens.cellSecondary, "mt-1")}>
          Escolha uma variavel ja produzida por uma etapa anterior (ex.: o
          CNPJ que o analista preencheu no formulario) ou digite o valor
          direto.
        </p>
      </div>

      <div>
        <Label htmlFor="bureau-env" className="text-xs">
          Ambiente
        </Label>
        <Select
          value={environment}
          onValueChange={(v) => onUpdateConfig({ ...config, environment: v })}
        >
          <SelectTrigger id="bureau-env">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ENVIRONMENT_OPTIONS.map((e) => (
              <SelectItem key={e.value} value={e.value}>
                {e.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="rounded-md border border-blue-200 bg-blue-50 p-3 text-xs dark:border-blue-500/30 dark:bg-blue-500/10">
        <div className="flex items-start gap-2">
          <RiInformationLine
            className="mt-0.5 size-4 shrink-0 text-blue-700 dark:text-blue-400"
            aria-hidden
          />
          <div className="text-blue-900 dark:text-blue-200">
            <p className="font-medium">Saida desta etapa</p>
            <p className="mt-1">
              A consulta gera um <code className="font-mono">consulta_id</code>{" "}
              e contadores agregados (socios, restricoes, protestos, etc.).
              Etapas seguintes (analises IA) podem ler os detalhes completos
              via esse ID.
            </p>
          </div>
        </div>
      </div>

      <AdvancedJsonToggle config={config} onUpdateConfig={onUpdateConfig} />
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════
// Helpers genericos (escape hatch + simple inputs)
// ═══════════════════════════════════════════════════════════════════════

function SimpleConfigField({
  field,
  value,
  onChange,
}: {
  field: NodeConfigField
  value: unknown
  onChange: (v: unknown) => void
}) {
  const id = `field-${field.key}`
  const labelEl = (
    <Label htmlFor={id} className="text-xs">
      {field.label}
      {field.required && <span className="ml-0.5 text-red-600">*</span>}
    </Label>
  )

  if (field.type === "text") {
    return (
      <div>
        {labelEl}
        <Textarea
          id={id}
          rows={3}
          placeholder={field.placeholder}
          value={(value as string) ?? ""}
          onChange={(e) => onChange(e.target.value)}
        />
      </div>
    )
  }

  if (field.type === "number") {
    return (
      <div>
        {labelEl}
        <Input
          id={id}
          type="number"
          placeholder={field.placeholder}
          value={(value as number | undefined) ?? ""}
          onChange={(e) =>
            onChange(e.target.value === "" ? undefined : Number(e.target.value))
          }
        />
      </div>
    )
  }

  if (field.type === "boolean") {
    return (
      <label className="flex items-center gap-2 text-xs">
        <input
          type="checkbox"
          className="rounded"
          checked={Boolean(value)}
          onChange={(e) => onChange(e.target.checked)}
        />
        {field.label}
      </label>
    )
  }

  return (
    <div>
      {labelEl}
      <Input
        id={id}
        placeholder={field.placeholder}
        value={(value as string) ?? ""}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  )
}

function ConfigForm({
  configSchema,
  config,
  onChange,
}: {
  configSchema: NodeConfigField[]
  config: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
}) {
  if (configSchema.length === 0) {
    return (
      <details className="rounded-md border border-gray-200 dark:border-gray-800">
        <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-gray-700 dark:text-gray-300">
          Configuracao avancada (JSON)
        </summary>
        <RawJsonEditor value={config} onChange={onChange} />
      </details>
    )
  }

  return (
    <div className="space-y-3">
      <p className={tableTokens.header}>Configuracao</p>
      {configSchema.map((field) => (
        <SimpleConfigField
          key={field.key}
          field={field}
          value={config[field.key]}
          onChange={(v) => onChange({ ...config, [field.key]: v })}
        />
      ))}
      <AdvancedJsonToggle config={config} onUpdateConfig={onChange} />
    </div>
  )
}

function AdvancedConfigSection({
  title,
  config,
  onUpdateConfig,
  excludeKeys,
}: {
  title: string
  config: Record<string, unknown>
  onUpdateConfig: (cfg: Record<string, unknown>) => void
  excludeKeys: string[]
}) {
  const filtered = Object.entries(config).filter(
    ([k]) => !excludeKeys.includes(k),
  )
  if (filtered.length === 0) {
    return <AdvancedJsonToggle config={config} onUpdateConfig={onUpdateConfig} />
  }
  return (
    <details className="rounded-md border border-gray-200 dark:border-gray-800">
      <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-gray-700 dark:text-gray-300">
        {title}
      </summary>
      <div className="border-t border-gray-200 p-2 dark:border-gray-800">
        <RawJsonEditor value={config} onChange={onUpdateConfig} />
      </div>
    </details>
  )
}

function AdvancedJsonToggle({
  config,
  onUpdateConfig,
}: {
  config: Record<string, unknown>
  onUpdateConfig: (cfg: Record<string, unknown>) => void
}) {
  return (
    <details className="rounded-md border border-gray-200 dark:border-gray-800">
      <summary className="cursor-pointer px-3 py-2 text-[11px] font-medium text-gray-500 dark:text-gray-400">
        Avancado (editar JSON cru)
      </summary>
      <RawJsonEditor value={config} onChange={onUpdateConfig} />
    </details>
  )
}

function RawJsonEditor({
  value,
  onChange,
}: {
  value: Record<string, unknown>
  onChange: (next: Record<string, unknown>) => void
}) {
  const [draft, setDraft] = React.useState(() => JSON.stringify(value, null, 2))
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    setDraft(JSON.stringify(value, null, 2))
  }, [value])

  return (
    <div className="border-t border-gray-200 p-2 dark:border-gray-800">
      <Textarea
        rows={8}
        value={draft}
        onChange={(e) => {
          setDraft(e.target.value)
          setError(null)
        }}
        className="font-mono text-[11px]"
      />
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
      <Button
        type="button"
        variant="secondary"
        className="mt-2 w-full"
        onClick={() => {
          try {
            const parsed = JSON.parse(draft)
            if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
              setError("Config deve ser um objeto JSON.")
              return
            }
            onChange(parsed as Record<string, unknown>)
            setError(null)
          } catch (e) {
            setError(`JSON invalido: ${(e as Error).message}`)
          }
        }}
      >
        Aplicar JSON
      </Button>
    </div>
  )
}

// Re-export for callers that need it.
export { ETAPA_LABEL }
