"use client"

/**
 * Controladoria > Fechamento Mensal > Lamina do Fundo.
 *
 * Lamina mensal do FIDC (documento de 3 paginas A4), alimentada 100% pelas
 * silver QiTech via /controladoria/lamina. Competencia sempre FECHADA (a
 * parcial do mes corrente nunca e oferecida). Export = print do navegador
 * (CSS @media print isola o documento). MOTIVO de divergir do pattern
 * Dashboard: e uma superficie de documento/impressao, nao pagina BI.
 */

import * as React from "react"
import { RiPrinterLine } from "@remixicon/react"
import { useQueryState } from "nuqs"

import { Button } from "@/components/tremor/Button"
import { PageHeader } from "@/design-system/components/PageHeader"
import { ErrorState } from "@/design-system/components/ErrorState"
import { LaminaDocument } from "@/components/controladoria/lamina/LaminaDocument"
import { useLamina, useLaminaCompetencias } from "@/lib/hooks/lamina"

export default function LaminaPage() {
  const [competencia, setCompetencia] = useQueryState("competencia")

  const competenciasQ = useLaminaCompetencias()
  const laminaQ = useLamina(competencia)

  // Default: a competencia efetivamente resolvida pelo backend (ultima fechada).
  const competenciaAtual = laminaQ.data?.competencia ?? competencia ?? ""

  const isLoading = laminaQ.isLoading || competenciasQ.isLoading

  return (
    <div className="flex h-full flex-col">
      {/* Toolbar (tela apenas; some na impressao) */}
      <div className="flex flex-wrap items-end justify-between gap-3 px-6 py-4 print:hidden">
        <PageHeader
          title="Lamina do Fundo"
          info="Lamina mensal do FIDC (3 paginas) gerada a partir das silver alimentadas pela QiTech. Sempre de competencia fechada — a parcial do mes corrente nao e exibida."
          subtitle="Controladoria · Fechamento Mensal"
        />
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-[13px] text-gray-600 dark:text-gray-300">
            <span className="text-gray-500 dark:text-gray-400">Competencia</span>
            <select
              className="h-[30px] rounded border border-gray-300 bg-white px-2 text-[13px] text-gray-900 dark:border-gray-700 dark:bg-gray-950 dark:text-gray-50"
              value={competenciaAtual}
              onChange={(e) => void setCompetencia(e.target.value || null)}
              disabled={competenciasQ.isLoading || !competenciasQ.data?.competencias.length}
            >
              {competenciasQ.data?.competencias.map((c) => (
                <option key={c.competencia} value={c.competencia}>
                  {c.label}
                </option>
              ))}
            </select>
          </label>
          <Button
            variant="secondary"
            className="h-[30px]"
            onClick={() => window.print()}
            disabled={!laminaQ.data}
          >
            <RiPrinterLine className="mr-1.5 size-4" aria-hidden />
            Exportar PDF
          </Button>
        </div>
      </div>

      {/* Conteudo */}
      <div className="min-h-0 flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="flex items-center justify-center gap-2 py-24 text-sm text-gray-500 dark:text-gray-400">
            <span className="size-4 animate-spin rounded-full border-2 border-gray-300 border-t-blue-500" />
            Carregando a lamina…
          </div>
        ) : laminaQ.isError ? (
          <div className="px-6 py-12">
            <ErrorState
              title="Nao foi possivel carregar a lamina"
              description="Verifique se ha competencia fechada com dados publicados para o fundo."
              action={
                <Button variant="secondary" onClick={() => void laminaQ.refetch()}>
                  Tentar novamente
                </Button>
              }
            />
          </div>
        ) : laminaQ.data ? (
          <LaminaDocument data={laminaQ.data} />
        ) : null}
      </div>
    </div>
  )
}
