# qitech.market.cpr

> **canonical_table:** `wh_cpr_movimento`
> **admin:** qitech
> **mapper:** [adapters/admin/qitech/mappers/cpr.py](../mappers/cpr.py)
> **schedule:** `daily_at 08:30` SP (sincrono — GET JSON)
> **upstream:** `GET /v2/netreport/report/market/cpr/{data}`

## Visao geral

CPR (Contas a Pagar e Receber) do FIDC — despesas estruturadas (auditoria,
custodia, taxa CVM, taxa ANBIMA, taxa de administracao, etc) e receitas
diferidas. Uma linha por lancamento.

Fluxo **sincrono**. Reconciler usa defaults de market reports.

## Shape do payload

**Formato:** JSON.
**Encoding:** UTF-8.
**Locale:** numericos mistos. Datas ISO-8601 com `Z`.
**Acentuacao:** `relatórios`, `descrição`, `históricoTraduzido`, `dataDaPosição`.

### Estrutura

```
{
  "relatórios": {
    "cpr": [
      {
        "dataDaPosição": "2026-01-13T00:00:00.000Z",
        "descrição": "Provisao Taxa CVM",
        "históricoTraduzido": "Taxa de fiscalizacao CVM",
        "valor": -1234.56,
        "percentualSobreCpr": -2.0387403,
        "percentualSobreTotal": -0.01,
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
    "cpr": [
      {
        "dataDaPosição": "2026-05-15T00:00:00.000Z",
        "descrição": "Provisao Taxa de Administracao",
        "históricoTraduzido": "Taxa mensal administracao",
        "valor": -8520.00,
        "percentualSobreCpr": -45.1234567,
        "percentualSobreTotal": -0.0367,
        "cpfDoCliente": "12345678000190",
        "clienteNome": "EXEMPLO FIDC",
        "clienteId": "EXEMPLO"
      },
      {
        "dataDaPosição": "2026-05-15T00:00:00.000Z",
        "descrição": "Provisao Custodia",
        "históricoTraduzido": "Custodia mensal",
        "valor": -2350.00,
        "percentualSobreCpr": -12.4567890,
        "percentualSobreTotal": -0.0101,
        "cpfDoCliente": "12345678000190",
        "clienteNome": "EXEMPLO FIDC",
        "clienteId": "EXEMPLO"
      }
    ]
  },
  "_links": { "lastAvailableReport": "/v2/netreport/report/market/cpr/2026-05-15" }
}
```

## Gotchas

- **Sem id estavel na QiTech**: mesmo padrao do demonstrativo-caixa —
  `source_id` inclui `sha16(item)` pra garantir unicidade. Trade-off: typo
  corrigido vira linha nova.
- **`valor` tipicamente negativo**: despesa = negativo, receita = positivo.
  Diferimentos podem ser positivos.
- **`percentualSobreCpr` com alta precisao**: observado 7 casas decimais
  (`-2.0387403`). Schema `Numeric(12,8)` preserva ate 8 casas. Diferente
  do `percentualSobreTotal` que e `Numeric(8,4)`.
- **Sem `to_decimal_or_none_within`**: se a QiTech devolver lixo numerico
  em percentuais, este mapper estoura. Nao reproduzido em producao ate
  2026-05-18 — replicar patch do conta-corrente se aparecer.
- **`source_updated_at` parseado de `dataDaPosição`** (nao `dataLiquidação` —
  diferente do demonstrativo-caixa).
- **"sem dados"**: payload sem `cpr` na lista retorna `[]`.
- **`descrição` e `históricoTraduzido` podem ser longos** — schema `Text`.

## Mapping campo do payload -> coluna do silver (`wh_cpr_movimento`)

| Campo (payload)         | Tipo (payload)            | Coluna (silver)                  | Tipo (silver)    | Transformacao        |
|-------------------------|---------------------------|----------------------------------|------------------|----------------------|
| `clienteId`             | string                    | `carteira_cliente_id`            | varchar(50)      | str()                |
| `clienteNome`           | string                    | `carteira_cliente_nome`          | varchar(200)     | str()                |
| `cpfDoCliente`          | string (CNPJ digits)      | `carteira_cliente_doc`           | varchar(14)      | str()                |
| `descrição`             | string                    | `descricao`                      | text             | str()                |
| `históricoTraduzido`    | string                    | `historico_traduzido`            | text             | str()                |
| `valor`                 | number (signed)           | `valor`                          | numeric(18,2)    | to_decimal           |
| `percentualSobreCpr`    | number (signed, 8 casas)  | `percentual_sobre_cpr`           | numeric(12,8)    | to_decimal           |
| `percentualSobreTotal`  | number (signed)           | `percentual_sobre_total`         | numeric(8,4)     | to_decimal           |
| `dataDaPosição`         | string ISO-8601           | `source_updated_at` (Auditable)  | timestamptz      | parse_iso_or_none    |
| _(param)_ `data_posicao`| -                         | `data_posicao`                   | date             | passado pelo caller  |

### Source-id (UQ no upsert)

```
{clienteId}|{YYYY-MM-DD data_posicao}|{sha16(item)}
```

Composicao: `clienteId` + `data_posicao` do parametro + sha16 do item completo
(mesmo padrao de `demonstrativo_caixa`).

## Historico

- **2026-01-13:** shape confirmado contra sample REALINVEST FIDC.
  `percentualSobreCpr` observado com 7 casas decimais — schema canonico
  ajustado pra `Numeric(12,8)`.
- Preencher quando QiTech mudar payload.
