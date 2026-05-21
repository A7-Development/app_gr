"use client"

//
// ExpertiseForm — formulario de expertise de agente (admin IA, F2.c.2).
//
// Expertise = knowledge pack injetado no system prompt (CLAUDE.md §19.12).
// Versionamento: editar SEMPRE cria nova versao; base imutavel.
//

import * as React from "react"
import { Controller, useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { RiLoader4Line } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { Divider } from "@/components/tremor/Divider"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import { Textarea } from "@/components/tremor/Textarea"
import type { AIExpertiseDetail } from "@/lib/api-client"
import {
  DOMAIN_SUGGESTIONS,
  expertiseCreateSchema,
  expertiseUpdateSchema,
  parseReferencesInput,
  referencesToInput,
  type ExpertiseCreateValues,
  type ExpertiseUpdateValues,
} from "@/lib/schemas/ai-expertise-schema"
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
// Create form
// ───────────────────────────────────────────────────────────────────────────

type CreateFormProps = {
  onSubmit: (values: ExpertiseCreateValues) => Promise<void>
  onCancel: () => void
  submitting: boolean
}

export function ExpertiseCreateForm({
  onSubmit,
  onCancel,
  submitting,
}: CreateFormProps) {
  const [refsInput, setRefsInput] = React.useState("")

  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isDirty },
    setValue,
  } = useForm<ExpertiseCreateValues>({
    resolver: zodResolver(expertiseCreateSchema),
    defaultValues: {
      name: "",
      display_name: "",
      domain: "",
      knowledge_text: "",
      reference_urls: [],
    },
  })

  // Sync refs textarea -> form value.
  React.useEffect(() => {
    setValue("reference_urls", parseReferencesInput(refsInput), {
      shouldDirty: true,
    })
  }, [refsInput, setValue])

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex flex-col gap-5">
      <section>
        <Label htmlFor="expertise-name">
          Nome canonico
          <RequiredMarker />
        </Label>
        <Input
          id="expertise-name"
          {...register("name")}
          placeholder="ex: contabilidade.fidc"
          autoComplete="off"
          // HTML5 pattern: feedback visual em tempo real no browser
          // (alem do Zod schema que valida no submit). Sem espacos,
          // sem maiusculas, sem caracteres especiais.
          pattern="^[a-z0-9]+(\.[a-z0-9_]+)*$"
          title="Use minusculas, digitos, pontos e underscores. Sem espacos. Ex: contabilidade.fidc"
        />
        <FieldHint>
          Formato: <code>dominio.topico</code>. Minusculas, pontos e
          underscores. Identifica unicamente esta expertise.
        </FieldHint>
        <FieldError message={errors.name?.message} />
      </section>

      <section>
        <Label htmlFor="expertise-display">
          Nome de exibicao
          <RequiredMarker />
        </Label>
        <Input
          id="expertise-display"
          {...register("display_name")}
          placeholder="ex: Contabilidade FIDC"
        />
        <FieldError message={errors.display_name?.message} />
      </section>

      <section>
        <Label htmlFor="expertise-domain">
          Dominio
          <RequiredMarker />
        </Label>
        <Input
          id="expertise-domain"
          list="domain-suggestions"
          {...register("domain")}
          placeholder="ex: contabilidade"
          autoComplete="off"
        />
        <datalist id="domain-suggestions">
          {DOMAIN_SUGGESTIONS.map((d) => (
            <option key={d} value={d} />
          ))}
        </datalist>
        <FieldHint>
          Area do conhecimento (contabilidade, credito, risco, regulatorio,
          mercado, ...). Usado pra filtrar/agrupar.
        </FieldHint>
        <FieldError message={errors.domain?.message} />
      </section>

      <section>
        <Label htmlFor="expertise-knowledge">
          Texto de conhecimento
          <RequiredMarker />
        </Label>
        <Controller
          name="knowledge_text"
          control={control}
          render={({ field }) => (
            <Textarea
              id="expertise-knowledge"
              {...field}
              rows={16}
              placeholder={
                "## Conceitos chave\n\n- Cota subordinada captura residual...\n\n" +
                "## CPC 48 — instrumentos financeiros\n\nMarkdown e suportado..."
              }
              className="font-mono text-[13px]"
            />
          )}
        />
        <FieldHint>
          Markdown. Vai dentro de <code>&lt;expertise name=&quot;...&quot;&gt;</code>
          no system prompt. Use headers, listas, tabelas, codigo livremente.
        </FieldHint>
        <FieldError message={errors.knowledge_text?.message} />
      </section>

      <Divider />

      <section>
        <Label htmlFor="expertise-refs">Referencias (URLs)</Label>
        <Textarea
          id="expertise-refs"
          value={refsInput}
          onChange={(e) => setRefsInput(e.target.value)}
          rows={4}
          placeholder={
            "https://www.bcb.gov.br/... | CMN 4966 | norma\n" +
            "https://www.cvm.gov.br/... | Instrucao 175 | norma"
          }
          className="font-mono text-[12px]"
        />
        <FieldHint>
          Uma linha por referencia. Formato:{" "}
          <code>url | label | kind?</code> (kind opcional: <em>norma</em>,{" "}
          <em>doc</em>, <em>link</em>).
        </FieldHint>
      </section>

      <FormFooter
        submitting={submitting}
        onCancel={onCancel}
        submitLabel="Criar expertise (v1, ativada)"
        isDirty={isDirty}
      />
    </form>
  )
}

