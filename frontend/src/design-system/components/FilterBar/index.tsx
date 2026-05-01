// src/design-system/components/FilterBar/index.tsx
//
// FilterBar — Z3 canonica dos patterns DashboardBiPadrao / DashboardOperacional /
// ListagemComDrilldown. Ver CLAUDE.md §7.1.
//
// ANATOMY (refinamento 2026-05-01)
// ─────────────────────────────────────────────────────────────────────────────
// Faixa sticky externa (bg-gray-50) + Card interno (bg-white border rounded
// p-3) — mesma estrutura visual de `/credito/workflows` (ListagemCrudCards).
// A faixa cinza mascara conteudo passando por baixo durante scroll; o Card
// delimita visualmente a zona de filtros sem brigar com a TabNavigation acima.
//
// CONTROLES — altura e tipografia canonica
// ─────────────────────────────────────────────────────────────────────────────
// Todos os controles (FilterChip, FilterSearch, RemovableChip, MoreFiltersButton,
// SavedViewsDropdown) renderizam a `h-[30px] px-2.5 text-[13px]` — mesma altura
// dos botoes do header (HEADER_BTN_CLASS em DashboardHeaderActions). Esses dois
// valores sao candidatos a token (tokens.controls.height/text) na varredura
// final do Modo Iteracao de Design.
//
// PER-ELEMENT COLORING (regra dura)
// ─────────────────────────────────────────────────────────────────────────────
// Controles compostos (icon + label + valor) NAO usam `text-X` no <button>
// raiz — cor no raiz se propaga por inheritance e achata a hierarquia visual.
// Padrao FilterChip:
//   - Icone:  text-gray-500 (inactive) / text-blue-500 (active)
//   - Label:  text-[11px] text-gray-500
//   - Valor:  font-medium text-gray-900 (inactive) / text-blue-700 (active)
//
// Componentes:
//   FilterBar           Faixa sticky + Card interno (composicao Z3 completa)
//   FilterSearch        Input de busca (h-[30px], expand-on-focus 56→72)
//   FilterChip          Trigger de filtro categorico (label + valor + chevron)
//   RemovableChip       Filtro aplicado com botao X
//   MoreFiltersButton   Botao "Mais filtros" (onClick handler) — nao suporta
//                       asChild ainda; paginas que precisam Popover trigger
//                       duplicam anatomy (CLAUDE.md §7.1 antipattern)
//   SavedViewsDropdown  Dropdown de visualizacoes salvas (localStorage)

"use client"

import * as React from "react"
import {
  RiCloseLine,
  RiEqualizerLine,
  RiSearchLine,
  RiBookmarkLine,
  RiBookmarkFill,
  RiAddLine,
  RiArrowDownSLine,
  RiCheckLine,
  type RemixiconComponentType,
} from "@remixicon/react"
import { cx, focusInput, focusRing } from "@/lib/utils"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/tremor/Popover"

export interface SavedView {
  id:     string
  name:   string
  params: Record<string, string>
}

interface FilterBarProps {
  children:      React.ReactNode
  extraActions?: React.ReactNode
  className?:    string
}

export function FilterBar({ children, extraActions, className }: FilterBarProps) {
  const [scrolled, setScrolled] = React.useState(false)
  const sentinelRef = React.useRef<HTMLDivElement>(null)

  React.useEffect(() => {
    const el = sentinelRef.current
    if (!el) return
    const obs = new IntersectionObserver(
      ([entry]) => setScrolled(!entry.isIntersecting),
      { threshold: 0 },
    )
    obs.observe(el)
    return () => obs.disconnect()
  }, [])

  return (
    <>
      <div ref={sentinelRef} aria-hidden="true" className="h-px w-full" />
      {/* Faixa sticky com fundo da pagina — mascara conteudo que passa por baixo durante scroll. */}
      <div
        className={cx(
          "sticky top-0 z-10 -mx-6 px-6 pt-2 pb-3",
          "bg-gray-50 dark:bg-gray-950",
          scrolled && "shadow-xs",
          "transition-shadow duration-150",
        )}
      >
        {/* Card visualmente delimitado — mesma anatomia de /credito/workflows. */}
        <div
          role="toolbar"
          aria-label="Filtros"
          className={cx(
            "flex flex-wrap items-center gap-2 rounded border p-3",
            "border-gray-200 bg-white dark:border-gray-900 dark:bg-[#090E1A]",
            className,
          )}
        >
          <div className="flex flex-1 flex-wrap items-center gap-2">{children}</div>
          {extraActions && (
            <div className="ml-auto flex shrink-0 items-center gap-2">{extraActions}</div>
          )}
        </div>
      </div>
    </>
  )
}

interface FilterSearchProps extends React.InputHTMLAttributes<HTMLInputElement> {
  onClear?: () => void
}

