import { format } from "date-fns"
import { ptBR } from "date-fns/locale"
import {
  RiAddLine,
  RiArrowLeftLine,
  RiArrowRightLine,
} from "@remixicon/react"

import { PageHeader } from "@/components/app/PageHeader"
import { Button } from "@/components/tremor/Button"
import { Badge } from "@/components/tremor/Badge"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRoot,
  TableRow,
} from "@/components/tremor/Table"

import { ContratosFilters } from "./_components/ContratosFilters"
import { ContratosRowActions } from "./_components/ContratosRowActions"

type StatusContrato = "ativo" | "pausado" | "encerrado"

type Contrato = {
  id: string
  numero: string
  cliente: string
  valor: number
  vencimento: Date
  status: StatusContrato
}

const contratos: Contrato[] = [
  {
    id: "1",
    numero: "CNT-00042",
    cliente: "Industria Alfa Ltda.",
    valor: 25800,
    vencimento: new Date(2026, 4, 15),
    status: "ativo",
  },
  {
    id: "2",
    numero: "CNT-00043",
    cliente: "Comercial Beta S.A.",
    valor: 12900.5,
    vencimento: new Date(2026, 4, 22),
    status: "ativo",
  },
  {
    id: "3",
    numero: "CNT-00044",
    cliente: "Transportes Gama",
    valor: 8700,
    vencimento: new Date(2026, 5, 2),
    status: "pausado",
  },
  {
    id: "4",
    numero: "CNT-00045",
    cliente: "Servicos Delta ME",
    valor: 3200,
    vencimento: new Date(2026, 3, 30),
    status: "encerrado",
  },
  {
    id: "5",
    numero: "CNT-00046",
    cliente: "Logistica Epsilon",
    valor: 41200.75,
    vencimento: new Date(2026, 5, 18),
    status: "ativo",
  },
  {
    id: "6",
    numero: "CNT-00047",
    cliente: "Construtora Zeta",
    valor: 67500,
    vencimento: new Date(2026, 6, 10),
    status: "ativo",
  },
]

const moedaBR = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
})

const statusCopy: Record<
  StatusContrato,
  { label: string; variant: "success" | "warning" | "neutral" }
> = {
  ativo: { label: "Ativo", variant: "success" },
  pausado: { label: "Pausado", variant: "warning" },
  encerrado: { label: "Encerrado", variant: "neutral" },
}

export default function ListTemplatePage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Contratos"
        subtitle="Gerencie todos os contratos ativos, pausados e encerrados."
        actions={
          <Button variant="primary">
            <RiAddLine className="mr-1.5 size-4" aria-hidden />
            Novo contrato
          </Button>
        }
      />

      <ContratosFilters />

      <div className="rounded border border-gray-200 bg-white dark:border-gray-800 dark:bg-gray-950">
        <TableRoot>
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell>Numero</TableHeaderCell>
                <TableHeaderCell>Cliente</TableHeaderCell>
                <TableHeaderCell className="text-right">Valor</TableHeaderCell>
                <TableHeaderCell>Vencimento</TableHeaderCell>
                <TableHeaderCell>Status</TableHeaderCell>
                <TableHeaderCell className="w-12 text-right">
                  <span className="sr-only">Acoes</span>
                </TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {contratos.map((contrato) => {
                const status = statusCopy[contrato.status]
                return (
                  <TableRow key={contrato.id}>
                    <TableCell className="font-medium text-gray-900 dark:text-gray-50">
                      {contrato.numero}
                    </TableCell>
                    <TableCell>{contrato.cliente}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {moedaBR.format(contrato.valor)}
                    </TableCell>
                    <TableCell>
                      {format(contrato.vencimento, "dd 'de' MMM 'de' yyyy", {
                        locale: ptBR,
                      })}
                    </TableCell>
                    <TableCell>
                      <Badge variant={status.variant}>{status.label}</Badge>
                    </TableCell>
                    <TableCell className="text-right">
                      <ContratosRowActions numero={contrato.numero} />
                    </TableCell>
                  </TableRow>
                )
              })}
            </TableBody>
          </Table>
        </TableRoot>

        <div className="flex flex-col items-start justify-between gap-3 border-t border-gray-200 px-4 py-3 text-sm dark:border-gray-800 sm:flex-row sm:items-center">
          <p className="text-gray-500 dark:text-gray-400">
            Mostrando 1-6 de 48
          </p>
          <div className="flex items-center gap-2">
            <Button variant="secondary" disabled>
              <RiArrowLeftLine className="mr-1.5 size-4" aria-hidden />
              Anterior
            </Button>
            <Button variant="secondary">
              Proxima
              <RiArrowRightLine className="ml-1.5 size-4" aria-hidden />
            </Button>
          </div>
        </div>
      </div>
    </div>
  )
}
