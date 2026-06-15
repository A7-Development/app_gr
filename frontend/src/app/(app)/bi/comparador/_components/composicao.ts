// Vocabulario fechado da COMPOSICAO DO ATIVO do Comparador (espelha
// COMPOSICAO_BUCKETS do backend benchmark_indicadores.py). Aqui vivem os
// rotulos pt-BR e a estrutura de drill (bucket -> folhas).
//
// Por que existe: o grupo "Perfil do ativo" tinha so RATIOS soltos (% em DC,
// liquidez/PL) que nao fecham em 100% — o "9,1% em DC" ficava orfao. Esta
// decomposicao fecha em 100% do ativo POR CONSTRUCAO: as chaves sao fixas,
// vem sempre (0 quando ausente) e a soma dos buckets = ativo_total. Garante
// que o comparador liste TODOS os ativos e mantenha as mesmas linhas para
// qualquer fundo (comparavel lado a lado) — §14.6 (zero ocultacao).

export type ComposicaoFolha = { key: string; label: string }

export type ComposicaoBucket = {
  key: string
  label: string
  /** Folhas reveladas no drill (somam o valor do bucket). */
  folhas: ComposicaoFolha[]
}

export const COMPOSICAO_BUCKETS: ComposicaoBucket[] = [
  {
    key: "dc",
    label: "Direitos creditórios",
    folhas: [
      { key: "c_dc_risco", label: "Com risco de cessão" },
      { key: "c_dc_sem_risco", label: "Sem risco de cessão" },
    ],
  },
  {
    key: "cota_fidc",
    label: "Cotas de FIDC",
    folhas: [
      { key: "c_cota_fidc", label: "Cotas de FIDC" },
      { key: "c_cota_fidc_np", label: "Cotas de FIDC-NP" },
    ],
  },
  {
    key: "cota_fundo",
    label: "Cotas de fundos (FIF/555)",
    folhas: [{ key: "c_cota_fundo", label: "Cotas de fundo (FIF/ICVM 555)" }],
  },
  {
    key: "vm",
    label: "Valores mobiliários",
    folhas: [
      { key: "c_deb", label: "Debêntures" },
      { key: "c_cri", label: "CRI" },
      { key: "c_np", label: "Notas promissórias comerciais" },
      { key: "c_lf", label: "Letras financeiras" },
      { key: "c_vm_outro", label: "Outros valores mobiliários" },
    ],
  },
  {
    key: "caixa_rf",
    label: "Caixa e renda fixa",
    folhas: [
      { key: "c_disp", label: "Disponibilidades" },
      { key: "c_tpf", label: "Títulos públicos federais" },
      { key: "c_cdb", label: "CDB" },
      { key: "c_compromissada", label: "Operações compromissadas" },
      { key: "c_outro_rf", label: "Outros renda fixa" },
    ],
  },
  {
    key: "derivativos",
    label: "Derivativos",
    folhas: [
      { key: "c_futuro", label: "Contratos futuros" },
      { key: "c_deriv", label: "Posição em derivativos" },
    ],
  },
  {
    key: "outros",
    label: "Outros ativos",
    folhas: [
      { key: "c_carteira_outro", label: "Outros ativos da carteira" },
      { key: "c_outro_ativo", label: "Outros ativos (curto/longo prazo)" },
    ],
  },
]

/** % do ativo (valor da chave ÷ ativo_total). null se sem ativo. */
export function pctDaComposicao(
  composicao: Record<string, number> | undefined,
  ativoTotal: number | null | undefined,
  key: string,
): number | null {
  if (!composicao || !ativoTotal || ativoTotal <= 0) return null
  const valor = composicao[key]
  if (valor === undefined || valor === null) return null
  return (100 * valor) / ativoTotal
}
