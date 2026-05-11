// _components/SnapshotsLanding.tsx
//
// Landing do slug `qitech-estoque-carteira` — lista combinada de
// Solicitacoes/Status/Disponiveis. Substitui o dashboard direto como
// "default view" da rota; dashboard so abre via `?data=YYYY-MM-DD`.
//
// Composicao:
//   1. PageHeader (titulo + voltar ao catalogo)
//   2. Hero "Snapshot mais recente" — bundle sem filtro (backend devolve
//      max(data_referencia)). 4 KPIs compactos + CTA "Abrir →".
//   3. CTA bar "Solicitacoes recentes" + botao "+ Solicitar nova".
//   4. DataTableShell com jobs (qitech_report_job, filter fidc-estoque).
//      Status badge + tempo decorrido + acao contextual:
//        SUCCESS    -> "Abrir →" (link pra ?data=<reference_date>)
//        WAITING    -> sem acao, timer no badge
//        PROCESSING -> sem acao, timer no badge
//        ERROR      -> "Re-disparar"
//      Polling 30s quando ha WAITING/PROCESSING na lista (para quando
//      todos terminaram).
//   5. Dispatch dialog — mesmo do antigo PageHeader, agora vive aqui.

"use client"

import * as React from "react"
import Link from "next/link"
import { usePathname, useRouter } from "next/navigation"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import {
  RiArrowLeftLine,
  RiArrowRightLine,
  RiDownloadCloud2Line,
  RiInboxLine,
  RiRefreshLine,
} from "@remixicon/react"
import { toast } from "sonner"
import type { ColumnDef } from "@tanstack/react-table"

import { Badge } from "@/components/tremor/Badge"
import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/tremor/Dialog"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import {
  DataTableShell,
  PageHeader,
} from "@/design-system/components"
import { tableTokens } from "@/design-system/tokens/table"
import { useUAs } from "@/lib/hooks/cadastros"
import { cx } from "@/lib/utils"

import {
  qitechJobs,
  relatorios,
  type DispatchFidcEstoquePayload,
  type QitechJob,
  type QitechJobStatus,
} from "../../../_lib/api"

import { brl, brlMi, formatDateBR, formatElapsed, pct } from "./format"

// ─────────────────────────────────────────────────────────────────────────────
// SnapshotsLanding
// ─────────────────────────────────────────────────────────────────────────────

