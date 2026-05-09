"use client"

/**
 * React hooks para a capacidade de IA (transversal — CLAUDE.md sec 19).
 *
 * - useAIChat        : streaming SSE multi-turn, retorna SendMessageFn para o <AIPanel />.
 * - useAIInsights    : 3 bullets automaticos por pagina (cache server-side 10min).
 * - useAIQuota       : saldo mensal de creditos para o <AIQuotaIndicator />.
 * - useAIConversations: lista historica para sidebar interna do AIPanel.
 */

import * as React from "react"
import { useQuery } from "@tanstack/react-query"

import {
  apiClient,
  buildAIChatRequest,
  type AIConversationListItem,
  type AIInsightsResponse,
  type AIQuota,
} from "@/lib/api-client"
import type { AIContext, SendMessageFn } from "@/design-system/components/AIPanel"

// ───────────────────────────────────────────────────────────────────────────
// useAIChat — streaming SSE
// ───────────────────────────────────────────────────────────────────────────

export type UseAIChatOptions = {
  /** ID da conversa atual; null = nova conversa */
  conversationId: string | null
  /** Disparado quando o backend confirma o conversation_id (depois do 1o chunk SSE). */
  onConversationCreated?: (id: string) => void
  /** Disparado ao final, com o id do usage event (para badges de proveniencia). */
  onDone?: (info: { usageEventId: string; turnIndex: number }) => void
  /** Disparado ao receber erro (rate limit, injection, config_error). */
  onError?: (info: { message: string; status: string }) => void
  /** Disparado a cada chunk de delta — uso opcional para "streaming" no UI. */
  onDelta?: (chunk: string) => void
}

/**
 * Cria uma `SendMessageFn` (compativel com a prop sendMessage do AIPanel) que:
 *   1. Envia POST /ai/chat com Bearer token e Accept: text/event-stream.
 *   2. Le o ReadableStream, parseia eventos SSE.
 *   3. Acumula texto AI e retorna no final.
 *   4. Dispara callbacks no caminho.
 */
export function useAIChat(options: UseAIChatOptions): {
  send: SendMessageFn
} {
  const conversationIdRef = React.useRef<string | null>(options.conversationId)
  const optsRef = React.useRef(options)

  React.useEffect(() => {
    conversationIdRef.current = options.conversationId
  }, [options.conversationId])

  React.useEffect(() => {
    optsRef.current = options
  }, [options])

  const send = React.useCallback<SendMessageFn>(
    async (text: string, context: AIContext): Promise<string> => {
      const { url, init } = buildAIChatRequest({
        message: text,
        context: {
          page: context.page,
          period: context.period ?? null,
          filters: context.filters ?? null,
        },
        conversation_id: conversationIdRef.current,
      })

      const res = await fetch(url, init)
      if (!res.ok || !res.body) {
        // 4xx/5xx — tenta extrair detail
        let detail = res.statusText
        try {
          const errJson = (await res.json()) as { detail?: string }
          if (errJson.detail) detail = errJson.detail
        } catch {
          // ignore
        }
        throw new Error(detail || `Falha HTTP ${res.status}`)
      }

      const reader = res.body.getReader()
      const decoder = new TextDecoder("utf-8")
      type StreamError = { message: string; status: string }
      const state: {
        buffer: string
        accumulatedText: string
        finalError: StreamError | null
      } = { buffer: "", accumulatedText: "", finalError: null }

      const handleEvent = (event: string, data: string) => {
        let payload: Record<string, unknown> = {}
        try {
          payload = JSON.parse(data) as Record<string, unknown>
        } catch {
          return
        }
        if (event === "conversation_id") {
          const id = payload.conversation_id as string | undefined
          if (id) {
            conversationIdRef.current = id
            optsRef.current.onConversationCreated?.(id)
          }
        } else if (event === "delta") {
          const delta = (payload.text as string | undefined) ?? ""
          if (delta) {
            state.accumulatedText += delta
            optsRef.current.onDelta?.(delta)
          }
        } else if (event === "done") {
          optsRef.current.onDone?.({
            usageEventId: (payload.usage_event_id as string) ?? "",
            turnIndex: (payload.turn_index as number) ?? 0,
          })
        } else if (event === "error") {
          state.finalError = {
            message: (payload.error as string) ?? "Erro desconhecido",
            status: (payload.status as string) ?? "error",
          }
        }
      }

      while (true) {
        const { value, done } = await reader.read()
        if (done) break
        state.buffer += decoder.decode(value, { stream: true })

        // SSE frames are separated by blank lines.
        let sep: number
        while ((sep = state.buffer.indexOf("\n\n")) !== -1) {
          const frame = state.buffer.slice(0, sep)
          state.buffer = state.buffer.slice(sep + 2)
          const lines = frame.split("\n")
          let event = "message"
          const dataLines: string[] = []
          for (const line of lines) {
            if (line.startsWith("event:")) event = line.slice(6).trim()
            else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim())
          }
          if (dataLines.length > 0) handleEvent(event, dataLines.join("\n"))
        }
      }

      if (state.finalError) {
        optsRef.current.onError?.(state.finalError)
        throw new Error(state.finalError.message)
      }
      return state.accumulatedText
    },
    [],
  )

  return { send }
}

// ───────────────────────────────────────────────────────────────────────────
// useAIInsights — auto bullets
// ───────────────────────────────────────────────────────────────────────────

export type UseAIInsightsParams = {
  page: string
  period?: string | null
  filters?: string | null
  /** Texto plano com KPIs/tendencias da pagina, alimentado ao LLM. */
  kpisBlock?: string | null
  enabled?: boolean
}

export function useAIInsights(params: UseAIInsightsParams) {
  const { page, period, filters, kpisBlock, enabled = true } = params
  return useQuery({
    queryKey: ["ai", "insights", page, period ?? null, filters ?? null] as const,
    queryFn: async () => {
      const qs = new URLSearchParams({ page })
      if (period) qs.set("period", period)
      if (filters) qs.set("filters", filters)
      if (kpisBlock) qs.set("kpis_block", kpisBlock)
      return apiClient.get<AIInsightsResponse>(`/ai/insights?${qs.toString()}`)
    },
    // 10 min staleTime — combina com o cache server-side.
    staleTime: 10 * 60 * 1000,
    enabled: enabled && !!page,
  })
}

// ───────────────────────────────────────────────────────────────────────────
// useAIQuota — saldo de creditos
// ───────────────────────────────────────────────────────────────────────────

export function useAIQuota(opts: { enabled?: boolean } = {}) {
  return useQuery({
    queryKey: ["ai", "quota"] as const,
    queryFn: () => apiClient.get<AIQuota>("/ai/quota"),
    staleTime: 30 * 1000,
    enabled: opts.enabled ?? true,
  })
}

// ───────────────────────────────────────────────────────────────────────────
// useAIConversations — historico do user
// ───────────────────────────────────────────────────────────────────────────

export function useAIConversations(opts: { limit?: number; enabled?: boolean } = {}) {
  const { limit = 20, enabled = true } = opts
  return useQuery({
    queryKey: ["ai", "conversations", limit] as const,
    queryFn: () =>
      apiClient.get<AIConversationListItem[]>(
        `/ai/conversations?limit=${limit}`,
      ),
    staleTime: 60 * 1000,
    enabled,
  })
}
