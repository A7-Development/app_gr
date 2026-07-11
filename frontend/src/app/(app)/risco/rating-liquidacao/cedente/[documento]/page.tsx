// src/app/(app)/risco/rating-liquidacao/cedente/[documento]/page.tsx
//
// Raio-X do cedente — dossiê profundo do perfil de liquidação (rating v2 PiT).
// "O filme, não a foto": a evolução mensal é a peça central (layout A,
// escolhido 2026-07-11). Zonas: Z1 veredito+tendência · Z2 filme mensal ·
// Z3 por que a nota (sinais do catálogo) · Z4 onde o dinheiro cai (agências
// com endereço) · Z5 concentração por sacado (pares) · Z6 CTA curadoria.
// MOTIVO: página dedicada (novo foco de trabalho → rota, §navegação); o
// filme é div-based (sem chart lib) para leitura densa e imediata.

"use client"

import * as React from "react"
import { useParams, useRouter } from "next/navigation"
import {
  RiArrowLeftLine,
  RiBankLine,
  RiCheckboxCircleLine,
  RiMapPin2Line,
} from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import { KpiBand, PageHeader } from "@/design-system/components"
import type { KpiBandItem } from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import type { RaioXFilmeMes } from "@/lib/api-client"
import { useRaioXCedente, useRatingLiquidacaoPares } from "@/lib/hooks/risco"
import { cx } from "@/lib/utils"

const brl = (v: number) =>
  v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 })

const GRADE_BADGE: Record<string, string> = {
  A: tableTokens.badgeSuccess,
  B: tableTokens.badgeSuccess,
  C: tableTokens.badgeWarning,
  D: tableTokens.badgeDanger,
  E: tableTokens.badgeDanger,
  NC: tableTokens.badgeNeutral,
}
const SEV_BADGE: Record<string, string> = {
  critica: tableTokens.badgeDanger,
  pendente: tableTokens.badgeWarning,
  alta: tableTokens.badgeWarning,
  media: tableTokens.badgeNeutral,
  baixa: tableTokens.badgeNeutral,
}

// ── Z2 · O FILME (série mensal, div-based) ──────────────────────────────────
function Filme({ meses }: { meses: RaioXFilmeMes[] }) {
  const maxValor = Math.max(1, ...meses.map((m) => m.valor))
  return (
    <Card className="p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h3 className={tableTokens.cellStrong}>O filme — evolução mês a mês</h3>
        <span className={tableTokens.cellMuted}>
          barra = valor liquidado · linha = % via boleto · ● = liquidações com sinal crítico
        </span>
      </div>
      <div className="flex items-end gap-2 overflow-x-auto pb-2">
        {meses.map((m) => {
          const alturaBarra = Math.round((m.valor / maxValor) * 80) + 4
          const boletoPct = Math.round(m.via_boleto * 100)
          return (
            <div key={m.competencia} className="flex min-w-[52px] flex-1 flex-col items-center gap-1">
              {m.n_critico > 0 && (
                <span
                  className="text-[11px] font-semibold text-red-600 dark:text-red-400"
                  title={`${m.n_critico} liquidações com sinal crítico`}
                >
                  ●{m.n_critico}
                </span>
              )}
              <div className="flex h-[90px] w-full items-end justify-center">
                <div
                  className={cx(
                    "w-6 rounded-t",
                    m.n_critico > 0 ? "bg-red-400 dark:bg-red-500/70" : "bg-blue-400 dark:bg-blue-500/60",
                  )}
                  style={{ height: `${alturaBarra}px` }}
                  title={`${m.competencia}: ${brl(m.valor)} · ${m.n_eventos} liquidações`}
                />
              </div>
              <span
                className={cx(
                  "text-[11px] tabular-nums",
                  boletoPct < 50 ? "text-amber-600 dark:text-amber-400" : "text-gray-500",
                )}
                title="% via boleto no mês (quanto menor, menos conferível)"
              >
                {boletoPct}%
              </span>
              <span className={cx(tableTokens.cellMuted, "text-[10px]")}>
                {m.competencia.slice(2)}
              </span>
            </div>
          )
        })}
      </div>
    </Card>
  )
}

