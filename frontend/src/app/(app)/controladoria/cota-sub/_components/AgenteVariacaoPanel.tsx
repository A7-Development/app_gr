"use client"

/**
 * AgenteVariacaoPanel — renderiza o output do agente IA `controladoria.
 * analista_variacao_cota` num DrillDownSheet right-side `xl`, no formato de
 * RELATORIO PROTOCOLAR (documento numerado), nao mais cards empilhados.
 *
 * Estrutura visual (documento):
 *   MetadataBanner — from_cache + custo + duracao + modelo (transparencia §14)
 *   Cabecalho protocolar — A7 Credit · Strata | titulo + fundo | nº/data-base/janela
 *   1.0 Sintese da Variacao        — sumario_executivo + bullets dos top movimentos
 *   2.0 Sanity Check               — kpi-table (Δ calculado / Δ MEC / residuo) + diagnostico
 *   3.0 Analise por Rubrica        — grupos Ativos / Passivos, subsecoes 3.1..3.N
 *                                    (narrativa + papeis como bullets, flag `!` em anomalia)
 *   4.0 Constatacoes de Risco      — findings (sinais_alerta) c/ severidade + evidencia
 *   5.0 Papeis Citados             — tabela agregando papeis_mencionados (dedupe)
 *   6.0 Acoes Requeridas           — sugestoes_acao por prioridade
 *   Rodape protocolar              — modelo + nº + audit/run (proveniencia)
 *
 * Frontend-only: consome o `AnalysisVariacaoCotaResponse` atual. Onde o modelo
 * de referencia mostra bullets curados (1.0/4.0/6.0), degrada para a prosa que o
 * schema ja emite (sumario/descricao/detalhe). Na 3.0 os `papeis_mencionados`
 * sao os bullets granulares.
 *
 * Stack: apenas componentes do design-system + tokens + primitivos Remix.
 */

import * as React from "react"
import { RiSparklingFill, RiDatabaseLine } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"
import { Card } from "@/components/tremor/Card"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { Button } from "@/components/tremor/Button"
import {
  AgentLiveStatus,
  type AgentToolLogEntry,
} from "@/design-system/components/AgentLiveStatus"
import type {
  AgenteAnaliseVariacao,
  AgenteCategoriaDelta,
  AgenteExplicacaoCategoria,
  AgentePapelMencionado,
  AgenteSinalAlerta,
  AgenteSugestaoAcao,
  AgenteVariacaoRunResponse,
} from "@/lib/api-client"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const fmtBRLSigned = (v: number): string => {
  if (Math.abs(v) < 0.005) return "R$ 0,00"
  const sign = v > 0 ? "+" : "−"
  return `${sign}${fmtBRL.format(Math.abs(v))}`
}

const fmtDateBR = (iso: string): string => {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[3]}/${m[2]}/${m[1]}` : iso
}

const fmtDuration = (ms: number): string => {
  if (ms < 1000) return `${ms}ms`
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`
  return `${Math.floor(ms / 60000)}m ${Math.round((ms % 60000) / 1000)}s`
}

const fmtCacheAge = (sec: number): string => {
  if (sec < 60) return `${sec}s atrás`
  if (sec < 3600) return `${Math.floor(sec / 60)}min atrás`
  if (sec < 86400) return `${Math.floor(sec / 3600)}h atrás`
  return `${Math.floor(sec / 86400)}d atrás`
}

// ─── Helpers de texto e cor ───────────────────────────────────────────────

const humanize = (s: string): string => (s || "").replace(/_/g, " ")

/** Primeira frase de uma narrativa, truncada — usada nos bullets da Sintese. */
const firstSentence = (text: string): string => {
  const t = (text || "").trim()
  if (!t) return ""
  const m = /^(.+?[.;])\s/.exec(t)
  const s = m ? m[1] : t
  return s.length > 140 ? `${s.slice(0, 137).trimEnd()}…` : s
}

