# qitech.market.demonstrativo_caixa

> **canonical_table:** `wh_movimento_caixa`
> **admin:** qitech
> **mapper:** [adapters/admin/qitech/mappers/demonstrativo_caixa.py](../mappers/demonstrativo_caixa.py)
> **schedule:** `daily_at 08:00` SP (sincrono — GET JSON)
> **upstream:** `GET /v2/netreport/report/market/demonstrativo-caixa/{data}`

## Visao geral

Demonstrativo de caixa do FIDC — entradas, saidas e saldo diario, com
quebra por lancamento. Cada movimento traz `tipoDeRegistro` (1=movimento,
2=saldo de fechamento, etc), `descricao`, `historicoTraduzido`, e
opcionalmente dados bancarios (banco/agencia/conta).

Fluxo **sincrono**. Reconciler usa defaults de market reports.

## Shape do payload

**Formato:** JSON.
**Encoding:** UTF-8.
**Locale:** numericos mistos. Datas ISO-8601 com `Z`.
**Acentuacao:** `relatórios`, `descrição`, `históricoTraduzido`, `saídas`,
`dataLiquidação`.

### Estrutura

```
{
  "relatórios": {
    "demonstrativo-caixa": [
      {
        "dataLiquidação": "2026-01-13T00:00:00.000Z",
        "tipoDeRegistro": 1,
        "descrição": "Aplicacao no Fundo REALIAVE [REALINVEST A VENCER]",
        "históricoTraduzido": "Aplicacao em cota de fundo",
        "banco": null,
        "agencia": null,
        "contaCorrente": null,
        "digito": null,
        "idConta": 0,
        "contaInvestimento": null,
        "entradas": 0,
        "saídas": -150000.00,
        "saldo": 24700123.45,
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
    "demonstrativo-caixa": [
      {
        "dataLiquidação": "2026-05-15T00:00:00.000Z",
        "tipoDeRegistro": 1,
        "descrição": "Aplicacao no Fundo EXFUNDA [EXEMPLO A VENCER]",
        "históricoTraduzido": "Aplicacao em cota de fundo",
        "banco": null,
        "agencia": null,
        "contaCorrente": null,
        "digito": null,
        "idConta": 0,
        "contaInvestimento": null,
        "entradas": 0,
        "saídas": -250000.00,
        "saldo": 18723451.12,
        "cpfDoCliente": "12345678000190",
        "clienteNome": "EXEMPLO FIDC",
        "clienteId": "EXEMPLO"
      },
      {
        "dataLiquidação": "2026-05-15T00:00:00.000Z",
        "tipoDeRegistro": 2,
        "descrição": "Saldo de fechamento",
        "históricoTraduzido": "Saldo do dia",
        "banco": null,
        "agencia": null,
        "contaCorrente": null,
        "digito": null,
        "idConta": null,
        "contaInvestimento": null,
        "entradas": 0,
        "saídas": 0,
        "saldo": 18723451.12,
        "cpfDoCliente": "12345678000190",
        "clienteNome": "EXEMPLO FIDC",
        "clienteId": "EXEMPLO"
      }
    ]
  },
  "_links": { "lastAvailableReport": "/v2/netreport/report/market/demonstrativo-caixa/2026-05-15" }
}
```

## Gotchas

- **Sem id estavel na QiTech**: pode haver dois lancamentos com mesma
  `descrição` no mesmo dia (ex.: 2 resgates do mesmo fundo). O `source_id`
  inclui `sha16` do item completo via `sha256_of_row(item)[:16]` —
  garante unicidade. Trade-off documentado no mapper: se a QiTech corrigir
  um typo na descricao, vira linha nova em vez de update (aceitavel MVP).
- **`data_liquidacao` pode divergir de `data_posicao`**: a `dataLiquidação`
  do payload pode ser passada/futura (pre-aviso de movimento). O silver
  guarda a `data_liquidacao` do **payload** (nao do parametro) — caso
  excecional vs outros mappers que guardam `data_posicao` do parametro.
  Fallback: se `dataLiquidação` nao parseia, usa `data_posicao` recebida.
