# qitech.market.rf_compromissadas

> **canonical_table:** `wh_posicao_compromissada`
> **admin:** qitech
> **mapper:** [adapters/admin/qitech/mappers/rf_compromissadas.py](../mappers/rf_compromissadas.py)
> **schedule:** `daily_at 08:00` SP (sincrono via `/netreport/*`)
> **upstream:** `GET /v2/netreport/report/market/rf-compromissadas/{data}` (template `E_REPORT_MARKET` em [endpoints.py](../endpoints.py))

## Visao geral

Posicoes em operacoes **compromissadas** (RF overnight tipico — o FIDC cede
um titulo de RF com compromisso de recompra D+1). Granularidade por `codigo`
interno da operacao na QiTech.

Schema parecido com `market.rf`, com diferencas relevantes que justificam
adapter/mapper proprio (ver Gotchas):

- SEM `emitente` / `cnpjEmitente` / `codigoLastro` (compromissada nao
  carrega esses metadados — sao do papel-lastro original).
- Em vez de `dataDaEmissão`/`dataAplicação`, traz par
  `dataAquisição`/`dataResgate` (datas da propria operacao compromissada).
- `valorAplicado`/`valorResgate` carregam semantica diferente — sao os
  valores da operacao compromissada (PU x quantidade no dia da aquisicao /
  no dia do resgate), nao do papel-lastro.
- Cadencia historicamente irregular — `endpoint_catalog.py` comenta que
  "rf_compromissadas tem cadencia irregular" e e candidato a tolerancia
  customizada.

Fluxo **sincrono** (familia `/netreport/*`): GET retorna JSON imediatamente
com envelope `{"relatórios": {"rf-compromissadas": [...]}}`. Disparo via
`etl.py::sync_rf_compromissadas` → `_sync_endpoint("rf-compromissadas", ...)`.

## Shape do payload

**Formato:** JSON. **Encoding:** UTF-8 (chaves acentuadas mantidas).
**Locale:** ISO-8601 com `Z` para datas; numeros como int/float/string.
**Envelope:**

```
{
  "relatórios": {
    "rf-compromissadas": [
      { ...item... },
      ...
    ]
  }
}
```

### Estrutura de cada `item`

```
clienteId             string
clienteNome           string
cpfDoCliente          string  (CNPJ do fundo titular)
código                string  (codigo interno da operacao — chave de source_id)
papel                 string  (nome do papel-lastro, ex.: "LFT 030328")
dataAquisição         string ISO-8601  (data de inicio da compromissada)
dataResgate           string ISO-8601  (data de fim da compromissada, normalmente D+1)
dataEmissão           string ISO-8601  (data de emissao do papel-lastro)
dataVencimento        string ISO-8601  (vencimento do papel-lastro)
dataDaPosição         string ISO-8601  (mapeado para source_updated_at)
taxaOver              number | string
taxaAno               number | string
quantidade            number | string
pu                    number | string  (PU unitario — diferente de `puMercado` em rf)
valorAplicado         number | string
valorResgate          number | string
valorBruto            number | string
percentualSobreRf     number | string  (case diferente de rf: aqui "Rf" minusculo, em rf e "RF")
percentualSobreTotal  number | string
mtm                   string | null
negociação/vencimento string | null
```

## Exemplo (anonimizado)

```json
{
  "relatórios": {
    "rf-compromissadas": [
      {
        "clienteId": "4532551",
        "clienteNome": "FIDC EXEMPLO MULTISETORIAL",
        "cpfDoCliente": "12345678000190",
        "código": "B811154",
        "papel": "LFT 010331",
        "dataAquisição": "2026-05-14T00:00:00.000Z",
        "dataResgate": "2026-05-15T00:00:00.000Z",
        "dataEmissão": "2024-03-15T00:00:00.000Z",
        "dataVencimento": "2031-03-01T00:00:00.000Z",
        "dataDaPosição": "2026-05-15T00:00:00.000Z",
        "taxaOver": "0.000412",
        "taxaAno": "0.105200",
        "quantidade": "10.000000",
        "pu": "15234.567890",
        "valorAplicado": "152345.67",
        "valorResgate": "152387.89",
        "valorBruto": "42.22",
        "percentualSobreRf": "8.50",
        "percentualSobreTotal": "5.10",
        "mtm": null,
        "negociação/vencimento": "vencimento"
      }
    ]
  }
}
```

## Gotchas

