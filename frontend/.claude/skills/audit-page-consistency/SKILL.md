---
name: audit-page-consistency
description: Audita uma pagina (ou componente) contra as regras de design system do projeto (CLAUDE.md). Reporta violacoes e sugere correcoes. Use quando o usuario pedir "audita a tela X", "verifica se Y segue o padrao", "revisa a consistencia de Z".
---

# audit-page-consistency

Verificador automatico de conformidade com `CLAUDE.md`. Roda como revisao estatica — nao altera o codigo, so reporta.

## Pre-condicao obrigatoria

Ler `CLAUDE.md` na raiz.

## Entrada

Caminho(s) de arquivo ou pasta a auditar. Se o usuario nao especificar, peca via `AskUserQuestion`.

## Procedimento

Para cada arquivo no escopo, verificar e reportar violacoes nas seguintes categorias.

### 1. Imports proibidos (erro grave)

Grep por:
- `from "lucide-react"` / `from 'lucide-react'`
- `from "@heroicons/react"` / `from '@heroicons/react'`
- `from "react-icons`
- `from "@mui/` / `from "@material-ui/`
- `from "@chakra-ui/`
- `from "antd"` / `from "@ant-design/`
- `from "shadcn"` (a biblioteca oficial; componentes copy-paste nao aparecem como import deste nome)
- `from "recharts"` **fora** de `src/components/charts/`
- `from "@radix-ui/` **fora** de `src/components/tremor/`

### 2. Utilitarios errados (erro grave)

- `import { cn }` vindo de qualquer lugar — deve ser `cx` de `@/lib/utils`.
- `from "class-variance-authority"` — deve ser `tailwind-variants`.
- `from "classnames"` ou `from "clsx"` direto em componentes — deve passar por `cx`.

### 3. Cores arbitrarias (erro)

Regex por:
- `text-\[#` / `bg-\[#` / `border-\[#`
- `text-\[rgb` / `bg-\[rgb` / `border-\[rgb`
- `text-\[hsl` / `bg-\[hsl` / `border-\[hsl`

Classes Tailwind permitidas:
- `gray-*` livremente (neutros, inclui `gray-925`).
- `blue-*` permitido como cor de acento/foco (focus rings, items de navegacao ativos, selecao).
- `red-*` permitido **apenas** em componentes com semantica de erro/destrutivo (ErrorState, validacoes de form, dialogs destrutivos, toasts de erro).
- `emerald|violet|amber|cyan|pink|lime|fuchsia-*` permitido **apenas** dentro de `src/components/charts/` ou quando a cor vem dinamicamente de `chartColors` via `getColorClassName()`.

Proibidas em todo lugar: `indigo-*`, `orange-*`, `teal-*`, `purple-*`, `sky-*`, `yellow-*`, `rose-*`, `stone-*`, `slate-*`, `zinc-*`, `neutral-*`.

### 4. Elementos HTML crus que deveriam ser Tremor (erro)

- `<button>` cru — deveria ser `Button` do Tremor.
- `<input>` cru — deveria ser `Input` ou outro primitivo de input.
- `<select>` cru — deveria ser `Select` do Tremor.
- `<textarea>` cru — deveria ser `Textarea` do Tremor.
- `<hr>` cru — deveria ser `Divider` do Tremor.
- `<dialog>` cru ou `window.confirm` — deveria ser `Dialog` do Tremor.
- `<table>` cru — deveria ser `Table` do Tremor.

### 5. Estilo inline (alerta)

`style={{` — aceitar apenas quando a cor vem dinamicamente de `chartColors` / `AvailableChartColors`. Reportar para revisao manual.

### 6. Idioma (alerta)

Procurar strings de UI (JSX children, labels, placeholders, mensagens de erro) em ingles. Heuristica: palavras comuns como "Submit", "Cancel", "Loading", "Error", "Save", "Delete". Reportar para revisao.

### 7. Dark mode ausente (alerta)

