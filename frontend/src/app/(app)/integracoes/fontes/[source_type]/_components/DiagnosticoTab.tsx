"use client"

//
// Tab "Diagnostico" — engloba Testar (ping sincrono / sync manual) e
// Historico (lista de runs recentes do decision_log).
//
// PR 3 (2026-05-21): fundiu as antigas tabs "Testar" + "Historico" numa so.
// Razao: ambas servem ao mesmo cenario — "abro quando algo deu errado ou
// quando quero auditar uma sync recente". Nao vivem no fluxo normal.
//
// Sub-views via SegmentSwitch interno; deep-link preservado via `?view=`.
// Aliases retrocompat (`?tab=testar`/`?tab=historico`) sao resolvidos pela
// page pai (`../page.tsx`) antes de chegar aqui.
//

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"

import { SegmentSwitch } from "@/design-system/components/SegmentSwitch"
import { TestarTab } from "./TestarTab"
import { HistoricoTab } from "./HistoricoTab"
import type { SourceDetail, SourceTypeId } from "@/lib/api-client"

const VIEWS = [
  { value: "testar", label: "Testar" },
  { value: "historico", label: "Historico" },
] as const
type ViewKey = (typeof VIEWS)[number]["value"]

export function DiagnosticoTab({
  detail,
  sourceType,
}: {
  detail: SourceDetail
  sourceType: SourceTypeId
}) {
  const sp = useSearchParams()
  const router = useRouter()

  const activeView: ViewKey =
    (VIEWS.find((v) => v.value === sp.get("view"))?.value ?? "testar") as ViewKey

  function setView(next: ViewKey) {
    const qs = new URLSearchParams(sp?.toString() ?? "")
    if (next === "testar") qs.delete("view")
    else qs.set("view", next)
    const s = qs.toString()
    const base = window.location.pathname
    router.replace(s ? `${base}?${s}` : base)
  }

  return (
    <div className="flex flex-col gap-4">
      <SegmentSwitch<ViewKey>
        ariaLabel="Visualizacao de diagnostico"
        value={activeView}
        options={VIEWS as unknown as { value: ViewKey; label: string }[]}
        onChange={setView}
      />
      {activeView === "testar" && (
        <TestarTab detail={detail} sourceType={sourceType} />
      )}
      {activeView === "historico" && <HistoricoTab sourceType={sourceType} />}
    </div>
  )
}
