"use client"

/**
 * DrillDcContent — conteudo do drill da categoria DC (Direitos Creditorios).
 *
 * F3 redesign 2026-05-24: decomposicao em 5 buckets calculada do granular
 * `wh_estoque_recebivel`. Identidade contabil fecha por construcao -- mutacao
 * silenciosa (ex-F5) vira RESULTADO NATURAL da decomposicao.
 *
 * 2026-05-29: TODAS as tabelas migraram do `<table>` artesanal (drillKit) para
 * a **`DataTable` canonica** `density="ultra"` (h-7/28px) — regra dura de
 * consistencia (sem multi-padrao). Tudo em 1 linha (cedente/sacado viram
 * colunas separadas; "Mudou" colapsa com "·" + tooltip) pra manter os 28px
 * uniformes. Totais via `renderFooter`; linhas especiais via `rowClassName`.
 *
 * Estrutura:
 *   1. Composicao do estoque (5 buckets + Estoque D-1 / D0 / Residuo)
 *   2. Mutacao silenciosa (papeis com mudanca de parametro, se houver)
 *   3. Migracao WOP (papeis que viraram WOP, se houver)
 *   4. Liquidacoes por tipo (agregado)
 *   5. Aquisicoes do dia (lista — top N visiveis)
 */

import * as React from "react"
import {
  RiCalculatorLine,
  RiPlayLine,
  RiAlertLine,
  RiArchive2Line,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { cx } from "@/lib/utils"
import { useDrillDc } from "@/lib/hooks/controladoria"
import { ErrorState } from "@/design-system/components/ErrorState"
import { Button } from "@/components/tremor/Button"
import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"
import type {
  DrillDcMutacaoPapel,
  DrillDcLiquidacaoParcialPapel,
  DrillDcAbatimentoPapel,
  DrillDcMigracaoWopPapel,
} from "@/lib/api-client"
import {
  DrillClosureBadge,
  DrillSectionTitle,
  fmtBRL,
  fmtBRLSigned,
  toneClass,
} from "./drillKit"

const fmtTaxa = (v: number): string => {
  // taxa_recebivel vem decimal (0,4692739943 = 0,47% ao mes)
  return `${(v * 100).toFixed(4).replace(".", ",")}%`
}

const fmtDateBR = (iso: string | null): string => {
  if (!iso) return "—"
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[3]}/${m[2]}/${m[1].slice(2)}` : iso
}

// Limite acima do qual o Residuo da decomposicao vira alerta.
// < R$ 0,50 = arredondamento contabil aceitavel; > = sinal de pipeline.
const RESIDUO_OK_BRL = 0.5

// Fonte (silver) de onde a decomposicao do estoque e calculada — exibida no
// canto superior direito da secao, padrao de proveniencia dos drills.
const DC_FONTE = "wh_estoque_recebivel"

// Props compartilhadas das DataTables do drill — todas ultra, sem toolbar,
// container bordado (espelha o antigo drillTableWrap).
const DT_PROPS = {
  density:           "ultra",
  virtualize:        false,
  showColumnManager: false,
  showDensityToggle: false,
  showExport:        false,
  className:         "rounded border border-gray-200 dark:border-gray-800",
} as const

// ── Helpers de celula (1 ponto de verdade — todos via tableTokens) ──────────

function NumCell({ value, secondary }: { value: number; secondary?: boolean }) {
  return (
    <div className={cx("text-right", secondary ? tableTokens.cellNumberSecondary : tableTokens.cellNumber)}>
      {fmtBRL.format(value)}
    </div>
  )
}

function ToneCell({ value, goodWhenPositive = true }: { value: number; goodWhenPositive?: boolean }) {
  return (
    <div className={cx("text-right text-xs font-semibold tabular-nums", toneClass(value, goodWhenPositive))}>
      {fmtBRLSigned(value)}
    </div>
  )
}

function TextTrunc({ value, title }: { value: string; title?: string }) {
  return <span className={cx("block truncate", tableTokens.cellText)} title={title}>{value}</span>
}

// Celula de identificacao do recebivel: numero do DOCUMENTO (duplicata/NF) +
// vencimento como desambiguador de parcela. NUNCA expoe `seu_numero` (referencia
// de admin opaca, ex.: codigo do originador) — nem em tooltip.
function DocCell({ doc, venc }: { doc: string; venc: string | null }) {
  return (
    <div className="flex items-baseline gap-1.5 truncate">
      <span className={cx("truncate font-mono", tableTokens.cellSecondary)}>{doc || "—"}</span>
      {venc ? (
        <span className="shrink-0 text-[10px] tabular-nums text-gray-400 dark:text-gray-600">{fmtDateBR(venc)}</span>
      ) : null}
    </div>
  )
}

// Linha de total no rodape (renderFooter) — borda superior destacada.
const FOOT_ROW = "border-t-2 border-t-gray-300 dark:border-t-gray-700"

// ── Tipos + colunas da Composicao do estoque ────────────────────────────────

type CompRow = {
  id:       string
  kind:     "anchor" | "bucket"
  label:    string
  detalhe:  string
  value:    number
  sign?:    "+" | "−"
  muted?:   boolean
  alert?:   boolean
}

const compCol = createColumnHelper<CompRow>()

const COMP_COLUMNS: ColumnDef<CompRow, unknown>[] = [
  compCol.accessor("label", {
    id:     "label",
    header: "Componente",
    size:   220,
    cell:   (info) => {
      const r = info.row.original
      return (
        <span className={cx("block truncate", r.kind === "anchor" ? tableTokens.cellStrong : tableTokens.cellText)}>
          {r.label}
        </span>
      )
    },
  }) as ColumnDef<CompRow, unknown>,
  compCol.accessor("detalhe", {
    id:     "detalhe",
    header: "Detalhe",
    size:   240,
    cell:   (info) => (
      <span className={cx("block truncate", tableTokens.cellSecondary)} title={info.getValue<string>() || ""}>{info.getValue<string>() || ""}</span>
    ),
  }) as ColumnDef<CompRow, unknown>,
  compCol.accessor("value", {
    id:     "value",
    header: "Valor",
    size:   160,
    meta:   { align: "right" },
    cell:   (info) => {
      const r = info.row.original
      const v = info.getValue<number>()
      if (r.kind === "anchor") {
        return <div className={cx("text-right tabular-nums", tableTokens.cellStrong)}>{fmtBRL.format(v)}</div>
      }
      const isZero = Math.abs(v) < 0.005
      const tone = isZero
        ? "text-gray-400 dark:text-gray-600"
        : v > 0 && r.sign === "+"
          ? "text-emerald-600 dark:text-emerald-400"
          : "text-red-600 dark:text-red-400"
      return (
        <div className={cx("text-right text-xs tabular-nums", tone, r.alert && "font-semibold")}>
          {fmtBRLSigned(v)}
        </div>
      )
    },
  }) as ColumnDef<CompRow, unknown>,
]

// ── Colunas: Mutacao silenciosa ──────────────────────────────────────────────

const mutCol = createColumnHelper<DrillDcMutacaoPapel>()

const MUTACAO_COLUMNS: ColumnDef<DrillDcMutacaoPapel, unknown>[] = [
  mutCol.accessor("cedente_nome", {
    id: "cedente", header: "Cedente", size: 160,
    cell: (info) => <TextTrunc value={info.getValue<string>()} title={info.row.original.cedente_doc} />,
  }) as ColumnDef<DrillDcMutacaoPapel, unknown>,
  mutCol.accessor("sacado_nome", {
    id: "sacado", header: "Sacado", size: 160,
    cell: (info) => <TextTrunc value={info.getValue<string>()} title={info.row.original.sacado_doc} />,
  }) as ColumnDef<DrillDcMutacaoPapel, unknown>,
  mutCol.accessor("numero_documento", {
    id: "titulo", header: "Documento", size: 150,
    cell: (info) => <DocCell doc={info.getValue<string>()} venc={info.row.original.venc_d0} />,
  }) as ColumnDef<DrillDcMutacaoPapel, unknown>,
  mutCol.accessor("vp_d1", {
    id: "vp_d1", header: "VP D-1", size: 120, meta: { align: "right" },
    cell: (info) => <NumCell value={info.getValue<number>()} secondary />,
  }) as ColumnDef<DrillDcMutacaoPapel, unknown>,
  mutCol.accessor("vp_d0", {
    id: "vp_d0", header: "VP D0", size: 120, meta: { align: "right" },
    cell: (info) => <NumCell value={info.getValue<number>()} />,
  }) as ColumnDef<DrillDcMutacaoPapel, unknown>,
  mutCol.accessor("delta_vp", {
    id: "delta_vp", header: "Δ VP", size: 110, meta: { align: "right" },
    cell: (info) => <ToneCell value={info.getValue<number>()} />,
  }) as ColumnDef<DrillDcMutacaoPapel, unknown>,
  mutCol.accessor((p) => p, {
    id: "mudou", header: "Mudou", size: 200,
    cell: (info) => {
      const p = info.row.original
      const ms: string[] = []
      if (p.mudou_vn) ms.push(`VN ${fmtBRL.format(p.vn_d1)} → ${fmtBRL.format(p.vn_d0)}`)
      if (p.mudou_taxa) ms.push(`Taxa ${fmtTaxa(p.taxa_d1)} → ${fmtTaxa(p.taxa_d0)}`)
      if (p.mudou_venc) ms.push(`Venc ${fmtDateBR(p.venc_d1)} → ${fmtDateBR(p.venc_d0)}`)
      const txt = ms.join(" · ")
      return <span className={cx("block truncate", tableTokens.cellSecondary)} title={txt}>{txt}</span>
    },
  }) as ColumnDef<DrillDcMutacaoPapel, unknown>,
]

// ── Colunas: Liquidacao parcial (ex-mutacao, casada com evento) ───────────────

const lpCol = createColumnHelper<DrillDcLiquidacaoParcialPapel>()

const LIQ_PARCIAL_COLUMNS: ColumnDef<DrillDcLiquidacaoParcialPapel, unknown>[] = [
  lpCol.accessor("cedente_nome", {
    id: "cedente", header: "Cedente", size: 150,
    cell: (info) => <TextTrunc value={info.getValue<string>()} title={info.row.original.cedente_doc} />,
  }) as ColumnDef<DrillDcLiquidacaoParcialPapel, unknown>,
  lpCol.accessor("numero_documento", {
    id: "titulo", header: "Documento", size: 150,
    cell: (info) => <DocCell doc={info.getValue<string>()} venc={info.row.original.data_vencimento} />,
  }) as ColumnDef<DrillDcLiquidacaoParcialPapel, unknown>,
  lpCol.accessor("tipo_movimento", {
    id: "tipo_movimento", header: "Evento", size: 220,
    cell: (info) => <TextTrunc value={info.getValue<string>()} title={info.getValue<string>()} />,
  }) as ColumnDef<DrillDcLiquidacaoParcialPapel, unknown>,
  lpCol.accessor("vp_d1", {
    id: "vp_d1", header: "VP D-1", size: 120, meta: { align: "right" },
    cell: (info) => <NumCell value={info.getValue<number>()} secondary />,
  }) as ColumnDef<DrillDcLiquidacaoParcialPapel, unknown>,
  lpCol.accessor("delta_vp", {
    id: "delta_vp", header: "Δ VP (carteira)", size: 130, meta: { align: "right" },
    cell: (info) => <ToneCell value={info.getValue<number>()} />,
  }) as ColumnDef<DrillDcLiquidacaoParcialPapel, unknown>,
  lpCol.accessor("valor_pago_evento", {
    id: "valor_pago_evento", header: "Pago (caixa)", size: 120, meta: { align: "right" },
    cell: (info) => <NumCell value={info.getValue<number>()} />,
  }) as ColumnDef<DrillDcLiquidacaoParcialPapel, unknown>,
]

// ── Colunas: Abatimento concedido (perda de credito sem caixa) ───────────────

const abCol = createColumnHelper<DrillDcAbatimentoPapel>()

const ABATIMENTO_COLUMNS: ColumnDef<DrillDcAbatimentoPapel, unknown>[] = [
  abCol.accessor("cedente_nome", {
    id: "cedente", header: "Cedente", size: 150,
    cell: (info) => <TextTrunc value={info.getValue<string>()} title={info.row.original.cedente_doc} />,
  }) as ColumnDef<DrillDcAbatimentoPapel, unknown>,
  abCol.accessor("numero_documento", {
    id: "titulo", header: "Documento", size: 150,
    cell: (info) => <DocCell doc={info.getValue<string>()} venc={info.row.original.data_vencimento} />,
  }) as ColumnDef<DrillDcAbatimentoPapel, unknown>,
  abCol.accessor("tipo_movimento", {
    id: "tipo_movimento", header: "Evento", size: 190,
    cell: (info) => <TextTrunc value={info.getValue<string>()} title={info.getValue<string>()} />,
  }) as ColumnDef<DrillDcAbatimentoPapel, unknown>,
  abCol.accessor("vp_d1", {
    id: "vp_d1", header: "VP D-1", size: 120, meta: { align: "right" },
    cell: (info) => <NumCell value={info.getValue<number>()} secondary />,
  }) as ColumnDef<DrillDcAbatimentoPapel, unknown>,
  abCol.accessor("delta_vp", {
    id: "delta_vp", header: "Δ VP (cota)", size: 120, meta: { align: "right" },
    cell: (info) => <ToneCell value={info.getValue<number>()} />,
  }) as ColumnDef<DrillDcAbatimentoPapel, unknown>,
  abCol.accessor("nominal_abatido", {
    id: "nominal_abatido", header: "Nominal abatido", size: 130, meta: { align: "right" },
    cell: (info) => <NumCell value={info.getValue<number>()} secondary />,
  }) as ColumnDef<DrillDcAbatimentoPapel, unknown>,
]

// ── Colunas: Migracao WOP ─────────────────────────────────────────────────────

const wopCol = createColumnHelper<DrillDcMigracaoWopPapel>()

const WOP_COLUMNS: ColumnDef<DrillDcMigracaoWopPapel, unknown>[] = [
  wopCol.accessor("cedente_nome", {
    id: "cedente", header: "Cedente", size: 170,
    cell: (info) => <TextTrunc value={info.getValue<string>()} title={info.row.original.cedente_doc} />,
  }) as ColumnDef<DrillDcMigracaoWopPapel, unknown>,
  wopCol.accessor("sacado_nome", {
    id: "sacado", header: "Sacado", size: 170,
    cell: (info) => <TextTrunc value={info.getValue<string>()} title={info.row.original.sacado_doc} />,
  }) as ColumnDef<DrillDcMigracaoWopPapel, unknown>,
  wopCol.accessor("numero_documento", {
    id: "titulo", header: "Documento", size: 150,
    cell: (info) => <DocCell doc={info.getValue<string>()} venc={info.row.original.data_vencimento} />,
  }) as ColumnDef<DrillDcMigracaoWopPapel, unknown>,
  wopCol.accessor("faixa_pdd_d1", {
    id: "faixa", header: "Faixa D-1", size: 90, meta: { align: "center" },
    cell: (info) => (
      <div className="text-center">
        <span className={tableTokens.badgeNeutral}>
          {info.getValue<string>()}
        </span>
      </div>
    ),
  }) as ColumnDef<DrillDcMigracaoWopPapel, unknown>,
  wopCol.accessor("vp_d1", {
    id: "vp_d1", header: "VP D-1", size: 120, meta: { align: "right" },
    cell: (info) => <NumCell value={info.getValue<number>()} />,
  }) as ColumnDef<DrillDcMigracaoWopPapel, unknown>,
  wopCol.accessor("valor_pdd_d1", {
    id: "pdd_d1", header: "PDD D-1", size: 120, meta: { align: "right" },
    cell: (info) => <NumCell value={info.getValue<number>()} secondary />,
  }) as ColumnDef<DrillDcMigracaoWopPapel, unknown>,
]

// ── Componente ───────────────────────────────────────────────────────────────

export type DrillDcContentProps = {
  fundoId:        string
  data:           string
  dataAnterior?:  string
}

export function DrillDcContent({ fundoId, data, dataAnterior }: DrillDcContentProps) {
  const q = useDrillDc(fundoId, data, dataAnterior)
  const [mutacaoExpanded, setMutacaoExpanded] = React.useState(false)
  const MUTACAO_PREVIEW = 5

  if (q.isError) {
    return (
      <ErrorState
        title="Falha ao carregar drill DC"
        description={(q.error as Error)?.message ?? "Erro desconhecido"}
        action={<Button onClick={() => q.refetch()}>Tentar novamente</Button>}
      />
    )
  }

  if (q.isLoading || !q.data) {
    return (
      <div className="flex h-40 items-center justify-center text-[12px] text-gray-500 dark:text-gray-400">
        Carregando drill DC…
      </div>
    )
  }

  const d = q.data
  const dec = d.decomposicao
  const mutacaoVisivel = mutacaoExpanded ? d.mutacao_papeis : d.mutacao_papeis.slice(0, MUTACAO_PREVIEW)

  const dcFecha = Math.abs(dec.residuo) < RESIDUO_OK_BRL
  const mutVpD1Total = d.mutacao_papeis.reduce((s, p) => s + p.vp_d1, 0)
  const mutVpD0Total = d.mutacao_papeis.reduce((s, p) => s + p.vp_d0, 0)
  const mutDeltaTotal = d.mutacao_papeis.reduce((s, p) => s + p.delta_vp, 0)
  const lpVpD1Total = d.liquidacao_parcial_papeis.reduce((s, p) => s + p.vp_d1, 0)
  const lpDeltaTotal = d.liquidacao_parcial_papeis.reduce((s, p) => s + p.delta_vp, 0)
  const lpPagoTotal = d.liquidacao_parcial_papeis.reduce((s, p) => s + p.valor_pago_evento, 0)
  const wopVpD1Total = d.migracao_wop_papeis.reduce((s, p) => s + p.vp_d1, 0)
  const wopPddD1Total = d.migracao_wop_papeis.reduce((s, p) => s + p.valor_pdd_d1, 0)
  const abVpD1Total = d.abatimentos_papeis.reduce((s, p) => s + p.vp_d1, 0)
  const abDeltaTotal = d.abatimentos_papeis.reduce((s, p) => s + p.delta_vp, 0)
  const abNominalTotal = d.abatimentos_papeis.reduce((s, p) => s + p.nominal_abatido, 0)

  const compRows: CompRow[] = [
    { id: "d1", kind: "anchor", label: "Estoque (D-1)", detalhe: "", value: dec.saldo_d1 },
    {
      id: "aquisicoes", kind: "bucket", label: "+ Aquisições", sign: "+",
      detalhe: `${dec.aquisicoes_n} título${dec.aquisicoes_n === 1 ? "" : "s"} novo${dec.aquisicoes_n === 1 ? "" : "s"}`,
      value: dec.aquisicoes_total,
    },
    {
      id: "liquidacoes", kind: "bucket", label: "− Liquidações", sign: "−",
      detalhe: `${dec.liquidacoes_n} título${dec.liquidacoes_n === 1 ? "" : "s"} baixado${dec.liquidacoes_n === 1 ? "" : "s"}`,
      value: -dec.liquidacoes_total,
    },
    {
      id: "liquidacao_parcial", kind: "bucket", label: "− Liquidação parcial", sign: "−",
      detalhe: `${dec.liquidacao_parcial_n} título${dec.liquidacao_parcial_n === 1 ? "" : "s"} com parcela paga em caixa (casa com evento)`,
      value: dec.liquidacao_parcial_total, muted: dec.liquidacao_parcial_n === 0,
    },
    {
      id: "abatimentos", kind: "bucket", label: "− Abatimento concedido", sign: "−",
      detalhe: `${dec.abatimentos_n} título${dec.abatimentos_n === 1 ? "" : "s"} com perda perdoada (sem entrada de caixa)`,
      value: dec.abatimentos_total, muted: dec.abatimentos_n === 0, alert: dec.abatimentos_n > 0,
    },
    {
      id: "wop", kind: "bucket", label: "− Migração WOP", sign: "−",
      detalhe: `${dec.migracao_wop_n} título${dec.migracao_wop_n === 1 ? "" : "s"} ${dec.migracao_wop_n === 1 ? "migrou" : "migraram"}`,
      value: -dec.migracao_wop_total, muted: dec.migracao_wop_n === 0,
    },
    {
      id: "apropriacao", kind: "bucket", label: "+ Acrúo de juros (carrego retido)", sign: "+",
      detalhe: `${dec.apropriacao_n} papéis · mora/antecipada realizam em caixa (ver Resultado)`,
      value: dec.apropriacao_total,
    },
    {
      id: "mutacao", kind: "bucket", label: "+ Mutação silenciosa", sign: "+",
      detalhe: `${dec.mutacao_n} papel${dec.mutacao_n === 1 ? "" : "is"} com mudança de parâmetro SEM evento`,
      value: dec.mutacao_total, muted: dec.mutacao_n === 0, alert: dec.mutacao_n > 0,
    },
  ]

  return (
    <div className="flex flex-col gap-5">
      {/* ── Selo de fechamento ── */}
      <DrillClosureBadge
        fecha={dcFecha}
        sub={!dcFecha ? "resíduo acima da tolerância — desalinhamento de pipeline" : undefined}
      >
        {dcFecha
          ? `Fecha · decomposição bate o Estoque D0 (${fmtBRL.format(dec.saldo_d0)})`
          : `Diverge · resíduo ${fmtBRLSigned(dec.residuo)}`}
      </DrillClosureBadge>

      {/* ── 0. Resultado do dia — o que MOVE a cota, com onde cada parte realiza.
          Carrego/mutação ficam no estoque (cresce o VP); carrego antecipado, mora
          e desconto vem de titulos liquidados → realizam em caixa (Tesouraria). */}
      {(() => {
        const r = d.resultado_do_dia
        const resultado =
          r.carrego_apropriacao + r.apropriacao_antecipada + r.juros_mora
          - r.desconto_concedido + r.mutacao_total + r.abatimentos_total
        const temCaixa =
          r.apropriacao_antecipada > 0 || r.juros_mora > 0 || r.desconto_concedido > 0
        const line = (label: string, tag: string, v: number, opts?: { alert?: boolean }) => (
          <div className="flex items-center justify-between">
            <span className={cx(tableTokens.cellSecondary, opts?.alert && "text-amber-700 dark:text-amber-400")}>
              {label} <span className="text-gray-400 dark:text-gray-600">({tag})</span>
            </span>
            <span className={cx("tabular-nums", toneClass(v))}>{fmtBRLSigned(v)}</span>
          </div>
        )
        return (
          <div className="rounded border border-gray-200 p-3 dark:border-gray-800">
            <div className="text-[10px] uppercase tracking-[0.06em] text-gray-400 dark:text-gray-600">
              Resultado da DC · move a cota
            </div>
            <div className={cx("mt-1 text-lg font-semibold tabular-nums", toneClass(resultado))}>
              {fmtBRLSigned(resultado)}
            </div>
            <div className="mt-2 space-y-1 text-[11px]">
              {line("Carrego", "estoque", r.carrego_apropriacao)}
              {r.apropriacao_antecipada > 0 && line("Carrego antecipado", "caixa", r.apropriacao_antecipada)}
              {r.juros_mora > 0 && line("Mora", "caixa", r.juros_mora)}
              {r.desconto_concedido > 0 && line("Desconto", "caixa", -r.desconto_concedido)}
              {Math.abs(r.abatimentos_total) >= 1 && line("Abatimento concedido", "carteira", r.abatimentos_total, { alert: r.abatimentos_total < 0 })}
              {Math.abs(r.mutacao_total) >= 1 && line("Mutação", "estoque", r.mutacao_total, { alert: r.mutacao_total < 0 })}
            </div>
            {temCaixa && (
              <p className="mt-2 text-[10px] leading-snug text-gray-400 dark:text-gray-500">
                Títulos liquidados: o VP saiu em “Liquidações”; o ganho
                (mora/antecipada) entra no caixa, não no estoque.
              </p>
            )}
          </div>
        )
      })()}

      {/* ── 1. Decomposicao do estoque ── */}
      <section>
        <DrillSectionTitle
          icon={RiCalculatorLine}
          label="Composição do estoque"
          help="Σ Valor Presente dos recebíveis em estoque (exclui WOP)"
          counter={<span className="font-mono">{DC_FONTE}</span>}
        />
        <div className="mt-3">
          <DataTable<CompRow>
            {...DT_PROPS}
            data={compRows}
            columns={COMP_COLUMNS}
            rowClassName={(r) => cx(
              r.alert && "bg-amber-50/40 dark:bg-amber-950/10",
              r.muted && "opacity-50",
            )}
            renderFooter={() => (
              <>
                <tr className={cx(FOOT_ROW, "bg-blue-50/40 dark:bg-blue-950/10")}>
                  <td className="px-3"><span className={tableTokens.cellStrong}>= Estoque (D0)</span></td>
                  <td className="px-3" />
                  <td className="px-3"><div className={cx("text-right tabular-nums", tableTokens.cellStrong)}>{fmtBRL.format(dec.saldo_d0)}</div></td>
                </tr>
                <tr className={cx(
                  "border-t",
                  dcFecha
                    ? "border-t-gray-100 dark:border-t-gray-900"
                    : "border-t-amber-200 bg-amber-50/40 dark:border-t-amber-900/40 dark:bg-amber-950/10",
                )}>
                  <td colSpan={2} className={cx(
                    "px-3 text-[10px] uppercase tracking-[0.06em]",
                    dcFecha ? "text-gray-400 dark:text-gray-600" : "font-semibold text-amber-800 dark:text-amber-300",
                  )}>
                    Resíduo {dcFecha ? "(arredondamento)" : "(desalinhamento de pipeline)"}
                  </td>
                  <td className={cx(
                    "px-3 text-right text-xs tabular-nums",
                    dcFecha ? "text-gray-500 dark:text-gray-400" : "font-semibold text-amber-800 dark:text-amber-300",
                  )}>
                    {fmtBRLSigned(dec.residuo)}
                  </td>
                </tr>
              </>
            )}
          />
        </div>
      </section>

      {/* ── 2. Detalhe Mutacao silenciosa (so se houver) ── */}
      {d.mutacao_papeis.length > 0 && (
        <section>
          <DrillSectionTitle
            icon={RiAlertLine}
            label="Papéis com mutação silenciosa"
            counter={`${d.mutacao_papeis.length} papel${d.mutacao_papeis.length === 1 ? "" : "is"}`}
            tone="alert"
          />
          <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
            Papéis presentes nos dois dias com mudança em valor nominal, taxa
            ou vencimento entre D-1 e D0 — sem evento de liquidação ou aquisição
            correspondente.
          </p>
          <div className="mt-2">
            <DataTable<DrillDcMutacaoPapel>
              {...DT_PROPS}
              data={mutacaoVisivel}
              columns={MUTACAO_COLUMNS}
              renderFooter={() => (
                <tr className={FOOT_ROW}>
                  <td colSpan={3} className="px-3"><span className={tableTokens.cellStrong}>Total · {d.mutacao_papeis.length} papel(eis)</span></td>
                  <td className="px-3"><div className={cx("text-right", tableTokens.cellNumberSecondary)}>{fmtBRL.format(mutVpD1Total)}</div></td>
                  <td className="px-3"><div className={cx("text-right font-semibold", tableTokens.cellNumber)}>{fmtBRL.format(mutVpD0Total)}</div></td>
                  <td className="px-3"><div className={cx("text-right text-xs font-semibold tabular-nums", toneClass(mutDeltaTotal))}>{fmtBRLSigned(mutDeltaTotal)}</div></td>
                  <td className="px-3" />
                </tr>
              )}
            />
          </div>
          {d.mutacao_papeis.length > MUTACAO_PREVIEW && (
            <button
              type="button"
              onClick={() => setMutacaoExpanded((v) => !v)}
              className="mt-2 inline-flex items-center gap-1 text-[11px] font-medium text-amber-800 hover:text-amber-900 dark:text-amber-300 dark:hover:text-amber-200"
            >
              <RiPlayLine className={cx("size-3 transition-transform", mutacaoExpanded && "rotate-90")} aria-hidden="true" />
              {mutacaoExpanded
                ? `Mostrar apenas os ${MUTACAO_PREVIEW} primeiros`
                : `Mostrar todos os ${d.mutacao_papeis.length} papéis`}
            </button>
          )}
        </section>
      )}

      {/* ── 2b. Detalhe Liquidacao parcial (so se houver) ── */}
      {d.liquidacao_parcial_papeis.length > 0 && (
        <section>
          <DrillSectionTitle
            icon={RiArchive2Line}
            label="Títulos com liquidação parcial"
            counter={`${d.liquidacao_parcial_papeis.length} papel${d.liquidacao_parcial_papeis.length === 1 ? "" : "is"}`}
          />
          <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
            Títulos que ficaram na carteira mas tiveram parcela paga em caixa no
            dia (liquidação/recompra parcial). A queda de VP casa com o evento em
            liquidações — é giro carteira → caixa, <strong>não</strong> resultado.
            A perna de caixa entra na Tesouraria/Disponibilidades. (Abatimentos
            concedidos — perda sem caixa — têm seção própria abaixo.)
          </p>
          <div className="mt-2">
            <DataTable<DrillDcLiquidacaoParcialPapel>
              {...DT_PROPS}
              data={d.liquidacao_parcial_papeis}
              columns={LIQ_PARCIAL_COLUMNS}
              renderFooter={() => (
                <tr className={FOOT_ROW}>
                  <td colSpan={3} className="px-3"><span className={tableTokens.cellStrong}>Total · {d.liquidacao_parcial_papeis.length} papel(eis)</span></td>
                  <td className="px-3"><div className={cx("text-right", tableTokens.cellNumberSecondary)}>{fmtBRL.format(lpVpD1Total)}</div></td>
                  <td className="px-3"><div className={cx("text-right text-xs font-semibold tabular-nums", toneClass(lpDeltaTotal))}>{fmtBRLSigned(lpDeltaTotal)}</div></td>
                  <td className="px-3"><div className={cx("text-right font-semibold", tableTokens.cellNumber)}>{fmtBRL.format(lpPagoTotal)}</div></td>
                </tr>
              )}
            />
          </div>
        </section>
      )}

      {/* ── 2c. Detalhe Abatimentos concedidos (so se houver) ── */}
      {d.abatimentos_papeis.length > 0 && (
        <section>
          <DrillSectionTitle
            icon={RiAlertLine}
            label="Abatimentos concedidos na carteira"
            counter={`${d.abatimentos_papeis.length} papel${d.abatimentos_papeis.length === 1 ? "" : "is"}`}
            tone="alert"
          />
          <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
            Títulos que ficaram na carteira mas tiveram <strong>abatimento concedido</strong> ao
            sacado — valor perdoado, <strong>sem entrada de caixa</strong>. A queda de VP é
            perda de crédito que bate na cota (resultado do DC), não giro. O
            <strong> Δ VP</strong> é o impacto na cota; o <strong>nominal abatido</strong> é a face perdoada
            (contexto).
          </p>
          <div className="mt-2">
            <DataTable<DrillDcAbatimentoPapel>
              {...DT_PROPS}
              data={d.abatimentos_papeis}
              columns={ABATIMENTO_COLUMNS}
              renderFooter={() => (
                <tr className={FOOT_ROW}>
                  <td colSpan={3} className="px-3"><span className={tableTokens.cellStrong}>Total · {d.abatimentos_papeis.length} papel(eis)</span></td>
                  <td className="px-3"><div className={cx("text-right", tableTokens.cellNumberSecondary)}>{fmtBRL.format(abVpD1Total)}</div></td>
                  <td className="px-3"><div className={cx("text-right text-xs font-semibold tabular-nums", toneClass(abDeltaTotal))}>{fmtBRLSigned(abDeltaTotal)}</div></td>
                  <td className="px-3"><div className={cx("text-right", tableTokens.cellNumberSecondary)}>{fmtBRL.format(abNominalTotal)}</div></td>
                </tr>
              )}
            />
          </div>
        </section>
      )}

      {/* ── 3. Detalhe Migracao WOP (so se houver) ── */}
      {d.migracao_wop_papeis.length > 0 && (
        <section>
          <DrillSectionTitle
            icon={RiArchive2Line}
            label="Papéis que migraram para WOP"
            counter={`${d.migracao_wop_papeis.length} papel${d.migracao_wop_papeis.length === 1 ? "" : "is"}`}
          />
          <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
            Saem da DC (VP zera no estoque ex-WOP) e simultaneamente saem da
            PDD — efeito líquido no PL Sub Jr é zero.
          </p>
          <div className="mt-2">
            <DataTable<DrillDcMigracaoWopPapel>
              {...DT_PROPS}
              data={d.migracao_wop_papeis}
              columns={WOP_COLUMNS}
              renderFooter={() => (
                <tr className={FOOT_ROW}>
                  <td colSpan={4} className="px-3"><span className={tableTokens.cellStrong}>Total · {d.migracao_wop_papeis.length} papel(eis)</span></td>
                  <td className="px-3"><div className={cx("text-right", tableTokens.cellNumber)}>{fmtBRL.format(wopVpD1Total)}</div></td>
                  <td className="px-3"><div className={cx("text-right", tableTokens.cellNumberSecondary)}>{fmtBRL.format(wopPddD1Total)}</div></td>
                </tr>
              )}
            />
          </div>
        </section>
      )}

    </div>
  )
}
