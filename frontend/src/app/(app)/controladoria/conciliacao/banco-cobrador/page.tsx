// src/app/(app)/controladoria/conciliacao/banco-cobrador/page.tsx
//
// Controladoria · Conciliacao · Banco Cobrador (Entrega 3, item 2).
// Cruza a carteira Bitfin (titulos abertos elegiveis a boleto) x boletos
// ativos dos bancos cobradores (retorno CNAB).
//
// Pattern: DashboardBiPadrao (composicao direta, anatomy de /bi/panorama):
//   Z1 PageHeader + DashboardHeaderActions
//   Z2 TabNavigation L3 (segmentos por status — filosofia "segmento -> tabela")
//   Z3 Toolbar de filtros (seletor de data-base)
//   Z4 KpiStrip (resumo do dia) + DataTable canonica titulo-a-titulo
//   Z5 ProvenanceFooter
// Lateral: AIPanel.
//
// data_ref = filtro global; status = lente local (client-side). Exclusoes de
// tenant (ex.: Pedreira so-CBV) seriam filtro de front — backend ja expoe
// cedente_documento + produto por linha.

"use client"

import * as React from "react"
import { RiCalendarLine, RiCheckLine, RiInboxArchiveLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import { TabNavigation, TabNavigationLink } from "@/components/tremor/TabNavigation"
import { PageHeader } from "@/design-system/components/PageHeader"
import { DashboardHeaderActions } from "@/design-system/components/DashboardHeaderActions"
import { FilterChip, FilterSearch } from "@/design-system/components/FilterBar"
import { KpiStrip, KpiCard } from "@/design-system/components/KpiStrip"
import { EmptyState } from "@/design-system/components/EmptyState"
import { AIPanel, useAIPanel } from "@/design-system/components/AIPanel"
import { cardTokens } from "@/design-system/tokens/card"
import { ProvenanceFooter } from "@/components/bi/ProvenanceFooter"
import { useScrollShadow } from "@/lib/hooks/use-scroll-shadow"
import {
  useConciliacaoBancoCobrador,
  useConciliacaoBancoCobradorDatas,
} from "@/lib/hooks/controladoria"
import type { StatusConciliacaoBoleto } from "@/lib/api-client"

import { ConciliacaoBoletoTable } from "./_components/ConciliacaoBoletoTable"

const fmtInt = new Intl.NumberFormat("pt-BR")

function fmtDateBR(iso: string | null | undefined): string {
  if (!iso) return "—"
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[3]}/${m[2]}/${m[1].slice(2)}` : iso
}

// Segmentos L3 (filosofia "A"): "Todos" + 5 status. Ordem fixa.
type Segmento = "todos" | StatusConciliacaoBoleto
const SEGMENTOS: { key: Segmento; label: string }[] = [
  { key: "todos",                  label: "Todos" },
  { key: "conciliado",             label: "Conciliado" },
  { key: "divergencia_valor",      label: "Div. valor" },
  { key: "divergencia_vencimento", label: "Div. venc." },
  { key: "so_em_bitfin",           label: "Só em BITFIN" },
  { key: "so_em_banco",            label: "Só em banco" },
]

export default function ConciliacaoBancoCobradorPage() {
  const ai = useAIPanel()
  const [scrollRef, scrolled] = useScrollShadow<HTMLDivElement>()

  const datasQuery = useConciliacaoBancoCobradorDatas()
  const datas = React.useMemo(() => datasQuery.data ?? [], [datasQuery.data])

  const [dataRef, setDataRef] = React.useState<string | null>(null)
  React.useEffect(() => {
    if (dataRef === null && datas.length > 0) setDataRef(datas[0])
  }, [datas, dataRef])

  const [segmento, setSegmento] = React.useState<Segmento>("todos")
  const [search, setSearch] = React.useState("")

  const q = useConciliacaoBancoCobrador(dataRef)
  const conc = q.data

  const countByStatus = React.useMemo(() => {
    const m = new Map<string, number>()
    for (const r of conc?.resumo ?? []) m.set(r.status, r.quantidade)
    return m
  }, [conc])

  const totalLinhas = conc?.linhas.length ?? 0

  const divergencias =
    (countByStatus.get("divergencia_valor") ?? 0) +
    (countByStatus.get("divergencia_vencimento") ?? 0)
  const soBanco = countByStatus.get("so_em_banco") ?? 0
  const taxaPct =
    conc && conc.boletos_ativos > 0
      ? (conc.conciliados / conc.boletos_ativos) * 100
      : 0

  const linhasFiltradas = React.useMemo(() => {
    if (!conc) return []
    if (segmento === "todos") return conc.linhas
    return conc.linhas.filter((l) => l.status === segmento)
  }, [conc, segmento])

  const handleExport = React.useCallback(() => {
    // eslint-disable-next-line no-console
    console.log("export conciliacao", { dataRef, segmento })
  }, [dataRef, segmento])

  const handleShare = React.useCallback(() => {
    void navigator.clipboard?.writeText(window.location.href)
  }, [])

  const aiContext = React.useMemo(
    () => ({
      page: "Controladoria · Conciliação · Banco Cobrador",
      period: dataRef ? fmtDateBR(dataRef) : "—",
      filters: `Segmento: ${SEGMENTOS.find((s) => s.key === segmento)?.label}`,
    }),
    [dataRef, segmento],
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

        {/* Z2 — Tabs L3 (segmentos por status) */}
        <div className="shrink-0 border-b border-gray-200 bg-white px-6 dark:border-gray-800 dark:bg-gray-950">
          <TabNavigation className="border-0">
            {SEGMENTOS.map((s) => {
              const n = s.key === "todos" ? totalLinhas : (countByStatus.get(s.key) ?? 0)
              return (
                <TabNavigationLink
                  key={s.key}
                  href="#"
                  active={segmento === s.key}
                  onClick={(e) => {
                    e.preventDefault()
                    setSegmento(s.key)
                  }}
                >
                  {s.label}
                  <span className="ml-1.5 tabular-nums text-gray-400 dark:text-gray-500">{n}</span>
                </TabNavigationLink>
              )
            })}
          </TabNavigation>
        </div>

        {/* Z3 — Toolbar de filtros (data-base) */}
        <div
          className={cx(
            "shrink-0 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
            scrolled && "scroll-shadow",
          )}
        >
          <div className="flex h-[52px] items-center gap-2 px-6">
            <FilterSearch
              placeholder="Buscar número, produto, cedente…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              onClear={() => setSearch("")}
            />

            <FilterChip
              label="Data-base"
              value={fmtDateBR(dataRef)}
              active={dataRef !== null}
              icon={RiCalendarLine}
            >
              <div className="max-h-72 overflow-y-auto py-1">
                {datas.length === 0 && (
                  <div className="px-3 py-1.5 text-xs text-gray-500 dark:text-gray-400">
                    Sem datas disponíveis
                  </div>
                )}
                {datas.map((d) => (
                  <button
                    key={d}
                    type="button"
                    onClick={() => setDataRef(d)}
                    className={cx(
                      "flex w-full items-center gap-2 rounded px-3 py-1.5 text-sm transition-colors",
                      d === dataRef
                        ? "bg-blue-50 text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-800",
                    )}
                  >
                    <span className="flex-1 text-left tabular-nums">{fmtDateBR(d)}</span>
                    {d === dataRef && <RiCheckLine className="size-3.5 shrink-0 text-blue-500" />}
                  </button>
                ))}
              </div>
            </FilterChip>

            <span className="ml-auto shrink-0 text-[11px] text-gray-500 dark:text-gray-400">
              {q.isFetching ? "Atualizando…" : "Atualizado"}
            </span>
          </div>
        </div>

        {/* Z4 — Conteudo */}
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
              {/* Z4.1 — KpiStrip (resumo do dia) */}
              <KpiStrip cols={5}>
                <KpiCard
                  label="Títulos abertos"
                  value={fmtInt.format(conc?.titulos_abertos ?? 0)}
                  sub="elegíveis a boleto"
                />
                <KpiCard
                  label="Boletos ativos"
                  value={fmtInt.format(conc?.boletos_ativos ?? 0)}
                  sub="nos bancos cobradores"
                />
                <KpiCard
                  label="Conciliados"
                  value={fmtInt.format(conc?.conciliados ?? 0)}
                  sub={`${taxaPct.toFixed(0)}% dos boletos`}
                />
                <KpiCard
                  label="Divergências"
                  value={fmtInt.format(divergencias)}
                  sub="valor + vencimento"
                />
                <KpiCard
                  label="Só em banco"
                  value={fmtInt.format(soBanco)}
                  sub="boletos sem título"
                />
              </KpiStrip>

              {/* Z4.2 — Tabela do segmento ativo */}
              {q.isError ? (
                <Card className={cx(cardTokens.body, "py-12 text-center")}>
                  <p className="text-sm text-gray-500 dark:text-gray-400">
                    Não foi possível carregar a conciliação.
                  </p>
                </Card>
              ) : linhasFiltradas.length === 0 && !q.isLoading ? (
                <EmptyState
                  icon={RiCheckLine}
                  title="Nada neste segmento"
                  description="Nenhum título com este status na data-base selecionada."
                  className="mt-4"
                />
              ) : (
                <ConciliacaoBoletoTable linhas={linhasFiltradas} globalFilter={search} />
              )}
            </div>
          )}
        </div>

        {/* Z5 — ProvenanceFooter (BI) — backend ainda nao expoe; render quando houver */}
        <ProvenanceFooter provenance={undefined} />
      </div>

      <AIPanel open={ai.open} onClose={() => ai.setOpen(false)} context={aiContext} />
    </div>
  )
}
