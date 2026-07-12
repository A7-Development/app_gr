// components/risco/CuradoriaModal.tsx
//
// Modal de julgamento da curadoria de liquidação — surface de decisão do
// analista (rolagem única; layout "confronto de praças", escolhido 2026-07-12).
// A fraude de auto-liquidação é uma DIVERGÊNCIA DE PRAÇA: o sacado é de um
// lugar, mas o dinheiro caiu noutro (a praça do cedente). O modal põe os dois
// lados frente a frente com a divergência no centro. Reusado pela curadoria e
// pelo raio-X. Trilha (autor+data+nota) já vive em curadoria_tag.

"use client"

import * as React from "react"
import {
  RiCheckboxCircleLine,
  RiCloseCircleLine,
  RiQuestionLine,
  RiScales3Line,
  RiShieldCheckLine,
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
const fmtData = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("pt-BR") : "—")
const fmtDataHora = (iso: string) =>
  new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })
const norm = (s: string | null) =>
  (s ?? "").normalize("NFD").replace(/[̀-ͯ]/g, "").trim().toLowerCase()

const SEV_BADGE: Record<string, string> = {
  critica: tableTokens.badgeDanger,
  pendente: tableTokens.badgeWarning,
  alta: tableTokens.badgeWarning,
  media: tableTokens.badgeNeutral,
  baixa: tableTokens.badgeNeutral,
}
const CANAL_LABEL: Record<string, string> = {
  bancaria: "pago no banco",
  baixa_manual: "baixa manual (sem rastro)",
  recompra: "recompra",
}

