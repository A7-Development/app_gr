"use client"

//
// McpServerForm — formulario de servidor MCP (admin IA, Fase 3 copiloto-mcp).
//
// Servidor MCP = primitivo da camada agentica (CLAUDE.md §19), catalogo
// versionado DB-first. Editar SEMPRE cria nova versao (`v(N+1)`); base
// imutavel; ativar e passo separado.
//
// Padrao espelhado de PersonaForm.tsx — variantes Create + Edit.
//

import * as React from "react"
import { Controller, useForm } from "react-hook-form"
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
import { Textarea } from "@/components/tremor/Textarea"
import type { AIMcpServerDetail } from "@/lib/api-client"
import { MODULE_OPTIONS } from "@/lib/schemas/ai-agent-definition-schema"
import {
  mcpServerCreateSchema,
  mcpServerUpdateSchema,
  type McpServerCreateValues,
  type McpServerUpdateValues,
} from "@/lib/schemas/ai-mcp-server-schema"
import { cx } from "@/lib/utils"

// ───────────────────────────────────────────────────────────────────────────
// Helpers visuais
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
    <div className="flex items-center justify-end gap-2 pt-4">
      <Button
        type="button"
        variant="secondary"
        onClick={onCancel}
        disabled={submitting}
      >
        Cancelar
      </Button>
      <Button type="submit" disabled={submitting || !isDirty}>
        {submitting && (
          <RiLoader4Line className="mr-1.5 size-4 animate-spin" aria-hidden />
        )}
        {submitLabel}
      </Button>
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Campos compartilhados (Create + Edit)
// ───────────────────────────────────────────────────────────────────────────

// Sentinela pro Select de modulo — Radix Select nao aceita value="".
const CROSS_MODULE = "__cross__"

type SharedFieldsProps = {
  // RHF generics divergem entre Create/Update — mesmo shape de campos.
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  register: any
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  control: any
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  errors: any
  idPrefix: string
}

