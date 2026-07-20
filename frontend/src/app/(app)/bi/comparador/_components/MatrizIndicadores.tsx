"use client"

// Matriz do Comparador: linhas = 17 indicadores (agrupados por dimensao),
// colunas = ate 10 fundos + mediana do universo. Cada celula traz o VALOR +
// percentil no universo (p0-100, orientado: 100 = melhor). ● marca o melhor
// da linha; ⚠ marca red flag de leitura combinada.
//
// DataTable canonica (density compact) com linhas de secao via tipo proprio —
// mesma mecanica das tabelas hierarquicas (§6).

import * as React from "react"
import {
  RiAlertFill,
  RiArrowDownSLine,
  RiArrowRightSLine,
  RiInformationLine,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import { Badge } from "@/components/tremor/Badge"
import { Card } from "@/components/tremor/Card"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"
import type { ComparadorIndicadoresFundo } from "@/lib/api-client"

import {
  COMPOSICAO_BUCKETS,
  pctDaComposicao,
  type ComposicaoBucket,
  type ComposicaoFolha,
} from "./composicao"
import {
  GRUPOS,
  INDICADORES,
  formatIndicador,
  rankOrientado,
  type IndicadorDef,
} from "./indicadores"

type Linha =
  | { tipo: "secao"; label: string }
  | { tipo: "indicador"; def: IndicadorDef }
  | { tipo: "comp_bucket"; bucket: ComposicaoBucket }
  | { tipo: "comp_folha"; bucketKey: string; folha: ComposicaoFolha }
  | { tipo: "comp_total" }

// Grupo onde a decomposicao do ativo (que fecha em 100%) e injetada — abre o
// grupo, com os ratios soltos (% em DC, liquidez) logo abaixo.
const GRUPO_COMPOSICAO = "Perfil do ativo"

function montarLinhas(expandidos: Set<string>): Linha[] {
  const linhas: Linha[] = []
  for (const grupo of GRUPOS) {
    linhas.push({ tipo: "secao", label: grupo })
    if (grupo === GRUPO_COMPOSICAO) {
      for (const bucket of COMPOSICAO_BUCKETS) {
        linhas.push({ tipo: "comp_bucket", bucket })
        if (expandidos.has(bucket.key)) {
          for (const folha of bucket.folhas) {
            linhas.push({ tipo: "comp_folha", bucketKey: bucket.key, folha })
          }
        }
      }
      linhas.push({ tipo: "comp_total" })
    }
    for (const def of INDICADORES.filter((i) => i.grupo === grupo)) {
      linhas.push({ tipo: "indicador", def })
    }
  }
  return linhas
}

/** % total da composicao de um fundo (soma dos buckets ÷ ativo) — deve dar 100%
 * por construcao; se divergir, o residuo aparece (zero ocultacao §14.6). */
function pctTotalComposicao(fundo: ComparadorIndicadoresFundo): number | null {
  if (!fundo.ativo_total || fundo.ativo_total <= 0) return null
  const soma = COMPOSICAO_BUCKETS.reduce(
    (acc, b) => acc + (fundo.composicao_ativo?.[b.key] ?? 0),
    0,
  )
  return (100 * soma) / fundo.ativo_total
}

/** Red flags de leitura combinada (retorna tooltip ou null). */
function redFlag(
  def: IndicadorDef,
  fundo: ComparadorIndicadoresFundo,
): string | null {
  if (def.key === "recompra_dc_pct") {
    const rec = fundo.recompra_dc_pct_rank
    const inad = fundo.inad_total_pct_rank
    if (rec !== null && inad !== null && rec >= 80 && inad <= 30) {
      return "Recompra alta com inadimplência baixa — cedente pode estar recomprando o atraso antes de aparecer (red flag clássico de agência)"
    }
  }
  if (def.key === "cobertura_pdd_pct") {
    const v = fundo.cobertura_pdd_pct
    if (v !== null && v < 100) {
      return "Provisão cobre menos de 100% dos inadimplentes"
    }
  }
  return null
}

/** A partir daqui a coluna fica estreita demais para o formato folgado. */
const LIMIAR_COMPACTO = 5

function CelulaFundo({
  def,
  fundo,
  direcao,
  melhor,
  compacto,
}: {
  def: IndicadorDef
  fundo: ComparadorIndicadoresFundo
  direcao: Record<string, boolean>
  melhor: boolean
  /** Muitos fundos na tela: encurta valor e percentil para caber sem rolagem. */
  compacto: boolean
}) {
  const valor = fundo[def.key]
  const rank = fundo[`${def.key}_rank` as keyof ComparadorIndicadoresFundo]
  const orientado = rankOrientado(
    typeof rank === "number" ? rank : null,
    direcao[def.key],
  )
  const flag = redFlag(def, fundo)
  // Categoricos (ex.: Condominio) viram Badge — Aberto em azul (atencao:
  // resgate a qualquer tempo) e demais em cinza neutro.
  if (def.fmt === "texto") {
    if (typeof valor !== "string" || !valor) {
      return <div className={cx("text-right", tableTokens.cellMuted)}>—</div>
    }
    return (
      <div className="flex justify-end">
        <Badge variant={valor === "Aberto" ? "default" : "neutral"}>
          {valor}
        </Badge>
      </div>
    )
  }
  const texto = formatIndicador(
    typeof valor === "number" || typeof valor === "string" ? valor : null,
    def.fmt,
  )
  // Em coluna estreita o prefixo "R$ " e o que menos informa (o rotulo da
  // linha ja diz que e valor) — sai primeiro para o numero nao truncar.
  const textoFinal =
    compacto && def.fmt === "brl" ? texto.replace(/^R\$\s*/, "") : texto

  return (
    <div
      className={cx(
        "flex items-baseline justify-end whitespace-nowrap",
        compacto ? "gap-1" : "gap-1.5",
      )}
    >
      {flag && (
        <span title={flag}>
          <RiAlertFill
            className="size-3 self-center text-amber-500"
            aria-hidden="true"
          />
        </span>
      )}
      {melhor && (
        <span
          className="size-1.5 self-center rounded-full bg-blue-500"
          title="Melhor da linha"
          aria-hidden="true"
        />
      )}
      <span
        className={cx(
          tableTokens.cellNumber,
          melhor && "font-semibold",
          // Trunca em vez de estourar a coluna elastica.
          "min-w-0 truncate",
        )}
        title={texto}
      >
        {textoFinal}
      </span>
      {orientado !== null && (
        <span
          className={cx(
            "shrink-0 text-left tabular-nums",
            compacto ? "w-6" : "w-8",
            tableTokens.cellMuted,
          )}
          title={`Percentil ${Math.round(orientado)} de 100 no universo (orientado: 100 = melhor)`}
        >
          p{Math.round(orientado)}
        </span>
      )}
    </div>
  )
}

/** Celula de composicao do ativo (% que fecha em 100% por fundo). Sem
 * percentil/marcador — e decomposicao, nao ratio benchmarkado. */
function CelulaComposicao({
  pct,
  folha,
  forte,
}: {
  pct: number | null
  folha?: boolean
  forte?: boolean
}) {
  const tom = forte
    ? cx(tableTokens.cellNumber, "font-semibold")
    : folha
      ? tableTokens.cellNumberSecondary
      : tableTokens.cellNumber
  return (
    <div className={cx("text-right tabular-nums", tom)}>
      {pct === null ? "—" : formatIndicador(pct, "pct2")}
    </div>
  )
}

export function MatrizIndicadores({
  fundos,
  mediana,
  composicaoMediana,
  direcao,
}: {
  fundos: ComparadorIndicadoresFundo[]
  mediana: Record<string, number | null>
  composicaoMediana: Record<string, number | null>
  direcao: Record<string, boolean>
}) {
  // Buckets da composicao expandidos (drill -> folhas). Vazio = so buckets.
  const [expandidos, setExpandidos] = React.useState<Set<string>>(new Set())
  const toggleBucket = React.useCallback((key: string) => {
    setExpandidos((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  const linhas = React.useMemo(() => montarLinhas(expandidos), [expandidos])

  // Melhor da linha (na direcao do indicador) — so quando ha 2+ fundos.
  const melhorPorIndicador = React.useMemo(() => {
    const out = new Map<string, string>()
    if (fundos.length < 2) return out
    for (const def of INDICADORES) {
      // `neutro`: maior nao e inequivocamente melhor (ex.: variacao do PL —
      // encolher pode ser amortizacao programada). Sem marcador de melhor.
      if (def.neutro) continue
      const candidatos = fundos
        .map((f) => ({ cnpj: f.cnpj, v: f[def.key] }))
        .filter((c): c is { cnpj: string; v: number } => typeof c.v === "number")
      if (candidatos.length < 2) continue
      const maior = direcao[def.key] !== false
      candidatos.sort((a, b) => (maior ? b.v - a.v : a.v - b.v))
      out.set(def.key, candidatos[0].cnpj)
    }
    return out
  }, [fundos, direcao])

  const columns = React.useMemo(() => {
    const col = createColumnHelper<Linha>()
    const defs: ColumnDef<Linha, unknown>[] = [
      col.display({
        id: "indicador",
        header: "Indicador",
        // Com tableLayout="fixed" este `size` e largura REAL. As colunas de
        // fundo NAO declaram size — dividem o resto em partes iguais, entao
        // 10 fundos cabem sem rolagem (CLAUDE.md §6 / prop tableLayout).
        // 224px: medido para o rotulo mais longo com formula
        // ("Subordinação total (Jr+Mez)/PL") nao encostar na borda.
        size: 224,
        cell: (info) => {
          const row = info.row.original
          if (row.tipo === "secao") {
            return <span className={tableTokens.header}>{row.label}</span>
          }
          if (row.tipo === "comp_bucket") {
            const aberto = expandidos.has(row.bucket.key)
            const Chevron = aberto ? RiArrowDownSLine : RiArrowRightSLine
            return (
              <button
                type="button"
                onClick={() => toggleBucket(row.bucket.key)}
                className="flex items-center gap-1 whitespace-nowrap text-left"
                title={aberto ? "Recolher" : "Ver detalhe"}
              >
                <Chevron
                  className="size-3.5 shrink-0 text-gray-400 dark:text-gray-500"
                  aria-hidden="true"
                />
                <span className={tableTokens.cellText}>{row.bucket.label}</span>
              </button>
            )
          }
          if (row.tipo === "comp_folha") {
            return (
              <span className="flex whitespace-nowrap pl-[18px]">
                <span className={tableTokens.cellSecondary}>
                  {row.folha.label}
                </span>
              </span>
            )
          }
          if (row.tipo === "comp_total") {
            return (
              <span className={cx(tableTokens.cellStrong, "whitespace-nowrap")}>
                Total do Ativo
              </span>
            )
          }
          return (
            <span className="flex items-baseline gap-1.5 whitespace-nowrap">
              <span className={tableTokens.cellText}>{row.def.label}</span>
              {row.def.formula && (
                <span className={cx("tabular-nums", tableTokens.cellMuted)}>
                  {row.def.formula}
                </span>
              )}
              <span title={row.def.info} className="self-center">
                <RiInformationLine
                  className="size-3 text-gray-300 dark:text-gray-600"
                  aria-hidden="true"
                />
              </span>
            </span>
          )
        },
      }) as ColumnDef<Linha, unknown>,
      ...fundos.map(
        (fundo, idx) =>
          col.display({
            id: `fundo_${idx}`,
            // Nome TRUNCADO na largura da coluna (que agora e elastica —
            // sem w-[] fixo, senao volta a esticar a tabela). Tooltip mostra
            // o nome completo.
            header: () => {
              const nome = fundo.denom_social ?? fundo.cnpj
              return (
                <span className="block truncate" title={nome}>
                  {nome}
                </span>
              )
            },
            // SEM `size`: divide o espaco restante igualmente entre os fundos.
            meta: { align: "right" },
            cell: (info) => {
              const row = info.row.original
              if (row.tipo === "secao") return null
              if (row.tipo === "comp_bucket") {
                return (
                  <CelulaComposicao
                    pct={pctDaComposicao(
                      fundo.composicao_ativo,
                      fundo.ativo_total,
                      row.bucket.key,
                    )}
                  />
                )
              }
              if (row.tipo === "comp_folha") {
                return (
                  <CelulaComposicao
                    pct={pctDaComposicao(
                      fundo.composicao_ativo,
                      fundo.ativo_total,
                      row.folha.key,
                    )}
                    folha
                  />
                )
              }
              if (row.tipo === "comp_total") {
                return <CelulaComposicao pct={pctTotalComposicao(fundo)} forte />
              }
              return (
                <CelulaFundo
                  def={row.def}
                  fundo={fundo}
                  direcao={direcao}
                  melhor={melhorPorIndicador.get(row.def.key) === fundo.cnpj}
                  compacto={fundos.length > LIMIAR_COMPACTO}
                />
              )
            },
          }) as ColumnDef<Linha, unknown>,
      ),
      col.display({
        id: "mediana",
        header: () => (
          <span
            className="block truncate"
            title="Mediana do universo CVM na competência"
          >
            Mediana
          </span>
        ),
        size: 104,
        meta: { align: "right" },
        cell: (info) => {
          const row = info.row.original
          if (row.tipo === "secao") return null
          if (row.tipo === "comp_total") {
            return (
              <div className={cx("text-right", tableTokens.cellNumberSecondary)}>
                100,00%
              </div>
            )
          }
          if (row.tipo === "comp_bucket" || row.tipo === "comp_folha") {
            const key =
              row.tipo === "comp_bucket" ? row.bucket.key : row.folha.key
            return (
              <div className={cx("text-right", tableTokens.cellNumberSecondary)}>
                {formatIndicador(composicaoMediana[key] ?? null, "pct2")}
              </div>
            )
          }
          // Mesmo encurtamento das celulas de fundo (sem "R$ "), senao a
          // coluna Mediana destoa da linha inteira.
          const txt = formatIndicador(mediana[row.def.key] ?? null, row.def.fmt)
          return (
            <div className={cx("text-right", tableTokens.cellNumberSecondary)}>
              {fundos.length > LIMIAR_COMPACTO && row.def.fmt === "brl"
                ? txt.replace(/^R\$\s*/, "")
                : txt}
            </div>
          )
        },
      }) as ColumnDef<Linha, unknown>,
    ]
    return defs
  }, [
    fundos,
    mediana,
    composicaoMediana,
    direcao,
    melhorPorIndicador,
    expandidos,
    toggleBucket,
  ])

  return (
    <Card className={tableTokens.cardWrapper}>
      <DataTable
        data={linhas}
        columns={columns}
        density="compact"
        showColumnManager={false}
        showDensityToggle={false}
        showExport={false}
        virtualize={false}
        // "fixed": as colunas de fundo (sem `size`) dividem o espaco restante,
        // entao 10 fundos CABEM sem rolagem — pedido do Ricardo, 2026-07-20.
        tableLayout="fixed"
        // Piso: abaixo disso a coluna de fundo ficaria ilegivel, entao a
        // tabela volta a rolar em vez de esmagar os numeros. 224 (indicador)
        // + 104 (mediana) + 96 por fundo.
        tableMinWidth={328 + fundos.length * 96}
        // So tem efeito quando o piso acima e acionado (tela estreita): sem a
        // coluna do indicador congelada a matriz vira grade sem legenda.
        stickyFirstColumn
        rowClassName={(row) =>
          row.tipo === "secao"
            ? "bg-gray-50 dark:bg-gray-900/60 border-t-gray-200 dark:border-t-gray-800"
            : row.tipo === "comp_total"
              ? "border-t-gray-200 dark:border-t-gray-800"
              : ""
        }
      />
    </Card>
  )
}