const deltaTone = (v: number): string =>
  v > 0.005
    ? "text-emerald-700 dark:text-emerald-400"
    : v < -0.005
      ? "text-red-700 dark:text-red-400"
      : "text-gray-400 dark:text-gray-600"

/** Naturezas de papel que merecem o marcador de alerta `!` no bullet. */
const FLAG_NATUREZA = /mutac|silenc|offrecord|abatim|write[_-]?off|engaiol/i

/** Nº de relatorio deterministico: CSJ-<data>-<4 chars do run_id>. */
const reportNoFrom = (data: string, runId: string): string => {
  const id = (runId || "").replace(/-/g, "").slice(0, 4).toUpperCase() || "0001"
  return `CSJ-${data}-${id}`
}

// Chips de severidade (constatacoes) e prioridade (acoes) — mesma escala visual.
type ChipTone = "alta" | "media" | "baixa"
const CHIP_TONE: Record<ChipTone, string> = {
  alta: "bg-red-50 text-red-700 dark:bg-red-950/40 dark:text-red-300",
  media: "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300",
  baixa: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
}
const SEV_TONE: Record<AgenteSinalAlerta["severidade"], ChipTone> = {
  critico: "alta",
  atencao: "media",
  info: "baixa",
}
const SEV_LABEL: Record<AgenteSinalAlerta["severidade"], string> = {
  critico: "Crítico",
  atencao: "Atenção",
  info: "Info",
}
const PRIO_LABEL: Record<AgenteSugestaoAcao["prioridade"], string> = {
  alta: "Alta",
  media: "Média",
  baixa: "Baixa",
}

/** Agrega todos os papeis citados nas explicacoes, deduplicando por documento. */
const collectPapeis = (
  explicacoes: AgenteExplicacaoCategoria[],
): AgentePapelMencionado[] => {
  const seen = new Set<string>()
  const out: AgentePapelMencionado[] = []
  for (const e of explicacoes) {
    for (const p of e.papeis_mencionados) {
      const k = p.numero_documento || p.seu_numero
      if (!k || seen.has(k)) continue
      seen.add(k)
      out.push(p)
    }
  }
  return out
}

// ─── Props ────────────────────────────────────────────────────────────────

export type AgenteVariacaoPanelProps = {
  open:        boolean
  onClose:     () => void
  /** Estado do stream SSE — controla qual corpo o painel renderiza. */
  status:      "idle" | "streaming" | "done" | "error"
  /** Trace ao vivo (tool_use / tool_result / reasoning) — alimenta a timeline. */
  toolsLog:    AgentToolLogEntry[]
  /** ISO em que o stream comecou — alimenta o ticker do timer. */
  startedAt:   string | null
  /** Resultado final (chega no frame `result`). */
  result:      AgenteVariacaoRunResponse | null
  error:       string | null
  onRetry?:    () => void
}

// ─── Componente raiz ──────────────────────────────────────────────────────

export function AgenteVariacaoPanel(props: AgenteVariacaoPanelProps) {
  const { open, onClose, status, toolsLog, startedAt, result, error, onRetry } = props
  return (
    <DrillDownSheet open={open} onClose={onClose} size="xl" title="Análise IA · Variação da Cota Sub Jr">
      <DrillDownSheet.Header
        breadcrumb={["Cota Sub", "Análise IA da variação"]}
        statusSlot={
          <span className="inline-flex items-center gap-1 rounded-sm bg-violet-50 px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-[0.04em] text-violet-700 dark:bg-violet-500/10 dark:text-violet-300">
            <RiSparklingFill className="size-3" aria-hidden />
            agente IA
          </span>
        }
      />
      <DrillDownSheet.Body>
        {status === "streaming" && <LiveState toolsLog={toolsLog} startedAt={startedAt} />}
        {status === "error" && (
          <ErrorState
            title="Falha ao invocar o agente"
            description={error ?? "Erro desconhecido"}
            action={onRetry ? <Button onClick={onRetry}>Tentar novamente</Button> : undefined}
          />
        )}
        {status === "done" && result && <RelatorioProtocolar data={result} />}
      </DrillDownSheet.Body>
    </DrillDownSheet>
  )
}