export function SnapshotsLanding() {
  const router = useRouter()
  const pathname = usePathname()
  const qc = useQueryClient()

  const [dispatchOpen, setDispatchOpen] = React.useState(false)

  const uasQuery = useUAs({ tipo: "fidc", ativa: true })
  const fundos = uasQuery.data ?? []

  // Bundle sem filtro → backend retorna max(data_referencia) do tenant.
  const heroBundleQuery = useQuery({
    queryKey: ["controladoria", "qitech-estoque-carteira", "bundle", null, null] as const,
    queryFn: () => relatorios.qitechEstoqueCarteiraBundle({}),
    staleTime: 30_000,
  })

  // Lista de jobs com polling 30s enquanto ha WAITING/PROCESSING.
  const jobsQuery = useQuery({
    queryKey: ["integracoes", "qitech-jobs", "fidc-estoque"] as const,
    queryFn: () => qitechJobs.list({ report_type: "fidc-estoque", limit: 50 }),
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data) return false
      const hasPending = data.some(
        (j) => j.status === "WAITING" || j.status === "PROCESSING",
      )
      return hasPending ? 30_000 : false
    },
  })

  // Re-disparar — usa o cnpj_fundo + reference_date do job original.
  const redispatchMut = useMutation({
    mutationFn: (job: QitechJob) =>
      qitechJobs.dispatchFidcEstoque({
        cnpj_fundo: job.cnpj_fundo,
        reference_date: job.reference_date,
        environment: job.environment,
      }),
    onSuccess: (newJob) => {
      toast.success(
        `Re-disparado. JobId ${newJob.qitech_job_id} em processamento.`,
        { duration: 6000 },
      )
      qc.invalidateQueries({ queryKey: ["integracoes", "qitech-jobs"] })
    },
    onError: (err) => {
      const msg = err instanceof Error ? err.message : String(err)
      toast.error(`Falha ao re-disparar: ${msg}`)
    },
  })

  const goBackToCatalog = React.useCallback(() => {
    router.push("/controladoria/relatorios?tab=padronizados")
  }, [router])

  const heroBundle = heroBundleQuery.data
  const heroHasData =
    heroBundle && !heroBundle.is_empty && heroBundle.data_referencia

  const columns = React.useMemo<ColumnDef<QitechJob, unknown>[]>(
    () => makeColumns({ pathname, onRedispatch: (job) => redispatchMut.mutate(job), isRedispatching: redispatchMut.isPending }),
    [pathname, redispatchMut],
  )

  return (
    <div className="flex h-[calc(100vh-3rem)] flex-col overflow-hidden">
      {/* Title row */}
      <div className="shrink-0 bg-white px-6 pt-3.5 pb-3 dark:bg-gray-950">
        <PageHeader
          title="Carteira de recebiveis"
          info="Snapshot diario dos recebiveis em carteira do FIDC. Disparado via callback (eventType=fidcEstoque)."
          subtitle="Controladoria · Relatorio padronizado"
          actions={
            <Button variant="ghost" onClick={goBackToCatalog}>
              <RiArrowLeftLine className="mr-1 size-4" aria-hidden />
              Voltar ao catalogo
            </Button>
          }
        />
      </div>

      {/* Conteudo scrollavel */}
      <div className="min-h-0 flex-1 overflow-y-auto px-6 pt-4 pb-6">
        <div className="flex flex-col gap-4">
          {/* Hero "Snapshot mais recente" */}
          <SnapshotMaisRecenteHero
            bundle={heroBundle}
            isLoading={heroBundleQuery.isLoading}
            heroHasData={!!heroHasData}
            onOpenLatest={() => {
              if (heroBundle?.data_referencia) {
                router.push(`${pathname}?data=${heroBundle.data_referencia}`)
              }
            }}
            onRequestNew={() => setDispatchOpen(true)}
          />

          {/* CTA bar + lista de solicitacoes */}
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between gap-2">
              <div className="flex flex-col gap-0.5">
                <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
                  Solicitacoes recentes
                </h2>
                <p className="text-xs text-gray-500 dark:text-gray-400">
                  Lista das ultimas 50 solicitacoes. Click numa linha disponivel
                  abre o relatorio. Em processamento atualiza automaticamente a
                  cada 30s.
                </p>
              </div>
              <Button onClick={() => setDispatchOpen(true)}>
                <RiDownloadCloud2Line className="mr-1 size-4" aria-hidden />
                Solicitar novo snapshot
              </Button>
            </div>

            <DataTableShell
              data={jobsQuery.data ?? []}
              columns={columns}
              loading={jobsQuery.isLoading}
              error={(jobsQuery.error ?? null) as Error | null}
              onRetry={() => jobsQuery.refetch()}
              itemNoun={{ singular: "solicitacao", plural: "solicitacoes" }}
              emptyState={{
                icon: RiInboxLine,
                title: "Nenhuma solicitacao ainda",
                description:
                  "Click em \"Solicitar novo snapshot\" para pedir o primeiro relatorio FIDC Estoque.",
              }}
            />
          </div>
        </div>
      </div>

      {/* Dispatch dialog */}
      <DispatchSnapshotDialog
        open={dispatchOpen}
        onClose={() => setDispatchOpen(false)}
        fundos={fundos}
      />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// SnapshotMaisRecenteHero
// ─────────────────────────────────────────────────────────────────────────────

function SnapshotMaisRecenteHero({
  bundle,
  isLoading,
  heroHasData,
  onOpenLatest,
  onRequestNew,
}: {
  bundle: ReturnType<typeof relatorios.qitechEstoqueCarteiraBundle> extends Promise<infer T> ? T | undefined : never
  isLoading: boolean
  heroHasData: boolean
  onOpenLatest: () => void
  onRequestNew: () => void
}) {
  if (isLoading) {
    return (
      <Card>
        <div className="flex h-[110px] items-center justify-center">
          <span className="text-sm text-gray-500 dark:text-gray-400">
            Carregando snapshot mais recente...
          </span>
        </div>
      </Card>
    )
  }

  if (!heroHasData || !bundle) {
    return (
      <Card>
        <div className="flex flex-col items-start gap-3 px-1 py-2">
          <div className="flex flex-col gap-1">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
              Nenhum snapshot disponivel ainda
            </h2>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Nenhuma solicitacao FIDC Estoque foi bem-sucedida pra este
              tenant. Solicite a primeira pra popular a carteira.
            </p>
          </div>
          <Button onClick={onRequestNew}>
            <RiDownloadCloud2Line className="mr-1 size-4" aria-hidden />
            Solicitar primeiro snapshot
          </Button>
        </div>
      </Card>
    )
  }

  const kpis = bundle.kpis
  return (
    <Card>
      <div className="flex flex-col gap-3">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <div className="flex flex-col gap-0.5">
            <span className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Snapshot mais recente
            </span>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-gray-50">
              Carteira de {formatDateBR(bundle.data_referencia)}
              {bundle.fundo_nome ? (
                <span className="ml-2 text-sm font-normal text-gray-500 dark:text-gray-400">
                  · {bundle.fundo_nome}
                </span>
              ) : null}
            </h2>
          </div>
          <Button onClick={onOpenLatest}>
            Abrir relatorio
            <RiArrowRightLine className="ml-1 size-4" aria-hidden />
          </Button>
        </div>

        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <HeroKpi
            label="Valor presente"
            value={brlMi(kpis.valor_presente_total)}
            sub={`${kpis.qtd_titulos.toLocaleString("pt-BR")} titulos`}
          />
          <HeroKpi
            label="Valor nominal"
            value={brlMi(kpis.valor_nominal_total)}
            sub="A receber"
          />
          <HeroKpi
            label="PDD"
            value={pct(kpis.pdd_medio_pct, 2)}
            sub={brl(kpis.valor_pdd_total)}
          />
          <HeroKpi
            label="Vencido"
            value={pct(kpis.pct_vencido, 2)}
            sub="% do nominal"
          />
        </div>
      </div>
    </Card>
  )
}

function HeroKpi({
  label,
  value,
  sub,
}: {
  label: string
  value: string
  sub?: string
}) {
  return (
    <div className="flex flex-col gap-0.5">
      <span className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
        {label}
      </span>
      <span className="text-lg font-semibold tabular-nums text-gray-900 dark:text-gray-50">
        {value}
      </span>
      {sub ? (
        <span className="text-[11px] text-gray-500 dark:text-gray-400">
          {sub}
        </span>
      ) : null}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Status badge + columns
// ─────────────────────────────────────────────────────────────────────────────

function StatusBadge({ job }: { job: QitechJob }) {
  if (job.status === "SUCCESS") return <Badge variant="success">Disponivel</Badge>
  if (job.status === "ERROR") return <Badge variant="error">Falhou</Badge>
  if (job.status === "EXPIRED")
    return <Badge variant="neutral">Expirado</Badge>
  // WAITING / PROCESSING: mostra timer inline pra evidenciar progresso
  const elapsed = formatElapsed(job.created_at)
  const label = job.status === "WAITING" ? "Aguardando" : "Em processamento"
  return (
    <Badge variant="warning">
      {label} · {elapsed}
    </Badge>
  )
}

function triggeredByLabel(triggered_by: string): string {
  if (triggered_by.startsWith("user:")) return "Manual"
  if (triggered_by.startsWith("system:scheduler")) return "Scheduler"
  if (triggered_by.startsWith("webhook")) return "Webhook"
  return triggered_by
}

function makeColumns({
  pathname,
  onRedispatch,
  isRedispatching,
}: {
  pathname: string
  onRedispatch: (job: QitechJob) => void
  isRedispatching: boolean
}): ColumnDef<QitechJob, unknown>[] {
  return [
    {
      id: "status",
      header: "Status",
      accessorKey: "status",
      cell: ({ row }) => <StatusBadge job={row.original} />,
    },
    {
      id: "reference_date",
      header: "Data ref.",
      accessorKey: "reference_date",
      cell: ({ row }) => (
        <span className={tableTokens.cellText}>
          {formatDateBR(row.original.reference_date)}
        </span>
      ),
    },
    {
      id: "created_at",
      header: "Solicitado",
      accessorKey: "created_at",
      cell: ({ row }) => (
        <span className={tableTokens.cellSecondary}>
          ha {formatElapsed(row.original.created_at)}
        </span>
      ),
    },
    {
      id: "triggered_by",
      header: "Disparo",
      accessorKey: "triggered_by",
      cell: ({ row }) => (
        <span className={tableTokens.cellSecondary}>
          {triggeredByLabel(row.original.triggered_by)}
        </span>
      ),
    },
    {
      id: "error",
      header: "Mensagem",
      cell: ({ row }) => {
        const msg = row.original.error_message
        if (!msg) return <span className={tableTokens.cellSecondary}>—</span>
        return (
          <span
            className={cx(tableTokens.cellSecondary, "line-clamp-1 max-w-xs")}
            title={msg}
          >
            {msg}
          </span>
        )
      },
    },
    {
      id: "actions",
      header: "",
      cell: ({ row }) => {
        const job = row.original
        if (job.status === "SUCCESS") {
          return (
            <div className="flex justify-end">
              <Link href={`${pathname}?data=${job.reference_date}`}>
                <Button variant="ghost">
                  Abrir
                  <RiArrowRightLine className="ml-1 size-3.5" aria-hidden />
                </Button>
              </Link>
            </div>
          )
        }
        if (job.status === "ERROR") {
          return (
            <div className="flex justify-end">
              <Button
                variant="secondary"
                onClick={(e) => {
                  e.stopPropagation()
                  onRedispatch(job)
                }}
                disabled={isRedispatching}
              >
                <RiRefreshLine className="mr-1 size-3.5" aria-hidden />
                Re-disparar
              </Button>
            </div>
          )
        }
        return null
      },
    },
  ]
}

// ─────────────────────────────────────────────────────────────────────────────
// Dispatch dialog — solicitar novo snapshot (job + webhook)
// ─────────────────────────────────────────────────────────────────────────────

type UAOption = {
  id: string
  nome: string
  cnpj: string | null
}

function DispatchSnapshotDialog({
  open,
  onClose,
  fundos,
}: {
  open: boolean
  onClose: () => void
  fundos: UAOption[]
}) {
  const qc = useQueryClient()

  const yesterdayISO = React.useMemo(() => {
    const d = new Date()
    d.setUTCDate(d.getUTCDate() - 1)
    return d.toISOString().slice(0, 10)
  }, [])

  const fundosComCnpj = React.useMemo(
    () => fundos.filter((f) => !!f.cnpj),
    [fundos],
  )

  const initialFundoId = React.useMemo(() => {
    if (fundosComCnpj.length === 1) return fundosComCnpj[0].id
    return ""
  }, [fundosComCnpj])

  const [fundoId, setFundoId] = React.useState(initialFundoId)
  const [referenceDate, setReferenceDate] = React.useState(yesterdayISO)
  const [error, setError] = React.useState<string | null>(null)

  React.useEffect(() => {
    if (open) {
      setFundoId(initialFundoId)
      setReferenceDate(yesterdayISO)
      setError(null)
    }
  }, [open, initialFundoId, yesterdayISO])

  const dispatchMut = useMutation({
    mutationFn: (payload: DispatchFidcEstoquePayload) =>
      qitechJobs.dispatchFidcEstoque(payload),
    onSuccess: (job) => {
      toast.success(
        `Solicitacao enfileirada. JobId ${job.qitech_job_id} — vai aparecer na lista em segundos.`,
        { duration: 6000 },
      )
      // Invalida a lista pra a nova row aparecer com status WAITING.
      // Bundle nao precisa invalidar — a row "Disponivel" so aparece quando
      // o callback chegar e o status flipar via polling.
      qc.invalidateQueries({ queryKey: ["integracoes", "qitech-jobs"] })
      onClose()
    },
    onError: (err) => {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      toast.error(`Falha ao solicitar: ${msg}`)
    },
  })

  const handleSubmit = React.useCallback(() => {
    setError(null)
    const fundo = fundosComCnpj.find((f) => f.id === fundoId)
    if (!fundo || !fundo.cnpj) {
      setError("Selecione um fundo com CNPJ cadastrado.")
      return
    }
    if (!/^\d{4}-\d{2}-\d{2}$/.test(referenceDate)) {
      setError("Data de referencia precisa estar em YYYY-MM-DD.")
      return
    }
    dispatchMut.mutate({
      cnpj_fundo: fundo.cnpj,
      reference_date: referenceDate,
    })
  }, [fundoId, fundosComCnpj, referenceDate, dispatchMut])

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Solicitar novo snapshot da carteira</DialogTitle>
          <DialogDescription>
            Dispara o relatorio FIDC Estoque para o fundo e data escolhidos. O
            arquivo chega via webhook em alguns minutos e popula a carteira
            automaticamente.
          </DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="dispatch-fundo">Fundo</Label>
            <Select value={fundoId} onValueChange={setFundoId}>
              <SelectTrigger id="dispatch-fundo">
                <SelectValue placeholder="Selecione o fundo..." />
              </SelectTrigger>
              <SelectContent>
                {fundosComCnpj.length === 0 ? (
                  <SelectItem value="__none__" disabled>
                    Nenhum fundo com CNPJ cadastrado
                  </SelectItem>
                ) : (
                  fundosComCnpj.map((f) => (
                    <SelectItem key={f.id} value={f.id}>
                      {f.nome}
                      {f.cnpj ? ` · ${f.cnpj}` : ""}
                    </SelectItem>
                  ))
                )}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="dispatch-date">Data de referencia</Label>
            <Input
              id="dispatch-date"
              type="date"
              value={referenceDate}
              onChange={(e) => setReferenceDate(e.currentTarget.value)}
            />
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Default = ontem (D-1). QiTech publica relatorios do dia anterior
              tipicamente a partir de 3h-6h SP.
            </p>
          </div>

          {error && (
            <div className="rounded border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-700 dark:bg-red-950 dark:text-red-300">
              {error}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button
            variant="ghost"
            onClick={onClose}
            disabled={dispatchMut.isPending}
          >
            Cancelar
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={dispatchMut.isPending || fundosComCnpj.length === 0}
          >
            {dispatchMut.isPending ? "Enviando..." : "Solicitar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Garantir que QitechJobStatus continua sendo um tipo usado (status no Badge).
// Se for retirar do enum no futuro, atualizar StatusBadge tambem.
export type { QitechJobStatus }
