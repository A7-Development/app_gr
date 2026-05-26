"use client"

//
// Sync em massa por endpoint — Sheet lateral aberto a partir da aba Cobertura.
//
// Fluxo: usuario escolhe periodo (De/Ate) + 2 filtros opcionais (so dias uteis,
// pular ja coletados) → preview da contagem de dias → dispara um unico
// BackfillJob com o array de datas. Worker do backend ja processa
// sequencialmente respeitando timing entre chamadas.
//
// Seletor de periodo: dois inputs de texto (De / Ate) onde o usuario DIGITA a
// data no formato dd/mm/aaaa. Mascara aplicada conforme digita (insere as
// barras), parse + validacao via date-fns, e revert para o ultimo valor valido
// no blur se ficar incompleto/invalido. Escolha trocada de calendario livre e
// depois de dropdown de datas pre-definidas por digitacao direta (pedido do
// Ricardo). Com dois valores independentes + clamp (digitar De depois do Ate
// arrasta o Ate junto, e vice-versa) e impossivel travar numa combinacao
// invalida.
//
// Cap de seguranca: 180 dias por disparo. Acima disso, bloqueia e pede pra
// quebrar em meses.
//

import * as React from "react"
import { format, isValid, parse, parseISO } from "date-fns"

import {
  Button,
  Input,
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

const ISO_FMT = "yyyy-MM-dd"
const BR_FMT = "dd/MM/yyyy"

/** Aplica mascara dd/mm/aaaa conforme digita (insere as barras). */
function maskDateInput(raw: string): string {
  const d = raw.replace(/\D/g, "").slice(0, 8)
  let out = d.slice(0, 2)
  if (d.length > 2) out += "/" + d.slice(2, 4)
  if (d.length > 4) out += "/" + d.slice(4, 8)
  return out
}

/** "dd/MM/yyyy" digitado -> ISO yyyy-MM-dd, ou null se incompleto/invalido. */
function parseTypedDate(text: string): string | null {
  if (text.length !== 10) return null
  const d = parse(text, BR_FMT, new Date())
  if (!isValid(d)) return null
  // Guarda round-trip: rejeita 31/02 etc. que o parse poderia normalizar.
  if (format(d, BR_FMT) !== text) return null
  return format(d, ISO_FMT)
}

function isoToBr(iso: string): string {
  return iso ? format(parseISO(iso), BR_FMT) : ""
}

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

  const [fromDate, setFromDate] = React.useState<string>(firstDay ?? "")
  const [toDate, setToDate] = React.useState<string>(lastDay ?? "")
  const [onlyBusinessDays, setOnlyBusinessDays] = React.useState(true)
  const [skipAlreadyOk, setSkipAlreadyOk] = React.useState(false)

  // Reset state quando troca de endpoint ou quando o sheet (re)abre — evita
  // que abrir o sheet pro endpoint B mostre o range do endpoint A.
  React.useEffect(() => {
    if (open) {
      setFromDate(firstDay ?? "")
      setToDate(lastDay ?? "")
      setOnlyBusinessDays(true)
      setSkipAlreadyOk(false)
    }
  }, [open, firstDay, lastDay])

  // Clamp: manter sempre fromDate <= toDate sem nunca bloquear uma escolha.
  // Comparacao lexicografica de yyyy-MM-dd == comparacao cronologica.
  const handleFromChange = React.useCallback(
    (v: string) => {
      setFromDate(v)
      if (toDate && v > toDate) setToDate(v)
    },
    [toDate],
  )
  const handleToChange = React.useCallback(
    (v: string) => {
      setToDate(v)
      if (fromDate && v < fromDate) setFromDate(v)
    },
    [fromDate],
  )

  const selectedDates = React.useMemo<string[]>(() => {
    if (!endpoint || !fromDate) return []
    const from = fromDate
    const to = toDate || fromDate
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
  }, [endpoint, fromDate, toDate, onlyBusinessDays, skipAlreadyOk])

  const overCap = selectedDates.length > MAX_DATES_PER_DISPATCH
  const canSubmit =
    !isSubmitting && selectedDates.length > 0 && !overCap && Boolean(endpoint)

  const handleSubmit = async () => {
    if (!endpoint || !canSubmit) return
    await onSubmit(endpoint.name, selectedDates)
    onOpenChange(false)
  }

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
            <div className="grid grid-cols-[2.5rem_1fr] items-center gap-x-3 gap-y-2">
              <label
                htmlFor="bulk-from"
                className="text-[13px] text-gray-600 dark:text-gray-400"
              >
                De
              </label>
              <DateTextInput
                id="bulk-from"
                ariaLabel="Data inicial (dd/mm/aaaa)"
                value={fromDate}
                onValueChange={handleFromChange}
              />
              <label
                htmlFor="bulk-to"
                className="text-[13px] text-gray-600 dark:text-gray-400"
              >
                Até
              </label>
              <DateTextInput
                id="bulk-to"
                ariaLabel="Data final (dd/mm/aaaa)"
                value={toDate}
                onValueChange={handleToChange}
              />
            </div>
            <p className="text-[11px] text-gray-500 dark:text-gray-400">
              Digite no formato dd/mm/aaaa. Limitado ao range já carregado na
              Cobertura — para datas mais antigas, troque o range no seletor do
              topo antes.
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

function DateTextInput({
  id,
  ariaLabel,
  value,
  onValueChange,
}: {
  id: string
  ariaLabel: string
  /** ISO yyyy-MM-dd ou "". */
  value: string
  onValueChange: (iso: string) => void
}) {
  const [text, setText] = React.useState<string>(() => isoToBr(value))

  // Sincroniza quando o value externo muda (clamp, reset ao abrir/trocar
  // endpoint). Quando o usuario digita, o ISO resultante ja casa com o texto,
  // entao isso vira no-op e nao mexe no cursor.
  React.useEffect(() => {
    setText(isoToBr(value))
  }, [value])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const masked = maskDateInput(e.target.value)
    setText(masked)
    const iso = parseTypedDate(masked)
    if (iso) onValueChange(iso)
  }

  const handleBlur = () => {
    // Texto incompleto/invalido ao sair do campo volta pro ultimo valor valido.
    if (!parseTypedDate(text)) setText(isoToBr(value))
  }

  const hasError = text.length === 10 && parseTypedDate(text) === null

  return (
    <Input
      id={id}
      aria-label={ariaLabel}
      inputMode="numeric"
      autoComplete="off"
      placeholder="dd/mm/aaaa"
      value={text}
      onChange={handleChange}
      onBlur={handleBlur}
      hasError={hasError}
    />
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
