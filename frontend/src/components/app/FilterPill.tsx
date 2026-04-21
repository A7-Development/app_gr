"use client"

import * as React from "react"
import { RiAddLine, RiArrowDownSLine } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { Checkbox } from "@/components/tremor/Checkbox"
import { Label } from "@/components/tremor/Label"
import {
  Popover,
  PopoverClose,
  PopoverContent,
  PopoverTrigger,
} from "@/components/tremor/Popover"
import { cx, focusRing } from "@/lib/utils"

export type FilterPillOption = {
  value: string
  label: string
}

type FilterPillProps = {
  /** Texto do botao quando sem selecao (ex.: "Produto", "UA"). */
  title: string
  /** Lista de opcoes disponiveis. */
  options: FilterPillOption[]
  /** Valores selecionados (multi). Array vazio = sem selecao. */
  value: string[]
  /** Chamado quando o usuario aplica mudancas (Apply) ou clica em Reset/X. */
  onChange: (next: string[]) => void
  className?: string
}

/**
 * FilterPill — botao-chip com popover de checkboxes multi-select.
 * Adaptado do `DataTableFilter` do template-dashboard oficial do Tremor
 * (src/components/ui/data-table/DataTableFilter.tsx), sem dependencia de
 * TanStack Table. Preserva o padrao visual:
 *  - Sem selecao: border tracejado + icone "+" + titulo.
 *  - Com selecao: border solido + icone "X" (clicavel para limpar) + titulo
 *    + separador | + lista de valores selecionados em destaque (azul).
 *  - Popover: Label "Filtrar por X" + checkboxes + botoes Aplicar/Limpar.
 *
 * Multi-select: o estado interno acumula ate o usuario clicar Aplicar.
 * A11y: Popover do Radix + labels associados aos checkboxes.
 */
