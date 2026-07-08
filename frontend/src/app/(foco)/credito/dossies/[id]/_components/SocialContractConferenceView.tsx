// SocialContractConferenceView — ficha de conferência por seções do CONTRATO
// SOCIAL (Opção A da conferência guiada, 2026-06-11).
//
// Substitui a FichaConferenceZone genérica PARA doc_type=social_contract: a
// extração tipada (ContratoSocialExtraction) tem seções, tabelas e citações —
// a comparação plana "IA propôs × No dossiê" fica pequena pra ela.
//
// Anatomia:
//   header   — identificação do instrumento (documento_meta) + confiança +
//              progresso de conferência (x/y seções)
//   esquerda — seções em ordem fixa de auditoria, cada uma com DataTable
//              (density ultra) ou grid de propriedades + citações (⌕ abre
//              HoverCard com o trecho_literal) + voz do agente (violeta)
//   direita  — OriginPanel (PDF real) — a citação aponta, o painel mostra
//
// Fatos vêm do payload determinístico (GET /societario) — a MESMA fonte da
// read-tool do agente e do check (§14: um fato, três consumidores). O
// "Conferido" por seção é progresso LOCAL da tela (fase 1); a homologação
// continua sendo do documento inteiro, no fluxo existente.

"use client"

import * as React from "react"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import * as HoverCardPrimitives from "@radix-ui/react-hover-card"
import {
  RiArrowDownSLine,
  RiArrowRightSLine,
  RiCheckboxCircleFill,
  RiCheckboxCircleLine,
  RiCheckLine,
  RiCloseLine,
  RiDoubleQuotesL,
  RiErrorWarningLine,
  RiSparklingLine,
} from "@remixicon/react"
import { type ColumnDef, createColumnHelper } from "@tanstack/react-table"

import { DataTable } from "@/design-system/components/DataTable"
import { tableTokens } from "@/design-system/tokens/table"
import {
  credito,
  type CreditDocumentRead,
  type SocialContractAnalysis,
  type SocietarioAdministrador,
  type SocietarioPoder,
  type SocietarioPontoAtencao,
  type SocietarioRestricao,
  type SocietarioSocio,
} from "@/lib/credito-client"
import { cx } from "@/lib/utils"

import { toast } from "sonner"

import { Button } from "@/components/tremor/Button"

import { extractedFieldsOf, OriginPanel } from "./DocumentZones"

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })
const num = new Intl.NumberFormat("pt-BR")

function fmtBRL(v: unknown): string {
  const n = Number(v)
  return Number.isFinite(n) ? brl.format(n) : "—"
}

function fmtNum(v: unknown): string {
  const n = Number(v)
  return Number.isFinite(n) ? num.format(n) : "—"
}

const DOC_TIPO_LABEL: Record<string, string> = {
  constituicao: "Constituição",
  alteracao: "Alteração contratual",
  consolidacao: "Consolidação",
  alteracao_com_consolidacao: "Alteração c/ consolidação",
  estatuto_social: "Estatuto social",
  outro: "Instrumento societário",
}

const TEMA_LABEL: Record<string, string> = {
  aval_fianca_garantias: "Aval, fiança e garantias",
  cessao_creditos: "Cessão de créditos/recebíveis",
  alienacao_bens: "Alienação de bens",
  emprestimos_endividamento: "Empréstimos e endividamento",
  alcadas_valor: "Alçadas de valor",
  quorum_qualificado: "Quórum qualificado",
  cessao_quotas: "Cessão de quotas",
  outras: "Outras restrições",
}

// Badge COMPLETO por status (tableTokens.badge*) — usar direto no className.
const STATUS_TONE: Record<string, string> = {
  vedado: tableTokens.badgeDanger,
  condicionado: tableTokens.badgeWarning,
  permitido_expressamente: tableTokens.badgeSuccess,
  sem_clausula: tableTokens.badgeNeutral,
}

const STATUS_LABEL: Record<string, string> = {
  vedado: "Vedado",
  condicionado: "Condicionado",
  permitido_expressamente: "Permitido",
  sem_clausula: "Sem cláusula",
}

// ─── Citação (⌕ → HoverCard com o trecho literal) ───────────────────────────

