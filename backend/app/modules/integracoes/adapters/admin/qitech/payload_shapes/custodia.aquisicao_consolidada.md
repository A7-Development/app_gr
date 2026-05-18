# qitech.custodia.aquisicao_consolidada

> **canonical_table:** `wh_aquisicao_recebivel`
> **admin:** qitech
> **mapper:** [adapters/admin/qitech/mappers/aquisicao_consolidada.py](../mappers/aquisicao_consolidada.py)
> **schedule:** `daily_at 09:30` SP (sincrono via `/v2/fidc-custodia/*`)
> **upstream:** `GET /v2/fidc-custodia/report/aquisicao-consolidada/{cnpj}/{data_inicial}/{data_final}` (handler em [custodia.py::sync_aquisicao_consolidada](../custodia.py))

## Visao geral

Cessoes (recebiveis) **adquiridas no periodo** pelo FIDC — granularidade por
recebivel individual. Cada linha representa uma duplicata/CCB/NP que o fundo
comprou de um cedente naquela janela.

Familia `/v2/fidc-custodia/report/*` — **periodo no path** (D_i..D_f). O job
scheduler default usa janela rolante **D-7..D-1** (ver `endpoint_catalog.py`)
para capturar correcoes tardias da QiTech via upsert idempotente. Backfill
historico via REST proprio (`POST /qitech/custodia/aquisicao-consolidada/sync`)
com `data_inicial`/`data_final` explicitos.

Granularidade complementar a `custodia.liquidados_baixados` (mesma estrutura
de recebivel, fato diferente): aquisicao = entrada da cessao na carteira;
liquidacao/baixa = saida.

Schema validado contra sample real de 583 cessoes (REALINVEST FIDC, periodo
2026-01-01..2026-01-08).

## Shape do payload

**Formato:** JSON. **Encoding:** UTF-8 (sem chaves acentuadas — diferente da
familia `/netreport/*`).
**Locale:** ISO-8601 para datas; numeros como int/float/string.
**Envelope:**

```
{
  "aquisicaoConsolidada": [
    { ...item... },
    ...
  ]
}
```

### Estrutura de cada `item`

```
fundoCnpj            int | string  (CNPJ — inconsistencia documentada, ver Gotchas)
fundoNome            string
cpfCnpjCedente       string CNPJ  (ou ja sem pontuacao)
cedente              string  (nome do cedente; NOTA: chave e "cedente", nao "nomeCedente")
cpfCnpjSacado        string CNPJ
nomeSacado           string
idRecebivel          int | string  (chave de source_id; tipo varia)
seuNumero            string
numeroDocumento      string
tipoRecebivel        string  (ex.: "DUPLICATA", "CCB", "NP")
valorCompra          number | string
valorVencimento      number | string
prazoRecebivel       int | string
taxaAquisicao        number | string
dataDaPosicao        string ISO-8601  (data da aquisicao = source_updated_at)
dataVencimento       string ISO-8601
```

## Exemplo (anonimizado)

```json
{
  "aquisicaoConsolidada": [
    {
      "fundoCnpj": 12345678000190,
      "fundoNome": "FIDC EXEMPLO MULTISETORIAL",
      "cpfCnpjCedente": "55666777000188",
      "cedente": "CEDENTE EXEMPLO SA",
      "cpfCnpjSacado": "77888999000122",
      "nomeSacado": "SACADO EXEMPLO COMERCIO LTDA",
      "idRecebivel": 987654321,
      "seuNumero": "CES12345",
      "numeroDocumento": "DUP-2024-0001",
      "tipoRecebivel": "DUPLICATA",
      "valorCompra": 352000,
      "valorVencimento": 360000,
      "prazoRecebivel": 47,
      "taxaAquisicao": 0.0185,
      "dataDaPosicao": "2026-01-06T00:00:00.000Z",
      "dataVencimento": "2026-02-22T00:00:00.000Z"
    }
  ]
}
```

## Gotchas

- **`fundoCnpj` tipo varia:** aqui pode vir `int` (`42449234000160`); em
  `custodia.liquidados_baixados` vem `string` (`"42449234000160"`).
  `_normalize_cnpj_any` aceita ambos (int → `zfill(14)`, str → digits-only).
- **`idRecebivel` tipo varia:** aqui pode vir `int`; em
  `liquidados_baixados` vem `string`. Convertido sempre via `str(...)` para
  o DB.
- **Chaves sem acento, mas inconsistentes com outras familias:** aqui o
  cedente vem em `cedente` + `cpfCnpjCedente`; em `liquidados_baixados` vem
  em `cedente` + `identificacaoCedente`; em `detalhes_operacoes` vem em
  `nomeCedente` + `documentoCedente`. Cada endpoint inventou sua propria
  convencao.
