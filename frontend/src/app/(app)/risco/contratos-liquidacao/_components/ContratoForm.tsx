"use client"

// Form do drawer de curadoria: os 3 campos DECLARADOS do contrato de
// liquidacao + justificativa (vira trilha de auditoria da versao nova).

import * as React from "react"
import { zodResolver } from "@hookform/resolvers/zod"
import { RiLoader4Line } from "@remixicon/react"
import { Controller, useForm } from "react-hook-form"

import { Button } from "@/components/tremor/Button"
import { Divider } from "@/components/tremor/Divider"
import { Label } from "@/components/tremor/Label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import { Textarea } from "@/components/tremor/Textarea"
import {
  BAIXA_MANUAL_LABELS,
  BOLETO_LABELS,
  contratoLiquidacaoSchema,
  FLUXO_LABELS,
  type ContratoLiquidacaoFormValues,
} from "@/lib/schemas/contrato-liquidacao-schema"

function FieldError({ message }: { message?: string }) {
  if (!message) return null
  return <p className="mt-1 text-xs text-red-600 dark:text-red-400">{message}</p>
}

function FieldHint({ children }: { children: React.ReactNode }) {
  return <p className="mt-1 text-xs text-gray-500 dark:text-gray-500">{children}</p>
}

type SelectFieldProps = {
  id: string
  label: string
  hint: string
  value: string
  onChange: (v: string) => void
  options: Record<string, string>
}

function SelectField({ id, label, hint, value, onChange, options }: SelectFieldProps) {
  return (
    <div>
      <Label htmlFor={id} className="font-medium">
        {label}
      </Label>
      <Select value={value} onValueChange={onChange}>
        <SelectTrigger id={id} className="mt-1.5">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {Object.entries(options).map(([v, l]) => (
            <SelectItem key={v} value={v}>
              {l}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      <FieldHint>{hint}</FieldHint>
    </div>
  )
}

type ContratoFormProps = {
  initial: ContratoLiquidacaoFormValues
  submitting: boolean
  submitLabel: string
  onSubmit: (values: ContratoLiquidacaoFormValues) => void
  onCancel: () => void
}

export function ContratoForm({
  initial,
  submitting,
  submitLabel,
  onSubmit,
  onCancel,
}: ContratoFormProps) {
  const form = useForm<ContratoLiquidacaoFormValues>({
    resolver: zodResolver(contratoLiquidacaoSchema),
    defaultValues: initial,
  })

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="flex flex-col gap-5">
      <Controller
        control={form.control}
        name="fluxo_esperado"
        render={({ field }) => (
          <SelectField
            id="fluxo-esperado"
            label="Fluxo esperado de liquidação"
            hint="Como o dinheiro deve chegar quando o sacado paga um título deste produto."
            value={field.value}
            onChange={field.onChange}
            options={FLUXO_LABELS}
          />
        )}
      />

      <Controller
        control={form.control}
        name="boleto"
        render={({ field }) => (
          <SelectField
            id="boleto"
            label="Boleto bancário"
            hint="Obrigatório: todo título deve ter boleto registrado. Permitido: pode acontecer, sem alerta. Não esperado: boleto neste produto é divergência."
            value={field.value}
            onChange={field.onChange}
            options={BOLETO_LABELS}
          />
        )}
      />

      <Controller
        control={form.control}
        name="baixa_manual"
        render={({ field }) => (
          <SelectField
            id="baixa-manual"
            label="Baixa manual"
            hint="Anômala: título bancarizado liquidado fora do trilho do banco vira sinal de investigação. Normal: faz parte da operação do produto."
            value={field.value}
            onChange={field.onChange}
            options={BAIXA_MANUAL_LABELS}
          />
        )}
      />

      <div>
        <Label htmlFor="justificativa" className="font-medium">
          Justificativa
        </Label>
        <Textarea
          id="justificativa"
          className="mt-1.5"
          rows={3}
          placeholder="Por que este contrato está sendo (re)definido? Fica registrado na versão."
          {...form.register("justificativa")}
        />
        <FieldError message={form.formState.errors.justificativa?.message} />
      </div>

      <Divider className="my-1" />

      <div className="flex items-center justify-end gap-2">
        <Button type="button" variant="secondary" onClick={onCancel} disabled={submitting}>
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
