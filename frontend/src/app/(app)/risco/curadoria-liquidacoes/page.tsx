// src/app/(app)/risco/curadoria-liquidacoes/page.tsx
//
// Risco · Curadoria de liquidações — a máquina de rotulagem do modelo de
// detecção de anomalias (handoff 2026-07-08).
//
// Princípios duros implementados aqui:
// - Mostra TODAS as liquidações (não só alertas do modelo): falso negativo
//   precisa ser etiquetável. Paginação SERVER-SIDE real (~93k eventos) com
//   total exposto — nada é cortado silenciosamente (§14.6).
// - Tag é append-only: marcar de novo cria registro novo; nada se apaga.
// - Sugestão do sistema (score, regra dura, candidato de lastro) é FLAG,
//   nunca tag — a tag é sempre humana, com autor e data.
//
// Pattern: ListagemComDrilldown (DataTable direta + DrillDownSheet de
// evidência via ?selected=<id>); paginação server-side no rodapé.
// MOTIVO: DataTableShell é client-side (~200 rows) — aqui o universo é 93k.
//

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import {
  RiAlarmWarningLine,
  RiArrowLeftSLine,
  RiArrowRightSLine,
  RiCheckLine,
  RiFlaskLine,
  RiSearchEyeLine,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import { format, parseISO } from "date-fns"
import { toast } from "sonner"

import { Button } from "@/components/tremor/Button"
import { Divider } from "@/components/tremor/Divider"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/tremor/Select"
import { Textarea } from "@/components/tremor/Textarea"
import {
  DataTable,
  DrillDownSheet,
  FilterSearch,
  PageHeader,
  SegmentSwitch,
} from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type { LiquidacaoCuradoriaRow } from "@/lib/api-client"
import {
  useCuradoriaLiquidacoes,
  useDeteccaoModelos,
  usePontuarAgora,
  useTagLiquidacao,
  useTreinarModelo,
} from "@/lib/hooks/risco"
import { cx } from "@/lib/utils"

const PAGE_SIZE = 50

// Labels humanas das features (fatores de explicabilidade §14.3).
const FEATURE_LABELS: Record<string, string> = {
  bit_pago_agencia_cliente: "Pago na agência do cedente (declarado pelo banco)",
  bit_pago_praca_cliente: "Pago na praça do cedente (declarado pelo banco)",
  bit_fora_praca_sacado: "Pago fora da praça do sacado (declarado pelo banco)",
  pago_banco_digital: "Pago em banco digital",
  match_agencia_conta_cedente: "Agência onde o cedente mantém conta",
  cidade_pgto_eq_cedente: "Pagamento na cidade do cedente",
  cidade_pgto_neq_sacado: "Pagamento fora da cidade do sacado",
  canal_cooperativa: "Canal: cooperativa",
  canal_ip: "Canal: instituição de pagamento",
  canal_sem_praca: "Canal: banco sem praça física",
  canal_nao_resolvido: "Canal não resolvido",
  quebra_fingerprint: "Quebra do padrão bancário do sacado",
  agencia_compartilhada: "Agência compartilhada por vários sacados do cedente",
  canal_baixa_manual: "Liquidação por baixa manual",
  baixa_confirmada: "Boleto baixado por instrução e liquidado por fora",
  sem_ocorrencia: "Bancarizado sem ocorrência de liquidação",
  baixa_manual_produto_anomala: "Baixa manual em produto onde é anômala",
  boleto_nao_esperado_mas_teve: "Boleto em produto onde não era esperado",
  contrato_aberto: "Produto sem contrato definido",
  pago_exato_vencimento: "Pago exatamente no vencimento",
  lote_dia: "Liquidado em lote (mesmo dia, mesmo cedente)",
  ticket_z: "Valor fora do padrão do cedente",
  valor_log: "Magnitude do valor",
}

type Segmento = "todas" | "sugeridas" | "regra_dura" | "fraude" | "sem_tag"

function ScoreBadge({ row }: { row: LiquidacaoCuradoriaRow }) {
  if (row.regra_dura) {
    return (
      <span
        className={cx(tableTokens.badge, tableTokens.badgeDanger)}
        title={row.regra_dura_motivo ?? "Regra determinística disparada"}
      >
        Regra dura
      </span>
    )
  }
  if (row.score === null) {
    return <span className={tableTokens.cellMuted}>—</span>
  }
  const pct = Math.round(row.score * 100)
  const classe =
    row.score >= 0.7
      ? tableTokens.badgeDanger
      : row.score >= 0.4
        ? tableTokens.badgeWarning
        : tableTokens.badgeNeutral
  return <span className={cx(tableTokens.badge, classe)}>{pct}%</span>
}

function TagBadge({ row }: { row: LiquidacaoCuradoriaRow }) {
  if (!row.tag_vigente) {
    return <span className={tableTokens.cellMuted}>—</span>
  }
  const fraude = row.tag_vigente === "FRAUDE"
  return (
    <span
      className={cx(
        tableTokens.badge,
        fraude ? tableTokens.badgeDanger : tableTokens.badgeSuccess,
      )}
      title={
        row.tag_autor
          ? `${row.tag_autor} · ${row.tag_em ? format(parseISO(row.tag_em), "dd/MM/yyyy HH:mm") : ""}`
          : undefined
      }
    >
      {fraude ? "Fraude" : "OK"}
    </span>
  )
}

const col = createColumnHelper<LiquidacaoCuradoriaRow>()

export default function CuradoriaLiquidacoesPage() {
  const router = useRouter()
  const sp = useSearchParams()
  const selectedId = sp.get("selected")

  const [page, setPage] = React.useState(1)
  const [busca, setBusca] = React.useState("")
  const [buscaDebounced, setBuscaDebounced] = React.useState("")
  const [segmento, setSegmento] = React.useState<Segmento>("todas")
  const [produto, setProduto] = React.useState<string>("todos")

  React.useEffect(() => {
    const t = setTimeout(() => setBuscaDebounced(busca), 350)
    return () => clearTimeout(t)
  }, [busca])
  React.useEffect(() => {
    setPage(1)
  }, [buscaDebounced, segmento, produto])

  const filtros = React.useMemo(
    () => ({
      page,
      page_size: PAGE_SIZE,
      cedente: buscaDebounced || undefined,
      produto_sigla: produto !== "todos" ? produto : undefined,
      sugeridos: segmento === "sugeridas" || undefined,
      regra_dura: segmento === "regra_dura" || undefined,
      tag:
        segmento === "fraude"
          ? ("fraude" as const)
          : segmento === "sem_tag"
            ? ("sem_tag" as const)
            : undefined,
    }),
    [page, buscaDebounced, segmento, produto],
  )

  const listQuery = useCuradoriaLiquidacoes(filtros)
  const modelosQuery = useDeteccaoModelos()
  const tagMut = useTagLiquidacao()
  const treinarMut = useTreinarModelo()
  const pontuarMut = usePontuarAgora()

  const pageData = listQuery.data
  const rows = pageData?.rows ?? []
  const total = pageData?.total ?? 0
  const totalPaginas = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const selected = React.useMemo(
    () => (selectedId ? (rows.find((r) => r.liquidacao_id === selectedId) ?? null) : null),
    [rows, selectedId],
  )
  const [nota, setNota] = React.useState("")
  React.useEffect(() => setNota(""), [selectedId])

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

  const marcar = React.useCallback(
    async (row: LiquidacaoCuradoriaRow, tag: "fraude" | "ok", notaTexto?: string) => {
      try {
        await tagMut.mutateAsync({
          liquidacaoId: row.liquidacao_id,
          tag,
          nota: notaTexto || null,
        })
        toast.success(
          tag === "fraude"
            ? `Liquidação do título ${row.titulo_numero ?? row.titulo_id} marcada como fraude.`
            : `Liquidação do título ${row.titulo_numero ?? row.titulo_id} marcada como OK.`,
        )
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Falha ao registrar a marcação.")
      }
    },
    [tagMut],
  )

  const modelo = modelosQuery.data?.find((m) => m.nome === "liquidacao_boleto")

  const treinar = React.useCallback(async () => {
    try {
      const r = await treinarMut.mutateAsync("liquidacao_boleto")
      toast.success(
        `Versão v${r.versao} treinada (inativa). Gini OOT: ${String(
          (r.metrics as Record<string, unknown>)?.gini_oot ?? "—",
        )}. Ative na lista de versões para valer no scoring.`,
      )
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao treinar.")
    }
  }, [treinarMut])

  const pontuar = React.useCallback(async () => {
    try {
      const r = await pontuarMut.mutateAsync("liquidacao_boleto")
      toast.success(
        `Scoring executado: ${r.scores_gravados.toLocaleString("pt-BR")} liquidações avaliadas, ${r.regra_dura} regras duras.`,
      )
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao pontuar.")
    }
  }, [pontuarMut])

  const produtos = React.useMemo(() => {
    // Opções do filtro de produto: colhidas da própria página (nome completo).
    const vistos = new Map<string, string>()
    for (const r of rows) {
      if (r.produto_sigla) vistos.set(r.produto_sigla, r.produto_nome ?? r.produto_sigla)
    }
    return Array.from(vistos.entries()).sort((a, b) => a[1].localeCompare(b[1]))
  }, [rows])

  const columns = React.useMemo<ColumnDef<LiquidacaoCuradoriaRow, unknown>[]>(
    () => [
      col.accessor("data_evento", {
        header: "Data",
        size: 92,
        cell: (info) => (
          <span className={tableTokens.cellSecondary}>
            {format(parseISO(info.getValue() as string), "dd/MM/yyyy")}
          </span>
        ),
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.accessor("cedente_nome", {
        header: "Cedente",
        size: 200,
        cell: (info) => (
          <span className={tableTokens.cellStrong}>{info.getValue() ?? "—"}</span>
        ),
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.accessor("sacado_nome", {
        header: "Sacado",
        size: 180,
        cell: (info) => (
          <span className={tableTokens.cellText}>{info.getValue() ?? "—"}</span>
        ),
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.accessor("produto_nome", {
        header: "Produto",
        size: 140,
        cell: (info) => (
          <span className={tableTokens.cellText}>
            {info.getValue() ?? info.row.original.produto_sigla ?? "—"}
          </span>
        ),
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.accessor("valor", {
        header: "Valor",
        size: 110,
        cell: (info) => {
          const v = info.getValue() as number | null
          return v !== null ? (
            <span className={tableTokens.cellNumber}>
              {v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}
            </span>
          ) : (
            <span className={tableTokens.cellMuted}>—</span>
          )
        },
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.display({
        id: "mecanica",
        header: "Mecânica",
        size: 150,
        cell: ({ row }) => (
          <span className={tableTokens.cellSecondary}>
            {row.original.canal === "bancaria" ? "Bancária" : "Baixa manual"}
            {row.original.evidencia === "baixa_confirmada" && (
              <span className={cx(tableTokens.badge, tableTokens.badgeWarning, "ml-1.5")}>
                baixa confirmada
              </span>
            )}
          </span>
        ),
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.display({
        id: "score",
        header: "Risco",
        size: 96,
        cell: ({ row }) => <ScoreBadge row={row.original} />,
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.display({
        id: "sugestao",
        header: "Sugestão",
        size: 96,
        cell: ({ row }) =>
          row.original.candidato_lastro ? (
            <span
              className={cx(tableTokens.badge, tableTokens.badgeWarning)}
              title="Título com lastro marcado como inconsistente na verificação — candidato a fraude de liquidação. Sugestão do sistema; a tag é sua."
            >
              candidato
            </span>
          ) : (
            <span className={tableTokens.cellMuted}>—</span>
          ),
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.display({
        id: "tag",
        header: "Marcação",
        size: 90,
        cell: ({ row }) => <TagBadge row={row.original} />,
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.display({
        id: "actions",
        header: "",
        size: 84,
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button
              variant="ghost"
              className="size-7 p-0 text-red-600 dark:text-red-400"
              aria-label="Marcar como fraude"
              title="Marcar como fraude"
              isLoading={tagMut.isPending}
              onClick={(e) => {
                e.stopPropagation()
                void marcar(row.original, "fraude")
              }}
            >
              <RiAlarmWarningLine className="size-4" aria-hidden />
            </Button>
            <Button
              variant="ghost"
              className="size-7 p-0"
              aria-label="Marcar como OK"
              title="Marcar como OK"
              isLoading={tagMut.isPending}
              onClick={(e) => {
                e.stopPropagation()
                void marcar(row.original, "ok")
              }}
            >
              <RiCheckLine className="size-4" aria-hidden />
            </Button>
          </div>
        ),
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
    ],
    [marcar, tagMut.isPending],
  )

  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Curadoria de liquidações"
        info="Todas as liquidações da carteira, com o risco estimado pelo modelo de detecção e as regras determinísticas. Marque fraude/OK: cada marcação é registrada com autor e data (nada se apaga) e realimenta o treino do modelo — IA opina, humano homologa."
        subtitle="Risco · Detecção de anomalias"
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              className="h-[30px] text-[13px]"
              isLoading={pontuarMut.isPending}
              onClick={() => void pontuar()}
              title="Aplica a versão ativa do modelo (ou só as regras duras) agora"
            >
              Pontuar agora
            </Button>
            <Button
              variant="secondary"
              className="h-[30px] text-[13px]"
              isLoading={treinarMut.isPending}
              onClick={() => void treinar()}
              title="Treina uma nova versão com as marcações homologadas (nasce inativa)"
            >
              Treinar modelo
            </Button>
          </div>
        }
      />

      {/* Faixa do modelo: versão ativa + métrica — visibilidade do estado (§7.3) */}
      {modelo && (
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded-md border border-gray-200 bg-gray-50 px-4 py-2 dark:border-gray-800 dark:bg-gray-900">
          <RiFlaskLine className="size-4 text-gray-500" aria-hidden />
          <span className={tableTokens.cellSecondary}>
            Modelo <span className={tableTokens.cellStrong}>liquidação de boleto</span>
            {" · "}
            {modelo.versao_ativa
              ? `versão ativa v${modelo.versao_ativa}`
              : "sem versão ativa — exibindo apenas regras determinísticas"}
            {modelo.versoes.length > 0 &&
              modelo.versoes[0] &&
              ` · última treinada: v${modelo.versoes[0].versao} (Gini OOT ${String(
                (modelo.versoes[0].metrics as Record<string, unknown>)?.gini_oot ?? "—",
              )})`}
          </span>
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2">
        <FilterSearch
          value={busca}
          onChange={(e) => setBusca(e.target.value)}
          placeholder="Buscar cedente..."
          className="w-64"
        />
        <SegmentSwitch
          value={segmento}
          onChange={(v) => setSegmento(v as Segmento)}
          options={[
            { value: "todas", label: "Todas" },
            { value: "sugeridas", label: "Sugeridas" },
            { value: "regra_dura", label: "Regra dura" },
            { value: "fraude", label: "Fraude" },
            { value: "sem_tag", label: "Sem marcação" },
          ]}
        />
        <Select value={produto} onValueChange={setProduto}>
          <SelectTrigger className="h-[30px] w-56 text-[13px]">
            <SelectValue placeholder="Produto" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="todos">Todos os produtos</SelectItem>
            {produtos.map(([sigla, nome]) => (
              <SelectItem key={sigla} value={sigla}>
                {nome} ({sigla})
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <span className={cx(tableTokens.cellSecondary, "ml-auto tabular-nums")}>
          {total.toLocaleString("pt-BR")} liquidações
        </span>
      </div>

      <DataTable<LiquidacaoCuradoriaRow>
        data={rows}
        columns={columns}
        loading={listQuery.isLoading}
        error={listQuery.error ? listQuery.error.message : null}
        onRetry={() => listQuery.refetch()}
        onRowClick={(r) => setSelected(r.liquidacao_id)}
        showDensityToggle={false}
        showColumnManager={false}
        renderEmpty={() => (
          <div className="flex flex-col items-center gap-1 py-10">
            <RiSearchEyeLine className="size-6 text-gray-400" aria-hidden />
            <span className={tableTokens.cellSecondary}>
              Nenhuma liquidação com estes filtros.
            </span>
          </div>
        )}
        renderFooter={() => (
          <div className="flex items-center justify-between px-3 py-2">
            <span className={cx(tableTokens.cellSecondary, "tabular-nums")}>
              {total === 0
                ? "0 de 0"
                : `${((page - 1) * PAGE_SIZE + 1).toLocaleString("pt-BR")}–${Math.min(
                    page * PAGE_SIZE,
                    total,
                  ).toLocaleString("pt-BR")} de ${total.toLocaleString("pt-BR")}`}
              {listQuery.isFetching && " · atualizando…"}
            </span>
            <div className="flex items-center gap-1">
              <Button
                variant="ghost"
                className="h-7 px-2"
                disabled={page <= 1 || listQuery.isFetching}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                aria-label="Página anterior"
              >
                <RiArrowLeftSLine className="size-4" aria-hidden />
              </Button>
              <span className={cx(tableTokens.cellSecondary, "tabular-nums")}>
                {page} / {totalPaginas.toLocaleString("pt-BR")}
              </span>
              <Button
                variant="ghost"
                className="h-7 px-2"
                disabled={page >= totalPaginas || listQuery.isFetching}
                onClick={() => setPage((p) => Math.min(totalPaginas, p + 1))}
                aria-label="Próxima página"
              >
                <RiArrowRightSLine className="size-4" aria-hidden />
              </Button>
            </div>
          </div>
        )}
      />

      {/* Drawer: evidência completa + marcação com nota */}
      <DrillDownSheet
        open={selected !== null}
        onClose={() => setSelected(null)}
        title={
          selected
            ? `Título ${selected.titulo_numero ?? selected.titulo_id} · ${selected.cedente_nome ?? ""}`
            : ""
        }
        size="md"
      >
        {selected && (
          <div className="flex flex-col gap-5 p-6">
            <div className="flex flex-col gap-1">
              <span className={tableTokens.header}>Evento</span>
              <span className={tableTokens.cellSecondary}>
                {format(parseISO(selected.data_evento), "dd/MM/yyyy")} ·{" "}
                {selected.produto_nome ?? selected.produto_sigla ?? "—"} ·{" "}
                {selected.valor !== null
                  ? selected.valor.toLocaleString("pt-BR", {
                      style: "currency",
                      currency: "BRL",
                    })
                  : "—"}
              </span>
              <span className={tableTokens.cellSecondary}>
                Sacado: {selected.sacado_nome ?? "—"}
                {selected.sacado_documento && ` (${selected.sacado_documento})`}
              </span>
              <span className={tableTokens.cellSecondary}>
                Mecânica: {selected.canal === "bancaria" ? "bancária" : "baixa manual"}
                {selected.evidencia && ` · evidência: ${selected.evidencia}`}
                {selected.local_pagamento && ` · local: ${selected.local_pagamento}`}
              </span>
            </div>

            {selected.regra_dura && (
              <div className="flex flex-col gap-1">
                <span className={tableTokens.header}>Regra determinística</span>
                <span className={cx(tableTokens.badge, tableTokens.badgeDanger, "w-fit")}>
                  {selected.regra_dura_motivo ?? "Regra dura disparada"}
                </span>
              </div>
            )}

            {selected.fatores && selected.fatores.length > 0 && (
              <div className="flex flex-col gap-2">
                <span className={tableTokens.header}>
                  Por que este risco ({Math.round((selected.score ?? 0) * 100)}%)
                </span>
                <ul className="flex flex-col gap-1">
                  {selected.fatores.map((f) => (
                    <li key={f.feature} className="flex items-baseline justify-between gap-3">
                      <span className={tableTokens.cellText}>
                        {FEATURE_LABELS[f.feature] ?? f.feature}
                      </span>
                      <span
                        className={cx(
                          tableTokens.cellNumber,
                          f.contrib > 0
                            ? "text-red-600 dark:text-red-400"
                            : "text-gray-500",
                        )}
                      >
                        {f.contrib > 0 ? "+" : ""}
                        {f.contrib.toLocaleString("pt-BR", { maximumFractionDigits: 2 })}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            <Divider className="my-0" />

            <div className="flex flex-col gap-2">
              <span className={tableTokens.header}>Marcação</span>
              {selected.tag_vigente && (
                <span className={tableTokens.cellSecondary}>
                  Vigente: <TagBadge row={selected} />
                  {selected.tag_nota && ` — "${selected.tag_nota}"`}
                </span>
              )}
              <Textarea
                value={nota}
                onChange={(e) => setNota(e.target.value)}
                placeholder="Nota (opcional) — por que esta liquidação é fraude/OK?"
                rows={2}
              />
              <div className="flex gap-2">
                <Button
                  variant="destructive"
                  isLoading={tagMut.isPending}
                  onClick={() => void marcar(selected, "fraude", nota)}
                >
                  Marcar fraude
                </Button>
                <Button
                  variant="secondary"
                  isLoading={tagMut.isPending}
                  onClick={() => void marcar(selected, "ok", nota)}
                >
                  Marcar OK
                </Button>
              </div>
              <span className={tableTokens.cellMuted}>
                Marcações são registradas com autor e data e nunca são apagadas —
                remarcar cria um novo registro.
              </span>
            </div>
          </div>
        )}
      </DrillDownSheet>
    </div>
  )
}
