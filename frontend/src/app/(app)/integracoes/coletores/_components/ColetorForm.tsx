"use client"

//
// ColetorForm — criar/editar um coletor (Strata Collector) e sua watch_config.
// Mesmo padrao do ProviderForm (admin IA): react-hook-form + zod, primitivos
// Tremor, footer Cancelar | Salvar, toast pelo caller.
//
// A watch_config e um array dinamico (useFieldArray): cada linha = uma pasta
// vigiada no servidor do cliente -> um source_label (esteira) no Strata.
//

import * as React from "react"
import { zodResolver } from "@hookform/resolvers/zod"
import { RiAddLine, RiDeleteBinLine, RiLoader4Line } from "@remixicon/react"
import { Controller, useFieldArray, useForm } from "react-hook-form"

import { Button } from "@/components/tremor/Button"
import { Divider } from "@/components/tremor/Divider"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import { Switch } from "@/components/tremor/Switch"
import {
  coletorFormSchema,
  WATCH_DEFAULTS,
  type ColetorFormValues,
} from "@/lib/schemas/coletor-schema"

function FieldError({ message }: { message?: string }) {
  if (!message) return null
  return (
    <span className="text-xs text-red-600 dark:text-red-500" role="alert">
      {message}
    </span>
  )
}

function FieldHint({ children }: { children: React.ReactNode }) {
  return (
    <span className="text-xs text-gray-500 dark:text-gray-400">{children}</span>
  )
}

function RequiredMarker() {
  return (
    <span className="ml-1 text-red-600 dark:text-red-500" aria-hidden>
      *
    </span>
  )
}

export type ColetorFormProps = {
  initial: ColetorFormValues
  submitting: boolean
  submitLabel: string
  onSubmit: (values: ColetorFormValues) => void
  onCancel: () => void
}

export function ColetorForm({
  initial,
  submitting,
  submitLabel,
  onSubmit,
  onCancel,
}: ColetorFormProps) {
  const form = useForm<ColetorFormValues>({
    resolver: zodResolver(coletorFormSchema),
    defaultValues: initial,
  })
  const watches = useFieldArray({ control: form.control, name: "watches" })
  const errors = form.formState.errors

  return (
    <form
      onSubmit={form.handleSubmit(onSubmit)}
      className="flex flex-col gap-5"
      noValidate
    >
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="coletor-name">
          Nome do coletor
          <RequiredMarker />
        </Label>
        <Input
          id="coletor-name"
          placeholder="Ex.: Servidor Bitfin — Financeiro"
          {...form.register("name")}
        />
        <FieldHint>
          Nome humano da maquina onde o agente roda. Aparece nesta lista e no
          instalador (teste de conexao).
        </FieldHint>
        <FieldError message={errors.name?.message} />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="coletor-interval">Intervalo de varredura (minutos)</Label>
        <Input
          id="coletor-interval"
          type="number"
          min={1}
          max={1440}
          className="w-32"
          {...form.register("scan_interval_minutes", { valueAsNumber: true })}
        />
        <FieldHint>
          De quanto em quanto tempo o agente varre as pastas e envia novidades.
        </FieldHint>
        <FieldError message={errors.scan_interval_minutes?.message} />
      </div>

      <Divider className="my-1" />

      <div className="flex items-center justify-between">
        <div className="flex flex-col">
          <span className="text-sm font-medium text-gray-900 dark:text-gray-100">
            Pastas monitoradas
          </span>
          <FieldHint>
            Cada pasta do servidor do cliente alimenta uma esteira
            (source_label) no Strata. O agente le esta lista a cada ciclo —
            editar aqui NAO exige tocar na maquina do cliente.
          </FieldHint>
        </div>
        <Button
          type="button"
          variant="secondary"
          onClick={() => watches.append(WATCH_DEFAULTS)}
        >
          <RiAddLine className="mr-1 size-4" aria-hidden />
          Pasta
        </Button>
      </div>

      {watches.fields.length === 0 && (
        <p className="rounded-md border border-dashed border-gray-300 p-4 text-center text-xs text-gray-500 dark:border-gray-700 dark:text-gray-400">
          Nenhuma pasta configurada — o agente conecta mas nao coleta nada.
        </p>
      )}

      {watches.fields.map((field, index) => {
        const watchErrors = errors.watches?.[index]
        return (
          <div
            key={field.id}
            className="flex flex-col gap-3 rounded-md border border-gray-200 p-3 dark:border-gray-800"
          >
            <div className="flex items-start justify-between gap-2">
              <div className="flex w-full flex-col gap-1.5">
                <Label htmlFor={`watch-path-${index}`}>
                  Pasta no servidor do cliente
                  <RequiredMarker />
                </Label>
                <Input
                  id={`watch-path-${index}`}
                  placeholder="Ex.: C:/Bitfin/Retorno"
                  {...form.register(`watches.${index}.path`)}
                />
                <FieldError message={watchErrors?.path?.message} />
              </div>
              <Button
                type="button"
                variant="ghost"
                className="mt-6 size-8 shrink-0 p-0 text-gray-500 hover:text-red-600 dark:hover:text-red-400"
                aria-label={`Remover pasta ${index + 1}`}
                onClick={() => watches.remove(index)}
              >
                <RiDeleteBinLine className="size-4" aria-hidden />
              </Button>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`watch-glob-${index}`}>Filtro de arquivos</Label>
                <Input
                  id={`watch-glob-${index}`}
                  placeholder="*.RET"
                  {...form.register(`watches.${index}.glob`)}
                />
                <FieldHint>Ex.: *.RET, *.xml, *.zip ou * (todos).</FieldHint>
                <FieldError message={watchErrors?.glob?.message} />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor={`watch-label-${index}`}>
                  Esteira (source_label)
                  <RequiredMarker />
                </Label>
                <Input
                  id={`watch-label-${index}`}
                  placeholder="cobranca_cnab"
                  {...form.register(`watches.${index}.source_label`)}
                />
                <FieldHint>Minusculas, numeros e _ .</FieldHint>
                <FieldError message={watchErrors?.source_label?.message} />
              </div>
            </div>

            <div className="flex items-center gap-2">
              <Controller
                control={form.control}
                name={`watches.${index}.zip`}
                render={({ field: zipField }) => (
                  <Switch
                    id={`watch-zip-${index}`}
                    checked={zipField.value}
                    onCheckedChange={zipField.onChange}
                  />
                )}
              />
              <Label htmlFor={`watch-zip-${index}`} className="cursor-pointer">
                Conteudo zipado (ex.: pacote diario)
              </Label>
              <FieldHint>
                O arquivo sobe intacto; o Strata descompacta no servidor.
              </FieldHint>
            </div>
          </div>
        )
      })}

      <Divider className="my-1" />

      <div className="flex items-center justify-end gap-2">
        <Button
          type="button"
          variant="secondary"
          onClick={onCancel}
          disabled={submitting}
        >
          Cancelar
        </Button>
        <Button type="submit" variant="primary" disabled={submitting}>
          {submitting && (
            <RiLoader4Line className="mr-1.5 size-4 animate-spin" aria-hidden />
          )}
          {submitLabel}
        </Button>
      </div>
    </form>
  )
}
