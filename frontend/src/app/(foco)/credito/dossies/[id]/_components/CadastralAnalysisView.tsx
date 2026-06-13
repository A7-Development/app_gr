// CadastralAnalysisView — análise cadastral (cadastral_analyst) no cockpit.
//
// Em cima, os dados coletados (CadastralCard, fonte oficial); embaixo, o
// julgamento do agente sobre a saúde cadastral.
//
// Fase 1 / Etapa 2: a camada de julgamento renderiza via <SectionRenderer>.
// O CadastralCard (produtor "consulta/silver") segue como está — vira blocos
// via Contrato de Dados na Etapa 4.

"use client"

import { SectionRenderer } from "@/design-system/components/SectionRenderer"
import { type CadastralAnalysis } from "@/lib/credito-client"
import { CadastralCard } from "./CadastralCard"
import { cadastralToSection } from "../_lib/section-mappers"

export function CadastralAnalysisView({
  dossierId,
  output,
}: {
  dossierId: string
  output: CadastralAnalysis
}) {
  return (
    <div className="space-y-4">
      {/* Dados coletados (fonte oficial) */}
      <CadastralCard dossierId={dossierId} />

      {/* Julgamento do agente (via vocabulário de blocos) */}
      <SectionRenderer section={cadastralToSection(output)} mode="work" />
    </div>
  )
}
