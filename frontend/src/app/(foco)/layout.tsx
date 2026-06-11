// src/app/(foco)/layout.tsx
//
// Route group do MODO FOCO (handoff Conceito D, frame D0).
// Dentro de uma análise, a navegação do app colapsa: a AppSidebar canônica
// de 256px dá lugar ao rail de 56px (ícones + tooltips) e a sidebar de
// etapas de 292px assume o espaço — quem renderiza a sidebar de etapas é
// a página, que conhece o estado do fluxo.
//
// Caminhos de volta: link "← Fila de análises" na sidebar de etapas,
// tecla Esc (registrada aqui), clique em outro item do rail.

"use client"

import * as React from "react"
import { usePathname, useRouter } from "next/navigation"
import { useQuery } from "@tanstack/react-query"

import { AuthGuard } from "@/design-system/components/AuthGuard"
import { FocusRail, type FocusRailItem } from "@/design-system/components"
import { fetchMe } from "@/lib/api-client"
import { getActiveModule } from "@/lib/modules"

function initialsOf(name: string | undefined): string {
  if (!name) return "—"
  const parts = name.trim().split(/\s+/)
  const first = parts[0]?.[0] ?? ""
  const last = parts.length > 1 ? parts[parts.length - 1][0] : ""
  return (first + last).toUpperCase() || "—"
}

export default function FocoLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const router = useRouter()

  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: fetchMe,
    staleTime: 5 * 60 * 1000,
  })

  const activeModule = React.useMemo(() => getActiveModule(pathname), [pathname])

  const items: FocusRailItem[] = React.useMemo(
    () =>
      activeModule.sections
        .filter((s) => s.href !== "#")
        .map((s) => ({
          href: s.href,
          label: s.name,
          icon: (s.icon ?? activeModule.icon) as FocusRailItem["icon"],
          active: pathname.startsWith(s.href) && s.href !== "/credito/dossies/novo",
          disabled: !s.enabled,
        })),
    [activeModule, pathname],
  )

  // Esc sai do modo foco e volta pra fila — exceto quando o usuário está
  // digitando (input/textarea/contenteditable) ou um overlay tratou o evento.
  React.useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || e.defaultPrevented) return
      const el = document.activeElement as HTMLElement | null
      if (el) {
        const tag = el.tagName
        if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable) {
          return
        }
      }
      // Overlays Radix abertos tratam o próprio Esc (defaultPrevented) — se
      // chegou aqui sem prevenção, é seguro sair.
      router.push("/credito/dossies")
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [router])

  return (
    <AuthGuard>
      <div className="flex h-screen overflow-hidden">
        <FocusRail
          items={items}
          userInitials={initialsOf(me?.user?.name)}
          userName={me?.user?.name}
        />
        <div className="flex min-w-0 flex-1">{children}</div>
      </div>
    </AuthGuard>
  )
}
