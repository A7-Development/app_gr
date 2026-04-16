"use client"

import * as React from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { toast } from "sonner"
import {
  RiGoogleFill,
  RiLoader4Line,
  RiMicrosoftFill,
} from "@remixicon/react"

import { Button } from "@/components/tremor/Button"
import { Checkbox } from "@/components/tremor/Checkbox"
import { Divider } from "@/components/tremor/Divider"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import { Logo } from "@/components/app/Logo"

//
// Schema de validacao
//

const loginSchema = z.object({
  email: z
    .string()
    .min(1, "Informe seu e-mail")
    .email("E-mail invalido"),
  password: z.string().min(1, "Informe sua senha"),
  remember: z.boolean(),
})

type LoginFormValues = z.infer<typeof loginSchema>

//
// Pagina
//

export default function LoginPage() {
  const router = useRouter()
  const [submitting, setSubmitting] = React.useState(false)

  const form = useForm<LoginFormValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { email: "", password: "", remember: false },
  })

  const errors = form.formState.errors
  const rememberChecked = form.watch("remember")

  async function onSubmit(values: LoginFormValues) {
    setSubmitting(true)
    try {
      // TODO: integrar com backend real (POST /api/v1/auth/login).
      // Por ora apenas simula a operacao.
      console.log("[login] submit", values)
      await new Promise((resolve) => setTimeout(resolve, 600))
      toast.success("Login efetuado com sucesso")
      router.push("/")
    } catch (error) {
      console.error("[login] error", error)
      toast.error("Nao foi possivel fazer login. Tente novamente.")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="rounded-lg border border-gray-200 bg-white p-6 shadow-sm dark:border-gray-800 dark:bg-gray-900 sm:p-8">
        <div className="flex flex-col items-center gap-4 text-center">
          <Logo variant="full" />
          <div className="flex flex-col gap-1">
            <h1 className="text-xl font-semibold text-gray-900 dark:text-gray-50">
              Acessar sua conta
            </h1>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Entre com suas credenciais para continuar
            </p>
          </div>
        </div>

        {/* SSO */}
        <div className="mt-6 flex flex-col gap-2">
          <Button
            type="button"
            variant="secondary"
            disabled
            className="w-full gap-2"
          >
            <RiMicrosoftFill
              className="size-5 shrink-0"
              aria-hidden="true"
            />
            Entrar com Microsoft
          </Button>
          <Button
            type="button"
            variant="secondary"
            disabled
            className="w-full gap-2"
          >
            <RiGoogleFill className="size-5 shrink-0" aria-hidden="true" />
            Entrar com Google
          </Button>
        </div>

        <Divider>ou</Divider>

        {/* Credenciais */}
        <form
          onSubmit={form.handleSubmit(onSubmit)}
          className="flex flex-col gap-4"
        >
          <div className="flex flex-col gap-2">
            <Label htmlFor="email">E-mail</Label>
            <Input
              id="email"
              type="email"
              placeholder="voce@a7credit.com.br"
              autoComplete="email"
              hasError={!!errors.email}
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

          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <Label htmlFor="password">Senha</Label>
              <Link
                href="#"
                className="text-xs font-medium text-blue-600 transition hover:text-blue-700 dark:text-blue-500 dark:hover:text-blue-400"
              >
                Esqueci minha senha
              </Link>
            </div>
            <Input
              id="password"
              type="password"
              placeholder="Sua senha"
              autoComplete="current-password"
              hasError={!!errors.password}
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

          <div className="flex items-center gap-2">
            <Checkbox
              id="remember"
              checked={rememberChecked}
              onCheckedChange={(checked) =>
                form.setValue("remember", checked === true, {
                  shouldDirty: true,
                })
              }
            />
            <Label
              htmlFor="remember"
              className="cursor-pointer font-normal text-gray-700 dark:text-gray-300"
            >
              Manter conectado
            </Label>
          </div>

          <Button
            type="submit"
            disabled={submitting}
            className="mt-2 w-full gap-2"
          >
            {submitting && (
              <RiLoader4Line
                className="size-4 shrink-0 animate-spin"
                aria-hidden="true"
              />
            )}
            Entrar
          </Button>
        </form>
      </div>

      <p className="text-center text-xs text-gray-500 dark:text-gray-400">
        Nao tem acesso? Fale com o administrador do sistema.
      </p>
    </div>
  )
}
