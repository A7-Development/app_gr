// src/app/(app)/admin/dados/catalogo/page.tsx
//
// Admin · Dados · Catálogo (Fase F — o TRONCO da governança de dados).
//
// Navega o que cada provedor oferece: Provedor → API/endpoint → Dataset. É aqui
// que o mantenedor cadastra o "nome da consulta" (public_code + nome pt-BR),
// habilita o dataset e cria o Contrato de campos (que é a FOLHA — abre em
// /admin/dados/contratos). Nível mantenedor (backend: require_system_maintainer).
//
// Decisões: nome auto-sugerido + aprovação (§14.8); criar contrato pré-popula
// campos de um payload real (§14.9); modo (marketplace/adapter) vem da relação
// provedor×tenant (§15.1) — no catálogo global é o modo de revenda.

"use client"

import * as React from "react"
import { useRouter } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"
import {
  RiArrowRightLine,
  RiCheckboxCircleFill,
  RiDatabase2Line,
  RiPriceTag3Line,
  RiSparkling2Line,
} from "@remixicon/react"

import { Badge } from "@/components/tremor/Badge"
import { Button } from "@/components/tremor/Button"
import { Checkbox } from "@/components/tremor/Checkbox"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import { Switch } from "@/components/tremor/Switch"
import { DrillDownSheet, PageHeader } from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import {
  dataCatalog,
  type CatalogDatasetRow,
  type CatalogProviderGroup,
} from "@/lib/data-catalog-client"
import { cx } from "@/lib/utils"

function brl(v: number | null): string {
  if (v == null) return "—"
  return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL", minimumFractionDigits: 2, maximumFractionDigits: 4 })
}

// ─── Filtro client-side sobre a árvore carregada ─────────────────────────────

function filterGroup(
  g: CatalogProviderGroup,
  needle: string,
  onlyEnabled: boolean,
  onlyNoContract: boolean,
): CatalogProviderGroup {
  const n = needle.trim().toLowerCase()
  const apis = g.apis
    .map((a) => ({
      ...a,
      datasets: a.datasets.filter((d) => {
        if (onlyEnabled && !d.enabled_for_sale) return false
        if (onlyNoContract && d.contract.status === "active") return false
        if (!n) return true
        const hay = [
          d.provider_dataset_code,
          d.provider_query_name,
          d.public_code,
          d.display_name_pt_br,
          d.categoria_ui,
        ]
          .map((x) => (x ?? "").toLowerCase())
          .join(" ")
        return hay.includes(n)
      }),
    }))
    .filter((a) => a.datasets.length > 0)
  return { ...g, apis }
}

