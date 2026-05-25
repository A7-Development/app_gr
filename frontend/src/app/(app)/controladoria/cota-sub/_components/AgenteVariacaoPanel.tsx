"use client"

/**
 * AgenteVariacaoPanel — renderiza o output do agente IA `controladoria.
 * analista_variacao_cota` num DrillDownSheet right-side `xl`.
 *
 * Estrutura visual:
 *   Header  — badge IA + data + audit_version
 *   Hero    — sumario executivo destacado
 *   Banner  — from_cache + custo + duracao + modelo (transparencia)
 *   Body    — 4 secoes empilhadas:
 *     1. Nivel 1 Sanity (badge passou/divergente + numeros)
 *     2. Alertas (cards por severidade)
 *     3. Sugestoes (cards por prioridade)
 *     4. Decomposicao (Nivel 2 + Nivel 3 com expansao por categoria)
 *   Footer  — link "Ver JSON" + analysis_run_id (dev/audit)
 *
 * Stack: apenas componentes do design-system + tokens + primitivos Remix.
 */

import * as React from "react"
import {
  RiSparklingFill,
  RiCheckLine,
  RiAlertLine,
  RiErrorWarningLine,
  RiArrowDownSLine,
  RiArrowUpSLine,
  RiInformationLine,
  RiSpeakLine,
  RiDatabaseLine,
} from "@remixicon/react"

