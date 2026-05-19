// Surface publica de aceite de convite.
//
// Fluxo:
//   1. GET /invitations/{token}  -> contexto (tenant, email, role, expira)
//   2. POST /invitations/{token}/accept { name, password }
//      -> cria User, ja popula permissoes via role defaults, retorna JWT
//      -> salva token + redireciona pra /
//
// Estados de erro:
//   - 404 token nao encontrado
//   - 410 expirado
//   - 409 ja consumido
//   Renderiza error state com CTA pra contatar quem convidou.

"use client"

import * as React from "react"
import { useParams, useRouter } from "next/navigation"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { toast } from "sonner"
import { RiErrorWarningLine, RiLoader4Line } from "@remixicon/react"
import { useQuery } from "@tanstack/react-query"
import { format, parseISO } from "date-fns"
import { ptBR } from "date-fns/locale"

import { Button } from "@/components/tremor/Button"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import { HeroSplitAuth, STRATA_TRUST_SIGNALS } from "@/design-system/surfaces"
import { ApiError, invitations, setToken } from "@/lib/api-client"

const ROLE_LABEL: Record<string, string> = {
  owner: "Owner",
  member: "Member",
  viewer: "Viewer",
}

const acceptSchema = z
  .object({
    name: z.string().min(2, "Informe seu nome").max(255),
    password: z.string().min(8, "Minimo 8 caracteres").max(128),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, {
    message: "As senhas nao conferem",
    path: ["confirm"],
  })

type FormValues = z.infer<typeof acceptSchema>

export default function AcceptInvitationPage() {
  const router = useRouter()
  const params = useParams<{ token: string }>()
  const token = params.token

  const ctxQuery = useQuery({
    queryKey: ["invitation-context", token],
    queryFn: () => invitations.context(token),
    retry: false,
  })

  const [submitting, setSubmitting] = React.useState(false)
  const [serverError, setServerError] = React.useState<string | null>(null)

  const form = useForm<FormValues>({
    resolver: zodResolver(acceptSchema),
    defaultValues: { name: "", password: "", confirm: "" },
  })

  const errors = form.formState.errors

  async function onSubmit(values: FormValues) {
    setSubmitting(true)
    setServerError(null)
    try {
      const res = await invitations.accept(token, {
        name: values.name.trim(),
        password: values.password,
      })
      setToken(res.access_token)
      toast.success("Bem-vindo!")
      router.push("/")
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? typeof err.detail === "string"
            ? err.detail
            : "Falha ao aceitar convite. Tente novamente."
          : "Falha ao aceitar convite. Tente novamente."
      setServerError(msg)
    } finally {
      setSubmitting(false)
    }
  }

  // Mapeia erros de contexto pra mensagens humanas.
  const ctxError = ctxQuery.error instanceof ApiError ? ctxQuery.error : null
  const ctx = ctxQuery.data ?? null

  return (
    <HeroSplitAuth>
      <HeroSplitAuth.Hero>
        <HeroSplitAuth.Brand wordmark="Strata" eyebrow="Agentic Solution" />
        <HeroSplitAuth.HeroSpacer />
        <HeroSplitAuth.Headline>
          {ctx ? (
            <>
              Voce foi convidado para
              <br />
              {ctx.tenant_name}.
            </>
          ) : (
            <>
              Aceite seu convite
              <br />
              para entrar.
            </>
          )}
        </HeroSplitAuth.Headline>
        <HeroSplitAuth.Lede>
          {ctx ? (
            <>
              Defina sua senha e voce ja entra como{" "}
              <HeroSplitAuth.Highlight>{ROLE_LABEL[ctx.role] ?? ctx.role}</HeroSplitAuth.Highlight>.
            </>
          ) : (
            <>O Strata centraliza suas analises. Os agentes multiplicam o que sua equipe pode fazer.</>
          )}
        </HeroSplitAuth.Lede>
        <HeroSplitAuth.HeroSpacer />
        <HeroSplitAuth.TrustSignals items={STRATA_TRUST_SIGNALS} />
      </HeroSplitAuth.Hero>

      <HeroSplitAuth.FormPanel
        title={ctx ? "Crie sua conta" : "Convite"}
        description={
          ctx
            ? `Para ${ctx.email} em ${ctx.tenant_name}.`
            : "Verificando o link recebido..."
        }
        footer={
          ctx ? (
            <>
              Convite expira em{" "}
              <span className="font-medium text-gray-900 dark:text-gray-50">
                {format(parseISO(ctx.expires_at), "dd/MM/yyyy 'as' HH:mm", { locale: ptBR })}
              </span>
              .
            </>
          ) : null
        }
      >
        {ctxQuery.isLoading && (
          <div className="flex items-center gap-2 text-sm text-gray-500">
            <RiLoader4Line className="size-4 animate-spin" aria-hidden />
            Verificando link...
          </div>
        )}

        {ctxError && (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2.5 dark:border-red-900/50 dark:bg-red-950/30"
          >
            <RiErrorWarningLine
              className="mt-0.5 size-4 shrink-0 text-red-600 dark:text-red-400"
              aria-hidden
            />
            <div className="flex flex-col gap-1">
              <p className="text-sm font-medium text-red-700 dark:text-red-300">
                {ctxError.status === 404 && "Convite invalido"}
                {ctxError.status === 410 && "Convite expirado"}
                {ctxError.status === 409 && "Convite ja utilizado"}
                {![404, 410, 409].includes(ctxError.status) && "Erro ao validar convite"}
              </p>
              <p className="text-[13px] leading-relaxed text-red-700 dark:text-red-300">
                {typeof ctxError.detail === "string"
                  ? ctxError.detail
                  : "Peca um novo convite a quem te convidou."}
              </p>
            </div>
          </div>
        )}

        {ctx && (
          <>
            {serverError && (
              <div
                role="alert"
                className="mb-4 flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2.5 dark:border-red-900/50 dark:bg-red-950/30"
              >
                <RiErrorWarningLine
                  className="mt-0.5 size-4 shrink-0 text-red-600 dark:text-red-400"
                  aria-hidden
                />
                <p className="text-[13px] leading-relaxed text-red-700 dark:text-red-300">
                  {serverError}
                </p>
              </div>
            )}

            <form
              onSubmit={form.handleSubmit(onSubmit)}
              className="flex flex-col gap-[18px]"
            >
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="name" className="text-[13px] font-medium">
                  Seu nome
                </Label>
                <Input
                  id="name"
                  placeholder="Como prefere ser chamado"
                  disabled={submitting}
                  hasError={!!errors.name}
                  autoComplete="name"
                  {...form.register("name")}
                />
                {errors.name && (
                  <p role="alert" className="text-xs text-red-600 dark:text-red-400">
                    {errors.name.message}
                  </p>
                )}
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="password" className="text-[13px] font-medium">
                  Senha
                </Label>
                <Input
                  id="password"
                  type="password"
                  placeholder="Minimo 8 caracteres"
                  disabled={submitting}
                  hasError={!!errors.password}
                  autoComplete="new-password"
                  {...form.register("password")}
                />
                {errors.password && (
                  <p role="alert" className="text-xs text-red-600 dark:text-red-400">
                    {errors.password.message}
                  </p>
                )}
              </div>

              <div className="flex flex-col gap-1.5">
                <Label htmlFor="confirm" className="text-[13px] font-medium">
                  Confirme a senha
                </Label>
                <Input
                  id="confirm"
                  type="password"
                  placeholder="Repita a senha"
                  disabled={submitting}
                  hasError={!!errors.confirm}
                  autoComplete="new-password"
                  {...form.register("confirm")}
                />
                {errors.confirm && (
                  <p role="alert" className="text-xs text-red-600 dark:text-red-400">
                    {errors.confirm.message}
                  </p>
                )}
              </div>

              <Button
                type="submit"
                disabled={submitting}
                className="mt-1 h-11 w-full gap-2 text-sm font-semibold"
              >
                {submitting ? (
                  <>
                    <RiLoader4Line className="size-4 shrink-0 animate-spin" aria-hidden />
                    Entrando...
                  </>
                ) : (
                  "Aceitar convite e entrar"
                )}
              </Button>
            </form>
          </>
        )}
      </HeroSplitAuth.FormPanel>
    </HeroSplitAuth>
  )
}