export default function CatalogoPage() {
  const qc = useQueryClient()
  const router = useRouter()

  const listQ = useQuery({
    queryKey: ["admin", "data-catalog"],
    queryFn: () => dataCatalog.list(),
  })

  const [provider, setProvider] = React.useState<string | null>(null)
  React.useEffect(() => {
    if (!provider && listQ.data && listQ.data.length > 0)
      setProvider(listQ.data[0].provider_slug)
  }, [provider, listQ.data])

  const [search, setSearch] = React.useState("")
  const [onlyEnabled, setOnlyEnabled] = React.useState(false)
  const [onlyNoContract, setOnlyNoContract] = React.useState(false)
  const [openApis, setOpenApis] = React.useState<Set<string>>(new Set())
  const [editing, setEditing] = React.useState<CatalogDatasetRow | null>(null)

  const group = (listQ.data ?? []).find((g) => g.provider_slug === provider) ?? null
  const filtered = group
    ? filterGroup(group, search, onlyEnabled, onlyNoContract)
    : null

  // Abre automaticamente as APIs com match quando há busca/filtro.
  React.useEffect(() => {
    if ((search || onlyEnabled || onlyNoContract) && filtered) {
      setOpenApis(new Set(filtered.apis.map((a) => a.api)))
    }
  }, [search, onlyEnabled, onlyNoContract, filtered])

  const toggleApi = (api: string) =>
    setOpenApis((prev) => {
      const next = new Set(prev)
      if (next.has(api)) next.delete(api)
      else next.add(api)
      return next
    })

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["admin", "data-catalog"] })

  const enableMut = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      dataCatalog.curate(id, { enabled_for_sale: enabled }),
    onSuccess: () => invalidate(),
    onError: (e) => toast.error(`Erro: ${(e as Error).message}`),
  })

  return (
    <div className="px-6 py-6">
      <PageHeader
        title="Catálogo de dados"
        subtitle="Admin · Dados"
        info="O que cada provedor oferece — APIs, endpoints e datasets. Cadastre o nome da consulta, habilite e crie o contrato de campos. Nível mantenedor."
      />

      {/* Seletor de provedor + métricas */}
      <div className="mt-4 mb-3 flex flex-wrap items-center gap-1.5">
        {(listQ.data ?? []).map((g) => {
          const active = provider === g.provider_slug
          return (
            <button
              key={g.provider_slug}
              type="button"
              onClick={() => setProvider(g.provider_slug)}
              className={cx(
                "rounded-md border px-2.5 py-1 text-xs font-medium",
                active
                  ? "border-blue-500 bg-blue-50 text-blue-700 dark:border-blue-500/40 dark:bg-blue-500/10 dark:text-blue-300"
                  : "border-gray-200 bg-white text-gray-600 hover:border-gray-300 dark:border-gray-800 dark:bg-gray-950 dark:text-gray-400",
              )}
            >
              {g.provider_name}
              <span className="ml-1.5 text-gray-400">
                {g.total} · {g.with_contract_count} c/ contrato
              </span>
            </button>
          )
        })}
      </div>

      {/* Filtros */}
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Input
          placeholder="Buscar dataset, código, public_code…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-8 max-w-xs"
        />
        <label className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400">
          <Checkbox checked={onlyEnabled} onCheckedChange={(v) => setOnlyEnabled(v === true)} />
          só habilitados
        </label>
        <label className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-400">
          <Checkbox checked={onlyNoContract} onCheckedChange={(v) => setOnlyNoContract(v === true)} />
          só sem contrato
        </label>
      </div>

      {listQ.isLoading && <p className={tableTokens.cellSecondary}>Carregando catálogo…</p>}

      {filtered && (
        <div className="space-y-2">
          {filtered.apis.map((a) => {
            const isOpen = openApis.has(a.api)
            return (
              <div
                key={a.api}
                className="overflow-hidden rounded-lg border border-gray-200 dark:border-gray-800"
              >
                <button
                  type="button"
                  onClick={() => toggleApi(a.api)}
                  className="flex w-full items-center gap-2 bg-gray-50/60 px-3 py-2 text-left dark:bg-gray-900/40"
                >
                  <RiDatabase2Line className="size-4 text-gray-400" aria-hidden />
                  <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                    {a.api}
                  </span>
                  <span className={cx(tableTokens.cellSecondary, "ml-1")}>
                    {a.datasets.length} dataset(s)
                  </span>
                  <RiArrowRightLine
                    className={cx(
                      "ml-auto size-4 text-gray-400 transition-transform",
                      isOpen && "rotate-90",
                    )}
                    aria-hidden
                  />
                </button>

                {isOpen && (
                  <table className="w-full">
                    <thead>
                      <tr className="border-y border-gray-100 dark:border-gray-900">
                        <th className={cx(tableTokens.header, "px-3 py-1.5 text-left")}>Dataset (vendor)</th>
                        <th className={cx(tableTokens.header, "px-3 py-1.5 text-left")}>Nome · public_code</th>
                        <th className={cx(tableTokens.header, "px-3 py-1.5 text-center")}>Vender</th>
                        <th className={cx(tableTokens.header, "px-3 py-1.5 text-left")}>Contrato</th>
                        <th className={cx(tableTokens.header, "px-3 py-1.5 text-right")}>Custo</th>
                        <th className={cx(tableTokens.header, "px-3 py-1.5")}></th>
                      </tr>
                    </thead>
                    <tbody>
                      {a.datasets.map((d) => (
                        <tr
                          key={d.dataset_id}
                          className="border-b border-gray-50 last:border-0 hover:bg-gray-50/50 dark:border-gray-900/60 dark:hover:bg-gray-900/30"
                        >
                          <td className="px-3 py-1.5">
                            <span className={tableTokens.cellTextMono}>{d.provider_dataset_code}</span>
                            {d.provider_query_name && (
                              <span className={cx(tableTokens.cellSecondary, "ml-1.5")}>
                                ({d.provider_query_name})
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-1.5">
                            {d.public_code ? (
                              <span className={tableTokens.cellText}>
                                {d.display_name_pt_br ?? "—"}{" "}
                                <span className="font-medium text-blue-700 dark:text-blue-300">
                                  · {d.public_code}
                                </span>
                              </span>
                            ) : (
                              <span className={cx(tableTokens.cellMuted, "italic")}>
                                — sugerir: {d.suggested_public_code}
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-1.5 text-center">
                            <div className="flex justify-center">
                              <Switch
                                checked={d.enabled_for_sale}
                                disabled={!d.public_code || enableMut.isPending}
                                onCheckedChange={(v) =>
                                  enableMut.mutate({ id: d.dataset_id, enabled: v })
                                }
                              />
                            </div>
                          </td>
                          <td className="px-3 py-1.5">
                            {d.contract.status === "active" ? (
                              <Badge variant="success">
                                <RiCheckboxCircleFill className="size-3" aria-hidden />
                                v{d.contract.version} · {d.contract.n_campos} campos
                              </Badge>
                            ) : (
                              <span className={tableTokens.cellMuted}>—</span>
                            )}
                          </td>
                          <td className={cx("px-3 py-1.5 text-right", tableTokens.cellNumberSecondary)}>
                            {d.mode === "marketplace" ? brl(d.current_cost_brl) : "—"}
                          </td>
                          <td className="px-3 py-1.5 text-right">
                            <Button
                              variant="light"
                              className="h-7 px-2 text-xs"
                              onClick={() => setEditing(d)}
                            >
                              Gerenciar
                            </Button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            )
          })}
          {filtered.apis.length === 0 && (
            <p className={tableTokens.cellSecondary}>Nenhum dataset com esses filtros.</p>
          )}
        </div>
      )}

      <DatasetDrawer
        row={editing}
        onClose={() => setEditing(null)}
        onSaved={invalidate}
        onOpenContract={(provider_, api_, dataset_) => {
          setEditing(null)
          const q = new URLSearchParams({ provider: provider_, api: api_, dataset: dataset_ })
          router.push(`/admin/dados/contratos?${q.toString()}`)
        }}
      />
    </div>
  )
}

// ─── Drawer de curadoria do dataset ──────────────────────────────────────────

function DatasetDrawer({
  row,
  onClose,
  onSaved,
  onOpenContract,
}: {
  row: CatalogDatasetRow | null
  onClose: () => void
  onSaved: () => void
  onOpenContract: (provider: string, api: string, dataset: string) => void
}) {
  const qc = useQueryClient()
  const [publicCode, setPublicCode] = React.useState("")
  const [nome, setNome] = React.useState("")
  const [categoria, setCategoria] = React.useState("")
  const [markup, setMarkup] = React.useState("")

  React.useEffect(() => {
    if (row) {
      setPublicCode(row.public_code ?? "")
      setNome(row.display_name_pt_br ?? "")
      setCategoria(row.categoria_ui ?? "")
      setMarkup(row.markup_pct != null ? String(row.markup_pct) : "")
    }
  }, [row])

  const saveMut = useMutation({
    mutationFn: () => {
      if (!row) throw new Error("—")
      return dataCatalog.curate(row.dataset_id, {
        public_code: publicCode.trim() || null,
        display_name_pt_br: nome.trim() || null,
        categoria_ui: categoria.trim() || null,
        markup_pct: markup.trim() ? Number(markup) : null,
      })
    },
    onSuccess: () => {
      toast.success("Dataset atualizado.")
      onSaved()
      onClose()
    },
    onError: (e) => toast.error(`Erro: ${(e as Error).message}`),
  })

  const createMut = useMutation({
    mutationFn: () => {
      if (!row) throw new Error("—")
      return dataCatalog.createContract(row.dataset_id)
    },
    onSuccess: (c) => {
      toast.success(
        c.already_existed
          ? "Contrato já existia — abrindo."
          : `Contrato criado (${c.n_campos} campos detectados).`,
      )
      qc.invalidateQueries({ queryKey: ["admin", "data-catalog"] })
      onOpenContract(c.provider, c.api_endpoint, c.dataset_code)
    },
    onError: (e) => toast.error(`Erro: ${(e as Error).message}`),
  })

  const applySuggestion = () => {
    if (!row) return
    if (!publicCode.trim()) setPublicCode(row.suggested_public_code)
    if (!nome.trim()) setNome(row.suggested_name)
  }

  const hasContract = row?.contract.status === "active"

  return (
    <DrillDownSheet open={Boolean(row)} onClose={onClose} title="Gerenciar dataset">
      {row && (
        <div className="space-y-5 px-1 py-2">
          {/* Identidade do vendor (read-only) */}
          <div className="rounded-md bg-gray-50 px-3 py-2 dark:bg-gray-900/50">
            <p className={tableTokens.cellSecondary}>
              {row.provider_slug} › {row.provider_api}
            </p>
            <p className={cx(tableTokens.cellTextMono, "mt-0.5")}>
              {row.provider_dataset_code}
              {row.provider_query_name ? ` (${row.provider_query_name})` : ""}
            </p>
            <Badge variant="neutral" className="mt-1.5">
              {row.mode === "marketplace" ? "Marketplace (revenda)" : "Adapter (interno)"}
            </Badge>
          </div>

          {/* Nome da consulta */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Label className="text-sm font-medium">Nome da consulta</Label>
              <button
                type="button"
                onClick={applySuggestion}
                className="flex items-center gap-1 text-xs text-blue-600 hover:underline dark:text-blue-400"
              >
                <RiSparkling2Line className="size-3.5" aria-hidden />
                usar sugestão
              </button>
            </div>
            <div>
              <Label htmlFor="pc" className="text-xs text-gray-500">public_code</Label>
              <Input
                id="pc"
                value={publicCode}
                onChange={(e) => setPublicCode(e.target.value)}
                placeholder={row.suggested_public_code}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="nm" className="text-xs text-gray-500">Nome (pt-BR)</Label>
              <Input
                id="nm"
                value={nome}
                onChange={(e) => setNome(e.target.value)}
                placeholder={row.suggested_name}
                className="mt-1"
              />
            </div>
            <div>
              <Label htmlFor="cat" className="text-xs text-gray-500">Categoria</Label>
              <Input
                id="cat"
                value={categoria}
                onChange={(e) => setCategoria(e.target.value)}
                placeholder="empresas · pessoas · processos…"
                className="mt-1"
              />
            </div>
            {row.mode === "marketplace" && (
              <div>
                <Label htmlFor="mk" className="text-xs text-gray-500">
                  Markup (%) — custo {brl(row.current_cost_brl)}
                </Label>
                <Input
                  id="mk"
                  type="number"
                  value={markup}
                  onChange={(e) => setMarkup(e.target.value)}
                  className="mt-1"
                />
              </div>
            )}
          </div>

          <Button onClick={() => saveMut.mutate()} isLoading={saveMut.isPending} className="w-full">
            Salvar dataset
          </Button>

          {/* Contrato de campos */}
          <div className="border-t border-gray-100 pt-4 dark:border-gray-800">
            <div className="mb-2 flex items-center gap-1.5">
              <RiPriceTag3Line className="size-4 text-gray-400" aria-hidden />
              <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
                Contrato de campos
              </span>
            </div>
            {hasContract ? (
              <>
                <p className={cx(tableTokens.cellSecondary, "mb-2")}>
                  Versão ativa v{row.contract.version} · {row.contract.n_campos} campos.
                </p>
                <Button
                  variant="secondary"
                  className="w-full"
                  onClick={() =>
                    onOpenContract(
                      row.contract.provider!,
                      row.contract.api_endpoint!,
                      row.contract.dataset_code!,
                    )
                  }
                >
                  Abrir contrato de campos
                  <RiArrowRightLine className="size-4" aria-hidden />
                </Button>
              </>
            ) : (
              <>
                <p className={cx(tableTokens.cellSecondary, "mb-2")}>
                  Sem contrato. Criar a 1ª versão pré-popula os campos a partir de
                  uma consulta real (quando houver). Requer public_code salvo.
                </p>
                <Button
                  className="w-full"
                  disabled={!row.public_code}
                  isLoading={createMut.isPending}
                  onClick={() => createMut.mutate()}
                >
                  Criar contrato de campos
                  <RiArrowRightLine className="size-4" aria-hidden />
                </Button>
                {!row.public_code && (
                  <p className={cx(tableTokens.cellMuted, "mt-1.5")}>
                    Defina e <b>salve</b> o public_code antes de criar o contrato.
                  </p>
                )}
              </>
            )}
          </div>
        </div>
      )}
    </DrillDownSheet>
  )
}
