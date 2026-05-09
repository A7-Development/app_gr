"use client"

//
// ProviderForm — formulario compartilhado para cadastrar/editar credenciais
// LLM (admin IA). Espelha o padrao estabelecido em
// `src/app/(app)/integracoes/catalogo/[source_type]/_components/CredenciaisTab.tsx`:
//
//   - react-hook-form + zod (CLAUDE.md §6).
//   - Primitivos Tremor: Input, Label, Select, Switch, Textarea, Button.
//   - SecretInput (DS) para API key — nunca expoe valor persistido em claro.
//   - Layout Card + Divider + footer right-aligned (Cancelar | Salvar).
//   - Toast pelo caller (mantem o componente puro de I/O).
//

import * as React from "react"
import { useForm, Controller } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
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
import { Textarea } from "@/components/tremor/Textarea"
import { SecretInput } from "@/design-system/components/SecretInput"
import type { AIProviderCredentialRead } from "@/lib/api-client"
import {
  AI_PROVIDERS,
  AI_PROVIDER_LABEL,
  providerCreateSchema,
  providerUpdateSchema,
  type ProviderCreateValues,
  type ProviderUpdateValues,
} from "@/lib/schemas/ai-provider-schema"

// ───────────────────────────────────────────────────────────────────────────
// Pieces compartilhadas
// ───────────────────────────────────────────────────────────────────────────

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

// ───────────────────────────────────────────────────────────────────────────
// CREATE
// ───────────────────────────────────────────────────────────────────────────

export type ProviderCreateFormProps = {
  submitting: boolean
  onSubmit: (values: ProviderCreateValues) => void
  onCancel: () => void
}

const CREATE_DEFAULTS: ProviderCreateValues = {
  provider: "anthropic",
  alias: "",
  api_key: "",
  org_id: "",
  zdr_enabled: false,
  notes: "",
}

