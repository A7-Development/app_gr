// src/app/design/page.tsx
// Live Design System — dev-only route gated via middleware.
// Shows tokens, primitives, components, and patterns in every variant.

import { notFound } from "next/navigation"
import { DesignSystemClient } from "./DesignSystemClient"

export const metadata = { title: "Design System — Strata" }

export default function DesignPage() {
  if (process.env.NODE_ENV === "production") {
    notFound()
  }
  return <DesignSystemClient />
}
