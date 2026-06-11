"use client"

// Preview /preview/esteira-ds — fundações do design system da esteira de
// crédito (handoff Conceito D, 2026-06-10). Demonstra a linguagem de
// proveniência (4 assinaturas) + chassi de estação ISOLADOS, com os dados
// mock do próprio handoff, para validação visual antes do wiring real.

import * as React from "react"
import {
  RiArchiveDrawerLine,
  RiFileUploadLine,
  RiInformationLine,
  RiQuillPenLine,
  RiSparkling2Line,
  RiUserFollowLine,
} from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import {
  AgentConclusion,
  AgentLiveChip,
  ClosureBar,
  DiffInserted,
  DiffRemoved,
  FocusRail,
  KpiChartCard,
  PreviousValue,
  ProvenanceChip,
  ProvenanceSup,
  ProvenanceTile,
  ProvenanceValue,
  StationHeader,
  StationStateChip,
  StationsSidebar,
  type StationItem,
} from "@/design-system/components"
import { provenanceTokens, type ProvenanceOrigin } from "@/design-system/tokens/provenance"

// Dados do gráfico do handoff (D1 — faturamento Jan–Dez, Nov selecionada).
const CHART_DATA = [
  { label: "Jan", value: 2.41, valueLabel: "2,41" },
  { label: "Fev", value: 2.38, valueLabel: "2,38" },
  { label: "Mar", value: 2.52, valueLabel: "2,52" },
  { label: "Abr", value: 2.49, valueLabel: "2,49" },
  { label: "Mai", value: 2.61, valueLabel: "2,61" },
  { label: "Jun", value: 2.58, valueLabel: "2,58" },
  { label: "Jul", value: 2.72, valueLabel: "2,72" },
  { label: "Ago", value: 2.69, valueLabel: "2,69" },
  { label: "Set", value: 2.81, valueLabel: "2,81" },
  { label: "Out", value: 2.77, valueLabel: "2,77" },
  { label: "Nov", value: 2.94, valueLabel: "2,94", selected: true },
  { label: "Dez", value: 3.08, valueLabel: "3,08" },
]

const Y_TICKS = [
  { v: 0, label: "0" },
  { v: 1, label: "1 mi" },
  { v: 2, label: "2 mi" },
  { v: 3, label: "3 mi" },
]

const STATIONS: StationItem[] = [
  { id: "1", label: "1 · Identificação", sublabel: "fechou sozinha · 2 fontes", state: "fechada" },
  { id: "2", label: "2 · Faturamento", sublabel: "extração pronta · 12 valores", state: "sua_vez" },
  { id: "3", label: "3 · Endividamento", sublabel: "conclusão pronta", state: "homologar" },
  { id: "4", label: "4 · Apontamentos", sublabel: "agente cruzando · 2/3 fontes", state: "rodando" },
  { id: "5", label: "5 · Parecer", sublabel: "abre quando 2–4 fecharem", state: "bloqueada" },
]

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-4">
      <h2 className="text-[11px] font-semibold uppercase tracking-[0.06em] text-gray-400">
        {title}
      </h2>
      {children}
    </section>
  )
}

