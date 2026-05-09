---
name: create-form-page
description: Cria uma nova pagina de formulario (criar ou editar registro) usando Tremor Raw, react-hook-form e zod. Use quando o usuario pedir "cria um formulario de X", "tela de cadastro de Y", "edicao de Z".
---

# create-form-page

Use para qualquer pagina cuja funcao principal e **criar ou editar um registro**.

## Pre-condicao obrigatoria

Ler `CLAUDE.md` na raiz do monorepo. Regras nao-negociaveis.

> **🔓 Modo Iteracao de Design ativo** (ver banner em `CLAUDE.md` raiz):
> Durante este periodo, ao criar pagina nova:
> - Valores arbitrarios de Tailwind aceitaveis (`text-[Npx]`, `rounded-[Npx]`, `gap-[Npx]`).
> - Hex literals e `rgba(...)` aceitaveis em codigo de componente/surface.
> - Inline styles `style={{...}}` aceitaveis para efeitos especificos do handoff.
> - Cores Tailwind fora da paleta canonica §4 aceitaveis quando do handoff.
> - **Continuam invioaveis**: §2 stack, §3 6 camadas, §11.6 hierarquia 3 niveis, idioma pt-BR, formulario sempre via `react-hook-form` + `zod`.
> Lock-down volta com promocao a tokens nomeados.

## Informacoes a coletar

1. **Dominio** + operacao (criar / editar / ambos via rota dinamica).
2. **Campos** — nome, tipo (texto, numero, moeda, data, select, checkbox, textarea, radio, switch), obrigatoriedade, regras de validacao.
3. **Endpoint** — POST/PUT para onde.
4. **Comportamento pos-submit** — redirect para detalhe? voltar para lista? toast?
5. **Valor inicial** — em modo edicao, onde buscar o registro.

## Estrutura a produzir

```
src/app/(app)/<dominio>/novo/page.tsx           <- criar
src/app/(app)/<dominio>/[id]/editar/page.tsx    <- editar (se aplicavel)
src/app/(app)/<dominio>/_components/
    <Dominio>Form.tsx                           <- Client Component; o formulario compartilhado
src/lib/services/<dominio>-service.ts           <- adicionar create/update
src/lib/schemas/<dominio>-schema.ts             <- schema zod compartilhado
src/types/<dominio>.ts                          <- tipos inferidos do schema
```

## Regras de montagem

### Schema

Arquivo dedicado em `src/lib/schemas/`. Usar `z.object({...})`. Tipos inferidos via `z.infer<typeof Schema>`. Schema vive fora do componente para ser reutilizado por backend-facing types.

### Componentes de input permitidos

| Tipo | Componente Tremor |
|---|---|
| Texto curto | `Input` |
| Senha | `Input type="password"` |
| Numero / moeda | `Input type="number"` (`enableStepper` ativa steppers) |
| Data | `DatePicker` |
| Texto longo | `Textarea` |
| Escolha unica (dropdown) | `Select` |
| Escolha unica (visivel) | `RadioGroup` |
| Boolean (toggle) | `Switch` |
| Boolean (checkbox) | `Checkbox` |

**Proibido:** `<input>`, `<select>`, `<textarea>` HTML crus.

### Layout

Usar `FormLayout` de `@/design-system/components/FormLayout` (criar se nao existir). Contem:
- `PageHeader` (reutilizado).
- Agrupamento de campos em secoes semanticas (cada secao com titulo h2 opcional).
- Rodape fixo com botoes de acao: `<Button variant="secondary">Cancelar</Button> <Button type="submit" variant="primary">Salvar</Button>`.

### Feedback

- Erros de validacao: abaixo do campo, classe de cor herdada do primitivo Tremor (nao pintar erro ad-hoc).
- Sucesso: toast via `sonner` (ja instalado). Mensagem em pt-BR.
- Erro de servidor: toast + manter valores no form.

### Estado de loading

Botao `Submit` entra em `disabled` + spinner (`RiLoader4Line className="animate-spin"`) durante submit.

## Regras de codigo

- Form sempre dentro de `<FormProvider>` (de `react-hook-form`) quando usar `useFormContext` em filhos. Caso contrario, `useForm` direto no componente.
- `zodResolver` do pacote `@hookform/resolvers/zod`. **Nao** reinventar resolver.
- Mensagens de erro em pt-BR dentro do schema.

## Proibicoes duras

- Nenhum form HTML cru.
- Nenhuma biblioteca alternativa (Formik, react-final-form).
- Nenhuma cor arbitraria.

## Checkpoint final

`npx tsc --noEmit && npm run lint && npm run build`. Todos devem passar.
