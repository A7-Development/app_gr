"use client"

/**
 * EntidadePeek — drawer global da Ficha da Entidade (party model).
 *
 * Montado UMA vez no layout autenticado. Escuta `?entidade=<documento>` (via
 * `<EntidadeLink />`) e abre o resumo da entidade SOBRE qualquer pagina —
 * a analise em curso continua atras (abrir = push; voltar fecha).
 *
 * Blocos (design validado 2026-06-10):
 *   Hero (identidade + papeis + RJ) ->
 *   Carteira Ativa [F1] -> Limites aprovados [F1, so cedente] ->
 *   Performance [F1] -> Consultas financeiras (Serasa, REAL hoje) ->
 *   Operacoes 12M (REAL, so cedente) -> Grupo economico -> Estabelecimentos.
 *
 * Blocos F1 mostram empty state de dominio ("aguardando posicoes") — a secao
 * existe e comunica o que vira, nunca quebra (§14.6 espirito: nada some).
 * Botao "Abrir ficha completa" entra quando a rota dedicada for construida.
 */

import { useQuery } from "@tanstack/react-query"
import { useQueryState } from "nuqs"
import * as React from "react"

import { Badge } from "@/components/tremor/Badge"
import {
  biOperacoes5,
  cadastrosEntidades,
  type CarteiraAtivaLinha,
  type EntidadeBureauResumo,
  type LimiteProduto,
  type PerformanceResumo,
} from "@/lib/api-client"
import { cx } from "@/lib/utils"
import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"
import { EntidadeLink } from "@/design-system/components/EntidadeLink"
import { StrataConclusaoBadge } from "@/design-system/components/StrataConclusaoBadge"
import { fmt, fmtCNPJ, fmtDate, caption } from "@/design-system/tokens/typography"
import { tableTokens } from "@/design-system/tokens/table"

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
          />

          <DrillDownSheet.Body>
            {/* Papeis + alertas — a tese do party model visivel de cara */}
            <div className="flex flex-wrap items-center gap-1.5 pb-1">
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

            {/* ── Carteira Ativa ── */}
            <DrillDownSheet.SectionLabel>
              Carteira ativa
            </DrillDownSheet.SectionLabel>
            {resumo.carteira_ativa.length > 0 ? (
              <CarteiraAtivaBloco linhas={resumo.carteira_ativa} />
            ) : (
              <p className={tableTokens.cellSecondary}>
                Sem posição registrada para esta entidade.
              </p>
            )}

            {/* ── Limites aprovados (so cedente — nao ha limite por sacado) ── */}
            {isCedente && (
              <>
                <DrillDownSheet.SectionLabel>
                  Limites aprovados
                </DrillDownSheet.SectionLabel>
                {resumo.limites.length > 0 ? (
                  <LimitesBloco limites={resumo.limites} />
                ) : (
                  <p className={tableTokens.cellSecondary}>
                    Sem limites aprovados para este cedente.
                  </p>
                )}
              </>
            )}

            {/* ── Performance (vencimentario da janela de apuracao) ── */}
            {resumo.performance && (
              <>
                <DrillDownSheet.SectionLabel>
                  Performance
                  {resumo.performance.janela_dias != null &&
                    ` (${resumo.performance.janela_dias} dias · lente ${resumo.performance.papel})`}
                </DrillDownSheet.SectionLabel>
                <PerformanceBloco perf={resumo.performance} />
              </>
            )}

            {/* ── Consultas financeiras (REAL — Serasa via silver) ── */}
            <DrillDownSheet.SectionLabel>
              Consultas financeiras
            </DrillDownSheet.SectionLabel>
            {resumo.bureau ? (
              <BureauResumoBloco bureau={resumo.bureau} />
            ) : (
              <p className={tableTokens.cellSecondary}>
                Nenhuma consulta de bureau registrada para este documento.
              </p>
            )}

            {/* ── Operacoes 12M (REAL, so cedente) ── */}
            {resumo.cedente_id != null && (
              <>
                <DrillDownSheet.SectionLabel>
                  Operações (12 meses)
                </DrillDownSheet.SectionLabel>
                {opsQ.isLoading && <DrillDownSheet.Skeleton lines={3} />}
                {ops && (
                  <div className="space-y-1.5">
                    <p className={tableTokens.cellText}>
                      <span className={tableTokens.cellStrong}>
                        {fmt.currencyCompact.format(ops.vop_total)}
                      </span>{" "}
                      em {fmt.number.format(ops.total)} operações · receita{" "}
                      {fmt.currencyCompact.format(ops.receita_total)}
                    </p>
                    {ops.operacoes.slice(0, 5).map((op) => (
                      <div
                        key={op.operacao_id}
                        className="flex items-baseline justify-between gap-2"
                      >
                        <span className={tableTokens.cellSecondary}>
                          {op.data_de_efetivacao
                            ? fmtDate(op.data_de_efetivacao)
                            : "—"}{" "}
                          · {op.produto}
                        </span>
                        <span className={cx(tableTokens.cellNumber)}>
                          {fmt.currencyWhole.format(op.vop)}
                          {op.taxa_final != null && (
                            <span className={tableTokens.cellSecondary}>
                              {" "}
                              · {op.taxa_final.toLocaleString("pt-BR", {
                                maximumFractionDigits: 2,
                              })}
                              % a.m.
                            </span>
                          )}
                        </span>
                      </div>
                    ))}
                    {ops.total > 5 && (
                      <p className={caption}>
                        Últimas 5 de {fmt.number.format(ops.total)} — total acima
                        soma todas.
                      </p>
                    )}
                  </div>
                )}
              </>
            )}

            {/* ── Grupo economico ── */}
            {resumo.grupo && resumo.grupo.membros.length > 0 && (
              <>
                <DrillDownSheet.SectionLabel>
                  Grupo econômico — {resumo.grupo.nome} (
                  {resumo.grupo.membros.length})
                </DrillDownSheet.SectionLabel>
                <div className="space-y-1">
                  {resumo.grupo.membros.map((m, i) => (
                    <div key={m.documento ?? i} className="flex items-baseline justify-between gap-2">
                      <EntidadeLink
                        documento={m.documento}
                        history="replace"
                        className={tableTokens.cellText}
                      >
                        {m.nome ?? "(em quarentena)"}
                      </EntidadeLink>
                      <span className={tableTokens.cellSecondary}>
                        {[
                          m.vinculo,
                          m.papeis
                            .map((p) => PAPEL_LABEL[p] ?? p)
                            .join(", ")
                            .toLowerCase(),
                        ]
                          .filter(Boolean)
                          .join(" · ")}
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* ── Estabelecimentos da mesma raiz ── */}
            {outrosEstabelecimentos.length > 0 && (
              <>
                <DrillDownSheet.SectionLabel>
                  Estabelecimentos da empresa ({resumo.estabelecimentos.length})
                </DrillDownSheet.SectionLabel>
                <div className="space-y-1">
                  {outrosEstabelecimentos.map((e) => (
                    <div key={e.documento} className="flex items-baseline justify-between gap-2">
                      <EntidadeLink
                        documento={e.documento}
                        history="replace"
                        className={tableTokens.cellText}
                      >
                        {e.is_matriz ? "Matriz" : `Filial ${e.filial_numero}`} ·{" "}
                        {fmtCNPJ(e.documento)}
                      </EntidadeLink>
                      <span className={tableTokens.cellSecondary}>
                        {[e.localidade, e.estado].filter(Boolean).join("/")}
                      </span>
                    </div>
                  ))}
                </div>
              </>
            )}
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

// ── Bloco bureau (consultas financeiras) ─────────────────────────────────────

function BureauResumoBloco({ bureau }: { bureau: EntidadeBureauResumo }) {
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
  // Suspeita corrente (flag da última consulta OU estado da sentinela) —
  // o "✓ sem restrições" seria mentira quando os zeros vêm de supressão
  // judicial, então o badge SUBSTITUI a linha de "limpo".
  const suspeitaLiminar =
    bureau.suspeita_liminar || bureau.liminar_estado === "suspeita_ativa"
  const liminarCaida = bureau.liminar_estado === "liminar_caida"
  const liminarEmRevisao = bureau.liminar_estado === "transicao_ambigua"

  return (
    <div className="space-y-1">
      <p className={tableTokens.cellText}>
        Última: {bureau.fonte} · {fmtDate(isoDateOnly(bureau.consultado_em))}
        {bureau.score != null && (
          <span className={tableTokens.cellStrong}>
            {" "}
            · score {bureau.score}
            {bureau.score_classe ? ` (${bureau.score_classe})` : ""}
          </span>
        )}
      </p>
      {comRestricao.length > 0 ? (
        <p className={cx(tableTokens.cellText, "text-red-600 dark:text-red-400")}>
          ⚠{" "}
          {comRestricao.map((r) => `${r.label} ${r.qtd}`).join(" · ")}
          {bureau.valor_total_restricoes != null &&
            bureau.valor_total_restricoes > 0 &&
            ` · total ${fmt.currencyCompact.format(bureau.valor_total_restricoes)}`}
        </p>
      ) : suspeitaLiminar ? (
        <LiminarBadge bureau={bureau} variant="warning" label="Possível Liminar" />
      ) : liminarEmRevisao ? (
        <LiminarBadge
          bureau={bureau}
          variant="neutral"
          label="Possível Liminar (em revisão)"
        />
      ) : (
        <p className={tableTokens.cellSecondary}>✓ sem restrições apontadas</p>
      )}
      {liminarCaida && (
        <LiminarBadge bureau={bureau} variant="error" label="Liminar caída" />
      )}
      {comRestricao.length > 0 && limpos.length > 0 && (
        <p className={tableTokens.cellSecondary}>
          ✓ sem {limpos.map((r) => r.label.toLowerCase()).join(", ")}
        </p>
      )}
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


// ── Blocos F1 (posicoes por papel) ───────────────────────────────────────────

/** Mini-matriz CNPJ × Grupo nas pontas cedente/sacado. A coluna Total soma
 *  as duas pontas na tela (§14.6). */
function CarteiraAtivaBloco({ linhas }: { linhas: CarteiraAtivaLinha[] }) {
  const rotulo: Record<CarteiraAtivaLinha["escopo"], string> = {
    cnpj: "CNPJ",
    grupo: "Grupo",
  }
  return (
    <div className="space-y-1">
      <div className="grid grid-cols-[64px_1fr_1fr_1fr] gap-x-2">
        <span />
        <span className={cx(tableTokens.header, "text-right")}>Como cedente</span>
        <span className={cx(tableTokens.header, "text-right")}>Como sacado</span>
        <span className={cx(tableTokens.header, "text-right")}>Total</span>
        {linhas.map((l) => (
          <React.Fragment key={l.escopo}>
            <span className={tableTokens.cellSecondary}>{rotulo[l.escopo]}</span>
            <span className={cx(tableTokens.cellNumber, "text-right")}>
              {fmt.currencyCompact.format(l.cedente_valor)}
            </span>
            <span className={cx(tableTokens.cellNumber, "text-right")}>
              {fmt.currencyCompact.format(l.sacado_valor)}
            </span>
            <span className={cx(tableTokens.cellStrong, "text-right tabular-nums")}>
              {fmt.currencyCompact.format(l.total)}
            </span>
          </React.Fragment>
        ))}
      </div>
      {linhas.some((l) => l.cedente_vencido + l.sacado_vencido > 0) && (
        <p className={cx(tableTokens.cellText, "text-red-600 dark:text-red-400")}>
          vencido:{" "}
          {linhas
            .filter((l) => l.cedente_vencido + l.sacado_vencido > 0)
            .map(
              (l) =>
                `${rotulo[l.escopo]} ${fmt.currencyCompact.format(
                  l.cedente_vencido + l.sacado_vencido,
                )}`,
            )
            .join(" · ")}
        </p>
      )}
    </div>
  )
}

/** Barra de uso de limite (azul <75% · âmbar <90% · vermelho >=90%). */
function UsoBar({ pct }: { pct: number }) {
  const clamped = Math.min(pct, 100)
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
      <div
        className={cx(
          "h-full rounded-full",
          pct >= 90 ? "bg-red-500" : pct >= 75 ? "bg-amber-500" : "bg-blue-500",
        )}
        style={{ width: `${clamped}%` }}
      />
    </div>
  )
}

function LimitesBloco({ limites }: { limites: LimiteProduto[] }) {
  const totalLimite = limites.reduce((s, l) => s + l.limite, 0)
  const totalUso = limites.reduce((s, l) => s + l.em_uso, 0)
  return (
    <div className="space-y-1.5">
      {limites.map((l, i) => {
        const pct = l.limite > 0 ? (l.em_uso / l.limite) * 100 : null
        return (
          <div key={`${l.produto_sigla}-${i}`} className="space-y-0.5">
            <div className="flex items-baseline justify-between gap-2">
              <span className={tableTokens.cellStrong}>
                {l.produto_sigla ?? "(produto)"}
              </span>
              <span className={tableTokens.cellNumber}>
                {fmt.currencyCompact.format(l.em_uso)} de{" "}
                {fmt.currencyCompact.format(l.limite)}
                {pct != null && (
                  <span className={tableTokens.cellSecondary}>
                    {" "}
                    · {pct.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}%
                  </span>
                )}
              </span>
            </div>
            {pct != null && <UsoBar pct={pct} />}
          </div>
        )
      })}
      {limites.length > 1 && (
        <p className={tableTokens.cellText}>
          Total: {fmt.currencyCompact.format(totalUso)} de{" "}
          {fmt.currencyCompact.format(totalLimite)} · disponível{" "}
          <span className={tableTokens.cellStrong}>
            {fmt.currencyCompact.format(Math.max(totalLimite - totalUso, 0))}
          </span>
        </p>
      )}
    </div>
  )
}

/** Composicao do vencimentario: liquidados (azul) / recomprados (âmbar) /
 *  vencidos (vermelho). As linhas somam o vencimentario total (§14.6). */
function PerformanceBloco({ perf }: { perf: PerformanceResumo }) {
  const venc = perf.vencimentario ?? 0
  const liq = perf.liquidados ?? 0
  const rec = perf.recomprados ?? 0
  const vcd = (perf.vencidos_penalizados ?? 0) + (perf.vencidos_nao_penalizados ?? 0)
  const pctOf = (v: number) =>
    venc > 0
      ? `${((v / venc) * 100).toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`
      : "—"
  const linhas = [
    { label: "Liquidados", valor: liq, cor: "bg-blue-500" },
    { label: "Recomprados", valor: rec, cor: "bg-amber-500" },
    { label: "Vencidos em aberto", valor: vcd, cor: "bg-red-500" },
  ]
  return (
    <div className="space-y-1.5">
      {venc > 0 && (
        <div className="flex h-2 w-full gap-px overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
          {linhas
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
      {linhas.map((l) => (
        <div key={l.label} className="flex items-baseline justify-between gap-2">
          <span className={tableTokens.cellText}>
            <span
              className={cx("mr-1.5 inline-block size-2 rounded-full", l.cor)}
            />
            {l.label}
          </span>
          <span className={tableTokens.cellNumber}>
            {fmt.currencyCompact.format(l.valor)}
            <span className={tableTokens.cellSecondary}> · {pctOf(l.valor)}</span>
          </span>
        </div>
      ))}
      <div className="flex items-baseline justify-between gap-2 border-t border-gray-100 pt-1 dark:border-gray-800">
        <span className={tableTokens.cellStrong}>Vencimentário total</span>
        <span className={cx(tableTokens.cellStrong, "tabular-nums")}>
          {fmt.currencyCompact.format(venc)}
        </span>
      </div>
      <p className={tableTokens.cellSecondary}>
        {perf.indice_liquidez != null &&
          `Liquidez ${perf.indice_liquidez.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`}
        {perf.prazo_medio_carteira != null &&
          ` · prazo carteira ${perf.prazo_medio_carteira.toLocaleString("pt-BR", { maximumFractionDigits: 0 })}d`}
        {perf.indice_pontualidade != null &&
          ` · pontualidade ${perf.indice_pontualidade.toLocaleString("pt-BR", { maximumFractionDigits: 1 })}%`}
        {perf.data_apuracao != null &&
          ` · apuração ${fmtDate(perf.data_apuracao.slice(0, 10))}`}
      </p>
    </div>
  )
}
