"use client"

//
// Tab "Credenciais" da pagina de detalhe de uma fonte.
//
// - Renderiza form baseado em descriptor por source_type (campos conhecidos).
// - Secrets sao mascarados pelo backend como "***SET***"; usamos `SecretInput`
//   para nunca expor o valor persistido e so enviar campo quando operador substitui.
// - Switch enabled: chama endpoint /enable separado (mutacao simples).
//

import * as React from "react"
import { Controller, useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { toast } from "sonner"
import { RiLoader4Line, RiInformationLine } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import { Divider } from "@/components/tremor/Divider"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import { Switch } from "@/components/tremor/Switch"
import { SecretInput } from "@/design-system/components/SecretInput"
import {
  useSetSourceEnabled,
  useUpdateSourceConfig,
} from "@/lib/hooks/integracoes"
import type {
  ConfigUpdatePayload,
  SourceDetail,
  SourceTypeId,
} from "@/lib/api-client"

//
// Descritor de campo. `secret` => usa SecretInput; `multiline` => Textarea (PEM).
//
// `secret-json` = textarea de JSON cifrado em repouso; parseado client-side
// no submit. Util quando o shape do valor varia por contrato (ex.: payload
// de credenciais da QiTech e repassado tal e qual pro endpoint de token).
type FieldType = "text" | "secret" | "secret-multiline" | "secret-json"

type FieldDescriptor = {
  key: string
  label: string
  type: FieldType
  placeholder?: string
  helper?: string
  required?: boolean
}

// Campos por source_type. Quando source_type nao tem descriptor, mostramos aviso.
// Mantemos aqui (co-localizado com a tab) para facilitar extensao por fase.
const FIELDS_BY_SOURCE: Partial<Record<SourceTypeId, FieldDescriptor[]>> = {
  "erp:bitfin": [
    {
      key: "server",
      label: "Servidor",
      type: "text",
      placeholder: "10.0.0.1\\SQLEXPRESS ou host:1433",
      required: true,
    },
    {
      key: "database_bitfin",
      label: "Database Bitfin",
      type: "text",
      placeholder: "UNLTD_TENANT",
      required: true,
    },
    {
      key: "database_analytics",
      label: "Database Analytics",
      type: "text",
      placeholder: "ANALYTICS_TENANT",
      required: true,
    },
    {
      key: "user",
      label: "Usuario",
      type: "text",
      placeholder: "sa ou usuario dedicado",
      required: true,
    },
    {
      key: "password",
      label: "Senha",
      type: "secret",
      required: true,
    },
    {
      key: "driver",
      label: "Driver ODBC",
      type: "text",
      placeholder: "ODBC Driver 17 for SQL Server",
      helper: "Opcional. Default: ODBC Driver 17 for SQL Server.",
    },
  ],
  "admin:qitech": [
    {
      key: "base_url",
      label: "Base URL",
      type: "text",
      placeholder: "https://api-portal.singulare.com.br",
      helper:
        "Default: https://api-portal.singulare.com.br (QiTech herdou o portal da Singulare).",
    },
    {
      key: "client_id",
      label: "Client ID",
      type: "secret",
      required: true,
      helper:
        "Identificador emitido pela QiTech ao tenant. Vai no Authorization: Basic base64(client_id:client_secret) da request de token.",
    },
    {
      key: "client_secret",
      label: "Client Secret",
      type: "secret",
      required: true,
      helper:
        "Secret correspondente ao Client ID. Cifrado em repouso via envelope encryption.",
    },
    {
      key: "token_ttl_seconds",
      label: "TTL do token (segundos)",
      type: "text",
      placeholder: "3600",
      helper: "Opcional. Default: 3600 (1h).",
    },
  ],
}

// Valor que o backend usa para indicar "secret persistido sem vazamento".
const MASK = "***SET***"

export function CredenciaisTab({
  detail,
  sourceType,
}: {
  detail: SourceDetail
  sourceType: SourceTypeId
}) {
  const fields = FIELDS_BY_SOURCE[sourceType]

  const updateMut = useUpdateSourceConfig(sourceType)
  const enableMut = useSetSourceEnabled(sourceType)

  if (!fields) {
    return (
      <Card>
        <div className="flex items-start gap-3">
          <RiInformationLine
            className="mt-0.5 size-5 text-gray-500 dark:text-gray-400"
            aria-hidden
          />
          <div className="flex flex-col gap-1">
            <h3 className="text-sm font-semibold text-gray-900 dark:text-gray-50">
              Fonte ainda nao possui formulario
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              O adapter de <span className="font-mono">{sourceType}</span> nao
              expoe um schema de campos suportado pela UI. Edite o registro
              diretamente em <span className="font-mono">tenant_source_config</span>
              {" "}ou aguarde a fase correspondente do roadmap.
            </p>
          </div>
        </div>
      </Card>
    )
  }

  return (
    <div className="flex flex-col gap-6">
      <EnabledToggle
        detail={detail}
        disabled={!detail.configured || enableMut.isPending}
        onToggle={(next) =>
          enableMut.mutate(
            { enabled: next, environment: detail.environment },
            {
              onSuccess: () =>
                toast.success(
                  next ? "Fonte habilitada." : "Fonte desabilitada.",
                ),
              onError: (err: unknown) =>
                toast.error(
                  err instanceof Error ? err.message : "Falha ao alterar estado.",
                ),
            },
          )
        }
      />

      <CredenciaisForm
        detail={detail}
        fields={fields}
        submitting={updateMut.isPending}
        onSubmit={(payload) =>
          updateMut.mutate(payload, {
            onSuccess: () => toast.success("Credenciais salvas."),
            onError: (err: unknown) =>
              toast.error(
                err instanceof Error ? err.message : "Falha ao salvar credenciais.",
              ),
          })
        }
      />
    </div>
  )
}

//
// Card de enable/disable.
//
function EnabledToggle({
  detail,
  disabled,
  onToggle,
}: {
  detail: SourceDetail
  disabled: boolean
  onToggle: (next: boolean) => void
}) {
  return (
    <Card>
      <div className="flex items-center justify-between gap-4">
        <div className="flex flex-col gap-0.5">
          <Label htmlFor="enabled-switch" className="text-sm font-medium">
            Habilitar sincronizacao automatica
          </Label>
          <span className="text-sm text-gray-500 dark:text-gray-400">
            Quando ligada, a fonte entra no scheduler e roda conforme a
            frequencia configurada.
            {!detail.configured && (
              <> Salve as credenciais antes de habilitar.</>
            )}
          </span>
        </div>
        <Switch
          id="enabled-switch"
          checked={detail.enabled}
          onCheckedChange={onToggle}
          disabled={disabled}
        />
      </div>
    </Card>
  )
}

//
// Form de credenciais. Secret persistido nao sai em claro — so enviamos campo
// quando operador de fato substituiu. Campos `text` sempre viajam (idempotente).
//
function CredenciaisForm({
  detail,
  fields,
  submitting,
  onSubmit,
}: {
  detail: SourceDetail
  fields: FieldDescriptor[]
  submitting: boolean
  onSubmit: (payload: ConfigUpdatePayload) => void
}) {
  // Schema zod dinamico: text = string; secret = string opcional (mantem mascara se vazio).
  const schema = React.useMemo(() => {
    const shape: Record<string, z.ZodTypeAny> = {}
    for (const f of fields) {
      if (f.type === "text") {
        shape[f.key] = f.required
          ? z.string().min(1, `Informe ${f.label.toLowerCase()}.`)
          : z.string().optional()
      } else {
        // secret / secret-multiline: sempre opcional no form — required real so vale se nao persistido
        shape[f.key] = z.string().optional()
      }
    }
    return z.object(shape)
  }, [fields])

  type FormValues = z.infer<typeof schema>

  // Default: valores plaintext que o backend devolveu (secrets ja mascarados).
  const defaultValues = React.useMemo(() => {
    const out: Record<string, string> = {}
    for (const f of fields) {
      const raw = detail.config[f.key]
      if (f.type === "text") {
        out[f.key] = typeof raw === "string" ? raw : ""
      } else {
        out[f.key] = "" // secret nunca pre-preenchido
      }
    }
    return out as FormValues
  }, [detail.config, fields])

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isDirty },
  } = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues,
  })

  // Reset quando detail muda (ex.: apos salvar, backend devolve config atualizado).
  React.useEffect(() => {
    reset(defaultValues)
  }, [defaultValues, reset])

  function isSecretPersisted(key: string): boolean {
    return detail.config[key] === MASK
  }

  function submit(values: FormValues) {
    // Valida secrets obrigatorios nao persistidos (zod nao sabe do estado do servidor).
    const missingSecrets: string[] = []
    for (const f of fields) {
      if (f.type === "text" || !f.required) continue
      const persisted = isSecretPersisted(f.key)
      const typed = (values as Record<string, string>)[f.key]
      if (!persisted && !typed) missingSecrets.push(f.label)
    }
    if (missingSecrets.length) {
      toast.error(
        `Preencha: ${missingSecrets.join(", ")}.`,
      )
      return
    }

    // Monta payload: text sempre, secret so se preenchido nesta sessao.
    // `secret-json` parseia — JSON invalido = erro visivel sem bater no backend.
    const nextConfig: Record<string, unknown> = {}
    for (const f of fields) {
      const v = (values as Record<string, string>)[f.key]
      if (f.type === "text") {
        if (v !== undefined && v !== "") nextConfig[f.key] = v
      } else if (f.type === "secret-json") {
        if (!v) continue
        try {
          const parsed = JSON.parse(v)
          if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
            toast.error(`${f.label}: JSON deve ser um objeto.`)
            return
          }
          nextConfig[f.key] = parsed
        } catch {
          toast.error(`${f.label}: JSON invalido.`)
          return
        }
      } else if (v) {
        nextConfig[f.key] = v
      }
    }
    onSubmit({
      config: nextConfig,
      environment: detail.environment,
    })
  }

  return (
    <form onSubmit={handleSubmit(submit)} className="flex flex-col gap-6">
      <Card className="flex flex-col gap-6">
        <div className="flex flex-col gap-1">
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
            Credenciais · {detail.environment === "production" ? "Producao" : "Sandbox"}
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Campos sensiveis ficam cifrados em repouso (envelope encryption).
            Valores persistidos aparecem como <span className="font-mono">***SET***</span>
            {" "}e nunca sao retornados em claro — clique em{" "}
            <span className="font-medium">Substituir</span> para rotacionar.
          </p>
        </div>

        <Divider />

        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {fields.map((f) => {
            const isSecret = f.type !== "text"
            const isMultiline =
              f.type === "secret-multiline" || f.type === "secret-json"
            const fieldError = errors[f.key as keyof typeof errors]?.message as
              | string
              | undefined
            const persisted = isSecret && isSecretPersisted(f.key)

            return (
              <div
                key={f.key}
                className={
                  isMultiline
                    ? "flex flex-col gap-1.5 md:col-span-2"
                    : "flex flex-col gap-1.5"
                }
              >
                <Label htmlFor={f.key}>
                  {f.label}
                  {f.required && (
                    <span
                      className="ml-1 text-red-600 dark:text-red-500"
                      aria-hidden
                    >
                      *
                    </span>
                  )}
                </Label>

                {isSecret ? (
                  <Controller
                    control={control}
                    name={f.key as never}
                    render={({ field }) => (
                      <SecretInput
                        id={f.key}
                        value={(field.value as string | undefined) ?? ""}
                        onChange={field.onChange}
                        persisted={persisted}
                        multiline={isMultiline}
                        rows={isMultiline ? 8 : undefined}
                        placeholder={f.placeholder}
                        hasError={Boolean(fieldError)}
                      />
                    )}
                  />
                ) : (
                  <Input
                    id={f.key}
                    placeholder={f.placeholder}
                    hasError={Boolean(fieldError)}
                    {...register(f.key as never)}
                  />
                )}

                {f.helper && !fieldError && (
                  <span className="text-xs text-gray-500 dark:text-gray-400">
                    {f.helper}
                  </span>
                )}
                {fieldError && (
                  <span className="text-xs text-red-600 dark:text-red-500">
                    {fieldError}
                  </span>
                )}
              </div>
            )
          })}
        </div>

        <Divider />

        <div className="flex items-center justify-end gap-2">
          <Button
            type="button"
            variant="secondary"
            onClick={() => reset(defaultValues)}
            disabled={submitting || !isDirty}
          >
            Descartar
          </Button>
          <Button type="submit" variant="primary" disabled={submitting}>
            {submitting && (
              <RiLoader4Line
                className="mr-1.5 size-4 animate-spin"
                aria-hidden
              />
            )}
            Salvar credenciais
          </Button>
        </div>
      </Card>
    </form>
  )
}
