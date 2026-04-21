"use client"

import * as React from "react"
import {
  RiArrowLeftLine,
  RiArrowRightLine,
  RiUploadCloud2Line,
  RiCheckboxCircleLine,
} from "@remixicon/react"

import { PageHeader } from "@/components/app/PageHeader"
import { Button } from "@/components/tremor/Button"
import { Card } from "@/components/tremor/Card"
import { Label } from "@/components/tremor/Label"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/tremor/Select"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRoot,
  TableRow,
} from "@/components/tremor/Table"
import { Badge } from "@/components/tremor/Badge"
import { Stepper, type Step } from "@/components/app/Stepper"

const steps: Step[] = [
  { id: "origem", label: "Origem", description: "Arquivo ou integracao" },
  { id: "mapeamento", label: "Mapeamento", description: "Colunas" },
  { id: "validacao", label: "Validacao", description: "Revisar pendencias" },
  { id: "confirmacao", label: "Confirmacao", description: "Finalizar" },
]

//
// Conteudo por step
//

function StepOrigem() {
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
          Origem dos dados
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Escolha o arquivo ou integracao que contem os contratos a importar.
        </p>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="tipo-origem">Tipo de origem</Label>
        <Select defaultValue="csv">
          <SelectTrigger id="tipo-origem">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="csv">Arquivo CSV</SelectItem>
            <SelectItem value="excel">Planilha Excel</SelectItem>
            <SelectItem value="api">Integracao via API</SelectItem>
          </SelectContent>
        </Select>
      </div>

      <div className="flex flex-col items-center justify-center gap-3 rounded border border-dashed border-gray-300 bg-gray-50 px-6 py-10 text-center dark:border-gray-700 dark:bg-gray-900">
        <div className="flex size-10 items-center justify-center rounded-full bg-white text-gray-700 dark:bg-gray-950 dark:text-gray-300">
          <RiUploadCloud2Line className="size-5" aria-hidden />
        </div>
        <div className="flex flex-col gap-1">
          <span className="text-sm font-medium text-gray-900 dark:text-gray-50">
            Arraste o arquivo aqui ou clique para selecionar
          </span>
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Aceita CSV e XLSX ate 10 MB.
          </span>
        </div>
      </div>
    </div>
  )
}

function StepMapeamento() {
  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
          Mapeamento de colunas
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Relacione cada coluna do arquivo a um campo de contrato.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {[
          { coluna: "numero_contrato", campo: "numero" },
          { coluna: "razao_social", campo: "cliente" },
          { coluna: "valor_mensal", campo: "valor" },
          { coluna: "dt_vencimento", campo: "vencimento" },
        ].map((linha) => (
          <div key={linha.coluna} className="flex flex-col gap-1.5">
            <Label htmlFor={`map-${linha.coluna}`}>{linha.coluna}</Label>
            <Select defaultValue={linha.campo}>
              <SelectTrigger id={`map-${linha.coluna}`}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="numero">Numero do contrato</SelectItem>
                <SelectItem value="cliente">Cliente</SelectItem>
                <SelectItem value="valor">Valor mensal</SelectItem>
                <SelectItem value="vencimento">Data de vencimento</SelectItem>
                <SelectItem value="ignorar">Ignorar coluna</SelectItem>
              </SelectContent>
            </Select>
          </div>
        ))}
      </div>
    </div>
  )
}

function StepValidacao() {
  const linhas = [
    {
      linha: 12,
      numero: "CNT-00052",
      problema: "Valor invalido",
      severidade: "error" as const,
    },
    {
      linha: 18,
      numero: "CNT-00058",
      problema: "Data fora do formato esperado",
      severidade: "warning" as const,
    },
    {
      linha: 23,
      numero: "CNT-00063",
      problema: "Cliente nao encontrado",
      severidade: "warning" as const,
    },
  ]

  return (
    <div className="flex flex-col gap-5">
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
          Validacao
        </h2>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          Revise as linhas com pendencias antes de confirmar a importacao.
        </p>
      </div>

      <TableRoot>
        <Table>
          <TableHead>
            <TableRow>
              <TableHeaderCell>Linha</TableHeaderCell>
              <TableHeaderCell>Numero</TableHeaderCell>
              <TableHeaderCell>Problema</TableHeaderCell>
              <TableHeaderCell>Severidade</TableHeaderCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {linhas.map((item) => (
              <TableRow key={item.linha}>
                <TableCell className="tabular-nums">{item.linha}</TableCell>
                <TableCell className="font-medium text-gray-900 dark:text-gray-50">
                  {item.numero}
                </TableCell>
                <TableCell>{item.problema}</TableCell>
                <TableCell>
                  <Badge variant={item.severidade}>
                    {item.severidade === "error" ? "Erro" : "Aviso"}
                  </Badge>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </TableRoot>
    </div>
  )
}

function StepConfirmacao() {
  return (
    <div className="flex flex-col items-center gap-4 py-4 text-center">
      <div className="flex size-12 items-center justify-center rounded-full bg-gray-100 text-gray-900 dark:bg-gray-900 dark:text-gray-50">
        <RiCheckboxCircleLine className="size-6" aria-hidden />
      </div>
      <div className="flex flex-col gap-1">
        <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
          Tudo pronto para importar
        </h2>
        <p className="max-w-md text-sm text-gray-500 dark:text-gray-400">
          Serao criados 42 novos contratos e atualizados 6 existentes. Esta
          acao pode ser revertida nas proximas 24 horas.
        </p>
      </div>
      <div className="grid grid-cols-3 gap-6 pt-2">
        <div className="flex flex-col">
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Novos
          </span>
          <span className="text-lg font-semibold text-gray-900 dark:text-gray-50">
            42
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Atualizados
          </span>
          <span className="text-lg font-semibold text-gray-900 dark:text-gray-50">
            6
          </span>
        </div>
        <div className="flex flex-col">
          <span className="text-xs text-gray-500 dark:text-gray-400">
            Ignorados
          </span>
          <span className="text-lg font-semibold text-gray-900 dark:text-gray-50">
            3
          </span>
        </div>
      </div>
    </div>
  )
}

export default function WizardTemplatePage() {
  const [currentIndex, setCurrentIndex] = React.useState(0)

  const isFirst = currentIndex === 0
  const isLast = currentIndex === steps.length - 1

  const handlePrev = () => {
    if (!isFirst) setCurrentIndex((index) => index - 1)
  }

  const handleNext = () => {
    if (isLast) {
      // eslint-disable-next-line no-console
      console.log("Importacao finalizada")
      return
    }
    setCurrentIndex((index) => index + 1)
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Importar contratos"
        subtitle="Siga as etapas para importar contratos em lote."
      />

      <Stepper steps={steps} currentIndex={currentIndex} />

      <Card>
        {currentIndex === 0 && <StepOrigem />}
        {currentIndex === 1 && <StepMapeamento />}
        {currentIndex === 2 && <StepValidacao />}
        {currentIndex === 3 && <StepConfirmacao />}
      </Card>

      <div className="flex items-center justify-between border-t border-gray-200 pt-4 dark:border-gray-800">
        <Button variant="secondary" onClick={handlePrev} disabled={isFirst}>
          <RiArrowLeftLine className="mr-1.5 size-4" aria-hidden />
          Voltar
        </Button>
        <Button variant="primary" onClick={handleNext}>
          {isLast ? "Finalizar" : "Proximo"}
          {!isLast && (
            <RiArrowRightLine className="ml-1.5 size-4" aria-hidden />
          )}
        </Button>
      </div>
    </div>
  )
}
