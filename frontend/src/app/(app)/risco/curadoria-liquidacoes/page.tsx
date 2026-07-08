// src/app/(app)/risco/curadoria-liquidacoes/page.tsx
//
// Risco · Curadoria de liquidações — a máquina de rotulagem do modelo de
// detecção de anomalias (handoff 2026-07-08; ajustes de UX 2026-07-08:
// anatomia canônica + filtros Cedente/Sacado/Produto/Situação + coluna
// "Sinal" com a conclusão legível do sistema).
//
// Princípios duros implementados aqui:
// - Mostra TODAS as liquidações (não só alertas do modelo): falso negativo
//   precisa ser etiquetável. Paginação SERVER-SIDE real (~93k eventos) com
//   total exposto — nada é cortado silenciosamente (§14.6).
// - Tag é append-only: marcar de novo cria registro novo; nada se apaga.
// - Sugestão do sistema (sinais, score, regra dura) é FLAG, nunca tag —
//   a tag é sempre humana, com autor e data.
//
// Anatomia: canônica das listagens CRUD (Card > busca + segments + contador
// > tabela > rodapé), com a MECÂNICA server-side por trás.
// MOTIVO: DataTableShell é client-side (~200 rows) — aqui o universo é 93k;
// a anatomia é reproduzida manualmente para manter a identidade visual.
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
import { Card } from "@/components/tremor/Card"
import { Divider } from "@/components/tremor/Divider"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import { Textarea } from "@/components/tremor/Textarea"
import {
  DataTable,
  DrillDownSheet,
  FilterSearch,
  filterControlClass,
  PageHeader,
  SegmentSwitch,
} from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type { LiquidacaoCuradoriaRow } from "@/lib/api-client"
import {
  useContratosLiquidacao,
  useCuradoriaLiquidacoes,
  useDeteccaoModelos,
  useMemoriaLiquidacao,
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

// Conclusões do sistema ("qual foi o bad") — códigos do backend em pt-BR.
const SINAL_LABELS: Record<string, string> = {
  regra_dura: "Sacado de outra cidade pagou na agência do cedente",
  baixa_confirmada: "Boleto baixado por instrução e liquidado por fora",
  pago_agencia_cedente: "Pago na agência do cedente",
  agencia_conta_cedente: "Pago em agência onde o cedente mantém conta",
  quebra_fingerprint: "Quebrou o padrão bancário do sacado",
  boleto_nao_esperado: "Boleto em produto onde não era esperado",
  lastro_inconsistente: "Lastro marcado inconsistente na verificação",
  fora_praca_sacado: "Pago fora da praça do sacado",
  sem_ocorrencia: "Bancarizado sem ocorrência de liquidação",
}
const SINAL_CURTO: Record<string, string> = {
  regra_dura: "agência do cedente",
  baixa_confirmada: "baixa confirmada",
  pago_agencia_cedente: "agência do cedente",
  agencia_conta_cedente: "conta do cedente",
  quebra_fingerprint: "quebra de padrão",
  boleto_nao_esperado: "boleto inesperado",
  lastro_inconsistente: "lastro inconsistente",
  fora_praca_sacado: "fora da praça",
  sem_ocorrencia: "sem ocorrência",
}
// Sinais fortes ganham pill amber; informativos ficam neutros.
const SINAIS_FORTES = new Set([
  "regra_dura",
  "baixa_confirmada",
  "pago_agencia_cedente",
  "agencia_conta_cedente",
  "lastro_inconsistente",
])

// Dicionário Titulo.Situacao (mapeado 2026-07-08).
const SITUACAO_LABELS: Record<number, string> = {
  0: "Em aberto",
  1: "Liquidação Normal",
  2: "Liquidação em Cartório",
  3: "Baixado",
  5: "Recomprado",
  7: "Recuperação de Crédito",
  9: "Perda",
}

type Segmento = "todas" | "sugeridas" | "regra_dura" | "fraude" | "sem_tag"

function ScoreBadge({ row }: { row: LiquidacaoCuradoriaRow }) {
  if (row.regra_dura) {
    return (
      <span
        className={cx(tableTokens.badge, tableTokens.badgeDanger)}
        title={row.regra_dura_motivo ?? "Padrão inequívoco de auto-liquidação"}
      >
        Padrão crítico
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

function SinaisCell({ sinais }: { sinais: string[] }) {
  if (sinais.length === 0) {
    return <span className={tableTokens.cellMuted}>sem sinal</span>
  }
  const [primeiro, ...resto] = sinais
  return (
    <div className="flex items-center gap-1">
      <span
        className={cx(
          tableTokens.badge,
          SINAIS_FORTES.has(primeiro)
            ? tableTokens.badgeWarning
            : tableTokens.badgeNeutral,
        )}
        title={SINAL_LABELS[primeiro] ?? primeiro}
      >
        {SINAL_CURTO[primeiro] ?? primeiro}
      </span>
      {resto.length > 0 && (
        <span
          className={tableTokens.cellSecondary}
          title={resto.map((s) => SINAL_LABELS[s] ?? s).join(" · ")}
        >
          +{resto.length}
        </span>
      )}
    </div>
  )
}

function SituacaoCell({ situacao }: { situacao: number | null }) {
  if (situacao === null) return <span className={tableTokens.cellMuted}>—</span>
  const label = SITUACAO_LABELS[situacao] ?? `Situação ${situacao}`
  // Baixado/Perda merecem o olho: título saiu da carteira fora do fluxo normal.
  const destaque = situacao === 3 || situacao === 9
  return (
    <span
      className={cx(
        tableTokens.badge,
        destaque ? tableTokens.badgeWarning : tableTokens.badgeNeutral,
      )}
    >
      {label}
    </span>
  )
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
  const [buscaCedente, setBuscaCedente] = React.useState("")
  const [buscaSacado, setBuscaSacado] = React.useState("")
  const [buscaDocumento, setBuscaDocumento] = React.useState("")
  const [cedenteDebounced, setCedenteDebounced] = React.useState("")
  const [sacadoDebounced, setSacadoDebounced] = React.useState("")
  const [documentoDebounced, setDocumentoDebounced] = React.useState("")
  const [segmento, setSegmento] = React.useState<Segmento>("todas")
  const [produto, setProduto] = React.useState<string>("todos")
  const [situacao, setSituacao] = React.useState<string>("todas")

  React.useEffect(() => {
    const t = setTimeout(() => setCedenteDebounced(buscaCedente), 350)
    return () => clearTimeout(t)
  }, [buscaCedente])
  React.useEffect(() => {
    const t = setTimeout(() => setSacadoDebounced(buscaSacado), 350)
    return () => clearTimeout(t)
  }, [buscaSacado])
  React.useEffect(() => {
    const t = setTimeout(() => setDocumentoDebounced(buscaDocumento), 350)
    return () => clearTimeout(t)
  }, [buscaDocumento])
  React.useEffect(() => {
    setPage(1)
  }, [cedenteDebounced, sacadoDebounced, documentoDebounced, segmento, produto, situacao])

  const filtros = React.useMemo(
    () => ({
      page,
      page_size: PAGE_SIZE,
      cedente: cedenteDebounced || undefined,
      sacado: sacadoDebounced || undefined,
      documento: documentoDebounced || undefined,
      produto_sigla: produto !== "todos" ? produto : undefined,
      situacao_titulo: situacao !== "todas" ? Number(situacao) : undefined,
      sugeridos: segmento === "sugeridas" || undefined,
      regra_dura: segmento === "regra_dura" || undefined,
      tag:
        segmento === "fraude"
          ? ("fraude" as const)
          : segmento === "sem_tag"
            ? ("sem_tag" as const)
            : undefined,
    }),
    [
      page,
      cedenteDebounced,
      sacadoDebounced,
      documentoDebounced,
      segmento,
      produto,
      situacao,
    ],
  )

  const listQuery = useCuradoriaLiquidacoes(filtros)
  const modelosQuery = useDeteccaoModelos()
  // Catálogo completo de produtos (nome por extenso) — não depende da página.
  const contratosQuery = useContratosLiquidacao(180)
  const tagMut = useTagLiquidacao()
  const treinarMut = useTreinarModelo()
  const pontuarMut = usePontuarAgora()

  const pageData = listQuery.data
  const rows = pageData?.rows ?? []
  const total = pageData?.total ?? 0
  const totalPaginas = Math.max(1, Math.ceil(total / PAGE_SIZE))

  const selected = React.useMemo(
    () =>
      selectedId ? (rows.find((r) => r.liquidacao_id === selectedId) ?? null) : null,
    [rows, selectedId],
  )
  // Memoria de calculo completa — buscada por demanda ao abrir o drawer.
  const memoriaQuery = useMemoriaLiquidacao(selectedId)
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
        `Scoring executado: ${r.scores_gravados.toLocaleString("pt-BR")} liquidações avaliadas, ${r.regra_dura} padrões críticos.`,
      )
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao pontuar.")
    }
  }, [pontuarMut])

  const produtos = React.useMemo(
    () =>
      (contratosQuery.data ?? [])
        .map((c) => [c.produto_sigla, c.produto_nome] as const)
        .sort((a, b) => a[1].localeCompare(b[1])),
    [contratosQuery.data],
  )

  const columns = React.useMemo<ColumnDef<LiquidacaoCuradoriaRow, unknown>[]>(
    () => [
      col.accessor("data_evento", {
        header: "Data",
        size: 88,
        cell: (info) => (
          <span className={tableTokens.cellSecondary}>
            {format(parseISO(info.getValue() as string), "dd/MM/yyyy")}
          </span>
        ),
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.accessor("titulo_numero", {
        header: "Documento",
        size: 100,
        cell: (info) => (
          <span className={tableTokens.cellTextMono}>
            {info.getValue() ?? info.row.original.titulo_id}
          </span>
        ),
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.accessor("cedente_nome", {
        header: "Cedente",
        size: 190,
        cell: (info) => {
          const nome = (info.getValue() as string | null) ?? "—"
          // Uma linha, corte limpo — nome completo no tooltip.
          return (
            <span
              className={cx(tableTokens.cellStrong, "block max-w-[180px] truncate")}
              title={nome}
            >
              {nome}
            </span>
          )
        },
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.accessor("sacado_nome", {
        header: "Sacado",
        size: 170,
        cell: (info) => {
          const nome = (info.getValue() as string | null) ?? "—"
          return (
            <span
              className={cx(tableTokens.cellText, "block max-w-[160px] truncate")}
              title={nome}
            >
              {nome}
            </span>
          )
        },
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.accessor("produto_nome", {
        header: "Produto",
        size: 130,
        cell: (info) => (
          <span className={tableTokens.cellText}>
            {info.getValue() ?? info.row.original.produto_sigla ?? "—"}
          </span>
        ),
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.accessor("valor", {
        header: "Valor",
        size: 105,
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
        id: "situacao",
        header: "Situação do título",
        size: 130,
        cell: ({ row }) => <SituacaoCell situacao={row.original.situacao_titulo} />,
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.display({
        id: "sinal",
        header: "Sinal",
        size: 160,
        cell: ({ row }) => <SinaisCell sinais={row.original.sinais} />,
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.display({
        id: "score",
        header: "Risco",
        size: 90,
        cell: ({ row }) => <ScoreBadge row={row.original} />,
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.display({
        id: "tag",
        header: "Marcação",
        size: 86,
        cell: ({ row }) => <TagBadge row={row.original} />,
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.display({
        id: "actions",
        header: "",
        size: 80,
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
        info="Todas as liquidações da carteira, com a conclusão do sistema (coluna Sinal), o risco estimado pelo modelo e as regras determinísticas. Marque fraude/OK: cada marcação é registrada com autor e data (nada se apaga) e realimenta o treino do modelo — IA opina, humano homologa."
        subtitle="Risco · Detecção de anomalias"
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="secondary"
              className="h-[30px] text-[13px]"
              isLoading={pontuarMut.isPending}
              onClick={() => void pontuar()}
              title="Aplica a versão ativa do modelo (ou só os padrões críticos determinísticos) agora"
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
              : "sem versão ativa — exibindo regras determinísticas e sinais declarados"}
            {modelo.versoes.length > 0 &&
              modelo.versoes[0] &&
              ` · última treinada: v${modelo.versoes[0].versao} (Gini OOT ${String(
                (modelo.versoes[0].metrics as Record<string, unknown>)?.gini_oot ?? "—",
              )})`}
          </span>
        </div>
      )}

      {/* Anatomia canônica: Card > filtros + segments + contador > tabela > rodapé */}
      <Card className="p-0">
        <div className="flex flex-wrap items-center gap-2 border-b border-gray-200 p-4 dark:border-gray-800">
          <FilterSearch
            value={buscaCedente}
            onChange={(e) => setBuscaCedente(e.target.value)}
            placeholder="Cedente (nome ou CNPJ)..."
            className="w-56"
          />
          <FilterSearch
            value={buscaSacado}
            onChange={(e) => setBuscaSacado(e.target.value)}
            placeholder="Sacado (nome ou CNPJ)..."
            className="w-56"
          />
          <FilterSearch
            value={buscaDocumento}
            onChange={(e) => setBuscaDocumento(e.target.value)}
            placeholder="Documento / nº do título..."
            className="w-48"
          />
          <Select value={produto} onValueChange={setProduto}>
            <SelectTrigger className={cx(filterControlClass, "w-52")}>
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
          <Select value={situacao} onValueChange={setSituacao}>
            <SelectTrigger className={cx(filterControlClass, "w-52")}>
              <SelectValue placeholder="Situação do título" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="todas">Todas as situações</SelectItem>
              {Object.entries(SITUACAO_LABELS)
                .filter(([v]) => v !== "0") // em aberto não gera evento de liquidação
                .map(([valor, label]) => (
                  <SelectItem key={valor} value={valor}>
                    {label}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
          <SegmentSwitch
            value={segmento}
            onChange={(v) => setSegmento(v as Segmento)}
            options={[
              { value: "todas", label: "Todas" },
              { value: "sugeridas", label: "Sugeridas" },
              { value: "regra_dura", label: "Padrão crítico" },
              { value: "fraude", label: "Fraude" },
              { value: "sem_tag", label: "Sem marcação" },
            ]}
          />
          <span className={cx(tableTokens.cellSecondary, "ml-auto tabular-nums")}>
            {rows.length.toLocaleString("pt-BR")} de {total.toLocaleString("pt-BR")}{" "}
            liquidações
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
      </Card>

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
            {/* Conclusões (sinais) no topo — o resumo do porquê */}
            {selected.sinais.length > 0 && (
              <div className="flex flex-wrap gap-1.5">
                {selected.sinais.map((s) => (
                  <span
                    key={s}
                    className={cx(
                      tableTokens.badge,
                      SINAIS_FORTES.has(s)
                        ? tableTokens.badgeWarning
                        : tableTokens.badgeNeutral,
                    )}
                  >
                    {SINAL_LABELS[s] ?? s}
                  </span>
                ))}
              </div>
            )}

            {selected.regra_dura && (
              <span className={cx(tableTokens.badge, tableTokens.badgeDanger, "w-fit")}>
                {selected.regra_dura_motivo ?? "Padrão crítico disparado"}
              </span>
            )}

            {/* Memória de cálculo — os DADOS que sustentam cada conclusão */}
            {memoriaQuery.isLoading && (
              <span className={tableTokens.cellMuted}>
                Montando a memória de cálculo…
              </span>
            )}
            {memoriaQuery.data?.secoes.map((secao) => (
              <div key={secao.titulo} className="flex flex-col gap-1.5">
                <span className={tableTokens.header}>{secao.titulo}</span>
                <ul className="flex flex-col gap-1">
                  {secao.itens.map((item, i) => (
                    <li
                      key={`${item.label}-${i}`}
                      className="flex items-baseline justify-between gap-4"
                    >
                      <span className={tableTokens.cellSecondary}>{item.label}</span>
                      <span
                        className={cx(
                          "text-right",
                          item.destaque
                            ? cx(tableTokens.cellStrong, "text-amber-700 dark:text-amber-400")
                            : tableTokens.cellText,
                        )}
                      >
                        {item.valor}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}

            {memoriaQuery.data?.fatores && memoriaQuery.data.fatores.length > 0 && (
              <div className="flex flex-col gap-2">
                <span className={tableTokens.header}>
                  Contribuições do modelo (
                  {Math.round((memoriaQuery.data.score ?? 0) * 100)}%)
                </span>
                <ul className="flex flex-col gap-1">
                  {memoriaQuery.data.fatores.map((f) => (
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
