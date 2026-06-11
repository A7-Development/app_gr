"use client"

/**
 * EntidadePeek — drawer global da Ficha da Entidade (party model).
 *
 * Montado UMA vez no layout autenticado. Escuta `?entidade=<documento>` (via
 * `<EntidadeLink />`) e abre o resumo da entidade SOBRE qualquer pagina —
 * a analise em curso continua atras (abrir = push; voltar fecha).
 *
 * LINGUAGEM VISUAL (pedido Ricardo 2026-06-11): mesma gramatica dos drills da
 * Cota Sub (DrillDcContent + drillKit) — Hero com titulo/KPIs/subtitulo,
 * secoes com titulo icone+help+fonte, `DataTable` canonica density="ultra"
 * com rodape de totais (renderFooter), cards bordados com eyebrow. Os helpers
 * do drillKit sao replicados localmente porque design-system nao pode
 * importar de app/<dominio> (§3) — manter visualmente identicos ao kit.
 */

import { useQuery } from "@tanstack/react-query"
import { useQueryState } from "nuqs"
import * as React from "react"
import {
  createColumnHelper,
  type ColumnDef,
} from "@tanstack/react-table"
import {
  RiBuilding2Line,
  RiCommunityLine,
  RiExchangeFundsLine,
  RiFileSearchLine,
  RiPulseLine,
  RiShieldCheckLine,
  RiWallet3Line,
  type RemixiconComponentType,
} from "@remixicon/react"

import { Badge } from "@/components/tremor/Badge"
import {
  biOperacoes5,
  cadastrosEntidades,
  type CarteiraAtivaLinha,
  type EntidadeBureauResumo,
  type EntidadeEstabelecimento,
  type EntidadeGrupoMembro,
  type LimiteProduto,
  type Operacoes5OperacaoItem,
  type PerformanceResumo,
} from "@/lib/api-client"
import { cx } from "@/lib/utils"
import { DataTable } from "@/design-system/components/DataTable"
import { DrillDownSheet, type HeroKpi } from "@/design-system/components/DrillDownSheet"
import { EntidadeLink } from "@/design-system/components/EntidadeLink"
import { StrataConclusaoBadge } from "@/design-system/components/StrataConclusaoBadge"
import { fmt, fmtCNPJ, fmtDate, caption } from "@/design-system/tokens/typography"
import { tableTokens } from "@/design-system/tokens/table"

// ── Gramatica visual dos drills (replica local do drillKit da Cota Sub) ─────

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

/** Props compartilhadas das DataTables do peek — todas ultra, sem toolbar,
 *  container bordado (identico ao DT_PROPS do DrillDcContent). */
const DT_PROPS = {
  density: "ultra",
  virtualize: false,
  showColumnManager: false,
  showDensityToggle: false,
  showExport: false,
  className: "rounded border border-gray-200 dark:border-gray-800",
} as const

/** Linha de rodape (tfoot) com total — mesma classe do drill DC. */
const FOOT_ROW = "border-t-2 border-t-gray-300 dark:border-t-gray-700"

/** Titulo de secao do drill (icone + label + help + fonte a direita). */
function SectionTitle({
  icon: Icon,
  label,
  counter,
  help,
}: {
  icon: RemixiconComponentType
  label: string
  counter?: React.ReactNode
  help?: string
}) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <h4 className="flex items-center gap-1.5 text-[12px] font-semibold uppercase tracking-[0.04em] text-gray-700 dark:text-gray-300">
        <Icon className="size-3.5 text-gray-400 dark:text-gray-500" aria-hidden />
        {label}
        {help && (
          <span
            className="cursor-help text-[10px] font-normal normal-case tracking-normal text-gray-400 dark:text-gray-600"
            title={help}
          >
            (?)
          </span>
        )}
      </h4>
      {counter != null && counter !== "" && (
        <span className="text-[11px] tabular-nums text-gray-500 dark:text-gray-400">
          {counter}
        </span>
      )}
    </div>
  )
}

function NumCell({ value, strong }: { value: number; strong?: boolean }) {
  return (
    <div
      className={cx(
        "text-right",
        strong ? tableTokens.cellStrong : tableTokens.cellNumber,
        strong && "tabular-nums",
      )}
    >
      {fmtBRL.format(value)}
    </div>
  )
}

