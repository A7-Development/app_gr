"use client"

import { RiLightbulbLine } from "@remixicon/react"

import { cx } from "@/lib/utils"

type Props = {
  text: string | null
  loading?: boolean
  className?: string
}

export function BiTakeaway({ text, loading = false, className }: Props) {
  if (loading) {
    return (
      <div
        className={cx(
          "flex items-start gap-2 rounded-md border border-gray-200 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-900",
          className,
        )}
      >
        <div className="size-4 shrink-0 animate-pulse rounded-full bg-gray-200 dark:bg-gray-800" />
        <div className="h-4 w-2/3 animate-pulse rounded bg-gray-200 dark:bg-gray-800" />
      </div>
    )
  }

  if (!text) {
    return null
  }

  return (
    <div
      className={cx(
        "flex items-start gap-2 rounded-md border border-gray-200 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-900",
        className,
      )}
    >
      <RiLightbulbLine
        aria-hidden="true"
        className="mt-0.5 size-4 shrink-0 text-gray-500 dark:text-gray-400"
      />
      <p className="text-sm text-gray-700 dark:text-gray-300">{text}</p>
    </div>
  )
}
