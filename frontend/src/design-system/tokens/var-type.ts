// src/design-system/tokens/var-type.ts
//
// Tokens visuais por VarType — espelha o enum em
// `backend/app/shared/workflow/nodes/_base.py::VarType`.
//
// Usado por:
// - StrataNode → renderiza chips de output tipados (Fase 3a)
// - VariablesPill → mostra variáveis upstream coloridas pelo tipo
// - (futuro) handles tipados no React Flow
//
// Princípio de cor:
//   Documento (CPF/CNPJ) = tons de azul/verde por categoria de pessoa
//   Numérico (NUMBER/MONEY/SCORE) = tons quentes (amarelo/âmbar/laranja)
//   Texto (STRING/EMAIL/URL/PHONE) = neutros + cinza-azul
//   Estrutural (OBJECT/LIST/FILE) = roxo (chamando "este é compósito")
//   Boolean = simples cinza
//
// As cores fogem de algumas restrições da §4 do CLAUDE.md (uso de
// emerald/amber etc fora de chart) — autorizado em modo iteração de
// design ativo. Quando a janela fechar, vamos varrer e migrar pra
// tokens nomeados (`tokens.colors.dataType.cnpj`, etc).

import type { VarType } from "./var-type-enum"

export type VarTypeMeta = {
  /** Label curto pra mostrar em chip (3-8 chars). */
  label: string
  /** Classes Tailwind pro chip pequeno: bg + text. */
  chipClass: string
  /** Classe de bg só (pra dot/handle indicator pequeno). */
  dotClass: string
  /** Texto descritivo curto pra tooltip. */
  description: string
}

export const VAR_TYPE_META: Record<VarType, VarTypeMeta> = {
  string: {
    label: "txt",
    chipClass: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
    dotClass: "bg-gray-400 dark:bg-gray-600",
    description: "Texto livre",
  },
  cpf: {
    label: "CPF",
    chipClass: "bg-blue-50 text-blue-700 dark:bg-blue-500/15 dark:text-blue-300",
    dotClass: "bg-blue-500",
    description: "CPF (11 dígitos)",
  },
  cnpj: {
    label: "CNPJ",
    chipClass: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300",
    dotClass: "bg-emerald-500",
    description: "CNPJ (14 dígitos)",
  },
  email: {
    label: "@",
    chipClass: "bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300",
    dotClass: "bg-violet-500",
    description: "Email",
  },
  phone: {
    label: "tel",
    chipClass: "bg-violet-50 text-violet-700 dark:bg-violet-500/15 dark:text-violet-300",
    dotClass: "bg-violet-400",
    description: "Telefone",
  },
  date: {
    label: "data",
    chipClass: "bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300",
    dotClass: "bg-sky-500",
    description: "Data (YYYY-MM-DD)",
  },
  datetime: {
    label: "ts",
    chipClass: "bg-sky-50 text-sky-700 dark:bg-sky-500/15 dark:text-sky-300",
    dotClass: "bg-sky-600",
    description: "Data e hora (ISO 8601)",
  },
  number: {
    label: "num",
    chipClass: "bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
    dotClass: "bg-amber-500",
    description: "Número (inteiro ou decimal)",
  },
  money_brl: {
    label: "R$",
    chipClass: "bg-amber-50 text-amber-700 dark:bg-amber-500/15 dark:text-amber-300",
    dotClass: "bg-amber-600",
    description: "Valor monetário em BRL",
  },
  score: {
    label: "score",
    chipClass: "bg-yellow-50 text-yellow-800 dark:bg-yellow-500/15 dark:text-yellow-300",
    dotClass: "bg-yellow-500",
    description: "Score (geralmente 0-1000)",
  },
  boolean: {
    label: "bool",
    chipClass: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
    dotClass: "bg-gray-500",
    description: "Verdadeiro / Falso",
  },
  url: {
    label: "url",
    chipClass: "bg-indigo-50 text-indigo-700 dark:bg-indigo-500/15 dark:text-indigo-300",
    dotClass: "bg-indigo-500",
    description: "URL",
  },
  uuid: {
    label: "id",
    chipClass: "bg-stone-100 text-stone-700 dark:bg-stone-800 dark:text-stone-300",
    dotClass: "bg-stone-500",
    description: "UUID — identificador único",
  },
  file: {
    label: "file",
    chipClass: "bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300",
    dotClass: "bg-rose-500",
    description: "Arquivo (PDF, imagem, etc)",
  },
  object: {
    label: "obj",
    chipClass: "bg-purple-50 text-purple-700 dark:bg-purple-500/15 dark:text-purple-300",
    dotClass: "bg-purple-500",
    description: "Objeto estruturado (dict)",
  },
  list: {
    label: "[…]",
    chipClass: "bg-purple-50 text-purple-700 dark:bg-purple-500/15 dark:text-purple-300",
    dotClass: "bg-purple-400",
    description: "Lista de valores",
  },
}

/** Lookup defensivo — retorna meta default pra tipos desconhecidos. */
export function varTypeMeta(type: string | undefined | null): VarTypeMeta {
  if (!type) return VAR_TYPE_META.string
  const meta = VAR_TYPE_META[type as VarType]
  return meta ?? VAR_TYPE_META.string
}
