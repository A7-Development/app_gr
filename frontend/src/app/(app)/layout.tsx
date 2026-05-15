import { AppSidebar, SidebarTrigger } from "@/design-system/components/Sidebar"
import { AuthGuard } from "@/design-system/components/AuthGuard"
import { HeaderBreadcrumbs } from "@/design-system/components/Breadcrumbs"
import { SyncHealthBadge } from "@/design-system/components/SyncHealthBadge"
import { CommandPaletteProvider } from "@/design-system/components/CommandPalette"

export default function AppShellLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <AuthGuard>
      <CommandPaletteProvider>
        <div className="flex h-screen">
          {/* badgeCounts: chave = href da secao. TODO: substituir por contagens
              reais vindas do backend (ex.: queue de aprovacoes em /bi/operacoes). */}
          <AppSidebar
            badgeCounts={{
              "/bi/operacoes": 12,
              "/bi/carteira": 3,
            }}
          />
          {/* min-w-0 e essencial: este div e item flex e tem min-width: auto
              por default, o que impede encolhimento abaixo do min-content do
              conteudo. Quando o AIPanel (in-layout, shrink-0, 272px) abre numa
              pagina BI, a soma sidebar + coluna + painel ultrapassa 100vw e
              vaza pro body sem essa barreira. */}
          <div className="flex w-full min-w-0 flex-col">
            <header className="sticky top-0 z-10 flex h-12 shrink-0 items-center gap-2 border-b border-gray-200 bg-white px-4 dark:border-gray-800 dark:bg-gray-950">
              <SidebarTrigger className="-ml-1" />
              <div className="mr-2 h-4 w-px bg-gray-200 dark:bg-gray-800" />
              <HeaderBreadcrumbs />
              <div className="ml-auto">
                <SyncHealthBadge />
              </div>
            </header>
            {/* overflow-x-hidden no main: barreira final contra qualquer
                vazamento horizontal de pagina interna. overflow-y-auto para
                que o scroll vertical aconteca dentro do main, nao no body. */}
            <main className="flex-1 overflow-y-auto overflow-x-hidden">{children}</main>
          </div>
        </div>
      </CommandPaletteProvider>
    </AuthGuard>
  )
}
