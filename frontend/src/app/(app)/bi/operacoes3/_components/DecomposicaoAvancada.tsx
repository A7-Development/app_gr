// src/app/(app)/bi/operacoes3/_components/DecomposicaoAvancada.tsx
//
// L5 da pagina /bi/operacoes3 — secao colapsavel "Decomposicao avancada".
//
// Fechada por default. Quem quer entender o "porque" expande. Contem os 5
// cards de decomposicao remanescentes (VOP waterfall ficou no Hero L2, ja
// em destaque):
//
//   - Receita waterfall (VarianceBridgeCard)
//   - Taxa media (PvmBridgeCard)
//   - Prazo medio (PvmBridgeCard)
//   - Mix de produtos (MixDeltaBarCard)
//   - Concentracao (ConcentracaoDeltaCard)
//
// Usa `<details>`/`<summary>` HTML5 nativo (acessibilidade gratis) +
// styling Tremor. Sem componente novo no design-system — sufix simples.

"use client"

import * as React from "react"
import { RiArrowDownSLine } from "@remixicon/react"

import {
  ConcentracaoDeltaCard,
  MixDeltaBarCard,
  PvmBridgeCard,
  VarianceBridgeCard,
} from "@/design-system/components"
import { cardTokens } from "@/design-system/tokens/card"
import type {
  Operacoes2ConcentracaoDeltaData,
  Operacoes2DumbbellSeriesData,
  Operacoes2ProjectionBridgeData,
  Operacoes2PvmBridgeData,
  Operacoes2VarianceBridgeData,
} from "@/lib/api-client"
import { cx } from "@/lib/utils"

export function DecomposicaoAvancada({
  receita,
  taxa,
  prazo,
  mix,
  concentracao,
}: {
  receita: Operacoes2VarianceBridgeData
  receitaProjecao: Operacoes2ProjectionBridgeData | null
  taxa: Operacoes2PvmBridgeData
  prazo: Operacoes2PvmBridgeData
  mix: Operacoes2DumbbellSeriesData
  concentracao: Operacoes2ConcentracaoDeltaData
}) {
  return (
    <details className="group rounded border border-gray-200 bg-white dark:border-gray-900 dark:bg-[#090E1A]">
      <summary
        className={cx(
          cardTokens.header,
          "flex cursor-pointer items-center justify-between gap-2 list-none",
          "[&::-webkit-details-marker]:hidden",
        )}
      >
        <div className="flex flex-col">
          <h3 className={cardTokens.headerTitle}>Decomposição avançada</h3>
          <p className={cx(cardTokens.headerSubtitle, "mt-0.5")}>
            Receita · Taxa · Prazo · Mix · Concentração — drivers por dimensão
          </p>
        </div>
        <RiArrowDownSLine
          aria-hidden="true"
          className="size-5 shrink-0 text-gray-500 transition-transform group-open:rotate-180 dark:text-gray-400"
        />
      </summary>

      <div
        className={cx(
          cardTokens.body,
          "grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3",
        )}
      >
        <VarianceBridgeCard data={receita} title="Receita contratada" />
        <PvmBridgeCard data={taxa} title="Taxa média" />
        <PvmBridgeCard
          data={prazo}
          title="Prazo médio"
          // Override do good (alongar prazo nao e bom).
          headerKpi={{
            value: `${prazo.current_anchor_value.toFixed(1).replace(".", ",")} d`,
            delta: {
              value: prazo.delta,
              suffix: "d",
              good: prazo.delta < 0,
            },
            deltaSub: prazo.current_anchor_label,
          }}
        />
        <MixDeltaBarCard data={mix} title="Mix de produtos" />
        <ConcentracaoDeltaCard data={concentracao} />
      </div>
    </details>
  )
}
