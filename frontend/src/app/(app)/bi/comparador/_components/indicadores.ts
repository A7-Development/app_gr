// Config da cesta de indicadores do Comparador (espelha o backend
// /bi/benchmark/indicadores e docs/cvm-fidc/indicadores-benchmarking.md).
// `key` = campo do valor; `${key}_rank` = percentil 0-100 no universo.

import type { ComparadorIndicadoresFundo } from "@/lib/api-client"

export type GrupoIndicador =
  | "Estrutura"
  | "Perfil do ativo"
  | "Qualidade de crédito"
  | "Fluxo"
  | "Performance"

export const GRUPOS: GrupoIndicador[] = [
  "Estrutura",
  "Perfil do ativo",
  "Qualidade de crédito",
  "Fluxo",
  "Performance",
]

type FmtKind = "brl" | "pct1" | "pct2" | "dias" | "pp" | "texto"

export type IndicadorDef = {
  key: keyof ComparadorIndicadoresFundo
  label: string
  /** Fracao/formula exibida como sufixo discreto ao lado do label. */
  formula?: string
  grupo: GrupoIndicador
  fmt: FmtKind
  /** Tooltip de definicao (proveniencia/semantica). */
  info: string
}

export const INDICADORES: IndicadorDef[] = [
  { key: "condominio", label: "Condomínio", grupo: "Estrutura", fmt: "texto",
    info: "Aberto (cotista resgata a qualquer tempo — exige gestão de liquidez) ou Fechado (resgate só no vencimento/amortização). Cadastral CVM." },
  { key: "pl", label: "Patrimônio Líquido", grupo: "Estrutura", fmt: "brl",
    info: "PL do fundo na competência (tab_iv). Porte." },
  { key: "subordinacao_pct", label: "Subordinação total", formula: "(Jr+Mez)/PL", grupo: "Estrutura", fmt: "pct1",
    info: "PL das classes subordinadas (incl. mezanino) ÷ PL total. Colchão de proteção da SENIOR — mercado considera >20% conservador." },
  { key: "subordinacao_jr_pct", label: "Subordinação júnior", formula: "Jr/PL", grupo: "Estrutura", fmt: "pct1",
    info: "PL da subordinada júnior (sem mezanino) ÷ PL total. O first-loss real do fundo — e a proteção que a MEZANINO enxerga." },
  { key: "sub_jr_sobre_sub_pct", label: "Composição do colchão", formula: "Jr/Sub total", grupo: "Estrutura", fmt: "pct1",
    info: "Quanto do colchão subordinado é first-loss genuíno (júnior) vs mezanino. 100% = sem mezanino; valores baixos = colchão 'diluído' em camadas vendidas a terceiros." },
  { key: "passivo_ativo_pct", label: "Passivo / Ativo", grupo: "Estrutura", fmt: "pct2",
    info: "Obrigações ÷ ativo total. FIDC quase não tem passivo; valor alto = estrutura atípica." },
  { key: "dc_ativo_pct", label: "% do Ativo em DC", grupo: "Perfil do ativo", fmt: "pct1",
    info: "Direitos creditórios (líquidos) ÷ ativo. Separa fundo-de-carteira de fundo-veículo/distressed." },
  { key: "alta_liquidez_pl_pct", label: "Alta Liquidez / PL", grupo: "Perfil do ativo", fmt: "pct2",
    info: "Caixa amplo (disponibilidades + tít. públicos + CDB + compromissadas + fundos DI + recebíveis de curto prazo) ÷ PL. Eficiência de alocação." },
  { key: "prazo_medio_dias", label: "Prazo médio da carteira (≈)", grupo: "Perfil do ativo", fmt: "dias",
    info: "APROXIMADO: a CVM só publica o vencimento em 10 faixas; usamos o ponto médio de cada uma. Superestima carteiras curtas (~+20% — validado: REALINVEST real 21,7d vs 26,8d aqui) e subestima fundos com cauda >1080d (faixa censurada). Confiável para COMPARAR fundos, não como nível absoluto." },
  { key: "inad_total_pct", label: "Inadimplência total", grupo: "Qualidade de crédito", fmt: "pct2",
    info: "DC vencidos e não pagos ÷ DC bruto (blocos com E sem risco — atraso normalizado). Mercado abr/26 ≈ 11%." },
  { key: "inad_90_pct", label: "Inadimplência > 90d", grupo: "Qualidade de crédito", fmt: "pct2",
    info: "Vencidos há mais de 90 dias ÷ DC bruto. A cauda dura do atraso." },
  { key: "inad_180_pct", label: "Inadimplência > 180d", grupo: "Qualidade de crédito", fmt: "pct2",
    info: "Vencidos há mais de 180 dias ÷ DC bruto (faixas exatas da CVM). Perda quase certa — separa atraso operacional de problema estrutural." },
  { key: "cobertura_pdd_pct", label: "Cobertura de PDD", grupo: "Qualidade de crédito", fmt: "pct1",
    info: "Provisão ÷ inadimplentes. ≥100% = bem provisionado. Ler junto com a taxa de recompra (recompra alta mascara atraso)." },
  { key: "pdd_pl_pct", label: "PDD / PL", grupo: "Qualidade de crédito", fmt: "pct2",
    info: "Provisão para perdas ÷ PL. Peso da perda esperada no patrimônio." },
  { key: "recompra_dc_pct", label: "Taxa de recompra (mês)", grupo: "Qualidade de crédito", fmt: "pct2",
    info: "Recompras pelo cedente no mês ÷ DC bruto. Proxy de write-off/suporte do cedente — alta com inadimplência baixa é red flag clássico." },
  { key: "scr_dh_pct", label: "Carteira SCR D–H", grupo: "Qualidade de crédito", fmt: "pct2",
    info: "Fatia da carteira nos ratings BACEN D a H (visão da operação). Única lente pública de rating." },
  { key: "divida_ativa_pct", label: "DC de cedentes em Dívida Ativa", grupo: "Qualidade de crédito", fmt: "pct1",
    info: "DC cedidos por cedentes com débito inscrito em Dívida Ativa da União ÷ DC bruto. Risco de constrição judicial do lastro." },
  { key: "captacao_liq_pl_pct", label: "Captação líquida / PL", grupo: "Fluxo", fmt: "pct2",
    info: "(Captações − resgates − amortizações) do mês ÷ PL. Crescimento orgânico." },
  { key: "giro_pct", label: "Giro da carteira (mês)", grupo: "Fluxo", fmt: "pct1",
    info: "DC adquiridos no mês ÷ DC bruto. Velocity do lastro (carteira curta gira ~1×/mês)." },
  { key: "rentab_sub_pct", label: "Rentabilidade da Subordinada", grupo: "Performance", fmt: "pct2",
    info: "Rentabilidade mensal da classe subordinada júnior (tab_x_3 — o 'equity' do fundo)." },
  { key: "atingimento_pp", label: "Real − Meta (séries com meta)", grupo: "Performance", fmt: "pp",
    info: "Desempenho real menos esperado das séries com meta (senior/mezanino). 0 = entregou a meta exata." },
  { key: "yield_efetivo_pct", label: "Yield efetivo da carteira", grupo: "Performance", fmt: "pct2",
    info: "Resultado do mês de todas as classes ÷ DC bruto médio. Retorno líquido que a carteira entregou (piso da taxa praticada)." },
]