- **`idConta` aceita `0` e `null`**: helper `_to_int_or_none` retorna `None`
  se nao parsear; mas `0` vira `0` (caller decide se 0 e legitimo).
- **`saidas` vem com valor negativo** da QiTech (`"saídas": -150000.00`).
  Mapper guarda como esta — nao inverte sinal. Soma `entradas + saidas`
  retorna o fluxo liquido naturalmente.
- **`saídas` (chave com acento) != `saidas` (coluna silver)**: o mapper
  le `item.get("saídas")` mas grava em `saidas` (sem acento).
- **`históricoTraduzido` e descricao podem ser longos** (>200 chars) —
  schema usa `Text` em ambos.
- **Dados bancarios geralmente null**: o demonstrativo caixa de FIDC nao
  costuma trazer (banco/agencia/conta/digito ficam None). `normalize_str_or_none`
  uniformiza `""` -> `None`.
- **"sem dados"**: payload sem `demonstrativo-caixa` na lista retorna `[]`.
- **`source_updated_at` parseado de `dataLiquidação`** (nao `dataDaPosição`).

## Mapping campo do payload -> coluna do silver (`wh_movimento_caixa`)

| Campo (payload)         | Tipo (payload)            | Coluna (silver)                  | Tipo (silver)    | Transformacao                                  |
|-------------------------|---------------------------|----------------------------------|------------------|------------------------------------------------|
| `clienteId`             | string                    | `carteira_cliente_id`            | varchar(50)      | str()                                          |
| `clienteNome`           | string                    | `carteira_cliente_nome`          | varchar(200)     | str()                                          |
| `cpfDoCliente`          | string (CNPJ digits)      | `carteira_cliente_doc`           | varchar(14)      | str()                                          |
| `tipoDeRegistro`        | int                       | `tipo_de_registro`               | int              | int(default 0)                                 |
| `descrição`             | string                    | `descricao`                      | text             | str()                                          |
| `históricoTraduzido`    | string                    | `historico_traduzido`            | text             | str()                                          |
| `banco`                 | string \| null \| ""      | `banco`                          | varchar(100)null | normalize_str_or_none                          |
| `agencia`               | string \| null \| ""      | `agencia`                        | varchar(20) null | normalize_str_or_none                          |
| `contaCorrente`         | string \| null \| ""      | `conta_corrente`                 | varchar(30) null | normalize_str_or_none                          |
| `digito`                | string \| null \| ""      | `digito`                         | varchar(5) null  | normalize_str_or_none                          |
| `idConta`               | int \| null \| 0          | `id_conta`                       | int null         | _to_int_or_none                                |
| `contaInvestimento`     | string \| null \| ""      | `conta_investimento`             | varchar(50) null | normalize_str_or_none                          |
| `entradas`              | number                    | `entradas`                       | numeric(18,2)    | to_decimal                                     |
| `saídas`                | number (signed)           | `saidas`                         | numeric(18,2)    | to_decimal                                     |
| `saldo`                 | number                    | `saldo`                          | numeric(18,2)    | to_decimal                                     |
| `dataLiquidação`        | string ISO-8601           | `data_liquidacao`                | date             | parse_iso_or_none().date() (fallback data_posicao) |
| `dataLiquidação`        | string ISO-8601           | `source_updated_at` (Auditable)  | timestamptz      | parse_iso_or_none                              |

### Source-id (UQ no upsert)

```
{clienteId}|{YYYY-MM-DD data_posicao}|{sha16(item)}
```

Composicao: `clienteId` + `data_posicao` do parametro (nao do payload —
evita colisao com movimentos de dias diferentes que tenham mesmo conteudo) +
sha16 do item completo.

## Historico

- **2026-01-13:** shape confirmado contra sample REALINVEST FIDC.
  Padronizada estrategia de source_id com sha16 (compartilhada com `cpr`).
- Preencher quando QiTech mudar payload.
