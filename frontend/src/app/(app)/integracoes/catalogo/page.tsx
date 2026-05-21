// Shim de retrocompatibilidade — rota antiga /integracoes/catalogo.
// Renomeada para /integracoes/fontes em 2026-05-21 (PR 1).
// Preserva query string (environment, etc) no redirect.

import { redirect } from "next/navigation"

type SearchParams = { [key: string]: string | string[] | undefined }

export default function CatalogoLegacyRedirect({
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
  redirect(s ? `/integracoes/fontes?${s}` : "/integracoes/fontes")
}
