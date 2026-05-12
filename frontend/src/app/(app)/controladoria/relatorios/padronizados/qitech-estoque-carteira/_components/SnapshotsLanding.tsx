// _components/SnapshotsLanding.tsx
//
// Landing do slug `qitech-estoque-carteira` — lista combinada de
// Solicitacoes/Status/Disponiveis. Substitui o dashboard direto como
// "default view" da rota; dashboard so abre via `?data=YYYY-MM-DD`.
//
// Composicao:
//   1. PageHeader (titulo + voltar ao catalogo)
//   2. CTA bar "Solicitacoes recentes" + botao "+ Solicitar nova".
//   3. DataTableShell com jobs (qitech_report_job, filter fidc-estoque).
//      Status badge + tempo decorrido + acao contextual:
//        SUCCESS    -> "Abrir →" (link pra ?data=<reference_date>)
//        WAITING    -> sem acao, timer no badge
//        PROCESSING -> sem acao, timer no badge
//        ERROR      -> "Re-disparar"
//      Polling 30s quando ha WAITING/PROCESSING na lista (para quando
//      todos terminaram).
//   4. Dispatch dialog — mesmo do antigo PageHeader, agora vive aqui.

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
import { ApiError } from "@/lib/api-client"
import { cx } from "@/lib/utils"

import {
  qitechJobs,
  type DispatchFidcEstoquePayload,
  type DuplicateSuccessDetail,
  type QitechJob,
  type QitechJobStatus,
} from "../../../_lib/api"

