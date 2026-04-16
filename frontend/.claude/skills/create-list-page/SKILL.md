---
name: create-list-page
description: Cria uma nova pagina de listagem (index/busca/tabela) usando Tremor Raw no padrao do projeto. Use quando o usuario pedir "cria uma pagina de listagem de X", "index de Y", "tela de listagem", "grade de registros".
---

# create-list-page

Use esta skill para criar qualquer pagina cuja funcao principal e **listar registros com busca/filtro/paginacao**.

## Pre-condicao obrigatoria

Ler `CLAUDE.md` na raiz do monorepo antes de qualquer coisa. As regras de design system sao nao-negociaveis.

## Informacoes a coletar (via AskUserQuestion se nao vieram no pedido)

1. **Nome do dominio** (ex.: "contratos", "fornecedores") — define o segmento de rota e a pasta.
2. **Colunas da tabela** — nome + tipo (texto, numero, moeda, data, badge de status, acao).
3. **Filtros** — quais campos filtram a lista? (ex.: status, periodo, categoria).
4. **Origem dos dados** — endpoint da API (se ja existir) ou mock temporario.
5. **Acoes por linha** — editar, excluir, visualizar, exportar? Quais?
6. **Acao do header** — botao "Novo X"? Exportar lista?

## Estrutura a produzir

```
src/app/(app)/<dominio>/page.tsx           <- Server Component; loader da lista
src/app/(app)/<dominio>/_components/
    <Dominio>Table.tsx                     <- Client Component; tabela com @tanstack/react-table
    <Dominio>Filters.tsx                   <- Client Component; barra de filtros
src/lib/services/<dominio>-service.ts      <- queries de leitura (reutiliza api-client)
src/types/<dominio>.ts                     <- tipos do dominio (se ainda nao existirem)
```

## Regras de montagem

### Header da pagina

Sempre com `PageHeader` de `@/components/app/PageHeader` (criar se nao existir), contendo:
- Titulo (h1)
- Subtitulo opcional
- Acao primaria: `<Button variant="primary"><RiAddLine className="size-4" /> Novo X</Button>`

### Tabela

- Componente: `Table`, `TableHead`, `TableHeaderCell`, `TableBody`, `TableRow`, `TableCell` de `@/components/tremor/Table`.
- Sort/paginacao: `@tanstack/react-table` por tras.
- **Nunca** AG Grid, DataGrid externo, ou tabela HTML crua.
- Celulas com badges de status: `<Badge variant="success|warning|error|neutral">` de `@/components/tremor/Badge`.
- Celulas com valores monetarios: formatadas em pt-BR via `Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' })`.
- Celulas com datas: formatadas via `date-fns` com `locale: ptBR`.

### Filtros

- Campo de busca: `Input` com `RiSearchLine` como `<RiSearchLine className="size-4 text-gray-400" />` dentro de `leftElement` (se o primitivo suportar) ou como adorno ao lado.
- Selects de filtro: `Select` do Tremor.
- Filtro por periodo: `DatePicker` com modo range.
- Zero `<input>` cru, zero `<select>` HTML.

### Estado vazio

Quando a lista estiver vazia, renderizar `<EmptyState />` de `@/components/app/EmptyState` (criar se nao existir) com icone Ri*, titulo, subtitulo e acao primaria.

### Loading

Durante fetch, usar skeleton baseado em `div` com `animate-pulse` do Tailwind + classes de cor Tremor (`bg-gray-100 dark:bg-gray-800`). Nao usar bibliotecas de skeleton externas.

### Dark mode

Obrigatorio. Testar mentalmente cada classe de cor: se nao houver variante `dark:`, esta errado.

## Proibicoes duras

- Nenhum `import` de `lucide-react`, `@heroicons/react`, shadcn, MUI.
- Nenhum valor de cor arbitrario (`text-[#...]`, `bg-red-500` fora da paleta).
- `cx()` nunca `cn()`.
- Strings de UI em **pt-BR**.

## Checkpoint final

Antes de terminar, rodar:

```bash
cd C:\app_gr\frontend && npx tsc --noEmit && npm run lint
```

Se qualquer um falhar, corrigir antes de sinalizar fim da tarefa.
