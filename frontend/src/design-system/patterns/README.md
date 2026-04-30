# Patterns

Templates copy-paste-edit para nascimento de paginas. **Nao sao componentes black-box** -- sao starting points que voce copia, troca os tipos de dominio, e adapta.

## Por que copy-paste-edit?

Componentes pequenos sao reutilizaveis. Layouts de pagina, nao -- cada pagina BI tem necessidades especificas que nao cabem em props de um componente generico. Patterns evitam dois problemas:

1. **Black-box generico** -- props infladas para cobrir todos os casos, ninguem entende.
2. **Pagina do zero a cada vez** -- divergencia visual e perda de canon.

Solucao: voce copia o pattern, le os comentarios `HOW TO ADAPT:` no topo, e modifica. As 7 zonas e a paleta sao identicas; o conteudo e seu.

## Patterns disponiveis

| Pattern | Use para | Composicao |
|---|---|---|
| **DashboardOperacional** | `/bi/operacoes`, `/bi/carteira`, `/bi/rentabilidade`, `/bi/fluxo-caixa` | PageHeader (Z2) + FilterBar (Z1) + KpiStrip 4 KPIs (Z3) + Grid 2×2 EChartsCards (Z6) + DataTable de atividade recente |
| **DashboardBiPadrao** | Pages do BI Framework completo (handoff bi-padrao 2026-04-26) | 5 zonas: Z1 PageHeader + Z2 TabNavigation L3 + Z3 FilterBar sticky + Z4 conteudo (InsightBar + KpiStrip + grid + DataTable) + Z5 ProvenanceFooter + AIPanel violeta |
| **ListagemComDrilldown** | Cessoes, Cedentes, Sacados, Cobranca, Reconciliacao, Eventos | PageHeader (Z2) + FilterBar (Z1) + DataTable + DrillDownSheet (URL-synced via `?selected=ID`) |
| **ListagemCrudInline** | Cadastros administrativos pequenos a medios (~5-200 rows) com criar/editar/excluir inline. Ex.: credenciais de provedor, usuarios do tenant, etiquetas, templates, regras de classificacao. | PageHeader (com botao "+ Novo") + Card { `<FilterSearch>` + `<SegmentSwitch>` + contador `X de Y` + DataTable } + DrillDownSheet (criar via `?action=new`) + DrillDownSheet (editar via `?selected=ID`) + Dialog destrutivo (state local). Filtros client-side ate ~200 rows; acima disso, escala documentada no header do pattern. |

## Como usar

### Opcao A -- importar e renderizar (rapido pra preview)

```tsx
import { DashboardOperacional } from "@/design-system/patterns"

export default function CarteiraPage() {
  return <DashboardOperacional />
}
```

Funciona com dados de exemplo. Util para validar UI antes de plugar dados reais.

### Opcao B -- copy-paste-edit (recomendado para producao)

1. Abra o arquivo do pattern (`DashboardOperacional.tsx` ou `ListagemComDrilldown.tsx`)
2. Leia os comentarios `HOW TO ADAPT:` no topo
3. Copie todo o conteudo para sua nova pagina
4. Troque o tipo do dominio (ex.: `CessaoRow` -> `ContratoRow`)
5. Troque os mocks por queries reais (`useQuery` / SWR)
6. Adapte os campos de KPI/columns/filtros

## Quando NAO usar pattern

- Pagina precisa de Z6 totalmente customizado (ex.: `/bi/benchmark` com 4 abas e dados externos CVM) -- componha manualmente
- Pagina tem zonas extras nao canonicas (rare -- discuta antes)
- Pagina e fluxo wizard multi-step -- use componente `Stepper` direto, sem pattern

## Como escolher entre `ListagemComDrilldown` e `ListagemCrudInline`

| Pergunta | ListagemComDrilldown | ListagemCrudInline |
|---|---|---|
| Quem produz os dados? | Sistema (ETL, calculo) | Operador humano (cadastra na UI) |
| Operacoes principais | Ler / aprofundar / explorar contexto | Criar / editar / excluir registros |
| O que abre no DrillDownSheet | Painel rico: PropertyList, Tabs, Timeline, LinkedObjects | Form de cadastro / edicao |
| Volume tipico | Centenas ou milhares de rows | Dezenas (~5-50) |
| Dialog destrutivo | Geralmente nao | Sim (excluir registro) |
| Exemplos | Cessoes, Eventos, Cobranca | Credenciais, Usuarios, Etiquetas, Templates |

## Referencias

- **CLAUDE.md §7** -- regra dos patterns canonicos
- **CLAUDE.md §19** -- 7 zonas BI
- **docs/BI_FRAMEWORK.md** -- detalhes de cada zona, tabelas de decisao, exemplos
- **`HOW TO ADAPT:`** -- comentarios no topo de cada arquivo .tsx deste folder
