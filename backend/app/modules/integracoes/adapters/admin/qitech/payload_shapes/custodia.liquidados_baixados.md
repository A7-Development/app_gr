# qitech.custodia.liquidados_baixados

> **canonical_table:** `wh_liquidacao_recebivel`
> **admin:** qitech
> **mapper:** [adapters/admin/qitech/mappers/liquidados_baixados.py](../mappers/liquidados_baixados.py)
> **schedule:** `daily_at 09:45` SP (sincrono via `/v2/fidc-custodia/*`)
> **upstream:** `GET /v2/fidc-custodia/report/liquidados-baixados/v2/{cnpj}/{data_inicial}/{data_final}` (handler em [custodia.py::sync_liquidados_baixados](../custodia.py))

## Visao geral

**Liquidacoes e baixas** de recebiveis ocorridas no periodo. Granularidade
por recebivel — uma linha por evento de saida da carteira (pagamento normal,
recompra, baixa por inadimplencia/recompra etc).

Familia `/v2/fidc-custodia/report/*` — **periodo no path** (D_i..D_f).
Scheduler default usa janela rolante **D-7..D-1** (mesma estrategia da
`aquisicao_consolidada`) — captura correcoes tardias da QiTech via upsert
idempotente. Backfill historico via REST proprio
(`POST /qitech/custodia/liquidados-baixados/sync`).

Coluna **`ajuste`** desta tabela e o heroi de varias analises de Controladoria
(ver memoria `project_dash_liquidacoes_urgencia` — stress operacional de
abril/2026 veio de um ajuste negativo grande em 13/04 invisivel ate
explicitarmos a coluna).

Schema validado contra sample real de 799 baixas (REALINVEST FIDC).

## Shape do payload

**Formato:** JSON. **Encoding:** UTF-8 (sem chaves acentuadas).
**Locale:** ISO-8601 para datas; numeros como int/float/string ou string com
virgula BR (`"12699,03"`) dependendo do campo — ver Gotchas.
**Envelope:**

```
{
  "liquidadosBaixados": [
    { ...item... },
    ...
  ]
}
```

### Estrutura de cada `item`

```
fundoCnpj                string CNPJ
fundoNome                string
cedente                  string  (nome — NAO "nomeCedente")
identificacaoCedente     string CNPJ  (NAO "cpfCnpjCedente")
sacado                   string  (nome — NAO "nomeSacado")
identificacaoSacado      string CNPJ
idRecebivel              string  (NAO int como em aquisicao_consolidada)
seuNumero                string
documento                string  (NAO "numeroDocumento" — equivalente)
numeroCorrespondente     string | null
tipoRecebivel            string
valorAquisicao           number | string BR "12699,03"  (tipo varia)
valorVencimento          number | string BR  (tipo varia)
valorPago                number | string BR
ajuste                   number | string BR  (positivo, negativo OU zero)
txAquisicao              number | string BR  (NAO "taxaAquisicao")
stRecebivel              string  (status: "LIQUIDADO", "BAIXADO", etc)
tipoMovimento            string  (ex.: "LIQUIDACAO", "RECOMPRA", "BAIXA")
dataDaPosicao            string ISO-8601  (data do evento = source_updated_at)
dataAquisicao            string ISO-8601  (data quando o fundo adquiriu)
dataVencimento           string ISO-8601
```

## Exemplo (anonimizado)

```json
{
  "liquidadosBaixados": [
    {
      "fundoCnpj": "12345678000190",
      "fundoNome": "FIDC EXEMPLO MULTISETORIAL",
      "cedente": "CEDENTE EXEMPLO SA",
      "identificacaoCedente": "55666777000188",
      "sacado": "SACADO EXEMPLO COMERCIO LTDA",
      "identificacaoSacado": "77888999000122",
      "idRecebivel": "987654321",
      "seuNumero": "CES12345",
      "documento": "DUP-2024-0001",
      "numeroCorrespondente": null,
      "tipoRecebivel": "DUPLICATA",
      "valorAquisicao": "3520,00",
      "valorVencimento": 3600.00,
      "valorPago": "3600,00",
      "ajuste": "0,00",
      "txAquisicao": "0,0185",
      "stRecebivel": "LIQUIDADO",
      "tipoMovimento": "LIQUIDACAO",
      "dataDaPosicao": "2026-02-22T00:00:00.000Z",
      "dataAquisicao": "2026-01-06T00:00:00.000Z",
      "dataVencimento": "2026-02-22T00:00:00.000Z"
    }
  ]
}
```

## Gotchas

- **`_parse_loose_decimal` (mapper proprio):** os campos
  `valorAquisicao`/`valorVencimento`/`valorPago`/`ajuste`/`txAquisicao` vem
  **as vezes como float** (`12699.03`) **as vezes como string locale BR**
  (`"12699,03"`). Heuristica do helper:
  - Tem virgula → formato BR (ponto = separador de milhar, removido).
  - Sem virgula → ISO/numero (ponto = decimal, preservado).
  - `None`/vazio → `Decimal("0")`.
  Falha silenciosa em `Decimal("0")` se conversao explodir — caller nao
  detecta corrupcao numerica.
