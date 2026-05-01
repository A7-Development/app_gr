---
name: create-list-page
description: Cria uma nova pagina de listagem (index/busca/tabela) usando Tremor Raw no padrao do projeto. Use quando o usuario pedir "cria uma pagina de listagem de X", "index de Y", "tela de listagem", "grade de registros".
---

# create-list-page

Use esta skill para criar qualquer pagina cuja funcao principal e **listar registros com busca/filtro/paginacao**.

## Pre-condicao obrigatoria

Ler `CLAUDE.md` na raiz do monorepo antes de qualquer coisa. As regras de design system sao nao-negociaveis.

> **🔓 Modo Iteracao de Design ativo** (ver banner em `CLAUDE.md` raiz):
> Durante este periodo, ao criar pagina nova:
> - Valores arbitrarios de Tailwind aceitaveis (`text-[Npx]`, `rounded-[Npx]`, `gap-[Npx]`).
> - Hex literals e `rgba(...)` aceitaveis em codigo de componente/surface.
> - Inline styles `style={{...}}` aceitaveis para efeitos especificos do handoff.
> - Cores Tailwind fora da paleta canonica §4 aceitaveis quando do handoff.
> - **Continuam invioaveis**: §2 stack, §3 6 camadas, §11.6 hierarquia 3 niveis, idioma pt-BR.
> Lock-down volta com promocao a tokens nomeados.

## Decisao 0 — qual PATTERN aplicar (CLAUDE.md §7)

**Patterns sao o ponto de partida canonico.** Toda pagina de listagem nasce de um arquivo em `frontend/src/design-system/patterns/` (copy-paste-edit), nao do zero.

| Caracteristica da listagem | Pattern | Primeira instancia |
|---|---|---|
| Dados de DOMINIO (cessoes, sacados, eventos — sistema gera) com drill-down de leitura | `ListagemComDrilldown` | (varias) |
| CRUD admin de cadastros tabulares (usuarios, etiquetas, credenciais) — comparacao linha-a-linha | `ListagemCrudInline` | `/admin/ia/providers` |
| CRUD admin de cadastros visuais (workflows, agentes, dashboards salvos) — icone + descricao + meta | `ListagemCrudCards` | `/credito/workflows` |
| Variante de inline com expand inline (detail dentro da row) | `ListagemCrudExpand` | (raro) |

**Como decidir entre `ListagemCrudInline` e `ListagemCrudCards`:**

- Se cada entidade ganha sendo **comparada linha-a-linha** (mesmas colunas estruturadas, ex.: aliases, datas, contagens) → `ListagemCrudInline` com `<DataTableShell>`.
- Se cada entidade tem **identidade visual heterogenea** (icone identitario, descricao livre, badges variados, metadata multi-eixo) → `ListagemCrudCards` com `<EntityCard>`.

Em duvida, prefira `ListagemCrudInline` — tabela e mais densa, mais escalavel e mais facil de filtrar/ordenar. Cards exigem espaco e sao mais lentos pra escanear em volume.

**Como aplicar o pattern:**

1. Copie o arquivo do pattern (ex.: `patterns/ListagemCrudCards.tsx`) pra `app/(app)/<dominio>/<rota>/page.tsx`.
2. Siga os comentarios `HOW TO ADAPT:` no topo do pattern — eles dizem exatamente o que trocar.
3. Mantenha PageHeader, container outer, URL state convention, drawers/dialogs intactos. Custom o tipo de dominio, mock data, EntityCard/columns, e mutations.

## Informacoes a coletar (via AskUserQuestion se nao vieram no pedido)

1. **Nome do dominio** (ex.: "contratos", "fornecedores") — define o segmento de rota e a pasta.
2. **Pattern aplicavel** — confirmar a decisao acima com o usuario se nao for obvia.
3. **Colunas da tabela / campos do EntityCard** — nome + tipo (texto, numero, moeda, data, badge de status, acao).
4. **Filtros** — quais campos filtram a lista? (ex.: status, periodo, categoria) — alimentam SegmentSwitch e/ou FilterChip.
5. **Origem dos dados** — endpoint da API (se ja existir) ou mock temporario.
6. **Acoes por linha/card** — editar, excluir, visualizar, exportar? Quais?
7. **Acao do header** — botao "+ Novo X"? Exportar lista?

## Estrutura a produzir

A estrutura de pasta segue o pattern escolhido. Em geral:

```
src/app/(app)/<dominio>/<rota>/page.tsx          <- copia adaptada do pattern
src/app/(app)/<dominio>/<rota>/_components/
    <X>Form.tsx                                  <- form de create/edit usado dentro do DrillDownSheet
                                                    (so quando ListagemCrud* — segue padrao react-hook-form + zod)
    <X>Card.tsx                                  <- so em ListagemCrudCards, se EntityCard for complexo;
                                                    se simples, mantem inline na page.tsx
src/lib/hooks/<dominio>-hooks.ts                 <- React Query hooks (useList, useCreate, useUpdate, useDelete)
src/lib/services/<dominio>-service.ts (opcional) <- queries de leitura (reutiliza api-client)
src/types/<dominio>.ts                            <- tipos do dominio (se ainda nao existirem)
```

**Importante**: nao recrie Table/Filters do zero. O pattern ja vem com:
- `<DataTableShell>` (Inline) ou grid de `<EntityCard>` (Cards) prontos
- FilterSearch + SegmentSwitch + counter integrados
- DrillDownSheet de create/edit com URL state (?action=new / ?selected=<id>)
- Dialog destrutivo com state local
- EmptyState e ErrorState canonicos

## Regras de montagem

### Header da pagina

Sempre com `PageHeader` de `@/design-system/components/PageHeader` (criar se nao existir), contendo:
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

Quando a lista estiver vazia, renderizar `<EmptyState />` de `@/design-system/components/EmptyState` (criar se nao existir) com icone Ri*, titulo, subtitulo e acao primaria.

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
