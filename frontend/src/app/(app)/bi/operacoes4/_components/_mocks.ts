// Mocks PR1 do redesign /bi/operacoes4 (handoff 2026-05-21).
//
// Conteudo deste arquivo cobre dados que o backend ainda nao expoe (PR3):
//   1. Taxa media ponderada por produto (coluna "Taxa media" do Mix em L2)
//   2. Distribuicao de taxas MTD em buckets (Hist L3 card 1)
//   3. Taxa media por produto ordenada (Bar L3 card 2)
//   4. Distribuicao de prazo em buckets (Hist L3 card 3)
//
// Tudo aqui esta marcado com TODO_PR3 — substituir por dados reais do
// backend quando o endpoint for entregue. Quando isso acontecer, este
// arquivo pode ser deletado e os componentes que importam dele migram
// para hooks/useQuery direto.
//
// NAO popular este arquivo com dados de producao reais — e fixture de
// desenvolvimento. Sempre que possivel, usar valores que batam com o
// protótipo Hi-Fi (mesma escala/proporcao) para nao gerar regressao
// visual entre dev e o handoff.

// TODO_PR3: backend precisa expor taxa media ponderada por produto
// (peso = VOP MTD). Hoje so vem prior_value/current_value no Mix.
export const MOCK_TAXA_MEDIA_POR_PRODUTO: Record<string, number> = {
  DMS: 3.12,
  CCB: 2.95,
  FAT: 2.88,
  CMS: 2.81,
  CDC: 2.74,
  INT: 2.62,
  FOM: 2.55,
}

export type HistogramBucket = {
  label: string
  vop_mtd: number
  /** Marca tail bucket (`>3,5` ou `>90`) — usado pra pintar em red/orange. */
  is_tail?: boolean
}

// TODO_PR3: hist de taxas MTD em 5 buckets, ponderado por VOP.
export const MOCK_HIST_TAXAS_MTD: HistogramBucket[] = [
  { label: "<2,0", vop_mtd: 1_200_000 },
  { label: "2,0–2,5", vop_mtd: 4_400_000 },
  { label: "2,5–3,0", vop_mtd: 8_900_000 },
  { label: "3,0–3,5", vop_mtd: 5_700_000 },
  { label: ">3,5", vop_mtd: 1_500_000, is_tail: true },
]

// TODO_PR3: hist de prazo em 6 buckets (15d cada).
export const MOCK_HIST_PRAZO: HistogramBucket[] = [
  { label: "0–15", vop_mtd: 3_200_000 },
  { label: "15–30", vop_mtd: 7_100_000 },
  { label: "30–45", vop_mtd: 6_800_000 },
  { label: "45–60", vop_mtd: 2_900_000 },
  { label: "60–90", vop_mtd: 1_400_000 },
  { label: ">90", vop_mtd: 300_000, is_tail: true },
]

export const MOCK_WAVG_TAXAS_MTD = 2.84
export const MOCK_MEDIANA_TAXAS_MTD = 2.78
export const MOCK_PRAZO_MEDIO_MTD = 30.8
export const MOCK_PRAZO_DELTA_DIAS = 1.6
