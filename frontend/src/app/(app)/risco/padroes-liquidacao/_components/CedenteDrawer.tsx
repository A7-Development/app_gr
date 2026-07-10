// Drawer do cedente — a "resolução de foco": a narrativa determinística (a
// história de UM cedente, com números reais) + um resumo compacto dos sinais.
//
// REGRA DURA (Ricardo): o conteúdo NUNCA rola — cabe sempre na altura da
// janela. Por isso é um resumo curado, não a base inteira. O detalhe extremo
// (todas as liquidações) abre numa janela dedicada pelo botão do rodapé.

import { RiArrowRightLine } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { tableTokens } from "@/design-system/tokens/table"
import type { CedentePerfilRow } from "@/lib/api-client"
import { cx } from "@/lib/utils"
import { ReasonChips, SeverityPill } from "./chips"
import { narrativa, severidade } from "./leitura"

const brl = (v: number) =>
  v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", maximumFractionDigits: 0 })

const pct = (n: number, total: number) => (total > 0 ? Math.round((100 * n) / total) : 0)

// Mix de canal por segmento (banco tradicional = resto). Barra compacta.
const CANAL: { key: string; label: string; cor: string }[] = [
  { key: "_banco", label: "Banco tradicional", cor: "bg-gray-300 dark:bg-gray-600" },
  { key: "banco_digital", label: "Banco digital", cor: "bg-blue-500" },
  { key: "cooperativa", label: "Cooperativa", cor: "bg-sky-500" },
  { key: "ip", label: "IP", cor: "bg-violet-500" },
  { key: "scd", label: "SCD", cor: "bg-teal-500" },
  { key: "financeira", label: "Financeira", cor: "bg-amber-500" },
]

function Stat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className={tableTokens.header}>{label}</span>
      <span className={cx(tableTokens.cellStrong, "text-[13px]")}>{value}</span>
      {hint && <span className={tableTokens.cellMuted}>{hint}</span>}
    </div>
  )
}

export function CedenteDrawerBody({
  row,
  janelaLabel,
  onVerLiquidacoes,
}: {
  row: CedentePerfilRow
  janelaLabel: string
  onVerLiquidacoes: () => void
}) {
  const total = row.n_liq || 1
  const seg = { ...row.segmentos } as Record<string, number>
  const somaSeg = CANAL.slice(1).reduce((a, c) => a + (seg[c.key] ?? 0), 0)
  seg._banco = Math.max(0, row.n_liq - somaSeg)

  const dias =
    row.ultima_liq !== null
      ? Math.floor((Date.now() - new Date(row.ultima_liq).getTime()) / 86_400_000)
      : null
  const recencia = dias === null ? "—" : dias <= 0 ? "hoje" : `há ${dias}d`
  const deltaTxt =
    row.cedente_novo
      ? "novo na janela"
      : row.delta_alerta === null || row.delta_alerta === 0
        ? "estável"
        : `${row.delta_alerta > 0 ? "+" : ""}${row.delta_alerta} vs janela anterior`

  return (
    <div className="flex h-full flex-col gap-4 p-6">
      {/* topo: severidade + doc + janela */}
      <div className="flex items-center justify-between gap-3">
        <SeverityPill sev={severidade(row)} />
        <span className={tableTokens.cellSecondary}>
          {row.cedente_documento} · janela {janelaLabel}
        </span>
      </div>

      {/* narrativa determinística (a história, com números reais) */}
      <p className="text-[13.5px] leading-relaxed text-gray-700 dark:text-gray-200">
        {narrativa(row)}
      </p>

      {/* reason chips */}
      <div className="flex flex-col gap-1.5">
        <span className={tableTokens.header}>Drivers</span>
        <ReasonChips row={row} />
      </div>

      {/* números-chave (grade compacta, sem rolagem) */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-3 border-t border-gray-100 pt-4 dark:border-gray-800">
        <Stat label="Liquidações" value={row.n_liq.toLocaleString("pt-BR")} hint={brl(row.valor)} />
        <Stat
          label="Alertas (regra dura)"
          value={row.n_alerta.toLocaleString("pt-BR")}
          hint={
            row.n_alerta > 0
              ? `${row.n_alerta_multicedente} multi-cedente · ${row.n_alerta_conta} conta`
              : "sem alerta"
          }
        />
        <Stat
          label="Conta do cedente"
          value={`${row.sinais.conta_cedente ?? 0} de ${row.n_liq}`}
          hint={`${pct(row.sinais.conta_cedente ?? 0, total)}% — o maior red flag`}
        />
        <Stat
          label="Fora do sacado, na praça do cedente"
          value={`${row.sinais.praca_cedente ?? 0} de ${row.n_liq}`}
          hint={`${pct(row.sinais.praca_cedente ?? 0, total)}% — assinatura geográfica de captura`}
        />
        <Stat
          label="Multi-sacado · fora do padrão"
          value={`${pct(row.sinais.multi_sacado ?? 0, total)}% · ${pct(row.sinais.fora_padrao ?? 0, total)}%`}
          hint={`fora do sacado (outra praça) ${pct(Math.max(0, (row.sinais.fora_praca ?? 0) - (row.sinais.praca_cedente ?? 0)), total)}%`}
        />
        <Stat label="Recência · Δ" value={recencia} hint={deltaTxt} />
      </div>

      {/* canal por segmento (mix compacto) */}
      <div className="flex flex-col gap-1.5">
        <span className={tableTokens.header}>Canal (segmento Bacen)</span>
        <div
          className="flex h-3 w-full overflow-hidden rounded-sm"
          title={CANAL.map((c) => `${c.label}: ${seg[c.key] ?? 0}`).join(" · ")}
        >
          {CANAL.map((c) => {
            const n = seg[c.key] ?? 0
            if (!n) return null
            return <div key={c.key} className={c.cor} style={{ width: `${(100 * n) / total}%` }} />
          })}
        </div>
        <div className="flex flex-wrap gap-x-3 gap-y-0.5">
          {CANAL.filter((c) => (seg[c.key] ?? 0) > 0).map((c) => (
            <span key={c.key} className={tableTokens.cellMuted}>
              <span className={cx("mr-1 inline-block size-2 rounded-[2px] align-middle", c.cor)} />
              {c.label} {seg[c.key]}
            </span>
          ))}
        </div>
      </div>

      {/* rodapé fixo: botão pro detalhe extremo (janela dedicada futura) */}
      <div className="mt-auto border-t border-gray-100 pt-4 dark:border-gray-800">
        <Button variant="secondary" className="w-full justify-center" onClick={onVerLiquidacoes}>
          Ver liquidações do cedente
          <RiArrowRightLine className="ml-1.5 size-4" aria-hidden />
        </Button>
        <p className={cx(tableTokens.cellMuted, "mt-2 text-center")}>
          Abre o detalhe das liquidações deste cedente
        </p>
      </div>
    </div>
  )
}
