"use client"

//
// AgentForm — editor de agent definition (admin IA, F2.c.3).
//
// Compoe persona + expertises + prompt + modelo + governance via
// pickers (Select e checkboxes). CLAUDE.md §19.12.
//

import * as React from "react"
import Link from "next/link"
import { Controller, useForm, useWatch } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import {
  RiAlertLine,
  RiCheckLine,
  RiLoader4Line,
  RiToolsLine,
} from "@remixicon/react"

import { Badge } from "@/components/tremor/Badge"
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
  AIToolInfo,
} from "@/lib/api-client"
import {
  agentDefinitionCreateSchema,
  agentDefinitionUpdateSchema,
  MODULE_OPTIONS,
  type AgentDefinitionCreateValues,
  type AgentDefinitionUpdateValues,
} from "@/lib/schemas/ai-agent-definition-schema"
import { cx } from "@/lib/utils"
import { PromptInstructionsField } from "./PromptInstructionsField"

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

// Badge "usado por N agentes" — torna o relacionamento (cadastro compartilhado)
// visivel direto no cockpit. >1 ganha tom amber (editar afeta varios).
function UsageBadge({ count, href }: { count: number; href: string }) {
  if (count <= 0) return null
  return (
    <Link href={href} className="shrink-0">
      <Badge variant={count > 1 ? "warning" : "neutral"}>
        usado por {count} agente{count > 1 ? "s" : ""}
      </Badge>
    </Link>
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
                  <span className="flex items-center gap-1.5 text-[13px] font-medium text-gray-900 dark:text-gray-100">
                    {e.display_name}
                    {e.usage_count > 0 && (
                      <span className="text-[10px] font-normal text-gray-400 dark:text-gray-500">
                        · {e.usage_count} agente{e.usage_count > 1 ? "s" : ""}
                      </span>
                    )}
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
// Tool picker (escopado por modulo + cross_module)
// ───────────────────────────────────────────────────────────────────────────
//
// Semantica do valor (espelha agent_definition.allowed_tools no backend):
//   null  -> override DESLIGADO: usa as tools padrao do CATALOG (codigo).
//   []    -> override LIGADO sem nenhuma tool (agente sem ferramentas).
//   [...] -> override LIGADO com subset explicito.
//
// Gate de modulo (CLAUDE.md §11.3/§19): tools do proprio modulo do agente
// sao sempre selecionaveis; tools de OUTRO modulo so podem ser ADICIONADAS
// quando cross_module estiver ligado. Remover e sempre permitido (limpar
// entradas "mortas"). O runtime reaplica o mesmo gate — a UI so antecipa.

type ToolPickerProps = {
  available: AIToolInfo[]
  agentModule: string
  crossModule: boolean
  value: string[] | null
  onChange: (next: string[] | null) => void
}

function ToolPicker({
  available,
  agentModule,
  crossModule,
  value,
  onChange,
}: ToolPickerProps) {
  const overrideOn = value !== null
  const selectedSet = new Set(value ?? [])

  function toggle(name: string) {
    const next = new Set(selectedSet)
    if (next.has(name)) {
      next.delete(name)
    } else {
      next.add(name)
    }
    onChange(Array.from(next))
  }

  // Tools fora do modulo do agente, atualmente selecionadas, enquanto
  // cross_module esta desligado: nao serao carregadas em runtime.
  const deadCrossModule = (value ?? []).filter((n) => {
    const t = available.find((x) => x.name === n)
    return t && t.module !== agentModule && !crossModule
  })

  return (
    <div className="flex flex-col gap-2">
      <label className="flex items-start gap-2 cursor-pointer">
        <input
          type="checkbox"
          checked={overrideOn}
          onChange={(e) => onChange(e.target.checked ? (value ?? []) : null)}
          className="mt-0.5 size-4 rounded border-gray-300 dark:border-gray-700"
        />
        <div className="flex flex-col">
          <span className="text-[13px] font-medium text-gray-900 dark:text-gray-100">
            Sobrescrever tools do CATALOG
          </span>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Desligado: usa as tools definidas em codigo (CATALOG). Ligue para
            escolher o conjunto pela UI — sem deploy.
          </span>
        </div>
      </label>

      {!overrideOn ? null : available.length === 0 ? (
        <FieldHint>
          Nenhuma tool registrada. Tools nascem em codigo via{" "}
          <code>@register_tool</code> (veja /admin/ia/tools).
        </FieldHint>
      ) : (
        <ToolGroups
          available={available}
          agentModule={agentModule}
          crossModule={crossModule}
          selectedSet={selectedSet}
          onToggle={toggle}
        />
      )}

      {overrideOn && deadCrossModule.length > 0 && (
        <div
          className={cx(
            "flex items-start gap-1.5 rounded-md border p-2 text-[12px]",
            "border-amber-200 bg-amber-50 text-amber-900",
            "dark:border-amber-900/50 dark:bg-amber-500/10 dark:text-amber-200",
          )}
        >
          <RiAlertLine className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          <span>
            {deadCrossModule.length} tool(s) de outro modulo selecionada(s) NAO
            serao carregadas enquanto &quot;Permitir invocacao cross-modulo&quot;
            estiver desligado: <code>{deadCrossModule.join(", ")}</code>. Ligue
            o cross-modulo ou remova-as.
          </span>
        </div>
      )}
    </div>
  )
}

function ToolGroups({
  available,
  agentModule,
  crossModule,
  selectedSet,
  onToggle,
}: {
  available: AIToolInfo[]
  agentModule: string
  crossModule: boolean
  selectedSet: Set<string>
  onToggle: (name: string) => void
}) {
  // Agrupa por modulo; o modulo do agente vem primeiro.
  const grouped = new Map<string, AIToolInfo[]>()
  for (const t of available) {
    const list = grouped.get(t.module) ?? []
    list.push(t)
    grouped.set(t.module, list)
  }
  const moduleOrder = Array.from(grouped.keys()).sort((a, b) => {
    if (a === agentModule) return -1
    if (b === agentModule) return 1
    return a.localeCompare(b)
  })

  return (
    <div className="flex flex-col gap-3 max-h-[320px] overflow-y-auto rounded border border-gray-200 dark:border-gray-800 p-3">
      {moduleOrder.map((mod) => {
        const isOwn = mod === agentModule
        const gated = !isOwn && !crossModule
        return (
          <div key={mod}>
            <div className="mb-1.5 flex items-center gap-1.5">
              <span className="text-[10px] font-semibold uppercase tracking-wider text-gray-500 dark:text-gray-400">
                {mod}
                {isOwn && " (modulo do agente)"}
              </span>
              {gated && (
                <span className="text-[10px] text-amber-600 dark:text-amber-400">
                  requer cross-modulo
                </span>
              )}
            </div>
            <div className="flex flex-col gap-1.5">
              {(grouped.get(mod) ?? []).map((t) => {
                const checked = selectedSet.has(t.name)
                // So bloqueia ADICIONAR cross-modulo; remover e sempre ok.
                const disabled = gated && !checked
                return (
                  <label
                    key={t.name}
                    className={cx(
                      "flex items-start gap-2 rounded px-2 py-1",
                      disabled
                        ? "cursor-not-allowed opacity-50"
                        : "cursor-pointer hover:bg-gray-50 dark:hover:bg-gray-900",
                      checked && "bg-blue-50 dark:bg-blue-500/10",
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      disabled={disabled}
                      onChange={() => onToggle(t.name)}
                      className="mt-0.5 size-4 rounded border-gray-300 dark:border-gray-700"
                    />
                    <div className="flex flex-col">
                      <span className="font-mono text-[13px] font-medium text-gray-900 dark:text-gray-100">
                        {t.name}
                      </span>
                      <span className="text-[11px] text-gray-500 dark:text-gray-400">
                        {t.description}
                      </span>
                    </div>
                  </label>
                )
              })}
            </div>
          </div>
        )
      })}
    </div>
  )
}

// `ToolField` conecta o picker ao form: le `cross_module` via useWatch
// (vive na secao Governance, em ModelFields) e resolve o modulo do agente.
function ToolField({
  control,
  tools,
  agentModule,
}: {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  control: any
  tools: AIToolInfo[]
  agentModule: string
}) {
  const crossModule = useWatch({ control, name: "cross_module" }) ?? false
  return (
    <div>
      <Label className="flex items-center gap-1.5">
        <RiToolsLine className="size-3.5 text-gray-500" aria-hidden />
        Tools (ferramentas)
      </Label>
      <Controller
        name="allowed_tools"
        control={control}
        render={({ field }) => (
          <ToolPicker
            available={tools}
            agentModule={agentModule}
            crossModule={!!crossModule}
            value={(field.value ?? null) as string[] | null}
            onChange={field.onChange}
          />
        )}
      />
      <FieldHint>
        Subset que o agente pode chamar em runtime. Criar tool nova continua
        sendo codigo (<code>@register_tool</code> + deploy) — aqui voce so
        escolhe entre as ja registradas.
      </FieldHint>
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
  tools: AIToolInfo[]
}

// ───────────────────────────────────────────────────────────────────────────
// Cockpit em abas (Fatia C) — espelha o painel do Toqan
// (Identidade · Composicao · Tools · Modelo · Avancado).
// ───────────────────────────────────────────────────────────────────────────

const COCKPIT_TABS = [
  { id: "identidade", label: "Identidade" },
  { id: "composicao", label: "Composicao" },
  { id: "tools", label: "Tools" },
  { id: "modelo", label: "Modelo" },
  { id: "avancado", label: "Avancado" },
] as const

type TabId = (typeof COCKPIT_TABS)[number]["id"]

// Qual campo mora em qual aba — usado pra (a) pintar o ponto de erro na aba
// e (b) saltar pra aba do primeiro erro quando o submit falha validacao.
const FIELD_TAB: Record<string, TabId> = {
  name: "identidade",
  module: "identidade",
  persona_id: "composicao",
  expertise_ids: "composicao",
  prompt_name: "composicao",
  allowed_tools: "tools",
  model: "modelo",
  fallback_model: "modelo",
  temperature: "modelo",
  max_tokens: "modelo",
  cross_module: "avancado",
  credit_hint: "avancado",
}

function CockpitTabBar({
  active,
  onChange,
  errorTabs,
}: {
  active: TabId
  onChange: (id: TabId) => void
  errorTabs: Set<TabId>
}) {
  return (
    <div
      role="tablist"
      className="flex flex-wrap gap-1 border-b border-gray-200 dark:border-gray-800"
    >
      {COCKPIT_TABS.map((t) => {
        const isActive = t.id === active
        return (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={isActive}
            onClick={() => onChange(t.id)}
            className={cx(
              "-mb-px flex items-center gap-1.5 border-b-2 px-3 py-2 text-[13px] font-medium transition-colors",
              isActive
                ? "border-blue-500 text-blue-700 dark:text-blue-300"
                : "border-transparent text-gray-500 hover:text-gray-800 dark:text-gray-400 dark:hover:text-gray-200",
            )}
          >
            {t.label}
            {errorTabs.has(t.id) && (
              <span
                className="size-1.5 rounded-full bg-red-500"
                aria-label="contem erro"
              />
            )}
          </button>
        )
      })}
    </div>
  )
}

// Painel: fica montado o tempo todo (preserva estado do react-hook-form),
// so alterna visibilidade — NUNCA desmonta (senao perde registro de campos).
function TabPanel({
  id,
  active,
  children,
}: {
  id: TabId
  active: TabId
  children: React.ReactNode
}) {
  return (
    <div hidden={id !== active} className="flex flex-col gap-4 pt-4">
      {children}
    </div>
  )
}

// Deriva quais abas tem erro a partir do objeto `errors` do RHF.
function errorTabsFrom(errors: Record<string, unknown>): Set<TabId> {
  const set = new Set<TabId>()
  for (const key of Object.keys(errors)) {
    const tab = FIELD_TAB[key]
    if (tab) set.add(tab)
  }
  return set
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
  tools,
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
      // null = override desligado (usa default do CATALOG).
      allowed_tools: null,
      credit_hint: null,
    },
  })

  const [activeTab, setActiveTab] = React.useState<TabId>("identidade")

  // Modulo atual (campo do form) — escopa o ToolPicker.
  const watchedModule = useWatch({ control, name: "module" }) ?? "credito"

  // Filtra apenas versoes ativas dos pickers
  const personasAtivas = personas.filter((p) => p.is_active)
  const expertisesAtivas = expertises.filter((e) => e.is_active)
  const promptsAtivos = prompts.filter((p) => p.is_active)

  const jumpToFirstError = (errs: Record<string, unknown>) => {
    const first = Object.keys(errs)[0]
    const tab = first ? FIELD_TAB[first] : undefined
    if (tab) setActiveTab(tab)
  }

  return (
    <form
      onSubmit={handleSubmit(onSubmit, jumpToFirstError)}
      className="flex flex-col gap-5"
    >
      <CockpitTabBar
        active={activeTab}
        onChange={setActiveTab}
        errorTabs={errorTabsFrom(errors)}
      />

      {/* IDENTIDADE */}
      <TabPanel id="identidade" active={activeTab}>
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
      </TabPanel>

      {/* COMPOSICAO */}
      <TabPanel id="composicao" active={activeTab}>
        <CompositionFields
          control={control}
          register={register}
          errors={errors}
          personas={personasAtivas}
          expertises={expertisesAtivas}
          prompts={promptsAtivos}
        />
      </TabPanel>

      {/* TOOLS */}
      <TabPanel id="tools" active={activeTab}>
        <ToolField control={control} tools={tools ?? []} agentModule={watchedModule} />
      </TabPanel>

      {/* MODELO */}
      <TabPanel id="modelo" active={activeTab}>
        <ModelFields
          control={control}
          register={register}
          errors={errors}
          models={models}
        />
      </TabPanel>

      {/* AVANCADO */}
      <TabPanel id="avancado" active={activeTab}>
        <AdvancedFields control={control} register={register} errors={errors} />
      </TabPanel>

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
  tools,
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
      // null preservado = override desligado (usa CATALOG); array = override ligado.
      allowed_tools: agent.allowed_tools,
      credit_hint: agent.credit_hint,
    },
  })

  const [activeTab, setActiveTab] = React.useState<TabId>("composicao")

  const personasAtivas = personas.filter((p) => p.is_active)
  const expertisesAtivas = expertises.filter((e) => e.is_active)
  const promptsAtivos = prompts.filter((p) => p.is_active)

  const jumpToFirstError = (errs: Record<string, unknown>) => {
    const first = Object.keys(errs)[0]
    const tab = first ? FIELD_TAB[first] : undefined
    if (tab) setActiveTab(tab)
  }

  return (
    <form
      onSubmit={handleSubmit(onSubmit, jumpToFirstError)}
      className="flex flex-col gap-5"
    >
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

      <CockpitTabBar
        active={activeTab}
        onChange={setActiveTab}
        errorTabs={errorTabsFrom(errors)}
      />

      {/* IDENTIDADE (read-only na edicao) */}
      <TabPanel id="identidade" active={activeTab}>
        <section>
          <Label>Nome canonico</Label>
          <Input value={agent.name} disabled className="font-mono text-[13px]" />
          <FieldHint>Nao editavel — identidade da familia de versoes.</FieldHint>
        </section>
        <section>
          <Label>Modulo</Label>
          <Input value={agent.module} disabled className="font-mono text-[13px]" />
        </section>
      </TabPanel>

      {/* COMPOSICAO */}
      <TabPanel id="composicao" active={activeTab}>
        <CompositionFields
          control={control}
          register={register}
          errors={errors}
          personas={personasAtivas}
          expertises={expertisesAtivas}
          prompts={promptsAtivos}
        />
      </TabPanel>

      {/* TOOLS */}
      <TabPanel id="tools" active={activeTab}>
        <ToolField control={control} tools={tools ?? []} agentModule={agent.module} />
      </TabPanel>

      {/* MODELO */}
      <TabPanel id="modelo" active={activeTab}>
        <ModelFields
          control={control}
          register={register}
          errors={errors}
          models={models}
        />
      </TabPanel>

      {/* AVANCADO */}
      <TabPanel id="avancado" active={activeTab}>
        <AdvancedFields control={control} register={register} errors={errors} />
      </TabPanel>

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
  // Persona selecionada — pra mostrar "usada por N agentes" no cabecalho.
  const selectedPersonaId = useWatch({ control, name: "persona_id" }) as
    | string
    | null
    | undefined
  const selectedPersona = (personas as AIPersonaVersionInfo[]).find(
    (p) => p.id === selectedPersonaId,
  )

  return (
    <section className="flex flex-col gap-4">
      <div>
        <div className="flex items-center gap-2">
          <Label htmlFor="agent-persona">Persona</Label>
          {selectedPersona && (
            <UsageBadge
              count={selectedPersona.usage_count}
              href="/admin/ia/personas"
            />
          )}
        </div>
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
          <code>&lt;task&gt;</code>.
        </FieldHint>
        <FieldError message={errors.prompt_name?.message} />
      </div>

      {/* Fatia A: ver/editar o system_text do prompt sem sair do cockpit. */}
      <PromptInstructionsField control={control} prompts={prompts ?? []} />
    </section>
  )
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function ModelFields({ control, register, errors, models }: any) {
  return (
    <section className="flex flex-col gap-4">
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
    </section>
  )
}

// Aba "Avancado" — governance + hints. So expoe params REAIS e funcionais
// (cross_module e consumido pelo registry; credit_hint vira metadado de
// billing). thinking_budget/timeout/memory_scopes NAO entram aqui: o runtime
// ainda nao os consome como override de DB — seriam botoes mortos (§7.3).
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function AdvancedFields({ control, register, errors }: any) {
  return (
    <section className="flex flex-col gap-4">
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

      <Divider />

      <div className="max-w-xs">
        <Label htmlFor="agent-credit-hint">Credit hint (billing)</Label>
        <Input
          id="agent-credit-hint"
          type="number"
          step="1"
          min="0"
          {...register("credit_hint", {
            setValueAs: (v: string) => (v === "" ? null : Number(v)),
          })}
          placeholder="(opcional)"
        />
        <FieldHint>
          Estimativa de creditos por execucao — metadado pra billing/quota.
          Vazio = sem hint.
        </FieldHint>
        <FieldError message={errors.credit_hint?.message} />
      </div>
    </section>
  )
}
