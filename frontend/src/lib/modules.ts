// Registry unico dos modulos do App GR (frontend).
// Espelho de `app/core/enums.py::Module` do backend.
// A ordem canonica aqui e a mesma da sidebar — mexer aqui mexe na UI.

import {
  RiBarChartGroupedLine,
  RiBookOpenLine,
  RiBuilding2Line,
  RiBuilding4Line,
  RiCheckDoubleLine,
  RiCheckboxCircleLine,
  RiContactsBookLine,
  RiCpuLine,
  RiDashboard3Line,
  RiDatabase2Line,
  RiExchangeFundsLine,
  RiFileChartLine,
  RiFileSearchLine,
  RiFileTextLine,
  RiFlaskLine,
  RiFlowChart,
  RiFolderUserLine,
  RiHandCoinLine,
  RiHistoryLine,
  RiKey2Line,
  RiLightbulbLine,
  RiLineChartLine,
  RiPieChart2Line,
  RiPulseLine,
  RiRobot2Line,
  RiSettings3Line,
  RiShieldCheckLine,
  RiSignalTowerLine,
  RiStackLine,
  RiToolsLine,
  RiUserLine,
  RiUserStarLine,
  RiWallet3Line,
  type RemixiconComponentType,
} from "@remixicon/react"

export type ModuleId =
  | "bi"
  | "cadastros"
  | "operacoes"
  | "credito"
  | "controladoria"
  | "risco"
  | "integracoes"
  | "laboratorio"
  | "admin"

