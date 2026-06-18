"use client"

//
// BI · Concentração — Top-10 cedentes e sacados por valor presente (carteira
// QiTech) sobre o PL total do fundo (MEC), + histórico diário. Só Realinvest
// por enquanto (A7 Credit terá lógica própria). Padrão BI canônico.
//

import * as React from "react"
import { useQuery } from "@tanstack/react-query"

import { PageHeader } from "@/design-system/components/PageHeader"
import { biConcentracao } from "@/lib/api-client"
import { cx } from "@/lib/utils"

import { ConcentracaoCard } from "./_components/ConcentracaoCard"
import { HistoricoCard } from "./_components/HistoricoCard"

function fmtData(iso: string | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  return d.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    timeZone: "UTC",
  })
}

function fmtDataLong(iso: string | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  return d.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "UTC",
  })
}

export default function ConcentracaoPage() {
  const q = useQuery({
    queryKey: ["bi", "concentracao"],
    queryFn: () => biConcentracao.get(),
  })

  const data = q.data?.data
  const loading = q.isLoading
  const posicao = fmtData(data?.data_posicao)

  return (
    <div className="flex h-[calc(100vh-56px)] flex-col">
      <div className="flex-1 overflow-auto">
        <div className="flex flex-col gap-6 px-6 pt-5 pb-8">
          <PageHeader
            title="Concentração"
            subtitle="BI · Risco"
            info="Top-10 cedentes e sacados por valor presente da carteira FIDC (QiTech) sobre o PL total do fundo (MEC, soma das classes). Posição diária. Apenas Realinvest."
          />

          {/* Tabelas — Cedentes | Sacados */}
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <ConcentracaoCard
              titulo="Cedentes"
              eyebrow="Cedentes"
              posicao={posicao}
              tabela={data?.cedentes}
              loading={loading}
            />
            <ConcentracaoCard
              titulo="Sacados"
              eyebrow="Sacados"
              posicao={posicao}
              tabela={data?.sacados}
              loading={loading}
            />
          </div>

          {/* Histórico — Cedentes | Sacados */}
          <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
            <HistoricoCard
              titulo="Histórico de concentração — cedentes"
              labelMaior="Maior cedente"
              pontos={data?.historico_cedentes ?? []}
              loading={loading}
            />
            <HistoricoCard
              titulo="Histórico de concentração — sacados"
              labelMaior="Maior sacado"
              pontos={data?.historico_sacados ?? []}
              loading={loading}
            />
          </div>
        </div>
      </div>

      {/* Proveniência — linha de marca A7 (lâmina de consultoria). */}
      <div
        className={cx(
          "flex shrink-0 items-center border-t px-6 py-1.5",
          "border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900/40",
        )}
      >
        <span className="text-[11px] text-gray-500 dark:text-gray-400">
          Dados fornecidos pela administradora e modelados pela consultoria A7
          Credit. Posição {fmtDataLong(data?.data_posicao)}.
        </span>
      </div>
    </div>
  )
}
