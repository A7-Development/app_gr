// src/app/(app)/admin/dados/saude/page.tsx
//
// Admin · Saúde das integrações — o painel de mantenedor (feedback Ricardo
// 2026-07-08: "estou sem visão da CVM"). Uma linha por fonte/job/modelo
// monitorado, com última execução + status + FRESCOR (o dado está velho?).
// A régua de frescor é o que pega uma fonte que parou em silêncio.
//
// Lê /admin/saude-integracoes (agrega decision_log + sondas de frescor).
// Refetch a cada 60s (§7.3 — estado sempre visível).
//

"use client"

import * as React from "react"
import {
  RiAlertLine,
  RiCheckboxCircleFill,
  RiErrorWarningFill,
  RiPulseLine,
  RiQuestionLine,
  RiTimeLine,
} from "@remixicon/react"
import { useQuery } from "@tanstack/react-query"
import { formatDistanceToNow, parseISO } from "date-fns"
import { ptBR } from "date-fns/locale"

import { Card } from "@/components/tremor/Card"
import { PageHeader } from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import { adminSaudeIntegracoes, type SaudeIntegracaoItem } from "@/lib/api-client"
import { cx } from "@/lib/utils"

const CATEGORIA_LABEL: Record<string, string> = {
  fonte_externa: "Fonte externa",
  job_interno: "Job interno",
  modelo: "Modelo",
  federado: "Federado",
}

const STATUS: Record<
  string,
  { label: string; badge: string; Icon: typeof RiCheckboxCircleFill }
> = {
  ok: { label: "Saudável", badge: tableTokens.badgeSuccess, Icon: RiCheckboxCircleFill },
  atrasado: { label: "Atrasado", badge: tableTokens.badgeWarning, Icon: RiTimeLine },
  erro: { label: "Erro", badge: tableTokens.badgeDanger, Icon: RiErrorWarningFill },
  nunca_rodou: { label: "Nunca rodou", badge: tableTokens.badgeNeutral, Icon: RiQuestionLine },
}

function cadenciaLabel(horas: number): string {
  if (horas < 24) return `a cada ${Math.round(horas)}h`
  const dias = Math.round(horas / 24)
  return dias <= 1 ? "diária" : `a cada ${dias} dias`
}

function ItemCard({ item }: { item: SaudeIntegracaoItem }) {
  const st = STATUS[item.status] ?? STATUS.nunca_rodou
  const alerta = item.status === "erro" || item.status === "atrasado"
  return (
    <Card
      className={cx(
        "flex flex-col gap-2 p-4",
        alerta && "border-amber-300 dark:border-amber-800",
        item.status === "erro" && "border-red-300 dark:border-red-800",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-col gap-0.5">
          <span className={tableTokens.cellStrong}>{item.label}</span>
          <span className={tableTokens.header}>
            {CATEGORIA_LABEL[item.categoria] ?? item.categoria} · frescor{" "}
            {cadenciaLabel(item.cadencia_horas)}
          </span>
        </div>
        <span className={cx(tableTokens.badge, st.badge, "flex items-center gap-1 shrink-0")}>
          <st.Icon className="size-3.5" aria-hidden />
          {st.label}
        </span>
      </div>

      <span className={tableTokens.cellSecondary}>
        {item.ultima_execucao ? (
          <>
            Última:{" "}
            <span className={item.status !== "ok" ? "font-semibold" : undefined}>
              {formatDistanceToNow(parseISO(item.ultima_execucao), {
                addSuffix: true,
                locale: ptBR,
              })}
            </span>
            {item.volume !== null &&
              ` · ${item.volume.toLocaleString("pt-BR")} registros`}
          </>
        ) : (
          <span className="text-red-600 dark:text-red-400">
            Sem registro de execução — nunca rodou (ou não emite heartbeat).
          </span>
        )}
      </span>

      {item.detalhe && (
        <span className={tableTokens.cellMuted}>{item.detalhe}</span>
      )}
      {item.descricao && (
        <span className={tableTokens.cellMuted}>{item.descricao}</span>
      )}
    </Card>
  )
}

export default function SaudeIntegracoesPage() {
  const q = useQuery({
    queryKey: ["admin", "saude-integracoes"],
    queryFn: () => adminSaudeIntegracoes.list(),
    refetchInterval: 60_000,
    staleTime: 30_000,
  })

  const itens = q.data ?? []
  const alertas = itens.filter((i) => i.status === "erro" || i.status === "atrasado")
  const naoRodou = itens.filter((i) => i.status === "nunca_rodou")

  return (
    <div className="flex flex-col gap-6 px-6 pt-5 pb-6">
      <PageHeader
        title="Saúde das integrações"
        info="Uma linha por fonte, job ou modelo monitorado: última execução, status e frescor. Um item fica 'atrasado' quando passa da cadência esperada — é o alarme que pega uma fonte que parou em silêncio. Federados (CVM) são monitorados por sonda de frescor; o resto pelo registro de execuções (decision_log)."
        subtitle="Admin · Dados"
      />

      {/* Faixa de resumo — o que exige atenção agora */}
      <div className="flex flex-wrap items-center gap-3">
        <span
          className={cx(
            tableTokens.badge,
            alertas.length > 0 ? tableTokens.badgeWarning : tableTokens.badgeSuccess,
            "flex items-center gap-1",
          )}
        >
          {alertas.length > 0 ? (
            <RiAlertLine className="size-3.5" aria-hidden />
          ) : (
            <RiCheckboxCircleFill className="size-3.5" aria-hidden />
          )}
          {alertas.length > 0
            ? `${alertas.length} exigindo atenção`
            : "Tudo saudável"}
        </span>
        {naoRodou.length > 0 && (
          <span className={cx(tableTokens.badge, tableTokens.badgeNeutral)}>
            {naoRodou.length} nunca rodou / sem heartbeat
          </span>
        )}
        <span className={cx(tableTokens.cellSecondary, "ml-auto flex items-center gap-1")}>
          <RiPulseLine className="size-3.5" aria-hidden />
          {q.isFetching ? "atualizando…" : `${itens.length} monitorados`}
        </span>
      </div>

      {q.isLoading ? (
        <span className={tableTokens.cellMuted}>Carregando saúde das integrações…</span>
      ) : q.error ? (
        <span className="text-red-600 dark:text-red-400">
          Falha ao carregar. {q.error instanceof Error ? q.error.message : ""}
        </span>
      ) : (
        <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
          {itens.map((item) => (
            <ItemCard key={item.chave} item={item} />
          ))}
        </div>
      )}
    </div>
  )
}
