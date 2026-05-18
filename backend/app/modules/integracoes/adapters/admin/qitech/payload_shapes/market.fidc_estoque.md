# qitech.market.fidc_estoque

> **canonical_table:** `wh_estoque_recebivel`
> **admin:** qitech
> **mapper:** [adapters/admin/qitech/mappers/fidc_estoque.py](../mappers/fidc_estoque.py)
> **schedule:** `daily_at 09:00` SP (assíncrono — job + webhook)
> **upstream:** `POST /v2/queue/scheduler/report/fidc-estoque` → job → callback `POST /webhooks/qitech/job-callback` com `fileLink` (CSV em S3 presigned)

## Visão geral

Posição consolidada da carteira de recebíveis do FIDC numa data de referência
(D-1). É o relatório com **maior volume** do catálogo QiTech — N linhas onde
N = quantidade de recebíveis cedidos vivos no fundo na data alvo.

Fluxo **assíncrono** (único do catálogo): nosso adapter dispara um job via
`POST /v2/queue/scheduler/report/fidc-estoque`, recebe um `jobId`. A QiTech
processa entre 8h-9h SP, e quando termina chama nosso webhook
(`/webhooks/qitech/job-callback`) com o link S3 do CSV. Nós baixamos, parseamos
e gravamos.

Por causa do assincronismo, o reconciler trata este endpoint com
`tolerance=2 dias úteis` / `give_up=7` (mais apertado que market.* síncronos)
— pendência longa de job assíncrono trava retry do reconciler.

## Shape do payload

**Formato:** CSV separador `;`, encoding pode ser UTF-8 ou cp1252 (latim-1).
**Locale:** BR — vírgula decimal, dd/mm/yyyy, "SIM"/"NAO".
**Headers:** 30 colunas fixas. Validados como `_EXPECTED_HEADER` no mapper.

### Estrutura (todas as 30 colunas)

```
nomeFundo;docFundo;dataFundo;
nomeGestor;docGestor;
nomeOriginador;docOriginador;
nomeCedente;docCedente;
nomeSacado;docSacado;
seuNumero;numeroDocumento;tipoRecebivel;
valorNominal;valorPresente;valorAquisicao;valorPdd;faixaPdd;
dataReferencia;dataVencimentoOriginal;dataVencimentoAjustada;
dataEmissao;dataAquisicao;
prazo;prazoAnual;
situacaoRecebivel;
taxaCessao;taxaRecebivel;coobrigacao
```

## Exemplo (anonimizado)

```csv
nomeFundo;docFundo;dataFundo;nomeGestor;docGestor;nomeOriginador;docOriginador;nomeCedente;docCedente;nomeSacado;docSacado;seuNumero;numeroDocumento;tipoRecebivel;valorNominal;valorPresente;valorAquisicao;valorPdd;faixaPdd;dataReferencia;dataVencimentoOriginal;dataVencimentoAjustada;dataEmissao;dataAquisicao;prazo;prazoAnual;situacaoRecebivel;taxaCessao;taxaRecebivel;coobrigacao
FIDC EXEMPLO MULTISETORIAL;12.345.678/0001-90;15/03/2024;GESTOR EXEMPLO LTDA;98.765.432/0001-10;ORIGINADOR EXEMPLO SA;11.222.333/0001-44;CEDENTE EXEMPLO SA;55.666.777/0001-88;SACADO EXEMPLO COMERCIO LTDA;77.888.999/0001-22;CES12345;DUP-2024-0001;DUPLICATA;3600,00;3540,12;3520,00;0,00;a;13/05/2026;30/05/2026;30/05/2026;13/04/2026;15/04/2026;47;0,128767;VINCENDO;0,0185;0,0205;NAO
```

## Gotchas

- **`valorPdd` + `faixaPdd`:** PDD em R$ e faixa contábil (`a`/`b`/`c`/`d`/`wop`).
  `faixaPdd` é string crua — armazenada sem conversão.
- **CNPJ formatado:** `42.449.234/0001-60` no payload → normalizado para
  `42449234000160` (digits-only) no silver via `_normalize_cnpj`.
- **Decimais BR:** `"3600,00"` → `Decimal("3600.00")`. Vazio/None → `Decimal("0")`.
  Suporta separador de milhar (`1.234,56`) caso a QiTech mude um dia.
- **Datas vazias:** `dataEmissao` pode vir vazio em recebíveis de fluxo
  específico → mapper devolve `None`.
- **Booleanos:** `coobrigacao` é `"SIM"`/`"NAO"` (case-insensitive).
  Vazio/null → `False`.
