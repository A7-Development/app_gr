import type { Ficha } from "./types"

//
// 5 fundos sinteticos. O primeiro e o ARTICO MIDDLE CORPORATE (fonte XML real).
// Valores foram arredondados e os outros 4 derivados a partir dele com variacoes
// coerentes, para o comparativo renderizar algo plausivel ao analista.
//

const meses24 = (() => {
  const arr: string[] = []
  const now = new Date(2026, 2, 1) // mar/2026 competencia de referencia
  for (let i = 23; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1)
    arr.push(
      `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`,
    )
  }
  return arr
})()

//
// Helper: curva suavemente crescente com ruido, ancorada no valor final.
//
function serieCrescente(final: number, pontos = 24, volatilidade = 0.06) {
  const base = final * 0.82
  const ramp = (final - base) / (pontos - 1)
  return Array.from({ length: pontos }, (_, i) => {
    const ruido = 1 + (Math.sin(i * 1.7) * volatilidade)
    return Math.round((base + ramp * i) * ruido)
  })
}

//
// Ficha ARTICO MIDDLE CORPORATE — baseada no XML real
//
const ARTICO: Ficha = {
  identidade: {
    cnpj_fundo: "26208328000191",
    cnpj_classe: "26208328000191",
    denominacao_social: "ARTICO MIDDLE CORPORATE FIDC",
    administrador: "BRL Trust DTVM",
    classe_anbima: "FIDC Fomento Mercantil",
    condominio: "fechado",
    exclusivo: false,
    monoclasse: false,
    prazo_min_resgate_dias: null,
    prazo_conversao_dias: 180,
    competencia: "2026-03",
  },
  escala: {
    pl: 351_644_188,
    pl_medio_3m: 315_213_309,
    colchao_subordinacao_pct: 24.8,
    duration_dias: 148,
    nro_cotistas: 31,
    pct_dc_pl: 98.2,
    valor_total_dc: 345_314_800,
  },
  pl_subclasses: [
    { subclasse: "Senior", qtd_cotas: 264_298, vl_cota: 1_000.45, pl: 264_418_908, pct_pl: 75.2 },
    { subclasse: "Mezanino", qtd_cotas: 52_310, vl_cota: 1_004.22, pl: 52_530_901, pct_pl: 14.9 },
    { subclasse: "Subordinada", qtd_cotas: 34_694, vl_cota: 999.10, pl: 34_663_379, pct_pl: 9.9 },
  ],
  qualidade: {
    pct_inad_total: 4.9,
    pct_inad_90d: 2.7,
    pct_inad_360d: 0.8,
    pct_cobertura_pdd: 97.4,
    percentil_inad_total: 72,
    percentil_cobertura: 81,
    aging_a_vencer: [
      { faixa: "0-30d", valor: 68_200_000 },
      { faixa: "31-60d", valor: 61_100_000 },
      { faixa: "61-90d", valor: 48_400_000 },
      { faixa: "91-120d", valor: 40_500_000 },
      { faixa: "121-150d", valor: 35_900_000 },
      { faixa: "151-180d", valor: 28_300_000 },
      { faixa: "181-360d", valor: 41_200_000 },
      { faixa: "361-720d", valor: 14_700_000 },
      { faixa: "721-1080d", valor: 4_800_000 },
      { faixa: "+1080d", valor: 2_200_000 },
    ],
    aging_inadimplente: [
      { faixa: "0-30d", valor: 3_850_000 },
      { faixa: "31-60d", valor: 3_220_000 },
      { faixa: "61-90d", valor: 2_980_000 },
      { faixa: "91-120d", valor: 2_110_000 },
      { faixa: "121-150d", valor: 1_730_000 },
      { faixa: "151-180d", valor: 1_480_000 },
      { faixa: "181-360d", valor: 1_120_000 },
      { faixa: "361-720d", valor: 540_000 },
      { faixa: "721-1080d", valor: 290_000 },
      { faixa: "+1080d", valor: 180_000 },
    ],
    pdd_provisao: 16_490_000,
    scr_devedores: [
      { rating: "AA", pct_devedores: 62.1, pct_operacoes: 64.3 },
      { rating: "A", pct_devedores: 18.4, pct_operacoes: 17.9 },
      { rating: "B", pct_devedores: 8.6, pct_operacoes: 8.1 },
      { rating: "C", pct_devedores: 4.1, pct_operacoes: 3.7 },
      { rating: "D", pct_devedores: 2.8, pct_operacoes: 2.5 },
      { rating: "E", pct_devedores: 1.4, pct_operacoes: 1.3 },
      { rating: "F", pct_devedores: 1.0, pct_operacoes: 0.9 },
      { rating: "G", pct_devedores: 0.8, pct_operacoes: 0.7 },
      { rating: "H", pct_devedores: 0.8, pct_operacoes: 0.6 },
    ],
    evolucao: meses24.map((p, i) => ({
      periodo: p,
      pct_inad_total: +(5.4 + Math.sin(i * 0.4) * 0.6 - i * 0.02).toFixed(2),
      pct_inad_90d: +(3.2 + Math.sin(i * 0.5) * 0.3 - i * 0.01).toFixed(2),
      pct_inad_360d: +(1.1 + Math.cos(i * 0.3) * 0.1).toFixed(2),
      pct_cobertura: +(94 + Math.sin(i * 0.6) * 3).toFixed(1),
    })),
  },
  ativo: [
    { categoria: "DC com risco cedente", valor: 289_490_000, pct: 82.3 },
    { categoria: "DC sem risco cedente", valor: 38_100_000, pct: 10.8 },
    { categoria: "Disponibilidades", valor: 12_040_000, pct: 3.4 },
    { categoria: "Titulos Publicos Federais", valor: 6_800_000, pct: 1.9 },
    { categoria: "CDB", valor: 3_200_000, pct: 0.9 },
    { categoria: "Operacoes Compromissadas", valor: 1_800_000, pct: 0.5 },
    { categoria: "Cotas de FIDC", valor: 150_000, pct: 0.1 },
    { categoria: "Outros Renda Fixa", valor: 80_000, pct: 0.1 },
  ],
  segmento: [
    { setor: "Comercial", valor: 196_890_000, pct: 68.0, subsetores: [
      { nome: "Atacadista", valor: 112_000_000, pct: 38.7 },
      { nome: "Varejo", valor: 64_300_000, pct: 22.2 },
      { nome: "Leasing mercantil", valor: 20_590_000, pct: 7.1 },
    ]},
    { setor: "Industrial", valor: 49_230_000, pct: 17.0 },
    { setor: "Servicos", valor: 28_980_000, pct: 10.0, subsetores: [
      { nome: "Saude", valor: 14_500_000, pct: 5.0 },
      { nome: "Educacao", valor: 8_700_000, pct: 3.0 },
      { nome: "Entretenimento", valor: 5_780_000, pct: 2.0 },
    ]},
    { setor: "Factoring (fomento)", valor: 8_700_000, pct: 3.0 },
    { setor: "Agro", valor: 4_340_000, pct: 1.5 },
    { setor: "Financeiro", valor: 870_000, pct: 0.3 },
    { setor: "Setor publico", valor: 290_000, pct: 0.1 },
    { setor: "Judicial", valor: 190_000, pct: 0.1 },
  ],
  cedentes: [
    { cnpj_mascarado: "12.***.***/0001-10", denominacao: "Cedente Alfa S.A.", valor_cedido: 31_200_000, pct: 10.8 },
    { cnpj_mascarado: "34.***.***/0001-20", denominacao: "Cedente Beta Industria", valor_cedido: 28_800_000, pct: 9.9 },
    { cnpj_mascarado: "56.***.***/0001-30", denominacao: "Cedente Gamma Comercial", valor_cedido: 24_100_000, pct: 8.3 },
    { cnpj_mascarado: "78.***.***/0001-40", denominacao: "Cedente Delta", valor_cedido: 19_800_000, pct: 6.8 },
    { cnpj_mascarado: "90.***.***/0001-50", denominacao: "Cedente Epsilon", valor_cedido: 17_200_000, pct: 5.9 },
    { cnpj_mascarado: "11.***.***/0001-60", denominacao: "Cedente Zeta", valor_cedido: 14_900_000, pct: 5.1 },
    { cnpj_mascarado: "22.***.***/0001-70", denominacao: "Cedente Eta", valor_cedido: 12_300_000, pct: 4.2 },
    { cnpj_mascarado: "33.***.***/0001-80", denominacao: "Cedente Theta", valor_cedido: 10_800_000, pct: 3.7 },
    { cnpj_mascarado: "44.***.***/0001-90", denominacao: "Cedente Iota", valor_cedido: 9_200_000, pct: 3.2 },
  ],
  passivo: {
    curto_prazo: 4_820_000,
    longo_prazo: 0,
    derivativos: [
      { tipo: "Swap CDI passivo", valor: 0 },
      { tipo: "Futuro DI", valor: 0 },
      { tipo: "Opcoes", valor: 0 },
      { tipo: "NDF", valor: 0 },
    ],
    alavancagem_pct: 1.4,
  },
  taxas: {
    taxa_media_ponderada_dc_com_risco: 2.41,
    taxa_media_ponderada_dc_sem_risco: 1.28,
    por_tipo: [
      { tipo_ativo: "DC com risco", taxa_min: 1.4, taxa_media: 2.41, taxa_max: 3.8 },
      { tipo_ativo: "DC sem risco", taxa_min: 0.9, taxa_media: 1.28, taxa_max: 1.7 },
      { tipo_ativo: "Titulos publicos", taxa_min: 0.85, taxa_media: 0.92, taxa_max: 0.98 },
      { tipo_ativo: "CDB", taxa_min: 1.1, taxa_media: 1.18, taxa_max: 1.25 },
      { tipo_ativo: "Outros RF", taxa_min: 0.95, taxa_media: 1.05, taxa_max: 1.2 },
    ],
    evolucao: meses24.map((p, i) => ({
      periodo: p,
      taxa_dc_com: +(2.3 + Math.sin(i * 0.5) * 0.15 + i * 0.003).toFixed(2),
      taxa_dc_sem: +(1.2 + Math.sin(i * 0.4) * 0.08 + i * 0.002).toFixed(2),
    })),
  },
  cotistas: {
    total: 31,
    por_subclasse: [
      { subclasse: "Senior", qtd: 22 },
      { subclasse: "Mezanino", qtd: 5 },
      { subclasse: "Subordinada", qtd: 4 },
    ],
    por_tipo_investidor: [
      { tipo: "Fundos de investimento", senior: 12, subord: 2 },
      { tipo: "Pessoa Juridica nao-financeira", senior: 5, subord: 3 },
      { tipo: "Banco multiplo / comercial", senior: 3, subord: 0 },
      { tipo: "Pessoa Fisica (qualificado)", senior: 2, subord: 4 },
      { tipo: "RPPS", senior: 0, subord: 0 },
      { tipo: "Clubes de investimento", senior: 0, subord: 0 },
    ],
  },
  regularidade_cedido_com_divida: 840_000,
  garantias_pct_dc_com_garantia: 12.4,
  garantias_valor_total: 35_900_000,
  evolucao_pl: (() => {
    const vals = serieCrescente(351_644_188)
    return meses24.map((p, i) => ({ periodo: p, pl: vals[i] }))
  })(),
  evolucao_dc: (() => {
    const vals = serieCrescente(345_314_800)
    return meses24.map((p, i) => ({ periodo: p, dc: vals[i] }))
  })(),
  evolucao_setores: meses24.map((p, i) => ({
    periodo: p,
    Comercial: 196_890_000 * (0.85 + i * 0.008),
    Industrial: 49_230_000 * (0.9 + i * 0.004),
    Servicos: 28_980_000 * (0.88 + i * 0.005),
    "Factoring": 8_700_000 * (0.95 + i * 0.002),
    Agro: 4_340_000,
    Outros: 1_350_000,
  })),
}