- **Comparado a `market.rf`:**
  - Sem `emitente`/`cnpjEmitente`/`codigoLastro` (papel-lastro identificado
    apenas em `papel`).
  - `pu` (sem sufixo Mercado) em vez de `puMercado`.
  - `percentualSobreRf` com case **diferente** de `market.rf` — la e
    `percentualSobreRF` (maiusculo). Mapper consome o caso correto para
    cada endpoint; replicar errado quebra silenciosamente.
  - SEM `valorImpostos`/`valorLiquido` (operacao curta, sem retencao
    documentada no payload).
  - SEM `taxaMTM` (compromissada nao tem MTM proprio — o papel-lastro tem).
  - SEM `origem`/`operaçãoATermo` (sempre operacao a termo por natureza).
- **Chaves acentuadas:** `relatórios`, `código`, `dataAquisição`,
  `dataEmissão`, `dataDaPosição`, `negociação/vencimento`.
- **Cadencia irregular:** historicamente publica em horarios diferentes do
  resto dos market reports — `rf_compromissadas` e candidato a tolerancia
  customizada se aparecerem furos sistematicos (ver comentario em
  `endpoint_catalog.py`).
- **`dataAquisição` ≠ `dataAplicação`:** semantica diferente. Em `rf`,
  `dataAplicação` e quando o fundo comprou o papel. Em
  `rf-compromissadas`, `dataAquisição` e quando o fundo entrou na operacao
  compromissada (normalmente D-1 da posicao).
- **Datas ISO-8601 com `Z`:** mapper extrai apenas `date` via
  `_parse_date_or_none`. Hora descartada.
- **Empty/sem dados:** `relatorios["rf-compromissadas"]` vazio/ausente →
  mapper devolve `[]`. Raw ainda persistido para coverage.

## Mapping campo do payload → coluna do silver (`wh_posicao_compromissada`)

| Campo (payload)         | Tipo (payload)      | Coluna (silver)              | Tipo (silver) | Transformacao         |
| ----------------------- | ------------------- | ---------------------------- | ------------- | --------------------- |
| `clienteId`             | string              | `carteira_cliente_id`        | text          | str(...)              |
| `clienteNome`           | string              | `carteira_cliente_nome`      | text          | str(...)              |
| `cpfDoCliente`          | string              | `carteira_cliente_doc`       | text          | str(...)              |
| `código`                | string              | `codigo`                     | text          | str(...) — chave src  |
| `papel`                 | string              | `papel`                      | text          | str(...)              |
| `dataAquisição`         | string ISO-8601     | `data_aquisicao`             | date          | parse_iso_or_none → date |
| `dataResgate`           | string ISO-8601     | `data_resgate`               | date          | parse_iso_or_none → date |
| `dataEmissão`           | string ISO-8601     | `data_emissao`               | date          | parse_iso_or_none → date |
| `dataVencimento`        | string ISO-8601     | `data_vencimento`            | date          | parse_iso_or_none → date |
| `taxaOver`              | number\|string      | `taxa_over`                  | numeric       | to_decimal            |
| `taxaAno`               | number\|string      | `taxa_ano`                   | numeric       | to_decimal            |
| `quantidade`            | number\|string      | `quantidade`                 | numeric       | to_decimal            |
| `pu`                    | number\|string      | `pu`                         | numeric       | to_decimal            |
| `valorAplicado`         | number\|string      | `valor_aplicado`             | numeric       | to_decimal            |
| `valorResgate`          | number\|string      | `valor_resgate`              | numeric       | to_decimal            |
| `valorBruto`            | number\|string      | `valor_bruto`                | numeric       | to_decimal            |
| `percentualSobreRf`     | number\|string      | `percentual_sobre_rf`        | numeric       | to_decimal            |
| `percentualSobreTotal`  | number\|string      | `percentual_sobre_total`     | numeric       | to_decimal            |
| `mtm`                   | string\|null        | `mtm`                        | text\|null    | normalize_str_or_none |
| `negociação/vencimento` | string\|null        | `negociacao_vencimento`      | text\|null    | normalize_str_or_none |
| `dataDaPosição`         | string ISO-8601     | (provenance) `source_updated_at` | timestamptz | parse_iso_or_none |
| _(param)_ `data_posicao` | _                  | `data_posicao`               | date          | passado pelo caller   |

### Source-id (UQ no upsert)

```
{clienteId}|{codigo}|{data_posicao_iso}
```

Mesma estrutura do `market.rf` — `clienteId` separa carteiras (multi-UA),
`codigo` separa posicoes dentro da carteira.

## Historico

- Preencher quando QiTech mudar payload.