function CitBadge({
  trecho,
  referencia,
  onFocus,
}: {
  trecho?: string | null
  referencia?: string | null
  onFocus?: () => void
}) {
  if (!trecho && !referencia) return <span className={tableTokens.cellMuted}>—</span>
  return (
    <HoverCardPrimitives.Root openDelay={150} closeDelay={100}>
      <HoverCardPrimitives.Trigger asChild>
        <button
          type="button"
          onClick={onFocus}
          className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium text-blue-600 hover:bg-blue-50 dark:text-blue-400 dark:hover:bg-blue-500/10"
          title="Ver citação do documento"
        >
          <RiDoubleQuotesL className="size-3" aria-hidden />
          {referencia ? referencia.slice(0, 18) : "citação"}
        </button>
      </HoverCardPrimitives.Trigger>
      <HoverCardPrimitives.Portal>
        <HoverCardPrimitives.Content
          side="left"
          align="start"
          sideOffset={6}
          className="z-50 w-80 rounded-md border border-gray-200 bg-white p-3 shadow-lg dark:border-gray-800 dark:bg-gray-950"
        >
          {trecho && (
            <p className="border-l-2 pl-2 text-xs italic leading-relaxed text-gray-700 dark:text-gray-300" style={{ borderColor: "#059669" }}>
              “{trecho}”
            </p>
          )}
          {referencia && (
            <p className={cx(tableTokens.cellSecondary, "mt-1.5")}>{referencia}</p>
          )}
          <p className="mt-1.5 text-[10px] text-gray-400 dark:text-gray-500">
            citação literal do documento — confira no painel ao lado
          </p>
        </HoverCardPrimitives.Content>
      </HoverCardPrimitives.Portal>
    </HoverCardPrimitives.Root>
  )
}

// ─── Voz do agente (violeta, por seção) ──────────────────────────────────────

function AgentNote({ children }: { children: React.ReactNode }) {
  return (
    <div className="flex items-start gap-2 rounded-md border border-violet-200/70 bg-violet-50/60 px-3 py-2 dark:border-violet-500/20 dark:bg-violet-500/10">
      <RiSparklingLine
        className="mt-0.5 size-3.5 shrink-0 text-violet-600 dark:text-violet-400"
        aria-hidden
      />
      <p className="text-xs leading-relaxed text-violet-900 dark:text-violet-200">
        {children}
      </p>
    </div>
  )
}

// ─── Seção colapsável com "Conferido" ────────────────────────────────────────

function Section({
  id,
  title,
  badge,
  checked,
  onToggleChecked,
  children,
}: {
  id: string
  title: string
  badge?: React.ReactNode
  checked: boolean
  onToggleChecked: () => void
  children: React.ReactNode
}) {
  const [open, setOpen] = React.useState(true)
  return (
    <section className="border-b border-gray-100 last:border-0 dark:border-gray-900">
      <div className="flex items-center gap-2 py-2">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
          aria-expanded={open}
          aria-controls={`sc-section-${id}`}
        >
          {open ? (
            <RiArrowDownSLine className="size-4 shrink-0 text-gray-400" aria-hidden />
          ) : (
            <RiArrowRightSLine className="size-4 shrink-0 text-gray-400" aria-hidden />
          )}
          <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-gray-600 dark:text-gray-300">
            {title}
          </span>
          {badge}
        </button>
        <button
          type="button"
          onClick={onToggleChecked}
          className={cx(
            "inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium",
            checked
              ? "text-emerald-700 dark:text-emerald-300"
              : "text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300",
          )}
          title={checked ? "Marcar como não conferida" : "Marcar seção como conferida"}
        >
          {checked ? (
            <RiCheckboxCircleFill className="size-3.5" aria-hidden />
          ) : (
            <RiCheckboxCircleLine className="size-3.5" aria-hidden />
          )}
          {checked ? "Conferido" : "Conferir"}
        </button>
      </div>
      {open && (
        <div id={`sc-section-${id}`} className="space-y-2 pb-3">
          {children}
        </div>
      )}
    </section>
  )
}

function Prop({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <p className={cx(tableTokens.header, "mb-0.5")}>{label}</p>
      <div className="truncate text-xs font-medium text-gray-900 dark:text-gray-100">
        {value ?? "—"}
      </div>
    </div>
  )
}