// ─── Live state — agente trabalhando ao vivo (SSE) ─────────────────────────

function LiveState({
  toolsLog,
  startedAt,
}: {
  toolsLog: AgentToolLogEntry[]
  startedAt: string | null
}) {
  return (
    <div className="flex flex-col gap-3">
      <p className="text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">
        O agente faz sanity check, decompõe as 12 categorias do balanço e investiga
        cruzando estoque × liquidações × histórico. Acompanhe abaixo, em tempo real,
        o que ele está consultando e raciocinando. Pode levar até 90s na primeira
        execução (cacheia depois).
      </p>
      <Card className="p-4">
        <AgentLiveStatus
          startedAt={startedAt}
          toolsLog={toolsLog}
          maxEntries={60}
          fallbackMessage="Conectando ao agente…"
        />
      </Card>
    </div>
  )
}

// ─── Relatorio protocolar (documento) ──────────────────────────────────────

// Ordem canonica do balancete estrutural (espelha compute_balanco_estrutural).
// A secao "Analise por Rubrica" segue ESTA ordem — igual a tela — nao a
// magnitude. Keys batem com os emitidos pelo agente (prompt v7+ le o estrutural).
const BALANCO_ORDER: Record<string, number> = {
  dc_bruto: 0, pdd: 1, titulos_publicos: 2, op_estruturadas: 3, fundos_di: 4,
  compromissada: 5, outros_ativos: 6, tesouraria: 7, saldo_conta_corrente: 8,
  cpr_receber: 9, cpr_pagar: 10, senior: 11, mezanino: 12,
}
const balancoPos = (k: string): number => BALANCO_ORDER[k] ?? 999

