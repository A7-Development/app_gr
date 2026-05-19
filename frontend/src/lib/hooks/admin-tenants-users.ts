"use client"

/**
 * React Query hooks para gestao de tenants/users/convites.
 * Espelha endpoints em backend/app/modules/admin/api/{tenants,users}.py.
 *
 * /admin/tenants/*           -> system maintainer (require_system_maintainer)
 * /admin/users/*             -> Owner do tenant (tenant_role=owner)
 * /admin/users/invitations/* -> Owner do tenant
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"

import {
  type InvitationCreatePayload,
  type InvitationCreateResponse,
  type InvitationRead,
  type ModuleId,
  type TenantCreatePayload,
  type TenantRead,
  type TenantSubscriptionUpdatePayload,
  type TenantUpdatePayload,
  type UserPermissionRead,
  type UserPermissionUpdatePayload,
  type UserRead,
  type UserUpdatePayload,
  adminTenants,
  adminUsers,
} from "@/lib/api-client"

const KEYS = {
  tenants: ["admin", "tenants"] as const,
  tenant: (id: string) => ["admin", "tenant", id] as const,
  users: ["admin", "users"] as const,
  user: (id: string) => ["admin", "user", id] as const,
  invitations: ["admin", "invitations"] as const,
}

// ───────────────────────────────────────────────────────────────────────────
// Tenants (system maintainer)
// ───────────────────────────────────────────────────────────────────────────

export function useTenants() {
  return useQuery({
    queryKey: KEYS.tenants,
    queryFn: () => adminTenants.list(),
    staleTime: 30 * 1000,
  })
}

export function useTenant(id: string | null) {
  return useQuery({
    queryKey: KEYS.tenant(id ?? ""),
    queryFn: () => adminTenants.get(id!),
    enabled: !!id,
    staleTime: 30 * 1000,
  })
}

export function useCreateTenant() {
  const qc = useQueryClient()
  return useMutation<InvitationCreateResponse, Error, TenantCreatePayload>({
    mutationFn: (payload) => adminTenants.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.tenants })
    },
  })
}

export function useUpdateTenant() {
  const qc = useQueryClient()
  return useMutation<
    TenantRead,
    Error,
    { id: string; payload: TenantUpdatePayload }
  >({
    mutationFn: ({ id, payload }) => adminTenants.update(id, payload),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: KEYS.tenants })
      qc.setQueryData(KEYS.tenant(updated.id), updated)
    },
  })
}

export function useSetTenantSubscription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({
      tenantId,
      moduleId,
      payload,
    }: {
      tenantId: string
      moduleId: ModuleId
      payload: TenantSubscriptionUpdatePayload
    }) => adminTenants.setSubscription(tenantId, moduleId, payload),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: KEYS.tenants })
      qc.invalidateQueries({ queryKey: KEYS.tenant(vars.tenantId) })
    },
  })
}

// ───────────────────────────────────────────────────────────────────────────
// Users (Owner do tenant)
// ───────────────────────────────────────────────────────────────────────────

export function useUsers() {
  return useQuery({
    queryKey: KEYS.users,
    queryFn: () => adminUsers.list(),
    staleTime: 30 * 1000,
  })
}

export function useUserDetail(id: string | null) {
  return useQuery({
    queryKey: KEYS.user(id ?? ""),
    queryFn: () => adminUsers.get(id!),
    enabled: !!id,
    staleTime: 30 * 1000,
  })
}

export function useUpdateUser() {
  const qc = useQueryClient()
  return useMutation<
    UserRead,
    Error,
    { id: string; payload: UserUpdatePayload }
  >({
    mutationFn: ({ id, payload }) => adminUsers.update(id, payload),
    onSuccess: (updated) => {
      qc.invalidateQueries({ queryKey: KEYS.users })
      qc.setQueryData(KEYS.user(updated.id), updated)
    },
  })
}

export function useSetUserPermission() {
  const qc = useQueryClient()
  return useMutation<
    UserPermissionRead,
    Error,
    { userId: string; moduleId: ModuleId; payload: UserPermissionUpdatePayload }
  >({
    mutationFn: ({ userId, moduleId, payload }) =>
      adminUsers.setPermission(userId, moduleId, payload),
    onSuccess: (_, vars) => {
      qc.invalidateQueries({ queryKey: KEYS.users })
      qc.invalidateQueries({ queryKey: KEYS.user(vars.userId) })
    },
  })
}

// ───────────────────────────────────────────────────────────────────────────
// Invitations
// ───────────────────────────────────────────────────────────────────────────

export function useInvitations() {
  return useQuery<InvitationRead[]>({
    queryKey: KEYS.invitations,
    queryFn: () => adminUsers.invitations.list(),
    staleTime: 30 * 1000,
  })
}

export function useCreateInvitation() {
  const qc = useQueryClient()
  return useMutation<InvitationCreateResponse, Error, InvitationCreatePayload>({
    mutationFn: (payload) => adminUsers.invitations.create(payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: KEYS.invitations })
    },
  })
}

export function useCancelInvitation() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) => adminUsers.invitations.cancel(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEYS.invitations }),
  })
}
