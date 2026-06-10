// src/app/(app)/controladoria/conciliacao/banco-cobrador/page.tsx
//
// Controladoria · Conciliacao · Banco Cobrador (Entrega 3, item 2).
// Conciliacao ESTADO-VS-ESTADO: carteira Bitfin ATUAL (titulos abertos
// elegiveis a boleto) x cobranca VIGENTE (boletos ativos, projecao do fold da
// timeline). Sem data-base -- a defasagem do banco vai como FRESCOR.
//
// Pattern: DashboardBiPadrao (composicao direta, anatomy de /bi/panorama):
//   Z1 PageHeader + DashboardHeaderActions
//   Z2 Toolbar: UA · Status · Banco · Produto · Cedente (todos globais) +
//      indicador de frescor (nao-filtro)
//   Z3 Resumo 50/50 (tabela canonica + charts da carteira) + DataTable
//      canonica titulo-a-titulo
//   Z4 ProvenanceFooter
// Lateral: AIPanel.
//
// RE-ESCOPO TOTAL (2026-06-07): TODOS os filtros (UA/Status/Banco/Produto/
// Cedente) recortam o MESMO conjunto que alimenta resumo + charts + detalhe —
// os numeros na tela sempre batem (§7.2/§14.6). Acabou a distincao escopo/lente
// (antes so a UA reescopava o resumo). Exclusoes de tenant (ex.: Pedreira
// so-CBV) saem desses filtros (backend expoe cedente_documento).

"use client"

import * as React from "react"
import { useQuery } from "@tanstack/react-query"
import {
  RiAuctionLine,
  RiBankLine,
  RiBriefcase2Line,
  RiBuilding2Line,
  RiCheckLine,
  RiFilter3Line,
  RiInboxArchiveLine,
  RiPriceTag3Line,
  RiRefreshLine,
  RiTimeLine,
  type RemixiconComponentType,
} from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import { PageHeader } from "@/design-system/components/PageHeader"
import { DashboardHeaderActions } from "@/design-system/components/DashboardHeaderActions"
import {
  FilterChip,
  MultiCheckList,
  multiLabel,
  ResetFiltersButton,
  type MultiOption,
} from "@/design-system/components/FilterBar"
import { EmptyState } from "@/design-system/components/EmptyState"
import { AIPanel, useAIPanel } from "@/design-system/components/AIPanel"
import { cardTokens } from "@/design-system/tokens/card"
import { ProvenanceFooter } from "@/components/bi/ProvenanceFooter"
import { useScrollShadow } from "@/lib/hooks/use-scroll-shadow"
import {
  useConciliacaoBancoCobrador,
  useConciliacaoBancoCobradorSync,
  useConciliacaoBancoCobradorSyncStatus,
} from "@/lib/hooks/controladoria"
import { biMetadata } from "@/lib/api-client"
import type {
  LinhaConciliacaoBoleto,
  ResumoStatusConciliacao,
  StatusConciliacaoBoleto,
} from "@/lib/api-client"

import { ConciliacaoBoletoTable } from "./_components/ConciliacaoBoletoTable"
import { ResumoConciliacaoCharts } from "./_components/ResumoConciliacaoCharts"
import { ResumoConciliacaoTable } from "./_components/ResumoConciliacaoTable"
import { protestoLabel } from "./_components/status"

const fmtInt = new Intl.NumberFormat("pt-BR")

