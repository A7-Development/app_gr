// Shim de retrocompatibilidade — rota antiga /integracoes/catalogo/[source_type].
// Renomeada para /integracoes/fontes/[source_type] em 2026-05-21 (PR 1).
// Preserva query string (tab, environment, ua) no redirect.

import { redirect } from "next/navigation"

type SearchParams = { [key: string]: string | string[] | undefined }

export default function CatalogoSourceLegacyRedirect({
  params,
  searchParams,
}: {
  params: { source_type: string }
  searchParams: SearchParams
}) {
  const qs = new URLSearchParams()
  for (const [k, v] of Object.entries(searchParams)) {
    if (Array.isArray(v)) v.forEach((x) => qs.append(k, x))
    else if (v != null) qs.set(k, v)
  }
  const s = qs.toString()
  const target = `/integracoes/fontes/${params.source_type}`
  redirect(s ? `${target}?${s}` : target)
}
