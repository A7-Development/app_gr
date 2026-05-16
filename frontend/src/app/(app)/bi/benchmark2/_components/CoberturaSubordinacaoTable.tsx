"use client"

import {
  CompactSeriesTable,
  type CompactSeriesRow,
} from "@/design-system/components/CompactSeriesTable"
import type { FichaFundo } from "@/lib/api-client"

import { SectionCard } from "./SectionCard"

// CoberturaSubordinacaoTable — reproduz a tabela "Indices de Cobertura da
// Subordinacao Disponivel para as Cotas Seniores (Vezes)" da Lamina Austin.
//
// CVM publica concentracao SO de cedentes (sem sacados) e SO top-9 (sem
// top-10/20). O backend deriva PL_Sub via `tab_x_2.qt_cota * vl_cota` e
// cobertura = PL_Sub / (% cedente x PL_total).
//
// Quando o admin nao reporta `qt_cota` (caso Puma), todas as competencias
// vem com `dado_indisponivel=true` -> renderiza EmptyState.

export function CoberturaSubordinacaoTable({ ficha }: { ficha: FichaFundo }) {
  const serie = ficha.cobertura_subordinacao_serie ?? []
  const allIndisp =
    serie.length > 0 && serie.every((s) => s.dado_indisponivel)

  if (serie.length === 0 || allIndisp) {
    return (
      <SectionCard title="Indices de Cobertura da Subordinacao (vezes)">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Dado nao reportado pelo administrador a CVM
          (<code className="font-mono text-[11px]">tab_x_2.qt_cota</code>{" "}
          NULL — sem como calcular PL Subordinada).
        </p>
      </SectionCard>
    )
  }

  const periodos = serie.map((s) => s.competencia)

  const valuesByComp = (
    pick: (
      s: FichaFundo["cobertura_subordinacao_serie"][number],
    ) => number | null,
  ): Record<string, number | null> => {
    const out: Record<string, number | null> = {}
    for (const s of serie) out[s.competencia] = pick(s)
    return out
  }

  const rows: CompactSeriesRow[] = [
    {
      label: "PL Sub / (maior Cedente)",
      format: "num",
      values: valuesByComp((s) => s.cobertura_maior_cedente),
    },
    {
      label: "PL Sub / (3 maiores Cedentes)",
      format: "num",
      values: valuesByComp((s) => s.cobertura_top3_cedentes),
    },
    {
      label: "PL Sub / (5 maiores Cedentes)",
      format: "num",
      values: valuesByComp((s) => s.cobertura_top5_cedentes),
    },
    {
      label: "PL Sub / (9 maiores Cedentes)",
      format: "num",
      emphasis: "subtotal",
      values: valuesByComp((s) => s.cobertura_top9_cedentes),
    },
  ]

  return (
    <SectionCard
      title="Indices de Cobertura da Subordinacao (vezes)"
      info="Cobertura = PL Subordinada / (% maiores cedentes x PL total). Fonte: CVM tab_x_2 (PL Sub derivado de qt*vl) + tab_i2a12 (concentracao). CVM publica so cedentes (sem sacados) e so top-9 (limite legal)."
    >
      <CompactSeriesTable
        label="Linha"
        periods={periodos}
        rows={rows}
        bordered={false}
        widthMode="adaptive"
      />
    </SectionCard>
  )
}
