// src/design-system/components/DrillDownSheet/index.tsx
// Drill-down Sheet — compound component API.
// Rule: drill-down NEVER opens full-screen modal. Always Sheet lateral right.
// URL deep-link: ?selected=ID via nuqs (or native URLSearchParams fallback).

"use client"

import * as React from "react"
import * as DialogPrimitive from "@radix-ui/react-dialog"
import * as VisuallyHidden from "@radix-ui/react-visually-hidden"
import {
  RiCloseLine,
  RiArrowLeftLine,
  RiArrowRightLine,
  RiMoreLine,
  RiCheckLine,
  RiExchangeFundsLine,
  RiFileTextLine,
  RiMoneyDollarCircleLine,
  RiRefreshLine,
  RiArrowUpLine,
  RiArrowDownLine,
  RiPencilLine,
} from "@remixicon/react"
import { cx, focusRing } from "@/lib/utils"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/tremor/Tabs"
import { fmt } from "@/design-system/tokens/typography"

export type SheetSize = "sm" | "md" | "lg"
const SIZE_W: Record<SheetSize, string> = {
  sm: "max-w-[400px]",
  md: "max-w-[560px]",
  lg: "max-w-[720px]",
}

interface SheetCtx {
  onClose: () => void
}
const SheetContext = React.createContext<SheetCtx>({ onClose: () => {} })
const useSheetCtx  = () => React.useContext(SheetContext)

export interface DrillDownSheetProps {
  open:                   boolean
  onClose:                () => void
  size?:                  SheetSize
  dismissOnClickOutside?: boolean
  children:               React.ReactNode
  title?:                 string
}

function DrillDownSheetRoot({
  open,
  onClose,
  size                  = "md",
  dismissOnClickOutside = true,
  children,
  title                 = "Detalhe",
}: DrillDownSheetProps) {
  return (
    <SheetContext.Provider value={{ onClose }}>
      <DialogPrimitive.Root open={open} onOpenChange={(v) => !v && onClose()}>
        <DialogPrimitive.Portal>
          <DialogPrimitive.Overlay
            onClick={dismissOnClickOutside ? onClose : undefined}
            className="fixed inset-0 z-40 bg-black/35 backdrop-blur-[2px] animate-dialog-overlay-show"
          />
          <DialogPrimitive.Content
            onPointerDownOutside={dismissOnClickOutside ? (e) => e.preventDefault() : undefined}
            onEscapeKeyDown={onClose}
            className={cx(
              "fixed inset-y-0 right-0 z-50 flex w-full flex-col overflow-hidden",
              SIZE_W[size],
              "bg-white dark:bg-[#090E1A]",
              "border-l border-gray-200 dark:border-gray-900",
              "shadow-2xl",
              "animate-drawer-slide-left-and-fade",
              "data-[state=closed]:animate-drawer-slide-right-and-fade",
            )}
          >
            <VisuallyHidden.Root>
              <DialogPrimitive.Title>{title}</DialogPrimitive.Title>
            </VisuallyHidden.Root>
            {children}
          </DialogPrimitive.Content>
        </DialogPrimitive.Portal>
      </DialogPrimitive.Root>
    </SheetContext.Provider>
  )
}

interface HeaderProps {
  breadcrumb?:   string[]
  statusSlot?:   React.ReactNode
  onPrevious?:   () => void
  onNext?:       () => void
  extraActions?: React.ReactNode
  className?:    string
}

