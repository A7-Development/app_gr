// src/app/(app)/controladoria/conciliacao/banco-cobrador/page.tsx
//
// Controladoria · Conciliacao · Banco Cobrador (Entrega 3, item 2).
// Cruza a carteira Bitfin (titulos abertos elegiveis a boleto) x boletos
// ativos dos bancos cobradores (retorno CNAB).
//
// Pattern: DashboardBiPadrao (composicao direta, anatomy de /bi/panorama):
//   Z1 PageHeader + DashboardHeaderActions
//   Z2 Toolbar de filtros globais: Data-base · Status · Banco · Produto ·
//      Cedente (esquerda->direita: escopo -> mais granular)
//   Z3 KpiStrip (resumo do dia) + DataTable canonica titulo-a-titulo
//      (a busca por palavra mora DENTRO do card da tabela)
//   Z4 ProvenanceFooter
// Lateral: AIPanel.
//
// data_ref e o escopo (re-fetcha o dia). Status/Banco/Produto/Cedente sao
// lentes client-side sobre as linhas do dia; o KpiStrip mostra o resumo do
// DIA INTEIRO (visao geral), nao reage aos chips. Exclusoes de tenant (ex.:
// Pedreira so-CBV) saem desses filtros (backend expoe cedente_documento).

"use client"

import * as React from "react"
import {
  RiBankLine,
  RiBriefcase2Line,
  RiBuilding2Line,
  RiCalendarLine,
  RiCheckLine,
  RiFilter3Line,
  RiInboxArchiveLine,
  RiPriceTag3Line,
  type RemixiconComponentType,
} from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import { PageHeader } from "@/design-system/components/PageHeader"
import { DashboardHeaderActions } from "@/design-system/components/DashboardHeaderActions"
import { FilterChip } from "@/design-system/components/FilterBar"
import { EmptyState } from "@/design-system/components/EmptyState"
import { AIPanel, useAIPanel } from "@/design-system/components/AIPanel"
import { cardTokens } from "@/design-system/tokens/card"
import { ProvenanceFooter } from "@/components/bi/ProvenanceFooter"
import { useScrollShadow } from "@/lib/hooks/use-scroll-shadow"
import {
  useConciliacaoBancoCobrador,
  useConciliacaoBancoCobradorDatas,
} from "@/lib/hooks/controladoria"
import type {
  LinhaConciliacaoBoleto,
  ResumoStatusConciliacao,
  StatusConciliacaoBoleto,
} from "@/lib/api-client"

import { ConciliacaoBoletoTable } from "./_components/ConciliacaoBoletoTable"
import { ResumoConciliacaoTable } from "./_components/ResumoConciliacaoTable"

const fmtInt = new Intl.NumberFormat("pt-BR")

