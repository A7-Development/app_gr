"use client"

//
// Sync em massa por endpoint — Sheet lateral aberto a partir da aba Cobertura.
//
// Fluxo: usuario escolhe periodo (De/Ate) + 2 filtros opcionais (so dias uteis,
// pular ja coletados) → preview da contagem de dias → dispara um unico
// BackfillJob com o array de datas. Worker do backend ja processa
// sequencialmente respeitando timing entre chamadas.
//
// Cap de seguranca: 180 dias por disparo. Acima disso, bloqueia e pede pra
// quebrar em meses.
//

import * as React from "react"
import { format, parseISO } from "date-fns"
import { ptBR } from "date-fns/locale"

import {
  Button,
  DateRangePicker,
  type DateRange,
  Sheet,
  SheetBody,
  SheetContent,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  Switch,
} from "@/design-system/primitives"
import { cx } from "@/lib/utils"
import type { EndpointCoverage } from "@/lib/api-client"

const MAX_DATES_PER_DISPATCH = 180

export function BulkBackfillSheet({
  open,
  onOpenChange,
  endpoint,
  onSubmit,
  isSubmitting = false,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  /** null = sheet fechado/sem contexto. */
  endpoint: EndpointCoverage | null
  onSubmit: (endpointName: string, dates: string[]) => Promise<unknown> | void
  isSubmitting?: boolean
}) {
  const firstDay = endpoint?.days[0]?.data
  const lastDay = endpoint?.days[endpoint.days.length - 1]?.data

  const defaultRange = React.useMemo<DateRange | undefined>(() => {
    if (!firstDay || !lastDay) return undefined
    return { from: parseISO(firstDay), to: parseISO(lastDay) }
  }, [firstDay, lastDay])

  const [range, setRange] = React.useState<DateRange | undefined>(defaultRange)
  const [onlyBusinessDays, setOnlyBusinessDays] = React.useState(true)
  const [skipAlreadyOk, setSkipAlreadyOk] = React.useState(false)

  // Reset state quando troca de endpoint ou quando o sheet (re)abre — evita
  // que abrir o sheet pro endpoint B mostre o range do endpoint A.
  React.useEffect(() => {
    if (open) {
      setRange(defaultRange)
      setOnlyBusinessDays(true)
      setSkipAlreadyOk(false)
    }
  }, [open, defaultRange])

  const selectedDates = React.useMemo<string[]>(() => {
    if (!endpoint || !range?.from) return []
    const from = format(range.from, "yyyy-MM-dd")
    const to = format(range.to ?? range.from, "yyyy-MM-dd")
    return endpoint.days
      .filter((d) => d.data >= from && d.data <= to)
      .filter((d) => {
        if (
          onlyBusinessDays &&
          (d.status === "weekend" || d.status === "holiday")
        ) {
          return false
        }
        if (
          skipAlreadyOk &&
          d.status === "ok" &&
          (d.completeness === "complete" || d.completeness === null)
        ) {
          return false
        }
        // Status nao acionaveis nunca disparam backfill.
        if (d.status === "before_first_sync" || d.status === "unsupported") {
          return false
        }
        return true
      })
      .map((d) => d.data)
  }, [endpoint, range, onlyBusinessDays, skipAlreadyOk])

  const overCap = selectedDates.length > MAX_DATES_PER_DISPATCH
  const canSubmit =
    !isSubmitting && selectedDates.length > 0 && !overCap && Boolean(endpoint)

  const handleSubmit = async () => {
    if (!endpoint || !canSubmit) return
    await onSubmit(endpoint.name, selectedDates)
    onOpenChange(false)
  }

  const fromDate = firstDay ? parseISO(firstDay) : undefined
  const toDate = lastDay ? parseISO(lastDay) : undefined

  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent size="md">
        <SheetHeader className="pl-12">
          <SheetTitle>
            Sync em massa{endpoint ? ` — ${endpoint.label}` : ""}
          </SheetTitle>
        </SheetHeader>

        <SheetBody className="space-y-6">
          {/* Periodo */}
          <section className="space-y-2">
            <h3 className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Período
            </h3>
            <DateRangePicker
              value={range}
              onChange={setRange}
              locale={ptBR}
              fromDate={fromDate}
              toDate={toDate}
              className="w-full"
            />
            <p className="text-[11px] text-gray-500 dark:text-gray-400">
              Limitado ao range já carregado na Cobertura. Para datas mais
              antigas, troque o range no seletor do topo antes.
            </p>
          </section>

          {/* Filtros */}
          <section className="space-y-3">
            <h3 className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Filtros
            </h3>
            <ToggleRow
              label="Apenas dias úteis"
              description="Pula fins de semana e feriados (calendário ANBIMA)."
              checked={onlyBusinessDays}
              onCheckedChange={setOnlyBusinessDays}
            />
            <ToggleRow
              label="Pular dias já coletados"
              description="Exclui dias com status OK e payload completo."
              checked={skipAlreadyOk}
              onCheckedChange={setSkipAlreadyOk}
            />
          </section>

          {/* Preview */}
          <section className="space-y-2">
            <h3 className="text-[11px] font-medium uppercase tracking-wider text-gray-500 dark:text-gray-400">
              Preview
            </h3>
            <div
              className={cx(
                "rounded border p-3",
                overCap
                  ? "border-amber-300 bg-amber-50 dark:border-amber-900/50 dark:bg-amber-500/10"
                  : "border-gray-200 bg-gray-50 dark:border-gray-800 dark:bg-gray-900/40",
              )}
            >
              <p className="text-sm text-gray-900 dark:text-gray-100">
                <span className="font-medium">{selectedDates.length}</span>{" "}
                dia{selectedDates.length === 1 ? "" : "s"}{" "}
                {selectedDates.length === 1 ? "será" : "serão"} sincronizado
                {selectedDates.length === 1 ? "" : "s"}.
              </p>
              {overCap && (
                <p className="mt-1 text-[11px] text-amber-800 dark:text-amber-300">
                  Acima do limite de {MAX_DATES_PER_DISPATCH} dias por disparo.
                  Quebre em meses ou ajuste o range.
                </p>
              )}
              {selectedDates.length > 0 && !overCap && (
                <p className="mt-1 text-[11px] text-gray-500 dark:text-gray-400">
                  Worker dispara as chamadas sequencialmente respeitando timing
                  entre elas. Acompanhe o progresso na própria linha da
                  Cobertura.
                </p>
              )}
            </div>
            {selectedDates.length > 0 && selectedDates.length <= 60 && (
              <details className="text-[11px] text-gray-500 dark:text-gray-400">
                <summary className="cursor-pointer select-none">
                  Ver datas selecionadas
                </summary>
                <p className="mt-1 break-words">{selectedDates.join(", ")}</p>
              </details>
            )}
          </section>
        </SheetBody>

        <SheetFooter className="justify-end">
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancelar
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={!canSubmit}
            isLoading={isSubmitting}
          >
            Disparar{selectedDates.length > 0 ? ` ${selectedDates.length}` : ""}
          </Button>
        </SheetFooter>
      </SheetContent>
    </Sheet>
  )
}

function ToggleRow({
  label,
  description,
  checked,
  onCheckedChange,
}: {
  label: string
  description: string
  checked: boolean
  onCheckedChange: (v: boolean) => void
}) {
  return (
    <div className="flex items-start justify-between gap-3">
      <div className="space-y-0.5">
        <p className="text-sm text-gray-900 dark:text-gray-100">{label}</p>
        <p className="text-[11px] text-gray-500 dark:text-gray-400">
          {description}
        </p>
      </div>
      <Switch checked={checked} onCheckedChange={onCheckedChange} />
    </div>
  )
}
