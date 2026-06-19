// src/design-system/components/SectionRenderer/index.tsx
//
// RENDERIZADOR ÚNICO da esteira de crédito (Fase 1 / Etapa 2).
// Ver docs/esteira-credito-interface-camadas.md.
//
// Consome um `SectionDescriptor` e desenha seus blocos. NÃO sabe se o descritor
// veio de um agente, de uma consulta, de um check ou de um documento — a
// consistência é POR CONSTRUÇÃO: só existem os tipos de bloco da Camada C, cada
// um renderiza de um jeito só, em todo lugar. O MESMO componente serve o
// workbench (`mode="work"`, editável) e o dossiê (`mode="read"`, projeção).

"use client"

import * as React from "react"
import {
  RiAlertLine,
  RiErrorWarningLine,
  RiFileTextLine,
  RiInformationLine,
  RiQuillPenLine,
} from "@remixicon/react"
import ReactMarkdown from "react-markdown"
import remarkGfm from "remark-gfm"

import { KpiChartCard } from "@/design-system/components/KpiChartCard"
import { AgentConclusion } from "@/design-system/components/AgentConclusion"
import { DevZoneLabel } from "@/design-system/components/DevZoneLabel"
import { DenseTable, type DenseColumn, type DenseRow } from "@/design-system/components/DenseTable"
import { ProvenanceValue } from "@/design-system/components/Provenance"
import { provenanceTokens, type ProvenanceRef } from "@/design-system/tokens/provenance"
import { tableTokens } from "@/design-system/tokens/table"
import type {
  Apontamento,
  ApontamentosBlock,
  Block,
  ConclusaoAgenteBlock,
  ConferenciaBlock,
  FichaBlock,
  FonteOrigemBlock,
  GraficoBlock,
  RenderMode,
  SectionDescriptor,
  SubDossieBlock,
  TabelaBlock,
  TextoBlock,
} from "@/design-system/types/section"
import { cx } from "@/lib/utils"
import { useZonas } from "@/lib/zonasOverlay"

// ─── Tons (reaproveita a paleta semântica das views migradas) ────────────────

const SEV_TONE: Record<Apontamento["severidade"], string> = {
  critico: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
  atencao: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
  info: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
}

const BADGE_TONE = {
  ok: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
  atencao: "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300",
  critico: "bg-red-50 text-red-700 dark:bg-red-500/10 dark:text-red-300",
  neutro: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
} as const

const SEV_ICON: Record<Apontamento["severidade"], typeof RiAlertLine> = {
  critico: RiErrorWarningLine,
  atencao: RiAlertLine,
  info: RiInformationLine,
}

// Cor do ícone no modo READ (documento): sem badge/card, só o glifo colorido.
const READ_SEV_ICON_COLOR: Record<Apontamento["severidade"], string> = {
  critico: "text-red-600",
  atencao: "text-amber-600",
  info: "text-gray-400",
}

// ─── Sup de lastro (citação inline = proveniência + localizador) ──────────────

function ProvenanceSup({ provenance }: { provenance?: ProvenanceRef }) {
  if (!provenance) return null
  const t = provenanceTokens[provenance.origin]
  // Só renderiza o sup quando há citação (localizador) — proveniência sem drill
  // fino não polui o texto.
  if (!provenance.locator) return null
  return (
    <sup
      className="ml-0.5 align-super text-[9px] font-semibold"
      style={{ color: t.color }}
      title={`${t.label} — citação`}
    >
      {t.supPrefix}
    </sup>
  )
}

// ════════════════════════════════════════════════════════════════════════════
// Blocos (Camada C)
// ════════════════════════════════════════════════════════════════════════════

function FichaBlockView({ block }: { block: FichaBlock }) {
  return (
    <div className="space-y-1.5">
      {block.titulo && <p className={cx(tableTokens.header, "mb-1")}>{block.titulo}</p>}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {block.campos.map((c, i) => (
          <div key={i} className="flex flex-col gap-0.5">
            <span className={tableTokens.header}>{c.label}</span>
            <span className="text-sm text-gray-900 dark:text-gray-100">
              {/* C1 co-autoria: o valor carrega a assinatura na propria prosa
                  (sublinha por origem) + sup de lastro quando ha citacao. */}
              {c.provenance ? (
                <ProvenanceValue
                  origin={c.provenance.origin}
                  homologado={c.provenance.homologado}
                >
                  {c.valor}
                </ProvenanceValue>
              ) : (
                c.valor
              )}
              <ProvenanceSup provenance={c.provenance} />
              {c.badge && (
                <span className={cx(tableTokens.badge, BADGE_TONE[c.badge.tom], "ml-1.5")}>
                  {c.badge.texto}
                </span>
              )}
            </span>
            {c.nota && <p className={tableTokens.cellSecondary}>{c.nota}</p>}
          </div>
        ))}
      </div>
    </div>
  )
}

