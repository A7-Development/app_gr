// src/design-system/components/Sidebar/UserProfileDropdown.tsx
// User dropdown menu — opens above the avatar trigger.
// Items: email · Theme (Light/Dark/System) · Configuracoes · Atalhos · Documentacao · Sair
//
// Built on @radix-ui/react-dropdown-menu directly (no Tremor DropdownMenu primitive yet —
// the Tremor wrapper does not expose RadioGroup/RadioItem with custom indicators).

"use client"

import * as React from "react"
import * as DropdownMenu from "@radix-ui/react-dropdown-menu"
import * as AvatarPrimitive from "@radix-ui/react-avatar"
import { useTheme } from "next-themes"
import {
  RiSunLine,
  RiMoonLine,
  RiComputerLine,
  RiSettings3Line,
  RiKeyboardLine,
  RiBookOpenLine,
  RiLogoutBoxRLine,
  RiArrowUpDownLine,
  RiCheckLine,
} from "@remixicon/react"
import { cx, focusRing } from "@/lib/utils"

export type UserCommand = "settings" | "shortcuts" | "docs" | "signout"

export interface UserProfileDropdownProps {
  user: {
    name: string
    email?: string
    imageUrl?: string
  }
  onCommand?: (cmd: UserCommand) => void
  className?: string
}

function Initials({ name }: { name: string }) {
  return (
    <>
      {name
        .split(" ")
        .slice(0, 2)
        .map((w) => w[0])
        .join("")
        .toUpperCase()}
    </>
  )
}

function UserAvatar({ name, imageUrl }: { name: string; imageUrl?: string }) {
  return (
    <AvatarPrimitive.Root className="relative flex size-7 shrink-0 overflow-hidden rounded-full ring-1 ring-gray-200 dark:ring-gray-800">
      {imageUrl && (
        <AvatarPrimitive.Image
          src={imageUrl}
          alt={name}
          className="aspect-square size-full object-cover"
        />
      )}
      <AvatarPrimitive.Fallback className="flex size-full items-center justify-center bg-white text-[11px] font-semibold text-gray-700 dark:bg-gray-900 dark:text-gray-300">
        <Initials name={name} />
      </AvatarPrimitive.Fallback>
    </AvatarPrimitive.Root>
  )
}

const menuContentCls = cx(
  "z-50 min-w-[14rem] overflow-hidden rounded-md border p-1 shadow-lg",
  "border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
  "animate-slide-up-and-fade",
)

const menuItemCls = cx(
  "flex w-full cursor-pointer items-center gap-2.5 rounded px-2 py-1.5",
  "text-[13px] text-gray-900 dark:text-gray-50",
  "outline-none focus:bg-gray-100 dark:focus:bg-gray-900",
  "data-[disabled]:cursor-not-allowed data-[disabled]:opacity-50",
)

const menuLabelCls = "px-2 py-1.5 text-[11px] font-medium text-gray-500 dark:text-gray-400"
const menuSepCls = "my-1 h-px bg-gray-200 dark:bg-gray-800"
const menuCaptionCls =
  "px-2 pb-0.5 pt-1.5 text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600"

