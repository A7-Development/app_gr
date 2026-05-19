"use client"

/**
 * StatusHeadlineCompact — banda Z1 compacta da aba "Eventos do dia".
 *
 * Layout (refactor 2026-05-19):
 *
 *   [PL Cota Sub D0]  |  [Δ apurado (MEC)]  |  [Σ drivers]  |  [Não-explicado]  ...chips
 *
 * Os 3 deltas tornam visivel a qualidade da analise:
 *  - **Apurado (MEC)**: ΔPL Sub vindo de `wh_mec_evolucao_cotas` —
 *    `recon.delta_pl_cota_sub_real`. E a "verdade" do administrador (Singulare).
 *  - **Σ drivers**: soma dos 11 drivers do metodo gestor (variacao patrimonial
 *    por categoria) — `variacao_diaria.soma_drivers`. Quando o modelo fecha,
 *    Σ drivers ≡ Apurado MEC.
 *  - **Não-explicado**: residuo (`Apurado − Σ drivers`) + % da variacao apurada.
 *    `variacao_diaria.residuo_modelo`. Verde se |residuo|/|baseD1| < 0.1%,
 *    amber 0.1-0.5%, red >0.5%.
 *
 * Tone do numero primary (PL D0): vira `neutral` quando ha pendente COSIF OU
 * `data_quality.comparable=false`. Coerente com CLAUDE.md §14 explicabilidade
 * > inferencia. O sinal dos deltas (verde/rose) SEMPRE reflete o valor real
 * — pendencia afeta confianca no absoluto, nao no sinal.
 */

import * as React from "react"

import { cx } from "@/lib/utils"

const fmtBRL = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL",
  minimumFractionDigits: 2, maximumFractionDigits: 2,
})

const fmtBRLCompact = new Intl.NumberFormat("pt-BR", {
  style: "currency", currency: "BRL",
  notation: "compact", maximumFractionDigits: 2,
})

// 4 casas decimais na variacao % — Cota Sub mexe em centesimos de pp e
// arredondar pra 2 casas perde sinal relevante (ex.: 0,0017 vira 0,00).
const fmtPct = (v: number) => `${v >= 0 ? "+" : ""}${v.toFixed(4).replace(".", ",")}%`
const fmtPctAbs = (v: number) => `${Math.abs(v).toFixed(2).replace(".", ",")}%`

export type StatusHeadlineChip = {
  label: string
  tone:  "ok" | "warn" | "error" | "neutral"
}

export type StatusHeadlineCompactProps = {
  /** Data D0 formatada (ex.: "13/05/2026"). */
  dataD0?: string
  /** PL Cota Sub em D0. Quando indefinido, mostra "—". */
  plSubD0?: number
  /** Δ R$ apurado pelo MEC (= recon.delta_pl_cota_sub_real). */
  deltaApuradoMec?: number
  /** Δ % apurado pelo MEC (= recon.delta_pct_sobre_d1). */
  deltaApuradoPct?: number
  /** Σ R$ dos 11 drivers do metodo gestor (= variacao_diaria.soma_drivers). */
  somaDrivers?: number
  /** Σ % dos drivers (= soma_drivers / pl_d-1 * 100). */
  somaDriversPct?: number
  /** Residuo R$ = apurado MEC − Σ drivers (= variacao_diaria.residuo_modelo). */
  residuo?: number
  /** Base de comparacao para classificar o residuo (= pl_cota_sub_d1). */
  baseResiduo?: number
  /** Numero primary vira cinza (snapshot parcial OU pendentes COSIF). */
  forceNeutral?: boolean
  /** Chips de status no canto direito. */
  chips?: StatusHeadlineChip[]
  /** Loading visual quando true (skeleton bars). */
  loading?: boolean
}