// ── helpers ──────────────────────────────────────────────────────────────────

function fmtDocumento(doc: string, tipo: "pj" | "pf"): string {
  if (tipo === "pj") return fmtCNPJ(doc)
  return doc.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4")
}

function isoDateOnly(iso: string): string {
  return iso.slice(0, 10)
}

const PAPEL_LABEL: Record<string, string> = {
  cedente: "CEDENTE",
  sacado: "SACADO",
  avalista: "AVALISTA",
  socio: "SÓCIO",
  fornecedor: "FORNECEDOR",
}

function pct(v: number, digits = 0): string {
  return `${v.toLocaleString("pt-BR", { maximumFractionDigits: digits })}%`
}

// ── componente ───────────────────────────────────────────────────────────────

export function EntidadePeek() {
  // Abrir = push (voltar fecha). Navegacao peek->peek usa replace (EntidadeLink).
  const [entidade, setEntidade] = useQueryState("entidade", { history: "push" })

  const resumoQ = useQuery({
    queryKey: ["cadastros", "entidades", "resumo", entidade],
    queryFn: () => cadastrosEntidades.resumo(entidade as string),
    enabled: entidade != null,
    retry: false,
  })
  const resumo = resumoQ.data ?? null

  // Operacoes 12M — so quando a entidade tem papel cedente resolvido.
  const periodo12m = React.useMemo(() => {
    const fim = new Date()
    const inicio = new Date()
    inicio.setFullYear(inicio.getFullYear() - 1)
    return {
      periodoInicio: inicio.toISOString().slice(0, 10),
      periodoFim: fim.toISOString().slice(0, 10),
    }
  }, [])
  const opsQ = useQuery({
    queryKey: ["cadastros", "entidades", "peek-ops", resumo?.cedente_id, periodo12m],
    queryFn: () =>
      biOperacoes5.operacoes({ ...periodo12m, cedenteId: resumo?.cedente_id ?? undefined }),
    enabled: resumo?.cedente_id != null,
  })
  const ops = opsQ.data?.data ?? null

  const isCedente = resumo?.papeis.some((p) => p.papel === "cedente") ?? false
  const outrosEstabelecimentos =
    resumo?.estabelecimentos.filter((e) => e.documento !== resumo.documento) ?? []

  // ── KPIs do hero (titulo / KPI / subtitulo — padrao Cota Sub) ──
  const heroKpis: HeroKpi[] = []
  if (resumo) {
    const cnpjRow = resumo.carteira_ativa.find((l) => l.escopo === "cnpj")
    if (cnpjRow) {
      heroKpis.push({
        label: "Carteira ativa",
        value: fmt.currencyCompact.format(cnpjRow.total),
        emphasis: true,
      })
      const vencido = cnpjRow.cedente_vencido + cnpjRow.sacado_vencido
      if (vencido > 0) {
        heroKpis.push({ label: "Vencido", value: fmt.currencyCompact.format(vencido) })
      }
    }
    if (resumo.limites.length > 0) {
      const limite = resumo.limites.reduce((s, l) => s + l.limite, 0)
      const uso = resumo.limites.reduce((s, l) => s + l.em_uso, 0)
      if (limite > 0) {
        heroKpis.push({ label: "Limite usado", value: pct((uso / limite) * 100) })
      }
    }
    if (resumo.performance?.indice_liquidez != null) {
      heroKpis.push({
        label: "Liquidez",
        value: pct(resumo.performance.indice_liquidez, 1),
      })
    }
    if (resumo.bureau?.score != null) {
      heroKpis.push({ label: "Score Serasa", value: String(resumo.bureau.score) })
    }
  }

  return (
    <DrillDownSheet
      open={entidade != null}
      onClose={() => void setEntidade(null)}
      title={resumo?.nome ?? "Entidade"}
    >
      {resumoQ.isLoading && <DrillDownSheet.Skeleton lines={10} />}

      {resumoQ.isError && (
        <DrillDownSheet.Body>
          <p className={tableTokens.cellSecondary}>
            Entidade não encontrada para este documento — pode ainda não ter
            sido sincronizada do ERP.
          </p>
        </DrillDownSheet.Body>
      )}

      {resumo && (
        <>
          <DrillDownSheet.Header breadcrumb={["Entidades", resumo.nome]} />
          <DrillDownSheet.Hero
            id={fmtDocumento(resumo.documento, resumo.tipo_pessoa)}
            title={resumo.nome}
            subtitle={[
              resumo.tipo_pessoa === "pj"
                ? resumo.is_matriz
                  ? `Matriz${outrosEstabelecimentos.length ? ` (+${outrosEstabelecimentos.length})` : ""}`
                  : `Filial ${resumo.filial_numero ?? ""}`
                : "Pessoa física",
              resumo.cnae_denominacao,
              resumo.porte,
              [resumo.localidade, resumo.estado].filter(Boolean).join("/"),
            ]
              .filter(Boolean)
              .join(" · ")}
            kpis={heroKpis.length > 0 ? heroKpis : undefined}
          />

          <DrillDownSheet.Body>
            <div className="flex flex-col gap-5">
              {/* Papeis + alertas — a tese do party model visivel de cara */}
              <div className="flex flex-wrap items-center gap-1.5">
                {resumo.papeis.map((p) => (
                  <Badge key={p.papel} variant="default">
                    {PAPEL_LABEL[p.papel] ?? p.papel.toUpperCase()}
                  </Badge>
                ))}
                {resumo.em_recuperacao_judicial && (
                  <Badge variant="error">
                    RECUPERAÇÃO JUDICIAL
                    {resumo.data_recuperacao_judicial
                      ? ` · ${fmtDate(isoDateOnly(resumo.data_recuperacao_judicial))}`
                      : ""}
                  </Badge>
                )}
                {resumo.grupo && (
                  <Badge variant="default">Grupo {resumo.grupo.nome}</Badge>
                )}
              </div>

              {/* ── 1. Carteira Ativa ── */}
              <section>
                <SectionTitle
                  icon={RiWallet3Line}
                  label="Carteira ativa"
                  help="Risco em aberto nas duas pontas — como cedente (coobrigação) e como sacado (pagador). A coluna Total soma as pontas; a linha Grupo consolida todas as entidades do grupo econômico."
                  counter={
                    <span className="font-mono">wh_posicao_cedente · wh_posicao_sacado</span>
                  }
                />
                <div className="mt-3">
                  {resumo.carteira_ativa.length > 0 ? (
                    <DataTable<CarteiraAtivaLinha>
                      {...DT_PROPS}
                      data={resumo.carteira_ativa}
                      columns={CARTEIRA_COLUMNS}
                    />
                  ) : (
                    <p className={tableTokens.cellSecondary}>
                      Sem posição registrada para esta entidade.
                    </p>
                  )}
                </div>
              </section>

              {/* ── 2. Limites aprovados (so cedente — nao ha limite por sacado) ── */}
              {isCedente && (
                <section>
                  <SectionTitle
                    icon={RiShieldCheckLine}
                    label="Limites aprovados"
                    help="Limite operacional por produto (conceito do papel cedente). Em uso = risco total em aberto no produto."
                    counter={<span className="font-mono">wh_posicao_cedente_produto</span>}
                  />
                  <div className="mt-3">
                    {resumo.limites.length > 0 ? (
                      <DataTable<LimiteProduto>
                        {...DT_PROPS}
                        data={resumo.limites}
                        rowClassName={(l) =>
                          cx(
                            l.limite > 0 &&
                              l.em_uso / l.limite >= 0.9 &&
                              "bg-red-50/40 dark:bg-red-950/10",
                          )
                        }
                        columns={LIMITE_COLUMNS}
                        renderFooter={(rows) => {
                          const tLim = rows.reduce((s, l) => s + l.limite, 0)
                          const tUso = rows.reduce((s, l) => s + l.em_uso, 0)
                          return (
                            <tr className={FOOT_ROW}>
                              <td className="px-3">
                                <span className={tableTokens.cellStrong}>Total</span>
                              </td>
                              <td className="px-3"><NumCell value={tLim} strong /></td>
                              <td className="px-3"><NumCell value={tUso} strong /></td>
                              <td className="px-3">
                                <div
                                  className={cx(
                                    "text-right text-xs font-semibold tabular-nums",
                                    usoTone(tLim > 0 ? tUso / tLim : 0),
                                  )}
                                >
                                  {tLim > 0 ? pct((tUso / tLim) * 100) : "—"}
                                </div>
                              </td>
                              <td className="px-3">
                                <NumCell value={Math.max(tLim - tUso, 0)} strong />
                              </td>
                            </tr>
                          )
                        }}
                      />
                    ) : (
                      <p className={tableTokens.cellSecondary}>
                        Sem limites aprovados para este cedente.
                      </p>
                    )}
                  </div>
                </section>
              )}

              {/* ── 3. Performance (vencimentario da janela de apuracao) ── */}
              {resumo.performance && <PerformanceSection perf={resumo.performance} />}

              {/* ── 4. Consultas financeiras ── */}
              <section>
                <SectionTitle
                  icon={RiFileSearchLine}
                  label="Consultas financeiras"
                  help="Última consulta de bureau registrada para este documento (relay das consultas feitas no Bitfin)."
                  counter={<span className="font-mono">wh_serasa_pj_consulta</span>}
                />
                <div className="mt-3">
                  {resumo.bureau ? (
                    <BureauCard bureau={resumo.bureau} />
                  ) : (
                    <p className={tableTokens.cellSecondary}>
                      Nenhuma consulta de bureau registrada para este documento.
                    </p>
                  )}
                </div>
              </section>

              {/* ── 5. Operacoes 12M (so cedente) ── */}
              {resumo.cedente_id != null && (
                <section>
                  <SectionTitle
                    icon={RiExchangeFundsLine}
                    label="Operações (12 meses)"
                    help="Últimas 5 operações; o rodapé soma o conjunto COMPLETO dos 12 meses (não só as visíveis)."
                    counter={
                      ops ? (
                        <span>
                          últimas 5 de {fmt.number.format(ops.total)} ·{" "}
                          <span className="font-mono">wh_operacao</span>
                        </span>
                      ) : undefined
                    }
                  />
                  <div className="mt-3">
                    {opsQ.isLoading && <DrillDownSheet.Skeleton lines={4} />}
                    {ops && (
                      <DataTable<Operacoes5OperacaoItem>
                        {...DT_PROPS}
                        data={ops.operacoes.slice(0, 5)}
                        columns={OPS_COLUMNS}
                        renderFooter={() => (
                          <tr className={FOOT_ROW}>
                            <td className="px-3" colSpan={2}>
                              <span className={tableTokens.cellStrong}>
                                Total 12M · {fmt.number.format(ops.total)} operações
                              </span>
                            </td>
                            <td className="px-3"><NumCell value={ops.vop_total} strong /></td>
                            <td className="px-3">
                              <div className={cx("text-right", tableTokens.cellNumberSecondary)}>
                                receita {fmt.currencyCompact.format(ops.receita_total)}
                              </div>
                            </td>
                          </tr>
                        )}
                      />
                    )}
                  </div>
                </section>
              )}

              {/* ── 6. Grupo economico ── */}
              {resumo.grupo && resumo.grupo.membros.length > 0 && (
                <section>
                  <SectionTitle
                    icon={RiCommunityLine}
                    label={`Grupo econômico — ${resumo.grupo.nome}`}
                    help="Membros curados na fonte. Clique num membro para abrir o peek dele."
                    counter={`${resumo.grupo.membros.length} membro${resumo.grupo.membros.length === 1 ? "" : "s"}`}
                  />
                  <div className="mt-3">
                    <DataTable<EntidadeGrupoMembro>
                      {...DT_PROPS}
                      data={resumo.grupo.membros}
                      columns={GRUPO_COLUMNS}
                    />
                  </div>
                </section>
              )}

              {/* ── 7. Estabelecimentos da mesma raiz ── */}
              {outrosEstabelecimentos.length > 0 && (
                <section>
                  <SectionTitle
                    icon={RiBuilding2Line}
                    label="Estabelecimentos da empresa"
                    help="Matriz e filiais compartilham a raiz do CNPJ — juridicamente a mesma pessoa. Clique para abrir o peek do estabelecimento."
                    counter={`${resumo.estabelecimentos.length} no total`}
                  />
                  <div className="mt-3">
                    <DataTable<EntidadeEstabelecimento>
                      {...DT_PROPS}
                      data={outrosEstabelecimentos}
                      columns={ESTABELECIMENTO_COLUMNS}
                    />
                  </div>
                </section>
              )}
            </div>
          </DrillDownSheet.Body>

          <DrillDownSheet.Footer>
            <span className={caption}>
              {resumo.source_type === "erp:bitfin" ? "Bitfin" : resumo.source_type}{" "}
              · sincronizado em {fmtDate(isoDateOnly(resumo.ingested_at))}
            </span>
          </DrillDownSheet.Footer>
        </>
      )}
    </DrillDownSheet>
  )
}