function SharedFields({ register, control, errors, idPrefix }: SharedFieldsProps) {
  return (
    <>
      <section>
        <Label htmlFor={`${idPrefix}-url`}>
          URL
          <RequiredMarker />
        </Label>
        <Input
          id={`${idPrefix}-url`}
          {...register("url")}
          placeholder="https://app.bigdatacorp.com.br/bigia/mcp"
          autoComplete="off"
        />
        <FieldHint>
          Endpoint do servidor MCP (Streamable HTTP). O backend e o cliente —
          nada e exposto publicamente.
        </FieldHint>
        <FieldError message={errors.url?.message} />
      </section>

      <div className="grid grid-cols-2 gap-3">
        <section>
          <Label htmlFor={`${idPrefix}-transport`}>Transporte</Label>
          <Controller
            name="transport"
            control={control}
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id={`${idPrefix}-transport`}>
                  <SelectValue placeholder="Transporte" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="http">http (Streamable HTTP)</SelectItem>
                  <SelectItem value="stdio">stdio</SelectItem>
                </SelectContent>
              </Select>
            )}
          />
        </section>

        <section>
          <Label htmlFor={`${idPrefix}-module`}>Modulo</Label>
          <Controller
            name="module"
            control={control}
            render={({ field }) => (
              <Select
                value={field.value ? field.value : CROSS_MODULE}
                onValueChange={(v) =>
                  field.onChange(v === CROSS_MODULE ? "" : v)
                }
              >
                <SelectTrigger id={`${idPrefix}-module`}>
                  <SelectValue placeholder="Cross-modulo" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value={CROSS_MODULE}>
                    — Cross-modulo —
                  </SelectItem>
                  {MODULE_OPTIONS.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          <FieldHint>
            Tag de escopo (RBAC). Vazio = disponivel a agentes de qualquer
            modulo.
          </FieldHint>
        </section>
      </div>

      <section>
        <Label htmlFor={`${idPrefix}-credential`}>Credencial (UUID)</Label>
        <Input
          id={`${idPrefix}-credential`}
          {...register("credential_id")}
          placeholder="00000000-0000-0000-0000-000000000000"
          autoComplete="off"
          className="font-mono text-[13px]"
        />
        <FieldHint>
          Credencial do store de provedores de dados
          (provedor_dados_credencial, cifrada). Opcional — vazio = servidor sem
          auth.
        </FieldHint>
        <FieldError message={errors.credential_id?.message} />
      </section>

      <section>
        <Label htmlFor={`${idPrefix}-headers`}>
          Mapeamento de headers de auth (JSON)
        </Label>
        <Controller
          name="auth_header_map_text"
          control={control}
          render={({ field }) => (
            <Textarea
              id={`${idPrefix}-headers`}
              {...field}
              rows={3}
              placeholder={'{"access_token": "AccessToken", "token_id": "TokenId"}'}
              className="font-mono text-[13px]"
            />
          )}
        />
        <FieldHint>
          Objeto JSON: campo da credencial → nome do header enviado ao vendor.
          Opcional.
        </FieldHint>
        <FieldError message={errors.auth_header_map_text?.message} />
      </section>

      <section>
        <Label htmlFor={`${idPrefix}-allowed-tools`}>
          Allowlist de tools (uma por linha)
        </Label>
        <Controller
          name="allowed_tools_text"
          control={control}
          render={({ field }) => (
            <Textarea
              id={`${idPrefix}-allowed-tools`}
              {...field}
              rows={5}
              placeholder={"consultar_cadastro_pj\nconsultar_qsa_pj"}
              className="font-mono text-[13px]"
            />
          )}
        />
        <FieldHint>
          Somente estas tools do servidor chegam ao agente. Vazio = todas as
          tools expostas pelo servidor.
        </FieldHint>
      </section>

      <Divider />

      <div className="grid grid-cols-2 gap-3">
        <section>
          <Label htmlFor={`${idPrefix}-mode`}>Modo</Label>
          <Controller
            name="mode"
            control={control}
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id={`${idPrefix}-mode`}>
                  <SelectValue placeholder="Modo" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="ephemeral">
                    ephemeral (so LLM, sem silver)
                  </SelectItem>
                  <SelectItem value="materialized">
                    materialized (mapper → silver)
                  </SelectItem>
                </SelectContent>
              </Select>
            )}
          />
          <FieldHint>
            Contrato de proveniencia. Nesta rodada apenas ephemeral e usado.
          </FieldHint>
        </section>

        <section>
          <Label htmlFor={`${idPrefix}-cost`}>Custo (hint)</Label>
          <Controller
            name="cost_hint"
            control={control}
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id={`${idPrefix}-cost`}>
                  <SelectValue placeholder="Custo" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="cheap">cheap</SelectItem>
                  <SelectItem value="medium">medium</SelectItem>
                  <SelectItem value="expensive">expensive</SelectItem>
                </SelectContent>
              </Select>
            )}
          />
        </section>

        <section>
          <Label htmlFor={`${idPrefix}-max-calls`}>Max chamadas por turno</Label>
          <Input
            id={`${idPrefix}-max-calls`}
            type="number"
            step="1"
            min="1"
            max="100"
            {...register("max_calls_per_turn", {
              setValueAs: (v: string) => (v === "" ? undefined : Number(v)),
            })}
            placeholder="5"
          />
          <FieldError message={errors.max_calls_per_turn?.message} />
        </section>

        <section>
          <Label htmlFor={`${idPrefix}-max-chars`}>
            Max chars por tool_result
          </Label>
          <Input
            id={`${idPrefix}-max-chars`}
            type="number"
            step="1000"
            min="100"
            max="1000000"
            {...register("tool_result_max_chars", {
              setValueAs: (v: string) => (v === "" ? undefined : Number(v)),
            })}
            placeholder="20000"
          />
          <FieldError message={errors.tool_result_max_chars?.message} />
        </section>
      </div>

      <section>
        <Label htmlFor={`${idPrefix}-description`}>
          Descricao (nota interna)
        </Label>
        <Controller
          name="description"
          control={control}
          render={({ field }) => (
            <Textarea
              id={`${idPrefix}-description`}
              {...field}
              value={field.value ?? ""}
              rows={2}
              placeholder="O que este servidor oferece, quando usar..."
            />
          )}
        />
      </section>
    </>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Create form
