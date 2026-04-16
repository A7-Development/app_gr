import { RiCheckboxCircleFill } from "@remixicon/react"

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 p-8">
      <div className="flex items-center gap-3 rounded-lg border border-gray-200 bg-white px-6 py-4 shadow-sm dark:border-gray-800 dark:bg-gray-900">
        <RiCheckboxCircleFill className="size-6 text-emerald-500" />
        <div>
          <h1 className="text-lg font-semibold text-gray-900 dark:text-gray-50">
            App GR -- Tremor Raw configurado
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Etapa 1: Fundacao em andamento
          </p>
        </div>
      </div>
    </main>
  )
}
