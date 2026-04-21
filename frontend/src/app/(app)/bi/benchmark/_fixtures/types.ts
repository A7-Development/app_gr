//
// Tipos dos fixtures mock da feature Ficha + Comparativo.
// Espelham o shape que o backend vai devolver (§Backend do plano).
// Quando os endpoints `/fundo/{cnpj}` e `/comparativo` existirem,
// substituimos esses imports pelo api-client sem mudar os componentes.
//

export type Identidade = {
  cnpj_fundo: string
  cnpj_classe: string
  denominacao_social: string
  administrador: string
  classe_anbima: string
  condominio: "aberto" | "fechado"
  exclusivo: boolean
  monoclasse: boolean
  prazo_min_resgate_dias: number | null
  prazo_conversao_dias: number | null
  competencia: string // YYYY-MM
}

export type EscalaSnapshot = {
  pl: number
  pl_medio_3m: number
  colchao_subordinacao_pct: number // 0..100
  duration_dias: number
  nro_cotistas: number
  pct_dc_pl: number
  valor_total_dc: number
}

export type PlSubclasse = {
  subclasse: "Senior" | "Mezanino" | "Subordinada"
  qtd_cotas: number
  vl_cota: number
  pl: number
  pct_pl: number
}

export type AgingFaixa = {
  faixa: string // "0-30d", "31-60d", ...
  valor: number
}

export type ScrBucket = {
  rating: "AA" | "A" | "B" | "C" | "D" | "E" | "F" | "G" | "H"
  pct_devedores: number
  pct_operacoes: number
}

export type QualidadeBloco = {
  pct_inad_total: number
  pct_inad_90d: number
  pct_inad_360d: number
  pct_cobertura_pdd: number
  percentil_inad_total: number // 0..100, vs classe ANBIMA
  percentil_cobertura: number
  aging_a_vencer: AgingFaixa[]   // 10 faixas
  aging_inadimplente: AgingFaixa[] // 10 faixas
  pdd_provisao: number
  scr_devedores: ScrBucket[]
  evolucao: Array<{
    periodo: string
    pct_inad_total: number
    pct_inad_90d: number
    pct_inad_360d: number
    pct_cobertura: number
  }>
}

export type AtivoLinha = {
  categoria: string
  valor: number
  pct: number
}

export type SegmentoLinha = {
  setor: string
  valor: number
  pct: number
  subsetores?: Array<{ nome: string; valor: number; pct: number }>
}

export type Cedente = {
  cnpj_mascarado: string
  denominacao: string | null
  valor_cedido: number
  pct: number
}

export type PassivoBloco = {
  curto_prazo: number
  longo_prazo: number
  derivativos: Array<{ tipo: string; valor: number }>
  alavancagem_pct: number
}

export type TaxaLinha = {
  tipo_ativo: string
  taxa_min: number
  taxa_media: number
  taxa_max: number
}

export type TaxasBloco = {
  taxa_media_ponderada_dc_com_risco: number
  taxa_media_ponderada_dc_sem_risco: number
  por_tipo: TaxaLinha[]
  evolucao: Array<{ periodo: string; taxa_dc_com: number; taxa_dc_sem: number }>
}

export type CotistasBloco = {
  total: number
  por_subclasse: Array<{ subclasse: string; qtd: number }>
  por_tipo_investidor: Array<{
    tipo: string
    senior: number
    subord: number
  }>
}

export type Ficha = {
  identidade: Identidade
  escala: EscalaSnapshot
  pl_subclasses: PlSubclasse[]
  qualidade: QualidadeBloco
  ativo: AtivoLinha[]
  segmento: SegmentoLinha[]
  cedentes: Cedente[]
  passivo: PassivoBloco
  taxas: TaxasBloco
  cotistas: CotistasBloco
  regularidade_cedido_com_divida: number
  garantias_pct_dc_com_garantia: number
  garantias_valor_total: number
  evolucao_pl: Array<{ periodo: string; pl: number }>
  evolucao_dc: Array<{ periodo: string; dc: number }>
  evolucao_setores: Array<Record<string, number | string>> // stacked
}

export type FundoListItem = {
  cnpj_fundo: string
  denominacao_social: string
  classe_anbima: string
  pl: number
  nro_cotistas: number
  pct_pdd: number
  pct_inad_total: number
}

export type IndicadorKey =
  | "pl"
  | "pl_medio_3m"
  | "pct_dc_pl"
  | "nro_cotistas"
  | "colchao_subordinacao_pct"
  | "top1_cedente_pct"
  | "duration_dias"
  | "pct_inad_total"
  | "pct_inad_90d"
  | "pct_inad_360d"
  | "pct_cobertura_pdd"
  | "pct_aa_scr"
  | "pct_d_mais_scr"
  | "taxa_dc_com"
  | "taxa_dc_sem"

export type IndicadorDefinicao = {
  key: IndicadorKey
  label: string
  unidade: "BRL" | "%" | "dias" | "un"
  grupo: "escala" | "estrutura" | "qualidade" | "taxas"
  /** `higher_is_better` para ranking visual (↑ melhor / ↓ melhor). */
  direcao: "higher_is_better" | "lower_is_better"
}
