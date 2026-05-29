"use client"

/**
 * AgenteVariacaoPanel — renderiza o output do agente IA `controladoria.
 * analista_variacao_cota` (redesign 2026-05-29) num DrillDownSheet right-side `xl`.
 *
 * Leitura em camadas, do macro ao detalhe:
 *   MetadataBanner   — from_cache + custo + duracao + modelo (transparencia §14)
 *   Header           — titulo + fundo + janela D-1 -> D0
 *   MACRO            — 3 KPIs (Δ PL Sub = Δ Ativo - Δ Passivo) + leitura + selo de sanity
 *   OFENSORES        — top movimentos por impacto no PL Sub, bullets de 5s (atipico realcado)
 *   GRUPOS           — Accordion na ordem da tabela (Ativos -> Passivos): bullets primeiro,
 *                      explicacao depois, papeis quando relevante; atipicos abertos por default
 *   CONCLUSAO        — fecho curto
 *   ALERTAS          — so os atipicos materiais, por severidade
 *   Footer           — proveniencia (modelo + audit + run)
 *
 * Stack: design-system + primitivos Tremor (Accordion, Badge, Card) + tokens.
 * O agente entrega numeros com sinal de IMPACTO ja corrigido (impacto_pl_sub) —
 * a UI nao reinterpreta sinal.
 */

