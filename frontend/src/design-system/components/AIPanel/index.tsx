// src/design-system/components/AIPanel/index.tsx
//
// AIPanel — drawer lateral violeta com insights automaticos + chat IA.
// Padrao Strata para paginas que tem assistente IA "in-layout" (nao modal).
//
// Decisoes de design (chat handoff bi-padrao, 2026-04-26):
// - Fechado por padrao; abre via botao no header OU atalho Cmd/Ctrl+I.
// - Estado open/closed persiste em localStorage (chave AI_PANEL_STORAGE_KEY).
// - Indicador discreto "✦ ⌘I" no header quando fechado, para descoberta.
// - "In-layout": consome largura horizontal do flex container pai (nao overlay).
// - Tom violeta exclusivo de IA (nao confundir com blue-500 de selecao §4).
// - Historico de chat persiste em localStorage (ultimas 20 mensagens).
//
// Como integrar com LLM real:
//   <AIPanel sendMessage={async (text, ctx) => api.aiChat(text, ctx)} ... />
// O componente gerencia loading/error UI; sua funcao so retorna texto.
//

"use client"

import * as React from "react"
import {
  RiCloseLine,
  RiSparkling2Line,
  RiArrowDownSLine,
  RiArrowUpSLine,
  RiArrowRightLine,
} from "@remixicon/react"

import { cx } from "@/lib/utils"

// ───────────────────────────────────────────────────────────────────────────
// Tipos
// ───────────────────────────────────────────────────────────────────────────

export type AIContext = {
  /** Pagina atual (ex.: "BI · Carteira"). Aparece no chip violeta no topo. */
  page: string
  /** Periodo aplicado nos filtros (ex.: "Ultimos 30 dias"). */
  period?: string
  /** Demais filtros como string ja formatada (ex.: "Fundo: FIDC Acme"). */
  filters?: string
}

export type AIMessage =
  | { role: "user"; text: string; id?: string }
  | { role: "ai";   text: string; id: string; loading?: boolean }

export type AIInsight = {
  /** Texto do insight (1 linha curta — preview corta em 80 chars). */
  text: string
}

/** Funcao opcional que envia mensagem do usuario ao LLM e retorna a resposta. */
export type SendMessageFn = (text: string, context: AIContext) => Promise<string>

// ───────────────────────────────────────────────────────────────────────────
// Constantes
// ───────────────────────────────────────────────────────────────────────────

export const AI_PANEL_STORAGE_KEY = "strata.ai_panel.open"
const AI_HISTORY_STORAGE_KEY = "strata.ai_panel.history"
const AI_HISTORY_MAX = 20

const SUGGESTED_QUESTIONS = [
  "Por que a inadimplencia subiu?",
  "Qual cedente mais arriscado?",
  "Tendencia para o proximo mes?",
]

// ───────────────────────────────────────────────────────────────────────────
// Hook — useAIPanel
// ───────────────────────────────────────────────────────────────────────────

/**
 * Gerencia estado open/closed do AIPanel + atalho Cmd/Ctrl+I + persistencia.
 * Use no componente que renderiza tanto o botao quanto o panel.
 */
export function useAIPanel(): {
  open: boolean
  setOpen: (next: boolean | ((prev: boolean) => boolean)) => void
  toggle: () => void
} {
  // SSR-safe: comeca fechado, hidrata do localStorage no client.
  const [open, setOpenState] = React.useState(false)

  React.useEffect(() => {
    try {
      const stored = window.localStorage.getItem(AI_PANEL_STORAGE_KEY)
      if (stored === "true") setOpenState(true)
    } catch {
      // localStorage indisponivel (Safari private etc) — segue fechado.
    }
  }, [])

  const setOpen = React.useCallback(
    (next: boolean | ((prev: boolean) => boolean)) => {
      setOpenState((prev) => {
        const value = typeof next === "function" ? next(prev) : next
        try {
          window.localStorage.setItem(AI_PANEL_STORAGE_KEY, String(value))
        } catch {
          // ignore
        }
        return value
      })
    },
    [],
  )

  const toggle = React.useCallback(() => setOpen((o) => !o), [setOpen])

  // Atalho global Cmd/Ctrl+I.
  React.useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      const isToggle = (e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "i"
      if (isToggle) {
        e.preventDefault()
        toggle()
      }
    }
    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [toggle])

  return { open, setOpen, toggle }
}