export function StatusHeadlineCompact({
  dataD0,
  plSubD0,
  deltaApuradoMec,
  deltaApuradoPct,
  somaDrivers,
  somaDriversPct,
  residuo,
  baseResiduo,
  forceNeutral = false,
  chips = [],
  loading = false,
}: StatusHeadlineCompactProps) {
  // Residuo classificacao — pp do PL D-1.
  // < 1% -> aderente (verde); 1-5% -> divergencia leve (amber); > 5% -> divergencia grave (red).
  // Quando baseResiduo nao definido, considera apenas o |residuo| absoluto.
  const residuoSeverity = React.useMemo<"ok" | "warn" | "error" | "neutral">(() => {
    if (residuo == null || baseResiduo == null || baseResiduo === 0) return "neutral"
    const ratio = Math.abs(residuo) / Math.abs(baseResiduo)
    if (ratio < 0.001) return "ok"
    if (ratio < 0.005) return "warn"
    return "error"
  }, [residuo, baseResiduo])

  // % do residuo sobre a variacao apurada — "X% da variacao nao explicada".
  const residuoPctSobreApurado = React.useMemo<number | null>(() => {
    if (residuo == null || deltaApuradoMec == null || deltaApuradoMec === 0) return null
    return (residuo / deltaApuradoMec) * 100
  }, [residuo, deltaApuradoMec])

  return (
    <section
      className={cx(
        "flex flex-wrap items-center gap-x-6 gap-y-2 rounded border px-4 py-3",
        "border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950",
      )}
    >
      {/* Coluna 1: PL Sub D0 */}
      <HeadlineCol
        label={`PL Cota Sub${dataD0 ? ` · ${formatBrazilianDate(dataD0)}` : ""}`}
        loading={loading}
        primaryClass={cx(
          "text-[26px] font-semibold leading-[1.05] tracking-[-0.025em] tabular-nums",
          forceNeutral
            ? "text-gray-600 dark:text-gray-300"
            : "text-gray-900 dark:text-gray-50",
        )}
        skeletonWidth="w-44"
      >
        {plSubD0 != null ? fmtBRL.format(plSubD0) : "—"}
      </HeadlineCol>

      {/* Coluna 2: Apurado (MEC) */}
      <DeltaCol
        label="Variação apurada · MEC"
        valor={deltaApuradoMec}
        pct={deltaApuradoPct}
        loading={loading}
        divider
      />

      {/* Coluna 3: Σ dos drivers do metodo gestor */}
      <DeltaCol
        label="Soma dos drivers"
        valor={somaDrivers}
        pct={somaDriversPct}
        loading={loading}
        divider
      />

      {/* Coluna 4: Não-explicado (residuo) */}
      <ResiduoCol
        residuo={residuo}
        pctSobreApurado={residuoPctSobreApurado}
        severity={residuoSeverity}
        loading={loading}
      />

      {/* Chips no canto direito */}
      {chips.length > 0 && (
        <div className="ml-auto flex flex-wrap items-center gap-1.5">
          {chips.map((c, i) => (
            <ChipPill key={i} chip={c} />
          ))}
        </div>
      )}
    </section>
  )
}

// ─── Sub-componentes ──────────────────────────────────────────────────────

function HeadlineCol({
  label,
  loading,
  primaryClass,
  skeletonWidth,
  children,
}: {
  label:         string
  loading:       boolean
  primaryClass:  string
  skeletonWidth: string
  children:      React.ReactNode
}) {
  return (
    <div>
      <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
        {label}
      </div>
      {loading ? (
        <div className={cx("mt-1 h-[26px] animate-pulse rounded bg-gray-100 dark:bg-gray-800", skeletonWidth)} />
      ) : (
        <div className={cx("mt-0.5", primaryClass)}>{children}</div>
      )}
    </div>
  )
}