Toda classe de cor clara (`bg-white`, `text-gray-900`, `border-gray-200`, etc) deveria ter contrapartida `dark:`. Procurar linhas com classes de cor sem variante `dark:` na mesma string.

### 8. Tamanhos/espacamentos magicos (alerta)

Regex por classes arbitrarias:
- `text-\[\d+px\]`
- `p-\[\d+px\]`, `m-\[\d+px\]`, `gap-\[\d+px\]`
- `w-\[\d+px\]`, `h-\[\d+px\]` (aceitar quando for altura de chart, ex.: `h-72`)
- `rounded-\[`

Herdar tokens Tremor ao inves de valores magicos.

### 9. Componentes fora das camadas (alerta)

- Arquivo em `src/design-system/components/` importando de `src/components/<dominio>/` (errado; `app/` e dominio-neutro).
- Arquivo em `src/components/tremor/` importando de `src/design-system/components/` ou `src/components/<dominio>/` (errado; tremor e camada base).
- Arquivo em `src/components/charts/` importando de `src/components/<dominio>/` (errado).

### 10. `any` em codigo de dominio (alerta)

`: any` ou `<any>` fora de `src/components/tremor/` e `src/components/charts/`. Primitivos verbatim podem ter `any` com eslint-disable, mas codigo de dominio nao.

### 11. Navegacao — hierarquia de 3 niveis (erro)

Ver CLAUDE.md secao 11.6. Sistema tem exatamente 3 niveis de navegacao: L1 (modulo/sidebar grupo), L2 (secao/sidebar sub-item), L3 (abertura/TabNavigation na pagina).

Violacoes a detectar:

- **Sidebar com aninhamento de 3+ niveis.** Procurar em `src/design-system/components/AppSidebar.tsx` (ou equivalente) por `SidebarMenuSub` aninhado dentro de outro `SidebarMenuSub`. Se houver, e violacao.
- **Tabs criadas fora de `TabNavigation` do Tremor.** Em qualquer `src/app/(app)/**/page.tsx`, `<Tabs>` ou `<TabsList>` de `@radix-ui/react-tabs` direto e proibido — deve ser `TabNavigation` do Tremor em todos os casos de navegacao de L3.
- **Ausencia de `L3` via URL.** Pagina que mostra tabs mas tem estado somente em React state (sem search param) — viola a regra "URL como fonte unica da verdade". Procurar `useState<string>` combinado com tabs ou switch case de conteudo — suspeito de nao-deep-link.
- **Sidebar sem suporte a active state via `pathname`.** `SidebarSubLink` com `isActive={false}` hard-coded — deveria ser `isActive={pathname === item.href}` ou similar.

### 12. Module guard no backend (erro grave)

Verificar `src/app/(app)/<modulo>/` — toda rota de modulo no frontend pressupoe que o backend tenha `require_module(Module.X, Permission.READ)` no endpoint correspondente. Auditoria so e relevante no frontend para:

- Confirmar que `/auth/me` e consultado para filtrar sidebar (componente `AppSidebar` deveria ler `enabled_modules` e `user_permissions`).
- Confirmar que paginas nao assumem permissao — erro de 403/402 do backend tem que exibir estado amigavel (nao crash).

## Saida esperada

Relatorio estruturado em markdown:

```markdown
# Auditoria: <caminho>

## Resumo
- X erros graves
- Y erros
- Z alertas

## Erros graves

### <arquivo>:<linha>
[import proibido de lucide-react]
Trecho:
> import { Check } from "lucide-react"
Correcao sugerida:
> import { RiCheckLine } from "@remixicon/react"

...

## Erros

### ...

## Alertas

### ...

## Passa em
- (lista de arquivos auditados sem violacoes)
```

## O que NAO fazer

- Nao alterar codigo automaticamente.
- Nao sugerir correcoes que rivalizem com CLAUDE.md ("poderia usar essa outra lib"). Se CLAUDE.md diz que e proibido, e proibido.
- Nao marcar como passa se houver algum erro grave ou erro — apenas alertas podem ficar pendentes para revisao humana.
