# qitech.custodia.detalhes_operacoes

> **canonical_table:** `wh_operacao_remessa`
> **admin:** qitech
> **mapper:** [adapters/admin/qitech/mappers/detalhes_operacoes.py](../mappers/detalhes_operacoes.py)
> **schedule:** `daily_at 10:00` SP (sincrono via `/v2/fidc-custodia/*`)
> **upstream:** `GET /v2/fidc-custodia/report/fundo/{cnpj}/data/{data}` (handler em [custodia.py::sync_detalhes_operacoes](../custodia.py))

## Visao geral

**Lotes CNAB** processados no dia — uma linha por arquivo de remessa que o
cedente enviou. Diferente dos outros endpoints `/v2/fidc-custodia/report/*`
(granularidade por recebivel), aqui granularidade e por **lote/operacao** —
varios recebiveis agregados em 1 linha de remessa.

Tipica relacao 1:N entre 1 linha desta tabela e N linhas em
`custodia.aquisicao_consolidada` (recebiveis individuais dentro do mesmo
arquivo CNAB).

Familia `/v2/fidc-custodia/report/*` — **data unica no path** (nao
periodo). Scheduler default usa D-1; backfill via REST proprio
(`POST /qitech/custodia/detalhes-operacoes/sync` com `data_importacao`).

## Shape do payload

**Formato:** JSON — **lista direta no root** (sem wrapper), diferente dos
outros endpoints da familia. Mapper aceita tambem dict com chave
`detalhesOperacoes`/`operacoes` defensivamente (se a QiTech mudar futuro).
**Encoding:** UTF-8.
**Locale:** ISO-8601 para datas; numeros como int/float/string; booleano via
`"SIM"`/`"NAO"`.
**Envelope:**

```json
[
  { ...item... },
  ...
]
```

Raw persistido em JSONB embrulha em `{"items": [...]}` para caber (ver
`custodia.py::_persist_raw`).

### Estrutura de cada `item`

```
cnpjFundo               string CNPJ
nomeFundo               string
cnpjGestor              string CNPJ
gestor                  string
documentoCedente        string CNPJ
nomeCedente             string
idOperacaoRecebivel     string (ou int — mapper normaliza)
nomeArquivo             string  (nome do arquivo CNAB processado)
nomeArquivoEntrada      string  (nome original do upload)
tipoRecebivel           string
remessa                 number | string  (valor total da remessa)
reembolso               number | string  (valor de reembolso)
recompra                number | string  (valor de recompra)
valorTotal              number | string  (total liquido = remessa + ajustes)
coobrigacao             string "SIM" | "NAO"
data                    string ISO-8601  (data do processamento = source_updated_at)
```

## Exemplo (anonimizado)

```json
[
  {
    "cnpjFundo": "12345678000190",
    "nomeFundo": "FIDC EXEMPLO MULTISETORIAL",
    "cnpjGestor": "98765432000110",
    "gestor": "GESTOR EXEMPLO LTDA",
    "documentoCedente": "55666777000188",
    "nomeCedente": "CEDENTE EXEMPLO SA",
    "idOperacaoRecebivel": "RES-2026-05-15-001",
    "nomeArquivo": "CES_20260515_001.rem",
    "nomeArquivoEntrada": "remessa_cedente_20260515.txt",
    "tipoRecebivel": "DUPLICATA",
    "remessa": 150000.00,
    "reembolso": 0.00,
    "recompra": 12500.00,
    "valorTotal": 137500.00,
    "coobrigacao": "NAO",
    "data": "2026-05-15T00:00:00.000Z"
  }
]
```

## Gotchas

- **Payload e lista direta no root** — `_extract_items` em outros mappers
  espera dict. Aqui, mapper aceita explicitamente `list | dict` e olha
  `detalhesOperacoes`/`operacoes` no segundo caso (defensivo).
- **Granularidade por LOTE, nao por recebivel.** 1 linha = 1 arquivo CNAB
  processado, agregando N duplicatas. Para detalhe do recebivel, JOIN
  contra `custodia.aquisicao_consolidada` por `cedente_doc` + janela de
  data.
