# qitech.bank_account.statement

> **canonical_table:** `wh_extrato_bancario`
> **admin:** qitech
> **mapper:** [adapters/admin/qitech/mappers/bank_account_statement.py](../mappers/bank_account_statement.py)
> **schedule:** `interval 60 min` (intraday — lancamentos chegam ao longo do dia)
> **upstream:** `GET /v2/conta-corrente/bank-account/statement/{agencia}/{conta}/{inicio}/{fim}` (template `E_BANK_ACCOUNT_STATEMENT` em [endpoints.py](../endpoints.py); handler em [bank_account.py::fetch_statement](../bank_account.py); ETL em [bank_account_sync.py](../bank_account_sync.py))

## Visao geral

**Lancamentos** da conta-corrente Singulare em um periodo. Granularidade:
**1 chamada → N linhas** em `wh_extrato_bancario` (1 por lancamento).

Diferente do `bank_account.balance` (D+0 end-of-day), aqui temos cadencia
**intraday** — `default_schedule_kind=INTERVAL`, `default_schedule_value="60"`
(minutos). Lancamentos arrivam ao longo do dia; cada sync de hora em hora
captura novos eventos.

**Coverage:** UNSUPPORTED nesse endpoint hoje (semanticamente nao tem "data
referencia" no mesmo sentido dos market reports — e periodo + intraday).
Tolerancia: `expected_lag=0 / tolerance=1 / give_up=3` — valores defensivos
mantidos mesmo sem coverage ativo.

Sincronizou primeira vez em prod (ver memoria
`project_cadencia_endpoint_followups`).

## Shape do payload

**Formato:** JSON. **Encoding:** UTF-8.
**Locale:** ISO-8601 ou `YYYY-MM-DD` para datas; numeros como int/float/string.

Schema **inferido** — mapper foi escrito antes de observarmos payload real,
tolerante a multiplos formatos. Quando virmos payload real em prod,
removeremos alternativas que nao aparecem.

**Envelope** — mapper aceita 4 formas:
- **Lista direta no root:** `[ { ...item... }, ... ]`
- **Wrapped:** `{ "lancamentos": [...] }` (ou variante acentuada
  `"lançamentos"`)
- **Items:** `{ "items": [...] }` ou `{ "extrato": [...] }` ou
  `{ "movimentos": [...] }`
- **Nested:** `{ "relatorios": { "statement"/"extrato"/"lancamentos": [...] } }`

### Estrutura de cada `item`

Mapper tenta multiplas chaves por campo critico — primeiro disponivel ganha:

```
# Critic'os (sem qualquer um deles, linha e descartada)
dataLancamento (ou dataLançamento, data, dataLiquidacao, dataLiquidação)
                       string ISO-8601 ou YYYY-MM-DD
valor (ou valorMovimento, valorMovimentacao, amount)
                       number | string  (sinal negativo aceito → vira tipo "D")
tipo (ou tipoOperacao, tipoDeOperacao, natureza)
                       string  ("D"/"C"/"DEBITO"/"CREDITO"/"+"/"-"/etc; normalizado)

# Opcionais
dataMovimento (ou dataMovimentacao, dataOperacao)
                       string ISO-8601
historico (ou histórico)         string
descricao (ou descrição)         string
documento (ou nrDocumento)       string
contrapartida (ou contraparte)   object
    nome (ou name)               string
    cnpj (ou cpf, documento, doc) string
banco                            object
    codigo (ou código, code)     string
    nome (ou name)               string
moeda                            string  (default "BRL")
dataAtualizacao (ou updatedAt)   string ISO-8601  (mapeado para source_updated_at)
```

## Exemplo (anonimizado — inferido)

```json
[
  {
    "dataLancamento": "2026-05-15",
    "dataMovimento": "2026-05-15",
    "valor": 12500.00,
    "tipo": "C",
    "historico": "TED RECEBIDA",
    "descricao": "TED RECEBIDA DE FORNECEDOR X",
    "documento": "12345678",
    "contrapartida": {
      "nome": "FORNECEDOR EXEMPLO LTDA",
      "cnpj": "99888777000166"
    },
    "moeda": "BRL"
  },
  {
    "dataLancamento": "2026-05-15",
    "valor": -3520.00,
    "tipo": "D",
    "historico": "PAGAMENTO CESSAO",
    "contrapartida": {
      "nome": "CEDENTE EXEMPLO SA",
      "cnpj": "55666777000188"
    }
  }
]
```

## Gotchas

- **Schema inferido — nao 100% validado contra payload real.** Comportamento
  nao totalmente claro — investigar quando primeiros syncs reais em
  volume acontecerem em prod.
- **Lancamentos sem `(data_lancamento AND valor AND tipo)` sao descartados
  silenciosamente.** Sao campos criticos — sem eles a linha nao tem
  semantica. Caller pode contar `len(input) - len(output)` para estimar
  perda.
- **`valor` sempre absoluto no warehouse, sinal vai em `tipo`:** mapper
  faz `abs(valor)` antes de gravar, e seta `tipo="D"` se valor original
  for negativo. Garante semantica consistente (`valor + tipo` reconstroi
  o sinal).
- **Normalizacao de `tipo`:**
  - Comeca com `D` ou esta em `("DEBIT", "DEBITO", "DÉBITO", "SAIDA",
    "SAÍDA", "-")` → `"D"`.
  - Comeca com `C` ou esta em `("CREDIT", "CREDITO", "CRÉDITO", "ENTRADA",
    "+")` → `"C"`.
  - Senao, fallback pelo sinal de `valor` (negativo → "D", positivo →
    "C", zero → `None` → linha descartada).
- **`historico` vs `descricao`:** o mapper guarda os dois separadamente
  (chaves acentuadas e nao-acentuadas testadas). Em prod podemos ver que
  apenas um veio preenchido — o outro fica `None`.
- **`source_id` usa hash do item:** como QiTech pode nao expor ID estavel
  do lancamento, mapper usa `sha256_of_row(item)[:16]` no source_id.
  Re-fetch do mesmo lancamento nao duplica (UQ `tenant, source_id`).
  Risco: se a QiTech mudar formatacao do payload entre fetches sem mudar
  semantica (ex.: renomear chave), o hash muda e duplicamos. Aceitavel
  hoje — adapter version protege contra essa mudanca.
- **Coverage UNSUPPORTED:** endpoint intraday nao se encaixa no modelo
  `(data_referencia, status)` do coverage atual. Reconciler nao reabre
  furo aqui — monitoria precisa ser por idade do ultimo sync ok, nao por
  data referencia faltante.
- **HTTP 400 sem dados:** ver `bank_account.py` — 400 sobe ao caller para
  decidir; >=500/401/403/404 levantam `QiTechHttpError`.
- **`fim < inicio`:** `fetch_statement` levanta `ValueError` antes do
  request — defesa contra parametros invertidos.
- **`source_updated_at` pode ser None:** se `dataAtualizacao`/`updatedAt`
  ausentes do item, fica None na proveniencia. `data_lancamento` do
  silver e a chave forte para series temporais.

## Mapping campo do payload → coluna do silver (`wh_extrato_bancario`)

| Campo (payload, primeiro disponivel)                  | Tipo (payload)         | Coluna (silver)        | Tipo (silver)  | Transformacao              |
| ----------------------------------------------------- | ---------------------- | ---------------------- | -------------- | -------------------------- |
| `dataLancamento`/`dataLançamento`/`data`/`dataLiquidacao`/`dataLiquidação` | string ISO/YYYY-MM-DD | `data_lancamento` | date | _pick_data_lancamento (crit'o) |
| `dataMovimento`/`dataMovimentacao`/`dataOperacao`     | string ISO\|null       | `data_movimento`       | date\|null     | _pick_data_movimento       |
| `valor`/`valorMovimento`/`valorMovimentacao`/`amount` | number\|string         | `valor`                | numeric(18,2)  | _pick_valor → abs(...)     |
| `tipo`/`tipoOperacao`/`tipoDeOperacao`/`natureza`     | string                 | `tipo`                 | text ("D"/"C") | _pick_tipo (normalize)     |
| `historico`/`histórico`                               | string\|null           | `historico`            | text\|null     | normalize_str_or_none      |
| `descricao`/`descrição`                               | string\|null           | `descricao`            | text\|null     | normalize_str_or_none      |
| `documento`/`nrDocumento`                             | string\|null           | `documento`            | text\|null     | normalize_str_or_none      |
| `contrapartida.nome`/`contrapartida.name` (ou `contraparte.*`) | string\|null  | `contrapartida_nome`   | text\|null     | _pick_contrapartida        |
| `contrapartida.cnpj`/`cpf`/`documento`/`doc`          | string\|null           | `contrapartida_doc`    | text\|null     | _pick_contrapartida        |
| `banco.codigo`/`código`/`code` (item-level)           | string\|null           | `banco_codigo`         | text\|null     | normalize_str_or_none      |
| `banco.nome`/`name` (item-level)                      | string\|null           | `banco_nome`           | text\|null     | normalize_str_or_none      |
| `moeda`                                               | string                 | `moeda`                | text           | normalize_str_or_none, default "BRL" |
| `dataAtualizacao`/`updatedAt`                         | string ISO-8601\|null  | (provenance) `source_updated_at` | timestamptz\|null | parse_iso_or_none |
| _(param)_ `tenant_id`                                 | _                      | `tenant_id`            | uuid           | passado pelo caller        |
| _(param)_ `unidade_administrativa_id`                 | _                      | `unidade_administrativa_id` | uuid      | passado pelo caller        |
| _(param)_ `agencia`                                   | _                      | `agencia`              | text           | passado pelo caller        |
| _(param)_ `conta`                                     | _                      | `conta`                | text           | passado pelo caller        |

### Source-id (UQ no upsert)

```
bank_account_statement|{ua_id}|{agencia}|{conta}|{data_lancamento_iso}|{sha16(item)}
```

`sha16(item)` (primeiros 16 chars do SHA256 do item bruto) protege contra
QiTech nao expor ID estavel. Re-fetch do mesmo lancamento (byte-identico)
nao duplica via UQ. Mudancas no payload (mesmo semanticamente
equivalentes) geram hash diferente — pode duplicar; aceitavel hoje, mas
candidato a tracking caso vire problema.

## Historico

- **2026-05-01:** confirmado em teste real que endereco antigo
  `/v2/bank-account/statement/...` (sem `/conta-corrente/`) NAO existe —
  URL canonica e `/v2/conta-corrente/bank-account/statement/...`.
- **Mapper escrito antes** de observarmos payload real — tolerante a
  multiplos formatos. Preencher quando primeiros syncs reais em volume
  validarem o shape exato e quando QiTech mudar payload.