// ── Colunas (tudo via tableTokens — regra dura §6) ──────────────────────────

const colCarteira = createColumnHelper<CarteiraAtivaLinha>()
const CARTEIRA_COLUMNS = [
  colCarteira.accessor("escopo", {
    header: "Escopo",
    size: 90,
    cell: (info) => (
      <span className={tableTokens.cellStrong}>
        {info.getValue() === "cnpj" ? "CNPJ" : "Grupo"}
      </span>
    ),
  }),
  colCarteira.accessor("cedente_valor", {
    header: () => <div className="text-right">Como cedente</div>,
    size: 110,
    cell: (info) => <NumCell value={info.getValue()} />,
  }),
  colCarteira.accessor("sacado_valor", {
    header: () => <div className="text-right">Como sacado</div>,
    size: 110,
    cell: (info) => <NumCell value={info.getValue()} />,
  }),
  colCarteira.display({
    id: "vencido",
    header: () => <div className="text-right">Vencido</div>,
    size: 100,
    cell: ({ row }) => {
      const v = row.original.cedente_vencido + row.original.sacado_vencido
      return (
        <div
          className={cx(
            "text-right text-xs tabular-nums",
            v > 0
              ? "font-semibold text-red-600 dark:text-red-400"
              : "text-gray-400 dark:text-gray-600",
          )}
        >
          {fmtBRL.format(v)}
        </div>
      )
    },
  }),
  colCarteira.accessor("total", {
    header: () => <div className="text-right">Total</div>,
    size: 110,
    cell: (info) => <NumCell value={info.getValue()} strong />,
  }),
] as ColumnDef<CarteiraAtivaLinha, unknown>[]