function RelatorioProtocolar({ data }: { data: AgenteVariacaoRunResponse }) {
  const { metadata, analise } = data
  const reportNo = reportNoFrom(analise.data, metadata.analysis_run_id)

  const expMap = React.useMemo(() => {
    const m = new Map<string, AgenteExplicacaoCategoria>()
    for (const e of analise.nivel_3_explicacoes) m.set(e.categoria_key, e)
    return m
  }, [analise.nivel_3_explicacoes])

  const byRank = (a: AgenteCategoriaDelta, b: AgenteCategoriaDelta) =>
    a.rank_magnitude - b.rank_magnitude
  // Seção "Por rubrica" segue a ordem do balancete (igual a tela), NAO magnitude.
  const byBalanco = (a: AgenteCategoriaDelta, b: AgenteCategoriaDelta) =>
    balancoPos(a.key) - balancoPos(b.key)
  const ativos = analise.nivel_2_decomposicao.filter((c) => c.tipo === "ativo").sort(byBalanco)
  const passivos = analise.nivel_2_decomposicao.filter((c) => c.tipo === "passivo").sort(byBalanco)

  const papeis = React.useMemo(
    () => collectPapeis(analise.nivel_3_explicacoes),
    [analise.nivel_3_explicacoes],
  )

  const acoes = React.useMemo(() => {
    const ord = { alta: 0, media: 1, baixa: 2 } as const
    return [...analise.sugestoes_acao].sort((a, b) => ord[a.prioridade] - ord[b.prioridade])
  }, [analise.sugestoes_acao])

  const topCats = React.useMemo(
    () =>
      [...analise.nivel_2_decomposicao]
        .filter((c) => Math.abs(c.delta) >= 1)
        .sort(byRank)
        .slice(0, 4),
    [analise.nivel_2_decomposicao],
  )

  // Numeracao contigua das secoes opcionais (4+) — sem buracos quando vazias.
  let secInt = 3
  const constInt = analise.sinais_alerta.length > 0 ? ++secInt : 0
  const papInt = papeis.length > 0 ? ++secInt : 0
  const acaoInt = acoes.length > 0 ? ++secInt : 0

  // Numeracao continua das rubricas (3.1..3.N) atravessando Ativos -> Passivos.
  let rubricaN = 0

  return (
    <div className="text-[13px] leading-relaxed text-gray-900 dark:text-gray-100">
      <MetadataBanner metadata={metadata} />

      <ProtocolHeader analise={analise} reportNo={reportNo} />

      {/* 1.0 SÍNTESE */}
      <Section>
        <SectionHead num="1.0" title="Síntese da Variação" />
        <div className="pl-9">
          <p className="m-0 mb-2">{analise.sumario_executivo}</p>
          {topCats.length > 0 && (
            <ul className="m-0 list-none p-0">
              {topCats.map((c) => {
                const e = expMap.get(c.key)
                const reason = e ? firstSentence(e.narrativa) : ""
                return (
                  <Bullet key={c.key}>
                    <span className="text-gray-600 dark:text-gray-400">{c.label}</span>{" "}
                    <span className={cx("font-mono tabular-nums font-medium", deltaTone(c.delta))}>
                      {fmtBRLSigned(c.delta)}
                    </span>
                    {reason ? (
                      <span className="text-gray-700 dark:text-gray-300"> — {reason}</span>
                    ) : null}
                  </Bullet>
                )
              })}
            </ul>
          )}
        </div>
      </Section>

      {/* 2.0 SANITY CHECK */}
      <Section>
        <SectionHead num="2.0" title="Sanity Check de Identidade Contábil" />
        <div className="pl-9">
          <table className="my-1.5 w-full border-collapse text-[12px]">
            <tbody>
              <KpiRow label="Δ PL calculado (granular)" value={fmtBRLSigned(analise.nivel_1_sanity.pl_deduzido_delta)} />
              <KpiRow label="Δ PL fonte MEC" value={fmtBRLSigned(analise.nivel_1_sanity.pl_fonte_delta)} />
              <KpiRow
                label="Resíduo do dia"
                value={fmtBRLSigned(analise.nivel_1_sanity.residuo_brl)}
                residuo={Math.abs(analise.nivel_1_sanity.residuo_brl) >= 1}
              />
            </tbody>
          </table>
          <p className="m-0 text-[12px] text-gray-600 dark:text-gray-400">
            {analise.nivel_1_sanity.diagnostico}
          </p>
        </div>
      </Section>

      {/* 3.0 ANÁLISE POR RUBRICA */}
      <Section>
        <SectionHead num="3.0" title="Análise por Rubrica" />
        <div className="pl-9">
          <p className="m-0 text-[12px] text-gray-600 dark:text-gray-400">
            Organizada na ordem do balancete: Ativos, depois Passivos e redutores do
            PL. Variação D-1 → D0.
          </p>
        </div>

        {ativos.length > 0 && <GroupHead>Ativos</GroupHead>}
        {ativos.map((cat) => (
          <RubricaSubsection
            key={cat.key}
            num={`3.${++rubricaN}`}
            cat={cat}
            exp={expMap.get(cat.key) ?? null}
          />
        ))}

        {passivos.length > 0 && <GroupHead>Passivos · Redutores</GroupHead>}
        {passivos.map((cat) => (
          <RubricaSubsection
            key={cat.key}
            num={`3.${++rubricaN}`}
            cat={cat}
            exp={expMap.get(cat.key) ?? null}
          />
        ))}
      </Section>

      {/* 4.0 CONSTATAÇÕES DE RISCO */}
      {constInt > 0 && (
        <Section>
          <SectionHead num={`${constInt}.0`} title="Constatações de Risco" />
          {analise.sinais_alerta.map((alerta, i) => (
            <ConstatacaoFinding key={i} num={`${constInt}.${i + 1}`} alerta={alerta} />
          ))}
        </Section>
      )}

      {/* 5.0 PAPÉIS CITADOS */}
      {papInt > 0 && (
        <Section>
          <SectionHead num={`${papInt}.0`} title="Papéis Citados" />
          <div className="pl-9">
            <PapeisTable papeis={papeis} />
          </div>
        </Section>
      )}

      {/* 6.0 AÇÕES REQUERIDAS */}
      {acaoInt > 0 && (
        <Section>
          <SectionHead num={`${acaoInt}.0`} title="Ações Requeridas" />
          {acoes.map((s, i) => (
            <AcaoSubsection key={i} num={`${acaoInt}.${i + 1}`} sugestao={s} />
          ))}
        </Section>
      )}

      <ProtocolFooter metadata={metadata} analise={analise} reportNo={reportNo} />
    </div>
  )
}