//
// Fundo 2 — ZENIT CREDITOS DIVERSIFICADOS (grande, multicedente, concentracao moderada)
//
const ZENIT: Ficha = {
  ...ARTICO,
  identidade: {
    cnpj_fundo: "18739245000178",
    cnpj_classe: "18739245000178",
    denominacao_social: "ZENIT CREDITOS DIVERSIFICADOS FIDC",
    administrador: "Oliveira Trust DTVM",
    classe_anbima: "FIDC Fomento Mercantil",
    condominio: "fechado",
    exclusivo: false,
    monoclasse: false,
    prazo_min_resgate_dias: null,
    prazo_conversao_dias: 120,
    competencia: "2026-03",
  },
  escala: {
    pl: 612_480_000,
    pl_medio_3m: 598_100_000,
    colchao_subordinacao_pct: 18.2,
    duration_dias: 102,
    nro_cotistas: 48,
    pct_dc_pl: 96.8,
    valor_total_dc: 592_880_000,
  },
  pl_subclasses: [
    { subclasse: "Senior", qtd_cotas: 501_000, vl_cota: 1_000.30, pl: 501_150_000, pct_pl: 81.8 },
    { subclasse: "Mezanino", qtd_cotas: 58_000, vl_cota: 1_002.50, pl: 58_145_000, pct_pl: 9.5 },
    { subclasse: "Subordinada", qtd_cotas: 53_000, vl_cota: 1_000.10, pl: 53_005_300, pct_pl: 8.7 },
  ],
  qualidade: {
    ...ARTICO.qualidade,
    pct_inad_total: 7.2,
    pct_inad_90d: 4.1,
    pct_inad_360d: 1.8,
    pct_cobertura_pdd: 85.3,
    percentil_inad_total: 48,
    percentil_cobertura: 62,
  },
  cedentes: ARTICO.cedentes.map((c, i) => ({
    ...c,
    pct: +(c.pct * 0.72).toFixed(1),
    valor_cedido: Math.round(c.valor_cedido * 1.8),
    denominacao: `Cedente Zenit ${String.fromCharCode(65 + i)}`,
  })),
  taxas: {
    ...ARTICO.taxas,
    taxa_media_ponderada_dc_com_risco: 2.18,
    taxa_media_ponderada_dc_sem_risco: 1.14,
  },
  evolucao_pl: (() => {
    const vals = serieCrescente(612_480_000)
    return meses24.map((p, i) => ({ periodo: p, pl: vals[i] }))
  })(),
}