- **`coobrigacao` como string `"SIM"`/`"NAO"`:** mapper helper
  `_parse_bool_sim_nao` faz `str(...).strip().upper() == "SIM"` →
  `True`/`False`. Vazio/None → `False`.
- **Chaves diferentes das outras tabelas custodia:**
  - Fundo: `cnpjFundo` + `nomeFundo` (em `aquisicao_consolidada`:
    `fundoCnpj` + `fundoNome`; em `movimento_aberto`: `docFundo` +
    `nomeFundo`).
  - Cedente: `documentoCedente` + `nomeCedente` (em
    `aquisicao_consolidada`: `cpfCnpjCedente` + `cedente`).
- **Sem datas de vencimento/aquisicao do recebivel** — sao agregados
  diferentes; a granularidade do recebivel mora em
  `custodia.aquisicao_consolidada` ou `custodia.liquidados_baixados`.
- **`valorTotal` vs soma de `remessa + reembolso + recompra`:** nao
  garantido bater por arredondamento — `valorTotal` e calculado pela
  QiTech, nao reconstrutivel localmente.
- **Empty/sem dados:** lista vazia → mapper devolve `[]`. Comum em dias
  sem remessa nova (fim de semana, feriado).
- **Lista vazia vs sem dado:** se a QiTech devolver 400/404 (envelope
  canonico de "sem dados"), `custodia.py::_fetch_json` trata e raw e
  gravado com http_status preservado para coverage classificar como
  NOT_PUBLISHED.

## Mapping campo do payload → coluna do silver (`wh_operacao_remessa`)

| Campo (payload)        | Tipo (payload)        | Coluna (silver)         | Tipo (silver)  | Transformacao              |
| ---------------------- | --------------------- | ----------------------- | -------------- | -------------------------- |
| `cnpjFundo`            | string CNPJ           | `fundo_doc`             | text           | _normalize_cnpj_any (fallback p/ param) |
| `nomeFundo`            | string                | `fundo_nome`            | text           | str(...)                   |
| `cnpjGestor`           | string CNPJ           | `gestor_doc`            | text           | _normalize_cnpj_any        |
| `gestor`               | string                | `gestor_nome`           | text           | str(...)                   |
| `documentoCedente`     | string CNPJ           | `cedente_doc`           | text           | _normalize_cnpj_any        |
| `nomeCedente`          | string                | `cedente_nome`          | text           | str(...)                   |
| `idOperacaoRecebivel`  | string\|int           | `id_operacao_recebivel` | text           | str(...) — chave src       |
| `nomeArquivo`          | string                | `nome_arquivo`          | text           | str(...)                   |
| `nomeArquivoEntrada`   | string                | `nome_arquivo_entrada`  | text           | str(...)                   |
| `tipoRecebivel`        | string                | `tipo_recebivel`        | text           | str(...)                   |
| `remessa`              | number\|string        | `remessa`               | numeric(18,2)  | to_decimal                 |
| `reembolso`            | number\|string        | `reembolso`             | numeric(18,2)  | to_decimal                 |
| `recompra`             | number\|string        | `recompra`              | numeric(18,2)  | to_decimal                 |
| `valorTotal`           | number\|string        | `valor_total`           | numeric(18,2)  | to_decimal                 |
| `coobrigacao`          | string "SIM"/"NAO"    | `coobrigacao`           | bool           | _parse_bool_sim_nao        |
| `data`                 | string ISO-8601       | `data_importacao`       | date           | parse_iso_or_none → date   |
| `data`                 | string ISO-8601       | (provenance) `source_updated_at` | timestamptz | parse_iso_or_none |

### Source-id (UQ no upsert)

```
{cnpj_fundo_norm}|{idOperacaoRecebivel}|rem
```

Sufixo `|rem` (de "remessa") distingue de `|aq`/`|liq`/`|abt` em outras
tabelas custodia. `idOperacaoRecebivel` e unico por lote — definido pela
QiTech, estavel entre re-fetches.

## Historico

- Preencher quando QiTech mudar payload.
