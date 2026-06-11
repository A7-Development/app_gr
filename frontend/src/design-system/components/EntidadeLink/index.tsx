"use client"

/**
 * EntidadeLink — torna qualquer nome de cedente/sacado clicavel no sistema.
 *
 * Clicar abre o `<EntidadePeek />` (drawer global) setando `?entidade=<documento>`
 * na URL via nuqs. Abrir = `push` (botao voltar fecha o peek); navegar de um
 * peek para outro (ex.: membro do grupo dentro do proprio peek) = `replace`
 * (nao infla o historico) — controle via prop `history`.
 *
 * Sem `documento` (cedente "(n/d)", sacado nao resolvido), renderiza o children
 * como texto plano — nunca um link morto.
 *
 * Uso tipico em cell renderer de DataTable (stopPropagation evita disparar o
 * onRowClick da linha):
 *
 *   cell: ({ row }) => (
 *     <EntidadeLink documento={row.original.cedente_documento}>
 *       {row.original.cedente_nome}
 *     </EntidadeLink>
 *   )
 */

import { useQueryState } from "nuqs"
import * as React from "react"

import { cx } from "@/lib/utils"

type EntidadeLinkProps = {
  /** CPF/CNPJ em digitos (aceita padded-15 do Bitfin — normalizado no backend). */
  documento: string | null | undefined
  children: React.ReactNode
  /** `push` (default): abrir peek = entrada no historico (voltar fecha).
   *  `replace`: navegar lateralmente entre peeks (dentro do proprio peek). */
  history?: "push" | "replace"
  className?: string
}

export function EntidadeLink({
  documento,
  children,
  history = "push",
  className,
}: EntidadeLinkProps) {
  const [, setEntidade] = useQueryState("entidade", { history })

  if (!documento) {
    return <span className={className}>{children}</span>
  }

  return (
    <button
      type="button"
      onClick={(e) => {
        e.stopPropagation()
        void setEntidade(documento, { history })
      }}
      className={cx(
        "cursor-pointer text-left underline-offset-2 hover:text-blue-600 hover:underline",
        "dark:hover:text-blue-400",
        className,
      )}
      title="Ver ficha da entidade"
    >
      {children}
    </button>
  )
}
