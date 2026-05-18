# qitech.market.rf

> **canonical_table:** `wh_posicao_renda_fixa`
> **admin:** qitech
> **mapper:** [adapters/admin/qitech/mappers/rf.py](../mappers/rf.py)
> **schedule:** `daily_at 08:00` SP (sincrono via `/netreport/*`)
> **upstream:** `GET /v2/netreport/report/market/rf/{data}` (template `E_REPORT_MARKET` em [endpoints.py](../endpoints.py))

## Visao geral

Posicoes de renda fixa do FIDC numa data de referencia D-1 — titulos publicos
(LFT, LTN, NTN-B), debentures, CDBs, LCAs etc. Granularidade por **codigo
interno da operacao** (`codigo`, ex.: "C274830", "B811154") — uma linha por
papel em carteira na data alvo.

Fluxo **sincrono** (familia `/netreport/*`): GET retorna JSON imediatamente
com envelope `{"relatorios": {"rf": [...]}}` ou variante acentuada
`{"relatórios": {"rf": [...]}}` — o mapper le com chave acentuada
(`payload["relatórios"]`).

Disparo via `etl.py::sync_rf` → `_sync_endpoint("rf", ...)` → mapper consome o
array sob `relatorios["rf"]`.

## Shape do payload

**Formato:** JSON. **Encoding:** UTF-8 (com chaves acentuadas — `relatórios`,
`código`, `dataDaEmissão`, etc.).
**Locale:** ISO-8601 com sufixo `Z` para datas; numeros como int/float/string
(o mapper aceita as tres formas via `to_decimal`).
**Envelope:**

```
{
  "relatórios": {
    "rf": [
      { ...item... },
      ...
    ]
  }
}
```

### Estrutura de cada `item`

Lista exaustiva dos campos consumidos pelo mapper (campos extras no payload
sao ignorados — apenas o que aparece abaixo vira silver):

```
clienteId             string  (ID interno da carteira na QiTech)
clienteNome           string
cpfDoCliente          string  (CNPJ do fundo titular)
código                string  (codigo interno da operacao — chave de source_id)
nomeDoPapel           string
Emitente              string  (nota: capital inicial — mantida como esta no payload)
cnpjEmitente          string
códigoLastro          string
indexador             string  (ex.: "CDI", "IPCA+", "PRE")
dataDaEmissão         string ISO-8601
dataAplicação         string ISO-8601
dataVencimento        string ISO-8601
dataVencimentoLastro  string ISO-8601 | null
dataDaPosição         string ISO-8601 (mapeado para source_updated_at)
origem                string | null
operaçãoATermo        string | null
negociação/vencimento string | null    (chave contem barra "/")
taxaMTM               number | string
taxaOver              number | string
taxaAno               number | string
quantidade            number | string
puMercado             number | string
valorAplicado         number | string
valorResgate          number | string
valorBruto            number | string
valorImpostos         number | string
valorLíquido          number | string
percentualSobreRF     number | string
percentualSobreTotal  number | string
mtm                   string | null  (label/categoria, NAO valor numerico)
```

## Exemplo (anonimizado)

```json
{
  "relatórios": {
    "rf": [
      {
        "clienteId": "4532551",
        "clienteNome": "FIDC EXEMPLO MULTISETORIAL",
        "cpfDoCliente": "12345678000190",
        "código": "C274830",
        "nomeDoPapel": "LFT 010331",
        "Emitente": "TESOURO NACIONAL",
        "cnpjEmitente": "00394460000141",
        "códigoLastro": "",
        "indexador": "SELIC",
        "dataDaEmissão": "2024-03-15T00:00:00.000Z",
        "dataAplicação": "2025-11-10T00:00:00.000Z",
        "dataVencimento": "2031-03-01T00:00:00.000Z",
        "dataVencimentoLastro": null,
        "dataDaPosição": "2026-05-15T00:00:00.000Z",
        "origem": "compra",
        "operaçãoATermo": "NAO",
        "negociação/vencimento": "vencimento",
        "taxaMTM": "0.000123",
        "taxaOver": "0.000412",
        "taxaAno": "0.105200",
        "quantidade": "10.000000",
        "puMercado": "15234.567890",
        "valorAplicado": "150000.00",
        "valorResgate": "152345.67",
        "valorBruto": "2345.67",
        "valorImpostos": "528.78",
        "valorLíquido": "1816.89",
        "percentualSobreRF": "12.34",
        "percentualSobreTotal": "8.20",
        "mtm": null
      }
    ]
  }
}
```

## Gotchas

- **Chaves acentuadas:** `relatórios`, `código`, `dataDaEmissão`,
  `dataAplicação`, `dataDaPosição`, `códigoLastro`, `operaçãoATermo`,
  `negociação/vencimento`, `valorLíquido`. O mapper le **exatamente** com
  acento — se a QiTech um dia normalizar pra ASCII, vira regressao silenciosa
  (mapper devolve 0/None pra todos os campos).
- **`negociação/vencimento`:** unica chave do payload QiTech que contem `/`.
  Mantida como esta no `item.get(...)`.
