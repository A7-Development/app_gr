import * as React from "react"

export default function TemplatesLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return <div className="mx-auto max-w-7xl p-6 sm:p-8">{children}</div>
}
