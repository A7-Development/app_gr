"use client"

// /bi/comparador — Comparador de FIDCs por indicadores (ate 3 fundos).
//
// Opcao A da reorganizacao do grupo Benchmark (aprovada 2026-06-11):
//   Panorama = mercado · Fundos = explorador · COMPARADOR = confronto.
// Cesta de 17 indicadores (docs/cvm-fidc/indicadores-benchmarking.md), cada
// valor com percentil no universo da competencia; mediana do mercado como
// "4o competidor" implicito. Radar de 5 dimensoes da o veredito visual.
//
// Arquitetura (CLAUDE.md §11.6): L1 BI > L2 Benchmark > Comparador.
// Estado deep-linkavel: ?fundos=cnpj1,cnpj2,cnpj3&comp=YYYY-MM-DD (nuqs).
//
// MOTIVO (pattern): nao e dashboard nem listagem — e ferramenta de confronto
// (matriz transposta). Composicao direta sobre design-system/components,
// shell visual do benchmark2/cota-sub (title row + toolbar + conteudo).

import * as React from "react"
import { RiScales3Line } from "@remixicon/react"
import { useQuery } from "@tanstack/react-query"
import { parseAsString, useQueryState } from "nuqs"

import { cx } from "@/lib/utils"
import { PageHeader } from "@/design-system/components/PageHeader"
import { EmptyState } from "@/design-system/components/EmptyState"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import { filterControlClass } from "@/design-system/components"
import { biBenchmarkIndicadores } from "@/lib/api-client"

import {
  ComparadorFundoPicker,
  type FundoSelecionado,
} from "./_components/ComparadorFundoPicker"
import { MatrizIndicadores } from "./_components/MatrizIndicadores"
import { RadarDimensoes } from "./_components/RadarDimensoes"

const MAX_FUNDOS = 3

function labelCompetencia(iso: string): string {
  const m = /^(\d{4})-(\d{2})/.exec(iso)
  if (!m) return iso
  return `${m[2]}/${m[1]}`
}