export default function EsteiraDsPreviewPage() {
  const [closureState, setClosureState] = React.useState<"pending" | "armed" | "external">(
    "pending",
  )

  return (
    <div className="min-h-screen bg-gray-50 px-8 py-8 dark:bg-gray-925">
      <div className="mx-auto flex max-w-[1100px] flex-col gap-10">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-gray-400">
            Preview · Esteira de crédito
          </p>
          <h1 className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-50">
            Fundações — linguagem de proveniência + chassi de estação
          </h1>
          <p className="mt-1 text-[13px] text-gray-500">
            Handoff Conceito D (2026-06-10). Dados mock do próprio handoff.
          </p>
        </div>

        {/* ── 1. As 4 assinaturas ── */}
        <Section title="1 · Assinaturas de origem (ícone + cor + forma — nunca cor sozinha)">
          <div className="grid grid-cols-1 gap-px overflow-hidden rounded border border-gray-200 bg-gray-200 sm:grid-cols-4 dark:border-gray-800 dark:bg-gray-800">
            {(Object.keys(provenanceTokens) as ProvenanceOrigin[]).map((origin) => {
              const t = provenanceTokens[origin]
              return (
                <div key={origin} className="bg-white p-6 dark:bg-gray-950">
                  <ProvenanceTile origin={origin} />
                  <p className="mt-3 text-[13px] font-semibold text-gray-900 dark:text-gray-50">
                    {t.label}
                  </p>
                  <p className="mt-0.5 text-[11px] text-gray-500">
                    {t.line === "continua"
                      ? "cyan · linha contínua"
                      : t.line === "pontilhada"
                        ? "indigo · pontilhada → contínua ao homologar"
                        : t.line === "tracejada"
                          ? "verde · tracejada"
                          : "grafite · linha dupla"}
                  </p>
                  <p className="mt-3 text-[14px] font-semibold tabular-nums text-gray-900 dark:text-gray-50">
                    <ProvenanceValue origin={origin} homologado={origin !== "agente"}>
                      {origin === "fonte"
                        ? "12 operações"
                        : origin === "agente"
                          ? "risco moderado"
                          : origin === "documento"
                            ? "R$ 2,94 mi"
                            : "42 dias"}
                    </ProvenanceValue>
                    {origin === "analista" && <PreviousValue>38</PreviousValue>}
                  </p>
                </div>
              )
            })}
          </div>

          <div className="flex flex-wrap items-center gap-2">
            <ProvenanceChip origin="fonte">SCR · Bacen</ProvenanceChip>
            <ProvenanceChip origin="documento">Balancete 2025</ProvenanceChip>
            <ProvenanceChip origin="analista">M. Costa · era 38</ProvenanceChip>
            <ProvenanceChip origin="agente">
              Agente de endividamento · aguarda homologação
            </ProvenanceChip>
            <AgentLiveChip>Agente ativo · 2/3 fontes</AgentLiveChip>
          </div>

          <p className="max-w-[620px] text-sm leading-[1.9] text-gray-700 dark:text-gray-300">
            O prazo médio de recebimento é de{" "}
            <strong className="font-semibold tabular-nums">
              42 dias
              <ProvenanceSup origin="analista" index={1} />
            </strong>{" "}
            sobre uma carteira com{" "}
            <strong className="font-semibold tabular-nums">
              12 operações ativas
              <ProvenanceSup origin="fonte" index={1} />
            </strong>{" "}
            e faturamento médio de{" "}
            <strong className="font-semibold tabular-nums">
              R$ 2,68 mi
              <ProvenanceSup origin="documento" index={1} />
            </strong>
            , com tendência de alta confirmada pelo agente
            <ProvenanceSup origin="agente" index={1} />.
          </p>
        </Section>

        {/* ── 2. Diff de edição humana ── */}
        <Section title="2 · Diff de edição humana (única linguagem de edição do produto)">
          <div className="rounded border border-gray-200 bg-white p-5 text-[13.5px] leading-[1.8] text-gray-700 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-300">
            A concentração nas três maiores instituições é{" "}
            <DiffRemoved>preocupante</DiffRemoved>{" "}
            <DiffInserted>compatível com o porte, considerando a sazonalidade do 4º tri</DiffInserted>
            , e o endividamento total representa 0,9× o faturamento anual.
          </div>
        </Section>

        {/* ── 3. Conclusão de agente ── */}
        <Section title="3 · Conclusão de agente (não homologada · indigo dashed)">
          <AgentConclusion
            eyebrow="Leitura do agente de faturamento"
            meta="v1.8 · gerada após a extração · será revisada se você ajustar valores"
            tag="julgamento · editável"
            footnote={
              <>
                <RiInformationLine className="mt-px size-3.5 shrink-0" aria-hidden />
                <span>
                  1 trecho ajustado por você — a versão original do agente fica preservada na
                  trilha.
                </span>
              </>
            }
            actions={
              <>
                <Button className="h-8">Homologar leitura</Button>
                <Button variant="secondary" className="h-8">
                  Editar
                </Button>
                <Button variant="ghost" className="h-8">
                  Recusar e reprocessar
                </Button>
                <span className="ml-auto text-[11.5px] text-gray-400">
                  recusar pede um motivo — ele vira instrução para a nova rodada do agente
                </span>
              </>
            }
          >
            Receita com crescimento consistente de 28% em 12 meses, sem ruptura de padrão.
            A queda pontual de março é compatível com a sazonalidade declarada do setor.
            Documento assinado e recente — credibilidade alta. Leitura para crédito:{" "}
            <strong className="font-semibold">favorável, sem ressalvas de faturamento</strong>.
          </AgentConclusion>
        </Section>

        {/* ── 4. KpiChartCard ── */}
        <Section title="4 · KpiChartCard (anatomia L1/L2/L3 + barra selecionada)">
          <div className="max-w-[860px]">
            <KpiChartCard
              eyebrow="Faturamento mensal · últimos 12 meses"
              value="R$ 2,68 mi"
              delta="↑ 9,8%"
              deltaSuffix="vs. 12m anteriores"
              context="média mensal · fonte: balancete homologado (D1)"
              data={CHART_DATA}
              yTicks={Y_TICKS}
              yMax={3.4}
              height={280}
            />
          </div>
        </Section>

        {/* ── 5. Chips de estado + header de estação ── */}
        <Section title="5 · Header de estação + sub-passos + chips de estado">
          <div className="flex flex-wrap gap-2">
            <StationStateChip variant="blue" icon={RiUserFollowLine}>
              Sua vez
            </StationStateChip>
            <StationStateChip variant="indigo" icon={RiSparkling2Line}>
              Aguardando homologação
            </StationStateChip>
            <StationStateChip variant="neutral" icon={RiFileUploadLine}>
              Aguardando documento
            </StationStateChip>
            <StationStateChip variant="green">Fechada</StationStateChip>
          </div>
          <div className="overflow-hidden rounded border border-gray-200 dark:border-gray-800">
            <StationHeader
              title="Estação 2 · Faturamento"
              chip={
                <StationStateChip variant="blue" icon={RiUserFollowLine}>
                  Sua vez
                </StationStateChip>
              }
              subtitle="Rodou sozinho: recebimento do documento → extração de 12 valores em 47s. Falta você: conferir, decidir sobre a leitura da IA e fechar."
              substeps={[
                { label: "Documento", state: "done" },
                { label: "Conferência · 1 pendente", state: "active" },
                { label: "Conclusão da IA", state: "future" },
                { label: "Fechamento", state: "future" },
              ]}
              onOpenTrail={() => {}}
              trailDisabled
            />
            <div className="bg-gray-50 px-8 py-6 text-[13px] text-gray-400 dark:bg-gray-925">
              … zonas de trabalho da estação (cards, gap 20px) …
            </div>
          </div>
        </Section>

        {/* ── 6. Barra de fechamento (3 estados) ── */}
        <Section title="6 · Barra de fechamento — salvar ≠ fechar">
          <div className="flex gap-2">
            {(["pending", "armed", "external"] as const).map((s) => (
              <Button
                key={s}
                variant={closureState === s ? "primary" : "secondary"}
                className="h-7 text-xs"
                onClick={() => setClosureState(s)}
              >
                {s === "pending" ? "1 · pendências suas" : s === "armed" ? "2 · tudo resolvido" : "3 · pendência externa"}
              </Button>
            ))}
          </div>
          <div className="overflow-hidden rounded border border-gray-200 dark:border-gray-800">
            {closureState === "pending" && (
              <ClosureBar
                state="pending"
                statusText="Rascunho salvo automaticamente às 09:04 — nada se perde se você sair."
                pendingText="falta: confirmar Nov/25 · decidir sobre a leitura"
                onPrimary={() => {}}
                primaryLabel="Fechar estação"
              />
            )}
            {closureState === "armed" && (
              <ClosureBar
                state="armed"
                statusText="12 valores conferidos · leitura homologada · pronto para gravar a seção §2 no dossiê."
                onPrimary={() => {}}
                primaryLabel="Fechar e seguir → Estação 3 · Endividamento"
                statusIcon={RiArchiveDrawerLine}
              />
            )}
            {closureState === "external" && (
              <ClosureBar
                state="external"
                statusText="Nov/25 aguarda reenvio do cedente — pendência externa, fora do seu controle."
                onPrimary={() => {}}
                primaryLabel="Fechar com ressalva"
                secondary={
                  <Button variant="ghost" className="h-9">
                    Deixar em espera
                  </Button>
                }
              />
            )}
          </div>
        </Section>

        {/* ── 7. Modo foco (rail + sidebar de etapas) ── */}
        <Section title="7 · Modo foco — rail 56px + sidebar de etapas 292px">
          <div className="flex h-[560px] overflow-hidden rounded border border-gray-200 dark:border-gray-800">
            <FocusRail
              items={[
                { href: "#fila", label: "Fila de análises", icon: RiUserFollowLine, active: true },
                { href: "#agentes", label: "Agentes", icon: RiSparkling2Line },
                { href: "#parecer", label: "Pareceres", icon: RiQuillPenLine },
              ]}
              userInitials="MC"
              userName="Mariana Costa"
              className="h-full"
            />
            <StationsSidebar
              backHref="#"
              title="Transportes Meridiano Ltda"
              meta="DC-2026-0148 · R$ 2,5 mi pleiteado"
              progressPct={40}
              progressLabel="2 de 5"
              stations={STATIONS}
              activeId="2"
              onSelect={() => {}}
              dossierLabel="Ver dossiê · 48% montado"
              trailLabel="Trilha: 23 eventos · último há 4 min"
              className="h-full"
            />
            <div className="flex flex-1 items-center justify-center bg-gray-50 text-[13px] text-gray-400 dark:bg-gray-925">
              … workbench da estação ativa …
            </div>
          </div>
        </Section>
      </div>
    </div>
  )
}