function fmtDateBR(iso: string | null | undefined): string {
  if (!iso) return "—"
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[3]}/${m[2]}/${m[1].slice(2)}` : iso
}

function fmtDateTimeBR(iso: string | null | undefined): string {
  if (!iso) return "—"
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return iso
  const p = (n: number) => String(n).padStart(2, "0")
  return `${p(d.getDate())}/${p(d.getMonth() + 1)} ${p(d.getHours())}:${p(d.getMinutes())}`
}

// Fase do sync -> rotulo amigavel pro botao enquanto roda.
const FASE_LABEL: Record<string, string> = {
  coleta: "Coletando arquivos",
  decode: "Decodificando",
  project: "Atualizando carteira",
  done: "Concluindo",
}

const STATUS_OPTS: { value: StatusConciliacaoBoleto; label: string }[] = [
  { value: "conciliado",             label: "Conciliado" },
  { value: "divergencia_valor",      label: "Divergência de valor" },
  { value: "divergencia_vencimento", label: "Divergência de vencimento" },
  { value: "so_em_bitfin",           label: "Só em BITFIN" },
  { value: "enviado_nao_confirmado", label: "Enviado, aguardando confirmação" },
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

  // ESCOPO (UA) — define a conciliacao que se ve; o resumo reflete. LENTES
  // (status/banco/produto/cedente) filtram so o detalhe, nao o resumo.
  // Multi-select (padrao /bi/operacoes4): cada filtro e uma lista de selecionados.
  const [uaFilter, setUaFilter] = React.useState<string[]>([])
  const [statusFilter, setStatusFilter] = React.useState<string[]>([])
  const [bancoFilter, setBancoFilter] = React.useState<string[]>([])
  const [produtoFilter, setProdutoFilter] = React.useState<string[]>([])
  const [cedenteFilter, setCedenteFilter] = React.useState<string[]>([])
  const [protestoFilter, setProtestoFilter] = React.useState<string[]>([])

  // Reset de TODOS os filtros (escopo UA + lentes). O botao "Resetar" fica
  // sempre visivel (padrao /bi/operacoes2) e habilita quando ha filtro ativo.
  const hasFilters =
    uaFilter.length > 0 ||
    statusFilter.length > 0 ||
    bancoFilter.length > 0 ||
    produtoFilter.length > 0 ||
    cedenteFilter.length > 0 ||
    protestoFilter.length > 0
  const resetFilters = React.useCallback(() => {
    setUaFilter([])
    setStatusFilter([])
    setBancoFilter([])
    setProdutoFilter([])
    setCedenteFilter([])
    setProtestoFilter([])
  }, [])

  const q = useConciliacaoBancoCobrador()
  const conc = q.data

  // Sincronizacao manual (por tenant). O servidor roda em background; a pagina
  // faz POLLING do estado real (fase/heartbeat) em vez de esperar no escuro, e
  // re-busca a conciliacao quando o run termina (status='ok').
  const syncMut = useConciliacaoBancoCobradorSync()
  const syncStatus = useConciliacaoBancoCobradorSyncStatus()
  const st = syncStatus.data
  const sincronizando = st?.status === "running"
  const handleSync = React.useCallback(() => {
    syncMut.mutate(undefined, { onSuccess: () => void syncStatus.refetch() })
  }, [syncMut, syncStatus])
  // Quando um run termina (ok), re-busca a conciliacao uma vez.
  const lastDoneRef = React.useRef<string | null>(null)
  React.useEffect(() => {
    if (st?.status === "ok" && st.run_id && st.run_id !== lastDoneRef.current) {
      lastDoneRef.current = st.run_id
      void q.refetch()
    }
  }, [st?.status, st?.run_id, q])

  // Nome amigavel dos produtos ("Faturização (FAT)") — fonte canonica.
  const produtosMetaQuery = useQuery({
    queryKey: ["bi", "metadata", "produtos"],
    queryFn: () => biMetadata.produtos(),
    staleTime: 60 * 60 * 1000,
  })
  const produtoLabel = React.useMemo(() => {
    const m = new Map<string, string>()
    for (const p of produtosMetaQuery.data ?? []) m.set(p.sigla, `${p.nome} (${p.sigla})`)
    return m
  }, [produtosMetaQuery.data])

  // Resolver sigla -> nome completo (so o nome, ex.: "Comissária") para a
  // coluna Produto da tabela de detalhe. Fallback pra sigla se o catalogo
  // ainda nao carregou ou nao tiver o produto.
  const produtoNomeMap = React.useMemo(() => {
    const m = new Map<string, string>()
    for (const p of produtosMetaQuery.data ?? []) m.set(p.sigla, p.nome)
    return m
  }, [produtosMetaQuery.data])
  const produtoNome = React.useCallback(
    (sigla: string | null) => (sigla ? produtoNomeMap.get(sigla) ?? sigla : "—"),
    [produtoNomeMap],
  )

  // Opcoes dos chips derivadas das linhas (multi-option {value,label}).
  const uaOpts = React.useMemo(
    () => distinctOpts(conc?.linhas, (l) => l.ua_nome),
    [conc],
  )
  const bancoOpts = React.useMemo(
    () => distinctOpts(conc?.linhas, (l) => l.banco, capitalize),
    [conc],
  )
  const produtoOpts = React.useMemo(
    () => distinctOpts(conc?.linhas, (l) => l.produto, (v) => produtoLabel.get(v) ?? v),
    [conc, produtoLabel],
  )
  const cedenteOpts = React.useMemo(
    () => distinctOpts(conc?.linhas, (l) => l.cedente_nome),
    [conc],
  )
  // Opcoes do chip Protesto: tipos presentes nas linhas (value=tipo canonico).
  const protestoOpts = React.useMemo(
    () => distinctOpts(conc?.linhas, (l) => l.protesto_tipo, (v) => protestoLabel(v)),
    [conc],
  )

  // Re-escopo TOTAL (decisao 2026-06-07): UA/Status/Banco/Produto/Cedente
  // recortam o MESMO conjunto que alimenta a tabela-resumo, os charts e o
  // detalhe — os numeros na tela sempre batem (§7.2/§14.6). Acabou a distincao
  // escopo (UA) vs lente; todo filtro e global. (Filtrar Status colapsa o
  // resumo/donut para o subset escolhido — comportamento aceito.)
  const linhasFiltradas = React.useMemo(() => {
    if (!conc) return []
    return conc.linhas.filter(
      (l) =>
        (uaFilter.length === 0 || (l.ua_nome != null && uaFilter.includes(l.ua_nome))) &&
        (statusFilter.length === 0 || statusFilter.includes(l.status)) &&
        (bancoFilter.length === 0 || (l.banco != null && bancoFilter.includes(l.banco))) &&
        (produtoFilter.length === 0 || (l.produto != null && produtoFilter.includes(l.produto))) &&
        (cedenteFilter.length === 0 ||
          (l.cedente_nome != null && cedenteFilter.includes(l.cedente_nome))) &&
        (protestoFilter.length === 0 ||
          (l.protesto_tipo != null && protestoFilter.includes(l.protesto_tipo))),
    )
  }, [conc, uaFilter, statusFilter, bancoFilter, produtoFilter, cedenteFilter, protestoFilter])

  // Resumo (tabela + charts) computado do MESMO conjunto filtrado do detalhe.
  const resumo = React.useMemo(() => computeResumo(linhasFiltradas), [linhasFiltradas])

  const handleShare = React.useCallback(() => {
    void navigator.clipboard?.writeText(window.location.href)
  }, [])

  const handleExport = React.useCallback(() => {
    // eslint-disable-next-line no-console
    console.log("export conciliacao")
  }, [])

  const aiContext = React.useMemo(() => {
    const join = (xs: string[]) => xs.join(", ")
    return {
      page: "Controladoria · Conciliação · Banco Cobrador",
      period: `Cobrança até ${fmtDateBR(conc?.cobranca_atualizada_ate)}`,
      filters: [
        uaFilter.length > 0 && `UA: ${join(uaFilter)}`,
        statusFilter.length > 0 &&
          `Status: ${join(statusFilter.map((s) => STATUS_OPTS.find((o) => o.value === s)?.label ?? s))}`,
        bancoFilter.length > 0 && `Banco: ${join(bancoFilter.map(capitalize))}`,
        produtoFilter.length > 0 && `Produto: ${join(produtoFilter)}`,
        cedenteFilter.length > 0 && `Cedente: ${join(cedenteFilter)}`,
        protestoFilter.length > 0 && `Protesto: ${join(protestoFilter.map((p) => protestoLabel(p)))}`,
      ].filter(Boolean).join(" · ") || "Nenhum",
    }
  }, [conc, uaFilter, statusFilter, bancoFilter, produtoFilter, cedenteFilter, protestoFilter])

  // "Sem dados" = conciliacao carregada e nao ha titulos nem boletos.
  const semDados =
    !q.isLoading &&
    conc != null &&
    conc.titulos_abertos === 0 &&
    conc.boletos_ativos === 0

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
                ? `${fmtInt.format(conc.titulos_abertos)} títulos abertos · ${fmtInt.format(conc.boletos_ativos)} boletos ativos`
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
            <MultiSelectChip
              label="UA"
              icon={RiBriefcase2Line}
              options={uaOpts}
              selected={uaFilter}
              onChange={setUaFilter}
            />

            <span className="h-5 w-px shrink-0 bg-gray-200 dark:bg-gray-800" aria-hidden="true" />

            <MultiSelectChip
              label="Status"
              icon={RiFilter3Line}
              options={STATUS_OPTS}
              selected={statusFilter}
              onChange={setStatusFilter}
            />
            <MultiSelectChip
              label="Banco"
              icon={RiBankLine}
              options={bancoOpts}
              selected={bancoFilter}
              onChange={setBancoFilter}
            />
            <MultiSelectChip
              label="Produto"
              icon={RiPriceTag3Line}
              options={produtoOpts}
              selected={produtoFilter}
              onChange={setProdutoFilter}
            />
            <MultiSelectChip
              label="Cedente"
              icon={RiBuilding2Line}
              options={cedenteOpts}
              selected={cedenteFilter}
              onChange={setCedenteFilter}
              searchable
            />
            {/* Protesto: so aparece quando ha boleto no pipeline de protesto
                no conjunto atual (opcoes derivadas das linhas). */}
            {protestoOpts.length > 0 && (
              <MultiSelectChip
                label="Protesto"
                icon={RiAuctionLine}
                options={protestoOpts}
                selected={protestoFilter}
                onChange={setProtestoFilter}
              />
            )}

            {/* Resetar filtros (controle canonico): zera escopo (UA) + lentes. */}
            <ResetFiltersButton hasActiveFilters={hasFilters} onReset={resetFilters} />

            <div className="ml-auto flex shrink-0 items-center gap-3">
              {/* Status compacto: UMA linha so — ultima sync + frescor da
                  cobranca (o essencial). Travado/erro substituem o texto. */}
              <span
                className={cx(
                  "flex shrink-0 items-center gap-1.5 text-[11px]",
                  st?.status === "stuck"
                    ? "font-medium text-amber-600 dark:text-amber-400"
                    : st?.status === "error"
                      ? "font-medium text-red-600 dark:text-red-400"
                      : "text-gray-500 dark:text-gray-400",
                )}
                title={st?.status === "error" ? (st.erro ?? undefined) : undefined}
              >
                <RiTimeLine className="size-3.5 shrink-0 text-gray-400 dark:text-gray-500" aria-hidden="true" />
                {st?.status === "stuck" ? (
                  "Sincronização travada"
                ) : st?.status === "error" ? (
                  "Erro na sincronização"
                ) : (
                  <>
                    {st?.status === "ok" && st.finished_at && (
                      <>
                        Última sync{" "}
                        <span className="font-medium tabular-nums text-gray-700 dark:text-gray-300">
                          {fmtDateTimeBR(st.finished_at)}
                        </span>
                        <span className="text-gray-300 dark:text-gray-700">·</span>
                      </>
                    )}
                    Cobrança até{" "}
                    <span className="font-medium tabular-nums text-gray-700 dark:text-gray-300">
                      {fmtDateBR(conc?.cobranca_atualizada_ate)}
                    </span>
                  </>
                )}
              </span>

              {/* Sincronizar: dispara a coleta/reprocessamento dos arquivos CNAB
                  da inbox (por tenant; banco/UA saem dos arquivos/titulos). */}
              <Button
                variant="secondary"
                onClick={handleSync}
                disabled={sincronizando || syncMut.isPending}
                className="h-[30px] gap-1.5 px-2.5 py-1 text-[13px]"
              >
                <RiRefreshLine
                  className={cx("size-3.5 shrink-0", sincronizando && "animate-spin")}
                  aria-hidden="true"
                />
                {sincronizando
                  ? `${FASE_LABEL[st?.fase ?? ""] ?? "Sincronizando"}…`
                  : "Sincronizar"}
              </Button>
            </div>
          </div>
        </div>

        {/* Z3 — Conteudo */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4">
          {semDados ? (
            <EmptyState
              icon={RiInboxArchiveLine}
              title="Sem carteira de cobrança ainda"
              description="Não há títulos abertos elegíveis nem boletos vigentes para este tenant. Assim que a carteira e os retornos CNAB forem processados, a conciliação aparece aqui."
              className="mt-6"
            />
          ) : (
            <div className="flex flex-col gap-4">
              {/* Resumo 50/50: tabela canonica (esq.) + charts da carteira
                  (dir.). Ambos no MESMO conjunto filtrado do detalhe; reconcilia
                  (§14.6). Empilha em telas estreitas (< xl). */}
              <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                <ResumoConciliacaoTable resumo={resumo} />
                <ResumoConciliacaoCharts
                  linhas={linhasFiltradas}
                  frescores={conc?.frescor_bancos ?? []}
                  bancoFilter={bancoFilter}
                  onBancoToggle={(banco) =>
                    setBancoFilter((prev) =>
                      prev.includes(banco)
                        ? prev.filter((b) => b !== banco)
                        : [...prev, banco],
                    )
                  }
                />
              </div>

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
                  description="Nenhum título atende aos filtros no escopo atual. Ajuste ou limpe os filtros."
                  className="mt-4"
                />
              ) : (
                <ConciliacaoBoletoTable linhas={linhasFiltradas} produtoNome={produtoNome} />
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

// Chip de filtro multi-select (padrao /bi/operacoes4): label + "N selecionados"
// + lista de checkboxes. Reusa FilterChip + MultiCheckList/multiLabel canonicos.
function MultiSelectChip({
  label,
  icon,
  options,
  selected,
  onChange,
  searchable,
}: {
  label: string
  icon?: RemixiconComponentType
  options: MultiOption[]
  selected: string[]
  onChange: (next: string[]) => void
  searchable?: boolean
}) {
  return (
    <FilterChip
      label={label}
      value={multiLabel(selected, options)}
      active={selected.length > 0}
      icon={icon}
    >
      {/* Largura folgada pra label nao quebrar; cedente (searchable) mais larga. */}
      <div className={searchable ? "w-72" : "w-64"}>
        <MultiCheckList
          options={options}
          selected={selected}
          onChange={onChange}
          searchable={searchable}
          searchPlaceholder="Buscar cedente…"
        />
      </div>
    </FilterChip>
  )
}
