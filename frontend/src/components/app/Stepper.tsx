import * as React from "react"
import { RiCheckLine } from "@remixicon/react"

import { cx } from "@/lib/utils"

//
// Tipos
//

export type Step = {
  id: string
  label: string
  description?: string
}

type StepperProps = {
  steps: Step[]
  currentIndex: number
  className?: string
}

//
// Stepper (horizontal)
//

export function Stepper({ steps, currentIndex, className }: StepperProps) {
  return (
    <nav aria-label="Etapas" className={cx("w-full", className)}>
      <ol className="flex w-full items-start">
        {steps.map((step, index) => {
          const isCompleted = index < currentIndex
          const isCurrent = index === currentIndex
          const isLast = index === steps.length - 1

          return (
            <li
              key={step.id}
              className={cx(
                "relative flex flex-1 flex-col items-center gap-2",
                !isLast && "pr-4",
              )}
            >
              <div className="flex w-full items-center">
                {/* Circulo do step */}
                <div
                  className={cx(
                    "relative z-10 flex size-8 shrink-0 items-center justify-center rounded-full border text-sm font-semibold transition-colors",
                    isCompleted &&
                      "border-gray-900 bg-gray-900 text-gray-50 dark:border-gray-50 dark:bg-gray-50 dark:text-gray-900",
                    isCurrent &&
                      "border-gray-900 bg-white text-gray-900 dark:border-gray-50 dark:bg-gray-950 dark:text-gray-50",
                    !isCompleted &&
                      !isCurrent &&
                      "border-dashed border-gray-300 bg-white text-gray-400 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-600",
                  )}
                  aria-current={isCurrent ? "step" : undefined}
                >
                  {isCompleted ? (
                    <RiCheckLine className="size-4" aria-hidden="true" />
                  ) : (
                    <span>{index + 1}</span>
                  )}
                </div>

                {/* Linha conectora ate o proximo step */}
                {!isLast && (
                  <div
                    className={cx(
                      "ml-2 h-px flex-1 transition-colors",
                      isCompleted
                        ? "bg-gray-900 dark:bg-gray-50"
                        : "bg-gray-200 dark:bg-gray-800",
                    )}
                    aria-hidden="true"
                  />
                )}
              </div>

              {/* Label + descricao */}
              <div className="flex flex-col items-start gap-0.5 self-start">
                <span
                  className={cx(
                    "text-sm",
                    isCurrent &&
                      "font-semibold text-gray-900 dark:text-gray-50",
                    isCompleted && "font-medium text-gray-900 dark:text-gray-50",
                    !isCompleted &&
                      !isCurrent &&
                      "text-gray-500 dark:text-gray-400",
                  )}
                >
                  {step.label}
                </span>
                {step.description && (
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    {step.description}
                  </span>
                )}
              </div>
            </li>
          )
        })}
      </ol>
    </nav>
  )
}
