"use client"

/**
 * CosifDrillSheet — drill-down ao clicar conta analitica no BalanceteDiarioTable.
 *
 * Aba unica (sem tabs) com 3 secoes em coluna:
 *
 *   1. Hero (nome + saldo D0 + delta vs D-1)
 *   2. Composicao e variacao — tabela diff D-1 vs D0 por papel, com status
 *      visual: novo (verde), removido (vermelho), alterado (Δ destacado),
 *      inalterado (cinza). Mescla "rows silver" com "analise da variacao".
 *   3. Composicao por classe — Sr/Mez/Sub quando aplicavel
 *   4. Metadados — details/summary collapsed por default (codigo cosif,
 *      natureza, grupo, parent)
 *
 * Sem PropertyList grande de metadados — eles eram redundantes com a
 * tabela principal. Drill foca no que ESTA dentro da conta e no que MUDOU.
 */

import { Badge } from "@/components/tremor/Badge"
import { DrillDownSheet } from "@/design-system/components/DrillDownSheet"

import type { CosifNode } from "@/lib/api-client"
import { sourceBadge } from "../_lib/cosif"

// ─── Formatters ──────────────────────────────────────────────────────────────

const fmtPct = new Intl.NumberFormat("pt-BR", {
  minimumFractionDigits: 2, maximumFractionDigits: 2,
})

// ─── Source badge ────────────────────────────────────────────────────────────

function SourceBadgeChip({ source }: { source: string }) {
  const { label, tone } = sourceBadge(source)
  const variant =
    tone === "blue"    ? "default"  :
    tone === "green"   ? "success"  :
    tone === "amber"   ? "warning"  :
    tone === "red"     ? "error"    :
    "neutral"
  return <Badge variant={variant} className="px-2 py-0.5 text-[10px] ring-0">{label}</Badge>
}

// ─── Metadados (collapsed) ───────────────────────────────────────────────────

const NATUREZA_LABEL: Record<string, string> = {
  D: "Devedora",
  C: "Credora",
  "?": "Pendente",
}

const GRUPO_LABEL: Record<number, string> = {
  1: "Ativo (Circulante e Realizável)",
  3: "Compensação (Ativo)",
  4: "Passivo (Circulante e Exigível)",
  6: "Patrimônio Líquido",
  7: "Resultado (Credoras)",
  8: "Resultado (Devedoras)",
  9: "Compensação (Passivo)",
  0: "Pendente",
}

