// src/design-system/components/DataTableShell/ShellStatusFilter.tsx
//
// ShellStatusFilter — filtro de status multi-select do DataTableShell
// (handoff "Tabela canonica v2", DataTableShell v2.dc.html, arquetipos 1-2).
//
// "Dropdown quieto (multi-selecao); gatilho fechado mostra cor + contagem do
// filtro ativo." Anatomia fiel ao spec:
//   - Trigger em repouso: chip 26px (ri-equalizer-2-line 14px gray-500 ·
//     label 11px gray-500 · caret 15px gray-400).
//   - Trigger ativo: + divisoria 1px · valor na COR do status (dot 6px + nome
//     semibold) · pill de contagem (17px, rounded-full, bg tone/10, 11px bold
//     tabular). Com 2+ status selecionados: dots empilhados + "N status" +
//     pill neutra com a contagem total.
//   - Menu: Popover com checkbox por status (aplica no toggle — sem
//     Apply/Reset; para o padrao pendente use <FilterPill>).
//
// Tones alinhados aos badges semanticos de tableTokens (§4/§6): success=
// emerald, warning=amber, danger=red, neutral=gray, info=blue.

"use client"

import * as React from "react"
import { RiArrowDownSLine, RiEqualizer2Line } from "@remixicon/react"

import { Checkbox } from "@/components/tremor/Checkbox"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/tremor/Popover"
import { cx, focusRing } from "@/lib/utils"

export type ShellStatusTone = "success" | "warning" | "danger" | "neutral" | "info"

const TONE: Record<
  ShellStatusTone,
  { dot: string; text: string; pill: string }
> = {
  success: {
    dot: "bg-emerald-500",
    text: "text-emerald-600 dark:text-emerald-400",
    pill: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
  },
  warning: {
    dot: "bg-amber-500",
    text: "text-amber-600 dark:text-amber-400",
    pill: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
  },
  danger: {
    dot: "bg-red-500",
    text: "text-red-600 dark:text-red-400",
    pill: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
  },
  neutral: {
    dot: "bg-gray-400",
    text: "text-gray-600 dark:text-gray-400",
    pill: "bg-gray-100 text-gray-600 dark:bg-gray-500/10 dark:text-gray-400",
  },
  info: {
    dot: "bg-blue-500",
    text: "text-blue-600 dark:text-blue-400",
    pill: "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300",
  },
}

export type ShellStatusOption = {
  value: string
  label: string
  tone: ShellStatusTone
  /** Contagem de linhas neste status (o Shell calcula e injeta). */
  count?: number
}

type ShellStatusFilterViewProps = {
  /** Rotulo do filtro no trigger. Default "Status". */
  label?: string
  options: ShellStatusOption[]
  /** Valores selecionados. Vazio = todos (filtro inativo). */
  value: string[]
  onChange: (next: string[]) => void
  /** Contagem total de linhas que casam com a selecao (pill do trigger). */
  activeCount?: number
  ariaLabel?: string
}

/** Apresentacao pura (trigger + popover). O calculo de counts/filtragem vive
 *  no DataTableShell — use a prop `statusFilter` de la, nao este componente
 *  direto (exportado para preview/demo). */
export function ShellStatusFilter({
  label = "Status",
  options,
  value,
  onChange,
  activeCount,
  ariaLabel,
}: ShellStatusFilterViewProps) {
  const selected = options.filter((o) => value.includes(o.value))
  const active = selected.length > 0
  const single = selected.length === 1 ? selected[0] : null

  function toggle(v: string) {
    onChange(value.includes(v) ? value.filter((x) => x !== v) : [...value, v])
  }

  return (
    <Popover>
      <PopoverTrigger asChild>
        <button
          type="button"
          aria-label={ariaLabel ?? `Filtrar por ${label.toLowerCase()}`}
          className={cx(
            "inline-flex h-[26px] shrink-0 items-center gap-[7px] whitespace-nowrap rounded-[4px] border px-2.5 text-[13px] transition-colors duration-100",
            "border-gray-200 bg-white text-gray-700 hover:bg-gray-50",
            "dark:border-gray-800 dark:bg-gray-950 dark:text-gray-300 dark:hover:bg-gray-900",
            focusRing,
          )}
        >
          <RiEqualizer2Line className="size-3.5 text-gray-500 dark:text-gray-400" aria-hidden />
          <span className="text-[11px] text-gray-500 dark:text-gray-400">{label}</span>

          {active && (
            <>
              <span className="h-3.5 w-px bg-gray-200 dark:bg-gray-800" aria-hidden />
              {single ? (
                <span className={cx("inline-flex items-center gap-1.5 font-semibold", TONE[single.tone].text)}>
                  <span className={cx("size-1.5 rounded-full", TONE[single.tone].dot)} aria-hidden />
                  {single.label}
                </span>
              ) : (
                <span className="inline-flex items-center gap-1.5 font-semibold text-gray-900 dark:text-gray-100">
                  <span className="inline-flex items-center gap-0.5" aria-hidden>
                    {selected.map((o) => (
                      <span key={o.value} className={cx("size-1.5 rounded-full", TONE[o.tone].dot)} />
                    ))}
                  </span>
                  {selected.length} status
                </span>
              )}
              {activeCount !== undefined && (
                <span
                  className={cx(
                    "inline-flex h-[17px] items-center rounded-full px-1.5 text-[11px] font-bold tabular-nums",
                    single ? TONE[single.tone].pill : TONE.neutral.pill,
                  )}
                >
                  {activeCount}
                </span>
              )}
            </>
          )}

          <RiArrowDownSLine className="size-[15px] text-gray-400 dark:text-gray-600" aria-hidden />
        </button>
      </PopoverTrigger>

      <PopoverContent align="start" className="w-56 p-1">
        <div role="group" aria-label={ariaLabel ?? `Filtrar por ${label.toLowerCase()}`}>
          {options.map((opt) => {
            const checked = value.includes(opt.value)
            return (
              <label
                key={opt.value}
                className={cx(
                  "flex cursor-pointer items-center gap-2 rounded px-2 py-1.5",
                  "hover:bg-gray-50 dark:hover:bg-gray-900",
                )}
              >
                <Checkbox
                  checked={checked}
                  onCheckedChange={() => toggle(opt.value)}
                  className="size-3.5"
                />
                <span className={cx("size-1.5 shrink-0 rounded-full", TONE[opt.tone].dot)} aria-hidden />
                <span className="min-w-0 flex-1 truncate text-xs text-gray-900 dark:text-gray-100">
                  {opt.label}
                </span>
                {opt.count !== undefined && (
                  <span className="text-[11px] tabular-nums text-gray-400 dark:text-gray-600">
                    {opt.count}
                  </span>
                )}
              </label>
            )
          })}
        </div>
        {active && (
          <>
            <div className="my-1 border-t border-t-gray-100 dark:border-t-gray-900" aria-hidden />
            <button
              type="button"
              onClick={() => onChange([])}
              className="flex w-full items-center rounded px-2 py-1.5 text-xs font-medium text-gray-500 hover:bg-gray-50 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-900 dark:hover:text-gray-200"
            >
              Limpar filtro
            </button>
          </>
        )}
      </PopoverContent>
    </Popover>
  )
}