import * as React from "react"
import { RiSparklingFill, RiDatabaseLine, RiAlertFill } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"
import { Card } from "@/components/tremor/Card"
import { Badge } from "@/components/tremor/Badge"
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "@/components/tremor/Accordion"
import { EmptyState } from "@/design-system/components/EmptyState"
import { ErrorState } from "@/design-system/components/ErrorState"
import { Button } from "@/components/tremor/Button"
import {
  AgentLiveStatus,
  type AgentToolLogEntry,
} from "@/design-system/components/AgentLiveStatus"
import type {
  AgenteAnaliseVariacao,
  AgenteGrupoAnalise,
  AgenteOfensorLinha,
  AgentePapelMencionado,
  AgenteSinalAlerta,
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

const humanize = (s: string | null | undefined): string => (s || "").replace(/_/g, " ")

/** Cor por sinal de IMPACTO no PL Sub: positivo ajudou (verde), negativo pressionou (vermelho). */
const impactoTone = (v: number): string =>
  v > 0.005
    ? "text-emerald-700 dark:text-emerald-400"
    : v < -0.005
      ? "text-red-700 dark:text-red-400"
      : "text-gray-400 dark:text-gray-600"

type Severidade = "ok" | "info" | "atencao" | "critico"
const SEV_BADGE: Record<Severidade, "success" | "neutral" | "warning" | "error"> = {
  ok: "success",
  info: "neutral",
  atencao: "warning",
  critico: "error",
}
const SEV_LABEL: Record<Severidade, string> = {
  ok: "Fechamento sadio",
  info: "Info",
  atencao: "Atenção",
  critico: "Crítico",
}

// Ordem canonica do balancete estrutural (espelha compute_balanco_estrutural).
const BALANCO_ORDER: Record<string, number> = {
  dc_bruto: 0, pdd: 1, titulos_publicos: 2, op_estruturadas: 3, fundos_di: 4,
  compromissada: 5, outros_ativos: 6, tesouraria: 7, saldo_conta_corrente: 8,
  cpr_receber: 9, cpr_pagar: 10, senior: 11, mezanino: 12,
}
const balancoPos = (k: string): number => BALANCO_ORDER[k] ?? 999

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
        {status === "done" && result && <Relatorio data={result} />}
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
        O agente faz o sanity check, monta a macro (Ativo × Passivo), rankeia os
        ofensores e abre grupo a grupo cruzando estoque × liquidações × histórico.
        Acompanhe abaixo, em tempo real, o que ele consulta e raciocina. Pode levar
        até 90s na primeira execução (cacheia depois).
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

// ─── Relatorio (documento) ──────────────────────────────────────────────────

function Relatorio({ data }: { data: AgenteVariacaoRunResponse }) {
  const { metadata, analise } = data
  const { macro } = analise

  // Grupos na ordem da tabela (defensivo — o agente ja deve emitir assim).
  const grupos = React.useMemo(
    () => [...analise.grupos].sort((a, b) => balancoPos(a.key) - balancoPos(b.key)),
    [analise.grupos],
  )
  // Atipicos abrem por default no accordion.
  const defaultAbertos = React.useMemo(
    () => grupos.filter((g) => g.atipico).map((g) => g.key),
    [grupos],
  )

  return (
    <div className="flex flex-col gap-5 text-[13px] leading-relaxed text-gray-900 dark:text-gray-100">
      <MetadataBanner metadata={metadata} />
      <Header analise={analise} />

      {/* MACRO */}
      <section className="flex flex-col gap-2">
        <SectionHead title="Macro · Ativo × Passivo" />
        <div className="grid grid-cols-3 gap-2">
          <MacroKpi label="Δ PL Sub Jr" value={fmtBRLSigned(macro.pl_sub_delta)} tone={impactoTone(macro.pl_sub_delta)} />
          <MacroKpi label="Δ Ativos" value={fmtBRLSigned(macro.total_ativo_delta)} />
          <MacroKpi label="Δ Passivos" value={fmtBRLSigned(macro.total_passivo_delta)} />
        </div>
        <p className="m-0 text-[12.5px] text-gray-700 dark:text-gray-300">{macro.leitura}</p>
        <SanitySelo sanity={macro.sanity} />
      </section>

      {/* OFENSORES */}
      {analise.ofensores.length > 0 && (
        <section className="flex flex-col gap-2">
          <SectionHead title="Maiores ofensores" hint="Por impacto no PL Sub" />
          <Card className="p-3">
            <ul className="m-0 flex list-none flex-col gap-1.5 p-0">
              {analise.ofensores.map((o) => (
                <OfensorBullet key={`${o.lado}-${o.key}`} ofensor={o} />
              ))}
            </ul>
          </Card>
        </section>
      )}

      {/* GRUPOS */}
      {grupos.length > 0 && (
        <section className="flex flex-col gap-2">
          <SectionHead title="Análise por grupo" hint="Ordem do balanço · Ativos → Passivos" />
          <Accordion type="multiple" defaultValue={defaultAbertos}>
            {grupos.map((g) => (
              <GrupoItem key={g.key} grupo={g} />
            ))}
          </Accordion>
        </section>
      )}

      {/* CONCLUSAO */}
      {analise.conclusao && (
        <section className="flex flex-col gap-2">
          <SectionHead title="Conclusão" />
          <Card className="border-l-2 border-l-violet-400 p-3 text-[12.5px] text-gray-800 dark:border-l-violet-500 dark:text-gray-200">
            {analise.conclusao}
          </Card>
        </section>
      )}

      {/* ALERTAS */}
      {analise.alertas.length > 0 && (
        <section className="flex flex-col gap-2">
          <SectionHead title="Alertas" hint="Atípicos materiais" />
          <div className="flex flex-col gap-2">
            {analise.alertas.map((a, i) => (
              <AlertaCard key={i} alerta={a} />
            ))}
          </div>
        </section>
      )}

      <Footer metadata={metadata} analise={analise} />
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

// ─── Header ─────────────────────────────────────────────────────────────────

function Header({ analise }: { analise: AgenteAnaliseVariacao }) {
  return (
    <div className="flex items-baseline justify-between border-b border-gray-200 pb-2 dark:border-gray-800">
      <div>
        <h1 className="m-0 text-[16px] font-medium text-gray-900 dark:text-gray-100">
          Variação da Cota Sub Jr
        </h1>
        <div className="text-[11px] text-gray-500 dark:text-gray-400">{analise.fundo_nome}</div>
      </div>
      <div className="text-right text-[11px] tabular-nums text-gray-500 dark:text-gray-400">
        {fmtDateBR(analise.data_anterior)} → {fmtDateBR(analise.data)}
      </div>
    </div>
  )
}

// ─── Macro ────────────────────────────────────────────────────────────────

function MacroKpi({ label, value, tone }: { label: string; value: string; tone?: string }) {
  return (
    <Card className="p-3">
      <div className="text-[10px] font-medium uppercase tracking-[0.04em] text-gray-500 dark:text-gray-400">
        {label}
      </div>
      <div className={cx("mt-1 font-mono text-[18px] font-medium tabular-nums", tone ?? "text-gray-900 dark:text-gray-100")}>
        {value}
      </div>
    </Card>
  )
}

function SanitySelo({ sanity }: { sanity: AgenteAnaliseVariacao["macro"]["sanity"] }) {
  const sev = sanity.severidade as Severidade
  return (
    <div className="flex flex-wrap items-center gap-2 text-[11px] text-gray-500 dark:text-gray-400">
      <Badge variant={SEV_BADGE[sev]}>{SEV_LABEL[sev]}</Badge>
      <span>
        Resíduo do dia <span className="font-mono tabular-nums">{fmtBRLSigned(sanity.residuo_brl)}</span>
      </span>
      {!sanity.deve_continuar && (
        <span className="font-medium text-red-700 dark:text-red-400">
          · pipeline com furo — análise interrompida
        </span>
      )}
    </div>
  )
}

// ─── Ofensores ───────────────────────────────────────────────────────────

function OfensorBullet({ ofensor }: { ofensor: AgenteOfensorLinha }) {
  return (
    <li className="flex items-start gap-2">
      <span
        className={cx(
          "mt-[3px] shrink-0 text-[11px]",
          ofensor.atipico ? "text-amber-600 dark:text-amber-500" : "text-gray-400 dark:text-gray-600",
        )}
        aria-hidden
      >
        {ofensor.atipico ? <RiAlertFill className="size-3.5" /> : "—"}
      </span>
      <div className="min-w-0 flex-1 text-[12.5px]">
        <span className="font-medium text-gray-900 dark:text-gray-100">{ofensor.label}</span>{" "}
        <span className={cx("font-mono tabular-nums font-medium", impactoTone(ofensor.impacto_pl_sub))}>
          {fmtBRLSigned(ofensor.impacto_pl_sub)}
        </span>
        {ofensor.atipico && (
          <Badge variant="warning" className="ml-1.5 align-middle">atípico</Badge>
        )}
        <span className="text-gray-600 dark:text-gray-400"> — {ofensor.bullet}</span>
      </div>
    </li>
  )
}

// ─── Grupo (Accordion item) ─────────────────────────────────────────────────

function GrupoItem({ grupo }: { grupo: AgenteGrupoAnalise }) {
  return (
    <AccordionItem value={grupo.key}>
      <AccordionTrigger>
        <div className="flex flex-1 items-center justify-between gap-3 pr-2">
          <span className="flex items-center gap-2 text-left">
            {grupo.atipico && (
              <RiAlertFill className="size-3.5 shrink-0 text-amber-600 dark:text-amber-500" aria-hidden />
            )}
            <span className="font-medium text-gray-900 dark:text-gray-100">{grupo.label}</span>
            {grupo.atipico && <Badge variant="warning">atípico</Badge>}
          </span>
          <span className={cx("shrink-0 font-mono text-[12px] tabular-nums font-medium", impactoTone(grupo.impacto_pl_sub))}>
            {fmtBRLSigned(grupo.impacto_pl_sub)}
          </span>
        </div>
      </AccordionTrigger>
      <AccordionContent>
        <div className="flex flex-col gap-2 text-[12.5px]">
          {grupo.atipicidade && (
            <div className="flex items-start gap-2 rounded bg-amber-50 px-2.5 py-1.5 text-[12px] text-amber-800 dark:bg-amber-950/30 dark:text-amber-200">
              <RiAlertFill className="mt-[2px] size-3.5 shrink-0" aria-hidden />
              <span>{grupo.atipicidade.motivo}</span>
            </div>
          )}
          {grupo.classificacao && (
            <div>
              <Badge variant="neutral">{humanize(grupo.classificacao)}</Badge>
            </div>
          )}
          {grupo.bullets.length > 0 && (
            <ul className="m-0 flex list-none flex-col gap-1 p-0">
              {grupo.bullets.map((b, i) => (
                <li key={i} className="relative pl-4 leading-relaxed">
                  <span className="absolute left-0 top-0 text-gray-400 dark:text-gray-600" aria-hidden>—</span>
                  {b}
                </li>
              ))}
            </ul>
          )}
          {grupo.explicacao && (
            <p className="m-0 leading-relaxed text-gray-700 dark:text-gray-300">{grupo.explicacao}</p>
          )}
          {grupo.papeis.length > 0 && <PapeisInline papeis={grupo.papeis} />}
          <div className="text-[10px] tabular-nums text-gray-400 dark:text-gray-600">
            D-1 {fmtBRL.format(grupo.d1)} → D0 {fmtBRL.format(grupo.d0)} · Δ {fmtBRLSigned(grupo.delta)}
          </div>
        </div>
      </AccordionContent>
    </AccordionItem>
  )
}

function PapeisInline({ papeis }: { papeis: AgentePapelMencionado[] }) {
  return (
    <table className="w-full border-collapse text-[11px]">
      <tbody>
        {papeis.map((p, i) => (
          <tr key={i}>
            <td
              className="border-b border-dashed border-gray-200 py-1 pr-2 font-mono font-medium tabular-nums dark:border-gray-800"
              title={p.seu_numero ? `DID ${p.seu_numero}` : undefined}
            >
              {p.numero_documento || p.seu_numero}
            </td>
            <td className="border-b border-dashed border-gray-200 py-1 pr-2 text-gray-500 dark:border-gray-800 dark:text-gray-400">
              {p.cedente_nome} → {p.sacado_nome}
              <span className="text-[10px] uppercase tracking-[0.04em] text-gray-400 dark:text-gray-600"> · {humanize(p.natureza)}</span>
            </td>
            <td
              className={cx(
                "border-b border-dashed border-gray-200 py-1 text-right font-mono font-medium tabular-nums dark:border-gray-800",
                impactoTone(p.delta_brl),
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

// ─── Alertas ────────────────────────────────────────────────────────────────

function AlertaCard({ alerta }: { alerta: AgenteSinalAlerta }) {
  const sev = alerta.severidade as Severidade
  const tone =
    sev === "critico"
      ? "border-l-red-500 dark:border-l-red-500"
      : sev === "atencao"
        ? "border-l-amber-400 dark:border-l-amber-500"
        : "border-l-gray-300 dark:border-l-gray-700"
  return (
    <Card className={cx("border-l-2 p-3", tone)}>
      <div className="mb-1 flex flex-wrap items-center gap-2">
        <Badge variant={SEV_BADGE[sev]}>{SEV_LABEL[sev]}</Badge>
        <span className="text-[10px] font-medium uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600">
          {humanize(alerta.tipo)}
        </span>
        <span className="text-[12px] font-medium text-gray-900 dark:text-gray-100">{alerta.entidade}</span>
      </div>
      <p className="m-0 text-[12.5px] text-gray-800 dark:text-gray-200">{alerta.descricao}</p>
      {alerta.evidencia && (
        <p className="m-0 mt-1 font-mono text-[11px] leading-relaxed tabular-nums text-gray-500 dark:text-gray-400">
          {alerta.evidencia}
        </p>
      )}
    </Card>
  )
}

// ─── Footer (proveniencia §14) ──────────────────────────────────────────────

function Footer({
  metadata,
  analise,
}: {
  metadata: AgenteVariacaoRunResponse["metadata"]
  analise: AgenteAnaliseVariacao
}) {
  return (
    <div className="mt-2 border-t border-gray-200 pt-2 text-center dark:border-gray-800">
      <p className="m-0 text-[10px] text-gray-400 dark:text-gray-600">
        Confidencial · A7 Credit / Strata · {metadata.model_used}
        {metadata.from_cache ? " · cache" : ""} · {fmtDateBR(analise.data)}
      </p>
      <p className="m-0 mt-1 font-mono text-[9px] text-gray-300 dark:text-gray-700">
        audit {metadata.audit_version} · run {metadata.analysis_run_id}
      </p>
    </div>
  )
}

// ─── Section head ────────────────────────────────────────────────────────────

function SectionHead({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex items-baseline justify-between">
      <h3 className="m-0 text-[12px] font-medium uppercase tracking-[0.04em] text-gray-900 dark:text-gray-100">
        {title}
      </h3>
      {hint && (
        <span className="text-[10px] uppercase tracking-[0.04em] text-gray-400 dark:text-gray-600">{hint}</span>
      )}
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
