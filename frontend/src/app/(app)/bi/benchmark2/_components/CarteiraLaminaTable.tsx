"use client"

import {
  CompactSeriesTable,
  type CompactSeriesRow,
} from "@/design-system/components/CompactSeriesTable"
import type { FichaFundo, FundoCarteiraPonto } from "@/lib/api-client"

import { SectionCard } from "./SectionCard"

// CarteiraLaminaTable — reproduz a tabela "Posicao da Carteira" da Lamina
// Austin (R$ mil OU % do PL conforme `format`).
//
// Decomposicao CVM completa em 4 linhas dentro de "DIREITOS CREDITORIOS":
//   - A vencer (com risco)    = tab_i2a1
//   - Vencidos (com risco)    = tab_i2a2 + i2a3 + i2a5
//   - A vencer (sem risco)    = tab_i2b1
//   - Vencidos (sem risco)    = tab_i2b2 + i2b3 + i2b5
//   - Total Dir. Creditorios  = soma das 4
//
// Cobre fundos que classificam a maior parte como "sem risco" (REALINVEST,
// Puma). A separacao "com/sem risco" reflete a estrutura contabil CVM: DC
// com risco = cedente mantem coobrigacao; DC sem risco = cessao sem
// coobrigacao.

type Props = {
  ficha: FichaFundo
  format: "brl" | "pct"
}

function valuesByComp(
  serie: FundoCarteiraPonto[],
  pick: (p: FundoCarteiraPonto) => number | null,
): Record<string, number | null> {
  const out: Record<string, number | null> = {}
  for (const p of serie) out[p.competencia] = pick(p)
  return out
}

function makeGetter(
  format: "brl" | "pct",
  plByComp: Map<string, number>,
): (val: number, competencia: string) => number | null {
  // BRL em milhares (Austin publica em R$ mil). Pct dividido pelo PL mensal.
  return (val, comp) => {
    if (format === "brl") return val / 1000
    const pl = plByComp.get(comp) ?? 0
    if (pl <= 0) return null
    return (val / pl) * 100
  }
}

export function CarteiraLaminaTable({ ficha, format }: Props) {
  const serie = ficha.carteira_serie
  if (serie.length === 0) {
    return (
      <SectionCard
        title={
          format === "brl"
            ? "Posicao da Carteira (R$ mil)"
            : "Posicao da Carteira (% do PL)"
        }
      >
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Nao ha composicao do ativo publicada pela CVM para o periodo.
        </p>
      </SectionCard>
    )
  }

  const plByComp = new Map(ficha.pl_serie.map((p) => [p.competencia, p.pl]))
  const periodos = serie.map((p) => p.competencia)
  const formatRow = format === "brl" ? "brlFull" : "pct"
  const get = makeGetter(format, plByComp)

  // Helper pra somar 4 sub-categorias do DC com tolerancia a null.
  const totalDc = (p: FundoCarteiraPonto): number => {
    return (
      (p.dc_a_vencer_com_risco ?? 0) +
      (p.dc_vencido_com_risco ?? 0) +
      (p.dc_a_vencer_sem_risco ?? 0) +
      (p.dc_vencido_sem_risco ?? 0)
    )
  }

  const rows: CompactSeriesRow[] = [
    { label: "DIREITOS CREDITORIOS", emphasis: "header", values: {} },
    {
      label: "A vencer (com risco)",
      format: formatRow,
      indent: 1,
      values: valuesByComp(serie, (p) =>
        p.dc_a_vencer_com_risco == null
          ? null
          : get(p.dc_a_vencer_com_risco, p.competencia),
      ),
    },
    {
      label: "Vencidos (com risco)",
      format: formatRow,
      indent: 1,
      values: valuesByComp(serie, (p) =>
        p.dc_vencido_com_risco == null
          ? null
          : get(p.dc_vencido_com_risco, p.competencia),
      ),
    },
    {
      label: "A vencer (sem risco)",
      format: formatRow,
      indent: 1,
      values: valuesByComp(serie, (p) =>
        p.dc_a_vencer_sem_risco == null
          ? null
          : get(p.dc_a_vencer_sem_risco, p.competencia),
      ),
    },
    {
      label: "Vencidos (sem risco)",
      format: formatRow,
      indent: 1,
      values: valuesByComp(serie, (p) =>
        p.dc_vencido_sem_risco == null
          ? null
          : get(p.dc_vencido_sem_risco, p.competencia),
      ),
    },
    {
      label: "Total Dir. Creditorios",
      format: formatRow,
      emphasis: "subtotal",
      values: valuesByComp(serie, (p) => {
        const v = totalDc(p)
        if (v <= 0) return null
        return get(v, p.competencia)
      }),
    },
    { separator: true },
    {
      label: "Titulos Publicos",
      format: formatRow,
      values: valuesByComp(serie, (p) => get(p.tit_pub, p.competencia)),
    },
    {
      label: "Fundos Renda Fixa",
      format: formatRow,
      values: valuesByComp(serie, (p) =>
        get(p.cotas_fidc + p.cotas_fidc_np + p.outros_rf, p.competencia),
      ),
    },
    {
      label: "Saldo Tesouraria",
      format: formatRow,
      values: valuesByComp(serie, (p) => get(p.disp, p.competencia)),
    },
    { separator: true },
    {
      label: "Total Geral da Carteira",
      format: formatRow,
      emphasis: "total",
      values: valuesByComp(serie, (p) => {
        const dc = totalDc(p)
        const rf = p.cotas_fidc + p.cotas_fidc_np + p.outros_rf
        const total = dc + p.tit_pub + rf + p.disp
        if (total <= 0) return null
        return get(total, p.competencia)
      }),
    },
    {
      label: "PDD",
      format: formatRow,
      emphasis: "emphasis",
      // PDD negativo: vermelho automatico pelo CompactSeriesTable.
      values: valuesByComp(serie, (p) =>
        get(-Math.abs(p.pdd_aprox), p.competencia),
      ),
    },
    {
      label: "Imoveis",
      format: formatRow,
      values: valuesByComp(serie, (p) => get(p.outro_ativo, p.competencia)),
    },
  ]

  return (
    <SectionCard
      title={
        format === "brl"
          ? "Posicao da Carteira (R$ mil)"
          : "Posicao da Carteira (% do PL)"
      }
      info="Fonte: CVM Informe Mensal FIDC. DC decomposto em 4 linhas: com risco (i2a) vs sem risco (i2b), cada qual em a-vencer e vencidos. Imoveis = tab_i4 (Outros Ativos)."
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
