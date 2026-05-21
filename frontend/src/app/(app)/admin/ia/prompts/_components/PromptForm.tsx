"use client"

//
// PromptForm — formulario de prompt LLM (admin IA, DB-backed).
//
// Padrao espelhado de:
//   - src/app/(app)/integracoes/fontes/[source_type]/_components/CredenciaisTab.tsx
//   - src/app/(app)/admin/ia/providers/_components/ProviderForm.tsx
//
// Diferencas pra ProviderForm:
//   - System text e o cerne — Textarea grande monospace.
//   - Versao base e imutavel: editar SEMPRE cria nova versao (`v(N+1)`).
//

import * as React from "react"
import { useForm, Controller } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { RiInformationLine, RiLoader4Line } from "@remixicon/react"

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
import type { AIPromptDetail } from "@/lib/api-client"
import {
  CACHE_STRATEGIES,
  promptCreateSchema,
  promptUpdateSchema,
  type PromptCreateValues,
  type PromptUpdateValues,
} from "@/lib/schemas/ai-prompt-schema"
import { cx } from "@/lib/utils"

// ───────────────────────────────────────────────────────────────────────────
// Helpers visuais (puros — sem react-hook-form)
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
          <RiLoader4Line className="mr-1.5 size-4 animate-spin" aria-hidden />
        )}
        {submitLabel}
      </Button>
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// CREATE
// ───────────────────────────────────────────────────────────────────────────

export type PromptCreateFormProps = {
  submitting: boolean
  onSubmit: (values: PromptCreateValues) => void
  onCancel: () => void
}

const CREATE_DEFAULTS: PromptCreateValues = {
  name: "",
  system_text: "",
  user_context_template: "",
  assistant_prime: "",
  model: "claude-opus-4-7",
  fallback_model: "",
  temperature: 0.3,
  max_tokens: 2048,
  cache_strategy: "after_system",
  description: "",
}