//
// Fundo 3 — NOVA ORLA AGRO (agro + factoring, maior duration)
//
const NOVA_ORLA: Ficha = {
  ...ARTICO,
  identidade: {
    cnpj_fundo: "41308255000144",
    cnpj_classe: "41308255000144",
    denominacao_social: "NOVA ORLA AGRO FIDC",
    administrador: "Vortx DTVM",
    classe_anbima: "FIDC Agro",
    condominio: "fechado",
    exclusivo: false,
    monoclasse: false,
    prazo_min_resgate_dias: null,
    prazo_conversao_dias: 360,
    competencia: "2026-03",
  },
  escala: {
    pl: 189_210_000,
    pl_medio_3m: 181_450_000,
    colchao_subordinacao_pct: 31.5,
    duration_dias: 244,
    nro_cotistas: 14,
    pct_dc_pl: 94.2,
    valor_total_dc: 178_230_000,
  },
  pl_subclasses: [
    { subclasse: "Senior", qtd_cotas: 129_600, vl_cota: 1_001.20, pl: 129_756_000, pct_pl: 68.6 },
    { subclasse: "Mezanino", qtd_cotas: 28_200, vl_cota: 1_005.10, pl: 28_343_820, pct_pl: 15.0 },
    { subclasse: "Subordinada", qtd_cotas: 31_100, vl_cota: 1_000.10, pl: 31_110_000, pct_pl: 16.4 },
  ],
  qualidade: {
    ...ARTICO.qualidade,
    pct_inad_total: 3.2,
    pct_inad_90d: 1.4,
    pct_inad_360d: 0.3,
    pct_cobertura_pdd: 112.0,
    percentil_inad_total: 88,
    percentil_cobertura: 94,
  },
  taxas: {
    ...ARTICO.taxas,
    taxa_media_ponderada_dc_com_risco: 1.98,
    taxa_media_ponderada_dc_sem_risco: 1.05,
  },
  evolucao_pl: (() => {
    const vals = serieCrescente(189_210_000)
    return meses24.map((p, i) => ({ periodo: p, pl: vals[i] }))
  })(),
}

