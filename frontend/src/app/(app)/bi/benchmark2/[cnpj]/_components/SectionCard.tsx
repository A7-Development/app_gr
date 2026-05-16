"use client"

import * as React from "react"
import { RiInformationLine } from "@remixicon/react"

import { Card } from "@/components/tremor/Card"
import { cx } from "@/lib/utils"

// Wrapper minimo pra envolver as secoes da Lamina. Equivalente local ao
// ChartCard que vive em /bi/benchmark/_components — duplicado aqui pra
// permitir a substituicao na Fase 4 sem dependencia cruzada.

export function SectionCard({
  title,
  info,
  className,
  children,
}: {
  title: string
  info?: string
  className?: string
  children: React.ReactNode
}) {
  return (
    <Card className={cx("flex flex-col gap-3 p-4", className)}>
      <div className="flex items-start gap-2">
        <h3 className="text-sm font-medium leading-tight text-gray-900 dark:text-gray-50">
          {title}
        </h3>
        {info ? (
          <span
            className="mt-0.5 text-gray-400 dark:text-gray-500"
            title={info}
          >
            <RiInformationLine className="size-4" aria-hidden />
          </span>
        ) : null}
      </div>
      {children}
    </Card>
  )
}
