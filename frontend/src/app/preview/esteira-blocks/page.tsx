"use client"

// Preview /preview/esteira-blocks — validação visual da Fase 1 / Etapa 2.
// Renderiza, com dados MOCK e sem backend/auth:
//   1. as 3 seções de agente (revenue/cadastral/social) via os mappers reais,
//      em modo WORK (workbench) e READ (projeção do dossiê) lado a lado;
//   2. exemplos isolados dos blocos que os agentes ainda não exercem
//      (tabela / grafico / conferencia / fonte_origem / sub_dossie).
// Objetivo: validar a consistência do vocabulário de blocos antes do wiring real.

import * as React from "react"

import { SectionRenderer } from "@/design-system/components/SectionRenderer"
import type { SectionDescriptor } from "@/design-system/types/section"
import type {
  CadastralAnalysis,
  RevenueAnalysis,
  SocialContractAnalysis,
} from "@/lib/credito-client"
import {
  cadastralToSection,
  revenueToSection,
  socialContractToSection,
} from "@/app/(foco)/credito/dossies/[id]/_lib/section-mappers"

// ─── Mocks dos outputs de agente ──────────────────────────────────────────────

const REVENUE: RevenueAnalysis = {
  resumo_executivo:
    "Faturamento crescente e consistente nos últimos 12 meses, com sazonalidade típica de varejo.",
  tendencia: { direcao: "crescente", intensidade: "forte", leitura: "Alta sustentada de ~16% no período." },
  sazonalidade: { detectada: true, confiavel: false, padrao: "pico de fim de ano (varejo)", meses_pico: ["2025-12"], meses_vale: ["2025-02"] },
  pontos_de_atencao: [
    { mes: "2025-12", tipo: "pico", esperado_ou_anomalo: "esperado", severidade: "baixa", observacao: "Pico de dezembro coerente com o setor." },
    { mes: "2025-07", tipo: "quebra", esperado_ou_anomalo: "anomalo", severidade: "media", observacao: "Queda isolada sem razão sazonal aparente." },
  ],
  qualidade_do_dado: { soma_confere: true, n_meses: 12, meses_faltantes: [], observacao: "Série completa e consistente." },
  credibilidade_documento: {
    assinado: true, signatarios_resumo: "João Contador (CRC-1234)", documento_recente: true,
    emitente_confere: true, ressalvas: ["Documento sem ECD anexa."], nivel: "alto",
    leitura: "Assinado por contador habilitado, recente, emitente confere.",
  },
  leitura_para_credito: "Capacidade de pagamento **estável** e em leve expansão — favorável à operação.",
}

const CADASTRAL: CadastralAnalysis = {
  resumo_executivo: "Empresa ativa há 12 anos, CNAE aderente, capital coerente com o porte.",
  situacao_cadastral: "ativa",
  tempo_atividade_leitura: "12 anos de atividade — maturidade operacional.",
  aderencia_atividade: "CNAE principal compatível com a operação de crédito pretendida.",
  porte_capital_leitura: "Capital social de R$ 250 mil, coerente com o faturamento declarado.",
  pontos_de_atencao: [
    { tipo: "capital", severidade: "baixa", observacao: "Capital não atualizado desde 2019." },
  ],
  leitura_para_credito: "Cadastro saudável e regular — sem impeditivos cadastrais.",
}

const SOCIAL: SocialContractAnalysis = {
  summary: "Estrutura societária simples, dois sócios, administração isolada.",
  qsa_changes_recent: false,
  qsa_changes_detail: null,
  signing_powers: { "João Silva": "isolada", "Maria Souza": "conjunta acima de R$ 100 mil" },
  object_compatible_with_operation: true,
  object_compatibility_rationale: "Objeto social cobre a atividade financiada.",
  capital_social: {},
  statutory_restrictions: ["Cessão de quotas a terceiros vedada sem anuência unânime."],
  checklist_results: [
    { code: "SOC.001", description: "QSA condizente com a Receita", status: "ok", rationale: "Sócios conferem.", confidence: 0.95 },
    { code: "SOC.004", description: "Cláusula de alçada", status: "alert", rationale: "Exige ¾ das quotas acima de 20% do capital.", confidence: 0.8 },
  ],
  red_flags: [],
}

// ─── Seção mock cobrindo os blocos não exercidos pelos agentes ────────────────