export function ProviderCreateForm({
  submitting,
  onSubmit,
  onCancel,
}: ProviderCreateFormProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isDirty },
  } = useForm<ProviderCreateValues>({
    resolver: zodResolver(providerCreateSchema),
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
          Nova credencial LLM
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          A API key e cifrada em repouso (envelope encryption) e nunca e
          retornada em claro. Para rotacionar mais tarde, edite a credencial
          e clique em Substituir.
        </p>
      </div>

      <Divider />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="provider">
            Provedor
            <RequiredMarker />
          </Label>
          <Controller
            control={control}
            name="provider"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id="provider" hasError={Boolean(errors.provider)}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {AI_PROVIDERS.map((p) => (
                    <SelectItem key={p} value={p}>
                      {AI_PROVIDER_LABEL[p]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          <FieldError message={errors.provider?.message} />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="alias">
            Alias
            <RequiredMarker />
          </Label>
          <Input
            id="alias"
            placeholder="anthropic-prod"
            hasError={Boolean(errors.alias)}
            {...register("alias")}
          />
          {errors.alias ? (
            <FieldError message={errors.alias.message} />
          ) : (
            <FieldHint>
              Identificador unico (sem espaco). Use para distinguir keys (prod,
              eu, zdr).
            </FieldHint>
          )}
        </div>

        <div className="flex flex-col gap-1.5 md:col-span-2">
          <Label htmlFor="api_key">
            API key
            <RequiredMarker />
          </Label>
          <Controller
            control={control}
            name="api_key"
            render={({ field }) => (
              <SecretInput
                id="api_key"
                value={field.value}
                onChange={field.onChange}
                persisted={false}
                placeholder="sk-ant-..."
                hasError={Boolean(errors.api_key)}
              />
            )}
          />
          {errors.api_key ? (
            <FieldError message={errors.api_key.message} />
          ) : (
            <FieldHint>
              Anthropic: sk-ant-... · OpenAI: sk-... — copie do painel do
              provedor. Cifrada em repouso via Fernet KEK.
            </FieldHint>
          )}
        </div>

        <div className="flex flex-col gap-1.5 md:col-span-2">
          <Label htmlFor="org_id">Organization ID (opcional)</Label>
          <Input
            id="org_id"
            placeholder="org-abc123 (OpenAI) · deixe em branco para Anthropic"
            hasError={Boolean(errors.org_id)}
            {...register("org_id")}
          />
          <FieldHint>
            Necessario para OpenAI quando se usa endpoint ZDR. Anthropic nao
            usa este campo.
          </FieldHint>
        </div>

        <div className="flex items-center justify-between gap-4 rounded-md border border-gray-200 bg-gray-50 px-3 py-2.5 dark:border-gray-800 dark:bg-gray-900 md:col-span-2">
          <div className="flex flex-col gap-0.5">
            <Label htmlFor="zdr_enabled" className="text-sm font-medium">
              Zero Data Retention contratado
            </Label>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Marcar somente se o ZDR esta efetivamente ativo no contrato com
              o provedor. O adapter bloqueia chamadas em producao quando este
              flag esta desligado.
            </span>
          </div>
          <Controller
            control={control}
            name="zdr_enabled"
            render={({ field }) => (
              <Switch
                id="zdr_enabled"
                checked={field.value}
                onCheckedChange={field.onChange}
              />
            )}
          />
        </div>

        <div className="flex flex-col gap-1.5 md:col-span-2">
          <Label htmlFor="notes">Notas (opcional)</Label>
          <Textarea
            id="notes"
            rows={3}
            placeholder="Ex.: Key da org corporativa, contrato ZDR ate 2027-04, contato suporte..."
            hasError={Boolean(errors.notes)}
            {...register("notes")}
          />
          <FieldError message={errors.notes?.message} />
        </div>
      </div>

      <Divider />

      <FormFooter
        submitting={submitting}
        onCancel={onCancel}
        submitLabel="Cadastrar credencial"
        isDirty={isDirty}
      />
    </form>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// EDIT
// ───────────────────────────────────────────────────────────────────────────

export type ProviderEditFormProps = {
  initial: AIProviderCredentialRead
  submitting: boolean
  onSubmit: (values: ProviderUpdateValues) => void
  onCancel: () => void
}

export function ProviderEditForm({
  initial,
  submitting,
  onSubmit,
  onCancel,
}: ProviderEditFormProps) {
  const defaults: ProviderUpdateValues = React.useMemo(
    () => ({
      api_key: "",
      org_id: "",
      zdr_enabled: initial.zdr_enabled,
      active: initial.active,
      notes: initial.notes ?? "",
    }),
    [initial],
  )

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isDirty },
  } = useForm<ProviderUpdateValues>({
    resolver: zodResolver(providerUpdateSchema),
    defaultValues: defaults,
  })

  // Reset quando troca de credencial selecionada (drawer reusa).
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
          Editar credencial · {initial.alias}
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Provedor e alias sao imutaveis — para mudar, crie uma nova credencial
          e desative esta. API key persistida aparece como{" "}
          <span className="font-mono">***SET***</span> e nao sai em claro;
          clique em Substituir para rotacionar.
        </p>
      </div>

      <Divider />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="edit-provider">Provedor</Label>
          <Input
            id="edit-provider"
            value={AI_PROVIDER_LABEL[initial.provider]}
            disabled
            readOnly
          />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="edit-alias">Alias</Label>
          <Input id="edit-alias" value={initial.alias} disabled readOnly />
        </div>

        <div className="flex flex-col gap-1.5 md:col-span-2">
          <Label htmlFor="edit-api_key">API key</Label>
          <Controller
            control={control}
            name="api_key"
            render={({ field }) => (
              <SecretInput
                id="edit-api_key"
                value={field.value ?? ""}
                onChange={field.onChange}
                persisted
                placeholder="Substituir para rotacionar"
                hasError={Boolean(errors.api_key)}
              />
            )}
          />
          {errors.api_key ? (
            <FieldError message={errors.api_key.message} />
          ) : (
            <FieldHint>
              A nova key entra em vigor imediatamente apos salvar; chamadas
              em curso continuam com a key anterior ate completarem.
            </FieldHint>
          )}
        </div>

        <div className="flex flex-col gap-1.5 md:col-span-2">
          <Label htmlFor="edit-org_id">Organization ID (opcional)</Label>
          <Input
            id="edit-org_id"
            placeholder="org-abc123"
            hasError={Boolean(errors.org_id)}
            {...register("org_id")}
          />
        </div>

        <div className="flex items-center justify-between gap-4 rounded-md border border-gray-200 bg-gray-50 px-3 py-2.5 dark:border-gray-800 dark:bg-gray-900 md:col-span-2">
          <div className="flex flex-col gap-0.5">
            <Label htmlFor="edit-zdr_enabled" className="text-sm font-medium">
              Zero Data Retention contratado
            </Label>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Reflete o status atual do contrato com o provedor.
            </span>
          </div>
          <Controller
            control={control}
            name="zdr_enabled"
            render={({ field }) => (
              <Switch
                id="edit-zdr_enabled"
                checked={field.value}
                onCheckedChange={field.onChange}
              />
            )}
          />
        </div>

        <div className="flex items-center justify-between gap-4 rounded-md border border-gray-200 bg-gray-50 px-3 py-2.5 dark:border-gray-800 dark:bg-gray-900 md:col-span-2">
          <div className="flex flex-col gap-0.5">
            <Label htmlFor="edit-active" className="text-sm font-medium">
              Credencial ativa
            </Label>
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Quando desligada, o adapter ignora esta credencial. Use para
              suspender uma key sem deletar.
            </span>
          </div>
          <Controller
            control={control}
            name="active"
            render={({ field }) => (
              <Switch
                id="edit-active"
                checked={field.value}
                onCheckedChange={field.onChange}
              />
            )}
          />
        </div>

        <div className="flex flex-col gap-1.5 md:col-span-2">
          <Label htmlFor="edit-notes">Notas (opcional)</Label>
          <Textarea
            id="edit-notes"
            rows={3}
            placeholder="Contexto sobre esta credencial..."
            hasError={Boolean(errors.notes)}
            {...register("notes")}
          />
          <FieldError message={errors.notes?.message} />
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
