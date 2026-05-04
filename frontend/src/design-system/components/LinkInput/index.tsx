// src/design-system/components/LinkInput/index.tsx
//
// LinkInput: form simples de URL + descricao opcional. react-hook-form + zod
// para validacao de URL. Submete via callback onSubmit, limpa o form.
//
// LinkList: lista de links (URLs externas anexadas ao step ou ao dossie).
// Cada item: favicon + title + description + relative timestamp + actions
// (abrir em nova aba, remover).

"use client"

import * as React from "react"
import { zodResolver } from "@hookform/resolvers/zod"
import {
  RiDeleteBinLine,
  RiExternalLinkLine,
  RiLink,
} from "@remixicon/react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { Button } from "@/components/tremor/Button"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import { Textarea } from "@/components/tremor/Textarea"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

// ─── LinkInput ──────────────────────────────────────────────────────────────

const linkSchema = z.object({
  url: z.string().url("URL invalida"),
  title: z.string().max(512).optional().or(z.literal("")),
  description: z.string().max(2000).optional().or(z.literal("")),
})

export type LinkInputValues = z.infer<typeof linkSchema>

export type LinkInputProps = {
  onSubmit: (values: { url: string; title?: string; description?: string }) =>
    | Promise<void>
    | void
  /** Toggle modo compacto vs expandido. Default: compact (so URL); expandido
   *  abre quando user comeca a digitar. */
  className?: string
}

export function LinkInput({ onSubmit, className }: LinkInputProps) {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
    reset,
    watch,
  } = useForm<LinkInputValues>({
    resolver: zodResolver(linkSchema),
    defaultValues: { url: "", title: "", description: "" },
  })

  const url = watch("url")
  const expanded = url.length > 0

  const submit = handleSubmit(async (values) => {
    await onSubmit({
      url: values.url,
      title: values.title?.trim() || undefined,
      description: values.description?.trim() || undefined,
    })
    reset({ url: "", title: "", description: "" })
  })

  return (
    <form onSubmit={submit} className={cx("space-y-2", className)}>
      <div>
        <Label htmlFor="link-url" className="sr-only">
          URL
        </Label>
        <div className="relative">
          <RiLink
            className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-gray-400 dark:text-gray-500"
            aria-hidden
          />
          <Input
            id="link-url"
            type="url"
            placeholder="https://servicos.receita.fazenda.gov.br/..."
            className="pl-8"
            {...register("url")}
          />
        </div>
        {errors.url && (
          <p className="mt-1 text-xs text-red-600 dark:text-red-400">
            {errors.url.message}
          </p>
        )}
      </div>

      {expanded && (
        <>
          <div>
            <Label htmlFor="link-title" className="text-xs">
              Titulo (opcional)
            </Label>
            <Input
              id="link-title"
              placeholder="Ex.: Cadastro publico do CNPJ"
              {...register("title")}
              maxLength={512}
            />
          </div>
          <div>
            <Label htmlFor="link-desc" className="text-xs">
              Descricao (opcional)
            </Label>
            <Textarea
              id="link-desc"
              rows={2}
              placeholder="Por que esse link e relevante para a analise..."
              {...register("description")}
              maxLength={2000}
            />
          </div>
        </>
      )}

      <div className="flex items-center justify-end gap-2">
        {expanded && (
          <Button
            type="button"
            variant="ghost"
            onClick={() => reset({ url: "", title: "", description: "" })}
            disabled={isSubmitting}
          >
            Cancelar
          </Button>
        )}
        <Button type="submit" disabled={!url || isSubmitting} isLoading={isSubmitting}>
          Adicionar link
        </Button>
      </div>
    </form>
  )
}

// ─── LinkList ───────────────────────────────────────────────────────────────

export type LinkListItem = {
  id: string
  url: string
  title?: string | null
  description?: string | null
  added_at: string
  added_by?: string | null
  added_by_label?: string | null
  /** node_id ao qual o link esta vinculado (null = link global do dossie). */
  node_id?: string | null
}

