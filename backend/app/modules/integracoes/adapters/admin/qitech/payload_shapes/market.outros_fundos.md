# qitech.market.outros_fundos

> **canonical_table:** `wh_posicao_cota_fundo`
> **admin:** qitech
> **mapper:** [adapters/admin/qitech/mappers/outros_fundos.py](../mappers/outros_fundos.py)
> **schedule:** `daily_at 07:00` SP (sincrono — GET JSON)
> **upstream:** `GET /v2/netreport/report/market/outros-fundos/{data}`

## Visao geral

Posicao do FIDC em cotas de outros fundos (carteira de investimento em cotas
externas) numa data de referencia (tipicamente D-1). Uma linha por par
`(carteira, ativo)` — ex.: o FIDC investe em REALINVEST A VENCER, REALINVEST
VENCIDOS, etc.

Fluxo **sincrono**: o adapter chama o endpoint REST e recebe JSON de volta no
mesmo request. Reconciler usa defaults de market reports (`expected=1`,
`tolerance=3`, `give_up=10` dias uteis).

## Shape do payload

**Formato:** JSON.
**Encoding:** UTF-8.
**Locale:** numeros vem como int/float/string mistos (campos percentuais e
monetarios podem ser int `0`, float `82.140195` ou string — `to_decimal`
normaliza todos via `str(value)`). Datas ISO-8601 com sufixo `Z`.
**Acentuacao:** as chaves do payload preservam acentos portugueses
(`relatórios`, `código`, `descrição`, `instituição`, `dataDaPosição`,
`valorAplicação/resgate`, `valorLíquido`, `códigoDoClienteNoSAC`).

### Estrutura

```
{
  "relatórios": {
    "outros-fundos": [
      {
        "dataDaPosição": "2026-01-13T00:00:00.000Z",
        "código": "REALIAVE",
        "fundo": "REALINVEST A VENCER",
        "nomeDaInstituição": "REALINVEST FIDC",
        "quantidade": 18892619.39422062,
        "quantidadeBloqueada": 0,
        "valorDaCota": 1.0573,
        "valorAplicação/resgate": 0,
        "valorAtual": 19972132.50,
        "valorDeImpostos": 0,
        "valorLíquido": 19972132.50,
        "percentualSobreFundos": 82.140195,
        "percentualSobreTotal": 80.43,
        "cpfDoCliente": "42449234000160",
        "clienteNome": "REALINVEST FIDC",
        "clienteId": "REALINVEST",
        "códigoDoClienteNoSAC": null
      },
      ...
    ]
  },
  "_links": { "lastAvailableReport": "..." }
}
```

## Exemplo (anonimizado)

```json
{
  "relatórios": {
    "outros-fundos": [
      {
        "dataDaPosição": "2026-05-15T00:00:00.000Z",
        "código": "EXFUNDA",
        "fundo": "EXEMPLO FUNDO A VENCER",
        "nomeDaInstituição": "EXEMPLO FIDC",
        "quantidade": 12345678.12345678,
        "quantidadeBloqueada": 0,
        "valorDaCota": 1.0421,
        "valorAplicação/resgate": 0,
        "valorAtual": 12865432.10,
        "valorDeImpostos": 0,
        "valorLíquido": 12865432.10,
        "percentualSobreFundos": 75.123456,
        "percentualSobreTotal": 73.41,
        "cpfDoCliente": "12345678000190",
        "clienteNome": "EXEMPLO FIDC",
        "clienteId": "EXEMPLO",
        "códigoDoClienteNoSAC": null
      }
    ]
  },
  "_links": { "lastAvailableReport": "/v2/netreport/report/market/outros-fundos/2026-05-15" }
}
```

## Gotchas

- **Chaves com acento**: `relatórios`, `código`, `instituição`, `descrição`,
  `dataDaPosição`, `valorAplicação/resgate`, `valorLíquido`. O mapper
  referencia as chaves com acento — nao normaliza. Se o vendor remover o
  acento um dia, o mapper quebra silenciosamente (retorna `""` ou `Decimal("0")`).
- **`valorAplicação/resgate` tem barra na chave** — `to_decimal` recebe o
  valor por dict lookup, nao ha parsing especial.
