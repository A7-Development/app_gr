"use client"

import * as React from "react"
import { RiPencilLine, RiCloseLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Button } from "@/components/tremor/Button"
import { Input } from "@/components/tremor/Input"
import { Textarea } from "@/components/tremor/Textarea"

/**
 * Input de campo sensivel (secret). Nunca expoe valor persistido.
 *
 * Comportamento:
 * - Se `persisted=true`, mostra placeholder "***SET***" num campo desabilitado.
 *   Usuario clica "Substituir" para liberar edicao. Se deixar vazio, nao envia.
 * - Se `persisted=false`, mostra campo vazio, obrigatorio para submit.
 * - `multiline` habilita Textarea (para PEMs e certificados).
 *
 * Integracao com react-hook-form:
 * - `value` e `onChange` sao controlados externamente.
 * - Ao "Substituir" setamos `value=""` (mudanca explicita) e focamos.
 * - Ao "Cancelar" voltamos para o estado persistido (onClear callback).
 */
type SecretInputProps = {
  value: string
  onChange: (v: string) => void
  /** Campo ja tem valor salvo no servidor? */
  persisted: boolean
  /** Se true, usa Textarea (PEM multi-linha). */
  multiline?: boolean
  rows?: number
  placeholder?: string
  /** Chamado ao cancelar a substituicao (voltar ao estado persistido). */
  onClear?: () => void
  disabled?: boolean
  hasError?: boolean
  id?: string
  name?: string
  className?: string
}

export function SecretInput({
  value,
  onChange,
  persisted,
  multiline = false,
  rows = 4,
  placeholder,
  onClear,
  disabled,
  hasError,
  id,
  name,
  className,
}: SecretInputProps) {
  const [editing, setEditing] = React.useState(!persisted)
  const inputRef = React.useRef<HTMLInputElement | HTMLTextAreaElement>(null)

  React.useEffect(() => {
    // Se o estado persistido mudou (ex.: apos save bem sucedido), volta para view mode.
    setEditing(!persisted)
  }, [persisted])

  const effectivePlaceholder = persisted && !editing ? "***SET***" : placeholder

  function handleStartEdit() {
    setEditing(true)
    onChange("")
    setTimeout(() => inputRef.current?.focus(), 0)
  }

  function handleCancel() {
    setEditing(false)
    onChange("")
    onClear?.()
  }

  const showReplaceBtn = persisted && !editing
  const showCancelBtn = persisted && editing

  return (
    <div className={cx("flex items-start gap-2", className)}>
      <div className="flex-1">
        {multiline ? (
          <Textarea
            ref={inputRef as React.RefObject<HTMLTextAreaElement>}
            id={id}
            name={name}
            value={editing ? value : ""}
            onChange={(e) => onChange(e.target.value)}
            placeholder={effectivePlaceholder}
            rows={rows}
            disabled={disabled || (persisted && !editing)}
            hasError={hasError}
            className="font-mono text-xs"
          />
        ) : (
          <Input
            ref={inputRef as React.RefObject<HTMLInputElement>}
            id={id}
            name={name}
            type="password"
            value={editing ? value : ""}
            onChange={(e) => onChange(e.target.value)}
            placeholder={effectivePlaceholder}
            disabled={disabled || (persisted && !editing)}
            hasError={hasError}
          />
        )}
      </div>
      {showReplaceBtn && (
        <Button
          type="button"
          variant="secondary"
          onClick={handleStartEdit}
          disabled={disabled}
        >
          <RiPencilLine className="mr-1.5 size-4" aria-hidden />
          Substituir
        </Button>
      )}
      {showCancelBtn && (
        <Button
          type="button"
          variant="ghost"
          onClick={handleCancel}
          disabled={disabled}
        >
          <RiCloseLine className="mr-1.5 size-4" aria-hidden />
          Cancelar
        </Button>
      )}
    </div>
  )
}
