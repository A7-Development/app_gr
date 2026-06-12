// src/app/(app)/credito/workflows/[id]/editor/_components/NodeContract.tsx
//
// Render do contrato "RECEBE → FAZ → PUBLICA" (F1, 2026-06-12) em dois
// contextos: bloco fixo no topo do inspector e HoverCard sobre o node no
// canvas. Mesma fonte (nodeContract + produced_by_node da validação) — quem
// aprende a ler num lugar lê no outro.

"use client"

import * as React from "react"
import * as HoverCardPrimitives from "@radix-ui/react-hover-card"
import {
  RiArrowRightDownLine,
  RiFlashlightLine,
  RiUploadLine,
  type RemixiconComponentType,
} from "@remixicon/react"

import { varTypeMeta } from "@/design-system/tokens/var-type"
import type { AgentMeta } from "@/lib/credito-client"
import { cx } from "@/lib/utils"

import { nodeContract, type ContractGraphNode } from "../_lib/contract"

/** Catálogo de agentes disponível pro canvas inteiro — o StrataNode (dentro
 *  do React Flow) lê daqui pra montar o "RECEBE" dos specialist agents sem
 *  inflar o `data` de cada node. Provider no editor page. */
export const AgentCatalogContext = React.createContext<AgentMeta[]>([])

function Row({
  icon: Icon,
  label,
  tone,
  children,
}: {
  icon: RemixiconComponentType
  label: string
  tone: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-start gap-2">
      <span
        className={cx(
          "mt-px flex w-[72px] shrink-0 items-center gap-1 text-[10px] font-semibold uppercase tracking-[0.05em]",
          tone,
        )}
      >
        <Icon className="size-3" aria-hidden />
        {label}
      </span>
      <div className="min-w-0 flex-1 text-xs leading-relaxed text-gray-700 dark:text-gray-300">
        {children}
      </div>
    </div>
  )
}

function VarChip({ name, type }: { name: string; type: string }) {
  const meta = varTypeMeta(type)
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded px-1.5 py-px text-[10px] font-medium",
        meta.chipClass,
      )}
      title={meta.label}
    >
      {name}
    </span>
  )
}

export function ContractBlock({
  nodeType,
  config,
  agentCatalog,
  producedVars,
  graphNodes,
  compact = false,
}: {
  nodeType: string
  config: Record<string, unknown>
  agentCatalog: AgentMeta[]
  /** { varName: vartype } vindo da validação semântica (produces() real). */
  producedVars?: Record<string, string>
  /** Grafo atual — permite ao contrato nomear a etapa que publica a
   *  variável consumida (mesma palavra/cor nas duas pontas). */
  graphNodes?: ContractGraphNode[]
  compact?: boolean
}) {
  const contract = nodeContract(nodeType, config, agentCatalog, graphNodes)
  const recebeVars = Object.entries(contract.recebeVars ?? {})
  const vars = Object.entries(producedVars ?? {})

  return (
    <div
      className={cx(
        "space-y-1.5 rounded-md border border-gray-200 bg-gray-50/70 p-2.5 dark:border-gray-800 dark:bg-gray-900/40",
        compact && "border-0 bg-transparent p-0 dark:bg-transparent",
      )}
    >
      <Row
        icon={RiArrowRightDownLine}
        label="Recebe"
        tone="text-blue-600 dark:text-blue-400"
      >
        {recebeVars.length > 0 && (
          <span className="mr-1.5 inline-flex flex-wrap gap-1 align-middle">
            {recebeVars.map(([name, type]) => (
              <VarChip key={name} name={name} type={type} />
            ))}
          </span>
        )}
        {contract.recebe}
      </Row>
      <Row icon={RiFlashlightLine} label="Faz" tone="text-gray-500 dark:text-gray-400">
        {contract.faz}
        {contract.internalSteps && (
          <span className="mt-1 block space-y-0.5">
            {contract.internalSteps.map((s, i) => (
              <span key={i} className="flex items-baseline gap-1.5 text-[11px]">
                <span className="font-semibold text-gray-400 dark:text-gray-500">
                  {i + 1}.
                </span>
                <span className="font-medium text-gray-700 dark:text-gray-300">
                  {s.label}
                </span>
                <span className="text-gray-400 dark:text-gray-500">→ {s.produz}</span>
              </span>
            ))}
          </span>
        )}
      </Row>
      <Row
        icon={RiUploadLine}
        label="Publica"
        tone="text-emerald-600 dark:text-emerald-400"
      >
        {vars.length === 0 ? (
          <span className="text-gray-400 dark:text-gray-500">
            nada — etapa de pausa/roteamento (valide o fluxo p/ atualizar)
          </span>
        ) : (
          <span className="flex flex-wrap gap-1">
            {vars.map(([name, type]) => (
              <VarChip key={name} name={name} type={type} />
            ))}
          </span>
        )}
        {contract.publicaNota && (
          <span className="mt-1 block text-[11px] leading-snug text-gray-500 dark:text-gray-400">
            {contract.publicaNota}
          </span>
        )}
      </Row>
      {contract.proxima && (
        <div className="flex items-start gap-2 rounded-md border border-violet-200/70 bg-violet-50/60 px-2 py-1.5 dark:border-violet-500/20 dark:bg-violet-500/10">
          <span className="mt-px shrink-0 text-[10px] font-semibold uppercase tracking-[0.05em] text-violet-600 dark:text-violet-400">
            E agora?
          </span>
          <p className="text-[11px] leading-snug text-violet-900 dark:text-violet-200">
            {contract.proxima}
          </p>
        </div>
      )}
    </div>
  )
}

/** Envolve o card do node no canvas — hover de ~0,5s abre o contrato. */
export function NodeContractHover({
  nodeType,
  config,
  agentCatalog,
  producedVars,
  graphNodes,
  title,
  children,
}: {
  nodeType: string
  config: Record<string, unknown>
  agentCatalog: AgentMeta[]
  producedVars?: Record<string, string>
  graphNodes?: ContractGraphNode[]
  title: string
  children: React.ReactNode
}) {
  return (
    <HoverCardPrimitives.Root openDelay={550} closeDelay={80}>
      <HoverCardPrimitives.Trigger asChild>{children}</HoverCardPrimitives.Trigger>
      <HoverCardPrimitives.Portal>
        <HoverCardPrimitives.Content
          side="right"
          align="start"
          sideOffset={10}
          className="z-50 w-[340px] rounded-md border border-gray-200 bg-white p-3 shadow-lg dark:border-gray-800 dark:bg-gray-950"
        >
          <p className="mb-2 text-xs font-semibold text-gray-900 dark:text-gray-100">
            {title}
          </p>
          <ContractBlock
            nodeType={nodeType}
            config={config}
            agentCatalog={agentCatalog}
            producedVars={producedVars}
            graphNodes={graphNodes}
            compact
          />
        </HoverCardPrimitives.Content>
      </HoverCardPrimitives.Portal>
    </HoverCardPrimitives.Root>
  )
}