- **`dataReferencia` no CSV vs `data_referencia` no banco:** o silver guarda
  a data **do parâmetro** (data alvo do relatório), não a do CSV. Defesa
  contra divergência de TZ ou ajuste pela QiTech.
- **Linhas sem `seuNumero`:** filtradas (linhas vazias ou malformadas que
  `DictReader` pode devolver).
- **CSV vazio (só header):** mapper retorna `[]`. Não é erro — apenas
  significa "fundo sem carteira nessa data".

## Mapping campo do payload → coluna do silver (`wh_estoque_recebivel`)

| Campo (payload)          | Tipo (payload)     | Coluna (silver)            | Tipo (silver)  | Transformação         |
| ------------------------ | ------------------ | -------------------------- | -------------- | --------------------- |
| `nomeFundo`              | string             | `fundo_nome`               | text           | strip                 |
| `docFundo`               | string CNPJ fmt    | `fundo_doc`                | text           | _normalize_cnpj       |
| `dataFundo`              | string dd/mm/yyyy  | `data_fundo`               | date           | _parse_date_br        |
| `nomeGestor`             | string             | `gestor_nome`              | text           | strip                 |
| `docGestor`              | string CNPJ fmt    | `gestor_doc`               | text           | _normalize_cnpj       |
| `nomeOriginador`         | string             | `originador_nome`          | text           | strip                 |
| `docOriginador`          | string CNPJ fmt    | `originador_doc`           | text           | _normalize_cnpj       |
| `nomeCedente`            | string             | `cedente_nome`             | text           | strip                 |
| `docCedente`             | string CNPJ fmt    | `cedente_doc`              | text           | _normalize_cnpj       |
| `nomeSacado`             | string             | `sacado_nome`              | text           | strip                 |
| `docSacado`              | string CNPJ fmt    | `sacado_doc`               | text           | _normalize_cnpj       |
| `seuNumero`              | string             | `seu_numero`               | text           | strip (filtra vazio)  |
| `numeroDocumento`        | string             | `numero_documento`         | text           | strip                 |
| `tipoRecebivel`          | string             | `tipo_recebivel`           | text           | strip                 |
| `valorNominal`           | string "3600,00"   | `valor_nominal`            | numeric(18,2)  | _parse_decimal_br     |
| `valorPresente`          | string "3540,12"   | `valor_presente`           | numeric(18,2)  | _parse_decimal_br     |
| `valorAquisicao`         | string "3520,00"   | `valor_aquisicao`          | numeric(18,2)  | _parse_decimal_br     |
| `valorPdd`               | string "0,00"      | `valor_pdd`                | numeric(18,2)  | _parse_decimal_br     |
| `faixaPdd`               | string "a"/"b"/... | `faixa_pdd`                | text           | strip                 |
| `dataVencimentoOriginal` | string dd/mm/yyyy  | `data_vencimento_original` | date           | _parse_date_br        |
| `dataVencimentoAjustada` | string dd/mm/yyyy  | `data_vencimento_ajustada` | date           | _parse_date_br        |
| `dataEmissao`            | string dd/mm/yyyy  | `data_emissao`             | date           | _parse_date_br        |
| `dataAquisicao`          | string dd/mm/yyyy  | `data_aquisicao`           | date           | _parse_date_br        |
| `prazo`                  | string int         | `prazo`                    | int            | _parse_int_or_zero    |
| `prazoAnual`             | string "0,128767"  | `prazo_anual`              | numeric        | _parse_decimal_br     |
| `situacaoRecebivel`      | string             | `situacao_recebivel`       | text           | strip                 |
| `taxaCessao`             | string "0,0185"    | `taxa_cessao`              | numeric        | _parse_decimal_br     |
| `taxaRecebivel`          | string "0,0205"    | `taxa_recebivel`           | numeric        | _parse_decimal_br     |
| `coobrigacao`            | string "SIM"/"NAO" | `coobrigacao`              | bool           | _parse_bool_br        |
| _(param)_ `data_ref`     | _                  | `data_referencia`          | date           | passado pelo caller   |

### Source-id (UQ no upsert)

```
{fundo_doc}|{cedente_doc}|{seu_numero}|{numero_documento}|{data_ref_iso}
```

Inclui `cedente_doc` porque um mesmo `seuNumero` pode existir em diferentes
cedentes (numeração de duplicatas é por cedente).

## Histórico

- **2026-04-25:** schema confirmado contra sample real REALINVEST FIDC
  (data 2026-01-08). 30 colunas estáveis.
- **2026-05-13:** promovido de `on_demand` para `daily_at 09:00` (QiTech
  informou que processamento do fundo termina entre 8h-9h SP). Reconciler
  cobre retry com cooldown.
