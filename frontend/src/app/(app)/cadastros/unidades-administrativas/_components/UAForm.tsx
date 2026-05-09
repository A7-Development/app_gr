"use client"

import * as React from "react"
import { useForm, Controller } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { RiLoader4Line } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { Divider } from "@/components/tremor/Divider"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import { Switch } from "@/components/tremor/Switch"
import type { TipoUA, UnidadeAdministrativa } from "@/lib/api-client"

const TIPOS: TipoUA[] = [
  "fidc",
  "consultoria",
  "securitizadora",
  "factoring",
  "gestora",
]

const TIPO_LABELS: Record<TipoUA, string> = {
  fidc: "FIDC",
  consultoria: "Consultoria",
  securitizadora: "Securitizadora",
  factoring: "Factoring",
  gestora: "Gestora",
}

const uaSchema = z.object({
  nome: z.string().min(1, "Nome e obrigatorio").max(200),
  tipo: z.enum(["fidc", "consultoria", "securitizadora", "factoring", "gestora"]),
  cnpj: z.string().max(18),
  ativa: z.boolean(),
})

export type UAFormValues = z.infer<typeof uaSchema>

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

function FormFooter({
  submitting,
  onCancel,
  submitLabel,
  isDirty,
}: {
  submitting: boolean
  onCancel: () => void
  submitLabel: string
  isDirty: boolean
}) {
  return (
    <div className="flex items-center justify-end gap-2">
      <Button
        type="button"
        variant="secondary"
        onClick={onCancel}
        disabled={submitting}
      >
        Cancelar
      </Button>
      <Button
        type="submit"
        variant="primary"
        disabled={submitting || !isDirty}
      >
        {submitting && (
          <RiLoader4Line
            className="mr-1.5 size-4 animate-spin"
            aria-hidden
          />
        )}
        {submitLabel}
      </Button>
    </div>
  )
}

// ─── CREATE ──────────────────────────────────────────────────────────────────

export type UACreateFormProps = {
  submitting: boolean
  onSubmit: (values: UAFormValues) => void
  onCancel: () => void
}

const CREATE_DEFAULTS: UAFormValues = {
  nome: "",
  tipo: "fidc",
  cnpj: "",
  ativa: true,
}