function usoTone(frac: number): string {
  if (frac >= 0.9) return "text-red-600 dark:text-red-400"
  if (frac >= 0.75) return "text-amber-600 dark:text-amber-400"
  return "text-gray-900 dark:text-gray-100"
}

const colLimite = createColumnHelper<LimiteProduto>()
const LIMITE_COLUMNS = [
  colLimite.accessor("produto_sigla", {
    header: "Produto",
    size: 80,
    cell: (info) => (
      <span className={tableTokens.cellStrong}>{info.getValue() ?? "(produto)"}</span>
    ),
  }),
  colLimite.accessor("limite", {
    header: () => <div className="text-right">Limite</div>,
    size: 100,
    cell: (info) => <NumCell value={info.getValue()} />,
  }),
  colLimite.accessor("em_uso", {
    header: () => <div className="text-right">Em uso</div>,
    size: 100,
    cell: (info) => <NumCell value={info.getValue()} />,
  }),
  colLimite.display({
    id: "uso_pct",
    header: () => <div className="text-right">Uso</div>,
    size: 60,
    cell: ({ row }) => {
      const l = row.original
      if (l.limite <= 0)
        return <div className={cx("text-right", tableTokens.cellMuted)}>—</div>
      const frac = l.em_uso / l.limite
      return (
        <div className={cx("text-right text-xs font-semibold tabular-nums", usoTone(frac))}>
          {pct(frac * 100)}
        </div>
      )
    },
  }),
  colLimite.display({
    id: "disponivel",
    header: () => <div className="text-right">Disponível</div>,
    size: 100,
    cell: ({ row }) => (
      <NumCell value={Math.max(row.original.limite - row.original.em_uso, 0)} />
    ),
  }),
] as ColumnDef<LimiteProduto, unknown>[]

