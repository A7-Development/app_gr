// Shim de retrocompatibilidade — rota antiga /integracoes/sync.
// Renomeada para /integracoes/operacao/status em 2026-05-21 (PR 1).
// Preserva query string (environment, tab, etc) no redirect.

import { redirect } from "next/navigation"

type SearchParams = { [key: string]: string | string[] | undefined }

export default function SyncLegacyRedirect({
  searchParams,
}: {
  searchParams: SearchParams
}) {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(searchParams)) {
    if (Array.isArray(v)) v.forEach((x) => qs.append(k, x))
    else if (v != null) qs.set(k, v)
  }
  const s = qs.toString()
  redirect(s ? `/integracoes/operacao/status?${s}` : "/integracoes/operacao/status")
}
