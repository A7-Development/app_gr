// components/risco/CuradoriaModal.tsx
//
// Modal de curadoria de liquidação — surface de decisão do analista de risco
// (handoff 6a "case file", 940px, rolagem única que cabe sem scroll).
// Decide se a liquidação é pagamento de terceiro real ou auto-liquidação
// (cedente pagando o boleto do próprio sacado). Duas fichas (Cedente | Sacado)
// com endereço + dados bancários conhecidos, o card da liquidação com "onde
// liquidou" e os sinais do catálogo, e a decisão OK/Fraude/Não sei com trilha.
// A tabela de evidência (os N sacados do balcão) abre em toggle interno para
// não estourar a altura. Reusado pela curadoria e pelo raio-X.

"use client"

import * as React from "react"
import {
  RiAlarmWarningFill,
  RiBankLine,
  RiCheckLine,
  RiCloseLine,
  RiErrorWarningLine,
  RiFlagLine,
  RiHistoryLine,
  RiInformationLine,
  RiMapPin2Line,
  RiQuestionLine,
} from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { Dialog, DialogContent } from "@/components/tremor/Dialog"
import { Input } from "@/components/tremor/Input"
import type { DossieLiquidacao } from "@/lib/api-client"
import { useDossieLiquidacao, useTagLiquidacao } from "@/lib/hooks/risco"
import { cx } from "@/lib/utils"

// ── formatação ──────────────────────────────────────────────────────────────
const brl = (v: number) =>
  v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", minimumFractionDigits: 2 })
const fmtData = (iso: string | null) => (iso ? new Date(iso).toLocaleDateString("pt-BR") : "—")
const fmtDataHora = (iso: string) =>
  new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })

function fmtCnpj(doc: string | null): string {
  if (!doc) return ""
  const d = doc.replace(/\D/g, "").replace(/^0+/, "").padStart(14, "0")
  return d.length === 14
    ? `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`
    : doc
}

// Nome de banco enxuto: tira "Banco", parênteses e sufixos societários.
const _CUT = /\b(s\.?\/?a\.?|ltda|scmepp|dtvm|distribuidora|corretora|pactual|unibanco)\b.*/i
function bankShort(n: string | null): string {
  if (!n) return ""
  const base = n.replace(/\(.*?\)/g, "").replace(/^banco\s+/i, "").replace(_CUT, "").trim()
  const s = base || n
  return s.replace(/\S+/g, (w) => (w.length <= 3 ? w.toUpperCase() : w[0].toUpperCase() + w.slice(1).toLowerCase()))
}

function haQuanto(iso: string | null): string | null {
  if (!iso) return null
  const min = Math.max(0, Math.round((Date.now() - new Date(iso).getTime()) / 60000))
  if (min < 60) return `há ${min} min`
  const h = Math.round(min / 60)
  if (h < 48) return `há ${h} h`
  return `há ${Math.round(h / 24)} d`
}

const cidadeUf = (cidade: string | null, uf: string | null) =>
  cidade ? `${cidade}${uf ? `/${uf}` : ""}` : "—"

