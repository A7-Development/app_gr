"use client"

/**
 * ResumoConciliacaoCharts — "Cobertura de cobrança" (ao lado da tabela-resumo).
 *
 * Redesenho 2026-06-10 (escolha Ricardo, Opção A híbrida): o card responde
 * "quanto da carteira aberta está protegida por cobrança bancária — e onde
 * está o buraco?". Anatomia canônica de chart card (operacoes4): eyebrow
 * uppercase + KPI 20px + subtitle.
 *
 *   - KPI: % do valor da carteira aberta (lado BITFIN) com boleto ATIVO no
 *     banco (conciliado + divergências — banco confirmou a entrada).
 *   - Barra 100% da carteira: coberto / enviado-aguardando / sem boleto.
 *     A decomposição soma o total on-screen (§14.6).
 *   - Linhas por banco (clicáveis → toggle do filtro Banco): valor coberto,
 *     valor "no limbo" (enviado sem confirmação) e FRESCOR do retorno por
 *     banco — banco parado ganha ⚠ mesmo com o frescor global em dia.
 *
 * Lê as MESMAS linhas filtradas da página (re-escopo total, §7.2/§14.6).
 */

import * as React from "react"
import { RiAlertFill } from "@remixicon/react"

import { cx } from "@/lib/utils"
import { Card } from "@/components/tremor/Card"
import { cardTokens } from "@/design-system/tokens/card"
import type {
  FrescorBancoConciliacao,
  LinhaConciliacaoBoleto,
} from "@/lib/api-client"

const fmtInt = new Intl.NumberFormat("pt-BR")

/** R$ compacto (39,6M / 812,4k / 950). */
function fmtBRLcompact(v: number): string {
  const abs = Math.abs(v)
  if (abs >= 1_000_000) return `R$ ${(v / 1_000_000).toFixed(1).replace(".", ",")}M`
  if (abs >= 1_000) return `R$ ${(v / 1_000).toFixed(1).replace(".", ",")}k`
  return `R$ ${fmtInt.format(Math.round(v))}`
}

function fmtDateBR(iso: string | null | undefined): string {
  if (!iso) return "—"
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  return m ? `${m[3]}/${m[2]}` : iso
}

/** Dias corridos desde uma data ISO (YYYY-MM-DD). */
function diasDesde(iso: string): number | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!m) return null
  const d = new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3]))
  return Math.max(0, Math.floor((Date.now() - d.getTime()) / 86_400_000))
}

// Rotulo amigavel do banco (linhas trazem "bradesco"/"vortx"/"bmp"/"itau").
const BANCO_LABEL: Record<string, string> = {
  bradesco: "Bradesco",
  vortx: "Vórtx",
  bmp: "BMP",
  itau: "Itaú",
}

// Boleto ATIVO no banco (entrada confirmada) — incl. divergências.
const COBERTO = new Set(["conciliado", "divergencia_valor", "divergencia_vencimento"])

type BancoAgg = { banco: string; coberto: number; limbo: number }

