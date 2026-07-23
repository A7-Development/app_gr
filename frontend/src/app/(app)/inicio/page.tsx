import { RiCheckboxCircleFill } from "@remixicon/react"

// Home de atalhos por modulo — deixou de ser a landing quando `/` passou a
// redirecionar para /copiloto (spec copiloto-mcp §8.1, virada da Fase 5).
// A navegacao por modulo vive na sidebar; esta pagina e opcional.
export default function Inicio() {
  return (
    <div className="flex min-h-[calc(100svh-4rem)] flex-col items-center justify-center gap-6 p-8">
      <div className="flex items-center gap-3 rounded border border-gray-200 bg-white px-6 py-4 shadow-sm dark:border-gray-800 dark:bg-gray-900">
        <RiCheckboxCircleFill
          className="size-6 text-emerald-500"
          aria-hidden="true"
        />
        <div>
          <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-50">
            Bem-vindo ao Strata
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Use a barra lateral para navegar pelos modulos — ou converse com o
            Strata AI na tela inicial.
          </p>
        </div>
      </div>
    </div>
  )
}