function TabelaBlockView({ block }: { block: TabelaBlock }) {
  // Mapeia o contrato do bloco -> <DenseTable> canônica (mesmo look, agora
  // padronizado). Célula do bloco é {valor, provenance?}; a DenseTable consome
  // o valor cru e formata por coluna.
  const columns: DenseColumn[] = block.colunas.map((c) => ({
    key: c.key,
    label: c.label,
    align: c.align,
    format: c.formato,
  }))
  const toRow = (r: Record<string, { valor: string | number | null }>): DenseRow => {
    const out: DenseRow = {}
    for (const c of block.colunas) out[c.key] = r[c.key]?.valor ?? null
    return out
  }
  return (
    <DenseTable
      caption={block.titulo}
      columns={columns}
      rows={block.linhas.map(toRow)}
      footer={block.rodape ? toRow(block.rodape) : undefined}
    />
  )
}

function GraficoBlockView({ block }: { block: GraficoBlock }) {
  // Usa a 1ª série como dado do KpiChartCard (anatomia canônica L1/L2/L3).
  const serie = block.series[0]
  const data = (serie?.pontos ?? []).map((p) => ({ label: p.x, value: p.y }))
  return (
    <KpiChartCard
      eyebrow={block.kpi?.eyebrow ?? block.titulo ?? ""}
      value={block.kpi?.valor ?? ""}
      delta={block.kpi?.delta}
      context={block.kpi?.contexto}
      data={data}
    />
  )
}

function ConclusaoAgenteBlockView({ block, mode }: { block: ConclusaoAgenteBlock; mode: RenderMode }) {
  return (
    <AgentConclusion
      homologado={block.homologado || mode === "read"}
      eyebrow={`Leitura do agente — ${block.agente}`}
      tag={mode === "work" ? "julgamento · editável" : undefined}
    >
      <p className="text-sm text-gray-900 dark:text-gray-100">{block.resumo}</p>
      {block.recomendacao && (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span
            className={cx(
              tableTokens.badge,
              block.recomendacao.veredito === "aprovar"
                ? BADGE_TONE.ok
                : block.recomendacao.veredito === "negar"
                  ? BADGE_TONE.critico
                  : BADGE_TONE.atencao,
            )}
          >
            {block.recomendacao.veredito}
          </span>
          {block.recomendacao.condicoes?.map((c, i) => (
            <span key={i} className={tableTokens.cellSecondary}>
              · {c}
            </span>
          ))}
        </div>
      )}
    </AgentConclusion>
  )
}

