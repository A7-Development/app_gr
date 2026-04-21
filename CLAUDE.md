# App GR -- Regras do Projeto

> Sistema de inteligencia de dados para FIDC (pt-BR). Monorepo com `frontend/` (Next.js 14 + Tremor Raw — entregue) e `backend/` (FastAPI + PostgreSQL, multi-tenant — em construcao). Este arquivo governa o comportamento do Claude Code em todas as sessoes deste repositorio.
>
> **Palavras-chave do sistema:** multi-tenant, adapter pattern por fonte de dados, modelo canonico entity-centric, DNA de auditabilidade (proveniencia + explicabilidade + versionamento), laboratorio de teses em dados historicos.

---

## 1. Palavra de ordem: **padrao e consistencia visual**

O sistema usa **Tremor Raw** como **unico** design system. Qualquer desvio quebra a razao de existir do projeto. Regra dura:

> **Nada que nao esteja em `frontend/src/components/tremor/` ou `frontend/src/components/charts/` pode aparecer na UI.**

Nao existe excecao "so dessa vez". Se faltar um componente, voce:

1. Verifica se o Tremor Raw publica ele (https://tremor.so/docs).
2. Se sim: copia verbatim do docs oficial para `src/components/tremor/` e usa.
3. Se nao: compoe a partir dos primitivos existentes dentro de `src/components/app/` (camada de composicao — nunca "invencao").
4. Em ultimo caso extremo, abra a discussao antes de escrever codigo.

---

## 2. Stack obrigatoria (sem substituicoes)

| Area | Obrigatorio | Proibido |
|---|---|---|
| Framework | Next.js 14.2.x (App Router) | pages/ router, Remix, Vite |
| Design System | Tremor Raw | shadcn/ui, MUI, Chakra, Ant, Bootstrap, Mantine |
| Styling | Tailwind CSS v4 + tokens do Tremor | CSS-in-JS, styled-components, emotion, CSS modules |
| Utilitario de classes | `cx()` de `@/lib/utils` | `cn()`, `clsx()` direto, `classnames` |
| Variantes | `tailwind-variants` | `class-variance-authority`, objetos de variantes manuais |
| Icones | `@remixicon/react` (Ri*) | `lucide-react`, `react-icons`, `heroicons`, SVG ad-hoc |
| Fonte | `GeistSans` | Inter, Roboto, Arial, qualquer outra |
| Charts (core) | `src/components/charts/*` (Recharts por tras) | Nivo, Chart.js, Victory, Plotly |
| Charts (BI complexo) | ECharts **apenas** se o chart do Tremor nao suportar o caso | ECharts para qualquer chart que o Tremor ja tenha |
| Forms | `react-hook-form` + `zod` | Formik, uncontrolled manual |
| HTTP | `@tanstack/react-query` via `src/lib/api-client.ts` | fetch/axios direto em componentes |
| Estado global | `zustand` quando necessario | Redux, MobX, Recoil, Jotai |
| Datas | `date-fns` | moment, dayjs, luxon |

Instalar qualquer biblioteca fora desta tabela exige autorizacao explicita do usuario no chat.

---

## 3. Arquitetura em 4 camadas

```
src/components/tremor/      <- Primitivos Tremor Raw (verbatim da doc).
                                Nao editar. Substitua apenas ao atualizar a versao upstream.

src/components/charts/      <- Charts do Tremor (verbatim). Mesma regra.

src/components/app/         <- Composicoes reutilizaveis de dominio neutro
                                (ex.: PageHeader, DataTable, FormLayout, EmptyState).
                                USA apenas tremor/ e charts/, nunca Tailwind bruto
                                de cor / Radix cru.

src/components/<dominio>/   <- Componentes amarrados a um dominio especifico
                                (ex.: "contratos", "fornecedores", "dashboards").
                                Compostos de app/ + tremor/ + charts/.
```

**Imports permitidos por camada:**

- `tremor/` importa: `@/lib/utils`, `@/lib/chartUtils`, `@remixicon/react`, `tailwind-variants`, Radix UI (interno), Recharts (interno).
- `charts/` importa: o mesmo que `tremor/` + `react`.
- `app/` importa: `@/components/tremor/*`, `@/components/charts/*`, `@/lib/*`, `@remixicon/react`. **Proibido**: Radix direto, Recharts direto, classes de cor Tailwind ad-hoc.
- `<dominio>/` importa: `@/components/app/*`, `@/components/tremor/*`, `@/components/charts/*`, hooks de dominio, types de dominio.

---

## 4. Tokens e cores

**Paleta Tremor — unicas cores brutas aceitas:**

| Categoria | Classes permitidas | Uso |
|---|---|---|
| Neutros | `gray-*` (todas as escalas + `dark:`, inclui `gray-925`) | textos, bordas, backgrounds, superficies |
| **Atencao / selecao** | `blue-*` (principalmente `blue-500` para bg/fill e `blue-600`/`blue-700` para texto em light; `blue-400`/`blue-500` em dark) | **chama os olhos do usuario** — estado ativo da sidebar, aba ativa (TabNavigation/Tabs), filtros com selecao aplicada (FilterPill, PeriodoPresets), botoes primary, focus rings (`focusInput`/`focusRing`), checkbox/radio/switch marcados, calendar selected, link "voltar/editar". **Nao** use como cor semantica de "sucesso/info" — para isso use `Badge variant`. |
| Destrutivo / erro | `red-*` (em qualquer escala + `dark:`) | ErrorState, Dialog destructive, Button destructive, validacao de form, toasts de erro |
| **Dados (chart)** — paleta A7 Credit | cores de `chartColors` em `@/lib/chartUtils`, na ordem canonica: `slate` → `sky` → `teal` → `emerald` → `amber` → `rose` → `violet` → `indigo`. `blue`/`gray`/`cyan`/`pink`/`lime`/`fuchsia` existem no dicionario mas **nao iteram no default** — use por override explicito. | **apenas em `src/components/charts/`** ou quando a cor vier dinamicamente de `getColorClassName()`. `slate` (1a serie) escolhido por ser azul-acinzentado de baixa saturacao — nao cansa durante horas de analise. |

**Racional da paleta dual (v0.3.0, 2026-04-21):**
- **`blue-*` chama atencao** (seletivo, pontual) — aparece onde o olho precisa ir primeiro: "algo esta aplicado", "algo e clicavel", "algo esta em foco".
- **`slate-*` acomoda o olho** (horas de leitura) — para series de chart que ficam renderizadas longamente.
- Esta divisao resolve o conflito entre "sistema convidativo" (precisa de contraste em interacao) e "sistema que nao cansa" (charts com baixa saturacao).

**Proibido:**
- Valores arbitrarios de cor: `text-[#123abc]`, `bg-[rgb(...)]`, `border-[hsl(...)]`.
- **`slate-*` como cor de atencao/selecao** — use `blue-*`. `slate` e exclusivamente para dados de chart + neutros raros.
- **`blue-*` como cor de serie default em chart** — a 1a cor iteravel da paleta A7 e `slate`, nao `blue`. `blue` so como override explicito `<Chart colors={["blue"]}>`.
- Cores Tailwind fora das categorias acima: `orange-*`, `purple-*`, `yellow-*`, `stone-*`, `zinc-*`, `neutral-*`. (`teal`, `sky`, `rose`, `indigo`, `violet` estao liberadas **somente para series de chart**, via `chartUtils`.)
- Usar cores de dados (`emerald`, `teal`, `rose`, etc) como cor semantica geral fora de charts (ex.: `bg-emerald-500` em badge de "ativo" — use `Badge variant="success"` do Tremor).
- Gradientes manuais (`bg-gradient-to-*` com cores arbitrarias).

**Dark mode:** sempre suportar. Usar as mesmas classes que o Tremor usa (`dark:bg-gray-950`, `dark:text-gray-50`, `dark:border-gray-800`). O `<html>` ja tem `dark:bg-gray-950` em `layout.tsx`.

**Espacamento, tipografia, radius:** herdar do Tremor. Sem classes magicas (`text-[13px]`, `p-[7px]`). Se precisar de um tamanho que o Tremor nao cobre, pare e discuta.

---

## 5. Regras de codigo

- **Idioma da UI:** sempre pt-BR. Strings voltadas para usuario em pt-BR. Mensagens de erro tecnicas (console/dev) podem ser em ingles.
- **Imports:** usar sempre alias `@/*` (nunca `../../../`).
- **Componentes:** `function Component() { return (...) }` exportado. Props tipadas com `type`, nao `interface`, a menos que precise de extends.
- **`use client`** so quando necessario (interatividade, hooks de browser). Por padrao, Server Components.
- **Nenhum `any`** em codigo de dominio. Em codigo verbatim do Tremor, preservar com `// eslint-disable-next-line @typescript-eslint/no-explicit-any`.
- **Nada de inline styles** (`style={{...}}`) exceto quando o Tremor exige (ex.: `style={{ color }}` em cores dinamicas via paleta).

---

## 6. Formularios e tabelas

**Formularios** sempre compoem apenas primitivos `tremor/`: `Input`, `Select`, `Textarea`, `Checkbox`, `Switch`, `RadioGroup`, `Label`, `DatePicker`, `NumberInput` (via Input com `type="number"`).

- Validacao: `react-hook-form` + `zod`.
- Layout: `src/components/app/FormLayout` (a criar como template).
- Botoes: sempre `Button` do Tremor, nunca `<button>` cru.

**Tabelas** sempre com `Table` do Tremor. Para tabelas com sort/filter/paginacao, usar `@tanstack/react-table` por baixo + componentes Tremor no render. Nunca AG Grid, nunca data grid externo.

---

## 7. Paginas e rotas

Toda pagina nasce de um dos 5 templates canonicos (quando existirem em `src/templates/`):

- **ListTemplate** — tela de listagem com busca/filtro/tabela.
- **FormTemplate** — criar/editar recurso.
- **DetailTemplate** — visualizacao de recurso.
- **DashboardTemplate** — KPIs + charts.
- **WizardTemplate** — fluxo multi-step.

Antes de escrever uma `page.tsx` nova, pergunte: "qual template aplica?". Se nenhum, e sinal de que precisa de discussao, nao de uma excecao.

---

## 8. Skills do projeto

Em `frontend/.claude/skills/` vivem skills que automatizam o nascimento de novo codigo ja alinhado a estas regras. Use-as sempre que for criar:

- `create-list-page` — nova pagina de listagem
- `create-form-page` — nova pagina de formulario
- `create-detail-page` — nova pagina de detalhe
- `create-dashboard-page` — novo dashboard
- `create-component` — novo componente reutilizavel em `components/app/`
- `audit-page-consistency` — verificar se uma pagina segue as regras acima

Quando o usuario pedir "cria uma pagina de X" ou "audita a tela Y", prefira invocar a skill ao inves de escrever do zero.

---

## 9. Backend -- Visao geral

**Repo:** `C:\app_gr\backend\` (greenfield, em construcao)

**Relacao com `app_controladoria`:** O backend em `C:\app_controladoria\backend\` e **legado em producao na VM** e continua rodando em paralelo. Dele copiamos **seletivamente** (via copy-paste + refactor), nunca importamos como dependencia, nunca evoluimos. Modelos reaproveitados: `Tenant`, `User`, `Empresa`. Servicos reaproveitados: `auth_service`, `dre_calculo_*` (quando reativarmos contabilidade). Tudo o mais e desenho novo.

**Stack obrigatoria:**

| Area | Obrigatorio | Proibido |
|---|---|---|
| Framework | FastAPI (>= 0.115) | Flask, Django, Express |
| Python | 3.11+ | <= 3.10 |
| ORM | SQLAlchemy 2.0 async + asyncpg | SQLAlchemy sync, Tortoise, Django ORM |
| Schemas | Pydantic v2 | Pydantic v1, marshmallow |
| Banco | PostgreSQL 16 | MySQL, SQLite em prod |
| Migrations | Alembic (migration REAL, nao `create_all`) | `create_all` em startup, migrations manuais ad-hoc |
| Linter/formatter | Ruff | black standalone, flake8, pylint |
| Testes | pytest + pytest-asyncio + httpx | unittest manual |
| Task scheduling | APScheduler (MVP); Celery/Temporal (futuro) | threading.Timer ad-hoc |
| HTTP client | httpx (async) | requests |
| Logging | `structlog` ou `logging` com JSON formatter | `print()` |
| Secrets | `.env` em dev, env vars no systemd em prod | hard-coded |
| Deploy | systemd + uvicorn na VM (sem Docker) | Docker em prod |

Instalar qualquer biblioteca fora desta tabela exige autorizacao explicita.

---

## 10. Backend -- Multi-tenant (regra absoluta)

O GR e **multi-tenant desde o dia 1**, mesmo rodando com 1 tenant real no MVP.

**Regras duras:**

1. **Toda tabela de dominio tem `tenant_id` NOT NULL.** Excecoes: tabelas globais como `tenant` e `source_catalog`. Essas sao claramente marcadas em comentario.
2. **Nenhuma query sem escopo de tenant.** O escopo e aplicado via dependency/middleware (`get_current_tenant_id`), nao por dev lembrar de filtrar.
3. **Middleware central** extrai `tenant_id` do JWT e injeta no contexto da request. Repository/service recebe o `tenant_id` explicitamente — nunca pega de session/thread-local global.
4. **Testes de isolamento obrigatorios:** para cada modulo, testes que verificam que tenant A nao ve dado de tenant B.
5. **Tenant_id em TODO indice composto** onde faz sentido. Queries lentas por "esqueci o indice com tenant_id" sao bug.

**Modelo de multi-tenancy:** shared DB + `tenant_id` (opcao simples, suficiente ate N pequeno de tenants). Quando escala pedir, evoluimos para schema-per-tenant com zero refactor de codigo de dominio — o adapter de DB muda, o dominio nao.

---

## 11. Backend -- Modularizacao (bounded contexts)

O GR e **modular** em 4 dimensoes simultaneas (UI, codigo, permissao, licenciamento). Modularizacao e **estrutural**, aplicada desde o Sprint 1. Retrofit e caro.

### 11.1 Os 8 modulos oficiais (enum fechado)

| Modulo | Proposito |
|---|---|
| `bi` | Dashboards, analises, cruzamentos (MVP) |
| `cadastros` | Empresas, pessoas, cedentes, sacados |
| `operacoes` | Contratos, titulos, pagamentos, recebimentos |
| `controladoria` | Contabilidade, plano de contas, DRE, balancete |
| `risco` | Scoring, limites, PDD, stress, concentracao |
| `integracoes` | Adapters, catalogo de fontes, sync, reconciliacao |
| `laboratorio` | Teses de dados, correlacoes, experimentos |
| `admin` | Tenants, users, roles, subscriptions, config sistemica |

Adicionar um nono modulo exige **autorizacao explicita** + atualizacao deste documento + atualizacao do enum `Module` em `app/core/enums.py`.

### 11.2 Estrutura fisica (bounded contexts)

```
app/
├── core/                 # cross-cutting absoluto (config, db, security, middlewares, enums)
├── shared/               # shared kernel
│   ├── auditable.py      # mixin
│   ├── audit_log/        # decision_log, premise_set
│   └── identity/         # Tenant, User, UserModulePermission, TenantModuleSubscription
├── modules/
│   ├── bi/
│   │   ├── public.py     # CONTRATO publico do modulo
│   │   ├── models/
│   │   ├── services/
│   │   ├── schemas/
│   │   └── api/
│   ├── cadastros/
│   ├── operacoes/
│   ├── controladoria/
│   ├── risco/
│   ├── integracoes/
│   │   └── adapters/
│   │       └── erp/bitfin/
│   ├── laboratorio/
│   └── admin/
└── main.py
```

### 11.3 Regras de import (bounded contexts)

- Modulo X pode importar **livremente** de `app/core/` e `app/shared/`.
- Modulo X pode importar de modulo Y **somente** via `app/modules/Y/public.py`. Imports de internals de Y (`modules/Y/models/*`, `modules/Y/services/*`) sao **proibidos**.
- Cada modulo expoe em `public.py` APENAS o que e contrato estavel. Mudar `public.py` e mudanca de API — exige reflexao.
- Modulo nao deve depender de mais de 1-2 outros modulos. Se depender de 3+, provavelmente precisa de shared kernel ou event bus.
- **BI** le do `warehouse` (dado canonico), nao importa de outros modulos.
- **Integracoes** popula warehouse; outros modulos leem warehouse, nunca chamam integracoes.

### 11.4 Estrutura de rotas do frontend

```
src/app/(app)/
├── page.tsx              # home global (atalhos por modulo)
├── bi/...
├── cadastros/...
├── operacoes/...
├── controladoria/...
├── risco/...
├── integracoes/...
├── laboratorio/...
├── admin/...
└── templates/            # dev-only, fora de modulos
```

Cada modulo pode ter seu proprio `layout.tsx` interno e submenus proprios.

### 11.5 Regras do frontend

- Sidebar: um modulo ativo por vez (selecionado via `ModuleSwitcher`), lista plana das secoes L2 abaixo.
- Um modulo desabilitado (subscription `enabled=false`) **nao aparece** no `ModuleSwitcher` nem e acessivel.
- Um modulo sem permissao de usuario (`permission=none`) **nao aparece** no `ModuleSwitcher`.
- Breadcrumbs hierarquicos: `Modulo > Funcionalidade > Recurso`.
- Pagina do modulo X nunca importa componentes especificos de modulo Y. Componentes compartilhados ficam em `src/components/app/`.

### 11.6 Navegacao — hierarquia de 3 niveis (regra oficial)

Toda navegacao do sistema respeita **3 niveis, nunca 4**. Usa apenas primitivos Tremor existentes — zero padrao inventado.

| Nivel | Significado | Onde vive | Primitivo Tremor |
|---|---|---|---|
| **L1** | Modulo (um dos 8) | `ModuleSwitcher` no topo da sidebar (dropdown) | `DropdownMenu` |
| **L2** | Secao/funcionalidade do modulo | Lista plana de links na sidebar (do modulo ativo) | `SidebarLink` |
| **L3** | Abertura/drill-down/perspectiva | Tabs horizontais no topo da pagina | `TabNavigation` + `TabNavigationLink` |

**Exemplo canonico — modulo BI:**

```
L1 (dropdown no topo): [BI ▾]
    L2 (sidebar): Operacoes   → /bi/operacoes      → L3 tabs: Visao geral | Por produto | ...
                  Carteira    → /bi/carteira       → L3 tabs: Total | Por produto | Por cedente | Aging
                  Fluxo caixa → /bi/fluxo-caixa    → L3 tabs: ...
                  Benchmark   → /bi/benchmark      → L3 tabs: Visao geral | PDD | Evolucao | Fundos
                                (dados publicos CVM FIDC — ver docs/integracao-cvm-fidc.md)
```

**Regras duras:**

1. **Maximo 3 niveis.** Se surgir L4, o modulo precisa ser dividido OU aquilo vira filtro/modal/drawer — nunca 4o nivel de navegacao.
2. **Sidebar nao aninha.** Sidebar mostra SO as secoes L2 do modulo ativo, como lista plana. Sem grupos colapsaveis, sem arvore. L3 sempre e `TabNavigation` na pagina.
3. **URL e a fonte unica da verdade.** Modulo, secao, tab e filtros sao todos deep-linkaveis (ex.: `/bi/carteira?tab=por-produto&periodo=30d`). O modulo ativo e inferido do pathname.
4. **Troca entre modulos (L1) e SEMPRE pelo `ModuleSwitcher`** (dropdown no topo da sidebar). O switcher lista os modulos com subscription + permissao; demais ficam em "Em breve" (disabled). Sem icon rail, sem module picker separado do header, sem tabs de modulo.
5. **Breadcrumbs sticky no header** mostram o path: `Modulo > Secao > Pagina` (L1 > L2 > L3).

**Active state (implementacao):**

- L1 ativo: `ModuleSwitcher` exibe o modulo inferido de `getActiveModule(pathname)` (em `src/lib/modules.ts`) com avatar colorido + nome + permissao.
- L2 ativo: `SidebarLink` com `isActive={pathname.startsWith(section.href)}` — borda/texto azul via `data-active=true`.
- L3 ativo: `TabNavigationLink active={pathname includes tab}` ou comparacao com search param.

**Avatars de modulo — cor canonica (uma por modulo, paleta A7 Credit):**

| Modulo | Cor |
|---|---|
| BI | `blue` |
| Cadastros | `sky` |
| Operacoes | `teal` |
| Controladoria | `emerald` |
| Risco | `amber` |
| Integracoes | `rose` |
| Laboratorio | `violet` |
| Admin | `slate` |

Qualquer outro uso de cor nessa escala dentro de componentes `app/` e proibido (exceto chart series). Ver `src/lib/modules.ts::MODULE_AVATAR_COLORS`.

---

## 12. Backend -- RBAC + Subscription por modulo

Acesso a cada modulo e controlado em duas camadas independentes:

1. **Subscription (tenant-level):** o tenant contratou/habilitou o modulo?
2. **Permission (user-level):** o usuario tem permissao dentro daquele modulo?

### 12.1 Enums centralizados

`app/core/enums.py`:
- `Module` — um valor por modulo: `BI`, `CADASTROS`, `OPERACOES`, `CONTROLADORIA`, `RISCO`, `INTEGRACOES`, `LABORATORIO`, `ADMIN`
- `Permission` — escala: `NONE`, `READ`, `WRITE`, `ADMIN` (ordem crescente)

### 12.2 Tabelas

```sql
-- shared/identity
tenant_module_subscription (
  tenant_id uuid FK,
  module Module,
  enabled bool,
  enabled_since timestamptz,
  enabled_until timestamptz null,
  plan_ref text null,
  PRIMARY KEY (tenant_id, module)
)

user_module_permission (
  user_id uuid FK,
  module Module,
  permission Permission,
  PRIMARY KEY (user_id, module)
)
```

### 12.3 Dependency obrigatoria em todo endpoint de modulo

```python
from app.core.module_guard import require_module
from app.core.enums import Module, Permission

@router.get("/api/v1/bi/receita")
async def receita(
    _: None = Depends(require_module(Module.BI, Permission.READ)),
    ...
):
    ...
```

`require_module`:
1. Verifica `tenant_module_subscription.enabled` → se `false`, HTTP 402 (Payment Required).
2. Verifica `user_module_permission.permission >= Permission exigida` → se nao, HTTP 403.

**Nenhum endpoint de modulo pode existir sem `require_module`.** Endpoints cross-cutting (auth, health, audit/ping) podem usar `require_authenticated` simples.

### 12.4 `/auth/me` e contrato com o frontend

Retorna:
```json
{
  "user": { "id": "...", "email": "...", "name": "..." },
  "tenant": { "id": "...", "slug": "...", "name": "..." },
  "enabled_modules": ["bi", "cadastros", "admin"],
  "user_permissions": {
    "bi": "admin",
    "cadastros": "write",
    "admin": "admin"
  }
}
```

Frontend usa `enabled_modules` + `user_permissions` para renderizar sidebar e esconder areas. Ainda assim, backend valida em toda request (defense in depth).

### 12.5 Evolucao (nao no MVP)

- `Role` + `RoleModulePermission` + `UserRole` quando `user_module_permission` virar repetitivo
- Permissoes de objeto (filial, carteira) quando a necessidade aparecer
- Multi-role por user
- Planos agregados (`Plan` + `PlanModule`) para spinoff comercial

---

## 13. Backend -- Adapter pattern (fontes externas)

Fontes de dados externas (ERPs, admin APIs, bureaus, parsers de documento) **NUNCA** sao chamadas diretamente de servicos de dominio. Sempre atraves de adapters.

**Camadas:**

```
app/adapters/<tipo>/<nome>/
    __init__.py
    connection.py      # como abrir conexao / sessao
    queries.py         # queries/requests especificos da fonte
    mappers.py         # transforma dado da fonte para modelo canonico
    etl.py             # orquestra extract + transform + load
```

**Exemplos (plano):**
- `app/adapters/erp/bitfin/` — leitura SQL Server do Bitfin
- `app/adapters/admin/qitech/` — API QiTech (pos-MVP)
- `app/adapters/bureau/serasa_refinho/` — Serasa Refinho (pos-MVP)
- `app/adapters/document/nfe/` — parser XML de NFe (pos-MVP)

**Regras do adapter:**

1. **Um adapter por ENDPOINT/API, nao por provedor.** Refinho e PFIN sao adapters separados mesmo sendo ambos Serasa.
2. **Versao embutida no adapter:** constante `ADAPTER_VERSION = "1.0.0"` registrada em toda linha ingerida (`ingested_by_version`).
3. **Output sempre em modelo canonico.** Adapter conhece a fonte e conhece o canonico; dominio nao conhece fontes.
4. **Config por tenant:** cada tenant tem seu registro de configuracao (connection string, credenciais, parametros) em tabela `tenant_source_config`. Adapter le config do tenant, nao ha hardcode.
5. **Proibido adapter em codigo de dominio.** Services de dominio leem APENAS do warehouse canonico.
6. **Observabilidade obrigatoria:** cada sync registra metricas (linhas lidas, tempo, erros) no `decision_log`.
7. **Custo + rate limit como metadados** em `source_catalog` quando fonte for paga (bureaus).

Adicionar uma fonte nova = novo adapter + registro em `source_catalog` + registro em `tenant_source_config`. **Zero refactor do core.**

### 13.1 Fontes externas federadas (postgres_fdw)

Nem toda fonte externa que popula o GR vira adapter no bounded context `integracoes`. Fontes **publicas** (sem `tenant_id`), com ciclo de ingestao proprio e volume significativo, podem viver em **DB separado no mesmo cluster Postgres** e serem lidas pelo `gr_db` via `postgres_fdw`.

**Criterios pra escolher esse padrao em vez de adapter interno:**

1. Dado e **publico** — sem escopo de tenant (ex.: CVM dados abertos, Receita Federal, Bacen)
2. Volume justifica DB dedicada — backup, vacuum e lifecycle desacoplados do `gr_db`
3. Pipeline de ingestao tem cadencia propria (cron mensal, por exemplo) nao acoplada ao trafego transacional do GR
4. Ciclo de dev / deploy da ingestao faz sentido ser independente (repo proprio, CI propria)

**Como funciona:**

- DB dedicada na mesma instancia Postgres da VM 27 (ver §17). Role dona da DB isolada.
- Repo de ETL separado, deploy independente (sem Docker — venv + pip + cron ou systemd).
- `gr_db` le via `CREATE EXTENSION postgres_fdw` + `CREATE SERVER` + `IMPORT FOREIGN SCHEMA <fonte> INTO <fonte>_remote`.
- Backend GR trata as foreign tables como locais, mas **anota no `decision_log`** `source_type='public:<fonte>'` sempre que calcular metrica derivada. Badge de proveniencia no frontend mostra a origem publica + competencia + versao do adapter que ingeriu (CLAUDE.md §14.6).
- **Nao duplicar dado** no `gr_db`. Se performance pedir, usar materialized view local OU indices no banco federado. Nunca copy-to-gr_db.

**O que NAO e fonte federada (continua sendo adapter em `modules/integracoes`):**

- Qualquer fonte com escopo de tenant (ERP, admin API, bureau pago por consulta)
- Fontes transacionais cuja sincronizacao dispara evento de dominio (recebimento, conciliacao)
- Fontes cuja config varia por tenant (credenciais, filtros, parametros)

**Primeiro exemplo em producao:** CVM FIDC (Informes Mensais, dados abertos). Detalhes completos em [`docs/integracao-cvm-fidc.md`](./docs/integracao-cvm-fidc.md) — arquitetura, schema, ponte FDW, consumo pelo modulo BI.

---

## 14. Backend -- Proveniencia e auditabilidade (DNA do sistema)

Em mercado financeiro regulado (CVM/ANBIMA/Bacen), **explicabilidade + rastreabilidade valem mais que sofisticacao**. Recomendacao sem trilha de auditoria nao passa em compliance. Isso nao e feature — e estrutural. Disciplina aplicada em TODAS as camadas desde o dia 1.

### 14.1 Modelo `Auditable` (mixin SQLAlchemy)

**Toda** tabela de dominio que armazena dado ingerido de fonte externa herda deste mixin. Campos obrigatorios:

| Campo | Tipo | Proposito |
|---|---|---|
| `source_type` | enum | "erp:bitfin", "admin:qitech", "bureau:serasa_refinho", "self_declared", "peer_declared", "internal_note", "derived" |
| `source_id` | text | ID do registro na fonte original |
| `source_updated_at` | timestamp | Quando o dado foi atualizado na fonte |
| `ingested_at` | timestamp | Quando foi lido para o warehouse |
| `hash_origem` | text | SHA256 do payload bruto (deteccao de mudanca) |
| `ingested_by_version` | text | Versao do adapter que ingeriu (ex.: "bitfin_adapter_v1.0.0") |
| `trust_level` | enum | "high", "medium", "low" |
| `collected_by` | uuid nullable | Usuario que coletou (aplica a self_declared, peer_declared) |

### 14.2 Tabela `decision_log` (append-only)

Toda decisao/calculo/sync do sistema e registrado aqui. Particionada por tenant + data.

**Append-only:** sem UPDATE, sem DELETE. Correcao se da por NOVA entrada que referencia a anterior.

**Campos principais:**
- `id`, `tenant_id`, `occurred_at`
- `decision_type` (enum: "sync", "calculation", "alert", "recommendation", "score", "reconciliation_check", ...)
- `inputs_ref` (JSON ou FK para tabela de inputs estruturados)
- `rule_or_model` + `rule_or_model_version`
- `output` (JSON)
- `explanation` (texto estruturado, top-N fatores quando aplicavel)
- `triggered_by` (user_id ou "system:scheduler")

### 14.3 Tabela `premise_set` (premissas como dado)

Premissas de calculos/projecoes (taxa CDI, curva, tolerancias, cortes) vivem em tabelas versionadas, nao em constantes no codigo.

- Usuario edita via UI; cada edicao cria nova versao
- Projecao referencia o `premise_set_id` usado
- Historico preservado — replay de projecao antiga reutiliza premissas da epoca

### 14.4 Versionamento de regras e modelos

Regra de negocio, formula DRE, modelo de score: **todas** tem versao explicita. Decisao tomada com v1 fica imutavelmente referenciando v1 mesmo 5 anos depois. v2 nao substitui — coexiste.

### 14.5 Explicabilidade obrigatoria para qualquer output derivado

Score, alerta, recomendacao, classificacao: o sistema registra no `decision_log` os 3-5 fatores principais que geraram o output. Nao e optional — e contrato de produto.

**Escolha de ferramentas de ML:** preferir modelos interpretaveis (regressao logistica, GBM com SHAP) sobre caixas-preta. Quando caixa-preta for necessaria, registrar inputs + outputs + explicacao gerada sistematicamente.

### 14.6 Trust metadata visivel na UI

Frontend exibe:
- Badge `<DataOriginBadge />` ao lado de cada KPI/numero: tooltip/click abre proveniencia (source, timestamp, versao do adapter, trust level)
- Botao `<ShowPremisesButton />` em qualquer visual que mostre calculo/projecao: abre modal com premissas usadas
- Rodape de cada dashboard: "Dados sincronizados em XX/XX as HH:MM a partir de Bitfin"

---

## 15. Backend -- Regras de codigo

- **Idioma:** comentarios e docstrings em ingles (padrao python community). Strings voltadas para API/usuario em pt-BR quando aplicavel.
- **Imports:** absolutos (`from app.services import ...`). Nunca relativos profundos (`from ....`).
- **Type hints obrigatorios** em todas as funcoes publicas. `any` proibido.
- **Async por padrao.** Qualquer I/O (DB, HTTP, filesystem) em async. Lib sync (pyodbc) roda em thread pool.
- **Functions > classes.** Use classes para models ORM, Pydantic schemas, adapters. Logica de dominio preferencialmente em funcoes puras.
- **Sem `print`.** Sempre logger estruturado.
- **Zero dependencia de caminho absoluto.** Config via env var.
- **Um endpoint = um responsability.** Nao ha endpoint "generico" que faz varias coisas.

---

## 16. Backend -- Dev workflow e deploy

### Desenvolvimento local (Windows)

```
C:\app_gr\backend\
├── .venv\                    # venv local (nao commitar)
├── .env                      # config local (nao commitar)
├── pyproject.toml            # ou requirements.txt
├── alembic.ini
├── alembic\versions\
└── app\...
```

- Python 3.11+ instalado
- Postgres local (ou remoto via SSH tunnel para VM) com database `gr_db_dev`
- `.env` aponta para Postgres local
- Rodar: `source .venv/Scripts/activate && uvicorn app.main:app --reload`

### Producao (VM Linux Ubuntu/Debian)

```
/opt/app_gr/backend/
├── .venv/
├── .env                      # config prod (chmod 600)
├── app/...
└── alembic/...
```

- Systemd service: `/etc/systemd/system/gr-api.service`
- Rodar: `systemctl start gr-api`
- Postgres na VM: database `gr_db` (separada do banco do app_controladoria que continua na mesma instancia)

### Deploy (manual inicial, automavel depois)

```bash
ssh vm
cd /opt/app_gr/backend
git pull
source .venv/bin/activate
pip install -r requirements.txt  # ou poetry install
alembic upgrade head
sudo systemctl restart gr-api
```

CI via GitHub Actions roda lint + pytest em cada push.

---

## 17. Banco de dados -- arquitetura

**Mesmo servidor Postgres da VM, databases separadas:**

| Database | Proposito |
|---|---|
| `gr_db` | GR — novo, construido neste projeto |
| `cvm_benchmark` | Dados publicos CVM FIDC — populado pelo ETL externo `etl-cvm` (repo `A7-Development/etl-cvm`, VM 26), lido pelo `gr_db` via `postgres_fdw` sob schema `cvm_remote`. Ver [`docs/integracao-cvm-fidc.md`](./docs/integracao-cvm-fidc.md) e §13.1 |
| (database legada) | app_controladoria — producao, nao tocar |

- Zero acoplamento direto entre os dois. Se GR precisar ler dado do app_controladoria no futuro, usar `postgres_fdw` (foreign data wrapper).
- Backups independentes.
- Migrations independentes.
- Roles de usuario Postgres separados (user do GR so acessa `gr_db`).

---

## 18. Checklist antes de commitar

### Frontend (pagina)

- [ ] Usa apenas componentes de `tremor/`, `charts/`, `app/` ou do proprio dominio?
- [ ] Zero `import` de `lucide-react`, `shadcn`, `@mui`, etc?
- [ ] `cx()` e nao `cn()`?
- [ ] Icones sao `Ri*` de `@remixicon/react`?
- [ ] Zero cor arbitraria (`text-[#...]`, `bg-red-500` fora da paleta Tremor)?
- [ ] Dark mode testado?
- [ ] Strings de UI em pt-BR?
- [ ] **Pagina respeita regra de 3 niveis (L1 sidebar grupo / L2 sidebar sub-item / L3 TabNavigation)?**
- [ ] **Sidebar nao aninha em 3+ niveis (L3 sempre como tabs na pagina, nunca sub-sub-item)?**
- [ ] **Estado de navegacao (modulo/secao/tab/filtros) e deep-linkavel via URL?**
- [ ] `npx tsc --noEmit` passa?
- [ ] `npm run build` passa?

### Backend (endpoint/servico)

- [ ] Endpoint e autenticado via `Depends(get_current_user)` (ou explicitamente marcado como publico)?
- [ ] **Endpoint de modulo usa `require_module(Module.X, Permission.Y)` como dependency obrigatoria?**
- [ ] Query escopa por `tenant_id` automaticamente via middleware/dependency?
- [ ] Teste de isolamento de tenant existe?
- [ ] **Teste de regressao de permissao de modulo existe (user sem permissao recebe 403)?**
- [ ] Se cria dado no warehouse, aplica mixin `Auditable` com proveniencia completa?
- [ ] Se e decisao/calculo, registra no `decision_log`?
- [ ] **Import cruzado entre modulos so passa por `modules/Y/public.py`? Zero import de internals de outro modulo?**
- [ ] **Se introduziu modulo novo, atualizou enum `Module` + CLAUDE.md secao 11.1?**
- [ ] Type hints completos? Zero `any`?
- [ ] Novo secret em `.env.example` (sem valor)?
- [ ] Migration Alembic criada se alterou modelo?
- [ ] `ruff check` passa?
- [ ] `pytest` passa?

### Adapter novo

- [ ] Extende a interface base de adapter?
- [ ] Constante `ADAPTER_VERSION` definida e registrada?
- [ ] Output em modelo canonico?
- [ ] Config vindo de `tenant_source_config`, zero hardcode?
- [ ] Registra sync no `decision_log`?
- [ ] Registro correspondente adicionado em `source_catalog`?
- [ ] Teste de integracao com fonte (mock ou sandbox) existe?

Se qualquer item reprovar, **nao corrija pontualmente** — pare e revise a mudanca inteira.