const colOps = createColumnHelper<Operacoes5OperacaoItem>()
const OPS_COLUMNS = [
  colOps.accessor("data_de_efetivacao", {
    header: "Data",
    size: 80,
    cell: (info) => (
      <span className={tableTokens.cellText}>
        {info.getValue() ? fmtDate(info.getValue() as string) : "—"}
      </span>
    ),
  }),
  colOps.accessor("produto", {
    header: "Produto",
    size: 70,
    cell: (info) => <span className={tableTokens.cellSecondary}>{info.getValue()}</span>,
  }),
  colOps.accessor("vop", {
    header: () => <div className="text-right">VOP</div>,
    size: 110,
    cell: (info) => <NumCell value={info.getValue()} />,
  }),
  colOps.accessor("taxa_final", {
    header: () => <div className="text-right">Taxa final</div>,
    size: 90,
    cell: (info) => {
      const v = info.getValue()
      return (
        <div className={cx("text-right", tableTokens.cellNumber)}>
          {v != null
            ? `${v.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}% a.m.`
            : "—"}
        </div>
      )
    },
  }),
] as ColumnDef<Operacoes5OperacaoItem, unknown>[]

const colGrupo = createColumnHelper<EntidadeGrupoMembro>()
const GRUPO_COLUMNS = [
  colGrupo.accessor("nome", {
    header: "Membro",
    size: 240,
    cell: ({ row }) => (
      <EntidadeLink
        documento={row.original.documento}
        history="replace"
        className={cx("block truncate", tableTokens.cellText)}
      >
        {row.original.nome ?? "(em quarentena)"}
      </EntidadeLink>
    ),
  }),
  colGrupo.accessor("vinculo", {
    header: "Vínculo",
    size: 130,
    cell: (info) => (
      <span className={cx("block truncate", tableTokens.cellSecondary)}>
        {info.getValue() ?? "—"}
      </span>
    ),
  }),
  colGrupo.accessor("papeis", {
    header: "Papéis",
    size: 130,
    cell: (info) => (
      <span className={tableTokens.cellSecondary}>
        {info.getValue().length > 0
          ? info
              .getValue()
              .map((p) => PAPEL_LABEL[p] ?? p)
              .join(", ")
              .toLowerCase()
          : "—"}
      </span>
    ),
  }),
] as ColumnDef<EntidadeGrupoMembro, unknown>[]