function LiqItem({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="min-w-0">
      <div className={tableTokens.header}>{label}</div>
      <div className={cx(tableTokens.cellStrong, "truncate")}>{value}</div>
    </div>
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
  const produto = d.produto_nome
    ? `${d.produto_nome}${d.produto_sigla ? ` (${d.produto_sigla})` : ""}`
    : (d.produto_sigla ?? "—")

  const sacadoCidade = d.sacado_cidade
  const pagCidade = ag.cidade
  // Divergência = sacado paga fora da própria praça.
  const divergente = !!(sacadoCidade && pagCidade && norm(sacadoCidade) !== norm(pagCidade))
  // O pagamento caiu na praça do cedente?
  const ehPracaCedente = !!(pagCidade && d.cedente_cidade && norm(pagCidade) === norm(d.cedente_cidade))

  return (
    <div className="flex max-h-[88vh] flex-col">
      {/* ── Header: propósito + dados da liquidação ── */}
      <header className="border-b border-gray-200 bg-gray-50 px-5 py-4 dark:border-gray-800 dark:bg-gray-900/50">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="flex items-center gap-1.5 text-[10.5px] font-bold uppercase tracking-wider text-blue-600 dark:text-blue-400">
              <RiScales3Line className="size-3.5" /> Curadoria de liquidação
            </p>
            <h2 className="mt-1 text-lg font-semibold text-gray-900 dark:text-gray-50">
              Título {d.titulo_numero ?? d.titulo_id}
            </h2>
          </div>
          <div className="flex shrink-0 flex-wrap justify-end gap-1.5" style={{ maxWidth: 160 }}>
            {d.sinais.slice(0, 3).map((s) => (
              <span key={s.codigo} className={cx(tableTokens.badge, SEV_BADGE[s.severidade] ?? tableTokens.badgeNeutral)}>
                {s.codigo}
              </span>
            ))}
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-x-6 gap-y-2">
          <LiqItem label="Cedente" value={d.cedente_nome ?? "—"} />
          <LiqItem label="Produto" value={produto} />
          <LiqItem label="Valor" value={<span className="tabular-nums">{brl(d.valor)}</span>} />
          <LiqItem label="Liquidado em" value={`${fmtData(d.data_evento)} · ${CANAL_LABEL[d.canal] ?? d.canal}`} />
        </div>
      </header>

      {/* ── Confronto de praças ── */}
      <div className="grid grid-cols-[1fr_auto_1fr] items-stretch border-b border-gray-200 dark:border-gray-800">
        {/* Sacado */}
        <div className="px-4 py-4">
          <h3 className="text-xs font-bold text-gray-900 dark:text-gray-100">Sacado — quem deveria pagar</h3>
          <p className={cx(tableTokens.cellStrong, "mt-1 truncate")} title={d.sacado_nome ?? undefined}>
            {d.sacado_nome ?? "sacado não identificado"}
          </p>
          <p className="mt-1 text-xl font-bold leading-tight tracking-tight text-gray-900 dark:text-gray-100">
            {sacadoCidade ?? "—"}
          </p>
          <p className={tableTokens.cellSecondary}>{d.sacado_uf ?? ""}</p>
          <p className={cx(tableTokens.cellMuted, "mt-2.5 text-[11.5px]")}>
            Banco habitual: {d.quebra_fingerprint > 0 ? "quebrou o padrão ⚠" : "estável"}
          </p>
        </div>

        {/* Divergência no centro */}
        <div className="flex flex-col items-center justify-center gap-1.5 border-x border-dashed border-gray-200 px-3 dark:border-gray-800">
          {divergente ? (
            <>
              <span className="text-2xl font-extrabold leading-none text-red-600 dark:text-red-400">≠</span>
              <span className="max-w-[76px] text-center text-[9.5px] font-bold uppercase tracking-wide text-red-600 dark:text-red-400">
                praça divergente
              </span>
            </>
          ) : (
            <>
              <span className="text-2xl font-extrabold leading-none text-gray-400">=</span>
              <span className="max-w-[76px] text-center text-[9.5px] font-bold uppercase tracking-wide text-gray-400">
                mesma praça
              </span>
            </>
          )}
        </div>

        {/* Pagamento / praça do cedente */}
        <div className={cx("px-4 py-4", divergente && "bg-gradient-to-b from-red-500/[.05] to-transparent")}>
          <h3 className="text-xs font-bold text-gray-900 dark:text-gray-100">
            Onde o dinheiro caiu{ehPracaCedente ? " — praça do cedente" : ""}
          </h3>
          <p className={cx(tableTokens.cellStrong, "mt-1 truncate")} title={ag.nome ?? undefined}>
            {ag.banco}/{ag.agencia} · {ag.nome ?? "(agência não resolvida)"}
          </p>
          <p className={cx(
            "mt-1 text-xl font-bold leading-tight tracking-tight",
            divergente ? "text-red-600 dark:text-red-400" : "text-gray-900 dark:text-gray-100",
          )}>
            {pagCidade ?? "—"}
          </p>
          <p className={tableTokens.cellSecondary}>
            {ag.uf ?? ""}{ag.endereco ? ` · ${ag.endereco}` : ""}{ag.vigencia ? ` · vigente ${ag.vigencia}` : ""}
          </p>
          <p className={cx(tableTokens.cellMuted, "mt-2.5 text-[11.5px]")}>
            {ag.conta_do_cedente
              ? "É a agência onde o cedente tem conta"
              : ehPracaCedente
                ? `= praça do cedente (${d.cedente_nome?.split(" ")[0] ?? "cedente"} é de ${d.cedente_cidade})`
                : "Conta do cedente aqui: não cadastrada"}
          </p>
        </div>
      </div>

      {/* Convergência (S2) */}
      {conv && conv.sacados > 1 && (
        <div className="mx-4 mt-3 flex items-center gap-2 rounded-lg border border-red-200 bg-red-50 px-3 py-2.5 text-xs text-red-700 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300">
          <RiShieldCheckLine className="size-4 shrink-0" />
          <span>
            Convergência nesta agência:{" "}
            <b>{conv.sacados} sacados distintos · {conv.cidades} cidades · {conv.fora} de outra praça</b>
            {conv.fora >= 5 ? " — improvável para uma agência real." : "."}
          </span>
        </div>
      )}

      {/* Corpo rolável — sinais + histórico */}
      <div className="flex-1 space-y-3 overflow-y-auto px-5 pb-4 pt-3">
        <section className="rounded-md border border-gray-200 p-3 dark:border-gray-800">
          <h4 className={cx(tableTokens.cellStrong, "mb-2")}>Por que o sistema marcou</h4>
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
        </section>

        <section className="rounded-md border border-gray-200 p-3 dark:border-gray-800">
          <h4 className={cx(tableTokens.cellStrong, "mb-2")}>Histórico de curadoria</h4>
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
        </section>
      </div>

      {/* Footer sticky — decisão */}
      <footer className="space-y-3 border-t border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-[#090E1A]">
        <Textarea
          value={nota}
          onChange={(e) => setNota(e.target.value)}
          placeholder="Ponderação do analista (opcional) — fica registrada com seu login e data/hora."
          rows={2}
        />
        <div className="flex flex-wrap gap-2">
          <Button className="bg-emerald-600 hover:bg-emerald-700" disabled={saving} onClick={() => onDecidir("ok", nota)}>
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
    tagMut.mutate({ liquidacaoId, tag, nota: nota.trim() || null }, { onSuccess: onClose })
  }

  return (
    <Dialog open={liquidacaoId !== null} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="w-[96vw] max-w-3xl p-0">
        {q.isPending ? (
          <div className="p-10 text-center"><span className={tableTokens.cellMuted}>Carregando dossiê…</span></div>
        ) : q.isError || !q.data ? (
          <div className="p-10 text-center"><span className={tableTokens.cellSecondary}>Falha ao carregar o dossiê da liquidação.</span></div>
        ) : (
          <Corpo d={q.data} onDecidir={decidir} saving={tagMut.isPending} />
        )}
      </DialogContent>
    </Dialog>
  )
}