// ─── Colunas das DataTables ──────────────────────────────────────────────────

type CitFocus = (label: string) => void

function socioColumns(onFocus: CitFocus): ColumnDef<SocietarioSocio, unknown>[] {
  const col = createColumnHelper<SocietarioSocio>()
  void onFocus
  return [
    col.accessor("nome", {
      header: "Sócio",
      size: 220,
      cell: (i) => <span className={tableTokens.cellText}>{i.getValue()}</span>,
    }),
    col.accessor((r) => r.tipo ?? null, {
      id: "tipo",
      header: "Tipo",
      size: 60,
      cell: (i) => (
        <span className={tableTokens.cellSecondary}>
          {i.getValue() ? String(i.getValue()).toUpperCase() : "—"}
        </span>
      ),
    }),
    col.accessor((r) => r.cpf_ultimos4 ?? null, {
      id: "doc",
      header: "CPF/CNPJ",
      size: 110,
      cell: (i) => (
        <span className={tableTokens.cellTextMono}>
          {i.getValue() ? `***${String(i.getValue())}` : "—"}
        </span>
      ),
    }),
    col.accessor((r) => r.quotas ?? null, {
      id: "quotas",
      header: "Quotas",
      size: 100,
      cell: (i) => (
        <span className={cx(tableTokens.cellNumber, "block text-right")}>
          {fmtNum(i.getValue())}
        </span>
      ),
    }),
    col.accessor((r) => r.capital_subscrito_socio ?? null, {
      id: "capital",
      header: "Capital",
      size: 120,
      cell: (i) => (
        <span className={cx(tableTokens.cellNumber, "block text-right")}>
          {i.getValue() != null ? fmtBRL(i.getValue()) : "—"}
        </span>
      ),
    }),
    col.accessor((r) => r.participacao_pct ?? null, {
      id: "pct",
      header: "% (calc)",
      size: 80,
      cell: (i) => (
        <span className={cx(tableTokens.cellNumber, "block text-right")}>
          {i.getValue() != null ? `${i.getValue()}%` : "—"}
        </span>
      ),
    }),
  ] as ColumnDef<SocietarioSocio, unknown>[]
}

function adminColumns(onFocus: CitFocus): ColumnDef<SocietarioAdministrador, unknown>[] {
  const col = createColumnHelper<SocietarioAdministrador>()
  return [
    col.accessor("nome", {
      header: "Administrador",
      size: 200,
      cell: (i) => <span className={tableTokens.cellText}>{i.getValue()}</span>,
    }),
    col.accessor((r) => r.socio ?? null, {
      id: "socio",
      header: "Sócio?",
      size: 70,
      cell: (i) =>
        i.getValue() == null ? (
          <span className={tableTokens.cellMuted}>—</span>
        ) : i.getValue() ? (
          <span className={tableTokens.cellSecondary}>sim</span>
        ) : (
          <span className={tableTokens.cellSecondary}>não</span>
        ),
    }),
    col.accessor((r) => r.forma_atuacao_descricao || r.forma_atuacao || null, {
      id: "forma",
      header: "Forma de atuação",
      size: 200,
      cell: (i) => (
        <span className={tableTokens.cellSecondary}>{String(i.getValue() ?? "—")}</span>
      ),
    }),
    col.accessor((r) => r.mandato ?? null, {
      id: "mandato",
      header: "Mandato",
      size: 110,
      cell: (i) => (
        <span className={tableTokens.cellSecondary}>{String(i.getValue() ?? "—")}</span>
      ),
    }),
    col.display({
      id: "cit",
      header: "Citação",
      size: 110,
      cell: ({ row }) => (
        <CitBadge
          trecho={row.original.trecho_literal}
          referencia={row.original.referencia}
          onFocus={() => onFocus(`Administrador: ${row.original.nome}`)}
        />
      ),
    }),
  ] as ColumnDef<SocietarioAdministrador, unknown>[]
}

