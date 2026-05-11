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

/**
 * Prazo atual = dias restantes do recebivel a partir da `data_referencia`
 * ate o `data_vencimento_ajustada`. Calculado no client porque o QiTech CSV
 * nao manda esse campo (so envia `prazo` total). Quando o vencimento ja
 * passou na data do snapshot, retorna numero negativo (dias em atraso).
 */
function computePrazoAtual(
  dataReferencia: string | null | undefined,
  dataVencimentoAjustada: string | null | undefined,
): number | null {
  if (!dataReferencia || !dataVencimentoAjustada) return null
  const ref = new Date(dataReferencia)
  const venc = new Date(dataVencimentoAjustada)
  if (Number.isNaN(ref.getTime()) || Number.isNaN(venc.getTime())) return null
  // Diff em dias corridos (UTC pra evitar surpresa de DST).
  const msPerDay = 1000 * 60 * 60 * 24
  return Math.round((venc.getTime() - ref.getTime()) / msPerDay)
}

// ─── Column defs ───────────────────────────────────────────────────────

const col = createColumnHelper<EstoqueRecebivelRow>()

// Helpers de cell pra valor monetario / taxa / inteiro — extraidos pra cortar
// repeticao das 23 colunas. Mantem tudo via tableTokens.* (sem text-[Npx]).
//
// Regra dura: NENHUMA cell quebra em 2 linhas. Toda celula usa `block truncate`
// + `title` no caso de texto livre (para hover mostrar o valor completo).
// Numeros nao precisam de title — o valor completo ja eh visivel (ou
// formatado por inteiro).

function MoneyCell({ value }: { value: string | number | null | undefined }) {
  return (
    <span className={cx(tableTokens.cellNumber, "block truncate")}>
      {formatBR(value)}
    </span>
  )
}

function DateCell({ value }: { value: string | null | undefined }) {
  return (
    <span className={cx(tableTokens.cellText, "block truncate")}>
      {formatDateBR(value)}
    </span>
  )
}

function TaxaCell({ value }: { value: string | number | null | undefined }) {
  const n = typeof value === "number" ? value : Number(value)
  return (
    <span className={cx(tableTokens.cellNumber, "block truncate")}>
      {Number.isNaN(n) ? "—" : `${(n * 100).toFixed(4)}%`}
    </span>
  )
}

function IntCell({ value }: { value: number | null | undefined }) {
  if (value === null || value === undefined) {
    return (
      <span className={cx(tableTokens.cellSecondary, "block truncate")}>—</span>
    )
  }
  return (
    <span className={cx(tableTokens.cellNumber, "block truncate")}>{value}</span>
  )
}

/** Cell de texto que trunca em 1 linha + tooltip com valor completo no hover. */
function TextCell({
  value,
  mono,
}: {
  value: string | null | undefined
  mono?: boolean
}) {
  const text = value || "—"
  return (
    <span
      className={cx(
        mono ? tableTokens.cellTextMono : tableTokens.cellText,
        "block truncate",
      )}
      title={text}
    >
      {text}
    </span>
  )
}

export const columns: ColumnDef<EstoqueRecebivelRow, unknown>[] = [
  col.accessor("cedente_nome", {
    header: "Nome cedente",
    size: 220,
    cell: (info) => <TextCell value={info.getValue<string | null>()} />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("cedente_doc", {
    header: "Doc cedente",
    size: 150,
    cell: (info) => <TextCell value={formatDoc(info.getValue<string | null>())} mono />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("sacado_nome", {
    header: "Nome sacado",
    size: 220,
    cell: (info) => <TextCell value={info.getValue<string | null>()} />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("sacado_doc", {
    header: "Doc sacado",
    size: 150,
    cell: (info) => <TextCell value={formatDoc(info.getValue<string | null>())} mono />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("seu_numero", {
    header: "Seu numero",
    size: 120,
    cell: (info) => <TextCell value={info.getValue<string | null>()} mono />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("numero_documento", {
    header: "Nu. documento",
    size: 140,
    cell: (info) => <TextCell value={info.getValue<string | null>()} mono />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("tipo_recebivel", {
    header: "Tipo recebivel",
    size: 120,
    cell: (info) => <TextCell value={info.getValue<string | null>()} />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("valor_nominal", {
    header: "Valor nominal",
    size: 140,
    cell: (info) => <MoneyCell value={info.getValue()} />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("valor_presente", {
    header: "Valor presente",
    size: 140,
    cell: (info) => <MoneyCell value={info.getValue()} />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("valor_aquisicao", {
    header: "Valor aquisicao",
    size: 140,
    cell: (info) => <MoneyCell value={info.getValue()} />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("valor_pdd", {
    header: "Valor PDD",
    size: 120,
    cell: (info) => <MoneyCell value={info.getValue()} />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("faixa_pdd", {
    header: "Faixa PDD",
    size: 90,
    cell: (info) => <TextCell value={info.getValue<string | null>()} />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("data_referencia", {
    header: "Data ref.",
    size: 110,
    cell: (info) => <DateCell value={info.getValue()} />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("data_vencimento_original", {
    header: "Vcto original",
    size: 110,
    cell: (info) => <DateCell value={info.getValue()} />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("data_vencimento_ajustada", {
    header: "Vcto ajustado",
    size: 110,
    cell: (info) => <DateCell value={info.getValue()} />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("data_emissao", {
    header: "Data emissao",
    size: 110,
    cell: (info) => <DateCell value={info.getValue()} />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("data_aquisicao", {
    header: "Data aquisicao",
    size: 110,
    cell: (info) => <DateCell value={info.getValue()} />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("prazo", {
    header: "Prazo",
    size: 80,
    cell: (info) => <IntCell value={info.getValue<number | null>()} />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  // Prazo atual = dias entre data_referencia e data_vencimento_ajustada.
  // Calculado client-side porque o CSV da QiTech nao manda esse campo.
  // Acessor de funcao (col.accessor((row) => ...)) pra que sorting funcione.
  col.accessor(
    (row) =>
      computePrazoAtual(row.data_referencia, row.data_vencimento_ajustada),
    {
      id: "prazo_atual",
      header: "Prazo atual",
      size: 100,
      cell: (info) => <IntCell value={info.getValue<number | null>()} />,
    },
  ) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("situacao_recebivel", {
    header: "Situacao",
    size: 120,
    cell: (info) => <TextCell value={info.getValue<string | null>()} />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("taxa_cessao", {
    header: "Taxa cessao",
    size: 110,
    cell: (info) => <TaxaCell value={info.getValue()} />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("taxa_recebivel", {
    header: "Tx recebivel",
    size: 110,
    cell: (info) => <TaxaCell value={info.getValue()} />,
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
  col.accessor("coobrigacao", {
    header: "Coobrigacao",
    size: 110,
    cell: (info) => (
      <span
        className={cx(tableTokens.cellSecondary, "block truncate")}
      >
        {info.getValue() ? "Sim" : "Nao"}
      </span>
    ),
  }) as ColumnDef<EstoqueRecebivelRow, unknown>,
]

export const itemNoun = { singular: "recebivel", plural: "recebiveis" }
