"use client"

import { useQuery } from "@tanstack/react-query"

import { biBenchmark2 } from "@/lib/api-client"

export function useBenchmark2Fundos() {
  return useQuery({
    queryKey: ["bi", "benchmark2", "fundos"] as const,
    queryFn: () => biBenchmark2.fundos(),
    staleTime: 5 * 60 * 1000,
  })
}
