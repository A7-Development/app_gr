// src/design-system/components/CommandPalette/index.tsx
// Universal command palette — ⌘K / Ctrl+K.
// Adds: CommandPaletteProvider + useCommandPalette context,
//       8 canonical sections, ⌘+Shift+K (close without persisting),
//       numbered shortcuts ⌘1-9 on first 9 results, loading skeleton.

"use client"

import * as React from "react"
import { Command } from "cmdk"
import * as DialogPrimitive from "@radix-ui/react-dialog"
import {
  RiSearchLine,
  RiHomeLine,
  RiExchangeFundsLine,
  RiBuildingLine,
  RiUserStarLine,
  RiFileChart2Line,
  RiAddLine,
  RiDownloadLine,
  RiLineChartLine,
  RiSettings3Line,
  RiQuestionLine,
  RiKeyboardLine,
  RiWallet3Line,
  RiArrowRightUpLine,
  RiTimeLine,
  type RemixiconComponentType,
} from "@remixicon/react"
import { cx } from "@/lib/utils"

export interface CommandItem {
  id:           string
  label:        string
  description?: string
  icon?:        RemixiconComponentType
  shortcut?:    string[]
  onSelect:     () => void
  group:        string
}

interface CommandPaletteCtx {
  open:    boolean
  setOpen: (open: boolean) => void
  toggle:  () => void
}

const CommandPaletteContext = React.createContext<CommandPaletteCtx>({
  open:    false,
  setOpen: () => {},
  toggle:  () => {},
})

export function useCommandPalette() {
  return React.useContext(CommandPaletteContext)
}

export interface CommandPaletteProviderProps {
  children:  React.ReactNode
  items?:    CommandItem[]
  navItems?: CommandItem[]
}

export function CommandPaletteProvider({ children, items = [], navItems = [] }: CommandPaletteProviderProps) {
  const [open, setOpen] = React.useState(false)
  const toggle = React.useCallback(() => setOpen((o) => !o), [])

  React.useEffect(() => {
    function handler(e: KeyboardEvent) {
      const meta = e.metaKey || e.ctrlKey
      if (meta && e.shiftKey && e.key === "K") {
        e.preventDefault()
        setOpen(false)
        return
      }
      if (meta && !e.shiftKey && e.key === "k") {
        e.preventDefault()
        setOpen((o) => !o)
      }
    }
    document.addEventListener("keydown", handler)
    return () => document.removeEventListener("keydown", handler)
  }, [])

  return (
    <CommandPaletteContext.Provider value={{ open, setOpen, toggle }}>
      {children}
      <CommandPaletteModal
        open={open}
        onOpenChange={setOpen}
        extraItems={items}
        extraNavItems={navItems}
      />
    </CommandPaletteContext.Provider>
  )
}

const RECENTS_KEY = "strata:command:recents"
const MAX_RECENTS = 5

function getRecents(): string[] {
  if (typeof window === "undefined") return []
  try { return JSON.parse(localStorage.getItem(RECENTS_KEY) ?? "[]") } catch { return [] }
}

function pushRecent(id: string) {
  const prev = getRecents().filter((r) => r !== id)
  try { localStorage.setItem(RECENTS_KEY, JSON.stringify([id, ...prev].slice(0, MAX_RECENTS))) } catch {}
}

function Kbd({ keys }: { keys: string[] }) {
  return (
    <span className="ml-auto flex shrink-0 items-center gap-0.5">
      {keys.map((k, i) => (
        <kbd
          key={i}
          className="inline-flex h-5 min-w-5 items-center justify-center rounded border border-gray-200 dark:border-gray-700 bg-gray-100 dark:bg-gray-800 px-1 font-mono text-[10px] font-medium text-gray-500 dark:text-gray-400"
        >
          {k}
        </kbd>
      ))}
    </span>
  )
}

function CommandSkeleton() {
  return (
    <div className="animate-pulse px-2 py-2 space-y-1.5">
      {[80, 65, 75].map((w, i) => (
        <div key={i} className="flex items-center gap-3 px-2 py-2">
          <div className="size-7 rounded bg-gray-100 dark:bg-gray-800 shrink-0" />
          <div className="h-3 rounded bg-gray-100 dark:bg-gray-800" style={{ width: `${w}%` }} />
        </div>
      ))}
    </div>
  )
}

