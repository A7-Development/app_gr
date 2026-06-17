"use client"

/**
 * ChatVariacaoDrawer — o chat-investigador da variação da Cota Sub (Camada 2).
 *
 * Drawer summonable. Pré-carregado (no backend) com o headline + detalhamento do
 * dia, então responde do contexto quando dá (rápido) e investiga com as tools
 * (cross-reference) quando precisa. É o ÚNICO lugar onde o LLM entra — o read e
 * os detalhes da página são 100% estruturados.
 */

import * as React from "react"
import { RiSendPlane2Fill, RiSparkling2Line } from "@remixicon/react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { cx } from "@/lib/utils"
import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"
import { Input } from "@/components/tremor/Input"
import { Button } from "@/components/tremor/Button"
import { controladoria } from "@/lib/api-client"
import type { ChatMensagem } from "@/lib/api-client"

// Chip primario (sob demanda): chama o agente pra sintetizar o dia. O texto
// enviado e o que o controller "perguntou" — o agente ja recebe o resumo
// estruturado no contexto e responde curto, do maior impacto pro menor.
const RESUMO_DIA = "Resumir o dia: o que impactou a cota?"

const SUGESTOES = [
  "Por que a cota mexeu hoje?",
  "O que eu deveria vigiar?",
  "Algum pagamento fora do previsto?",
]

type Props = {
  fundoId: string | null
  data:    string
  open:    boolean
  onClose: () => void
}

export function ChatVariacaoDrawer({ fundoId, data, open, onClose }: Props) {
  const [messages, setMessages] = React.useState<ChatMensagem[]>([])
  const [input, setInput] = React.useState("")
  const [loading, setLoading] = React.useState(false)
  // Codigo discreto do agente que atende esta janela (rastreabilidade).
  const [agentCode, setAgentCode] = React.useState<string | null>(null)
  const endRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" })
  }, [messages, loading])

  // Busca o codigo do agente ao abrir (uma vez — e estavel).
  React.useEffect(() => {
    if (!open || agentCode) return
    let alive = true
    controladoria
      .cotaSubVariacaoChatAgente()
      .then((r) => {
        if (alive) setAgentCode(r.code)
      })
      .catch(() => {})
    return () => {
      alive = false
    }
  }, [open, agentCode])

  const send = React.useCallback(async (texto: string) => {
    const pergunta = texto.trim()
    if (!pergunta || !fundoId || loading) return
    const hist = messages
    setMessages((m) => [...m, { role: "user", content: pergunta }])
    setInput("")
    setLoading(true)
    try {
      const r = await controladoria.cotaSubVariacaoChat(fundoId, data, pergunta, hist)
      setMessages((m) => [...m, { role: "assistant", content: r.resposta }])
    } catch {
      setMessages((m) => [...m, { role: "assistant", content: "Não consegui responder agora. Tente de novo." }])
    } finally {
      setLoading(false)
    }
  }, [fundoId, data, messages, loading])

  return (
    <DrillDownSheet open={open} onClose={onClose} size="lg" title="Perguntar sobre o dia">
      <div className="flex h-full min-h-0 flex-col">
        {/* Barra discreta: identifica o agente desta janela pelo codigo. */}
        <div className="flex items-center justify-between border-b border-gray-100 px-4 py-2 dark:border-gray-800">
          <span className="flex items-center gap-1.5 text-[12px] text-gray-500 dark:text-gray-400">
            <RiSparkling2Line className="size-3.5 text-violet-500" aria-hidden />
            Assistente
          </span>
          {agentCode && (
            <span
              className="rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[10px] font-medium text-gray-500 dark:bg-gray-800 dark:text-gray-400"
              title="Codigo do agente que atende esta janela"
            >
              {agentCode}
            </span>
          )}
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
          {messages.length === 0 && !loading && (
            <div className="flex flex-col items-start gap-3 pt-2">
              <div className="flex items-center gap-2 text-[13px] text-gray-500 dark:text-gray-400">
                <RiSparkling2Line className="size-4 text-violet-500" aria-hidden />
                Pergunte sobre a variação da cota deste dia. Eu uso os dados já calculados e investigo quando precisa.
              </div>

              {/* Chip primario — sintese do dia sob demanda. */}
              <button
                type="button"
                onClick={() => void send(RESUMO_DIA)}
                disabled={!fundoId || loading}
                className="flex w-full items-center gap-2 rounded-lg border border-violet-300 bg-violet-50 px-3 py-2 text-left text-[13px] font-medium text-violet-800 transition-colors hover:bg-violet-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-violet-700/50 dark:bg-violet-950/30 dark:text-violet-200 dark:hover:bg-violet-900/30"
              >
                <RiSparkling2Line className="size-4 shrink-0 text-violet-500" aria-hidden />
                {RESUMO_DIA}
              </button>

              <div className="flex flex-col gap-1.5">
                <span className="text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600">
                  Ou investigue
                </span>
                {SUGESTOES.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => void send(s)}
                    className="rounded-full border border-gray-200 px-3 py-1 text-[12px] text-gray-700 hover:border-violet-300 hover:bg-violet-50/50 dark:border-gray-800 dark:text-gray-300 dark:hover:border-violet-800 dark:hover:bg-violet-950/20"
                  >
                    {s}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((m, i) => (
            <div key={i} className={cx("flex", m.role === "user" ? "justify-end" : "justify-start")}>
              <div className={cx(
                "max-w-[88%] rounded-lg px-3 py-2 text-[13px]",
                m.role === "user"
                  ? "bg-blue-500 text-white"
                  : "bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-200",
              )}>
                {m.role === "assistant" ? (
                  <div className="prose prose-sm max-w-none break-words text-[13px] leading-relaxed dark:prose-invert prose-p:my-1 prose-ul:my-1 prose-li:my-0">
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>{m.content}</ReactMarkdown>
                  </div>
                ) : (
                  <span className="whitespace-pre-wrap">{m.content}</span>
                )}
              </div>
            </div>
          ))}

          {loading && (
            <div className="flex justify-start">
              <div className="flex items-center gap-1.5 rounded-lg bg-gray-100 px-3 py-2 dark:bg-gray-900">
                <span className="size-1.5 animate-bounce rounded-full bg-violet-400 [animation-delay:-0.3s]" />
                <span className="size-1.5 animate-bounce rounded-full bg-violet-400 [animation-delay:-0.15s]" />
                <span className="size-1.5 animate-bounce rounded-full bg-violet-400" />
                <span className="ml-1 text-[11px] text-gray-500 dark:text-gray-400">investigando…</span>
              </div>
            </div>
          )}
          <div ref={endRef} />
        </div>

        <form
          className="flex items-center gap-2 border-t border-gray-100 p-3 dark:border-gray-900"
          onSubmit={(e) => { e.preventDefault(); void send(input) }}
        >
          <Input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Perguntar sobre 13/05…"
            disabled={loading || !fundoId}
            className="flex-1"
          />
          <Button type="submit" disabled={loading || !input.trim() || !fundoId} className="shrink-0">
            <RiSendPlane2Fill className="size-4" aria-hidden />
          </Button>
        </form>
      </div>
    </DrillDownSheet>
  )
}
