// src/app/(app)/risco/lastro-fiscal/[chave]/page.tsx
//
// Risco · Lastro fiscal — ficha 360 de um documento (NF-e) por chave de acesso.
//
// MOTIVO (diverge de pattern): nao e listagem nem dashboard — e uma FICHA de
// entidade (documento fiscal), "novo foco de trabalho" (navegacao-aprofundamento
// §7): vira ROTA. Compoe PageHeader + Cards com PropertyList (secoes escalares)
// e DataTable (itens/duplicatas/eventos/titulos). Fonte: /risco/lastro-fiscal/
// documento/{chave} — 100% silver (§13.2.1). Zero ocultacao (§14.6): todas as
// linhas de cada tabela sao renderizadas (sem corte), rodape soma quando aplica.

"use client"

import * as React from "react"
import { useParams, useRouter } from "next/navigation"
import {
  RiArrowLeftLine,
  RiFileList3Line,
  RiFileTextLine,
  RiPriceTag3Line,
  RiTruckLine,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import {
  DataTable,
  EmptyState,
  ErrorState,
  PageHeader,
  PropertyList,
} from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type {
  NfeDoc360Duplicata,
  NfeDoc360Evento,
  NfeDoc360Item,
  NfeDoc360Titulo,
} from "@/lib/api-client"
import { useNfeDocumento360 } from "@/lib/hooks/risco"
import { cx } from "@/lib/utils"

// ── Formatadores locais (pt-BR) ─────────────────────────────────────────────
const brl = (v: number | null | undefined) =>
  v == null
    ? "—"
    : new Intl.NumberFormat("pt-BR", {
        style: "currency",
        currency: "BRL",
      }).format(v)

const qtd = (v: number | null | undefined) =>
  v == null ? "—" : v.toLocaleString("pt-BR", { maximumFractionDigits: 4 })

const dataHora = (s: string | null | undefined) =>
  !s ? "—" : new Date(s).toLocaleString("pt-BR")

const dia = (s: string | null | undefined) =>
  !s ? "—" : new Date(s).toLocaleDateString("pt-BR")

const doc = (s: string | null | undefined) => {
  if (!s) return "—"
  if (s.length === 14)
    return s.replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, "$1.$2.$3/$4-$5")
  if (s.length === 11)
    return s.replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4")
  return s
}

const TIPO_OP: Record<string, string> = { "0": "Entrada", "1": "Saída" }
const FINALIDADE: Record<string, string> = {
  "1": "Normal",
  "2": "Complementar",
  "3": "Ajuste",
  "4": "Devolução",
}
const MOD_FRETE: Record<string, string> = {
  "0": "Por conta do emitente (CIF)",
  "1": "Por conta do destinatário (FOB)",
  "2": "Por conta de terceiros",
  "3": "Transporte próprio (remetente)",
  "4": "Transporte próprio (destinatário)",
  "9": "Sem transporte",
}
const SEV_PILL: Record<string, string> = {
  critica: tableTokens.pillDanger,
  media: tableTokens.pillWarning,
  positiva: tableTokens.pillSuccess,
}

function SectionCard({
  icon: Icon,
  title,
  count,
  children,
}: {
  icon: React.ElementType
  title: string
  count?: number
  children: React.ReactNode
}) {
  return (
    <Card className="p-0">
      <div className="flex items-center gap-2 border-b border-gray-200 px-4 py-3 dark:border-gray-800">
        <Icon className="size-4 text-gray-400" aria-hidden />
        <h2 className="text-[13px] font-semibold text-gray-900 dark:text-gray-100">
          {title}
        </h2>
        {count != null && (
          <span className={cx(tableTokens.chipCount, "ml-1")}>{count}</span>
        )}
      </div>
      <div className="p-4">{children}</div>
    </Card>
  )
}

