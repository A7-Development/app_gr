---
name: create-detail-page
description: Cria uma pagina de detalhe/visualizacao de um registro unico usando Tremor Raw. Use quando o usuario pedir "tela de detalhe de X", "pagina de visualizacao de Y", "ficha do registro Z".
---

# create-detail-page

Pagina read-only (ou com acoes pontuais) que mostra **um registro unico** em profundidade.

## Pre-condicao obrigatoria

Ler `CLAUDE.md` na raiz. Regras nao-negociaveis.

## Informacoes a coletar

1. **Dominio** e o identificador da rota (`[id]`, `[slug]`).
2. **Secoes** — como agrupar os dados (ex.: "Dados gerais", "Faturamento", "Historico")?
3. **Dados relacionados** — mostrar listas menores dentro do detalhe? charts de historico?
4. **Acoes de topo** — editar? excluir? exportar? aprovar?
5. **Breadcrumb** — qual o caminho ate esta pagina?

## Estrutura a produzir

```
src/app/(app)/<dominio>/[id]/page.tsx           <- Server Component; loader
src/app/(app)/<dominio>/[id]/_components/
    <Dominio>Summary.tsx                        <- cabecalho com info essencial
    <Dominio>Section<Nome>.tsx                  <- por secao
src/lib/services/<dominio>-service.ts           <- adicionar getById
```

## Regras de montagem

### Header

`PageHeader` com:
- Breadcrumb opcional (via `<Breadcrumb />` de `@/design-system/components/` — criar se nao existir).
- Titulo (nome do registro).
- Badge de status ao lado do titulo, se aplicavel.
- Acoes secundarias/primarias: sempre via `Button` ou `DropdownMenu` do Tremor.

### Blocos de conteudo

Cada secao e um `Card` do Tremor. Dentro do card:
- Titulo h2 (classe herdada, nunca `text-[18px]` ad-hoc).
- Grid de pares "label + valor" com `<Label>` do Tremor + `<span>` de valor.
- Para listas internas (ex.: itens do contrato): `Table` do Tremor em versao compacta.
- Para historico/evolucao: `AreaChart` ou `LineChart` de `@/components/charts/`.

### Separadores

`Divider` do Tremor. Nunca `<hr>` cru.

### Acoes destrutivas

Excluir / arquivar / cancelar sempre abrem `Dialog` do Tremor como confirmacao. **Nunca** `window.confirm`. Botao de confirmacao: `variant="destructive"`.

### Estado de loading / erro

- Loading: skeleton baseado em `animate-pulse` com cores Tremor.
- 404: componente `<NotFoundState />` de `@/design-system/components/` com icone Ri*, titulo e link de volta.
- Erro: `<ErrorState />` com `RiErrorWarningLine` e retry.

## Proibicoes duras

- Sem `<hr>`, `<button>` cru, `<dialog>` cru.
- Sem cor arbitraria.
- Sem charts externos ao `src/components/charts/`.

## Checkpoint final

`npx tsc --noEmit && npm run lint && npm run build`.
