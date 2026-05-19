"use client"

import * as React from "react"
import { toast } from "sonner"
import { format, parseISO } from "date-fns"
import { ptBR } from "date-fns/locale"

import { Button } from "@/components/tremor/Button"
import { Divider } from "@/components/tremor/Divider"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/tremor/Select"
import { Switch } from "@/components/tremor/Switch"
import type { ModuleId, TenantRead, TenantStatusId } from "@/lib/api-client"
import {
  useSetTenantSubscription,
  useUpdateTenant,
} from "@/lib/hooks/admin-tenants-users"

const STATUSES: { value: TenantStatusId; label: string }[] = [
  { value: "trial",     label: "Trial"     },
  { value: "active",    label: "Ativo"     },
  { value: "suspended", label: "Suspenso"  },
  { value: "cancelled", label: "Cancelado" },
]

const ALL_MODULES: { id: ModuleId; label: string }[] = [
  { id: "bi",             label: "BI"             },
  { id: "cadastros",      label: "Cadastros"      },
  { id: "operacoes",      label: "Operacoes"      },
  { id: "credito",        label: "Credito"        },
  { id: "controladoria",  label: "Controladoria"  },
  { id: "risco",          label: "Risco"          },
  { id: "integracoes",    label: "Integracoes"    },
  { id: "laboratorio",    label: "Laboratorio"    },
  { id: "admin",          label: "Admin"          },
]

export function TenantEditPanel({
  tenant,
  onClose,
}: {
  tenant: TenantRead
  onClose: () => void
}) {
  const updateMut = useUpdateTenant()
  const setSubMut = useSetTenantSubscription()

  const [name, setName] = React.useState(tenant.name)
  const [status, setStatus] = React.useState<TenantStatusId>(tenant.status)
  const [trialEndsAt, setTrialEndsAt] = React.useState<string>(
    tenant.trial_ends_at ? tenant.trial_ends_at.slice(0, 10) : "",
  )

  // Mantem em sync se o tenant prop mudar (apos refresh do cache).
  React.useEffect(() => {
    setName(tenant.name)
    setStatus(tenant.status)
    setTrialEndsAt(tenant.trial_ends_at ? tenant.trial_ends_at.slice(0, 10) : "")
  }, [tenant])

  const dirty =
    name !== tenant.name ||
    status !== tenant.status ||
    (tenant.trial_ends_at?.slice(0, 10) ?? "") !== trialEndsAt

  async function handleSave() {
    try {
      await updateMut.mutateAsync({
        id: tenant.id,
        payload: {
          name: name !== tenant.name ? name : undefined,
          status: status !== tenant.status ? status : undefined,
          trial_ends_at:
            (tenant.trial_ends_at?.slice(0, 10) ?? "") !== trialEndsAt
              ? trialEndsAt
                ? new Date(trialEndsAt).toISOString()
                : null
              : undefined,
        },
      })
      toast.success("Tenant atualizado.")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao atualizar.")
    }
  }

  async function toggleSubscription(moduleId: ModuleId, currentlyEnabled: boolean) {
    try {
      await setSubMut.mutateAsync({
        tenantId: tenant.id,
        moduleId,
        payload: { enabled: !currentlyEnabled },
      })
      toast.success(
        currentlyEnabled
          ? `Modulo ${moduleId} desabilitado para este tenant.`
          : `Modulo ${moduleId} habilitado para este tenant.`,
      )
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao alterar subscription.")
    }
  }

  const subsByModule = React.useMemo(() => {
    const m = new Map<ModuleId, boolean>()
    for (const s of tenant.subscriptions) m.set(s.module, s.enabled)
    return m
  }, [tenant.subscriptions])

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Identificacao (read-only de slug + flag system maintainer) */}
      <section className="flex flex-col gap-2 rounded-md bg-gray-50 px-3 py-2.5 dark:bg-gray-900">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">Slug</span>
          <span className="font-mono text-xs text-gray-900 dark:text-gray-100">{tenant.slug}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">Criado em</span>
          <span className="text-xs text-gray-900 dark:text-gray-100">
            {format(parseISO(tenant.created_at), "dd/MM/yyyy HH:mm", { locale: ptBR })}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">Usuarios</span>
          <span className="text-xs text-gray-900 dark:text-gray-100">{tenant.user_count}</span>
        </div>
        {tenant.is_system_maintainer && (
          <div className="rounded-md bg-blue-50 px-2 py-1.5 text-xs text-blue-700 dark:bg-blue-500/10 dark:text-blue-300">
            Este e o tenant mantenedor do sistema — nao pode ser suspenso/cancelado.
          </div>
        )}
      </section>

      <Divider />

      {/* Campos editaveis */}
      <section className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="t-name" className="text-[13px] font-medium">Nome</Label>
          <Input
            id="t-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={updateMut.isPending}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="t-status" className="text-[13px] font-medium">Status</Label>
          <Select
            value={status}
            onValueChange={(v) => setStatus(v as TenantStatusId)}
            disabled={updateMut.isPending || tenant.is_system_maintainer}
          >
            <SelectTrigger id="t-status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUSES.map((s) => (
                <SelectItem key={s.value} value={s.value}>{s.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        {status === "trial" && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="t-trial-ends" className="text-[13px] font-medium">
              Trial termina em
            </Label>
            <Input
              id="t-trial-ends"
              type="date"
              value={trialEndsAt}
              onChange={(e) => setTrialEndsAt(e.target.value)}
              disabled={updateMut.isPending}
            />
          </div>
        )}
      </section>

      <Divider />

      {/* Subscriptions */}
      <section className="flex flex-col gap-2">
        <div className="flex flex-col gap-0.5">
          <Label className="text-[13px] font-medium">Modulos contratados</Label>
          <p className="text-xs text-gray-500">
            Tenant precisa ter o modulo habilitado para que seus users tenham
            acesso. Mudar aqui afeta imediatamente quem ja esta logado.
          </p>
        </div>
        <div className="mt-1 grid grid-cols-1 gap-1">
          {ALL_MODULES.map((m) => {
            const enabled = subsByModule.get(m.id) ?? false
            return (
              <div
                key={m.id}
                className="flex items-center justify-between rounded-md border border-gray-200 px-3 py-2 dark:border-gray-800"
              >
                <span className="text-sm text-gray-900 dark:text-gray-100">{m.label}</span>
                <Switch
                  checked={enabled}
                  onCheckedChange={() => toggleSubscription(m.id, enabled)}
                  disabled={setSubMut.isPending}
                />
              </div>
            )
          })}
        </div>
      </section>

      <div className="sticky bottom-0 mt-2 flex justify-end gap-2 border-t border-gray-200 bg-white pt-4 dark:border-gray-800 dark:bg-[#090E1A]">
        <Button variant="secondary" onClick={onClose} disabled={updateMut.isPending}>
          Fechar
        </Button>
        <Button
          variant="primary"
          onClick={handleSave}
          disabled={!dirty || updateMut.isPending}
        >
          {updateMut.isPending ? "Salvando..." : "Salvar alteracoes"}
        </Button>
      </div>
    </div>
  )
}