// ───────────────────────────────────────────────────────────────────────────
// Edit form (cria nova versao)
// ───────────────────────────────────────────────────────────────────────────

type EditFormProps = {
  expertise: AIExpertiseDetail
  onSubmit: (values: ExpertiseUpdateValues) => Promise<void>
  onCancel: () => void
  submitting: boolean
}

export function ExpertiseEditForm({
  expertise,
  onSubmit,
  onCancel,
  submitting,
}: EditFormProps) {
  const [refsInput, setRefsInput] = React.useState(() =>
    referencesToInput(expertise.reference_urls),
  )

  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isDirty },
    setValue,
  } = useForm<ExpertiseUpdateValues>({
    resolver: zodResolver(expertiseUpdateSchema),
    defaultValues: {
      display_name: expertise.display_name,
      domain: expertise.domain,
      knowledge_text: expertise.knowledge_text,
      reference_urls: expertise.reference_urls ?? [],
    },
  })

  React.useEffect(() => {
    setValue("reference_urls", parseReferencesInput(refsInput), {
      shouldDirty: refsInput !== referencesToInput(expertise.reference_urls),
    })
  }, [refsInput, expertise.reference_urls, setValue])

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
          A versao base ({expertise.name}@v{expertise.version}) e imutavel.
          Salvar gera v{expertise.version + 1}. A versao ativa nao muda
          automaticamente — promova depois via &ldquo;Ativar versao&rdquo;.
        </p>
      </div>

      <section>
        <Label>Nome canonico</Label>
        <Input
          value={expertise.name}
          disabled
          className="font-mono text-[13px]"
        />
        <FieldHint>Nao editavel — identifica a familia de versoes.</FieldHint>
      </section>

      <section>
        <Label htmlFor="expertise-display-edit">Nome de exibicao</Label>
        <Input id="expertise-display-edit" {...register("display_name")} />
        <FieldError message={errors.display_name?.message} />
      </section>

      <section>
        <Label htmlFor="expertise-domain-edit">Dominio</Label>
        <Input
          id="expertise-domain-edit"
          list="domain-suggestions-edit"
          {...register("domain")}
        />
        <datalist id="domain-suggestions-edit">
          {DOMAIN_SUGGESTIONS.map((d) => (
            <option key={d} value={d} />
          ))}
        </datalist>
        <FieldError message={errors.domain?.message} />
      </section>

      <section>
        <Label htmlFor="expertise-knowledge-edit">Texto de conhecimento</Label>
        <Controller
          name="knowledge_text"
          control={control}
          render={({ field }) => (
            <Textarea
              id="expertise-knowledge-edit"
              {...field}
              value={field.value ?? ""}
              rows={20}
              className="font-mono text-[13px]"
            />
          )}
        />
        <FieldHint>
          Markdown. Vai dentro de <code>&lt;expertise&gt;</code> no system prompt.
        </FieldHint>
        <FieldError message={errors.knowledge_text?.message} />
      </section>

      <Divider />

      <section>
        <Label htmlFor="expertise-refs-edit">Referencias (URLs)</Label>
        <Textarea
          id="expertise-refs-edit"
          value={refsInput}
          onChange={(e) => setRefsInput(e.target.value)}
          rows={4}
          className="font-mono text-[12px]"
        />
        <FieldHint>
          Uma linha por referencia: <code>url | label | kind?</code>.
        </FieldHint>
      </section>

      <FormFooter
        submitting={submitting}
        onCancel={onCancel}
        submitLabel={`Criar versao v${expertise.version + 1}`}
        isDirty={isDirty}
      />
    </form>
  )
}