export function UserProfileDropdown({
  user,
  onCommand,
  className,
}: UserProfileDropdownProps) {
  const [mounted, setMounted] = React.useState(false)
  const { theme, setTheme } = useTheme()
  React.useEffect(() => setMounted(true), [])

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          aria-label="Menu do usuario"
          className={cx(
            "group flex w-full items-center gap-2.5 rounded-md px-2 py-1.5",
            "text-left",
            "hover:bg-gray-200/50 dark:hover:bg-gray-900",
            "data-[state=open]:bg-gray-200/50 dark:data-[state=open]:bg-gray-900",
            "transition-colors duration-100",
            focusRing,
            className,
          )}
        >
          <UserAvatar name={user.name} imageUrl={user.imageUrl} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13px] font-medium text-gray-900 dark:text-gray-50">
              {user.name}
            </span>
            {user.email && (
              <span className="block truncate text-[11px] text-gray-500 dark:text-gray-400">
                {user.email}
              </span>
            )}
          </span>
          <RiArrowUpDownLine
            className="size-3.5 shrink-0 text-gray-400 group-hover:text-gray-600 dark:group-hover:text-gray-300"
            aria-hidden="true"
          />
        </button>
      </DropdownMenu.Trigger>

      <DropdownMenu.Portal>
        <DropdownMenu.Content
          side="top"
          sideOffset={8}
          align="start"
          className={menuContentCls}
        >
          {user.email && (
            <DropdownMenu.Label className={menuLabelCls}>{user.email}</DropdownMenu.Label>
          )}
          <DropdownMenu.Separator className={menuSepCls} />

          {mounted && (
            <>
              <DropdownMenu.Label className={menuCaptionCls}>Tema</DropdownMenu.Label>
              <DropdownMenu.RadioGroup value={theme} onValueChange={setTheme}>
                <DropdownMenu.RadioItem value="light" className={menuItemCls}>
                  <RiSunLine className="size-3.5 shrink-0 text-gray-500" aria-hidden="true" />
                  <span className="flex-1">Claro</span>
                  <DropdownMenu.ItemIndicator>
                    <RiCheckLine className="size-3.5 text-blue-500" aria-hidden="true" />
                  </DropdownMenu.ItemIndicator>
                </DropdownMenu.RadioItem>
                <DropdownMenu.RadioItem value="dark" className={menuItemCls}>
                  <RiMoonLine className="size-3.5 shrink-0 text-gray-500" aria-hidden="true" />
                  <span className="flex-1">Escuro</span>
                  <DropdownMenu.ItemIndicator>
                    <RiCheckLine className="size-3.5 text-blue-500" aria-hidden="true" />
                  </DropdownMenu.ItemIndicator>
                </DropdownMenu.RadioItem>
                <DropdownMenu.RadioItem value="system" className={menuItemCls}>
                  <RiComputerLine className="size-3.5 shrink-0 text-gray-500" aria-hidden="true" />
                  <span className="flex-1">Sistema</span>
                  <DropdownMenu.ItemIndicator>
                    <RiCheckLine className="size-3.5 text-blue-500" aria-hidden="true" />
                  </DropdownMenu.ItemIndicator>
                </DropdownMenu.RadioItem>
              </DropdownMenu.RadioGroup>
              <DropdownMenu.Separator className={menuSepCls} />
            </>
          )}

          <DropdownMenu.Item className={menuItemCls} onSelect={() => onCommand?.("settings")}>
            <RiSettings3Line className="size-3.5 shrink-0 text-gray-500" aria-hidden="true" />
            <span className="flex-1">Configuracoes</span>
          </DropdownMenu.Item>
          <DropdownMenu.Item className={menuItemCls} onSelect={() => onCommand?.("shortcuts")}>
            <RiKeyboardLine className="size-3.5 shrink-0 text-gray-500" aria-hidden="true" />
            <span className="flex-1">Atalhos de teclado</span>
            <kbd className="rounded border border-gray-200 bg-gray-50 px-1 text-[10px] text-gray-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">⌘K</kbd>
          </DropdownMenu.Item>
          <DropdownMenu.Item className={menuItemCls} onSelect={() => onCommand?.("docs")}>
            <RiBookOpenLine className="size-3.5 shrink-0 text-gray-500" aria-hidden="true" />
            <span className="flex-1">Documentacao</span>
          </DropdownMenu.Item>

          <DropdownMenu.Separator className={menuSepCls} />

          <DropdownMenu.Item
            className={cx(menuItemCls, "text-red-600 dark:text-red-500")}
            onSelect={() => onCommand?.("signout")}
          >
            <RiLogoutBoxRLine className="size-3.5 shrink-0" aria-hidden="true" />
            <span className="flex-1">Sair</span>
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}
