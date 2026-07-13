// src/app/(app)/risco/lastro-fiscal/page.tsx
//
// Risco · Lastro fiscal — feed de ocorrências SEFAZ nas notas que lastreiam
// a carteira EM ABERTO (F4 da integração SERPRO).
//
// Pattern: ListagemComDrilldown (§7) — PageHeader + KpiBand + DataTableShell
// (feed cronológico) + DrillDownSheet (?selected=<evento_id>).
//
// Fonte: /risco/lastro-fiscal/* (read puro sobre warehouse: silver SERPRO +
// ponte wh_titulo_fiscal). Grão da linha = evento SEFAZ × nota; catálogo
// FIS-* com severidade (crítica/média/baixa/positiva/info). Zero ocultação
// (§14.6): total do backend == linhas alcançáveis; nenhum corte silencioso.
//

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { RiFileShield2Line } from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import {
  DataTableShell,
  DrillDownSheet,
  KpiBand,
  PageHeader,
} from "@/design-system/components"
import type { KpiBandItem } from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type {
  LastroFiscalOcorrencia,
  LastroFiscalSeveridade,
} from "@/lib/api-client"
import {
  useLastroFiscalOcorrencias,
  useLastroFiscalResumo,
} from "@/lib/hooks/risco"
import { cx } from "@/lib/utils"

const PAGE_INFO =
  "Fatos oficiais da SEFAZ (via SERPRO) sobre as notas fiscais que lastreiam títulos em aberto: cancelamentos, manifestações do sacado, cartas de correção. Cancelamento pós-cessão é perda de lastro — sinal crítico. As notas entram e saem da vigilância conforme o título abre e liquida."

const brl = (v: number) =>
  v.toLocaleString("pt-BR", {
    style: "currency",
    currency: "BRL",
    maximumFractionDigits: 0,
  })

// Rótulos e badge por severidade do catálogo FIS-* (badge semântico §6).
const SEVERIDADE_META: Record<
  LastroFiscalSeveridade,
  { label: string; badge: string }
> = {
  critica: { label: "Crítica", badge: tableTokens.badgeDanger },
  media: { label: "Média", badge: tableTokens.badgeWarning },
  baixa: { label: "Baixa", badge: tableTokens.badgeNeutral },
  positiva: { label: "Positiva", badge: tableTokens.badgeSuccess },
  info: { label: "Info", badge: tableTokens.badgeNeutral },
}

