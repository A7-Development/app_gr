// src/app/(app)/bi/padrao/page.tsx
//
// BI · Pagina padrao — handoff bi-padrao (2026-04-26).
// Pattern em design-system/patterns/DashboardBiPadrao.tsx.
//
// Esta pagina e um wrapper fino. Para customizar:
//   1. Copie DashboardBiPadrao.tsx para co-localizar com a pagina.
//   2. Substitua mocks por queries reais via @tanstack/react-query.
//   3. Conecte AIPanel.sendMessage no LLM real.

"use client"

import { DashboardBiPadrao } from "@/design-system/patterns/DashboardBiPadrao"

export default function BiPadraoPage() {
  return <DashboardBiPadrao />
}