function Header({ breadcrumb, statusSlot, onPrevious, onNext, extraActions, className }: HeaderProps) {
  const { onClose } = useSheetCtx()
  return (
    <div className={cx(
      "flex shrink-0 items-center gap-2 px-4 py-3",
      "border-b border-gray-200 dark:border-gray-800",
      className,
    )}>
      <DialogPrimitive.Close asChild>
        <button
          onClick={onClose}
          aria-label="Fechar"
          className={cx(
            "flex size-7 shrink-0 items-center justify-center rounded",
            "text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100",
            "hover:bg-gray-100 dark:hover:bg-gray-800",
            "transition-colors duration-100",
            focusRing,
          )}
        >
          <RiCloseLine className="size-4" aria-hidden="true" />
        </button>
      </DialogPrimitive.Close>

      {breadcrumb && (
        <nav className="flex min-w-0 items-center gap-1 text-xs text-gray-500 dark:text-gray-400">
          {breadcrumb.map((crumb, i) => (
            <React.Fragment key={i}>
              {i > 0 && <span aria-hidden="true">›</span>}
              <span className={cx(
                "truncate",
                i === breadcrumb.length - 1 && "font-mono text-gray-900 dark:text-gray-50",
              )}>{crumb}</span>
            </React.Fragment>
          ))}
        </nav>
      )}

      <div className="flex flex-1 items-center justify-end gap-1.5">
        {statusSlot}

        {(onPrevious || onNext) && (
          <div className="flex overflow-hidden rounded border border-gray-200 dark:border-gray-800">
            <button
              type="button"
              onClick={onPrevious}
              disabled={!onPrevious}
              aria-label="Item anterior"
              className="flex h-7 w-7 items-center justify-center text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-30 transition-colors"
            >
              <RiArrowLeftLine className="size-3.5" />
            </button>
            <span className="w-px bg-gray-200 dark:bg-gray-800" />
            <button
              type="button"
              onClick={onNext}
              disabled={!onNext}
              aria-label="Próximo item"
              className="flex h-7 w-7 items-center justify-center text-gray-500 hover:bg-gray-100 dark:hover:bg-gray-800 disabled:opacity-30 transition-colors"
            >
              <RiArrowRightLine className="size-3.5" />
            </button>
          </div>
        )}

        {extraActions}

        <button
          type="button"
          aria-label="Mais ações"
          className={cx(
            "flex size-7 items-center justify-center rounded",
            "text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-100",
            "hover:bg-gray-100 dark:hover:bg-gray-800",
            "transition-colors duration-100",
            focusRing,
          )}
        >
          <RiMoreLine className="size-4" />
        </button>
      </div>
    </div>
  )
}

interface HeroProps {
  id?:        string
  title:      string
  value?:     number
  delta?:     { value: number; label?: string }
  className?: string
}

function Hero({ id, title, value, delta, className }: HeroProps) {
  const dir = delta ? (delta.value >= 0 ? "up" : "down") : null
  const good = dir === "up"
  const ArrowIcon = dir === "up" ? RiArrowUpLine : RiArrowDownLine
  const deltaColor = good
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-red-600 dark:text-red-400"

  return (
    <div className={cx(
      "shrink-0 border-b border-gray-200 dark:border-gray-800",
      "bg-gray-50 dark:bg-gray-900/40 px-6 py-5",
      className,
    )}>
      {id && (
        <p className="mb-1.5 font-mono text-[11px] tracking-[0.04em] text-gray-500 dark:text-gray-400">
          {id}
        </p>
      )}
      <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50 mb-3 truncate">
        {title}
      </h2>
      {value != null && (
        <div>
          <p className="text-[28px] font-semibold tabular-nums tracking-tight text-gray-900 dark:text-gray-50 leading-none">
            {fmt.currencyWhole.format(value)}
          </p>
          {delta && (
            <p className="mt-1.5 flex items-center gap-1 text-xs tabular-nums">
              <span className={cx("inline-flex items-center gap-0.5 font-medium", deltaColor)}>
                <ArrowIcon className="size-3.5 shrink-0" aria-hidden="true" />
                {Math.abs(delta.value).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%
              </span>
              {delta.label && (
                <span className="text-gray-500 dark:text-gray-400">{delta.label}</span>
              )}
            </p>
          )}
        </div>
      )}
    </div>
  )
}

export interface TabDef {
  value:   string
  label:   string
  content: React.ReactNode
}

interface TabsZoneProps {
  tabs:          TabDef[]
  defaultValue?: string
}

function TabsZone({ tabs, defaultValue }: TabsZoneProps) {
  return (
    <Tabs defaultValue={defaultValue ?? tabs[0]?.value} className="flex flex-1 flex-col overflow-hidden">
      <TabsList className="shrink-0 rounded-none border-b border-gray-200 dark:border-gray-800 px-6">
        {tabs.map((t) => (
          <TabsTrigger key={t.value} value={t.value} className="text-sm">
            {t.label}
          </TabsTrigger>
        ))}
      </TabsList>
      {tabs.map((t) => (
        <TabsContent
          key={t.value}
          value={t.value}
          className="flex-1 overflow-y-auto px-6 py-5 mt-0 outline-none"
        >
          {t.content}
        </TabsContent>
      ))}
    </Tabs>
  )
}

function Body({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cx("flex-1 overflow-y-auto px-6 py-5", className)}>
      {children}
    </div>
  )
}

