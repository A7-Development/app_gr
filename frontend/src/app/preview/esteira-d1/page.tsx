"use client"

// Preview /preview/esteira-d1 — Estação Faturamento (frame D1, tela-herói)
// com dados MOCK do handoff. Renderiza o FaturamentoStation real em fase
// "homologar" (documento extraído + conferência + chart + leitura da IA).
// O painel de origem mostra fallback (sem backend no preview).

import * as React from "react"

import {
  ClosureBar,
  StationHeader,
  StationStateChip,
  StationsSidebar,
  type StationItem,
} from "@/design-system/components"
import type { CreditDocumentRead, RevenueAnalysis } from "@/lib/credito-client"
import { FaturamentoStation } from "@/app/(foco)/credito/dossies/[id]/_components/FaturamentoStation"

const MONTHLY = [
  ["2025-01", 2_410_000],
  ["2025-02", 2_380_000],
  ["2025-03", 2_520_000],
  ["2025-04", 2_490_000],
  ["2025-05", 2_610_000],
  ["2025-06", 2_580_000],
  ["2025-07", 2_720_000],
  ["2025-08", 2_690_000],
  ["2025-09", 2_810_000],
  ["2025-10", 2_690_000], // ajustado pelo analista (IA propôs 2.770.000)
  ["2025-11", 940_000], // pendente (outlier — digitalização borrada)
  ["2025-12", 3_080_000],
] as const

const monthlyRows = MONTHLY.map(([month, value]) => ({ month, value }))
const aiRows = monthlyRows.map((r) =>
  r.month === "2025-10" ? { ...r, value: 2_770_000 } : r,
)

const MOCK_DOC: CreditDocumentRead = {
  id: "doc-1",
  dossier_id: "mock",
  doc_type: "revenue_report",
  original_filename: "Balancete 2025 — Transportes Meridiano.pdf",
  mime_type: "application/pdf",
  file_size_bytes: 1_204_000,
  extraction_status: "success",
  ai_extraction: {
    extracted_fields: { monthly: monthlyRows, revenue: 29_920_000 },
    _ai_original: { monthly: aiRows, revenue: 30_000_000 },
    _analyst_edited: true,
  },
  ai_model_used: "claude-opus-4-8",
  ai_prompt_version: "extraction.revenue@v3",
  extraction_confidence: "0.94",
  extraction_error: null,
  uploaded_at: "2026-06-09T13:58:00Z",
}

const MOCK_ANALYSIS: RevenueAnalysis = {
  resumo_executivo:
    "Receita com crescimento consistente de 28% em 12 meses, sem ruptura de padrão. A queda pontual de novembro é incompatível com a sazonalidade declarada do setor e coincide com trecho de digitalização borrada — confirmar o valor no documento.",
  tendencia: { direcao: "alta", intensidade: "consistente", leitura: "crescimento sustentado" },
  sazonalidade: {
    detectada: true,
    confiavel: true,
    padrao: "pico no 4º tri",
    meses_pico: ["2025-12"],
    meses_vale: ["2025-02"],
  },
  pontos_de_atencao: [
    {
      mes: "2025-11",
      tipo: "outlier",
      esperado_ou_anomalo: "anômalo",
      severidade: "alta",
      observacao:
        "valor 65% abaixo da média — provável erro de leitura (digitalização borrada na p. 4).",
    },
  ],
  qualidade_do_dado: {
    soma_confere: true,
    n_meses: 12,
    meses_faltantes: [],
    observacao: "série completa",
  },
  credibilidade_documento: {
    assinado: true,
    signatarios_resumo: "contador responsável (CRC ativo)",
    documento_recente: true,
    emitente_confere: true,
    ressalvas: [],
    nivel: "alta",
    leitura: "documento assinado e recente",
  },
  leitura_para_credito: "favorável, condicionada à confirmação de novembro.",
}

const STATIONS: StationItem[] = [
  { id: "1", label: "1 · Identificação", sublabel: "fechada", state: "fechada" },
  { id: "2", label: "2 · Cadastral", sublabel: "fechada", state: "fechada" },
  { id: "3", label: "3 · Faturamento", sublabel: "conclusão pronta", state: "homologar" },
  { id: "4", label: "4 · Apontamentos", sublabel: "abre quando a 3 fechar", state: "bloqueada" },
  { id: "5", label: "5 · Parecer", sublabel: "abre quando 3–4 fecharem", state: "bloqueada" },
]

export default function EsteiraD1PreviewPage() {
  return (
    <div className="flex h-screen overflow-hidden bg-white dark:bg-gray-950">
      <StationsSidebar
        backHref="#"
        title="Transportes Meridiano Ltda"
        meta="DC-2026-0148 · R$ 2,5 mi pleiteado"
        progressPct={40}
        progressLabel="2 de 5"
        stations={STATIONS}
        activeId="3"
        onSelect={() => {}}
        dossierLabel="Ver dossiê · 40% montado"
        trailLabel="Trilha: 23 eventos · último há 4 min"
      />
      <div className="flex h-screen min-w-0 flex-1 flex-col">
        <StationHeader
          title="Estação 3 · Faturamento"
          chip={
            <StationStateChip variant="indigo">Aguardando homologação</StationStateChip>
          }
          subtitle="Rodou sozinho: recebimento do documento → extração de 12 valores em 47s → leitura do agente. Falta você: conferir Nov/25 e decidir sobre a leitura."
          substeps={[
            { label: "Documento", state: "done" },
            { label: "Conferência", state: "done" },
            { label: "Conclusão da IA", state: "active" },
            { label: "Fechamento", state: "future" },
          ]}
          onOpenTrail={() => {}}
          trailDisabled
        />
        <div className="flex-1 space-y-5 overflow-y-auto bg-gray-50 px-8 pb-6 pt-6 dark:bg-gray-925">
          <FaturamentoStation
            dossierId="mock"
            docs={[MOCK_DOC]}
            requiredDocTypes={["revenue_report"]}
            phase="homologar"
            agentOutput={MOCK_ANALYSIS}
            onApproveGate={() => {}}
            approving={false}
            onRerunAgent={() => {}}
            rerunning={false}
          />
        </div>
        <ClosureBar
          state="pending"
          statusText="Homologar a leitura fecha a estação e grava a seção §Faturamento no dossiê."
          pendingText="falta: decidir sobre a leitura da IA"
          primaryLabel="Fechar estação"
          onPrimary={() => {}}
        />
      </div>
    </div>
  )
}