// ── Colunas das tabelas ─────────────────────────────────────────────────────
const itemCol = createColumnHelper<NfeDoc360Item>()
const ITEM_COLUMNS = [
  itemCol.accessor("n_item", {
    header: "#",
    cell: (c) => <span className={tableTokens.cellSecondary}>{c.getValue()}</span>,
  }),
  itemCol.accessor("descricao", {
    header: "Produto",
    cell: (c) => (
      <span className={tableTokens.cellStrong}>{c.getValue() ?? "—"}</span>
    ),
  }),
  itemCol.accessor("codigo", {
    header: "Código",
    cell: (c) => (
      <span className={tableTokens.cellTextMono}>{c.getValue() ?? "—"}</span>
    ),
  }),
  itemCol.accessor("ncm", {
    header: "NCM",
    cell: (c) => (
      <span className={tableTokens.cellTextMono}>{c.getValue() ?? "—"}</span>
    ),
  }),
  itemCol.accessor("cfop", {
    header: "CFOP",
    cell: (c) => (
      <span className={tableTokens.cellTextMono}>{c.getValue() ?? "—"}</span>
    ),
  }),
  itemCol.accessor("quantidade", {
    header: "Qtd",
    cell: (c) => (
      <span className={tableTokens.cellNumber}>
        {qtd(c.getValue())}
        {c.row.original.unidade ? (
          <span className={cx(tableTokens.cellSecondary, "ml-1")}>
            {c.row.original.unidade}
          </span>
        ) : null}
      </span>
    ),
  }),
  itemCol.accessor("valor_unitario", {
    header: "Valor unit.",
    cell: (c) => <span className={tableTokens.cellNumber}>{brl(c.getValue())}</span>,
  }),
  itemCol.accessor("valor_total", {
    header: "Valor",
    cell: (c) => (
      <span className={tableTokens.cellNumber}>{brl(c.getValue())}</span>
    ),
  }),
] as ColumnDef<NfeDoc360Item, unknown>[]

const dupCol = createColumnHelper<NfeDoc360Duplicata>()
const DUP_COLUMNS = [
  dupCol.accessor("numero", {
    header: "Parcela",
    cell: (c) => <span className={tableTokens.cellText}>{c.getValue()}</span>,
  }),
  dupCol.accessor("vencimento", {
    header: "Vencimento",
    cell: (c) => (
      <span className={tableTokens.cellSecondary}>{dia(c.getValue())}</span>
    ),
  }),
  dupCol.accessor("valor", {
    header: "Valor",
    cell: (c) => (
      <span className={tableTokens.cellNumber}>{brl(c.getValue())}</span>
    ),
  }),
] as ColumnDef<NfeDoc360Duplicata, unknown>[]

const evtCol = createColumnHelper<NfeDoc360Evento>()
const EVENTO_COLUMNS = [
  evtCol.accessor("dh_evento", {
    header: "Quando",
    cell: (c) => (
      <span className={tableTokens.cellSecondary}>{dataHora(c.getValue())}</span>
    ),
  }),
  evtCol.accessor("codigo", {
    header: "Sinal",
    cell: (c) => {
      const pill = SEV_PILL[c.row.original.severidade]
      return pill ? (
        <span className={pill}>{c.getValue()}</span>
      ) : (
        <span className={tableTokens.cellTextMono}>{c.getValue()}</span>
      )
    },
  }),
  evtCol.accessor("desc_evento", {
    header: "Evento",
    cell: (c) => (
      <span className={tableTokens.cellText}>
        {c.getValue() ?? `tpEvento ${c.row.original.tp_evento}`}
      </span>
    ),
  }),
  evtCol.accessor("autor_documento", {
    header: "Autor (CNPJ/CPF)",
    cell: (c) => (
      <span className={tableTokens.cellTextMono}>{doc(c.getValue())}</span>
    ),
  }),
] as ColumnDef<NfeDoc360Evento, unknown>[]

const titCol = createColumnHelper<NfeDoc360Titulo>()
const TITULO_COLUMNS = [
  titCol.accessor("numero", {
    header: "Título",
    cell: (c) => (
      <span className={tableTokens.cellStrong}>{c.getValue() ?? "—"}</span>
    ),
  }),
  titCol.accessor("vencimento", {
    header: "Vencimento",
    cell: (c) => (
      <span className={tableTokens.cellSecondary}>{dia(c.getValue())}</span>
    ),
  }),
  titCol.accessor("valor", {
    header: "Valor",
    cell: (c) => (
      <span className={tableTokens.cellNumber}>{brl(c.getValue())}</span>
    ),
  }),
  titCol.accessor("saldo_devedor", {
    header: "Saldo devedor",
    cell: (c) => (
      <span className={tableTokens.cellNumber}>{brl(c.getValue())}</span>
    ),
  }),
  titCol.accessor("em_aberto", {
    header: "Situação",
    cell: (c) =>
      c.getValue() ? (
        <span className={tableTokens.badgeWarning}>Em aberto</span>
      ) : (
        <span className={tableTokens.badgeNeutral}>Encerrado</span>
      ),
  }),
] as ColumnDef<NfeDoc360Titulo, unknown>[]

