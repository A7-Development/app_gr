// src/app/(app)/bi/padrao/page.tsx
//
// BI · Pagina padrao — handoff bi-padrao (2026-04-26).
// Pattern em design-system/patterns/DashboardBiPadrao.tsx.
//
// Wiring real (2026-04-30):
//   - sendMessage   liga AIPanel ao backend POST /ai/chat (SSE).
//   - insights      le GET /ai/insights (cache server-side 10min).
//   - quotaSlot     mostra <AIQuotaIndicator /> com saldo mensal de creditos.
//
// Pre-requisitos para o wiring funcionar:
//   - Backend rodando (uvicorn) com migration 9a1ccaa15a01 aplicada.
//   - Tenant logado tem `tenant_ai_subscription.enabled = true`.
//   - User logado tem `user_ai_permission.permission >= read`.
//   - Maintainer cadastrou key Anthropic em /admin/ia/providers.

"use client"

import * as React from "react"

import { AIQuotaIndicator } from "@/design-system/components/AIQuotaIndicator"
import { DashboardBiPadrao } from "@/design-system/patterns/DashboardBiPadrao"
import { useAIChat, useAIInsights, useAIQuota } from "@/lib/hooks/ai"

export default function BiPadraoPage() {
  const [conversationId, setConversationId] = React.useState<string | null>(null)

  const quotaQ = useAIQuota()
  const insightsQ = useAIInsights({
    page: "/bi/padrao",
    period: "30d",
    // kpisBlock vem dos KPIs reais quando a pagina os tiver via React Query.
    kpisBlock: undefined,
  })

  const { send } = useAIChat({
    conversationId,
    onConversationCreated: setConversationId,
  })

  const insights = React.useMemo(
    () =>
      (insightsQ.data?.insights ?? []).map((i) => ({ text: i.text })),
    [insightsQ.data],
  )

  return (
    <DashboardBiPadrao
      sendMessage={send}
      insights={insights.length > 0 ? insights : undefined}
      quotaSlot={
        <AIQuotaIndicator quota={quotaQ.data} loading={quotaQ.isLoading} />
      }
    />
  )
}