const colEst = createColumnHelper<EntidadeEstabelecimento>()
const ESTABELECIMENTO_COLUMNS = [
  colEst.accessor("documento", {
    header: "Estabelecimento",
    size: 220,
    cell: ({ row }) => (
      <EntidadeLink
        documento={row.original.documento}
        history="replace"
        className={cx("block truncate", tableTokens.cellText)}
      >
        {row.original.is_matriz ? "Matriz" : `Filial ${row.original.filial_numero}`} ·{" "}
        {fmtCNPJ(row.original.documento)}
      </EntidadeLink>
    ),
  }),
  colEst.display({
    id: "cidade",
    header: "Cidade/UF",
    size: 140,
    cell: ({ row }) => (
      <span className={cx("block truncate", tableTokens.cellSecondary)}>
        {[row.original.localidade, row.original.estado].filter(Boolean).join("/") || "—"}
      </span>
    ),
  }),
] as ColumnDef<EntidadeEstabelecimento, unknown>[]

// ── Performance (barra de composicao + tabela com rodape reconciliado) ──────

type PerfRow = { label: string; valor: number; cor: string }

const colPerf = createColumnHelper<PerfRow>()

function PerformanceSection({ perf }: { perf: PerformanceResumo }) {
  const venc = perf.vencimentario ?? 0
  const rows: PerfRow[] = [
    { label: "Liquidados", valor: perf.liquidados ?? 0, cor: "bg-blue-500" },
    { label: "Recomprados", valor: perf.recomprados ?? 0, cor: "bg-amber-500" },
    {
      label: "Vencidos em aberto",
      valor: (perf.vencidos_penalizados ?? 0) + (perf.vencidos_nao_penalizados ?? 0),
      cor: "bg-red-500",
    },
  ]
  const columns = React.useMemo(
    () =>
      [
        colPerf.accessor("label", {
          header: "Componente",
          size: 200,
          cell: ({ row }) => (
            <span className={cx("flex items-center gap-1.5", tableTokens.cellText)}>
              <span
                className={cx("inline-block size-2 shrink-0 rounded-full", row.original.cor)}
              />
              {row.original.label}
            </span>
          ),
        }),
        colPerf.accessor("valor", {
          header: () => <div className="text-right">Valor</div>,
          size: 110,
          cell: (info) => <NumCell value={info.getValue()} />,
        }),
        colPerf.display({
          id: "pct",
          header: () => <div className="text-right">%</div>,
          size: 60,
          cell: ({ row }) => (
            <div className={cx("text-right", tableTokens.cellNumberSecondary)}>
              {venc > 0 ? pct((row.original.valor / venc) * 100, 1) : "—"}
            </div>
          ),
        }),
      ] as ColumnDef<PerfRow, unknown>[],
    [venc],
  )

  const subtitulo = [
    perf.prazo_medio_carteira != null &&
      `prazo carteira ${perf.prazo_medio_carteira.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}d`,
    perf.indice_pontualidade != null && `pontualidade ${pct(perf.indice_pontualidade, 1)}`,
    perf.data_apuracao != null && `apuração ${fmtDate(isoDateOnly(perf.data_apuracao))}`,
  ]
    .filter(Boolean)
    .join(" · ")

  return (
    <section>
      <SectionTitle
        icon={RiPulseLine}
        label={`Performance${perf.janela_dias != null ? ` · ${perf.janela_dias} dias` : ""}`}
        help="Vencimentário da janela de apuração do Bitfin (lente do papel). Os componentes somam o total — reconciliação on-screen."
        counter={
          perf.indice_liquidez != null ? (
            <span>
              liquidez{" "}
              <span className="font-semibold tabular-nums text-gray-900 dark:text-gray-100">
                {pct(perf.indice_liquidez, 1)}
              </span>
            </span>
          ) : undefined
        }
      />
      <div className="mt-3 flex flex-col gap-2">
        {venc > 0 && (
          <div className="flex h-2 w-full gap-px overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
            {rows
              .filter((l) => l.valor > 0)
              .map((l) => (
                <div
                  key={l.label}
                  className={cx("h-full", l.cor)}
                  style={{ width: `${(l.valor / venc) * 100}%` }}
                />
              ))}
          </div>
        )}
        <DataTable<PerfRow>
          {...DT_PROPS}
          data={rows}
          columns={columns}
          renderFooter={() => (
            <tr className={cx(FOOT_ROW, "bg-blue-50/40 dark:bg-blue-950/10")}>
              <td className="px-3">
                <span className={tableTokens.cellStrong}>= Vencimentário total</span>
              </td>
              <td className="px-3"><NumCell value={venc} strong /></td>
              <td className="px-3">
                <div className={cx("text-right", tableTokens.cellNumberSecondary)}>100%</div>
              </td>
            </tr>
          )}
        />
        {subtitulo && <p className={caption}>{subtitulo}</p>}
      </div>
    </section>
  )
}

