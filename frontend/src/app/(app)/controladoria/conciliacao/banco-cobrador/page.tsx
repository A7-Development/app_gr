// src/app/(app)/controladoria/conciliacao/banco-cobrador/page.tsx
//
// Controladoria · Conciliacao · Banco Cobrador (Entrega 3, item 2).
// Cruza a carteira Bitfin (titulos abertos) x boletos ativos dos bancos
// cobradores. Shell derivado do DashboardBiPadrao (CLAUDE.md §7):
//   Z1 PageHeader + DashboardHeaderActions
//   Z2 toolbar (seletor de data-base)
//   Z2.5 L3 TabNavigation (segmentos por status) — filosofia "A"
//   Z4 resumo (5 status) + DataTable titulo-a-titulo (filtrada pelo segmento)
//   Z5 ProvenanceFooter
//
// data_ref e o filtro global; o status e lente local (client-side). Exclusoes
// de tenant (ex.: Pedreira so-CBV) seriam filtro de front — nao implementado
// no v1 (backend ja expoe cedente_documento/produto pra isso).

"use client"

import * as React from "react"
import { RiCalendarLine, RiCheckLine, RiInboxArchiveLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { PageHeader } from "@/design-system/components/PageHeader"
import { DashboardHeaderActions } from "@/design-system/components/DashboardHeaderActions"
import { ProvenanceFooter, type ProvenanceSource } from "@/design-system/components/ProvenanceFooter"
import { FilterChip } from "@/design-system/components/FilterBar"
import { EmptyState } from "@/design-system/components/EmptyState"
import { AIPanel, useAIPanel } from "@/design-system/components/AIPanel"
import { TabNavigation, TabNavigationLink } from "@/components/tremor/TabNavigation"
import { Card } from "@/components/tremor/Card"
import { useScrollShadow } from "@/lib/hooks/use-scroll-shadow"
import {
  useConciliacaoBancoCobrador,
  useConciliacaoBancoCobradorDatas,
} from "@/lib/hooks/controladoria"
import type { StatusConciliacaoBoleto } from "@/lib/api-client"

import { ConciliacaoBoletoTable } from "./_components/ConciliacaoBoletoTable"

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

const MOCK_PROVENANCE: ProvenanceSource[] = [
  { label: "Bitfin (carteira)", updated: "silver wh_titulo", sla: "—", stale: false },
  { label: "Banco cobrador (CNAB)", updated: "wh_boleto", sla: "D-1", stale: false },
]

export default function ConciliacaoBancoCobradorPage() {
  const ai = useAIPanel()
  const [scrollRef, scrolled] = useScrollShadow<HTMLDivElement>()

  const datasQuery = useConciliacaoBancoCobradorDatas()
  const datas = React.useMemo(() => datasQuery.data ?? [], [datasQuery.data])

  // Data-base selecionada: default = mais recente. Re-sincroniza quando as
  // datas carregam.
  const [dataRef, setDataRef] = React.useState<string | null>(null)
  React.useEffect(() => {
    if (dataRef === null && datas.length > 0) setDataRef(datas[0])
  }, [datas, dataRef])

  const [segmento, setSegmento] = React.useState<Segmento>("todos")

  const concQuery = useConciliacaoBancoCobrador(dataRef)
  const conc = concQuery.data

  // Contagem por status (do resumo) p/ os badges das tabs.
  const countByStatus = React.useMemo(() => {
    const m = new Map<string, number>()
    for (const r of conc?.resumo ?? []) m.set(r.status, r.quantidade)
    return m
  }, [conc])

  const totalLinhas = conc?.linhas.length ?? 0

  // Linhas filtradas pelo segmento ativo (lente local client-side).
  const linhasFiltradas = React.useMemo(() => {
    if (!conc) return []
    if (segmento === "todos") return conc.linhas
    return conc.linhas.filter((l) => l.status === segmento)
  }, [conc, segmento])

  const handleExport = React.useCallback(() => {
    // eslint-disable-next-line no-console
    console.log("export conciliacao", { dataRef, segmento })
  }, [dataRef, segmento])

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
        {/* Z1 — Title */}
        <div className="shrink-0 bg-white px-6 pt-3.5 pb-3 dark:bg-gray-950">
          <PageHeader
            title="Banco Cobrador"
            info="Conciliacao da carteira Bitfin (titulos em aberto elegiveis a boleto: FAT/CBV/DMS/CBS) com os boletos ativos dos bancos cobradores (retorno CNAB). Cruzamento titulo-a-titulo por numero do documento; valor comparado = valor liquido; vencimento tz-aware (Sao Paulo)."
            subtitle="Controladoria · Conciliações"
            actions={
              <DashboardHeaderActions
                ai={{ open: ai.open, onToggle: ai.toggle }}
                onExport={handleExport}
              />
            }
          />
        </div>

        {/* Z2 — Toolbar: seletor de data-base */}
        <div
          className={cx(
            "shrink-0 border-b border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
            scrolled && "scroll-shadow",
          )}
        >
          <div className="flex h-[52px] items-center gap-2 px-6">
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

            <div className="ml-auto flex items-center gap-2">
              <span className="shrink-0 text-[11px] text-gray-500 dark:text-gray-400">
                {concQuery.isFetching ? "Atualizando…" : "Atualizado"}
              </span>
            </div>
          </div>
        </div>

        {/* Z2.5 — L3 tabs por status */}
        <div className="shrink-0 border-b border-gray-200 bg-white px-6 dark:border-gray-800 dark:bg-gray-950">
          <TabNavigation>
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

        {/* Z4 — conteudo */}
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
              {/* Resumo: titulos abertos / boletos ativos / conciliados */}
              <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <ResumoTile label="Títulos abertos" value={conc?.titulos_abertos ?? 0} />
                <ResumoTile label="Boletos ativos" value={conc?.boletos_ativos ?? 0} />
                <ResumoTile label="Conciliados" value={conc?.conciliados ?? 0} tone="positive" />
                <ResumoTile
                  label="Divergências"
                  value={
                    (countByStatus.get("divergencia_valor") ?? 0) +
                    (countByStatus.get("divergencia_vencimento") ?? 0) +
                    (countByStatus.get("so_em_banco") ?? 0)
                  }
                  tone="warning"
                />
              </div>

              {/* Tabela do segmento ativo */}
              {linhasFiltradas.length === 0 && !concQuery.isLoading ? (
                <EmptyState
                  icon={RiCheckLine}
                  title="Nada neste segmento"
                  description="Nenhum título com este status na data-base selecionada."
                  className="mt-4"
                />
              ) : (
                <ConciliacaoBoletoTable linhas={linhasFiltradas} />
              )}
            </div>
          )}
        </div>

        {/* Z5 — ProvenanceFooter */}
        <ProvenanceFooter sources={MOCK_PROVENANCE} />
      </div>

      <AIPanel open={ai.open} onClose={() => ai.setOpen(false)} context={aiContext} />
    </div>
  )
}

// ── Tile de resumo (KPI compacto) ───────────────────────────────────────────

function ResumoTile({
  label,
  value,
  tone,
}: {
  label: string
  value: number
  tone?: "positive" | "warning"
}) {
  const toneClass =
    tone === "positive"
      ? "text-emerald-600 dark:text-emerald-400"
      : tone === "warning"
        ? "text-amber-600 dark:text-amber-400"
        : "text-gray-900 dark:text-gray-50"
  return (
    <Card className="p-3">
      <div className="text-[11px] font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
        {label}
      </div>
      <div className={cx("mt-1 text-2xl font-semibold tabular-nums", toneClass)}>{value}</div>
    </Card>
  )
}
