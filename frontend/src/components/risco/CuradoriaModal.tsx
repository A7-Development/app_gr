// components/risco/CuradoriaModal.tsx
//
// Modal de julgamento da curadoria de liquidação — surface de decisão do
// analista de risco (rolagem única, sem tabs; decisão 2026-07-11). Reusado
// pela página de curadoria e pelo drill do raio-X. Grande, cara de página:
// header com título/subtítulo, KPI strip, cards de evidência, footer sticky
// com OK/FRAUDE/Não sei + ponderação opcional. A trilha (autor+data+nota)
// já vive em curadoria_tag; o histórico é exibido no próprio modal.

"use client"

import * as React from "react"
import {
  RiBankLine,
  RiCheckboxCircleLine,
  RiCloseCircleLine,
  RiMapPin2Line,
  RiQuestionLine,
} from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { Dialog, DialogContent } from "@/components/tremor/Dialog"
import { Textarea } from "@/components/tremor/Textarea"
import { tableTokens } from "@/design-system/tokens/table"
import type { DossieLiquidacao } from "@/lib/api-client"
import { useDossieLiquidacao, useTagLiquidacao } from "@/lib/hooks/risco"
import { cx } from "@/lib/utils"

const brl = (v: number) =>
  v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 2 })
const fmtData = (iso: string | null) =>
  iso ? new Date(iso).toLocaleDateString("pt-BR") : "—"
const fmtDataHora = (iso: string) =>
  new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })

const SEV_BADGE: Record<string, string> = {
  critica: tableTokens.badgeDanger,
  pendente: tableTokens.badgeWarning,
  alta: tableTokens.badgeWarning,
  media: tableTokens.badgeNeutral,
  baixa: tableTokens.badgeNeutral,
}
const CANAL_LABEL: Record<string, string> = {
  bancaria: "Pago no banco",
  baixa_manual: "Baixa manual (sem rastro)",
  recompra: "Recompra",
}

function Kpi({ label, value, tone }: { label: string; value: React.ReactNode; tone?: "danger" | "warn" }) {
  return (
    <div className="flex flex-col gap-0.5 px-3 py-2">
      <span className={tableTokens.header}>{label}</span>
      <span
        className={cx(
          tableTokens.cellStrong,
          tone === "danger" && "text-red-600 dark:text-red-400",
          tone === "warn" && "text-amber-600 dark:text-amber-400",
        )}
      >
        {value}
      </span>
    </div>
  )
}

function Secao({ titulo, icon, children }: { titulo: string; icon?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-md border border-gray-200 p-3 dark:border-gray-800">
      <h4 className={cx(tableTokens.cellStrong, "mb-2 flex items-center gap-1.5")}>
        {icon}
        {titulo}
      </h4>
      {children}
    </section>
  )
}

