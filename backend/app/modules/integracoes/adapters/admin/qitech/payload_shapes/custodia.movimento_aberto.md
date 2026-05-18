# qitech.custodia.movimento_aberto

> **canonical_table:** `wh_movimento_aberto`
> **admin:** qitech
> **mapper:** [adapters/admin/qitech/mappers/movimento_aberto.py](../mappers/movimento_aberto.py)
> **schedule:** `daily_at 10:00` SP (sincrono via `/v2/fidc-custodia/*`)
> **upstream:** `GET /v2/fidc-custodia/report/movimento-aberto/{cnpj}/` (handler em [custodia.py::sync_movimento_aberto](../custodia.py))

## Visao geral

Snapshot **atual** de cessoes em aberto (pendentes de liquidacao) do FIDC.
Sem data no path — cada chamada e uma foto do estado naquele momento.
Granularidade por movimento aberto.

Cada disparo diario forma uma serie temporal de snapshots — o silver
`wh_movimento_aberto` mantem `data_referencia` (data da fetch) na PK do
`source_id` para que snapshots de dias diferentes coexistam.

Schema baseado em **spec passada pelo usuario em 2026-04-25** — o sample real
veio vazio. Quando aparecer dado real, validar tipos no mapper.

## Shape do payload

**Formato:** JSON. **Encoding:** UTF-8.
**Locale:** ISO-8601 para datas; numeros como int/float/string.
**Envelope:**

```
{
  "movimentoAberto": [
    { ...item... },
    ...
  ]
}
```

### Estrutura de cada `item`

(Schema inferido da spec — nao validado contra dado real ainda.)

```
docFundo            string CNPJ  (do fundo titular)
nomeFundo           string
seuNumero           string | int   (mapper normaliza pra string)
numeroDocumento     string
tipoMovimento       string
valorAquisicao      number | string
valorNominal        number | string
valorMovimentacao   number | string
dataMovimento       string ISO-8601  (mapeado para source_updated_at)
dataVencimento      string ISO-8601
```

## Exemplo (anonimizado — inferido da spec)

```json
{
  "movimentoAberto": [
    {
      "docFundo": "12345678000190",
      "nomeFundo": "FIDC EXEMPLO MULTISETORIAL",
      "seuNumero": "CES12345",
      "numeroDocumento": "DUP-2024-0001",
      "tipoMovimento": "AQUISICAO",
      "valorAquisicao": 3520.00,
      "valorNominal": 3600.00,
      "valorMovimentacao": 3520.00,
      "dataMovimento": "2026-04-20T00:00:00.000Z",
      "dataVencimento": "2026-06-10T00:00:00.000Z"
    }
  ]
}
```

## Gotchas

- **Schema nao validado contra dado real.** Sample real veio vazio em
  2026-04-25 (REALINVEST). Quando aparecer dado, conferir tipos e ajustar.
  Comportamento nao totalmente claro — investigar quando surgir.
- **Sem data no path:** diferente dos outros endpoints da familia
  `/v2/fidc-custodia/report/*`. Cada chamada e foto do estado AGORA. Mapper
  recebe `data_referencia` por param (default = hoje UTC em
  `sync_movimento_aberto`) que vira `data_referencia` no silver E entra no
  `source_id` — snapshots em datas diferentes nao colidem no upsert.
- **Sem `cedente`/`sacado` no payload (inferido):** spec inicial nao
  contempla esses campos. Se aparecerem em dado real, mapper precisa ser
  estendido — hoje nao captura.
- **`seuNumero` pode vir int:** spec inicial sugere — mapper normaliza
  proativamente via `str(item.get("seuNumero", ""))`.
- **`docFundo` (nao `fundoCnpj`):** diferente das outras tabelas custodia.
  Mapper faz fallback para `cnpj_fundo` por param quando vazio:
  `_normalize_cnpj_any(item.get("docFundo")) or cnpj_fundo_norm`.
- **Empty/sem dados:** `movimentoAberto` vazio/ausente → mapper devolve
  `[]`. Comum em FIDCs com carteira pequena ou em dias sem movimento em
  aberto. Raw ainda persistido para coverage.
- **Snapshot diario forma serie:** consumir o silver com filtro de
  `data_referencia` — sem o filtro, query retorna N x M (N dias x M
  cessoes em aberto). Importante em paginas BI que comparam dia-a-dia.

## Mapping campo do payload → coluna do silver (`wh_movimento_aberto`)

| Campo (payload)     | Tipo (payload)         | Coluna (silver)        | Tipo (silver)  | Transformacao              |
| ------------------- | ---------------------- | ---------------------- | -------------- | -------------------------- |
| `docFundo`          | string CNPJ            | `fundo_doc`            | text           | _normalize_cnpj_any (fallback p/ param) |
| `nomeFundo`         | string                 | `fundo_nome`           | text           | str(...)                   |
| `seuNumero`         | string\|int            | `seu_numero`           | text           | str(...)                   |
| `numeroDocumento`   | string                 | `numero_documento`     | text           | str(...)                   |
| `tipoMovimento`     | string                 | `tipo_movimento`       | text           | str(...)                   |
| `valorAquisicao`    | number\|string         | `valor_aquisicao`      | numeric(18,2)  | to_decimal                 |
| `valorNominal`      | number\|string         | `valor_nominal`        | numeric(18,2)  | to_decimal                 |
| `valorMovimentacao` | number\|string         | `valor_movimentacao`   | numeric(18,2)  | to_decimal                 |
| `dataMovimento`     | string ISO-8601        | `data_movimento`       | date           | parse_iso_or_none → date   |
| `dataMovimento`     | string ISO-8601        | (provenance) `source_updated_at` | timestamptz | parse_iso_or_none |
| `dataVencimento`    | string ISO-8601        | `data_vencimento`      | date           | parse_iso_or_none → date   |
| _(param)_ `data_referencia` | _              | `data_referencia`      | date           | passado pelo caller        |

### Source-id (UQ no upsert)

```
{cnpj_fundo_norm}|{seuNumero}|{numeroDocumento}|abt|{data_referencia_iso}
```

Inclui `data_referencia` (data da fetch) — snapshot diario forma serie
temporal, cada dia gera um novo conjunto de linhas. Sufixo `|abt` distingue
de `|aq`/`|liq` em outras tabelas custodia se um dia o mesmo ID viajar.

## Historico

- **2026-04-25:** schema baseado em spec passada pelo usuario; sample real
  veio vazio. Comportamento nao totalmente claro — investigar quando
  surgirem cessoes em aberto em volume.
- Preencher quando QiTech mudar payload OU quando dado real validar/refutar
  schema atual.