- **"sem dados" nao e erro**: payload `{"relatórios": {}, "message": "Nao ha
  resultados..."}` ou ausencia da lista `outros-fundos` retorna `[]` do mapper.
  Reconciler trata como dia legitimamente sem posicoes.
- **HTTP 400 canonico**: a QiTech retorna 400 com body de "sem dados" em
  vez de 200/204. O `reports.py` reconhece esse caso (body com chave
  `relatórios`) e nao propaga como erro.
- **`dataDaPosição` vs `data_posicao`**: silver guarda a data **do parametro
  da chamada** (`data_posicao` recebido pelo mapper), nao a do payload.
  Defesa contra TZ drift do vendor.
- **`source_updated_at` parseado do `dataDaPosição`** — pode ser None se a
  string vier malformada (sem derrubar ETL).
- **Numericos mistos** (int/float/string): `to_decimal` faz `Decimal(str(v))`
  pra evitar ruido float -> Decimal.
- **`quantidade` com 8 decimais**: cotas fracionarias com 8 casas observadas
  (`18892619.39422062`). Schema canonico `Numeric(24, 8)`.
- **`percentualSobreTotal` pode passar de 100%**: carteira com alavancagem
  ou passivo. Coluna `Numeric(8,4)` sem clamp — preserva valor real.
- **`códigoDoClienteNoSAC` opcional** — vem `null` na maioria. `normalize_str_or_none`
  uniformiza `""` e `null` em `None`.

## Mapping campo do payload -> coluna do silver (`wh_posicao_cota_fundo`)

| Campo (payload)               | Tipo (payload)        | Coluna (silver)             | Tipo (silver)   | Transformacao            |
|-------------------------------|-----------------------|-----------------------------|-----------------|--------------------------|
| `clienteId`                   | string                | `carteira_cliente_id`       | varchar(50)     | str()                    |
| `clienteNome`                 | string                | `carteira_cliente_nome`     | varchar(200)    | str()                    |
| `cpfDoCliente`                | string (CNPJ digits)  | `carteira_cliente_doc`      | varchar(14)     | str()                    |
| `códigoDoClienteNoSAC`        | string \| null \| ""  | `carteira_cliente_sac`      | varchar(100)    | normalize_str_or_none    |
| `código`                      | string                | `ativo_codigo`              | varchar(50)     | str()                    |
| `fundo`                       | string                | `ativo_nome`                | varchar(200)    | str()                    |
| `nomeDaInstituição`           | string                | `ativo_instituicao`         | varchar(100)    | str()                    |
| `quantidade`                  | number                | `quantidade`                | numeric(24,8)   | to_decimal               |
| `quantidadeBloqueada`         | number                | `quantidade_bloqueada`      | numeric(24,8)   | to_decimal               |
| `valorDaCota`                 | number                | `valor_cota`                | numeric(24,8)   | to_decimal               |
| `valorAplicação/resgate`      | number                | `valor_aplicacao_resgate`   | numeric(18,2)   | to_decimal               |
| `valorAtual`                  | number                | `valor_atual`               | numeric(18,2)   | to_decimal               |
| `valorDeImpostos`             | number                | `valor_impostos`            | numeric(18,2)   | to_decimal               |
| `valorLíquido`                | number                | `valor_liquido`             | numeric(18,2)   | to_decimal               |
| `percentualSobreFundos`       | number                | `percentual_sobre_fundos`   | numeric(8,4)    | to_decimal               |
| `percentualSobreTotal`        | number                | `percentual_sobre_total`    | numeric(8,4)    | to_decimal               |
| `dataDaPosição`               | string ISO-8601       | `source_updated_at` (Auditable) | timestamptz | parse_iso_or_none        |
| _(param)_ `data_posicao`      | -                     | `data_posicao`              | date            | passado pelo caller      |

### Source-id (UQ no upsert)

```
{clienteId}|{código}|{YYYY-MM-DD}
```

Determinista — re-ingerir o mesmo dia substitui a linha via
`uq_wh_posicao_cota_fundo (tenant_id, source_id)`.

## Historico

- **2026-01-13:** shape confirmado contra sample REALINVEST FIDC. Chaves com
  acento portugues preservadas.
- Preencher quando QiTech mudar payload.