// ── Card de bureau (estilo "Resultado da DC": eyebrow + numero + linhas).
//    Preserva a deteccao de liminar judicial (#281): quando os zeros vem de
//    supressao judicial, o "sem restricoes" seria mentira — badge substitui. ──

function BureauCard({ bureau }: { bureau: EntidadeBureauResumo }) {
  const restricoes = [
    { label: "Protestos", qtd: bureau.protestos_qtd },
    { label: "PEFIN", qtd: bureau.pefin_qtd },
    { label: "REFIN", qtd: bureau.refin_qtd },
    { label: "Cheques s/ fundo", qtd: bureau.cheques_qtd },
    { label: "Ações judiciais", qtd: bureau.acoes_judiciais_qtd },
    { label: "Falências", qtd: bureau.falencias_qtd },
  ]
  const comRestricao = restricoes.filter((r) => (r.qtd ?? 0) > 0)
  const limpos = restricoes.filter((r) => (r.qtd ?? 0) === 0)
  const suspeitaLiminar =
    bureau.suspeita_liminar || bureau.liminar_estado === "suspeita_ativa"
  const liminarCaida = bureau.liminar_estado === "liminar_caida"
  const liminarEmRevisao = bureau.liminar_estado === "transicao_ambigua"

  return (
    <div className="rounded border border-gray-200 p-3 dark:border-gray-800">
      <div className="text-[10px] uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600">
        {bureau.fonte} · {fmtDate(isoDateOnly(bureau.consultado_em))}
      </div>
      {bureau.score != null && (
        <div className="mt-1 text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-100">
          score {bureau.score}
          {bureau.score_classe && (
            <span className="text-[12px] font-normal text-gray-500 dark:text-gray-400">
              {" "}
              ({bureau.score_classe})
            </span>
          )}
        </div>
      )}
      <div className="mt-2 space-y-1 text-[11px]">
        {comRestricao.map((r) => (
          <div key={r.label} className="flex items-center justify-between">
            <span className="text-red-700 dark:text-red-400">⚠ {r.label}</span>
            <span className="font-semibold tabular-nums text-red-700 dark:text-red-400">
              {r.qtd}
            </span>
          </div>
        ))}
        {comRestricao.length > 0 &&
          bureau.valor_total_restricoes != null &&
          bureau.valor_total_restricoes > 0 && (
            <div className="flex items-center justify-between border-t border-gray-100 pt-1 dark:border-gray-900">
              <span className="text-gray-500 dark:text-gray-400">Total de restrições</span>
              <span className="font-semibold tabular-nums text-red-700 dark:text-red-400">
                {fmtBRL.format(bureau.valor_total_restricoes)}
              </span>
            </div>
          )}
        {comRestricao.length === 0 &&
          (suspeitaLiminar ? (
            <LiminarBadge bureau={bureau} variant="warning" label="Possível Liminar" />
          ) : liminarEmRevisao ? (
            <LiminarBadge
              bureau={bureau}
              variant="neutral"
              label="Possível Liminar (em revisão)"
            />
          ) : (
            <p className="text-gray-400 dark:text-gray-500">✓ sem restrições apontadas</p>
          ))}
        {liminarCaida && (
          <LiminarBadge bureau={bureau} variant="error" label="Liminar caída" />
        )}
        {comRestricao.length > 0 && limpos.length > 0 && (
          <p className="text-gray-400 dark:text-gray-500">
            ✓ sem {limpos.map((r) => r.label.toLowerCase()).join(", ")}
          </p>
        )}
      </div>
    </div>
  )
}

