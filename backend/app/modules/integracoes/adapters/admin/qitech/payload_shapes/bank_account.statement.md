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

Schema **REAL** — validado contra payload de prod em 2026-05 (mapper corrigido
em `qitech_adapter_v0.5.0`). O mapper ainda aceita envelopes alternativos por
defesa, mas o formato observado e estavel.

**Envelope (observado):** `{ "extrato": [ { ...item... }, ... ] }`.
(Mapper tambem tolera lista direta, `lancamentos`, `items`, `movimentos` e
`relatorios.*` por compatibilidade.)

### Estrutura de cada `item` (REAL)

```
data            string  "YYYY-MM-DDT00:00:00.000"  — data contabil (CRITICO)
dataHora        string  "DD/MM/YYYY HH:MM:SS"       — timestamp do evento
valor           number  SEMPRE POSITIVO             — sinal NAO vem aqui (CRITICO)
tipoLancamento  string  "C" | "D" | "S"             — o SINAL (CRITICO)
                          C = credito/entrada
                          D = debito/saida
                          S = SALDO (snapshot, NAO e movimento → descartado)
documento       int|str|null
lancamento      int                                 — id estavel do lancamento
historico       object  { "codigo": "0497",         — codigo de historico bancario
                          "descricao": "TED - ..." } — texto do lancamento
contraparte     object                              — (chave SEM "rtida")
    nome                  string  (as vezes literal "null")
    inscricao             int|null  — CPF/CNPJ SEM zero-pad (PJ 14 / PF 11)
    tipoPessoa            "J" | "F" | "null"
    banco/agencia/conta   int|null  — dados bancarios DA CONTRAPARTE
    indicadorEnviadoRecebido  "R" | "E" | null
```

## Exemplo (real, anonimizado)

```json
{
  "extrato": [
    {
      "data": "2026-05-26T00:00:00.000",
      "dataHora": "26/05/2026 07:15:08",
      "valor": 1559348.82,
      "documento": 0,
      "lancamento": 50957269,
      "historico": { "codigo": "0497", "descricao": "TED - STR FORNECEDOR X" },
      "contraparte": {
        "nome": "FORNECEDOR X", "inscricao": 99888777000166,
        "tipoPessoa": "J", "indicadorEnviadoRecebido": "R"
      },
      "tipoLancamento": "C"
    },
    {
      "data": "2026-05-12T00:00:00.000",
      "dataHora": "12/05/2026 10:39:38",
      "valor": 667065.09,
      "lancamento": 50633207,
      "historico": { "codigo": "0123", "descricao": "TRANSFERENCIA A DEBITO ..." },
      "contraparte": { "nome": null, "inscricao": null, "tipoPessoa": null },
      "tipoLancamento": "D"
    },
    {
      "data": "2026-05-08T00:00:00.000",
      "valor": 2461.57,
      "lancamento": 24554012,
      "historico": { "codigo": "0099", "descricao": "SALDO C/C" },
      "contraparte": { "nome": "null", "inscricao": null, "tipoPessoa": "null" },
      "tipoLancamento": "S"
    }
  ]
}
```

## Gotchas

- **O sinal NAO vem no `valor`** (sempre positivo) — vem em `tipoLancamento`
  (C/D/S). O bug original (mapper pre-v0.5.0) procurava `tipo`/`natureza`,
  nao achava `tipoLancamento`, e caia no fallback "valor>0 → C": TUDO virava
  credito. Corrigido.
- **`tipoLancamento="S"` sao linhas de SALDO, nao movimentos** — descartadas
  aqui. Saldo de conta vive em `wh_saldo_bancario_diario` (endpoint
  `bank_account.balance`). Cuidado: "SAIDA" tambem comeca com S; o mapper so
  trata `"S"`/`"SALDO"` exatos como saldo, nao prefixo.
- **`historico` e um OBJETO `{codigo, descricao}`, nao string.** Mapeamento:
  `historico.descricao` (texto) → coluna **`descricao`** (e o campo
  pesquisavel + parte da business key); `historico.codigo` → coluna
  **`historico`** (codigo de historico bancario, ex.: 0497=TED, 0099=saldo,
  0123=transf a debito). O bug original gravava o dict cru stringificado em
  `historico` e deixava `descricao` nula — quebrava a UQ e o filtro por texto.
