"use client"

import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { useState } from "react"

export function QueryProvider({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            staleTime: 60_000, // 1 min
            // Revalida ao remontar (navegacao entre paginas) e ao focar janela
            // — garante que tela sempre acompanha o sync mais recente sem
            // martelar o backend (ainda respeita staleTime).
            refetchOnMount: "always",
            refetchOnWindowFocus: true,
            retry: 1,
          },
        },
      }),
  )
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>
}