const fmtInt = new Intl.NumberFormat("pt-BR")

export function formatIndicador(
  v: number | string | null | undefined,
  fmt: FmtKind,
): string {
  if (v === null || v === undefined) return "—"
  if (typeof v === "string") return v
  switch (fmt) {
    case "brl": {
      const abs = Math.abs(v)
      if (abs >= 1_000_000_000) return `R$ ${(v / 1_000_000_000).toFixed(2).replace(".", ",")} bi`
      if (abs >= 1_000_000) return `R$ ${(v / 1_000_000).toFixed(1).replace(".", ",")} mi`
      if (abs >= 1_000) return `R$ ${(v / 1_000).toFixed(0)} mil`
      return `R$ ${fmtInt.format(Math.round(v))}`
    }
    case "pct1":
      return `${v.toFixed(1).replace(".", ",")}%`
    case "pct2":
      return `${v.toFixed(2).replace(".", ",")}%`
    case "dias":
      return `${v.toFixed(0)}d`
    case "pp":
      return `${v >= 0 ? "+" : ""}${v.toFixed(2).replace(".", ",")} pp`
    case "texto":
      return String(v)
  }
}

/** Percentil orientado: 100 = melhor do universo, na direcao do indicador. */
export function rankOrientado(
  rank: number | null | undefined,
  maiorMelhor: boolean | undefined,
): number | null {
  if (rank === null || rank === undefined) return null
  return maiorMelhor === false ? 100 - rank : rank
}
