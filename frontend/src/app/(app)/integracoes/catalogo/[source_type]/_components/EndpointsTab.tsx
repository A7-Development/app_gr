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
import {
  RiLoader4Line,
  RiPlayLine,
  RiSettings3Line,
  RiInboxLine,
  RiFileCopyLine,
  RiCheckLine,
} from "@remixicon/react"
import type { ColumnDef } from "@tanstack/react-table"

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
import { Switch } from "@/components/tremor/Switch"
import { Badge } from "@/components/tremor/Badge"
import { DataTableShell } from "@/design-system/components/DataTableShell"
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
  if (kind === "daily_at") return value ? `Âncora diária às ${value}` : "—"
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
  if (kind === "daily_at") return "Âncora diária"
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
              {/* global_id mono — facilita correlacao com logs e referencias
                  cruzadas no catalogo de proveniencia (Fase 1 2026-05-18). */}
              <span className={cx(tableTokens.cellTextMono, "text-gray-500")}>
                {ep.global_id}
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
          <LastSyncCell
            startedAt={row.original.last_sync_started_at}
            finishedAt={row.original.last_sync_finished_at}
            status={row.original.last_sync_status}
            errorMessage={row.original.last_sync_error}
          />
        ),
      },
      {
        id: "actions",
        header: "",
        cell: ({ row }) => {
          const isRowSyncing =
            syncMut.isPending &&
            syncMut.variables?.endpointName === row.original.name
          return (
          <div className="flex items-center justify-end gap-2">
            <Button
              variant="ghost"
              onClick={(e) => {
                e.stopPropagation()
                handleSyncNow(row.original)
              }}
              disabled={syncMut.isPending}
              title={isRowSyncing ? "Sincronizando…" : "Sincronizar agora"}
              aria-label={`Sincronizar ${row.original.label} agora`}
            >
              {isRowSyncing ? (
                <RiLoader4Line className="size-4 animate-spin text-blue-500" aria-hidden />
              ) : (
                <RiPlayLine className="size-4" aria-hidden />
              )}
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
          )
        },
      },
    ],
    [handleSyncNow, syncMut.isPending, syncMut.variables?.endpointName],
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

// ─────────────────────────────────────────────────────────────────────────────
// EndpointIdentifiers — bloco compacto mostrando global_id + handle + silver
// canonico. Copy-to-clipboard em cada linha. Sem caixa preta: admin enxerga
// qual codigo identifica este endpoint no sistema todo e qual tabela ele
// alimenta.
// ─────────────────────────────────────────────────────────────────────────────

function EndpointIdentifiers({
  globalId,
  tenantHandle,
  canonicalTable,
}: {
  globalId: string
  tenantHandle: string
  canonicalTable: string
}) {
  return (
    <div className="flex flex-col gap-1.5 rounded border border-gray-200 px-3 py-2.5 dark:border-gray-800">
      <CopyableId
        label="Endpoint global"
        value={globalId}
        hint="Identifica este endpoint em todo o sistema (admin + nome)."
      />
      <CopyableId
        label="Handle do tenant"
        value={tenantHandle}
        hint="Inclui o slug do tenant — usado em logs e suporte."
      />
      <div className="flex items-center gap-2">
        <span className="min-w-[7.5rem] text-[11px] font-medium text-gray-500 dark:text-gray-400">
          Tabela canônica
        </span>
        <code className="text-xs font-mono text-gray-700 dark:text-gray-300">
          {canonicalTable}
        </code>
      </div>
    </div>
  )
}

