"use client"

// Matriz do Comparador: linhas = 17 indicadores (agrupados por dimensao),
// colunas = ate 3 fundos + mediana do universo. Cada celula traz o VALOR +
// percentil no universo (p0-100, orientado: 100 = melhor). ● marca o melhor
// da linha; ⚠ marca red flag de leitura combinada.
//
// DataTable canonica (density compact) com linhas de secao via tipo proprio —
// mesma mecanica das tabelas hierarquicas (§6).

import * as React from "react"
import { RiAlertFill, RiInformationLine } from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"
import type { ComparadorIndicadoresFundo } from "@/lib/api-client"

import {
  GRUPOS,
  INDICADORES,
  formatIndicador,
  rankOrientado,
  type IndicadorDef,
} from "./indicadores"

type Linha =
  | { tipo: "secao"; label: string }
  | { tipo: "indicador"; def: IndicadorDef }

function montarLinhas(): Linha[] {
  const linhas: Linha[] = []
  for (const grupo of GRUPOS) {
    linhas.push({ tipo: "secao", label: grupo })
    for (const def of INDICADORES.filter((i) => i.grupo === grupo)) {
      linhas.push({ tipo: "indicador", def })
    }
  }
  return linhas
}

/** Red flags de leitura combinada (retorna tooltip ou null). */
function redFlag(
  def: IndicadorDef,
  fundo: ComparadorIndicadoresFundo,
): string | null {
  if (def.key === "recompra_dc_pct") {
    const rec = fundo.recompra_dc_pct_rank
    const inad = fundo.inad_total_pct_rank
    if (rec !== null && inad !== null && rec >= 80 && inad <= 30) {
      return "Recompra alta com inadimplência baixa — cedente pode estar recomprando o atraso antes de aparecer (red flag clássico de agência)"
    }
  }
  if (def.key === "cobertura_pdd_pct") {
    const v = fundo.cobertura_pdd_pct
    if (v !== null && v < 100) {
      return "Provisão cobre menos de 100% dos inadimplentes"
    }
  }
  return null
}

function CelulaFundo({
  def,
  fundo,
  direcao,
  melhor,
}: {
  def: IndicadorDef
  fundo: ComparadorIndicadoresFundo
  direcao: Record<string, boolean>
  melhor: boolean
}) {
  const valor = fundo[def.key]
  const rank = fundo[`${def.key}_rank` as keyof ComparadorIndicadoresFundo]
  const orientado = rankOrientado(
    typeof rank === "number" ? rank : null,
    direcao[def.key],
  )
  const flag = redFlag(def, fundo)
  return (
    <div className="flex items-baseline justify-end gap-1.5">
      {flag && (
        <span title={flag}>
          <RiAlertFill
            className="size-3 self-center text-amber-500"
            aria-hidden="true"
          />
        </span>
      )}
      {melhor && (
        <span
          className="size-1.5 self-center rounded-full bg-blue-500"
          title="Melhor da linha"
          aria-hidden="true"
        />
      )}
      <span
        className={cx(
          tableTokens.cellNumber,
          melhor && "font-semibold text-gray-900 dark:text-gray-50",
        )}
      >
        {formatIndicador(typeof valor === "number" ? valor : null, def.fmt)}
      </span>
      {orientado !== null && (
        <span
          className={cx("w-8 text-left tabular-nums", tableTokens.cellMuted)}
          title={`Percentil ${Math.round(orientado)} de 100 no universo (orientado: 100 = melhor)`}
        >
          p{Math.round(orientado)}
        </span>
      )}
    </div>
  )
}

export function MatrizIndicadores({
  fundos,
  mediana,
  direcao,
}: {
  fundos: ComparadorIndicadoresFundo[]
  mediana: Record<string, number | null>
  direcao: Record<string, boolean>
}) {
  const linhas = React.useMemo(montarLinhas, [])

  // Melhor da linha (na direcao do indicador) — so quando ha 2+ fundos.
  const melhorPorIndicador = React.useMemo(() => {
    const out = new Map<string, string>()
    if (fundos.length < 2) return out
    for (const def of INDICADORES) {
      const candidatos = fundos
        .map((f) => ({ cnpj: f.cnpj, v: f[def.key] }))
        .filter((c): c is { cnpj: string; v: number } => typeof c.v === "number")
      if (candidatos.length < 2) continue
      const maior = direcao[def.key] !== false
      candidatos.sort((a, b) => (maior ? b.v - a.v : a.v - b.v))
      out.set(def.key, candidatos[0].cnpj)
    }
    return out
  }, [fundos, direcao])

  const columns = React.useMemo(() => {
    const col = createColumnHelper<Linha>()
    const defs: ColumnDef<Linha, unknown>[] = [
      col.display({
        id: "indicador",
        header: "Indicador",
        size: 240,
        cell: (info) => {
          const row = info.row.original
          if (row.tipo === "secao") {
            return (
              <span className={tableTokens.header}>{row.label}</span>
            )
          }
          return (
            <span className="flex items-center gap-1.5">
              <span className={tableTokens.cellText}>{row.def.label}</span>
              <span title={row.def.info}>
                <RiInformationLine
                  className="size-3 text-gray-300 dark:text-gray-600"
                  aria-hidden="true"
                />
              </span>
            </span>
          )
        },
      }) as ColumnDef<Linha, unknown>,
      ...fundos.map(
        (fundo, idx) =>
          col.display({
            id: `fundo_${idx}`,
            header: fundo.denom_social ?? fundo.cnpj,
            size: 170,
            meta: { align: "right" },
            cell: (info) => {
              const row = info.row.original
              if (row.tipo === "secao") return null
              return (
                <CelulaFundo
                  def={row.def}
                  fundo={fundo}
                  direcao={direcao}
                  melhor={melhorPorIndicador.get(row.def.key) === fundo.cnpj}
                />
              )
            },
          }) as ColumnDef<Linha, unknown>,
      ),
      col.display({
        id: "mediana",
        header: "Mediana do universo",
        size: 140,
        meta: { align: "right" },
        cell: (info) => {
          const row = info.row.original
          if (row.tipo === "secao") return null
          return (
            <div className={cx("text-right", tableTokens.cellNumberSecondary)}>
              {formatIndicador(mediana[row.def.key] ?? null, row.def.fmt)}
            </div>
          )
        },
      }) as ColumnDef<Linha, unknown>,
    ]
    return defs
  }, [fundos, mediana, direcao, melhorPorIndicador])

  return (
    <Card className={tableTokens.cardWrapper}>
      <DataTable
        data={linhas}
        columns={columns}
        density="compact"
        showColumnManager={false}
        showDensityToggle={false}
        showExport={false}
        virtualize={false}
        rowClassName={(row) =>
          row.tipo === "secao"
            ? "bg-gray-50 dark:bg-gray-900/60 border-t-gray-200 dark:border-t-gray-800"
            : ""
        }
      />
    </Card>
  )
}
