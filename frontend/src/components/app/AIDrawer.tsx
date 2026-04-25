"use client"

import * as React from "react"
import {
  RiCloseLine,
  RiSendPlane2Fill,
  RiShieldCheckLine,
  RiSparkling2Fill,
} from "@remixicon/react"

import {
  Drawer,
  DrawerContent,
  DrawerTitle,
} from "@/components/tremor/Drawer"
import { cx, focusRing } from "@/lib/utils"

//
// AIDrawer -- Copiloto contextual de BI (handoff v2 §15+§16).
//
// Drawer lateral direito (420px, full-height, border-left, slide-in), com
// UI de chat: bloco de contexto + sugestoes + mensagens + input no rodape.
//
// Spec:
//   - bi-framework.css linhas 38-80 (drawer-overlay, .drawer, .ai-*)
//   - COMPONENTS.md \u00a715 (Drawer) + \u00a716 (AI Drawer)
//
// Contrato:
//   - open/onClose controlado externamente (AIButton + page.tsx).
//   - context = { page, tab?, filters[] } — exibido no bloco ai-ctx.
//   - sugestoes default podem ser sobrescritas via prop `suggestions`.
//   - sendMessage e mock por enquanto (sem backend IA). Cada envio empilha
//     mensagem do user + resposta fake em 900ms. Pos-MVP troca por endpoint.
//
// Override da posicao/dimensao do DrawerContent do Tremor:
//   - inset-y-0 / right-0 / w-[420px] / rounded-none / border-l only
//   - p-0 (padding e interno em cada secao drawer-head/body/foot)
//

export type AIContext = {
  page: string
  tab?: string
  filters?: string[]
}

type Message = {
  role: "user" | "ai"
  text: string
  source?: string
}

type AIDrawerProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  context?: AIContext
  suggestions?: string[]
  /** Resposta mockada (trocar por endpoint quando houver backend IA). */
  onSend?: (question: string, ctx?: AIContext) => Promise<Message> | Message
}

const DEFAULT_SUGGESTIONS = [
  "Quais sao os 3 fatos mais relevantes desta tela?",
  "Me detalhe o KPI com maior variacao.",
  "Resuma a leitura do periodo em 2 frases.",
]

function defaultReply(question: string, ctx?: AIContext): Message {
  const ctxStr = ctx
    ? `pagina ${ctx.page}${ctx.tab ? ` · aba ${ctx.tab}` : ""}`
    : "contexto atual"
  return {
    role: "ai",
    text: `Sobre "${question}" no ${ctxStr}: esta e uma resposta mockada. O endpoint de IA ainda nao esta conectado — a resposta real sera gerada quando o backend de copiloto for ativado, sempre com citacao de fonte do DW e registro em decision_log.`,
    source: "mock · sem backend IA",
  }
}

