// src/app/(app)/bi/operacoes4/_components/DecomposicaoAvancada4.tsx
//
// L8 da pagina /bi/operacoes4 — versao reduzida da DecomposicaoAvancada de
// operacoes3. 4 cards (omitindo Mix de produtos, que agora vive em L4
// dedicada) + VOP que continua em L2 hero. Cards:
//
//   - Receita waterfall (VarianceBridgeCard)
//   - Taxa media (PvmBridgeCard)
//   - Prazo medio (PvmBridgeCard)
//   - Concentracao (ConcentracaoDeltaCard)
//
// Mantemos o <details>/<summary> com mesma UX colapsavel.

"use client"

import * as React from "react"
import { RiArrowDownSLine } from "@remixicon/react"

import {
  ConcentracaoDeltaCard,
  PvmBridgeCard,
  VarianceBridgeCard,
} from "@/design-system/components"
import { cardTokens } from "@/design-system/tokens/card"
import type {
  Operacoes2ConcentracaoDeltaData,
  Operacoes2PvmBridgeData,
  Operacoes2VarianceBridgeData,
} from "@/lib/api-client"
import { cx } from "@/lib/utils"

export function DecomposicaoAvancada4({
  receita,
  taxa,
  prazo,
  concentracao,
}: {
  receita: Operacoes2VarianceBridgeData
  taxa: Operacoes2PvmBridgeData
  prazo: Operacoes2PvmBridgeData
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
            Receita · Taxa · Prazo · Concentração — VOP fica em L2 e Mix em L4
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
          "grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-2",
        )}
      >
        <VarianceBridgeCard data={receita} title="Receita contratada" />
        <PvmBridgeCard data={taxa} title="Taxa média" />
        <PvmBridgeCard
          data={prazo}
          title="Prazo médio"
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
        <ConcentracaoDeltaCard data={concentracao} />
      </div>
    </details>
  )
}
