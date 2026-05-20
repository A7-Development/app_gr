// src/app/preview/operacoes4-charts/page.tsx
//
// Preview/QA dos 5 components locais da pagina /bi/operacoes4 (PR2).
// Fora do (app) auth shell — acessivel via URL direta em dev.
//
// Smoke visual de cada chart + escolhas de cor/typography/layout. Quando
// PR3 amarrar tudo na pagina real, este preview vira referencia historica
// (pode ser apagado quando o produto estabilizar).

"use client"

import * as React from "react"

import { Card } from "@/components/tremor/Card"
import { cardTokens } from "@/design-system/tokens/card"

import { HistogramWithParity } from "@/app/(app)/bi/operacoes4/_components/charts/HistogramWithParity"
import { MovementCard } from "@/app/(app)/bi/operacoes4/_components/charts/MovementCard"
import { ProjectionFan } from "@/app/(app)/bi/operacoes4/_components/charts/ProjectionFan"
import { ReceitaCompositionBar } from "@/app/(app)/bi/operacoes4/_components/charts/ReceitaCompositionBar"
import { YieldChart } from "@/app/(app)/bi/operacoes4/_components/charts/YieldChart"
import {
  mockComposicao,
  mockHistPrazos,
  mockHistTaxas,
  mockMovers,
  mockNovos,
  mockProjectionCenarios,
  mockProjectionDuCorrente,
  mockProjectionDuLabels,
  mockProjectionRealizado,
  mockSumidos,
  mockYieldDu,
} from "@/app/(app)/bi/operacoes4/_components/charts/_mock"

export default function Operacoes4ChartsPreviewPage() {
  return (
    <div className="flex flex-col gap-8 px-12 py-6 pb-20">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-50">
          /bi/operacoes4 · charts preview (PR2)
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-500">
          5 components locais — dados ficticios. Use para validar
          cor/tipografia/layout antes do PR3 amarrar na pagina real.
        </p>
      </div>

      {/* 1. ReceitaCompositionBar */}
      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
          1. ReceitaCompositionBar — composicao MTD (4 buckets)
        </h2>
        <Card className={cardTokens.body}>
          <ReceitaCompositionBar buckets={mockComposicao} />
        </Card>
      </section>

      {/* 2. YieldChart */}
      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
          2. YieldChart — yield efetivo por DU + paridade
        </h2>
        <Card className={cardTokens.body}>
          <YieldChart data={mockYieldDu} embedded={false} />
        </Card>
      </section>

      {/* 3. HistogramWithParity (taxas) */}
      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
          3. HistogramWithParity — distribuicao de taxas (% a.m.)
        </h2>
        <Card className={cardTokens.body}>
          <HistogramWithParity
            data={mockHistTaxas}
            xAxisLabel="Taxa (% a.m.)"
            valueSuffix=" M"
            embedded={false}
          />
        </Card>
      </section>

      {/* 4. HistogramWithParity (prazos) */}
      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
          4. HistogramWithParity — distribuicao de prazos (dias)
        </h2>
        <Card className={cardTokens.body}>
          <HistogramWithParity
            data={mockHistPrazos}
            xAxisLabel="Prazo (dias)"
            valueSuffix=" M"
            embedded={false}
          />
        </Card>
      </section>

      {/* 5. ProjectionFan */}
      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
          5. ProjectionFan — VOP acumulado + 3 cenarios fim de mes
        </h2>
        <Card className={cardTokens.body}>
          <ProjectionFan
            realizado={mockProjectionRealizado}
            duLabels={mockProjectionDuLabels}
            duCorrente={mockProjectionDuCorrente}
            scenarios={mockProjectionCenarios}
            valueUnit=" M"
            embedded={false}
          />
        </Card>
      </section>

      {/* 6. MovementCards (3 lado a lado) */}
      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
          6. MovementCards — Novos / Sumidos / Top Movers (L5 lateral)
        </h2>
        <div className="grid grid-cols-3 gap-3">
          <MovementCard
            eyebrow="NOVOS NO MÊS"
            count={mockNovos.count}
            items={mockNovos.items}
            caption="+5 cedentes não exibidos"
          />
          <MovementCard
            eyebrow="SUMIDOS"
            count={mockSumidos.count}
            items={mockSumidos.items}
          />
          <MovementCard
            eyebrow="TOP MOVERS"
            count={mockMovers.count}
            items={mockMovers.items}
          />
        </div>
      </section>

      {/* 7. Loading state (smoke) */}
      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
          7. Loading state (smoke) — YieldChart
        </h2>
        <Card className={cardTokens.body}>
          <YieldChart data={[]} loading embedded={false} />
        </Card>
      </section>

      {/* 8. Error state (smoke) */}
      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
          8. Error state (smoke) — HistogramWithParity
        </h2>
        <Card className={cardTokens.body}>
          <HistogramWithParity
            data={[]}
            error="Falha ao carregar histograma"
            onRetry={() => alert("retry")}
            embedded={false}
          />
        </Card>
      </section>
    </div>
  )
}
