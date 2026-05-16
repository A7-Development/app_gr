"use client"

// /bi/benchmark2/[cnpj] — Ficha Lamina do fundo CVM.
//
// Reproduz o layout do Relatorio de Monitoramento da Austin Rating, com
// foco nas tabelas que CVM publica:
//   1. Posicao da Carteira (R$ mil)         ← CarteiraLaminaTable
//   2. Posicao da Carteira (% do PL)        ← CarteiraLaminaTable
//   3. Indices de Cobertura da Subordinacao ← CoberturaSubordinacaoTable
//
// Versao inicial (Fase 3). As demais secoes da Lamina (Recompras, Atraso,
// Cedentes top-9, PL por subclasse, Rentabilidade) entram em iteracao
// posterior reusando componentes existentes ou adaptados.
//
// CNPJ vem do route param (formatado ou so digitos). Backend normaliza.

import Link from "next/link"
import { RiAlertLine, RiArrowLeftLine, RiSearchLine } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { PageHeader } from "@/design-system/components/PageHeader"
import { EmptyState } from "@/design-system/components/EmptyState"

import { useBenchmark2Fundo } from "../_components/useBenchmark2"
import { CarteiraLaminaTable } from "./_components/CarteiraLaminaTable"
import { CoberturaSubordinacaoTable } from "./_components/CoberturaSubordinacaoTable"
import { IdentidadeHeader } from "./_components/IdentidadeHeader"

const PAGE_INFO =
  "Ficha do fundo no layout Lamina (Austin Rating style). Dados publicos via CVM Informe Mensal FIDC (schema cvm_remote)."

// Next 14 (App Router): `params` em client components vem como objeto plano,
// nao Promise. (Promise + use() so a partir de Next 15.)
type PageProps = {
  params: { cnpj: string }
}

export default function Benchmark2FichaPage({ params }: PageProps) {
  const digits = params.cnpj.replace(/\D/g, "")
  const query = useBenchmark2Fundo(digits)

  if (query.isPending) {
    return (
      <div className="flex flex-col gap-4 px-6 pt-5 pb-6">
        <BackButton />
        <div className="flex h-48 items-center justify-center text-sm text-gray-500 dark:text-gray-400">
          Carregando ficha do fundo...
        </div>
      </div>
    )
  }

  if (query.isError) {
    return (
      <div className="flex flex-col gap-4 px-6 pt-5 pb-6">
        <BackButton />
        <EmptyState
          icon={RiAlertLine}
          title="Fundo nao encontrado"
          description={`Nenhuma ficha disponivel para o CNPJ ${params.cnpj} na base CVM.`}
        />
      </div>
    )
  }

  const ficha = query.data?.data
  if (!ficha) {
    return (
      <div className="flex flex-col gap-4 px-6 pt-5 pb-6">
        <BackButton />
        <EmptyState
          icon={RiSearchLine}
          title="Sem dados"
          description="O endpoint retornou vazio para este CNPJ."
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 px-6 pt-5 pb-10">
      <BackButton />

      <PageHeader
        title={ficha.identificacao.denom_social ?? "Fundo CVM"}
        info={PAGE_INFO}
        subtitle="BI · Benchmark · Ficha Lamina"
      />

      <IdentidadeHeader ficha={ficha} />

      <CarteiraLaminaTable ficha={ficha} format="brl" />
      <CarteiraLaminaTable ficha={ficha} format="pct" />
      <CoberturaSubordinacaoTable ficha={ficha} />
    </div>
  )
}

function BackButton() {
  return (
    <Link href="/bi/benchmark2">
      <Button variant="ghost" className="gap-1.5 self-start">
        <RiArrowLeftLine className="size-4" aria-hidden />
        Voltar para lista
      </Button>
    </Link>
  )
}
