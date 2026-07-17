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
// Anatomia: canônica das listagens CRUD via tableTokens.cardWrapper/filterBar/
// countLabel (Card p-4 + gap > filtros + contador > tabela > TablePagination
// sangrando ate as bordas), com a MECÂNICA server-side por trás.
// MOTIVO: DataTableShell é client-side (~200 rows) — aqui o universo é 93k;
// a anatomia usa os MESMOS tokens do Shell para nao divergir visualmente.
//

"use client"

import * as React from "react"
import { useRouter, useSearchParams } from "next/navigation"
import {
  RiAlarmWarningLine,
  RiCheckLine,
  RiEraserLine,
  RiErrorWarningLine,
  RiFlagLine,
  RiFlaskLine,
  RiSearchEyeLine,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"
import { format, parseISO } from "date-fns"
import { toast } from "sonner"

import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import {
  DataTable,
  FilterChip,
  FilterSearch,
  MultiCheckList,
  multiLabel,
  type MultiOption,
  PageHeader,
  TablePagination,
} from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type { LiquidacaoCuradoriaRow } from "@/lib/api-client"
import {
  useContratosLiquidacao,
  useCuradoriaLiquidacoes,
  useAtivarVersaoModelo,
  useDeteccaoModelos,
  usePontuarAgora,
  useTagLiquidacao,
  useTreinarModelo,
} from "@/lib/hooks/risco"
import { CuradoriaModal } from "@/components/risco/CuradoriaModal"
import { cx } from "@/lib/utils"

const PAGE_SIZE = 50

// Labels humanas das features (fatores de explicabilidade §14.3).
// Conclusões do sistema ("qual foi o bad") — códigos do backend em pt-BR.
const SINAL_LABELS: Record<string, string> = {
  // regra_dura por match de conta cadastrada do cedente (a agência É do cedente).
  regra_dura_conta: "Sacado de outra cidade pagou em agência do cedente",
  // regra_dura por agência multi-cidade compartilhada (NÃO é do cedente).
  regra_dura_multicidade: "Agência compartilhada por sacados de outras cidades",
  regra_dura: "Padrão crítico",
  baixa_confirmada: "Boleto baixado por instrução e liquidado por fora",
  agencia_conta_cedente: "Pago em agência onde o cedente mantém conta",
  agencia_compartilhada: "Agência compartilhada por vários sacados do cedente",
  agencia_multi_cedente: "Agência usada por vários cedentes (rede)",
  quebra_fingerprint: "Quebrou o padrão bancário do sacado",
  boleto_nao_esperado: "Boleto em produto onde não era esperado",
  lastro_inconsistente: "Lastro marcado inconsistente na verificação",
  fora_praca_sacado: "Pago fora da praça do sacado",
  sem_ocorrencia: "Bancarizado sem ocorrência de liquidação",
}
const SINAL_CURTO: Record<string, string> = {
  regra_dura_conta: "agência do cedente",
  regra_dura_multicidade: "compartilhada multi-cidade",
  regra_dura: "padrão crítico",
  baixa_confirmada: "baixa confirmada",
  agencia_conta_cedente: "conta do cedente",
  agencia_compartilhada: "agência compartilhada",
  agencia_multi_cedente: "multi-cedente",
  quebra_fingerprint: "quebra de padrão",
  boleto_nao_esperado: "boleto inesperado",
  lastro_inconsistente: "lastro inconsistente",
  fora_praca_sacado: "fora da praça",
  sem_ocorrencia: "sem ocorrência",
}
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

// ── Opcoes dos chips multi-select (vocabulario BI, §7.1) ─────────────────────
// Codigos = _SINAL_SQL/_MARCACAO_SQL/_RISCO_SQL do backend (curadoria_liquidacao.py).
const SITUACAO_OPTIONS: MultiOption[] = Object.entries(SITUACAO_LABELS)
  .filter(([v]) => v !== "0") // em aberto não gera evento de liquidação
  .map(([value, label]) => ({ value, label }))

const SINAL_OPTIONS: MultiOption[] = [
  { value: "regra_dura", label: "Padrão crítico" },
  { value: "baixa_confirmada", label: "Baixa confirmada" },
  { value: "agencia_conta_cedente", label: "Conta do cedente" },
  { value: "agencia_compartilhada", label: "Agência compartilhada" },
  { value: "agencia_multi_cedente", label: "Multi-cedente (rede)" },
  { value: "quebra_fingerprint", label: "Quebra de padrão" },
  { value: "boleto_nao_esperado", label: "Boleto inesperado" },
  { value: "lastro_inconsistente", label: "Lastro inconsistente" },
  { value: "sem_ocorrencia", label: "Sem ocorrência" },
]

const RISCO_OPTIONS: MultiOption[] = [
  { value: "padrao_critico", label: "Padrão crítico" },
  { value: "alto", label: "Alto (≥ 70%)" },
  { value: "medio", label: "Médio (40–70%)" },
  { value: "baixo", label: "Baixo (< 40%)" },
  { value: "sem_score", label: "Sem score" },
]

const MARCACAO_OPTIONS: MultiOption[] = [
  { value: "sugeridas", label: "Sugeridas pelo modelo" },
  { value: "padrao_critico", label: "Padrão crítico" },
  { value: "fraude", label: "Fraude" },
  { value: "ok", label: "OK" },
  { value: "sem_tag", label: "Sem marcação" },
]

// "Cor como sinal, não decoração" (handoff Liquidações 2026-07-09): pill
// vermelho tintado SÓ quando é alerta real; risco médio = amber; baixo =
// texto de apoio sem pill — o olho vai direto ao que importa.
function ScoreBadge({ row }: { row: LiquidacaoCuradoriaRow }) {
  if (row.regra_dura) {
    return (
      <span
        className={tableTokens.pillDanger}
        title={row.regra_dura_motivo ?? "Padrão inequívoco de auto-liquidação"}
      >
        <RiErrorWarningLine className="size-3" aria-hidden />
        Padrão crítico
      </span>
    )
  }
  if (row.score === null) {
    return <span className={tableTokens.cellMuted}>—</span>
  }
  const pct = Math.round(row.score * 100)
  if (row.score >= 0.7) {
    return (
      <span className={tableTokens.pillDanger}>
        <RiErrorWarningLine className="size-3" aria-hidden />
        {pct}%
      </span>
    )
  }
  if (row.score >= 0.4) {
    return <span className={tableTokens.pillWarning}>{pct}%</span>
  }
  return <span className={cx(tableTokens.cellSecondary, "tabular-nums")}>{pct}%</span>
}

// Sinal é informação, não alerta: texto neutro + contador "+N" (o vermelho
// fica reservado ao Risco/Marcação). Tooltip carrega a conclusão completa.
function SinaisCell({ sinais }: { sinais: string[] }) {
  if (sinais.length === 0) {
    return <span className={tableTokens.cellMuted}>—</span>
  }
  const [primeiro, ...resto] = sinais
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <span className={tableTokens.cellText} title={SINAL_LABELS[primeiro] ?? primeiro}>
        {SINAL_CURTO[primeiro] ?? primeiro}
      </span>
      {resto.length > 0 && (
        <span
          className={tableTokens.chipCount}
          title={resto.map((s) => SINAL_LABELS[s] ?? s).join(" · ")}
        >
          +{resto.length}
        </span>
      )}
    </span>
  )
}

