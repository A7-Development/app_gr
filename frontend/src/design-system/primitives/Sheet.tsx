// src/design-system/primitives/Sheet.tsx
// Radix Dialog configured as a right-side Sheet/Drawer.
// This is the canonical drill-down container for the FIDC platform.
// Rule: drill-down NEVER opens full-screen modal. Always Sheet lateral.

"use client"

import * as React from "react"
import * as DialogPrimitive from "@radix-ui/react-dialog"
import { RiCloseLine } from "@remixicon/react"
import { cx, focusRing } from "@/lib/utils"

const Sheet        = DialogPrimitive.Root
const SheetClose   = DialogPrimitive.Close
const SheetPortal  = DialogPrimitive.Portal
const SheetTrigger = DialogPrimitive.Trigger

const SheetOverlay = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Overlay>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Overlay>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Overlay
    ref={ref}
    className={cx(
      "fixed inset-0 z-40 bg-black/35 backdrop-blur-[2px]",
      "animate-dialog-overlay-show",
      className,
    )}
    {...props}
  />
))
SheetOverlay.displayName = "SheetOverlay"

export type SheetSize = "sm" | "md" | "lg"

const sheetWidths: Record<SheetSize, string> = {
  sm: "w-[400px]",
  md: "w-[560px]",
  lg: "w-[720px]",
}

interface SheetContentProps
  extends React.ComponentPropsWithoutRef<typeof DialogPrimitive.Content> {
  size?: SheetSize
  /** When false, hides the default close button (provide your own). */
  showClose?: boolean
}

const SheetContent = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Content>,
  SheetContentProps
>(({ className, size = "md", showClose = true, children, ...props }, ref) => (
  <SheetPortal>
    <SheetOverlay />
    <DialogPrimitive.Content
      ref={ref}
      className={cx(
        "fixed inset-y-0 right-0 z-50",
        "max-w-full",
        sheetWidths[size],
        "bg-white dark:bg-[#090E1A]",
        "border-l border-gray-200 dark:border-gray-900",
        "shadow-xl dark:shadow-black/40",
        "flex flex-col overflow-hidden",
        "animate-drawer-slide-left-and-fade",
        "data-[state=closed]:animate-drawer-slide-right-and-fade",
        className,
      )}
      {...props}
    >
      {showClose && (
        <DialogPrimitive.Close
          className={cx(
            "absolute left-4 top-4 z-10",
            "inline-flex size-7 items-center justify-center rounded",
            "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200",
            "hover:bg-gray-100 dark:hover:bg-gray-800",
            "transition-colors duration-100",
            focusRing,
          )}
          aria-label="Fechar"
        >
          <RiCloseLine className="size-4" aria-hidden="true" />
        </DialogPrimitive.Close>
      )}
      {children}
    </DialogPrimitive.Content>
  </SheetPortal>
))
SheetContent.displayName = "SheetContent"

function SheetHeader({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cx(
        "flex items-center gap-3 px-5 py-3.5",
        "border-b border-gray-200 dark:border-gray-800",
        "shrink-0",
        className,
      )}
      {...props}
    />
  )
}

function SheetHero({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cx(
        "px-6 py-5 border-b border-gray-200 dark:border-gray-800",
        "bg-gray-50 dark:bg-gray-900/50 shrink-0",
        className,
      )}
      {...props}
    />
  )
}

function SheetBody({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cx("flex-1 overflow-y-auto px-6 py-5", className)}
      {...props}
    />
  )
}

function SheetFooter({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cx(
        "flex items-center gap-2 px-5 py-3",
        "border-t border-gray-200 dark:border-gray-800",
        "bg-white dark:bg-[#090E1A] shrink-0",
        className,
      )}
      {...props}
    />
  )
}

const SheetTitle = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Title>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Title>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Title
    ref={ref}
    className={cx("text-sm font-semibold text-gray-900 dark:text-gray-50", className)}
    {...props}
  />
))
SheetTitle.displayName = "SheetTitle"

const SheetDescription = React.forwardRef<
  React.ElementRef<typeof DialogPrimitive.Description>,
  React.ComponentPropsWithoutRef<typeof DialogPrimitive.Description>
>(({ className, ...props }, ref) => (
  <DialogPrimitive.Description
    ref={ref}
    className={cx("text-sm text-gray-500 dark:text-gray-400", className)}
    {...props}
  />
))
SheetDescription.displayName = "SheetDescription"

export {
  Sheet,
  SheetBody,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetHero,
  SheetTitle,
  SheetTrigger,
}