export type LinkListProps = {
  links: LinkListItem[]
  onDelete?: (id: string) => void
  /** Quando o requester nao e o adder nem admin, omitir delete. */
  canDelete?: (item: LinkListItem) => boolean
  emptyMessage?: string
  className?: string
}

export function LinkList({
  links,
  onDelete,
  canDelete,
  emptyMessage = "Nenhum link anexado",
  className,
}: LinkListProps) {
  if (links.length === 0) {
    return (
      <p className={cx(tableTokens.cellSecondary, "py-3 text-center", className)}>
        {emptyMessage}
      </p>
    )
  }
  return (
    <ul className={cx("space-y-1", className)}>
      {links.map((link) => {
        const allowDelete = canDelete?.(link) ?? Boolean(onDelete)
        const displayTitle = link.title?.trim() || hostname(link.url)
        return (
          <li
            key={link.id}
            className="flex items-start gap-2 rounded border border-gray-100 bg-white px-2.5 py-1.5 dark:border-gray-900 dark:bg-gray-950"
          >
            <FaviconImage url={link.url} />
            <div className="min-w-0 flex-1">
              <a
                href={link.url}
                target="_blank"
                rel="noopener noreferrer"
                className={cx(
                  "inline-flex items-center gap-1 truncate text-xs font-medium",
                  "text-blue-600 hover:text-blue-700 hover:underline",
                  "dark:text-blue-400 dark:hover:text-blue-300",
                )}
              >
                <span className="truncate">{displayTitle}</span>
                <RiExternalLinkLine className="size-3 shrink-0 opacity-60" aria-hidden />
              </a>
              <p className={cx(tableTokens.cellSecondary, "truncate")}>
                {hostname(link.url)}
                {" · "}
                {formatRelativeShort(link.added_at)}
                {link.added_by_label && <> · {link.added_by_label}</>}
              </p>
              {link.description && (
                <p className="mt-0.5 line-clamp-2 text-xs text-gray-700 dark:text-gray-300">
                  {link.description}
                </p>
              )}
            </div>
            {allowDelete && onDelete && (
              <Button
                variant="ghost"
                className="size-7 shrink-0 p-0"
                onClick={() => onDelete(link.id)}
                aria-label={`Remover link ${displayTitle}`}
              >
                <RiDeleteBinLine className="size-3.5" aria-hidden />
              </Button>
            )}
          </li>
        )
      })}
    </ul>
  )
}

// ─── Favicon (best-effort via Google s2) ────────────────────────────────────

function FaviconImage({ url }: { url: string }) {
  const [error, setError] = React.useState(false)
  const host = hostname(url)
  const src = `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=32`
  if (error) {
    return (
      <RiLink
        className="mt-0.5 size-4 shrink-0 text-gray-400 dark:text-gray-500"
        aria-hidden
      />
    )
  }
  return (
    // MOTIVO: <img> cru — favicon vem de URL externa, nao precisa do
    // Image do Next (sem optimization, sem priority). Tamanho fixo 16px.
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={src}
      alt=""
      width={16}
      height={16}
      className="mt-0.5 size-4 shrink-0 rounded-sm"
      onError={() => setError(true)}
    />
  )
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function hostname(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "")
  } catch {
    return url
  }
}

function formatRelativeShort(iso: string): string {
  const ts = Date.parse(iso)
  if (Number.isNaN(ts)) return "—"
  const diffSec = Math.max(0, Math.floor((Date.now() - ts) / 1000))
  if (diffSec < 60) return "agora"
  const diffMin = Math.floor(diffSec / 60)
  if (diffMin < 60) return `ha ${diffMin}min`
  const diffH = Math.floor(diffMin / 60)
  if (diffH < 24) return `ha ${diffH}h`
  const diffD = Math.floor(diffH / 24)
  if (diffD < 30) return `ha ${diffD}d`
  return new Date(ts).toLocaleDateString("pt-BR")
}