//
// Fundo 4 — CANAL 7 RECEBIVEIS (estressado — inad alta, cobertura baixa)
//
const CANAL7: Ficha = {
  ...ARTICO,
  identidade: {
    cnpj_fundo: "29004155000120",
    cnpj_classe: "29004155000120",
    denominacao_social: "CANAL 7 RECEBIVEIS FIDC",
    administrador: "Planner DTVM",
    classe_anbima: "FIDC Multisetorial",
    condominio: "fechado",
    exclusivo: false,
    monoclasse: false,
    prazo_min_resgate_dias: null,
    prazo_conversao_dias: 90,
    competencia: "2026-03",
  },
  escala: {
    pl: 94_820_000,
    pl_medio_3m: 101_410_000,
    colchao_subordinacao_pct: 14.1,
    duration_dias: 89,
    nro_cotistas: 9,
    pct_dc_pl: 102.5,
    valor_total_dc: 97_200_000,
  },
  pl_subclasses: [
    { subclasse: "Senior", qtd_cotas: 81_500, vl_cota: 1_000.15, pl: 81_512_200, pct_pl: 86.0 },
    { subclasse: "Mezanino", qtd_cotas: 9_300, vl_cota: 1_003.20, pl: 9_329_760, pct_pl: 9.8 },
    { subclasse: "Subordinada", qtd_cotas: 4_000, vl_cota: 999.40, pl: 3_997_600, pct_pl: 4.2 },
  ],
  qualidade: {
    ...ARTICO.qualidade,
    pct_inad_total: 11.4,
    pct_inad_90d: 7.8,
    pct_inad_360d: 3.1,
    pct_cobertura_pdd: 68.0,
    percentil_inad_total: 18,
    percentil_cobertura: 24,
  },
  taxas: {
    ...ARTICO.taxas,
    taxa_media_ponderada_dc_com_risco: 2.85,
    taxa_media_ponderada_dc_sem_risco: 1.42,
  },
  evolucao_pl: (() => {
    const vals = serieCrescente(94_820_000, 24, 0.12)
    return meses24.map((p, i) => ({ periodo: p, pl: vals[i] }))
  })(),
}