// ─── Metadata banner (cache + custo) ──────────────────────────────────────

function MetadataBanner({ metadata }: { metadata: AgenteVariacaoRunResponse["metadata"] }) {
  if (metadata.from_cache) {
    return (
      <div className="mb-4 flex items-center gap-2 rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-[11px] dark:border-emerald-900/40 dark:bg-emerald-950/30">
        <RiDatabaseLine className="size-3.5 shrink-0 text-emerald-700 dark:text-emerald-400" aria-hidden />
        <div className="flex flex-1 flex-wrap items-center gap-x-3 gap-y-0.5 text-emerald-800 dark:text-emerald-200">
          <span className="font-medium">Análise carregada do cache</span>
          <span className="text-emerald-700 dark:text-emerald-300">· {fmtCacheAge(metadata.cache_age_seconds)}</span>
          <span className="text-emerald-700 dark:text-emerald-300">· custo R$ 0,00</span>
          <span className="text-emerald-700 dark:text-emerald-300">· {metadata.model_used}</span>
        </div>
      </div>
    )
  }
  return (
    <div className="mb-4 flex items-center gap-2 rounded border border-violet-200 bg-violet-50 px-3 py-2 text-[11px] dark:border-violet-900/40 dark:bg-violet-950/30">
      <RiSparklingFill className="size-3.5 shrink-0 text-violet-700 dark:text-violet-400" aria-hidden />
      <div className="flex flex-1 flex-wrap items-center gap-x-3 gap-y-0.5 text-violet-800 dark:text-violet-200">
        <span className="font-medium">Análise nova gerada por LLM</span>
        <span>· {metadata.model_used}</span>
        <span>· {fmtDuration(metadata.duration_ms)}</span>
        <span>· custo aprox {fmtBRL.format(metadata.cost_brl_estimated)}</span>
        <span className="text-[10px] text-violet-600 dark:text-violet-400">
          ({(metadata.tokens_input + metadata.tokens_output).toLocaleString("pt-BR")} tokens)
        </span>
      </div>
    </div>
  )
}

// ─── Cabeçalho / rodapé protocolar ──────────────────────────────────────────

function ProtocolHeader({ analise, reportNo }: { analise: AgenteAnaliseVariacao; reportNo: string }) {
  return (
    <div className="mb-4 grid grid-cols-[1fr_auto_1fr] items-start gap-6 border-b-[1.5px] border-gray-900 pb-3.5 dark:border-gray-100">
      <div className="pt-1 text-[11px] font-medium uppercase tracking-[0.04em] text-blue-600 dark:text-blue-400">
        A7 Credit · Strata
      </div>
      <div className="text-center">
        <h1 className="m-0 mb-0.5 text-[18px] font-medium tracking-[0.02em] text-gray-900 dark:text-gray-100">
          Análise de Variação · Cota Sub Jr
        </h1>
        <div className="text-[11px] text-gray-600 dark:text-gray-400">{analise.fundo_nome}</div>
      </div>
      <div className="text-right font-mono text-[10px] leading-[1.7] tabular-nums text-gray-600 dark:text-gray-400">
        <div>
          <span className="text-gray-400 dark:text-gray-600">Relatório nº:</span>{" "}
          <span className="font-medium text-red-600 dark:text-red-400">{reportNo}</span>
        </div>
        <div>
          <span className="text-gray-400 dark:text-gray-600">Data-base:</span> {fmtDateBR(analise.data)}
        </div>
        <div>
          <span className="text-gray-400 dark:text-gray-600">Janela:</span>{" "}
          {fmtDateBR(analise.data_anterior)} → {fmtDateBR(analise.data)}
        </div>
      </div>
    </div>
  )
}