function poderColumns(onFocus: CitFocus): ColumnDef<SocietarioPoder, unknown>[] {
  const col = createColumnHelper<SocietarioPoder>()
  return [
    col.accessor((r) => r.quem ?? null, {
      id: "quem",
      header: "Quem",
      size: 160,
      cell: (i) => <span className={tableTokens.cellText}>{String(i.getValue() ?? "—")}</span>,
    }),
    col.accessor((r) => r.forma ?? null, {
      id: "forma",
      header: "Forma",
      size: 120,
      cell: (i) => (
        <span className={tableTokens.cellSecondary}>{String(i.getValue() ?? "—")}</span>
      ),
    }),
    col.accessor((r) => r.descricao ?? null, {
      id: "descricao",
      header: "Condições",
      size: 240,
      cell: (i) => (
        <span className={cx(tableTokens.cellSecondary, "line-clamp-2")}>
          {String(i.getValue() ?? "—")}
        </span>
      ),
    }),
    col.accessor((r) => r.limites_valor ?? null, {
      id: "limites",
      header: "Alçada",
      size: 130,
      cell: (i) => (
        <span className={cx(tableTokens.cellStrong)}>{String(i.getValue() ?? "—")}</span>
      ),
    }),
    col.display({
      id: "cit",
      header: "Citação",
      size: 110,
      cell: ({ row }) => (
        <CitBadge
          trecho={row.original.trecho_literal}
          referencia={row.original.referencia}
          onFocus={() => onFocus(`Poder de assinatura: ${row.original.quem ?? ""}`)}
        />
      ),
    }),
  ] as ColumnDef<SocietarioPoder, unknown>[]
}

function restricaoColumns(onFocus: CitFocus): ColumnDef<SocietarioRestricao, unknown>[] {
  const col = createColumnHelper<SocietarioRestricao>()
  return [
    col.accessor((r) => TEMA_LABEL[r.tema ?? ""] ?? (r.tema || "—"), {
      id: "tema",
      header: "Tema",
      size: 200,
      cell: (i) => <span className={tableTokens.cellText}>{String(i.getValue())}</span>,
    }),
    col.accessor((r) => r.status ?? null, {
      id: "status",
      header: "Status",
      size: 110,
      cell: (i) => {
        const s = String(i.getValue() ?? "")
        return (
          <span className={STATUS_TONE[s] ?? STATUS_TONE.sem_clausula}>
            {STATUS_LABEL[s] ?? (s || "—")}
          </span>
        )
      },
    }),
    col.accessor((r) => r.condicao || r.resumo || null, {
      id: "condicao",
      header: "Condição / resumo",
      size: 280,
      cell: (i) => (
        <span className={cx(tableTokens.cellSecondary, "line-clamp-2")}>
          {String(i.getValue() ?? "—")}
        </span>
      ),
    }),
    col.display({
      id: "cit",
      header: "Citação",
      size: 110,
      cell: ({ row }) =>
        row.original.status === "sem_clausula" ? (
          <span className={tableTokens.cellMuted}>—</span>
        ) : (
          <CitBadge
            trecho={row.original.trecho_literal}
            referencia={row.original.referencia}
            onFocus={() =>
              onFocus(`Restrição: ${TEMA_LABEL[row.original.tema ?? ""] ?? row.original.tema}`)
            }
          />
        ),
    }),
  ] as ColumnDef<SocietarioRestricao, unknown>[]
}

// ─── View ────────────────────────────────────────────────────────────────────

const SECTION_IDS = [
  "identificacao",
  "capital",
  "qsa",
  "administracao",
  "poderes",
  "restricoes",
  "atencao",
  "cruzamentos",
] as const

