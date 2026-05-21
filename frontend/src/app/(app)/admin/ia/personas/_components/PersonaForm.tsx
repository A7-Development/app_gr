"use client"

//
// PersonaForm — formulario de persona de agente (admin IA, F2.c.1).
//
// Persona = papel reutilizavel injetado no system prompt (CLAUDE.md §19.12).
// Versionamento: editar SEMPRE cria nova versao (`v(N+1)`); base imutavel.
//
// Padrao espelhado de PromptForm.tsx — variantes Create + Edit.
//

import * as React from "react"
import { useForm, Controller } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { RiLoader4Line } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { Divider } from "@/components/tremor/Divider"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import { Textarea } from "@/components/tremor/Textarea"
import type { AIPersonaDetail } from "@/lib/api-client"
import {
  personaCreateSchema,
  personaUpdateSchema,
  type PersonaCreateValues,
  type PersonaUpdateValues,
} from "@/lib/schemas/ai-persona-schema"
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

/**
 * Converte string com chips separados por virgula em array de strings.
 * Trim + dedupe + remove vazios.
 */
function parseDomainsInput(value: string): string[] {
  const seen = new Set<string>()
  const out: string[] = []
  for (const raw of value.split(",")) {
    const trimmed = raw.trim()
    if (trimmed && !seen.has(trimmed)) {
      seen.add(trimmed)
      out.push(trimmed)
    }
  }
  return out
}

function domainsToInput(domains: string[] | null | undefined): string {
  return (domains ?? []).join(", ")
}

// ───────────────────────────────────────────────────────────────────────────
// Create form
// ───────────────────────────────────────────────────────────────────────────

type CreateFormProps = {
  onSubmit: (values: PersonaCreateValues) => Promise<void>
  onCancel: () => void
  submitting: boolean
}

export function PersonaCreateForm({
  onSubmit,
  onCancel,
  submitting,
}: CreateFormProps) {
  const [domainsInput, setDomainsInput] = React.useState("")

  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isDirty },
    setValue,
  } = useForm<PersonaCreateValues>({
    resolver: zodResolver(personaCreateSchema),
    defaultValues: {
      name: "",
      display_name: "",
      role_block: "",
      description: "",
      expertise_domains: [],
    },
  })

  // Sync chip input -> form value.
  React.useEffect(() => {
    setValue("expertise_domains", parseDomainsInput(domainsInput), {
      shouldDirty: true,
    })
  }, [domainsInput, setValue])

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-5">
      <section>
        <Label htmlFor="persona-name">
          Nome canonico
          <RequiredMarker />
        </Label>
        <Input
          id="persona-name"
          {...register("name")}
          placeholder="ex: credito.analista_financial"
          autoComplete="off"
          // HTML5 pattern: feedback visual em tempo real no browser
          // (alem do Zod schema que valida no submit). Sem espacos,
          // sem maiusculas, sem caracteres especiais.
          pattern="^[a-z0-9]+(\.[a-z0-9_]+)*$"
          title="Use minusculas, digitos, pontos e underscores. Sem espacos. Ex: credito.analista_financial"
        />
        <FieldHint>
          Formato: <code>modulo.nome_papel</code>. Minusculas, pontos e
          underscores. Identifica unicamente esta persona.
        </FieldHint>
        <FieldError message={errors.name?.message} />
      </section>

      <section>
        <Label htmlFor="persona-display">
          Nome de exibicao
          <RequiredMarker />
        </Label>
        <Input
          id="persona-display"
          {...register("display_name")}
          placeholder="ex: Analista Financeiro Senior"
        />
        <FieldHint>Como aparece na UI admin e em logs.</FieldHint>
        <FieldError message={errors.display_name?.message} />
      </section>

      <section>
        <Label htmlFor="persona-role-block">
          Texto da persona (role_block)
          <RequiredMarker />
        </Label>
        <Controller
          name="role_block"
          control={control}
          render={({ field }) => (
            <Textarea
              id="persona-role-block"
              {...field}
              rows={10}
              placeholder={
                "Voce e Analista Financeiro Senior. Domina DRE, balanco...\n\n" +
                "Markdown e suportado. Inclua autoridade, rigor, formato esperado."
              }
              className="font-mono text-[13px]"
            />
          )}
        />
        <FieldHint>
          Markdown. Vai dentro de <code>&lt;persona&gt;</code> no system
          prompt. Mantenha curto (~100-300 tokens) — conhecimento aplicado
          vai em <em>expertise</em> separada.
        </FieldHint>
        <FieldError message={errors.role_block?.message} />
      </section>

      <Divider />

      <section>
        <Label htmlFor="persona-domains">Dominios (tags)</Label>
        <Input
          id="persona-domains"
          value={domainsInput}
          onChange={(e) => setDomainsInput(e.target.value)}
          placeholder="credito, contabilidade, fidc"
        />
        <FieldHint>
          Lista separada por virgula. Usado pelo curador para filtrar/agrupar.
        </FieldHint>
      </section>

      <section>
        <Label htmlFor="persona-description">Descricao (nota interna)</Label>
        <Controller
          name="description"
          control={control}
          render={({ field }) => (
            <Textarea
              id="persona-description"
              {...field}
              value={field.value ?? ""}
              rows={2}
              placeholder="Quando usar essa persona, observacoes pro time..."
            />
          )}
        />
      </section>

      <FormFooter
        submitting={submitting}
        onCancel={onCancel}
        submitLabel="Criar persona (v1, ativada)"
        isDirty={isDirty}
      />
    </form>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Edit form (cria nova versao)
