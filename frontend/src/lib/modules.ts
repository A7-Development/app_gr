// Registry unico dos modulos do App GR (frontend).
// Espelho de `app/core/enums.py::Module` do backend.
// A ordem canonica aqui e a mesma da sidebar — mexer aqui mexe na UI.

import {
  RiBuilding2Line,
  RiContactsBookLine,
  RiExchangeFundsLine,
  RiFlaskLine,
  RiPieChart2Line,
  RiSettings3Line,
  RiShieldCheckLine,
  RiStackLine,
  type RemixiconComponentType,
} from "@remixicon/react"

export type ModuleId =
  | "bi"
  | "cadastros"
  | "operacoes"
  | "controladoria"
  | "risco"
  | "integracoes"
  | "laboratorio"
  | "admin"

export type ModuleSection = {
  name: string
  href: string
  enabled: boolean
}

// Paleta de avatar de modulo v0.4.0 (handoff A7 Credit v2, 2026-04-24).
// Cada modulo tem cor de identidade fixa — nao iterativa. Difere da paleta de
// chart series (essa segue `chartColors` em @/lib/chartUtils). Ver CLAUDE.md §11.6.
export type ModuleColor =
  | "gray"
  | "blue"
  | "emerald"
  | "teal"
  | "amber"
  | "red"
  | "violet"
  | "slate"

export type ModuleDefinition = {
  id: ModuleId
  name: string
  initials: string
  icon: RemixiconComponentType
  // Cor do avatar — mapeia 1:1 com a paleta canonica do chartUtils.
  color: ModuleColor
  // O tenant contratou o modulo? (MVP: hardcoded; no futuro vem de /auth/me)
  enabled: boolean
  // Permissao do usuario no modulo. MVP: assumido "admin" para BI, "none" para demais.
  permission: "none" | "read" | "write" | "admin"
  // Rota base — usada para detectar modulo ativo pelo pathname.
  basePath: string
  sections: ModuleSection[]
}

// Mapeia cor do modulo para classes Tailwind do avatar (bg + texto branco).
// Cores alinhadas ao handoff v2: BI ancora em gray-800 (estilo Linear/Notion),
// demais modulos em tons sobrios. Exceptional — sao cores de identidade, nao
// de status (rose nao = erro, red aqui nao = destrutivo).
export const MODULE_AVATAR_COLORS: Record<ModuleColor, string> = {
  gray: "bg-gray-800 dark:bg-gray-700",
  blue: "bg-blue-500 dark:bg-blue-500",
  emerald: "bg-emerald-500 dark:bg-emerald-500",
  teal: "bg-teal-500 dark:bg-teal-500",
  amber: "bg-amber-500 dark:bg-amber-500",
  red: "bg-red-600 dark:bg-red-500",
  violet: "bg-violet-500 dark:bg-violet-500",
  slate: "bg-slate-600 dark:bg-slate-500",
}

export const MODULES: ModuleDefinition[] = [
  {
    id: "bi",
    name: "BI",
    initials: "BI",
    icon: RiPieChart2Line,
    color: "gray",
    enabled: true,
    permission: "admin",
    basePath: "/bi",
    sections: [
      { name: "Operacoes", href: "/bi/operacoes", enabled: true },
      { name: "Carteira", href: "/bi/carteira", enabled: false },
      { name: "Comportamento", href: "/bi/comportamento", enabled: false },
      { name: "Receitas", href: "/bi/receitas", enabled: false },
      { name: "Fluxo de caixa", href: "/bi/fluxo-caixa", enabled: false },
      { name: "DRE", href: "/bi/dre", enabled: false },
      // Benchmark — dados publicos CVM FIDC via postgres_fdw.
      // Ver docs/integracao-cvm-fidc.md e CLAUDE.md §13.1.
      { name: "Benchmark", href: "/bi/benchmark", enabled: true },
    ],
  },
  {
    id: "cadastros",
    name: "Cadastros",
    initials: "CA",
    icon: RiContactsBookLine,
    color: "blue",
    enabled: true,
    permission: "admin",
    basePath: "/cadastros",
    sections: [
      {
        name: "Unidades administrativas",
        href: "/cadastros/unidades-administrativas",
        enabled: true,
      },
    ],
  },
  {
    id: "operacoes",
    name: "Operacoes",
    initials: "OP",
    icon: RiExchangeFundsLine,
    color: "emerald",
    enabled: false,
    permission: "none",
    basePath: "/operacoes",
    sections: [{ name: "Em breve", href: "#", enabled: false }],
  },
  {
    id: "controladoria",
    name: "Controladoria",
    initials: "CO",
    icon: RiBuilding2Line,
    color: "teal",
    enabled: false,
    permission: "none",
    basePath: "/controladoria",
    sections: [{ name: "Em breve", href: "#", enabled: false }],
  },
  {
    id: "risco",
    name: "Risco",
    initials: "RI",
    icon: RiShieldCheckLine,
    color: "amber",
    enabled: false,
    permission: "none",
    basePath: "/risco",
    sections: [{ name: "Em breve", href: "#", enabled: false }],
  },
  {
    id: "integracoes",
    name: "Integracoes",
    initials: "IN",
    icon: RiStackLine,
    color: "red",
    enabled: true,
    permission: "admin",
    basePath: "/integracoes",
    sections: [
      { name: "Catalogo", href: "/integracoes/catalogo", enabled: true },
      { name: "Sync", href: "/integracoes/sync", enabled: true },
    ],
  },
  {
    id: "laboratorio",
    name: "Laboratorio",
    initials: "LA",
    icon: RiFlaskLine,
    color: "violet",
    enabled: false,
    permission: "none",
    basePath: "/laboratorio",
    sections: [{ name: "Em breve", href: "#", enabled: false }],
  },
  {
    id: "admin",
    name: "Admin",
    initials: "AD",
    icon: RiSettings3Line,
    color: "slate",
    enabled: false,
    permission: "none",
    basePath: "/admin",
    sections: [{ name: "Em breve", href: "#", enabled: false }],
  },
]

export const PERMISSION_LABEL: Record<ModuleDefinition["permission"], string> = {
  none: "Sem acesso",
  read: "Leitor",
  write: "Editor",
  admin: "Admin",
}

// Retorna o modulo ativo inferido do pathname.
// Fallback: primeiro modulo habilitado (BI no MVP).
export function getActiveModule(pathname: string): ModuleDefinition {
  const match = MODULES.find(
    (m) => pathname === m.basePath || pathname.startsWith(`${m.basePath}/`),
  )
  if (match) return match
  const firstEnabled = MODULES.find((m) => m.enabled)
  return firstEnabled ?? MODULES[0]
}

// Modulos visiveis no dropdown = enabled pelo tenant + com permissao >= read.
export function getVisibleModules(): ModuleDefinition[] {
  return MODULES.filter((m) => m.enabled && m.permission !== "none")
}