export function FilterSearch({ className, onClear, ...props }: FilterSearchProps) {
  return (
    <div className={cx("relative flex items-center", className)}>
      <RiSearchLine
        className="pointer-events-none absolute left-2.5 size-3.5 shrink-0 text-gray-400 dark:text-gray-600"
        aria-hidden="true"
      />
      <input
        type="search"
        className={cx(
          "h-[30px] w-56 rounded border pl-7 text-[13px]",
          props.value ? "pr-7" : "pr-2.5",
          "border-gray-200 dark:border-gray-800",
          "bg-white dark:bg-gray-950",
          "text-gray-900 dark:text-gray-50",
          "placeholder:text-gray-400 dark:placeholder:text-gray-600",
          "[&::-webkit-search-cancel-button]:hidden",
          "transition-[width] duration-150 focus:w-72",
          focusInput,
        )}
        {...props}
      />
      {props.value && onClear && (
        <button
          type="button"
          onClick={onClear}
          aria-label="Limpar busca"
          className="absolute right-2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
        >
          <RiCloseLine className="size-3.5" />
        </button>
      )}
    </div>
  )
}

interface FilterChipProps {
  label:      string
  value:      React.ReactNode
  active?:    boolean
  /** Optional leading icon (Remix Icon component). */
  icon?:      RemixiconComponentType
  children?:  React.ReactNode
  className?: string
}

export function FilterChip({ label, value, active = false, icon: Icon, children, className }: FilterChipProps) {
  const trigger = (
    <button
      type="button"
      className={cx(
        "inline-flex h-[30px] shrink-0 items-center gap-1.5 whitespace-nowrap rounded-[4px] border px-2.5 text-[13px]",
        "transition-colors duration-100",
        active
          ? "border-blue-300 bg-blue-50 hover:bg-blue-100 dark:border-blue-500 dark:bg-blue-500/10 dark:hover:bg-blue-500/15"
          : "border-gray-200 bg-white hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-950 dark:hover:bg-gray-900",
        focusRing,
        className,
      )}
    >
      {Icon && (
        <Icon
          className={cx("size-3.5 shrink-0", active ? "text-blue-500" : "text-gray-500 dark:text-gray-400")}
          aria-hidden="true"
        />
      )}
      <span className={cx("text-[11px]", active ? "text-gray-600 dark:text-gray-400" : "text-gray-500 dark:text-gray-400")}>
        {label}
      </span>
      <span
        aria-hidden="true"
        className={cx("h-3.5 w-px", active ? "bg-blue-300 dark:bg-blue-700" : "bg-gray-200 dark:bg-gray-700")}
      />
      <span className={cx("font-medium", active ? "text-blue-700 dark:text-blue-300" : "text-gray-900 dark:text-gray-50")}>
        {value}
      </span>
      <RiArrowDownSLine
        className={cx("size-3.5 shrink-0", active ? "text-blue-500" : "text-gray-400 dark:text-gray-500")}
        aria-hidden="true"
      />
    </button>
  )

  if (!children) return trigger

  return (
    <Popover>
      <PopoverTrigger asChild>{trigger}</PopoverTrigger>
      <PopoverContent align="start" sideOffset={6} className="min-w-52 max-w-72 p-1">
        {children}
      </PopoverContent>
    </Popover>
  )
}

interface RemovableChipProps {
  label:      string
  value:      React.ReactNode
  onRemove:   () => void
  className?: string
}

export function RemovableChip({ label, value, onRemove, className }: RemovableChipProps) {
  return (
    <div className={cx(
      "inline-flex h-[30px] items-center gap-1.5 rounded-[4px] border px-2.5 text-[13px]",
      "border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
      className,
    )}>
      <span className="text-gray-500 dark:text-gray-400">{label}:</span>
      <span className="font-medium text-blue-700 dark:text-blue-300">{value}</span>
      <button
        type="button"
        onClick={onRemove}
        aria-label={`Remover filtro ${label}`}
        className={cx("ml-0.5 rounded text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors", focusRing)}
      >
        <RiCloseLine className="size-3" />
      </button>
    </div>
  )
}

interface MoreFiltersButtonProps {
  onClick?:   () => void
  count?:     number
  className?: string
}

export function MoreFiltersButton({ onClick, count, className }: MoreFiltersButtonProps) {
  const hasCount = typeof count === "number" && count > 0
  return (
    <button
      type="button"
      onClick={onClick}
      className={cx(
        "inline-flex h-[30px] shrink-0 items-center gap-1.5 whitespace-nowrap rounded-[4px] border px-2.5 text-[13px] transition-colors duration-100",
        hasCount
          ? "border-blue-300 bg-blue-50 hover:bg-blue-100 dark:border-blue-500 dark:bg-blue-500/10 dark:hover:bg-blue-500/15"
          : "border-gray-200 bg-white hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-950 dark:hover:bg-gray-900",
        focusRing,
        className,
      )}
    >
      <RiEqualizerLine
        className={cx("size-3.5 shrink-0", hasCount ? "text-blue-500" : "text-gray-500 dark:text-gray-400")}
        aria-hidden="true"
      />
      <span className={cx("font-medium", hasCount ? "text-blue-700 dark:text-blue-300" : "text-gray-900 dark:text-gray-50")}>
        Mais filtros
      </span>
      {hasCount && (
        <span className="inline-flex min-w-4 items-center justify-center rounded-sm bg-blue-500 px-1 text-[10px] font-semibold text-white">
          {count}
        </span>
      )}
    </button>
  )
}