function CopyableId({
  label,
  value,
  hint,
}: {
  label: string
  value: string
  hint: string
}) {
  const [copied, setCopied] = React.useState(false)
  const handleCopy = React.useCallback(async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    } catch {
      toast.error("Falha ao copiar — copie manualmente.")
    }
  }, [value])

  return (
    <div className="flex items-center gap-2" title={hint}>
      <span className="min-w-[7.5rem] text-[11px] font-medium text-gray-500 dark:text-gray-400">
        {label}
      </span>
      <code className="flex-1 truncate text-xs font-mono text-gray-700 dark:text-gray-300">
        {value}
      </code>
      <button
        type="button"
        onClick={handleCopy}
        className="rounded p-1 text-gray-500 hover:bg-gray-100 hover:text-gray-700 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-200"
        aria-label={`Copiar ${label}`}
      >
        {copied ? (
          <RiCheckLine className="size-3.5 text-emerald-600 dark:text-emerald-400" aria-hidden />
        ) : (
          <RiFileCopyLine className="size-3.5" aria-hidden />
        )}
      </button>
    </div>
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
  { value: "daily_at", label: "Âncora diária" },
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

  // Tolerância: strings vazias representam "herda do catálogo" (null no PUT).
  // Inputs numéricos guardam string crua pra permitir digitação parcial.
  const [expectedLagStr, setExpectedLagStr] = React.useState("")
  const [toleranceStr, setToleranceStr] = React.useState("")
  const [giveUpStr, setGiveUpStr] = React.useState("")

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
    setExpectedLagStr(
      endpoint.expected_lag_business_days_override?.toString() ?? "",
    )
    setToleranceStr(
      endpoint.tolerance_business_days_override?.toString() ?? "",
    )
    setGiveUpStr(endpoint.give_up_business_days_override?.toString() ?? "")
  }, [endpoint])

  if (!endpoint) return null

  // Valores efetivos previstos com o que está atualmente no form. Usado pra
  // a pré-visualização ao vivo da seção Tolerância.
  const previewExpected =
    expectedLagStr === ""
      ? endpoint.default_expected_lag_business_days
      : Number.parseInt(expectedLagStr, 10)
  const previewTolerance =
    toleranceStr === ""
      ? endpoint.default_tolerance_business_days
      : Number.parseInt(toleranceStr, 10)
  const previewGiveUp =
    giveUpStr === ""
      ? endpoint.default_give_up_business_days
      : Number.parseInt(giveUpStr, 10)

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

    // Tolerância: string vazia = null (limpa override). Caso contrário,
    // valida que é inteiro >= 0 e enquadra na monotonia local antes de
    // mandar pro backend (que valida de novo contra defaults do catálogo).
    const parseToleranceField = (
      raw: string,
      max: number,
      label: string,
    ): number | null | "invalid" => {
      if (raw.trim() === "") return null
      const n = Number.parseInt(raw, 10)
      if (Number.isNaN(n) || n < 0 || n > max) {
        setError(
          `${label} precisa ser inteiro entre 0 e ${max}, ou vazio para herdar do catálogo.`,
        )
        return "invalid"
      }
      return n
    }
    const expectedOverride = parseToleranceField(
      expectedLagStr,
      30,
      "Esperado em D+",
    )
    if (expectedOverride === "invalid") return
    const toleranceOverride = parseToleranceField(
      toleranceStr,
      60,
      "Atrasado após",
    )
    if (toleranceOverride === "invalid") return
    const giveUpOverride = parseToleranceField(giveUpStr, 120, "Desistir após")
    if (giveUpOverride === "invalid") return

    // Pré-check de monotonicidade da janela efetiva (mesma fórmula do backend
    // mas em JS, pra feedback imediato sem round-trip).
    const eff = (override: number | null, defaultVal: number) =>
      override ?? defaultVal
    const effExpected = eff(
      expectedOverride,
      endpoint.default_expected_lag_business_days,
    )
    const effTolerance = eff(
      toleranceOverride,
      endpoint.default_tolerance_business_days,
    )
    const effGiveUp = eff(
      giveUpOverride,
      endpoint.default_give_up_business_days,
    )
    if (effTolerance < effExpected) {
      setError(
        `Janela inválida: "atrasado após" (${effTolerance}) precisa ser >= "esperado em D+" (${effExpected}).`,
      )
      return
    }
    if (effGiveUp < effTolerance) {
      setError(
        `Janela inválida: "desistir após" (${effGiveUp}) precisa ser >= "atrasado após" (${effTolerance}).`,
      )
      return
    }

    const payload: EndpointConfigPayload = {
      enabled,
      schedule_kind: kind,
      schedule_value: scheduleValue,
      environment,
      unidade_administrativa_id: uaId ?? null,
      expected_lag_business_days_override: expectedOverride,
      tolerance_business_days_override: toleranceOverride,
      give_up_business_days_override: giveUpOverride,
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
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{endpoint.label}</DialogTitle>
          <DialogDescription>{endpoint.description}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-4 py-2">
          {/* Identificadores do endpoint (Fase 1 do refactor de proveniencia
              transversal, 2026-05-18) — visivel pro admin SEM caixa preta. */}
          <EndpointIdentifiers
            globalId={endpoint.global_id}
            tenantHandle={endpoint.tenant_endpoint_handle}
            canonicalTable={endpoint.canonical_table}
          />

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
              <Label htmlFor="daily-input">
                Início do ciclo diário (HH:MM, São Paulo)
              </Label>
              <Input
                id="daily-input"
                type="time"
                value={dailyAtValue}
                onChange={(e) => setDailyAtValue(e.currentTarget.value)}
              />
              <p className={cx(tableTokens.cellSecondary, "leading-snug")}>
                Inicia o ciclo do dia neste horário. Continua tentando dentro
                do dia (cadência adaptativa por estado — ver{" "}
                <strong>Como tentamos buscar</strong> abaixo) até retorno OK
                ou furo definitivo. Default do catálogo:{" "}
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

          {/* Tolerância de publicação (2026-05-15) — quando começar a alertar
              que o relatório não chegou. Vide CLAUDE.md memoria
              project_qitech_freshness_followups + project_qitech_response_semantics. */}
          <div className="flex flex-col gap-2 rounded border border-gray-200 px-3 py-3 dark:border-gray-800">
            <div className="flex flex-col gap-0.5">
              <Label className="text-sm font-medium">
                Tolerância de publicação
              </Label>
              <span className={tableTokens.cellSecondary}>
                Quantos dias úteis ANBIMA esperar antes de considerar o dia
                atrasado, suspeito ou furo definitivo. Vazio = herda do
                catálogo (padrão por endpoint).
              </span>
            </div>
            <div className="grid grid-cols-3 gap-2 pt-1">
              <div className="flex flex-col gap-1">
                <Label htmlFor="expected-lag-input" className="text-xs">
                  Esperado em D+
                </Label>
                <Input
                  id="expected-lag-input"
                  type="number"
                  min={0}
                  max={30}
                  placeholder={String(
                    endpoint.default_expected_lag_business_days,
                  )}
                  value={expectedLagStr}
                  onChange={(e) => setExpectedLagStr(e.currentTarget.value)}
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="tolerance-input" className="text-xs">
                  Atrasado após D+
                </Label>
                <Input
                  id="tolerance-input"
                  type="number"
                  min={0}
                  max={60}
                  placeholder={String(
                    endpoint.default_tolerance_business_days,
                  )}
                  value={toleranceStr}
                  onChange={(e) => setToleranceStr(e.currentTarget.value)}
                />
              </div>
              <div className="flex flex-col gap-1">
                <Label htmlFor="give-up-input" className="text-xs">
                  Desistir após D+
                </Label>
                <Input
                  id="give-up-input"
                  type="number"
                  min={0}
                  max={120}
                  placeholder={String(
                    endpoint.default_give_up_business_days,
                  )}
                  value={giveUpStr}
                  onChange={(e) => setGiveUpStr(e.currentTarget.value)}
                />
              </div>
            </div>
            <p
              className={cx(
                tableTokens.cellSecondary,
                "leading-snug pt-1",
              )}
            >
              Pré-visualização efetiva:{" "}
              <strong>esperado em D+{previewExpected}</strong>,{" "}
              <strong>atrasado entre D+{previewExpected + 1} e D+
                {previewTolerance}</strong>
              , <strong>suspeito até D+{previewGiveUp}</strong>, depois disso
              vira furo definitivo (sistema para de tentar sozinho).
            </p>
          </div>

          {/* Informativo: como o sistema tenta — frequência fixa, NÃO é configurável.
              Documentado aqui pro usuário entender o vocabulário das janelas acima. */}
          <div className="rounded border border-gray-200 bg-gray-50 px-3 py-2 dark:border-gray-800 dark:bg-gray-900/40">
            <p className="text-xs font-medium text-gray-700 dark:text-gray-300">
              Como tentamos buscar
            </p>
            <ul className="mt-1.5 flex flex-col gap-0.5 text-xs text-gray-600 dark:text-gray-400">
              <li>
                <strong>Esperado</strong> — sistema tenta a cada tick do
                reconciler (~30 min).
              </li>
              <li>
                <strong>Atrasado</strong> — sistema tenta no máximo a cada 4h.
              </li>
              <li>
                <strong>Suspeito</strong> — sistema tenta no máximo 1x/dia +
                alerta na aba Cobertura.
              </li>
              <li>
                <strong>Furo definitivo</strong> — sistema para de tentar
                sozinho. Você pode reabrir manualmente na Cobertura.
              </li>
            </ul>
            <p
              className={cx(
                tableTokens.cellSecondary,
                "leading-snug pt-2",
              )}
            >
              A frequência das tentativas é fixa do sistema. Você define os
              limites entre os estados nos campos acima.
            </p>
          </div>

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
