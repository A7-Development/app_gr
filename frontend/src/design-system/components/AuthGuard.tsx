"use client"

import { useRouter } from "next/navigation"
import { useEffect, useState } from "react"

import { ApiError, fetchMe } from "@/lib/api-client"

/**
 * Client-side auth guard for the (app) shell.
 * - Chama /auth/me no mount
 * - Se falhar (401 / token ausente / expirado) → redireciona para /login
 * - Enquanto checa, renderiza nada (evita flash de conteudo autenticado)
 */
export function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchMe()
      .then(() => {
        if (!cancelled) setReady(true)
      })
      .catch((e: unknown) => {
        if (cancelled) return
        if (e instanceof ApiError && e.status === 401) {
          router.replace("/login")
        } else {
          // Erro inesperado — loga mas ainda manda pro login pra nao travar UI
          console.error("[AuthGuard] falha ao validar sessao:", e)
          router.replace("/login")
        }
      })
    return () => {
      cancelled = true
    }
  }, [router])

  if (!ready) return null
  return <>{children}</>
}
