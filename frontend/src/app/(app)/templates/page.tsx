import {
  RiDashboardLine,
  RiFileListLine,
  RiFileTextLine,
  RiEditBoxLine,
  RiArrowRightLine,
  RiStackLine,
  type RemixiconComponentType,
} from "@remixicon/react"

import { PageHeader } from "@/components/app/PageHeader"
import { Card } from "@/components/tremor/Card"
import { Button } from "@/components/tremor/Button"

type TemplateEntry = {
  href: string
  title: string
  description: string
  icon: RemixiconComponentType
}

const templates: TemplateEntry[] = [
  {
    href: "/templates/list",
    title: "ListTemplate",
    description:
      "Pagina de listagem com busca, filtros, tabela e paginacao. Base para telas index de dominios.",
    icon: RiFileListLine,
  },
  {
    href: "/templates/form",
    title: "FormTemplate",
    description:
      "Formulario de criar/editar registro com react-hook-form, validacao zod e feedback via toast.",
    icon: RiEditBoxLine,
  },
  {
    href: "/templates/detail",
    title: "DetailTemplate",
    description:
      "Pagina de detalhe de um registro unico, com resumo, chart de historico e itens relacionados.",
    icon: RiFileTextLine,
  },
  {
    href: "/templates/dashboard",
    title: "DashboardTemplate",
    description:
      "Painel gerencial com KPIs, filtros globais, charts e rankings de topo.",
    icon: RiDashboardLine,
  },
  {
    href: "/templates/wizard",
    title: "WizardTemplate",
    description:
      "Fluxo multi-step com Stepper e navegacao entre etapas. Ideal para importacoes e onboarding.",
    icon: RiStackLine,
  },
]

export default function TemplatesIndexPage() {
  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title="Templates canonicos"
        subtitle="Pontos de partida aprovados pelo design system. Todo novo fluxo deve nascer de um destes."
      />

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {templates.map((template) => {
          const Icon = template.icon
          return (
            <Card key={template.href} className="flex flex-col gap-4">
              <div className="flex size-10 items-center justify-center rounded bg-gray-100 text-gray-700 dark:bg-gray-900 dark:text-gray-300">
                <Icon className="size-5" aria-hidden />
              </div>
              <div className="flex flex-col gap-1">
                <h2 className="text-base font-semibold text-gray-900 dark:text-gray-50">
                  {template.title}
                </h2>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  {template.description}
                </p>
              </div>
              <div className="mt-auto">
                <Button asChild variant="secondary" className="w-full">
                  <a href={template.href}>
                    Abrir template
                    <RiArrowRightLine
                      className="ml-1.5 size-4"
                      aria-hidden
                    />
                  </a>
                </Button>
              </div>
            </Card>
          )
        })}
      </div>
    </div>
  )
}
