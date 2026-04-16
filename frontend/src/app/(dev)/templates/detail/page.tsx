import { format } from "date-fns"
import { ptBR } from "date-fns/locale"

import { PageHeader } from "@/components/app/PageHeader"
import { Badge } from "@/components/tremor/Badge"
import { Card } from "@/components/tremor/Card"
import { Divider } from "@/components/tremor/Divider"
import { Label } from "@/components/tremor/Label"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeaderCell,
  TableRoot,
  TableRow,
} from "@/components/tremor/Table"
import { DetailActions } from "./_components/DetailActions"
import { FaturamentoChart } from "./_components/FaturamentoChart"

const moedaBR = new Intl.NumberFormat("pt-BR", {
  style: "currency",
  currency: "BRL",
})

const resumo = [
  { label: "Cliente", valor: "Industria Alfa Ltda." },
  { label: "CNPJ", valor: "12.345.678/0001-90" },
  { label: "Valor mensal", valor: moedaBR.format(25800) },
  {
    label: "Data de inicio",
    valor: format(new Date(2025, 10, 1), "dd 'de' MMMM 'de' yyyy", {
      locale: ptBR,
    }),
  },
  {
    label: "Vencimento",
    valor: format(new Date(2026, 10, 1), "dd 'de' MMMM 'de' yyyy", {
      locale: ptBR,
    }),
  },
  { label: "Responsavel", valor: "Ricardo Pimenta" },
]

const faturamento = [
  { mes: "Mai/25", Receita: 24500 },
  { mes: "Jun/25", Receita: 24800 },
  { mes: "Jul/25", Receita: 25100 },
  { mes: "Ago/25", Receita: 25100 },
  { mes: "Set/25", Receita: 25400 },
  { mes: "Out/25", Receita: 25400 },
  { mes: "Nov/25", Receita: 25800 },
  { mes: "Dez/25", Receita: 25800 },
  { mes: "Jan/26", Receita: 25800 },
  { mes: "Fev/26", Receita: 26200 },
  { mes: "Mar/26", Receita: 26200 },
  { mes: "Abr/26", Receita: 26200 },
]

type Item = {
  id: string
  descricao: string
  quantidade: number
  unitario: number
}

const itens: Item[] = [
  { id: "1", descricao: "Mensalidade plano Essencial", quantidade: 1, unitario: 18500 },
  { id: "2", descricao: "Modulo de relatorios avancados", quantidade: 1, unitario: 3500 },
  { id: "3", descricao: "Suporte dedicado 8x5", quantidade: 1, unitario: 2800 },
  { id: "4", descricao: "Licencas de usuario adicionais", quantidade: 5, unitario: 200 },
]

export default function DetailTemplatePage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        breadcrumbs={[
          { label: "Contratos", href: "/templates/list" },
          { label: "CNT-00042" },
        ]}
        title="Contrato CNT-00042"
        subtitle="Visao detalhada do contrato e suas condicoes vigentes."
        actions={
          <>
            <Badge variant="success">Ativo</Badge>
            <DetailActions />
          </>
        }
      />

      <Card className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
            Resumo
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Informacoes principais do contrato.
          </p>
        </div>

        <Divider />

        <dl className="grid grid-cols-1 gap-x-6 gap-y-4 md:grid-cols-2">
          {resumo.map((item) => (
            <div key={item.label} className="flex flex-col gap-1">
              <Label>{item.label}</Label>
              <span className="text-sm font-medium text-gray-900 dark:text-gray-50">
                {item.valor}
              </span>
            </div>
          ))}
        </dl>
      </Card>

      <Card className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
            Evolucao de faturamento
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Receita do contrato nos ultimos 12 meses.
          </p>
        </div>

        <FaturamentoChart data={faturamento} />
      </Card>

      <Card className="flex flex-col gap-4">
        <div className="flex flex-col gap-1">
          <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
            Itens do contrato
          </h2>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Composicao mensal do valor cobrado.
          </p>
        </div>

        <TableRoot>
          <Table>
            <TableHead>
              <TableRow>
                <TableHeaderCell>Descricao</TableHeaderCell>
                <TableHeaderCell className="text-right">Qtd.</TableHeaderCell>
                <TableHeaderCell className="text-right">
                  Valor unitario
                </TableHeaderCell>
                <TableHeaderCell className="text-right">Subtotal</TableHeaderCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {itens.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="font-medium text-gray-900 dark:text-gray-50">
                    {item.descricao}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {item.quantidade}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {moedaBR.format(item.unitario)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {moedaBR.format(item.quantidade * item.unitario)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableRoot>
      </Card>
    </div>
  )
}