//
// Fundo 5 — POLO NORTE CORPORATE (conservador, monoclasse senior, cotistas institucionais)
//
const POLO_NORTE: Ficha = {
  ...ARTICO,
  identidade: {
    cnpj_fundo: "33872104000187",
    cnpj_classe: "33872104000187",
    denominacao_social: "POLO NORTE CORPORATE FIDC",
    administrador: "Intrag DTVM",
    classe_anbima: "FIDC Fomento Mercantil",
    condominio: "fechado",
    exclusivo: true,
    monoclasse: true,
    prazo_min_resgate_dias: 180,
    prazo_conversao_dias: 180,
    competencia: "2026-03",
  },
  escala: {
    pl: 428_950_000,
    pl_medio_3m: 422_110_000,
    colchao_subordinacao_pct: 22.0,
    duration_dias: 168,
    nro_cotistas: 5,
    pct_dc_pl: 95.0,
    valor_total_dc: 407_500_000,
  },
  pl_subclasses: [
    { subclasse: "Senior", qtd_cotas: 334_600, vl_cota: 1_000.80, pl: 334_867_680, pct_pl: 78.0 },
    { subclasse: "Mezanino", qtd_cotas: 42_900, vl_cota: 1_003.10, pl: 43_032_990, pct_pl: 10.0 },
    { subclasse: "Subordinada", qtd_cotas: 51_000, vl_cota: 1_000.20, pl: 51_010_200, pct_pl: 12.0 },
  ],
  qualidade: {
    ...ARTICO.qualidade,
    pct_inad_total: 3.8,
    pct_inad_90d: 2.0,
    pct_inad_360d: 0.5,
    pct_cobertura_pdd: 105.2,
    percentil_inad_total: 82,
    percentil_cobertura: 90,
  },
  taxas: {
    ...ARTICO.taxas,
    taxa_media_ponderada_dc_com_risco: 2.12,
    taxa_media_ponderada_dc_sem_risco: 1.22,
  },
  evolucao_pl: (() => {
    const vals = serieCrescente(428_950_000)
    return meses24.map((p, i) => ({ periodo: p, pl: vals[i] }))
  })(),
}

export const FICHAS: Record<string, Ficha> = {
  [ARTICO.identidade.cnpj_fundo]: ARTICO,
  [ZENIT.identidade.cnpj_fundo]: ZENIT,
  [NOVA_ORLA.identidade.cnpj_fundo]: NOVA_ORLA,
  [CANAL7.identidade.cnpj_fundo]: CANAL7,
  [POLO_NORTE.identidade.cnpj_fundo]: POLO_NORTE,
}

export function ficha(cnpj: string): Ficha | undefined {
  return FICHAS[cnpj]
}