export default function ComparadorPage() {
  // URL = fonte da verdade (§11.6): fundos CSV de CNPJs (digitos) + competencia.
  const [fundosCsv, setFundosCsv] = useQueryState(
    "fundos",
    parseAsString.withDefault(""),
  )
  const [comp, setComp] = useQueryState("comp", parseAsString.withDefault(""))

  const cnpjs = React.useMemo(
    () => fundosCsv.split(",").map((s) => s.trim()).filter(Boolean).slice(0, MAX_FUNDOS),
    [fundosCsv],
  )

  // Nomes escolhidos no picker (cache local; a resposta da API tambem traz).
  const [nomes, setNomes] = React.useState<Record<string, string>>({})

  const competenciasQ = useQuery({
    queryKey: ["bi", "benchmark", "indicadores", "competencias"],
    queryFn: () => biBenchmarkIndicadores.competencias(),
    staleTime: 60 * 60 * 1000,
  })
  const competencias = competenciasQ.data?.competencias ?? []

  const q = useQuery({
    queryKey: ["bi", "benchmark", "indicadores", cnpjs, comp || "ultima"],
    queryFn: () => biBenchmarkIndicadores.comparar(cnpjs, comp || undefined),
    enabled: cnpjs.length > 0,
  })
  const data = q.data

  const setSlot = (idx: number, f: FundoSelecionado | null) => {
    const next = [...cnpjs]
    if (f === null) next.splice(idx, 1)
    else {
      next[idx] = f.cnpj
      setNomes((prev) => ({ ...prev, [f.cnpj]: f.nome }))
    }
    void setFundosCsv(next.filter(Boolean).join(","))
  }

  const nomeDe = (cnpj: string): string => {
    const daApi = data?.fundos.find(
      (f) => f.cnpj.replace(/\D/g, "") === cnpj,
    )?.denom_social
    return daApi ?? nomes[cnpj] ?? cnpj
  }

  // Slots: fundos escolhidos + 1 slot vazio (ate o maximo).
  const slots: (FundoSelecionado | null)[] = [
    ...cnpjs.map((c) => ({ cnpj: c, nome: nomeDe(c) })),
    ...(cnpjs.length < MAX_FUNDOS ? [null] : []),
  ]

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col overflow-hidden">
      {/* Title row */}
      <div className="shrink-0 bg-white px-6 pt-3.5 pb-3 dark:bg-gray-950">
        <PageHeader
          title="Comparador de FIDCs"
          subtitle="BI · Benchmark"
          info="Confronto de até 3 fundos pela cesta de 17 indicadores derivada dos Informes Mensais CVM (dado público). Cada valor traz o percentil no universo da competência (p100 = melhor, já na direção do indicador); a mediana do mercado é o 4º competidor implícito. Semântica validada empiricamente — ver docs/cvm-fidc/indicadores-benchmarking.md."
        />
      </div>

      {/* Toolbar: pickers + competencia */}
      <div className="shrink-0 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
        <div className="flex min-h-[52px] flex-wrap items-center gap-2 px-6 py-2">
          {slots.map((slot, idx) => (
            <ComparadorFundoPicker
              key={slot?.cnpj ?? `vazio-${idx}`}
              selecionado={slot}
              onSelect={(f) => setSlot(idx, f)}
              onRemove={() => setSlot(idx, null)}
              disabledCnpjs={cnpjs}
            />
          ))}

          <div className="ml-auto flex shrink-0 items-center gap-2">
            <span className="text-[11px] text-gray-500 dark:text-gray-400">
              Competência
            </span>
            <Select
              value={comp || competencias[0] || ""}
              onValueChange={(v) => void setComp(v)}
            >
              <SelectTrigger className={cx(filterControlClass, "w-32")}>
                <SelectValue placeholder="Última" />
              </SelectTrigger>
              <SelectContent>
                {competencias.map((c) => (
                  <SelectItem key={c} value={c}>
                    {labelCompetencia(c)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {data && (
              <span className="text-[11px] tabular-nums text-gray-400 dark:text-gray-500">
                {data.total_fundos_universo.toLocaleString("pt-BR")} fundos no
                universo
              </span>
            )}
          </div>
        </div>
      </div>

      {/* Conteudo */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {cnpjs.length === 0 ? (
          <EmptyState
            icon={RiScales3Line}
            title="Escolha os fundos para comparar"
            description="Adicione até 3 FIDCs pela busca acima. Cada indicador vem com o percentil do fundo no universo CVM da competência — e a mediana do mercado entra como referência em todas as linhas."
            className="mt-10"
          />
        ) : q.isError ? (
          <EmptyState
            icon={RiScales3Line}
            title="Não foi possível carregar os indicadores"
            description="Tente novamente em instantes."
            className="mt-10"
          />
        ) : q.isLoading ? (
          // Primeira consulta de uma competencia calcula o universo inteiro
          // (~4k fundos via FDW) — pode levar ate ~1 min com cache frio.
          // Sem este estado a tela fica em branco e parece quebrada.
          <div className="mt-16 flex flex-col items-center gap-3">
            <span
              className="size-6 animate-spin rounded-full border-2 border-gray-200 border-t-blue-500 dark:border-gray-700 dark:border-t-blue-400"
              aria-hidden="true"
            />
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Calculando os indicadores do universo CVM…
            </p>
            <p className="text-xs text-gray-400 dark:text-gray-500">
              A primeira consulta de uma competência avalia ~4 mil fundos e
              pode levar até um minuto. As próximas são instantâneas.
            </p>
          </div>
        ) : (
          <div
            className={cx(
              "flex flex-col gap-4",
              q.isFetching && "opacity-60 transition-opacity",
            )}
          >
            {data && data.nao_encontrados.length > 0 && (
              <p className="text-xs text-amber-600 dark:text-amber-400">
                Sem informe na competência: {data.nao_encontrados.join(" · ")}
              </p>
            )}
            {data && data.fundos.length > 0 && (
              <>
                <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
                  <RadarDimensoes fundos={data.fundos} direcao={data.direcao} />
                  <div className="xl:col-span-2">
                    <MatrizIndicadores
                      fundos={data.fundos}
                      mediana={data.mediana}
                      composicaoMediana={data.composicao_mediana}
                      direcao={data.direcao}
                    />
                  </div>
                </div>
                <p className="text-[11px] text-gray-400 dark:text-gray-500">
                  Fonte: Informes Mensais FIDC · CVM dados abertos
                  (public:cvm_fidc) · competência{" "}
                  {labelCompetencia(data.competencia)} · pN = percentil no
                  universo, orientado (100 = melhor) · ● melhor da linha · ⚠
                  red flag de leitura combinada
                </p>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
