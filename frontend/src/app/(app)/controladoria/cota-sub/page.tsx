// src/app/(app)/controladoria/cota-sub/page.tsx
//
// Controladoria · Cota Sub — analise da cota subordinada do FIDC.
// Pagina derivada do pattern `DashboardBiPadrao` (handoff bi-padrao 2026-04-26).
//
// HOW TO ADAPT (mocks → queries reais):
//   1. Substituir MOCK_MOVIMENTACOES por useQuery contra endpoint
//      /controladoria/cota-sub/movimentacoes (futuro).
//   2. Substituir MOCK_INSIGHTS por insights gerados pela IA (server-side LLM).
//   3. Substituir MOCK_PROVENANCE por status real dos adapters
//      (Bitfin, QiTech, PDD).
//   4. Substituir series ECharts por dados de wh_posicao_cota_fundo +
//      wh_movimentacao_cotista (warehouse silver).
//   5. Conectar AIPanel.sendMessage no LLM real (api.aiChat).
//
// L3 tabs por agora: Visao geral · Evolucao · Cotistas. Quando outras
// dimensoes (por classe, por sacado da operacao, por safra) entrarem,
// basta adicionar entradas em TABS — pagina nao precisa de refactor.

"use client"

import * as React from "react"
import {
  RiAlertLine,
  RiArrowDownLine,
  RiArrowUpLine,
  RiCalendarLine,
  RiCheckLine,
  RiDownloadLine,
  RiEqualizerLine,
  RiFundsLine,
  RiInformationLine,
  RiShareLine,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import type { EChartsOption } from "echarts"

import { format, isSameDay, parseISO } from "date-fns"
import { ptBR } from "date-fns/locale"

import { cx, focusRing } from "@/lib/utils"
import { Button } from "@/components/tremor/Button"
import { Calendar } from "@/components/tremor/Calendar"
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/tremor/Popover"
import {
  TabNavigation,
  TabNavigationLink,
} from "@/components/tremor/TabNavigation"

import { PageHeader } from "@/design-system/components/PageHeader"
import {
  KpiCard,
  KpiStrip,
} from "@/design-system/components/KpiStrip"
import { EChartsCard } from "@/design-system/components/EChartsCard"
import {
  FilterBar,
  FilterChip,
  FilterSearch,
  RemovableChip,
  SavedViewsDropdown,
} from "@/design-system/components/FilterBar"
import { EmptyState } from "@/design-system/components/EmptyState"
import { Insight, InsightBar } from "@/design-system/components/Insight"
import { useUAs } from "@/lib/hooks/cadastros"
import { useVariacaoDiaria } from "@/lib/hooks/controladoria"
import type { VariacaoDiariaResponse as ApiVariacao } from "@/lib/api-client"
import {
  CurrencyCell,
  DataTable,
  DateCell,
  IdCell,
  StatusCell,
} from "@/design-system/components/DataTable"
import {
  DrillDownSheet,
  type TimelineEventDef,
} from "@/design-system/components/DrillDownSheet"
import {
  AIPanel,
  AIToggleButton,
  useAIPanel,
  type AIInsight,
} from "@/design-system/components/AIPanel"
import { tokens, type StatusKey } from "@/design-system/tokens"

// ───────────────────────────────────────────────────────────────────────────
// Tipos + Mocks
// ───────────────────────────────────────────────────────────────────────────

type MovimentacaoTipo = "subscricao" | "resgate"

type MovimentacaoRow = {
  id:      string
  cotista: string
  classe:  "Mezanino" | "Junior"
  tipo:    MovimentacaoTipo
  valor:   number
  data:    string
  status:  StatusKey
}

const MOCK_MOVIMENTACOES: MovimentacaoRow[] = [
  { id: "MOV-2026-000821", cotista: "Aurora Capital",        classe: "Mezanino", tipo: "subscricao", valor:   850_000, data: "2026-04-22", status: "liquidado" },
  { id: "MOV-2026-000822", cotista: "Vanguard FII",          classe: "Junior",   tipo: "subscricao", valor:   320_000, data: "2026-04-20", status: "em-dia" },
  { id: "MOV-2026-000823", cotista: "Helios Asset",          classe: "Mezanino", tipo: "resgate",    valor:   180_000, data: "2026-04-18", status: "em-dia" },
  { id: "MOV-2026-000824", cotista: "Atlas Investimentos",   classe: "Junior",   tipo: "resgate",    valor:    95_000, data: "2026-04-15", status: "liquidado" },
  { id: "MOV-2026-000825", cotista: "Aurora Capital",        classe: "Mezanino", tipo: "subscricao", valor: 1_200_000, data: "2026-04-10", status: "liquidado" },
  { id: "MOV-2026-000826", cotista: "Polaris Family Office", classe: "Junior",   tipo: "subscricao", valor:   540_000, data: "2026-04-08", status: "liquidado" },
]

const MOCK_INSIGHTS: AIInsight[] = [
  { text: "Subordinacao efetiva em 15,0% (+0,3pp), acima do minimo regulamentar de 10%. Margem confortavel para absorver perdas." },
  { text: "Rentabilidade da Cota Sub em 118,2% do CDI — 3 meses consecutivos batendo o benchmark." },
  { text: "Top 3 cotistas concentram 62% do PL subordinado — acima do alerta interno de 50%. Considerar diversificacao." },
]

const MOCK_PROVENANCE = [
  { label: "Bitfin", updated: "ha 12 min", sla: "15 min", stale: false },
  { label: "QiTech", updated: "ha 8 min",  sla: "30 min", stale: false },
  { label: "PDD",    updated: "ha 47 min", sla: "30 min", stale: true  },
]

// ───────────────────────────────────────────────────────────────────────────
// Variacao diaria — contrato com backend (futuro endpoint
// GET /controladoria/cota-sub/variacao-diaria?fundo_id={id}&data={D0}).
//
// Logica espelhada da planilha "VariacaoDeCota_Preenchida.xlsx" (aba Analise):
//   PL Sub Jr (D0) − PL Sub Jr (D-1) = Σ delta por categoria de ativo
//   Painel de Impactos atribui parcelas a "causas" (apropriacao vs movimento).
//
// Origem dos campos no warehouse silver (canonico) — ver mapeamento aprovado:
//   - PL Sub Jr           ← wh_mec_evolucao_cotas (campo `patrimonio`)
//   - Compromissada       ← wh_posicao_compromissada (sum valor_bruto)
//   - Mezanino/Senior     ← wh_mec_evolucao_cotas (classe Mez/Sr, patrimonio × −1)
//   - Titulos Publicos    ← wh_posicao_outros_ativos (filtro TPF)
//   - Fundos DI           ← wh_posicao_cota_fundo (filtro DI)
//   - DC                  ← wh_estoque_recebivel.valor_presente (liquido de PDD)
//   - Op Estruturadas/    ← wh_posicao_outros_ativos (trazer tudo, segregar
//     Outros Ativos          por tipo_do_ativo no frontend)
//   - PDD                 ← wh_estoque_recebivel.valor_pdd (absoluto, negativo)
//   - CPR                 ← wh_cpr_movimento (sum valor agregado)
//   - Tesouraria          ← wh_saldo_tesouraria + wh_saldo_conta_corrente
//   - Apropriacao DC      ← derivado: G − (D + E + F) sobre wh_estoque_recebivel
//                          + wh_aquisicao_recebivel + wh_liquidacao_recebivel
//   - Apropriacao despesas ← derivado de wh_cpr_movimento (D37 da aba CPR)

type PlCategoriaKey =
  | "compromissada" | "mezanino" | "senior" | "titulos_publicos"
  | "fundos_di" | "dc" | "op_estruturadas" | "outros_ativos"
  | "pdd" | "cpr" | "tesouraria"

type PlCategoria = {
  key:    PlCategoriaKey
  label:  string
  d1:     number   // valor em D-1 (R$)
  d0:     number   // valor em D0  (R$)
  delta:  number   // d0 − d1
  source: string   // tabela canonica origem
}

type DecomposicaoSinal = "ganho" | "prejuizo" | "neutro"

type DecomposicaoItem = {
  key:    string
  label:  string
  valor:  number
  sinal:  DecomposicaoSinal
}

type ApropriacaoDcLinha = {
  estoque_d1:  number
  aquisicoes:  number
  liquidados:  number  // negativo = saida
  estoque_d0:  number
  apropriacao: number  // estoque_d0 − (estoque_d1 + aquisicoes + liquidados)
}

type ApropriacaoDc = {
  a_vencer:  ApropriacaoDcLinha
  vencidos:  ApropriacaoDcLinha
  total:     number
}

type CprMovimentoItem = {
  descricao: string
  valor:     number
}

type CprDetalhado = {
  receber_d1: CprMovimentoItem[]
  receber_d0: CprMovimentoItem[]
  pagar_d1:   CprMovimentoItem[]
  pagar_d0:   CprMovimentoItem[]
  total_d1:   number  // recebivel − pagavel em D-1
  total_d0:   number  // recebivel − pagavel em D0
  variacao:   number  // total_d0 − total_d1
}

type VariacaoDiariaResponse = {
  fundo_id:           string
  fundo_nome:         string
  data:               string  // ISO D0
  data_anterior:      string  // ISO D-1 (dia util anterior)
  pl_d1:              number
  pl_d0:              number
  pl_delta:           number  // pl_d0 − pl_d1
  pl_delta_pct:       number  // pl_delta / pl_d1
  categorias:         PlCategoria[]
  decomposicao:       DecomposicaoItem[]
  decomposicao_total: number
  divergencia:        number  // decomposicao_total − pl_delta (deve ser ~0)
  apropriacao_dc:     ApropriacaoDc
  cpr_detalhado:      CprDetalhado
}

// Mock construido a partir da planilha (28/11/2025 → 01/12/2025).
// Substituir por useQuery contra /controladoria/cota-sub/variacao-diaria.
const MOCK_VARIACAO: VariacaoDiariaResponse = {
  fundo_id:      "realinvet-001",
  fundo_nome:    "Realinvet",
  data:          "2025-12-01",
  data_anterior: "2025-11-28",
  pl_d1:          9_931_604.76,
  pl_d0:          9_907_498.55,
  pl_delta:        -24_106.21,
  pl_delta_pct:    -0.002428,
  categorias: [
    { key: "compromissada",     label: "Compromissada",     d1:           0, d0:            0, delta:          0,    source: "wh_posicao_compromissada" },
    { key: "mezanino",          label: "Mezanino",          d1:   -748_968.54, d0:    -749_554.75, delta:       -586.21, source: "wh_mec_evolucao_cotas (classe Mez × −1)" },
    { key: "senior",            label: "Senior",            d1:  -6_580_013.75, d0:  -7_182_520.07, delta:   -602_506.32, source: "wh_mec_evolucao_cotas (classe Sr × −1)" },
    { key: "titulos_publicos",  label: "Titulos Publicos",  d1:      12_091.03, d0:      12_066.77, delta:        -24.26, source: "wh_posicao_outros_ativos (TPF)" },
    { key: "fundos_di",         label: "Fundos DI",         d1:      35_614.96, d0:     550_634.35, delta:    515_019.39, source: "wh_posicao_cota_fundo (DI)" },
    { key: "dc",                label: "DC",                d1:  17_175_520.63, d0:  17_072_781.29, delta:   -102_739.34, source: "wh_estoque_recebivel.valor_presente" },
    { key: "op_estruturadas",   label: "Op Estruturadas",   d1:     220_608.15, d0:     199_828.94, delta:    -20_779.21, source: "wh_posicao_outros_ativos (estruturadas)" },
    { key: "outros_ativos",     label: "Outros Ativos",     d1:           0, d0:            0, delta:          0,    source: "wh_posicao_outros_ativos (demais)" },
    { key: "pdd",               label: "PDD",               d1:    -333_940.40, d0:    -336_007.70, delta:     -2_067.30, source: "wh_estoque_recebivel.valor_pdd" },
    { key: "cpr",               label: "CPR",               d1:     149_615.77, d0:     339_796.27, delta:    190_180.50, source: "wh_cpr_movimento (sum valor)" },
    { key: "tesouraria",        label: "Tesouraria",        d1:       1_076.91, d0:         473.45, delta:       -603.46, source: "wh_saldo_tesouraria + wh_saldo_conta_corrente" },
  ],
  decomposicao: [
    { key: "pdd",            label: "PDD",                  valor:     -2_067.30, sinal: "prejuizo" },
    { key: "apropriacao_dc", label: "Apropriacao de DC",    valor:     26_425.11, sinal: "ganho" },
    { key: "fundos_di",      label: "Fundos DI",            valor:    600_000.00, sinal: "ganho" },
    { key: "apropriacao_dsp",label: "Apropriacao despesas", valor:     -5_785.23, sinal: "prejuizo" },
    { key: "compromissada",  label: "Compromissada",        valor:           0, sinal: "neutro" },
    { key: "senior",         label: "Senior",               valor:   -602_506.32, sinal: "prejuizo" },
    { key: "mezanino",       label: "Mezanino",             valor:       -586.21, sinal: "prejuizo" },
    { key: "titulos",        label: "Titulos Publicos",     valor:        -24.26, sinal: "prejuizo" },
    { key: "tarifas",        label: "Tarifas",              valor:           0, sinal: "neutro" },
  ],
  decomposicao_total: 15_455.79,
  divergencia:        39_562.00,
  apropriacao_dc: {
    a_vencer: {
      estoque_d1:   16_506_992.33,
      aquisicoes:      568_996.10,
      liquidados:      -45_959.99,
      estoque_d0:   16_392_350.47,
      apropriacao:    -637_637.97,
    },
    vencidos: {
      estoque_d1:      668_528.22,
      aquisicoes:            0.00,
      liquidados:     -652_160.52,
      estoque_d0:      680_430.78,
      apropriacao:     664_063.08,
    },
    total:              26_425.11,
  },
  cpr_detalhado: {
    receber_d1: [
      { descricao: "Valores a receber 1b · item 1", valor: 2_417.26 },
      { descricao: "Valores a receber 1b · item 2", valor: 3_283.42 },
    ],
    receber_d0: [
      { descricao: "Valores a receber 2b · item 1", valor: 2_377.63 },
      { descricao: "Valores a receber 2b · item 2", valor: 3_251.54 },
    ],
    pagar_d1: [
      { descricao: "Valores a pagar 1a · item 1", valor: -6_371.03 },
      { descricao: "Valores a pagar 1a · item 2", valor:   -701.35 },
      { descricao: "Valores a pagar 1a · item 3", valor:     -2.53 },
      { descricao: "Valores a pagar 1a · item 4", valor: -4_253.26 },
      { descricao: "Valores a pagar 1a · item 5", valor: -13_535.33 },
      { descricao: "Valores a pagar 1a · item 6", valor: -6_379.89 },
    ],
    pagar_d0: [
      { descricao: "Valores a pagar 2a · item 1",  valor:     -2.53 },
      { descricao: "Valores a pagar 2a · item 2",  valor: -6_408.73 },
      { descricao: "Valores a pagar 2a · item 3",  valor: -4_545.45 },
      { descricao: "Valores a pagar 2a · item 4",  valor:   -701.35 },
      { descricao: "Valores a pagar 2a · item 5",  valor:    -31.88 },
      { descricao: "Valores a pagar 2a · item 6",  valor:     -0.12 },
      { descricao: "Valores a pagar 2a · item 7",  valor: -4_253.26 },
      { descricao: "Valores a pagar 2a · item 8",  valor:   -193.33 },
      { descricao: "Valores a pagar 2a · item 9",  valor: -13_535.33 },
      { descricao: "Valores a pagar 2a · item 10", valor:   -615.24 },
      { descricao: "Valores a pagar 2a · item 11", valor: -6_379.89 },
      { descricao: "Valores a pagar 2a · item 12", valor:   -290.00 },
    ],
    total_d1:    -25_542.71,
    total_d0:    -31_327.94,
    variacao:     -5_785.23,
  },
}

// ───────────────────────────────────────────────────────────────────────────
// L3 Tabs
// ───────────────────────────────────────────────────────────────────────────

const TABS = [
  { key: "visao-geral", label: "Visao geral" },
  { key: "evolucao",    label: "Evolucao" },
  { key: "cotistas",    label: "Cotistas" },
] as const

type TabKey = (typeof TABS)[number]["key"]

// ───────────────────────────────────────────────────────────────────────────
// Filtros
// ───────────────────────────────────────────────────────────────────────────

const CLASSE_OPTIONS = ["Todas", "Subordinada Mezanino", "Subordinada Junior"] as const

type ClasseOption = (typeof CLASSE_OPTIONS)[number]

// Filtros dinamicos (adicionados via "Mais filtros"). Default values
// definem o "Todos/Nenhum" do filtro — quando o user troca, o chip vira
// active e ganha botao de remover.
type DynamicFilterKey = "Cotista" | "Status" | "Classe op." | "Origem"

const DYNAMIC_FILTER_OPTIONS: Record<DynamicFilterKey, readonly string[]> = {
  Cotista:     ["Todos", "Aurora Capital", "Vanguard FII", "Helios Asset", "Atlas Investimentos", "Polaris Family Office"],
  Status:      ["Todos", "Em dia", "Liquidado", "Atrasado", "Inadimplente"],
  "Classe op.": ["Todas", "Multiclasse", "Padronizado", "Nao-padronizado"],
  Origem:      ["Todas", "QiTech", "Bitfin", "Manual"],
}

type DynamicFilter = { key: DynamicFilterKey; value: string }

// Filtros inline na DataTable (Status / Cotista) — mesmas opcoes que
// os dinamicos, mas com escopo limitado a tabela (nao reaplicam a charts).
const TABLE_STATUS_OPTIONS  = DYNAMIC_FILTER_OPTIONS.Status
const TABLE_COTISTA_OPTIONS = DYNAMIC_FILTER_OPTIONS.Cotista

// ───────────────────────────────────────────────────────────────────────────
// ECharts options (mock — substituir pelas series reais)
// ───────────────────────────────────────────────────────────────────────────

const MONTHS = ["Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez", "Jan", "Fev", "Mar", "Abr"]
const CHART_COLORS = tokens.colors.chart

const plCotaSubOption: EChartsOption = {
  grid: { top: 12, right: 12, bottom: 28, left: 52 },
  xAxis: { type: "category", data: MONTHS, axisTick: { show: false } },
  yAxis: { type: "value", min: 14, axisLabel: { formatter: "R$ {value}M" } },
  series: [
    {
      type: "line", smooth: true, symbol: "none",
      data: [14.8, 15.2, 15.6, 15.9, 16.2, 16.5, 16.8, 17.1, 17.4, 17.9, 18.3, 18.7],
      lineStyle: { color: "#3B82F6", width: 2 },
      areaStyle: {
        color: {
          type: "linear", x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: "rgba(59,130,246,0.20)" },
            { offset: 1, color: "rgba(59,130,246,0)" },
          ],
        },
      },
    },
  ],
  tooltip: { trigger: "axis" },
}

