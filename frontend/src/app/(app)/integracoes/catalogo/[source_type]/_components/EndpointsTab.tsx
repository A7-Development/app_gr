"use client"

//
// Tab "Endpoints" da pagina de detalhe de uma fonte.
//
// Granularidade fina (CLAUDE.md §13 — refactor 2026-05-05): cada source pode
// ter N endpoints, cada um com cadencia propria. A pagina lista o catalogo
// declarativo (default) e o override do tenant (quando existe) para cada
// endpoint daquela fonte.
//
// Edicao via Dialog (escolha pragmatica para edicao curta): SegmentSwitch
// para schedule_kind, input apropriado por kind, switch enabled, botao
// "Sincronizar agora". Para sources sem catalogo (Serasa, etc) renderiza
// estado vazio explicativo.
//

import * as React from "react"
import { toast } from "sonner"
import { RiPlayLine, RiSettings3Line, RiInboxLine } from "@remixicon/react"
import type { ColumnDef } from "@tanstack/react-table"

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
import { Switch } from "@/components/tremor/Switch"
import { Badge } from "@/components/tremor/Badge"
import { DataTableShell } from "@/design-system/components/DataTableShell"
import { EmptyState } from "@/design-system/components/EmptyState"
import { LastSyncCell } from "@/design-system/components/LastSyncCell"
import { SegmentSwitch } from "@/design-system/components/SegmentSwitch"
import { tableTokens } from "@/design-system/tokens/table"
import { cx } from "@/lib/utils"
import {
  useSourceEndpoints,
  useSyncEndpoint,
  useUpdateEndpoint,
} from "@/lib/hooks/integracoes"
import type {
  EndpointConfigPayload,
  EndpointDetail,
  Environment,
  ScheduleKind,
  SourceTypeId,
} from "@/lib/api-client"

// ─────────────────────────────────────────────────────────────────────────────
// Helpers de derivacao (catalogo + override)
// ─────────────────────────────────────────────────────────────────────────────

function effectiveKind(detail: EndpointDetail): ScheduleKind {
  return detail.schedule_kind ?? detail.default_schedule_kind
}

function effectiveValue(detail: EndpointDetail): string | null {
  return detail.schedule_value ?? detail.default_schedule_value
}

function effectiveEnabled(detail: EndpointDetail): boolean {
  // null = nunca persistido = consideramos habilitado (segue catalogo).
  return detail.enabled ?? true
}

function formatScheduleSummary(detail: EndpointDetail): string {
  const kind = effectiveKind(detail)
  const value = effectiveValue(detail)
  if (kind === "interval") return value ? `A cada ${value} min` : "—"
  if (kind === "daily_at") return value ? `Diário às ${value}` : "—"
  return "Sob demanda"
}

function kindBadgeVariant(
  kind: ScheduleKind,
): "default" | "neutral" | "success" | "warning" | "error" {
  if (kind === "interval") return "default"
  if (kind === "daily_at") return "success"
  return "neutral"
}

function kindBadgeLabel(kind: ScheduleKind): string {
  if (kind === "interval") return "Intervalo"
  if (kind === "daily_at") return "Diário"
  return "Sob demanda"
}

// ─────────────────────────────────────────────────────────────────────────────
// EndpointsTab
// ─────────────────────────────────────────────────────────────────────────────

type EndpointsTabProps = {
  sourceType: SourceTypeId
  environment: Environment
  uaId?: string | null
}

