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
// Estrutura (labels Austin, 9 linhas):
//   DIREITOS CREDITORIOS   (header)
//     Direitos Creditorios    (a vencer  = tab_v_a_vl_dircred_prazo)
//     Creditos Vencidos       (inad      = tab_v_b_vl_dircred_inad)
//     Total Dir. Creditorios  (subtotal a+b)
//   ---
//     Titulos Publicos        (tab_i2d_vl_titpub_fed)
//     Fundos Renda Fixa       (cotas_fidc + cotas_fidc_np + outros_rf)
//     Saldo Tesouraria        (tab_i1_vl_disp)
//   ---
//   Total Geral da Carteira   (total = Total DC + tit_pub + fundos_rf + tesouraria)
//   PDD                       (emphasis, valor negativo -> vermelho automatico)
//   Imoveis                   (= I.4 outro_ativo — aproximacao CVM)
//
// Quando o fundo sub-reporta tab_v (caso Puma), uma nota inline alerta o
// usuario que os DC reportados estao abaixo do total do fundo.

type Props = {
  ficha: FichaFundo
  format: "brl" | "pct"
}

// Detecta sub-reporting: soma(a + b) << soma(dc_risco + dc_sem_risco).
function isSubReported(serie: FundoCarteiraPonto[]): boolean {
  if (serie.length === 0) return false
  const sumAB = serie.reduce(
    (s, p) => s + (p.dc_a_vencer ?? 0) + (p.dc_inadimplente ?? 0),
    0,
  )
  const sumRisco = serie.reduce(
    (s, p) => s + (p.dc_risco ?? 0) + (p.dc_sem_risco ?? 0),
    0,
  )
  return sumRisco > 0 && sumAB / sumRisco < 0.5
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
  const subReported = isSubReported(serie)

  const rows: CompactSeriesRow[] = [
    { label: "DIREITOS CREDITORIOS", emphasis: "header", values: {} },
    {
      label: "Direitos Creditorios",
      format: formatRow,
      indent: 1,
      values: valuesByComp(serie, (p) =>
        p.dc_a_vencer == null ? null : get(p.dc_a_vencer, p.competencia),
      ),
    },
    {
      label: "Creditos Vencidos",
      format: formatRow,
      indent: 1,
      values: valuesByComp(serie, (p) =>
        p.dc_inadimplente == null
          ? null
          : get(p.dc_inadimplente, p.competencia),
      ),
    },
    {
      label: "Total Dir. Creditorios",
      format: formatRow,
      emphasis: "subtotal",
      values: valuesByComp(serie, (p) => {
        const v = (p.dc_a_vencer ?? 0) + (p.dc_inadimplente ?? 0)
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
        const dc = (p.dc_a_vencer ?? 0) + (p.dc_inadimplente ?? 0)
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
      // PDD negativo: vermelho automatico pelo CompactSeriesTable
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
      info="Fonte: CVM Informe Mensal FIDC (tab_i, tab_v). Direitos Creditorios = tab_v_a (a vencer). Creditos Vencidos = tab_v_b (inadimplentes). Imoveis = tab_i4 (Outros Ativos — aproximacao CVM)."
    >
      <CompactSeriesTable
        label="Linha"
        periods={periodos}
        rows={rows}
        bordered={false}
        widthMode="adaptive"
      />
      {subReported ? (
        <p className="mt-1 text-[11px] italic text-amber-700 dark:text-amber-400">
          Os Direitos Creditorios reportados (tab_v) estao abaixo do total
          do fundo. O administrador classifica a maior parte como
          &ldquo;DC sem risco&rdquo; e nao detalha em a-vencer/inadimplente.
        </p>
      ) : null}
    </SectionCard>
  )
}
