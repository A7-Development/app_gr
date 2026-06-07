// src/app/(app)/admin/dados/contratos/page.tsx
//
// Admin · Dados · Contratos (Fase 5 — curadoria de Contratos de Dados).
//
// Nível MANTENEDOR (backend: require_system_maintainer). O mantenedor define,
// por campo, o destino nas 5 superfícies (silver/tela/tool/agente/check) +
// rótulo pt-BR + categoria. Campos NOVOS (🆕) detectados de uma consulta real
// aparecem pra classificar. Salvar = nova versão imutável + ativa (rollback =
// reativar). Vendor nunca vaza (white-label) — mas a gestão vê a hierarquia.

"use client"

import * as React from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import { RiArrowLeftLine, RiSaveLine, RiSparkling2Line, RiStackLine } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { Checkbox } from "@/components/tremor/Checkbox"
import { Input } from "@/components/tremor/Input"
import { tableTokens } from "@/design-system/tokens/table"
import {
  dataContracts,
  type DataContractField,
  type DataContractListItem,
  type FieldSaveSpec,
} from "@/lib/data-contracts-client"
import { cx } from "@/lib/utils"

type ToggleKey = "to_silver" | "on_screen" | "to_tool" | "to_agent" | "to_check"

const TOGGLES: Array<{ key: ToggleKey; label: string }> = [
  { key: "to_silver", label: "Silver" },
  { key: "on_screen", label: "Tela" },
  { key: "to_tool", label: "Tool" },
  { key: "to_agent", label: "Agente" },
  { key: "to_check", label: "Check" },
]

export default function ContratosPage() {
  return (
    <React.Suspense fallback={null}>
      <ContratosInner />
    </React.Suspense>
  )
}

