---
name: create-component
description: Cria um componente reutilizavel em src/design-system/components/ (camada de composicao neutra). Use quando for criar PageHeader, EmptyState, ErrorState, Breadcrumb, DataTable, FormLayout ou qualquer composicao que agregue primitivos Tremor.
---

# create-component

Use para criar **componentes de composicao** que vivem em `src/design-system/components/`. Esta camada fica entre os primitivos Tremor e os componentes de dominio.

## Pre-condicao obrigatoria

Ler `CLAUDE.md` na raiz. Regras nao-negociaveis.

## Quando usar esta skill

**Use** quando:
- O componente e neutro (nao amarrado a um dominio especifico).
- Sera reutilizado em varias paginas.
- E composicao de primitivos (nao redesenho).

**Nao use** quando:
- E um primitivo novo do Tremor (vai em `src/components/tremor/` copiado verbatim do docs).
- E amarrado a um dominio (vai em `src/components/<dominio>/`).
- E interno a uma so pagina (vira `_components/` da rota).

## Informacoes a coletar

1. **Nome** e proposito do componente.
2. **Props** esperadas (com tipos).
3. **Variantes** (se houver).
4. **Comportamento interativo** (estados, callbacks).
5. **Contexto onde sera usado** (para validar se e reutilizavel de fato).

## Estrutura a produzir

```
src/design-system/components/<NomeComponente>.tsx
```

Um unico arquivo. Se precisar de sub-componentes, exportar todos a partir do mesmo arquivo (como o Tremor faz com Card/CardHeader/CardContent).

## Regras de codigo

### Imports permitidos

- `@/components/tremor/*`
- `@/components/charts/*`
- `@/lib/utils` (`cx`, `focusInput`, `focusRing`, `hasErrorInput`)
- `@/lib/chartUtils` (se precisar de helpers de cor)
- `@remixicon/react`
- `tailwind-variants`
- `react`

### Imports proibidos

- Radix UI direto (use o primitivo Tremor que ja encapsula).
- Recharts direto.
- Qualquer biblioteca de UI externa.
- `lucide-react`, `@heroicons/react`, etc.

### Variantes

Usar `tailwind-variants` (`tv`). Padrao:

```tsx
import { tv, type VariantProps } from "tailwind-variants"

const styles = tv({
  base: "...",
  variants: {
    size: { sm: "...", md: "...", lg: "..." },
    tone: { neutral: "...", success: "...", error: "..." },
  },
  defaultVariants: { size: "md", tone: "neutral" },
})

type Variants = VariantProps<typeof styles>
```

### Props

- Tipar via `type Props = { ... } & Variants` (ou extender props nativos de um primitivo quando wrappar).
- Sempre aceitar `className` e fundir via `cx()`.
- Sempre aceitar `ref` via `React.forwardRef` quando renderizar um elemento DOM.

### Acessibilidade

- Labels sempre associadas (via `htmlFor` ou wrapping).
- Icones decorativos: `aria-hidden="true"`.
- Elementos interativos: roles/labels corretos.
- Contraste: dark mode obrigatorio.

## Proibicoes duras

- Zero cor arbitraria.
- Zero `className="text-[#...]"`.
- Zero hardcode de strings em ingles na UI (pt-BR).
- Zero `cn()` — so `cx()`.
- Zero componente que "rivaliza" com um primitivo Tremor existente. Se ja existe `Button` no Tremor, nao criar `MyButton` — se precisa de variacao, compor o Button.

## Checkpoint final

`npx tsc --noEmit && npm run lint`. Se o componente for exportado, verificar que nao quebra nenhuma importacao existente via `npm run build`.