- **`fundoCnpj` no payload pode estar vazio:** mapper faz fallback para o
  `cnpj_fundo` passado por param (`_normalize_cnpj_any(item.get(...)) or
  cnpj_fundo_norm`).
- **`prazoRecebivel` como string:** `int(item.get("prazoRecebivel") or 0)` —
  vazio/None vira `0`. Cuidado: zero pode ser legitimo OU pode ser "campo
  ausente". Hoje nao distinguimos.
- **`taxaAquisicao`:** ja vem em decimal (`0.0185` = 1.85% a.m.), nao
  precisa de divisao.
- **⚠️ `valorCompra` e `valorVencimento` vem em CENTAVOS (int):** divergencia
  confirmada em 2026-05-18 cruzando com `wh_estoque_recebivel` mesmo titulo
  (razao exata 100x). Mapper aplica `_centavos_to_reais` (= `to_decimal / 100`)
  antes de gravar. Outros endpoints da mesma administradora usam float ISO
  ou string BR — incoerencia interna da QiTech, documentada aqui. Se a
  QiTech um dia migrar pra reais, revisar mapper + reprocessar wh_aquisicao_recebivel
  do raw.
- **Datas ISO-8601 com `Z`:** mapper extrai `.date()` — hora descartada.
- **Empty/sem dados:** `aquisicaoConsolidada` vazio/ausente → mapper devolve
  `[]`. `_generic_sync` em `custodia.py` trata HTTP 400/404 como envelope
  canonico de "sem dados", grava raw e coverage marca NOT_PUBLISHED.
- **Janela rolante e upsert:** scheduler default re-executa D-7..D-1 a cada
  dia → recebiveis adquiridos em D-7 sao re-fetchados por 7 dias e
  upsertados via `source_id`. Permite captar correcoes tardias do
  custodiante (raras, mas existem).

## Mapping campo do payload → coluna do silver (`wh_aquisicao_recebivel`)

| Campo (payload)    | Tipo (payload)         | Coluna (silver)     | Tipo (silver)  | Transformacao                |
| ------------------ | ---------------------- | ------------------- | -------------- | ---------------------------- |
| `fundoCnpj`        | int\|string CNPJ       | `fundo_doc`         | text           | _normalize_cnpj_any (fallback p/ param) |
| `fundoNome`        | string                 | `fundo_nome`        | text           | str(...)                     |
| `cpfCnpjCedente`   | string CNPJ            | `cedente_doc`       | text           | _normalize_cnpj_any          |
| `cedente`          | string                 | `cedente_nome`      | text           | str(...)                     |
| `cpfCnpjSacado`    | string CNPJ            | `sacado_doc`        | text           | _normalize_cnpj_any          |
| `nomeSacado`       | string                 | `sacado_nome`       | text           | str(...)                     |
| `idRecebivel`      | int\|string            | `id_recebivel`      | text           | str(...) — chave src         |
| `seuNumero`        | string                 | `seu_numero`        | text           | str(...)                     |
| `numeroDocumento`  | string                 | `numero_documento`  | text           | str(...)                     |
| `tipoRecebivel`    | string                 | `tipo_recebivel`    | text           | str(...)                     |
| `valorCompra`      | int (centavos)         | `valor_compra`      | numeric(18,2)  | _centavos_to_reais (÷ 100)   |
| `valorVencimento`  | int (centavos)         | `valor_vencimento`  | numeric(18,2)  | _centavos_to_reais (÷ 100)   |
| `prazoRecebivel`   | int\|string            | `prazo_recebivel`   | int            | int(... or 0)                |
| `taxaAquisicao`    | number\|string         | `taxa_aquisicao`    | numeric        | to_decimal                   |
| `dataDaPosicao`    | string ISO-8601        | `data_aquisicao`    | date           | parse_iso_or_none → date     |
| `dataDaPosicao`    | string ISO-8601        | (provenance) `source_updated_at` | timestamptz | parse_iso_or_none |
| `dataVencimento`   | string ISO-8601        | `data_vencimento`   | date           | parse_iso_or_none → date     |

### Source-id (UQ no upsert)

```
{cnpj_fundo_norm}|{idRecebivel}|aq
```

Sufixo `|aq` distingue do `|liq` em `custodia.liquidados_baixados` —
mesmo `idRecebivel` pode existir nas duas tabelas (uma cessao adquirida e
depois liquidada). `cnpj_fundo` normalizado via `_normalize_cnpj_any` em
ambos os lados para defender contra drift de formato vindo do payload.

## Historico

- **Sample real REALINVEST FIDC** (583 cessoes, periodo 2026-01-01..08)
  validou schema. 17 campos estaveis. Inconsistencias de tipo
  (`fundoCnpj`/`idRecebivel`) versionadas no docstring do mapper.
- Preencher quando QiTech mudar payload.
