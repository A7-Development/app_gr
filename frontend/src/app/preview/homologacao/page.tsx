"use client"

// Preview (dev-only) — MOCK de alta fidelidade da "bancada de homologação" do
// dossiê de crédito. NÃO é a feature; é o conceito vestido com o design system
// pra validar antes de codar.
//
// Conceito: IA propõe, analista homologa. Cada saída de IA é um CARTÃO DE
// HOMOLOGAÇÃO (componente inline, 3 estados). A tela tem 3 zonas: Trilho
// (onde está), Foco (cartões da etapa) e Evidência (drawer sob demanda).
// O "dial de autonomia" (v1 Total → v2 Exceção → v3 Auditoria) controla
// quantos cartões pedem o martelo — a mesma UI fica só mais leve.

import * as React from "react"
import {
  RiAlertLine,
  RiArrowRightLine,
  RiBarChartBoxLine,
  RiBuilding2Line,
  RiCheckLine,
  RiCheckboxCircleFill,
  RiCloseLine,
  RiFileTextLine,
  RiPencilLine,
  RiRefreshLine,
  RiShieldCheckLine,
  RiSparkling2Line,
} from "@remixicon/react"

import { Badge } from "@/components/tremor/Badge"
import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import { Divider } from "@/components/tremor/Divider"
import { cardTokens } from "@/design-system/tokens/card"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"

// ─────────────────────────────────────────────────────────────────────────────
// Tipos do mock
// ─────────────────────────────────────────────────────────────────────────────

type Estado = "pendente" | "homologado" | "ajustado" | "rejeitado"
type Confianca = "alta" | "media" | "baixa"
type EtapaId = "cadastral" | "faturamento" | "parecer"

type HCard = {
  id: string
  etapa: EtapaId
  titulo: string
  proposta: string
  confianca: Confianca
  altoImpacto?: boolean
  porque: string[]
  evidencia: { icon: React.ElementType; label: string }[]
  estado: Estado
  ajuste?: string // texto "IA dizia X → você Y" quando ajustado
  carimbo?: string // "você · 14:32" quando decidido
}

// ─────────────────────────────────────────────────────────────────────────────
// Dados mockados — ACTION LINE DO BRASIL LTDA (CNPJ real do wh_pj_cadastro)
// ─────────────────────────────────────────────────────────────────────────────