function fmtDateBR(iso: string | null | undefined): string {
  if (!iso) return "—"
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[3]}/${m[2]}/${m[1].slice(2)}` : iso
}

const STATUS_OPTS: { value: StatusConciliacaoBoleto; label: string }[] = [
  { value: "conciliado",             label: "Conciliado" },
  { value: "divergencia_valor",      label: "Divergência de valor" },
  { value: "divergencia_vencimento", label: "Divergência de vencimento" },
  { value: "so_em_bitfin",           label: "Só em BITFIN" },
  { value: "so_em_banco",            label: "Só em banco" },
]

const capitalize = (s: string) => s.charAt(0).toUpperCase() + s.slice(1)

function distinctOpts(
  linhas: LinhaConciliacaoBoleto[] | undefined,
  get: (l: LinhaConciliacaoBoleto) => string | null,
  fmt?: (v: string) => string,
): { value: string; label: string }[] {
  const set = new Set<string>()
  for (const l of linhas ?? []) {
    const v = get(l)
    if (v) set.add(v)
  }
  return Array.from(set)
    .sort((a, b) => a.localeCompare(b, "pt-BR"))
    .map((v) => ({ value: v, label: fmt ? fmt(v) : v }))
}

// Resumo consolidado por status, computado das linhas NO ESCOPO (UA) — assim o
// resumo reflete a UA selecionada (escopo), sem reagir aos demais filtros
// (lentes). Percentual sobre o total de linhas no escopo.
function computeResumo(linhas: LinhaConciliacaoBoleto[]): ResumoStatusConciliacao[] {
  const total = linhas.length || 1
  const agg = new Map<StatusConciliacaoBoleto, { q: number; vb: number; vbanco: number }>()
  for (const l of linhas) {
    const a = agg.get(l.status) ?? { q: 0, vb: 0, vbanco: 0 }
    a.q += 1
    a.vb += l.valor_bitfin ?? 0
    a.vbanco += l.valor_banco ?? 0
    agg.set(l.status, a)
  }
  return Array.from(agg.entries()).map(([status, a]) => ({
    status,
    quantidade: a.q,
    percentual: Math.round((a.q * 1000) / total) / 10,
    valor_bitfin: a.vb,
    valor_banco: a.vbanco,
    diferenca: a.vbanco - a.vb,
  }))
}

export default function ConciliacaoBancoCobradorPage() {
  const ai = useAIPanel()
  const [scrollRef, scrolled] = useScrollShadow<HTMLDivElement>()

  const datasQuery = useConciliacaoBancoCobradorDatas()
  const datas = React.useMemo(() => datasQuery.data ?? [], [datasQuery.data])

  const [dataRef, setDataRef] = React.useState<string | null>(null)
  React.useEffect(() => {
    if (dataRef === null && datas.length > 0) setDataRef(datas[0])
  }, [datas, dataRef])

  // ESCOPO (UA) — define a conciliacao que se ve; o resumo reflete. LENTES
  // (status/banco/produto/cedente) filtram so o detalhe, nao o resumo.
  const [uaFilter, setUaFilter] = React.useState<string | null>(null)
  const [statusFilter, setStatusFilter] = React.useState<StatusConciliacaoBoleto | null>(null)
  const [bancoFilter, setBancoFilter] = React.useState<string | null>(null)
  const [produtoFilter, setProdutoFilter] = React.useState<string | null>(null)
  const [cedenteFilter, setCedenteFilter] = React.useState<string | null>(null)

  const q = useConciliacaoBancoCobrador(dataRef)
  const conc = q.data

  // Opcoes dos chips derivadas das linhas do dia.
  const uaOpts = React.useMemo(
    () => distinctOpts(conc?.linhas, (l) => l.ua_nome),
    [conc],
  )
  const bancoOpts = React.useMemo(
    () => distinctOpts(conc?.linhas, (l) => l.banco, capitalize),
    [conc],
  )
  const produtoOpts = React.useMemo(
    () => distinctOpts(conc?.linhas, (l) => l.produto),
    [conc],
  )
  const cedenteOpts = React.useMemo(
    () => distinctOpts(conc?.linhas, (l) => l.cedente_documento),
    [conc],
  )

  // Escopo: linhas filtradas SO pela UA. Alimenta o resumo (que reflete a UA).
  // Nota: linhas "só em banco" ficam sem UA ate o boleto carregar UA do header
  // CNAB; com UA especifica selecionada elas saem do escopo (interim).
  const linhasNoEscopo = React.useMemo(() => {
    if (!conc) return []
    if (uaFilter === null) return conc.linhas
    return conc.linhas.filter((l) => l.ua_nome === uaFilter)
  }, [conc, uaFilter])

  const resumoEscopo = React.useMemo(() => computeResumo(linhasNoEscopo), [linhasNoEscopo])

  // Detalhe: escopo + lentes.
  const linhasFiltradas = React.useMemo(() => {
    return linhasNoEscopo.filter(
      (l) =>
        (statusFilter === null || l.status === statusFilter) &&
        (bancoFilter === null || l.banco === bancoFilter) &&
        (produtoFilter === null || l.produto === produtoFilter) &&
        (cedenteFilter === null || l.cedente_documento === cedenteFilter),
    )
  }, [linhasNoEscopo, statusFilter, bancoFilter, produtoFilter, cedenteFilter])

  const handleShare = React.useCallback(() => {
    void navigator.clipboard?.writeText(window.location.href)
  }, [])

  const handleExport = React.useCallback(() => {
    // eslint-disable-next-line no-console
    console.log("export conciliacao", { dataRef })
  }, [dataRef])

  const aiContext = React.useMemo(
    () => ({
      page: "Controladoria · Conciliação · Banco Cobrador",
      period: dataRef ? fmtDateBR(dataRef) : "—",
      filters: [
        uaFilter && `UA: ${uaFilter}`,
        statusFilter && `Status: ${STATUS_OPTS.find((s) => s.value === statusFilter)?.label}`,
        bancoFilter && `Banco: ${capitalize(bancoFilter)}`,
        produtoFilter && `Produto: ${produtoFilter}`,
        cedenteFilter && `Cedente: ${cedenteFilter}`,
      ].filter(Boolean).join(", ") || "Nenhum",
    }),
    [dataRef, uaFilter, statusFilter, bancoFilter, produtoFilter, cedenteFilter],
  )

  const semDatas = !datasQuery.isLoading && datas.length === 0

  return (
    <div className="flex h-[calc(100vh-3rem)] overflow-hidden">
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        {/* Z1 — Title row */}
        <div className="shrink-0 bg-white px-6 pt-3.5 pb-3 dark:bg-gray-950">
          <PageHeader
            title="Banco Cobrador"
            info="Conciliação da carteira Bitfin (títulos em aberto elegíveis a boleto: FAT/CBV/DMS/CBS) com os boletos ativos dos bancos cobradores (retorno CNAB). Cruzamento título-a-título por número do documento; valor comparado = valor líquido; vencimento tz-aware (São Paulo)."
            subtitle={
              conc
                ? `Data-base ${fmtDateBR(conc.data_ref)} · ${fmtInt.format(conc.boletos_ativos)} boletos ativos`
                : "Controladoria · Conciliações"
            }
            actions={
              <DashboardHeaderActions
                ai={{ open: ai.open, onToggle: ai.toggle }}
                onShare={handleShare}
                onExport={handleExport}
              />
            }
          />
        </div>

        {/* Z2 — Toolbar de filtros globais */}
        <div
          className={cx(
            "shrink-0 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
            scrolled && "scroll-shadow",
          )}
        >
          <div className="flex min-h-[52px] flex-wrap items-center gap-2 px-6 py-2">
            <FilterChip
              label="Data-base"
              value={fmtDateBR(dataRef)}
              active={dataRef !== null}
              icon={RiCalendarLine}
            >
              <div className="max-h-72 w-44 overflow-y-auto py-1">
                {datas.length === 0 && (
                  <div className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400">
                    Sem datas disponíveis
                  </div>
                )}
                {datas.map((d) => (
                  <OptionBtn
                    key={d}
                    label={fmtDateBR(d)}
                    selected={d === dataRef}
                    onClick={() => setDataRef(d)}
                    mono
                  />
                ))}
              </div>
            </FilterChip>

            <SelectChip
              label="UA"
              icon={RiBriefcase2Line}
              options={uaOpts}
              value={uaFilter}
              onChange={setUaFilter}
            />

            <span className="h-5 w-px shrink-0 bg-gray-200 dark:bg-gray-800" aria-hidden="true" />

            <SelectChip
              label="Status"
              icon={RiFilter3Line}
              options={STATUS_OPTS}
              value={statusFilter}
              onChange={(v) => setStatusFilter(v as StatusConciliacaoBoleto | null)}
            />
            <SelectChip
              label="Banco"
              icon={RiBankLine}
              options={bancoOpts}
              value={bancoFilter}
              onChange={setBancoFilter}
            />
            <SelectChip
              label="Produto"
              icon={RiPriceTag3Line}
              options={produtoOpts}
              value={produtoFilter}
              onChange={setProdutoFilter}
            />
            <SelectChip
              label="Cedente"
              icon={RiBuilding2Line}
              options={cedenteOpts}
              value={cedenteFilter}
              onChange={setCedenteFilter}
            />

            <span className="ml-auto shrink-0 text-[11px] text-gray-500 dark:text-gray-400">
              {q.isFetching ? "Atualizando…" : "Atualizado"}
            </span>
          </div>
        </div>

        {/* Z3 — Conteudo */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4">
          {semDatas ? (
            <EmptyState
              icon={RiInboxArchiveLine}
              title="Nenhum retorno de boleto ingerido ainda"
              description="Configure a fonte de cobrança (pasta de retornos CNAB) e rode o sync. Assim que houver boletos, a conciliação do dia aparece aqui."
              className="mt-6"
            />
          ) : (
            <div className="flex flex-col gap-4">
              {/* Tabela-resumo no ESCOPO da UA (reage so a UA, nao as lentes) —
                  Entrega 3 §2. Substitui o KpiStrip; reconcilia (§14.6). */}
              <ResumoConciliacaoTable resumo={resumoEscopo} />

              {/* DataTable — filtrada pelos chips + busca */}
              {q.isError ? (
                <Card className={cx(cardTokens.body, "py-12 text-center")}>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Não foi possível carregar a conciliação.
                  </p>
                </Card>
              ) : linhasFiltradas.length === 0 && !q.isLoading ? (
                <EmptyState
                  icon={RiCheckLine}
                  title="Nada com estes filtros"
                  description="Nenhum título atende aos filtros nesta data-base. Ajuste ou limpe os filtros."
                  className="mt-4"
                />
              ) : (
                <ConciliacaoBoletoTable linhas={linhasFiltradas} />
              )}
            </div>
          )}
        </div>

        {/* Z4 — ProvenanceFooter (BI) — backend ainda nao expoe; render quando houver */}
        <ProvenanceFooter provenance={undefined} />
      </div>

      <AIPanel open={ai.open} onClose={() => ai.setOpen(false)} context={aiContext} />
    </div>
  )
}

// ── Controles de filtro (chip single-select) ────────────────────────────────

function OptionBtn({
  label,
  selected,
  onClick,
  mono,
}: {
  label: string
  selected: boolean
  onClick: () => void
  mono?: boolean
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cx(
        "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
        selected
          ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
          : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
      )}
    >
      <span className={cx("flex-1 text-left", mono && "tabular-nums")}>{label}</span>
      {selected && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
    </button>
  )
}

function SelectChip({
  label,
  icon,
  options,
  value,
  onChange,
}: {
  label: string
  icon?: RemixiconComponentType
  options: { value: string; label: string }[]
  value: string | null
  onChange: (v: string | null) => void
}) {
  const current = options.find((o) => o.value === value)
  return (
    <FilterChip label={label} value={current?.label ?? "Todos"} active={value !== null} icon={icon}>
      <div className="max-h-72 w-56 overflow-y-auto py-1">
        <OptionBtn label="Todos" selected={value === null} onClick={() => onChange(null)} />
        {options.length === 0 && (
          <div className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400">
            Sem opções
          </div>
        )}
        {options.map((o) => (
          <OptionBtn
            key={o.value}
            label={o.label}
            selected={value === o.value}
            onClick={() => onChange(o.value)}
          />
        ))}
      </div>
    </FilterChip>
  )
}