import { formatDateBR, formatElapsed } from "./format"

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

  // Lista de jobs com polling: 5s enquanto ha WAITING/PROCESSING (badge
  // transita rapido pra Disponivel/Falhou), off quando todos terminaram.
  const jobsQuery = useQuery({
    queryKey: ["integracoes", "qitech-jobs", "fidc-estoque"] as const,
    queryFn: () => qitechJobs.list({ report_type: "fidc-estoque", limit: 50 }),
    refetchInterval: (query) => {
      const data = query.state.data
      if (!data) return false
      const hasPending = data.some(
        (j) => j.status === "WAITING" || j.status === "PROCESSING",
      )
      return hasPending ? 5_000 : false
    },
  })

  // Re-disparar — usa o cnpj_fundo + reference_date do job original.
  // force=true porque clicar Re-disparar e acao deliberada — se houver
  // SUCCESS recente conflictante, o usuario ja decidiu sobrescrever.
  const redispatchMut = useMutation({
    mutationFn: (job: QitechJob) =>
      qitechJobs.dispatchFidcEstoque({
        cnpj_fundo: job.cnpj_fundo,
        reference_date: job.reference_date,
        environment: job.environment,
        force: true,
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
        jobs={jobsQuery.data ?? []}
      />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Status badge + columns
// ─────────────────────────────────────────────────────────────────────────────

function StatusBadge({ job }: { job: QitechJob }) {
  if (job.status === "SUCCESS") return <Badge variant="success">Disponivel</Badge>
  if (job.status === "ERROR") return <Badge variant="error">Falhou</Badge>
  if (job.status === "TIMEOUT")
    return <Badge variant="error">Tempo esgotado</Badge>
  if (job.status === "EMPTY")
    return <Badge variant="warning">Sem dados</Badge>
  if (job.status === "CANCELED")
    return <Badge variant="neutral">Cancelado</Badge>
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
              <Link
                href={`${pathname}?data=${job.reference_date}`}
                aria-label={`Abrir relatorio de ${formatDateBR(job.reference_date)}`}
              >
                <Button variant="ghost" title="Abrir relatorio">
                  <RiArrowRightLine className="size-4" aria-hidden />
                </Button>
              </Link>
            </div>
          )
        }
        if (
          job.status === "ERROR" ||
          job.status === "TIMEOUT" ||
          job.status === "CANCELED" ||
          job.status === "EMPTY"
        ) {
          return (
            <div className="flex justify-end">
              <Button
                variant="ghost"
                onClick={(e) => {
                  e.stopPropagation()
                  onRedispatch(job)
                }}
                disabled={isRedispatching}
                title="Re-disparar"
                aria-label={`Re-disparar solicitacao de ${formatDateBR(job.reference_date)}`}
              >
                <RiRefreshLine className="size-4" aria-hidden />
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
  jobs,
}: {
  open: boolean
  onClose: () => void
  fundos: UAOption[]
  jobs: QitechJob[]
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
  // Quando achamos um SUCCESS recente pra (cnpj, data) — seja localmente
  // antes do POST ou via 409 do backend (race) — guardamos aqui o payload
  // pendente + o job em conflito. Renderiza o sub-dialog ConfirmForce.
  const [pendingForce, setPendingForce] = React.useState<{
    payload: DispatchFidcEstoquePayload
    existingJob: QitechJob | null
    serverMessage: string | null
  } | null>(null)

  React.useEffect(() => {
    if (open) {
      setFundoId(initialFundoId)
      setReferenceDate(yesterdayISO)
      setError(null)
      setPendingForce(null)
    }
  }, [open, initialFundoId, yesterdayISO])

  // Procura SUCCESS recente (< 24h) pra (cnpj, ref_date) na lista local
  // de jobs — espelha o gate do backend em qitech_jobs.py::dispatch.
  const findRecentSuccess = React.useCallback(
    (cnpj: string, refDate: string): QitechJob | null => {
      const cutoff = Date.now() - 24 * 60 * 60 * 1000
      return (
        jobs.find(
          (j) =>
            j.cnpj_fundo === cnpj &&
            j.reference_date === refDate &&
            j.status === "SUCCESS" &&
            new Date(j.created_at).getTime() >= cutoff,
        ) ?? null
      )
    },
    [jobs],
  )

  // Procura ultima tentativa pra (cnpj, ref_date) que terminou em estado
  // util de mostrar — error_message recente da QiTech (EMPTY, TIMEOUT,
  // ERROR). Renderiza como aviso contextual no dialog.
  const lastFailedAttempt = React.useMemo<QitechJob | null>(() => {
    const fundo = fundosComCnpj.find((f) => f.id === fundoId)
    if (!fundo?.cnpj || !/^\d{4}-\d{2}-\d{2}$/.test(referenceDate)) {
      return null
    }
    return (
      jobs.find(
        (j) =>
          j.cnpj_fundo === fundo.cnpj &&
          j.reference_date === referenceDate &&
          (j.status === "EMPTY" ||
            j.status === "TIMEOUT" ||
            j.status === "ERROR"),
      ) ?? null
    )
  }, [jobs, fundosComCnpj, fundoId, referenceDate])

  const dispatchMut = useMutation({
    mutationFn: (payload: DispatchFidcEstoquePayload) =>
      qitechJobs.dispatchFidcEstoque(payload),
    onSuccess: (job) => {
      toast.success(
        `Solicitacao enfileirada. JobId ${job.qitech_job_id} — vai aparecer na lista em segundos.`,
        { duration: 6000 },
      )
      qc.invalidateQueries({ queryKey: ["integracoes", "qitech-jobs"] })
      onClose()
    },
    onError: (err, variables) => {
      // Race condition: cliente nao tinha o job na lista (cache stale,
      // outro user/tela disparou) mas backend tem. Abre o mesmo sub-dialog
      // de confirm em vez de jogar string crua no usuario.
      if (
        err instanceof ApiError &&
        err.status === 409 &&
        typeof err.detail === "object" &&
        err.detail !== null &&
        (err.detail as { code?: string }).code === "DUPLICATE_SUCCESS"
      ) {
        const detail = err.detail as DuplicateSuccessDetail
        setPendingForce({
          payload: variables,
          existingJob: null,
          serverMessage: detail.message,
        })
        return
      }
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
    const payload: DispatchFidcEstoquePayload = {
      cnpj_fundo: fundo.cnpj,
      reference_date: referenceDate,
    }
    const existing = findRecentSuccess(fundo.cnpj, referenceDate)
    if (existing) {
      setPendingForce({
        payload,
        existingJob: existing,
        serverMessage: null,
      })
      return
    }
    dispatchMut.mutate(payload)
  }, [fundoId, fundosComCnpj, referenceDate, dispatchMut, findRecentSuccess])

  const handleConfirmForce = React.useCallback(() => {
    if (!pendingForce) return
    const p = pendingForce.payload
    setPendingForce(null)
    dispatchMut.mutate({ ...p, force: true })
  }, [pendingForce, dispatchMut])

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

          {lastFailedAttempt && (
            <div className="flex flex-col gap-1 rounded border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-700 dark:border-gray-800 dark:bg-gray-900 dark:text-gray-300">
              <div className="flex items-center gap-1.5">
                <Badge variant="warning">Atencao</Badge>
                <span className="font-medium text-gray-900 dark:text-gray-50">
                  Tentativa anterior: {failedLabel(lastFailedAttempt.status)}
                  {" "}({formatElapsed(lastFailedAttempt.created_at)} atras)
                </span>
              </div>
              {lastFailedAttempt.error_message && (
                <span className="text-gray-600 dark:text-gray-400">
                  {lastFailedAttempt.error_message}
                </span>
              )}
            </div>
          )}

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

      <ConfirmForceDialog
        pending={pendingForce}
        isPending={dispatchMut.isPending}
        onCancel={() => setPendingForce(null)}
        onConfirm={handleConfirmForce}
      />
    </Dialog>
  )
}

function failedLabel(status: QitechJobStatus): string {
  if (status === "EMPTY") return "veio vazia (Sem dados)"
  if (status === "TIMEOUT") return "timeout"
  if (status === "ERROR") return "erro"
  return status
}

// ─────────────────────────────────────────────────────────────────────────────
// ConfirmForceDialog — sub-dialog "ja existe snapshot, forcar novo?"
// ─────────────────────────────────────────────────────────────────────────────

function ConfirmForceDialog({
  pending,
  isPending,
  onCancel,
  onConfirm,
}: {
  pending: {
    payload: DispatchFidcEstoquePayload
    existingJob: QitechJob | null
    serverMessage: string | null
  } | null
  isPending: boolean
  onCancel: () => void
  onConfirm: () => void
}) {
  const open = pending !== null
  const existing = pending?.existingJob
  return (
    <Dialog open={open} onOpenChange={(o) => !o && onCancel()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Ja existe snapshot pra esta data</DialogTitle>
          <DialogDescription>
            {existing
              ? `Snapshot baixado em ${formatDateBR(existing.reference_date)} foi gerado ha ${formatElapsed(existing.created_at)}. Forcar novo disparo vai consumir uma consulta paga na QiTech e sobrescrever os dados canonicos quando o callback voltar.`
              : pending?.serverMessage ??
                "Outro disparo recente ja foi feito. Confirmar forca novo disparo."}
          </DialogDescription>
        </DialogHeader>

        <DialogFooter>
          <Button variant="ghost" onClick={onCancel} disabled={isPending}>
            Cancelar
          </Button>
          <Button onClick={onConfirm} disabled={isPending}>
            {isPending ? "Enviando..." : "Forcar novo disparo"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// Garantir que QitechJobStatus continua sendo um tipo usado (status no Badge).
// Se for retirar do enum no futuro, atualizar StatusBadge tambem.
export type { QitechJobStatus }
