"use client"

import * as React from "react"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"

import { Button } from "@/components/tremor/Button"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/tremor/Select"
import type { InvitationCreatePayload, TenantRoleId } from "@/lib/api-client"

const ROLES: { value: TenantRoleId; label: string; description: string }[] = [
  {
    value: "owner",
    label: "Owner",
    description: "Gere o tenant, convida users, ativa/desativa modulos. Sem limites internos.",
  },
  {
    value: "member",
    label: "Member",
    description: "Opera o produto. Write em Cadastros/Operacoes/Credito; Read em BI/Controladoria/Risco.",
  },
  {
    value: "viewer",
    label: "Viewer",
    description: "Read-only em tudo. Sem acesso a Integracoes e Admin.",
  },
]

const schema = z.object({
  email: z.string().email("Email invalido"),
  role: z.enum(["owner", "member", "viewer"]),
})

type FormValues = z.infer<typeof schema>

export function UserInviteForm({
  submitting,
  onSubmit,
  onCancel,
}: {
  submitting: boolean
  onSubmit: (payload: InvitationCreatePayload) => Promise<void> | void
  onCancel: () => void
}) {
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { email: "", role: "member" },
  })

  const errors = form.formState.errors
  const role = form.watch("role")

  async function handleSubmit(values: FormValues) {
    await onSubmit({ email: values.email.trim(), role: values.role })
  }

  return (
    <form onSubmit={form.handleSubmit(handleSubmit)} className="flex flex-col gap-5">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="email" className="text-[13px] font-medium">
          Email <span className="text-red-600">*</span>
        </Label>
        <Input
          id="email"
          type="email"
          placeholder="colega@empresa.com.br"
          disabled={submitting}
          hasError={!!errors.email}
          {...form.register("email")}
        />
        {errors.email && (
          <p role="alert" className="text-xs text-red-600 dark:text-red-400">
            {errors.email.message}
          </p>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="role" className="text-[13px] font-medium">Role</Label>
        <Select
          value={role}
          onValueChange={(v) => form.setValue("role", v as TenantRoleId, { shouldValidate: true })}
          disabled={submitting}
        >
          <SelectTrigger id="role">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {ROLES.map((r) => (
              <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
        <p className="text-xs text-gray-500">
          {ROLES.find((r) => r.value === role)?.description}
        </p>
      </div>

      <div className="flex justify-end gap-2 border-t border-gray-200 pt-5 dark:border-gray-800">
        <Button type="button" variant="secondary" onClick={onCancel} disabled={submitting}>
          Cancelar
        </Button>
        <Button type="submit" variant="primary" disabled={submitting}>
          {submitting ? "Enviando..." : "Enviar convite"}
        </Button>
      </div>
    </form>
  )
}