const VIEWS_STORAGE_KEY = "strata:saved-views"

function getSavedViews(): SavedView[] {
  if (typeof window === "undefined") return []
  try { return JSON.parse(localStorage.getItem(VIEWS_STORAGE_KEY) ?? "[]") } catch { return [] }
}

function setSavedViews(views: SavedView[]) {
  try { localStorage.setItem(VIEWS_STORAGE_KEY, JSON.stringify(views)) } catch {}
}

interface SavedViewsDropdownProps {
  activeViewId?:  string
  currentParams?: Record<string, string>
  onApplyView?:   (view: SavedView) => void
  className?:     string
}

export function SavedViewsDropdown({
  activeViewId,
  currentParams = {},
  onApplyView,
  className,
}: SavedViewsDropdownProps) {
  const [views, setViews]     = React.useState<SavedView[]>([])
  const [newName, setNewName] = React.useState("")
  const [saving, setSaving]   = React.useState(false)

  React.useEffect(() => {
    setViews(getSavedViews())
  }, [])

  function saveCurrentView() {
    if (!newName.trim()) return
    const view: SavedView = {
      id:     `view-${Date.now()}`,
      name:   newName.trim(),
      params: currentParams,
    }
    const updated = [...views, view]
    setViews(updated)
    setSavedViews(updated)
    setNewName("")
    setSaving(false)
  }

  function deleteView(id: string) {
    const updated = views.filter((v) => v.id !== id)
    setViews(updated)
    setSavedViews(updated)
  }

  const hasViews   = views.length > 0
  const activeView = views.find((v) => v.id === activeViewId)

  const trigger = (
    <button
      type="button"
      className={cx(
        "inline-flex h-[30px] shrink-0 items-center gap-1.5 whitespace-nowrap rounded border px-2.5 text-[13px] transition-colors duration-100",
        activeView
          ? "border-blue-400 bg-blue-50 text-blue-700 dark:border-blue-500 dark:bg-blue-500/10 dark:text-blue-300"
          : "border-gray-200 bg-white text-gray-700 hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-300",
        focusRing,
        className,
      )}
    >
      {activeView
        ? <RiBookmarkFill className="size-3.5 shrink-0 text-blue-500" />
        : <RiBookmarkLine className="size-3.5 shrink-0" />}
      <span className="font-medium">{activeView ? activeView.name : "Visualizações"}</span>
      <RiArrowDownSLine className="size-3 shrink-0 text-gray-400" aria-hidden="true" />
    </button>
  )

  return (
    <Popover>
      <PopoverTrigger asChild>{trigger}</PopoverTrigger>
      <PopoverContent align="end" sideOffset={6} className="w-60 p-2">
        {hasViews && (
          <div className="mb-2 space-y-0.5">
            <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600">
              Salvas
            </p>
            {views.map((view) => (
              <div key={view.id} className="group flex items-center gap-1">
                <button
                  type="button"
                  onClick={() => onApplyView?.(view)}
                  className={cx(
                    "flex flex-1 items-center gap-2 rounded px-2 py-1.5 text-left text-sm transition-colors",
                    view.id === activeViewId
                      ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                      : "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
                    focusRing,
                  )}
                >
                  <span className="flex-1 truncate">{view.name}</span>
                  {view.id === activeViewId && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                </button>
                <button
                  type="button"
                  onClick={() => deleteView(view.id)}
                  aria-label={`Excluir visualização ${view.name}`}
                  className="hidden size-6 shrink-0 items-center justify-center rounded text-gray-300 hover:text-red-500 group-hover:flex dark:text-gray-600"
                >
                  <RiCloseLine className="size-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="border-t border-gray-100 dark:border-gray-800 pt-2">
          {saving ? (
            <div className="flex items-center gap-1.5 px-1">
              <input
                type="text"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && saveCurrentView()}
                placeholder="Nome da visualização"
                autoFocus
                className={cx(
                  "h-7 flex-1 rounded border px-2 text-xs",
                  "border-gray-200 dark:border-gray-700",
                  "bg-white dark:bg-gray-950 text-gray-900 dark:text-gray-50",
                  "placeholder:text-gray-400",
                  focusInput,
                )}
              />
              <button
                type="button"
                onClick={saveCurrentView}
                disabled={!newName.trim()}
                className="rounded bg-blue-500 px-2 py-1 text-[11px] font-medium text-white hover:bg-blue-600 disabled:opacity-50"
              >
                Salvar
              </button>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setSaving(true)}
              className={cx(
                "flex w-full items-center gap-2 rounded px-2 py-1.5 text-xs text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800 transition-colors",
                focusRing,
              )}
            >
              <RiAddLine className="size-3.5 shrink-0" aria-hidden="true" />
              Salvar visão atual
            </button>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
