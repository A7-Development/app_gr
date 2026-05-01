// src/app/(app)/credito/layout.tsx
//
// Layout do modulo Credito. Minimal — apenas envolve as rotas filhas.
// O AuthGuard + Sidebar + Header sticky vem de (app)/layout.tsx.
//
// Modulo: Dossie de credito + workflow visual + agentes especialistas IA.
// Plano em ~/.claude/plans/c-users-ricardopimenta-a7-credit-securi-agile-hearth.md.

import type { ReactNode } from "react"

export default function CreditoLayout({ children }: { children: ReactNode }) {
  return <>{children}</>
}
