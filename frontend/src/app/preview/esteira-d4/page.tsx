"use client"

// Preview /preview/esteira-d4 — Dossiê de leitura (frame D4, projeção
// compilada) com dados mock do handoff. Cadastral mostra fallback (sem
// backend no preview).

import * as React from "react"

import { StationsSidebar, type StationItem } from "@/design-system/components"
import type {
  CreditDocumentRead,
  DossierRead,
  RedFlagItem,
  RevenueAnalysis,
} from "@/lib/credito-client"
import { DossierReadingView } from "@/app/(foco)/credito/dossies/[id]/_components/DossierReadingView"

const MONTHLY = [
  ["2025-01", 2_410_000], ["2025-02", 2_380_000], ["2025-03", 2_520_000],
  ["2025-04", 2_490_000], ["2025-05", 2_610_000], ["2025-06", 2_580_000],
  ["2025-07", 2_720_000], ["2025-08", 2_690_000], ["2025-09", 2_810_000],
  ["2025-10", 2_770_000], ["2025-11", 2_940_000], ["2025-12", 3_080_000],
].map(([month, value]) => ({ month: String(month), value: Number(value) }))

const MOCK_DOC: CreditDocumentRead = {
  id: "doc-1",
  dossier_id: "mock",
  doc_type: "revenue_report",
  original_filename: "Balancete 2025 — Transportes Meridiano.pdf",
  mime_type: "application/pdf",
  file_size_bytes: 1_204_000,
  extraction_status: "validated",
  ai_extraction: {
    extracted_fields: { monthly: MONTHLY, revenue: 31_000_000 },
    _ai_original: { monthly: MONTHLY, revenue: 31_000_000 },
    _analyst_edited: true,
  },
  ai_model_used: "claude-opus-4-8",
  ai_prompt_version: "extraction.revenue@v3",
  extraction_confidence: "0.94",
  extraction_error: null,
  uploaded_at: "2026-06-09T13:58:00Z",
}

const MOCK_DOSSIER: DossierRead = {
  id: "dc20260148-0000-0000-0000-000000000000",
  tenant_id: "t",
  target_cnpj: "31.482.905/0001-44",
  target_name: "Transportes Meridiano Ltda",
  status: "finalized",
  operation_type: "cessao",
  requested_amount: "2000000",
  requested_term_days: null,
  analyst_id: "mc",
  workflow_definition_id: "wf",
  workflow_run_id: "run",
  created_at: "2026-06-09T10:00:00Z",
  updated_at: "2026-06-10T09:12:00Z",
  finalized_at: "2026-06-10T09:12:00Z",
  notes: null,
  completed_steps: 8,
  total_steps: 8,
  next_action_kind: "finalized",
  next_action_label: "Finalizado",
  next_node_id: null,
}

const MOCK_REVENUE: RevenueAnalysis = {
  resumo_executivo:
    "Receita com crescimento consistente de 28% em 12 meses, sem ruptura de padrão.",
  tendencia: { direcao: "alta", intensidade: "consistente", leitura: "crescimento sustentado" },
  sazonalidade: { detectada: true, confiavel: true, padrao: "pico 4º tri", meses_pico: [], meses_vale: [] },
  pontos_de_atencao: [],
  qualidade_do_dado: { soma_confere: true, n_meses: 12, meses_faltantes: [], observacao: "" },
  credibilidade_documento: {
    assinado: true, signatarios_resumo: null, documento_recente: true,
    emitente_confere: true, ressalvas: [], nivel: "alta", leitura: "",
  },
  leitura_para_credito: "favorável, sem ressalvas de faturamento.",
}

const MOCK_FLAGS: RedFlagItem[] = [
  {
    id: "f1",
    section: "faturamento",
    severity: "important",
    title: "Concentração em 3 sacados acima de 60%",
    description:
      "Os três maiores sacados respondem por 62% do faturamento — acima da política PC-04 (50%).",
    evidence: "curva ABC × faturamento mensal",
    check_type: "concentracao",
    provenance: null,
    decision_log_id: null,
    raised_by_agent: null,
    analyst_resolution: null,
    analyst_notes: null,
    created_at: "2026-06-09T16:31:00Z",
  },
]

const OPINION = {
  executive_summary:
    "A análise sustenta aprovação condicional de R$ 2,0 mi (pleito de R$ 2,5 mi). Faturamento crescente e bem documentado; cadastro regular há 8 anos. A concentração em 3 sacados exige mitigação via trava de concentração por sacado e reapresentação de curva ABC em 30 dias.",
  recommendation: "conditional" as const,
  strengths: [
    "Faturamento médio de R$ 2,68 mi/mês com tendência de alta consistente",
    "Documento assinado por contador com CRC ativo — credibilidade alta",
    "Cadastro regular, CNAE aderente à operação",
  ],
  concerns: [
    "Concentração de 62% nos 3 maiores sacados (política: 50%)",
    "Pleito 25% acima do limite sugerido pela política de faturamento",
  ],
  conditions: [
    "Trava de concentração por sacado em 25% do limite",
    "Reapresentação da curva ABC em até 30 dias",
    "Limite inicial de R$ 2,0 mi, revisão em 90 dias",
  ],
}

const STATIONS: StationItem[] = [
  { id: "1", label: "1 · Identificação", sublabel: "fechada", state: "fechada" },
  { id: "2", label: "2 · Cadastral", sublabel: "fechada", state: "fechada" },
  { id: "3", label: "3 · Faturamento", sublabel: "fechada", state: "fechada" },
  { id: "4", label: "4 · Apontamentos", sublabel: "fechada", state: "fechada" },
  { id: "5", label: "5 · Parecer", sublabel: "assinado", state: "fechada" },
]

export default function EsteiraD4PreviewPage() {
  return (
    <div className="flex h-screen overflow-hidden bg-white dark:bg-gray-950">
      <StationsSidebar
        backHref="#"
        title="Transportes Meridiano Ltda"
        meta="DC-2026-0148 · R$ 2,5 mi pleiteado"
        progressPct={100}
        progressLabel="5 de 5"
        stations={STATIONS}
        activeId={null}
        onSelect={() => {}}
        dossierLabel="Ver dossiê · completo"
        dossierActive
        onOpenDossier={() => {}}
        trailLabel="Trilha: 31 eventos · assinado às 09:12"
      />
      <DossierReadingView
        dossier={MOCK_DOSSIER}
        docs={[MOCK_DOC]}
        redFlags={MOCK_FLAGS}
        revenueOutput={MOCK_REVENUE}
        opinionOutput={OPINION}
        hasCadastral={false}
        agentSteps={[
          { id: "ag1", label: "Análise de faturamento", state: "completed", nodeType: "specialist_agent" },
          { id: "ag2", label: "Análise cadastral", state: "completed", nodeType: "specialist_agent" },
        ]}
        adjustments={[
          "Valores de Balancete 2025 ajustados pelo analista · original preservado",
        ]}
        progressPct={100}
        trailCount={31}
        onOpenTrail={() => {}}
        onGoToStation={() => {}}
      />
    </div>
  )
}