export default function RaioXCedentePage() {
  const router = useRouter()
  const params = useParams<{ documento: string }>()
  const documento = params.documento
  const q = useRaioXCedente(documento)
  const pares = useRatingLiquidacaoPares(documento)
  const d = q.data

  const kpis: KpiBandItem[] = React.useMemo(() => {
    if (!d) return []
    const dias = d.dias_ultimo_critico
    return [
      { eyebrow: "RATING (PONTO NO TEMPO)", value: d.grade, sub: d.score != null ? `score ${d.score.toFixed(0)}` : "sem score" },
      {
        eyebrow: "ALERTA / WATCHLIST",
        value: d.watchlist ? "ATIVO" : d.critico_historico ? "cicatriz" : "—",
        sub: dias != null ? `último crítico há ${dias}d` : "sem crítico",
      },
      { eyebrow: "VIA BOLETO", value: `${Math.round(d.cobertura * 100)}%`, sub: "do valor liquidado (conferível)" },
      { eyebrow: "TÍTULOS LIQUIDADOS 12M", value: d.n_desfechos.toLocaleString("pt-BR"), sub: brl(d.valor_desfechos) },
      { eyebrow: "PENDÊNCIAS DE CURADORIA", value: d.pendencias_curadoria.toLocaleString("pt-BR"), sub: "aguardando validação" },
    ]
  }, [d])

  if (q.isPending) {
    return <div className="p-6"><span className={tableTokens.cellMuted}>Carregando raio-X…</span></div>
  }
  if (q.isError || !d) {
    return (
      <div className="flex flex-col items-start gap-3 p-6">
        <span className={tableTokens.cellSecondary}>Cedente sem rating calculado ou falha ao carregar.</span>
        <Button variant="secondary" onClick={() => router.push("/risco/rating-liquidacao")}>Voltar ao ranking</Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-5 px-6 pt-5 pb-8">
      <button
        onClick={() => router.push("/risco/rating-liquidacao")}
        className={cx(tableTokens.cellSecondary, "flex w-fit items-center gap-1 hover:text-blue-600")}
      >
        <RiArrowLeftLine className="size-4" /> Ranking de liquidação
      </button>

      {/* Z1 · Veredito */}
      <PageHeader
        title={d.cedente_nome ?? d.cedente_documento}
        subtitle="Risco · Liquidações · Raio-X do cedente"
        info="Dossiê profundo do perfil de liquidação. Rating v2 point-in-time: recência pesa mais (half-life 90d). Watchlist = crítico nos últimos 90 dias (fogo ativo) vs cicatriz (crítico velho já dissolvido). O filme mostra a evolução; as agências mostram onde o dinheiro cai."
        actions={
          <div className="flex items-center gap-2">
            <span className={cx(tableTokens.badge, GRADE_BADGE[d.grade] ?? tableTokens.badgeNeutral, "text-sm")}>
              {d.grade === "NC" ? "Sem classificação" : `Rating ${d.grade}`}
            </span>
            {d.watchlist && (
              <span className={cx(tableTokens.badge, tableTokens.badgeDanger)} title="Sinal crítico nos últimos 90 dias">
                watchlist ativo
              </span>
            )}
          </div>
        }
      />

      <KpiBand items={kpis} />

      {/* Z2 · O filme */}
      <Filme meses={d.filme} />

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
        {/* Z3 · Por que a nota */}
        <Card className="p-4">
          <h3 className={cx(tableTokens.cellStrong, "mb-3")}>Por que a nota — sinais acesos</h3>
          <div className="space-y-2">
            {d.sinais.map((s) => (
              <div key={s.codigo} className="flex items-start gap-2 border-b border-gray-100 pb-2 dark:border-gray-800/60">
                <span className={cx(tableTokens.badge, SEV_BADGE[s.severidade] ?? tableTokens.badgeNeutral, "shrink-0")}>
                  {s.codigo}·{s.n}
                </span>
                <div className="min-w-0">
                  <p className={tableTokens.cellText}>{s.nome}</p>
                  {s.definicao && <p className={cx(tableTokens.cellMuted, "text-[11px]")}>{s.definicao}</p>}
                </div>
              </div>
            ))}
            {d.sinais.length === 0 && <p className={tableTokens.cellMuted}>Nenhum sinal aceso.</p>}
          </div>
        </Card>

        {/* Z4 · Onde o dinheiro cai */}
        <Card className="p-4">
          <div className="mb-3 flex items-center gap-2">
            <RiBankLine className="size-4 text-gray-500" />
            <h3 className={tableTokens.cellStrong}>Onde o dinheiro cai — agências</h3>
          </div>
          <div className="max-h-[420px] space-y-2 overflow-y-auto">
            {d.agencias.slice(0, 20).map((a, i) => (
              <div key={`${a.banco}-${a.agencia}-${i}`} className="border-b border-gray-100 pb-2 dark:border-gray-800/60">
                <div className="flex items-baseline justify-between gap-2">
                  <span className={cx(tableTokens.cellText, "truncate")}>
                    {a.banco}/{a.agencia} · {a.nome ?? "(agência não resolvida)"}
                  </span>
                  <span className={cx(tableTokens.cellNumber, "shrink-0")}>{brl(a.valor)}</span>
                </div>
                <div className="flex flex-wrap items-center gap-2">
                  {a.cidade && (
                    <span className={cx(tableTokens.cellMuted, "text-[11px] inline-flex items-center gap-0.5")}>
                      <RiMapPin2Line className="size-3" />
                      {a.cidade}/{a.uf}
                      {a.endereco ? ` · ${a.endereco}` : ""}
                    </span>
                  )}
                  <span className={cx(tableTokens.cellMuted, "text-[11px]")}>{a.n} tít.</span>
                  {a.conta_do_cedente && (
                    <span className={cx(tableTokens.badge, tableTokens.badgeDanger)} title="É a agência onde o cedente tem conta">
                      conta do cedente
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* Z5 · Concentração por sacado */}
      <Card className="p-4">
        <h3 className={cx(tableTokens.cellStrong, "mb-3")}>Concentração por sacado — os pares (pior primeiro)</h3>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="border-b border-gray-200 text-left dark:border-gray-800">
                <th className={tableTokens.header}>Sacado</th>
                <th className={tableTokens.header}>Rating</th>
                <th className={cx(tableTokens.header, "text-right")}>Score</th>
                <th className={cx(tableTokens.header, "text-right")}>Títulos</th>
                <th className={cx(tableTokens.header, "text-right")}>Valor</th>
              </tr>
            </thead>
            <tbody>
              {(pares.data?.rows ?? []).slice(0, 30).map((p) => (
                <tr key={p.sacado_documento ?? ""} className="h-8 border-b border-gray-100 dark:border-gray-800/60">
                  <td className={cx(tableTokens.cellText, "max-w-[260px] truncate")} title={p.sacado_nome ?? undefined}>
                    {p.sacado_nome ?? p.sacado_documento}
                  </td>
                  <td>
                    <span className={cx(tableTokens.badge, GRADE_BADGE[p.grade] ?? tableTokens.badgeNeutral)}>{p.grade}</span>
                  </td>
                  <td className={cx(tableTokens.cellNumber, "text-right")}>{p.score != null ? p.score.toFixed(0) : "—"}</td>
                  <td className={cx(tableTokens.cellNumberSecondary, "text-right")}>{p.n_desfechos}</td>
                  <td className={cx(tableTokens.cellNumber, "text-right")}>{brl(p.valor_desfechos)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Z6 · Curadoria */}
      <Card className="flex items-center justify-between gap-4 p-4">
        <div className="flex items-center gap-2">
          <RiCheckboxCircleLine className="size-5 text-blue-600" />
          <div>
            <p className={tableTokens.cellStrong}>Curar as liquidações deste cedente</p>
            <p className={tableTokens.cellMuted}>
              {d.pendencias_curadoria > 0
                ? `${d.pendencias_curadoria} liquidação(ões) aguardando validação humana (mesma-cidade). Valide ou confirme cada uma — a nota se corrige.`
                : "Abrir a fila de curadoria filtrada por este cedente para revisar título a título."}
            </p>
          </div>
        </div>
        <Button
          onClick={() =>
            router.push(`/risco/curadoria-liquidacoes?cedente=${encodeURIComponent(d.cedente_nome ?? d.cedente_documento)}`)
          }
        >
          Abrir curadoria
        </Button>
      </Card>
    </div>
  )
}
