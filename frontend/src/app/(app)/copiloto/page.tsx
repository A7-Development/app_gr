"use client"

/**
 * /copiloto — Strata AI, chat livre (spec specs/active/copiloto-mcp.md §8).
 *
 * Fase 1a (esqueleto): Estados 1+2 minimos.
 *   Estado 1 (novo chat): composer heroi centralizado + atalhos + recentes.
 *   Estado 2 (conversa): thread + composer sticky embaixo.
 * Rail completo de conversas, acesso ubiquo e titulos automaticos sao
 * Fase 4. Conversa ativa e deep-linkavel via ?c=<id> (nuqs).
 */

import * as React from "react"
import { useQueryState } from "nuqs"
import {
  RiArrowUpLine,
  RiChat3Line,
  RiLoader4Line,
  RiSparkling2Line,
} from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { AIQuotaIndicator } from "@/design-system/components/AIQuotaIndicator"
import {
  useAIConversationMessages,
  useAIConversations,
  useAIQuota,
  useCopilotoChat,
} from "@/lib/hooks/ai"
import type { CopilotoToolStatus } from "@/lib/api-client"
import { cx } from "@/lib/utils"

import { CopilotoMarkdown } from "./_components/CopilotoMarkdown"

// ───────────────────────────────────────────────────────────────────────────
// Tipos locais
// ───────────────────────────────────────────────────────────────────────────

type Msg = {
  id: string
  role: "user" | "ai"
  text: string
  loading?: boolean
  error?: boolean
}

const SUGGESTED_PROMPTS = [
  { icon: "📊", label: "Analisar um cedente", prompt: "Analise o cedente " },
  { icon: "📁", label: "Ver a carteira", prompt: "Como está a carteira hoje?" },
  {
    icon: "🔎",
    label: "Puxar dossiê de um CNPJ",
    prompt: "Puxe o dossiê do CNPJ ",
  },
  { icon: "⚖", label: "Comparar fundos", prompt: "Compare os fundos " },
] as const

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

export default function CopilotoPage() {
  return (
    <React.Suspense>
      <CopilotoPageInner />
    </React.Suspense>
  )
}

