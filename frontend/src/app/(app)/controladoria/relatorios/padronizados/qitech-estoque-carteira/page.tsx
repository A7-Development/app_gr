// src/app/(app)/controladoria/relatorios/padronizados/qitech-estoque-carteira/page.tsx
//
// Detail page do relatorio "Carteira de recebiveis" (slug
// `qitech-estoque-carteira`). Override estatico da rota dinamica
// `[slug]/page.tsx` — Next.js prioriza arquivo estatico sobre dinamico.
// Outros 16 slugs continuam servidos pela rota generica.
//
// Esta pagina e um SWITCH baseado em `?data=YYYY-MM-DD`:
//   - SEM data: renderiza <SnapshotsLanding /> — lista de Solicitacoes +
//     Hero "Snapshot mais recente" + CTA "+ Solicitar".
//   - COM data: renderiza <CarteiraDashboard /> — KPIs + charts + tabela
//     + drilldown daquele snapshot especifico.
//
// Decisao de IA (2026-05-10): relatorios assincronos (refresh_kind=
// ON_DEMAND_ASYNC) usam landing-as-list, dashboard-as-destination. Pros 16
// outros slugs sincronos, landing = dashboard direto. Ver memoria
// `project_qitech_fidc_estoque_followups.md`.

"use client"

import * as React from "react"
import { useSearchParams } from "next/navigation"

import { CarteiraDashboard } from "./_components/CarteiraDashboard"
import { SnapshotsLanding } from "./_components/SnapshotsLanding"

function PageInner() {
  const searchParams = useSearchParams()
  const data = searchParams.get("data")

  if (data && /^\d{4}-\d{2}-\d{2}$/.test(data)) {
    return <CarteiraDashboard dataReferencia={data} />
  }
  return <SnapshotsLanding />
}

export default function QitechEstoqueCarteiraPage() {
  // Suspense boundary requerido pelo Next 14 quando useSearchParams e usado
  // num client component — sem isso, o SSR de outras rotas pode quebrar.
  return (
    <React.Suspense fallback={null}>
      <PageInner />
    </React.Suspense>
  )
}
