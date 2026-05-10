// src/app/(app)/controladoria/relatorios/padronizados/[slug]/page.tsx
//
// Tab Padronizados — formato A7 comparavel entre administradoras.
// Ver Opcao A (lente operacional) em CLAUDE.md plano
// `~/.claude/plans/shimmering-snuggling-snail.md`.

"use client"

import { useParams } from "next/navigation"

import { ReportDetailPage } from "../../_components/ReportDetailPage"

export default function PadronizadoSlugPage() {
  const params = useParams<{ slug: string }>()
  return <ReportDetailPage slug={params.slug} mode="padronizado" />
}