// ── tokens de cor do handoff (hex de handoff — política de iteração visual) ──
const ROLE = {
  cedente: "bg-[#EFF6FF] text-[#1E3A8A] dark:bg-blue-950/40 dark:text-blue-300",
  sacado: "bg-[#FEFCE8] text-[#713F12] dark:bg-amber-950/40 dark:text-amber-300",
  liquidacao: "bg-[#FEF2F2] text-[#7F1D1D] dark:bg-red-950/40 dark:text-red-300",
  onde: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
}
const SEV: Record<string, { cls: string; label: string }> = {
  critica: { cls: "bg-[#FEF2F2] text-[#7F1D1D] dark:bg-red-950/40 dark:text-red-300", label: "Crítica" },
  pendente: { cls: "bg-[#FEF2F2] text-[#7F1D1D] dark:bg-red-950/40 dark:text-red-300", label: "Crítica" },
  alta: { cls: "bg-[#FEFCE8] text-[#713F12] dark:bg-amber-950/40 dark:text-amber-300", label: "Alta" },
  media: { cls: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300", label: "Média" },
  baixa: { cls: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300", label: "Baixa" },
}

// ── átomos ──────────────────────────────────────────────────────────────────
function Pill({ children, className, icon: Icon }: {
  children: React.ReactNode
  className: string
  icon?: React.ComponentType<{ className?: string }>
}) {
  return (
    <span className={cx(
      "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide",
      className,
    )}>
      {Icon && <Icon className="size-3" />}
      {children}
    </span>
  )
}

const CAPTION = "text-[10px] font-semibold uppercase tracking-[0.05em] text-gray-400"

function Endereco({ logradouro, numero, bairro, cidade, uf }: {
  logradouro: string | null; numero: string | null; bairro: string | null
  cidade: string | null; uf: string | null
}) {
  const rua = [logradouro, numero].filter(Boolean).join(", ")
  const linha1 = [rua, bairro].filter(Boolean).join(" — ")
  return (
    <div className="mt-2.5">
      <div className={CAPTION}>Endereço</div>
      {linha1 && <div className="mt-0.5 truncate text-[12.5px] text-gray-600 dark:text-gray-400">{linha1}</div>}
      <div className="text-[13px] font-semibold text-gray-900 dark:text-gray-100">{cidadeUf(cidade, uf)}</div>
    </div>
  )
}

function LiqLine({ label, value, red }: { label: string; value: React.ReactNode; red?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-gray-100 py-1 last:border-0 dark:border-gray-800/60">
      <span className="shrink-0 text-[12px] text-gray-500">{label}</span>
      <span className={cx(
        "truncate text-right text-[12px] font-semibold tabular-nums",
        red ? "text-[#DC2626]" : "text-gray-900 dark:text-gray-100",
      )}>
        {value}
      </span>
    </div>
  )
}

// ── painel de evidência (sacados do balcão) — coluna da análise ──────────────
function EvidenciaPanel({ d }: { d: DossieLiquidacao }) {
  const conv = d.agencia.convergencia
  // Na matriz eletrônica (0001) "fora da praça" é ruído (todos aparecem em SP);
  // vira contexto neutro — concentração, não divergência.
  const eletronica = d.agencia.praca_eletronica
  if (!d.evidencia_sacados.length) return null
  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className={cx(CAPTION, "mb-2")}>
        Sacados que liquidam nesta {eletronica ? "matriz eletrônica" : "agência"}{conv ? ` (${conv.sacados})` : ""}
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto rounded border border-gray-100 dark:border-gray-800">
        <table className="w-full">
          <thead className="sticky top-0 bg-gray-50 dark:bg-gray-900">
            <tr className="text-left">
              <th className={cx(CAPTION, "px-2 py-1.5")}>Sacado</th>
              <th className={cx(CAPTION, "px-2 py-1.5")}>Praça</th>
              <th className={cx(CAPTION, "px-2 py-1.5 text-right")}>Títulos</th>
            </tr>
          </thead>
          <tbody>
            {d.evidencia_sacados.map((s, i) => {
              const atual = s.nome != null && s.nome === d.sacado_nome
              return (
                <tr key={i} className={cx(
                  "border-t border-gray-100 dark:border-gray-800/60",
                  atual && "bg-[#EFF6FF] dark:bg-blue-950/30",
                )}>
                  <td className={cx("truncate px-2 py-1 text-[12px]", atual ? "font-semibold text-[#1E3A8A] dark:text-blue-300" : "text-gray-900 dark:text-gray-100")}>
                    {s.nome ?? "—"}
                  </td>
                  <td className="px-2 py-1 text-[12px] text-gray-600 dark:text-gray-400">
                    {cidadeUf(s.cidade, s.uf)}
                    {!eletronica && s.fora && <span className="ml-1.5 rounded bg-[#FEFCE8] px-1 text-[10px] font-semibold text-[#B45309] dark:bg-amber-950/40">fora</span>}
                  </td>
                  <td className="px-2 py-1 text-right text-[12px] tabular-nums text-gray-600 dark:text-gray-400">{s.qtd}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      {conv && (
        <p className="mt-1.5 text-[11px] text-gray-500">
          <b className="text-gray-700 dark:text-gray-300">{conv.sacados} sacados</b>
          {eletronica ? " desta operação liquidam nesta matriz eletrônica" : ` · ${conv.fora} de fora da praça do balcão`}
        </p>
      )}
    </div>
  )
}

// ── corpo do modal ───────────────────────────────────────────────────────────
function Corpo({ d, onDecidir, onClose, saving }: {
  d: DossieLiquidacao
  onDecidir: (tag: "ok" | "fraude" | "neutro", nota: string) => void
  onClose: () => void
  saving: boolean
}) {
  const [nota, setNota] = React.useState("")
  const ag = d.agencia
  const produto = d.produto_nome ?? d.produto_sigla ?? "—"
  const classe = d.classificacao
  const critico = classe.nivel === "critico"
  const alto = classe.nivel === "alto"
  const riscoCls = critico
    ? "bg-[rgba(220,38,38,0.10)] text-[#DC2626]"
    : alto
      ? "bg-[#FEFCE8] text-[#B45309]"
      : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300"
  const ultimaTag = d.historico_curadoria[0]
  const sync = haQuanto(d.sincronizado_em)

  return (
    <div className="flex h-full flex-col">
      {/* ── Header ── */}
      <header className="flex items-start justify-between gap-4 border-b border-gray-200 px-6 py-4 dark:border-gray-800">
        <div className="min-w-0">
          <div className={CAPTION}>Curadoria de liquidação</div>
          <h2 className="mt-1 truncate text-[15px] font-semibold text-gray-900 dark:text-gray-50">
            {d.cedente_nome ?? "—"} <span className="text-gray-400">→</span> {d.sacado_nome ?? "—"}{" "}
            <span className="font-mono text-[12px] font-normal text-gray-500">· título {d.titulo_numero ?? d.titulo_id}</span>
          </h2>
        </div>
        <div className="flex shrink-0 items-start gap-4">
          <div className="text-right">
            <div className={cx(CAPTION, "mb-1")}>Classificação do sistema</div>
            <Pill className={riscoCls} icon={critico ? RiAlarmWarningFill : RiErrorWarningLine}>{classe.label}</Pill>
          </div>
          <button
            onClick={onClose}
            aria-label="Fechar"
            className="mt-0.5 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200"
          >
            <RiCloseLine className="size-5" />
          </button>
        </div>
      </header>

      {/* ── Corpo: 2 colunas — os fatos (esq) · a análise (dir) ── */}
      <div className="grid min-h-0 flex-1 grid-cols-[1.7fr_1fr] bg-gray-50 dark:bg-gray-950/40">
        {/* Coluna esquerda — fatos: identidades + a liquidação */}
        <div className="flex min-h-0 flex-col gap-3.5 overflow-y-auto p-4">
          {/* Fichas Cedente | Sacado */}
          <div className="grid grid-cols-2 gap-3.5">
          {/* Cedente */}
          <div className="rounded border border-gray-200 bg-white p-3.5 shadow-xs dark:border-gray-800 dark:bg-gray-900">
            <Pill className={ROLE.cedente}>Cedente</Pill>
            <p className="mt-1.5 truncate text-[14px] font-semibold text-gray-900 dark:text-gray-100" title={d.cedente_nome ?? undefined}>
              {d.cedente_nome ?? "—"}
            </p>
            <p className="font-mono text-[12px] text-gray-500">{fmtCnpj(d.cedente_documento)}</p>
            <Endereco logradouro={d.cedente_logradouro} numero={d.cedente_numero} bairro={d.cedente_bairro} cidade={d.cedente_cidade} uf={d.cedente_uf} />
            <div className="my-2.5 border-t border-gray-100 dark:border-gray-800" />
            <div className={CAPTION}>Contas bancárias conhecidas ({d.cedente_contas.length})</div>
            <table className="mt-1.5 w-full">
              <thead>
                <tr className="text-left">
                  <th className={cx(CAPTION, "pb-1 font-semibold")}>Banco</th>
                  <th className={cx(CAPTION, "pb-1 text-right font-semibold")}>Agência</th>
                  <th className={cx(CAPTION, "pb-1 text-right font-semibold")}>Qtd tít.</th>
                </tr>
              </thead>
              <tbody>
                {d.cedente_contas.length === 0 ? (
                  <tr><td colSpan={3} className="py-1 text-[12px] text-gray-400">Nenhuma conta cadastrada.</td></tr>
                ) : d.cedente_contas.map((c, i) => (
                  <tr key={i} className="border-t border-gray-100 dark:border-gray-800/60">
                    <td className="py-1 text-[12px] text-gray-900 dark:text-gray-100">
                      <span className="font-mono text-gray-500">{c.banco}</span> {bankShort(c.banco_nome)}
                    </td>
                    <td className="py-1 text-right font-mono text-[12px] tabular-nums text-gray-700 dark:text-gray-300">{c.agencia}</td>
                    <td className="py-1 text-right text-[12px] text-gray-400">—</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Sacado */}
          <div className="rounded border border-gray-200 bg-white p-3.5 shadow-xs dark:border-gray-800 dark:bg-gray-900">
            <Pill className={ROLE.sacado}>Sacado</Pill>
            <p className="mt-1.5 truncate text-[14px] font-semibold text-gray-900 dark:text-gray-100" title={d.sacado_nome ?? undefined}>
              {d.sacado_nome ?? "—"}
            </p>
            <p className="text-[12px] text-gray-400">quem deveria pagar o título</p>
            <Endereco logradouro={d.sacado_logradouro} numero={d.sacado_numero} bairro={d.sacado_bairro} cidade={d.sacado_cidade} uf={d.sacado_uf} />
            <div className="my-2.5 border-t border-gray-100 dark:border-gray-800" />
            <div className={CAPTION}>Histórico de liquidação</div>
            <table className="mt-1.5 w-full">
              <thead>
                <tr className="text-left">
                  <th className={cx(CAPTION, "pb-1 font-semibold")}>Banco · praça</th>
                  <th className={cx(CAPTION, "pb-1 text-right font-semibold")}>Agência</th>
                  <th className={cx(CAPTION, "pb-1 text-right font-semibold")}>Qtd tít.</th>
                </tr>
              </thead>
              <tbody>
                {d.sacado_historico.length === 0 ? (
                  <tr><td colSpan={3} className="py-1 text-[12px] text-gray-400">Sem histórico de liquidação.</td></tr>
                ) : d.sacado_historico.map((h, i) => (
                  <tr key={i} className="border-t border-gray-100 dark:border-gray-800/60">
                    <td className="py-1 text-[12px] text-gray-900 dark:text-gray-100">
                      <span className="font-mono text-gray-500">{h.banco}</span> {bankShort(h.banco_nome)}
                      {h.matriz
                        ? <span className="text-gray-400"> · matriz (liq. eletrônica)</span>
                        : h.cidade && <span className="text-gray-500"> · {[h.bairro, cidadeUf(h.cidade, h.uf)].filter(Boolean).join(", ")}</span>}
                    </td>
                    <td className="py-1 text-right font-mono text-[12px] tabular-nums text-gray-700 dark:text-gray-300">{h.agencia}</td>
                    <td className="py-1 text-right text-[12px] font-semibold tabular-nums text-gray-900 dark:text-gray-100">{h.qtd}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {d.sacado_fora_praca ? (
              <p className="mt-2 flex items-center gap-1 text-[11.5px] font-medium text-[#B45309] dark:text-amber-400">
                <RiErrorWarningLine className="size-3.5 shrink-0" />
                Todo o histórico fora da sua praça{d.sacado_liquida_em ? ` (liquida em ${d.sacado_liquida_em})` : ""}
              </p>
            ) : d.sacado_liquida_eletronico ? (
              <p className="mt-2 flex items-start gap-1 text-[11px] leading-snug text-gray-500">
                <RiInformationLine className="mt-0.5 size-3.5 shrink-0" />
                Liquida via matriz eletrônica (0001) — a cidade é a sede do banco, não uma praça física.
              </p>
            ) : null}
          </div>
        </div>

        {/* 2.2 Card Liquidação do título */}
        <div className="overflow-hidden rounded border border-[#FECACA] bg-white shadow-xs dark:border-red-900/50 dark:bg-gray-900">
          <div className="grid grid-cols-2">
            {/* esquerda: liquidação */}
            <div className="border-r border-gray-100 p-3.5 dark:border-gray-800">
              <Pill className={ROLE.liquidacao} icon={RiBankLine}>Liquidação do título</Pill>
              <div className="mt-2">
                <LiqLine label="Título" value={<span className="font-mono">{d.titulo_numero ?? d.titulo_id}</span>} />
                <LiqLine label="Valor" value={brl(d.valor)} />
                <LiqLine label="Data liquidação" value={fmtData(d.data_evento)} />
                <LiqLine label="Produto" value={produto} />
                <LiqLine label="Canal" value={d.canal === "bancaria" ? "Bancária" : d.canal} />
              </div>
            </div>
            {/* direita: onde liquidou */}
            <div className="p-3.5">
              <Pill className={ROLE.onde} icon={RiMapPin2Line}>Onde liquidou</Pill>
              <div className="mt-2">
                <LiqLine label="Banco" value={ag.banco ? `${bankShort(ag.banco_nome) || "Banco"} (${ag.banco})` : "—"} />
                <LiqLine label="Agência" value={<span>{ag.agencia}{ag.nome ? ` · ${ag.nome}` : ""}</span>} />
                <LiqLine label="Endereço" value={ag.endereco ? [ag.endereco, ag.bairro].filter(Boolean).join(" — ") : "—"} />
                {/* Praça em vermelho só quando é divergência REAL. Na matriz 0001
                    (liquidação eletrônica) a cidade é a sede do banco, não praça. */}
                <LiqLine label="Praça" value={cidadeUf(ag.cidade, ag.uf)} red={!ag.praca_eletronica} />
              </div>
              {ag.praca_eletronica && (
                <p className="mt-2 flex items-start gap-1 text-[11px] leading-snug text-gray-500">
                  <RiInformationLine className="mt-0.5 size-3.5 shrink-0" />
                  Agência-matriz 0001 — liquidação eletrônica. {cidadeUf(ag.cidade, ag.uf)} é a sede do banco, não a praça do pagamento; por isso não há sinal de praça.
                </p>
              )}
            </div>
          </div>

        </div>
        </div>

        {/* Coluna direita — análise: por que marcou + evidência do balcão */}
        <div className="flex min-h-0 flex-col gap-4 border-l border-gray-200 bg-white p-4 dark:border-gray-800 dark:bg-gray-900/40">
          <div>
            <div className={cx(CAPTION, "mb-2")}>Sinais — por que o sistema marcou</div>
            {d.sinais.length === 0 ? (
              <p className="text-[12px] text-gray-500">Nenhum sinal automático — revisão manual.</p>
            ) : (
              <div className="space-y-2">
                {d.sinais.map((s) => (
                  <div key={s.codigo} className="flex items-start gap-2.5">
                    <span className="mt-0.5 shrink-0 rounded bg-gray-100 px-1.5 py-0.5 font-mono text-[10px] text-gray-700 dark:bg-gray-800 dark:text-gray-300">
                      {s.codigo}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-[12px] font-semibold text-gray-900 dark:text-gray-100">{s.nome}</p>
                      {s.definicao && <p className="text-[12px] text-gray-600 dark:text-gray-400">{s.definicao}</p>}
                    </div>
                    <Pill className={cx((SEV[s.severidade] ?? SEV.media).cls, "shrink-0")}>
                      {(SEV[s.severidade] ?? SEV.media).label}
                    </Pill>
                  </div>
                ))}
              </div>
            )}
          </div>
          <EvidenciaPanel d={d} />
        </div>
      </div>

      {/* ── Proveniência + trilha ── */}
      <div className="flex items-center justify-between gap-4 border-t border-gray-200 bg-white px-6 py-2 dark:border-gray-800 dark:bg-gray-950">
        <span className="truncate text-[11px] text-gray-400">
          Fonte: wh_liquidacao · wh_conta_bancaria · ref_bacen_agencia{sync ? ` · última sync ${sync}` : ""}
        </span>
        <span className="flex shrink-0 items-center gap-1 text-[11px] text-gray-400">
          <RiHistoryLine className="size-3.5" />
          {ultimaTag
            ? `${ultimaTag.tag} · ${ultimaTag.autor ?? "—"} · ${fmtDataHora(ultimaTag.em)}${d.historico_curadoria.length > 1 ? ` (+${d.historico_curadoria.length - 1})` : ""}`
            : "Histórico de curadoria: nenhuma marcação ainda — a decisão registra data, hora e login"}
        </span>
      </div>

      {/* ── Footer de decisão ── */}
      <footer className="flex items-center gap-2 border-t border-gray-200 bg-white px-6 py-3 dark:border-gray-800 dark:bg-gray-950">
        <Input
          value={nota}
          onChange={(e) => setNota(e.target.value)}
          placeholder="Nota da decisão (opcional)"
          className="h-[30px] flex-1 text-[13px]"
        />
        <Button variant="secondary" disabled={saving} onClick={() => onDecidir("ok", nota)} className="h-[30px]">
          <RiCheckLine className="mr-1 size-4" /> OK · terceiro
        </Button>
        <Button variant="destructive" disabled={saving} onClick={() => onDecidir("fraude", nota)} className="h-[30px]">
          <RiFlagLine className="mr-1 size-4" /> Fraude · auto-liquidação
        </Button>
        <Button variant="ghost" disabled={saving} onClick={() => onDecidir("neutro", nota)} className="h-[30px]">
          <RiQuestionLine className="mr-1 size-4" /> Não sei
        </Button>
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
      <DialogContent className="h-[80vh] w-[70vw] max-w-[70vw] gap-0 p-0">
        {q.isPending ? (
          <div className="flex h-full items-center justify-center"><span className="text-[13px] text-gray-400">Carregando dossiê…</span></div>
        ) : q.isError || !q.data ? (
          <div className="flex h-full items-center justify-center"><span className="text-[13px] text-gray-500">Falha ao carregar o dossiê da liquidação.</span></div>
        ) : (
          <Corpo d={q.data} onDecidir={decidir} onClose={onClose} saving={tagMut.isPending} />
        )}
      </DialogContent>
    </Dialog>
  )
}
