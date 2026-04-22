"use client"

/**
 * Estrela de favorito para um fundo CVM.
 *
 * Padrao Gmail/Outlook: vazia (cinza neutro) ↔ cheia (azul A7 = atencao).
 * Clique alterna o estado atraves do hook compartilhado `useFavoritos`
 * (optimistic update + toast em erro).
 */

import { RiStarFill, RiStarLine } from "@remixicon/react"
import type { MouseEvent } from "react"

import { Button } from "@/components/tremor/Button"
import { cx } from "@/lib/utils"

import { useFavoritos } from "./useFavoritos"

type FavoritoStarProps = {
  cnpj: string
  className?: string
}

export function FavoritoStar({ cnpj, className }: FavoritoStarProps) {
  const { isFavorito, toggle, isPending, isLoading } = useFavoritos()
  const ativo = isFavorito(cnpj)
  const Icon = ativo ? RiStarFill : RiStarLine

  const onClick = (e: MouseEvent<HTMLButtonElement>) => {
    e.stopPropagation()
    toggle(cnpj)
  }

  return (
    <Button
      variant="ghost"
      onClick={onClick}
      disabled={isPending || isLoading}
      aria-label={ativo ? "Remover dos favoritos" : "Adicionar aos favoritos"}
      aria-pressed={ativo}
      title={ativo ? "Remover dos favoritos" : "Adicionar aos favoritos"}
      className={cx("size-8 shrink-0 p-0", className)}
    >
      <Icon
        className={cx(
          "size-5 shrink-0",
          ativo
            ? "text-blue-500 dark:text-blue-400"
            : "text-gray-400 dark:text-gray-500",
        )}
        aria-hidden="true"
      />
    </Button>
  )
}
