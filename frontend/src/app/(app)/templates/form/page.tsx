"use client"

import * as React from "react"
import { Controller, useForm } from "react-hook-form"
import { zodResolver } from "@hookform/resolvers/zod"
import { z } from "zod"
import { toast, Toaster } from "sonner"
import { ptBR } from "date-fns/locale"
import { RiLoader4Line } from "@remixicon/react"

import { PageHeader } from "@/components/app/PageHeader"
import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import { Input } from "@/components/tremor/Input"
import { Label } from "@/components/tremor/Label"
import { Textarea } from "@/components/tremor/Textarea"
import { Checkbox } from "@/components/tremor/Checkbox"
import { Switch } from "@/components/tremor/Switch"
import { Divider } from "@/components/tremor/Divider"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import { DatePicker } from "@/components/tremor/DatePicker"

//
// Schema zod
//

const contratoSchema = z.object({
  numero: z.string().min(3, "Informe o numero do contrato."),
  cliente: z.string().min(2, "Informe o cliente."),
  responsavel: z.string().min(2, "Informe o responsavel."),
  modalidade: z.enum(["mensal", "anual", "avulso"], {
    message: "Selecione uma modalidade.",
  }),
  inicio: z.date({ message: "Selecione a data de inicio." }),
  observacoes: z.string().max(500).optional(),
  valor: z
    .number({ message: "Informe o valor." })
    .positive("O valor deve ser positivo."),
  parcelas: z
    .number({ message: "Informe o numero de parcelas." })
    .int()
    .min(1, "Minimo 1 parcela.")
    .max(120, "Maximo 120 parcelas."),
  reajusteAnual: z.boolean(),
  notificarCliente: z.boolean(),
  termosAceitos: z.boolean().refine((value) => value === true, {
    message: "Voce precisa aceitar os termos.",
  }),
})

type ContratoFormValues = z.infer<typeof contratoSchema>

const defaultValues: Partial<ContratoFormValues> = {
  numero: "",
  cliente: "",
  responsavel: "",
  observacoes: "",
  parcelas: 12,
  reajusteAnual: true,
  notificarCliente: false,
  termosAceitos: false,
}

