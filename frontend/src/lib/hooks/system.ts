"use client"

/**
 * React Query hooks pra endpoints `/system/*` (cross-cutting health).
 *
 * Espelha backend/app/api/v1/system.py.
 */

import { useQuery } from "@tanstack/react-query"

import { system } from "@/lib/api-client"

/**
 * Pollado a cada 60s pelo badge no header — endpoint barato (1 SELECT em TSEC).
 * Retorna `failing_count` + lista de endpoints com last_sync_status='erro'.
 */
export function useSyncHealthSummary() {
  return useQuery({
    queryKey: ["system", "sync-health-summary"],
    queryFn: () => system.syncHealthSummary(),
    refetchInterval: 60_000,
    refetchIntervalInBackground: false,
    staleTime: 30_000,
  })
}
