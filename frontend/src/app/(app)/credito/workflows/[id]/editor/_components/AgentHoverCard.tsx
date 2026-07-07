// src/app/(app)/credito/workflows/[id]/editor/_components/AgentHoverCard.tsx
//
// HoverCard rico no palette para entries de specialist_agent.
//
// Quando o user passa o mouse sobre um agente IA na palette, abre popover
// lateral mostrando: descricao completa + inputs declarados (slots que o
// agente le, vindo de agentCatalog) + outputs (campos do output_schema).
//
// Para agentes nao-migrados (inputs=[]) mostra nota "Recebe contexto
// completo do fluxo" sinalizando que esta no caminho legacy.
//
// Usa Radix HoverCard direto (CLAUDE.md §3 permite primitivos Radix
// sem equivalente no Tremor — Tremor nao tem HoverCard, so Tooltip).
// Mesmo padrao ja em uso em components/charts/Tracker.tsx.

"use client"

import * as React from "react"
import * as HoverCardPrimitives from "@radix-ui/react-hover-card"
import { RiAiAgentLine, RiArrowRightLine } from "@remixicon/react"

import type { AgentMeta } from "@/lib/credito-client"
import { cx } from "@/lib/utils"

import { getAgentOutputFields } from "../_lib/refs"

// pt-BR labels per VarType (espelha o mapa em AgentInputBindingsField).
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

export type AgentHoverCardProps = {
  /** Nome do agente (chave em CATALOG.py). */
  agentName: string
  /** Label amigavel ja resolvido pelo caller (ex.: "Analise Financeira"). */
  agentLabel: string
  /** Descricao curta vinda do PaletteEntry. */
  description: string
  /** Catalog completo — usado para encontrar inputs declarados. */
  agentCatalog: AgentMeta[]
  children: React.ReactNode
}

export function AgentHoverCard({
  agentName,
  agentLabel,
  description,
  agentCatalog,
  children,
}: AgentHoverCardProps) {
  const meta = agentCatalog.find((a) => a.name === agentName)
  const inputs = meta?.inputs ?? []
  const outputs = getAgentOutputFields(agentName)
  const isLegacy = inputs.length === 0

  return (
    <HoverCardPrimitives.Root openDelay={400} closeDelay={100}>
      <HoverCardPrimitives.Trigger asChild>{children}</HoverCardPrimitives.Trigger>
      <HoverCardPrimitives.Portal>
        <HoverCardPrimitives.Content
          side="right"
          align="start"
          sideOffset={8}
          className={cx(
            "z-50 w-80 rounded-md border border-gray-200 bg-white p-3 shadow-lg",
            "dark:border-gray-800 dark:bg-gray-950",
            "data-[state=open]:animate-in data-[state=closed]:animate-out",
            "data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0",
          )}
        >
          {/* Cabecalho: chip IA + label do agente */}
          <div className="mb-2 flex items-center gap-1.5">
            <span
              className="inline-flex items-center gap-0.5 rounded bg-gradient-to-r from-blue-100 to-violet-100 px-1.5 py-0.5 text-[9px] font-bold tracking-wider text-blue-700 dark:from-blue-500/20 dark:to-violet-500/20 dark:text-blue-300"
              aria-hidden
            >
              <RiAiAgentLine className="size-2.5" aria-hidden />
              IA
            </span>
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
              {agentLabel}
            </p>
          </div>

          {/* Descricao */}
          <p className="text-xs text-gray-600 dark:text-gray-400">
            {description}
          </p>

          {/* Inputs */}
          <div className="mt-3">
            <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Recebe
              {!isLegacy && (
                <span className="ml-1 text-gray-400 dark:text-gray-500">
                  ({inputs.length})
                </span>
              )}
            </p>
            {isLegacy ? (
              <p className="mt-1 text-[11px] italic text-gray-500 dark:text-gray-400">
                Contexto completo do workflow (caminho legacy — sera migrado).
              </p>
            ) : (
              <ul className="mt-1 space-y-0.5">
                {inputs.map((slot) => (
                  <li
                    key={slot.name}
                    className="flex items-center gap-1.5 text-[11px]"
                  >
                    <span className="font-mono text-gray-900 dark:text-gray-100">
                      {slot.name}
                    </span>
                    <span className="rounded bg-gray-100 px-1 py-0.5 text-[9px] font-medium uppercase tracking-wider text-gray-600 dark:bg-gray-800 dark:text-gray-300">
                      {typeLabel(slot.type)}
                    </span>
                    {!slot.optional && (
                      <span className="text-[9px] font-medium uppercase tracking-wider text-blue-600 dark:text-blue-400">
                        obrig.
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {/* Outputs */}
          {outputs.length > 0 && (
            <div className="mt-3">
              <p className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Produz{" "}
                <span className="text-gray-400 dark:text-gray-500">
                  ({outputs.length})
                </span>
              </p>
              <ul className="mt-1 flex flex-wrap gap-1">
                {outputs.slice(0, 8).map((f) => (
                  <li
                    key={f.key}
                    className="rounded bg-blue-50 px-1.5 py-0.5 font-mono text-[10px] text-blue-800 dark:bg-blue-500/10 dark:text-blue-200"
                    title={`${f.label} (${f.type})`}
                  >
                    {f.key}
                  </li>
                ))}
                {outputs.length > 8 && (
                  <li className="text-[10px] text-gray-500 dark:text-gray-400">
                    +{outputs.length - 8} mais
                  </li>
                )}
              </ul>
            </div>
          )}

          {/* Footer com hint */}
          <div className="mt-3 flex items-center gap-1 border-t border-gray-100 pt-2 text-[10px] text-gray-500 dark:border-gray-900 dark:text-gray-400">
            <RiArrowRightLine className="size-3 shrink-0" aria-hidden />
            <span>Arraste para o canvas para usar este agente</span>
          </div>
        </HoverCardPrimitives.Content>
      </HoverCardPrimitives.Portal>
    </HoverCardPrimitives.Root>
  )
}