export function PromptCreateForm({
  submitting,
  onSubmit,
  onCancel,
}: PromptCreateFormProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isDirty },
  } = useForm<PromptCreateValues>({
    resolver: zodResolver(promptCreateSchema),
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
          Novo prompt
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Cria a primeira versao (v1) de um novo prompt. Para adicionar nova
          versao a um prompt existente, abra-o e clique em <em>Editar</em>.
        </p>
      </div>

      <Divider />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="flex flex-col gap-1.5 md:col-span-2">
          <Label htmlFor="name">
            Nome
            <RequiredMarker />
          </Label>
          <Input
            id="name"
            placeholder="insight.risco_3bullets"
            hasError={Boolean(errors.name)}
            {...register("name")}
          />
          {errors.name ? (
            <FieldError message={errors.name.message} />
          ) : (
            <FieldHint>
              Formato <span className="font-mono">categoria.nome</span>. Ex.:{" "}
              <span className="font-mono">chat.fidc_geral</span>,{" "}
              <span className="font-mono">insight.carteira_3bullets</span>.
            </FieldHint>
          )}
        </div>

        <div className="flex flex-col gap-1.5 md:col-span-2">
          <Label htmlFor="description">Descricao (opcional)</Label>
          <Textarea
            id="description"
            rows={2}
            placeholder="O que esse prompt faz, quando e usado, decisoes de design..."
            hasError={Boolean(errors.description)}
            {...register("description")}
          />
          <FieldError message={errors.description?.message} />
        </div>
      </div>

      <Divider />

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="system_text">
          System text
          <RequiredMarker />
        </Label>
        <Textarea
          id="system_text"
          rows={14}
          placeholder="Voce e a Strata IA, assistente do sistema..."
          hasError={Boolean(errors.system_text)}
          className="font-mono text-[12px] leading-relaxed"
          {...register("system_text")}
        />
        {errors.system_text ? (
          <FieldError message={errors.system_text.message} />
        ) : (
          <FieldHint>
            Bloco principal do prompt. Cacheado quando{" "}
            <span className="font-mono">cache_strategy=after_system</span>.
          </FieldHint>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="user_context_template">
          User context template (opcional)
        </Label>
        <Textarea
          id="user_context_template"
          rows={6}
          placeholder={
            "[Contexto da pagina]\nPagina: {page}\nPeriodo: {period}\nFiltros: {filters}"
          }
          hasError={Boolean(errors.user_context_template)}
          className="font-mono text-[12px] leading-relaxed"
          {...register("user_context_template")}
        />
        {errors.user_context_template ? (
          <FieldError message={errors.user_context_template.message} />
        ) : (
          <FieldHint>
            Vai como user message logo apos o system block. Aceita variaveis{" "}
            <span className="font-mono">{`{nome}`}</span> via str.format. Ex.:{" "}
            <span className="font-mono">{"{page}"}</span>,{" "}
            <span className="font-mono">{"{kpis_block}"}</span>.
          </FieldHint>
        )}
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="assistant_prime">Assistant prime (opcional)</Label>
        <Textarea
          id="assistant_prime"
          rows={2}
          placeholder="Entendi o contexto. Em que posso ajudar?"
          hasError={Boolean(errors.assistant_prime)}
          className="font-mono text-[12px] leading-relaxed"
          {...register("assistant_prime")}
        />
        {errors.assistant_prime ? (
          <FieldError message={errors.assistant_prime.message} />
        ) : (
          <FieldHint>
            Resposta canned do assistente apos o context, pra primar o tom.
          </FieldHint>
        )}
      </div>

      <Divider />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="model">
            Modelo default
            <RequiredMarker />
          </Label>
          <Input
            id="model"
            placeholder="claude-opus-4-7"
            hasError={Boolean(errors.model)}
            {...register("model")}
          />
          {errors.model ? (
            <FieldError message={errors.model.message} />
          ) : (
            <FieldHint>
              Ex.: claude-opus-4-7, claude-haiku-4-5-20251001, gpt-4o, gpt-4o-mini
            </FieldHint>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="fallback_model">Fallback (opcional)</Label>
          <Input
            id="fallback_model"
            placeholder="gpt-4o-mini"
            hasError={Boolean(errors.fallback_model)}
            {...register("fallback_model")}
          />
          <FieldHint>Usado se o default rate-limita ou falha.</FieldHint>
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="temperature">
            Temperature
            <RequiredMarker />
          </Label>
          <Input
            id="temperature"
            type="number"
            step={0.05}
            min={0}
            max={2}
            hasError={Boolean(errors.temperature)}
            {...register("temperature", { valueAsNumber: true })}
          />
          {errors.temperature ? (
            <FieldError message={errors.temperature.message} />
          ) : (
            <FieldHint>
              0 = deterministico. 0.3 = factual. 0.7+ = criativo.
            </FieldHint>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="max_tokens">
            Max tokens
            <RequiredMarker />
          </Label>
          <Input
            id="max_tokens"
            type="number"
            step={1}
            min={1}
            max={128_000}
            hasError={Boolean(errors.max_tokens)}
            {...register("max_tokens", { valueAsNumber: true })}
          />
          {errors.max_tokens ? (
            <FieldError message={errors.max_tokens.message} />
          ) : (
            <FieldHint>Limite duro de output.</FieldHint>
          )}
        </div>

        <div className="flex flex-col gap-1.5 md:col-span-2">
          <Label htmlFor="cache_strategy">Estrategia de cache</Label>
          <Controller
            control={control}
            name="cache_strategy"
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id="cache_strategy">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CACHE_STRATEGIES.map((c) => (
                    <SelectItem key={c} value={c}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          <FieldHint>
            <strong>after_system</strong>: cache breakpoint Anthropic apos system
            block (~90% custo off em prompts longos). <strong>none</strong>: sem
            cache.
          </FieldHint>
        </div>
      </div>

      <Divider />

      <FormFooter
        submitting={submitting}
        onCancel={onCancel}
        submitLabel="Criar prompt (v1)"
        isDirty={isDirty}
      />
    </form>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// EDIT — sempre cria nova versao
// ───────────────────────────────────────────────────────────────────────────

export type PromptEditFormProps = {
  initial: AIPromptDetail
  submitting: boolean
  onSubmit: (values: PromptUpdateValues) => void
  onCancel: () => void
}

export function PromptEditForm({
  initial,
  submitting,
  onSubmit,
  onCancel,
}: PromptEditFormProps) {
  const defaults: PromptUpdateValues = React.useMemo(
    () => ({
      system_text: initial.system_text,
      user_context_template: initial.user_context_template ?? "",
      assistant_prime: initial.assistant_prime ?? "",
      model: initial.model,
      fallback_model: initial.fallback_model ?? "",
      temperature: initial.temperature,
      max_tokens: initial.max_tokens,
      cache_strategy: initial.cache_strategy,
      description: initial.description ?? "",
    }),
    [initial],
  )

  const {
    register,
    handleSubmit,
    control,
    reset,
    formState: { errors, isDirty },
  } = useForm<PromptUpdateValues>({
    resolver: zodResolver(promptUpdateSchema),
    defaultValues: defaults,
  })

  React.useEffect(() => reset(defaults), [defaults, reset])

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="flex flex-col gap-6"
      noValidate
    >
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
          Editar · {initial.name}
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Versao base{" "}
          <span className="font-mono">{initial.version}</span> e imutavel —{" "}
          esta operacao cria nova versao copiando os campos atuais e aplicando
          os patches abaixo. A nova versao NAO e ativada automaticamente.
        </p>
      </div>

      <div
        role="note"
        className={cx(
          "flex items-start gap-2 rounded border px-3 py-2 text-xs",
          "border-blue-200 bg-blue-50 text-blue-900",
          "dark:border-blue-700/40 dark:bg-blue-500/10 dark:text-blue-200",
        )}
      >
        <RiInformationLine className="mt-0.5 size-4 shrink-0" aria-hidden />
        <div>
          Editar = nova versao (audit trail preservado). Pra reverter, abra a
          versao anterior e clique em <em>Ativar versao</em>.
        </div>
      </div>

      <Divider />

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="edit-description">Descricao</Label>
        <Textarea
          id="edit-description"
          rows={2}
          hasError={Boolean(errors.description)}
          {...register("description")}
        />
        <FieldError message={errors.description?.message} />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="edit-system_text">
          System text
          <RequiredMarker />
        </Label>
        <Textarea
          id="edit-system_text"
          rows={14}
          hasError={Boolean(errors.system_text)}
          className="font-mono text-[12px] leading-relaxed"
          {...register("system_text")}
        />
        <FieldError message={errors.system_text?.message} />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="edit-user_context_template">
          User context template
        </Label>
        <Textarea
          id="edit-user_context_template"
          rows={6}
          hasError={Boolean(errors.user_context_template)}
          className="font-mono text-[12px] leading-relaxed"
          {...register("user_context_template")}
        />
        <FieldError message={errors.user_context_template?.message} />
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="edit-assistant_prime">Assistant prime</Label>
        <Textarea
          id="edit-assistant_prime"
          rows={2}
          hasError={Boolean(errors.assistant_prime)}
          className="font-mono text-[12px] leading-relaxed"
          {...register("assistant_prime")}
        />
        <FieldError message={errors.assistant_prime?.message} />
      </div>

      <Divider />

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="edit-model">Modelo default</Label>
          <Input
            id="edit-model"
            hasError={Boolean(errors.model)}
            {...register("model")}
          />
          <FieldError message={errors.model?.message} />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="edit-fallback_model">Fallback</Label>
          <Input
            id="edit-fallback_model"
            hasError={Boolean(errors.fallback_model)}
            {...register("fallback_model")}
          />
          <FieldError message={errors.fallback_model?.message} />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="edit-temperature">Temperature</Label>
          <Input
            id="edit-temperature"
            type="number"
            step={0.05}
            min={0}
            max={2}
            hasError={Boolean(errors.temperature)}
            {...register("temperature", { valueAsNumber: true })}
          />
          <FieldError message={errors.temperature?.message} />
        </div>

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="edit-max_tokens">Max tokens</Label>
          <Input
            id="edit-max_tokens"
            type="number"
            step={1}
            min={1}
            max={128_000}
            hasError={Boolean(errors.max_tokens)}
            {...register("max_tokens", { valueAsNumber: true })}
          />
          <FieldError message={errors.max_tokens?.message} />
        </div>

        <div className="flex flex-col gap-1.5 md:col-span-2">
          <Label htmlFor="edit-cache_strategy">Estrategia de cache</Label>
          <Controller
            control={control}
            name="cache_strategy"
            render={({ field }) => (
              <Select
                value={field.value ?? initial.cache_strategy}
                onValueChange={field.onChange}
              >
                <SelectTrigger id="edit-cache_strategy">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CACHE_STRATEGIES.map((c) => (
                    <SelectItem key={c} value={c}>
                      {c}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </div>
      </div>

      <Divider />

      <FormFooter
        submitting={submitting}
        onCancel={onCancel}
        submitLabel="Criar nova versao"
        isDirty={isDirty}
      />
    </form>
  )
}
