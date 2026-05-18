# qitech.market.rentabilidade

> **canonical_table:** `wh_rentabilidade_fundo`
> **admin:** qitech
> **mapper:** [adapters/admin/qitech/mappers/rentabilidade.py](../mappers/rentabilidade.py)
> **schedule:** `daily_at 09:00` SP (sincrono — GET JSON)
> **upstream:** `GET /v2/netreport/report/market/rentabilidade/{data}`

## Visao geral

Metricas de rentabilidade do FIDC por classe de cota e indexador. Cada
linha do payload e uma combinacao `(classe_de_cota, indexador)`. No sample
REALINVEST: 27 linhas = 3 classes x 9 indexadores
(`PATRIMON`, `COTA`, `CDI`, `SEL`, `DOL`, `IBOV FEC`, `IGPM`, `Ctbrpfee`,
`Qtd Cota`, `Vlr Cota`).

`indexador` mantido como `String(20)` no silver — nao enum, absorve novos
indexadores sem migration.

Fluxo **sincrono**. Reconciler usa defaults de market reports.

## Shape do payload

**Formato:** JSON.
**Encoding:** UTF-8.
**Locale:** numericos mistos (int/float/string), as vezes `null`. Datas
ISO-8601 com `Z`.
**Acentuacao:** `relatórios`, `dataDaPosição`, `rentabilidadeDiária`,
`códigoIsin`.

### Estrutura

```
{
  "relatórios": {
    "rentabilidade": [
      {
        "dataDaPosição": "2026-01-13T00:00:00.000Z",
        "indexador": "CDI",
        "percentualBenchMark": 1.2345678,
        "rentabilidadeReal": 0.0512345,
        "rentabilidadeDiária": 0.0512345,
        "rentabilidadeMensal": 1.0234567,
        "rentabilidadeAnual": 12.3456789,
        "rentabilidade6Meses": 6.1234567,
        "rentabilidade12Meses": 12.3456789,
        "valorPatrimonio": null,
        "códigoIsin": "BRREALCTF001",
        "percentual6Meses": 110.4567,
        "percentual12Meses": 105.6789,
        "cpfDoCliente": "42449234000160",
        "clienteNome": "REALINVEST FIDC",
        "clienteId": "REALINVEST"
      },
      {
        "dataDaPosição": "2026-01-13T00:00:00.000Z",
        "indexador": "PATRIMON",
        "percentualBenchMark": null,
        "rentabilidadeReal": null,
        "rentabilidadeDiária": null,
        "rentabilidadeMensal": null,
        "rentabilidadeAnual": null,
        "rentabilidade6Meses": null,
        "rentabilidade12Meses": null,
        "valorPatrimonio": 24850123.45,
        "códigoIsin": null,
        "percentual6Meses": null,
        "percentual12Meses": null,
        "cpfDoCliente": "42449234000160",
        "clienteNome": "REALINVEST FIDC",
        "clienteId": "REALINVEST"
      },
      ...
    ]
  },
  "_links": { ... }
}
```

## Exemplo (anonimizado)

```json
{
  "relatórios": {
    "rentabilidade": [
      {
        "dataDaPosição": "2026-05-15T00:00:00.000Z",
        "indexador": "CDI",
        "percentualBenchMark": 0.0427834,
        "rentabilidadeReal": 0.0421567,
        "rentabilidadeDiária": 0.0421567,
        "rentabilidadeMensal": 0.7823456,
        "rentabilidadeAnual": 11.8901234,
        "rentabilidade6Meses": 5.9876543,
        "rentabilidade12Meses": 11.8901234,
        "valorPatrimonio": null,
        "códigoIsin": "BREXMPCTF001",
        "percentual6Meses": 98.4321,
        "percentual12Meses": 102.1234,
        "cpfDoCliente": "12345678000190",
        "clienteNome": "EXEMPLO FIDC",
        "clienteId": "EXEMPLO"
      },
      {
        "dataDaPosição": "2026-05-15T00:00:00.000Z",
        "indexador": "PATRIMON",
        "percentualBenchMark": null,
        "rentabilidadeReal": null,
        "rentabilidadeDiária": null,
        "rentabilidadeMensal": null,
        "rentabilidadeAnual": null,
        "rentabilidade6Meses": null,
        "rentabilidade12Meses": null,
        "valorPatrimonio": 18923451.12,
        "códigoIsin": null,
        "percentual6Meses": null,
        "percentual12Meses": null,
        "cpfDoCliente": "12345678000190",
        "clienteNome": "EXEMPLO FIDC",
        "clienteId": "EXEMPLO"
      }
    ]
  },
  "_links": { "lastAvailableReport": "/v2/netreport/report/market/rentabilidade/2026-05-15" }
}
```

## Gotchas