// ───────────────────────────────────────────────────────────────────────────

type EditFormProps = {
  persona: AIPersonaDetail
  onSubmit: (values: PersonaUpdateValues) => Promise<void>
  onCancel: () => void
  submitting: boolean
}

export function PersonaEditForm({
  persona,
  onSubmit,
  onCancel,
  submitting,
}: EditFormProps) {
  const [domainsInput, setDomainsInput] = React.useState(() =>
    domainsToInput(persona.expertise_domains),
  )

  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isDirty },
    setValue,
  } = useForm<PersonaUpdateValues>({
    resolver: zodResolver(personaUpdateSchema),
    defaultValues: {
      display_name: persona.display_name,
      role_block: persona.role_block,
      description: persona.description ?? "",
      expertise_domains: persona.expertise_domains ?? [],
    },
  })

  React.useEffect(() => {
    setValue("expertise_domains", parseDomainsInput(domainsInput), {
      shouldDirty: domainsInput !== domainsToInput(persona.expertise_domains),
    })
  }, [domainsInput, persona.expertise_domains, setValue])

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
          A versao base ({persona.name}@v{persona.version}) e imutavel. Salvar
          gera v{persona.version + 1}. A versao ativa nao muda automaticamente
          — promova depois via &ldquo;Ativar versao&rdquo;.
        </p>
      </div>

      <section>
        <Label>Nome canonico</Label>
        <Input value={persona.name} disabled className="font-mono text-[13px]" />
        <FieldHint>Nao editavel — identifica a familia de versoes.</FieldHint>
      </section>

      <section>
        <Label htmlFor="persona-display-edit">Nome de exibicao</Label>
        <Input id="persona-display-edit" {...register("display_name")} />
        <FieldError message={errors.display_name?.message} />
      </section>

      <section>
        <Label htmlFor="persona-role-edit">Texto da persona (role_block)</Label>
        <Controller
          name="role_block"
          control={control}
          render={({ field }) => (
            <Textarea
              id="persona-role-edit"
              {...field}
              value={field.value ?? ""}
              rows={12}
              className="font-mono text-[13px]"
            />
          )}
        />
        <FieldHint>
          Markdown. Vai dentro de <code>&lt;persona&gt;</code> no system prompt.
        </FieldHint>
        <FieldError message={errors.role_block?.message} />
      </section>

      <Divider />

      <section>
        <Label htmlFor="persona-domains-edit">Dominios (tags)</Label>
        <Input
          id="persona-domains-edit"
          value={domainsInput}
          onChange={(e) => setDomainsInput(e.target.value)}
        />
        <FieldHint>Lista separada por virgula.</FieldHint>
      </section>

      <section>
        <Label htmlFor="persona-description-edit">
          Descricao (nota interna)
        </Label>
        <Controller
          name="description"
          control={control}
          render={({ field }) => (
            <Textarea
              id="persona-description-edit"
              {...field}
              value={field.value ?? ""}
              rows={2}
            />
          )}
        />
      </section>

      <FormFooter
        submitting={submitting}
        onCancel={onCancel}
        submitLabel={`Criar versao v${persona.version + 1}`}
        isDirty={isDirty}
      />
    </form>
  )
}
