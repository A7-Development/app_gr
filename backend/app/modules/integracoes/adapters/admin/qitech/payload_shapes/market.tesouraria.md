# qitech.market.tesouraria

> **canonical_table:** `wh_saldo_tesouraria`
> **admin:** qitech
> **mapper:** [adapters/admin/qitech/mappers/tesouraria.py](../mappers/tesouraria.py)
> **schedule:** `daily_at 07:30` SP (sincrono — GET JSON)
> **upstream:** `GET /v2/netreport/report/market/tesouraria/{data}`

## Visao geral

Saldo em tesouraria do FIDC por classe de cota numa data de referencia.
Cada `clienteId` representa uma classe distinta — ex.: `REALINVEST`,
`REALINVEST MEZ`, `REALINVEST SEN`. Todos com `descricao = "Saldo em
Tesouraria"`; a discriminacao vem do `clienteId`/`clienteNome`.

Fluxo **sincrono**. Reconciler usa defaults de market reports.

## Shape do payload

**Formato:** JSON.
**Encoding:** UTF-8.
**Locale:** numericos mistos (int/float/string). Datas ISO-8601 com `Z`.
**Acentuacao:** `relatórios`, `descrição`, `dataDaPosição`.

### Estrutura

```
{
  "relatórios": {
    "tesouraria": [
      {
        "dataDaPosição": "2026-01-13T00:00:00.000Z",
        "descrição": "Saldo em Tesouraria",
        "valor": 24850123.45,
        "percentualSobreCpr": 99.8745,
        "percentualSobreTotal": 95.42,
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
    "tesouraria": [
      {
        "dataDaPosição": "2026-05-15T00:00:00.000Z",
        "descrição": "Saldo em Tesouraria",
        "valor": 18723451.12,
        "percentualSobreCpr": 95.4012,
        "percentualSobreTotal": 78.92,
        "cpfDoCliente": "12345678000190",
        "clienteNome": "EXEMPLO FIDC",
        "clienteId": "EXEMPLO"
      },
      {
        "dataDaPosição": "2026-05-15T00:00:00.000Z",
        "descrição": "Saldo em Tesouraria",
        "valor": 4521000.00,
        "percentualSobreCpr": 98.1234,
        "percentualSobreTotal": 19.05,
        "cpfDoCliente": "12345678000190",
        "clienteNome": "EXEMPLO MEZ",
        "clienteId": "EXEMPLO_MEZ"
      }
    ]
  },
  "_links": { "lastAvailableReport": "/v2/netreport/report/market/tesouraria/2026-05-15" }
}
```

## Gotchas

- **Multiplas classes de cota**: 1 linha por `clienteId`. O FIDC com 3
  classes (Sub/Mez/Sen) devolve 3 linhas — todas com `descricao` igual
  ("Saldo em Tesouraria"). A unicidade no silver e por `clienteId|data` —
  o `descricao` nao entra no source_id.
- **`percentualSobreCpr` e `percentualSobreTotal` sem clamp**: diferente do
  conta-corrente, este mapper NAO usa `to_decimal_or_none_within`. Se a
  QiTech vier a devolver lixo ~1e18 aqui, vai estourar `Numeric(8,4)`.
  Nunca observado em producao ate 2026-05-18 — se quebrar, replicar
  patch do conta-corrente.
- **`valor` pode ser negativo ou zero** (raro mas possivel — saldo de
  tesouraria pode zerar em janelas de movimento intenso).
- **"sem dados"**: payload sem `tesouraria` na lista retorna `[]` do mapper.
- **`source_updated_at` parseado de `dataDaPosição`**.

## Mapping campo do payload -> coluna do silver (`wh_saldo_tesouraria`)

| Campo (payload)         | Tipo (payload)        | Coluna (silver)                  | Tipo (silver)   | Transformacao        |
|-------------------------|-----------------------|----------------------------------|-----------------|----------------------|
| `clienteId`             | string                | `carteira_cliente_id`            | varchar(50)     | str()                |
| `clienteNome`           | string                | `carteira_cliente_nome`          | varchar(200)    | str()                |
| `cpfDoCliente`          | string (CNPJ digits)  | `carteira_cliente_doc`           | varchar(14)     | str()                |
| `descrição`             | string                | `descricao`                      | varchar(200)    | str()                |
| `valor`                 | number                | `valor`                          | numeric(18,2)   | to_decimal           |
| `percentualSobreCpr`    | number                | `percentual_sobre_cpr`           | numeric(8,4)    | to_decimal           |
| `percentualSobreTotal`  | number                | `percentual_sobre_total`         | numeric(8,4)    | to_decimal           |
| `dataDaPosição`         | string ISO-8601       | `source_updated_at` (Auditable)  | timestamptz     | parse_iso_or_none    |
| _(param)_ `data_posicao`| -                     | `data_posicao`                   | date            | passado pelo caller  |

### Source-id (UQ no upsert)

```
{clienteId}|{YYYY-MM-DD}
```

Sem `descricao` no source_id — todos os itens deste relatorio sao
"Saldo em Tesouraria"; a chave da granularidade e a classe de cota.

## Historico

- **2026-01-13:** shape confirmado contra sample REALINVEST FIDC (3 classes).
- Preencher quando QiTech mudar payload.
