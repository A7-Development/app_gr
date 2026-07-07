/**
 * Schema + labels da tela Risco · Contratos de liquidacao.
 * Espelha ContratoLiquidacaoUpdate do backend (3 campos declarados +
 * justificativa opcional). Labels pt-BR centralizados aqui para a pagina,
 * o form e o historico usarem o mesmo vocabulario.
 */

import { z } from "zod"

import type {
  ContratoLiquidacaoRow,
  ContratoLiquidacaoUpdatePayload,
  ExpectativaBaixaManual,
  ExpectativaBoleto,
  FluxoLiquidacao,
} from "@/lib/api-client"

export const contratoLiquidacaoSchema = z.object({
  fluxo_esperado: z.enum([
    "boleto_bancario",
    "deposito_em_conta",
    "liquidacao_interna",
  ]),
  boleto: z.enum(["obrigatorio", "permitido", "nao_esperado"]),
  baixa_manual: z.enum(["normal", "anomala"]),
  justificativa: z
    .string()
    .max(512, "Maximo de 512 caracteres.")
    .optional()
    .or(z.literal("")),
})

export type ContratoLiquidacaoFormValues = z.infer<typeof contratoLiquidacaoSchema>

export const FLUXO_LABELS: Record<FluxoLiquidacao, string> = {
  boleto_bancario: "Boleto bancário",
  deposito_em_conta: "Depósito em conta",
  liquidacao_interna: "Liquidação interna",
}

export const BOLETO_LABELS: Record<ExpectativaBoleto, string> = {
  obrigatorio: "Obrigatório",
  permitido: "Permitido",
  nao_esperado: "Não esperado",
}

export const BAIXA_MANUAL_LABELS: Record<ExpectativaBaixaManual, string> = {
  normal: "Normal",
  anomala: "Anômala",
}

export const DIVERGENCIA_LABELS: Record<string, string> = {
  volume_em_produto_aberto: "Volume em produto aberto",
  boleto_alem_do_esperado: "Boleto além do esperado",
  boleto_abaixo_do_esperado: "Boleto abaixo do esperado",
  baixa_manual_em_produto_anomalo: "Baixa manual em produto anômalo",
}

export function fromContrato(
  row: ContratoLiquidacaoRow,
): ContratoLiquidacaoFormValues {
  return {
    fluxo_esperado: row.fluxo_esperado ?? "boleto_bancario",
    boleto: row.boleto ?? "obrigatorio",
    baixa_manual: row.baixa_manual ?? "anomala",
    justificativa: "",
  }
}

export function toUpdatePayload(
  values: ContratoLiquidacaoFormValues,
): ContratoLiquidacaoUpdatePayload {
  return {
    fluxo_esperado: values.fluxo_esperado,
    boleto: values.boleto,
    baixa_manual: values.baixa_manual,
    justificativa: values.justificativa?.trim() ? values.justificativa.trim() : null,
  }
}
