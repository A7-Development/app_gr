// src/app/(app)/credito/workflows/[id]/editor/_components/StrataNode.tsx
//
// Custom React Flow node — etapa do fluxo no canvas.
//
// Layout:
//   ┌──────────────────────────────────┐
//   │ ● [icon]  Tipo da etapa          │   ← etapa em vocabulario amigavel
//   │   <Nome dado pelo usuario>       │
//   │   <subtitle: agente/expressao>   │
//   └──────────────────────────────────┘
//   handles em cima (target) e em baixo (source)
//
// Validacao visual: quando `data.validationStatus` for "error" ou "warning",
// renderiza um halo colorido + icone de alerta no canto superior direito.

"use client"

import * as React from "react"
import {
  Handle,
  Position,
  useEdges,
  useNodeId,
  type NodeProps,
} from "@xyflow/react"
import {
  RiAlertLine,
  RiCheckboxCircleLine,
  RiDatabase2Line,
  RiEditLine,
  RiErrorWarningLine,
  RiFilePdf2Line,
  RiFileSearchLine,
  RiGitBranchLine,
  RiGlobalLine,
  RiGovernmentLine,
  RiNotification3Line,
  RiPlayCircleLine,
  RiRobot2Line,
  RiUploadCloud2Line,
  type RemixiconComponentType,
} from "@remixicon/react"

import { type NodeTypeMeta } from "@/lib/credito-client"
import { varTypeMeta } from "@/design-system/tokens/var-type"
import { cx } from "@/lib/utils"

import { AGENT_FRIENDLY_LABEL, ETAPA_LABEL, getEtapaLabel } from "../_lib/glossary"
import { OFFICIAL_DOCUMENT_PALETTE, primitiveTypeFor } from "../_lib/etapas"
import { AgentCatalogContext, NodeContractHover } from "./NodeContract"

const ICON_MAP: Record<string, RemixiconComponentType> = {
  RiPlayCircleLine,
  RiEditLine,
  RiCheckboxCircleLine,
  RiUploadCloud2Line,
  RiFileSearchLine,
  RiDatabase2Line,
  RiRobot2Line,
  RiFilePdf2Line,
  RiGitBranchLine,
  RiGlobalLine,
  RiGovernmentLine,
  RiNotification3Line,
}

export type ValidationStatus = "ok" | "warning" | "error"

export type StrataNodeData = {
  label: string
  nodeType: string
  config: Record<string, unknown>
  meta?: NodeTypeMeta
  validationStatus?: ValidationStatus
  validationMessage?: string
  /** Map { var_name: vartype_str } do que este nó publica em runtime.
   *  Vem de SemanticValidationResult.produced_by_node (Fase 2/3a).
   *  Renderizado como chips coloridos no rodapé do nó. */
  producedVars?: Record<string, string>
  /** F3 — papel na linhagem do node selecionado: feeder (me alimenta, azul),
   *  consumer (consome meu output, verde), dim (sem relacao de dado). */
  lineageRole?: "feeder" | "consumer" | "dim"
  /** Variaveis que fluem entre este node e o selecionado. */
  lineageVars?: string[]
  /** Fan-in semantics quando o node tem 2+ incoming edges.
   *  "all" = espera todas as etapas anteriores; "any" = qualquer uma dispara.
   *  Default backend: "all". Renderizado como badge no header so quando
   *  o node de fato tem 2+ incoming (caso contrario o campo nao se aplica). */
  joinMode?: "any" | "all"
}