export default function DocumentoLastroFiscalPage() {
  const params = useParams<{ chave: string }>()
  const router = useRouter()
  const chave = typeof params.chave === "string" ? params.chave : ""
  const { data, isLoading, isError, error } = useNfeDocumento360(chave)

  const voltar = (
    <Button
      variant="secondary"
      onClick={() => router.push("/risco/lastro-fiscal")}
      className="h-[30px] text-[13px]"
    >
      <RiArrowLeftLine className="mr-1 size-4" aria-hidden />
      Voltar ao feed
    </Button>
  )

  if (isLoading) {
    return (
      <div className="space-y-4 p-6">
        <div className="h-8 w-64 animate-pulse rounded bg-gray-100 dark:bg-gray-900" />
        <div className="h-40 animate-pulse rounded bg-gray-100 dark:bg-gray-900" />
        <div className="h-40 animate-pulse rounded bg-gray-100 dark:bg-gray-900" />
      </div>
    )
  }

  if (isError) {
    const notFound = (error as { status?: number })?.status === 404
    return (
      <div className="p-6">
        {notFound ? (
          <EmptyState
            icon={RiFileTextLine}
            title="Documento sem XML ingerido"
            description="Essa nota ainda não tem o XML na base — os dados do documento chegam pela landing fiscal (Strata Collector). Assim que o XML for coletado, a ficha aparece aqui."
            action={voltar}
          />
        ) : (
          <ErrorState
            title="Não foi possível carregar o documento"
            description="Tente novamente em instantes."
            action={voltar}
          />
        )}
      </div>
    )
  }

  if (!data) return null
  const { nota } = data

  const identificacao = [
    { label: "Chave de acesso", value: nota.chave_acesso },
    { label: "Número", value: nota.numero },
    { label: "Série", value: nota.serie ?? "—" },
    { label: "Modelo", value: nota.modelo === "55" ? "55 (NF-e)" : nota.modelo ?? "—" },
    { label: "Natureza da operação", value: nota.natureza_operacao ?? "—" },
    { label: "Emissão", value: dataHora(nota.data_emissao) },
    { label: "Tipo", value: TIPO_OP[nota.tipo_operacao ?? ""] ?? nota.tipo_operacao ?? "—" },
    { label: "Finalidade", value: FINALIDADE[nota.finalidade ?? ""] ?? nota.finalidade ?? "—" },
  ]

  const partes = [
    { label: "Emitente (cedente)", value: nota.emitente_nome ?? "—" },
    { label: "CNPJ emitente", value: doc(nota.emitente_documento) },
    {
      label: "Município / UF emitente",
      value: [nota.emitente_municipio, nota.emitente_uf].filter(Boolean).join(" / ") || "—",
    },
    { label: "Destinatário (sacado)", value: nota.destinatario_nome ?? "—" },
    { label: "CNPJ/CPF destinatário", value: doc(nota.destinatario_documento) },
    {
      label: "Município / UF destinatário",
      value:
        [nota.destinatario_municipio, nota.destinatario_uf].filter(Boolean).join(" / ") || "—",
    },
  ]

  const valores = [
    { label: "Produtos", value: brl(nota.valor_produtos) },
    { label: "Frete", value: brl(nota.valor_frete) },
    { label: "Desconto", value: brl(nota.valor_desconto) },
    { label: "Tributos", value: brl(nota.valor_tributos) },
    { label: "Total da nota", value: brl(nota.valor_total) },
    { label: "Fatura (nº · líquido)", value: nota.numero_fatura
        ? `${nota.numero_fatura} · ${brl(nota.valor_fatura_liquido)}`
        : "—" },
  ]

  const sit = data.situacao_sefaz
  const situacao = [
    { label: "Autorizada (protocolo)", value: nota.autorizada
        ? `Sim · ${nota.protocolo ?? "—"}`
        : `Não${nota.cstat ? ` (cStat ${nota.cstat})` : ""}` },
    { label: "Autorização SEFAZ", value: dataHora(nota.data_autorizacao) },
    { label: "Situação atual", value: sit?.situacao ?? "—" },
    { label: "Cancelada", value: sit?.cancelada ? `Sim · ${dataHora(sit.dh_cancelamento)}` : "Não" },
    { label: "Manifestação do sacado", value: sit?.manifestacao ?? "—" },
    { label: "Última consulta SERPRO", value: dataHora(sit?.consultado_em) },
  ]

  const transporte = [
    { label: "Modalidade de frete", value: MOD_FRETE[nota.modalidade_frete ?? ""] ?? nota.modalidade_frete ?? "—" },
    { label: "Transportadora", value: nota.transportadora_nome ?? "—" },
    { label: "CNPJ transportadora", value: doc(nota.transportadora_documento) },
    {
      label: "Veículo (placa · UF)",
      value: nota.veiculo_placa
        ? `${nota.veiculo_placa}${nota.veiculo_uf ? ` · ${nota.veiculo_uf}` : ""}`
        : "—",
    },
  ]

  return (
    <div className="space-y-6 pb-10">
      <PageHeader
        title={`NF-e ${nota.numero}${nota.serie ? `/${nota.serie}` : ""}`}
        subtitle="Risco · Lastro fiscal · Documento"
        info="Ficha completa do documento fiscal: identificação, partes, valores, situação na SEFAZ, produtos, transporte, eventos e os títulos da carteira que a nota lastreia. Dados 100% do warehouse (silver)."
        actions={voltar}
      />

      <div className="space-y-6 px-6">
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <SectionCard icon={RiFileTextLine} title="Identificação">
            <PropertyList items={identificacao} columns={2} />
          </SectionCard>
          <SectionCard icon={RiFileTextLine} title="Partes">
            <PropertyList items={partes} columns={2} />
          </SectionCard>
          <SectionCard icon={RiPriceTag3Line} title="Valores">
            <PropertyList items={valores} columns={2} />
          </SectionCard>
          <SectionCard icon={RiFileTextLine} title="Situação na SEFAZ">
            <PropertyList items={situacao} columns={2} />
          </SectionCard>
        </div>

        <SectionCard icon={RiFileList3Line} title="Produtos" count={data.itens.length}>
          {data.itens.length === 0 ? (
            <p className={tableTokens.cellMuted}>Sem itens no XML da nota.</p>
          ) : (
            <DataTable data={data.itens} columns={ITEM_COLUMNS} density="compact" />
          )}
        </SectionCard>

        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <SectionCard icon={RiPriceTag3Line} title="Duplicatas" count={data.duplicatas.length}>
            {data.duplicatas.length === 0 ? (
              <p className={tableTokens.cellMuted}>Sem duplicatas.</p>
            ) : (
              <DataTable data={data.duplicatas} columns={DUP_COLUMNS} density="compact" />
            )}
          </SectionCard>
          <SectionCard icon={RiTruckLine} title="Transporte">
            <PropertyList items={transporte} columns={1} />
          </SectionCard>
        </div>

        <SectionCard icon={RiFileTextLine} title="Eventos SEFAZ" count={data.eventos.length}>
          {data.eventos.length === 0 ? (
            <p className={tableTokens.cellMuted}>
              Nenhum evento registrado para esta nota.
            </p>
          ) : (
            <DataTable data={data.eventos} columns={EVENTO_COLUMNS} density="compact" />
          )}
        </SectionCard>

        <SectionCard
          icon={RiFileList3Line}
          title="Títulos lastreados na carteira"
          count={data.titulos.length}
        >
          {data.titulos.length === 0 ? (
            <p className={tableTokens.cellMuted}>
              Nenhum título da carteira está vinculado a esta nota.
            </p>
          ) : (
            <DataTable data={data.titulos} columns={TITULO_COLUMNS} density="compact" />
          )}
        </SectionCard>
      </div>
    </div>
  )
}