function CommandRow({
  item,
  onSelect,
  numberHint,
}: {
  item:        CommandItem
  onSelect:    () => void
  numberHint?: number
}) {
  const Icon = item.icon
  const shortcut = numberHint != null ? ["⌘", String(numberHint)] : item.shortcut

  return (
    <Command.Item
      value={`${item.id} ${item.label} ${item.description ?? ""}`}
      onSelect={onSelect}
      className={cx(
        "flex items-center gap-3 rounded px-2 py-2 text-sm cursor-pointer mx-1",
        "text-gray-900 dark:text-gray-50",
        "aria-selected:bg-blue-50 dark:aria-selected:bg-blue-500/10",
        "transition-colors duration-75",
      )}
    >
      {Icon ? (
        <span className="flex size-7 shrink-0 items-center justify-center rounded bg-gray-100 dark:bg-gray-800 text-gray-500 dark:text-gray-400">
          <Icon className="size-3.5" aria-hidden="true" />
        </span>
      ) : (
        <span className="size-7 shrink-0" />
      )}

      <span className="flex min-w-0 flex-col">
        <span className="truncate font-medium">{item.label}</span>
        {item.description && (
          <span className="truncate text-xs text-gray-500 dark:text-gray-400">{item.description}</span>
        )}
      </span>

      {shortcut ? (
        <Kbd keys={shortcut} />
      ) : (
        <RiArrowRightUpLine className="ml-auto size-3.5 shrink-0 text-gray-300 dark:text-gray-600" aria-hidden="true" />
      )}
    </Command.Item>
  )
}

function GroupHeading({ children }: { children: React.ReactNode }) {
  return (
    <p className="px-3 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600">
      {children}
    </p>
  )
}

function defaultNavItems(onNavigate: (path: string) => void): CommandItem[] {
  return [
    { id: "nav-dashboard",     label: "Dashboard",     icon: RiHomeLine,          group: "Navegação", shortcut: ["G", "D"], onSelect: () => onNavigate("/") },
    { id: "nav-carteira",      label: "Carteira",      icon: RiWallet3Line,       group: "Navegação", shortcut: ["G", "C"], onSelect: () => onNavigate("/bi/carteira") },
    { id: "nav-cedentes",      label: "Cedentes",      icon: RiBuildingLine,      group: "Navegação", shortcut: ["G", "E"], onSelect: () => onNavigate("/cedentes") },
    { id: "nav-sacados",       label: "Sacados",       icon: RiUserStarLine,      group: "Navegação",                       onSelect: () => onNavigate("/sacados") },
    { id: "nav-cessoes",       label: "Cessões",       icon: RiExchangeFundsLine, group: "Navegação", shortcut: ["G", "S"], onSelect: () => onNavigate("/cessoes") },
    { id: "nav-rentabilidade", label: "Rentabilidade", icon: RiLineChartLine,     group: "Navegação",                       onSelect: () => onNavigate("/bi/rentabilidade") },
    { id: "nav-relatorios",    label: "Relatórios",    icon: RiFileChart2Line,    group: "Navegação",                       onSelect: () => onNavigate("/relatorios") },
  ]
}

function defaultActionItems(): CommandItem[] {
  return [
    { id: "act-nova-cessao",   label: "Nova cessão",        icon: RiAddLine,      group: "Ações", shortcut: ["C"], onSelect: () => {} },
    { id: "act-exportar",      label: "Exportar relatório", icon: RiDownloadLine, group: "Ações", shortcut: ["E"], onSelect: () => {} },
  ]
}

function defaultConfigItems(): CommandItem[] {
  return [
    { id: "cfg-settings", label: "Configurações", icon: RiSettings3Line, group: "Configurações", onSelect: () => {} },
  ]
}

function defaultHelpItems(): CommandItem[] {
  return [
    { id: "help-atalhos", label: "Ver todos os atalhos", icon: RiKeyboardLine, group: "Ajuda", shortcut: ["?"], onSelect: () => {} },
    { id: "help-docs",    label: "Documentação",         icon: RiQuestionLine, group: "Ajuda",                  onSelect: () => {} },
  ]
}

interface CommandPaletteModalProps {
  open:           boolean
  onOpenChange:   (open: boolean) => void
  extraItems?:    CommandItem[]
  extraNavItems?: CommandItem[]
  loading?:       boolean
}