function ApontamentosBlockView({ block, mode }: { block: ApontamentosBlock; mode: RenderMode }) {
  if (block.itens.length === 0) return null

  // READ (dossiê): estilo documento — ícone colorido + título + descrição, sem
  // card/badge de workbench. Espelha o §Apontamentos da projeção A4.
  if (mode === "read") {
    return (
      <div>
        <p className={cx(tableTokens.header, "mb-1.5")}>
          {block.titulo ?? "Apontamentos e cruzamentos"}
        </p>
        <ul className="space-y-2.5">
          {block.itens.map((p, i) => {
            const Icon = SEV_ICON[p.severidade]
            return (
              <li key={i} className="flex items-start gap-2.5">
                <Icon
                  className={cx("mt-0.5 size-4 shrink-0", READ_SEV_ICON_COLOR[p.severidade])}
                  aria-hidden
                />
                <div className="min-w-0">
                  <p className="text-[13px] font-semibold text-gray-900 dark:text-gray-50">
                    {p.titulo}
                    <ProvenanceSup provenance={p.provenance} />
                  </p>
                  {p.descricao && (
                    <p className="mt-0.5 text-[12.5px] leading-relaxed text-gray-600 dark:text-gray-400">
                      {p.descricao}
                    </p>
                  )}
                  {p.evidencia && (
                    <p className="mt-0.5 text-[12px] italic text-gray-500 dark:text-gray-500">
                      {p.evidencia}
                    </p>
                  )}
                </div>
              </li>
            )
          })}
        </ul>
      </div>
    )
  }

  // WORK (workbench): cards com badge de severidade.
  return (
    <div>
      <p className={cx(tableTokens.header, "mb-1")}>{block.titulo ?? "Pontos de atenção"}</p>
      <ul className="space-y-1.5">
        {block.itens.map((p, i) => {
          const Icon = SEV_ICON[p.severidade]
          return (
            <li
              key={i}
              className="flex items-start gap-2 rounded-md border border-gray-100 bg-gray-50/50 p-2 dark:border-gray-900 dark:bg-gray-950/40"
            >
              <span className={cx(tableTokens.badge, SEV_TONE[p.severidade], "inline-flex items-center gap-1")}>
                <Icon className="size-3" aria-hidden />
                {p.severidade}
              </span>
              <div className="min-w-0 flex-1">
                <p className="text-xs text-gray-900 dark:text-gray-100">
                  {p.titulo}
                  <ProvenanceSup provenance={p.provenance} />
                </p>
                {p.descricao && <p className={tableTokens.cellSecondary}>{p.descricao}</p>}
                {p.evidencia && (
                  <p className={cx(tableTokens.cellMuted, "mt-0.5 italic")}>{p.evidencia}</p>
                )}
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

function TextoBlockView({ block, mode }: { block: TextoBlock; mode: RenderMode }) {
  // "Sua análise" (analista, complementar): voz humana de 1ª classe, ao lado da
  // leitura da IA, nunca a substitui. Assinatura grafite (borda esquerda dupla).
  // Co-autoria C1. O texto editável (autosave) é a versão interativa — wiring na
  // estação; aqui rende a contribuição (work header + read "Análise do analista").
  if (block.provenance?.origin === "analista") {
    const grafite = provenanceTokens.analista
    return (
      <div
        className="rounded-md bg-gray-50/70 py-2 pl-3 pr-3 dark:bg-gray-900/40"
        style={{ borderLeft: `3px double ${grafite.color}` }}
      >
        <div className="mb-1 flex flex-wrap items-center gap-1.5">
          <RiQuillPenLine
            className="size-3.5 shrink-0"
            style={{ color: grafite.color }}
            aria-hidden
          />
          <span
            className="text-[11px] font-semibold uppercase tracking-[0.06em]"
            style={{ color: grafite.chipText }}
          >
            {mode === "read" ? "Análise do analista" : "Sua análise — complementar"}
          </span>
          {mode === "work" && (
            <span
              className={cx(
                tableTokens.badge,
                "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
              )}
            >
              soma à da IA · não a substitui
            </span>
          )}
        </div>
        <div className="prose prose-sm max-w-none text-sm leading-relaxed text-gray-800 dark:prose-invert dark:text-gray-200">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.markdown}</ReactMarkdown>
        </div>
      </div>
    )
  }

  // Trecho VERBATIM do documento (assinatura documento, verde tracejada). Voz do
  // doc, não do agente — distingue cláusula transcrita de leitura da IA. Co-autoria
  // C1: a borda esquerda tracejada verde marca a origem na própria prosa.
  if (block.provenance?.origin === "documento") {
    const verde = provenanceTokens.documento
    return (
      <div
        className="rounded-md bg-emerald-50/40 py-2 pl-3 pr-3 dark:bg-emerald-500/5"
        style={{ borderLeft: `3px dashed ${verde.color}` }}
      >
        <div className="mb-1 flex flex-wrap items-center gap-1.5">
          <RiFileTextLine
            className="size-3.5 shrink-0"
            style={{ color: verde.color }}
            aria-hidden
          />
          <span
            className="text-[11px] font-semibold uppercase tracking-[0.06em]"
            style={{ color: verde.chipText }}
          >
            {block.titulo ?? "Trecho do documento"}
          </span>
          <span
            className={cx(
              tableTokens.badge,
              "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
            )}
          >
            transcrito · não interpretado
          </span>
        </div>
        <div className="prose prose-sm max-w-none text-sm leading-relaxed text-gray-800 dark:prose-invert dark:text-gray-200">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.markdown}</ReactMarkdown>
        </div>
      </div>
    )
  }

  // READ (dossiê): prosa de documento, sem a caixa azul de destaque do workbench.
  if (mode === "read") {
    return (
      <div>
        {block.titulo && <p className={cx(tableTokens.header, "mb-1")}>{block.titulo}</p>}
        <div className="prose prose-sm max-w-none text-sm leading-relaxed text-gray-700 dark:prose-invert dark:text-gray-300">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.markdown}</ReactMarkdown>
        </div>
      </div>
    )
  }

  // WORK: caixa azul de destaque ("leitura para crédito").
  return (
    <div className="rounded-md bg-blue-50/60 p-2.5 dark:bg-blue-500/10">
      {block.titulo && (
        <p className={cx(tableTokens.header, "mb-0.5 text-blue-700 dark:text-blue-300")}>
          {block.titulo}
        </p>
      )}
      <div className="prose prose-sm max-w-none text-sm text-gray-900 dark:prose-invert dark:text-gray-100">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{block.markdown}</ReactMarkdown>
      </div>
    </div>
  )
}

function ConferenciaBlockView({ block }: { block: ConferenciaBlock }) {
  // Etapa 2: render fiel (display). A edição inline + autosave entra quando a
  // estação de documento migrar (a interação mora no DocumentZones hoje).
  return (
    <div className="space-y-1.5">
      {block.titulo && <p className={cx(tableTokens.header, "mb-1")}>{block.titulo}</p>}
      <div className="overflow-hidden rounded-md border border-gray-200 dark:border-gray-800">
        <table className="w-full">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50/60 dark:border-gray-900 dark:bg-gray-900/40">
              <th className={cx(tableTokens.header, "px-3 py-1 text-left")}>Campo</th>
              <th className={cx(tableTokens.header, "px-3 py-1 text-left")}>IA propôs</th>
              <th className={cx(tableTokens.header, "px-3 py-1 text-left")}>No dossiê</th>
            </tr>
          </thead>
          <tbody>
            {block.linhas.map((l, i) => (
              <tr key={i} className="border-b border-gray-50 last:border-0 dark:border-gray-900/60">
                <td className="px-3 py-0.5">
                  <span className={tableTokens.cellText}>{l.campo}</span>
                </td>
                <td className="px-3 py-0.5">
                  <span
                    className={cx(
                      tableTokens.cellText,
                      l.estado === "ajustado" && "text-gray-400 line-through dark:text-gray-500",
                    )}
                  >
                    {l.valorIa}
                  </span>
                </td>
                <td className="px-3 py-0.5">
                  <span className={tableTokens.cellStrong}>{l.valorDossie}</span>
                  {l.estado === "pendente" && (
                    <span className={cx(tableTokens.badge, BADGE_TONE.atencao, "ml-1.5")}>pendente</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function FonteOrigemBlockView({ block }: { block: FonteOrigemBlock }) {
  const verde = provenanceTokens.documento
  return (
    <div
      className="flex items-center gap-2 rounded-md border p-2.5"
      style={{ borderColor: verde.color, background: verde.tileBg }}
    >
      <RiFileTextLine className="size-4 shrink-0" style={{ color: verde.color }} aria-hidden />
      <span className="text-xs text-gray-700 dark:text-gray-300">
        Documento de origem
        {block.locator?.kind === "doc" && block.locator.page != null
          ? ` · pág. ${block.locator.page}`
          : ""}
      </span>
    </div>
  )
}

function SubDossieBlockView({ block, mode }: { block: SubDossieBlock; mode: RenderMode }) {
  // Recursivo (Fase 2). Mesma anatomia, um nível abaixo — dossiê fractal.
  return (
    <div className="rounded-md border border-dashed border-gray-300 p-3 dark:border-gray-700">
      <p className={cx(tableTokens.header, "mb-2")}>{block.titulo}</p>
      <SectionRenderer section={block.descriptor} mode={mode} />
    </div>
  )
}

// ─── Dispatch ────────────────────────────────────────────────────────────────

function BlockView({ block, mode }: { block: Block; mode: RenderMode }) {
  switch (block.type) {
    case "ficha":
      return <FichaBlockView block={block} />
    case "tabela":
      return <TabelaBlockView block={block} />
    case "grafico":
      return <GraficoBlockView block={block} />
    case "conclusao_agente":
      return <ConclusaoAgenteBlockView block={block} mode={mode} />
    case "apontamentos":
      return <ApontamentosBlockView block={block} mode={mode} />
    case "texto":
      return <TextoBlockView block={block} mode={mode} />
    case "conferencia":
      return <ConferenciaBlockView block={block} />
    case "fonte_origem":
      return <FonteOrigemBlockView block={block} />
    case "sub_dossie":
      return <SubDossieBlockView block={block} mode={mode} />
    default: {
      // Exaustividade: se um tipo de bloco novo entrar sem case, o TS reclama aqui.
      const _exhaustive: never = block
      return _exhaustive
    }
  }
}

// ════════════════════════════════════════════════════════════════════════════
// SectionRenderer
// ════════════════════════════════════════════════════════════════════════════

export type SectionRendererProps = {
  section: SectionDescriptor
  /** work = workbench (editável) · read = projeção do dossiê. Default work. */
  mode?: RenderMode
  className?: string
}

export function SectionRenderer({ section, mode = "work", className }: SectionRendererProps) {
  // Overlay "Zonas": rotula cada BLOCO com seu tipo (muted) pra orientar
  // edições visuais — qual bloco é qual, em qualquer seção. Sincronizado com o
  // toggle da topbar via store compartilhado.
  const zonas = useZonas()
  return (
    <div className={cx("space-y-4", className)}>
      {section.blocks.map((block) =>
        zonas ? (
          <div key={block.id} className="relative">
            <DevZoneLabel corner="tr">bloco · {block.type}</DevZoneLabel>
            <BlockView block={block} mode={mode} />
          </div>
        ) : (
          <BlockView key={block.id} block={block} mode={mode} />
        ),
      )}
    </div>
  )
}
