// Estados de loading/erro compartilhados pelas abas do /bi/panorama.

"use client"

import { cx } from "@/lib/utils"
import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import { cardTokens } from "@/design-system/tokens/card"

export function TabSkeleton() {
  return (
    <div className="flex flex-col gap-4">
      <div className="h-64 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
      <div className="h-72 animate-pulse rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900" />
    </div>
  )
}

export function TabError({ onRetry }: { onRetry: () => void }) {
  return (
    <Card className={cx(cardTokens.body, "py-12 text-center")}>
      <p className="text-sm text-gray-500 dark:text-gray-400">
        Não foi possível carregar esta análise.
      </p>
      <Button variant="ghost" className="mt-2" onClick={onRetry}>
        Tentar novamente
      </Button>
    </Card>
  )
}
