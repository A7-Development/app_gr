# QiTech — Catálogo de payload shapes

Documentação canônica do **shape** de cada endpoint QiTech consumido pelo
sistema. Resolve uma pergunta antiga: "quando a QiTech mudar algum payload
ou eu abrir um adapter novo, onde está a fonte de verdade do que ESTE
endpoint retorna?"

**Escopo:** 17 endpoints declarados em
[`endpoint_catalog.py`](../endpoint_catalog.py). Cada endpoint tem um arquivo
`<endpoint_name>.md` neste diretório com a mesma estrutura.

## Por que existe (CLAUDE.md §14 — proveniência transversal)

O sistema é multi-tenant e multi-administradora. Hoje só temos QiTech, mas
quando entrar Kanastra / BTG / outras, cada admin terá seu próprio catálogo
de payload shapes (`adapters/admin/<admin>/payload_shapes/`).

Cada arquivo aqui responde:

- **O que esse endpoint retorna?** — shape completo, campos, tipos, locale.
- **Quais valores são especiais?** — null/zero/vazio/sentinelas.
- **Como vira silver?** — mapping linha-a-linha pra coluna do `wh_*`.
- **Quando o vendor mudou algo?** — seção "Histórico" registra mudanças.

## Estrutura canônica de cada arquivo

```markdown
# <endpoint_global_id>

> **canonical_table:** `wh_xxxxx`
> **admin:** qitech
> **mapper:** [adapters/admin/qitech/mappers/xxxxx.py](../mappers/xxxxx.py)
> **schedule:** daily_at HH:MM SP / interval N min / on_demand
> **upstream:** GET /netreport/... (ou POST async + webhook)

## Visão geral

1-2 parágrafos: pra que serve esse relatório, qual fluxo (sync/async),
cadência típica de publicação pela QiTech.

## Shape do payload

Formato (JSON / CSV / outro), encoding, separador, locale.

### Estrutura

Lista hierárquica dos campos top-level + nested. Tipo de cada campo +
indicação de obrigatório/opcional.

## Exemplo (anonimizado)

Bloco \`\`\`json ou \`\`\`csv com 1-2 linhas reais sanitizadas.

## Gotchas

- Locale BR (vírgula decimal, dd/mm/yyyy).
- Campos opcionais que vêm vazios.
- Sentinelas (zero vs null vs "SIM"/"NAO").
- Pares ativo/passivo, agregações implícitas, etc.

## Mapping campo do payload → coluna do silver

| Campo (payload) | Tipo (payload) | Coluna (silver `wh_xxx`) | Tipo (silver) | Transformação |
|---|---|---|---|---|
| `seuNumero` | string | `seu_numero` | text | strip |
| `valorNominal` | string "3600,00" | `valor_nominal` | numeric(18,2) | parse_decimal_br |
| ... | ... | ... | ... | ... |

## Histórico

- **YYYY-MM-DD:** descrição da mudança (campo novo / renomeado / removido).
```

## Como atualizar

Quando a QiTech mudar algo (ou descobrir que um campo tem semântica
diferente do esperado):

1. Atualize o `mapper` correspondente em `adapters/admin/qitech/mappers/`.
2. Atualize o `.md` aqui com a mudança + entrada em "Histórico".
3. Se a coluna do silver mudou → migration Alembic.
4. Se quebra contrato com features downstream → comunicar antes do deploy.

A fonte de verdade do shape **é o mapper** (código). Este diretório é a
**documentação derivada** — quando divergir, mapper vence, atualizar o `.md`.
