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
import type {
  ModuleId,
  Permission,
  TenantRoleId,
  UserRead,
} from "@/lib/api-client"
import {
  useSetUserPermission,
  useUpdateUser,
} from "@/lib/hooks/admin-tenants-users"

const ROLES: { value: TenantRoleId; label: string }[] = [
  { value: "owner",  label: "Owner"  },
  { value: "member", label: "Member" },
  { value: "viewer", label: "Viewer" },
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

const PERMS: Permission[] = ["none", "read", "write", "admin"]

export function UserEditPanel({
  user,
  onClose,
}: {
  user: UserRead
  onClose: () => void
}) {
  const updateMut = useUpdateUser()
  const setPermMut = useSetUserPermission()

  const [name, setName] = React.useState(user.name)
  const [role, setRole] = React.useState<TenantRoleId>(user.tenant_role)
  const [ativo, setAtivo] = React.useState(user.ativo)

  React.useEffect(() => {
    setName(user.name)
    setRole(user.tenant_role)
    setAtivo(user.ativo)
  }, [user])

  const dirty = name !== user.name || role !== user.tenant_role || ativo !== user.ativo

  async function handleSave() {
    try {
      await updateMut.mutateAsync({
        id: user.id,
        payload: {
          name: name !== user.name ? name : undefined,
          tenant_role: role !== user.tenant_role ? role : undefined,
          ativo: ativo !== user.ativo ? ativo : undefined,
        },
      })
      toast.success("Usuario atualizado.")
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao atualizar.")
    }
  }

  async function changePermission(moduleId: ModuleId, permission: Permission) {
    try {
      await setPermMut.mutateAsync({
        userId: user.id,
        moduleId,
        payload: { permission },
      })
      toast.success(`Permissao do modulo ${moduleId} atualizada.`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Falha ao atualizar permissao.")
    }
  }

  const permsByModule = React.useMemo(() => {
    const m = new Map<ModuleId, Permission>()
    for (const p of user.permissions) m.set(p.module, p.permission)
    return m
  }, [user.permissions])

  return (
    <div className="flex flex-col gap-6 p-6">
      <section className="flex flex-col gap-2 rounded-md bg-gray-50 px-3 py-2.5 dark:bg-gray-900">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">Email</span>
          <span className="font-mono text-xs text-gray-900 dark:text-gray-100">{user.email}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">Criado em</span>
          <span className="text-xs text-gray-900 dark:text-gray-100">
            {format(parseISO(user.created_at), "dd/MM/yyyy HH:mm", { locale: ptBR })}
          </span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-500">Ultimo login</span>
          <span className="text-xs text-gray-900 dark:text-gray-100">
            {user.last_login_at
              ? format(parseISO(user.last_login_at), "dd/MM/yyyy HH:mm", { locale: ptBR })
              : "nunca"}
          </span>
        </div>
      </section>

      <Divider />

      <section className="flex flex-col gap-4">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="u-name" className="text-[13px] font-medium">Nome</Label>
          <Input
            id="u-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={updateMut.isPending}
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="u-role" className="text-[13px] font-medium">Role</Label>
          <Select
            value={role}
            onValueChange={(v) => setRole(v as TenantRoleId)}
            disabled={updateMut.isPending}
          >
            <SelectTrigger id="u-role">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ROLES.map((r) => (
                <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <p className="text-xs text-gray-500">
            Trocar o role re-aplica os defaults de permissao dele em cada modulo
            habilitado — sobrescreve overrides manuais.
          </p>
        </div>

        <div className="flex items-center justify-between rounded-md border border-gray-200 px-3 py-2.5 dark:border-gray-800">
          <div className="flex flex-col">
            <span className="text-sm text-gray-900 dark:text-gray-100">Ativo</span>
            <span className="text-xs text-gray-500">
              Desativar bloqueia o login imediatamente.
            </span>
          </div>
          <Switch
            checked={ativo}
            onCheckedChange={(v) => setAtivo(v === true)}
            disabled={updateMut.isPending}
          />
        </div>
      </section>

      <Divider />

      <section className="flex flex-col gap-2">
        <div className="flex flex-col gap-0.5">
          <Label className="text-[13px] font-medium">Permissoes por modulo</Label>
          <p className="text-xs text-gray-500">
            Defaults vem do role. Ajustes aqui sao overrides — sobreviven a tudo
            ate o role do user mudar (a entao re-materializa).
          </p>
        </div>

        <div className="mt-1 grid grid-cols-1 gap-1">
          {ALL_MODULES.map((m) => {
            const current = permsByModule.get(m.id) ?? "none"
            return (
              <div
                key={m.id}
                className="flex items-center justify-between rounded-md border border-gray-200 px-3 py-2 dark:border-gray-800"
              >
                <span className="text-sm text-gray-900 dark:text-gray-100">{m.label}</span>
                <Select
                  value={current}
                  onValueChange={(v) => changePermission(m.id, v as Permission)}
                  disabled={setPermMut.isPending}
                >
                  <SelectTrigger className="w-32 h-8">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {PERMS.map((p) => (
                      <SelectItem key={p} value={p}>{p}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
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
