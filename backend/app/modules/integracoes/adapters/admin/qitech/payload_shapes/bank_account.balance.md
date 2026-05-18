# qitech.bank_account.balance

> **canonical_table:** `wh_saldo_bancario_diario`
> **admin:** qitech
> **mapper:** [adapters/admin/qitech/mappers/bank_account_balance.py](../mappers/bank_account_balance.py)
> **schedule:** `daily_at 19:00` SP (sincrono — disponivel apos ~18h SP, end-of-day)
> **upstream:** `GET /v2/conta-corrente/bank-account/balance/{agencia}/{conta}/{data}` (template `E_BANK_ACCOUNT_BALANCE` em [endpoints.py](../endpoints.py); handler em [bank_account.py::fetch_balance](../bank_account.py); ETL em [bank_account_sync.py](../bank_account_sync.py))

## Visao geral

**Saldo de fechamento** da conta-corrente Singulare numa data. D+0 e o
esperado (disponivel apos ~18h SP); D+1 ja chama atencao (ver
`default_expected_lag_business_days=0` no catalog).

Granularidade: **1 chamada → 1 linha** em `wh_saldo_bancario_diario`. PK
logica = `(tenant, ua, agencia, conta, data_posicao)`, garantida via UQ
`(tenant_id, source_id)`.

Diferente da familia `/netreport/*` (data unica + tipo de mercado), aqui o
path inclui `agencia`+`conta` (vem de `QiTechConfig.bank_accounts` da UA).
CNPJ titular vem **implicitamente** da UA dona da credencial — nao viaja no
path.

**Tolerancia mais apertada que market reports:** `tolerance=1 / give_up=5`
(end-of-day mesmo dia, sem fluxo assincrono — atraso e suspeito).

## Shape do payload

**Formato:** JSON. **Encoding:** UTF-8.
**Locale:** ISO-8601 para datas; numeros como int/float/string.

Schema **inferido** — mapper foi escrito antes de observarmos payload real.
Tolerante a multiplas chaves comuns (`saldo`, `valor`, `valorTotal`,
`saldoTotal`, `balance`) e dois formatos de "banco" (objeto aninhado vs
chaves planas). Quando virmos payload real em prod, removeremos
alternativas que nao aparecem.

### Estrutura esperada (top-level objeto, single)

```
saldo          number  (OU "valor", "valorTotal", "saldoTotal", "balance" — mapper tenta nessa ordem)
moeda          string  (default "BRL" se ausente)
banco          object  (opcional, ver alternativas)
    codigo     string  ("código" tambem aceito)
    nome       string
dataDaPosicao  string ISO-8601  (opcional, redundante com path; mapeado para source_updated_at)
```

Alternativas para `banco`:
- **Forma 1 (aninhada):** `{"banco": {"codigo": "237", "nome": "Bradesco"}}`
- **Forma 2 (plana):** `{"codigoBanco": "237", "nomeBanco": "Bradesco"}` ou
  `instituicao` no lugar de `nomeBanco`.

## Exemplo (anonimizado — inferido)

```json
{
  "saldo": 12345.67,
  "moeda": "BRL",
  "banco": {
    "codigo": "237",
    "nome": "Bradesco"
  },
  "dataDaPosicao": "2026-05-15T18:30:00.000Z"
}
```

## Gotchas

- **Schema inferido — nao 100% validado contra payload real.** Comportamento
  nao totalmente claro — investigar quando primeiros syncs reais
  acontecerem em prod (ver memoria `project_cadencia_endpoint_followups`
  sobre `bank_account.statement` ja ter sincronizado uma primeira vez).
- **Mapper retorna `[]` se nao achar saldo:** se nenhuma chave de
  `_pick_saldo` (`saldo`/`valor`/`valorTotal`/`saldoTotal`/`balance`)
  estiver presente OU se for `None`, mapper devolve lista vazia. Caller
  decide se loga warning ou ignora silenciosamente. **Não** registra zero —
  pra evitar confundir "sem dado" com "saldo zero real".
