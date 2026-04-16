# App GR -- Regras do Projeto

> Sistema de controladoria financeira (pt-BR). Monorepo com `frontend/` (Next.js 14 + Tremor Raw) e futuramente `backend/` (FastAPI + PostgreSQL). Este arquivo governa o comportamento do Claude Code em todas as sessoes deste repositorio.

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
| Acento / foco | `blue-*` | focus rings, estados de foco, items de navegacao ativos, selecao, indicadores de selecionado, `focusInput`/`focusRing` do Tremor. NAO use como cor semantica de "sucesso" ou "informacao" — para badges, use `Badge variant` do Tremor. |
| Destrutivo / erro | `red-*` (em qualquer escala + `dark:`) | ErrorState, Dialog destructive, Button destructive, validacao de form, toasts de erro |
| Dados (chart) | cores de `chartColors` em `@/lib/chartUtils`: `emerald`, `violet`, `amber`, `cyan`, `pink`, `lime`, `fuchsia` (+ `blue` e `gray` ja incluidos acima) | **apenas dentro de `src/components/charts/`** ou quando a cor vier dinamicamente de `getColorClassName()` |

**Proibido:**
- Valores arbitrarios de cor: `text-[#123abc]`, `bg-[rgb(...)]`, `border-[hsl(...)]`.
- Cores Tailwind fora das 4 categorias acima: `indigo-*`, `orange-*`, `teal-*`, `purple-*`, `sky-*`, `yellow-*`, `rose-*`, `stone-*`, `slate-*`, `zinc-*`, `neutral-*`.
- Usar cores de dados (`emerald`, `violet`, etc) como cor semantica geral fora de charts (ex.: `bg-emerald-500` em badge de "ativo" — use `Badge variant="success"` do Tremor).
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

## 9. Backend (informativo)

- O backend permanece em `C:\app_controladoria\backend\` durante a refatoracao (FastAPI + PostgreSQL, multi-tenant, ~41 endpoints). **Nao tocar**.
- Futuramente sera movido para `C:\app_gr\backend\`.
- O frontend consome via `NEXT_PUBLIC_API_URL` (ver `.env.local`).

---

## 10. Checklist antes de commitar qualquer pagina

- [ ] Usa apenas componentes de `tremor/`, `charts/`, `app/` ou do proprio dominio?
- [ ] Zero `import` de `lucide-react`, `shadcn`, `@mui`, etc?
- [ ] `cx()` e nao `cn()`?
- [ ] Icones sao `Ri*` de `@remixicon/react`?
- [ ] Zero cor arbitraria (`text-[#...]`, `bg-red-500` fora da paleta Tremor)?
- [ ] Dark mode testado?
- [ ] Strings de UI em pt-BR?
- [ ] `npx tsc --noEmit` passa?
- [ ] `npm run build` passa?

Se qualquer item reprovar, **nao e para corrigir pontualmente**: pare e audite a pagina inteira com `audit-page-consistency`.