function ProtocolFooter({
  metadata,
  analise,
  reportNo,
}: {
  metadata: AgenteVariacaoRunResponse["metadata"]
  analise: AgenteAnaliseVariacao
  reportNo: string
}) {
  return (
    <div className="mt-6 border-t border-gray-200 pt-3 dark:border-gray-800">
      <div className="grid grid-cols-[1fr_auto_1fr] items-center gap-6 text-[10px] text-gray-400 dark:text-gray-600">
        <span>Confidencial · A7 Credit / Strata</span>
        <span className="text-center">
          {metadata.model_used}
          {metadata.from_cache ? " · cache" : ""}
        </span>
        <span className="text-right font-mono tabular-nums">
          {reportNo} · {fmtDateBR(analise.data)}
        </span>
      </div>
      <p className="mt-2 text-center font-mono text-[9px] text-gray-300 dark:text-gray-700">
        audit {metadata.audit_version} · run {metadata.analysis_run_id}
      </p>
    </div>
  )
}

// ─── Rubrica (3.N) ──────────────────────────────────────────────────────────

function RubricaSubsection({
  num,
  cat,
  exp,
}: {
  num: string
  cat: AgenteCategoriaDelta
  exp: AgenteExplicacaoCategoria | null
}) {
  const isZero = Math.abs(cat.delta) < 0.005
  const papeis = exp?.papeis_mencionados ?? []

  return (
    <div className="mt-3">
      <SubHead num={num} title={cat.label} meta={fmtBRLSigned(cat.delta)} metaTone={deltaTone(cat.delta)} />
      <div className="pl-9 text-[12.5px]">
        {exp ? (
          <>
            <div className="mb-1 flex flex-wrap items-center gap-2 text-[10px] uppercase tracking-[0.04em] text-gray-500 dark:text-gray-400">
              <span className="rounded-sm bg-gray-100 px-1.5 py-0.5 font-medium text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                {humanize(exp.classificacao_principal)}
              </span>
              <span>confiança {(exp.confianca * 100).toFixed(0)}%</span>
            </div>
            <p className="m-0 mb-1.5 leading-relaxed text-gray-900 dark:text-gray-100">{exp.narrativa}</p>
            {papeis.length > 0 && (
              <ul className="m-0 list-none p-0">
                {papeis.map((p, i) => (
                  <Bullet key={i} flag={FLAG_NATUREZA.test(p.natureza)}>
                    <span
                      title={p.seu_numero ? `DID ${p.seu_numero}` : undefined}
                      className="font-mono tabular-nums font-medium"
                    >
                      {p.numero_documento || p.seu_numero}
                    </span>
                    <span className="text-gray-500 dark:text-gray-400">
                      {" · "}
                      {p.cedente_nome} → {p.sacado_nome} · {humanize(p.natureza)} ·{" "}
                    </span>
                    <span className={cx("font-mono tabular-nums font-medium", deltaTone(p.delta_brl))}>
                      {fmtBRLSigned(p.delta_brl)}
                    </span>
                  </Bullet>
                ))}
              </ul>
            )}
          </>
        ) : (
          <ul className="m-0 list-none p-0">
            <Bullet>
              <span className="text-gray-600 dark:text-gray-400">
                {isZero
                  ? "Sem movimento no dia."
                  : "Carrego de rotina · variação sem evento material destacado."}
              </span>
            </Bullet>
          </ul>
        )}
      </div>
    </div>
  )
}

