"use client"

// /bi/comparador — Comparador de FIDCs por indicadores (ate 10 fundos).
//
// Opcao A da reorganizacao do grupo Benchmark (aprovada 2026-06-11):
//   Panorama = mercado · Fundos = explorador · COMPARADOR = confronto.
// Cesta de 17 indicadores (docs/cvm-fidc/indicadores-benchmarking.md), cada
// valor com percentil no universo da competencia; mediana do mercado como
// competidor implicito de toda linha.
//
// 2026-07-20 (Ricardo): teto 3 -> 10 fundos · "Score por dimensao" (radar)
// REMOVIDO — a matriz passa a ocupar a largura inteira, com a coluna do
// indicador congelada (stickyFirstColumn) porque 10 colunas exigem scroll-x ·
// favoritos por usuario plugados (estrela no chip + secao no picker + botao
// "Carregar favoritos"), reusando `components/bi/favoritos`.
//
// Arquitetura (CLAUDE.md §11.6): L1 BI > L2 Benchmark > Comparador.
// Estado deep-linkavel: ?fundos=cnpj1,cnpj2,cnpj3&comp=YYYY-MM-DD (nuqs).
//
// MOTIVO (pattern): nao e dashboard nem listagem — e ferramenta de confronto
// (matriz transposta). Composicao direta sobre design-system/components,
// shell visual do benchmark2/cota-sub (title row + toolbar + conteudo).

import * as React from "react"
import { RiScales3Line, RiStarFill } from "@remixicon/react"
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
import { useFavoritos } from "@/components/bi/favoritos"
import { biBenchmarkIndicadores } from "@/lib/api-client"

import {
  ComparadorFundoPicker,
  type FundoSelecionado,
} from "./_components/ComparadorFundoPicker"
import { MatrizIndicadores } from "./_components/MatrizIndicadores"

// Par do `_MAX_FUNDOS` em `backend/app/modules/bi/api/benchmark_indicadores.py`
// — subir aqui sem subir la faz a API rejeitar a request com 422.
const MAX_FUNDOS = 10

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

  // Atalho "Carregar favoritos": completa os slots livres com os favoritos do
  // usuario que ainda nao estao no comparador, respeitando o teto.
  const { favoritos } = useFavoritos()
  const favoritosForaDoComparador = favoritos.filter(
    (f) => !cnpjs.includes(f.cnpj),
  )
  const vagas = MAX_FUNDOS - cnpjs.length
  const carregarFavoritos = () => {
    const aAdicionar = favoritosForaDoComparador.slice(0, vagas).map((f) => f.cnpj)
    if (aAdicionar.length === 0) return
    setNomes((prev) => {
      const next = { ...prev }
      for (const f of favoritosForaDoComparador.slice(0, vagas)) {
        if (f.denom_social) next[f.cnpj] = f.denom_social
      }
      return next
    })
    void setFundosCsv([...cnpjs, ...aAdicionar].join(","))
  }

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col overflow-hidden">
      {/* Title row */}
      <div className="shrink-0 bg-white px-6 pt-3.5 pb-3 dark:bg-gray-950">
        <PageHeader
          title="Comparador de FIDCs"
          subtitle="BI · Benchmark"
          info="Confronto de até 10 fundos pela cesta de 17 indicadores derivada dos Informes Mensais CVM (dado público). Cada valor traz o percentil no universo da competência (p100 = melhor, já na direção do indicador); a mediana do mercado entra como competidor implícito em todas as linhas. Semântica validada empiricamente — ver docs/cvm-fidc/indicadores-benchmarking.md."
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

          {favoritosForaDoComparador.length > 0 && vagas > 0 && (
            <button
              type="button"
              onClick={carregarFavoritos}
              className="flex h-[30px] shrink-0 items-center gap-1.5 rounded border border-gray-300 px-2.5 text-[13px] font-medium text-gray-700 transition-colors hover:border-gray-400 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-200 dark:hover:border-gray-600 dark:hover:bg-gray-900"
              title={`Adiciona ${Math.min(favoritosForaDoComparador.length, vagas)} fundo(s) favorito(s) ao comparador`}
            >
              <RiStarFill
                className="size-3.5 text-blue-500 dark:text-blue-400"
                aria-hidden="true"
              />
              Carregar favoritos (
              {Math.min(favoritosForaDoComparador.length, vagas)})
            </button>
          )}

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
            description="Adicione até 10 FIDCs pela busca acima — ou carregue seus favoritos. Cada indicador vem com o percentil do fundo no universo CVM da competência, e a mediana do mercado entra como referência em todas as linhas."
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
                <MatrizIndicadores
                  fundos={data.fundos}
                  mediana={data.mediana}
                  composicaoMediana={data.composicao_mediana}
                  direcao={data.direcao}
                />
                <p className="text-[11px] text-gray-400 dark:text-gray-500">
                  Fonte: Informes Mensais FIDC · CVM dados abertos
                  (public:cvm_fidc) · competência{" "}
                  {labelCompetencia(data.competencia)}
                  {data.competencia_anterior && (
                    <>
                      {" "}
                      · movimento do PL vs{" "}
                      {labelCompetencia(data.competencia_anterior)}
                    </>
                  )}{" "}
                  · pN = percentil no universo, orientado (100 = melhor) · ●
                  melhor da linha · ⚠ red flag de leitura combinada · Variação
                  do PL não tem percentil nem mediana
                </p>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