export function StrataNode({ data, selected }: NodeProps) {
  const d = data as unknown as StrataNodeData
  const meta = d.meta
  // Contrato RECEBE→FAZ→PUBLICA no hover (F1) — catálogo via context pra não
  // inflar o data de cada node.
  const agentCatalog = React.useContext(AgentCatalogContext)
  const Icon = meta ? ICON_MAP[meta.icon] ?? RiRobot2Line : RiRobot2Line
  // Tile colorido por TIPO de primitivo (agente/check/externo/...), mesma
  // linguagem de cor da palette — quem aprende "violeta = agente" na palette
  // le o tile violeta no canvas como agente.
  const colorBg = primitiveTypeFor(d.nodeType, meta?.category).bar

  const friendlyTypeLabel = ETAPA_LABEL[d.nodeType] ?? meta?.label ?? d.nodeType
  const subtitle = pickSubtitle(d)
  const status = d.validationStatus ?? "ok"

  // Fan-in: conta incoming edges para decidir se mostra badge AND/OR.
  // Badge so faz sentido quando ha 2+ parents (com 1 parent, join_mode e moot).
  const nodeId = useNodeId()
  const edges = useEdges()
  const incomingCount = React.useMemo(
    () => (nodeId ? edges.filter((e) => e.target === nodeId).length : 0),
    [edges, nodeId],
  )
  const showJoinBadge = incomingCount >= 2
  const joinMode = d.joinMode ?? "all"

  return (
    <NodeContractHover
      nodeType={d.nodeType}
      config={d.config ?? {}}
      agentCatalog={agentCatalog}
      producedVars={d.producedVars}
      title={d.label || friendlyTypeLabel}
    >
    <div
      data-validation={status}
      className={cx(
        "relative min-w-[180px] max-w-[260px] rounded-md border bg-white shadow-sm transition-all dark:bg-gray-950",
        selected
          ? "border-blue-500 shadow-md"
          : status === "error"
            ? "border-red-400 dark:border-red-500/60"
            : status === "warning"
              ? "border-amber-400 dark:border-amber-500/60"
              : "border-gray-200 dark:border-gray-800",
        // F3 — linhagem do selecionado: quem alimenta (azul) / quem consome
        // (verde) ganha anel; sem relacao de dado esmaece.
        d.lineageRole === "feeder" && "ring-2 ring-blue-400/70 dark:ring-blue-500/50",
        d.lineageRole === "consumer" &&
          "ring-2 ring-emerald-400/70 dark:ring-emerald-500/50",
        d.lineageRole === "dim" && "opacity-35",
      )}
      title={d.validationMessage ?? undefined}
    >
      {(d.lineageRole === "feeder" || d.lineageRole === "consumer") &&
        (d.lineageVars?.length ?? 0) > 0 && (
          <span
            className={cx(
              "absolute -top-2 left-2 z-10 rounded px-1.5 py-px text-[9px] font-semibold shadow-sm",
              d.lineageRole === "feeder"
                ? "bg-blue-600 text-white"
                : "bg-emerald-600 text-white",
            )}
            title={
              d.lineageRole === "feeder"
                ? "Envia estas variaveis pro node selecionado"
                : "Consome estas variaveis do node selecionado"
            }
          >
            {d.lineageRole === "feeder" ? "envia → " : "← consome "}
            {d.lineageVars?.slice(0, 3).join(", ")}
            {(d.lineageVars?.length ?? 0) > 3 ? "…" : ""}
          </span>
        )}
      {/* 4 handles de conexão — um em cada lado. Todos `source` + ReactFlow
       *  configurado com `connectionMode=Loose` (no page.tsx) permite que
       *  qualquer handle se conecte a qualquer outro, independente do tipo.
       *  Resultado: usuário arrasta de qualquer lado pra qualquer lado. */}
      <Handle
        id="top"
        type="source"
        position={Position.Top}
        className="!size-2.5 !-translate-y-1/2 !border !border-white !bg-gray-400 hover:!bg-blue-500 dark:!border-gray-950 dark:!bg-gray-600"
      />
      <Handle
        id="right"
        type="source"
        position={Position.Right}
        className="!size-2.5 !translate-x-1/2 !border !border-white !bg-gray-400 hover:!bg-blue-500 dark:!border-gray-950 dark:!bg-gray-600"
      />

      {status !== "ok" && (
        <span
          className={cx(
            "absolute -right-1.5 -top-1.5 flex size-4 items-center justify-center rounded-full text-white shadow-sm",
            status === "error" ? "bg-red-500" : "bg-amber-500",
          )}
          title={d.validationMessage ?? undefined}
          aria-label={status === "error" ? "Erro" : "Atencao"}
        >
          {status === "error" ? (
            <RiErrorWarningLine className="size-3" aria-hidden />
          ) : (
            <RiAlertLine className="size-3" aria-hidden />
          )}
        </span>
      )}

      <div className="flex items-center gap-2 border-b border-gray-100 px-3 py-1.5 dark:border-gray-900">
        <span
          className={cx(
            "flex size-5 items-center justify-center rounded-sm text-white",
            colorBg,
          )}
        >
          <Icon className="size-3" aria-hidden />
        </span>
        <span className="text-[10px] uppercase tracking-wider text-gray-500 dark:text-gray-400">
          {friendlyTypeLabel}
        </span>
        {showJoinBadge && (
          <span
            className={cx(
              "ml-auto rounded px-1.5 py-0.5 text-[9px] font-semibold uppercase tracking-wider",
              joinMode === "all"
                ? "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
                : "bg-blue-100 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300",
            )}
            title={
              joinMode === "all"
                ? "Espera TODAS as etapas anteriores antes de executar"
                : "Executa quando QUALQUER UMA das etapas anteriores terminar"
            }
          >
            {joinMode === "all" ? "Todas" : "Qualquer"}
          </span>
        )}
      </div>
      <div className="px-3 py-2">
        <p className="text-xs font-semibold text-gray-900 dark:text-gray-100">
          {d.label || getEtapaLabel(d.nodeType, d.config ?? {})}
        </p>
        {subtitle && (
          <p className="mt-0.5 line-clamp-2 text-[11px] text-gray-500 dark:text-gray-400">
            {subtitle}
          </p>
        )}
      </div>
      <ProducedVarsRow vars={d.producedVars} />
      <Handle
        id="bottom"
        type="source"
        position={Position.Bottom}
        className="!size-2.5 !translate-y-1/2 !border !border-white !bg-gray-400 hover:!bg-blue-500 dark:!border-gray-950 dark:!bg-gray-600"
      />
      <Handle
        id="left"
        type="source"
        position={Position.Left}
        className="!size-2.5 !-translate-x-1/2 !border !border-white !bg-gray-400 hover:!bg-blue-500 dark:!border-gray-950 dark:!bg-gray-600"
      />
    </div>
    </NodeContractHover>
  )
}

