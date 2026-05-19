"use client"

import * as React from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"

import { Button } from "@/components/tremor/Button"
import { Checkbox } from "@/components/tremor/Checkbox"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/tremor/Select"
import type { ModuleId, TenantCreatePayload, TenantStatusId } from "@/lib/api-client"

const MODULES: { id: ModuleId; label: string; defaultOn: boolean }[] = [
  { id: "bi",             label: "BI",             defaultOn: true  },
  { id: "cadastros",      label: "Cadastros",      defaultOn: true  },
  { id: "operacoes",      label: "Operacoes",      defaultOn: false },
  { id: "credito",        label: "Credito",        defaultOn: false },
  { id: "controladoria",  label: "Controladoria",  defaultOn: false },
  { id: "risco",          label: "Risco",          defaultOn: false },
  { id: "integracoes",    label: "Integracoes",    defaultOn: true  },
  { id: "laboratorio",    label: "Laboratorio",    defaultOn: false },
  { id: "admin",          label: "Admin",          defaultOn: true  },
]

const STATUSES: { value: TenantStatusId; label: string; description: string }[] = [
  { value: "trial",     label: "Trial",     description: "Periodo de avaliacao com prazo." },
  { value: "active",    label: "Ativo",     description: "Contratado, plenamente operacional." },
  { value: "suspended", label: "Suspenso",  description: "Login bloqueado por inadimplencia/abuso." },
  { value: "cancelled", label: "Cancelado", description: "Encerrado. Login bloqueado, dado preservado." },
]

const schema = z.object({
  slug: z
    .string()
    .min(2, "Minimo 2 caracteres")
    .max(100)
    .regex(
      /^[a-z0-9](?:[a-z0-9-]*[a-z0-9])?$/,
      "Apenas minusculas, numeros e hifen (nao comeca/termina com hifen)",
    ),
  name: z.string().min(2, "Minimo 2 caracteres").max(255),
  owner_email: z.string().email("Email invalido"),
  status: z.enum(["trial", "active", "suspended", "cancelled"]),
  trial_ends_at: z.string().optional(),
  modules: z.record(z.string(), z.boolean()),
})

type FormValues = z.infer<typeof schema>

export function TenantCreateForm({
  submitting,
  onSubmit,
  onCancel,
}: {
  submitting: boolean
  onSubmit: (payload: TenantCreatePayload) => Promise<void> | void
  onCancel: () => void
}) {
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      slug: "",
      name: "",
      owner_email: "",
      status: "trial",
      trial_ends_at: "",
      modules: Object.fromEntries(MODULES.map((m) => [m.id, m.defaultOn])),
    },
  })

  const errors = form.formState.errors
  const status = form.watch("status")
  const modules = form.watch("modules")

  async function handleSubmit(values: FormValues) {
    const enabled = MODULES.filter((m) => values.modules[m.id]).map((m) => m.id)
    const payload: TenantCreatePayload = {
      slug: values.slug.trim(),
      name: values.name.trim(),
      owner_email: values.owner_email.trim(),
      status: values.status,
      trial_ends_at: values.status === "trial" && values.trial_ends_at
        ? new Date(values.trial_ends_at).toISOString()
        : null,
      enabled_modules: enabled,
    }
    await onSubmit(payload)
  }

  return (
    <form onSubmit={form.handleSubmit(handleSubmit)} className="flex flex-col gap-5">
      <section className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="slug" className="text-[13px] font-medium">
            Slug <span className="text-red-600">*</span>
          </Label>
          <Input
            id="slug"
            placeholder="cliente-acme"
            autoComplete="off"
            spellCheck={false}
            disabled={submitting}
            hasError={!!errors.slug}
            {...form.register("slug")}
          />
          <p className="text-xs text-gray-500">
            Identificador url-friendly. Aparece em /auth/login (?slug=...) e em
            integracoes externas. Nao pode ser alterado depois.
          </p>
          {errors.slug && (
            <p role="alert" className="text-xs text-red-600 dark:text-red-400">
              {errors.slug.message}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="name" className="text-[13px] font-medium">
            Nome <span className="text-red-600">*</span>
          </Label>
          <Input
            id="name"
            placeholder="Cliente ACME Ltda."
            disabled={submitting}
            hasError={!!errors.name}
            {...form.register("name")}
          />
          {errors.name && (
            <p role="alert" className="text-xs text-red-600 dark:text-red-400">
              {errors.name.message}
            </p>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="owner_email" className="text-[13px] font-medium">
            Email do primeiro Owner <span className="text-red-600">*</span>
          </Label>
          <Input
            id="owner_email"
            type="email"
            placeholder="responsavel@cliente.com.br"
            disabled={submitting}
            hasError={!!errors.owner_email}
            {...form.register("owner_email")}
          />
          <p className="text-xs text-gray-500">
            Sera convidado como Owner do tenant. Voce recebe o link de aceite
            (valido por 7 dias) na proxima tela.
          </p>
          {errors.owner_email && (
            <p role="alert" className="text-xs text-red-600 dark:text-red-400">
              {errors.owner_email.message}
            </p>
          )}
        </div>
      </section>

      <section className="flex flex-col gap-4 border-t border-gray-200 pt-5 dark:border-gray-800">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="status" className="text-[13px] font-medium">Status</Label>
          <Select
            value={status}
            onValueChange={(v) => form.setValue("status", v as TenantStatusId, { shouldValidate: true })}
            disabled={submitting}
          >
            <SelectTrigger id="status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUSES.map((s) => (
                <SelectItem key={s.value} value={s.value}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-gray-500">
            {STATUSES.find((s) => s.value === status)?.description}
          </p>
        </div>

        {status === "trial" && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="trial_ends_at" className="text-[13px] font-medium">
              Trial termina em
            </Label>
            <Input
              id="trial_ends_at"
              type="date"
              disabled={submitting}
              {...form.register("trial_ends_at")}
            />
          </div>
        )}
      </section>

      <section className="flex flex-col gap-2 border-t border-gray-200 pt-5 dark:border-gray-800">
        <Label className="text-[13px] font-medium">Modulos contratados</Label>
        <p className="text-xs text-gray-500">
          Marque os modulos que este tenant tem direito de usar. Pode mudar
          depois pelo painel do tenant.
        </p>
        <div className="mt-2 grid grid-cols-2 gap-2.5">
          {MODULES.map((m) => (
            <label
              key={m.id}
              className="flex cursor-pointer items-center gap-2 rounded-md border border-gray-200 px-3 py-2 hover:border-gray-300 dark:border-gray-800 dark:hover:border-gray-700"
            >
              <Checkbox
                checked={!!modules?.[m.id]}
                onCheckedChange={(v) =>
                  form.setValue(`modules.${m.id}`, v === true, { shouldDirty: true })
                }
                disabled={submitting}
              />
              <span className="text-sm text-gray-900 dark:text-gray-100">{m.label}</span>
            </label>
          ))}
        </div>
      </section>

      <div className="flex justify-end gap-2 border-t border-gray-200 pt-5 dark:border-gray-800">
        <Button type="button" variant="secondary" onClick={onCancel} disabled={submitting}>
          Cancelar
        </Button>
        <Button type="submit" variant="primary" disabled={submitting}>
          {submitting ? "Criando..." : "Criar tenant + convidar Owner"}
        </Button>
      </div>
    </form>
  )
}