export interface PropertyRowDef {
  label:     string
  value:     React.ReactNode
  type?:     "text" | "date" | "number" | "percentage" | "currency"
  suffix?:   string
  editable?: boolean
  onEdit?:   (newValue: string) => void
}

function PropertyList({
  items,
  columns   = 2,
  className,
}: {
  items:      PropertyRowDef[]
  columns?:   1 | 2
  className?: string
}) {
  return (
    <dl className={cx(
      "grid gap-x-6 gap-y-4",
      columns === 2 ? "grid-cols-2" : "grid-cols-1",
      className,
    )}>
      {items.map((item, i) => (
        <PropertyRow key={i} {...item} />
      ))}
    </dl>
  )
}

function PropertyRow({ label, value, type, suffix, editable, onEdit }: PropertyRowDef) {
  const [editing, setEditing] = React.useState(false)
  const [draft, setDraft]     = React.useState(String(value ?? ""))

  const displayValue = React.useMemo(() => {
    if (value == null) return "—"
    if (type === "currency")   return fmt.currencyWhole.format(Number(value))
    if (type === "percentage") return `${Number(value).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`
    return value
  }, [value, type])

  function commitEdit() {
    onEdit?.(draft)
    setEditing(false)
  }

  return (
    <div>
      <dt className="text-[10px] font-medium uppercase tracking-[0.05em] text-gray-500 dark:text-gray-400 mb-1">
        {label}
      </dt>
      <dd className="group flex items-center gap-1.5">
        {editing ? (
          <input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onBlur={commitEdit}
            onKeyDown={(e) => { if (e.key === "Enter") commitEdit(); if (e.key === "Escape") setEditing(false) }}
            className="rounded border border-blue-400 px-1.5 py-0.5 text-sm text-gray-900 dark:text-gray-50 dark:bg-gray-800 outline-none ring-2 ring-blue-200 dark:ring-blue-700/30"
          />
        ) : (
          <span className="text-sm font-medium tabular-nums text-gray-900 dark:text-gray-50">
            {displayValue as React.ReactNode}
            {suffix && <span className="ml-1 text-gray-400">{suffix}</span>}
          </span>
        )}
        {editable && !editing && (
          <button
            type="button"
            onClick={() => setEditing(true)}
            aria-label={`Editar ${label}`}
            className="opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-gray-700 dark:hover:text-gray-200"
          >
            <RiPencilLine className="size-3" />
          </button>
        )}
      </dd>
    </div>
  )
}

export interface LinkedObject {
  type:   string
  label:  string
  sub?:   string
  value?: string
  href?:  string
}

function LinkedObjects({
  items,
  className,
}: {
  items:      LinkedObject[]
  className?: string
}) {
  return (
    <div className={cx("shrink-0", className)}>
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600">
        Objetos relacionados
      </p>
      <div className="flex gap-3 overflow-x-auto pb-1">
        {items.map((obj, i) => (
          <a
            key={i}
            href={obj.href ?? "#"}
            onClick={(e) => !obj.href && e.preventDefault()}
            className={cx(
              "flex min-w-[140px] shrink-0 flex-col gap-1 rounded border p-3",
              "border-gray-200 dark:border-gray-800",
              "bg-gray-50 dark:bg-gray-900",
              "hover:border-gray-300 dark:hover:border-gray-700",
              "transition-colors duration-100 cursor-pointer",
            )}
          >
            <p className="text-[10px] font-semibold uppercase tracking-[0.05em] text-gray-400 dark:text-gray-600">
              {obj.type}
            </p>
            <p className="text-xs font-medium text-gray-900 dark:text-gray-50 truncate">{obj.label}</p>
            {obj.sub && (
              <p className="text-[11px] text-gray-500 dark:text-gray-400 truncate">{obj.sub}</p>
            )}
            {obj.value && (
              <p className="mt-auto text-xs font-semibold tabular-nums text-gray-700 dark:text-gray-300">{obj.value}</p>
            )}
          </a>
        ))}
      </div>
    </div>
  )
}