// ─── Constatação (4.N) ──────────────────────────────────────────────────────

function ConstatacaoFinding({ num, alerta }: { num: string; alerta: AgenteSinalAlerta }) {
  return (
    <div className="mt-3">
      <SubHead num={num} title={alerta.entidade} />
      <div className="pl-9">
        <div className="mb-1.5 flex flex-wrap items-baseline gap-2">
          <Chip tone={SEV_TONE[alerta.severidade]} label={SEV_LABEL[alerta.severidade]} />
          <span className="text-[10px] font-medium uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600">
            {humanize(alerta.tipo)}
          </span>
        </div>
        <p className="m-0 mb-1.5 text-[12.5px] font-medium text-gray-900 dark:text-gray-100">
          {alerta.descricao}
        </p>
        {alerta.evidencia && (
          <>
            <p className="mb-1 text-[10px] font-medium uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600">
              Evidência
            </p>
            <pre className="m-0 whitespace-pre-wrap rounded bg-gray-50 px-2.5 py-2 font-mono text-[11px] leading-relaxed tabular-nums text-gray-600 dark:bg-gray-900 dark:text-gray-400">
              {alerta.evidencia}
            </pre>
          </>
        )}
      </div>
    </div>
  )
}

// ─── Papéis citados (5.0) ───────────────────────────────────────────────────