export type ModuleSection = {
  name: string
  // Rota de destino quando o item e clicado. Quando `children` esta definido,
  // o parent e expand-only: `href` continua sendo usado APENAS como prefixo
  // pra detectar quando algum filho esta ativo (auto-expand). Parent nao
  // navega quando clicado. CLAUDE.md §11.6.
  href: string
  enabled: boolean
  // Icone proprio da secao. Fallback: icone do modulo (CLAUDE.md §11.6).
  icon?: RemixiconComponentType
  // Caption tipografico que agrupa visualmente itens contiguos com o mesmo
  // valor (ex.: "OPERACAO", "FINANCEIRO"). Nao e grupo colapsavel —
  // apenas separador visual. Permitido por CLAUDE.md §11.6.
  groupLabel?: string
  // Filhos aninhados (1 nivel max). Quando definido, item vira parent
  // expand-only: nao navega, so abre/fecha. Permitido por CLAUDE.md §11.6.
  children?: ModuleSection[]
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
  indigo: "bg-indigo-500 dark:bg-indigo-500",
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
      // IA reorganizada 2026-05-22: flat por pergunta de negocio. Cada parent
      // ganha submenus expansiveis conforme as paginas forem nascendo. Itens
      // sem pagina ficam enabled=false como placeholder visual. CLAUDE.md §11.6.
      { name: "Visão geral", href: "/bi", enabled: true, icon: RiDashboard3Line },
      // Originacao (ex-Operacoes) — VOP, ritmo, mix. Parent expand-only.
      // URLs dos filhos mantidas (/bi/operacoes2/3/4) ate rename pra /bi/originacao/*.
      {
        name: "Originação",
        href: "#originacao",
        enabled: true,
        icon: RiExchangeFundsLine,
        children: [
          { name: "Mês corrente · antigo", href: "/bi/operacoes2", enabled: true },
          { name: "Mês corrente · novo", href: "/bi/operacoes3", enabled: true },
          { name: "Mês corrente · operações", href: "/bi/operacoes4", enabled: true },
          { name: "Drill por dimensão", href: "/bi/operacoes5", enabled: true },
        ],
      },
      { name: "Carteira", href: "/bi/carteira", enabled: false, icon: RiWallet3Line },
      { name: "Liquidações", href: "/bi/liquidacoes", enabled: false, icon: RiHandCoinLine },
      { name: "Inadimplência", href: "/bi/inadimplencia", enabled: false, icon: RiPulseLine },
      { name: "Concentração", href: "/bi/concentracao", enabled: true, icon: RiBarChartGroupedLine },
      { name: "Rentabilidade", href: "/bi/rentabilidade", enabled: false, icon: RiLineChartLine },
      // Benchmark — dados publicos CVM FIDC via postgres_fdw.
      // Ver docs/integracao-cvm-fidc.md e CLAUDE.md §13.1.
      {
        name: "Benchmark",
        href: "#benchmark",
        enabled: true,
        icon: RiBookOpenLine,
        children: [
          { name: "Panorama do mercado", href: "/bi/panorama", enabled: true },
          // Comparador de FIDCs por indicadores (cesta de 17, Opcao A da
          // reorganizacao do Benchmark — docs/cvm-fidc/indicadores-benchmarking.md).
          { name: "Comparador", href: "/bi/comparador", enabled: true },
          { name: "Benchmark", href: "/bi/benchmark", enabled: true },
          { name: "Benchmark2", href: "/bi/benchmark2", enabled: true },
        ],
      },
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
        icon: RiBuilding2Line,
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
    id: "credito",
    name: "Crédito",
    initials: "Cr",
    icon: RiHandCoinLine,
    color: "indigo",
    // Modulo de credito (id mantido como "credito" pra preservar URLs e
    // enums backend). Display "Crédito" (2026-06-18, Ricardo) — antes
    // "StrataFlow" (marca propria); voltou ao nome do dominio.
    enabled: true,
    permission: "admin",
    basePath: "/credito",
    sections: [
      {
        name: "Análises",
        href: "/credito/dossies",
        enabled: true,
        icon: RiFolderUserLine,
        groupLabel: "Execucao",
      },
      {
        name: "Nova análise",
        href: "/credito/dossies/novo",
        enabled: true,
        icon: RiHandCoinLine,
        groupLabel: "Execucao",
      },
      // Consultas avulsas a fontes externas (bureau/cartório/junta). Parent
      // expand-only (§11.6); cada consulta vira um submenu. Protestos é a 1ª.
      {
        name: "Consultas",
        href: "#consultas",
        enabled: true,
        icon: RiFileSearchLine,
        groupLabel: "Execucao",
        children: [
          {
            name: "Protestos",
            href: "/credito/consultas/protestos",
            enabled: true,
          },
          {
            name: "Protestos · Credor (SP)",
            href: "/credito/consultas/protestos-credor",
            enabled: true,
          },
        ],
      },
      {
        name: "Workflows",
        href: "/credito/workflows",
        enabled: true,
        icon: RiFlowChart,
        groupLabel: "Configuracao",
      },
      {
        name: "Checklist",
        href: "/credito/checklist",
        enabled: true,
        icon: RiCheckboxCircleLine,
        groupLabel: "Configuracao",
      },
      {
        name: "Templates",
        href: "/credito/templates",
        enabled: true,
        icon: RiFileTextLine,
        groupLabel: "Configuracao",
      },
      {
        name: "Agentes",
        href: "/credito/agentes",
        enabled: true,
        icon: RiRobot2Line,
        groupLabel: "Configuracao",
      },
    ],
  },
  {
    id: "controladoria",
    name: "Controladoria",
    initials: "CO",
    icon: RiBuilding2Line,
    color: "teal",
    enabled: true,
    permission: "admin",
    basePath: "/controladoria",
    sections: [
      // 7 parents expand-only (1 nivel de aninhamento, CLAUDE.md §11.6).
      // Reestruturado 2026-05-17 a partir do briefing "Pontos de Controle".
      // Parents nao navegam (NavParent so toggla expand). `href` do parent e
      // identificador semantico — nunca vira <Link>. Filhos nao tem `icon`
      // pois NavSubLink so renderiza nome (nav-items.tsx:231-247). Itens nao
      // implementados ficam enabled=false como placeholders.
      {
        name: "Patrimonio e Cotas",
        href: "#patrimonio-cotas",
        enabled: true,
        icon: RiPieChart2Line,
        children: [
          { name: "Variacao da Cota", href: "/controladoria/cota-sub", enabled: true },
          { name: "Evolucao Patrimonial", href: "/controladoria/evolucao-patrimonial", enabled: true },
          { name: "Gatilhos", href: "/controladoria/gatilhos", enabled: false },
        ],
      },
      {
        name: "Fechamento Mensal",
        href: "#fechamento-mensal",
        enabled: true,
        icon: RiFileChartLine,
        children: [
          { name: "Lamina do Fundo", href: "/controladoria/lamina", enabled: true },
        ],
      },
      {
        name: "Carteira",
        href: "#carteira",
        enabled: true,
        icon: RiWallet3Line,
        children: [
          { name: "Saldo e Composicao", href: "/controladoria/carteira", enabled: false },
          { name: "PDD", href: "/controladoria/pdd", enabled: false },
          // Placeholder — pagina removida 2026-06-07 (catalogo de relatorios
          // descontinuado). Item mantido como destino futuro, nao-clicavel.
          { name: "Fechamentos", href: "/controladoria/relatorios/padronizados", enabled: false },
        ],
      },
      {
        name: "Elegibilidade e Concentracao",
        href: "#elegibilidade",
        enabled: true,
        icon: RiBarChartGroupedLine,
        children: [
          { name: "Concentracoes", href: "/controladoria/concentracoes", enabled: false },
          { name: "Limites", href: "/controladoria/limites", enabled: false },
          { name: "Cessoes", href: "/controladoria/cessoes", enabled: false },
          { name: "Desconformidades", href: "/controladoria/desconformidades", enabled: false },
        ],
      },
      {
        name: "Liquidez e Cobranca",
        href: "#liquidez-cobranca",
        enabled: true,
        icon: RiHandCoinLine,
        children: [
          // Placeholder — pagina removida 2026-06-07. Item mantido como
          // destino futuro, nao-clicavel.
          { name: "Pagamento Diario", href: "/controladoria/pagamento-diario", enabled: false },
          { name: "Liquidez", href: "/controladoria/liquidez", enabled: false },
          { name: "Collection", href: "/controladoria/collection", enabled: false },
        ],
      },
      {
        name: "Receitas e Resultado",
        href: "#receitas-resultado",
        enabled: true,
        icon: RiFileChartLine,
        children: [
          { name: "Receitas", href: "/controladoria/receitas", enabled: true },
        ],
      },
      {
        name: "Contrapartes",
        href: "#contrapartes",
        enabled: true,
        icon: RiContactsBookLine,
        children: [
          { name: "Cedentes", href: "/controladoria/cedentes", enabled: false },
          { name: "Sacados", href: "/controladoria/sacados", enabled: false },
        ],
      },
      {
        name: "Conciliacoes",
        href: "#conciliacoes",
        enabled: true,
        icon: RiCheckDoubleLine,
        children: [
          { name: "Custodiante", href: "/controladoria/conciliacao/custodiante", enabled: false },
          { name: "Banco Cobrador", href: "/controladoria/conciliacao/banco-cobrador", enabled: true },
          // Placeholder — pagina removida 2026-06-07 (catalogo de relatorios
          // descontinuado). Item mantido como destino futuro, nao-clicavel.
          { name: "Espelho Adm", href: "/controladoria/relatorios/espelho", enabled: false },
        ],
      },
    ],
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
      // Fontes — listagem + drill por fonte (config, endpoints, cobertura,
      // contas, diagnostico). Rename de "Catalogo" em 2026-05-21 (PR 1).
      { name: "Fontes", href: "/integracoes/fontes", enabled: true, icon: RiStackLine },
      // Operacao — visao operacional cross-source. Parent expand-only
      // (CLAUDE.md §11.6 regra 2). `href` e prefixo de active-state, nao
      // navega quando clicado. Auto-expand quando filho casa com pathname.
      {
        name: "Operacao",
        href: "#operacao",
        enabled: true,
        icon: RiPulseLine,
        children: [
          // Status — antigo /sync. Agregado cross-source com filtros
          // (Todas/Configuradas/Habilitadas) — migrados pra SegmentSwitch em PR 2.
          { name: "Status", href: "/integracoes/operacao/status", enabled: true, icon: RiSignalTowerLine },
          // Historico — decision_log cross-source unificado (PR 4).
          { name: "Historico", href: "/integracoes/operacao/historico", enabled: true, icon: RiHistoryLine },
        ],
      },
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
    // MVP: hardcoded enabled+admin para o tenant mantenedor (a7-credit).
    // TODO Phase 2: derivar dinamicamente do `/auth/me` via campo
    // `tenant.is_system_maintainer`. Backend ja protege com
    // `require_system_maintainer` (HTTP 403), entao expor extra na UI nao vaza.
    enabled: true,
    permission: "admin",
    basePath: "/admin",
    sections: [
      {
        name: "Tenants",
        href: "/admin/tenants",
        enabled: true,
        icon: RiBuilding4Line,
        groupLabel: "Gestao",
      },
      {
        name: "Usuarios",
        href: "/admin/usuarios",
        enabled: true,
        icon: RiUserLine,
        groupLabel: "Gestao",
      },
      {
        name: "Provedores",
        href: "/admin/ia/providers",
        enabled: true,
        icon: RiKey2Line,
        groupLabel: "Inteligencia Artificial",
      },
      {
        name: "Assinaturas",
        href: "/admin/ia/subscriptions",
        enabled: false,
        icon: RiHandCoinLine,
        groupLabel: "Inteligencia Artificial",
      },
      {
        name: "Prompts",
        href: "/admin/ia/prompts",
        enabled: true,
        icon: RiBookOpenLine,
        groupLabel: "Inteligencia Artificial",
      },
      {
        name: "Personas",
        href: "/admin/ia/personas",
        enabled: true,
        icon: RiUserStarLine,
        groupLabel: "Inteligencia Artificial",
      },
      {
        name: "Expertises",
        href: "/admin/ia/expertises",
        enabled: true,
        icon: RiLightbulbLine,
        groupLabel: "Inteligencia Artificial",
      },
      {
        name: "Agentes",
        href: "/admin/ia/agents",
        enabled: true,
        icon: RiCpuLine,
        groupLabel: "Inteligencia Artificial",
      },
      {
        name: "Tools",
        href: "/admin/ia/tools",
        enabled: true,
        icon: RiToolsLine,
        groupLabel: "Inteligencia Artificial",
      },
      {
        name: "Uso",
        href: "/admin/ia/usage",
        enabled: false,
        icon: RiLineChartLine,
        groupLabel: "Inteligencia Artificial",
      },
      {
        name: "Provedores",
        href: "/admin/dados/provedores",
        enabled: true,
        icon: RiKey2Line,
        groupLabel: "Dados",
      },
      {
        name: "Catálogo",
        href: "/admin/dados/catalogo",
        enabled: true,
        icon: RiDatabase2Line,
        groupLabel: "Dados",
      },
      {
        name: "Contrato de campos",
        href: "/admin/dados/contratos",
        enabled: true,
        icon: RiStackLine,
        groupLabel: "Dados",
      },
    ],
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

// Rota de pouso do modulo — para onde navegar quando o user seleciona o modulo
// no ModuleSwitcher (ou em qualquer "entrar no modulo X"). Regra do CLAUDE.md
// §11.6 regra 2: o `href` de section parent (com `children`) e expand-only e
// NUNCA destino real. Quando o primeiro section enabled e um parent, descemos
// pro primeiro filho enabled. Fallback final: `module.basePath`.
export function getModuleLandingHref(module: ModuleDefinition): string {
  for (const section of module.sections) {
    if (!section.enabled) continue
    if (section.children && section.children.length > 0) {
      const firstChild = section.children.find((c) => c.enabled)
      if (firstChild) return firstChild.href
      continue
    }
    return section.href
  }
  return module.basePath
}