- **`fundoCnpj` aqui e string** (em `aquisicao_consolidada` vem int).
- **`idRecebivel` aqui e string** (em `aquisicao_consolidada` vem int).
- **Chaves diferentes de `aquisicao_consolidada`:**
  - Cedente: `cedente` + `identificacaoCedente` (la: `cedente` +
    `cpfCnpjCedente`).
  - Sacado: `sacado` + `identificacaoSacado` (la: `nomeSacado` +
    `cpfCnpjSacado`).
  - Documento: `documento` (la: `numeroDocumento`).
  - Taxa: `txAquisicao` (la: `taxaAquisicao`).
- **`ajuste` pode ser negativo:** ajuste negativo significa que o fundo
  recebeu **menos** do que esperado naquela liquidacao (ex.: desconto
  cobrado). Em valor absoluto pode ser pequeno (centavos) ou
  significativo (R$ centenas de milhares). Caso real de 13/04/2026
  (REALINVEST) na memoria `project_dash_liquidacoes_urgencia`.
- **`numeroCorrespondente`:** string opcional — mapper canoniza
  `str(item.get(...) or "") or None`. Evita gravar `""` no banco.
- **`stRecebivel` vs `tipoMovimento`:** distintos.
  - `stRecebivel` = estado FINAL do recebivel (LIQUIDADO/BAIXADO).
  - `tipoMovimento` = evento que causou a saida (LIQUIDACAO/RECOMPRA/BAIXA).
  Combinacoes possiveis e ainda nao 100% mapeadas — investigar quando
  surgirem casos ambiguos.
- **Endpoint usa `/v2/` na URL** (`/liquidados-baixados/v2/...`). Versao v1
  existia antes — n+1 e descontinuada.

## Mapping campo do payload → coluna do silver (`wh_liquidacao_recebivel`)

| Campo (payload)        | Tipo (payload)             | Coluna (silver)        | Tipo (silver)  | Transformacao              |
| ---------------------- | -------------------------- | ---------------------- | -------------- | -------------------------- |
| `fundoCnpj`            | string CNPJ                | `fundo_doc`            | text           | _normalize_cnpj_any (fallback p/ param) |
| `fundoNome`            | string                     | `fundo_nome`           | text           | str(...)                   |
| `identificacaoCedente` | string CNPJ                | `cedente_doc`          | text           | _normalize_cnpj_any        |
| `cedente`              | string                     | `cedente_nome`         | text           | str(...)                   |
| `identificacaoSacado`  | string CNPJ                | `sacado_doc`           | text           | _normalize_cnpj_any        |
| `sacado`               | string                     | `sacado_nome`          | text           | str(...)                   |
| `idRecebivel`          | string                     | `id_recebivel`         | text           | str(...) — chave src       |
| `seuNumero`            | string                     | `seu_numero`           | text           | str(...)                   |
| `documento`            | string                     | `documento`            | text           | str(...)                   |
| `numeroCorrespondente` | string\|null               | `numero_correspondente` | text\|null    | str(... or "") or None     |
| `tipoRecebivel`        | string                     | `tipo_recebivel`       | text           | str(...)                   |
| `valorAquisicao`       | number\|string BR/ISO      | `valor_aquisicao`      | numeric(18,2)  | _parse_loose_decimal       |
| `valorVencimento`      | number\|string BR/ISO      | `valor_vencimento`     | numeric(18,2)  | _parse_loose_decimal       |
| `valorPago`            | number\|string BR/ISO      | `valor_pago`           | numeric(18,2)  | _parse_loose_decimal       |
| `ajuste`               | number\|string BR/ISO      | `ajuste`               | numeric(18,2)  | _parse_loose_decimal       |
| `txAquisicao`          | number\|string BR/ISO      | `taxa_aquisicao`       | numeric        | _parse_loose_decimal       |
| `stRecebivel`          | string                     | `st_recebivel`         | text           | str(...)                   |
| `tipoMovimento`        | string                     | `tipo_movimento`       | text           | str(...)                   |
| `dataDaPosicao`        | string ISO-8601            | `data_posicao`         | date           | parse_iso_or_none → date   |
| `dataDaPosicao`        | string ISO-8601            | (provenance) `source_updated_at` | timestamptz | parse_iso_or_none |
| `dataAquisicao`        | string ISO-8601            | `data_aquisicao`       | date           | parse_iso_or_none → date   |
| `dataVencimento`       | string ISO-8601            | `data_vencimento`      | date           | parse_iso_or_none → date   |

### Source-id (UQ no upsert)

```
{cnpj_fundo_norm}|{idRecebivel}|liq
```

Sufixo `|liq` distingue do `|aq` em `custodia.aquisicao_consolidada` —
mesmo `idRecebivel` aparece nas duas tabelas (recebivel adquirido e depois
liquidado).

## Historico

- **Sample real REALINVEST FIDC** (799 baixas) validou schema. 21 campos
  estaveis. Inconsistencias de tipo (`fundoCnpj`/`idRecebivel` string aqui
  vs int em `aquisicao_consolidada`) versionadas.
- **`_parse_loose_decimal`** criado em resposta a campos numericos que
  vinham as vezes float, as vezes string BR — comportamento da QiTech
  ainda inconsistente entre publicacoes.
- Preencher quando QiTech mudar payload.