- **`Emitente` (capital inicial):** todas as outras chaves comecam com
  minuscula — esta nao. Documentado por seguranca.
- **`mtm` (campo):** string/null (label como "MTM" ou null) — NAO confundir
  com `taxaMTM` (numero). O silver guarda os dois separados.
- **Datas ISO-8601 com `Z`:** `parse_iso_or_none` aceita; o mapper extrai
  apenas a `date` (sem TZ) via `_parse_date_or_none`. Hora descartada.
- **Numeros como string:** alguns campos vem como string ("0.000123") em vez
  de number. `to_decimal` aceita ambos via `Decimal(str(value))`.
- **Empty/sem dados:** se `relatorios["rf"]` for vazio/ausente, mapper devolve
  `[]`. `_sync_endpoint` no `etl.py` ainda persiste o raw com http_status pra
  o coverage classificar como NOT_PUBLISHED — nao e erro.
- **Source-id:** `{clienteId}|{codigo}|{YYYY-MM-DD}`. `clienteId` separa
  carteiras dentro do mesmo tenant (multi-UA); `codigo` separa posicoes dentro
  da carteira.

## Mapping campo do payload → coluna do silver (`wh_posicao_renda_fixa`)

| Campo (payload)         | Tipo (payload)      | Coluna (silver)            | Tipo (silver) | Transformacao         |
| ----------------------- | ------------------- | -------------------------- | ------------- | --------------------- |
| `clienteId`             | string              | `carteira_cliente_id`      | text          | str(...)              |
| `clienteNome`           | string              | `carteira_cliente_nome`    | text          | str(...)              |
| `cpfDoCliente`          | string              | `carteira_cliente_doc`     | text          | str(...)              |
| `código`                | string              | `codigo`                   | text          | str(...) — chave src  |
| `nomeDoPapel`           | string              | `nome_do_papel`            | text          | str(...)              |
| `Emitente`              | string              | `emitente`                 | text          | str(...)              |
| `cnpjEmitente`          | string              | `cnpj_emitente`            | text          | str(...)              |
| `códigoLastro`          | string              | `codigo_lastro`            | text          | str(...)              |
| `indexador`             | string              | `indexador`                | text          | str(...)              |
| `dataDaEmissão`         | string ISO-8601     | `data_da_emissao`          | date          | parse_iso_or_none → date |
| `dataAplicação`         | string ISO-8601     | `data_aplicacao`           | date          | parse_iso_or_none → date |
| `dataVencimento`        | string ISO-8601     | `data_vencimento`          | date          | parse_iso_or_none → date |
| `dataVencimentoLastro`  | string ISO-8601\|null | `data_vencimento_lastro`  | date\|null    | parse_iso_or_none → date |
| `origem`                | string\|null        | `origem`                   | text\|null    | normalize_str_or_none |
| `operaçãoATermo`        | string\|null        | `operacao_a_termo`         | text\|null    | normalize_str_or_none |
| `negociação/vencimento` | string\|null        | `negociacao_vencimento`    | text\|null    | normalize_str_or_none |
| `taxaMTM`               | number\|string      | `taxa_mtm`                 | numeric       | to_decimal            |
| `taxaOver`              | number\|string      | `taxa_over`                | numeric       | to_decimal            |
| `taxaAno`               | number\|string      | `taxa_ano`                 | numeric       | to_decimal            |
| `quantidade`            | number\|string      | `quantidade`               | numeric       | to_decimal            |
| `puMercado`             | number\|string      | `pu_mercado`               | numeric       | to_decimal            |
| `valorAplicado`         | number\|string      | `valor_aplicado`           | numeric       | to_decimal            |
| `valorResgate`          | number\|string      | `valor_resgate`            | numeric       | to_decimal            |
| `valorBruto`            | number\|string      | `valor_bruto`              | numeric       | to_decimal            |
| `valorImpostos`         | number\|string      | `valor_impostos`           | numeric       | to_decimal            |
| `valorLíquido`          | number\|string      | `valor_liquido`            | numeric       | to_decimal            |
| `percentualSobreRF`     | number\|string      | `percentual_sobre_rf`      | numeric       | to_decimal            |
| `percentualSobreTotal`  | number\|string      | `percentual_sobre_total`   | numeric       | to_decimal            |
| `mtm`                   | string\|null        | `mtm`                      | text\|null    | normalize_str_or_none |
| `dataDaPosição`         | string ISO-8601     | (provenance) `source_updated_at` | timestamptz | parse_iso_or_none |
| _(param)_ `data_posicao` | _                  | `data_posicao`             | date          | passado pelo caller   |

### Source-id (UQ no upsert)

```
{clienteId}|{codigo}|{data_posicao_iso}
```

`clienteId` na QiTech e o codigo interno da carteira (multi-UA dentro do
mesmo tenant). `codigo` e unico por posicao + data — uma cessao de RF pode
mudar de codigo entre datas se houver corporate action.

## Historico

- Preencher quando QiTech mudar payload.