const CARDS_INICIAIS: HCard[] = [
  // ── Cadastral ──
  {
    id: "c1",
    etapa: "cadastral",
    titulo: "Situação cadastral",
    proposta: "CNPJ ATIVO na Receita Federal, sem indício de baixa ou suspensão.",
    confianca: "alta",
    porque: ["TaxIdStatus = ATIVA", "Situação desde 2010, sem mudança recente"],
    evidencia: [{ icon: RiShieldCheckLine, label: "Fonte: BDC · Cadastro PJ" }],
    estado: "homologado",
    carimbo: "você · 14:28",
  },
  {
    id: "c2",
    etapa: "cadastral",
    titulo: "Tempo de atividade",
    proposta: "27 anos de atividade (fundada em 27/02/1998). Maturidade alta.",
    confianca: "alta",
    porque: ["FoundedDate = 1998-02-27", "Acima do mínimo de política (24 meses)"],
    evidencia: [{ icon: RiShieldCheckLine, label: "Fonte: BDC · Cadastro PJ" }],
    estado: "pendente",
  },
  {
    id: "c3",
    etapa: "cadastral",
    titulo: "CNAE compatível com a operação",
    proposta:
      "CNAE principal 8220-2 (call center) compatível com factoring de serviços. 9 CNAEs no total.",
    confianca: "media",
    porque: [
      "CNAE principal na lista permitida da política",
      "CNAEs secundários sem restrição",
    ],
    evidencia: [{ icon: RiShieldCheckLine, label: "Fonte: BDC · Cadastro PJ" }],
    estado: "pendente",
  },
  {
    id: "c4",
    etapa: "cadastral",
    titulo: "Capital social vs porte",
    proposta:
      "Capital social de R$ 250.755 parece baixo frente ao faturamento declarado — revisar coerência.",
    confianca: "baixa",
    altoImpacto: true,
    porque: [
      "CapitalRS = 250.755,00",
      "Faturamento declarado ~R$ 12M/ano → razão atípica",
    ],
    evidencia: [{ icon: RiShieldCheckLine, label: "Fonte: BDC · Cadastro PJ" }],
    estado: "pendente",
  },
  // ── Faturamento ──
  {
    id: "f1",
    etapa: "faturamento",
    titulo: "Tendência de faturamento",
    proposta: "Crescimento consistente de +12% a.a. nos últimos 12 meses.",
    confianca: "alta",
    porque: [
      "Receita mensal em alta 9 de 12 meses",
      "Sem quebras estruturais na série",
    ],
    evidencia: [
      { icon: RiFileTextLine, label: "Declaração de faturamento (PDF)" },
      { icon: RiBarChartBoxLine, label: "Série mensal (12 meses)" },
    ],
    estado: "ajustado",
    ajuste: "IA propôs +18% a.a. → você corrigiu p/ +12% (excluiu pico de mar/24)",
    carimbo: "você · 14:35",
  },
  {
    id: "f2",
    etapa: "faturamento",
    titulo: "Sazonalidade",
    proposta: "Sem sazonalidade atípica; variação mensal dentro do esperado.",
    confianca: "alta",
    porque: ["Desvio mensal < 15%", "Sem concentração em trimestre único"],
    evidencia: [{ icon: RiBarChartBoxLine, label: "Série mensal (12 meses)" }],
    estado: "homologado",
    carimbo: "você · 14:36",
  },
  {
    id: "f3",
    etapa: "faturamento",
    titulo: "Pico atípico em mar/24",
    proposta:
      "Mês de março/24 com receita 3,1× a média — possível evento não-recorrente. Investigar antes de projetar.",
    confianca: "media",
    altoImpacto: true,
    porque: [
      "Receita mar/24 = R$ 2,9M vs média R$ 0,94M",
      "Sem contrapartida nos meses seguintes",
    ],
    evidencia: [
      { icon: RiBarChartBoxLine, label: "Série mensal (destaque mar/24)" },
      { icon: RiFileTextLine, label: "Declaração de faturamento (PDF)" },
    ],
    estado: "pendente",
  },
  {
    id: "f4",
    etapa: "faturamento",
    titulo: "Credibilidade do documento",
    proposta:
      "Declaração assinada pelo contador (CRC 1SP-XXXXXX) e datada de 03/05/2025. Sem ressalvas.",
    confianca: "alta",
    porque: [
      "Assinatura + CRC presentes",
      "Data dentro da janela de 90 dias",
      "Sem observações/ressalvas no corpo",
    ],
    evidencia: [{ icon: RiFileTextLine, label: "Declaração de faturamento (PDF)" }],
    estado: "pendente",
  },
  // ── Parecer ──
  {
    id: "p1",
    etapa: "parecer",
    titulo: "Recomendação",
    proposta:
      "Aprovar com ressalva: conceder limite condicionado à reconciliação do pico de mar/24.",
    confianca: "media",
    altoImpacto: true,
    porque: [
      "Cadastral sólido (ATIVA, 27 anos)",
      "Faturamento crescente, mas 1 ponto a esclarecer",
      "Capital social a confirmar",
    ],
    evidencia: [{ icon: RiSparkling2Line, label: "Síntese dos cartões homologados" }],
    estado: "pendente",
  },
  {
    id: "p2",
    etapa: "parecer",
    titulo: "Limite sugerido",
    proposta: "R$ 500.000 (≈ 0,5× faturamento mensal médio). Revisar após esclarecer mar/24.",
    confianca: "media",
    porque: ["Política: até 0,6× faturamento mensal", "Desconto por ponto em aberto"],
    evidencia: [{ icon: RiBarChartBoxLine, label: "Base de cálculo do limite" }],
    estado: "pendente",
  },
]

// ─────────────────────────────────────────────────────────────────────────────
// Etapas / Trilho
// ─────────────────────────────────────────────────────────────────────────────

type TrilhoEtapa = {
  id: EtapaId | "identificacao" | "decisao"
  label: string
  estado: "feito" | "atual" | "proximo"
  selecionavel?: boolean
}

const TRILHO: TrilhoEtapa[] = [
  { id: "identificacao", label: "Identificação", estado: "feito" },
  { id: "cadastral", label: "Cadastral", estado: "feito", selecionavel: true },
  { id: "faturamento", label: "Faturamento", estado: "atual", selecionavel: true },
  { id: "parecer", label: "Parecer", estado: "proximo", selecionavel: true },
  { id: "decisao", label: "Decisão", estado: "proximo" },
]

// ─────────────────────────────────────────────────────────────────────────────
// Helpers de estilo
// ─────────────────────────────────────────────────────────────────────────────