- **Doc da contraparte vem em `contraparte.inscricao`** (inteiro, sem zeros a
  esquerda) — mapper faz zero-pad por `tipoPessoa` (J→14, F→11 digitos). Chave
  e `contraparte` (sem "rtida"); `nome`/`tipoPessoa` podem vir como literal
  string `"null"` → tratados como None.
- **`valor` sempre absoluto no warehouse, sinal vai em `tipo`:** mapper faz
  `abs(valor)`. `valor + tipo` reconstroi o sinal.
- **Lancamentos sem `(data E valor E tipo C/D)` sao descartados.** Campos
  criticos.
- **`source_id` usa `lancamento`** (id estavel) quando presente:
  `bank_account_statement|{ua}|{ag}|{conta}|{data}|{lancamento}`. Fallback
  `sha16(item)` quando ausente. Re-fetch nao duplica (business key UQ).
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

| Campo (payload real)                | Tipo (payload)     | Coluna (silver)        | Tipo (silver)  | Transformacao                       |
| ----------------------------------- | ------------------ | ---------------------- | -------------- | ----------------------------------- |
| `data`                              | string ISO        | `data_lancamento`      | date           | _pick_data_lancamento (CRITICO)     |
| `dataHora`                          | "DD/MM/YYYY HH:MM:SS" | `data_movimento`    | date\|null     | _pick_data_movimento (fallback `data`) |
| `valor`                             | number (>0)       | `valor`                | numeric(18,2)  | abs(...) — sinal vai em `tipo`      |
| `tipoLancamento`                    | "C"/"D"/"S"       | `tipo`                 | text ("C"/"D") | _pick_tipo; **`S` (saldo) descartado** |
| `historico.codigo`                  | string            | `historico`            | text\|null     | codigo de historico bancario        |
| `historico.descricao`               | string            | `descricao`            | text\|null     | texto (pesquisavel + business key)  |
| `documento`                         | int\|str\|null    | `documento`            | text\|null     | normalize_str_or_none               |
| `contraparte.nome`                  | string\|"null"    | `contrapartida_nome`   | text\|null     | _clean_null ("null" string → None)  |
| `contraparte.inscricao`             | int\|null         | `contrapartida_doc`    | text\|null (14)| _format_doc (zero-pad por tipoPessoa) |
| `dataHora` (→ datetime)             | "DD/MM/YYYY HH:MM:SS" | (prov.) `source_updated_at` | timestamptz\|null | _parse_datahora           |
| _(nao presente no payload)_         | _                  | `banco_codigo`/`banco_nome` | null      | item nao traz banco proprio da conta |
| _(param)_ `tenant_id`                                 | _                      | `tenant_id`            | uuid           | passado pelo caller        |
| _(param)_ `unidade_administrativa_id`                 | _                      | `unidade_administrativa_id` | uuid      | passado pelo caller        |
| _(param)_ `agencia`                                   | _                      | `agencia`              | text           | passado pelo caller        |
| _(param)_ `conta`                                     | _                      | `conta`                | text           | passado pelo caller        |

### Source-id (proveniencia; UQ real e a business key)

```
bank_account_statement|{ua_id}|{agencia}|{conta}|{data_lancamento_iso}|{lancamento}
```

`lancamento` e o id estavel do lancamento na Singulare. Fallback `sha16(item)`
quando ausente. A UQ do silver e a business key explicita
(`uq_wh_extrato_bancario`: tenant, ua, agencia, conta, data_lancamento, valor,
tipo, descricao, contrapartida_doc) — source_id e so proveniencia.

## Historico

- **2026-05-26:** **payload real validado em prod + mapper corrigido
  (`qitech_adapter_v0.5.0`).** Bugs do schema inferido consertados: (1) sinal
  agora vem de `tipoLancamento` (era sempre 'C'); (2) linhas de saldo
  (`S`) descartadas; (3) `historico.{codigo,descricao}` split correto entre
  colunas `historico`/`descricao` (era dict cru); (4) doc da contraparte via
  `inscricao` com zero-pad; (5) source_id usa `lancamento`. Silver historico
  (65 linhas erradas) re-mapeado do raw imutavel via
  `scripts/remap_bank_account_statement.py`.
- **2026-05-01:** confirmado em teste real que endereco antigo
  `/v2/bank-account/statement/...` (sem `/conta-corrente/`) NAO existe —
  URL canonica e `/v2/conta-corrente/bank-account/statement/...`.