const distribClasseOption: EChartsOption = {
  tooltip: { trigger: "item", formatter: "{b}: {d}%" },
  legend:  { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
  series: [
    {
      type: "pie", radius: ["42%", "70%"], center: ["50%", "44%"],
      label: { show: false },
      data: [
        { name: "Mezanino", value: 68, itemStyle: { color: CHART_COLORS[0] } },
        { name: "Junior",   value: 32, itemStyle: { color: CHART_COLORS[3] } },
      ],
    },
  ],
}

const subscRescOption: EChartsOption = {
  grid: { top: 8, right: 12, bottom: 28, left: 48 },
  xAxis: { type: "category", data: MONTHS, axisTick: { show: false } },
  yAxis: { type: "value", axisLabel: { formatter: "R$ {value}M" } },
  series: [
    { name: "Subscricao", type: "bar", data: [1.2, 0.8, 1.4, 1.0, 1.6, 1.3, 1.5, 1.1, 1.8, 1.4, 2.1, 2.4], itemStyle: { color: "#10B981" } },
    { name: "Resgate",    type: "bar", data: [0.3, 0.5, 0.4, 0.6, 0.4, 0.5, 0.7, 0.6, 0.5, 0.8, 0.6, 0.7], itemStyle: { color: "#EF4444" } },
  ],
  legend:  { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
  tooltip: { trigger: "axis", axisPointer: { type: "shadow" } },
}

const rentabSubOption: EChartsOption = {
  grid: { top: 12, right: 12, bottom: 28, left: 48 },
  xAxis: { type: "category", data: MONTHS, axisTick: { show: false } },
  yAxis: { type: "value", min: 100, axisLabel: { formatter: "{value}%" } },
  series: [
    {
      name: "Cota Sub", type: "line", smooth: true, symbol: "none",
      data: [102, 104, 107, 109, 110, 112, 113, 114, 115, 116, 117, 118],
      lineStyle: { color: "#3B82F6", width: 2 },
      areaStyle: {
        color: {
          type: "linear", x: 0, y: 0, x2: 0, y2: 1,
          colorStops: [
            { offset: 0, color: "rgba(59,130,246,0.15)" },
            { offset: 1, color: "rgba(59,130,246,0)" },
          ],
        },
      },
    },
    {
      name: "CDI", type: "line", smooth: true, symbol: "none",
      data: [101, 102, 103, 104, 105, 106, 107, 108, 109, 110, 111, 112],
      lineStyle: { color: "#9CA3AF", width: 1.5, type: "dashed" },
    },
  ],
  legend:  { bottom: 0, icon: "circle", itemWidth: 8, itemHeight: 8 },
  tooltip: { trigger: "axis" },
}

const topCotistasOption: EChartsOption = {
  grid: { top: 8, right: 24, bottom: 8, left: 110 },
  xAxis: { type: "value", axisLabel: { formatter: "{value}%" } },
  yAxis: {
    type: "category",
    data: ["Outros", "Polaris FO", "Atlas Inv.", "Helios Asset", "Vanguard FII", "Aurora Capital"],
    axisTick: { show: false },
  },
  series: [
    {
      type: "bar", barMaxWidth: 18,
      data: [
        { value: 12, itemStyle: { color: "#9CA3AF",       borderRadius: [0, 3, 3, 0] } },
        { value: 8,  itemStyle: { color: CHART_COLORS[5], borderRadius: [0, 3, 3, 0] } },
        { value: 8,  itemStyle: { color: CHART_COLORS[4], borderRadius: [0, 3, 3, 0] } },
        { value: 10, itemStyle: { color: CHART_COLORS[3], borderRadius: [0, 3, 3, 0] } },
        { value: 22, itemStyle: { color: CHART_COLORS[2], borderRadius: [0, 3, 3, 0] } },
        { value: 40, itemStyle: { color: CHART_COLORS[0], borderRadius: [0, 3, 3, 0] } },
      ],
    },
  ],
  tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, formatter: "{b}: {c}%" },
}

// ───────────────────────────────────────────────────────────────────────────
// Sparklines (mock)
// ───────────────────────────────────────────────────────────────────────────

const SPARK_PL_SUB   = [14.8, 15.2, 15.6, 15.9, 16.2, 16.5, 16.8, 17.1, 17.4, 17.9, 18.3, 18.7]
const SPARK_SUBORD   = [13.8, 14.0, 14.2, 14.3, 14.4, 14.5, 14.6, 14.7, 14.8, 14.9, 14.9, 15.0]
const SPARK_RENT_SUB = [102, 104, 107, 109, 110, 112, 113, 114, 115, 116, 117, 118]
const SPARK_COTISTAS = [9, 9, 10, 10, 10, 11, 11, 11, 11, 12, 12, 12]
const SPARK_RESGATES = [1, 0, 2, 1, 2, 1, 2, 1, 2, 3, 2, 3]

// ───────────────────────────────────────────────────────────────────────────
// labelForStatus — mapeia StatusKey canonico para o rotulo do filtro inline
// ───────────────────────────────────────────────────────────────────────────

const STATUS_LABEL: Record<StatusKey, string> = {
  "em-dia":       "Em dia",
  "liquidado":    "Liquidado",
  "atrasado-30":  "Atrasado",
  "atrasado-60":  "Atrasado",
  "inadimplente": "Inadimplente",
  "recomprado":   "Liquidado",
}

function labelForStatus(s: StatusKey): string {
  return STATUS_LABEL[s] ?? "Em dia"
}

// ───────────────────────────────────────────────────────────────────────────
// AddFilterMenu — Popover de "Mais filtros" (lista dimensoes disponiveis)
// ───────────────────────────────────────────────────────────────────────────

function AddFilterMenu({
  available,
  onAdd,
}: {
  available: DynamicFilterKey[]
  onAdd:     (k: DynamicFilterKey) => void
}) {
  const [open, setOpen] = React.useState(false)
  if (available.length === 0) return null

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <button
          type="button"
          className={cx(
            "inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded border px-2.5 py-1 text-xs transition-colors duration-100",
            "border-gray-200 bg-white text-gray-700 hover:bg-gray-50",
            "dark:border-gray-800 dark:bg-gray-950 dark:text-gray-300",
            focusRing,
          )}
        >
          <RiEqualizerLine className="size-3.5 shrink-0" aria-hidden="true" />
          <span className="font-medium">Mais filtros</span>
        </button>
      </PopoverTrigger>
      <PopoverContent align="start" sideOffset={6} className="min-w-44 p-1">
        <p className="px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600">
          Dimensao
        </p>
        {available.map((dim) => (
          <button
            key={dim}
            type="button"
            onClick={() => { setOpen(false); onAdd(dim) }}
            className={cx(
              "block w-full rounded px-2 py-1.5 text-left text-sm transition-colors",
              "text-gray-700 hover:bg-gray-100 dark:text-gray-300 dark:hover:bg-gray-800",
              focusRing,
            )}
          >
            {dim}
          </button>
        ))}
      </PopoverContent>
    </Popover>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// VizParam (chip group de período curto)
// ───────────────────────────────────────────────────────────────────────────

function VizParam({
  options,
  value,
  onChange,
}: {
  options:  readonly string[]
  value:    string
  onChange: (v: string) => void
}) {
  return (
    <div className="flex gap-0.5">
      {options.map((opt) => {
        const active = opt === value
        return (
          <button
            key={opt}
            type="button"
            onClick={() => onChange(opt)}
            className={cx(
              "rounded-sm border px-2 py-0.5 text-[11px] transition-colors",
              active
                ? "border-blue-500 bg-blue-500 text-white"
                : "border-gray-200 bg-transparent text-gray-500 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-400 dark:hover:bg-gray-800",
            )}
          >
            {opt}
          </button>
        )
      })}
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Variacao diaria — componentes da analise
// ───────────────────────────────────────────────────────────────────────────

const BRL = (n: number) =>
  n.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 2 })

const BRL_COMPACT = (n: number) => {
  const abs = Math.abs(n)
  if (abs >= 1_000_000) return `${n < 0 ? "−" : ""}R$ ${(abs / 1_000_000).toFixed(1)}M`
  if (abs >= 1_000)     return `${n < 0 ? "−" : ""}R$ ${(abs / 1_000).toFixed(1)}k`
  return BRL(n)
}

const PCT = (n: number) => `${(n * 100).toLocaleString("pt-BR", { maximumFractionDigits: 2 })}%`

function VariacaoHero({
  data,
  dataAnterior,
  plD1,
  plD0,
  plDelta,
  plDeltaPct,
}: {
  data:         string
  dataAnterior: string
  plD1:         number
  plD0:         number
  plDelta:      number
  plDeltaPct:   number
}) {
  const positive = plDelta >= 0
  const ArrowIcon = positive ? RiArrowUpLine : RiArrowDownLine
  const deltaColor = positive
    ? "text-emerald-600 dark:text-emerald-400"
    : "text-red-600 dark:text-red-400"

  const fmtData = (iso: string) => format(parseISO(iso), "dd/MM/yyyy", { locale: ptBR })

  return (
    <div className="grid grid-cols-1 gap-4 rounded border border-gray-200 bg-white p-5 shadow-xs dark:border-gray-800 dark:bg-gray-925 lg:grid-cols-[1fr_auto_1fr_auto_1fr]">
      {/* PL D-1 */}
      <div className="flex flex-col gap-1">
        <span className="text-[10px] font-semibold uppercase tracking-[0.05em] text-gray-500 dark:text-gray-400">
          PL Sub Jr · {fmtData(dataAnterior)}
        </span>
        <span className="text-2xl font-semibold leading-none tracking-tight tabular-nums text-gray-900 dark:text-gray-50">
          {BRL(plD1)}
        </span>
      </div>

      <div className="hidden items-center justify-center lg:flex">
        <span className="text-2xl text-gray-300 dark:text-gray-700">→</span>
      </div>

      {/* PL D0 */}
      <div className="flex flex-col gap-1">
        <span className="text-[10px] font-semibold uppercase tracking-[0.05em] text-gray-500 dark:text-gray-400">
          PL Sub Jr · {fmtData(data)}
        </span>
        <span className="text-2xl font-semibold leading-none tracking-tight tabular-nums text-gray-900 dark:text-gray-50">
          {BRL(plD0)}
        </span>
      </div>

      <div className="hidden items-center justify-center lg:flex">
        <span className="h-10 w-px bg-gray-200 dark:bg-gray-800" aria-hidden="true" />
      </div>

      {/* Variacao */}
      <div className="flex flex-col gap-1">
        <span className="text-[10px] font-semibold uppercase tracking-[0.05em] text-gray-500 dark:text-gray-400">
          Variacao
        </span>
        <div className="flex items-baseline gap-2">
          <span className={cx("inline-flex items-center gap-0.5 text-2xl font-semibold leading-none tabular-nums", deltaColor)}>
            <ArrowIcon className="size-5 shrink-0" aria-hidden="true" />
            {BRL(Math.abs(plDelta))}
          </span>
          <span className={cx("text-sm font-medium tabular-nums", deltaColor)}>
            ({PCT(Math.abs(plDeltaPct))})
          </span>
        </div>
      </div>
    </div>
  )
}

function PlCategoriaTable({ categorias }: { categorias: PlCategoria[] }) {
  return (
    <div className="rounded border border-gray-200 dark:border-gray-800 overflow-hidden">
      <div className="flex items-center gap-2 border-b border-gray-200 px-4 py-2.5 dark:border-gray-800">
        <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">PL por categoria</h3>
        <span className="rounded-full border border-gray-200 bg-gray-50 px-1.5 text-[11px] text-gray-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
          {categorias.length}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-200 text-left dark:border-gray-800">
              <th className="px-4 py-2 text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">Categoria</th>
              <th className="px-4 py-2 text-right text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">D-1</th>
              <th className="px-4 py-2 text-right text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">D0</th>
              <th className="px-4 py-2 text-right text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">Δ</th>
              <th className="px-4 py-2 text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">Fonte</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100 dark:divide-gray-800">
            {categorias.map((cat) => {
              const isPos = cat.delta > 0
              const isNeg = cat.delta < 0
              return (
                <tr key={cat.key} className="hover:bg-gray-50 dark:hover:bg-gray-900/40">
                  <td className="px-4 py-1.5 text-sm font-medium text-gray-900 dark:text-gray-50">{cat.label}</td>
                  <td className="px-4 py-1.5 text-right text-sm tabular-nums text-gray-700 dark:text-gray-300">{BRL(cat.d1)}</td>
                  <td className="px-4 py-1.5 text-right text-sm tabular-nums text-gray-700 dark:text-gray-300">{BRL(cat.d0)}</td>
                  <td className={cx(
                    "px-4 py-1.5 text-right text-sm font-medium tabular-nums",
                    isPos && "text-emerald-600 dark:text-emerald-400",
                    isNeg && "text-red-600 dark:text-red-400",
                    !isPos && !isNeg && "text-gray-400 dark:text-gray-600",
                  )}>
                    {cat.delta === 0 ? "—" : (cat.delta > 0 ? "+" : "") + BRL(cat.delta)}
                  </td>
                  <td className="px-4 py-1.5 font-mono text-[10px] text-gray-400 dark:text-gray-600">{cat.source}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function decomposicaoWaterfallOption(items: DecomposicaoItem[], total: number): EChartsOption {
  // Padrao waterfall: cada barra "stacked" sobre uma barra invisivel que representa
  // o acumulado anterior. Calculamos posicoes [acumulado_inicial, valor_da_barra]
  // pra cada item, e adicionamos uma barra final "Total" alinhada no zero.
  const labels: string[] = items.map((i) => i.label).concat(["Total"])
  const placeholders: number[] = []
  const values: number[] = []
  const colors: string[] = []
  let acc = 0
  for (const it of items) {
    if (it.valor >= 0) {
      placeholders.push(acc)
      values.push(it.valor)
    } else {
      placeholders.push(acc + it.valor)
      values.push(-it.valor)
    }
    acc += it.valor
    colors.push(
      it.sinal === "ganho"    ? "#10B981"
      : it.sinal === "prejuizo" ? "#EF4444"
      :                            "#9CA3AF",
    )
  }
  // Total — barra desde 0 ate o total
  placeholders.push(0)
  values.push(Math.abs(total))
  colors.push(total >= 0 ? "#3B82F6" : "#EF4444")

  return {
    grid: { top: 16, right: 16, bottom: 60, left: 64 },
    xAxis: {
      type: "category",
      data: labels,
      axisLabel: { interval: 0, rotate: 30, fontSize: 10 },
      axisTick: { show: false },
    },
    yAxis: {
      type: "value",
      axisLabel: { formatter: (v: number) => BRL_COMPACT(v) },
    },
    series: [
      {
        name: "_placeholder",
        type: "bar",
        stack: "wf",
        itemStyle: { color: "transparent" },
        emphasis: { itemStyle: { color: "transparent" } },
        data: placeholders,
        silent: true,
      },
      {
        name: "Variacao",
        type: "bar",
        stack: "wf",
        barMaxWidth: 28,
        data: values.map((v, i) => ({
          value: v,
          itemStyle: { color: colors[i], borderRadius: [3, 3, 0, 0] },
        })),
      },
    ],
    tooltip: {
      trigger: "axis",
      formatter: (params: unknown) => {
        const arr = params as { dataIndex: number; name: string }[]
        const idx = arr[0]?.dataIndex ?? 0
        const isTotal = idx === items.length
        const valor = isTotal ? total : items[idx].valor
        const label = isTotal ? "Total" : items[idx].label
        return `<b>${label}</b><br/>${BRL(valor)}`
      },
    },
  }
}

function DivergenciaPanel({
  divergencia,
  total,
  plDelta,
}: {
  divergencia: number
  total:       number
  plDelta:     number
}) {
  const tolerance = 1  // R$ 1 — abaixo disso considera reconciliado
  const ok = Math.abs(divergencia) < tolerance
  return (
    <div className={cx(
      "flex items-start gap-3 rounded border p-4",
      ok
        ? "border-emerald-200 bg-emerald-50/50 dark:border-emerald-900 dark:bg-emerald-950/20"
        : "border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/40",
    )}>
      <div className={cx(
        "mt-0.5 flex size-5 shrink-0 items-center justify-center rounded-full",
        ok ? "bg-emerald-500 text-white" : "bg-amber-500 text-white",
      )}>
        {ok
          ? <RiCheckLine className="size-3" aria-hidden="true" />
          : <RiAlertLine className="size-3" aria-hidden="true" />}
      </div>
      <div className="flex-1 text-sm">
        <p className="font-medium text-gray-900 dark:text-gray-50">
          {ok ? "Decomposicao reconciliada" : "Divergencia detectada"}
        </p>
        <p className="mt-1 text-xs text-gray-600 dark:text-gray-400">
          Σ decomposicao = <span className="font-mono tabular-nums">{BRL(total)}</span>
          {"  ·  "}
          Δ PL = <span className="font-mono tabular-nums">{BRL(plDelta)}</span>
          {"  ·  "}
          Diferenca = <span className={cx(
            "font-mono tabular-nums font-semibold",
            ok ? "text-emerald-600 dark:text-emerald-400" : "text-amber-700 dark:text-amber-400",
          )}>{BRL(divergencia)}</span>
        </p>
        {!ok && (
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-500">
            Indica que ha categoria(s) impactando o PL fora do escopo decomposto.
            Verifique tarifas, ajustes manuais ou ativos nao mapeados.
          </p>
        )}
      </div>
    </div>
  )
}

function ApropriacaoDcDrill({ data }: { data: ApropriacaoDc }) {
  const Row = ({ label, value, mono = true }: { label: string; value: number | string; mono?: boolean }) => (
    <div className="flex items-baseline justify-between gap-3 py-1">
      <span className="text-xs text-gray-600 dark:text-gray-400">{label}</span>
      <span className={cx(
        "text-sm tabular-nums text-gray-900 dark:text-gray-50",
        mono && "font-mono",
      )}>
        {typeof value === "number" ? BRL(value) : value}
      </span>
    </div>
  )

  const Block = ({ title, linha }: { title: string; linha: ApropriacaoDcLinha }) => (
    <div className="rounded border border-gray-200 p-4 dark:border-gray-800">
      <h4 className="mb-2 text-xs font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">{title}</h4>
      <Row label="Estoque D-1 (VP)" value={linha.estoque_d1} />
      <Row label="Aquisicoes" value={linha.aquisicoes} />
      <Row label="Liquidados" value={linha.liquidados} />
      <Row label="Estoque D0 (VP)" value={linha.estoque_d0} />
      <div className="mt-2 border-t border-gray-200 pt-2 dark:border-gray-800">
        <Row label="Apropriacao = G − (D + E + F)" value={linha.apropriacao} />
      </div>
    </div>
  )

  return (
    <div className="flex flex-col gap-4 p-6">
      <p className="text-xs text-gray-500 dark:text-gray-400">
        Origem: <span className="font-mono">wh_estoque_recebivel</span> + <span className="font-mono">wh_aquisicao_recebivel</span> + <span className="font-mono">wh_liquidacao_recebivel</span>
      </p>
      <Block title="A vencer" linha={data.a_vencer} />
      <Block title="Vencidos" linha={data.vencidos} />
      <div className="rounded border border-blue-200 bg-blue-50/50 p-4 dark:border-blue-900 dark:bg-blue-950/20">
        <Row label="Total apropriacao DC" value={data.total} />
      </div>
    </div>
  )
}

function CprDrill({ data }: { data: CprDetalhado }) {
  const List = ({ title, items }: { title: string; items: CprMovimentoItem[] }) => (
    <div className="rounded border border-gray-200 dark:border-gray-800">
      <div className="border-b border-gray-200 bg-gray-50 px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
        {title} · {items.length} item(s)
      </div>
      <ul className="divide-y divide-gray-100 dark:divide-gray-800">
        {items.length === 0 && (
          <li className="px-3 py-2 text-xs text-gray-400 dark:text-gray-600">—</li>
        )}
        {items.map((it, i) => (
          <li key={i} className="flex items-baseline justify-between gap-3 px-3 py-1.5">
            <span className="text-xs text-gray-700 dark:text-gray-300">{it.descricao}</span>
            <span className={cx(
              "font-mono text-xs tabular-nums",
              it.valor >= 0 ? "text-emerald-600 dark:text-emerald-400" : "text-red-600 dark:text-red-400",
            )}>
              {BRL(it.valor)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  )

  return (
    <div className="flex flex-col gap-4 p-6">
      <p className="text-xs text-gray-500 dark:text-gray-400">
        Origem: <span className="font-mono">wh_cpr_movimento</span> — segregacao receber/pagar pelo sinal de <span className="font-mono">valor</span>.
      </p>
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <List title="A receber D-1" items={data.receber_d1} />
        <List title="A receber D0"  items={data.receber_d0} />
        <List title="A pagar D-1"   items={data.pagar_d1} />
        <List title="A pagar D0"    items={data.pagar_d0} />
      </div>
      <div className="rounded border border-blue-200 bg-blue-50/50 p-4 dark:border-blue-900 dark:bg-blue-950/20">
        <div className="flex items-baseline justify-between gap-3 py-1">
          <span className="text-xs text-gray-600 dark:text-gray-400">Total D-1 (rec − pag)</span>
          <span className="font-mono text-sm tabular-nums">{BRL(data.total_d1)}</span>
        </div>
        <div className="flex items-baseline justify-between gap-3 py-1">
          <span className="text-xs text-gray-600 dark:text-gray-400">Total D0 (rec − pag)</span>
          <span className="font-mono text-sm tabular-nums">{BRL(data.total_d0)}</span>
        </div>
        <div className="mt-2 flex items-baseline justify-between gap-3 border-t border-blue-200 pt-2 dark:border-blue-900">
          <span className="text-xs font-medium text-gray-900 dark:text-gray-50">Δ Apropriacao despesas</span>
          <span className="font-mono text-sm font-semibold tabular-nums">{BRL(data.variacao)}</span>
        </div>
      </div>
    </div>
  )
}

type DrillTarget = "apropriacao_dc" | "cpr" | null

function VariacaoSectionEmpty({ title, message }: { title: string; message: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded border border-dashed border-gray-200 bg-white py-12 dark:border-gray-800 dark:bg-gray-925">
      <RiInformationLine className="size-5 text-gray-400" aria-hidden="true" />
      <p className="text-sm font-medium text-gray-700 dark:text-gray-300">{title}</p>
      <p className="text-xs text-gray-500 dark:text-gray-500">{message}</p>
    </div>
  )
}

function VariacaoDiariaSection({
  data,
  isLoading,
  isError,
  error,
  fundoSelected,
  onOpenDrill,
}: {
  data:           VariacaoDiariaResponse | undefined
  isLoading:      boolean
  isError:        boolean
  error:          Error | null
  fundoSelected:  boolean
  onOpenDrill:    (target: DrillTarget) => void
}) {
  const wfOption = React.useMemo(
    () => data
      ? decomposicaoWaterfallOption(data.decomposicao, data.decomposicao_total)
      : undefined,
    [data],
  )

  const Header = (
    <div className="flex items-center gap-2">
      <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">Variacao diaria da Cota</h2>
    </div>
  )

  if (!fundoSelected) {
    return (
      <div className="flex flex-col gap-3">
        {Header}
        <VariacaoSectionEmpty
          title="Selecione um fundo"
          message="Use o filtro 'Fundo' acima para escolher uma UA do tipo FIDC."
        />
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="flex flex-col gap-3">
        {Header}
        <VariacaoSectionEmpty title="Carregando variacao..." message="Consultando warehouse." />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="flex flex-col gap-3">
        {Header}
        <div className="rounded border border-red-200 bg-red-50 p-4 dark:border-red-900 dark:bg-red-950/30">
          <p className="text-sm font-medium text-red-900 dark:text-red-200">Falha ao carregar variacao</p>
          <p className="mt-1 font-mono text-xs text-red-700 dark:text-red-400">
            {error?.message ?? "Erro desconhecido"}
          </p>
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="flex flex-col gap-3">
        {Header}
        <VariacaoSectionEmpty title="Sem dados" message="Nenhuma variacao disponivel para esses parametros." />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      {Header}

      <VariacaoHero
        data={data.data}
        dataAnterior={data.data_anterior}
        plD1={data.pl_d1}
        plD0={data.pl_d0}
        plDelta={data.pl_delta}
        plDeltaPct={data.pl_delta_pct}
      />

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <PlCategoriaTable categorias={data.categorias} />

        <div className="flex flex-col gap-3">
          <EChartsCard
            title="Decomposicao da variacao"
            caption="Waterfall · clique em uma barra para drill-down"
            option={wfOption!}
            height={260}
            actions={
              <div className="flex gap-2 text-[11px]">
                <button type="button" onClick={() => onOpenDrill("apropriacao_dc")} className="text-blue-600 hover:underline dark:text-blue-400">
                  Apropriacao DC →
                </button>
                <button type="button" onClick={() => onOpenDrill("cpr")} className="text-blue-600 hover:underline dark:text-blue-400">
                  CPR →
                </button>
              </div>
            }
          />
          <DivergenciaPanel
            divergencia={data.divergencia}
            total={data.decomposicao_total}
            plDelta={data.pl_delta}
          />
        </div>
      </div>
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Visao geral
// ───────────────────────────────────────────────────────────────────────────

function VisaoGeralTab({
  variacao,
  variacaoLoading,
  variacaoError,
  variacaoErrorMsg,
  fundoSelected,
  onOpenDrill,
  rows,
  tableStatus,
  setTableStatus,
  tableCotista,
  setTableCotista,
  onRowClick,
}: {
  variacao:         VariacaoDiariaResponse | undefined
  variacaoLoading:  boolean
  variacaoError:    boolean
  variacaoErrorMsg: Error | null
  fundoSelected:    boolean
  onOpenDrill:      (target: DrillTarget) => void
  rows:             MovimentacaoRow[]
  tableStatus:      string
  setTableStatus:   (v: string) => void
  tableCotista:     string
  setTableCotista:  (v: string) => void
  onRowClick:       (row: MovimentacaoRow) => void
}) {
  const [plPeriod, setPlPeriod] = React.useState("12M")
  const [subPeriod, setSubPeriod] = React.useState("12M")

  return (
    <div className="flex flex-col gap-6">
      {/* Variacao diaria — analise principal (espelho da planilha) */}
      <VariacaoDiariaSection
        data={variacao}
        isLoading={variacaoLoading}
        isError={variacaoError}
        error={variacaoErrorMsg}
        fundoSelected={fundoSelected}
        onOpenDrill={onOpenDrill}
      />

      {/* Insights + charts evolutivos (12M) */}
      <InsightBar>
        {MOCK_INSIGHTS.map((ins, i) => (
          <Insight key={i} tone="violet" text={ins.text} />
        ))}
      </InsightBar>

      {/* Hero 2/3 + 1/3 */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <EChartsCard
          title="Evolucao do PL Cota Sub"
          caption="Patrimonio liquido subordinado · Bitfin"
          option={plCotaSubOption}
          height={160}
          className="lg:col-span-2"
          actions={
            <VizParam
              options={["12M", "6M", "3M", "1M"]}
              value={plPeriod}
              onChange={setPlPeriod}
            />
          }
        />
        <EChartsCard
          title="Distribuicao por classe"
          caption="Mezanino · Junior · participacao %"
          option={distribClasseOption}
          height={100}
          footer={
            <div className="flex items-end justify-between pt-2">
              <div>
                <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  Mezanino
                </div>
                <div className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                  68%
                </div>
              </div>
              <div>
                <div className="mb-0.5 text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                  Junior
                </div>
                <div className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                  32%
                </div>
              </div>
            </div>
          }
        />
      </div>

      {/* Grid 3 colunas */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <EChartsCard
          title="Subscricao vs Resgate"
          caption="Movimentacoes mensais (R$ mi)"
          option={subscRescOption}
          height={160}
          actions={
            <VizParam
              options={["12M", "6M", "3M"]}
              value={subPeriod}
              onChange={setSubPeriod}
            />
          }
        />
        <EChartsCard
          title="Rentabilidade Sub vs CDI"
          caption="Base 100 · mai/25"
          option={rentabSubOption}
          height={160}
        />
        <EChartsCard
          title="Top cotistas subordinados"
          caption="Top 5 + Outros · participacao %"
          option={topCotistasOption}
          height={160}
        />
      </div>

      {/* Tabela */}
      <div className="rounded border border-gray-200 dark:border-gray-800 overflow-hidden">
        <div className="flex flex-wrap items-center gap-2 border-b border-gray-200 px-4 py-2.5 dark:border-gray-800">
          <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
            Movimentacoes recentes
          </h3>
          <span className="rounded-full border border-gray-200 bg-gray-50 px-1.5 text-[11px] text-gray-500 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-400">
            {rows.length}
          </span>

          {/* Filtros inline da tabela (Status / Cotista) */}
          <div className="ml-2 flex items-center gap-1.5">
            <FilterChip
              label="Status"
              value={tableStatus}
              active={tableStatus !== "Todos"}
            >
              <div className="py-1">
                {TABLE_STATUS_OPTIONS.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setTableStatus(opt)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      tableStatus === opt
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{opt}</span>
                    {tableStatus === opt && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                  </button>
                ))}
              </div>
            </FilterChip>

            <FilterChip
              label="Cotista"
              value={tableCotista}
              active={tableCotista !== "Todos"}
            >
              <div className="py-1">
                {TABLE_COTISTA_OPTIONS.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setTableCotista(opt)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      tableCotista === opt
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{opt}</span>
                    {tableCotista === opt && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                  </button>
                ))}
              </div>
            </FilterChip>
          </div>

          <Button variant="ghost" className="ml-auto">
            <RiDownloadLine className="size-3.5" aria-hidden="true" />
            Exportar
          </Button>
        </div>
        <DataTable
          data={rows}
          columns={MOVIMENTACOES_COLUMNS}
          density="compact"
          showColumnManager={false}
          showDensityToggle={false}
          showExport={false}
          virtualize={false}
          onRowClick={onRowClick}
        />
      </div>
    </div>
  )
}

function PlaceholderTab({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16">
      <div className="size-10 rounded-full bg-gray-100 dark:bg-gray-800" aria-hidden="true" />
      <p className="text-sm font-medium text-gray-600 dark:text-gray-400">
        Visao &quot;{label}&quot;
      </p>
      <p className="text-xs text-gray-400 dark:text-gray-600">
        Adapte esta aba para o contexto analitico correspondente.
      </p>
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// DataTable columns
// ───────────────────────────────────────────────────────────────────────────

const col = createColumnHelper<MovimentacaoRow>()

const MOVIMENTACOES_COLUMNS: ColumnDef<MovimentacaoRow, unknown>[] = [
  col.accessor("id", {
    header: "ID",
    size:   150,
    cell:   (info) => <IdCell value={info.getValue<string>()} />,
  }) as ColumnDef<MovimentacaoRow, unknown>,
  col.accessor("cotista", {
    header: "Cotista",
    size:   180,
  }) as ColumnDef<MovimentacaoRow, unknown>,
  col.accessor("classe", {
    header: "Classe",
    size:   110,
    cell:   (info) => (
      <span className="text-sm text-gray-500 dark:text-gray-400">
        {info.getValue<string>()}
      </span>
    ),
  }) as ColumnDef<MovimentacaoRow, unknown>,
  col.accessor("tipo", {
    header: "Tipo",
    size:   110,
    cell:   (info) => {
      const tipo  = info.getValue<MovimentacaoTipo>()
      const isSub = tipo === "subscricao"
      return (
        <span className={cx(
          "inline-flex items-center rounded-sm px-1.5 py-0.5 text-[11px] font-medium",
          isSub
            ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
            : "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
        )}>
          {isSub ? "Subscricao" : "Resgate"}
        </span>
      )
    },
  }) as ColumnDef<MovimentacaoRow, unknown>,
  col.accessor("valor", {
    header: "Valor",
    size:   140,
    cell:   (info) => <CurrencyCell value={info.getValue<number>()} />,
  }) as ColumnDef<MovimentacaoRow, unknown>,
  col.accessor("data", {
    header: "Data",
    size:   110,
    cell:   (info) => <DateCell value={info.getValue<string>()} />,
  }) as ColumnDef<MovimentacaoRow, unknown>,
  col.accessor("status", {
    header: "Status",
    size:   140,
    cell:   (info) => <StatusCell value={info.getValue<StatusKey>()} />,
  }) as ColumnDef<MovimentacaoRow, unknown>,
]

// ───────────────────────────────────────────────────────────────────────────
// MockProvenanceFooter
// ───────────────────────────────────────────────────────────────────────────

function MockProvenanceFooter() {
  return (
    <div className="flex shrink-0 flex-wrap items-center gap-4 border-t border-gray-200 bg-gray-50 px-6 py-1.5 dark:border-gray-800 dark:bg-gray-900/40">
      {MOCK_PROVENANCE.map((s) => (
        <div key={s.label} className="flex items-center gap-1.5">
          <span
            aria-hidden="true"
            className={cx(
              "size-1.5 rounded-full",
              s.stale ? "bg-amber-500" : "bg-emerald-500",
            )}
          />
          <span className="text-[11px] text-gray-600 dark:text-gray-400">
            <span className="font-medium text-gray-900 dark:text-gray-50">{s.label}</span>
            {" · "}
            {s.updated}
          </span>
          <span className="text-[10px] text-gray-400 dark:text-gray-600">
            SLA {s.sla}
          </span>
        </div>
      ))}
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Page
// ───────────────────────────────────────────────────────────────────────────

export default function CotaSubPage() {
  const [search, setSearch] = React.useState("")
  // Dia: tab "Visao geral" analisa um unico dia por vez. Default = hoje.
  const today = React.useMemo(() => new Date(), [])
  const [day, setDay] = React.useState<Date>(today)
  // Fundo: opcoes vem de Cadastros · UAs do tipo FIDC. "Todos" e a opcao implicita default.
  const fundosQuery = useUAs({ tipo: "fidc", ativa: true })
  const fundoOptions = React.useMemo(
    () => ["Todos", ...(fundosQuery.data?.map((ua) => ua.nome) ?? [])],
    [fundosQuery.data],
  )
  const [fundo,  setFundo]  = React.useState<string>("Todos")
  const [classe, setClasse] = React.useState<ClasseOption>("Todas")

  // Filtros dinamicos (adicionados via "Mais filtros") — array imutavel no
  // sentido do user: cada chip vira RemovableChip + dropdown FilterChip.
  const [dynamicFilters, setDynamicFilters] = React.useState<DynamicFilter[]>([])

  // Filtros inline da DataTable (escopo: tabela apenas, nao charts)
  const [tableStatus,  setTableStatus]  = React.useState<string>("Todos")
  const [tableCotista, setTableCotista] = React.useState<string>("Todos")

  const [activeTab, setActiveTab] = React.useState<TabKey>("visao-geral")

  // Atalhos Cmd/Ctrl + 1..3 para tabs (regra L3 do CLAUDE.md §11.6).
  React.useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && ["1", "2", "3"].includes(e.key)) {
        const idx = Number(e.key) - 1
        if (TABS[idx]) {
          e.preventDefault()
          setActiveTab(TABS[idx].key)
        }
      }
    }
    window.addEventListener("keydown", handleKey)
    return () => window.removeEventListener("keydown", handleKey)
  }, [])

  const ai = useAIPanel()

  const [selected, setSelected] = React.useState<MovimentacaoRow | null>(null)

  // Drill-down de Variacao diaria — abre Apropriacao DC ou CPR detalhado.
  const [drillTarget, setDrillTarget] = React.useState<DrillTarget>(null)

  // Lookup do UUID da UA selecionada (para o endpoint backend que exige fundo_id).
  const fundoId = React.useMemo(() => {
    if (fundo === "Todos") return null
    return fundosQuery.data?.find((ua) => ua.nome === fundo)?.id ?? null
  }, [fundo, fundosQuery.data])

  const dayIso = React.useMemo(() => format(day, "yyyy-MM-dd"), [day])
  const variacaoQuery = useVariacaoDiaria(fundoId, dayIso)
  const variacaoData = variacaoQuery.data as VariacaoDiariaResponse | undefined
  // Pagina requer fundo selecionado. Sem fundo, Z4 entra em EmptyState.
  const fundoSelecionado = fundoId !== null

  const aiContext = React.useMemo(
    () => ({
      page: "Controladoria · Cota Sub",
      period: format(day, "dd/MM/yyyy"),
      filters: [
        fundo  !== "Todos" && `Fundo: ${fundo}`,
        classe !== "Todas" && `Classe: ${classe}`,
        ...dynamicFilters.map((f) => `${f.key}: ${f.value}`),
        search             && `Busca: ${search}`,
      ].filter(Boolean).join(", ") || "Nenhum",
    }),
    [day, fundo, classe, dynamicFilters, search],
  )

  const handleShare = React.useCallback(() => {
    void navigator.clipboard?.writeText(window.location.href)
  }, [])

  const handleExport = React.useCallback(() => {
    // Stub — wire to real export endpoint (CSV/XLSX da pagina inteira).
    // eslint-disable-next-line no-console
    console.log("export pagina cota-sub", { day, fundo, classe, dynamicFilters })
  }, [day, fundo, classe, dynamicFilters])

  // Linhas filtradas da DataTable (escopo: filtros inline da tabela)
  const filteredRows = React.useMemo(
    () => MOCK_MOVIMENTACOES.filter((r) => {
      if (tableStatus !== "Todos" && labelForStatus(r.status) !== tableStatus) return false
      if (tableCotista !== "Todos" && r.cotista !== tableCotista) return false
      if (search && !r.cotista.toLowerCase().includes(search.toLowerCase()) && !r.id.toLowerCase().includes(search.toLowerCase())) return false
      return true
    }),
    [tableStatus, tableCotista, search],
  )

  // Adicionar / remover filtro dinamico
  const addDynamicFilter = React.useCallback((key: DynamicFilterKey) => {
    setDynamicFilters((curr) => {
      if (curr.some((f) => f.key === key)) return curr
      const opts = DYNAMIC_FILTER_OPTIONS[key]
      return [...curr, { key, value: opts[0] }]
    })
  }, [])
  const removeDynamicFilter = React.useCallback((key: DynamicFilterKey) => {
    setDynamicFilters((curr) => curr.filter((f) => f.key !== key))
  }, [])
  const setDynamicFilterValue = React.useCallback((key: DynamicFilterKey, value: string) => {
    setDynamicFilters((curr) => curr.map((f) => f.key === key ? { ...f, value } : f))
  }, [])

  const usedDynamicKeys = dynamicFilters.map((f) => f.key)
  const availableDynamicKeys = (Object.keys(DYNAMIC_FILTER_OPTIONS) as DynamicFilterKey[])
    .filter((k) => !usedDynamicKeys.includes(k))

  // Saved views — params atuais + handler
  const currentViewParams = React.useMemo<Record<string, string>>(() => ({
    day:     format(day, "yyyy-MM-dd"),
    fundo,
    classe,
    search,
    ...Object.fromEntries(dynamicFilters.map((f) => [f.key, f.value])),
  }), [day, fundo, classe, search, dynamicFilters])

  const handleApplyView = React.useCallback((view: { params: Record<string, string> }) => {
    const p = view.params
    if (p.fundo)  setFundo(p.fundo)
    if (p.classe) setClasse(p.classe as ClasseOption)
    if (p.search) setSearch(p.search)
    if (p.day) {
      const d = new Date(p.day)
      if (!isNaN(d.getTime())) setDay(d)
    }
    // restaura filtros dinamicos
    const restored: DynamicFilter[] = []
    for (const k of Object.keys(DYNAMIC_FILTER_OPTIONS) as DynamicFilterKey[]) {
      if (p[k]) restored.push({ key: k, value: p[k] as string })
    }
    setDynamicFilters(restored)
  }, [])

  return (
    <div className="flex h-[calc(100vh-4rem)] overflow-hidden bg-gray-50 dark:bg-gray-950">
      {/* Coluna principal */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">

        {/* Z1 — PageHeader */}
        <div className="shrink-0 px-6 pt-5 pb-3">
          <PageHeader
            title="Cota Sub"
            info="Analise da cota subordinada do FIDC: PL, rentabilidade vs CDI, distribuicao por cotista subordinado e fluxo de subscricao/resgate."
            actions={
              <>
                <Button variant="secondary" onClick={handleExport}>
                  <RiDownloadLine className="size-4 shrink-0" aria-hidden="true" />
                  Exportar
                </Button>
                <Button variant="secondary" onClick={handleShare}>
                  <RiShareLine className="size-4 shrink-0" aria-hidden="true" />
                  Compartilhar
                </Button>
                <AIToggleButton open={ai.open} onClick={ai.toggle} />
              </>
            }
          />
        </div>

        {/* Z2 — TabNavigation L3 */}
        <div className="shrink-0 px-6">
          <TabNavigation>
            {TABS.map((t, i) => (
              <TabNavigationLink
                key={t.key}
                href="#"
                active={activeTab === t.key}
                onClick={(e) => {
                  e.preventDefault()
                  setActiveTab(t.key)
                }}
                title={`Cmd/Ctrl + ${i + 1}`}
              >
                {t.label}
              </TabNavigationLink>
            ))}
          </TabNavigation>
        </div>

        {/* Z3 — FilterBar sticky */}
        <div className="shrink-0 px-6">
          <FilterBar
            extraActions={
              <SavedViewsDropdown
                currentParams={currentViewParams}
                onApplyView={handleApplyView}
              />
            }
          >
            <FilterSearch
              placeholder="Buscar cotistas..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onClear={() => setSearch("")}
            />

            <FilterChip
              label="Dia"
              value={isSameDay(day, today) ? "Hoje" : format(day, "dd/MM/yyyy")}
              active={!isSameDay(day, today)}
              icon={RiCalendarLine}
            >
              <Calendar
                mode="single"
                selected={day}
                onSelect={(d) => d && setDay(d)}
                locale={ptBR}
                disabled={{ after: today }}
                initialFocus
              />
            </FilterChip>

            <FilterChip
              label="Fundo"
              value={fundo}
              active={fundo !== "Todos"}
            >
              <div className="py-1">
                {fundosQuery.isLoading && (
                  <div className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400">
                    Carregando UAs...
                  </div>
                )}
                {fundosQuery.isError && (
                  <div className="px-3 py-1.5 text-xs text-red-600 dark:text-red-400">
                    Falha ao carregar UAs
                  </div>
                )}
                {!fundosQuery.isLoading && !fundosQuery.isError && fundoOptions.length === 1 && (
                  <div className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400">
                    Nenhuma UA do tipo FIDC cadastrada
                  </div>
                )}
                {fundoOptions.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setFundo(opt)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      fundo === opt
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{opt}</span>
                    {fundo === opt && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                  </button>
                ))}
              </div>
            </FilterChip>

            <FilterChip
              label="Classe"
              value={classe}
              active={classe !== "Todas"}
            >
              <div className="py-1">
                {CLASSE_OPTIONS.map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    onClick={() => setClasse(opt)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      classe === opt
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left">{opt}</span>
                    {classe === opt && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                  </button>
                ))}
              </div>
            </FilterChip>

            {/* Filtros dinamicos — adicionados via "Mais filtros" */}
            {dynamicFilters.map((f) => (
              <FilterChip
                key={f.key}
                label={f.key}
                value={f.value}
                active={f.value !== DYNAMIC_FILTER_OPTIONS[f.key][0]}
              >
                <div className="py-1">
                  {DYNAMIC_FILTER_OPTIONS[f.key].map((opt) => (
                    <button
                      key={opt}
                      type="button"
                      onClick={() => setDynamicFilterValue(f.key, opt)}
                      className={cx(
                        "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                        f.value === opt
                          ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                          : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                      )}
                    >
                      <span className="flex-1 text-left">{opt}</span>
                      {f.value === opt && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => removeDynamicFilter(f.key)}
                    className={cx(
                      "mt-1 flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      "text-red-600 hover:bg-red-50 dark:text-red-400 dark:hover:bg-red-500/10",
                    )}
                  >
                    Remover filtro
                  </button>
                </div>
              </FilterChip>
            ))}

            {search && (
              <RemovableChip
                label="Busca"
                value={search}
                onRemove={() => setSearch("")}
              />
            )}

            <AddFilterMenu
              available={availableDynamicKeys}
              onAdd={addDynamicFilter}
            />
          </FilterBar>
        </div>

        {/* Z4 — Conteudo da aba */}
        <div className="flex-1 overflow-y-auto px-6 py-4">
          {!fundoSelecionado ? (
            <EmptyState
              icon={RiFundsLine}
              title="Selecione um fundo para comecar"
              description='A pagina Cota Sub analisa um FIDC por vez. Escolha o fundo no filtro "Fundo" acima para carregar PL, rentabilidade, decomposicao da variacao diaria e movimentacoes.'
              className="mt-4"
            />
          ) : (
            <div className="flex flex-col gap-4">
              <KpiStrip className="grid-cols-2 min-[720px]:grid-cols-3 lg:grid-cols-5 xl:grid-cols-5">
                <KpiCard
                  label="PL da Cota Sub"
                  deltaSub="vs mes anterior"
                  value="R$ 18,7M"
                  delta={{ value: 1.8, suffix: "%" }}
                  sparkData={SPARK_PL_SUB}
                  sparkColor="#059669"
                  source="Bitfin"
                />
                <KpiCard
                  label="Subordinacao efetiva"
                  deltaSub="vs mes anterior"
                  value="15,0%"
                  delta={{ value: 0.3, suffix: "pp" }}
                  sparkData={SPARK_SUBORD}
                  sparkColor="#3B82F6"
                />
                <KpiCard
                  label="Rentab. Sub vs CDI"
                  deltaSub="vs benchmark"
                  value="118,2%"
                  delta={{ value: 4.1, suffix: "pp" }}
                  sparkData={SPARK_RENT_SUB}
                  sparkColor="#3B82F6"
                />
                <KpiCard
                  label="Cotistas subordinados"
                  deltaSub="vs mes anterior"
                  value="12"
                  delta={{ value: 1, suffix: "" }}
                  sparkData={SPARK_COTISTAS}
                  sparkColor="#6B7280"
                />
                <KpiCard
                  label="Resgates"
                  deltaSub="vs semana anterior"
                  value="3"
                  currentValue={3}
                  delta={{ value: 1, suffix: "", direction: "up", good: false }}
                  alertThreshold={{ value: 2, severity: "warn" }}
                  sparkData={SPARK_RESGATES}
                  sparkColor="#F59E0B"
                  intensity={{ tone: "neg", level: "mid" }}
                />
              </KpiStrip>

              {activeTab === "visao-geral" && (
                <VisaoGeralTab
                  variacao={variacaoData}
                  variacaoLoading={variacaoQuery.isLoading}
                  variacaoError={variacaoQuery.isError}
                  variacaoErrorMsg={variacaoQuery.error as Error | null}
                  fundoSelected
                  onOpenDrill={setDrillTarget}
                  rows={filteredRows}
                  tableStatus={tableStatus}
                  setTableStatus={setTableStatus}
                  tableCotista={tableCotista}
                  setTableCotista={setTableCotista}
                  onRowClick={setSelected}
                />
              )}
              {activeTab === "evolucao" && <PlaceholderTab label="Evolucao" />}
              {activeTab === "cotistas" && <PlaceholderTab label="Cotistas" />}
            </div>
          )}
        </div>

        {/* Z5 — ProvenanceFooter (mock) */}
        <MockProvenanceFooter />
      </div>

      {/* AI Panel */}
      <AIPanel
        open={ai.open}
        onClose={() => ai.setOpen(false)}
        context={aiContext}
        insights={MOCK_INSIGHTS}
      />

      {/* DrillDown */}
      <DrillDownSheet
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={selected?.id ?? "Movimentacao"}
      >
        {selected && (
          <>
            <DrillDownSheet.Header
              breadcrumb={["Cota Sub", selected.id]}
              statusSlot={
                <span className={cx(
                  "inline-flex items-center rounded-sm px-1.5 py-0.5 text-[11px] font-medium",
                  selected.tipo === "subscricao"
                    ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
                    : "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
                )}>
                  {selected.tipo === "subscricao" ? "Subscricao" : "Resgate"}
                </span>
              }
            />
            <DrillDownSheet.Hero
              id={selected.id}
              title={selected.cotista}
              value={selected.valor}
              delta={{ value: selected.tipo === "subscricao" ? 1.8 : -0.6, label: "vs ultima movimentacao" }}
            />
            <DrillDownSheet.Tabs
              tabs={[
                {
                  value:   "geral",
                  label:   "Visao geral",
                  content: (
                    <>
                      <DrillDownSheet.PropertyList
                        items={[
                          { label: "Cotista",      value: selected.cotista },
                          { label: "Classe",       value: selected.classe },
                          { label: "Tipo",         value: selected.tipo === "subscricao" ? "Subscricao" : "Resgate" },
                          { label: "Valor",        value: selected.valor, type: "currency" },
                          { label: "Data",         value: selected.data, type: "date" },
                          { label: "Status",       value: STATUS_LABEL[selected.status] },
                          { label: "Origem",       value: "QiTech" },
                          { label: "Liquidacao",   value: selected.status === "liquidado" ? "D+0" : "D+1 (estimada)" },
                        ]}
                      />
                      <div className="mt-6">
                        <DrillDownSheet.SectionLabel>Linha do tempo</DrillDownSheet.SectionLabel>
                        <DrillDownSheet.Timeline
                          events={buildTimeline(selected)}
                        />
                      </div>
                    </>
                  ),
                },
                { value: "historico",  label: "Historico",   content: <PlaceholderSheetTab label="Historico" /> },
                { value: "documentos", label: "Documentos",  content: <PlaceholderSheetTab label="Documentos" /> },
                { value: "atividade",  label: "Atividade",   content: <PlaceholderSheetTab label="Atividade" /> },
              ]}
              defaultValue="geral"
            />
            <DrillDownSheet.Footer>
              <Button variant="secondary">Exportar PDF</Button>
              <Button variant="secondary">Ver historico</Button>
              <div className="flex-1" />
              <Button variant="primary">Registrar evento</Button>
            </DrillDownSheet.Footer>
          </>
        )}
      </DrillDownSheet>

      {/* DrillDown da Variacao diaria (Apropriacao DC / CPR) */}
      <DrillDownSheet
        open={drillTarget !== null}
        onClose={() => setDrillTarget(null)}
        title={
          drillTarget === "apropriacao_dc" ? "Apropriacao de DC" :
          drillTarget === "cpr"            ? "CPR detalhado"      : ""
        }
      >
        {drillTarget === "apropriacao_dc" && variacaoData && <ApropriacaoDcDrill data={variacaoData.apropriacao_dc} />}
        {drillTarget === "cpr"            && variacaoData && <CprDrill            data={variacaoData.cpr_detalhado} />}
      </DrillDownSheet>
    </div>
  )
}

function PlaceholderSheetTab({ label }: { label: string }) {
  return (
    <div className="flex h-full items-center justify-center py-10 text-sm text-gray-500 dark:text-gray-400">
      Em desenvolvimento — aba &quot;{label}&quot;
    </div>
  )
}

function buildTimeline(row: MovimentacaoRow): TimelineEventDef[] {
  const baseDate = format(new Date(row.data), "dd/MM/yyyy")
  const events: TimelineEventDef[] = [
    { type: "cedida",    date: baseDate, actor: "Front-office",  description: `${row.tipo === "subscricao" ? "Subscricao" : "Resgate"} solicitada pelo cotista` },
    { type: "lastreada", date: baseDate, actor: "Back-office",   description: "Pedido validado e enviado a administradora" },
  ]
  if (row.status === "liquidado") {
    events.push({ type: "liquidada", date: baseDate, actor: "QiTech", description: "Liquidacao efetivada", current: true })
  } else if (row.status === "atrasado-30" || row.status === "atrasado-60") {
    events.push({ type: "atrasada", date: baseDate, actor: "Sistema", description: "Aguardando confirmacao do cotista", current: true })
  } else {
    events.push({ type: "a-vencer", date: "—", actor: "Sistema", description: "Aguardando liquidacao", current: true })
  }
  return events
}
