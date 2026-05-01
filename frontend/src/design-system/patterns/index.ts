// src/design-system/patterns/index.ts
// Barrel export for design system patterns.
//
// Patterns sao copy-paste-edit (CLAUDE.md §7). Cada arquivo e uma `page.tsx`
// completa: container externo, PageHeader, filtros, conteudo, drawers,
// dialogs, URL state. Quando criar pagina nova, escolha o pattern aplicavel
// (decision tree em CLAUDE.md §7) e copie pra `app/<dominio>/<rota>/page.tsx`.

export { DashboardOperacional } from "./DashboardOperacional"
export { DashboardBiPadrao } from "./DashboardBiPadrao"
export { ListagemComDrilldown } from "./ListagemComDrilldown"
export { ListagemCrudInline } from "./ListagemCrudInline"
export { ListagemCrudExpand } from "./ListagemCrudExpand"
export { ListagemCrudCards, EspacoCard, type EspacoRow } from "./ListagemCrudCards"