function MetadadosCollapsed({ node }: { node: CosifNode }) {
  return (
    <details className="group rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
      <summary className="cursor-pointer list-none px-3 py-1.5 text-[11px] font-medium uppercase tracking-wide text-gray-500 marker:hidden hover:bg-gray-50 dark:text-gray-400 dark:hover:bg-gray-900/40">
        <span className="inline-block transition-transform group-open:rotate-90">▸</span>{" "}
        Metadados COSIF
      </summary>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 border-t border-gray-200 px-3 py-3 text-xs dark:border-gray-800">
        <div>
          <dt className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">Código</dt>
          <dd className="font-mono text-gray-900 dark:text-gray-50">{node.codigo ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">Natureza</dt>
          <dd className="text-gray-900 dark:text-gray-50">{NATUREZA_LABEL[node.natureza] ?? node.natureza}</dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">Grupo</dt>
          <dd className="text-gray-900 dark:text-gray-50">{GRUPO_LABEL[node.grupo] ?? String(node.grupo)}</dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">Conta pai</dt>
          <dd className="font-mono text-gray-900 dark:text-gray-50">{node.parent_codigo ?? "—"}</dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">Origem da classificação</dt>
          <dd className="text-gray-900 dark:text-gray-50">{node.cosif_source || "—"}</dd>
        </div>
        <div>
          <dt className="text-[10px] uppercase tracking-wide text-gray-500 dark:text-gray-400">Rows classificadas</dt>
          <dd className="font-mono text-gray-900 dark:text-gray-50">{node.rows_classified}</dd>
        </div>
      </dl>
    </details>
  )
}

// ─── Component ───────────────────────────────────────────────────────────────

export type CosifDrillSheetProps = {
  node:    CosifNode | null
  onClose: () => void
}

export function CosifDrillSheet({
  node,
  onClose,
}: CosifDrillSheetProps) {
  const open = node !== null

  if (!node) {
    return (
      <DrillDownSheet open={false} onClose={onClose} title="">
        <></>
      </DrillDownSheet>
    )
  }

  const title = node.codigo ?? "(pendente)"
  const breadcrumb = [
    "Balancete",
    `Grupo ${node.grupo === 0 ? "Pendente" : node.grupo}`,
    node.codigo ?? node.nome,
  ]

  return (
    <DrillDownSheet open={open} onClose={onClose} title={title} size="md">
      <DrillDownSheet.Header
        breadcrumb={breadcrumb}
        statusSlot={<SourceBadgeChip source={node.cosif_source} />}
      />

      <DrillDownSheet.Hero
        id={node.codigo ?? "—"}
        title={node.nome}
        value={node.d_zero}
        delta={{
          // Em analise contabil, o controller le R$ antes de %. Por isso
          // o numero grande do delta e o valor absoluto e o % vai no label
          // — com a MESMA cor (labelTone='match') porque os dois comunicam
          // a mesma direcao (negativo/positivo).
          value:     node.delta,
          format:    "currency",
          label:     `vs D-1 (${node.delta_pct >= 0 ? "+" : ""}${fmtPct.format(node.delta_pct)}%)`,
          labelTone: "match",
        }}
      />

      {/* Coluna unica — sheet agora e so EXPLICACAO (papeis estao na tabela). */}
      <div className="flex flex-1 flex-col gap-4 overflow-y-auto px-6 py-4">
        {!node.codigo ? (
          <div className="rounded border border-amber-200 bg-amber-50/60 px-3 py-4 text-center text-sm text-amber-700 dark:border-amber-900/40 dark:bg-amber-950/30 dark:text-amber-300">
            Conta sem classificação COSIF — não há drill-down disponível.<br />
            Crie um override em <span className="font-mono">/admin/controladoria/cosif</span> para classificar.
          </div>
        ) : (
          <ExplicacaoConta node={node} />
        )}

        <MetadadosCollapsed node={node} />
      </div>

      <DrillDownSheet.Footer>
        <div className="flex-1 text-xs text-gray-500 dark:text-gray-400">
          {node.cosif_source === "pendente"
            ? "Crie um override em /admin/controladoria/cosif para classificar."
            : null}
        </div>
      </DrillDownSheet.Footer>
    </DrillDownSheet>
  )
}

// ─── Explicacao da conta (texto narrativo, source-aware) ─────────────────────

const SOURCE_EXPLAIN: Record<string, string> = {
  override: "Esta conta foi classificada por um override do tenant (ajuste manual cadastrado em /admin/controladoria/cosif).",
  rule:     "Esta conta foi classificada automaticamente por uma regra do catalogo COSIF — match por silver de origem + predicado sobre os campos do papel.",
  mixed:    "Esta conta agrega rows classificadas por origens diferentes (mistura override + regra). Inspecione os papeis na tabela pra entender a composicao.",
  pendente: "Esta conta nao tem classificacao COSIF — nao casou com regra nem override. Crie um override em /admin/controladoria/cosif.",
}

function ExplicacaoConta({ node }: { node: CosifNode }) {
  const explain = SOURCE_EXPLAIN[node.cosif_source] ?? null
  return (
    <div className="flex flex-col gap-2 rounded border border-gray-200 bg-white px-3 py-2.5 dark:border-gray-800 dark:bg-gray-950">
      <div className="text-[10px] font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
        Explicação
      </div>
      <p className="text-xs leading-relaxed text-gray-700 dark:text-gray-300">
        {explain ?? "Conta COSIF analitica do balancete patrimonial diario."}
      </p>
      <p className="text-xs leading-relaxed text-gray-500 dark:text-gray-400">
        Os papéis que sustentam o saldo estão expandidos diretamente na tabela —
        clique no chevron ao lado do código <span className="font-mono">{node.codigo}</span> para abri-los.
      </p>
    </div>
  )
}