function ProducedVarsRow({
  vars,
}: {
  vars?: Record<string, string>
}) {
  if (!vars || Object.keys(vars).length === 0) return null
  // Cap em 6 chips pra nó não esticar demais; resto vira "+N".
  const entries = Object.entries(vars)
  const visible = entries.slice(0, 6)
  const overflow = entries.length - visible.length

  return (
    <div className="flex flex-wrap items-center gap-1 border-t border-gray-100 px-2 py-1.5 dark:border-gray-900">
      {visible.map(([varName, varType]) => {
        const meta = varTypeMeta(varType)
        return (
          <span
            key={varName}
            title={`${varName} · ${meta.description}`}
            className={cx(
              "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium",
              meta.chipClass,
            )}
          >
            <span
              aria-hidden
              className={cx("size-1.5 rounded-full", meta.dotClass)}
            />
            <span className="font-mono">{varName}</span>
          </span>
        )
      })}
      {overflow > 0 && (
        <span
          className="text-[10px] text-gray-500 dark:text-gray-400"
          title={`+${overflow} variável(is) — selecione o nó pra ver tudo`}
        >
          +{overflow}
        </span>
      )}
    </div>
  )
}

function pickSubtitle(d: StrataNodeData): string | null {
  const cfg = d.config ?? {}

  // Para specialist_agent, mostra o nome amigavel do agente.
  if (d.nodeType === "specialist_agent") {
    const agent = cfg.agent as string | undefined
    if (agent) {
      return AGENT_FRIENDLY_LABEL[agent] ?? agent
    }
  }

  // Para conditional_branch, mostra a expressao.
  if (d.nodeType === "conditional_branch") {
    const expr = cfg.expression as string | undefined
    if (expr) return expr.length > 60 ? `${expr.slice(0, 57)}...` : expr
  }

  // Para document_request, mostra qtd de docs.
  if (d.nodeType === "document_request") {
    const required = Array.isArray(cfg.required) ? (cfg.required as unknown[]).length : 0
    const optional = Array.isArray(cfg.optional) ? (cfg.optional as unknown[]).length : 0
    if (required + optional > 0) {
      return `${required} obrigatorio(s) · ${optional} opcional(is)`
    }
  }

  // Para human_input, mostra qtd de campos.
  if (d.nodeType === "human_input") {
    const fields = Array.isArray(cfg.fields) ? (cfg.fields as unknown[]).length : 0
    if (fields > 0) return `${fields} campo(s) no formulario`
  }

  // Para bureau_query, mostra adapter.
  if (d.nodeType === "bureau_query") {
    const adapter = cfg.adapter as string | undefined
    if (adapter) return adapter
  }

  // Para official_document_fetch, mostra a receita escolhida.
  if (d.nodeType === "official_document_fetch") {
    const document = cfg.document as string | undefined
    if (document) {
      const recipe = OFFICIAL_DOCUMENT_PALETTE.find((r) => r.key === document)
      return recipe?.label ?? document
    }
  }

  // Fallback: candidatos genericos.
  const candidates: string[] = ["url", "format", "channel"]
  for (const k of candidates) {
    const v = cfg[k]
    if (v) return `${k}: ${String(v)}`
  }
  return null
}