function DataHoraCell({ iso }: { iso: string | null }) {
  if (!iso) return <span className={tableTokens.cellMuted}>—</span>
  const d = new Date(iso)
  return (
    <span className={tableTokens.cellSecondary} title={d.toLocaleString("pt-BR")}>
      {d.toLocaleDateString("pt-BR")}{" "}
      {d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" })}
    </span>
  )
}

const col = createColumnHelper<LastroFiscalOcorrencia>()

export default function LastroFiscalPage() {
  const router = useRouter()
  const sp = useSearchParams()
  const selectedId = sp.get("selected")

  const [search, setSearch] = React.useState("")
  const [sevFilter, setSevFilter] = React.useState<string[]>([])
  const [segment, setSegment] = React.useState<"todas" | "pos_cessao">("todas")

  const resumoQuery = useLastroFiscalResumo()
  const ocorrenciasQuery = useLastroFiscalOcorrencias()
  const ocorrencias = React.useMemo(
    () => ocorrenciasQuery.data?.ocorrencias ?? [],
    [ocorrenciasQuery.data],
  )

  const selected = React.useMemo(
    () =>
      selectedId
        ? (ocorrencias.find((o) => o.evento_id === selectedId) ?? null)
        : null,
    [ocorrencias, selectedId],
  )

  const setSelected = React.useCallback(
    (id: string | null) => {
      const params = new URLSearchParams(sp.toString())
      if (id) params.set("selected", id)
      else params.delete("selected")
      const qs = params.toString()
      router.push(qs ? `?${qs}` : "?")
    },
    [router, sp],
  )

  const resumo = resumoQuery.data
  const kpiItems = React.useMemo<KpiBandItem[]>(() => {
    if (!resumo) return []
    return [
      {
        eyebrow: "NOTAS VIGIADAS",
        value: resumo.notas_vigiadas.toLocaleString("pt-BR"),
        sub: "lastreiam títulos em aberto",
      },
      {
        eyebrow: "NOTAS MORTAS · TÍTULO ABERTO",
        value: String(resumo.notas_mortas),
        sub: `${brl(resumo.notas_mortas_saldo)} de saldo devedor exposto`,
      },
      {
        eyebrow: `SEM MANIFESTAÇÃO > ${resumo.sem_manifestacao_dias}D`,
        value: String(resumo.sem_manifestacao),
        sub: `${brl(resumo.sem_manifestacao_saldo)} sem ciência do sacado`,
      },
      {
        eyebrow: "CONFIRMADAS PELO SACADO",
        value: `${resumo.pct_confirmada.toLocaleString("pt-BR")}%`,
        sub: `${resumo.confirmadas} notas com confirmação (trava cancelamento)`,
      },
    ]
  }, [resumo])

  // Ordem das colunas definida pelo Ricardo (2026-07-13): quem (cedente/
  // sacado) -> o que (documento/valor/titulos) -> estado (evento/situacao)
  // -> quando (data/hora no fim, feed continua ordenado por ela).
  const columns = React.useMemo<ColumnDef<LastroFiscalOcorrencia, unknown>[]>(
    () => [
      col.accessor("emitente_nome", {
        header: "Cedente",
        cell: (info) => {
          const nome = info.getValue() as string | null
          return (
            <span
              className={cx(tableTokens.cellStrong, "block max-w-[200px] truncate")}
              title={nome ?? undefined}
            >
              {nome ?? "—"}
            </span>
          )
        },
      }) as ColumnDef<LastroFiscalOcorrencia, unknown>,
      col.accessor("destinatario_nome", {
        header: "Sacado",
        cell: (info) => {
          const nome = info.getValue() as string | null
          return (
            <span
              className={cx(tableTokens.cellText, "block max-w-[180px] truncate")}
              title={nome ?? undefined}
            >
              {nome ?? "—"}
            </span>
          )
        },
      }) as ColumnDef<LastroFiscalOcorrencia, unknown>,
      col.accessor("nfe_numero", {
        header: "Documento",
        cell: (info) => (
          <span
            className={tableTokens.cellTextMono}
            title={info.row.original.chave_acesso}
          >
            NFe {(info.getValue() as number | null) ?? "—"}
          </span>
        ),
      }) as ColumnDef<LastroFiscalOcorrencia, unknown>,
      col.accessor("valor_nota", {
        header: "Valor",
        meta: { align: "right" },
        cell: (info) => {
          const v = info.getValue() as number | null
          return v === null ? (
            <span className={tableTokens.cellMuted}>—</span>
          ) : (
            <span className={tableTokens.cellNumber}>{brl(v)}</span>
          )
        },
      }) as ColumnDef<LastroFiscalOcorrencia, unknown>,
      col.accessor("saldo_devedor_aberto", {
        header: () => (
          <span title="Títulos em aberto lastreados pela nota (qtd · saldo devedor)">
            Títulos
          </span>
        ),
        meta: { align: "right" },
        cell: (info) => (
          <span className={tableTokens.cellNumberSecondary}>
            {info.row.original.qtd_titulos_abertos} ·{" "}
            {brl(info.getValue() as number)}
          </span>
        ),
      }) as ColumnDef<LastroFiscalOcorrencia, unknown>,
      col.accessor("desc_evento", {
        header: () => (
          <span title="Evento SEFAZ que gerou a ocorrência (código FIS + severidade)">
            Evento
          </span>
        ),
        cell: (info) => {
          const meta = SEVERIDADE_META[info.row.original.severidade]
          return (
            <span
              className={cx(tableTokens.badge, meta.badge, "whitespace-nowrap")}
              title={[
                `${info.row.original.codigo} · ${meta.label}`,
                info.getValue() as string | null,
                info.row.original.justificativa,
              ]
                .filter(Boolean)
                .join(" — ")}
            >
              {(info.getValue() as string | null) ??
                `Evento ${info.row.original.tp_evento}`}
            </span>
          )
        },
      }) as ColumnDef<LastroFiscalOcorrencia, unknown>,
      col.accessor("situacao_nota", {
        header: "Situação",
        cell: (info) => {
          const s = info.getValue() as string | null
          if (!s) return <span className={tableTokens.cellMuted}>—</span>
          const morta = s.startsWith("cancelada") || s === "denegada"
          return (
            <span
              className={cx(
                tableTokens.badge,
                "whitespace-nowrap",
                morta ? tableTokens.badgeDanger : tableTokens.badgeNeutral,
              )}
            >
              {s.replaceAll("_", " ")}
            </span>
          )
        },
      }) as ColumnDef<LastroFiscalOcorrencia, unknown>,
      col.accessor("dh_evento", {
        header: "Data · Hora",
        meta: { align: "right" },
        cell: (info) => <DataHoraCell iso={info.getValue() as string | null} />,
      }) as ColumnDef<LastroFiscalOcorrencia, unknown>,
    ],
    [],
  )

  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Lastro fiscal"
        info={PAGE_INFO}
        subtitle="Risco · Monitoramento SERPRO"
      />

      <KpiBand items={kpiItems} loading={resumoQuery.isLoading && !resumo} />

      <DataTableShell<LastroFiscalOcorrencia>
        data={ocorrencias}
        columns={columns}
        loading={ocorrenciasQuery.isLoading && !ocorrenciasQuery.data}
        error={ocorrenciasQuery.error}
        onRetry={() => ocorrenciasQuery.refetch()}
        onRowClick={(o) => setSelected(o.evento_id)}
        search={{
          value: search,
          onChange: setSearch,
          placeholder: "Buscar emitente, nota, chave…",
        }}
        statusFilter={{
          label: "Severidade",
          ariaLabel: "Filtrar por severidade (multi-seleção)",
          options: [
            {
              value: "critica",
              label: "Crítica",
              tone: "danger",
              filter: (o) => o.severidade === "critica",
            },
            {
              value: "media",
              label: "Média",
              tone: "warning",
              filter: (o) => o.severidade === "media",
            },
            {
              value: "positiva",
              label: "Positiva",
              tone: "success",
              filter: (o) => o.severidade === "positiva",
            },
            {
              value: "info",
              label: "Info/baixa",
              tone: "neutral",
              filter: (o) => o.severidade === "info" || o.severidade === "baixa",
            },
          ],
          value: sevFilter,
          onChange: setSevFilter,
        }}
        segments={{
          value: segment,
          onChange: (v) => setSegment(v as typeof segment),
          options: [
            { value: "todas", label: "Todas", filter: () => true },
            {
              value: "pos_cessao",
              label: "Pós-cessão",
              filter: (o) => o.pos_cessao === true,
            },
          ],
        }}
        itemNoun={{ singular: "ocorrência", plural: "ocorrências" }}
        emptyState={{
          icon: RiFileShield2Line,
          title: "Nenhuma ocorrência",
          description:
            "Nenhum evento SEFAZ registrado nas notas da carteira em aberto — bom sinal. O monitoramento SERPRO avisa em minutos quando algo acontecer.",
        }}
      />

      <DrillDownSheet
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={
          selected
            ? `${selected.desc_evento ?? "Evento"} · NFe ${selected.nfe_numero ?? "—"}`
            : ""
        }
        size="md"
      >
        {selected && <OcorrenciaDetalhe ocorrencia={selected} />}
      </DrillDownSheet>
    </div>
  )
}

