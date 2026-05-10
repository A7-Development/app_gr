// src/lib/reports/qitech-estoque-carteira.ts
//
// TS-types e column defs do relatorio "Carteira de recebiveis" (slug
// `qitech-estoque-carteira`, canonical `wh_estoque_recebivel`).
//
// Schema espelhado de `mappers/fidc_estoque.py` no backend. Quando o
// canonical evoluir, atualizar AQUI; nao tem migration de schema_columns
// no banco — fonte de verdade e este arquivo + o mapper.

import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

// ─── Row type (espelho do silver canonical) ────────────────────────────

export type EstoqueRecebivelRow = {
  // Tenant + dia
  tenant_id: string
  data_referencia: string

  // Fundo
  fundo_doc: string
  fundo_nome: string
  data_fundo: string | null

  // Gestor
  gestor_doc: string
  gestor_nome: string

  // Originador
  originador_doc: string
  originador_nome: string

  // Cedente
  cedente_doc: string
  cedente_nome: string

  // Sacado
  sacado_doc: string
  sacado_nome: string

  // Recebivel
  seu_numero: string
  numero_documento: string
  tipo_recebivel: string

  // Valores
  valor_nominal: string | number
  valor_presente: string | number
  valor_aquisicao: string | number
  valor_pdd: string | number
  faixa_pdd: string

  // Datas
  data_vencimento_original: string | null
  data_vencimento_ajustada: string | null
  data_emissao: string | null
  data_aquisicao: string | null
  prazo: number
  prazo_anual: string | number

  // Estado / risco
  situacao_recebivel: string
  taxa_cessao: string | number
  taxa_recebivel: string | number
  coobrigacao: boolean

  // Proveniencia (Auditable mixin)
  source_type: string
  source_id: string
  source_updated_at: string
  ingested_at: string
  hash_origem: string
  ingested_by_version: string
  trust_level: "high" | "medium" | "low"
  collected_by: string | null
}

// ─── Helpers de formatacao ─────────────────────────────────────────────

function formatBR(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—"
  const n = typeof value === "number" ? value : Number(value)
  if (Number.isNaN(n)) return "—"
  return n.toLocaleString("pt-BR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function formatDateBR(value: string | null | undefined): string {
  if (!value) return "—"
  // Aceita "yyyy-mm-dd" ou ISO completo. Devolve "dd/mm/yyyy".
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return value
  return d.toLocaleDateString("pt-BR", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    timeZone: "UTC",
  })
}

function formatDoc(doc: string | null | undefined): string {
  if (!doc) return "—"
  // CNPJ 14 digitos: 12.345.678/0001-90
  if (doc.length === 14) {
    return `${doc.slice(0, 2)}.${doc.slice(2, 5)}.${doc.slice(5, 8)}/${doc.slice(8, 12)}-${doc.slice(12)}`
  }
  // CPF 11 digitos: 123.456.789-00
  if (doc.length === 11) {
    return `${doc.slice(0, 3)}.${doc.slice(3, 6)}.${doc.slice(6, 9)}-${doc.slice(9)}`
  }
  return doc
}

// ─── Column defs ───────────────────────────────────────────────────────

const col = createColumnHelper<EstoqueRecebivelRow>()

export const columns: ColumnDef<EstoqueRecebivelRow, unknown>[] = [
  col.accessor("data_referencia", {
    header: "Data ref.",
    size: 100,
    cell: (info) => (
      <span className={tableTokens.cellText}>
        {formatDateBR(info.getValue())}
      </span>
    ),
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("cedente_nome", {
    header: "Cedente",
    size: 220,
    cell: (info) => (
      <div className="flex flex-col">
        <span className={cx(tableTokens.cellText, "line-clamp-1")}>
          {info.getValue() || "—"}
        </span>
        <span className={cx(tableTokens.cellSecondary, "tabular-nums")}>
          {formatDoc(info.row.original.cedente_doc)}
        </span>
      </div>
    ),
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("sacado_nome", {
    header: "Sacado",
    size: 220,
    cell: (info) => (
      <div className="flex flex-col">
        <span className={cx(tableTokens.cellText, "line-clamp-1")}>
          {info.getValue() || "—"}
        </span>
        <span className={cx(tableTokens.cellSecondary, "tabular-nums")}>
          {formatDoc(info.row.original.sacado_doc)}
        </span>
      </div>
    ),
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("numero_documento", {
    header: "Documento",
    size: 130,
    cell: (info) => (
      <span className={tableTokens.cellTextMono}>{info.getValue() || "—"}</span>
    ),
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("data_vencimento_ajustada", {
    header: "Vencimento",
    size: 110,
    cell: (info) => (
      <span className={tableTokens.cellText}>
        {formatDateBR(info.getValue())}
      </span>
    ),
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("valor_presente", {
    header: "Valor presente",
    size: 130,
    cell: (info) => (
      <span className={tableTokens.cellNumber}>{formatBR(info.getValue())}</span>
    ),
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("valor_nominal", {
    header: "Valor nominal",
    size: 130,
    cell: (info) => (
      <span className={tableTokens.cellNumber}>{formatBR(info.getValue())}</span>
    ),
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("situacao_recebivel", {
    header: "Situacao",
    size: 130,
    cell: (info) => (
      <span className={tableTokens.cellText}>{info.getValue() || "—"}</span>
    ),
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("valor_pdd", {
    header: "PDD",
    size: 110,
    cell: (info) => (
      <span className={tableTokens.cellNumber}>{formatBR(info.getValue())}</span>
    ),
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("taxa_cessao", {
    header: "Taxa cessao",
    size: 110,
    cell: (info) => {
      const v = info.getValue()
      const n = typeof v === "number" ? v : Number(v)
      return (
        <span className={tableTokens.cellNumber}>
          {Number.isNaN(n) ? "—" : `${(n * 100).toFixed(4)}%`}
        </span>
      )
    },
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("coobrigacao", {
    header: "Coobrig.",
    size: 90,
    cell: (info) => (
      <span className={tableTokens.cellSecondary}>
        {info.getValue() ? "Sim" : "Nao"}
      </span>
    ),
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
]

export const itemNoun = { singular: "recebivel", plural: "recebiveis" }
