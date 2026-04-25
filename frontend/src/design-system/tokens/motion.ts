// src/design-system/tokens/motion.ts
// Animation tokens + reduced-motion utilities.

import { tokens } from "./index"

export const duration = tokens.motion.duration
export const easing   = tokens.motion.easing

/**
 * Returns CSS transition string respecting prefers-reduced-motion.
 * Usage: `style={{ transition: transition('background-color', 'base') }}`
 */
export function transition(
  property: string,
  speed: keyof typeof duration = "base",
  ease: keyof typeof easing = "standard",
): string {
  return `${property} ${duration[speed]}ms ${easing[ease]}`
}

/**
 * Tailwind animation class map for common transitions.
 */
export const motionClasses = {
  sheetIn:   "animate-drawer-slide-left-and-fade",
  sheetOut:  "animate-drawer-slide-right-and-fade",
  tooltipIn: "animate-slide-down-and-fade",
  dialogIn:  "animate-dialog-content-show",
  fadeIn:    "animate-hide",
} as const

/**
 * ECharts-specific timing — animationDurationUpdate must be 0.
 */
export const echartsMotion = {
  animationDuration: duration.slower,
  animationDurationUpdate: duration.instant,
  animationEasing: "cubicOut",
} as const
