"use client"

//
// TokenDialog — exibe o token de agente UMA unica vez (create/rotate).
// Depois de fechado, o token nao e mais recuperavel (backend guarda so o
// sha256) — o dialogo forca essa consciencia antes de fechar.
//

import * as React from "react"
import { RiCheckLine, RiFileCopyLine, RiKey2Line } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/tremor/Dialog"

export type TokenDialogProps = {
  /** Token plaintext a exibir; null = dialogo fechado. */
  token: string | null
  /** Nome do coletor (contexto no titulo). */
  coletorName: string
  onClose: () => void
}

export function TokenDialog({ token, coletorName, onClose }: TokenDialogProps) {
  const [copied, setCopied] = React.useState(false)

  const copy = React.useCallback(async () => {
    if (!token) return
    await navigator.clipboard.writeText(token)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [token])

  return (
    <Dialog open={token !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <RiKey2Line className="size-5 text-blue-600 dark:text-blue-400" aria-hidden />
            Token do coletor
          </DialogTitle>
          <DialogDescription>
            Use este token no instalador do Strata Collector em{" "}
            <span className="font-medium text-gray-900 dark:text-gray-100">
              {coletorName}
            </span>
            .
          </DialogDescription>
        </DialogHeader>

        <div className="flex items-center gap-2 rounded-md border border-gray-200 bg-gray-50 p-3 dark:border-gray-800 dark:bg-gray-900">
          <code className="min-w-0 flex-1 break-all font-mono text-xs text-gray-900 dark:text-gray-100">
            {token}
          </code>
          <Button
            variant="secondary"
            className="shrink-0"
            onClick={copy}
            aria-label="Copiar token"
          >
            {copied ? (
              <RiCheckLine className="size-4 text-emerald-600" aria-hidden />
            ) : (
              <RiFileCopyLine className="size-4" aria-hidden />
            )}
            {copied ? "Copiado" : "Copiar"}
          </Button>
        </div>

        <div
          className="rounded-md border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800 dark:border-amber-500/30 dark:bg-amber-500/10 dark:text-amber-300"
          role="alert"
        >
          <p className="font-semibold">Exibido uma unica vez</p>
          <p className="mt-1">
            Por seguranca, o Strata guarda apenas uma impressao digital do
            token. Ao fechar esta janela ele nao podera ser consultado
            novamente — se o perder, gere um novo em Acoes → Gerar novo token.
          </p>
        </div>

        <DialogFooter>
          <Button variant="primary" onClick={onClose}>
            Entendi, ja copiei
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