const CONF_BADGE: Record<Confianca, { variant: "success" | "warning" | "error"; label: string }> = {
  alta: { variant: "success", label: "confiança alta" },
  media: { variant: "warning", label: "confiança média" },
  baixa: { variant: "error", label: "confiança baixa" },
}

// ─────────────────────────────────────────────────────────────────────────────
// Cartão de Homologação (o átomo)
// ─────────────────────────────────────────────────────────────────────────────

function HomologationCard({
  card,
  selecionado,
  onSelect,
  onHomologar,
  onReabrir,
}: {
  card: HCard
  selecionado: boolean
  onSelect: () => void
  onHomologar: () => void
  onReabrir: () => void
}) {
  // Estados colapsados (carimbo) — homologado / ajustado / rejeitado
  if (card.estado !== "pendente") {
    const meta =
      card.estado === "homologado"
        ? { icon: RiCheckboxCircleFill, cls: "text-emerald-600 dark:text-emerald-400", txt: "homologado" }
        : card.estado === "ajustado"
          ? { icon: RiPencilLine, cls: "text-blue-600 dark:text-blue-400", txt: "ajustado" }
          : { icon: RiCloseLine, cls: "text-gray-500", txt: "rejeitado" }
    const Icon = meta.icon
    return (
      <div
        role="button"
        tabIndex={0}
        onClick={onSelect}
        onKeyDown={(e) => e.key === "Enter" && onSelect()}
        className={cx(
          "flex w-full cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-left transition-colors",
          selecionado
            ? "border-blue-500 bg-blue-50/40 dark:border-blue-500/40 dark:bg-blue-500/5"
            : "border-gray-200 bg-white hover:border-gray-300 dark:border-gray-800 dark:bg-gray-950",
        )}
      >
        <Icon className={cx("size-4 shrink-0", meta.cls)} aria-hidden />
        <span className={cx(tableTokens.cellStrong, "shrink-0")}>{card.titulo}</span>
        <span className={cx(tableTokens.cellSecondary, "truncate")}>
          — {meta.txt}
          {card.carimbo ? ` · ${card.carimbo}` : ""}
        </span>
        {card.ajuste && (
          <span className={cx(tableTokens.cellMuted, "ml-auto hidden truncate md:block")}>
            {card.ajuste}
          </span>
        )}
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation()
            onReabrir()
          }}
          className="ml-auto shrink-0 text-[12px] font-medium text-blue-600 hover:underline dark:text-blue-400 md:ml-3"
        >
          reabrir
        </button>
      </div>
    )
  }

  // Estado pendente — cartão expandido
  const conf = CONF_BADGE[card.confianca]
  return (
    <Card
      className={cx(
        "border p-0 ring-0 transition-shadow",
        selecionado
          ? "border-blue-500 shadow-sm dark:border-blue-500/50"
          : "border-amber-200 dark:border-amber-500/30",
      )}
    >
      <button type="button" onClick={onSelect} className="block w-full text-left">
        <div className="flex items-start gap-2 px-4 pt-3">
          <span
            className="mt-1 inline-block size-2 shrink-0 rounded-full bg-amber-500"
            aria-hidden
          />
          <div className="min-w-0 flex-1">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[13px] font-semibold text-gray-900 dark:text-gray-50">
                {card.titulo}
              </span>
              <Badge variant={conf.variant}>{conf.label}</Badge>
              {card.altoImpacto && (
                <Badge variant="error">
                  <RiAlertLine className="size-3" aria-hidden />
                  alto impacto
                </Badge>
              )}
              <span className={cx(tableTokens.badge, "ml-auto bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300")}>
                aguarda você
              </span>
            </div>
            <p className="mt-1.5 text-[13px] leading-relaxed text-gray-700 dark:text-gray-300">
              <span className="font-medium text-violet-700 dark:text-violet-300">IA: </span>
              {card.proposta}
            </p>
          </div>
        </div>

        {/* por quê + evidência */}
        <div className="px-4 pb-1 pl-8">
          <ul className="mt-1 space-y-0.5">
            {card.porque.map((p) => (
              <li key={p} className={cx(tableTokens.cellSecondary, "flex gap-1.5")}>
                <span className="text-gray-400">·</span>
                {p}
              </li>
            ))}
          </ul>
          <div className="mt-2 flex flex-wrap gap-3">
            {card.evidencia.map((e) => {
              const Icon = e.icon
              return (
                <span
                  key={e.label}
                  className="inline-flex items-center gap-1 text-[12px] text-blue-600 dark:text-blue-400"
                >
                  <Icon className="size-3.5" aria-hidden />
                  {e.label}
                </span>
              )
            })}
          </div>
        </div>
      </button>

      <Divider className="my-2.5" />

      {/* ações — vocabulário fechado */}
      <div className="flex flex-wrap items-center gap-2 px-4 pb-3 pl-8">
        <Button className="h-8 px-3 text-[13px]" onClick={onHomologar}>
          <RiCheckLine className="size-4" aria-hidden />
          Homologar
        </Button>
        <Button variant="secondary" className="h-8 px-3 text-[13px]">
          <RiPencilLine className="size-4" aria-hidden />
          Ajustar
        </Button>
        <Button variant="light" className="h-8 px-3 text-[13px]">
          <RiRefreshLine className="size-4" aria-hidden />
          Pedir mais
        </Button>
        <Button variant="ghost" className="h-8 px-2 text-[13px] text-gray-500">
          <RiCloseLine className="size-4" aria-hidden />
          Rejeitar
        </Button>
      </div>
    </Card>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Página
// ─────────────────────────────────────────────────────────────────────────────

export default function PreviewHomologacaoPage() {
  const [etapa, setEtapa] = React.useState<EtapaId>("faturamento")
  const [cards, setCards] = React.useState<HCard[]>(CARDS_INICIAIS)
  const [selId, setSelId] = React.useState<string | null>("f3")

  const daEtapa = cards.filter((c) => c.etapa === etapa)
  const pendentes = daEtapa.filter((c) => c.estado === "pendente").length
  const sel = cards.find((c) => c.id === selId) ?? null

  const setEstado = (id: string, estado: Estado, extra?: Partial<HCard>) =>
    setCards((prev) =>
      prev.map((c) => (c.id === id ? { ...c, estado, carimbo: "você · agora", ...extra } : c)),
    )

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      <div className="mx-auto max-w-6xl px-6 py-6">
        {/* aviso de mock */}
        <p className={cx(tableTokens.cellMuted, "mb-3")}>
          MOCK (dev-only) · bancada de homologação do dossiê — conceito vestido com o design system
        </p>

        {/* ─── Cabeçalho do caso ─── */}
        <div className="flex flex-wrap items-start gap-3">
          <div className="flex size-10 items-center justify-center rounded-md bg-indigo-500 text-white">
            <RiBuilding2Line className="size-5" aria-hidden />
          </div>
          <div className="min-w-0 flex-1">
            <p className={tableTokens.header}>CRÉDITO · DOSSIÊ</p>
            <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-50">
              ACTION LINE DO BRASIL LTDA
            </h1>
            <p className={tableTokens.cellSecondary}>
              CNPJ 02.379.828/0001-28 · análise de onboarding
            </p>
          </div>
          {/* dial de autonomia */}
          <div className="rounded-md border border-gray-200 bg-white px-3 py-1.5 dark:border-gray-800 dark:bg-gray-900">
            <p className={tableTokens.header}>MODO DE HOMOLOGAÇÃO</p>
            <p className="text-[13px] font-medium text-gray-900 dark:text-gray-50">
              Total (v1) · para em todos os cartões
            </p>
          </div>
        </div>

        {/* ─── ZONA 1 · TRILHO ─── */}
        <Card className="mt-4 p-0 ring-0">
          <div className="flex flex-wrap items-center gap-1 px-4 py-3">
            {TRILHO.map((t, i) => {
              const isSel = t.selecionavel && t.id === etapa
              const dot =
                t.estado === "feito"
                  ? "bg-emerald-500"
                  : t.estado === "atual"
                    ? "bg-amber-500"
                    : "bg-gray-300 dark:bg-gray-700"
              return (
                <React.Fragment key={t.id}>
                  <button
                    type="button"
                    disabled={!t.selecionavel}
                    onClick={() => t.selecionavel && setEtapa(t.id as EtapaId)}
                    className={cx(
                      "flex items-center gap-1.5 rounded-md px-2.5 py-1 text-[13px]",
                      t.selecionavel ? "cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-900" : "cursor-default",
                      isSel
                        ? "bg-blue-50 font-medium text-blue-700 dark:bg-blue-500/10 dark:text-blue-300"
                        : "text-gray-600 dark:text-gray-400",
                    )}
                  >
                    {t.estado === "feito" ? (
                      <RiCheckboxCircleFill className="size-3.5 text-emerald-500" aria-hidden />
                    ) : (
                      <span className={cx("inline-block size-2 rounded-full", dot)} aria-hidden />
                    )}
                    {t.label}
                  </button>
                  {i < TRILHO.length - 1 && (
                    <span className="text-gray-300 dark:text-gray-700" aria-hidden>
                      →
                    </span>
                  )}
                </React.Fragment>
              )
            })}
            <div className="ml-auto flex items-center gap-3">
              <div className="flex items-center gap-1.5">
                <span className={tableTokens.header}>RISCO ATÉ AQUI</span>
                <span className="inline-flex gap-0.5">
                  {[0, 1, 2, 3, 4].map((n) => (
                    <span
                      key={n}
                      className={cx(
                        "inline-block h-3 w-1.5 rounded-sm",
                        n < 2 ? "bg-amber-400" : "bg-gray-200 dark:bg-gray-800",
                      )}
                    />
                  ))}
                </span>
              </div>
              <Button disabled={pendentes > 0} className="h-8 px-3 text-[13px]">
                Avançar etapa
                <RiArrowRightLine className="size-4" aria-hidden />
              </Button>
            </div>
          </div>
        </Card>

        {/* ─── ZONAS 2 + 3 ─── */}
        <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[1fr_320px]">
          {/* ZONA 2 · FOCO — cartões da etapa */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <h2 className="text-[13px] font-semibold text-gray-900 dark:text-gray-50">
                {etapa === "cadastral"
                  ? "Cadastral"
                  : etapa === "faturamento"
                    ? "Faturamento"
                    : "Parecer"}{" "}
                <span className="font-normal text-gray-400">
                  · {daEtapa.length} cartões
                </span>
              </h2>
              <span
                className={cx(
                  tableTokens.badge,
                  pendentes > 0
                    ? "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300"
                    : "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
                )}
              >
                {pendentes > 0 ? `${pendentes} aguardam você` : "tudo homologado"}
              </span>
            </div>

            <div className="space-y-2.5">
              {daEtapa.map((c) => (
                <HomologationCard
                  key={c.id}
                  card={c}
                  selecionado={selId === c.id}
                  onSelect={() => setSelId(c.id)}
                  onHomologar={() => setEstado(c.id, "homologado")}
                  onReabrir={() => setEstado(c.id, "pendente", { carimbo: undefined })}
                />
              ))}
            </div>
          </div>

          {/* ZONA 3 · EVIDÊNCIA */}
          <div className="lg:sticky lg:top-4 lg:self-start">
            <Card className={cx(cardTokens.body, "ring-0")}>
              <div className="flex items-center gap-1.5">
                <RiFileTextLine className="size-4 text-gray-400" aria-hidden />
                <span className="text-[13px] font-semibold text-gray-900 dark:text-gray-50">
                  Evidência
                </span>
              </div>
              <Divider className="my-2.5" />
              {sel ? (
                <div className="space-y-3">
                  <div>
                    <p className={tableTokens.header}>CARTÃO</p>
                    <p className="text-[13px] font-medium text-gray-900 dark:text-gray-50">
                      {sel.titulo}
                    </p>
                  </div>
                  <div>
                    <p className={tableTokens.header}>POR QUÊ (FATORES)</p>
                    <ul className="mt-0.5 space-y-0.5">
                      {sel.porque.map((p) => (
                        <li key={p} className={cx(tableTokens.cellSecondary, "flex gap-1.5")}>
                          <span className="text-gray-400">·</span>
                          {p}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <p className={tableTokens.header}>FONTES</p>
                    <div className="mt-1 space-y-1">
                      {sel.evidencia.map((e) => {
                        const Icon = e.icon
                        return (
                          <div
                            key={e.label}
                            className="flex items-center gap-1.5 rounded-md border border-gray-200 px-2 py-1.5 dark:border-gray-800"
                          >
                            <Icon className="size-3.5 text-gray-400" aria-hidden />
                            <span className={tableTokens.cellSecondary}>{e.label}</span>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                  {/* mock de "documento" */}
                  <div className="rounded-md bg-gray-50 p-2.5 dark:bg-gray-900/50">
                    <p className={tableTokens.header}>PRÉVIA</p>
                    <p className={cx(tableTokens.cellMuted, "mt-1 italic")}>
                      [prévia do documento / gráfico da série / payload da fonte
                      apareceria aqui — drill sob demanda, não despejado na bancada]
                    </p>
                  </div>
                </div>
              ) : (
                <p className={tableTokens.cellMuted}>
                  Selecione um cartão para ver a evidência.
                </p>
              )}
            </Card>
          </div>
        </div>
      </div>
    </div>
  )
}