// Status = dot + texto (sem pill): a cor do dot é o sinal. Verde = liquidação
// normal; amber = saiu da carteira fora do fluxo (baixado); vermelho = perda.
// Recomprado (5) / Recuperação (7) caem no default neutro — não são alerta.
const SITUACAO_DOT: Record<number, string> = {
  1: "bg-emerald-600", // Liquidação Normal
  2: "bg-emerald-600", // Liquidação em Cartório
  3: "bg-amber-500", // Baixado
  9: "bg-red-500", // Perda
}

function SituacaoCell({ situacao }: { situacao: number | null }) {
  if (situacao === null) return <span className={tableTokens.cellMuted}>—</span>
  const label = SITUACAO_LABELS[situacao] ?? `Situação ${situacao}`
  return (
    <span className="inline-flex items-center gap-1.5 whitespace-nowrap">
      <span
        className={cx("size-1.5 rounded-full", SITUACAO_DOT[situacao] ?? "bg-gray-300")}
        aria-hidden
      />
      <span className={tableTokens.cellText}>{label}</span>
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
      className={fraude ? tableTokens.pillDanger : tableTokens.pillSuccess}
      title={
        row.tag_autor
          ? `${row.tag_autor} · ${row.tag_em ? format(parseISO(row.tag_em), "dd/MM/yyyy HH:mm") : ""}`
          : undefined
      }
    >
      {fraude && <RiFlagLine className="size-3" aria-hidden />}
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
  // Deep-link: /risco/cedentes envia ?cedente=<nome> para abrir ja filtrado.
  const [buscaCedente, setBuscaCedente] = React.useState(() => sp.get("cedente") ?? "")
  const [buscaSacado, setBuscaSacado] = React.useState("")
  const [buscaDocumento, setBuscaDocumento] = React.useState("")
  const [cedenteDebounced, setCedenteDebounced] = React.useState(() => sp.get("cedente") ?? "")
  const [sacadoDebounced, setSacadoDebounced] = React.useState("")
  const [documentoDebounced, setDocumentoDebounced] = React.useState("")
  // Chips BI multi-select (vazio = todos): OR dentro do eixo, AND entre eixos.
  const [produtosSel, setProdutosSel] = React.useState<string[]>([])
  const [situacoesSel, setSituacoesSel] = React.useState<string[]>([])
  const [sinaisSel, setSinaisSel] = React.useState<string[]>([])
  const [riscosSel, setRiscosSel] = React.useState<string[]>([])
  const [marcacoesSel, setMarcacoesSel] = React.useState<string[]>([])

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
  }, [
    cedenteDebounced,
    sacadoDebounced,
    documentoDebounced,
    produtosSel,
    situacoesSel,
    sinaisSel,
    riscosSel,
    marcacoesSel,
  ])

  const filtros = React.useMemo(
    () => ({
      page,
      page_size: PAGE_SIZE,
      cedente: cedenteDebounced || undefined,
      sacado: sacadoDebounced || undefined,
      documento: documentoDebounced || undefined,
      produtos: produtosSel.length ? produtosSel : undefined,
      situacoes: situacoesSel.length ? situacoesSel.map(Number) : undefined,
      sinais: sinaisSel.length ? sinaisSel : undefined,
      riscos: riscosSel.length ? riscosSel : undefined,
      marcacoes: marcacoesSel.length ? marcacoesSel : undefined,
    }),
    [
      page,
      cedenteDebounced,
      sacadoDebounced,
      documentoDebounced,
      produtosSel,
      situacoesSel,
      sinaisSel,
      riscosSel,
      marcacoesSel,
    ],
  )

  const listQuery = useCuradoriaLiquidacoes(filtros)
  const modelosQuery = useDeteccaoModelos()
  // Catálogo completo de produtos (nome por extenso) — não depende da página.
  const contratosQuery = useContratosLiquidacao(180)
  const tagMut = useTagLiquidacao()
  const treinarMut = useTreinarModelo()
  const ativarMut = useAtivarVersaoModelo()
  const pontuarMut = usePontuarAgora()

  const pageData = listQuery.data
  const rows = pageData?.rows ?? []
  const total = pageData?.total ?? 0
  const totalPaginas = Math.max(1, Math.ceil(total / PAGE_SIZE))


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
    async (
      row: LiquidacaoCuradoriaRow,
      tag: "fraude" | "ok" | "neutro",
      notaTexto?: string,
    ) => {
      try {
        await tagMut.mutateAsync({
          liquidacaoId: row.liquidacao_id,
          tag,
          nota: notaTexto || null,
        })
        const doc = row.titulo_numero ?? row.titulo_id
        toast.success(
          tag === "fraude"
            ? `Liquidação do título ${doc} marcada como fraude.`
            : tag === "ok"
              ? `Liquidação do título ${doc} marcada como OK.`
              : `Marcação do título ${doc} removida (voltou a neutro).`,
        )
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Falha ao registrar a marcação.")
      }
    },
    [tagMut],
  )

  const modelo = modelosQuery.data?.find((m) => m.nome === "liquidacao_boleto")
  // Versões vêm em ordem desc do backend — [0] é a última treinada.
  const ultimaVersao = modelo?.versoes[0]

  const ativar = React.useCallback(
    async (versao: number) => {
      try {
        await ativarMut.mutateAsync({ nome: "liquidacao_boleto", versao })
        toast.success(
          `Versão v${versao} ativada. Rode "Pontuar agora" para reavaliar as liquidações com ela.`,
        )
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Falha ao ativar a versão.")
      }
    },
    [ativarMut],
  )

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

  const produtoOptions = React.useMemo<MultiOption[]>(
    () =>
      (contratosQuery.data ?? [])
        .map((c) => ({
          value: c.produto_sigla,
          label: `${c.produto_nome} (${c.produto_sigla})`,
        }))
        .sort((a, b) => a.label.localeCompare(b.label)),
    [contratosQuery.data],
  )

  // Só a linha em curso gira (não a tabela inteira): react-query mantém
  // `variables` durante o pending, então derivamos o alvo sem estado extra.
  const linhaEmCurso = tagMut.isPending ? tagMut.variables?.liquidacaoId : undefined

  const columns = React.useMemo<ColumnDef<LiquidacaoCuradoriaRow, unknown>[]>(
    () => [
      // ORDEM POR INTENÇÃO DE LEITURA (handoff Liquidações 2026-07-09):
      // identifica (Cedente·Sacado) → quantifica (Doc·Data·Produto·Valor)
      // → avalia (Situação·Sinal·Risco·Marcação, junto das ações).
      // LARGURAS: layout fixed — `size` e largura REAL (inclui px-3 da
      // cell); Cedente/Sacado NAO declaram size e dividem o restante em
      // partes IGUAIS. Acima de tableMinWidth a tabela nunca excede o
      // container (sem scroll-x); abaixo, rola horizontalmente (canonico).
      col.accessor("cedente_nome", {
        header: "Cedente",
        // SEM size: no layout fixed, Cedente e Sacado dividem o espaco
        // restante em partes IGUAIS (iguais por construcao). Nome completo
        // no tooltip; truncate acompanha a largura real da coluna.
        cell: (info) => {
          const nome = (info.getValue() as string | null) ?? "—"
          return (
            <span
              className={cx(tableTokens.cellStrong, "block truncate")}
              title={nome}
            >
              {nome}
            </span>
          )
        },
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.accessor("sacado_nome", {
        header: "Sacado",
        cell: (info) => {
          const nome = (info.getValue() as string | null) ?? "—"
          return (
            <span
              className={cx(tableTokens.cellText, "block truncate")}
              title={nome}
            >
              {nome}
            </span>
          )
        },
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.accessor("titulo_numero", {
        header: () => <span title="Documento do título">Doc.</span>,
        size: 92,
        cell: (info) => (
          <span className={tableTokens.cellTextMono}>
            {info.getValue() ?? info.row.original.titulo_id}
          </span>
        ),
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.accessor("data_evento", {
        header: "Data",
        size: 88,
        cell: (info) => (
          <span className={cx(tableTokens.cellSecondary, "tabular-nums")}>
            {format(parseISO(info.getValue() as string), "dd/MM/yyyy")}
          </span>
        ),
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.accessor("produto_nome", {
        header: "Produto",
        // 160px cobre o maior nome de produto atual sem truncar (regra:
        // nome completo). Se surgir produto maior, SUBA o size.
        size: 145,
        cell: (info) => (
          <span className={cx(tableTokens.cellText, "whitespace-nowrap")}>
            {info.getValue() ?? info.row.original.produto_sigla ?? "—"}
          </span>
        ),
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.accessor("valor", {
        header: () => (
          <span title="Valor efetivamente pago na liquidação (inclui encargos de mora) — não é o valor de face do título. Baixas sem pagamento mostram o valor de face.">
            Valor pago
          </span>
        ),
        size: 112,
        meta: { align: "right" },
        cell: (info) => {
          const v = info.getValue() as number | null
          return v !== null ? (
            <span
              className={cx(
                tableTokens.cellNumber,
                "block whitespace-nowrap text-right font-medium",
              )}
            >
              {v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}
            </span>
          ) : (
            <span className={cx(tableTokens.cellMuted, "block text-right")}>—</span>
          )
        },
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.display({
        id: "situacao",
        header: "Situação",
        size: 140,
        cell: ({ row }) => <SituacaoCell situacao={row.original.situacao_titulo} />,
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.display({
        id: "sinal",
        header: "Sinal",
        size: 158,
        cell: ({ row }) => <SinaisCell sinais={row.original.sinais} />,
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.display({
        id: "score",
        header: "Risco",
        // Cabe "Padrão crítico" em 1 linha (badge nowrap) + px-3 da cell.
        size: 112,
        cell: ({ row }) => <ScoreBadge row={row.original} />,
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.display({
        id: "tag",
        header: "Marcação",
        size: 92,
        cell: ({ row }) => <TagBadge row={row.original} />,
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
      col.display({
        id: "actions",
        header: "",
        size: 88,
        // Ações em repouso ficam apagadas (gray-300) e ganham a cor
        // semântica no hover — a linha lê limpa, a ação aparece ao mirar.
        cell: ({ row }) => (
          <div className="flex justify-end gap-1">
            <Button
              variant="ghost"
              className="size-7 p-0 text-gray-300 hover:text-red-600 dark:text-gray-600 dark:hover:text-red-400"
              aria-label="Marcar como fraude"
              title="Marcar como fraude"
              isLoading={linhaEmCurso === row.original.liquidacao_id}
              onClick={(e) => {
                e.stopPropagation()
                void marcar(row.original, "fraude")
              }}
            >
              <RiAlarmWarningLine className="size-4" aria-hidden />
            </Button>
            <Button
              variant="ghost"
              className="size-7 p-0 text-gray-300 hover:text-emerald-600 dark:text-gray-600 dark:hover:text-emerald-400"
              aria-label="Marcar como OK"
              title="Marcar como OK"
              isLoading={linhaEmCurso === row.original.liquidacao_id}
              onClick={(e) => {
                e.stopPropagation()
                void marcar(row.original, "ok")
              }}
            >
              <RiCheckLine className="size-4" aria-hidden />
            </Button>
            {/* Limpar (volta a neutro) — so quando ha marcacao vigente */}
            {row.original.tag_vigente && (
              <Button
                variant="ghost"
                className="size-7 p-0 text-gray-300 hover:text-gray-900 dark:text-gray-600 dark:hover:text-gray-100"
                aria-label="Remover marcação"
                title="Remover marcação (voltar a neutro)"
                isLoading={linhaEmCurso === row.original.liquidacao_id}
                onClick={(e) => {
                  e.stopPropagation()
                  void marcar(row.original, "neutro")
                }}
              >
                <RiEraserLine className="size-4" aria-hidden />
              </Button>
            )}
          </div>
        ),
      }) as ColumnDef<LiquidacaoCuradoriaRow, unknown>,
    ],
    [marcar, linhaEmCurso],
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

      {/* Faixa do modelo: versão ativa + métrica + ativar — estado (§7.3) */}
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
          {/* Ativar a última versão treinada quando ela ainda não é a ativa */}
          {ultimaVersao && ultimaVersao.versao !== modelo.versao_ativa && (
            <Button
              variant="secondary"
              className="ml-auto h-[26px] text-[12px]"
              isLoading={ativarMut.isPending}
              onClick={() => void ativar(ultimaVersao.versao)}
              title="Torna esta versão a que pontua as liquidações (rollback: reative uma versão anterior)"
            >
              Ativar v{ultimaVersao.versao}
            </Button>
          )}
        </div>
      )}

      {/* Anatomia canônica do Shell (tableTokens.cardWrapper): Card p-4 +
          gap-3, tabela DENTRO do respiro — toolbar SEM divisória própria
          (a hairline do header da tabela separa). Igual aos CRUDs. */}
      <Card className={tableTokens.cardWrapper}>
        <div className={tableTokens.filterBar}>
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
          {/* Chips multi-select — vocabulario canonico do BI (§7.1):
              FilterChip + multiLabel + MultiCheckList. OR dentro do eixo,
              AND entre eixos; filtragem SERVER-SIDE via params repetidos. */}
          <FilterChip
            label="Produto"
            value={multiLabel(produtosSel, produtoOptions)}
            active={produtosSel.length > 0}
          >
            <MultiCheckList
              options={produtoOptions}
              selected={produtosSel}
              onChange={setProdutosSel}
              searchable
              searchPlaceholder="Buscar produto…"
            />
          </FilterChip>
          <FilterChip
            label="Situação"
            value={multiLabel(situacoesSel, SITUACAO_OPTIONS, "Todas")}
            active={situacoesSel.length > 0}
          >
            <MultiCheckList
              options={SITUACAO_OPTIONS}
              selected={situacoesSel}
              onChange={setSituacoesSel}
            />
          </FilterChip>
          <FilterChip
            label="Sinal"
            value={multiLabel(sinaisSel, SINAL_OPTIONS)}
            active={sinaisSel.length > 0}
          >
            <MultiCheckList
              options={SINAL_OPTIONS}
              selected={sinaisSel}
              onChange={setSinaisSel}
            />
          </FilterChip>
          <FilterChip
            label="Risco"
            value={multiLabel(riscosSel, RISCO_OPTIONS)}
            active={riscosSel.length > 0}
          >
            <MultiCheckList
              options={RISCO_OPTIONS}
              selected={riscosSel}
              onChange={setRiscosSel}
            />
          </FilterChip>
          <FilterChip
            label="Marcação"
            value={multiLabel(marcacoesSel, MARCACAO_OPTIONS, "Todas")}
            active={marcacoesSel.length > 0}
          >
            <MultiCheckList
              options={MARCACAO_OPTIONS}
              selected={marcacoesSel}
              onChange={setMarcacoesSel}
            />
          </FilterChip>
          <span className={tableTokens.countLabel} aria-live="polite">
            {rows.length.toLocaleString("pt-BR")} de {total.toLocaleString("pt-BR")}{" "}
            liquidações
          </span>
        </div>

        <DataTable<LiquidacaoCuradoriaRow>
          data={rows}
          columns={columns}
          tableLayout="fixed"
          tableMinWidth={1320}
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
        />

        {/* Pager no local canonico: rodape do Card, FORA da <table>. Sangra
            ate as bordas (-mx-4 -mb-2) para a divisória atravessar o card
            (handoff: "o rodapé sangra até as bordas"). */}
        <TablePagination
          className="-mx-4 -mb-2"
          page={page}
          totalPages={totalPaginas}
          onPageChange={setPage}
          disabled={listQuery.isFetching}
          info={
            <>
              {total === 0
                ? "0 de 0"
                : `${((page - 1) * PAGE_SIZE + 1).toLocaleString("pt-BR")}–${Math.min(
                    page * PAGE_SIZE,
                    total,
                  ).toLocaleString("pt-BR")} de ${total.toLocaleString("pt-BR")}`}
              {listQuery.isFetching && " · atualizando…"}
            </>
          }
        />
      </Card>

      {/* Drawer: evidência completa + marcação com nota */}
      <CuradoriaModal
        liquidacaoId={selectedId}
        onClose={() => setSelected(null)}
      />
    </div>
  )
}