function Corpo({ d, onDecidir, saving }: {
  d: DossieLiquidacao
  onDecidir: (tag: "ok" | "fraude" | "neutro", nota: string) => void
  saving: boolean
}) {
  const [nota, setNota] = React.useState("")
  const ag = d.agencia
  const conv = ag.convergencia
  const foraPraca = d.sacado_uf && ag.uf && d.sacado_uf !== ag.uf

  return (
    <div className="flex max-h-[86vh] flex-col">
      {/* Header estilo página */}
      <header className="rounded-t-md bg-gray-50 px-5 py-4 dark:bg-gray-900/60">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="truncate text-lg font-semibold text-gray-900 dark:text-gray-50">
              Título {d.titulo_numero ?? d.titulo_id} · {d.sacado_nome ?? "sacado não identificado"}
            </h2>
            <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
              {d.cedente_nome} · {d.produto_nome ?? d.produto_sigla} · {brl(d.valor)} ·{" "}
              liquidado {fmtData(d.data_evento)}
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap justify-end gap-1.5">
            {d.sinais.slice(0, 2).map((s) => (
              <span key={s.codigo} className={cx(tableTokens.badge, SEV_BADGE[s.severidade] ?? tableTokens.badgeNeutral)}>
                {s.codigo}
              </span>
            ))}
          </div>
        </div>
      </header>

      {/* KPI strip */}
      <div className="grid grid-cols-2 divide-x divide-gray-200 border-b border-gray-200 sm:grid-cols-4 dark:divide-gray-800 dark:border-gray-800">
        <Kpi label="CANAL" value={CANAL_LABEL[d.canal] ?? d.canal} />
        <Kpi
          label="PRAÇA"
          value={foraPraca ? `${d.sacado_uf} ≠ ${ag.uf}` : (ag.uf ?? "—")}
          tone={foraPraca ? "danger" : undefined}
        />
        <Kpi label="SACADO" value={`${d.sacado_cidade ?? "—"}/${d.sacado_uf ?? "—"}`} />
        <Kpi
          label="BANCO HABITUAL"
          value={d.quebra_fingerprint > 0 ? "quebrou ⚠" : "estável"}
          tone={d.quebra_fingerprint > 0 ? "warn" : undefined}
        />
      </div>

      {/* Corpo — rolagem única */}
      <div className="flex-1 space-y-3 overflow-y-auto p-5">
        <Secao titulo="Onde o dinheiro caiu" icon={<RiBankLine className="size-4 text-gray-500" />}>
          <p className={tableTokens.cellText}>
            {ag.banco}/{ag.agencia} · {ag.nome ?? "(agência não resolvida)"}
          </p>
          {ag.cidade && (
            <p className={cx(tableTokens.cellSecondary, "flex items-center gap-1")}>
              <RiMapPin2Line className="size-3.5" />
              {ag.cidade}/{ag.uf}
              {ag.endereco ? ` · ${ag.endereco}` : ""}
              {ag.vigencia ? ` · vigente ${ag.vigencia}` : ""}
            </p>
          )}
          <div className="mt-2 flex flex-wrap gap-1.5">
            {ag.conta_do_cedente && (
              <span className={cx(tableTokens.badge, tableTokens.badgeDanger)}>é a conta do cedente</span>
            )}
            {conv && (
              <span
                className={cx(
                  tableTokens.badge,
                  conv.fora >= 5 ? tableTokens.badgeDanger : conv.fora > 0 ? tableTokens.badgeWarning : tableTokens.badgeNeutral,
                )}
                title="Sacados distintos que pagam nesta agência · de outras cidades"
              >
                convergência: {conv.sacados} sacados · {conv.cidades} cidades
                {conv.fora > 0 ? ` · ${conv.fora} de outra praça` : ""}
              </span>
            )}
          </div>
        </Secao>

        <Secao titulo="Por que o sistema marcou">
          {d.sinais.length === 0 ? (
            <p className={tableTokens.cellMuted}>Nenhum sinal automático — revisão manual.</p>
          ) : (
            <ul className="space-y-1.5">
              {d.sinais.map((s) => (
                <li key={s.codigo} className="flex items-start gap-2">
                  <span className={cx(tableTokens.badge, SEV_BADGE[s.severidade] ?? tableTokens.badgeNeutral, "shrink-0")}>
                    {s.codigo}
                  </span>
                  <div className="min-w-0">
                    <p className={tableTokens.cellText}>{s.nome}</p>
                    {s.definicao && <p className={cx(tableTokens.cellMuted, "text-[11px]")}>{s.definicao}</p>}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </Secao>

        <Secao titulo="Histórico de curadoria">
          {d.historico_curadoria.length === 0 ? (
            <p className={tableTokens.cellMuted}>Sem marcações anteriores.</p>
          ) : (
            <ul className="space-y-1.5">
              {d.historico_curadoria.map((t, i) => (
                <li key={i} className={tableTokens.cellSecondary}>
                  <span className={cx(tableTokens.badge, t.tag === "FRAUDE" ? tableTokens.badgeDanger : t.tag === "OK" ? tableTokens.badgeSuccess : tableTokens.badgeNeutral)}>
                    {t.tag}
                  </span>{" "}
                  {t.autor ?? "—"} · {fmtDataHora(t.em)}
                  {t.nota ? ` — "${t.nota}"` : ""}
                </li>
              ))}
            </ul>
          )}
        </Secao>
      </div>

      {/* Footer sticky — a decisão */}
      <footer className="space-y-3 border-t border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-[#090E1A]">
        <Textarea
          value={nota}
          onChange={(e) => setNota(e.target.value)}
          placeholder="Ponderação do analista (opcional) — fica registrada com seu login e data/hora."
          rows={2}
        />
        <div className="flex flex-wrap gap-2">
          <Button
            className="bg-emerald-600 hover:bg-emerald-700"
            disabled={saving}
            onClick={() => onDecidir("ok", nota)}
          >
            <RiCheckboxCircleLine className="mr-1 size-4" /> Íntegro (OK)
          </Button>
          <Button variant="destructive" disabled={saving} onClick={() => onDecidir("fraude", nota)}>
            <RiCloseCircleLine className="mr-1 size-4" /> Fraude
          </Button>
          <Button variant="secondary" disabled={saving} onClick={() => onDecidir("neutro", nota)}>
            <RiQuestionLine className="mr-1 size-4" /> Não consigo decidir
          </Button>
        </div>
      </footer>
    </div>
  )
}

export function CuradoriaModal({
  liquidacaoId,
  onClose,
}: {
  liquidacaoId: string | null
  onClose: () => void
}) {
  const q = useDossieLiquidacao(liquidacaoId)
  const tagMut = useTagLiquidacao()

  const decidir = (tag: "ok" | "fraude" | "neutro", nota: string) => {
    if (!liquidacaoId) return
    tagMut.mutate(
      { liquidacaoId, tag, nota: nota.trim() || null },
      { onSuccess: onClose },
    )
  }

  return (
    <Dialog open={liquidacaoId !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="w-[95vw] max-w-3xl p-0">
        {q.isPending ? (
          <div className="p-10 text-center">
            <span className={tableTokens.cellMuted}>Carregando dossiê…</span>
          </div>
        ) : q.isError || !q.data ? (
          <div className="p-10 text-center">
            <span className={tableTokens.cellSecondary}>Falha ao carregar o dossiê da liquidação.</span>
          </div>
        ) : (
          <Corpo d={q.data} onDecidir={decidir} saving={tagMut.isPending} />
        )}
      </DialogContent>
    </Dialog>
  )
}
