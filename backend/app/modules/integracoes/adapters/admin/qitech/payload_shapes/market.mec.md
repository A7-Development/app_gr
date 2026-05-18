# qitech.market.mec

> **canonical_table:** `wh_mec_evolucao_cotas`
> **admin:** qitech
> **mapper:** [adapters/admin/qitech/mappers/mec.py](../mappers/mec.py)
> **schedule:** `daily_at 08:30` SP (sincrono — GET JSON)
> **upstream:** `GET /v2/netreport/report/market/mec/{data}`

## Visao geral

Mapa Evolutivo de Cotas (MEC) — patrimonio, quantidade de cotas, valor da
cota e variacoes (diaria/mensal/anual/total) por classe de cota numa data.
Cada `clienteId` representa uma classe — ex.: 3 linhas no sample REALINVEST
(`REALINVEST` Sub, `REALINVEST_MEZ` Mezanino, `REALINVEST_SEN` Senior).

Fluxo **sincrono**. Reconciler usa defaults de market reports.

## Shape do payload

**Formato:** JSON.
**Encoding:** UTF-8.
**Locale:** numericos mistos (int/float/string). Datas ISO-8601 com `Z`.
**Acentuacao:** `relatórios`, `dataDaPosição`, `variaçãoDiaria`,
`variaçãoMensal`, `variaçãoAnual`, `variaçãoTotal`.

### Estrutura

```
{
  "relatórios": {
    "mec": [
      {
        "dataDaPosição": "2026-01-13T00:00:00.000Z",
        "entradas": 0,
        "saidas": 0,
        "aporte": 0,
        "retirada": 0,
        "patrimonio": 24850123.45,
        "quantidade": 23456789.12345678,
        "valorDaCota": 1.0594,
        "variaçãoDiaria": 0.0512,
        "variaçãoMensal": 0.8745,
        "variaçãoAnual": 12.3456,
        "variaçãoTotal": 5.9412,
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
    "mec": [
      {
        "dataDaPosição": "2026-05-15T00:00:00.000Z",
        "entradas": 0,
        "saidas": 0,
        "aporte": 100000.00,
        "retirada": 0,
        "patrimonio": 18923451.12,
        "quantidade": 17834567.12345678,
        "valorDaCota": 1.0611,
        "variaçãoDiaria": 0.0421,
        "variaçãoMensal": 0.7823,
        "variaçãoAnual": 11.8901,
        "variaçãoTotal": 6.1100,
        "cpfDoCliente": "12345678000190",
        "clienteNome": "EXEMPLO FIDC",
        "clienteId": "EXEMPLO"
      },
      {
        "dataDaPosição": "2026-05-15T00:00:00.000Z",
        "entradas": 0,
        "saidas": 0,
        "aporte": 0,
        "retirada": 0,
        "patrimonio": 4521000.00,
        "quantidade": 4234567.87654321,
        "valorDaCota": 1.0676,
        "variaçãoDiaria": 0.0612,
        "variaçãoMensal": 1.0214,
        "variaçãoAnual": 14.5023,
        "variaçãoTotal": 6.7600,
        "cpfDoCliente": "12345678000190",
        "clienteNome": "EXEMPLO MEZ",
        "clienteId": "EXEMPLO_MEZ"
      }
    ]
  },
  "_links": { "lastAvailableReport": "/v2/netreport/report/market/mec/2026-05-15" }
}
```

## Gotchas

- **Chaves de variacao com acento**: `variaçãoDiaria`, `variaçãoMensal`,
  `variaçãoAnual`, `variaçãoTotal`. **Atencao**: a chave e `variaçãoDiaria`
  (sem acento agudo no `a` final — `Diaria` nao `Diária`), confirmar com a
  QiTech caso aparente divergencia em logs. Mapper le exatamente
  `item.get("variaçãoDiaria")` etc.
- **`saidas` na chave do payload e SEM acento** (diferente do
  `demonstrativo_caixa`, que usa `saídas` com acento). Atencao se for
  copiar codigo entre mappers.
- **`quantidade` e `valorDaCota` com 8 decimais**: schema `Numeric(24,8)`.
- **Multiplas classes de cota**: 1 linha por `clienteId`. FIDC com 3
  classes devolve 3 linhas. Unicidade no silver via `clienteId|data`.
- **Variacoes em % multiplicadas** (175.64 = 175.64%). Pode ser negativa.
  Schema `Numeric(8,4)`.
- **Sem `to_decimal_or_none_within`**: se a QiTech vier a devolver lixo
  numerico em variacoes (cenario observado em conta-corrente), este
  mapper estoura. Nao reproduzido em producao ate 2026-05-18.
- **`entradas`/`saidas`/`aporte`/`retirada` podem ser zero** em dias sem
  movimento.
- **"sem dados"**: payload sem `mec` na lista retorna `[]`.
- **`source_updated_at` parseado de `dataDaPosição`**.

## Mapping campo do payload -> coluna do silver (`wh_mec_evolucao_cotas`)

| Campo (payload)         | Tipo (payload)        | Coluna (silver)                  | Tipo (silver)   | Transformacao        |
|-------------------------|-----------------------|----------------------------------|-----------------|----------------------|
| `clienteId`             | string                | `carteira_cliente_id`            | varchar(50)     | str()                |
| `clienteNome`           | string                | `carteira_cliente_nome`          | varchar(200)    | str()                |
| `cpfDoCliente`          | string (CNPJ digits)  | `carteira_cliente_doc`           | varchar(14)     | str()                |
| `entradas`              | number                | `entradas`                       | numeric(18,2)   | to_decimal           |
| `saidas`                | number                | `saidas`                         | numeric(18,2)   | to_decimal           |
| `aporte`                | number                | `aporte`                         | numeric(18,2)   | to_decimal           |
| `retirada`              | number                | `retirada`                       | numeric(18,2)   | to_decimal           |
| `patrimonio`            | number                | `patrimonio`                     | numeric(18,2)   | to_decimal           |
| `quantidade`            | number (8 casas)      | `quantidade`                     | numeric(24,8)   | to_decimal           |
| `valorDaCota`           | number (8 casas)      | `valor_da_cota`                  | numeric(24,8)   | to_decimal           |
| `variaçãoDiaria`        | number (signed)       | `variacao_diaria`                | numeric(8,4)    | to_decimal           |
| `variaçãoMensal`        | number (signed)       | `variacao_mensal`                | numeric(8,4)    | to_decimal           |
| `variaçãoAnual`         | number (signed)       | `variacao_anual`                 | numeric(8,4)    | to_decimal           |
| `variaçãoTotal`         | number (signed)       | `variacao_total`                 | numeric(8,4)    | to_decimal           |
| `dataDaPosição`         | string ISO-8601       | `source_updated_at` (Auditable)  | timestamptz     | parse_iso_or_none    |
| _(param)_ `data_posicao`| -                     | `data_posicao`                   | date            | passado pelo caller  |

### Source-id (UQ no upsert)

```
{clienteId}|{YYYY-MM-DD}
```

## Historico

- **2026-01-13:** shape confirmado contra sample REALINVEST FIDC (3 classes).
- Preencher quando QiTech mudar payload.
