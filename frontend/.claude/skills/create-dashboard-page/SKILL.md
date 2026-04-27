---
name: create-dashboard-page
description: Cria uma pagina de dashboard com KPIs, charts e tabelas resumidas usando Tremor Raw. Use quando o usuario pedir "dashboard de X", "painel de Y", "visao gerencial de Z".
---

# create-dashboard-page

Pagina orientada a **analise**: KPIs, charts, filtros temporais, tabelas resumo.

## Pre-condicao obrigatoria

Ler `CLAUDE.md` na raiz. Regras nao-negociaveis.

> **🔓 Modo Iteracao de Design ativo** (ver banner em `CLAUDE.md` raiz):
> Durante este periodo, ao criar dashboard novo:
> - Valores arbitrarios de Tailwind aceitaveis (`text-[Npx]`, `rounded-[Npx]`, `gap-[Npx]`).
> - Hex literals e `rgba(...)` aceitaveis em codigo de componente/surface.
> - Inline styles `style={{...}}` aceitaveis para efeitos especificos do handoff.
> - Cores Tailwind fora da paleta canonica §4 aceitaveis quando do handoff.
> - **Continuam invioaveis**: §2 stack, §3 6 camadas, §11.6 hierarquia 3 niveis, idioma pt-BR.
> - Header de dashboard usa `<DashboardHeaderActions>` no slot `actions` do `<PageHeader>` (CLAUDE.md §7).
> Lock-down volta com promocao a tokens nomeados.

## Informacoes a coletar

1. **Contexto do dashboard** — qual area/dominio?
2. **KPIs** — quais metricas no topo? (valor atual + delta vs periodo anterior).
3. **Charts** — tipo (area, bar, line, donut, bar list, tracker, progress circle)? eixo X / Y / categorias?
4. **Filtros globais** — periodo, unidade de negocio, categoria?
5. **Tabelas auxiliares** — top N, ranking, alertas?
6. **Frequencia de atualizacao** — tempo real? cache de 5min?

## Estrutura a produzir

```
src/app/(app)/<dominio>/dashboard/page.tsx
src/app/(app)/<dominio>/dashboard/_components/
    KpiCards.tsx                                <- grid de KPIs
    <Nome>Chart.tsx                             <- por chart
    PeriodFilter.tsx                            <- filtro global de periodo
```

## Regras de montagem

### Filtro global

Barra no topo (abaixo do `PageHeader`). `DatePicker` em modo range + `Select` de granularidade (Dia/Semana/Mes/Ano). Estado propagado via URL search params (`useSearchParams`) para ser compartilhavel/deep-linkavel.

### KPIs

- Grid responsivo: `grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4`.
- Cada KPI e um `Card` do Tremor contendo:
  - Label pequeno (pt-BR, caixa baixa).
  - Valor grande (heranca de typografia Tremor).
  - Delta com `<Badge>` colorido conforme sinal: `success` (positivo quando bom), `error` (negativo quando ruim). Incluir icone de seta `RiArrowUpLine` / `RiArrowDownLine`.
  - Sparkline opcional com `SparkAreaChart` de `@/components/charts/SparkChart`.

### Charts

- **Area/Line/Bar** para series temporais.
- **Donut** para composicao (parte/todo).
- **BarList** para rankings top-N.
- **Tracker** para status binario ao longo do tempo (ex.: disponibilidade).
- **ProgressCircle** para percentual de meta.
- Cores: sempre de `chartColors` (`blue`, `emerald`, `violet`, `amber`, etc).
- Titulo do chart: h3 com classe herdada do Tremor. Subtitulo opcional em `text-sm text-gray-500 dark:text-gray-400`.

### Tabelas resumo

- Quando usar: top-N, lista de alertas, ranking.
- Sempre `Table` do Tremor. Linhas clickaveis levam ao detalhe.

### Formatacao

- Moeda: `Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })`.
- Percentual: `toLocaleString('pt-BR', { style: 'percent', maximumFractionDigits: 1 })`.
- Datas: `date-fns` com `locale: ptBR`.
- **Nunca** formatacao em ingles.

### Responsividade

Dashboard deve funcionar em tablet (>=768px). Charts tem `className="h-72"` ou similar (altura fixa). Em mobile (<768px), KPIs empilham, charts mantem altura, filtros viram drawer.

## Proibicoes duras

- Zero chart de biblioteca externa (Chart.js, Nivo, etc).
- Zero cor arbitraria.
- Zero valor fora de pt-BR.
- Zero uso de `<canvas>` cru.

## Checkpoint final

`npx tsc --noEmit && npm run lint && npm run build`.
