"use client"

//
// AgentDetailView — leitura read-only de um agent_definition (versao).
// Extraido da page.tsx na promocao do editor para rota dedicada.
//

import {
  RiArchive2Line,
  RiCheckLine,
  RiEdit2Line,
  RiEyeLine,
  RiHistoryLine,
} from "@remixicon/react"
import { formatDistanceToNow, parseISO } from "date-fns"
import { ptBR } from "date-fns/locale"

import { Badge } from "@/components/tremor/Badge"
import { Button } from "@/components/tremor/Button"
import { Divider } from "@/components/tremor/Divider"
import { tableTokens } from "@/design-system/tokens/table"
import type { AIAgentDefinitionDetail } from "@/lib/api-client"
import { cx } from "@/lib/utils"

import { ModuleBadge, StatusBadge } from "./AgentBadges"

type DetailViewProps = {
  agent: AIAgentDefinitionDetail
  onEdit: () => void
  onActivate: () => void
  onArchive: () => void
  onPreview: () => void
  activating: boolean
  previewing: boolean
}

export function AgentDetailView({
  agent,
  onEdit,
  onActivate,
  onArchive,
  onPreview,
  activating,
  previewing,
}: DetailViewProps) {
  const isArchived = agent.archived_at !== null
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className={cx("font-mono text-[13px]", tableTokens.cellStrong)}>
          {agent.name}
        </span>
        <Badge variant="neutral" className={tableTokens.badge}>
          v{agent.version}
        </Badge>
        <ModuleBadge module={agent.module} />
        <StatusBadge active={agent.is_active} archived={isArchived} />
        {agent.cross_module && (
          <Badge variant="warning" className={tableTokens.badge}>
            cross-module
          </Badge>
        )}
        <span className="ml-auto text-[12px] text-gray-500 dark:text-gray-400">
          <RiHistoryLine className="-mt-0.5 mr-1 inline size-3.5" />
          {formatDistanceToNow(parseISO(agent.created_at), {
            addSuffix: true,
            locale: ptBR,
          })}
        </span>
      </div>

      <section>
        <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Persona
        </div>
        {agent.persona ? (
          <div className={tableTokens.cellText}>
            {agent.persona.display_name}{" "}
            <span className={cx(tableTokens.cellMuted, "font-mono ml-1")}>
              {agent.persona.name}@v{agent.persona.version}
            </span>
          </div>
        ) : (
          <span className={tableTokens.cellMuted}>(sem persona)</span>
        )}
      </section>

      <section>
        <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Expertises ({agent.expertises.length})
        </div>
        {agent.expertises.length === 0 ? (
          <span className={tableTokens.cellMuted}>(sem expertises)</span>
        ) : (
          <ul className="flex flex-col gap-1">
            {agent.expertises.map((e) => (
              <li key={e.id} className="text-[13px]">
                <span className="text-gray-900 dark:text-gray-100">
                  {e.display_name}
                </span>{" "}
                <span className={cx(tableTokens.cellMuted, "font-mono ml-1")}>
                  {e.name}@v{e.version} · {e.domain}
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section>
        <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Prompt task
        </div>
        <div className={cx(tableTokens.cellText, "font-mono")}>
          {agent.prompt_name}
          {agent.prompt && (
            <span className={cx(tableTokens.cellMuted, "ml-2")}>
              @v{agent.prompt.version}
            </span>
          )}
        </div>
      </section>

      <section>
        <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Tools
        </div>
        {agent.allowed_tools === null ? (
          <span className={tableTokens.cellMuted}>
            Padrao do CATALOG (definido em codigo)
          </span>
        ) : agent.allowed_tools.length === 0 ? (
          <span className={tableTokens.cellMuted}>(sem tools — conversacional)</span>
        ) : (
          <ul className="flex flex-wrap gap-1">
            {agent.allowed_tools.map((t) => (
              <li
                key={t}
                className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[11px] text-gray-700 dark:bg-gray-800 dark:text-gray-300"
              >
                {t}
              </li>
            ))}
          </ul>
        )}
      </section>

      <Divider />

      <section>
        <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
          Modelo (override)
        </div>
        <div className="grid grid-cols-2 gap-3 text-[13px]">
          <div>
            <span className={tableTokens.cellMuted}>Modelo: </span>
            {agent.model ? (
              <code className="font-mono text-[12px]">{agent.model}</code>
            ) : (
              <span className={tableTokens.cellMuted}>default do prompt</span>
            )}
          </div>
          <div>
            <span className={tableTokens.cellMuted}>Fallback: </span>
            {agent.fallback_model ? (
              <code className="font-mono text-[12px]">{agent.fallback_model}</code>
            ) : (
              <span className={tableTokens.cellMuted}>default</span>
            )}
          </div>
          <div>
            <span className={tableTokens.cellMuted}>Temperature: </span>
            {agent.temperature ?? "default"}
          </div>
          <div>
            <span className={tableTokens.cellMuted}>Max tokens: </span>
            {agent.max_tokens ?? "default"}
          </div>
        </div>
      </section>

      <Divider />

      <div className="flex flex-wrap items-center justify-end gap-2">
        <Button variant="secondary" onClick={onPreview} disabled={previewing}>
          <RiEyeLine className="mr-1.5 size-4" />
          Preview system_text
        </Button>
        {!isArchived && (
          <>
            <Button
              variant="secondary"
              onClick={onArchive}
              disabled={agent.is_active}
              title={
                agent.is_active
                  ? "Versao ativa nao pode ser arquivada"
                  : undefined
              }
            >
              <RiArchive2Line className="mr-1.5 size-4" />
              Arquivar
            </Button>
            {!agent.is_active && (
              <Button variant="secondary" onClick={onActivate} disabled={activating}>
                <RiCheckLine className="mr-1.5 size-4" />
                Ativar esta versao
              </Button>
            )}
            <Button onClick={onEdit}>
              <RiEdit2Line className="mr-1.5 size-4" />
              Editar (nova versao)
            </Button>
          </>
        )}
      </div>
    </div>
  )
}
