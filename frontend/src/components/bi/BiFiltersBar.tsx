"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"

import { Button } from "@/components/tremor/Button"
import { FilterPill } from "@/components/app/FilterPill"
import {
  MonthRangePicker,
  type MonthRange,
} from "@/components/app/MonthRangePicker"
import { PeriodoPresets } from "@/components/app/PeriodoPresets"
import { cx } from "@/lib/utils"
import { biMetadata } from "@/lib/api-client"
import { useBiFilters } from "@/lib/hooks/useBiFilters"

// Produtos e UAs: taxonomias vem da API (`/bi/metadata/*`), populadas por
// ETL do adapter Bitfin em `wh_dim_produto` / `wh_dim_unidade_administrativa`.
// Zero hardcode — novo produto cadastrado no ERP aparece automaticamente
// apos o proximo sync.

function toISO(d?: Date): string | undefined {
  if (!d) return undefined
  const yyyy = d.getFullYear()
  const mm = String(d.getMonth() + 1).padStart(2, "0")
  const dd = String(d.getDate()).padStart(2, "0")
  return `${yyyy}-${mm}-${dd}`
}

function fromISO(s?: string): Date | undefined {
  if (!s) return undefined
  const [y, m, d] = s.split("-").map(Number)
  return new Date(y, m - 1, d)
}

type BiFiltersBarProps = {
  /**
   * - `"sticky"` (legado): barra com `border-b` e fundo `bg-white`,
   *   pensada para posicao fixa abaixo do header global.
   * - `"inline"` (novo default, Tremor-style): sem borda, sem fundo proprio,
   *   renderiza diretamente dentro do conteudo da aba acima dos charts.
   */
  variant?: "sticky" | "inline"
  className?: string
}

/**
 * Barra de filtros globais do modulo BI.
 * Layout:
 *   [ YTD · 3M · 6M · 12M* · 24M · 36M · ALL ]  [📅 picker]  [Produto] [UA]  [Limpar]
 *
 * Regra de periodo:
 *  - Default: `12m` (quando URL nao tem preset nem periodo explicito).
 *  - Clicar num preset: aplica range rolling e limpa qualquer periodo custom.
 *  - Editar no DateRangePicker: sai do preset, entra em modo custom.
 */
export function BiFiltersBar({
  variant = "inline",
  className,
}: BiFiltersBarProps = {}) {
  // Data minima de operacao do tenant — usada para computar o preset 'ALL'.
  // Cache longo (6h) — so muda com ETL trazendo operacao retroativa.
  const dataMinimaQuery = useQuery({
    queryKey: ["bi", "metadata", "data-minima"],
    queryFn: () => biMetadata.dataMinima(),
    staleTime: 6 * 60 * 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })
  const dataMinima = dataMinimaQuery.data?.data_minima ?? undefined

  const { filters, preset, setFilter, resetFilters } = useBiFilters(dataMinima)

  // UAs ativas do tenant — taxonomia, muda raramente: cache longo (1h).
  const uasQuery = useQuery({
    queryKey: ["bi", "metadata", "uas"],
    queryFn: () => biMetadata.uas(),
    staleTime: 60 * 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })

  // Produtos do tenant (com operacoes).
  const produtosQuery = useQuery({
    queryKey: ["bi", "metadata", "produtos"],
    queryFn: () => biMetadata.produtos(),
    staleTime: 60 * 60 * 1000,
    gcTime: 24 * 60 * 60 * 1000,
  })

  const uaOptions = React.useMemo(
    () =>
      (uasQuery.data ?? []).map((u) => ({
        value: String(u.id),
        label: u.nome,
      })),
    [uasQuery.data],
  )

  // Opcoes do dropdown "Produto" — formato "Nome completo (SIGLA)".
  // Sigla continua sendo a chave usada em `BIFilters.produtoSigla`.
  const produtoOptions = React.useMemo(
    () =>
      (produtosQuery.data ?? []).map((p) => ({
        value: p.sigla,
        label: `${p.nome} (${p.sigla})`,
      })),
    [produtosQuery.data],
  )

  const range: MonthRange = {
    from: fromISO(filters.periodoInicio),
    to: fromISO(filters.periodoFim),
  }

  const produtoValue = filters.produtoSigla ?? []
  const uaValue = (filters.uaId ?? []).map(String)

  const hasCategoricalFilters = produtoValue.length > 0 || uaValue.length > 0

  return (
    <div
      className={cx(
        "flex flex-wrap items-center gap-2",
        variant === "sticky" &&
          "border-b border-gray-200 bg-white px-6 py-3 dark:border-gray-800 dark:bg-gray-950",
        variant === "inline" && "py-2",
        className,
      )}
    >
      <PeriodoPresets
        value={preset}
        onChange={(p) => setFilter({ preset: p })}
      />

      <MonthRangePicker
        value={range}
        onChange={(v) => {
          // Aplicar no picker tira do modo preset (useBiFilters limpa o
          // preset automaticamente quando periodoInicio/Fim vem no patch).
          setFilter({
            periodoInicio: toISO(v?.from),
            periodoFim: toISO(v?.to),
          })
        }}
      />

      <FilterPill
        title="Produto"
        options={produtoOptions}
        value={produtoValue}
        onChange={(next) =>
          setFilter({ produtoSigla: next.length > 0 ? next : undefined })
        }
      />

      <FilterPill
        title="UA"
        options={uaOptions}
        value={uaValue}
        onChange={(next) =>
          setFilter({
            uaId:
              next.length > 0
                ? next.map((x) => Number(x)).filter((n) => Number.isFinite(n))
                : undefined,
          })
        }
      />

      {/* Sempre visivel (evita layout shift) — desabilitado quando nao ha filtro. */}
      <Button
        variant="ghost"
        onClick={resetFilters}
        disabled={!hasCategoricalFilters}
        className="font-semibold text-blue-600 disabled:text-gray-400 dark:text-blue-400 dark:disabled:text-gray-600"
      >
        Limpar filtros
      </Button>
    </div>
  )
}