function Linha({
  rotulo,
  children,
}: {
  rotulo: string
  children: React.ReactNode
}) {
  return (
    <div className="flex items-start justify-between gap-4 border-b border-gray-100 py-2 last:border-b-0 dark:border-gray-800">
      <dt className={cx(tableTokens.cellSecondary, "shrink-0")}>{rotulo}</dt>
      <dd className={cx(tableTokens.cellText, "text-right min-w-0")}>{children}</dd>
    </div>
  )
}

function OcorrenciaDetalhe({
  ocorrencia,
}: {
  ocorrencia: LastroFiscalOcorrencia
}) {
  const meta = SEVERIDADE_META[ocorrencia.severidade]
  return (
    <dl>
      <Linha rotulo="Sinal">
        <span className={cx(tableTokens.badge, meta.badge)}>
          {ocorrencia.codigo} · {meta.label}
        </span>
      </Linha>
      <Linha rotulo="Quando">
        {ocorrencia.dh_evento
          ? new Date(ocorrencia.dh_evento).toLocaleString("pt-BR")
          : "—"}
      </Linha>
      <Linha rotulo="Autor (CNPJ/CPF)">{ocorrencia.autor_documento ?? "—"}</Linha>
      {ocorrencia.justificativa ? (
        <Linha rotulo="Justificativa">{ocorrencia.justificativa}</Linha>
      ) : null}
      <Linha rotulo="Pós-cessão">
        {ocorrencia.pos_cessao === null
          ? "—"
          : ocorrencia.pos_cessao
            ? "Sim — evento DEPOIS do desembolso"
            : "Não"}
      </Linha>
      <Linha rotulo="Emitente (cedente)">
        {ocorrencia.emitente_nome ?? "—"}
        {ocorrencia.emitente_documento ? ` · ${ocorrencia.emitente_documento}` : ""}
      </Linha>
      <Linha rotulo="Destinatário (sacado)">
        {ocorrencia.destinatario_nome ?? "—"}
      </Linha>
      <Linha rotulo="Valor da nota">
        {ocorrencia.valor_nota !== null ? brl(ocorrencia.valor_nota) : "—"}
      </Linha>
      <Linha rotulo="Situação atual da nota">
        {ocorrencia.situacao_nota?.replaceAll("_", " ") ?? "—"}
      </Linha>
      <Linha rotulo="Títulos em aberto lastreados">
        {ocorrencia.qtd_titulos_abertos} ·{" "}
        {brl(ocorrencia.saldo_devedor_aberto)} de saldo devedor
      </Linha>
      <Linha rotulo="Efetivação da operação">
        {ocorrencia.primeira_efetivacao
          ? new Date(ocorrencia.primeira_efetivacao).toLocaleString("pt-BR")
          : "—"}
      </Linha>
      <Linha rotulo="Chave de acesso">
        <span className={cx(tableTokens.cellTextMono, "break-all")}>
          {ocorrencia.chave_acesso}
        </span>
      </Linha>
    </dl>
  )
}
