# qitech.market.outros_ativos

> **canonical_table:** `wh_posicao_outros_ativos`
> **admin:** qitech
> **mapper:** [adapters/admin/qitech/mappers/outros_ativos.py](../mappers/outros_ativos.py)
> **schedule:** `daily_at 08:00` SP (sincrono — GET JSON)
> **upstream:** `GET /v2/netreport/report/market/outros-ativos/{data}`

## Visao geral

Posicoes que nao se encaixam em RF/RV/Fundos do FIDC — tipicamente PDD
(provisao para devedores duvidosos), reservas tecnicas, ajustes contabeis,
custos a apropriar. Uma linha por par `(carteira, codigo)`.

Fluxo **sincrono**. Reconciler usa defaults de market reports.

## Shape do payload

**Formato:** JSON.
**Encoding:** UTF-8.
**Locale:** numericos mistos (int/float/string). Datas ISO-8601 com `Z`.
**Acentuacao:** `relatórios`, `código`, `descrição`, `descriçãoTipoDeAtivo`,
`dataDaPosição`.

### Estrutura

```
{
  "relatórios": {
    "outros-ativos": [
      {
        "dataDaPosição": "2026-01-13T00:00:00.000Z",
        "código": "PDDREAL",
        "descrição": "PDD Recebiveis REALINVEST",
        "tipoDoAtivo": "PDD",
        "descriçãoTipoDeAtivo": "Provisao para Devedores Duvidosos",
        "valorTotal": -125430.12,
        "percentualSobreOutrosAtivos": 100.0000,
        "percentualSobreTotal": -0.51,
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
    "outros-ativos": [
      {
        "dataDaPosição": "2026-05-15T00:00:00.000Z",
        "código": "PDDEXM",
        "descrição": "PDD Recebiveis EXEMPLO",
        "tipoDoAtivo": "PDD",
        "descriçãoTipoDeAtivo": "Provisao para Devedores Duvidosos",
        "valorTotal": -89234.56,
        "percentualSobreOutrosAtivos": 100.0000,
        "percentualSobreTotal": -0.38,
        "cpfDoCliente": "12345678000190",
        "clienteNome": "EXEMPLO FIDC",
        "clienteId": "EXEMPLO"
      }
    ]
  },
  "_links": { "lastAvailableReport": "/v2/netreport/report/market/outros-ativos/2026-05-15" }
}
```

## Gotchas

- **`valor_total` frequentemente negativo**: PDD reduz ativo, vem como
  numero negativo. Schema `Numeric(18,2)` aceita negativos.
- **`percentual_sobre_total` pode ser negativo**: porque o valor e
  negativo. Sem clamp no schema (`Numeric(8,4)`).
- **`tipoDoAtivo` e enum implicito da QiTech** — observado `PDD`. Schema
  `String(20)` absorve novos valores sem migration.
- **"sem dados" -> 400 com body canonico**: igual aos outros markets.
- **Sem `to_decimal_or_none_within` aqui**: se a QiTech devolver lixo
  numerico em percentuais (cenario observado em conta-corrente), este
  mapper estoura. Nao reproduzido em producao ate 2026-05-18.
- **`source_updated_at` parseado de `dataDaPosição`**.

## Mapping campo do payload -> coluna do silver (`wh_posicao_outros_ativos`)

| Campo (payload)                  | Tipo (payload)        | Coluna (silver)                   | Tipo (silver)  | Transformacao        |
|----------------------------------|-----------------------|-----------------------------------|----------------|----------------------|
| `clienteId`                      | string                | `carteira_cliente_id`             | varchar(50)    | str()                |
| `clienteNome`                    | string                | `carteira_cliente_nome`           | varchar(200)   | str()                |
| `cpfDoCliente`                   | string (CNPJ digits)  | `carteira_cliente_doc`            | varchar(14)    | str()                |
| `código`                         | string                | `codigo`                          | varchar(50)    | str()                |
| `descrição`                      | string                | `descricao`                       | varchar(200)   | str()                |
| `tipoDoAtivo`                    | string                | `tipo_do_ativo`                   | varchar(20)    | str()                |
| `descriçãoTipoDeAtivo`           | string                | `descricao_tipo_de_ativo`         | varchar(100)   | str()                |
| `valorTotal`                     | number (signed)       | `valor_total`                     | numeric(18,2)  | to_decimal           |
| `percentualSobreOutrosAtivos`    | number                | `percentual_sobre_outros_ativos`  | numeric(8,4)   | to_decimal           |
| `percentualSobreTotal`           | number (signed)       | `percentual_sobre_total`          | numeric(8,4)   | to_decimal           |
| `dataDaPosição`                  | string ISO-8601       | `source_updated_at` (Auditable)   | timestamptz    | parse_iso_or_none    |
| _(param)_ `data_posicao`         | -                     | `data_posicao`                    | date           | passado pelo caller  |

### Source-id (UQ no upsert)

```
{clienteId}|{código}|{YYYY-MM-DD}
```

## Historico

- **2026-01-13:** shape confirmado contra sample REALINVEST FIDC (PDD).
- Preencher quando QiTech mudar payload.
