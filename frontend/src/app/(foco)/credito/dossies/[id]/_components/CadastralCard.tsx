// CadastralCard — card "Dados cadastrais coletados" (Fase 2: dirigido pelo Contrato).
//
// Lê GET /dossies/{id}/cadastral, que projeta o basic_data via o Contrato de
// Dados: campos com rótulo pt-BR / categoria / ordem (só on_screen) + campos
// NOVOS (🆕) fora do contrato. Sem identidade de vendor (white-label).

"use client"

import { useQuery } from "@tanstack/react-query"
import { RiBuilding4Line, RiSparkling2Line } from "@remixicon/react"

import { tableTokens } from "@/design-system/tokens/table"
import { credito, type CadastralCampo } from "@/lib/credito-client"
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
function fmtScalar(v: string | number | boolean): string {
  if (typeof v === "boolean") return v ? "Sim" : "Não"
  return String(v)
}
function fmtValor(v: CadastralCampo["valor"]): string {
  if (v === null || v === "") return "—"
  if (Array.isArray(v)) return v.map(fmtScalar).join(", ") || "—"
  return fmtScalar(v)
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
    (data.situacao_cadastral && SIT_TONE[data.situacao_cadastral.toLowerCase()]) ||
    "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300"

  // Agrupa campos por categoria, ordena grupos pela menor `ordem` e campos
  // dentro do grupo por `ordem`.
  const grupos = new Map<string, CadastralCampo[]>()
  for (const c of data.campos ?? []) {
    const arr = grupos.get(c.categoria) ?? []
    arr.push(c)
    grupos.set(c.categoria, arr)
  }
  const gruposOrdenados = Array.from(grupos.entries())
    .map(([cat, campos]) => ({
      cat,
      campos: [...campos].sort((a, b) => a.ordem - b.ordem),
      minOrdem: Math.min(...campos.map((c) => c.ordem)),
    }))
    .sort((a, b) => a.minOrdem - b.minOrdem)

  return (
    <div className="rounded-lg border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
      {/* Header */}
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
          <p className={cx(tableTokens.cellSecondary, "mt-0.5")}>CNPJ {data.cnpj}</p>
        </div>
      </div>

      {/* Resumo (campos validados) */}
      <div className="grid grid-cols-2 gap-x-6 gap-y-2 p-3 sm:grid-cols-3">
        <Field label="Data de fundação" value={fmtDate(data.data_fundacao)} />
        <Field label="Capital social" value={fmtBRL(data.capital_social)} />
        <Field label="Situação" value={data.situacao_cadastral ?? "—"} />
      </div>

      {/* Banner de campos novos (não classificados) */}
      {data.campos_novos_count > 0 && (
        <div className="mx-3 flex items-center gap-1.5 rounded-md bg-amber-50 px-2.5 py-1.5 dark:bg-amber-500/10">
          <RiSparkling2Line className="size-3.5 text-amber-600 dark:text-amber-400" aria-hidden />
          <span className="text-xs text-amber-700 dark:text-amber-300">
            {data.campos_novos_count} campo(s) novo(s) ainda não classificado(s) no contrato.
          </span>
        </div>
      )}

      {/* Campos projetados pelo contrato, por categoria */}
      <div className="space-y-3 p-3">
        {gruposOrdenados.map(({ cat, campos }) => (
          <div key={cat}>
            <p className={cx(tableTokens.header, "mb-1")}>{cat}</p>
            <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
              {campos.map((c) => (
                <div key={c.field_path} className="flex flex-col gap-0.5">
                  <dt className={cx(tableTokens.header, "flex items-center gap-1")}>
                    {c.label}
                    {c.novo && (
                      <span className={cx(tableTokens.badge, "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300")}>
                        novo
                      </span>
                    )}
                  </dt>
                  <dd className="text-sm text-gray-900 dark:text-gray-100">{fmtValor(c.valor)}</dd>
                </div>
              ))}
            </dl>
          </div>
        ))}
      </div>
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
