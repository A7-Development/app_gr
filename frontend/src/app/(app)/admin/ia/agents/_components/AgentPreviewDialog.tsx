"use client"

//
// Dialog de preview do system_text composto (persona + expertises + task).
// Reutilizado pela lista e pelo cockpit. Extraido da page.tsx.
//

import { Badge } from "@/components/tremor/Badge"
import { Button } from "@/components/tremor/Button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/tremor/Dialog"
import { tableTokens } from "@/design-system/tokens/table"
import type { AIAgentDefinitionPreview } from "@/lib/api-client"
import { cx } from "@/lib/utils"

export function AgentPreviewDialog({
  preview,
  onClose,
}: {
  preview: AIAgentDefinitionPreview | null
  onClose: () => void
}) {
  return (
    <Dialog open={preview !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-4xl">
        <DialogHeader>
          <DialogTitle>
            Preview system_text — {preview?.name}@v{preview?.version}
          </DialogTitle>
          <DialogDescription>
            Bloco XML composto (persona + expertises + task) que e enviado ao
            LLM em runtime. Cache breakpoint Anthropic aplicado apos este
            system_text.
          </DialogDescription>
        </DialogHeader>
        {preview && (
          <div className="flex flex-col gap-3">
            <div className="flex flex-wrap gap-1 text-[12px]">
              <Badge variant="neutral" className={tableTokens.badge}>
                {preview.model}
              </Badge>
              {preview.fallback_model && (
                <Badge variant="neutral" className={tableTokens.badge}>
                  fallback: {preview.fallback_model}
                </Badge>
              )}
              {preview.temperature !== null && (
                <Badge variant="neutral" className={tableTokens.badge}>
                  T={preview.temperature}
                </Badge>
              )}
              {preview.max_tokens !== null && (
                <Badge variant="neutral" className={tableTokens.badge}>
                  max={preview.max_tokens}
                </Badge>
              )}
            </div>
            <pre
              className={cx(
                "max-h-[500px] overflow-auto rounded-md border p-3 font-mono text-[12px] leading-relaxed",
                "border-gray-200 bg-gray-50 text-gray-900",
                "dark:border-gray-800 dark:bg-gray-900 dark:text-gray-100",
              )}
            >
              {preview.system_text}
            </pre>
            <div className="text-[12px] text-gray-500 dark:text-gray-400">
              {preview.persona_full_id && (
                <>
                  persona: <code>{preview.persona_full_id}</code> ·{" "}
                </>
              )}
              {preview.expertise_full_ids.length > 0 && (
                <>
                  expertises:{" "}
                  {preview.expertise_full_ids.map((id) => (
                    <code key={id} className="mr-1">
                      {id}
                    </code>
                  ))}
                  ·{" "}
                </>
              )}
              prompt: <code>{preview.prompt_full_id}</code>
            </div>
          </div>
        )}
        <DialogFooter>
          <Button variant="secondary" onClick={onClose}>
            Fechar
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
