"use client"

//
// AgentForm — editor de agent definition (admin IA, F2.c.3).
//
// Compoe persona + expertises + prompt + modelo + governance via
// pickers (Select e checkboxes). CLAUDE.md §19.12.
//

import * as React from "react"
import { Controller, useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { RiCheckLine, RiLoader4Line } from "@remixicon/react"

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
import type {
  AIAgentDefinitionDetail,
  AIAgentModelOption,
  AIExpertiseVersionInfo,
  AIPersonaVersionInfo,
  AIPromptVersionInfo,
} from "@/lib/api-client"
import {
  agentDefinitionCreateSchema,
  agentDefinitionUpdateSchema,
  MODULE_OPTIONS,
  type AgentDefinitionCreateValues,
  type AgentDefinitionUpdateValues,
} from "@/lib/schemas/ai-agent-definition-schema"
import { cx } from "@/lib/utils"

// ───────────────────────────────────────────────────────────────────────────
// Helpers visuais (compartilhados com Persona/Expertise forms)
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
// Multi-picker de expertises (checkboxes)
// ───────────────────────────────────────────────────────────────────────────

type ExpertisePickerProps = {
  available: AIExpertiseVersionInfo[]
  selected: string[]
  onChange: (next: string[]) => void
}

function ExpertisePicker({ available, selected, onChange }: ExpertisePickerProps) {
  const selectedSet = new Set(selected)

  function toggle(id: string) {
    const next = new Set(selectedSet)
    if (next.has(id)) {
      next.delete(id)
    } else {
      next.add(id)
    }
    // Preserva a ordem: items ja selecionados mantem posicao; novos vao no fim
    const ordered: string[] = []
    for (const sid of selected) {
      if (next.has(sid)) ordered.push(sid)
    }
    next.forEach((nid) => {
      if (!ordered.includes(nid)) ordered.push(nid)
    })
    onChange(ordered)
  }

  if (available.length === 0) {
    return (
      <FieldHint>
        Nenhuma expertise cadastrada. Crie em /admin/ia/expertises antes
        de associar a um agente.
      </FieldHint>
    )
  }

  // Agrupa por dominio
  const grouped = new Map<string, AIExpertiseVersionInfo[]>()
  for (const e of available) {
    const list = grouped.get(e.domain) ?? []
    list.push(e)
    grouped.set(e.domain, list)
  }

  return (
    <div className="flex flex-col gap-3 max-h-[320px] overflow-y-auto rounded border border-gray-200 dark:border-gray-800 p-3">
      {Array.from(grouped.entries()).map(([domain, items]) => (
        <div key={domain}>
          <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
            {domain}
          </div>
          <div className="flex flex-col gap-1.5">
            {items.map((e) => (
              <label
                key={e.id}
                className={cx(
                  "flex items-start gap-2 cursor-pointer rounded px-2 py-1",
                  "hover:bg-gray-50 dark:hover:bg-gray-900",
                  selectedSet.has(e.id) && "bg-blue-50 dark:bg-blue-500/10",
                )}
              >
                <input
                  type="checkbox"
                  checked={selectedSet.has(e.id)}
                  onChange={() => toggle(e.id)}
                  className="mt-0.5 size-4 rounded border-gray-300 dark:border-gray-700"
                />
                <div className="flex flex-col">
                  <span className="text-[13px] font-medium text-gray-900 dark:text-gray-100">
                    {e.display_name}
                  </span>
                  <span className="font-mono text-[11px] text-gray-500 dark:text-gray-400">
                    {e.name}@v{e.version}
                  </span>
                </div>
              </label>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Form bodies (compartilhado entre Create/Edit)
// ───────────────────────────────────────────────────────────────────────────

type CommonFormProps = {
  personas: AIPersonaVersionInfo[]
  expertises: AIExpertiseVersionInfo[]
  prompts: AIPromptVersionInfo[]
  models: AIAgentModelOption[]
}

// ───────────────────────────────────────────────────────────────────────────
// Create form
// ───────────────────────────────────────────────────────────────────────────

type CreateFormProps = CommonFormProps & {
  onSubmit: (values: AgentDefinitionCreateValues) => Promise<void>
  onCancel: () => void
  submitting: boolean
}

export function AgentCreateForm({
  personas,
  expertises,
  prompts,
  models,
  onSubmit,
  onCancel,
  submitting,
}: CreateFormProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isDirty },
  } = useForm<AgentDefinitionCreateValues>({
    resolver: zodResolver(agentDefinitionCreateSchema),
    defaultValues: {
      name: "",
      module: "credito",
      persona_id: null,
      expertise_ids: [],
      prompt_name: "",
      model: null,
      fallback_model: null,
      temperature: null,
      max_tokens: null,
      cross_module: false,
      credit_hint: null,
    },
  })

  // Filtra apenas versoes ativas dos pickers
  const personasAtivas = personas.filter((p) => p.is_active)
  const expertisesAtivas = expertises.filter((e) => e.is_active)
  const promptsAtivos = prompts.filter((p) => p.is_active)

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-5">
      {/* IDENTIDADE */}
      <section className="flex flex-col gap-4">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
          Identidade
        </h3>

        <div>
          <Label htmlFor="agent-name">
            Nome canonico
            <RequiredMarker />
          </Label>
          <Input
            id="agent-name"
            {...register("name")}
            placeholder="ex: credito.analista_variacao_cota"
            autoComplete="off"
            pattern="^[a-z0-9]+(\.[a-z0-9_]+)*$"
            title="Use minusculas, digitos, pontos e underscores. Sem espacos."
          />
          <FieldHint>
            Formato: <code>modulo.nome_agente</code>. Identifica unicamente
            este agente.
          </FieldHint>
          <FieldError message={errors.name?.message} />
        </div>

        <div>
          <Label htmlFor="agent-module">
            Modulo
            <RequiredMarker />
          </Label>
          <Controller
            name="module"
            control={control}
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger id="agent-module">
                  <SelectValue placeholder="Modulo" />
                </SelectTrigger>
                <SelectContent>
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
            Tag de modulo (CLAUDE.md §19.0) — define scope de RBAC + tools
            disponiveis em runtime.
          </FieldHint>
          <FieldError message={errors.module?.message} />
        </div>
      </section>

      <Divider />

      {/* COMPOSICAO */}
      <CompositionFields
        control={control}
        register={register}
        errors={errors}
        personas={personasAtivas}
        expertises={expertisesAtivas}
        prompts={promptsAtivos}
      />

      <Divider />

      {/* MODELO */}
      <ModelFields
        control={control}
        register={register}
        errors={errors}
        models={models}
      />

      <FormFooter
        submitting={submitting}
        onCancel={onCancel}
        submitLabel="Criar agente (v1, ativado)"
        isDirty={isDirty}
      />
    </form>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Edit form (cria nova versao)
// ───────────────────────────────────────────────────────────────────────────

type EditFormProps = CommonFormProps & {
  agent: AIAgentDefinitionDetail
  onSubmit: (values: AgentDefinitionUpdateValues) => Promise<void>
  onCancel: () => void
  submitting: boolean
}

export function AgentEditForm({
  agent,
  personas,
  expertises,
  prompts,
  models,
  onSubmit,
  onCancel,
  submitting,
}: EditFormProps) {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isDirty },
  } = useForm<AgentDefinitionUpdateValues>({
    resolver: zodResolver(agentDefinitionUpdateSchema),
    defaultValues: {
      persona_id: agent.persona?.id ?? null,
      expertise_ids: agent.expertises.map((e) => e.id),
      prompt_name: agent.prompt_name,
      model: agent.model,
      fallback_model: agent.fallback_model,
      temperature: agent.temperature,
      max_tokens: agent.max_tokens,
      cross_module: agent.cross_module,
      credit_hint: agent.credit_hint,
    },
  })

  const personasAtivas = personas.filter((p) => p.is_active)
  const expertisesAtivas = expertises.filter((e) => e.is_active)
  const promptsAtivos = prompts.filter((p) => p.is_active)

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
          A versao base ({agent.name}@v{agent.version}) e imutavel. Salvar
          gera v{agent.version + 1}. A versao ativa nao muda
          automaticamente — promova depois.
        </p>
      </div>

      <section>
        <Label>Nome canonico</Label>
        <Input value={agent.name} disabled className="font-mono text-[13px]" />
        <FieldHint>Nao editavel.</FieldHint>
      </section>

      <section>
        <Label>Modulo</Label>
        <Input value={agent.module} disabled className="font-mono text-[13px]" />
      </section>

      <Divider />

      <CompositionFields
        control={control}
        register={register}
        errors={errors}
        personas={personasAtivas}
        expertises={expertisesAtivas}
        prompts={promptsAtivos}
      />

      <Divider />

      <ModelFields
        control={control}
        register={register}
        errors={errors}
        models={models}
      />

      <FormFooter
        submitting={submitting}
        onCancel={onCancel}
        submitLabel={`Criar versao v${agent.version + 1}`}
        isDirty={isDirty}
      />
    </form>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Subforms — Composicao + Modelo (compartilhados)
// ───────────────────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function CompositionFields({ control, errors, personas, expertises, prompts }: any) {
  return (
    <section className="flex flex-col gap-4">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
        Composicao
      </h3>

      <div>
        <Label htmlFor="agent-persona">Persona</Label>
        <Controller
          name="persona_id"
          control={control}
          render={({ field }) => (
            <Select
              value={field.value ?? "__none__"}
              onValueChange={(v) =>
                field.onChange(v === "__none__" ? null : v)
              }
            >
              <SelectTrigger id="agent-persona">
                <SelectValue placeholder="Selecione persona..." />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__none__">— Sem persona —</SelectItem>
                {personas.map((p: AIPersonaVersionInfo) => (
                  <SelectItem key={p.id} value={p.id}>
                    {p.display_name}{" "}
                    <span className="font-mono text-[11px] text-gray-500">
                      ({p.name}@v{p.version})
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        />
        <FieldHint>
          Papel que o agente assume. Aparece dentro de
          <code>&lt;persona&gt;</code> no system prompt.
        </FieldHint>
      </div>

      <div>
        <Label>Expertises (knowledge packs)</Label>
        <Controller
          name="expertise_ids"
          control={control}
          render={({ field }) => (
            <ExpertisePicker
              available={expertises}
              selected={field.value ?? []}
              onChange={field.onChange}
            />
          )}
        />
        <FieldHint>
          Ordem preservada. Vao concatenadas em
          <code>&lt;expertise name=&quot;...&quot;&gt;</code> no system prompt.
        </FieldHint>
      </div>

      <div>
        <Label htmlFor="agent-prompt-name">
          Prompt task
          <RequiredMarker />
        </Label>
        <Controller
          name="prompt_name"
          control={control}
          render={({ field }) => (
            <Select value={field.value ?? ""} onValueChange={field.onChange}>
              <SelectTrigger id="agent-prompt-name">
                <SelectValue placeholder="Selecione prompt..." />
              </SelectTrigger>
              <SelectContent>
                {prompts.map((p: AIPromptVersionInfo) => (
                  <SelectItem key={p.id} value={p.name}>
                    {p.name}{" "}
                    <span className="font-mono text-[11px] text-gray-500">
                      @{p.version}
                    </span>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        />
        <FieldHint>
          Instrucao especifica da task. Aparece dentro de
          <code>&lt;task&gt;</code>. Edite em /admin/ia/prompts.
        </FieldHint>
        <FieldError message={errors.prompt_name?.message} />
      </div>
    </section>
  )
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function ModelFields({ control, register, errors, models }: any) {
  return (
    <section className="flex flex-col gap-4">
      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
        Modelo (override)
      </h3>

      <FieldHint>
        Deixe vazio pra usar o default do prompt. Override aqui tem prioridade
        sobre `agent_config` (legado) e prompt default.
      </FieldHint>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label htmlFor="agent-model">Modelo principal</Label>
          <Controller
            name="model"
            control={control}
            render={({ field }) => (
              <Select
                value={field.value ?? "__default__"}
                onValueChange={(v) =>
                  field.onChange(v === "__default__" ? null : v)
                }
              >
                <SelectTrigger id="agent-model">
                  <SelectValue placeholder="Default do prompt" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__default__">
                    — Default do prompt —
                  </SelectItem>
                  {models.map((m: AIAgentModelOption) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </div>

        <div>
          <Label htmlFor="agent-fallback-model">Fallback</Label>
          <Controller
            name="fallback_model"
            control={control}
            render={({ field }) => (
              <Select
                value={field.value ?? "__default__"}
                onValueChange={(v) =>
                  field.onChange(v === "__default__" ? null : v)
                }
              >
                <SelectTrigger id="agent-fallback-model">
                  <SelectValue placeholder="Default" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="__default__">— Default —</SelectItem>
                  {models.map((m: AIAgentModelOption) => (
                    <SelectItem key={m.id} value={m.id}>
                      {m.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </div>

        <div>
          <Label htmlFor="agent-temperature">Temperature</Label>
          <Input
            id="agent-temperature"
            type="number"
            step="0.1"
            min="0"
            max="2"
            {...register("temperature", {
              setValueAs: (v: string) => (v === "" ? null : Number(v)),
            })}
            placeholder="0.2"
          />
          <FieldError message={errors.temperature?.message} />
        </div>

        <div>
          <Label htmlFor="agent-max-tokens">Max tokens</Label>
          <Input
            id="agent-max-tokens"
            type="number"
            step="100"
            min="1"
            max="200000"
            {...register("max_tokens", {
              setValueAs: (v: string) => (v === "" ? null : Number(v)),
            })}
            placeholder="4096"
          />
          <FieldError message={errors.max_tokens?.message} />
        </div>
      </div>

      <Divider />

      <h3 className="text-[11px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
        Governance
      </h3>

      <div className="flex items-center gap-3">
        <Controller
          name="cross_module"
          control={control}
          render={({ field }) => (
            <Switch
              id="agent-cross-module"
              checked={!!field.value}
              onCheckedChange={field.onChange}
            />
          )}
        />
        <Label htmlFor="agent-cross-module" className="cursor-pointer">
          Permitir invocacao cross-modulo
          <FieldHint>
            <RiCheckLine className="inline size-3" /> Padrao: <code>false</code>.
            So habilite com justificativa explicita — audit log marca cross
            module invocations.
          </FieldHint>
        </Label>
      </div>
    </section>
  )
}