export function EndpointsTab({
  sourceType,
  environment,
  uaId,
}: EndpointsTabProps) {
  const { data: endpoints, isLoading } = useSourceEndpoints(
    sourceType,
    environment,
    uaId,
  )
  const [editing, setEditing] = React.useState<EndpointDetail | null>(null)
  const syncMut = useSyncEndpoint(sourceType)

  const handleSyncNow = React.useCallback(
    async (ep: EndpointDetail) => {
      try {
        const result = await syncMut.mutateAsync({
          endpointName: ep.name,
          environment,
          uaId,
        })
        if (result.ok) {
          toast.success(`Sync de "${ep.label}" concluído.`)
        } else {
          toast.error(
            `Sync de "${ep.label}" falhou: ${result.errors.join("; ") || "erro desconhecido"}`,
          )
        }
      } catch (err) {
        toast.error(
          `Falha ao disparar sync: ${err instanceof Error ? err.message : String(err)}`,
        )
      }
    },
    [syncMut, environment, uaId],
  )

  const columns = React.useMemo<ColumnDef<EndpointDetail, unknown>[]>(
    () => [
      {
        id: "label",
        header: "Endpoint",
        accessorKey: "label",
        cell: ({ row }) => {
          const ep = row.original
          return (
            <div className="flex flex-col gap-0.5">
              <span className={tableTokens.cellStrong}>{ep.label}</span>
              <span className={tableTokens.cellSecondary}>
                {ep.description}
              </span>
            </div>
          )
        },
      },
      {
        id: "kind",
        header: "Modo",
        cell: ({ row }) => {
          const k = effectiveKind(row.original)
          return <Badge variant={kindBadgeVariant(k)}>{kindBadgeLabel(k)}</Badge>
        },
      },
      {
        id: "schedule",
        header: "Cadência",
        cell: ({ row }) => (
          <span className={tableTokens.cellNumber}>
            {formatScheduleSummary(row.original)}
          </span>
        ),
      },
      {
        id: "state",
        header: "Estado",
        cell: ({ row }) => (
          <EndpointStateBadge
            enabled={effectiveEnabled(row.original)}
            status={row.original.last_sync_status}
          />
        ),
      },
      {
        id: "last_sync",
        header: "Último sync",
        cell: ({ row }) => (
          <LastSyncCell iso={row.original.last_sync_started_at} />
        ),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => (
          <div className="flex items-center justify-end gap-2">
            <Button
              variant="ghost"
              onClick={(e) => {
                e.stopPropagation()
                handleSyncNow(row.original)
              }}
              disabled={syncMut.isPending}
              title="Sincronizar agora"
              aria-label={`Sincronizar ${row.original.label} agora`}
            >
              <RiPlayLine className="size-4" aria-hidden />
            </Button>
            <Button
              variant="ghost"
              onClick={(e) => {
                e.stopPropagation()
                setEditing(row.original)
              }}
              title="Configurar"
              aria-label={`Configurar ${row.original.label}`}
            >
              <RiSettings3Line className="size-4" aria-hidden />
            </Button>
          </div>
        ),
      },
    ],
    [handleSyncNow, syncMut.isPending],
  )

  const rows = endpoints ?? []

  return (
    <>
      <div className="flex flex-col gap-3">
        <DataTableShell<EndpointDetail>
          data={rows}
          columns={columns}
          loading={isLoading}
          onRowClick={(ep) => setEditing(ep)}
          emptyState={{
            icon: RiInboxLine,
            title: "Sem catálogo de endpoints",
            description:
              "Esta fonte não participa do agendamento por endpoint — geralmente porque é consulta sob demanda (bureau) ou ainda não tem catálogo declarativo registrado no adapter.",
          }}
        />
      </div>

      <EndpointEditorDialog
        endpoint={editing}
        sourceType={sourceType}
        environment={environment}
        uaId={uaId}
        onClose={() => setEditing(null)}
      />
    </>
  )
}

function EndpointStateBadge({
  enabled,
  status,
}: {
  enabled: boolean
  status: EndpointDetail["last_sync_status"]
}) {
  if (!enabled) return <Badge variant="neutral">Desligado</Badge>
  if (status === "em_progresso") return <Badge variant="warning">Em curso</Badge>
  if (status === "erro") return <Badge variant="error">Erro</Badge>
  if (status === "ok") return <Badge variant="success">OK</Badge>
  return <Badge variant="neutral">Aguardando</Badge>
}

// ─────────────────────────────────────────────────────────────────────────────
// EndpointEditorDialog
// ─────────────────────────────────────────────────────────────────────────────

const KIND_OPTIONS: ReadonlyArray<{ value: ScheduleKind; label: string }> = [
  { value: "interval", label: "Intervalo" },
  { value: "daily_at", label: "Diário às" },
  { value: "on_demand", label: "Sob demanda" },
]

