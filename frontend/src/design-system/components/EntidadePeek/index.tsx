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
  type EntidadeBureauResumo,
} from "@/lib/api-client"
import { cx } from "@/lib/utils"
import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"
import { EntidadeLink } from "@/design-system/components/EntidadeLink"
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

/** Empty state de dominio dos blocos F1 (posicoes ainda nao ingeridas). */
function BlocoAguardandoPosicoes({ titulo }: { titulo: string }) {
  return (
    <div className="rounded-md border border-dashed border-gray-200 px-3 py-2.5 dark:border-gray-800">
      <p className={tableTokens.cellSecondary}>
        {titulo} entra com a sincronização de posições por papel (em
        construção) — fonte já mapeada no Bitfin.
      </p>
    </div>
  )
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

            {/* ── Carteira Ativa (F1) ── */}
            <DrillDownSheet.SectionLabel>
              Carteira ativa
            </DrillDownSheet.SectionLabel>
            <BlocoAguardandoPosicoes titulo="A carteira ativa (CNPJ × grupo, nas pontas cedente e sacado)" />

            {/* ── Limites aprovados (F1, so cedente) ── */}
            {isCedente && (
              <>
                <DrillDownSheet.SectionLabel>
                  Limites aprovados
                </DrillDownSheet.SectionLabel>
                <BlocoAguardandoPosicoes titulo="O quadro de limites por produto" />
              </>
            )}

            {/* ── Performance (F1) ── */}
            <DrillDownSheet.SectionLabel>
              Performance
            </DrillDownSheet.SectionLabel>
            <BlocoAguardandoPosicoes titulo="O vencimentário (liquidados/prorrogados/recomprados/vencidos)" />

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
      ) : (
        <p className={tableTokens.cellSecondary}>✓ sem restrições apontadas</p>
      )}
      {comRestricao.length > 0 && limpos.length > 0 && (
        <p className={tableTokens.cellSecondary}>
          ✓ sem {limpos.map((r) => r.label.toLowerCase()).join(", ")}
        </p>
      )}
    </div>
  )
}
