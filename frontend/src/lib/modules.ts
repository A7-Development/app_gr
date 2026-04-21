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

// Paleta A7 Credit v0.2.0 (migracao blue → slate).
// `blue` saiu da rotacao default; `indigo` entrou como 8a cor.
export type ModuleColor =
  | "slate"
  | "sky"
  | "teal"
  | "emerald"
  | "amber"
  | "rose"
  | "violet"
  | "indigo"

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

// Mapeia cor do modulo para as classes Tailwind do avatar (bg + texto branco).
// Usa tokens da paleta A7 Credit do chartUtils.ts (tambem validados pelo CLAUDE.md §4).
export const MODULE_AVATAR_COLORS: Record<ModuleColor, string> = {
  slate: "bg-slate-700 dark:bg-slate-600",
  sky: "bg-sky-600 dark:bg-sky-500",
  teal: "bg-teal-600 dark:bg-teal-500",
  emerald: "bg-emerald-600 dark:bg-emerald-500",
  amber: "bg-amber-600 dark:bg-amber-500",
  rose: "bg-rose-600 dark:bg-rose-500",
  violet: "bg-violet-600 dark:bg-violet-500",
  indigo: "bg-indigo-600 dark:bg-indigo-500",
}

export const MODULES: ModuleDefinition[] = [
  {
    id: "bi",
    name: "BI",
    initials: "BI",
    icon: RiPieChart2Line,
    color: "slate",
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
    color: "sky",
    enabled: false,
    permission: "none",
    basePath: "/cadastros",
    sections: [{ name: "Em breve", href: "#", enabled: false }],
  },
  {
    id: "operacoes",
    name: "Operacoes",
    initials: "OP",
    icon: RiExchangeFundsLine,
    color: "teal",
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
    color: "emerald",
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
    color: "rose",
    enabled: false,
    permission: "none",
    basePath: "/integracoes",
    sections: [{ name: "Em breve", href: "#", enabled: false }],
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
    color: "indigo",
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