function DeltaCol({
  label,
  valor,
  pct,
  loading,
  divider = false,
}: {
  label:    string
  valor?:   number
  pct?:     number
  loading:  boolean
  divider?: boolean
}) {
  const toneCls =
    valor != null && valor >= 0
      ? "text-emerald-700 dark:text-emerald-400"
      : valor != null
      ? "text-rose-700 dark:text-rose-400"
      : "text-gray-400 dark:text-gray-600"

  const pctBg =
    pct == null
      ? "bg-gray-50 text-gray-500 dark:bg-gray-900 dark:text-gray-400"
      : pct >= 0
      ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400"
      : "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-400"

  return (
    <div className={cx(divider && "border-l border-gray-200 pl-4 dark:border-gray-800")}>
      <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
        {label}
      </div>
      {loading ? (
        <div className="mt-1 h-[20px] w-28 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
      ) : (
        <div className="mt-0.5 flex items-baseline gap-2">
          <span
            className={cx(
              "text-[18px] font-semibold leading-tight tracking-[-0.02em] tabular-nums",
              toneCls,
            )}
          >
            {valor != null
              ? `${valor >= 0 ? "+" : ""}${fmtBRLCompact.format(valor)}`
              : "—"}
          </span>
          <span
            className={cx(
              "inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-semibold tabular-nums",
              pctBg,
            )}
          >
            {pct != null ? fmtPct(pct) : "—"}
          </span>
        </div>
      )}
    </div>
  )
}

function ResiduoCol({
  residuo,
  pctSobreApurado,
  severity,
  loading,
}: {
  residuo?:         number
  pctSobreApurado?: number | null
  severity:         "ok" | "warn" | "error" | "neutral"
  loading:          boolean
}) {
  const valorCls = {
    ok:      "text-emerald-700 dark:text-emerald-400",
    warn:    "text-amber-700 dark:text-amber-400",
    error:   "text-rose-700 dark:text-rose-400",
    neutral: "text-gray-500 dark:text-gray-400",
  }[severity]

  const pctBg = {
    ok:      "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400",
    warn:    "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-400",
    error:   "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-400",
    neutral: "bg-gray-50 text-gray-500 dark:bg-gray-900 dark:text-gray-400",
  }[severity]

  return (
    <div className="border-l border-gray-200 pl-4 dark:border-gray-800">
      <div className="text-[10px] font-semibold uppercase tracking-[0.06em] text-gray-500 dark:text-gray-400">
        Não-explicado · resíduo
      </div>
      {loading ? (
        <div className="mt-1 h-[20px] w-28 animate-pulse rounded bg-gray-100 dark:bg-gray-800" />
      ) : (
        <div className="mt-0.5 flex items-baseline gap-2">
          <span
            className={cx(
              "text-[18px] font-semibold leading-tight tracking-[-0.02em] tabular-nums",
              valorCls,
            )}
          >
            {residuo != null
              ? `${residuo >= 0 ? "+" : ""}${fmtBRLCompact.format(residuo)}`
              : "—"}
          </span>
          {pctSobreApurado != null && (
            <span
              className={cx(
                "inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-semibold tabular-nums",
                pctBg,
              )}
              title="Resíduo como % da variação apurada (MEC)"
            >
              {fmtPctAbs(pctSobreApurado)} da var.
            </span>
          )}
        </div>
      )}
    </div>
  )
}

function ChipPill({ chip }: { chip: StatusHeadlineChip }) {
  const palette = {
    ok:      "bg-emerald-50 text-emerald-700 border-emerald-100 dark:bg-emerald-500/10 dark:text-emerald-300 dark:border-emerald-900/40",
    warn:    "bg-amber-50 text-amber-700 border-amber-100 dark:bg-amber-500/10 dark:text-amber-300 dark:border-amber-900/40",
    error:   "bg-red-50 text-red-700 border-red-100 dark:bg-red-500/10 dark:text-red-300 dark:border-red-900/40",
    neutral: "bg-gray-50 text-gray-700 border-gray-200 dark:bg-gray-900 dark:text-gray-300 dark:border-gray-800",
  }[chip.tone]
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded border px-2 py-0.5 text-[11px] font-medium leading-tight",
        palette,
      )}
    >
      <span
        className={cx(
          "inline-block size-1.5 rounded-full",
          {
            ok:      "bg-emerald-500",
            warn:    "bg-amber-500",
            error:   "bg-red-500",
            neutral: "bg-gray-400",
          }[chip.tone],
        )}
        aria-hidden="true"
      />
      {chip.label}
    </span>
  )
}

function formatBrazilianDate(iso: string): string {
  // ISO "YYYY-MM-DD" -> "DD/MM/YYYY". Tolera valor ja formatado.
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso)
  if (!m) return iso
  return `${m[3]}/${m[2]}/${m[1]}`
}