function ContratosInner() {
  const qc = useQueryClient()
  const params = useSearchParams()
  // Deep-link vindo do Catálogo (tronco): ?provider&api&dataset.
  const dlProvider = params.get("provider")
  const dlApi = params.get("api")
  const dlDataset = params.get("dataset")
  const deepLink = React.useMemo(
    () =>
      dlProvider && dlApi && dlDataset
        ? { provider: dlProvider, api_endpoint: dlApi, dataset_code: dlDataset }
        : null,
    [dlProvider, dlApi, dlDataset],
  )

  const listQ = useQuery({
    queryKey: ["admin", "data-contracts"],
    queryFn: () => dataContracts.list(),
  })

  const [sel, setSel] = React.useState<DataContractListItem | null>(null)
  React.useEffect(() => {
    if (deepLink) return // deep-link manda; ignora seleção por chip
    if (!sel && listQ.data && listQ.data.length > 0) setSel(listQ.data[0])
  }, [sel, listQ.data, deepLink])

  // Identidade ativa: deep-link tem prioridade sobre a seleção por chip.
  const active = deepLink ?? sel

  const detailQ = useQuery({
    queryKey: [
      "admin",
      "data-contract",
      active?.provider,
      active?.api_endpoint,
      active?.dataset_code,
    ],
    queryFn: () =>
      dataContracts.detail(
        active!.provider,
        active!.api_endpoint,
        active!.dataset_code,
      ),
    enabled: Boolean(active),
  })

  const [draft, setDraft] = React.useState<DataContractField[]>([])
  React.useEffect(() => {
    if (detailQ.data) setDraft(detailQ.data.campos.map((c) => ({ ...c })))
  }, [detailQ.data])

  const saveMut = useMutation({
    mutationFn: () => {
      if (!active) throw new Error("Nenhum contrato selecionado.")
      const fields: FieldSaveSpec[] = draft.map((c) => ({
        field_path: c.field_path,
        public_label: c.public_label,
        description: c.description,
        semantic_type: c.semantic_type,
        categoria_ui: c.categoria_ui,
        sensibilidade: c.sensibilidade,
        eh_fato: c.eh_fato,
        to_silver: c.to_silver,
        silver_target: c.silver_target,
        on_screen: c.on_screen,
        screen_order: c.screen_order,
        to_tool: c.to_tool,
        to_agent: c.to_agent,
        to_check: c.to_check,
      }))
      return dataContracts.saveNewVersion(
        active.provider,
        active.api_endpoint,
        active.dataset_code,
        fields,
      )
    },
    onSuccess: () => {
      toast.success("Nova versão ativada.")
      qc.invalidateQueries({ queryKey: ["admin", "data-contracts"] })
      qc.invalidateQueries({
        queryKey: [
          "admin",
          "data-contract",
          active?.provider,
          active?.api_endpoint,
          active?.dataset_code,
        ],
      })
    },
    onError: (e) => toast.error(`Erro ao salvar: ${(e as Error).message}`),
  })

  const update = (i: number, patch: Partial<DataContractField>) =>
    setDraft((prev) => prev.map((c, idx) => (idx === i ? { ...c, ...patch } : c)))

  const onToggle = (i: number, key: ToggleKey, v: boolean) => {
    // Regra dura: marcar Check liga Silver (check ⇒ silver).
    if (key === "to_check" && v) update(i, { to_check: true, to_silver: true })
    else update(i, { [key]: v } as Partial<DataContractField>)
  }

  const detail = detailQ.data

  return (
    <div className="px-6 py-6">
      {deepLink && (
        <Link
          href="/admin/dados/catalogo"
          className="mb-3 inline-flex items-center gap-1 text-xs text-blue-600 hover:underline dark:text-blue-400"
        >
          <RiArrowLeftLine className="size-3.5" aria-hidden />
          Voltar ao Catálogo
        </Link>
      )}
      {/* Header */}
      <div className="mb-4 flex items-start gap-2.5">
        <div className="mt-0.5 flex size-9 items-center justify-center rounded-md bg-gray-100 dark:bg-gray-900">
          <RiStackLine className="size-5 text-gray-500" aria-hidden />
        </div>
        <div className="min-w-0 flex-1">
          <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-50">
            Contratos de dados
          </h1>
          <p className={tableTokens.cellSecondary}>
            Governança de campos das fontes externas — define o destino de cada
            campo nas 5 superfícies. Nível mantenedor.
          </p>
        </div>
        {detail && (
          <Button
            onClick={() => saveMut.mutate()}
            isLoading={saveMut.isPending}
            disabled={draft.length === 0}
          >
            <RiSaveLine className="size-4" aria-hidden />
            Salvar nova versão
          </Button>
        )}
      </div>

      {/* Seletor de contratos (provedor › api › dataset) — oculto no deep-link */}
      <div className={cx("mb-4 flex flex-wrap gap-1.5", deepLink && "hidden")}>
        {(listQ.data ?? []).map((c) => {
          const isActive = sel?.contract_id === c.contract_id
          return (
            <button
              key={c.contract_id}
              type="button"
              onClick={() => setSel(c)}
              className={cx(
                "rounded-md border px-2.5 py-1 text-xs font-medium",
                isActive
                  ? "border-blue-500 bg-blue-50 text-blue-700 dark:border-blue-500/40 dark:bg-blue-500/10 dark:text-blue-300"
                  : "border-gray-200 bg-white text-gray-600 hover:border-gray-300 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-400",
              )}
            >
              {c.provider} › {c.api_endpoint} › {c.public_code ?? c.dataset_code}
              <span className="ml-1 text-gray-400">v{c.version}</span>
            </button>
          )
        })}
      </div>

      {detailQ.isLoading && (
        <p className={tableTokens.cellSecondary}>Carregando contrato…</p>
      )}

      {detail && (
        <>
          {detail.n_novos > 0 && (
            <div className="mb-3 flex items-center gap-1.5 rounded-md bg-amber-50 px-2.5 py-1.5 dark:bg-amber-500/10">
              <RiSparkling2Line className="size-3.5 text-amber-600 dark:text-amber-400" aria-hidden />
              <span className="text-xs text-amber-700 dark:text-amber-300">
                {detail.n_novos} campo(s) novo(s) detectado(s) na última consulta — classifique e salve.
              </span>
            </div>
          )}

          <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-800">
            <table className="w-full min-w-[1000px]">
              <thead>
                <tr className="border-b border-gray-100 bg-gray-50/60 dark:border-gray-900 dark:bg-gray-900/40">
                  <th className={cx(tableTokens.header, "px-3 py-2 text-left")}>Campo</th>
                  <th className={cx(tableTokens.header, "px-3 py-2 text-left")}>Rótulo (pt-BR)</th>
                  <th className={cx(tableTokens.header, "px-3 py-2 text-left")}>Categoria</th>
                  <th className={cx(tableTokens.header, "px-3 py-2 text-left")}>Exemplo</th>
                  {TOGGLES.map((t) => (
                    <th key={t.key} className={cx(tableTokens.header, "px-2 py-2 text-center")}>
                      {t.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {draft.map((c, i) => (
                  <tr
                    key={c.field_path}
                    className="border-b border-gray-50 last:border-0 dark:border-gray-900/60"
                  >
                    <td className="px-3 py-1.5">
                      <span className={tableTokens.cellTextMono}>{c.field_path}</span>
                      {c.novo && (
                        <span className={cx(tableTokens.badge, "ml-1.5 bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300")}>
                          novo
                        </span>
                      )}
                    </td>
                    <td className="px-3 py-1.5">
                      <Input
                        value={c.public_label ?? ""}
                        onChange={(e) => update(i, { public_label: e.target.value })}
                        className="h-7"
                      />
                    </td>
                    <td className="px-3 py-1.5">
                      <Input
                        value={c.categoria_ui ?? ""}
                        onChange={(e) => update(i, { categoria_ui: e.target.value })}
                        className="h-7 w-32"
                      />
                    </td>
                    <td className="px-3 py-1.5">
                      <span className={cx(tableTokens.cellSecondary, "block max-w-[220px] truncate")}>
                        {c.valor_exemplo ?? "—"}
                      </span>
                    </td>
                    {TOGGLES.map((t) => (
                      <td key={t.key} className="px-2 py-1.5 text-center">
                        <div className="flex justify-center">
                          <Checkbox
                            checked={c[t.key]}
                            onCheckedChange={(v) => onToggle(i, t.key, v === true)}
                          />
                        </div>
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <p className={cx(tableTokens.cellSecondary, "mt-2")}>
            Regra: marcar <b>Check</b> liga <b>Silver</b> automaticamente (check ⇒ silver). Salvar cria uma nova versão e a ativa.
          </p>
        </>
      )}
    </div>
  )
}