export function FilterPill({
  title,
  options,
  value,
  onChange,
  className,
}: FilterPillProps) {
  // Estado interno do popover (pending changes antes do "Aplicar").
  const [pending, setPending] = React.useState<string[]>(value)

  // Sincroniza quando os filtros externos mudam (ex.: URL mudou por outra via).
  React.useEffect(() => {
    setPending(value)
  }, [value])

  const hasSelection = value.length > 0

  // Labels dos valores selecionados, para exibir no botao:
  //  - 1-2 itens: "FAT, CMS"
  //  - 3+ itens: "FAT e mais 2"
  const selectedLabels = React.useMemo(() => {
    if (!hasSelection) return null
    const labels = value.map(
      (v) => options.find((o) => o.value === v)?.label ?? v,
    )
    if (labels.length <= 2) return labels.join(", ")
    return `${labels[0]} e mais ${labels.length - 1}`
  }, [value, options, hasSelection])

  const toggle = (val: string, checked: boolean) => {
    setPending((prev) => {
      if (checked) return prev.includes(val) ? prev : [...prev, val]
      return prev.filter((x) => x !== val)
    })
  }

  // Estado de 3 fases para "Selecionar todos":
  //  - vazio:         checkbox vazio → click marca todos
  //  - todos:         checkbox checado → click desmarca todos
  //  - parcial (1+):  checkbox indeterminate (linha) → click marca todos
  const allPendingCount = pending.length
  const allOptionsCount = options.length
  const selectAllState: boolean | "indeterminate" =
    allPendingCount === 0
      ? false
      : allPendingCount === allOptionsCount
        ? true
        : "indeterminate"

  const toggleAll = () => {
    setPending(selectAllState === true ? [] : options.map((o) => o.value))
  }

  const apply = () => onChange(pending)
  const clear = () => {
    setPending([])
    onChange([])
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cx(
            "flex w-full items-center gap-x-1.5 whitespace-nowrap rounded border px-2 py-1.5 text-xs font-medium transition sm:w-fit",
            // Dual palette (CLAUDE.md §4): blue sinaliza "filtro aplicado"
            // com border solido + bg sutil + dot azul antes do titulo.
            // Estado vazio permanece discreto (dashed cinza).
            hasSelection
              ? [
                  "border-blue-500 bg-blue-50 text-gray-900",
                  "dark:border-blue-500 dark:bg-blue-500/10 dark:text-gray-50",
                  "hover:bg-blue-100 dark:hover:bg-blue-500/15",
                ]
              : [
                  "border-dashed border-gray-300 text-gray-600 hover:bg-gray-50",
                  "dark:border-gray-700 dark:text-gray-400 hover:dark:bg-gray-900",
                ],
            focusRing,
            className,
          )}
        >
          {/*
            Estado vazio: icone "+" para "adicionar filtro".
            Estado ativo: "X" clicavel para limpar (hover vermelho).
          */}
          <span
            aria-hidden={!hasSelection}
            aria-label={hasSelection ? `Limpar filtro ${title}` : undefined}
            role={hasSelection ? "button" : undefined}
            onClick={(e) => {
              if (hasSelection) {
                e.stopPropagation()
                clear()
              }
            }}
          >
            <RiAddLine
              className={cx(
                "-ml-px size-4 shrink-0 text-gray-500 transition",
                hasSelection && "rotate-45 hover:text-red-500",
              )}
              aria-hidden="true"
            />
          </span>

          {/*
            Dot azul — marcador visual forte de "filtro ativo".
            Estrategia copiada do template-dashboard oficial do Tremor.
          */}
          {hasSelection && (
            <span
              aria-hidden="true"
              className="size-1.5 shrink-0 rounded-full bg-blue-500 dark:bg-blue-400"
            />
          )}

          <span className="w-full text-left sm:w-fit">{title}</span>

          {hasSelection && (
            <>
              <span
                className="h-4 w-px bg-blue-300 dark:bg-blue-700"
                aria-hidden="true"
              />
              <span className="truncate font-semibold text-blue-700 dark:text-blue-300">
                {selectedLabels}
              </span>
            </>
          )}

          <RiArrowDownSLine
            className={cx(
              "size-4 shrink-0",
              hasSelection ? "text-blue-500 dark:text-blue-400" : "text-gray-500",
            )}
            aria-hidden="true"
          />
        </button>
      </PopoverTrigger>

      <PopoverContent
        align="start"
        sideOffset={6}
        className="min-w-56 max-w-64"
      >
        <form
          onSubmit={(e) => {
            e.preventDefault()
            apply()
          }}
        >
          <div className="space-y-2">
            <div>
              <Label className="text-sm font-medium">
                Filtrar por {title}
              </Label>
              <div className="mt-2 max-h-56 space-y-2 overflow-y-auto pr-1">
                {/* Selecionar todos — checkbox especial (3 fases). */}
                {options.length > 1 && (
                  <>
                    <div className="flex items-center gap-2">
                      <Checkbox
                        id={`filterpill-${title}-__all__`}
                        checked={selectAllState}
                        onCheckedChange={toggleAll}
                      />
                      <Label
                        htmlFor={`filterpill-${title}-__all__`}
                        className="text-sm font-medium"
                      >
                        Selecionar todos
                      </Label>
                    </div>
                    <div className="h-px bg-gray-200 dark:bg-gray-800" />
                  </>
                )}
                {options.map((opt) => {
                  const checked = pending.includes(opt.value)
                  const id = `filterpill-${title}-${opt.value}`
                  return (
                    <div key={opt.value} className="flex items-center gap-2">
                      <Checkbox
                        id={id}
                        checked={checked}
                        onCheckedChange={(c) => toggle(opt.value, c === true)}
                      />
                      <Label htmlFor={id} className="text-sm">
                        {opt.label}
                      </Label>
                    </div>
                  )
                })}
              </div>
            </div>
            <PopoverClose className="w-full" asChild>
              <Button type="submit" className="w-full">
                Aplicar
              </Button>
            </PopoverClose>
            {hasSelection && (
              <Button
                variant="secondary"
                className="w-full"
                type="button"
                onClick={clear}
              >
                Limpar
              </Button>
            )}
          </div>
        </form>
      </PopoverContent>
    </Popover>
  )
}
