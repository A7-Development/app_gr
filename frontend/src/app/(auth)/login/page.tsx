"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { toast } from "sonner"
import { RiErrorWarningLine, RiLoader4Line } from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import { HeroSplitAuth, STRATA_TRUST_SIGNALS } from "@/design-system/surfaces"
import { ApiError, login } from "@/lib/api-client"

//
// Schema de validacao
//

const loginSchema = z.object({
  email: z
    .string()
    .min(1, "Informe seu e-mail")
    .email("E-mail invalido"),
  password: z.string().min(1, "Informe sua senha"),
})

type LoginFormValues = z.infer<typeof loginSchema>

//
// Pagina
//

export default function LoginPage() {
  const router = useRouter()
  const [submitting, setSubmitting] = React.useState(false)
  const [authError, setAuthError] = React.useState<string | null>(null)
  const [shakeKey, setShakeKey] = React.useState(0)

  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "" },
  })

  const errors = form.formState.errors

  async function onSubmit(values: LoginFormValues) {
    setSubmitting(true)
    setAuthError(null)
    try {
      await login(values.email, values.password)
      toast.success("Login efetuado com sucesso")
      router.push("/")
    } catch (error) {
      console.error("[login] error", error)
      const message =
        error instanceof ApiError && error.status === 401
          ? "E-mail ou senha incorretos. Verifique as credenciais e tente novamente."
          : "Nao foi possivel fazer login. Tente novamente em instantes."
      setAuthError(message)
      setShakeKey((k) => k + 1)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <HeroSplitAuth>
      {/* ── HERO ZONE (60%) ───────────────────────────────────────── */}
      <HeroSplitAuth.Hero>
        <HeroSplitAuth.Brand wordmark="Strata" eyebrow="FIDC Analytics" />
        <HeroSplitAuth.HeroSpacer />
        <HeroSplitAuth.Headline>
          Inteligência de dados
          <br />
          para FIDC
        </HeroSplitAuth.Headline>
        <HeroSplitAuth.Lede>
          A plataforma de analytics para gestores de FIDC que operam com
          precisão institucional.
        </HeroSplitAuth.Lede>
        <HeroSplitAuth.HeroSpacer />
        <HeroSplitAuth.TrustSignals items={STRATA_TRUST_SIGNALS} />
      </HeroSplitAuth.Hero>

      {/* ── FORM ZONE (40%) ───────────────────────────────────────── */}
      <HeroSplitAuth.FormPanel
        title="Acesse sua conta"
        description="Bem-vindo de volta. Faça login para continuar."
        footer={
          <>
            Sem acesso?{" "}
            <Link
              href="#"
              className="font-medium text-blue-600 hover:underline dark:text-blue-500"
            >
              Contate seu administrador
            </Link>
          </>
        }
      >
        {authError && (
          <div
            key={shakeKey}
            data-hero-anim
            role="alert"
            className="mb-5 flex items-start gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2.5 dark:border-red-900/50 dark:bg-red-950/30"
            style={{ animation: "heroShake 0.5s ease both" }}
          >
            <RiErrorWarningLine
              className="mt-0.5 size-4 shrink-0 text-red-600 dark:text-red-400"
              aria-hidden="true"
            />
            <p className="text-[13px] leading-relaxed text-red-700 dark:text-red-300">
              {authError}
            </p>
          </div>
        )}

        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="flex flex-col gap-[18px]"
        >
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email" className="text-[13px] font-medium">
              E-mail
            </Label>
            <Input
              id="email"
              type="email"
              placeholder="seu@email.com.br"
              autoComplete="email"
              disabled={submitting}
              hasError={!!errors.email || !!authError}
              aria-invalid={!!errors.email}
              {...form.register("email")}
            />
            {errors.email && (
              <p
                role="alert"
                className="text-xs text-red-600 dark:text-red-400"
              >
                {errors.email.message}
              </p>
            )}
          </div>

          <div className="flex flex-col gap-1.5">
            <div className="flex items-center justify-between">
              <Label htmlFor="password" className="text-[13px] font-medium">
                Senha
              </Label>
              <Link
                href="#"
                className="text-xs font-medium text-blue-600 hover:underline dark:text-blue-500"
              >
                Esqueceu a senha?
              </Link>
            </div>
            <Input
              id="password"
              type="password"
              placeholder="********"
              autoComplete="current-password"
              disabled={submitting}
              hasError={!!errors.password || !!authError}
              aria-invalid={!!errors.password}
              {...form.register("password")}
            />
            {errors.password && (
              <p
                role="alert"
                className="text-xs text-red-600 dark:text-red-400"
              >
                {errors.password.message}
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
                <RiLoader4Line
                  className="size-4 shrink-0 animate-spin"
                  aria-hidden="true"
                />
                Entrando...
              </>
            ) : (
              "Entrar"
            )}
          </Button>
        </form>
      </HeroSplitAuth.FormPanel>
    </HeroSplitAuth>
  )
}