export function AIDrawer({
  open,
  onOpenChange,
  context,
  suggestions = DEFAULT_SUGGESTIONS,
  onSend,
}: AIDrawerProps) {
  const [messages, setMessages] = React.useState<Message[]>([])
  const [input, setInput] = React.useState("")
  const [thinking, setThinking] = React.useState(false)
  const bodyRef = React.useRef<HTMLDivElement | null>(null)

  // Reseta estado ao fechar (pos-MVP: persistir por sessao).
  React.useEffect(() => {
    if (!open) {
      setMessages([])
      setInput("")
      setThinking(false)
    }
  }, [open])

  // Auto-scroll para a ultima mensagem.
  React.useEffect(() => {
    if (!bodyRef.current) return
    bodyRef.current.scrollTop = bodyRef.current.scrollHeight
  }, [messages, thinking])

  async function send(text?: string) {
    const q = (text ?? input).trim()
    if (!q || thinking) return
    setMessages((m) => [...m, { role: "user", text: q }])
    setInput("")
    setThinking(true)
    try {
      const reply = await Promise.resolve(
        onSend ? onSend(q, context) : null,
      )
      const aiMsg =
        reply ??
        (await new Promise<Message>((resolve) =>
          setTimeout(() => resolve(defaultReply(q, context)), 900),
        ))
      setMessages((m) => [...m, aiMsg])
    } finally {
      setThinking(false)
    }
  }

  return (
    <Drawer open={open} onOpenChange={onOpenChange}>
      <DrawerContent
        className={cx(
          // Override da posicao/dimensao do Tremor Drawer:
          "!inset-y-0 !right-0 !left-auto !top-0 !bottom-0 !mx-0",
          "!w-[420px] !max-w-[100vw] !rounded-none",
          "!border-y-0 !border-r-0 !border-l !p-0",
          "max-sm:!inset-x-auto max-sm:!right-0 sm:!right-0 sm:!max-w-none",
          "flex flex-col",
          // Desativamos as animacoes do Tremor (translate-X de drawer centrado)
          // para o copiloto encostar direto na borda direita, sem transicao.
          "!animate-none",
        )}
      >
        {/* drawer-head (fixed top) */}
        <div className="flex shrink-0 items-start justify-between gap-3 border-b border-gray-200 px-5 py-4 dark:border-gray-800">
          <div className="flex flex-col gap-0.5">
            <DrawerTitle asChild>
              <div className="flex items-center gap-1.5 text-[15px] font-semibold leading-tight text-gray-900 dark:text-gray-50">
                <RiSparkling2Fill
                  className="size-4 text-violet-500 dark:text-violet-400"
                  aria-hidden="true"
                />
                Copiloto BI
              </div>
            </DrawerTitle>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Pergunte sobre os dados da tela — respostas citam fonte.
            </p>
          </div>
          <button
            type="button"
            aria-label="Fechar"
            onClick={() => onOpenChange(false)}
            className={cx(
              "inline-flex size-7 shrink-0 items-center justify-center rounded-md text-gray-500 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-50",
              focusRing,
            )}
          >
            <RiCloseLine className="size-[18px]" aria-hidden="true" />
          </button>
        </div>

        {/* drawer-body (scrollable) */}
        <div
          ref={bodyRef}
          className="flex-1 overflow-y-auto px-5 py-5"
        >
          {context && (
            <div className="mb-4 rounded border border-gray-200 bg-gray-50 px-3 py-2.5 text-xs text-gray-600 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-300">
              <div className="mb-1 text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Contexto atual
              </div>
              <div className="text-gray-700 dark:text-gray-200">
                Página <span className="font-semibold">{context.page}</span>
                {context.tab && (
                  <>
                    {" · "}aba{" "}
                    <span className="font-semibold">{context.tab}</span>
                  </>
                )}
              </div>
              {context.filters && context.filters.length > 0 && (
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {context.filters.map((f, i) => (
                    <span
                      key={i}
                      className="inline-flex items-center rounded-sm border border-gray-200 bg-white px-1.5 py-0.5 text-[11px] font-medium text-gray-700 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-300"
                    >
                      {f}
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}

          {messages.length === 0 && (
            <>
              <div className="mb-2 text-[10px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
                Sugestões
              </div>
              <div className="mb-3 flex flex-col gap-1.5">
                {suggestions.map((s) => (
                  <button
                    key={s}
                    type="button"
                    onClick={() => send(s)}
                    className={cx(
                      "rounded border border-gray-200 bg-white px-3 py-2 text-left text-xs text-gray-700 transition hover:border-gray-300 hover:bg-gray-50 hover:text-gray-900",
                      "dark:border-gray-800 dark:bg-gray-950 dark:text-gray-300 dark:hover:border-gray-700 dark:hover:bg-gray-900 dark:hover:text-gray-50",
                      focusRing,
                    )}
                  >
                    {s}
                  </button>
                ))}
              </div>
            </>
          )}

          {messages.map((m, i) => (
            <div key={i} className="mb-3.5 flex gap-2.5">
              <span
                aria-hidden="true"
                className={cx(
                  "inline-flex size-6 shrink-0 items-center justify-center rounded text-[11px] font-semibold",
                  m.role === "user"
                    ? "bg-gray-200 text-gray-700 dark:bg-gray-800 dark:text-gray-200"
                    : "bg-violet-500/15 text-violet-600 dark:bg-violet-500/20 dark:text-violet-400",
                )}
              >
                {m.role === "user" ? (
                  "JS"
                ) : (
                  <RiSparkling2Fill className="size-3.5" aria-hidden="true" />
                )}
              </span>
              <div className="flex-1 text-[13px] leading-relaxed text-gray-900 dark:text-gray-50">
                <p className="whitespace-pre-wrap">{m.text}</p>
                {m.source && (
                  <div className="mt-1.5 inline-flex items-center gap-1 text-[11px] text-gray-500 dark:text-gray-400">
                    <RiShieldCheckLine className="size-3" aria-hidden="true" />
                    Fonte:{" "}
                    <span className="font-mono text-[11px]">{m.source}</span>
                  </div>
                )}
              </div>
            </div>
          ))}

          {thinking && (
            <div className="mb-3.5 flex gap-2.5">
              <span
                aria-hidden="true"
                className="inline-flex size-6 shrink-0 items-center justify-center rounded bg-violet-500/15 text-violet-600 dark:bg-violet-500/20 dark:text-violet-400"
              >
                <RiSparkling2Fill className="size-3.5" aria-hidden="true" />
              </span>
              <div className="flex-1 text-xs italic text-gray-500 dark:text-gray-400">
                Analisando dados…
              </div>
            </div>
          )}
        </div>

        {/* drawer-foot (input) */}
        <div className="shrink-0 border-t border-gray-200 bg-white px-4 py-3 dark:border-gray-800 dark:bg-gray-950">
          <div className="flex items-end gap-2">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault()
                  void send()
                }
              }}
              placeholder="Pergunte algo sobre esta tela…"
              rows={1}
              className={cx(
                "min-h-[38px] max-h-[120px] flex-1 resize-none rounded border border-gray-300 bg-white px-2.5 py-2 text-[13px] leading-snug text-gray-900 shadow-xs",
                "placeholder:text-gray-400",
                "dark:border-gray-700 dark:bg-gray-950 dark:text-gray-50 dark:placeholder:text-gray-500",
                "focus:border-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-200 dark:focus:border-blue-400 dark:focus:ring-blue-400/30",
              )}
            />
            <button
              type="button"
              onClick={() => void send()}
              disabled={!input.trim() || thinking}
              aria-label="Enviar pergunta"
              className={cx(
                "inline-flex size-[38px] shrink-0 items-center justify-center rounded bg-blue-500 text-white transition hover:bg-blue-600 disabled:cursor-not-allowed disabled:bg-blue-200 dark:disabled:bg-blue-500/30",
                focusRing,
              )}
            >
              <RiSendPlane2Fill className="size-[14px]" aria-hidden="true" />
            </button>
          </div>
          <p className="mt-1.5 text-center text-[10px] text-gray-400 dark:text-gray-500">
            Cada pergunta é registrada em{" "}
            <span className="font-mono">decision_log</span> · conforme §14
          </p>
        </div>
      </DrawerContent>
    </Drawer>
  )
}