function EndpointEditorDialog({
  endpoint,
  sourceType,
  environment,
  uaId,
  onClose,
}: {
  endpoint: EndpointDetail | null
  sourceType: SourceTypeId
  environment: Environment
  uaId?: string | null
  onClose: () => void
}) {
  const updateMut = useUpdateEndpoint(sourceType)

  const [kind, setKind] = React.useState<ScheduleKind>("interval")
  const [intervalValue, setIntervalValue] = React.useState("60")
  const [dailyAtValue, setDailyAtValue] = React.useState("07:00")
  const [enabled, setEnabled] = React.useState(true)
  const [error, setError] = React.useState<string | null>(null)

  // Sincroniza o estado do form quando o endpoint muda (open/close).
  React.useEffect(() => {
    if (!endpoint) return
    const k = effectiveKind(endpoint)
    const v = effectiveValue(endpoint)
    setKind(k)
    setEnabled(effectiveEnabled(endpoint))
    setError(null)
    if (k === "interval" && v) setIntervalValue(v)
    if (k === "daily_at" && v) setDailyAtValue(v)
  }, [endpoint])

  if (!endpoint) return null

  const handleSave = async () => {
    setError(null)

    let scheduleValue: string | null = null
    if (kind === "interval") {
      const n = parseInt(intervalValue, 10)
      if (Number.isNaN(n) || n < 15 || n > 1440) {
        setError("Intervalo precisa ser número inteiro entre 15 e 1440 minutos.")
        return
      }
      scheduleValue = String(n)
    } else if (kind === "daily_at") {
      const ok = /^([01]\d|2[0-3]):[0-5]\d$/.test(dailyAtValue)
      if (!ok) {
        setError("Horário deve estar no formato HH:MM (24h).")
        return
      }
      scheduleValue = dailyAtValue
    }
    // on_demand → schedule_value fica null

    const payload: EndpointConfigPayload = {
      enabled,
      schedule_kind: kind,
      schedule_value: scheduleValue,
      environment,
      unidade_administrativa_id: uaId ?? null,
    }

    try {
      await updateMut.mutateAsync({
        endpointName: endpoint.name,
        payload,
      })
      toast.success(`Cadência de "${endpoint.label}" atualizada.`)
      onClose()
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg)
      toast.error(`Falha ao salvar: ${msg}`)
    }
  }

  return (
    <Dialog open={!!endpoint} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{endpoint.label}</DialogTitle>
          <DialogDescription>{endpoint.description}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          {/* Modo */}
          <div className="flex flex-col gap-1.5">
            <Label>Modo de agendamento</Label>
            <SegmentSwitch
              value={kind}
              onChange={(v) => setKind(v as ScheduleKind)}
              options={KIND_OPTIONS.map((o) => ({
                value: o.value,
                label: o.label,
              }))}
              ariaLabel="Modo de agendamento"
            />
          </div>

          {/* Valor */}
          {kind === "interval" && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="interval-input">Intervalo (minutos)</Label>
              <Input
                id="interval-input"
                type="number"
                min={15}
                max={1440}
                value={intervalValue}
                onChange={(e) => setIntervalValue(e.currentTarget.value)}
              />
              <p className={cx(tableTokens.cellSecondary, "leading-snug")}>
                Permitido entre 15 e 1440 (24h). Default do catálogo:{" "}
                {endpoint.default_schedule_kind === "interval"
                  ? `${endpoint.default_schedule_value} min`
                  : "diferente do modo atual"}
                .
              </p>
            </div>
          )}

          {kind === "daily_at" && (
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="daily-input">Horário (HH:MM, São Paulo)</Label>
              <Input
                id="daily-input"
                type="time"
                value={dailyAtValue}
                onChange={(e) => setDailyAtValue(e.currentTarget.value)}
              />
              <p className={cx(tableTokens.cellSecondary, "leading-snug")}>
                Roda uma vez por dia no horário configurado. Default do
                catálogo:{" "}
                {endpoint.default_schedule_kind === "daily_at"
                  ? endpoint.default_schedule_value
                  : "diferente do modo atual"}
                .
              </p>
            </div>
          )}

          {kind === "on_demand" && (
            <div className="rounded border border-gray-200 bg-gray-50 px-3 py-2 text-xs text-gray-700 dark:border-gray-800 dark:bg-gray-900/40 dark:text-gray-300">
              Endpoint não entra no scheduler. Sincronizações acontecem apenas
              quando você clica em <strong>Sincronizar agora</strong> ou via
              ações de outros módulos (ex.: workflow do crédito).
            </div>
          )}

          {/* Enabled */}
          <div className="flex items-center justify-between gap-3 rounded border border-gray-200 px-3 py-2 dark:border-gray-800">
            <div className="flex flex-col gap-0.5">
              <Label htmlFor="enabled-switch" className="text-sm font-medium">
                Endpoint habilitado
              </Label>
              <span className={tableTokens.cellSecondary}>
                Quando desligado, o endpoint não roda mesmo no modo configurado.
              </span>
            </div>
            <Switch
              id="enabled-switch"
              checked={enabled}
              onCheckedChange={setEnabled}
            />
          </div>

          {error && (
            <div className="rounded border border-red-300 bg-red-50 px-3 py-2 text-xs text-red-700 dark:border-red-700 dark:bg-red-950 dark:text-red-300">
              {error}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} disabled={updateMut.isPending}>
            Cancelar
          </Button>
          <Button onClick={handleSave} disabled={updateMut.isPending}>
            {updateMut.isPending ? "Salvando…" : "Salvar"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