import { cx } from "@/lib/utils"
import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"
import { Card } from "@/components/tremor/Card"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { Button } from "@/components/tremor/Button"
import type {
  AgenteAnaliseVariacao,
  AgenteCategoriaDelta,
  AgenteExplicacaoCategoria,
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
  return m ? `${m[3]}/${m[2]}/${m[1].slice(2)}` : iso
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

// ─── Cores semanticas ─────────────────────────────────────────────────────

const SEVERIDADE_STYLE: Record<AgenteSinalAlerta["severidade"], { icon: typeof RiInformationLine; cls: string; label: string }> = {
  info:    { icon: RiInformationLine,     cls: "border-blue-200 bg-blue-50 text-blue-700 dark:border-blue-900/60 dark:bg-blue-950/40 dark:text-blue-300",     label: "info"     },
  atencao: { icon: RiAlertLine,            cls: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-300", label: "atenção"  },
  critico: { icon: RiErrorWarningLine,     cls: "border-red-200 bg-red-50 text-red-700 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-300",          label: "crítico"  },
}

const PRIORIDADE_STYLE: Record<AgenteSugestaoAcao["prioridade"], { dot: string; cls: string; label: string }> = {
  alta:  { dot: "bg-red-500",     cls: "text-red-700 dark:text-red-400",     label: "ALTA"  },
  media: { dot: "bg-amber-500",   cls: "text-amber-700 dark:text-amber-400", label: "média" },
  baixa: { dot: "bg-gray-400",    cls: "text-gray-600 dark:text-gray-400",   label: "baixa" },
}

// ─── Props ────────────────────────────────────────────────────────────────

export type AgenteVariacaoPanelProps = {
  open:        boolean
  onClose:     () => void
  loading:     boolean
  error:       string | null
  data:        AgenteVariacaoRunResponse | null
  onRetry?:    () => void
}

// ─── Componente raiz ──────────────────────────────────────────────────────

export function AgenteVariacaoPanel(props: AgenteVariacaoPanelProps) {
  const { open, onClose, loading, error, data, onRetry } = props
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
        {loading && <LoadingState />}
        {error && !loading && (
          <ErrorState
            title="Falha ao invocar o agente"
            description={error}
            action={onRetry ? <Button onClick={onRetry}>Tentar novamente</Button> : undefined}
          />
        )}
        {data && !loading && !error && <AgenteAnaliseBody data={data} />}
      </DrillDownSheet.Body>
    </DrillDownSheet>
  )
}

// ─── Loading state ────────────────────────────────────────────────────────

function LoadingState() {
  return (
    <div className="flex flex-col items-center justify-center gap-4 py-16">
      <div className="relative size-12">
        <div className="absolute inset-0 animate-ping rounded-full bg-violet-200 opacity-50 dark:bg-violet-900/40" />
        <div className="absolute inset-2 flex items-center justify-center rounded-full bg-violet-500 text-white">
          <RiSparklingFill className="size-5" aria-hidden />
        </div>
      </div>
      <div className="flex flex-col items-center gap-1 text-center">
        <p className="text-sm font-medium text-gray-900 dark:text-gray-50">
          Analisando a variação do dia…
        </p>
        <p className="text-[11px] text-gray-500 dark:text-gray-400 max-w-md">
          O agente faz sanity check, decompõe as 12 categorias do balanço e
          investiga cruzando estoque × liquidações × histórico. Pode levar até 90s na primeira execução
          (cacheia depois).
        </p>
      </div>
    </div>
  )
}

// ─── Body principal ───────────────────────────────────────────────────────

function AgenteAnaliseBody({ data }: { data: AgenteVariacaoRunResponse }) {
  const { metadata, analise } = data
  return (
    <div className="flex flex-col gap-4">
      {/* Cache/custo banner */}
      <MetadataBanner metadata={metadata} />

      {/* Hero: sumario executivo */}
      <SumarioCard sumario={analise.sumario_executivo} fundoNome={analise.fundo_nome} data={analise.data} dataAnterior={analise.data_anterior} />

      {/* Nivel 1 Sanity */}
      <SanityCard sanity={analise.nivel_1_sanity} />

      {/* Alertas */}
      {analise.sinais_alerta.length > 0 && <AlertasSection alertas={analise.sinais_alerta} />}

      {/* Sugestoes */}
      {analise.sugestoes_acao.length > 0 && <SugestoesSection sugestoes={analise.sugestoes_acao} />}

      {/* Decomposicao + Explicacoes */}
      <DecomposicaoSection
        decomposicao={analise.nivel_2_decomposicao}
        explicacoes={analise.nivel_3_explicacoes}
      />

      {/* Footer audit */}
      <FooterAudit metadata={metadata} />
    </div>
  )
}

// ─── Metadata banner (cache + custo) ──────────────────────────────────────

function MetadataBanner({ metadata }: { metadata: AgenteVariacaoRunResponse["metadata"] }) {
  if (metadata.from_cache) {
    return (
      <div className="flex items-center gap-2 rounded border border-emerald-200 bg-emerald-50 px-3 py-2 text-[11px] dark:border-emerald-900/40 dark:bg-emerald-950/30">
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
    <div className="flex items-center gap-2 rounded border border-violet-200 bg-violet-50 px-3 py-2 text-[11px] dark:border-violet-900/40 dark:bg-violet-950/30">
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

// ─── Sumario executivo ────────────────────────────────────────────────────

function SumarioCard({ sumario, fundoNome, data, dataAnterior }: { sumario: string; fundoNome: string; data: string; dataAnterior: string }) {
  return (
    <Card className="border-l-4 border-l-violet-500 p-4 dark:border-l-violet-400">
      <div className="mb-2 flex items-center gap-2">
        <RiSpeakLine className="size-4 text-violet-600 dark:text-violet-400" aria-hidden />
        <h3 className="text-[12px] font-semibold uppercase tracking-[0.04em] text-gray-700 dark:text-gray-300">
          Resumo executivo
        </h3>
        <span className="ml-auto text-[11px] text-gray-500 dark:text-gray-400">
          {fundoNome} · {fmtDateBR(dataAnterior)} → {fmtDateBR(data)}
        </span>
      </div>
      <p className="text-[13px] leading-relaxed text-gray-800 dark:text-gray-200">
        {sumario}
      </p>
    </Card>
  )
}

// ─── Sanity check (Nivel 1) ──────────────────────────────────────────────

function SanityCard({ sanity }: { sanity: AgenteAnaliseVariacao["nivel_1_sanity"] }) {
  const passou = sanity.passou
  const Icon = passou ? RiCheckLine : RiAlertLine
  const headerCls = passou
    ? "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/40 dark:bg-emerald-950/30 dark:text-emerald-200"
    : "border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-200"

  return (
    <Card className="overflow-hidden p-0">
      <div className={cx("flex items-center gap-2 border-b px-3 py-2 text-[11px] font-medium", headerCls)}>
        <Icon className="size-3.5" aria-hidden />
        <span>Nível 1 · Sanity Check {passou ? "OK" : "divergente"}</span>
      </div>
      <div className="grid grid-cols-3 gap-2 px-3 py-2 text-[12px] tabular-nums">
        <Metric label="PL calculado (granular)" value={fmtBRLSigned(sanity.pl_deduzido_delta)} />
        <Metric label="PL fonte MEC" value={fmtBRLSigned(sanity.pl_fonte_delta)} />
        <Metric
          label="Resíduo do dia"
          value={fmtBRLSigned(sanity.residuo_brl)}
          tone={
            Math.abs(sanity.residuo_brl) < 1 ? "ok"
              : Math.abs(sanity.residuo_brl) < 100 ? "warn"
              : "alert"
          }
        />
      </div>
      <div className="border-t border-gray-100 px-3 py-2 text-[11px] text-gray-600 dark:border-gray-800 dark:text-gray-400">
        {sanity.diagnostico}
      </div>
    </Card>
  )
}

function Metric({ label, value, tone = "default" }: { label: string; value: string; tone?: "default" | "ok" | "warn" | "alert" }) {
  return (
    <div className="flex flex-col">
      <span className="text-[10px] uppercase tracking-[0.04em] text-gray-400 dark:text-gray-500">{label}</span>
      <span className={cx(
        "font-medium",
        tone === "ok"    && "text-emerald-700 dark:text-emerald-400",
        tone === "warn"  && "text-amber-700 dark:text-amber-400",
        tone === "alert" && "font-semibold text-red-700 dark:text-red-400",
        tone === "default" && "text-gray-900 dark:text-gray-50",
      )}>{value}</span>
    </div>
  )
}

// ─── Alertas ──────────────────────────────────────────────────────────────

function AlertasSection({ alertas }: { alertas: AgenteSinalAlerta[] }) {
  return (
    <section>
      <SectionTitle label="Sinais de alerta" count={alertas.length} />
      <div className="mt-2 flex flex-col gap-2">
        {alertas.map((a, i) => <AlertaCard key={i} alerta={a} />)}
      </div>
    </section>
  )
}

function AlertaCard({ alerta }: { alerta: AgenteSinalAlerta }) {
  const style = SEVERIDADE_STYLE[alerta.severidade]
  const Icon = style.icon
  return (
    <div className={cx("rounded border px-3 py-2", style.cls)}>
      <div className="mb-1 flex items-center gap-2">
        <Icon className="size-3.5 shrink-0" aria-hidden />
        <span className="text-[10px] font-semibold uppercase tracking-[0.04em]">
          {style.label} · {alerta.tipo.replace(/_/g, " ")}
        </span>
      </div>
      <p className="text-[12px] font-medium">{alerta.entidade}</p>
      <p className="mt-1 text-[12px]">{alerta.descricao}</p>
      {alerta.evidencia && (
        <p className="mt-1 text-[10px] italic opacity-80">
          Evidência: {alerta.evidencia}
        </p>
      )}
    </div>
  )
}

// ─── Sugestoes ────────────────────────────────────────────────────────────

function SugestoesSection({ sugestoes }: { sugestoes: AgenteSugestaoAcao[] }) {
  // Ordena por prioridade alta > media > baixa
  const ord = { alta: 0, media: 1, baixa: 2 } as const
  const sorted = [...sugestoes].sort((a, b) => ord[a.prioridade] - ord[b.prioridade])
  return (
    <section>
      <SectionTitle label="Sugestões de ação" count={sugestoes.length} />
      <div className="mt-2 flex flex-col gap-2">
        {sorted.map((s, i) => <SugestaoCard key={i} sugestao={s} />)}
      </div>
    </section>
  )
}

function SugestaoCard({ sugestao }: { sugestao: AgenteSugestaoAcao }) {
  const style = PRIORIDADE_STYLE[sugestao.prioridade]
  return (
    <div className="rounded border border-gray-200 px-3 py-2 dark:border-gray-800">
      <div className="mb-1 flex items-center gap-2">
        <span className={cx("inline-block size-1.5 rounded-full", style.dot)} aria-hidden />
        <span className={cx("text-[10px] font-semibold uppercase tracking-[0.04em]", style.cls)}>
          {style.label}
        </span>
        <span className="text-[12px] font-medium text-gray-900 dark:text-gray-50">
          {sugestao.acao}
        </span>
      </div>
      <p className="text-[12px] text-gray-600 dark:text-gray-400">{sugestao.detalhe}</p>
    </div>
  )
}

// ─── Decomposicao + Explicacoes ───────────────────────────────────────────

function DecomposicaoSection({
  decomposicao,
  explicacoes,
}: {
  decomposicao: AgenteCategoriaDelta[]
  explicacoes: AgenteExplicacaoCategoria[]
}) {
  const expMap = React.useMemo(() => {
    const m = new Map<string, AgenteExplicacaoCategoria>()
    for (const e of explicacoes) m.set(e.categoria_key, e)
    return m
  }, [explicacoes])

  const sorted = React.useMemo(
    () => [...decomposicao].sort((a, b) => a.rank_magnitude - b.rank_magnitude),
    [decomposicao],
  )

  return (
    <section>
      <SectionTitle
        label="Decomposição patrimonial"
        count={decomposicao.length}
        help={`${explicacoes.length} categoria(s) com explicação detalhada`}
      />
      <div className="mt-2 overflow-hidden rounded border border-gray-200 dark:border-gray-800">
        {sorted.map((cat) => {
          const exp = expMap.get(cat.key)
          return <CategoriaRow key={cat.key} cat={cat} explicacao={exp ?? null} />
        })}
      </div>
    </section>
  )
}

function CategoriaRow({ cat, explicacao }: { cat: AgenteCategoriaDelta; explicacao: AgenteExplicacaoCategoria | null }) {
  const [expanded, setExpanded] = React.useState(false)
  const hasExp = explicacao !== null
  const deltaPositive = cat.delta > 0
  const deltaNegative = cat.delta < 0

  return (
    <div className="border-t border-gray-100 first:border-t-0 dark:border-gray-900">
      <button
        type="button"
        disabled={!hasExp}
        onClick={() => hasExp && setExpanded((v) => !v)}
        className={cx(
          "flex w-full items-center gap-2 px-3 py-2 text-left text-[12px] tabular-nums transition-colors",
          hasExp && "cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-900/40",
          !hasExp && "cursor-default",
        )}
      >
        <span className="w-6 text-center text-[10px] font-mono text-gray-400 dark:text-gray-600">
          #{cat.rank_magnitude}
        </span>
        <span className="flex-1 font-medium text-gray-900 dark:text-gray-50">{cat.label}</span>
        <span className="hidden text-right text-gray-500 dark:text-gray-400 sm:inline-block sm:w-28">
          {fmtBRL.format(cat.d1)}
        </span>
        <span className="w-28 text-right text-gray-900 dark:text-gray-50">{fmtBRL.format(cat.d0)}</span>
        <span className={cx(
          "w-28 text-right font-semibold",
          deltaPositive && "text-emerald-700 dark:text-emerald-400",
          deltaNegative && "text-red-700 dark:text-red-400",
          !deltaPositive && !deltaNegative && "text-gray-400 dark:text-gray-600",
        )}>
          {fmtBRLSigned(cat.delta)}
        </span>
        {hasExp ? (
          expanded ? <RiArrowUpSLine className="size-4 text-gray-400" aria-hidden /> : <RiArrowDownSLine className="size-4 text-gray-400" aria-hidden />
        ) : <span className="w-4" />}
      </button>
      {hasExp && expanded && explicacao && (
        <div className="border-t border-gray-100 bg-gray-50/50 px-3 py-3 text-[12px] dark:border-gray-900 dark:bg-gray-900/20">
          <div className="mb-2 flex items-center gap-2 text-[10px] uppercase tracking-[0.04em] text-gray-500 dark:text-gray-400">
            <span className="rounded-sm bg-violet-100 px-1.5 py-0.5 font-medium text-violet-700 dark:bg-violet-500/20 dark:text-violet-300">
              {explicacao.classificacao_principal.replace(/_/g, " ")}
            </span>
            <span>confiança {(explicacao.confianca * 100).toFixed(0)}%</span>
          </div>
          <p className="leading-relaxed text-gray-700 dark:text-gray-300">{explicacao.narrativa}</p>
          {explicacao.papeis_mencionados.length > 0 && (
            <div className="mt-3">
              <p className="mb-1 text-[10px] font-semibold uppercase tracking-[0.04em] text-gray-500 dark:text-gray-400">
                Papéis citados ({explicacao.papeis_mencionados.length})
              </p>
              <ul className="flex flex-col gap-1.5">
                {explicacao.papeis_mencionados.map((p, i) => (
                  <li key={i} className="flex flex-col gap-0.5 rounded border border-gray-200 bg-white px-2 py-1.5 dark:border-gray-800 dark:bg-gray-950">
                    <div className="flex items-center justify-between gap-2 tabular-nums">
                      <span className="font-mono text-[11px] text-gray-700 dark:text-gray-300">{p.seu_numero}</span>
                      <span className={cx(
                        "font-medium",
                        p.delta_brl > 0 ? "text-emerald-700 dark:text-emerald-400" : p.delta_brl < 0 ? "text-red-700 dark:text-red-400" : "text-gray-400",
                      )}>
                        {fmtBRLSigned(p.delta_brl)}
                      </span>
                    </div>
                    <span className="text-[10px] text-gray-500 dark:text-gray-400">
                      {p.cedente_nome} → {p.sacado_nome}
                    </span>
                    <span className="text-[10px] italic text-gray-500 dark:text-gray-500">
                      {p.natureza}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─── Helpers ─────────────────────────────────────────────────────────────

function SectionTitle({ label, count, help }: { label: string; count?: number; help?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <h4 className="flex items-center gap-1.5 text-[12px] font-semibold uppercase tracking-[0.04em] text-gray-700 dark:text-gray-300">
        {label}
        {count !== undefined && (
          <span className="rounded-full bg-gray-100 px-1.5 text-[10px] text-gray-600 dark:bg-gray-800 dark:text-gray-400">
            {count}
          </span>
        )}
      </h4>
      {help && <span className="text-[11px] text-gray-400 dark:text-gray-600">{help}</span>}
    </div>
  )
}

function FooterAudit({ metadata }: { metadata: AgenteVariacaoRunResponse["metadata"] }) {
  return (
    <div className="border-t border-gray-100 pt-3 text-[10px] text-gray-400 dark:border-gray-800 dark:text-gray-600">
      <p className="font-mono">audit: {metadata.audit_version}</p>
      <p className="font-mono">run: {metadata.analysis_run_id}</p>
    </div>
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
