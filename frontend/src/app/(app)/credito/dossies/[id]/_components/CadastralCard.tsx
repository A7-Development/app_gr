// CadastralCard — card "Dados cadastrais coletados" (silver, white-label).
//
// Lê GET /dossies/{id}/cadastral (mesma fonte que a read-tool do agente usa).
// Mostra ao analista o que a consulta oficial trouxe — sem qualquer
// identidade de vendor (white-label).

"use client"

import { useQuery } from "@tanstack/react-query"
import { RiBuilding4Line } from "@remixicon/react"

import { tableTokens } from "@/design-system/tokens/table"
import { credito } from "@/lib/credito-client"
import { cx } from "@/lib/utils"

const brl = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" })

function fmtBRL(n: number | null): string {
  return typeof n === "number" && Number.isFinite(n) ? brl.format(n) : "—"
}

function fmtDate(s: string | null): string {
  if (!s) return "—"
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(s)
  return m ? `${m[3]}/${m[2]}/${m[1]}` : s
}

const SIT_TONE: Record<string, string> = {
  ativa: "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300",
}

export function CadastralCard({ dossierId }: { dossierId: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["credito", "cadastral", dossierId],
    queryFn: () => credito.dossies.cadastral(dossierId),
    retry: false,
  })

  if (isLoading) {
    return <p className={tableTokens.cellSecondary}>Carregando dados cadastrais…</p>
  }
  if (isError || !data) {
    return (
      <p className={tableTokens.cellSecondary}>
        Dados cadastrais ainda não coletados para este dossie.
      </p>
    )
  }

  const sitTone =
    (data.situacao_cadastral &&
      SIT_TONE[data.situacao_cadastral.toLowerCase()]) ||
    "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300"

  return (
    <div className="rounded-lg border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
      <div className="flex items-start gap-2.5 border-b border-gray-100 p-3 dark:border-gray-900">
        <div className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-md bg-gray-100 dark:bg-gray-900">
          <RiBuilding4Line className="size-4 text-gray-500" aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="truncate text-sm font-medium text-gray-900 dark:text-gray-100">
              {data.razao_social ?? data.cnpj}
            </p>
            {data.situacao_cadastral && (
              <span className={cx(tableTokens.badge, sitTone)}>{data.situacao_cadastral}</span>
            )}
            {!data.enriquecido && (
              <span className={cx(tableTokens.badge, "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300")}>
                não enriquecido
              </span>
            )}
          </div>
          <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>
            CNPJ {data.cnpj}
            {data.nome_fantasia && <> · {data.nome_fantasia}</>}
          </p>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-x-6 gap-y-2 p-3 sm:grid-cols-2">
        <Field label="Data de fundação" value={fmtDate(data.data_fundacao)} />
        <Field label="Capital social" value={fmtBRL(data.capital_social)} />
        <Field label="Regime tributário" value={data.regime_tributario ?? "—"} />
        <Field label="Natureza jurídica" value={data.natureza_juridica ?? "—"} />
        <Field label="Porte" value={data.porte ?? "—"} />
        <Field
          label="CNAE principal"
          value={
            data.cnae_principal
              ? `${data.cnae_principal.code ?? ""} ${data.cnae_principal.name ?? ""}`.trim() || "—"
              : "—"
          }
        />
      </div>

      {data.cnaes_secundarios.length > 0 && (
        <div className="border-t border-gray-100 p-3 dark:border-gray-900">
          <p className={cx(tableTokens.header, "mb-1")}>
            CNAEs secundários ({data.cnaes_secundarios.length})
          </p>
          <ul className="flex flex-wrap gap-1.5">
            {data.cnaes_secundarios.map((c, i) => (
              <li
                key={i}
                className={cx(tableTokens.badge, "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300")}
                title={c.name ?? undefined}
              >
                {c.code ?? c.name ?? "—"}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className={tableTokens.header}>{label}</span>
      <span className="text-sm font-medium text-gray-900 dark:text-gray-100">{value}</span>
    </div>
  )
}
