"use client"

// Preview page — fora do (app) auth shell.
import {
  CompactSeriesTable,
  type CompactSeriesRow,
} from "@/components/app/CompactSeriesTable"

// Dados ficticios estilo Austin (Puma FIDC, % do PL, 12 meses)
const MONTHS_12 = [
  "2025-01-01",
  "2025-02-01",
  "2025-03-01",
  "2025-04-01",
  "2025-05-01",
  "2025-06-01",
  "2025-07-01",
  "2025-08-01",
  "2025-09-01",
  "2025-10-01",
  "2025-11-01",
  "2025-12-01",
]

function series(base: number, drift: number, noise = 0.5): Record<string, number> {
  const out: Record<string, number> = {}
  MONTHS_12.forEach((m, i) => {
    out[m] = base + drift * i + (Math.sin(i * 1.7) * noise)
  })
  return out
}

const carteiraPctRows: CompactSeriesRow[] = [
  { label: "Direitos Creditorios", emphasis: "header", values: {} },
  { label: "A vencer", format: "pct", indent: 1, values: series(72.1, 0.3) },
  { label: "Vencidos", format: "pct", indent: 1, values: series(8.2, -0.1, 0.3) },
  { label: "Total DC", format: "pct", emphasis: "subtotal", values: series(80.3, 0.2) },
  { separator: true },
  { label: "Renda fixa", emphasis: "header", values: {} },
  { label: "Titulos publicos", format: "pct", indent: 1, values: series(4.5, -0.05) },
  { label: "Fundos RF", format: "pct", indent: 1, values: series(6.1, -0.1) },
  { label: "Tesouraria", format: "pct", indent: 1, values: series(3.8, 0.02, 0.2) },
  { separator: true },
  { label: "PDD", format: "pct", emphasis: "emphasis", values: series(-1.8, -0.02, 0.1) },
  { label: "Total Geral Carteira", format: "pct", emphasis: "total", values: series(92.9, 0.08) },
]

const carteiraBrlRows: CompactSeriesRow[] = [
  { label: "Direitos Creditorios", emphasis: "header", values: {} },
  { label: "A vencer", format: "brl", indent: 1, values: series(187_540, 820) },
  { label: "Vencidos", format: "brl", indent: 1, values: series(21_330, -80) },
  { label: "Total DC", format: "brl", emphasis: "subtotal", values: series(208_870, 740) },
  { separator: true },
  { label: "Titulos publicos", format: "brl", values: series(11_720, -40) },
  { label: "Fundos RF", format: "brl", values: series(15_880, -120) },
  { label: "Tesouraria", format: "brl", values: series(9_890, 30) },
  { label: "PDD", format: "brl", emphasis: "emphasis", values: series(-4_680, -15) },
  { label: "Total Geral Carteira", format: "brl", emphasis: "total", values: series(241_680, 595) },
]

const atrasoRows: CompactSeriesRow[] = [
  { label: "0-30 dias", format: "pct", values: series(3.1, 0.02) },
  { label: "30-60 dias", format: "pct", values: series(1.8, -0.01) },
  { label: "60-90 dias", format: "pct", values: series(0.9, 0.01) },
  { label: "90-120 dias", format: "pct", values: series(0.6, 0.01) },
  { label: "120-180 dias", format: "pct", values: series(0.8, 0.005) },
  { label: "180-360 dias", format: "pct", values: series(0.7, 0.008) },
  { label: "> 360 dias", format: "pct", values: series(0.3, 0.002) },
  { label: "Total Vencidos", format: "pct", emphasis: "total", values: series(8.2, -0.01) },
]

export default function CompactSeriesTablePreviewPage() {
  return (
    <div className="flex flex-col gap-6 px-12 py-6 pb-20">
      <div className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-50">
          CompactSeriesTable · preview
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-500">
          Proposta de tabela canonica para series temporais (estilo Austin Rating). Dados ficticios. Use para validar densidade, enfases e formato de data antes de migrar a FichaFundoTab.
        </p>
      </div>

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
          1. Density <code className="font-mono text-xs">compact</code> (default) · Posicao da Carteira % do PL
        </h2>
        <CompactSeriesTable
          label="Indicador"
          periods={MONTHS_12}
          rows={carteiraPctRows}
          density="compact"
          footnote="Em % do PL. Fonte: cvm_remote.tab_i + tab_v."
        />
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
          2. Density <code className="font-mono text-xs">ultra</code> · Mesmos dados, mais denso
        </h2>
        <CompactSeriesTable
          label="Indicador"
          periods={MONTHS_12}
          rows={carteiraPctRows}
          density="ultra"
        />
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
          3. Density <code className="font-mono text-xs">comfortable</code> · Versao espacada
        </h2>
        <CompactSeriesTable
          label="Indicador"
          periods={MONTHS_12}
          rows={carteiraPctRows}
          density="comfortable"
        />
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
          4. Formato <code className="font-mono text-xs">mmm/aa</code> · Posicao em R$ mil
        </h2>
        <CompactSeriesTable
          label="Indicador (R$ mil)"
          periods={MONTHS_12}
          rows={carteiraBrlRows}
          density="compact"
          periodFormat="mmm/aa"
          footnote="Abreviacao automatica: valores > 10k mostram 'k', > 1M mostram 'M'."
        />
      </section>

      <section className="flex flex-col gap-2">
        <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
          5. Tabela curta · Atraso em buckets (%PL)
        </h2>
        <div className="lg:max-w-[720px]">
          <CompactSeriesTable
            label="Bucket de atraso"
            periods={MONTHS_12}
            rows={atrasoRows}
            density="compact"
          />
        </div>
      </section>
    </div>
  )
}