- **`moeda` default "BRL"** se chave ausente — assume moeda local. Se
  multi-currency entrar em jogo, ajustar.
- **`source_updated_at` opcional:** se payload nao trouxer `dataDaPosicao`
  (ou variante acentuada `dataDaPosição`), fica `None` na proveniencia. O
  `data_posicao` no silver vem do param do caller (data alvo), nao do
  payload — defesa contra divergencia.
- **`banco_codigo`/`banco_nome` opcionais:** se nem forma aninhada nem
  forma plana presentes, ficam `None`. Util filtrar por
  `banco_codigo IS NOT NULL` em queries que assumem banco preenchido.
- **HTTP 400 sem dados:** `bank_account.py::_request_with_retry` devolve
  `(body, 400)` para 400 — caller (ETL) decide se 400 e "sem dados" ou
  erro real. O shape do payload de "sem dados" ainda nao foi observado
  em campo. Status >=500 ou 401/403/404 levantam `QiTechHttpError`.
- **URL legacy:** comentario em `endpoints.py` registra que o endereco
  antigo `/v2/bank-account/balance/...` (sem `/conta-corrente/`) NAO
  existe — herdado por simetria do `statement`. Validar diretamente em
  ambiente real antes de iterar em volume.
- **Path agencia/conta como string literal:** `agencia` vai zero-padded a
  4 digitos (ex.: `"0001"`); `conta` sem digito verificador (ex.:
  `"4532551"`). Viajam exatamente como cadastrados em
  `QiTechBankAccount.agencia`/`conta`.

## Mapping campo do payload → coluna do silver (`wh_saldo_bancario_diario`)

| Campo (payload)              | Tipo (payload)        | Coluna (silver)             | Tipo (silver)  | Transformacao                |
| ---------------------------- | --------------------- | --------------------------- | -------------- | ---------------------------- |
| `saldo` / `valor` / `valorTotal` / `saldoTotal` / `balance` (primeiro disponivel) | number\|string | `saldo` | numeric(18,2) | _pick_saldo → to_decimal |
| `moeda`                      | string                | `moeda`                     | text           | normalize_str_or_none, default "BRL" |
| `banco.codigo` (ou `banco.código`/`banco.code`/`codigoBanco`/`códigoBanco`) | string | `banco_codigo` | text\|null | normalize_str_or_none |
| `banco.nome` (ou `banco.name`/`nomeBanco`/`instituicao`) | string | `banco_nome` | text\|null | normalize_str_or_none |
| `dataDaPosicao` (ou `dataDaPosição`) | string ISO-8601\|null | (provenance) `source_updated_at` | timestamptz\|null | parse_iso_or_none |
| _(param)_ `tenant_id`        | _                     | `tenant_id`                 | uuid           | passado pelo caller          |
| _(param)_ `unidade_administrativa_id` | _            | `unidade_administrativa_id` | uuid           | passado pelo caller          |
| _(param)_ `agencia`          | _                     | `agencia`                   | text           | passado pelo caller          |
| _(param)_ `conta`            | _                     | `conta`                     | text           | passado pelo caller          |
| _(param)_ `data_posicao`     | _                     | `data_posicao`              | date           | passado pelo caller          |

### Source-id (UQ no upsert)

```
bank_account_balance|{ua_id}|{agencia}|{conta}|{data_posicao_iso}
```

Inclui `ua_id`/`agencia`/`conta` para que multi-UA com mesmo banco/conta
(raro mas possivel) nao colida. `data_posicao_iso` garante 1 linha por
dia por (UA, agencia, conta).

## Historico

- Mapper escrito **antes** de observarmos payload real — tolerante a
  multiplas chaves. Preencher quando primeiros syncs reais validarem o
  shape exato e quando QiTech mudar payload.