/** Badge de conclusão Strata pro caso liminar — proveniência no tooltip. */
function LiminarBadge({
  bureau,
  variant,
  label,
}: {
  bureau: EntidadeBureauResumo
  variant: "warning" | "error" | "neutral"
  label: string
}) {
  const tooltipPorLabel: Record<string, string> = {
    "Possível Liminar":
      "A Serasa retornou “NADA CONSTA” explícito no resumo de negativos — " +
      "padrão de supressão judicial de apontamentos. Os zeros não " +
      "significam ficha limpa: a empresa provavelmente obteve liminar " +
      "para escondê-los.",
    "Possível Liminar (em revisão)":
      "Este CNPJ esteve sob “NADA CONSTA” e a consulta mais recente veio " +
      "sem o carimbo, ainda sem negativos visíveis — liminar pode ter " +
      "expirado ou a Serasa mudou o marcador. Em revisão pela sentinela.",
    "Liminar caída":
      "Os apontamentos negativos VOLTARAM a aparecer após período sob " +
      "“NADA CONSTA” — a liminar provavelmente caiu. Revisar crédito.",
  }
  return (
    <div>
      <StrataConclusaoBadge
        label={label}
        variant={variant}
        tooltip={
          <div className="space-y-1 text-xs">
            <p>
              Conclusão derivada pelo Strata — não consta no ERP nem no
              bureau.
            </p>
            <p>{tooltipPorLabel[label]}</p>
            <p className="opacity-70">
              {bureau.liminar_desde &&
                `Sob suspeita desde ${fmtDate(isoDateOnly(bureau.liminar_desde))} · `}
              Regra {bureau.liminar_regra ?? "serasa_liminar_v1"} · confiança
              média
            </p>
          </div>
        }
      />
    </div>
  )
}