function PapeisTable({ papeis }: { papeis: AgentePapelMencionado[] }) {
  return (
    <table className="mt-2 w-full border-collapse text-[11px]">
      <thead>
        <tr>
          <Th>Documento</Th>
          <Th>Cedente → Sacado</Th>
          <Th>Evento</Th>
          <Th right>Δ no dia</Th>
        </tr>
      </thead>
      <tbody>
        {papeis.map((p, i) => (
          <tr key={i}>
            <td className="border-b border-dashed border-gray-200 py-1.5 pr-2 font-mono font-medium tabular-nums dark:border-gray-800">
              {p.numero_documento || p.seu_numero}
            </td>
            <td className="border-b border-dashed border-gray-200 py-1.5 pr-2 text-gray-600 dark:border-gray-800 dark:text-gray-400">
              {p.cedente_nome} → {p.sacado_nome}
            </td>
            <td className="border-b border-dashed border-gray-200 py-1.5 pr-2 text-[10px] uppercase tracking-[0.04em] text-gray-400 dark:border-gray-800 dark:text-gray-600">
              {humanize(p.natureza)}
            </td>
            <td
              className={cx(
                "border-b border-dashed border-gray-200 py-1.5 text-right font-mono font-medium tabular-nums dark:border-gray-800",
                deltaTone(p.delta_brl),
              )}
            >
              {fmtBRLSigned(p.delta_brl)}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

function Th({ children, right }: { children: React.ReactNode; right?: boolean }) {
  return (
    <th
      className={cx(
        "border-b border-gray-200 py-1 pr-2 text-[9px] font-medium uppercase tracking-[0.06em] text-gray-400 dark:border-gray-800 dark:text-gray-600",
        right ? "text-right" : "text-left",
      )}
    >
      {children}
    </th>
  )
}

// ─── Ação (6.N) ─────────────────────────────────────────────────────────────

function AcaoSubsection({ num, sugestao }: { num: string; sugestao: AgenteSugestaoAcao }) {
  return (
    <div className="mt-3">
      <div className="mb-1 grid grid-cols-[36px_1fr_auto] items-baseline gap-1">
        <span className="font-mono text-[12px] font-medium tabular-nums text-red-600 dark:text-red-400">{num}</span>
        <p className="m-0 text-[12px] font-medium italic text-gray-900 dark:text-gray-100">{sugestao.acao}</p>
        <Chip tone={sugestao.prioridade} label={PRIO_LABEL[sugestao.prioridade]} />
      </div>
      <div className="pl-9">
        <ul className="m-0 list-none p-0">
          <Bullet>
            <span className="text-gray-700 dark:text-gray-300">{sugestao.detalhe}</span>
          </Bullet>
        </ul>
      </div>
    </div>
  )
}

// ─── Primitivos do documento ────────────────────────────────────────────────

function Section({ children }: { children: React.ReactNode }) {
  return <div className="mt-5">{children}</div>
}

function SectionHead({ num, title }: { num: string; title: string }) {
  return (
    <div className="mb-2 grid grid-cols-[36px_1fr] items-baseline gap-1">
      <span className="font-mono text-[13px] font-medium tabular-nums text-gray-900 dark:text-gray-100">{num}</span>
      <h3 className="m-0 text-[13px] font-medium uppercase tracking-[0.01em] text-gray-900 dark:text-gray-100">
        {title}
      </h3>
    </div>
  )
}

function SubHead({
  num,
  title,
  meta,
  metaTone,
}: {
  num: string
  title: string
  meta?: string
  metaTone?: string
}) {
  return (
    <div className="mb-1 grid grid-cols-[36px_1fr_auto] items-baseline gap-1">
      <span className="font-mono text-[12px] font-medium tabular-nums text-red-600 dark:text-red-400">{num}</span>
      <p className="m-0 text-[12px] font-medium italic text-gray-900 dark:text-gray-100">{title}</p>
      {meta ? (
        <span className={cx("whitespace-nowrap text-right font-mono text-[12px] font-medium tabular-nums", metaTone)}>
          {meta}
        </span>
      ) : (
        <span />
      )}
    </div>
  )
}

function GroupHead({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-1 mt-4 border-b border-dashed border-gray-200 pb-1 pl-9 text-[10px] font-medium uppercase tracking-[0.08em] text-gray-400 dark:border-gray-800 dark:text-gray-600">
      {children}
    </p>
  )
}

function Bullet({ flag, children }: { flag?: boolean; children: React.ReactNode }) {
  return (
    <li className="relative py-[3px] pl-4 text-[12.5px] leading-relaxed">
      <span
        className={cx(
          "absolute left-0 top-[3px] text-[11px]",
          flag ? "font-medium text-amber-600 dark:text-amber-500" : "text-gray-500 dark:text-gray-400",
        )}
        aria-hidden
      >
        {flag ? "!" : "—"}
      </span>
      {children}
    </li>
  )
}

function KpiRow({ label, value, residuo }: { label: string; value: string; residuo?: boolean }) {
  return (
    <tr>
      <td
        className={cx(
          "border-b border-gray-200 px-2.5 py-1.5 dark:border-gray-800",
          residuo ? "font-medium text-red-600 dark:text-red-400" : "text-gray-600 dark:text-gray-400",
        )}
      >
        {label}
      </td>
      <td
        className={cx(
          "border-b border-gray-200 px-2.5 py-1.5 text-right font-mono font-medium tabular-nums dark:border-gray-800",
          residuo ? "text-red-600 dark:text-red-400" : "text-gray-900 dark:text-gray-100",
        )}
      >
        {value}
      </td>
    </tr>
  )
}

function Chip({ tone, label }: { tone: ChipTone; label: string }) {
  return (
    <span
      className={cx(
        "rounded-[2px] px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-[0.06em]",
        CHIP_TONE[tone],
      )}
    >
      {label}
    </span>
  )
}

// EmptyState reuse — for completeness when no data
export function AgenteVariacaoEmpty() {
  return (
    <EmptyState
      icon={RiSparklingFill}
      title="Análise IA não invocada"
      description="Clique em 'Explicar variação' no balanço pra invocar o agente."
    />
  )
}