const VOCAB_EXTRA: SectionDescriptor = {
  id: "vocab-extra",
  stationId: "demo",
  titulo: "Demo",
  generatesDossierSection: false,
  blocks: [
    {
      id: "ex-grafico",
      type: "grafico",
      titulo: "Faturamento mensal",
      kpi: { eyebrow: "Faturamento mensal · 6 meses", valor: "R$ 1,2 mi", contexto: "média mensal" },
      series: [
        {
          nome: "receita",
          pontos: [
            { x: "jul", y: 980000 }, { x: "ago", y: 1100000 }, { x: "set", y: 1050000 },
            { x: "out", y: 1240000 }, { x: "nov", y: 1310000 }, { x: "dez", y: 1620000 },
          ],
        },
      ],
    },
    {
      id: "ex-tabela",
      type: "tabela",
      titulo: "Série mensal",
      colunas: [
        { key: "mes", label: "Mês", align: "left" },
        { key: "receita", label: "Receita", align: "right", formato: "brl" },
      ],
      linhas: [
        { mes: { valor: "out/25" }, receita: { valor: 1240000 } },
        { mes: { valor: "nov/25" }, receita: { valor: 1310000 } },
        { mes: { valor: "dez/25" }, receita: { valor: 1620000 } },
      ],
      rodape: { mes: { valor: "Total" }, receita: { valor: 4170000 } },
    },
    {
      id: "ex-conferencia",
      type: "conferencia",
      titulo: "Conferência da extração",
      linhas: [
        { campo: "Razão social", valorIa: "ACTION LINE DO BRASIL LTDA", valorDossie: "ACTION LINE DO BRASIL LTDA", estado: "ok" },
        { campo: "Capital social", valorIa: "R$ 200.000", valorDossie: "R$ 250.000", estado: "ajustado" },
        { campo: "Data de constituição", valorIa: "—", valorDossie: "—", estado: "pendente" },
      ],
    },
    {
      id: "ex-fonte",
      type: "fonte_origem",
      docId: "doc-mock-1",
      locator: { kind: "doc", docId: "doc-mock-1", page: 3 },
      provenance: { origin: "documento" },
    },
    {
      id: "ex-sub",
      type: "sub_dossie",
      titulo: "Empresa do grupo — XYZ LTDA (Fase 2)",
      descriptor: {
        id: "sub-1",
        stationId: "grupo-xyz",
        titulo: "XYZ LTDA",
        generatesDossierSection: false,
        blocks: [
          {
            id: "sub-ficha",
            type: "ficha",
            campos: [
              { label: "Situação", valor: "ativa", badge: { texto: "ativa", tom: "ok" } },
              { label: "Vínculo", valor: "sócia em comum", provenance: { origin: "fonte", locator: { kind: "silver", table: "credit_dossier_company", field: "vinculo" } } },
            ],
          },
        ],
      },
    },
  ],
}

// ─── Página ────────────────────────────────────────────────────────────────

function Pane({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex-1">
      <p className="mb-2 text-[10px] font-semibold uppercase tracking-[0.08em] text-gray-400">
        {title}
      </p>
      <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-950">
        {children}
      </div>
    </div>
  )
}

function SideBySide({ label, section }: { label: string; section: SectionDescriptor }) {
  return (
    <section className="space-y-2">
      <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">{label}</h2>
      <div className="flex flex-col gap-4 lg:flex-row">
        <Pane title="modo work (workbench)">
          <SectionRenderer section={section} mode="work" />
        </Pane>
        <Pane title="modo read (dossiê)">
          <SectionRenderer section={section} mode="read" />
        </Pane>
      </div>
    </section>
  )
}

export default function EsteiraBlocksPreview() {
  return (
    <div className="mx-auto max-w-6xl space-y-8 px-6 py-8">
      <header>
        <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-50">
          Esteira — vocabulário de blocos (Fase 1 / Etapa 2)
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          As 3 análises de agente via os mappers reais + os blocos restantes. Dados mock.
        </p>
      </header>

      <SideBySide label="Faturamento (revenue_analyst)" section={revenueToSection(REVENUE)} />
      <SideBySide label="Cadastral (cadastral_analyst)" section={cadastralToSection(CADASTRAL)} />
      <SideBySide label="Contrato social (social_contract_analyst)" section={socialContractToSection(SOCIAL)} />

      <section className="space-y-2">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
          Demais blocos do vocabulário (grafico · tabela · conferencia · fonte_origem · sub_dossie)
        </h2>
        <div className="rounded-lg border border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-950">
          <SectionRenderer section={VOCAB_EXTRA} mode="work" />
        </div>
      </section>
    </div>
  )
}