export function SocialContractConferenceView({
  dossierId,
  doc,
  analysis,
}: {
  dossierId: string
  doc: CreditDocumentRead
  /** Julgamento do social_contract_analyst (quando já rodou) — vira a voz
   *  violeta por seção. */
  analysis?: SocialContractAnalysis | null
}) {
  const { data } = useQuery({
    queryKey: ["credito", "societario", dossierId],
    queryFn: () => credito.dossies.societario(dossierId),
  })

  const [checked, setChecked] = React.useState<Set<string>>(new Set())
  const [focusLabel, setFocusLabel] = React.useState<string | null>(null)
  const queryClient = useQueryClient()

  // HOMOLOGAR = PATCH extraction (status validated) — materializa o QSA no
  // dossiê E retoma o run quando a estação é o gate da busca oficial
  // (official_document_fetch pausado aguardando homologação, 2026-06-12).
  const homologarMut = useMutation({
    mutationFn: () =>
      credito.documents.updateExtraction(dossierId, doc.id, {
        extracted_fields: (extractedFieldsOf(doc) ?? {}) as Record<string, unknown>,
      }),
    onSuccess: () => {
      toast.success("Conferência homologada — o fluxo segue pra análise.")
      queryClient.invalidateQueries({ queryKey: ["credito"] })
    },
    onError: (e) =>
      toast.error(`Erro ao homologar: ${(e as Error).message}`),
  })

  const toggle = (id: string) =>
    setChecked((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })

  if (!data?.encontrado || !data.contrato) return null

  const c = data.contrato
  const e = data.estrutura
  const meta = data.documento_meta
  const cap = c.capital_social_detalhe
  const restricoes = c.restricoes_estatutarias ?? []
  const pontos = c.pontos_de_atencao ?? []
  const poderes = c.poderes_assinatura ?? []
  const admins = c.administradores ?? []

  const visibleSections = SECTION_IDS.filter((id) => {
    if (id === "administracao") return admins.length > 0
    if (id === "poderes") return poderes.length > 0
    if (id === "restricoes") return restricoes.length > 0
    if (id === "atencao") return pontos.length > 0
    if (id === "cruzamentos") return (data.cruzamentos ?? []).length > 0
    return true
  })
  const done = visibleSections.filter((id) => checked.has(id)).length

  const tipoLabel = DOC_TIPO_LABEL[meta?.tipo ?? ""] ?? "Contrato social"
  const restricoesAtivas = restricoes.filter((r) => r.status && r.status !== "sem_clausula")

  return (
    <section className="overflow-hidden rounded border border-gray-200 bg-white shadow-xs dark:border-gray-800 dark:bg-gray-950">
      {/* Header — identificação do instrumento + progresso */}
      <header className="flex flex-wrap items-center gap-x-3 gap-y-1 border-b border-gray-100 px-5 py-3 dark:border-gray-900">
        <span className="text-[11px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
          Conferência do contrato social
        </span>
        <span className={tableTokens.cellSecondary}>
          {tipoLabel}
          {meta?.numero_alteracao != null && ` · ${meta.numero_alteracao}ª alteração`}
          {meta?.registro_junta?.nire && ` · NIRE ${meta.registro_junta.nire}`}
        </span>
        {data.fonte?.confianca != null && (
          <span className={tableTokens.cellSecondary}>
            confiança {Math.round(data.fonte.confianca * 100)}%
          </span>
        )}
        <span className="ml-auto text-xs tabular-nums">
          <strong
            className="font-semibold"
            style={{ color: done === visibleSections.length ? "#059669" : undefined }}
          >
            {done}/{visibleSections.length}
          </strong>{" "}
          <span className="text-gray-500 dark:text-gray-400">seções conferidas</span>
        </span>
        {data.homologado ? (
          <span className={cx(tableTokens.badge, STATUS_TONE.permitido_expressamente)}>
            homologada
          </span>
        ) : (
          <Button
            className="h-7"
            onClick={() => homologarMut.mutate()}
            isLoading={homologarMut.isPending}
            title="Confirma que você conferiu a extração contra o documento — vira a verdade do dossiê e libera o fluxo pra análise."
          >
            Homologar conferência
          </Button>
        )}
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-[1fr_380px]">
        <div className="border-gray-100 px-5 lg:border-r dark:border-gray-900">
          {/* 1 · Identificação */}
          <Section
            id="identificacao"
            title="Identificação"
            checked={checked.has("identificacao")}
            onToggleChecked={() => toggle("identificacao")}
          >
            <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
              <Prop label="CNPJ" value={c.cnpj} />
              <Prop label="Razão social" value={c.razao_social} />
              <Prop
                label="Tipo societário"
                value={c.tipo_societario ? c.tipo_societario.toUpperCase() : null}
              />
              <Prop label="Constituição" value={c.data_constituicao} />
              <Prop label="Última alteração" value={c.data_ultima_alteracao} />
              <Prop
                label="Idade da empresa"
                value={e?.idade_empresa_anos != null ? `${e.idade_empresa_anos} anos` : null}
              />
              <Prop label="Endereço" value={c.endereco} />
            </div>
            {c.objeto_social && (
              <p className={cx(tableTokens.cellSecondary, "line-clamp-3")}>
                <strong className="font-medium text-gray-700 dark:text-gray-300">
                  Objeto social:
                </strong>{" "}
                {c.objeto_social}
              </p>
            )}
            {analysis && (
              <AgentNote>
                Objeto × operação:{" "}
                {analysis.object_compatible_with_operation ? "compatível" : "incompatível"} —{" "}
                {analysis.object_compatibility_rationale}
              </AgentNote>
            )}
          </Section>

          {/* 2 · Capital social */}
          <Section
            id="capital"
            title="Capital social"
            checked={checked.has("capital")}
            onToggleChecked={() => toggle("capital")}
            badge={
              cap?.trecho_literal ? (
                <CitBadge
                  trecho={cap.trecho_literal}
                  referencia={null}
                  onFocus={() => setFocusLabel("Capital social")}
                />
              ) : undefined
            }
          >
            <div className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
              <Prop label="Subscrito" value={fmtBRL(c.capital_social)} />
              <Prop
                label="Integralizado"
                value={cap?.integralizado != null ? fmtBRL(cap.integralizado) : null}
              />
              <Prop label="Forma" value={cap?.forma_integralizacao} />
              <Prop
                label="Total de quotas"
                value={cap?.total_quotas != null ? fmtNum(cap.total_quotas) : null}
              />
            </div>
            {(cap?.parcelas_integralizacao?.length ?? 0) > 0 && (
              <p className={tableTokens.cellSecondary}>
                Integralização em {cap?.parcelas_integralizacao?.length} parcela(s):{" "}
                {cap?.parcelas_integralizacao
                  ?.map((p) => `${fmtBRL(p.valor)} (${p.prazo ?? "prazo n/d"})`)
                  .join(" · ")}
              </p>
            )}
          </Section>

          {/* 3 · Quadro societário */}
          <Section
            id="qsa"
            title="Quadro societário"
            checked={checked.has("qsa")}
            onToggleChecked={() => toggle("qsa")}
          >
            <DataTable<SocietarioSocio>
              data={c.socios ?? []}
              columns={socioColumns(setFocusLabel)}
              density="ultra"
              showDensityToggle={false}
              showColumnManager={false}
              showExport={false}
            />
            {e && (
              <div className="flex flex-wrap gap-x-5 gap-y-1 text-xs">
                <span
                  className={cx(
                    "flex items-center gap-1",
                    e.soma_confere === false
                      ? "text-amber-700 dark:text-amber-300"
                      : "text-gray-600 dark:text-gray-400",
                  )}
                >
                  {e.soma_confere === false ? (
                    <RiErrorWarningLine className="size-3.5" aria-hidden />
                  ) : (
                    <RiCheckLine className="size-3.5 text-emerald-600" aria-hidden />
                  )}
                  participações somam {e.soma_participacoes_pct ?? "—"}% (calculado pelo
                  sistema)
                </span>
                {e.controlador && (
                  <span className="text-gray-600 dark:text-gray-400">
                    controle:{" "}
                    <strong className="font-medium">{e.controlador.nome}</strong> (
                    {e.controlador.participacao_pct}%
                    {e.controlador.controle_majoritario ? " · majoritário" : ""})
                  </span>
                )}
              </div>
            )}
            {analysis?.qsa_changes_detail && (
              <AgentNote>{analysis.qsa_changes_detail}</AgentNote>
            )}
          </Section>

          {/* 4 · Administração */}
          {admins.length > 0 && (
            <Section
              id="administracao"
              title="Administração"
              checked={checked.has("administracao")}
              onToggleChecked={() => toggle("administracao")}
            >
              <DataTable<SocietarioAdministrador>
                data={admins}
                columns={adminColumns(setFocusLabel)}
                density="ultra"
              showDensityToggle={false}
              showColumnManager={false}
              showExport={false}
              />
            </Section>
          )}

          {/* 5 · Poderes de assinatura */}
          {poderes.length > 0 && (
            <Section
              id="poderes"
              title="Poderes de assinatura"
              checked={checked.has("poderes")}
              onToggleChecked={() => toggle("poderes")}
            >
              <DataTable<SocietarioPoder>
                data={poderes}
                columns={poderColumns(setFocusLabel)}
                density="ultra"
              showDensityToggle={false}
              showColumnManager={false}
              showExport={false}
              />
            </Section>
          )}

          {/* 6 · Restrições estatutárias */}
          {restricoes.length > 0 && (
            <Section
              id="restricoes"
              title="Restrições estatutárias"
              checked={checked.has("restricoes")}
              onToggleChecked={() => toggle("restricoes")}
              badge={
                <span className={cx(tableTokens.badge, STATUS_TONE.condicionado)}>
                  {restricoesAtivas.length} com cláusula
                </span>
              }
            >
              <DataTable<SocietarioRestricao>
                data={restricoes}
                columns={restricaoColumns(setFocusLabel)}
                density="ultra"
              showDensityToggle={false}
              showColumnManager={false}
              showExport={false}
              />
              <p className="text-[11px] italic text-gray-400 dark:text-gray-500">
                os 8 temas são varridos sempre — &quot;sem cláusula&quot; é resultado
                informado, não omissão
              </p>
            </Section>
          )}

          {/* 7 · Pontos de atenção */}
          {pontos.length > 0 && (
            <Section
              id="atencao"
              title="Pontos de atenção"
              checked={checked.has("atencao")}
              onToggleChecked={() => toggle("atencao")}
              badge={
                <span className={cx(tableTokens.badge, STATUS_TONE.vedado)}>
                  {pontos.length}
                </span>
              }
            >
              {pontos.map((p: SocietarioPontoAtencao, i: number) => (
                <div
                  key={i}
                  className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50/70 px-3 py-2 dark:border-amber-500/30 dark:bg-amber-500/10"
                >
                  <RiErrorWarningLine
                    className="mt-0.5 size-3.5 shrink-0 text-amber-600 dark:text-amber-400"
                    aria-hidden
                  />
                  <div className="min-w-0">
                    <p className="text-xs font-semibold text-amber-900 dark:text-amber-200">
                      {p.titulo ?? "Ponto de atenção"}
                    </p>
                    {p.descricao && (
                      <p className="text-xs text-amber-800 dark:text-amber-300">
                        {p.descricao}
                      </p>
                    )}
                  </div>
                  <span className="ml-auto shrink-0">
                    <CitBadge
                      trecho={p.trecho_literal}
                      referencia={p.referencia}
                      onFocus={() => setFocusLabel(p.titulo ?? "Ponto de atenção")}
                    />
                  </span>
                </div>
              ))}
            </Section>
          )}

          {/* 8 · Cruzamentos com registros oficiais */}
          {(data.cruzamentos ?? []).length > 0 && (
            <Section
              id="cruzamentos"
              title="Cruzamentos com registros oficiais"
              checked={checked.has("cruzamentos")}
              onToggleChecked={() => toggle("cruzamentos")}
            >
              {(data.cruzamentos ?? []).map((cz, i) => (
                <div key={i} className="flex items-start gap-1.5 text-xs">
                  {cz.confere === true ? (
                    <RiCheckLine
                      className="mt-0.5 size-3.5 shrink-0 text-emerald-600"
                      aria-hidden
                    />
                  ) : cz.confere === false ? (
                    <RiCloseLine
                      className="mt-0.5 size-3.5 shrink-0 text-amber-600"
                      aria-hidden
                    />
                  ) : (
                    <span className="mt-1.5 size-1.5 shrink-0 rounded-full bg-gray-300 dark:bg-gray-700" />
                  )}
                  <span
                    className={cx(
                      cz.confere === false
                        ? "text-amber-700 dark:text-amber-300"
                        : "text-gray-600 dark:text-gray-400",
                    )}
                  >
                    {cz.detalhe}
                    {cz.confere === false && (
                      <span className={cx(tableTokens.cellTextMono, "ml-1")}>
                        (contrato: {String(cz.contrato ?? "—")} · oficial:{" "}
                        {String(cz.oficial ?? "—")})
                      </span>
                    )}
                  </span>
                </div>
              ))}
            </Section>
          )}
        </div>

        {/* PDF real — destino das citações */}
        <OriginPanel dossierId={dossierId} doc={doc} selectedLabel={focusLabel} />
      </div>
    </section>
  )
}