export default function FormTemplatePage() {
  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isSubmitting },
  } = useForm<ContratoFormValues>({
    resolver: zodResolver(contratoSchema),
    defaultValues: defaultValues as ContratoFormValues,
  })

  const onSubmit = async (values: ContratoFormValues) => {
    await new Promise((resolve) => setTimeout(resolve, 600))
    // eslint-disable-next-line no-console
    console.log("Contrato salvo", values)
    toast.success("Contrato salvo com sucesso.")
  }

  return (
    <div className="flex flex-col gap-6 pb-24">
      <Toaster richColors position="top-right" />

      <PageHeader
        breadcrumbs={[
          { label: "Contratos", href: "/templates/list" },
          { label: "Novo contrato" },
        ]}
        title="Novo contrato"
        subtitle="Preencha os dados abaixo para criar um novo contrato."
      />

      <form
        id="form-contrato"
        onSubmit={handleSubmit(onSubmit)}
        className="flex flex-col gap-6"
      >
        <Card className="flex flex-col gap-6">
          <div className="flex flex-col gap-1">
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
              Dados gerais
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Informacoes de identificacao do contrato.
            </p>
          </div>

          <Divider />

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="numero">Numero do contrato</Label>
              <Input
                id="numero"
                placeholder="CNT-00001"
                hasError={Boolean(errors.numero)}
                {...register("numero")}
              />
              {errors.numero && (
                <span className="text-xs text-red-600 dark:text-red-500">
                  {errors.numero.message}
                </span>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="cliente">Cliente</Label>
              <Input
                id="cliente"
                placeholder="Razao social do cliente"
                hasError={Boolean(errors.cliente)}
                {...register("cliente")}
              />
              {errors.cliente && (
                <span className="text-xs text-red-600 dark:text-red-500">
                  {errors.cliente.message}
                </span>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="responsavel">Responsavel interno</Label>
              <Input
                id="responsavel"
                placeholder="Nome do responsavel"
                hasError={Boolean(errors.responsavel)}
                {...register("responsavel")}
              />
              {errors.responsavel && (
                <span className="text-xs text-red-600 dark:text-red-500">
                  {errors.responsavel.message}
                </span>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="modalidade">Modalidade</Label>
              <Controller
                control={control}
                name="modalidade"
                render={({ field }) => (
                  <Select
                    value={field.value}
                    onValueChange={field.onChange}
                  >
                    <SelectTrigger
                      id="modalidade"
                      hasError={Boolean(errors.modalidade)}
                    >
                      <SelectValue placeholder="Selecione a modalidade" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="mensal">Mensal</SelectItem>
                      <SelectItem value="anual">Anual</SelectItem>
                      <SelectItem value="avulso">Avulso</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
              {errors.modalidade && (
                <span className="text-xs text-red-600 dark:text-red-500">
                  {errors.modalidade.message}
                </span>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="inicio">Data de inicio</Label>
              <Controller
                control={control}
                name="inicio"
                render={({ field }) => (
                  <DatePicker
                    value={field.value}
                    onChange={field.onChange}
                    locale={ptBR}
                    placeholder="Selecione a data"
                    hasError={Boolean(errors.inicio)}
                    translations={{
                      cancel: "Cancelar",
                      apply: "Aplicar",
                    }}
                  />
                )}
              />
              {errors.inicio && (
                <span className="text-xs text-red-600 dark:text-red-500">
                  {errors.inicio.message}
                </span>
              )}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="observacoes">Observacoes</Label>
            <Textarea
              id="observacoes"
              placeholder="Observacoes internas sobre o contrato..."
              rows={4}
              {...register("observacoes")}
            />
          </div>
        </Card>

        <Card className="flex flex-col gap-6">
          <div className="flex flex-col gap-1">
            <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
              Condicoes comerciais
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Valor, parcelamento e regras de reajuste.
            </p>
          </div>

          <Divider />

          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="valor">Valor total (R$)</Label>
              <Input
                id="valor"
                type="number"
                step="0.01"
                min="0"
                enableStepper={false}
                placeholder="0,00"
                hasError={Boolean(errors.valor)}
                {...register("valor", { valueAsNumber: true })}
              />
              {errors.valor && (
                <span className="text-xs text-red-600 dark:text-red-500">
                  {errors.valor.message}
                </span>
              )}
            </div>

            <div className="flex flex-col gap-1.5">
              <Label htmlFor="parcelas">Numero de parcelas</Label>
              <Input
                id="parcelas"
                type="number"
                min="1"
                max="120"
                step="1"
                placeholder="12"
                hasError={Boolean(errors.parcelas)}
                {...register("parcelas", { valueAsNumber: true })}
              />
              {errors.parcelas && (
                <span className="text-xs text-red-600 dark:text-red-500">
                  {errors.parcelas.message}
                </span>
              )}
            </div>
          </div>

          <Divider />

          <div className="flex flex-col gap-4">
            <Controller
              control={control}
              name="reajusteAnual"
              render={({ field }) => (
                <div className="flex items-center justify-between gap-4">
                  <div className="flex flex-col gap-0.5">
                    <Label htmlFor="reajuste-anual">Reajuste anual</Label>
                    <span className="text-sm text-gray-500 dark:text-gray-400">
                      Aplicar IPCA no aniversario do contrato.
                    </span>
                  </div>
                  <Switch
                    id="reajuste-anual"
                    checked={field.value}
                    onCheckedChange={field.onChange}
                  />
                </div>
              )}
            />

            <Controller
              control={control}
              name="notificarCliente"
              render={({ field }) => (
                <div className="flex items-start gap-2">
                  <Checkbox
                    id="notificar-cliente"
                    checked={field.value}
                    onCheckedChange={(checked) =>
                      field.onChange(checked === true)
                    }
                  />
                  <div className="flex flex-col gap-0.5">
                    <Label htmlFor="notificar-cliente">
                      Notificar o cliente por e-mail
                    </Label>
                    <span className="text-sm text-gray-500 dark:text-gray-400">
                      Envia uma copia assinada para o contato principal.
                    </span>
                  </div>
                </div>
              )}
            />

            <Controller
              control={control}
              name="termosAceitos"
              render={({ field }) => (
                <div className="flex flex-col gap-1">
                  <div className="flex items-start gap-2">
                    <Checkbox
                      id="termos-aceitos"
                      checked={field.value}
                      onCheckedChange={(checked) =>
                        field.onChange(checked === true)
                      }
                    />
                    <Label htmlFor="termos-aceitos">
                      Confirmo que li e aceito os termos internos de
                      contratacao.
                    </Label>
                  </div>
                  {errors.termosAceitos && (
                    <span className="text-xs text-red-600 dark:text-red-500">
                      {errors.termosAceitos.message}
                    </span>
                  )}
                </div>
              )}
            />
          </div>
        </Card>
      </form>

      {/* Rodape fixo de acoes */}
      <div className="fixed inset-x-0 bottom-0 z-20 border-t border-gray-200 bg-white/95 px-6 py-3 backdrop-blur dark:border-gray-800 dark:bg-gray-950/95">
        <div className="mx-auto flex max-w-7xl items-center justify-end gap-2">
          <Button variant="secondary" type="button">
            Cancelar
          </Button>
          <Button
            type="submit"
            form="form-contrato"
            variant="primary"
            disabled={isSubmitting}
          >
            {isSubmitting && (
              <RiLoader4Line
                className="mr-1.5 size-4 animate-spin"
                aria-hidden
              />
            )}
            Salvar contrato
          </Button>
        </div>
      </div>
    </div>
  )
}