function CopilotoPageInner() {
  const [conversationId, setConversationId] = useQueryState("c")
  const [messages, setMessages] = React.useState<Msg[]>([])
  const [input, setInput] = React.useState("")
  const [isSending, setIsSending] = React.useState(false)
  const [toolStatuses, setToolStatuses] = React.useState<CopilotoToolStatus[]>([])
  const hydratedConvRef = React.useRef<string | null>(null)

  const quotaQ = useAIQuota()
  const recentsQ = useAIConversations({ surface: "copiloto", limit: 8 })
  const messagesQ = useAIConversationMessages(conversationId)

  const composerRef = React.useRef<HTMLTextAreaElement>(null)
  const scrollRef = React.useRef<HTMLDivElement>(null)

  // Hidrata o thread ao abrir uma conversa existente via ?c= (deep link /
  // reconexao apos queda de SSE — spec §6.6: nada se perde).
  React.useEffect(() => {
    if (!conversationId || !messagesQ.data) return
    if (hydratedConvRef.current === conversationId) return
    hydratedConvRef.current = conversationId
    setMessages(
      messagesQ.data.map((m) => ({
        id: m.id,
        role: m.role,
        text: m.text,
      })),
    )
  }, [conversationId, messagesQ.data])

  const { send } = useCopilotoChat({
    conversationId,
    onConversationCreated: (id) => {
      hydratedConvRef.current = id // thread local ja esta correto
      void setConversationId(id)
    },
    onToolStatus: (status) => {
      setToolStatuses((prev) => {
        const rest = prev.filter((s) => s.id !== status.id)
        return [...rest, status]
      })
    },
  })

  // Auto-scroll ao fim quando o thread cresce.
  React.useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight })
  }, [messages, toolStatuses])

  const handleSend = React.useCallback(
    async (raw?: string) => {
      const text = (raw ?? input).trim()
      if (!text || isSending) return
      setInput("")
      setIsSending(true)
      setToolStatuses([])
      const aiMsgId = `ai-${Date.now()}`
      setMessages((prev) => [
        ...prev,
        { id: `user-${Date.now()}`, role: "user", text },
        { id: aiMsgId, role: "ai", text: "", loading: true },
      ])
      try {
        const answer = await send(text)
        setMessages((prev) =>
          prev.map((m) =>
            m.id === aiMsgId ? { ...m, text: answer, loading: false } : m,
          ),
        )
      } catch (err) {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === aiMsgId
              ? {
                  ...m,
                  loading: false,
                  error: true,
                  text:
                    err instanceof Error
                      ? err.message
                      : "Não consegui responder agora. Tente novamente.",
                }
              : m,
          ),
        )
      } finally {
        setIsSending(false)
        setToolStatuses([])
        composerRef.current?.focus()
      }
    },
    [input, isSending, send],
  )

  const startNewChat = React.useCallback(() => {
    hydratedConvRef.current = null
    setMessages([])
    setInput("")
    setToolStatuses([])
    void setConversationId(null)
    composerRef.current?.focus()
  }, [setConversationId])

  const openConversation = React.useCallback(
    (id: string) => {
      hydratedConvRef.current = null
      setMessages([])
      void setConversationId(id)
    },
    [setConversationId],
  )

  const isThread = conversationId !== null || messages.length > 0

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col">
      {/* Barra fina da superficie: identidade + quota + novo chat */}
      <div className="flex h-11 shrink-0 items-center justify-between border-b border-gray-200 px-6 dark:border-gray-800">
        <div className="flex items-center gap-2">
          <RiSparkling2Line className="size-4 text-violet-600 dark:text-violet-400" />
          <span className="text-sm font-semibold text-gray-900 dark:text-gray-50">
            Strata AI
          </span>
        </div>
        <div className="flex items-center gap-2">
          <AIQuotaIndicator quota={quotaQ.data} loading={quotaQ.isLoading} />
          {isThread && (
            <Button variant="secondary" className="h-[30px] text-[13px]" onClick={startNewChat}>
              Novo chat
            </Button>
          )}
        </div>
      </div>

      {isThread ? (
        <>
          {/* Estado 2 — thread */}
          <div ref={scrollRef} className="flex-1 overflow-y-auto">
            <div className="mx-auto w-full max-w-3xl space-y-4 px-6 py-6">
              {messagesQ.isLoading && messages.length === 0 ? (
                <div className="flex items-center gap-2 text-sm text-gray-500">
                  <RiLoader4Line className="size-4 animate-spin" />
                  Carregando a conversa…
                </div>
              ) : (
                messages.map((msg) => <MessageBubble key={msg.id} msg={msg} />)
              )}
              {toolStatuses.length > 0 && (
                <div className="space-y-1">
                  {toolStatuses.map((s) => (
                    <ToolStatusLine key={s.id} status={s} />
                  ))}
                </div>
              )}
            </div>
          </div>
          <div className="shrink-0 border-t border-gray-200 px-6 py-3 dark:border-gray-800">
            <div className="mx-auto w-full max-w-3xl">
              <Composer
                ref={composerRef}
                value={input}
                onChange={setInput}
                onSend={() => void handleSend()}
                disabled={isSending}
              />
            </div>
          </div>
        </>
      ) : (
        /* Estado 1 — heroi */
        <div className="flex flex-1 flex-col items-center justify-center overflow-y-auto px-6">
          <div className="w-full max-w-2xl">
            <div className="mb-8 text-center">
              <RiSparkling2Line className="mx-auto mb-4 size-8 text-violet-600 dark:text-violet-400" />
              <h1 className="text-2xl font-semibold text-gray-900 dark:text-gray-50">
                Como posso ajudar?
              </h1>
              <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">
                Pergunte sobre a sua operação e sobre quem você negocia — sem
                trocar de sistema.
              </p>
            </div>

            <Composer
              ref={composerRef}
              value={input}
              onChange={setInput}
              onSend={() => void handleSend()}
              disabled={isSending}
              hero
            />

            <div className="mt-4 flex flex-wrap justify-center gap-2">
              {SUGGESTED_PROMPTS.map((s) => (
                <button
                  key={s.label}
                  type="button"
                  onClick={() => {
                    setInput(s.prompt)
                    composerRef.current?.focus()
                  }}
                  className="rounded-full border border-gray-200 px-3 py-1.5 text-[13px] text-gray-700 transition hover:border-violet-300 hover:bg-violet-50 dark:border-gray-800 dark:text-gray-300 dark:hover:border-violet-700/40 dark:hover:bg-violet-500/5"
                >
                  <span className="mr-1.5" aria-hidden="true">
                    {s.icon}
                  </span>
                  {s.label}
                </button>
              ))}
            </div>

            {recentsQ.data && recentsQ.data.length > 0 && (
              <div className="mt-10">
                <div className="mb-2 text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  Conversas recentes
                </div>
                <ul className="divide-y divide-gray-100 dark:divide-gray-800/60">
                  {recentsQ.data.slice(0, 5).map((c) => (
                    <li key={c.id}>
                      <button
                        type="button"
                        onClick={() => openConversation(c.id)}
                        className="flex w-full items-center gap-2 py-2 text-left text-sm text-gray-700 transition hover:text-violet-700 dark:text-gray-300 dark:hover:text-violet-400"
                      >
                        <RiChat3Line className="size-4 shrink-0 text-gray-400" />
                        <span className="truncate">
                          {c.title ?? "Conversa sem título"}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Blocos internos
// ───────────────────────────────────────────────────────────────────────────

function MessageBubble({ msg }: { msg: Msg }) {
  if (msg.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] rounded-lg bg-gray-100 px-3.5 py-2.5 text-sm whitespace-pre-wrap text-gray-900 dark:bg-gray-800 dark:text-gray-100">
          {msg.text}
        </div>
      </div>
    )
  }
  return (
    <div className="flex gap-2.5">
      <RiSparkling2Line className="mt-1 size-4 shrink-0 text-violet-600 dark:text-violet-400" />
      <div className="min-w-0 flex-1">
        {msg.loading ? (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <RiLoader4Line className="size-4 animate-spin" />
            Pensando…
          </div>
        ) : msg.error ? (
          <p className="text-sm text-red-600 dark:text-red-400">{msg.text}</p>
        ) : (
          <CopilotoMarkdown text={msg.text} />
        )}
      </div>
    </div>
  )
}

function ToolStatusLine({ status }: { status: CopilotoToolStatus }) {
  return (
    <div
      className={cx(
        "flex items-center gap-2 pl-6 text-[13px]",
        status.status === "error"
          ? "text-red-600 dark:text-red-400"
          : "text-gray-500 dark:text-gray-400",
      )}
    >
      {status.status === "running" ? (
        <RiLoader4Line className="size-3.5 animate-spin" />
      ) : (
        <span
          className={cx(
            "size-1.5 rounded-full",
            status.status === "done" ? "bg-emerald-500" : "bg-red-500",
          )}
        />
      )}
      {status.label}
    </div>
  )
}

type ComposerProps = {
  value: string
  onChange: (v: string) => void
  onSend: () => void
  disabled?: boolean
  hero?: boolean
}

const Composer = React.forwardRef<HTMLTextAreaElement, ComposerProps>(
  function Composer({ value, onChange, onSend, disabled, hero }, ref) {
    return (
      <div
        className={cx(
          "flex items-end gap-2 rounded-lg border bg-white transition dark:bg-gray-950",
          "border-gray-200 focus-within:border-violet-400 dark:border-gray-800 dark:focus-within:border-violet-600",
          hero ? "px-4 py-3 shadow-sm" : "px-3 py-2",
        )}
      >
        <textarea
          ref={ref}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault()
              onSend()
            }
          }}
          rows={hero ? 2 : 1}
          placeholder="Pergunte sobre a sua operação ou sobre um CNPJ ou CPF…"
          className="max-h-40 flex-1 resize-none bg-transparent text-sm text-gray-900 outline-none placeholder:text-gray-400 dark:text-gray-100"
          autoFocus
        />
        <button
          type="button"
          onClick={onSend}
          disabled={disabled || !value.trim()}
          aria-label="Enviar"
          className={cx(
            "flex size-8 shrink-0 items-center justify-center rounded-md transition",
            value.trim() && !disabled
              ? "bg-violet-600 text-white hover:bg-violet-700"
              : "bg-gray-100 text-gray-400 dark:bg-gray-800 dark:text-gray-600",
          )}
        >
          {disabled ? (
            <RiLoader4Line className="size-4 animate-spin" />
          ) : (
            <RiArrowUpLine className="size-4" />
          )}
        </button>
      </div>
    )
  },
)
