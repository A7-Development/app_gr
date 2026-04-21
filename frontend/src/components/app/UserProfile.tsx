"use client"

import { Button } from "@/components/tremor/Button"
import { cx, focusRing } from "@/lib/utils"
import { RiExpandUpDownLine } from "@remixicon/react"

import { DropdownUserProfile } from "@/components/app/DropdownUserProfile"

export function UserProfile() {
  return (
    <DropdownUserProfile>
      <Button
        aria-label="Configuracoes do usuario"
        variant="ghost"
        className={cx(
          "group flex w-full items-center justify-between rounded px-1 py-2 text-sm font-medium text-gray-900 hover:bg-gray-200/50 data-[state=open]:bg-gray-200/50 hover:dark:bg-gray-800/50 data-[state=open]:dark:bg-gray-900",
          focusRing,
        )}
      >
        <span className="flex items-center gap-3">
          <span
            className="flex size-8 shrink-0 items-center justify-center rounded-full border border-gray-300 bg-white text-xs text-gray-700 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-300"
            aria-hidden="true"
          >
            RP
          </span>
          <span>Ricardo Pimenta</span>
        </span>
        <RiExpandUpDownLine
          className="size-4 shrink-0 text-gray-500 group-hover:text-gray-700 group-hover:dark:text-gray-400"
          aria-hidden="true"
        />
      </Button>
    </DropdownUserProfile>
  )
}