export function CommandPaletteModal({
  open,
  onOpenChange,
  extraItems    = [],
  extraNavItems = [],
  loading       = false,
}: CommandPaletteModalProps) {
  const [search, setSearch]   = React.useState("")
  const [recents, setRecents] = React.useState<string[]>([])

  React.useEffect(() => {
    if (open) setRecents(getRecents())
  }, [open])

  React.useEffect(() => {
    if (!open) setSearch("")
  }, [open])

  const navItems = React.useMemo(
    () => [...defaultNavItems(() => onOpenChange(false)), ...extraNavItems],
    [onOpenChange, extraNavItems],
  )
  const actionItems = React.useMemo(() => defaultActionItems(), [])
  const configItems = React.useMemo(() => defaultConfigItems(), [])
  const helpItems   = React.useMemo(() => defaultHelpItems(), [])

  const domainGroups = React.useMemo(() => {
    const map = new Map<string, CommandItem[]>()
    for (const item of extraItems) {
      if (!map.has(item.group)) map.set(item.group, [])
      map.get(item.group)!.push(item)
    }
    return map
  }, [extraItems])

  const recentItems = React.useMemo(() => {
    const all = [...navItems, ...actionItems, ...configItems, ...helpItems, ...extraItems]
    return recents.map((id) => all.find((i) => i.id === id)).filter(Boolean) as CommandItem[]
  }, [recents, navItems, actionItems, configItems, helpItems, extraItems])

  let resultCount = 0

  function handleSelect(item: CommandItem, persist = true) {
    if (persist) pushRecent(item.id)
    item.onSelect()
    onOpenChange(false)
  }

  function makeRow(item: CommandItem, forceHint?: number) {
    resultCount++
    const hint = !search ? undefined : resultCount <= 9 ? resultCount : undefined
    return (
      <CommandRow
        key={item.id}
        item={item}
        onSelect={() => handleSelect(item)}
        numberHint={forceHint ?? hint}
      />
    )
  }

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-black/40 backdrop-blur-sm animate-dialog-overlay-show" />
        <DialogPrimitive.Content
          aria-label="Paleta de comandos"
          className={cx(
            "fixed left-1/2 top-[18%] z-50 w-full max-w-[640px] -translate-x-1/2 mx-4",
            "overflow-hidden rounded-lg border shadow-2xl",
            "bg-white/95 dark:bg-[#0A0F1C]/95 backdrop-blur-md",
            "border-gray-300 dark:border-gray-700",
            "animate-dialog-content-show",
          )}
        >
          <DialogPrimitive.Title className="sr-only">Paleta de comandos</DialogPrimitive.Title>
          <Command className="flex flex-col" shouldFilter loop>
            <div className="flex items-center gap-3 border-b border-gray-200 dark:border-gray-800 px-4">
              <RiSearchLine className="size-4 shrink-0 text-gray-400 dark:text-gray-500" aria-hidden="true" />
              <Command.Input
                value={search}
                onValueChange={setSearch}
                placeholder="Busque por cedente, sacado, cessão ou ação..."
                className="h-12 flex-1 bg-transparent text-base outline-none text-gray-900 dark:text-gray-50 placeholder:text-gray-400 dark:placeholder:text-gray-600"
              />
              {search && (
                <button
                  type="button"
                  onClick={() => setSearch("")}
                  className="text-xs text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                >
                  Limpar
                </button>
              )}
            </div>

            <Command.List className="max-h-[380px] overflow-y-auto py-2">
              {loading && <CommandSkeleton />}

              {!loading && (
                <Command.Empty className="flex flex-col items-center gap-2 py-12 text-center">
                  <RiSearchLine className="size-8 text-gray-200 dark:text-gray-700" aria-hidden="true" />
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Nenhum resultado para{" "}
                    <span className="font-medium text-gray-700 dark:text-gray-200">&quot;{search}&quot;</span>
                  </p>
                </Command.Empty>
              )}

              {!search && !loading && recentItems.length > 0 && (
                <Command.Group heading={<GroupHeading><RiTimeLine className="inline size-3 mr-1" />Recentes</GroupHeading>}>
                  {recentItems.map((item) => (
                    <CommandRow key={item.id} item={item} onSelect={() => handleSelect(item)} />
                  ))}
                </Command.Group>
              )}

              {!loading && (
                <Command.Group heading={<GroupHeading>Navegação</GroupHeading>}>
                  {navItems.map((item) => makeRow(item))}
                </Command.Group>
              )}

              {!loading && Array.from(domainGroups.entries()).map(([group, items]) => (
                <Command.Group key={group} heading={<GroupHeading>{group}</GroupHeading>}>
                  {items.map((item) => makeRow(item))}
                </Command.Group>
              ))}

              {!loading && (
                <Command.Group heading={<GroupHeading>Ações</GroupHeading>}>
                  {actionItems.map((item) => makeRow(item))}
                </Command.Group>
              )}

              {!loading && (
                <Command.Group heading={<GroupHeading>Configurações</GroupHeading>}>
                  {configItems.map((item) => makeRow(item))}
                </Command.Group>
              )}

              {!loading && (
                <Command.Group heading={<GroupHeading>Ajuda e atalhos</GroupHeading>}>
                  {helpItems.map((item) => makeRow(item))}
                </Command.Group>
              )}
            </Command.List>

            <div className="flex items-center gap-4 border-t border-gray-100 dark:border-gray-800 px-4 py-2">
              <span className="text-[11px] text-gray-400 dark:text-gray-600">
                <kbd className="font-mono">↑↓</kbd> navegar
              </span>
              <span className="text-[11px] text-gray-400 dark:text-gray-600">
                <kbd className="font-mono">↵</kbd> abrir
              </span>
              <span className="text-[11px] text-gray-400 dark:text-gray-600">
                <kbd className="font-mono">ESC</kbd> fechar
              </span>
              {search && resultCount > 1 && (
                <span className="ml-auto text-[11px] text-gray-400 dark:text-gray-600">
                  <kbd className="font-mono">⌘1–9</kbd> atalho rápido
                </span>
              )}
            </div>
          </Command>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
