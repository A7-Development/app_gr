# qitech.market.conta_corrente

> **canonical_table:** `wh_saldo_conta_corrente`
> **admin:** qitech
> **mapper:** [adapters/admin/qitech/mappers/conta_corrente.py](../mappers/conta_corrente.py)
> **schedule:** `daily_at 07:30` SP (sincrono — GET JSON)
> **upstream:** `GET /v2/netreport/report/market/conta-corrente/{data}`

## Visao geral

Saldo das contas-corrente associadas ao FIDC (Bradesco, Socopa, conta de
conciliacao, etc) numa data de referencia. Uma linha por par
`(carteira, codigo_conta)` — chaves tipicas no `codigo`: `BRADESCO`,
`SOCOPA`, `CONCILIA`.

Fluxo **sincrono**. Reconciler usa defaults de market reports.

## Shape do payload

**Formato:** JSON.
**Encoding:** UTF-8.
**Locale:** numericos mistos (int/float/string). Datas ISO-8601 com sufixo `Z`.
**Acentuacao:** chaves preservam acentos (`relatórios`, `código`, `descrição`,
`instituição`, `dataDaPosição`).

### Estrutura

```
{
  "relatórios": {
    "conta-corrente": [
      {
        "dataDaPosição": "2026-01-13T00:00:00.000Z",
        "código": "BRADESCO",
        "descrição": "CC - BRADESCO",
        "instituição": "BRADESCO",
        "valorTotal": 13671.59,
        "percentualSobreContaCorrente": 0,
        "percentualSobreTotal": 0.13,
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
    "conta-corrente": [
      {
        "dataDaPosição": "2026-05-15T00:00:00.000Z",
        "código": "BRADESCO",
        "descrição": "CC - BRADESCO",
        "instituição": "BRADESCO",
        "valorTotal": 24512.78,
        "percentualSobreContaCorrente": 35.4012,
        "percentualSobreTotal": 0.18,
        "cpfDoCliente": "12345678000190",
        "clienteNome": "EXEMPLO FIDC",
        "clienteId": "EXEMPLO"
      },
      {
        "dataDaPosição": "2026-05-15T00:00:00.000Z",
        "código": "CONCILIA",
        "descrição": "Conciliacao operacional",
        "instituição": "SOCOPA",
        "valorTotal": -512.30,
        "percentualSobreContaCorrente": null,
        "percentualSobreTotal": null,
        "cpfDoCliente": "12345678000190",
        "clienteNome": "EXEMPLO FIDC",
        "clienteId": "EXEMPLO"
      }
    ]
  },
  "_links": { "lastAvailableReport": "/v2/netreport/report/market/conta-corrente/2026-05-15" }
}
```

## Gotchas

- **Percentuais com lixo numerico (~1e18)**: quando o saldo liquido da
  carteira e zero, a QiTech divide por valor muito proximo de zero e devolve
  numero gigante (ex.: `-6234570403704996000`). O schema canonico e
  `NUMERIC(8,4)` (max abs `9999.9999`). O mapper usa
  `to_decimal_or_none_within(value, max_abs=Decimal("9999.9999"))` — lixo
  vira `None`. Caso real validado em 2026-04-26 com REALINVEST.
- **`valor_total` pode ser negativo**: contas de conciliacao com creditos
  sobrescritos ou ajustes contabeis.
- **Chaves com acento**: `relatórios`, `código`, `descrição`, `instituição`,
  `dataDaPosição`. Acompanhar se a QiTech "deacentuar" um dia.
- **"sem dados" -> 400 com body canonico**: igual `market.outros_fundos`.
- **`codigo` nao e sempre nome de banco**: pode ser `CONCILIA`, `SOCOPA`,
  codigo interno. String generica de 50 chars.
- **CNPJ vem digit-only no payload** (`42449234000160`) — sem normalizacao
  necessaria.
- **`source_updated_at` parseado de `dataDaPosição`**.

## Mapping campo do payload -> coluna do silver (`wh_saldo_conta_corrente`)

| Campo (payload)                  | Tipo (payload)        | Coluna (silver)                       | Tipo (silver)    | Transformacao                              |
|----------------------------------|-----------------------|---------------------------------------|------------------|--------------------------------------------|
| `clienteId`                      | string                | `carteira_cliente_id`                 | varchar(50)      | str()                                      |
| `clienteNome`                    | string                | `carteira_cliente_nome`               | varchar(200)     | str()                                      |
| `cpfDoCliente`                   | string (CNPJ digits)  | `carteira_cliente_doc`                | varchar(14)      | str()                                      |
| `código`                         | string                | `codigo`                              | varchar(50)      | str()                                      |
| `descrição`                      | string                | `descricao`                           | varchar(200)     | str()                                      |
| `instituição`                    | string                | `instituicao`                         | varchar(100)     | str()                                      |
| `valorTotal`                     | number                | `valor_total`                         | numeric(18,2)    | to_decimal                                 |
| `percentualSobreContaCorrente`   | number \| lixo (~1e18) | `percentual_sobre_conta_corrente`    | numeric(8,4) null| to_decimal_or_none_within (max 9999.9999)  |
| `percentualSobreTotal`           | number \| lixo (~1e18) | `percentual_sobre_total`             | numeric(8,4) null| to_decimal_or_none_within (max 9999.9999)  |
| `dataDaPosição`                  | string ISO-8601       | `source_updated_at` (Auditable)       | timestamptz      | parse_iso_or_none                          |
| _(param)_ `data_posicao`         | -                     | `data_posicao`                        | date             | passado pelo caller                        |

### Source-id (UQ no upsert)

```
{clienteId}|{código}|{YYYY-MM-DD}
```

## Historico

- **2026-04-26:** descoberta do lixo numerico ~1e18 em percentuais quando
  saldo liquido da carteira e zero. Introduzido `to_decimal_or_none_within`
  + colunas `percentual_*` viraram nullable. Validado contra REALINVEST.
- Preencher quando QiTech mudar payload.