// ───────────────────────────────────────────────────────────────────────────
// AIToggleButton — botao no header com indicador "✦ ⌘I"
// ───────────────────────────────────────────────────────────────────────────

export function AIToggleButton({
  open,
  onClick,
  className,
}: {
  open:       boolean
  onClick:    () => void
  className?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      title="Strata IA (Cmd/Ctrl+I)"
      aria-pressed={open}
      className={cx(
        "inline-flex items-center gap-1.5 rounded px-3 py-1.5 text-xs font-medium",
        "transition-colors duration-150",
        open
          ? "border border-transparent bg-violet-600 text-white hover:bg-violet-700 dark:bg-violet-500 dark:hover:bg-violet-400"
          : "border border-violet-200 bg-violet-50 text-violet-700 hover:bg-violet-100 dark:border-violet-700/40 dark:bg-violet-500/10 dark:text-violet-300 dark:hover:bg-violet-500/15",
        className,
      )}
    >
      <RiSparkling2Line className="size-3.5 shrink-0" aria-hidden="true" />
      <span>IA</span>
      {!open && (
        <span className="ml-0.5 font-mono text-[10px] opacity-60">⌘I</span>
      )}
    </button>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Pieces internas
// ───────────────────────────────────────────────────────────────────────────

function ContextChip({ context }: { context: AIContext }) {
  const text = [
    context.page,
    context.period,
    context.filters,
  ].filter(Boolean).join(" · ")

  return (
    <div
      className={cx(
        "inline-flex max-w-full items-center gap-1 rounded-full px-2.5 py-1",
        "border border-violet-300 bg-violet-50 text-[10px] text-violet-700",
        "dark:border-violet-700/50 dark:bg-violet-500/10 dark:text-violet-300",
      )}
    >
      <span className="truncate">{text}</span>
    </div>
  )
}

function InsightChip({ insight, index }: { insight: AIInsight; index: number }) {
  const [expanded, setExpanded] = React.useState(false)
  const preview = insight.text.length > 80 ? insight.text.slice(0, 80) + "…" : insight.text

  return (
    <button
      type="button"
      onClick={() => setExpanded((e) => !e)}
      className={cx(
        "w-full rounded border px-2.5 py-2 text-left transition-colors",
        "border-violet-200 bg-violet-50/60 hover:bg-violet-100/60",
        "dark:border-violet-700/40 dark:bg-violet-500/5 dark:hover:bg-violet-500/10",
      )}
    >
      <div className="mb-1 flex items-center justify-between text-[10px] font-bold uppercase tracking-wider text-violet-600 dark:text-violet-400">
        <span>› Insight {index + 1}</span>
        {expanded ? (
          <RiArrowUpSLine className="size-3 opacity-60" aria-hidden="true" />
        ) : (
          <RiArrowDownSLine className="size-3 opacity-60" aria-hidden="true" />
        )}
      </div>
      <p className="text-[11px] leading-relaxed text-gray-900 dark:text-gray-100">
        {expanded ? insight.text : preview}
      </p>
    </button>
  )
}

function ChatBubble({ msg }: { msg: AIMessage }) {
  const isAI = msg.role === "ai"
  return (
    <div
      className={cx(
        "rounded border px-2.5 py-2 text-[12px] leading-relaxed",
        isAI
          ? "border-violet-200 bg-violet-50/60 dark:border-violet-700/40 dark:bg-violet-500/5"
          : "border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900",
      )}
    >
      <div
        className={cx(
          "mb-1 text-[10px] font-bold",
          isAI ? "text-violet-600 dark:text-violet-400" : "text-gray-500 dark:text-gray-400",
        )}
      >
        {isAI ? "› Strata IA" : "Voce"}
      </div>
      <p className="whitespace-pre-wrap text-gray-900 dark:text-gray-100">
        {msg.text}
        {"loading" in msg && msg.loading && (
          <span aria-hidden="true" className="animate-pulse opacity-50">
            {" "}▋
          </span>
        )}
      </p>
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// AIPanel
// ───────────────────────────────────────────────────────────────────────────

export interface AIPanelProps {
  open:    boolean
  onClose: () => void
  context: AIContext
  /**
   * Insights gerados automaticamente para a pagina/contexto atual.
   * Maximo 3 visiveis. Vazio = secao some.
   */
  insights?: AIInsight[]
  /**
   * Funcao que envia a pergunta ao LLM. Se omitida, o input fica
   * em modo "stub" e responde com placeholder.
   */
  sendMessage?: SendMessageFn
  /**
   * Largura em px. Default 272 (handoff bi-padrao). Pattern: 272-320.
   */
  width?: number
  className?: string
}

export function AIPanel({
  open,
  onClose,
  context,
  insights = [],
  sendMessage,
  width = 272,
  className,
}: AIPanelProps) {
  const [messages, setMessages] = React.useState<AIMessage[]>([])
  const [input, setInput] = React.useState("")
  const [loading, setLoading] = React.useState(false)
  const [insightsExpanded, setInsightsExpanded] = React.useState(true)
  const scrollRef = React.useRef<HTMLDivElement>(null)

  // Hidrata historico do localStorage (so client).
  React.useEffect(() => {
    try {
      const raw = window.localStorage.getItem(AI_HISTORY_STORAGE_KEY)
      if (raw) setMessages(JSON.parse(raw) as AIMessage[])
    } catch {
      // ignore
    }
  }, [])

  // Persiste historico (capped em AI_HISTORY_MAX).
  React.useEffect(() => {
    try {
      const trimmed = messages.slice(-AI_HISTORY_MAX)
      window.localStorage.setItem(AI_HISTORY_STORAGE_KEY, JSON.stringify(trimmed))
    } catch {
      // ignore
    }
  }, [messages])

  // Auto-scroll para a ultima mensagem.
  React.useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [messages])

  const handleSend = React.useCallback(
    async (text: string) => {
      const trimmed = text.trim()
      if (!trimmed || loading) return

      setMessages((prev) => [...prev, { role: "user", text: trimmed }])
      setInput("")
      setLoading(true)

      const aiId = `ai-${Date.now()}`
      setMessages((prev) => [...prev, { role: "ai", id: aiId, text: "", loading: true }])

      try {
        const reply = sendMessage
          ? await sendMessage(trimmed, context)
          : "Integracao com LLM nao configurada. Forneca a prop `sendMessage` ao AIPanel para conectar."
        setMessages((prev) =>
          prev.map((m) =>
            m.role === "ai" && m.id === aiId
              ? { ...m, text: reply, loading: false }
              : m,
          ),
        )
      } catch {
        setMessages((prev) =>
          prev.map((m) =>
            m.role === "ai" && m.id === aiId
              ? { ...m, text: "Falha ao consultar IA. Tente novamente.", loading: false }
              : m,
          ),
        )
      } finally {
        setLoading(false)
      }
    },
    [context, loading, sendMessage],
  )

  const handleKey = React.useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault()
        void handleSend(input)
      }
    },
    [handleSend, input],
  )

  if (!open) return null

  return (
    <aside
      aria-label="Painel Strata IA"
      style={{ width }}
      className={cx(
        "flex shrink-0 flex-col overflow-hidden",
        "border-l border-violet-200 dark:border-violet-700/40",
        "bg-violet-50/30 dark:bg-violet-500/[0.04]",
        className,
      )}
    >
      {/* Header */}
      <div className="shrink-0 border-b border-gray-200 px-3.5 py-3 dark:border-gray-800">
        <div className="mb-2 flex items-center gap-2">
          <RiSparkling2Line
            className="size-4 shrink-0 text-violet-600 dark:text-violet-400"
            aria-hidden="true"
          />
          <span className="flex-1 text-sm font-semibold text-gray-900 dark:text-gray-50">
            Strata IA
          </span>
          <button
            type="button"
            onClick={onClose}
            aria-label="Fechar painel IA"
            className="rounded p-0.5 text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
          >
            <RiCloseLine className="size-4" />
          </button>
        </div>
        <ContextChip context={context} />
      </div>

      {/* Auto insights */}
      {insights.length > 0 && (
        <div className="shrink-0 border-b border-gray-200 dark:border-gray-800">
          <button
            type="button"
            onClick={() => setInsightsExpanded((e) => !e)}
            className="flex w-full items-center justify-between px-3.5 py-2"
          >
            <span className="text-[10px] font-bold uppercase tracking-wider text-violet-600 dark:text-violet-400">
              Insights automaticos
            </span>
            {insightsExpanded ? (
              <RiArrowUpSLine className="size-3.5 text-gray-400" aria-hidden="true" />
            ) : (
              <RiArrowDownSLine className="size-3.5 text-gray-400" aria-hidden="true" />
            )}
          </button>
          {insightsExpanded && (
            <div className="flex flex-col gap-1.5 px-2.5 pb-2.5">
              {insights.slice(0, 3).map((ins, i) => (
                <InsightChip key={i} insight={ins} index={i} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* Chat history */}
      <div
        ref={scrollRef}
        className="flex flex-1 flex-col gap-1.5 overflow-y-auto p-2.5"
      >
        {messages.length === 0 ? (
          <div className="flex flex-col items-center gap-3 px-2 py-6">
            <RiSparkling2Line
              className="size-6 text-violet-500 dark:text-violet-400"
              aria-hidden="true"
            />
            <p className="text-center text-xs text-gray-600 dark:text-gray-400">
              Pergunte sobre os dados desta pagina
            </p>
            <div className="flex w-full flex-col gap-1.5">
              {SUGGESTED_QUESTIONS.map((q) => (
                <button
                  key={q}
                  type="button"
                  onClick={() => void handleSend(q)}
                  className={cx(
                    "flex w-full items-center justify-between gap-1 rounded border px-2.5 py-1.5 text-left text-[11px]",
                    "border-violet-200 text-violet-700 hover:bg-violet-100/40",
                    "dark:border-violet-700/40 dark:text-violet-300 dark:hover:bg-violet-500/10",
                  )}
                >
                  <span>{q}</span>
                  <RiArrowRightLine className="size-3 shrink-0 opacity-60" aria-hidden="true" />
                </button>
              ))}
            </div>
          </div>
        ) : (
          messages.map((m, i) => (
            <ChatBubble key={"id" in m && m.id ? m.id : `${m.role}-${i}`} msg={m} />
          ))
        )}
      </div>

      {/* Input */}
      <div className="shrink-0 border-t border-gray-200 p-2.5 dark:border-gray-800">
        <div className="flex items-end gap-1.5">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKey}
            placeholder="Pergunte sobre estes dados…"
            rows={2}
            className={cx(
              "flex-1 resize-none rounded border px-2.5 py-1.5 text-xs leading-relaxed outline-none",
              "border-violet-200 bg-white text-gray-900 placeholder:text-gray-400",
              "focus:border-violet-400 focus:ring-1 focus:ring-violet-200",
              "dark:border-violet-700/40 dark:bg-gray-950 dark:text-gray-50 dark:placeholder:text-gray-600",
              "dark:focus:border-violet-500 dark:focus:ring-violet-700/40",
            )}
          />
          <button
            type="button"
            onClick={() => void handleSend(input)}
            disabled={!input.trim() || loading}
            aria-label="Enviar mensagem"
            className={cx(
              "shrink-0 rounded px-2 py-1.5 text-sm transition-colors",
              input.trim() && !loading
                ? "bg-violet-600 text-white hover:bg-violet-700 dark:bg-violet-500 dark:hover:bg-violet-400"
                : "cursor-not-allowed bg-gray-100 text-gray-400 dark:bg-gray-800 dark:text-gray-600",
            )}
          >
            ↵
          </button>
        </div>
        <p className="mt-1 text-right text-[10px] text-gray-400 dark:text-gray-600">
          Enter para enviar
        </p>
      </div>
    </aside>
  )
}
