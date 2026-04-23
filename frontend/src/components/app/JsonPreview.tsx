"use client"

import * as React from "react"
import { RiFileCopyLine, RiCheckLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Button } from "@/components/tremor/Button"

/** Preview readonly de payload JSON (pretty-printed). Mostra em <pre> com scroll vertical. */
export function JsonPreview({
  value,
  maxHeight = 320,
  className,
}: {
  value: unknown
  maxHeight?: number
  className?: string
}) {
  const text = React.useMemo(() => {
    try {
      return JSON.stringify(value, null, 2)
    } catch {
      return String(value)
    }
  }, [value])
  const [copied, setCopied] = React.useState(false)

  async function handleCopy() {
    if (typeof navigator === "undefined" || !navigator.clipboard) return
    await navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }

  return (
    <div
      className={cx(
        "relative rounded border border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900",
        className,
      )}
    >
      <div className="absolute right-2 top-2">
        <Button
          type="button"
          variant="secondary"
          onClick={handleCopy}
          className="h-7 px-2 py-0"
        >
          {copied ? (
            <RiCheckLine className="size-4" aria-hidden />
          ) : (
            <RiFileCopyLine className="size-4" aria-hidden />
          )}
          <span className="ml-1.5 text-xs">
            {copied ? "Copiado" : "Copiar"}
          </span>
        </Button>
      </div>
      <pre
        className="overflow-auto p-3 pr-24 font-mono text-xs text-gray-900 dark:text-gray-50"
        style={{ maxHeight }}
      >
        {text}
      </pre>
    </div>
  )
}