- **`indexador` define quais campos vem preenchidos** — semantica nullable
  por indexador:
  - `PATRIMON`: so `valor_patrimonio`. Todos os demais `null`.
  - `COTA`: rentabilidades sim, percentuais e benchmark `null`.
  - `CDI` / `SEL` / `DOL` / `IBOV FEC` / `IGPM`: `percentual_bench_mark`
    + `rentabilidade_real` + demais rentabilidades.
  - Outros indexadores (`Ctbrpfee`, `Qtd Cota`, `Vlr Cota`) — verificar
    comportamento empirico (nao totalmente claro pelo mapper).
- **`to_decimal_or_none` preserva `null`**: diferente dos outros mappers
  (que usam `to_decimal` -> `Decimal("0")`), este mapper precisa preservar
  null porque 0 e null tem semanticas distintas (`0` = "calculado e deu 0",
  `null` = "nao se aplica a esse indexador"). Confundir corromperia o
  warehouse.
- **`rentabilidadeDiária` com acento agudo** (chave `Diária`, nao `Diaria`).
  Atencao se houver inconsistencia historica com `market.mec`
  (`variaçãoDiaria` sem acento agudo) — comportamento nao totalmente claro,
  investigar se aparente divergencia.
- **`códigoIsin` opcional** — `null` ou string. `normalize_str_or_none`
  uniformiza `""` -> `None`.
- **Alta precisao**: `Numeric(12,8)` em todas as metricas — observado max
  7 casas decimais em `percentualBenchMark` no sample. 1 casa de margem.
- **"sem dados"**: payload sem `rentabilidade` na lista retorna `[]`.
- **`source_updated_at` parseado de `dataDaPosição`**.
- **Sem `to_decimal_or_none_within`**: se a QiTech devolver lixo numerico
  em rentabilidades, este mapper estoura. Nao reproduzido em producao
  ate 2026-05-18.

## Mapping campo do payload -> coluna do silver (`wh_rentabilidade_fundo`)

| Campo (payload)         | Tipo (payload)            | Coluna (silver)                  | Tipo (silver)         | Transformacao            |
|-------------------------|---------------------------|----------------------------------|-----------------------|--------------------------|
| `clienteId`             | string                    | `carteira_cliente_id`            | varchar(50)           | str()                    |
| `clienteNome`           | string                    | `carteira_cliente_nome`          | varchar(200)          | str()                    |
| `cpfDoCliente`          | string (CNPJ digits)      | `carteira_cliente_doc`           | varchar(14)           | str()                    |
| `indexador`             | string                    | `indexador`                      | varchar(20)           | str()                    |
| `percentualBenchMark`   | number \| null            | `percentual_bench_mark`          | numeric(12,8) null    | to_decimal_or_none       |
| `rentabilidadeReal`     | number \| null            | `rentabilidade_real`             | numeric(12,8) null    | to_decimal_or_none       |
| `rentabilidadeDiária`   | number \| null            | `rentabilidade_diaria`           | numeric(12,8) null    | to_decimal_or_none       |
| `rentabilidadeMensal`   | number \| null            | `rentabilidade_mensal`           | numeric(12,8) null    | to_decimal_or_none       |
| `rentabilidadeAnual`    | number \| null            | `rentabilidade_anual`            | numeric(12,8) null    | to_decimal_or_none       |
| `rentabilidade6Meses`   | number \| null            | `rentabilidade_6_meses`          | numeric(12,8) null    | to_decimal_or_none       |
| `rentabilidade12Meses`  | number \| null            | `rentabilidade_12_meses`         | numeric(12,8) null    | to_decimal_or_none       |
| `valorPatrimonio`       | number \| null            | `valor_patrimonio`               | numeric(18,2) null    | to_decimal_or_none       |
| `códigoIsin`            | string \| null \| ""      | `codigo_isin`                    | varchar(20) null      | normalize_str_or_none    |
| `percentual6Meses`      | number \| null            | `percentual_6_meses`             | numeric(12,8) null    | to_decimal_or_none       |
| `percentual12Meses`     | number \| null            | `percentual_12_meses`            | numeric(12,8) null    | to_decimal_or_none       |
| `dataDaPosição`         | string ISO-8601           | `source_updated_at` (Auditable)  | timestamptz           | parse_iso_or_none        |
| _(param)_ `data_posicao`| -                         | `data_posicao`                   | date                  | passado pelo caller      |

### Source-id (UQ no upsert)

```
{clienteId}|{indexador}|{YYYY-MM-DD}
```

Inclui `indexador` porque cada classe de cota tem N linhas (uma por
indexador). `clienteId|data` sozinho colidiria.

## Historico

- **2026-01-13:** shape confirmado contra sample REALINVEST FIDC. 27
  linhas (3 classes x 9 indexadores). Politica de nullable por indexador
  documentada — `to_decimal_or_none` introduzido pra distinguir 0 de null.
- Preencher quando QiTech mudar payload.
