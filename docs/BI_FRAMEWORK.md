# BI Framework — detalhe de implementação

Referência detalhada para §19 do CLAUDE.md. As 7 zonas e regras duras estão no CLAUDE.md; aqui vivem os detalhes de composição e criação.

## §19.1 Composição em componentes canônicos

| Zona | Componente | Observação |
|---|---|---|
| Z1 | `<FilterBar />` + `<FilterChip />` | FilterBar sticky top 0, z-10; box-shadow ao scrollar. FilterChip: `[ícone] label \| valor [chevron]`; active=blue quando valor != default. Para multi-select com pending state usar `<FilterPill />`. |
| Z2 | `<PageHeader />` (com `subtitle`) + `<AIButton />` | Botões secundários antes do AIButton (padrão: Compartilhar / Exportar); AIButton sempre último. |
| Z3 | `<KPIStrip>` contendo `<KPICard>` × 6 | Cada KPI: prop `intensity` (3 barrinhas: `tone` pos/neu/neg/info × `level` low/mid/high) à esquerda do valor + `<OriginDot />` no canto inferior. |
| Z4 | `<InsightBar>` contendo `<Insight />` × N | Max 3 insights visíveis; prop `tone` (violet=IA neutra / amber=atenção / blue=informativo) determina border-left 2px + cor do ícone. |
| Z5 | `TabNavigation` do Tremor (`tremor/TabNavigation`) | Já existe; active = border-bottom `blue-500`. |
| Z6 | `<HeroGrid>` (3fr 2fr) + `<VizCard>` | VizCard tem menu "⋯" canônico (ver §19.2 abaixo). |
| Z7 | `<ProvenanceFooter />` | Sem borda, grid 3 colunas (fonte / atualizado / SLA). |

## §19.2 Menu "⋯" canônico em cada VizCard

Todo `<VizCard>` expõe um menu idêntico, com 3 seções:

1. **Agrupar por** — Segmento / Região / Canal / Produto / Cedente (conforme o domínio)
2. **Recorte** — Toda a carteira / Top 10 / Top 20 / Segmento X / ...
3. **Tipo de visualização** — Barras / Linhas / Área / Tabela

Quando usuário aplica override via menu, o card mostra `<OverrideChip />` ("Top 10 × resetar") no card-head. Click no chip reseta override daquele card.

## §19.4 Ordem de criação dos primitivos (ao abrir página de BI nova)

Se o primitivo não existir, criar nesta ordem:

1. `AIButton` — variante `bg-gray-900 text-white` + ícone `text-violet-500`
2. `OriginDot` — 12×12 no canto do KPI/card, tooltip "Fonte: DW — atualizado X"
3. `KPICard` + `KPIStrip` — grid de 6, responsivo 3/2
4. `Insight` + `InsightBar` — linha horizontal, borda esquerda violeta
5. `ProvenanceFooter` — grid 3 colunas, sem borda
6. `VizCard` — card com menu "⋯" + OverrideChip
7. `AIDrawer` — drawer lateral com chat (pós-MVP se não há backend IA ainda)
