// src/app/(app)/controladoria/relatorios/espelho/[admin]/[slug]/page.tsx
//
// Tab Espelho da Administradora — mesmos dados que Padronizados, com
// admin explicito no header. Phase 4 acrescenta lentes operacionais
// (frescor, reprocessar, logs do sync).

"use client"

import { useParams } from "next/navigation"

import { ReportDetailPage } from "../../../_components/ReportDetailPage"

export default function EspelhoSlugPage() {
  const params = useParams<{ admin: string; slug: string }>()
  return (
    <ReportDetailPage slug={params.slug} mode="espelho" admin={params.admin} />
  )
}