export function UACreateForm({
  submitting,
  onSubmit,
  onCancel,
}: UACreateFormProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isDirty },
  } = useForm<UAFormValues>({
    resolver: zodResolver(uaSchema),
    defaultValues: CREATE_DEFAULTS,
  })

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="flex flex-col gap-6"
      noValidate
    >
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
          Nova unidade administrativa
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Cadastre uma nova UA do tenant. CNPJ e opcional para UAs em formacao
          ou internas.
        </p>
      </div>

      <Divider />

      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="nome">
            Nome
            <RequiredMarker />
          </Label>
          <Input
            id="nome"
            placeholder="Ex.: REALINVEST FIDC"
            hasError={Boolean(errors.nome)}
            {...register("nome")}
          />
          <FieldError message={errors.nome?.message} />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="tipo">
            Tipo
            <RequiredMarker />
          </Label>
          <Controller
            control={control}
            name="tipo"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id="tipo" hasError={Boolean(errors.tipo)}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIPOS.map((t) => (
                    <SelectItem key={t} value={t}>
                      {TIPO_LABELS[t]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          <FieldError message={errors.tipo?.message} />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="cnpj">CNPJ (opcional)</Label>
          <Input
            id="cnpj"
            placeholder="00.000.000/0000-00 ou 14 digitos"
            inputMode="numeric"
            hasError={Boolean(errors.cnpj)}
            {...register("cnpj")}
          />
          {errors.cnpj ? (
            <FieldError message={errors.cnpj.message} />
          ) : (
            <FieldHint>
              Pode ficar vazio para UAs sem CNPJ proprio (em formacao, internas).
            </FieldHint>
          )}
        </div>

        <div className="flex items-center justify-between gap-4 rounded-md border border-gray-200 bg-gray-50 px-3 py-2.5 dark:border-gray-800 dark:bg-gray-900">
          <div className="flex flex-col gap-0.5">
            <Label htmlFor="ativa" className="text-sm font-medium">
              UA ativa
            </Label>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              UAs inativas nao aparecem em selecoes de integracao e BI.
            </span>
          </div>
          <Controller
            control={control}
            name="ativa"
            render={({ field }) => (
              <Switch
                id="ativa"
                checked={field.value}
                onCheckedChange={field.onChange}
              />
            )}
          />
        </div>
      </div>

      <Divider />

      <FormFooter
        submitting={submitting}
        onCancel={onCancel}
        submitLabel="Cadastrar UA"
        isDirty={isDirty}
      />
    </form>
  )
}

// ─── EDIT ────────────────────────────────────────────────────────────────────

export type UAEditFormProps = {
  initial: UnidadeAdministrativa
  submitting: boolean
  onSubmit: (values: UAFormValues) => void
  onCancel: () => void
}

export function UAEditForm({
  initial,
  submitting,
  onSubmit,
  onCancel,
}: UAEditFormProps) {
  const defaults: UAFormValues = React.useMemo(
    () => ({
      nome: initial.nome,
      tipo: initial.tipo,
      cnpj: initial.cnpj ?? "",
      ativa: initial.ativa,
    }),
    [initial],
  )

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isDirty },
  } = useForm<UAFormValues>({
    resolver: zodResolver(uaSchema),
    defaultValues: defaults,
  })

  React.useEffect(() => {
    reset(defaults)
  }, [defaults, reset])

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="flex flex-col gap-6"
      noValidate
    >
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
          Editar · {initial.nome}
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Atualize os dados da unidade administrativa.
        </p>
      </div>

      <Divider />

      <div className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="edit-nome">
            Nome
            <RequiredMarker />
          </Label>
          <Input
            id="edit-nome"
            placeholder="Ex.: REALINVEST FIDC"
            hasError={Boolean(errors.nome)}
            {...register("nome")}
          />
          <FieldError message={errors.nome?.message} />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="edit-tipo">
            Tipo
            <RequiredMarker />
          </Label>
          <Controller
            control={control}
            name="tipo"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id="edit-tipo" hasError={Boolean(errors.tipo)}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TIPOS.map((t) => (
                    <SelectItem key={t} value={t}>
                      {TIPO_LABELS[t]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          <FieldError message={errors.tipo?.message} />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="edit-cnpj">CNPJ (opcional)</Label>
          <Input
            id="edit-cnpj"
            placeholder="00.000.000/0000-00 ou 14 digitos"
            inputMode="numeric"
            hasError={Boolean(errors.cnpj)}
            {...register("cnpj")}
          />
          {errors.cnpj ? (
            <FieldError message={errors.cnpj.message} />
          ) : (
            <FieldHint>
              Pode ficar vazio para UAs sem CNPJ proprio (em formacao, internas).
            </FieldHint>
          )}
        </div>

        <div className="flex items-center justify-between gap-4 rounded-md border border-gray-200 bg-gray-50 px-3 py-2.5 dark:border-gray-800 dark:bg-gray-900">
          <div className="flex flex-col gap-0.5">
            <Label htmlFor="edit-ativa" className="text-sm font-medium">
              UA ativa
            </Label>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              UAs inativas nao aparecem em selecoes de integracao e BI.
            </span>
          </div>
          <Controller
            control={control}
            name="ativa"
            render={({ field }) => (
              <Switch
                id="edit-ativa"
                checked={field.value}
                onCheckedChange={field.onChange}
              />
            )}
          />
        </div>
      </div>

      <Divider />

      <FormFooter
        submitting={submitting}
        onCancel={onCancel}
        submitLabel="Salvar alteracoes"
        isDirty={isDirty}
      />
    </form>
  )
}