export function ResumoConciliacaoCharts({
  linhas,
  frescores,
  bancoFilter,
  onBancoToggle,
}: {
  linhas: LinhaConciliacaoBoleto[]
  /** Frescor do retorno por banco (backend). */
  frescores: FrescorBancoConciliacao[]
  /** Filtro Banco ativo na página (raw: "bradesco"/"vortx"/...). */
  bancoFilter: string[]
  /** Clique na linha do banco → toggle do filtro Banco da página. */
  onBancoToggle: (banco: string) => void
}) {
  // Carteira aberta = lado BITFIN (valor_bitfin). "Só em banco" fica fora por
  // construção (não tem valor BITFIN — não é carteira aberta).
  const agg = React.useMemo(() => {
    let coberto = 0
    let limbo = 0
    let semBoleto = 0
    const porBanco = new Map<string, BancoAgg>()
    for (const l of linhas) {
      const v = l.valor_bitfin ?? 0
      if (v === 0) continue
      if (COBERTO.has(l.status)) {
        coberto += v
        if (l.banco) {
          const g = porBanco.get(l.banco) ?? { banco: l.banco, coberto: 0, limbo: 0 }
          g.coberto += v
          porBanco.set(l.banco, g)
        }
      } else if (l.status === "enviado_nao_confirmado") {
        limbo += v
        if (l.banco) {
          const g = porBanco.get(l.banco) ?? { banco: l.banco, coberto: 0, limbo: 0 }
          g.limbo += v
          porBanco.set(l.banco, g)
        }
      } else {
        semBoleto += v // so_em_bitfin: nunca foi a banco nenhum
      }
    }
    const total = coberto + limbo + semBoleto
    return {
      coberto,
      limbo,
      semBoleto,
      total,
      bancos: Array.from(porBanco.values()).sort((a, b) => b.coberto - a.coberto),
    }
  }, [linhas])

  const frescorPorBanco = React.useMemo(() => {
    const m = new Map<string, string>()
    for (const f of frescores) m.set(f.banco, f.retorno_ate)
    return m
  }, [frescores])

  if (agg.total === 0) {
    return (
      <Card className={cx(cardTokens.body, "flex items-center justify-center")}>
        <p className="text-sm text-gray-400 dark:text-gray-600">Sem dados no escopo.</p>
      </Card>
    )
  }

  const pct = (v: number) => (agg.total > 0 ? (v / agg.total) * 100 : 0)
  const pctCoberto = pct(agg.coberto)

  return (
    <Card className={cx(cardTokens.body, "flex flex-col")}>
      {/* Header canônico (operacoes4): eyebrow + KPI + subtitle */}
      <header className="pb-3">
        <div className="text-[10.5px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
          Cobrança bancária · Carteira aberta
        </div>
        <p className="mt-1 flex flex-wrap items-baseline gap-x-2 tabular-nums">
          <span className="text-[20px] font-semibold leading-none tracking-tight text-gray-900 dark:text-gray-50">
            {pctCoberto.toFixed(1).replace(".", ",")}%
          </span>
          <span className="text-[12px] text-gray-500 dark:text-gray-400">
            {fmtBRLcompact(agg.coberto)} de {fmtBRLcompact(agg.total)} com boleto ativo no banco
          </span>
        </p>
      </header>

      {/* Barra 100% da carteira aberta: coberto / enviado / sem boleto.
          Decomposição soma o total on-screen (§14.6). */}
      <div
        className="flex h-2.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800"
        title={`Coberto ${fmtBRLcompact(agg.coberto)} · Enviado aguardando ${fmtBRLcompact(agg.limbo)} · Sem boleto ${fmtBRLcompact(agg.semBoleto)}`}
      >
        <div className="h-full bg-emerald-500" style={{ width: `${pct(agg.coberto)}%` }} />
        <div className="h-full bg-amber-400" style={{ width: `${pct(agg.limbo)}%` }} />
      </div>
      <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-gray-500 dark:text-gray-400">
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm bg-emerald-500" aria-hidden="true" />
          coberto {fmtBRLcompact(agg.coberto)}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm bg-amber-400" aria-hidden="true" />
          enviado, aguardando {fmtBRLcompact(agg.limbo)}
        </span>
        <span className="flex items-center gap-1.5">
          <span className="size-2.5 rounded-sm bg-gray-200 dark:bg-gray-700" aria-hidden="true" />
          sem boleto {fmtBRLcompact(agg.semBoleto)}
        </span>
      </div>

      {/* Por banco: valor coberto + limbo + frescor do retorno. Linha clicável
          = toggle do filtro Banco da página. */}
      <ul className="mt-4 flex-1 space-y-1 border-t border-gray-100 pt-3 dark:border-gray-800">
        {agg.bancos.map((g) => {
          const retornoAte = frescorPorBanco.get(g.banco)
          const dias = retornoAte ? diasDesde(retornoAte) : null
          const stale = dias !== null && dias >= 4
          const selecionado = bancoFilter.includes(g.banco)
          return (
            <li key={g.banco}>
              <button
                type="button"
                onClick={() => onBancoToggle(g.banco)}
                title={`${selecionado ? "Remover" : "Aplicar"} filtro: ${BANCO_LABEL[g.banco] ?? g.banco}`}
                className={cx(
                  "flex w-full items-baseline justify-between gap-2 rounded px-1.5 py-1 text-left text-[12px] transition-colors",
                  "hover:bg-gray-50 dark:hover:bg-gray-900",
                  selecionado && "bg-blue-50 dark:bg-blue-500/10",
                )}
              >
                <span className="flex min-w-0 items-baseline gap-1.5">
                  <span
                    className={cx(
                      "truncate font-medium",
                      selecionado
                        ? "text-blue-700 dark:text-blue-300"
                        : "text-gray-700 dark:text-gray-300",
                    )}
                  >
                    {BANCO_LABEL[g.banco] ?? g.banco}
                  </span>
                  <span className="shrink-0 tabular-nums text-gray-500 dark:text-gray-400">
                    {fmtBRLcompact(g.coberto)}
                  </span>
                  {g.limbo > 0 && (
                    <span
                      className="shrink-0 tabular-nums text-amber-600 dark:text-amber-400"
                      title="Enviado ao banco, sem confirmação de entrada"
                    >
                      · {fmtBRLcompact(g.limbo)} aguardando
                    </span>
                  )}
                </span>
                {retornoAte && (
                  <span
                    className={cx(
                      "flex shrink-0 items-center gap-1 tabular-nums text-[11px]",
                      stale
                        ? "font-medium text-amber-600 dark:text-amber-400"
                        : "text-gray-400 dark:text-gray-500",
                    )}
                    title={
                      stale
                        ? `Último retorno processado há ${dias} dias — verificar a fonte de arquivos deste banco`
                        : "Data do último retorno processado deste banco"
                    }
                  >
                    {stale && <RiAlertFill className="size-3" aria-hidden="true" />}
                    retorno até {fmtDateBR(retornoAte)}
                  </span>
                )}
              </button>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}