// ───────────────────────────────────────────────────────────────────────────

type CreateFormProps = {
  onSubmit: (values: McpServerCreateValues) => Promise<void>
  onCancel: () => void
  submitting: boolean
}

export function McpServerCreateForm({
  onSubmit,
  onCancel,
  submitting,
}: CreateFormProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isDirty },
  } = useForm<McpServerCreateValues>({
    resolver: zodResolver(mcpServerCreateSchema),
    defaultValues: {
      name: "",
      url: "",
      transport: "http",
      module: "",
      credential_id: "",
      auth_header_map_text: "",
      allowed_tools_text: "",
      mode: "ephemeral",
      cost_hint: "medium",
      max_calls_per_turn: 5,
      tool_result_max_chars: 20000,
      description: "",
    },
  })

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-5">
      <section>
        <Label htmlFor="mcp-name">
          Nome canonico
          <RequiredMarker />
        </Label>
        <Input
          id="mcp-name"
          {...register("name")}
          placeholder="ex: bigdatacorp"
          autoComplete="off"
          pattern="^[a-z0-9_-]+$"
          title="Use minusculas, digitos, underscore e hifen. Sem espacos."
          className="font-mono text-[13px]"
        />
        <FieldHint>
          Minusculas, digitos, underscore e hifen. Identifica a familia de
          versoes do servidor.
        </FieldHint>
        <FieldError message={errors.name?.message} />
      </section>

      <SharedFields
        register={register}
        control={control}
        errors={errors}
        idPrefix="mcp"
      />

      <FormFooter
        submitting={submitting}
        onCancel={onCancel}
        submitLabel="Cadastrar servidor (v1, ativado)"
        isDirty={isDirty}
      />
    </form>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Edit form (cria nova versao)
// ───────────────────────────────────────────────────────────────────────────

type EditFormProps = {
  server: AIMcpServerDetail
  onSubmit: (values: McpServerUpdateValues) => Promise<void>
  onCancel: () => void
  submitting: boolean
}

export function McpServerEditForm({
  server,
  onSubmit,
  onCancel,
  submitting,
}: EditFormProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isDirty },
  } = useForm<McpServerUpdateValues>({
    resolver: zodResolver(mcpServerUpdateSchema),
    defaultValues: {
      url: server.url,
      transport: server.transport,
      module: server.module ?? "",
      credential_id: server.credential_id ?? "",
      auth_header_map_text: server.auth_header_map
        ? JSON.stringify(server.auth_header_map, null, 2)
        : "",
      allowed_tools_text: (server.allowed_tools ?? []).join("\n"),
      mode: server.mode,
      cost_hint: server.cost_hint,
      max_calls_per_turn: server.max_calls_per_turn,
      tool_result_max_chars: server.tool_result_max_chars,
      description: server.description ?? "",
    },
  })

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-5">
      <div
        className={cx(
          "rounded-md border border-amber-200 bg-amber-50 p-3 text-[13px] text-amber-900",
          "dark:border-amber-900/50 dark:bg-amber-500/10 dark:text-amber-200",
        )}
      >
        <p className="font-medium">Editar cria nova versao</p>
        <p className="mt-0.5">
          A versao base ({server.name}@v{server.version}) e imutavel. Salvar
          gera v{server.version + 1}. A versao ativa nao muda automaticamente
          — promova depois via &ldquo;Ativar esta versao&rdquo;.
        </p>
      </div>

      <section>
        <Label>Nome canonico</Label>
        <Input
          value={server.name}
          disabled
          className="font-mono text-[13px]"
        />
        <FieldHint>Nao editavel — identifica a familia de versoes.</FieldHint>
      </section>

      <SharedFields
        register={register}
        control={control}
        errors={errors}
        idPrefix="mcp-edit"
      />

      <FormFooter
        submitting={submitting}
        onCancel={onCancel}
        submitLabel={`Criar versao v${server.version + 1}`}
        isDirty={isDirty}
      />
    </form>
  )
}