export type FIDCEventType =
  | "cedida" | "lastreada" | "a-vencer"
  | "liquidada" | "atrasada" | "recomprada" | "custom"

const EVENT_CONFIG: Record<FIDCEventType, { label: string; color: string; Icon: React.ElementType }> = {
  cedida:     { label: "Cedida",     color: "#3B82F6", Icon: RiExchangeFundsLine },
  lastreada:  { label: "Lastreada",  color: "#8B5CF6", Icon: RiFileTextLine },
  "a-vencer": { label: "A vencer",   color: "#10B981", Icon: RiMoneyDollarCircleLine },
  liquidada:  { label: "Liquidada",  color: "#0891B2", Icon: RiCheckLine },
  atrasada:   { label: "Atrasada",   color: "#CA8A04", Icon: RiArrowUpLine },
  recomprada: { label: "Recomprada", color: "#737373", Icon: RiRefreshLine },
  custom:     { label: "Evento",     color: "#6B7280", Icon: RiFileTextLine },
}

export interface TimelineEventDef {
  type:        FIDCEventType
  date:        string
  actor?:      string
  description?: string
  current?:    boolean
}

function Timeline({ events, className }: { events: TimelineEventDef[]; className?: string }) {
  return (
    <div className={cx("relative pl-5", className)}>
      <div className="absolute left-[7px] top-3 bottom-3 w-px bg-gray-200 dark:bg-gray-800" />

      {events.map((ev, i) => {
        const config = EVENT_CONFIG[ev.type]
        const Icon = config.Icon
        return (
          <div key={i} className="relative mb-5 flex gap-3 last:mb-0">
            <div
              className={cx(
                "absolute -left-5 mt-[3px] z-10 flex size-3.5 shrink-0 items-center justify-center rounded-full",
                ev.current && "ring-2 ring-offset-2 ring-offset-white dark:ring-offset-[#090E1A]",
              )}
              style={{ background: config.color, ...(ev.current ? { boxShadow: `0 0 0 2px ${config.color}` } : {}) }}
            >
              <Icon className="size-2.5 text-white" aria-hidden="true" />
            </div>

            <div className="min-w-0">
              <p className="text-sm font-medium text-gray-900 dark:text-gray-50">
                {config.label}
              </p>
              <p className="mt-0.5 text-xs tabular-nums text-gray-500 dark:text-gray-400">
                {ev.date}
                {ev.actor && ` · ${ev.actor}`}
              </p>
              {ev.description && (
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{ev.description}</p>
              )}
              {ev.current && (
                <span className="mt-1 inline-flex items-center gap-1 rounded-full bg-gray-100 dark:bg-gray-800 px-2 py-0.5 text-[10px] font-medium text-gray-500 dark:text-gray-400">
                  Estado atual
                </span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function SectionLabel({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <p className={cx(
      "mb-3 text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600",
      className,
    )}>
      {children}
    </p>
  )
}

function Footer({ children, className }: { children: React.ReactNode; className?: string }) {
  return (
    <div className={cx(
      "flex shrink-0 items-center gap-2 px-5 py-3",
      "border-t border-gray-200 dark:border-gray-800",
      "bg-white dark:bg-[#090E1A]",
      className,
    )}>
      {children}
    </div>
  )
}

function Skeleton({ lines = 5 }: { lines?: number }) {
  return (
    <div className="space-y-3 animate-pulse">
      {Array(lines).fill(null).map((_, i) => (
        <div
          key={i}
          className="h-4 rounded bg-gray-100 dark:bg-gray-800"
          style={{ width: `${[90, 70, 85, 60, 75][i % 5]}%` }}
        />
      ))}
    </div>
  )
}

export const DrillDownSheet = Object.assign(DrillDownSheetRoot, {
  Header,
  Hero,
  Tabs:          TabsZone,
  Body,
  PropertyList,
  PropertyRow,
  LinkedObjects,
  Timeline,
  SectionLabel,
  Footer,
  Skeleton,
})

export {
  Header        as DrillDownHeader,
  Hero          as DrillDownHero,
  TabsZone      as DrillDownTabs,
  Body          as DrillDownBody,
  PropertyList,
  Timeline      as DrillDownTimeline,
  Footer        as DrillDownFooter,
}
